"""Source-authoritative, loopback-only Workbench session for Product 0.6.1.

This module owns the first Workbench vertical slice: exact UTF-8 source load,
an in-memory draft, conflict-checked atomic Save, draft recovery, and the small
HTTP protocol used by the bundled editor.  It deliberately does not preview,
check, or build the source; those are later slices and must continue to use the
saved Author HTML file as their only compiler input.
"""

from __future__ import annotations

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

from .protocol import Artifact, CommandResult, Diagnostic, result
from .workbench_assets import INDEX_HTML


class WorkbenchState(str, Enum):
    """Observable document lifecycle states exposed to the browser/API."""

    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
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
        self._state = WorkbenchState.CLEAN
        self._last_error: dict[str, str] | None = None
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

    def set_draft(self, text: str) -> None:
        if not isinstance(text, str):
            raise WorkbenchError("invalid_draft", "Draft text must be a JSON string")
        with self._lock:
            self._draft_text = text
            self._draft_sha256 = _sha256_bytes(text.encode("utf-8"))
            self._last_error = None
            self._state = (
                WorkbenchState.CLEAN
                if text == self._source_text
                else WorkbenchState.DIRTY
            )
            try:
                self._persist_recovery_locked()
            except (OSError, UnicodeError, ValueError) as exc:
                # The draft remains in memory; a recovery write failure is
                # visible instead of being mistaken for a durable recovery.
                self._set_error_locked("recovery_write_failed", str(exc))
                raise WorkbenchError("recovery_write_failed", str(exc)) from exc

    def restore_recovery(self) -> None:
        with self._lock:
            payload = self._recovery_record_locked()
            if payload is None:
                raise WorkbenchError("recovery_unavailable", "No compatible draft recovery is available")
            self._draft_text = str(payload["text"])
            self._draft_sha256 = _sha256_bytes(self._draft_text.encode("utf-8"))
            self._state = WorkbenchState.DIRTY
            self._last_error = None

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
            payload: dict[str, Any] = {
                "source_path": str(self.source_path),
                "asset_root": str(self.asset_root),
                "source_sha256": self._source_sha256,
                "draft_sha256": self._draft_sha256,
                "disk_sha256": disk_sha,
                "state": self._state.value,
                # Save is deliberately not a Contract check or promotion.
                "contract_status": "UNKNOWN",
            }
            if include_text:
                payload["text"] = self._draft_text
            if self._last_error is not None:
                payload["error"] = dict(self._last_error)
            return payload

    def save(self, patch: SourcePatch) -> dict[str, Any]:
        expected = _validate_sha(patch.expected_sha256, "expected_sha256")
        if not isinstance(patch.text, str):
            raise WorkbenchError("invalid_draft", "Source Patch text must be a string")
        with self._lock:
            self._state = WorkbenchState.SAVING
            self._last_error = None
            try:
                # Save carries the complete draft so a click racing the
                # browser's debounced draft request cannot lose user text on a
                # conflict response.
                self._draft_text = patch.text
                self._draft_sha256 = _sha256_bytes(patch.text.encode("utf-8"))
                self._persist_recovery_locked()
                actual = self._disk_sha256_locked()
                if actual != expected:
                    self._state = WorkbenchState.CONFLICT
                    self._last_error = {
                        "code": "CONFLICT",
                        "message": "Source changed on disk; the Workbench draft was preserved.",
                    }
                    return {
                        "outcome": "CONFLICT",
                        "expected_sha256": expected,
                        "disk_sha256": actual,
                    }
                payload = patch.text.encode("utf-8")
                old_recovery = self.recovery_path
                _atomic_bytes(self.source_path, payload)
                saved_sha = _sha256_bytes(payload)
                self._source_text = patch.text
                self._source_sha256 = saved_sha
                self._draft_text = patch.text
                self._draft_sha256 = saved_sha
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

    @property
    def session_token(self) -> str:
        return self.token

    def as_result(self) -> CommandResult:
        return result(
            "workbench",
            "PASS",
            artifacts={"source": Artifact(self.source_path, self.source_sha256)},
            data={
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
            },
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
        return True

    def _json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _document_response(self, *, ok: bool = True, error: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": ok,
            "session_id": self.session.session_id,
            "document": self.session.document.snapshot(),
            "recovery": self.session.document.recovery_summary(),
        }
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
        if not self._authorized(mutating=False):
            return
        if parsed.path == "/api/session":
            self._json(self._document_response())
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
            if parsed.path == "/api/draft":
                payload = self._read_json()
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise WorkbenchError("invalid_draft", "Draft request requires a string 'text' field")
                self.session.document.set_draft(payload["text"])
                self._json(self._document_response())
                return
            if parsed.path == "/api/save":
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise WorkbenchError("invalid_save", "Save request must be a JSON object")
                expected = payload.get("expected_sha256")
                if not isinstance(expected, str):
                    raise WorkbenchError("invalid_save", "Save request requires expected_sha256")
                text = payload.get("text", self.session.document.text)
                if not isinstance(text, str):
                    raise WorkbenchError("invalid_save", "Save request text must be a string")
                outcome = self.session.document.save(SourcePatch(expected, text))
                if outcome["outcome"] == "CONFLICT":
                    self._json(
                        self._document_response(
                            ok=False,
                            error={
                                "code": "CONFLICT",
                                "message": "Source changed on disk; the Workbench draft was preserved.",
                                "expected_sha256": outcome["expected_sha256"],
                                "disk_sha256": outcome["disk_sha256"],
                            },
                        ),
                        HTTPStatus.CONFLICT,
                    )
                else:
                    self._json(self._document_response())
                return
            if parsed.path == "/api/recovery/restore":
                self.session.document.restore_recovery()
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
            self._json_error(exc, status)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            error = WorkbenchError("request_failed", str(exc))
            self.session.document.record_error(error.code, error.message)
            self._json_error(error, HTTPStatus.BAD_REQUEST)


class WorkbenchSession:
    """Own one source path, token, draft, HTTP lifecycle, and recovery root."""

    def __init__(self, document: WorkbenchDocument) -> None:
        self.document = document
        self.token = secrets.token_urlsafe(32)
        self.session_id = secrets.token_urlsafe(18)
        self._server: _WorkbenchHTTPServer | None = None
        self._startup: WorkbenchStartup | None = None
        self._serve_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        source_path: str | Path,
        *,
        recovery_root: str | Path | None = None,
    ) -> "WorkbenchSession":
        return cls(WorkbenchDocument.open(source_path, recovery_root=recovery_root))

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def startup(self) -> WorkbenchStartup:
        if self._startup is None:
            raise WorkbenchError("session_not_started", "Workbench session has not started")
        return self._startup

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
            )
            return self._startup

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
    "WorkbenchSession",
    "WorkbenchStartup",
    "WorkbenchState",
    "run_workbench",
]
