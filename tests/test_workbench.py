"""Public seams for the Product 0.6.1 source-authoritative Workbench slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from officecli_html_to_pptx import cli
from officecli_html_to_pptx import check_author_html
from officecli_html_to_pptx.protocol import Artifact, result
from officecli_html_to_pptx.workbench import WorkbenchSession


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _start(
    path: Path,
    recovery_root: Path,
    *,
    output_root: Path | None = None,
) -> tuple[WorkbenchSession, object, threading.Thread]:
    session = WorkbenchSession.open(
        path,
        recovery_root=recovery_root,
        output_root=output_root,
    )
    startup = session.start()
    thread = threading.Thread(target=session.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        if session.is_running:
            break
        time.sleep(0.01)
    return session, startup, thread


def _request(
    startup: object,
    method: str,
    path: str,
    *,
    token: str | None,
    session_id: str | None = None,
    payload: dict | None = None,
) -> tuple[int, dict]:
    url = startup.base_url + path  # type: ignore[attr-defined]
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token is not None:
        headers["X-Workbench-Token"] = token
    if session_id is not None:
        headers["X-Workbench-Session"] = session_id
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _stop(session: WorkbenchSession, thread: threading.Thread) -> None:
    session.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_workbench_cli_emits_one_clean_json_startup_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "候选.html"
    source.write_bytes("<!doctype html><p>中文 🙂</p>".encode("utf-8"))
    monkeypatch.setattr("officecli_html_to_pptx.workbench.webbrowser.open", lambda _: False)
    monkeypatch.setattr(WorkbenchSession, "serve_forever", lambda self: None)

    code = cli.main(["workbench", str(source), "--json", "--no-browser"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    envelope = json.loads(lines[0])
    assert envelope["command"] == "workbench"
    assert envelope["status"] == "PASS"
    assert envelope["data"]["ready"] is True
    assert envelope["data"]["host"] == "127.0.0.1"
    assert envelope["data"]["source_sha256"] == _sha256_bytes(source.read_bytes())
    assert envelope["data"]["session_token"]
    assert "url" in envelope["data"]


def test_workbench_http_session_requires_token_and_same_session_mutations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "author.html"
    original = "<!doctype html><p>原始</p>"
    source.write_bytes(original.encode("utf-8"))
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, unauthorized = _request(startup, "GET", "/api/session", token=None)
        assert status == 401
        assert unauthorized["error"]["code"] == "session_token_required"

        status, loaded = _request(startup, "GET", "/api/session", token=startup.token)
        assert status == 200
        assert loaded["document"]["text"] == original
        assert loaded["document"]["state"] == "CLEAN"

        status, denied = _request(
            startup,
            "POST",
            "/api/draft",
            token="a-different-session-token",
            payload={"text": "<p>不应写入</p>"},
        )
        assert status == 401
        assert denied["error"]["code"] == "session_token_invalid"
        assert source.read_text(encoding="utf-8") == original
    finally:
        _stop(session, thread)


def test_workbench_save_accepts_invalid_candidate_and_preserves_exact_utf8(
    tmp_path: Path,
) -> None:
    source = tmp_path / "author.html"
    original_bytes = "<!doctype html>\r\n<p>初始 — 🙂</p>\r\n".encode("utf-8")
    source.write_bytes(original_bytes)
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        candidate = "<html><canvas>未通过 Contract</canvas></html>\n"
        status, draft = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": candidate},
        )
        assert status == 200
        assert draft["document"]["state"] == "DIRTY"
        assert draft["document"]["draft_sha256"] == _sha256_bytes(candidate.encode("utf-8"))

        status, saved = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={
                "expected_sha256": _sha256_bytes(original_bytes),
                "text": candidate,
            },
        )
        assert status == 200
        assert saved["ok"] is True
        assert saved["document"]["state"] == "SAVED"
        assert saved["document"]["contract_status"] == "UNKNOWN"
        assert source.read_bytes() == candidate.encode("utf-8")
        assert saved["document"]["source_sha256"] == _sha256_bytes(source.read_bytes())
    finally:
        _stop(session, thread)


def test_workbench_conflict_is_atomic_and_preserves_draft(
    tmp_path: Path,
) -> None:
    source = tmp_path / "author.html"
    original = "<p>one</p>\n"
    external = "<p>external edit</p>\n"
    draft = "<p>my draft</p>\n"
    source.write_bytes(original.encode("utf-8"))
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        original_sha = _sha256_bytes(original.encode("utf-8"))
        _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
        source.write_bytes(external.encode("utf-8"))

        status, conflict = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": original_sha, "text": draft},
        )
        assert status == 409
        assert conflict["error"]["code"] == "CONFLICT"
        assert conflict["document"]["state"] == "CONFLICT"
        assert conflict["document"]["text"] == draft
        assert source.read_bytes() == external.encode("utf-8")

        status, loaded = _request(startup, "GET", "/api/session", token=startup.token)
        assert status == 200
        assert loaded["document"]["text"] == draft
        assert loaded["document"]["disk_sha256"] == _sha256_bytes(external.encode("utf-8"))
    finally:
        _stop(session, thread)


def test_workbench_rejects_external_sha_even_when_client_submits_current_disk_hash(
    tmp_path: Path,
) -> None:
    """The browser cannot turn an external edit into an accepted Save."""
    source = tmp_path / "author.html"
    original = "<p>one</p>\n"
    external = "<p>external edit</p>\n"
    draft = "<p>my draft</p>\n"
    source.write_bytes(original.encode("utf-8"))
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
        source.write_bytes(external.encode("utf-8"))
        external_sha = _sha256_bytes(external.encode("utf-8"))

        status, conflict = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": external_sha, "text": draft},
        )

        assert status == 409
        assert conflict["error"]["code"] == "CONFLICT"
        assert conflict["document"]["state"] == "CONFLICT"
        assert conflict["document"]["text"] == draft
        assert source.read_bytes() == external.encode("utf-8")
    finally:
        _stop(session, thread)


def test_workbench_mutations_require_current_session_id_in_addition_to_token(
    tmp_path: Path,
) -> None:
    source = tmp_path / "author.html"
    original = "<p>one</p>\n"
    draft = "<p>draft</p>\n"
    source.write_bytes(original.encode("utf-8"))
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        original_sha = _sha256_bytes(original.encode("utf-8"))
        for method, path, payload in (
            ("POST", "/api/draft", {"text": draft}),
            ("POST", "/api/save", {"expected_sha256": original_sha, "text": draft}),
            ("POST", "/api/shutdown", None),
        ):
            status, denied = _request(
                startup,
                method,
                path,
                token=startup.token,
                payload=payload,
            )
            assert status == 401
            assert denied["error"]["code"] == "session_id_required"

        status, denied = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id="wrong-session",
            payload={"text": draft},
        )
        assert status == 401
        assert denied["error"]["code"] == "session_id_invalid"
        assert source.read_bytes() == original.encode("utf-8")

        status, accepted = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
        assert status == 200
        assert accepted["document"]["state"] == "DIRTY"
    finally:
        _stop(session, thread)


def test_workbench_recovery_is_separate_and_never_auto_committed(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    original = "<p>saved</p>"
    draft = "<p>recover me 中文</p>"
    recovery_root = tmp_path / "recovery"
    source.write_bytes(original.encode("utf-8"))
    first, startup, thread = _start(source, recovery_root)
    try:
        _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft},
        )
    finally:
        _stop(first, thread)

    second, second_startup, second_thread = _start(source, recovery_root)
    try:
        status, loaded = _request(second_startup, "GET", "/api/session", token=second_startup.token)
        assert status == 200
        assert loaded["document"]["text"] == original
        assert loaded["document"]["state"] == "CLEAN"
        assert loaded["recovery"]["available"] is True

        status, restored = _request(
            second_startup,
            "POST",
            "/api/recovery/restore",
            token=second_startup.token,
            session_id=second_startup.session_id,
        )
        assert status == 200
        assert restored["document"]["text"] == draft
        assert restored["document"]["state"] == "DIRTY"
        assert source.read_text(encoding="utf-8") == original
    finally:
        _stop(second, second_thread)


def test_workbench_rejects_asset_traversal(tmp_path: Path) -> None:
    source = tmp_path / "author.html"
    outside = tmp_path.parent / "outside.txt"
    source.write_text("<p>source</p>", encoding="utf-8")
    outside.write_text("secret", encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, payload = _request(
            startup,
            "GET",
            "/api/asset/../outside.txt",
            token=startup.token,
        )
        assert status in {400, 403, 404}
        assert payload["ok"] is False
        assert outside.read_text(encoding="utf-8") == "secret"
    finally:
        _stop(session, thread)


def test_workbench_loads_source_larger_than_old_product_cap_without_rewrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large.html"
    original = ("<p>中文🙂</p>" + ("x" * (10 * 1024 * 1024))).encode("utf-8")
    source.write_bytes(original)

    session = WorkbenchSession.open(source, recovery_root=tmp_path / "recovery")
    try:
        assert session.document.text.encode("utf-8") == original
        assert session.document.source_sha256 == _sha256_bytes(original)
    finally:
        session.shutdown()


def test_workbench_draft_check_matches_file_check_envelope(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate.html"
    candidate = """<!doctype html>
