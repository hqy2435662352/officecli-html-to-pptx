"""Run the installed Product 0.6.1 Workbench acceptance path for ticket #44.

The script intentionally exercises the public HTTP session boundary and the
existing build implementation. It stops at a pending visual review; the caller
must inspect every Comparison Image and invoke the public ``finalize`` command
explicitly. It is a focused acceptance runner, not an alternate compiler or a
pytest replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from officecli_html_to_pptx.workbench import WorkbenchSession


ROOT = Path(__file__).parents[1]
DEFAULT_CORPUS = ROOT / "tests" / "fixtures" / "v06_01_workbench_corpus.html"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _request(
    startup: object,
    method: str,
    path: str,
    *,
    token: str,
    session_id: str,
    payload: dict | None = None,
) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "X-Workbench-Token": token,
        "X-Workbench-Session": session_id,
    }
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(startup.base_url + path, data=body, headers=headers, method=method)  # type: ignore[attr-defined]
    try:
        with urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _serve(session: WorkbenchSession) -> threading.Thread:
    thread = threading.Thread(target=session.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if session.is_running:
            return thread
        time.sleep(0.01)
    raise RuntimeError("Workbench server did not enter its running state")


def _stop(session: WorkbenchSession, thread: threading.Thread) -> None:
    session.shutdown()
    thread.join(timeout=10)
    if thread.is_alive():
        raise RuntimeError("Workbench server did not shut down cleanly")


def _assert_conflict(source: Path, root: Path) -> None:
    recovery = root / "conflict-recovery"
    output = root / "conflict-output"
    original = source.read_bytes()
    draft = original.replace(b"Slide 1 - UTF-8", b"Slide 1 - conflict draft", 1)
    session = WorkbenchSession.open(source, recovery_root=recovery, output_root=output)
    thread = _serve(session)
    try:
        startup = session.startup
        base_sha = _sha256(original)
        status, _ = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft.decode("utf-8")},
        )
        assert status == 200
        source.write_bytes(b"external edit\n")
        status, payload = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": base_sha, "text": draft.decode("utf-8")},
        )
        assert status == 409
        assert payload["error"]["code"] == "CONFLICT"
        assert source.read_bytes() == b"external edit\n"
    finally:
        _stop(session, thread)


def run(source: Path, root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    conflict_source = root / "conflict.html"
    shutil.copyfile(source, conflict_source)
    _assert_conflict(conflict_source, root)

    input_html = root / "workbench.html"
    shutil.copyfile(source, input_html)
    original = input_html.read_bytes()
    recovery = root / "recovery"
    output = root / "output"
    session = WorkbenchSession.open(input_html, recovery_root=recovery, output_root=output)
    thread = _serve(session)
    try:
        startup = session.startup
        base_sha = _sha256(original)
        status, loaded = _request(
            startup,
            "GET",
            "/api/session",
            token=startup.token,
            session_id=startup.session_id,
        )
        assert status == 200
        assert loaded["document"]["source_sha256"] == base_sha

        source_text = original.decode("utf-8")
        status, preview = _request(
            startup,
            "POST",
            "/api/preview",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": source_text},
        )
        assert status == 200
        assert preview["preview"]["status"] == "CURRENT"
        assert preview["preview"]["aspect_ratio"] == "16:9"
        assert preview["preview"]["slide_count"] == 4
        kinds = {item["kind"] for item in preview["preview"]["source_map"].values()}
        assert {"text", "picture", "table", "shape", "chart", "localized-fallback"} <= kinds
        marker = next(iter(preview["preview"]["source_map"]))
        status, selection = _request(
            startup,
            "POST",
            "/api/preview/select",
            token=startup.token,
            session_id=startup.session_id,
            payload={"marker": marker, "revision": preview["preview"]["revision"]},
        )
        assert status == 200
        assert selection["selection"]["status"] == "mapped"

        draft_text = source_text.replace(
            "Slide 1 - UTF-8 / inline CSS / deterministic data image",
            "Slide 1 - edited / UTF-8 / inline CSS / deterministic data image",
            1,
        )
        draft_sha = _sha256(draft_text.encode("utf-8"))
        status, drafted = _request(
            startup,
            "POST",
            "/api/draft",
            token=startup.token,
            session_id=startup.session_id,
            payload={"text": draft_text},
        )
        assert status == 200
        assert drafted["document"]["draft_sha256"] == draft_sha

        status, draft_check = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 200
        assert draft_check["check"]["status"] == "PASS"
        assert draft_check["check"]["checked_sha256"] == draft_sha

        status, saved = _request(
            startup,
            "POST",
            "/api/save",
            token=startup.token,
            session_id=startup.session_id,
            payload={"expected_sha256": base_sha, "text": draft_text},
        )
        assert status == 200
        assert saved["document"]["source_sha256"] == draft_sha
        assert input_html.read_bytes() == draft_text.encode("utf-8")
        assert "data-workbench-marker" not in input_html.read_text(encoding="utf-8")

        status, exact_check = _request(
            startup,
            "POST",
            "/api/check",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 200
        assert exact_check["check"]["status"] == "PASS"
        assert exact_check["check"]["checked_sha256"] == draft_sha

        status, built = _request(
            startup,
            "POST",
            "/api/build",
            token=startup.token,
            session_id=startup.session_id,
            payload={},
        )
        assert status == 200, built
        build = built["build"]
        assert build["artifact_pair_complete"] is True
        pptx = Path(build["target_pptx"])
        evidence = Path(build["target_evidence"])
        assert pptx.is_file() and evidence.is_dir()

        result_payload = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        assert result_payload["author_html"]["sha256"] == draft_sha
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        readback = json.loads((evidence / "readback.json").read_text(encoding="utf-8"))
        validate = json.loads((evidence / "validate.json").read_text(encoding="utf-8"))
        issues = json.loads((evidence / "issues.json").read_text(encoding="utf-8"))
        review_path = evidence / "visual-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        assert validate["status"] == "PASS"
        assert issues["status"] == "PASS"
        assert issues["issue_count"] == 0
        assert readback["object_kind_counts"] == manifest["object_kind_counts"]
        assert review["status"] == "PENDING"

        # Do not turn a build into a visual approval by automation. The caller
        # must inspect every comparison image, record the Gate 3 review, and
        # then invoke the public finalize command as a separate explicit step.
        return {
            "source": str(input_html),
            "source_sha256": draft_sha,
            "pptx": str(pptx),
            "evidence": str(evidence),
            "visual_review": str(review_path),
            "validate": validate["status"],
            "issues": issues["issue_count"],
            "gate3": review["status"],
            "finalize": "PENDING_VISUAL_REVIEW",
        }
    finally:
        _stop(session, thread)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source.resolve(), args.output_root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
