"""The small JSON protocol shared by the V0.6.1 application and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

PRODUCT_NAME = "officecli-html-to-pptx"
PRODUCT_VERSION = "0.6.1"
ENVELOPE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Diagnostic:
    """One actionable item in a command result."""

    code: str
    severity: str
    message: str
    blocking: bool = True
    source_slide: int | None = None
    source_object: str | None = None
    operation: str | None = None
    remediation: str | None = None
    recheck: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "blocking": self.blocking,
        }
        for key, value in (
            ("source_slide", self.source_slide),
            ("source_object", self.source_object),
            ("operation", self.operation),
            ("remediation", self.remediation),
            ("recheck", self.recheck),
        ):
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class Artifact:
    """A persisted file or directory referenced by a result."""

    path: str | Path
    sha256: str | None = None

    def as_dict(self) -> dict[str, str]:
        data = {"path": str(Path(self.path).expanduser().resolve())}
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        return data


@dataclass(frozen=True)
class CommandResult:
    """Versioned result envelope returned by every public operation."""

    command: str
    status: str
    diagnostics: tuple[Diagnostic, ...] = ()
    artifacts: Mapping[str, Artifact | Mapping[str, Any]] = field(default_factory=dict)
    data: Mapping[str, Any] = field(default_factory=dict)
    _exit_code: int | None = field(default=None, repr=False, compare=False)

    @property
    def exit_code(self) -> int:
        if self._exit_code is not None:
            return self._exit_code
        return exit_code_for_status(self.status, self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        artifacts: dict[str, Any] = {}
        for name, artifact in self.artifacts.items():
            artifacts[name] = (
                artifact.as_dict()
                if isinstance(artifact, Artifact)
                else dict(artifact)
            )
        return {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "command": self.command,
            "status": self.status,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "artifacts": artifacts,
            "data": dict(self.data),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))


_SUCCESS_STATUSES = frozenset(
    {"PASS", "PASS_WITH_FINDINGS", "VISUAL_REVIEW_REQUIRED"}
)
_ACTIONABLE_STATUSES = frozenset({"BLOCK", "REVISION_REQUIRED"})
_INVALID_CODES = frozenset(
    {
        "invalid_input",
        "invalid_invocation",
        "invalid_evidence",
        "invalid_review",
        "invalid_output",
    }
)


def exit_code_for_status(status: str, diagnostics: tuple[Diagnostic, ...] = ()) -> int:
    """Map the protocol status to the stable CLI exit classes."""
    if status in _SUCCESS_STATUSES:
        return 0
    if status in _ACTIONABLE_STATUSES:
        return 2
    if status == "ERROR":
        if any(item.code in _INVALID_CODES for item in diagnostics):
            return 3
        return 4
    return 4


def result(
    command: str,
    status: str,
    *,
    diagnostics: tuple[Diagnostic, ...] = (),
    artifacts: Mapping[str, Artifact | Mapping[str, Any]] | None = None,
    data: Mapping[str, Any] | None = None,
    exit_code: int | None = None,
) -> CommandResult:
    """Construct an envelope without duplicating protocol fields in handlers."""
    return CommandResult(
        command,
        status,
        diagnostics,
        artifacts or {},
        data or {},
        exit_code,
    )


__all__ = [
    "Artifact",
    "CommandResult",
    "Diagnostic",
    "ENVELOPE_SCHEMA_VERSION",
    "PRODUCT_NAME",
    "PRODUCT_VERSION",
    "exit_code_for_status",
    "result",
]
