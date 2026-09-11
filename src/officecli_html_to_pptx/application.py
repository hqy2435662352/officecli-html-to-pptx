"""Task-oriented V0.2 application operations.

The module is deliberately an orchestration layer, not a second renderer.  It
owns the public command semantics, the Artifact Pair transaction, and the
Evidence Bundle schemas while delegating Contract checking, Author lowering,
runtime discovery, and visual capture to the existing kernel helpers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable
from uuid import uuid4

from .contract import (
    CONTRACT_VERSION,
    OFFICECLI_COMPATIBILITY_BASELINE,
    ContractDiagnostic,
    ContractReport,
    author_capability_manifest,
    check_contract,
)
from ._internal.acceptance import _run_officecli, _screenshot_pptx
from ._internal.compare import create_comparison, screenshot_html_slides
from ._internal.officecli_compiler import (
    CompilationDiagnostic,
    OfficeCLICompilationError,
    OfficeCLICompilationResult,
    compile_officecli,
)
from .protocol import (
    Artifact,
    CommandResult,
    Diagnostic,
    PRODUCT_NAME,
    PRODUCT_VERSION,
    result,
)
from .runtime import (
    FORMAL_CHROMIUM_REVISION,
    FORMAL_OFFICECLI_VERSION,
    FORMAL_PLAYWRIGHT_VERSION,
    NODE_TESTED_RANGE,
    PYTHON_TESTED_RANGE,
    SUPPORTED_PLATFORMS,
    UNVALIDATED_PLATFORM_NOTE,
    VALIDATED_PLATFORM_SCOPE,
    current_platform,
    diagnose_environment as _diagnose_runtime,
)


PUBLIC_COMMANDS = ("capabilities", "doctor", "check", "build", "finalize")
VISUAL_REVIEW_SCHEMA_VERSION = 1
EVIDENCE_FILES = (
    "contract.json",
    "capabilities.json",
    "runtime.json",
    "manifest.json",
    "validate.json",
    "issues.json",
    "result.json",
    "visual-review.json",
)
_PUBLISH_RETRIES = 40
_PUBLISH_RETRY_DELAY_SECONDS = 0.25


def _json_dump(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one evidence JSON document with stable, readable UTF-8."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _diagnostic_from_contract(item: ContractDiagnostic) -> Diagnostic:
    return Diagnostic(
        code=item.code,
        severity=item.severity,
        message=item.message,
        blocking=item.blocking,
        source_object=item.source_object,
        remediation=(
            "Repair the Author HTML at the reported source object and rerun "
            "officecli-html-to-pptx check --json."
        ),
        recheck="officecli-html-to-pptx check --json <author.html>",
    )


def _diagnostics_from_compiler(
    diagnostics: Iterable[CompilationDiagnostic],
) -> tuple[Diagnostic, ...]:
    return tuple(
        Diagnostic(
            code=item.code,
            severity=item.severity,
            message=item.message,
            blocking=True,
            source_slide=item.source_slide,
            source_object=item.source_object,
            operation=item.operation,
            remediation=(
                "Repair the reported input or runtime problem, then rerun "
                "officecli-html-to-pptx build --json."
            ),
            recheck="officecli-html-to-pptx doctor --json",
        )
        for item in diagnostics
    )


def _invalid(
    command: str,
    code: str,
    message: str,
    *,
    remediation: str | None = None,
) -> CommandResult:
    return result(
        command,
        "ERROR",
        diagnostics=(
            Diagnostic(
                code=code,
                severity="error",
                message=message,
                blocking=True,
                remediation=remediation,
                recheck=f"officecli-html-to-pptx {command} --json",
            ),
        ),
    )


def _error(command: str, message: str, *, code: str = "unexpected_error") -> CommandResult:
    return result(
        command,
        "ERROR",
        diagnostics=(
            Diagnostic(
                code=code,
                severity="error",
                message=message,
                blocking=True,
                remediation="Inspect the diagnostic and retry after correcting the reported condition.",
                recheck=f"officecli-html-to-pptx {command} --json",
            ),
        ),
    )


def _contract_result(report: ContractReport) -> CommandResult:
    return result(
        "check",
        report.status,
        diagnostics=tuple(_diagnostic_from_contract(item) for item in report.diagnostics),
        data={"contract": report.as_dict()},
    )


def get_capabilities() -> CommandResult:
    """Return the formal, Author-only capability manifest.

    Object kinds and CSS classifications are read directly from the Contract
    authority used by ``check_contract``.  The compiler consumes that same
    supported object set at its lowering boundary, so no separate hand-written
    public capability matrix is maintained here.
    """
    contract_capabilities = author_capability_manifest()
    data = {
        "contract": contract_capabilities,
        # ``platform`` is where this command is running; ``supported_platforms``
        # is what this build supports.  A supported key is coarse -- the single
        # key "Linux" matches every distribution -- so the validated scope is
        # published beside it and a key is never read as a broader claim than the
        # Platform Acceptance Track supports.
        "platform": current_platform(),
        "supported_platforms": list(SUPPORTED_PLATFORMS),
        "validated_platform_scope": {
            "accepted": dict(VALIDATED_PLATFORM_SCOPE),
            "not_implied": UNVALIDATED_PLATFORM_NOTE,
        },
        "rendering_compatibility": {
            "officecli": f">={FORMAL_OFFICECLI_VERSION}",
            "playwright": FORMAL_PLAYWRIGHT_VERSION,
            "chromium_revision": FORMAL_CHROMIUM_REVISION,
        },
        "runtime_ranges": {
            "python": PYTHON_TESTED_RANGE,
            "node": NODE_TESTED_RANGE,
        },
        "commands": list(PUBLIC_COMMANDS),
        "scope": {
            "creates_new_pptx": True,
            "officehtml_import": False,
            "existing_pptx_editing": False,
        },
    }
    return result("capabilities", "PASS", data=data)


def diagnose_environment(
    output_path: str | Path | None = None,
    temp_dir: str | Path | None = None,
    *,
    _which: Callable[[str], str | None] | None = None,
    _runner: Callable[..., Any] | None = None,
) -> CommandResult:
    """Return a read-only runtime diagnosis in the public result envelope."""
    kwargs: dict[str, Any] = {
        "output_path": output_path,
        "temp_dir": temp_dir,
    }
    if _which is not None:
        kwargs["which"] = _which
    if _runner is not None:
        kwargs["runner"] = _runner
    diagnosis = _diagnose_runtime(**kwargs)
    return result(
        "doctor",
        "PASS" if diagnosis.compatible else "BLOCK",
        diagnostics=diagnosis.diagnostics,
        data={"runtime": diagnosis.snapshot},
    )


def check_author_html(input_html: str | Path) -> CommandResult:
    """Promote or reject one Candidate HTML through the Author Contract."""
    path = _absolute(input_html)
    if not path.is_file():
        return _invalid(
            "check",
            "invalid_input",
            f"Author HTML input does not exist: {path}",
            remediation="Provide an existing .html file and rerun officecli-html-to-pptx check --json.",
        )
    try:
        return _contract_result(check_contract(path, "author"))
    except (OSError, UnicodeError, ValueError) as exc:
        return _invalid("check", "invalid_input", str(exc))


def _evidence_path(output_path: Path) -> Path:
    return output_path.with_suffix(".evidence")


def _build_target_error(output_path: Path, evidence_path: Path) -> CommandResult | None:
    collisions = [
        str(path)
        for path in (output_path, evidence_path)
        if path.exists()
    ]
    if not collisions:
        return None
    return result(
        "build",
        "BLOCK",
        diagnostics=(
            Diagnostic(
                code="artifact_exists",
                severity="error",
                message=(
                    "Build will not overwrite an existing Artifact Pair target: "
                    + ", ".join(collisions)
                ),
                blocking=True,
                remediation="Choose a new .pptx output path or an Agent-managed revision suffix.",
                recheck="officecli-html-to-pptx build --json <author.html> <new-output.pptx>",
            ),
        ),
        data={"collisions": collisions},
    )


def _validate_build_output(path: Path) -> dict[str, Any]:
    """Collect OfficeCLI validation without treating issues as a failure."""
    text = str(_run_officecli("validate", path))
    return {"status": "PASS", "output": text}


def _collect_issues(path: Path) -> dict[str, Any]:
    text = str(_run_officecli("view", path, "issues"))
    return {"status": "PASS", "output": text}


def _publish_file(source: Path, target: Path) -> None:
    """Rename a staged file, allowing OfficeCLI's Windows handle to drain."""
    for attempt in range(_PUBLISH_RETRIES):
        try:
            source.rename(target)
            return
        except OSError as exc:
            sharing_violation = getattr(exc, "winerror", None) in {5, 32, 33}
            sharing_violation = sharing_violation or exc.errno in {
                errno.EACCES,
                errno.EBUSY,
                errno.ETXTBSY,
            }
            if not sharing_violation or attempt == _PUBLISH_RETRIES - 1:
                raise
            time.sleep(_PUBLISH_RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Could not publish staged file: {source}")


async def _make_comparisons(
    html_path: Path,
    pptx_path: Path,
    destination: Path,
    slide_count: int,
) -> list[dict[str, Any]]:
    """Render temporary source/output views and persist only combined images."""
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".comparison-",
        dir=str(destination.parent),
    ) as temporary_name:
        temporary = Path(temporary_name)
        html_dir = temporary / "html"
        pptx_dir = temporary / "pptx"
        combined_dir = temporary / "combined"
        html_dir.mkdir()
        pptx_dir.mkdir()
        combined_dir.mkdir()
        html_images = await screenshot_html_slides(html_path, html_dir)
        pptx_images = _screenshot_pptx(pptx_path, pptx_dir, slide_count)
        combined = create_comparison(html_images, pptx_images, combined_dir)
        if (
            len(html_images) != slide_count
            or len(pptx_images) != slide_count
            or len(combined) != slide_count
        ):
            raise RuntimeError(
                "Comparison evidence requires one Author HTML, PPTX, and "
                f"combined image per slide; got {len(html_images)}, "
                f"{len(pptx_images)}, and {len(combined)} for {slide_count}."
            )
        inventory: list[dict[str, Any]] = []
        for slide_number, source in enumerate(combined, start=1):
            target = destination / f"slide-{slide_number:03d}.png"
            shutil.copy2(source, target)
            inventory.append(
                {
                    "slide": slide_number,
                    "path": str(target.resolve()),
                    "sha256": _sha256(target),
                }
            )
        return inventory


