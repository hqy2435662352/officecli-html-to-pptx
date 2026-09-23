"""Task-oriented V0.6.1 application operations.

The module is deliberately an orchestration layer, not a second renderer.  It
owns the public command semantics, the Artifact Pair transaction, and the
Evidence Bundle schemas while delegating Contract checking, Author lowering,
runtime discovery, and visual capture to the existing kernel helpers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
import re
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
from ._internal.acceptance import (
    _officecli_manifest,
    _run_officecli,
    _screenshot_pptx,
    compare_manifests,
)
from ._internal.compare import create_comparison, screenshot_html_slides
from ._internal.officecli_compiler import (
    CompilationDiagnostic,
    OfficeCLICompilationError,
    OfficeCLICompilationResult,
    compile_officecli,
)
from ._internal.localized_evidence import (
    LOCALIZED_DIAGNOSTIC_KEYS,
    audit_localized_fallbacks,
    validate_localized_evidence,
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
    PLATFORM_SCOPE_ENFORCED,
    PYTHON_TESTED_RANGE,
    SUPPORTED_PLATFORMS,
    UNVALIDATED_PLATFORM_NOTE,
    VALIDATED_PLATFORM_SCOPE,
    current_platform,
    diagnose_environment as _diagnose_runtime,
    officecli_runtime_snapshot,
)


PUBLIC_COMMANDS = ("capabilities", "doctor", "check", "build", "finalize", "workbench")
VISUAL_REVIEW_SCHEMA_VERSION = 1
NATIVE_EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_FILES = (
    "contract.json",
    "capabilities.json",
    "runtime.json",
    "manifest.json",
    "readback.json",
    "native-evidence.json",
    "validate.json",
    "issues.json",
    "result.json",
    "visual-review.json",
)
_OFFICECLI_ISSUE_COUNT_RE = re.compile(r"\bFound\s+(\d+)\s+issue\(s\)", re.IGNORECASE)
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
        "runtime_attestation": {
            "officecli": officecli_runtime_snapshot(),
        },
        # ``platform`` is where this command is running; ``supported_platforms``
        # is what this build supports.  A supported key is coarse -- the single
        # key "Linux" matches every distribution -- so the validated scope is
        # published beside it, together with the fact that the gate does not
        # verify it.  A key must never be read as a broader claim than the
        # Platform Acceptance Track supports.
        "platform": current_platform(),
        "supported_platforms": list(SUPPORTED_PLATFORMS),
        "validated_platform_scope": {
            "enforced": PLATFORM_SCOPE_ENFORCED,
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
        "workbench": {
            "command": "workbench",
            "source_authority": "saved_author_html_sha256",
            "preview_authoritative": False,
            "draft_check": True,
            "save_invalid_candidate": True,
            "build_requires": [
                "draft_sha256_equals_disk_sha256",
                "no_external_modification_conflict",
                "exact_saved_sha_contract_pass",
            ],
            "bind": "loopback-only",
            "session_token": "unguessable",
            "remote_network": False,
        },
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
    """Collect the OfficeCLI validation result for the Artifact Pair."""
    text = str(_run_officecli("validate", path))
    return {
        "status": "PASS",
        "output": text,
        "returncode": 0,
    }


def _collect_issues(path: Path) -> dict[str, Any]:
    text = str(_run_officecli("view", path, "issues"))
    match = _OFFICECLI_ISSUE_COUNT_RE.search(text)
    issue_count = int(match.group(1)) if match else None
    return {
        "status": "PASS",
        "output": text,
        "issue_count": issue_count,
        "returncode": 0,
    }


def _collect_readback(
    path: Path,
    expected_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read the published PPTX independently of the compiler manifest."""

    manifest, _ = _officecli_manifest(path, expected_manifest)
    return manifest


def _manifest_object_counts(manifest: Mapping[str, Any]) -> dict[str, int]:
    raw = manifest.get("object_kind_counts")
    if isinstance(raw, Mapping):
        return {str(key): int(value) for key, value in raw.items()}
    counts: dict[str, int] = {}
    for item in manifest.get("objects", []) or []:
        if isinstance(item, Mapping):
            kind = str(item.get("kind", ""))
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
    return counts


_ALPHA_COLOR_RE = re.compile(r"#[0-9a-fA-F]{8}(?=$|[\s:])")
_ANY_COLOR_RE = re.compile(r"#([0-9a-fA-F]{6,8})(?=$|[\s:])")