<html><head><style>.slide { width: 1920px; height: 1080px; }</style></head>
<body><div class="slide"><canvas>unsupported</canvas></div></body></html>
"""
    source.write_text(candidate, encoding="utf-8")
    file_result = check_author_html(source)
    assert file_result.status == "BLOCK"

    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload=None,
        )

        assert status == 200
        assert checked["ok"] is True
        assert checked["check"]["contract"] == file_result.data["contract"]
        assert checked["check"]["diagnostics"] == [
            item.as_dict() for item in file_result.diagnostics
        ]
        assert checked["check"]["command"] == "check"
        assert checked["check"]["status"] == file_result.status
        assert checked["check"]["data"] == file_result.data
        assert checked["check"]["checked_sha256"] == _sha256_bytes(source.read_bytes())
        assert checked["document"]["contract_status"] == "BLOCK"
        assert checked["check"]["source_navigation"]
        assert all(
            item["status"] == "unmapped"
            for item in checked["check"]["source_navigation"]
        )
    finally:
        _stop(session, thread)


def test_workbench_editor_exposes_check_build_and_diagnostic_state_controls(
    tmp_path: Path,
) -> None:
    source = tmp_path / "author.html"
    source.write_text("<p>source</p>", encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        with urlopen(startup.base_url + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        assert 'id="check"' in page
        assert 'id="build"' in page
        assert 'id="diagnostics"' in page
        assert "/api/check" in page
        assert "/api/build" in page
        assert "navigation: unmapped" in page
    finally:
        _stop(session, thread)


def test_workbench_check_becomes_stale_after_any_draft_edit(tmp_path: Path) -> None:
    source = tmp_path / "candidate.html"
    checked_text = "<html><body><canvas>bad</canvas></body></html>"
    edited_text = checked_text.replace("bad", "changed")
    source.write_text(checked_text, encoding="utf-8")

    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": checked_text},
        )
        assert status == 200
        assert checked["document"]["contract_status"] == "BLOCK"
        assert checked["check"]["stale"] is False

        status, edited = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": edited_text},
        )
        assert status == 200
        assert edited["document"]["contract_status"] == "STALE"
        assert edited["document"]["contract_check"]["stale"] is True
        assert edited["document"]["contract_check"]["checked_sha256"] == _sha256_bytes(
            checked_text.encode("utf-8")
        )
    finally:
        _stop(session, thread)


def test_workbench_build_revision_blocks_dirty_or_unchecked_draft(tmp_path: Path) -> None:
    source = tmp_path / "candidate.html"
    source.write_text("<p>saved</p>", encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, _ = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": "<p>unsaved</p>"},
        )
        assert status == 200

        status, blocked = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload=None,
        )
        assert status == 409
        assert blocked["ok"] is False
        assert "DIRTY" in blocked["build"]["reasons"]
        assert "STALE_CHECK" in blocked["build"]["reasons"]
        assert list((tmp_path / ".officecli-workbench").glob("*.pptx")) == []
    finally:
        _stop(session, thread)


def test_workbench_can_save_contract_block_but_cannot_build_it(tmp_path: Path) -> None:
    source = tmp_path / "candidate.html"
    original = "<p>saved</p>"
    candidate = (
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><canvas>unsupported</canvas></div></body></html>"
    )
    source.write_text(original, encoding="utf-8")
    session, startup, thread = _start(source, tmp_path / "recovery")
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": candidate},
        )
        assert status == 200
        assert checked["check"]["contract"]["status"] == "BLOCK"

        status, saved = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={
                "expected_sha256": _sha256_bytes(original.encode("utf-8")),
                "text": candidate,
            },
        )
        assert status == 200
        assert saved["document"]["author_status"] == "CANDIDATE"
        assert saved["document"]["contract_status"] == "BLOCK"

        status, blocked = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 409
        assert blocked["build"]["reasons"] == ["CONTRACT_BLOCK"]
        assert any(item["code"] == "unsupported_visible_tag" for item in blocked["build"]["diagnostics"])
        assert source.read_text(encoding="utf-8") == candidate
    finally:
        _stop(session, thread)


def test_workbench_build_revision_uses_fixed_non_overwriting_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source_text = (
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><p>Author</p></div></body></html>"
    )
    source.write_text(source_text, encoding="utf-8")
    output_root = tmp_path / "fixed-output"
    calls: list[tuple[Path, Path]] = []

    async def fake_build(input_html: str | Path, output_pptx: str | Path):
        input_path = Path(input_html)
        output_path = Path(output_pptx)
        calls.append((input_path, output_path))
        output_path.write_bytes(b"fake pptx")
        output_path.with_suffix(".evidence").mkdir()
        return result(
            "build",
            "VISUAL_REVIEW_REQUIRED",
            artifacts={
                "pptx": Artifact(output_path, _sha256_bytes(output_path.read_bytes())),
                "evidence": Artifact(output_path.with_suffix(".evidence")),
            },
            data={
                "author_html": {
                    "path": str(input_path),
                    "sha256": _sha256_bytes(input_path.read_bytes()),
                }
            },
        )

    monkeypatch.setattr("officecli_html_to_pptx.workbench.build_author_html", fake_build)
    session, startup, thread = _start(
        source,
        tmp_path / "recovery",
        output_root=output_root,
    )
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        assert checked["document"]["author_status"] == "AUTHOR"

        status, rejected = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload={"output": str(tmp_path / "browser-chosen.pptx")},
        )
        assert status == 400
        assert rejected["error"]["code"] == "invalid_build"
        assert not (tmp_path / "browser-chosen.pptx").exists()

        for expected_name in ("author-r01.pptx", "author-r02.pptx"):
            status, built = _request(
                startup,
                "POST",
                "/api/build",
                token=startup.token,
                session_id=startup.session_id,
                payload={},
            )
            assert status == 200
            assert built["ok"] is True
            assert built["build"]["status"] == "VISUAL_REVIEW_REQUIRED"
            assert Path(built["build"]["target_pptx"]) == output_root / expected_name
            assert Path(built["build"]["target_evidence"]) == output_root / expected_name.replace(
                ".pptx", ".evidence"
            )
            assert built["build"]["artifact_pair_complete"] is True
    finally:
        _stop(session, thread)

    assert calls == [
        (source.resolve(), output_root / "author-r01.pptx"),
        (source.resolve(), output_root / "author-r02.pptx"),
    ]


def test_workbench_build_marks_concurrent_draft_edit_stale_without_rebinding_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source_text = (
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><p>Author</p></div></body></html>"
    )
    edited_text = source_text.replace("Author", "Edited while building")
    source.write_text(source_text, encoding="utf-8")
    output_root = tmp_path / "fixed-output"
    build_started = threading.Event()
    release_build = threading.Event()

    async def fake_build(input_html: str | Path, output_pptx: str | Path):
        input_path = Path(input_html)
        output_path = Path(output_pptx)
        build_started.set()
        assert release_build.wait(timeout=5)
        output_path.write_bytes(b"fake pptx")
        output_path.with_suffix(".evidence").mkdir()
        return result(
            "build",
            "VISUAL_REVIEW_REQUIRED",
            artifacts={
                "pptx": Artifact(output_path, _sha256_bytes(output_path.read_bytes())),
                "evidence": Artifact(output_path.with_suffix(".evidence")),
            },
            data={
                "author_html": {
                    "path": str(input_path),
                    "sha256": _sha256_bytes(input_path.read_bytes()),
                }
            },
        )

    monkeypatch.setattr("officecli_html_to_pptx.workbench.build_author_html", fake_build)
    session, startup, thread = _start(
        source,
        tmp_path / "recovery",
        output_root=output_root,
    )
    build_response: list[tuple[int, dict]] = []
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        initiating_sha = checked["document"]["source_sha256"]

        request_thread = threading.Thread(
            target=lambda: build_response.append(
                _request(
                    startup,
                    "POST",
                    "/api/build",
                    token=startup.token,
                    session_id=startup.session_id,
                    payload={},
                )
            ),
            daemon=True,
        )
        request_thread.start()
        assert build_started.wait(timeout=5)

        status, edited = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": edited_text},
        )
        assert status == 200
        assert edited["document"]["state"] == "DIRTY"
        release_build.set()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive()
        status, built = build_response[0]
        assert status == 200
        assert built["build"]["status"] == "STALE"
        assert built["build"]["stale"] is True
        assert built["build"]["initiating_sha256"] == initiating_sha
        assert built["build"]["current_draft_sha256"] == _sha256_bytes(
            edited_text.encode("utf-8")
        )
        assert built["build"]["result"]["data"]["author_html"]["sha256"] == initiating_sha
        assert built["build"]["artifact_pair_complete"] is True
        assert source.read_text(encoding="utf-8") == source_text
    finally:
        release_build.set()
        _stop(session, thread)


def test_workbench_rejects_save_while_building_and_preserves_build_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source.write_text(
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><p>Author</p></div></body></html>",
        encoding="utf-8",
    )
    source_text = source.read_text(encoding="utf-8")
    edited_text = source_text.replace("Author", "Edited while building")
    initiating_bytes = source.read_bytes()
    initiating_sha = _sha256_bytes(initiating_bytes)
    output_root = tmp_path / "fixed-output"
    build_started = threading.Event()
    release_build = threading.Event()
    delayed_input_sha: list[str] = []

    async def fake_build(input_html: str | Path, output_pptx: str | Path):
        input_path = Path(input_html)
        output_path = Path(output_pptx)
        build_started.set()
        assert release_build.wait(timeout=5)
        delayed_input_sha.append(_sha256_bytes(input_path.read_bytes()))
        output_path.write_bytes(b"fake pptx")
        output_path.with_suffix(".evidence").mkdir()
        return result(
            "build",
            "VISUAL_REVIEW_REQUIRED",
            artifacts={
                "pptx": Artifact(output_path, _sha256_bytes(output_path.read_bytes())),
                "evidence": Artifact(output_path.with_suffix(".evidence")),
            },
            data={
                "author_html": {
                    "path": str(input_path),
                    "sha256": delayed_input_sha[-1],
                }
            },
        )

    monkeypatch.setattr("officecli_html_to_pptx.workbench.build_author_html", fake_build)
    session, startup, thread = _start(
        source,
        tmp_path / "recovery",
        output_root=output_root,
    )
    build_response: list[tuple[int, dict]] = []
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        assert checked["document"]["source_sha256"] == initiating_sha

        request_thread = threading.Thread(
            target=lambda: build_response.append(
                _request(
                    startup,
                    "POST",
                    "/api/build",
                    token=startup.token,
                    session_id=startup.session_id,
                    payload=None,
                )
            ),
            daemon=True,
        )
        request_thread.start()
        assert build_started.wait(timeout=5)

        status, edited = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": edited_text},
        )
        assert status == 200
        assert edited["document"]["state"] == "DIRTY"

        status, rejected = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": initiating_sha, "text": edited_text},
        )
        assert status == 409
        assert rejected["error"]["code"] == "build_in_progress"
        assert rejected["document"]["text"] == edited_text
        assert source.read_bytes() == initiating_bytes

        release_build.set()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive()
        status, built = build_response[0]
        assert status == 200
        assert delayed_input_sha == [initiating_sha]
        assert built["build"]["status"] == "STALE"
        assert built["build"]["stale"] is True
        assert built["build"]["initiating_sha256"] == initiating_sha
        assert built["build"]["result"]["data"]["author_html"]["sha256"] == initiating_sha

        status, saved = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": initiating_sha, "text": edited_text},
        )
        assert status == 200
        assert saved["document"]["source_sha256"] == _sha256_bytes(edited_text.encode("utf-8"))
        assert source.read_text(encoding="utf-8") == edited_text
    finally:
        release_build.set()
        _stop(session, thread)


def test_workbench_build_failure_surfaces_diagnostics_without_artifact_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source_text = (
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><p>Author</p></div></body></html>"
    )
    source.write_text(source_text, encoding="utf-8")
    output_root = tmp_path / "fixed-output"

    # Use a real Diagnostic so the ordinary result envelope remains intact.
    async def failed_build(input_html: str | Path, output_pptx: str | Path):
        assert Path(input_html) == source.resolve()
        assert Path(output_pptx).parent == output_root.resolve()
        from officecli_html_to_pptx.protocol import Diagnostic

        return result(
            "build",
            "ERROR",
            diagnostics=(
                Diagnostic(
                    code="runtime_not_ready",
                    severity="error",
                    message="OfficeCLI runtime is not ready.",
                    blocking=True,
                ),
            ),
        )

    monkeypatch.setattr("officecli_html_to_pptx.workbench.build_author_html", failed_build)
    session, startup, thread = _start(
        source,
        tmp_path / "recovery",
        output_root=output_root,
    )
    try:
        status, checked = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        assert checked["document"]["author_status"] == "AUTHOR"

        status, failed = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 200
        assert failed["ok"] is True
        assert failed["build"]["status"] == "ERROR"
        assert failed["build"]["artifact_pair_complete"] is False
        assert failed["build"]["diagnostics"][0]["code"] == "runtime_not_ready"
        assert list(output_root.iterdir()) == []
    finally:
        _stop(session, thread)


def test_workbench_revision_allocator_skips_existing_pair_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "author.html"
    source_text = (
        "<html><head><style>.slide{width:1920px;height:1080px}</style></head>"
        "<body><div class='slide'><p>Author</p></div></body></html>"
    )
    source.write_text(source_text, encoding="utf-8")
    output_root = tmp_path / "fixed-output"
    output_root.mkdir()
    (output_root / "author-r01.pptx").write_bytes(b"existing")
    (output_root / "author-r02.evidence").mkdir()

    async def fake_build(input_html: str | Path, output_pptx: str | Path):
        output_path = Path(output_pptx)
        output_path.write_bytes(b"new")
        output_path.with_suffix(".evidence").mkdir()
        return result("build", "VISUAL_REVIEW_REQUIRED")

    monkeypatch.setattr("officecli_html_to_pptx.workbench.build_author_html", fake_build)
    session, startup, thread = _start(
        source,
        tmp_path / "recovery",
        output_root=output_root,
    )
    try:
        status, _ = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        status, built = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 200
        assert built["build"]["target_pptx"] == str(output_root / "author-r03.pptx")
        assert (output_root / "author-r01.pptx").read_bytes() == b"existing"
        assert (output_root / "author-r02.evidence").is_dir()
    finally:
        _stop(session, thread)