def _runtime_block_result(diagnosis: CommandResult) -> CommandResult:
    return result(
        "build",
        "BLOCK",
        diagnostics=diagnosis.diagnostics,
        data={"runtime": diagnosis.data.get("runtime", {})},
    )


def _review_seed(
    *,
    build_id: str,
    html_path: Path,
    html_hash: str,
    pptx_path: Path,
    pptx_hash: str,
    slide_count: int,
    comparisons: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    comparison_list = [dict(item) for item in comparisons]
    return {
        "schema_version": VISUAL_REVIEW_SCHEMA_VERSION,
        "status": "PENDING",
        "build_id": build_id,
        "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
        "contract_version": CONTRACT_VERSION,
        "author_html": {"path": str(html_path), "sha256": html_hash},
        "pptx": {"path": str(pptx_path), "sha256": pptx_hash},
        "comparisons": comparison_list,
        "slides": [
            {
                "slide": int(item["slide"]),
                "comparison_path": str(item["path"]),
                "comparison_sha256": str(item["sha256"]),
                "status": "PENDING",
                "findings": [],
                "notes": "",
            }
            for item in comparison_list
        ],
    }


async def build_author_html(
    input_html: str | Path,
    output_pptx: str | Path,
) -> CommandResult:
    """Build and publish one non-overwriting PPTX/Evidence Pair.

    All owned files are staged beside the requested output.  A controlled
    failure removes the exact staging directory and publishes neither target.
    """
    input_path = _absolute(input_html)
    output_path = _absolute(output_pptx)
    evidence_path = _evidence_path(output_path)

    if not input_path.is_file():
        return _invalid(
            "build",
            "invalid_input",
            f"Author HTML input does not exist: {input_path}",
            remediation="Provide an existing checked Author HTML file and retry.",
        )
    if output_path.suffix.lower() != ".pptx":
        return _invalid(
            "build",
            "invalid_output",
            f"Build output must use a .pptx suffix: {output_path}",
            remediation="Choose a new output path ending in .pptx and retry.",
        )
    if not output_path.parent.is_dir():
        return _invalid(
            "build",
            "invalid_output",
            f"Build output directory does not exist: {output_path.parent}",
            remediation="Create or choose an existing writable output directory and retry.",
        )
    collision = _build_target_error(output_path, evidence_path)
    if collision is not None:
        return collision

    contract: ContractReport
    try:
        contract = check_contract(input_path, "author")
    except (OSError, UnicodeError, ValueError) as exc:
        return _invalid("build", "invalid_input", str(exc))
    if contract.blocked:
        return result(
            "build",
            "BLOCK",
            diagnostics=tuple(_diagnostic_from_contract(item) for item in contract.diagnostics),
            data={"contract": contract.as_dict()},
        )

    # Runtime discovery uses Playwright's synchronous metadata API.  Run it in
    # a worker so the async build event loop never trips Playwright's
    # sync-inside-async guard (and so the check remains read-only).
    diagnosis = await asyncio.to_thread(
        diagnose_environment,
        output_path=output_path,
        temp_dir=output_path.parent,
    )
    if diagnosis.status != "PASS":
        return _runtime_block_result(diagnosis)

    html_hash = _sha256(input_path)
    build_id = str(uuid4())
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_path.stem}-{build_id[:8]}-", dir=str(output_path.parent))
    )
    staged_pptx = staging_dir / output_path.name
    staged_evidence = staging_dir / evidence_path.name
    published_pptx = False
    published_evidence = False

    try:
        try:
            compiled = await compile_officecli(
                str(input_path),
                "author",
                str(staged_pptx),
            )
            if not staged_pptx.is_file():
                raise RuntimeError(f"OfficeCLI compiler did not create {staged_pptx}")
        except OfficeCLICompilationError as exc:
            diagnostics = _diagnostics_from_compiler(exc.diagnostics)
            if any(item.code.startswith(("unsupported_", "undecodable_", "invalid_")) for item in exc.diagnostics):
                return result("build", "BLOCK", diagnostics=diagnostics)
            return result("build", "ERROR", diagnostics=diagnostics)
        except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
            return _error("build", str(exc))

        slide_count = int(compiled.slide_count)
        validation = _validate_build_output(staged_pptx)
        issues = _collect_issues(staged_pptx)
        staged_evidence.mkdir(parents=True, exist_ok=False)
        comparison_dir = staged_evidence / "comparisons"
        comparisons = await _make_comparisons(
            input_path,
            staged_pptx,
            comparison_dir,
            slide_count,
        )
        pptx_hash = _sha256(staged_pptx)
        final_comparisons = [
            {
                **item,
                "path": str((evidence_path / "comparisons" / Path(item["path"]).name).resolve()),
            }
            for item in comparisons
        ]
        # The source image is already in the staged Evidence Bundle; update the
        # inventory path to its eventual published absolute path and retain its
        # hash unchanged.
        result_payload: dict[str, Any] = {
            "schema_version": 1,
            "build_id": build_id,
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "contract_version": CONTRACT_VERSION,
            "officecli_compatibility_baseline": OFFICECLI_COMPATIBILITY_BASELINE,
            "runtime": diagnosis.data.get("runtime", {}),
            "author_html": {"path": str(input_path), "sha256": html_hash},
            "pptx": {"path": str(output_path), "sha256": pptx_hash},
            "pptx_path": str(output_path),
            "evidence_path": str(evidence_path),
            "slide_count": slide_count,
            "comparisons": final_comparisons,
            "status": "VISUAL_REVIEW_REQUIRED",
        }
        review_payload = _review_seed(
            build_id=build_id,
            html_path=input_path,
            html_hash=html_hash,
            pptx_path=output_path,
            pptx_hash=pptx_hash,
            slide_count=slide_count,
            comparisons=final_comparisons,
        )
        _json_dump(staged_evidence / "contract.json", contract.as_dict())
        _json_dump(staged_evidence / "capabilities.json", get_capabilities().data)
        _json_dump(staged_evidence / "runtime.json", diagnosis.data.get("runtime", {}))
        _json_dump(staged_evidence / "manifest.json", compiled.manifest)
        _json_dump(staged_evidence / "validate.json", validation)
        _json_dump(staged_evidence / "issues.json", issues)
        _json_dump(staged_evidence / "result.json", result_payload)
        _json_dump(staged_evidence / "visual-review.json", review_payload)

        missing = [
            str(path)
            for path in (
                staged_pptx,
                *(staged_evidence / name for name in EVIDENCE_FILES),
                *(staged_evidence / "comparisons" / f"slide-{index:03d}.png" for index in range(1, slide_count + 1)),
            )
            if not path.is_file()
        ]
        if missing:
            raise RuntimeError("Build evidence is incomplete: " + ", ".join(missing))

        # OfficeCLI 1.0.148 may keep validation/view results in a resident
        # process.  Close our staged document before a native Windows rename.
        _run_officecli("close", staged_pptx)

        # Recheck both destinations immediately before publication.  rename()
        # refuses an existing target on Windows, preserving non-overwrite
        # semantics even if another process created one after preflight.
        if output_path.exists() or evidence_path.exists():
            raise FileExistsError("Artifact Pair target appeared during build")
        _publish_file(staged_pptx, output_path)
        published_pptx = True
        _publish_file(staged_evidence, evidence_path)
        published_evidence = True
    except OfficeCLICompilationError as exc:
        return _error("build", str(exc), code="officecli_error")
    except (OSError, RuntimeError, ValueError) as exc:
        return _error("build", str(exc), code="build_failed")
    finally:
        # Only remove a target after our own rename succeeded.  In particular,
        # never delete a concurrently-created evidence directory merely
        # because the second publish rename failed.
        if published_pptx and not published_evidence and output_path.exists():
            output_path.unlink(missing_ok=True)
        if staged_pptx.exists():
            try:
                _run_officecli("close", staged_pptx)
            except Exception:
                # Cleanup must not mask the original build diagnostic.
                pass
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return result(
        "build",
        "VISUAL_REVIEW_REQUIRED",
        artifacts={
            "pptx": Artifact(output_path, pptx_hash),
            "evidence": Artifact(evidence_path),
            "comparisons": {"items": final_comparisons},
        },
        data=result_payload,
    )


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise ValueError(f"Evidence {label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Evidence {label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"Evidence {label} must contain a JSON object: {path}")
    return payload


def _field_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _required_text(mapping: Mapping[str, Any], names: Sequence[str], label: str) -> str:
    for name in names:
        value = mapping.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"{label} must contain a non-empty {names[0]!r}")