def _opacity_number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_alpha_color(
    actual_value: Any,
    expected_value: Any,
    expected_opacity: Any,
) -> Any:
    """Strip only a matching OfficeCLI alpha spelling from a readback color.

    OfficeCLI 1.0.151 can serialize the same native opacity both as the public
    ``opacity``/``lineOpacity`` property and as an alpha suffix on ``fill`` or
    ``line``.  The RGB value and the independent opacity remain strict: an
    alpha suffix is removed only when its RGB and alpha agree with the authored
    representation.  A changed color or opacity therefore still becomes a
    material finding.
    """

    actual_text = str(actual_value or "")
    expected_match = _ANY_COLOR_RE.search(str(expected_value or ""))
    actual_match = _ANY_COLOR_RE.search(actual_text)
    if not actual_match or not expected_match:
        return actual_value
    if len(actual_match.group(1)) != 8:
        return actual_value
    if actual_match.group(1)[:6].lower() != expected_match.group(1)[:6].lower():
        return actual_value
    expected_alpha = _opacity_number(expected_opacity)
    if expected_alpha is None:
        expected_alpha = (
            int(expected_match.group(1)[6:], 16) / 255.0
            if len(expected_match.group(1)) == 8
            else 1.0
        )
    actual_alpha = int(actual_match.group(1)[6:], 16) / 255.0
    if abs(actual_alpha - expected_alpha) > 0.01:
        return actual_value
    return _ALPHA_COLOR_RE.sub(
        f"#{actual_match.group(1)[:6].upper()}", actual_text, count=1
    )


def _normalize_readback_paragraph(paragraph: Any) -> None:
    if not isinstance(paragraph, dict) or str(paragraph.get("text", "")):
        return
    runs = paragraph.get("runs")
    if isinstance(runs, list):
        # The readback adapter materializes one empty run for authored empty
        # paragraphs.  Paragraph count, spacing, direction, and hard breaks
        # remain strict; only this non-semantic child is removed.
        paragraph["runs"] = [
            run for run in runs if isinstance(run, Mapping) and str(run.get("text", ""))
        ]


def _normalize_readback_item(
    expected: Mapping[str, Any] | None,
    actual: dict[str, Any],
) -> None:
    expected_properties = (
        expected.get("properties", {}) if isinstance(expected, Mapping) else {}
    )
    properties = actual.get("properties")
    if isinstance(properties, dict) and isinstance(expected_properties, Mapping):
        if "fill" in properties:
            properties["fill"] = _normalize_alpha_color(
                properties.get("fill"),
                expected_properties.get("fill"),
                expected_properties.get("opacity"),
            )
        if "line" in properties:
            properties["line"] = _normalize_alpha_color(
                properties.get("line"),
                expected_properties.get("line"),
                expected_properties.get("lineOpacity"),
            )
    for paragraph in actual.get("paragraphs", []) or []:
        _normalize_readback_paragraph(paragraph)

    expected_cells = expected.get("cells", []) if isinstance(expected, Mapping) else []
    for index, cell in enumerate(actual.get("cells", []) or []):
        if not isinstance(cell, dict):
            continue
        expected_cell = (
            expected_cells[index]
            if index < len(expected_cells) and isinstance(expected_cells[index], Mapping)
            else None
        )
        expected_cell_props = (
            expected_cell.get("props", {}) if isinstance(expected_cell, Mapping) else {}
        )
        cell_props = cell.get("props")
        if isinstance(cell_props, dict) and isinstance(expected_cell_props, Mapping):
            if "fill" in cell_props:
                cell_props["fill"] = _normalize_alpha_color(
                    cell_props.get("fill"),
                    expected_cell_props.get("fill"),
                    expected_cell_props.get("opacity"),
                )
            if "line" in cell_props:
                cell_props["line"] = _normalize_alpha_color(
                    cell_props.get("line"),
                    expected_cell_props.get("line"),
                    expected_cell_props.get("lineOpacity"),
                )
        for paragraph in cell.get("paragraphs", []) or []:
            _normalize_readback_paragraph(paragraph)


