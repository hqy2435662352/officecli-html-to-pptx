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
from officecli_html_to_pptx.workbench import WorkbenchSession


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _start(path: Path, recovery_root: Path) -> tuple[WorkbenchSession, object, threading.Thread]:
    session = WorkbenchSession.open(path, recovery_root=recovery_root)
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
    payload: dict | None = None,
) -> tuple[int, dict]:
    url = startup.base_url + path  # type: ignore[attr-defined]
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token is not None:
        headers["X-Workbench-Token"] = token
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
            payload={"text": draft},
        )
        source.write_bytes(external.encode("utf-8"))

        status, conflict = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
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