def _same_hash(path: Path, expected: Any, label: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{label} must contain a SHA-256 hash")
    actual = _sha256(path)
    if actual.lower() != expected.lower():
        raise ValueError(f"{label} hash does not match persisted evidence")


def _resolve_comparison_path(evidence_path: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Comparison Image path must be a non-empty string")
    path = _absolute(value)
    comparisons_root = (evidence_path / "comparisons").resolve()
    try:
        path.relative_to(comparisons_root)
    except ValueError as exc:
        raise ValueError("Comparison Image must remain inside evidence/comparisons") from exc
    return path


def _comparison_inventory(result_payload: Mapping[str, Any], evidence_path: Path) -> list[dict[str, Any]]:
    raw = result_payload.get("comparisons")
    if not isinstance(raw, list) or not raw:
        raise ValueError("result.json must contain a non-empty comparisons list")
    inventory: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in raw:
        mapping = _field_mapping(item, "result comparison")
        try:
            slide = int(mapping.get("slide"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Each result comparison needs an integer slide") from exc
        if slide in seen:
            raise ValueError(f"result.json repeats comparison slide {slide}")
        seen.add(slide)
        path = _resolve_comparison_path(evidence_path, mapping.get("path"))
        if not path.is_file():
            raise ValueError(f"Comparison Image does not exist: {path}")
        _same_hash(path, mapping.get("sha256"), f"Comparison Image slide {slide}")
        inventory.append({"slide": slide, "path": str(path), "sha256": str(mapping["sha256"])})
    inventory.sort(key=lambda item: int(item["slide"]))
    expected = list(range(1, int(result_payload.get("slide_count", 0)) + 1))
    if [int(item["slide"]) for item in inventory] != expected:
        raise ValueError("Comparison Image inventory does not cover every build slide exactly once")
    return inventory


def _review_comparisons(
    review_payload: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    evidence_path: Path,
) -> None:
    raw = review_payload.get("comparisons")
    if not isinstance(raw, list):
        raise ValueError("visual-review.json must contain a comparisons list")
    by_slide: dict[int, Mapping[str, Any]] = {}
    for item in raw:
        mapping = _field_mapping(item, "review comparison")
        try:
            slide = int(mapping.get("slide"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Each review comparison needs an integer slide") from exc
        if slide in by_slide:
            raise ValueError(f"visual-review.json repeats comparison slide {slide}")
        by_slide[slide] = mapping
    if set(by_slide) != {int(item["slide"]) for item in inventory}:
        raise ValueError("visual-review.json comparisons do not match result.json coverage")
    for expected in inventory:
        actual = by_slide[int(expected["slide"])]
        expected_path = _resolve_comparison_path(evidence_path, expected["path"])
        actual_path = _resolve_comparison_path(
            evidence_path,
            actual.get("path", actual.get("comparison_path")),
        )
        if actual_path != expected_path:
            raise ValueError(f"Review comparison path differs for slide {expected['slide']}")
        expected_hash = str(expected["sha256"])
        actual_hash = actual.get("sha256", actual.get("comparison_sha256"))
        if actual_hash != expected_hash:
            raise ValueError(f"Review comparison hash differs for slide {expected['slide']}")


def _review_slides(
    review_payload: Mapping[str, Any],
    slide_count: int,
) -> list[dict[str, Any]]:
    raw = review_payload.get("slides")
    if not isinstance(raw, list):
        raise ValueError("visual-review.json must contain a slides list")
    by_slide: dict[int, Mapping[str, Any]] = {}
    for item in raw:
        mapping = _field_mapping(item, "review slide")
        try:
            slide = int(mapping.get("slide"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Each review slide needs an integer slide") from exc
        if slide in by_slide:
            raise ValueError(f"visual-review.json repeats slide {slide}")
        by_slide[slide] = mapping
    if set(by_slide) != set(range(1, slide_count + 1)):
        raise ValueError("visual-review.json must cover every slide exactly once")

    normalized: list[dict[str, Any]] = []
    for slide in range(1, slide_count + 1):
        mapping = by_slide[slide]
        status = str(mapping.get("status", "")).upper()
        reviewed = mapping.get("reviewed") is True
        if status not in {"PASS", "REVIEWED", "DONE"} and not reviewed:
            raise ValueError(f"Slide {slide} has not been marked reviewed")
        findings_value = mapping.get("findings", [])
        if not isinstance(findings_value, list):
            raise ValueError(f"Slide {slide} findings must be a list")
        findings: list[dict[str, Any]] = []
        for finding in findings_value:
            finding_mapping = _field_mapping(finding, f"slide {slide} finding")
            severity = str(finding_mapping.get("severity", "")).lower()
            if severity not in {"major", "minor"}:
                raise ValueError(
                    f"Slide {slide} findings must use only major or minor severity"
                )
            category = _required_text(
                finding_mapping,
                ("category", "type"),
                f"Slide {slide} finding",
            )
            location = _required_text(
                finding_mapping,
                ("location", "visible_location", "where"),
                f"Slide {slide} finding",
            )
            description = _required_text(
                finding_mapping,
                ("description", "message"),
                f"Slide {slide} finding",
            )
            normalized_finding = dict(finding_mapping)
            normalized_finding.update(
                {
                    "severity": severity,
                    "category": category,
                    "location": location,
                    "description": description,
                }
            )
            if severity == "major":
                normalized_finding["revision"] = _required_text(
                    finding_mapping,
                    ("revision", "revision_instruction", "action", "instruction", "next_step"),
                    f"Major slide {slide} finding",
                )
            findings.append(normalized_finding)
        normalized.append({"slide": slide, "status": status or "REVIEWED", "findings": findings})
    return normalized


def _finalization_payload(
    *,
    result_payload: Mapping[str, Any],
    review_payload: Mapping[str, Any],
    slides: Sequence[Mapping[str, Any]],
    outcome: str,
) -> dict[str, Any]:
    findings = [
        {"slide": int(slide["slide"]), "finding": dict(finding)}
        for slide in slides
        for finding in slide.get("findings", [])
    ]
    return {
        "schema_version": 1,
        "build_id": result_payload["build_id"],
        "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
        "outcome": outcome,
        "slide_count": int(result_payload["slide_count"]),
        "review_schema_version": review_payload.get("schema_version"),
        "findings": findings,
    }


def finalize_build(evidence_bundle: str | Path) -> CommandResult:
    """Validate one reviewed Evidence Bundle and derive its outcome."""
    evidence_path = _absolute(evidence_bundle)
    if not evidence_path.is_dir():
        return _invalid(
            "finalize",
            "invalid_evidence",
            f"Evidence Bundle does not exist: {evidence_path}",
            remediation="Provide the exact .evidence directory produced by build and retry.",
        )
    try:
        missing_evidence = [
            str(evidence_path / name)
            for name in EVIDENCE_FILES
            if not (evidence_path / name).is_file()
        ]
        if missing_evidence:
            raise ValueError("Evidence Bundle is incomplete: " + ", ".join(missing_evidence))
        result_payload = _read_json(evidence_path / "result.json", "result.json")
        review_payload = _read_json(evidence_path / "visual-review.json", "visual-review.json")
        for name in ("contract.json", "capabilities.json", "runtime.json", "manifest.json", "validate.json", "issues.json"):
            _read_json(evidence_path / name, name)
        if result_payload.get("schema_version") != 1:
            raise ValueError("result.json has an unsupported schema_version")
        if result_payload.get("product") != {"name": PRODUCT_NAME, "version": PRODUCT_VERSION}:
            raise ValueError("result.json product identity does not match this product")
        if result_payload.get("status") != "VISUAL_REVIEW_REQUIRED":
            raise ValueError("result.json is not a pending V0.2 build")
        build_id = result_payload.get("build_id")
        if not isinstance(build_id, str) or not build_id:
            raise ValueError("result.json must contain a build_id")
        if review_payload.get("schema_version") != VISUAL_REVIEW_SCHEMA_VERSION:
            raise ValueError("visual-review.json has an unsupported schema_version")
        if review_payload.get("build_id") != build_id:
            raise ValueError("visual-review.json build_id does not match result.json")
        if review_payload.get("product") != {"name": PRODUCT_NAME, "version": PRODUCT_VERSION}:
            raise ValueError("visual-review.json product identity does not match this product")

        html_info = _field_mapping(result_payload.get("author_html"), "result author_html")
        html_path = _absolute(_required_text(html_info, ("path",), "result author_html"))
        if not html_path.is_file():
            raise ValueError(f"Author HTML does not exist: {html_path}")
        _same_hash(html_path, html_info.get("sha256"), "Author HTML")
        pptx_info = _field_mapping(result_payload.get("pptx"), "result pptx")
        pptx_path = _absolute(_required_text(pptx_info, ("path",), "result pptx"))
        if not pptx_path.is_file():
            raise ValueError(f"PPTX does not exist: {pptx_path}")
        _same_hash(pptx_path, pptx_info.get("sha256"), "PPTX")
        review_html = _field_mapping(review_payload.get("author_html"), "review author_html")
        review_pptx = _field_mapping(review_payload.get("pptx"), "review pptx")
        if _absolute(_required_text(review_html, ("path",), "review author_html")) != html_path:
            raise ValueError("visual-review.json Author HTML path does not match result.json")
        if review_html.get("sha256") != html_info.get("sha256"):
            raise ValueError("visual-review.json Author HTML hash does not match result.json")
        if _absolute(_required_text(review_pptx, ("path",), "review pptx")) != pptx_path:
            raise ValueError("visual-review.json PPTX path does not match result.json")
        if review_pptx.get("sha256") != pptx_info.get("sha256"):
            raise ValueError("visual-review.json PPTX hash does not match result.json")
        declared_evidence = result_payload.get("evidence_path")
        if declared_evidence and _absolute(str(declared_evidence)) != evidence_path:
            raise ValueError("result.json evidence_path does not match the finalized bundle")

        inventory = _comparison_inventory(result_payload, evidence_path)
        _review_comparisons(review_payload, inventory, evidence_path)
        slides = _review_slides(review_payload, int(result_payload.get("slide_count", 0)))
        major = sum(
            1
            for slide in slides
            for finding in slide["findings"]
            if finding["severity"] == "major"
        )
        minor = sum(
            1
            for slide in slides
            for finding in slide["findings"]
            if finding["severity"] == "minor"
        )
        outcome = (
            "REVISION_REQUIRED"
            if major
            else "PASS_WITH_FINDINGS"
            if minor
            else "PASS"
        )
        finalization = _finalization_payload(
            result_payload=result_payload,
            review_payload=review_payload,
            slides=slides,
            outcome=outcome,
        )
        finalization_path = evidence_path / "finalization.json"
        temporary = evidence_path / ".finalization.json.tmp"
        _json_dump(temporary, finalization)
        temporary.replace(finalization_path)
        diagnostics: list[Diagnostic] = []
        for slide in slides:
            for finding in slide["findings"]:
                diagnostics.append(
                    Diagnostic(
                        code=f"review_{finding['severity']}_finding",
                        severity=finding["severity"],
                        message=(
                            f"Slide {slide['slide']}: {finding['description']} "
                            f"({finding['location']})"
                        ),
                        blocking=finding["severity"] == "major",
                        source_slide=int(slide["slide"]),
                        source_object=finding["location"],
                        remediation=finding.get("revision"),
                        recheck="officecli-html-to-pptx finalize --json <bundle.evidence>",
                    )
                )
        return result(
            "finalize",
            outcome,
            diagnostics=tuple(diagnostics),
            artifacts={"finalization": Artifact(finalization_path)},
            data={
                "build_id": build_id,
                "pptx_path": str(pptx_path),
                "evidence_path": str(evidence_path),
                "slide_count": int(result_payload["slide_count"]),
                "major_findings": major,
                "minor_findings": minor,
            },
        )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return _invalid("finalize", "invalid_evidence", str(exc))


__all__ = [
    "PUBLIC_COMMANDS",
    "build_author_html",
    "check_author_html",
    "diagnose_environment",
    "finalize_build",
    "get_capabilities",
]