def _normalize_native_readback_noise(
    expected: Mapping[str, Any], readback: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a strict readback manifest with only two serializer noises removed."""

    normalized = deepcopy(dict(readback))
    expected_objects = {
        str(item.get("name")): item
        for item in expected.get("objects", []) or []
        if isinstance(item, Mapping) and item.get("name")
    }
    for item in normalized.get("objects", []) or []:
        if isinstance(item, dict):
            _normalize_readback_item(expected_objects.get(str(item.get("name"))), item)
    return normalized


def _native_material_delta_count(
    compiled: Mapping[str, Any], readback: Mapping[str, Any]
) -> int:
    """Count all supported native-field findings after narrow readback cleanup."""

    _, findings = compare_manifests(
        compiled,
        _normalize_native_readback_noise(compiled, readback),
    )
    return len(findings)


def _native_slice_evidence(
    *,
    compiled: OfficeCLICompilationResult,
    readback: Mapping[str, Any],
    runtime: Mapping[str, Any],
    validation: Mapping[str, Any] | None = None,
    issues: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize the native-slice evidence required by Contract 1.3."""

    capability = author_capability_manifest()
    compiled_objects = [
        item for item in compiled.manifest.get("objects", []) or []
        if isinstance(item, Mapping)
    ]
    readback_objects = [
        item for item in readback.get("objects", []) or []
        if isinstance(item, Mapping)
    ]
    text_kinds = {"shape", "textbox"}
    text_structure = {
        "compiled": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "paragraphs": item.get("paragraphs", []),
            }
            for item in compiled_objects
            if item.get("kind") in text_kinds and item.get("paragraphs")
        ],
        "readback": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "paragraphs": item.get("paragraphs", []),
            }
            for item in readback_objects
            if item.get("kind") in text_kinds and item.get("paragraphs")
        ],
    }
    merge_topology = [
        {
            "name": item.get("name"),
            "source_slide": item.get("source_slide"),
            "rows": item.get("rows", 0),
            "columns": item.get("columns", 0),
            "normalized_merge_topology": item.get("normalized_merge_topology", []),
        }
        for item in readback_objects
        if item.get("kind") == "table"
    ]
    native_geometry = [
        {
            "name": item.get("name"),
            "source_slide": item.get("source_slide"),
            "geometry": (item.get("properties") or {}).get("geometry"),
        }
        for item in readback_objects
        if item.get("kind") == "shape"
        and (item.get("properties") or {}).get("geometry")
    ]
    chart_structure = {
        "compiled": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "bounds_pt": item.get("bounds_pt", []),
                "chart": item.get("chart", {}),
                "chart_seam": item.get("chart_seam", {}),
            }
            for item in compiled_objects
            if item.get("kind") == "chart"
        ],
        "readback": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "bounds_pt": item.get("bounds_pt", []),
                "native_kind": item.get("native_kind"),
                "chart": item.get("chart", {}),
                "chart_seam": item.get("chart_seam", {}),
            }
            for item in readback_objects
            if item.get("kind") == "chart"
        ],
    }
    localized_fallbacks = {
        "compiled": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "source_identity": item.get("source_identity"),
                "source_object": item.get("source_object"),
                "compiled_kind": item.get("compiled_kind", item.get("kind")),
                "disposition": item.get("disposition"),
                "editable": item.get("editable"),
                "bounds_pt": item.get("bounds_pt", []),
                "localized_fallback": item.get("localized_fallback", {}),
            }
            for item in compiled_objects
            if item.get("disposition") == "rasterized"
        ],
        "readback": [
            {
                "name": item.get("name"),
                "source_slide": item.get("source_slide"),
                "source_identity": item.get("source_identity"),
                "compiled_kind": item.get("compiled_kind", item.get("kind")),
                "disposition": item.get("disposition"),
                "editable": item.get("editable"),
                "bounds_pt": item.get("bounds_pt", []),
                "localized_fallback": item.get("localized_fallback", {}),
            }
            for item in readback_objects
            if item.get("disposition") == "rasterized"
        ],
    }
    readback_native_counts: dict[str, int] = {}
    for item in readback_objects:
        if item.get("disposition") != "rasterized":
            kind = str(item.get("kind", ""))
            if kind:
                readback_native_counts[kind] = readback_native_counts.get(kind, 0) + 1
    compiled_chart_count = sum(
        item.get("kind") == "chart" for item in compiled_objects
    )
    readback_chart_count = sum(
        item.get("kind") == "chart" for item in readback_objects
    )
    compiler_diagnostics = [
        item.as_dict() for item in compiled.diagnostics
    ]
    localized = audit_localized_fallbacks(compiled.manifest, readback)
    diagnostics = {
        "unsupported": sum(
            item["code"].startswith("unsupported_")
            for item in compiler_diagnostics
        ) + int(localized["diagnostics"]["unsupported"]),
        "unresolved": sum(
            item["code"].startswith("unresolved_")
            for item in compiler_diagnostics
        ) + int(localized["diagnostics"]["unresolved"]),
        "material_delta": _native_material_delta_count(
            compiled.manifest, readback
        ) + int(localized["diagnostics"]["material_delta"]),
        "compiler": compiler_diagnostics,
    }
    evidence = {
        "schema_version": NATIVE_EVIDENCE_SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "officecli_compatibility_baseline": OFFICECLI_COMPATIBILITY_BASELINE,
        "runtime": {"officecli": dict(runtime.get("officecli", {}))},
        "frozen_text_matrix": {
            "run": capability["mixed_run_surface"],
            "paragraph": capability["paragraph_layout_surface"],
        },
        "text_structure": text_structure,
        "normalized_merge_topology": merge_topology,
        "native_geometry": native_geometry,
        "charts": chart_structure,
        "localized_fallbacks": localized_fallbacks,
        "validation": dict(validation or {}),
        "issues": dict(issues or {}),
        "counts": {
            "authored_object_count": int(compiled.object_count),
            "compiled_object_count": len(compiled_objects),
            "readback_object_count": len(readback_objects),
            "compiled_object_kind_counts": _manifest_object_counts(compiled.manifest),
            "readback_object_kind_counts": _manifest_object_counts(readback),
            "compiled_native_object_kind_counts": dict(
                compiled.manifest.get("native_object_kind_counts", {})
            ),
            "readback_native_object_kind_counts": readback_native_counts,
            "rasterized_object_count": len(localized_fallbacks["compiled"]),
            "chart_counts": {
                "authored": compiled_chart_count,
                "compiled": compiled_chart_count,
                "readback": readback_chart_count,
            },
        },
        "diagnostics": diagnostics,
        "gate3": {"status": "PENDING", "slide_count": int(compiled.slide_count)},
    }
    if localized["records"]:
        evidence["localized_fallback"] = localized
        evidence["counts"].update(
            {
                "native_object_count": localized["counts"]["native_object_count"],
                "native_object_kind_counts": localized["counts"]["native_object_kind_counts"],
                "native_ratio": localized["counts"]["native_ratio"],
                "rasterized_count": localized["counts"]["rasterized_count"],
            }
        )
        evidence["diagnostics"].update(
            {
                key: int(value)
                for key, value in localized["diagnostics"].items()
                if key not in {"unsupported", "unresolved", "material_delta"}
            }
        )
    return evidence


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
            if any(
                item.code.startswith(
                    ("unsupported_", "undecodable_", "invalid_", "unresolved_")
                )
                for item in exc.diagnostics
            ):
                return result("build", "BLOCK", diagnostics=diagnostics)
            return result("build", "ERROR", diagnostics=diagnostics)
        except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
            return _error("build", str(exc))

        slide_count = int(compiled.slide_count)
        validation = _validate_build_output(staged_pptx)
        issues = _collect_issues(staged_pptx)
        readback = _collect_readback(staged_pptx, compiled.manifest)
        native_evidence = _native_slice_evidence(
            compiled=compiled,
            readback=readback,
            runtime=diagnosis.data.get("runtime", {}),
            validation=validation,
            issues=issues,
        )
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
            "readback_path": str(evidence_path / "readback.json"),
            "native_evidence_path": str(evidence_path / "native-evidence.json"),
            "native_evidence": {
                "diagnostics": native_evidence["diagnostics"],
                "counts": native_evidence["counts"],
                "gate3": native_evidence["gate3"],
            },
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
        capability_evidence = dict(get_capabilities().data)
        capability_evidence["runtime_attestation"] = {
            "officecli": dict(
                _field_mapping(
                    diagnosis.data.get("runtime", {}).get("officecli", {}),
                    "doctor OfficeCLI runtime",
                )
            )
        }
        _json_dump(staged_evidence / "capabilities.json", capability_evidence)
        _json_dump(staged_evidence / "runtime.json", diagnosis.data.get("runtime", {}))
        _json_dump(staged_evidence / "manifest.json", compiled.manifest)
        _json_dump(staged_evidence / "readback.json", readback)
        _json_dump(staged_evidence / "native-evidence.json", native_evidence)
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

        # OfficeCLI 1.0.151 may keep validation/view results in a resident
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
        "gate3": {
            "status": "REVISION_REQUIRED" if any(
                finding.get("severity") == "major"
                for slide in slides
                for finding in slide.get("findings", [])
            ) else "PASS",
            "reviewed_slides": len(slides),
        },
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
        for name in (
            "contract.json",
            "capabilities.json",
            "runtime.json",
            "manifest.json",
            "readback.json",
            "native-evidence.json",
            "validate.json",
            "issues.json",
        ):
            _read_json(evidence_path / name, name)
        manifest = _read_json(evidence_path / "manifest.json", "manifest.json")
        validation = _read_json(evidence_path / "validate.json", "validate.json")
        issues = _read_json(evidence_path / "issues.json", "issues.json")
        if validation.get("status") != "PASS":
            raise ValueError("validate.json does not record OfficeCLI validation PASS")
        native_evidence = _read_json(
            evidence_path / "native-evidence.json", "native-evidence.json"
        )
        readback = _read_json(evidence_path / "readback.json", "readback.json")
        if native_evidence.get("product_version") != PRODUCT_VERSION:
            raise ValueError("native-evidence.json product version does not match this product")
        if native_evidence.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("native-evidence.json contract version does not match this product")
        officecli_runtime = _field_mapping(
            _field_mapping(native_evidence.get("runtime"), "native evidence runtime").get(
                "officecli"
            ),
            "native evidence OfficeCLI runtime",
        )
        if not str(officecli_runtime.get("discovered_version", "")).strip():
            raise ValueError("native-evidence.json must record the actual OfficeCLI runtime")
        if officecli_runtime.get("compatible") is not True:
            raise ValueError("native-evidence.json OfficeCLI runtime is below the Contract 1.3 floor")
        diagnostic_counts = _field_mapping(
            native_evidence.get("diagnostics"), "native evidence diagnostics"
        )
        for key in ("unsupported", "unresolved", "material_delta"):
            if diagnostic_counts.get(key) != 0:
                raise ValueError(
                    f"native-evidence.json {key} must be zero before finalization"
                )
        localized_evidence = native_evidence.get("localized_fallback")
        if localized_evidence is not None:
            for key in LOCALIZED_DIAGNOSTIC_KEYS:
                if diagnostic_counts.get(key, 0) != 0:
                    raise ValueError(
                        f"native-evidence.json {key} must be zero before finalization"
                    )
            localized_errors = validate_localized_evidence(
                _field_mapping(localized_evidence, "localized fallback evidence"),
                manifest,
                readback,
            )
            if localized_errors:
                raise ValueError("; ".join(localized_errors))
        counts = _field_mapping(native_evidence.get("counts"), "native evidence counts")
        if counts.get("readback_object_count") != len(readback.get("objects", []) or []):
            raise ValueError("native-evidence.json readback object count does not match readback.json")
        chart_counts = counts.get("chart_counts", {})
        if isinstance(chart_counts, Mapping) and any(chart_counts.values()):
            if chart_counts.get("authored") != chart_counts.get("compiled"):
                raise ValueError("native-evidence.json authored and compiled chart counts differ")
            if chart_counts.get("compiled") != chart_counts.get("readback"):
                raise ValueError("native-evidence.json compiled and readback chart counts differ")
            if issues.get("status") != "PASS" or issues.get("issue_count") != 0:
                raise ValueError("issues.json must record zero OfficeCLI issues for native-chart finalization")
            charts = _field_mapping(native_evidence.get("charts"), "native evidence charts")
            compiled_charts = charts.get("compiled", [])
            readback_charts = charts.get("readback", [])
            if not isinstance(compiled_charts, list) or not isinstance(readback_charts, list):
                raise ValueError("native-evidence.json chart evidence must contain lists")
            if len(compiled_charts) != chart_counts.get("compiled") or len(readback_charts) != chart_counts.get("readback"):
                raise ValueError("native-evidence.json chart evidence count does not match chart_counts")
            if any(item.get("native_kind") != "chart" for item in readback_charts if isinstance(item, Mapping)):
                raise ValueError("native-evidence.json readback chart proof is not native")
        if result_payload.get("schema_version") != 1:
            raise ValueError("result.json has an unsupported schema_version")
        if result_payload.get("product") != {"name": PRODUCT_NAME, "version": PRODUCT_VERSION}:
            raise ValueError("result.json product identity does not match this product")
        if result_payload.get("status") != "VISUAL_REVIEW_REQUIRED":
            raise ValueError("result.json is not a pending Product 0.6.1 build")
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
        native_gate3 = _field_mapping(
            native_evidence.get("gate3"), "native evidence Gate 3"
        )
        native_gate3["status"] = finalization["gate3"]["status"]
        native_gate3["reviewed_slides"] = len(slides)
        native_evidence["gate3"] = native_gate3
        _json_dump(evidence_path / "native-evidence.json", native_evidence)
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
