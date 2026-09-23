"""Source-authoritative, loopback-only Workbench session for Product 0.6.1.

This module owns the source-authoritative Workbench slices: exact UTF-8 source
load, an in-memory draft, conflict-checked atomic Save, draft recovery, the
shared Contract check seam, hash-gated Build Revision, and the small HTTP
protocol used by the bundled editor. Preview remains a later slice; every build
continues to use the saved Author HTML file as its only compiler input.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, TextIO
from urllib.parse import parse_qs, quote, unquote, urlsplit
import webbrowser

from .application import _diagnostic_from_contract, build_author_html
from .contract import check_contract_text
from .protocol import Artifact, CommandResult, Diagnostic, result
from .workbench_assets import INDEX_HTML
from .workbench_inspector import apply_text_patch, inspect_text_selection
from .workbench_preview import PreviewProduct, build_preview, resource_content_type


class WorkbenchState(str, Enum):
    """Observable document lifecycle states exposed to the browser/API."""

    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    CHECKING = "CHECKING"
    BUILDING = "BUILDING"
    STALE = "STALE"
    SAVING = "SAVING"
    SAVED = "SAVED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


class WorkbenchError(Exception):
    """A user-actionable Workbench startup or document error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkbenchPreviewState(str, Enum):
    """Ephemeral Preview lifecycle state exposed beside the document state."""

    IDLE = "IDLE"
    CURRENT = "CURRENT"
    STALE = "STALE"
    ERROR = "ERROR"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_utf8(path: Path) -> tuple[str, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise WorkbenchError("invalid_input", f"Cannot read Workbench source: {path}: {exc}") from exc
    try:
        return payload.decode("utf-8"), _sha256_bytes(payload)
    except UnicodeDecodeError as exc:
        raise WorkbenchError(
            "invalid_input",
            f"Workbench source is not valid UTF-8: {path}",
        ) from exc


def _identity_key(path: Path) -> str:
    # The resolved path is the source identity; hashing keeps it out of the
    # recovery filename while remaining deterministic across sessions.
    identity = os.path.normcase(str(path)).encode("utf-8")
    return _sha256_bytes(identity)


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise WorkbenchError("invalid_sha256", f"{field} must be a 64-character SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise WorkbenchError("invalid_sha256", f"{field} must be a 64-character SHA-256 hex digest") from exc
    return value.lower()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    """Write bytes beside ``path`` and atomically replace it."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


@dataclass(frozen=True)
class SourcePatch:
    """Internal whole-document conflict-checked source replacement."""

    expected_sha256: str
    text: str
    expected_draft_revision: int
    expected_draft_sha256: str


class WorkbenchDocument:
    """One resolved source file plus its non-authoritative draft."""

    RECOVERY_SCHEMA_VERSION = 1

    def __init__(
        self,
        source_path: Path,
        source_text: str,
        source_sha256: str,
        *,
        recovery_root: Path,
    ) -> None:
        self.source_path = source_path
        self.asset_root = source_path.parent
        self.recovery_root = recovery_root
        self._source_text = source_text
        self._source_sha256 = source_sha256
        self._draft_text = source_text
        self._draft_sha256 = source_sha256
        self._draft_revision = 0
        self._state = WorkbenchState.CLEAN
        self._last_error: dict[str, str] | None = None
        self._contract_check: dict[str, Any] | None = None
        self._build: dict[str, Any] | None = None
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        source_path: str | Path,
        *,
        recovery_root: str | Path | None = None,
    ) -> "WorkbenchDocument":
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise WorkbenchError("invalid_input", f"Workbench source does not exist: {path}")
        text, sha256 = _read_utf8(path)
        root = (
            Path(recovery_root).expanduser().resolve()
            if recovery_root is not None
            else Path(tempfile.gettempdir()) / "officecli-html-to-pptx-workbench-recovery"
        )
        return cls(path, text, sha256, recovery_root=root)

    @property
    def text(self) -> str:
        with self._lock:
            return self._draft_text

    @property
    def source_sha256(self) -> str:
        with self._lock:
            return self._source_sha256

    @property
    def draft_sha256(self) -> str:
        with self._lock:
            return self._draft_sha256

    @property
    def draft_revision(self) -> int:
        with self._lock:
            return self._draft_revision

    def _check_draft_preconditions_locked(self, expected_revision: Any, expected_sha256: Any) -> None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise WorkbenchError("invalid_draft_revision", "expected_draft_revision must be a non-negative integer")
        expected_sha = _validate_sha(expected_sha256, "expected_draft_sha256")
        if expected_revision != self._draft_revision or expected_sha != self._draft_sha256:
            raise WorkbenchError(
                "stale_draft",
                "Draft changed since this request was created; the current Draft and source were preserved.",
            )

    @property
    def state(self) -> WorkbenchState:
        with self._lock:
            return self._state

    @property
    def recovery_path(self) -> Path:
        return self.recovery_root / f"{_identity_key(self.source_path)}-{self._source_sha256}.json"

    def _disk_sha256_locked(self) -> str:
        try:
            return _sha256_bytes(self.source_path.read_bytes())
        except OSError as exc:
            self._state = WorkbenchState.ERROR
            self._last_error = {"code": "source_read_failed", "message": str(exc)}
            raise WorkbenchError("source_read_failed", f"Cannot read Workbench source: {exc}") from exc

    def _recovery_record_locked(self) -> dict[str, Any] | None:
        path = self.recovery_path
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("source_identity") != _identity_key(self.source_path):
            return None
        if payload.get("base_sha256") != self._source_sha256:
            return None
        if not isinstance(payload.get("text"), str):
            return None
        return payload

    def _persist_recovery_locked(self) -> None:
        if self._draft_text == self._source_text:
            try:
                self.recovery_path.unlink()
            except FileNotFoundError:
                pass
            return
        self.recovery_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.RECOVERY_SCHEMA_VERSION,
            "source_identity": _identity_key(self.source_path),
            "source_path": str(self.source_path),
            "base_sha256": self._source_sha256,
            "draft_sha256": self._draft_sha256,
            "draft_revision": self._draft_revision,
            "text": self._draft_text,
            "updated_at": time.time(),
        }
        _atomic_bytes(
            self.recovery_path,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def _set_error_locked(self, code: str, message: str) -> None:
        self._state = WorkbenchState.ERROR
        self._last_error = {"code": code, "message": message}

    def record_error(self, code: str, message: str) -> None:
        """Expose a failed public request as the document's Error state."""
        with self._lock:
            if code in {
                "build_in_progress",
                "stale_draft",
                "stale_preview",
                "inspector_read_only",
                "draft_preconditions_required",
            }:
                # A rejected user action does not make the source or Draft
                # erroneous; retain its current lifecycle state.
                self._last_error = {"code": code, "message": message}
            else:
                self._set_error_locked(code, message)

    def _refresh_state_locked(self) -> str | None:
        disk_sha = self._disk_sha256_locked()
        if disk_sha != self._source_sha256:
            self._state = WorkbenchState.CONFLICT
        elif self._state == WorkbenchState.CONFLICT:
            self._state = (
                WorkbenchState.CLEAN
                if self._draft_text == self._source_text
                else WorkbenchState.DIRTY
            )
        return disk_sha

    def _assign_draft_locked(self, text: str) -> None:
        changed = text != self._draft_text
        self._draft_text = text
        self._draft_sha256 = _sha256_bytes(text.encode("utf-8"))
        if changed:
            self._draft_revision += 1
        self._last_error = None
        self._state = WorkbenchState.CLEAN if text == self._source_text else WorkbenchState.DIRTY
        try:
            self._persist_recovery_locked()
        except (OSError, UnicodeError, ValueError) as exc:
            # The Draft remains in memory; a recovery write failure is visible
            # instead of being mistaken for a durable recovery.
            self._set_error_locked("recovery_write_failed", str(exc))
            raise WorkbenchError("recovery_write_failed", str(exc)) from exc

    def set_draft(self, text: str, *, expected_revision: int, expected_sha256: str) -> None:
        if not isinstance(text, str):
            raise WorkbenchError("invalid_draft", "Draft text must be a JSON string")
        with self._lock:
            self._check_draft_preconditions_locked(expected_revision, expected_sha256)
            self._assign_draft_locked(text)

    def restore_recovery(self, *, expected_revision: int, expected_sha256: str) -> None:
        with self._lock:
            self._check_draft_preconditions_locked(expected_revision, expected_sha256)
            payload = self._recovery_record_locked()
            if payload is None:
                raise WorkbenchError("recovery_unavailable", "No compatible draft recovery is available")
            self._assign_draft_locked(str(payload["text"]))

    def recovery_summary(self) -> dict[str, Any]:
        with self._lock:
            payload = self._recovery_record_locked()
            if payload is None:
                return {"available": False, "path": str(self.recovery_path)}
            return {
                "available": True,
                "path": str(self.recovery_path),
                "base_sha256": payload.get("base_sha256"),
                "draft_sha256": payload.get("draft_sha256"),
                "updated_at": payload.get("updated_at"),
            }

    def snapshot(self, *, include_text: bool = True) -> dict[str, Any]:
        with self._lock:
            try:
                disk_sha = self._refresh_state_locked()
            except WorkbenchError:
                disk_sha = None
            contract_check = self._contract_check_snapshot_locked()
            build = dict(self._build) if self._build is not None else {
                "status": "IDLE",
                "stale": False,
                "initiating_sha256": None,
                "target_pptx": None,
                "target_evidence": None,
                "result": None,
                "diagnostics": [],
            }
            payload: dict[str, Any] = {
                "source_path": str(self.source_path),
                "asset_root": str(self.asset_root),
                "source_sha256": self._source_sha256,
                "draft_sha256": self._draft_sha256,
                "draft_revision": self._draft_revision,
                "disk_sha256": disk_sha,
                "state": self._state.value,
                "contract_status": contract_check["status"],
                "author_status": self._author_status_locked(
                    disk_sha=disk_sha,
                    contract_status=contract_check["status"],
                ),
                "contract_check": contract_check,
                "build": build,
            }
            if include_text:
                payload["text"] = self._draft_text
            if self._last_error is not None:
                payload["error"] = dict(self._last_error)
            return payload

    def _contract_check_snapshot_locked(self) -> dict[str, Any]:
        if self._contract_check is None:
            return {
                "status": "UNKNOWN",
                "checked_sha256": None,
                "stale": False,
                "diagnostics": [],
                "contract": None,
            }
        record = dict(self._contract_check)
        stale = record.get("checked_sha256") != self._draft_sha256
        record["stale"] = stale
        record["status"] = "STALE" if stale else record.get("result_status", "UNKNOWN")
        return record

    def _author_status_locked(self, *, disk_sha: str | None, contract_status: str) -> str:
        if (
            disk_sha == self._source_sha256 == self._draft_sha256
            and contract_status == "PASS"
        ):
            return "AUTHOR"
        return "CANDIDATE"

    def check(
        self,
        text: str | None = None,
        *,
        expected_revision: int | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Check the current draft through the file checker's text seam."""
        with self._lock:
            if text is not None:
                if not isinstance(text, str):
                    raise WorkbenchError("invalid_draft", "Check text must be a JSON string")
                if expected_revision is None or expected_sha256 is None:
                    raise WorkbenchError("draft_preconditions_required", "Check text requires current Draft revision and SHA-256")
                self._check_draft_preconditions_locked(expected_revision, expected_sha256)
                self._assign_draft_locked(text)
            checked_sha256 = self._draft_sha256
            previous_state = self._state
            self._state = WorkbenchState.CHECKING
            try:
                report = check_contract_text(
                    self._draft_text,
                    self.source_path,
                    "author",
                    base_dir=self.asset_root,
                )
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                self._state = WorkbenchState.ERROR
                self._last_error = {"code": "check_failed", "message": str(exc)}
                raise WorkbenchError("check_failed", str(exc)) from exc
            diagnostics = tuple(_diagnostic_from_contract(item) for item in report.diagnostics)
            check_envelope = result(
                "check",
                report.status,
                diagnostics=diagnostics,
                data={"contract": report.as_dict()},
            ).as_dict()
            self._contract_check = {
                **check_envelope,
                "checked_sha256": checked_sha256,
                "result_status": report.status,
                "stale": False,
                "diagnostics": check_envelope["diagnostics"],
                # Source ranges belong to the later Preview/source-map slice.
                # Until that reliable seam exists, diagnostics remain visible
                # by Contract source_object but are explicitly unmapped.
                "source_navigation": [
                    {
                        "source_object": item.source_object,
                        "status": "unmapped",
                    }
                    for item in diagnostics
                ],
                "contract": report.as_dict(),
            }
            self._last_error = None
            if self._build is None or self._build.get("status") != "BUILDING":
                self._state = previous_state if previous_state != WorkbenchState.CHECKING else (
                    WorkbenchState.CLEAN
                    if self._draft_text == self._source_text
                    else WorkbenchState.DIRTY
                )
            return self._contract_check_snapshot_locked()

    def build_readiness(self) -> dict[str, Any]:
        """Return the hash-bound gates required before Build Revision."""
        with self._lock:
            disk_sha = self._refresh_state_locked()
            check = self._contract_check_snapshot_locked()
            diagnostics: list[dict[str, Any]] = []
            reasons: list[str] = []
            if self._draft_sha256 != self._source_sha256:
                reasons.append("DIRTY")
                diagnostics.append(
                    {
                        "code": "dirty_draft",
                        "severity": "error",
                        "message": "Build Revision requires an explicit Save for the current draft.",
                        "blocking": True,
                        "remediation": "Save the current Workbench draft, then rerun Build Revision.",
                    }
                )
            if disk_sha != self._source_sha256:
                reasons.append("CONFLICT")
                diagnostics.append(
                    {
                        "code": "source_conflict",
                        "severity": "error",
                        "message": "The source changed on disk after this Workbench loaded it.",
                        "blocking": True,
                        "remediation": "Reopen the source after reconciling the external change.",
                    }
                )
            if check["status"] == "STALE" or check["checked_sha256"] is None:
                reasons.append("STALE_CHECK")
                diagnostics.append(
                    {
                        "code": "stale_contract_check",
                        "severity": "error",
                        "message": "Build Revision requires Contract PASS for the exact saved SHA-256.",
                        "blocking": True,
                        "remediation": "Run Check for the current draft and save that exact text before building.",
                    }
                )
            elif check["result_status"] != "PASS":
                reasons.append("CONTRACT_BLOCK")
                diagnostics.extend(check["diagnostics"])
            if self._build is not None and self._build.get("status") == "BUILDING":
                reasons.append("BUILDING")
                diagnostics.append(
                    {
                        "code": "build_in_progress",
                        "severity": "error",
                        "message": "A Workbench Build Revision is already running.",
                        "blocking": True,
                    }
                )
            return {
                "ready": not diagnostics,
                "reasons": reasons,
                "diagnostics": diagnostics,
                "saved_sha256": self._source_sha256,
                "draft_sha256": self._draft_sha256,
                "disk_sha256": disk_sha,
                "check": check,
            }

    def begin_build(self, initiating_sha256: str, target_pptx: Path, target_evidence: Path) -> None:
        with self._lock:
            self._build = {
                "status": "BUILDING",
                "stale": False,
                "initiating_sha256": initiating_sha256,
                "target_pptx": str(target_pptx),
                "target_evidence": str(target_evidence),
                "result": None,
                "diagnostics": [],
            }
            self._state = WorkbenchState.BUILDING
            self._last_error = None

    def finish_build(
        self,
        build_result: CommandResult,
        *,
        initiating_sha256: str,
        target_pptx: Path,
        target_evidence: Path,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                disk_sha = self._disk_sha256_locked()
            except WorkbenchError:
                disk_sha = None
            successful = build_result.status in {"PASS", "PASS_WITH_FINDINGS", "VISUAL_REVIEW_REQUIRED"}
            stale = successful and (
                disk_sha != initiating_sha256 or self._draft_sha256 != initiating_sha256
            )
            status = "STALE" if successful and stale else build_result.status
            self._build = {
                "status": status,
                "stale": stale,
                "initiating_sha256": initiating_sha256,
                "current_draft_sha256": self._draft_sha256,
                "current_disk_sha256": disk_sha,
                "target_pptx": str(target_pptx),
                "target_evidence": str(target_evidence),
                "artifact_pair_complete": (
                    successful and target_pptx.is_file() and target_evidence.is_dir()
                ),
                "result": build_result.as_dict(),
                "diagnostics": [item.as_dict() for item in build_result.diagnostics],
            }
            if stale:
                self._state = WorkbenchState.STALE
            elif build_result.status == "ERROR":
                self._state = WorkbenchState.ERROR
            elif self._draft_text == self._source_text:
                self._state = WorkbenchState.SAVED
            else:
                self._state = WorkbenchState.DIRTY
            return dict(self._build)

    def save(self, patch: SourcePatch) -> dict[str, Any]:
        expected = _validate_sha(patch.expected_sha256, "expected_sha256")
        if not isinstance(patch.text, str):
            raise WorkbenchError("invalid_draft", "Source Patch text must be a string")
        with self._lock:
            self._check_draft_preconditions_locked(
                patch.expected_draft_revision,
                patch.expected_draft_sha256,
            )
            if self._build is not None and self._build.get("status") == "BUILDING":
                raise WorkbenchError(
                    "build_in_progress",
                    "Save is unavailable while Build Revision is running; the draft was preserved.",
                )
            self._state = WorkbenchState.SAVING
            self._last_error = None
            try:
                # Save carries the complete draft so a click racing the
                # browser's debounced draft request cannot lose user text on a
                # conflict response.
                self._assign_draft_locked(patch.text)
                actual = self._disk_sha256_locked()
                # The client must present the source revision this session
                # loaded (or last successfully saved), not merely any SHA that
                # happens to be on disk now.  Otherwise a client could observe
                # an external edit, submit that new SHA, and overwrite it with
                # its stale draft.
                if expected != self._source_sha256 or actual != expected:
                    self._state = WorkbenchState.CONFLICT
                    self._last_error = {
                        "code": "CONFLICT",
                        "message": "Source changed on disk; the Workbench draft was preserved.",
                    }
                    return {
                        "outcome": "CONFLICT",
                        "expected_sha256": expected,
                        "base_sha256": self._source_sha256,
                        "disk_sha256": actual,
                    }
                payload = patch.text.encode("utf-8")
                old_recovery = self.recovery_path
                _atomic_bytes(self.source_path, payload)
                saved_sha = _sha256_bytes(payload)
                self._source_text = patch.text
                self._source_sha256 = saved_sha
                self._state = WorkbenchState.SAVED
                self._last_error = None
                try:
                    old_recovery.unlink()
                except FileNotFoundError:
                    pass
                return {"outcome": "SAVED", "saved_sha256": saved_sha}
            except WorkbenchError:
                raise
            except (OSError, UnicodeError) as exc:
                self._set_error_locked("save_failed", str(exc))
                raise WorkbenchError("save_failed", f"Atomic Save failed: {exc}") from exc

    def shutdown(self) -> None:
        """Persist only a separate recovery record; never implicitly Save."""
        with self._lock:
            if self._draft_text != self._source_text:
                try:
                    self._persist_recovery_locked()
                except (OSError, UnicodeError, ValueError):
                    self._set_error_locked(
                        "recovery_write_failed",
                        "Could not persist the unsaved Workbench draft.",
                    )

    def resolve_asset(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path:
            raise WorkbenchError("invalid_asset", "Asset path is required")
        raw = unquote(relative_path).replace("\\", "/")
        candidate = (self.asset_root / Path(raw)).resolve()
        try:
            candidate.relative_to(self.asset_root)
        except ValueError as exc:
            raise WorkbenchError("path_forbidden", "Asset path escapes the authorized source root") from exc
        if not candidate.is_file():
            raise WorkbenchError("asset_not_found", f"Authorized asset does not exist: {relative_path}")
        return candidate


@dataclass(frozen=True)
class WorkbenchStartup:
    """Machine-readable state emitted before the long-running server loop."""

    base_url: str
    url: str
    host: str
    port: int
    token: str
    session_id: str
    source_path: Path
    source_sha256: str
    output_root: Path | None = None

    @property
    def session_token(self) -> str:
        return self.token

    def as_result(self) -> CommandResult:
        data: dict[str, Any] = {
            "ready": True,
            "lifecycle": "running",
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "session_id": self.session_id,
            "session_token": self.token,
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "browser_opened": False,
        }
        if self.output_root is not None:
            data["output_root"] = str(self.output_root)
        return result(
            "workbench",
            "PASS",
            artifacts={"source": Artifact(self.source_path, self.source_sha256)},
            data=data,
        )


class _WorkbenchHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _WorkbenchHandler(BaseHTTPRequestHandler):
    server: _WorkbenchHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep normal request traffic out of the CLI JSON startup channel.
        return

    @property
    def session(self) -> "WorkbenchSession":
        return self.server.workbench_session  # type: ignore[attr-defined]

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.path).query, keep_blank_values=True)

    def _authorized(self, *, mutating: bool) -> bool:
        query_token = self._query().get("token", [""])[0]
        header_token = self.headers.get("X-Workbench-Token", "")
        provided = header_token or query_token
        if not provided:
            self._json(
                {"ok": False, "error": {"code": "session_token_required", "message": "A Workbench session token is required."}},
                HTTPStatus.UNAUTHORIZED,
            )
            return False
        if not hmac.compare_digest(provided, self.session.token):
            self._json(
                {"ok": False, "error": {"code": "session_token_invalid", "message": "The Workbench session token is invalid."}},
                HTTPStatus.UNAUTHORIZED,
            )
            return False
        if mutating:
            session_id = self.headers.get("X-Workbench-Session", "")
            if not session_id:
                self._json(
                    {"ok": False, "error": {"code": "session_id_required", "message": "The current Workbench session ID is required for mutations."}},
                    HTTPStatus.UNAUTHORIZED,
                )
                return False
            if not hmac.compare_digest(session_id, self.session.session_id):
                self._json(
                    {"ok": False, "error": {"code": "session_id_invalid", "message": "The Workbench session ID is invalid."}},
                    HTTPStatus.UNAUTHORIZED,
                )
                return False
        return True

    def _json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _document_response(
        self,
        *,
        ok: bool = True,
        error: Mapping[str, Any] | None = None,
        check: Mapping[str, Any] | None = None,
        build: Mapping[str, Any] | None = None,
        source_patch: Mapping[str, Any] | None = None,
        include_preview_html: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": ok,
            "session_id": self.session.session_id,
            "output_root": str(self.session.output_root),
            "document": self.session.document.snapshot(),
            "recovery": self.session.document.recovery_summary(),
            "preview": self.session.preview_snapshot(include_html=include_preview_html),
        }
        if check is not None:
            payload["check"] = dict(check)
        if build is not None:
            payload["build"] = dict(build)
        if source_patch is not None:
            payload["source_patch"] = dict(source_patch)
        if error is not None:
            payload["error"] = dict(error)
        return payload

    def _json_error(self, error: WorkbenchError, status: HTTPStatus) -> None:
        self._json(
            self._document_response(
                ok=False,
                error={"code": error.code, "message": error.message},
            ),
            status,
        )

    def _read_json(self) -> Any:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise WorkbenchError("invalid_request", "JSON requests must include Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise WorkbenchError("invalid_request", "Content-Length must be an integer") from exc
        if length < 0:
            raise WorkbenchError("invalid_request", "Content-Length cannot be negative")
        try:
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkbenchError("invalid_request", "Request body must be one UTF-8 JSON document") from exc

    def _read_optional_json(self) -> Any:
        """Accept an empty body for actions that operate on the current draft."""
        if self.headers.get("Content-Length") in {None, "0"}:
            return {}
        return self._read_json()

    def _serve_index(self) -> None:
        body = INDEX_HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _serve_asset(self, relative_path: str) -> None:
        try:
            path = self.session.document.resolve_asset(relative_path)
            body = path.read_bytes()
        except WorkbenchError as exc:
            self._json_error(exc, HTTPStatus.FORBIDDEN if exc.code == "path_forbidden" else HTTPStatus.NOT_FOUND)
            return
        except OSError as exc:
            self._json_error(WorkbenchError("asset_read_failed", str(exc)), HTTPStatus.NOT_FOUND)
            return
        content_type = "application/octet-stream"
        if path.suffix.lower() in {".html", ".htm"}:
            content_type = "text/html; charset=utf-8"
        elif path.suffix.lower() == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix.lower() == ".js":
            content_type = "text/javascript; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_preview_resource(self, relative_path: str) -> None:
        """Serve only an authorized deterministic local Preview resource."""
        # Relative URLs in an iframe cannot retain a query string from a
        # <base> element, so the ephemeral session token is carried in the
        # resource URL path.  Traversal above this segment removes the token
        # and therefore fails closed.
        token_segment, separator, asset_path = relative_path.partition("/")
        query_token = self._query().get("token", [""])[0]
        if separator and hmac.compare_digest(unquote(token_segment), self.session.token):
            pass
        elif query_token and hmac.compare_digest(query_token, self.session.token):
            asset_path = relative_path
        else:
            self._json(
                {"ok": False, "error": {"code": "session_token_invalid", "message": "The Preview resource token is invalid."}},
                HTTPStatus.UNAUTHORIZED,
            )
            return
        try:
            path = self.session.document.resolve_asset(unquote(asset_path))
            if path.suffix.lower() in {".html", ".htm", ".js", ".mjs"}:
                raise WorkbenchError("resource_forbidden", "Preview resources cannot execute or embed HTML/JavaScript")
            body = path.read_bytes()
        except WorkbenchError as exc:
            status = HTTPStatus.FORBIDDEN if exc.code in {"path_forbidden", "resource_forbidden"} else HTTPStatus.NOT_FOUND
            self._json_error(exc, status)
            return
        except (OSError, ValueError) as exc:
            self._json_error(WorkbenchError("resource_read_failed", str(exc)), HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", resource_content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        parsed = urlsplit(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._serve_index()
            return
        if parsed.path == "/health":
            self._json({"ok": True, "ready": self.session.is_running})
            return
        if not parsed.path.startswith("/api/"):
            self._json({"ok": False, "error": {"code": "not_found", "message": "Workbench route not found."}}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path.startswith("/api/preview/resource/"):
            self._serve_preview_resource(parsed.path[len("/api/preview/resource/") :])
            return
        if not self._authorized(mutating=False):
            return
        if parsed.path == "/api/session":
            self._json(self._document_response())
        elif parsed.path == "/api/preview":
            self._json(
                {
                    "ok": True,
                    "session_id": self.session.session_id,
                    "preview": self.session.preview_snapshot(include_html=True),
                }
            )
        elif parsed.path == "/api/recovery":
            self._json({"ok": True, "recovery": self.session.document.recovery_summary()})
        elif parsed.path.startswith("/api/asset/"):
            self._serve_asset(parsed.path[len("/api/asset/") :])
        else:
            self._json({"ok": False, "error": {"code": "not_found", "message": "Workbench API route not found."}}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        parsed = urlsplit(self.path)
        if not self._authorized(mutating=True):
            return
        try:
            if parsed.path == "/api/check":
                payload = self._read_optional_json()
                if payload is not None and not isinstance(payload, dict):
                    raise WorkbenchError("invalid_check", "Check request must be a JSON object")
                text = payload.get("text") if isinstance(payload, dict) else None
                if text is not None:
                    revision, draft_sha = self._draft_preconditions(payload, "Check")
                    check = self.session.check_draft(text, revision, draft_sha)
                else:
                    check = self.session.document.check()
                self._json(self._document_response(check=check))
                return
            if parsed.path == "/api/build":
                payload = self._read_optional_json()
                if not isinstance(payload, dict):
                    raise WorkbenchError("invalid_build", "Build request must be a JSON object")
                if "output" in payload or "output_pptx" in payload:
                    raise WorkbenchError(
                        "invalid_build",
                        "Build Revision output is session-managed; browser output paths are not accepted.",
                    )
                build = self.session.build_revision()
                if not build.get("accepted", False):
                    reasons = ", ".join(str(item) for item in build.get("reasons", []))
                    self._json(
                        self._document_response(
                            ok=False,
                            error={
                                "code": "build_blocked",
                                "message": f"Build Revision is blocked: {reasons or 'unknown reason'}.",
                            },
                            build=build,
                        ),
                        HTTPStatus.CONFLICT,
                    )
                else:
                    self._json(self._document_response(build=build))
                return
            if parsed.path == "/api/draft":
                payload = self._read_json()
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise WorkbenchError("invalid_draft", "Draft request requires a string 'text' field")
                revision, draft_sha = self._draft_preconditions(payload, "Draft")
                self.session.update_draft(payload["text"], revision, draft_sha)
                self._json(self._document_response())
                return
            if parsed.path in {"/api/preview", "/api/preview/refresh"}:
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise WorkbenchError("invalid_preview", "Preview request must be a JSON object")
                text = payload.get("text")
                if not isinstance(text, str):
                    raise WorkbenchError("invalid_preview", "Preview request requires a string 'text' field")
                revision, draft_sha = self._draft_preconditions(payload, "Preview")
                preview = self.session.update_and_render_preview(text, revision, draft_sha)
                self._json(
                    self._document_response(
                        ok=preview.get("status") != WorkbenchPreviewState.ERROR.value,
                        error=preview.get("error"),
                        include_preview_html=True,
                    )
                )
                return
            if parsed.path == "/api/preview/select":
                payload = self._read_json()
                if not isinstance(payload, dict) or not isinstance(payload.get("marker"), str):
                    raise WorkbenchError("invalid_preview_selection", "Preview selection requires a marker")
                revision = payload.get("preview_revision")
                draft_revision = payload.get("draft_revision")
                draft_sha = payload.get("draft_sha256")
                if isinstance(revision, bool) or not isinstance(revision, int):
                    raise WorkbenchError("invalid_preview_selection", "Preview selection requires preview_revision")
                if isinstance(draft_revision, bool) or not isinstance(draft_revision, int):
                    raise WorkbenchError("invalid_preview_selection", "Preview selection requires draft_revision")
                if not isinstance(draft_sha, str):
                    raise WorkbenchError("invalid_preview_selection", "Preview selection requires draft_sha256")
                selection = self.session.preview_selection(
                    payload["marker"],
                    revision,
                    draft_revision,
                    draft_sha,
                    payload.get("computed"),
                    payload.get("matched_styles"),
                )
                self._json({"ok": True, "session_id": self.session.session_id, "selection": selection})
                return
            if parsed.path == "/api/inspector/apply":
                payload = self._read_json()
                if not isinstance(payload, dict) or not isinstance(payload.get("marker"), str):
                    raise WorkbenchError("invalid_inspector_edit", "Inspector apply requires a selected marker")
                preview_revision = payload.get("preview_revision")
                draft_revision = payload.get("draft_revision")
                draft_sha = payload.get("draft_sha256")
                if isinstance(preview_revision, bool) or not isinstance(preview_revision, int):
                    raise WorkbenchError("invalid_inspector_edit", "Inspector apply requires preview_revision")
                if isinstance(draft_revision, bool) or not isinstance(draft_revision, int):
                    raise WorkbenchError("invalid_inspector_edit", "Inspector apply requires draft_revision")
                if not isinstance(draft_sha, str):
                    raise WorkbenchError("invalid_inspector_edit", "Inspector apply requires draft_sha256")
                applied = self.session.apply_inspector(
                    payload["marker"],
                    preview_revision,
                    draft_revision,
                    draft_sha,
                    payload.get("intent"),
                )
                self._json(
                    self._document_response(
                        check=applied["check"],
                        source_patch=applied["source_patch"],
                        include_preview_html=True,
                    )
                )
                return
            if parsed.path == "/api/save":
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise WorkbenchError("invalid_save", "Save request must be a JSON object")
                expected = payload.get("expected_sha256")
                if not isinstance(expected, str):
                    raise WorkbenchError("invalid_save", "Save request requires expected_sha256")
                draft_revision, draft_sha = self._draft_preconditions(payload, "Save")
                text = payload.get("text", self.session.document.text)
                if not isinstance(text, str):
                    raise WorkbenchError("invalid_save", "Save request text must be a string")
                outcome = self.session.save_draft(
                    SourcePatch(expected, text, draft_revision, draft_sha)
                )
                if outcome["outcome"] == "CONFLICT":
                    self._json(
                        self._document_response(
                            ok=False,
                            error={
                                "code": "CONFLICT",
                                "message": "Source changed on disk; the Workbench draft was preserved.",
                                "expected_sha256": outcome["expected_sha256"],
                                "base_sha256": outcome["base_sha256"],
                                "disk_sha256": outcome["disk_sha256"],
                            },
                        ),
                        HTTPStatus.CONFLICT,
                    )
                else:
                    self._json(self._document_response())
                return
            if parsed.path == "/api/recovery/restore":
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise WorkbenchError("invalid_recovery", "Recovery restore requires current Draft preconditions")
                revision, draft_sha = self._draft_preconditions(payload, "Recovery restore")
                self.session.restore_draft(revision, draft_sha)
                self._json(self._document_response())
                return
            if parsed.path == "/api/shutdown":
                self._json({"ok": True, "lifecycle": "stopping"})
                threading.Thread(target=self.session.shutdown, daemon=True).start()
                return
            self._json({"ok": False, "error": {"code": "not_found", "message": "Workbench API route not found."}}, HTTPStatus.NOT_FOUND)
        except WorkbenchError as exc:
            self.session.document.record_error(exc.code, exc.message)
            status = HTTPStatus.BAD_REQUEST
            if exc.code == "recovery_unavailable":
                status = HTTPStatus.NOT_FOUND
            elif exc.code in {"build_in_progress", "stale_draft", "stale_preview", "inspector_read_only"}:
                status = HTTPStatus.CONFLICT
            self._json_error(exc, status)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            error = WorkbenchError("request_failed", str(exc))
            self.session.document.record_error(error.code, error.message)
            self._json_error(error, HTTPStatus.BAD_REQUEST)

    @staticmethod
    def _draft_preconditions(payload: Mapping[str, Any], action: str) -> tuple[int, str]:
        revision = payload.get("expected_draft_revision")
        draft_sha = payload.get("expected_draft_sha256")
        if revision is None or draft_sha is None:
            raise WorkbenchError(
                "draft_preconditions_required",
                f"{action} requires expected_draft_revision and expected_draft_sha256.",
            )
        return revision, draft_sha


class WorkbenchSession:
    """Own one source path, token, draft, HTTP lifecycle, and recovery root."""

    def __init__(self, document: WorkbenchDocument, output_root: Path | None = None) -> None:
        self.document = document
        self.output_root = output_root or document.source_path.parent / ".officecli-workbench"
        self.token = secrets.token_urlsafe(32)
        self.session_id = secrets.token_urlsafe(18)
        self._server: _WorkbenchHTTPServer | None = None
        self._startup: WorkbenchStartup | None = None
        self._serve_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()
        self._build_lock = threading.Lock()
        self._preview: PreviewProduct | None = None
        self._preview_status = WorkbenchPreviewState.IDLE
        self._preview_sha256: str | None = None
        self._preview_revision = 0
        self._preview_draft_revision: int | None = None
        self._preview_error: dict[str, str] | None = None
        self._inspector_context: dict[tuple[int, int, str, str], dict[str, Any]] = {}

    @classmethod
    def open(
        cls,
        source_path: str | Path,
        *,
        recovery_root: str | Path | None = None,
        output_root: str | Path | None = None,
    ) -> "WorkbenchSession":
        document = WorkbenchDocument.open(source_path, recovery_root=recovery_root)
        root = (
            Path(output_root).expanduser().resolve()
            if output_root is not None
            else document.source_path.parent / ".officecli-workbench"
        )
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkbenchError(
                "invalid_output",
                f"Cannot create Workbench output root: {root}: {exc}",
            ) from exc
        if not root.is_dir():
            raise WorkbenchError("invalid_output", f"Workbench output root is not a directory: {root}")
        return cls(document, root)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def startup(self) -> WorkbenchStartup:
        if self._startup is None:
            raise WorkbenchError("session_not_started", "Workbench session has not started")
        return self._startup

    def _next_revision_target(self) -> tuple[Path, Path]:
        stem = self.document.source_path.stem or "workbench"
        for revision in range(1, 10000):
            output = self.output_root / f"{stem}-r{revision:02d}.pptx"
            evidence = output.with_suffix(".evidence")
            if not output.exists() and not evidence.exists():
                return output, evidence
        raise WorkbenchError(
            "revision_exhausted",
            f"No free Workbench Build Revision target remains under {self.output_root}.",
        )

    def build_revision(self) -> dict[str, Any]:
        """Run the existing Author build for one hash-bound saved revision."""
        if not self._build_lock.acquire(blocking=False):
            return {
                "accepted": False,
                "status": "BLOCK",
                "reasons": ["BUILDING"],
                "diagnostics": [
                    {
                        "code": "build_in_progress",
                        "severity": "error",
                        "message": "A Workbench Build Revision is already running.",
                        "blocking": True,
                    }
                ],
            }
        try:
            readiness = self.document.build_readiness()
            if not readiness["ready"]:
                return {
                    "accepted": False,
                    "status": "BLOCK",
                    "reasons": readiness["reasons"],
                    "diagnostics": readiness["diagnostics"],
                    "saved_sha256": readiness["saved_sha256"],
                    "draft_sha256": readiness["draft_sha256"],
                    "disk_sha256": readiness["disk_sha256"],
                }
            target_pptx, target_evidence = self._next_revision_target()
            initiating_sha256 = str(readiness["saved_sha256"])
            self.document.begin_build(initiating_sha256, target_pptx, target_evidence)
            try:
                build_result = asyncio.run(
                    build_author_html(self.document.source_path, target_pptx)
                )
            except Exception as exc:  # pragma: no cover - defensive runtime boundary
                build_result = result(
                    "build",
                    "ERROR",
                    diagnostics=(
                        Diagnostic(
                            code="workbench_build_failed",
                            severity="error",
                            message=str(exc),
                            blocking=True,
                            remediation="Inspect the build diagnostic and retry Build Revision.",
                            recheck="officecli-html-to-pptx doctor --json",
                        ),
                    ),
                )
            finished = self.document.finish_build(
                build_result,
                initiating_sha256=initiating_sha256,
                target_pptx=target_pptx,
                target_evidence=target_evidence,
            )
            return {"accepted": True, **finished}
        finally:
            self._build_lock.release()

    def start(self, *, port: int = 0) -> WorkbenchStartup:
        with self._lock:
            if self._server is not None:
                return self.startup
            try:
                server = _WorkbenchHTTPServer(("127.0.0.1", port), _WorkbenchHandler)
            except OSError as exc:
                raise WorkbenchError("server_start_failed", f"Cannot bind Workbench loopback server: {exc}") from exc
            server.workbench_session = self  # type: ignore[attr-defined]
            self._server = server
            host, bound_port = server.server_address[:2]
            base_url = f"http://{host}:{bound_port}"
            url = f"{base_url}/?token={quote(self.token, safe='')}"
            self._startup = WorkbenchStartup(
                base_url=base_url,
                url=url,
                host=host,
                port=bound_port,
                token=self.token,
                session_id=self.session_id,
                source_path=self.document.source_path,
                source_sha256=self.document.source_sha256,
                output_root=self.output_root,
            )
            return self._startup

    def mark_preview_stale(self) -> None:
        """Mark a derived Preview stale after the draft changes."""
        with self._lock:
            if self._preview is not None:
                self._preview_status = WorkbenchPreviewState.STALE
            self._inspector_context.clear()

    def update_draft(self, text: str, expected_revision: int, expected_sha256: str) -> None:
        with self._lock:
            self.document.set_draft(
                text,
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
            )
            self.mark_preview_stale()

    def check_draft(self, text: str, expected_revision: int, expected_sha256: str) -> dict[str, Any]:
        with self._lock:
            before_revision = self.document.draft_revision
            checked = self.document.check(
                text,
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
            )
            if self.document.draft_revision != before_revision:
                self.mark_preview_stale()
            return checked

    def save_draft(self, patch: SourcePatch) -> dict[str, Any]:
        with self._lock:
            before_revision = self.document.draft_revision
            outcome = self.document.save(patch)
            if self.document.draft_revision != before_revision:
                self.mark_preview_stale()
            return outcome

    def restore_draft(self, expected_revision: int, expected_sha256: str) -> None:
        with self._lock:
            before_revision = self.document.draft_revision
            self.document.restore_recovery(
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
            )
            if self.document.draft_revision != before_revision:
                self.mark_preview_stale()

    def update_and_render_preview(
        self,
        text: str,
        expected_revision: int,
        expected_sha256: str,
    ) -> dict[str, Any]:
        with self._lock:
            self.document.set_draft(
                text,
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
            )
            self.mark_preview_stale()
            return self._render_preview_locked(text)

    def preview_snapshot(self, *, include_html: bool = False) -> dict[str, Any]:
        """Return Preview metadata, optionally including its transient HTML."""
        with self._lock:
            current_sha = self.document.draft_sha256
            status = self._preview_status
            if (
                self._preview is not None
                and self._preview_sha256 != current_sha
                and status != WorkbenchPreviewState.ERROR
            ):
                status = WorkbenchPreviewState.STALE
            if (
                self._preview is not None
                and self._preview_draft_revision != self.document.draft_revision
                and status != WorkbenchPreviewState.ERROR
            ):
                status = WorkbenchPreviewState.STALE
            payload: dict[str, Any] = {
                "status": status.value,
                "draft_sha256": self._preview_sha256,
                "revision": self._preview_revision,
                "draft_revision": self._preview_draft_revision,
                "aspect_ratio": "16:9",
                "slide_count": self._preview.slide_count if self._preview is not None else 0,
                "slides": list(self._preview.slides) if self._preview is not None else [],
            }
            if self._preview_error is not None:
                payload["error"] = dict(self._preview_error)
            if self._preview is not None:
                payload["source_map"] = dict(self._preview.source_map)
                payload["blocked_resources"] = list(self._preview.blocked_resources)
                payload["parser_repaired"] = self._preview.parser_repaired
                if include_html:
                    payload["html"] = self._preview.html
            return payload

    def render_preview(self, text: str) -> dict[str, Any]:
        """Render the current draft into an in-memory isolated Preview product."""
        if not isinstance(text, str):
            raise WorkbenchError("invalid_draft", "Preview text must be a string")
        with self._lock:
            if text != self.document.text:
                raise WorkbenchError("stale_draft", "Preview text does not match the current Draft.")
            return self._render_preview_locked(text)

    def _render_preview_locked(self, text: str) -> dict[str, Any]:
        try:
            startup = self.startup
            resource_base_url = (
                f"{startup.base_url}/api/preview/resource/{quote(self.token, safe='')}/"
            )
            product = build_preview(
                text,
                asset_root=self.document.asset_root,
                resource_base_url=resource_base_url,
                preview_origin=startup.base_url,
            )
        except Exception as exc:
            self._preview_status = WorkbenchPreviewState.ERROR
            self._preview_error = {"code": "preview_failed", "message": str(exc)}
            return self.preview_snapshot(include_html=False)
        self._preview = product
        self._preview_sha256 = _sha256_bytes(text.encode("utf-8"))
        self._preview_revision += 1
        self._preview_draft_revision = self.document.draft_revision
        self._preview_status = WorkbenchPreviewState.CURRENT
        self._preview_error = None
        self._inspector_context.clear()
        return self.preview_snapshot(include_html=True)

    def preview_selection(
        self,
        marker: str,
        preview_revision: int,
        draft_revision: int,
        draft_sha256: str,
        computed: Any = None,
        matched_styles: Any = None,
    ) -> dict[str, Any]:
        """Resolve one Preview marker without exposing parser internals."""
        with self._lock:
            if self._preview is None:
                return {"status": "unmapped", "marker": marker, "reason": "preview_unavailable"}
            if preview_revision != self._preview_revision or draft_revision != self._preview_draft_revision:
                return {"status": "stale", "marker": marker, "reason": "preview_revision_stale"}
            if (
                self._preview_status != WorkbenchPreviewState.CURRENT
                or self._preview_sha256 != self.document.draft_sha256
                or draft_sha256 != self.document.draft_sha256
                or draft_revision != self.document.draft_revision
            ):
                return {"status": "stale", "marker": marker, "reason": "preview_stale"}
            selection = self._preview.selection(marker)
            if selection.get("status") != "mapped":
                return selection
            inspector = inspect_text_selection(
                self.document.text,
                selection,
                computed,
                matched_styles,
            ) if selection.get("kind") == "text" else {
                "writable": False,
                "read_only_reason": "This ticket only edits simple text leaves/runs.",
                "text": {"editable": False, "reason": "This object kind is read-only in the text Inspector."},
                "fields": {},
            }
            selection["inspector"] = inspector
            if selection.get("kind") == "text":
                self._inspector_context[(preview_revision, draft_revision, draft_sha256, marker)] = {
                    "computed": computed,
                    "matched_styles": matched_styles,
                    "inspector": inspector,
                }
            return selection

    def _preview_identity_matches_locked(
        self,
        preview_revision: int,
        draft_revision: int,
        draft_sha256: str,
    ) -> bool:
        return (
            self._preview is not None
            and preview_revision == self._preview_revision
            and draft_revision == self._preview_draft_revision
            and self._preview_status == WorkbenchPreviewState.CURRENT
            and draft_revision == self.document.draft_revision
            and draft_sha256 == self._preview_sha256 == self.document.draft_sha256
        )

    def apply_inspector(
        self,
        marker: str,
        preview_revision: int,
        draft_revision: int,
        draft_sha256: str,
        intent: Any,
    ) -> dict[str, Any]:
        with self._lock:
            if not self._preview_identity_matches_locked(preview_revision, draft_revision, draft_sha256):
                raise WorkbenchError("stale_preview", "The selected Preview object is stale; select it again after Preview refreshes.")
            key = (preview_revision, draft_revision, draft_sha256, marker)
            context = self._inspector_context.get(key)
            if context is None:
                raise WorkbenchError("stale_preview", "Select the current Preview object before applying an Inspector edit.")
            current = self._preview.selection(marker) if self._preview is not None else {}
            if current.get("status") != "mapped":
                raise WorkbenchError("inspector_read_only", str(current.get("reason") or "The selected object is unmapped."))
            inspected = inspect_text_selection(
                self.document.text,
                current,
                context.get("computed"),
                context.get("matched_styles"),
            )
            context["inspector"] = inspected
            if not isinstance(intent, dict):
                raise WorkbenchError("invalid_inspector_edit", "Inspector edit must be one text or property intent.")
            if intent.get("kind") == "text":
                field = inspected.get("text", {})
            elif intent.get("kind") == "property":
                field = inspected.get("fields", {}).get(str(intent.get("name", "")).lower(), {})
            else:
                field = {}
            if not field.get("editable"):
                reason = field.get("reason") or inspected.get("read_only_reason") or "This field is read-only."
                raise WorkbenchError("inspector_read_only", str(reason))
            try:
                patch = apply_text_patch(
                    self.document.text,
                    current,
                    intent,
                    context.get("matched_styles"),
                )
            except ValueError as exc:
                raise WorkbenchError("inspector_read_only", str(exc)) from exc
            self.document.set_draft(
                patch["text"],
                expected_revision=draft_revision,
                expected_sha256=draft_sha256,
            )
            self._preview_status = WorkbenchPreviewState.STALE
            self._inspector_context.clear()
            preview = self._render_preview_locked(patch["text"])
            check = self.document.check()
            return {
                "source_patch": {
                    "property": patch["property"],
                    "before": patch["before"],
                    "after": patch["after"],
                    "diff": patch["diff"],
                    "local_override": patch["local_override"],
                    "draft_revision": self.document.draft_revision,
                    "draft_sha256": self.document.draft_sha256,
                },
                "preview": preview,
                "check": check,
            }

    def serve_forever(self) -> None:
        server = self._server
        if server is None:
            self.start()
            server = self._server
        assert server is not None
        with self._lock:
            self._serve_thread = threading.current_thread()
            self._running = True
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            with self._lock:
                self._running = False

    def shutdown(self) -> None:
        self.document.shutdown()
        server = self._server
        if server is None:
            return
        if threading.current_thread() is self._serve_thread:
            threading.Thread(target=server.shutdown, daemon=True).start()
            return
        server.shutdown()
        server.server_close()

    def close(self) -> None:
        self.document.shutdown()
        server = self._server
        if server is not None:
            server.server_close()
        with self._lock:
            self._running = False


def _startup_error(exc: WorkbenchError) -> CommandResult:
    code = "invalid_input" if exc.code == "invalid_input" else "unexpected_error"
    return result(
        "workbench",
        "ERROR",
        diagnostics=(
            Diagnostic(
                code=code,
                severity="error",
                message=exc.message,
                blocking=True,
                remediation="Correct the Workbench source or local runtime and retry.",
                recheck="officecli-html-to-pptx workbench --help",
            ),
        ),
    )


def run_workbench(
    input_html: str | Path,
    *,
    json_mode: bool = False,
    open_browser: bool = True,
    port: int = 0,
    recovery_root: str | Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Start the Workbench, emit readiness once, and run until shutdown."""
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    try:
        session = WorkbenchSession.open(input_html, recovery_root=recovery_root)
        startup = session.start(port=port)
    except WorkbenchError as exc:
        failure = _startup_error(exc)
        if json_mode:
            print(failure.to_json(), file=output, flush=True)
        else:
            print(f"workbench: ERROR", file=output, flush=True)
            for item in failure.diagnostics:
                print(f"{item.severity}: {item.message}", file=errors, flush=True)
        return failure.exit_code

    startup_result = startup.as_result()
    startup_data = dict(startup_result.data)
    startup_data["browser_opened"] = bool(open_browser)
    startup_result = result(
        startup_result.command,
        startup_result.status,
        artifacts=startup_result.artifacts,
        data=startup_data,
    )
    if json_mode:
        print(startup_result.to_json(), file=output, flush=True)
    else:
        print(f"workbench: READY\nurl: {startup.url}\nPress Ctrl+C to stop.", file=output, flush=True)
    if open_browser:
        try:
            webbrowser.open(startup.url)
        except Exception as exc:  # pragma: no cover - browser integration varies by host
            print(f"warning: could not open the system browser: {exc}", file=errors, flush=True)
    try:
        session.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


__all__ = [
    "SourcePatch",
    "WorkbenchDocument",
    "WorkbenchError",
    "WorkbenchPreviewState",
    "WorkbenchSession",
    "WorkbenchStartup",
    "WorkbenchState",
    "run_workbench",
]
