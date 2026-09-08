"""Repeatable OfficeCLI acceptance gate for the Algeria golden case.

The gate deliberately uses OfficeCLI for PPTX validation, inventory, reverse
projection, and screenshots.  ``python-pptx`` is not an oracle for the new
OfficeCLI path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping

from .compare import create_comparison, screenshot_html_slides
from .contract import (
    CONTRACT_VERSION,
    OFFICECLI_COMPATIBILITY_BASELINE,
    ContractReport,
    check_contract,
)
from .officecli_compiler import OfficeCLICompilationError, compile_officecli

PASS = "PASS"
KNOWN_BASELINE_DIFFERENCE = "KNOWN_BASELINE_DIFFERENCE"
UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
REGRESSION = "REGRESSION"

DEFAULT_AUTHOR_HTML = Path(
    os.environ.get(
        "HTML_TO_PPTX_ALGERIA_AUTHOR_HTML",
        r"D:\Opencodeworkspace\html-to-pptx\workspace\algeria\algeria\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html",
    )
)

# These are intentionally keyed by the generated stable object name and issue
# subtype.  A total count is not enough to tell a known baseline from a new
# regression when object order changes.
KNOWN_BASELINE_ISSUES = frozenset(
    {
        (1, "slide-001-textbox-012", "text_overflow"),
        (8, "slide-008-textbox-016", "text_overflow"),
        (8, "slide-008-textbox-020", "text_overflow"),
        (8, "slide-008-textbox-024", "text_overflow"),
        (8, "slide-008-textbox-028", "text_overflow"),
    }
)

_ISSUE_RE = re.compile(
    r"\[[A-Z]\d+\]\s+/slide\[(?P<slide>\d+)\]/"
    r"(?P<kind>[a-zA-Z]+)\[@id=(?P<id>\d+)\]:\s*(?P<message>.*)",
    re.I,
)
_PATH_LENGTH_RE = re.compile(
    r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(pt|emu|cm|mm|in)\s*$", re.I
)
_STRUCTURAL_ISSUE_MARKERS = (
    "schema",
    "shape_off_slide",
    "off-slide",
    "missing picture",
    "missing-picture",
    "table structure",
    "table-structure",
)


@dataclass(frozen=True)
class AcceptanceCheck:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class AcceptanceReport:
    status: str
    input_html: str
    output_dir: str
    checks: list[AcceptanceCheck] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "officecli_compatibility_baseline": OFFICECLI_COMPATIBILITY_BASELINE,
            "status": self.status,
            "input_html": self.input_html,
            "output_dir": self.output_dir,
            "checks": [check.as_dict() for check in self.checks],
            "findings": list(self.findings),
            "artifacts": dict(self.artifacts),
            "error": self.error,
        }

    def write(self) -> None:
        destination = Path(self.output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "acceptance-report.json").write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        lines = [
            "# Algeria OfficeCLI Acceptance Report",
            "",
            f"- Status: `{self.status}`",
            f"- Contract: `{CONTRACT_VERSION}`",
            f"- OfficeCLI baseline: `{OFFICECLI_COMPATIBILITY_BASELINE}`",
            f"- Input: `{self.input_html}`",
            "",
            "## Checks",
            "",
        ]
        for check in self.checks:
            lines.append(f"- `{check.status}` **{check.name}** — {check.message}")
        if self.findings:
            lines.extend(["", "## Findings", ""])
            for finding in self.findings:
                lines.append(f"- `{finding.get('status', REGRESSION)}` {finding.get('message', finding)}")
        if self.artifacts:
            lines.extend(["", "## Artifacts", ""])
            for name, path in sorted(self.artifacts.items()):
                lines.append(f"- `{name}`: `{path}`")
        if self.error:
            lines.extend(["", "## Error", "", self.error])
        (destination / "acceptance-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normal_text(value: Any) -> str:
    """Normalize only display whitespace introduced by OfficeHTML."""
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def _issue_subtype(message: str) -> str:
    lowered = message.lower()
    if "text overflow" in lowered:
        return "text_overflow"
    first = re.split(r"[:.]", lowered, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", "_", first).strip("_") or "unknown"


def issue_keys_from_officecli(
    issues: str,
    id_to_name: Mapping[tuple[int, int], str],
) -> list[dict[str, Any]]:
    """Extract stable issue identities from ``officecli view ... issues``."""
    keys: list[dict[str, Any]] = []
    for line in issues.splitlines():
        match = _ISSUE_RE.search(line)
        if match is None:
            continue
        slide = int(match.group("slide"))
        object_id = int(match.group("id"))
        object_identity = id_to_name.get((slide, object_id))
        if object_identity is None:
            object_identity = f"/slide[{slide}]/{match.group('kind')}[@id={object_id}]"
        keys.append(
            {
                "slide": slide,
                "object": object_identity,
                "subtype": _issue_subtype(match.group("message")),
            }
        )
    return keys


def _issue_tuple(item: Mapping[str, Any]) -> tuple[int, str, str]:
    return int(item["slide"]), str(item["object"]), str(item["subtype"])


def _points(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = _PATH_LENGTH_RE.fullmatch(str(value or ""))
    if match is None:
        raise ValueError(f"Unexpected OfficeCLI length: {value!r}")
    amount, unit = match.groups()
    number = float(amount)
    return {
        "pt": number,
        "emu": number / 12_700,
        "cm": number * 72 / 2.54,
        "mm": number * 72 / 25.4,
        "in": number * 72,
    }[unit.lower()]


def _approx_equal(left: Iterable[Any], right: Iterable[Any], tolerance: float) -> bool:
    left_values = list(left)
    right_values = list(right)
    return len(left_values) == len(right_values) and all(
        abs(float(a) - float(b)) <= tolerance for a, b in zip(left_values, right_values)
    )


def _manifest_objects(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item["name"]): item for item in manifest.get("objects", [])}


def compare_manifests(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    known_issue_keys: Iterable[Mapping[str, Any] | tuple[int, str, str]] = (),
) -> tuple[str, list[dict[str, Any]]]:
    """Compare supported normalized fields without comparing source paths."""
    findings: list[dict[str, Any]] = []

    def mismatch(message: str, **details: Any) -> None:
        findings.append({"status": REGRESSION, "message": message, **details})

    if expected.get("slide_count") != actual.get("slide_count"):
        mismatch("slide count differs", expected=expected.get("slide_count"), actual=actual.get("slide_count"))
    if expected.get("slide_size_pt") and actual.get("slide_size_pt"):
        left_size = expected["slide_size_pt"]
        right_size = actual["slide_size_pt"]
        if not _approx_equal(
            [left_size.get("width"), left_size.get("height")],
            [right_size.get("width"), right_size.get("height")],
            1.0,
        ):
            mismatch("slide size differs", expected=left_size, actual=right_size)
    if expected.get("object_kind_counts") != actual.get("object_kind_counts"):
        mismatch(
            "object-kind counts differ",
            expected=expected.get("object_kind_counts"),
            actual=actual.get("object_kind_counts"),
        )

    expected_objects = _manifest_objects(expected)
    actual_objects = _manifest_objects(actual)
    for name in sorted(set(expected_objects) | set(actual_objects)):
        left = expected_objects.get(name)
        right = actual_objects.get(name)
        if left is None or right is None:
            mismatch("stable object identity is missing", object=name)
            continue
        if left.get("kind") != right.get("kind"):
            mismatch("object kind differs", object=name, expected=left.get("kind"), actual=right.get("kind"))
        if not _approx_equal(left.get("bounds_pt", ()), right.get("bounds_pt", ()), 1.0):
            mismatch("object bounds differ by more than 1pt", object=name)
        if _normal_text(left.get("text")) != _normal_text(right.get("text")):
            mismatch("object text differs", object=name)
        if left.get("kind") == "table" and right.get("kind") == "table":
            for field_name in ("rows", "columns"):
                if left.get(field_name) != right.get(field_name):
                    mismatch(f"table {field_name} differ", object=name)
            if not _approx_equal(left.get("column_widths_pt", ()), right.get("column_widths_pt", ()), 0.5):
                mismatch("table column widths differ by more than 0.5pt", object=name)
            if not _approx_equal(left.get("row_heights_pt", ()), right.get("row_heights_pt", ()), 0.5):
                mismatch("table row heights differ by more than 0.5pt", object=name)
            left_cells = left.get("cells", ())
            right_cells = right.get("cells", ())
            if len(left_cells) != len(right_cells):
                mismatch("table cell count differs", object=name)
            for index, (left_cell, right_cell) in enumerate(zip(left_cells, right_cells)):
                if _normal_text(left_cell.get("text")) != _normal_text(right_cell.get("text")):
                    mismatch("table cell text differs", object=name, cell=index)

    known = {
        item if isinstance(item, tuple) else _issue_tuple(item)
        for item in known_issue_keys
    }
    status = REGRESSION if findings else (KNOWN_BASELINE_DIFFERENCE if known else PASS)
    return status, findings


class _AcceptanceToolError(RuntimeError):
    pass


def _run_officecli(*args: str | Path, json_output: bool = False) -> Any:
    command = ["officecli", *(str(arg) for arg in args)]
    if json_output:
        command.append("--json")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _AcceptanceToolError(f"{' '.join(command)} could not run: {exc}") from exc
    if result.returncode != 0:
        raise _AcceptanceToolError(
            f"{' '.join(command)} failed with exit code {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return json.loads(result.stdout) if json_output else result.stdout


def _walk(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in node.get("children", []) or []:
        yield from _walk(child)


def _children_by_slide(root: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    return [slide.get("children", []) for slide in root.get("children", []) or []]


def _officecli_manifest(pptx_path: Path) -> tuple[dict[str, Any], dict[tuple[int, int], str]]:
    shallow = _run_officecli("get", pptx_path, "/", "--depth", "1", json_output=True)["data"]["results"][0]
    deep = _run_officecli("get", pptx_path, "/", "--depth", "3", json_output=True)["data"]["results"][0]
    slides = _children_by_slide(shallow)
    deep_by_name = {
        str(node.get("format", {}).get("name")): node
        for node in _walk(deep)
        if node.get("format", {}).get("name")
    }
    objects: list[dict[str, Any]] = []
    id_to_name: dict[tuple[int, int], str] = {}
    for slide_index, children in enumerate(slides, start=1):
        for child in children:
            kind = str(child.get("type", ""))
            if kind not in {"shape", "textbox", "picture", "table"}:
                continue
            format_data = child.get("format", {})
            name = str(format_data.get("name", ""))
            if not name:
                raise _AcceptanceToolError(f"OfficeCLI object on slide {slide_index} has no stable name")
            if format_data.get("id") is not None:
                id_to_name[(slide_index, int(format_data["id"]))] = name
            object_data: dict[str, Any] = {
                "kind": kind,
                "name": name,
                "source_slide": slide_index,
                "source_object": child.get("path", ""),
                "bounds_pt": [_points(format_data.get(key)) for key in ("x", "y", "width", "height")],
                "text": child.get("text", "") or "",
            }
            detailed = deep_by_name.get(name, child)
            if kind == "table":
                object_data.update(_officecli_table_manifest(detailed))
            objects.append(object_data)
    slide_width = _points(shallow.get("format", {}).get("slideWidth"))
    slide_height = _points(shallow.get("format", {}).get("slideHeight"))
    counts: dict[str, int] = {}
    for item in objects:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return {
        "slide_count": len(slides),
        "slide_size_pt": {"width": slide_width, "height": slide_height},
        "object_kind_counts": counts,
        "objects": objects,
    }, id_to_name


def _officecli_table_manifest(table: Mapping[str, Any]) -> dict[str, Any]:
    format_data = table.get("format", {})
    rows = int(format_data.get("rows", 0))
    columns = int(format_data.get("cols", 0))
    column_widths = [_points(item) for item in str(format_data.get("colWidths", "")).split(",") if str(item).strip()]
    row_nodes = [node for node in table.get("children", []) or [] if node.get("type") == "tr"]
    row_heights = [_points(row.get("format", {}).get("height")) for row in row_nodes]
    table_x = _points(format_data.get("x"))
    table_y = _points(format_data.get("y"))
    cells: list[dict[str, Any]] = []
    for row_index, row in enumerate(row_nodes):
        cell_x = table_x
        for column_index, cell in enumerate(row.get("children", []) or []):
            if cell.get("type") != "tc":
                continue
            cell_format = cell.get("format", {})
            cell_width = column_widths[column_index] if column_index < len(column_widths) else 0.0
            cell_height = row_heights[row_index] if row_index < len(row_heights) else 0.0
            cells.append(
                {
                    "kind": "cell",
                    "name": cell_format.get("name", ""),
                    "source_object": cell.get("path", ""),
                    "bounds_pt": [cell_x, table_y + sum(row_heights[:row_index]), cell_width, cell_height],
                    "text": cell.get("text", "") or "",
                }
            )
            cell_x += cell_width
    return {
        "rows": rows,
        "columns": columns,
        "column_widths_pt": column_widths,
        "row_heights_pt": row_heights,
        "cells": cells,
    }


def _validate_with_officecli(pptx_path: Path) -> str:
    return str(_run_officecli("validate", pptx_path))


def _project_to_officehtml(pptx_path: Path, html_path: Path) -> None:
    _run_officecli("view", pptx_path, "html", "--out", html_path)


def _screenshot_pptx(pptx_path: Path, output_dir: Path, slide_count: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []
    for slide_number in range(1, slide_count + 1):
        path = output_dir / f"slide_{slide_number:02d}.png"
        _run_officecli("view", pptx_path, "screenshot", "--page", str(slide_number), "--out", path)
        if not path.is_file():
            raise _AcceptanceToolError(f"OfficeCLI did not create screenshot {path}")
        screenshots.append(path)
    return screenshots


def _record_manifest_check(
    report: AcceptanceReport,
    name: str,
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> bool:
    status, findings = compare_manifests(expected, actual)
    if findings:
        report.findings.extend(findings)
        report.checks.append(AcceptanceCheck(name, REGRESSION, "normalized manifest differs", {"findings": findings}))
        return False
    report.checks.append(AcceptanceCheck(name, PASS, "normalized manifest matches"))
    return True


def _final_status(report: AcceptanceReport, issue_keys: Iterable[Mapping[str, Any]]) -> str:
    if report.error or any(check.status == REGRESSION for check in report.checks):
        return REGRESSION
    tuples = {_issue_tuple(item) for item in issue_keys}
    unexpected = tuples - KNOWN_BASELINE_ISSUES
    if unexpected:
        report.findings.extend(
            {
                "status": REGRESSION,
                "message": "unallowlisted OfficeCLI issue",
                "issue": {"slide": slide, "object": name, "subtype": subtype},
            }
            for slide, name, subtype in sorted(unexpected)
        )
        return REGRESSION
    if tuples & KNOWN_BASELINE_ISSUES:
        for item in issue_keys:
            if _issue_tuple(item) in KNOWN_BASELINE_ISSUES:
                report.findings.append(
                    {
                        "status": KNOWN_BASELINE_DIFFERENCE,
                        "message": "known baseline OfficeCLI issue",
                        "issue": dict(item),
                    }
                )
        return KNOWN_BASELINE_DIFFERENCE
    return PASS


def _record_officecli_issue_gate(report: AcceptanceReport, issues: str) -> None:
    lowered = issues.lower()
    forbidden = [marker for marker in _STRUCTURAL_ISSUE_MARKERS if marker in lowered]
    if forbidden:
        finding = {
            "status": REGRESSION,
            "message": "OfficeCLI reported a forbidden structural issue",
            "markers": forbidden,
        }
        report.findings.append(finding)
        report.checks.append(
            AcceptanceCheck(
                "PPTX A issue gate",
                REGRESSION,
                "OfficeCLI structural issue is not allowlisted",
                finding,
            )
        )
    else:
        report.checks.append(
            AcceptanceCheck("PPTX A issue gate", PASS, "no forbidden structural OfficeCLI issue")
        )


async def run_algeria_acceptance(
    author_html: str | Path = DEFAULT_AUTHOR_HTML,
    output_dir: str | Path = "acceptance-output/algeria",
) -> AcceptanceReport:
    """Run the complete Algeria compilation, round-trip, inventory and visual gate."""
    input_path = Path(author_html).expanduser()
    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    report = AcceptanceReport(PASS, str(input_path), str(destination.resolve()))
    issue_keys: list[dict[str, Any]] = []

    try:
        contract = check_contract(input_path, "author")
        report.checks.append(
            AcceptanceCheck(
                "author contract",
                UNSUPPORTED_INPUT if contract.blocked else PASS,
                "author profile is blocked" if contract.blocked else "author profile is compatible",
                contract.as_dict(),
            )
        )
        report.artifacts["author-contract"] = str(destination / "author-contract.json")
        Path(report.artifacts["author-contract"]).write_text(
            json.dumps(contract.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if contract.blocked:
            report.status = UNSUPPORTED_INPUT
            report.error = "Author HTML contains blocking contract findings."
            report.write()
            return report

        pptx_a = destination / "algeria-a.pptx"
        officehtml_a = destination / "algeria-a.officehtml.html"
        pptx_b = destination / "algeria-b.pptx"
        first = await compile_officecli(str(input_path), "author", str(pptx_a))
        report.artifacts["pptx-a"] = str(pptx_a)
        report.checks.append(AcceptanceCheck("author compilation", PASS, "OfficeCLI PPTX A was compiled"))

        _validate_with_officecli(pptx_a)
        report.checks.append(AcceptanceCheck("PPTX A validation", PASS, "OfficeCLI validation passed"))
        observed_a, id_to_name = _officecli_manifest(pptx_a)
        report.checks.append(
            AcceptanceCheck(
                "PPTX A OfficeCLI inventory",
                PASS,
                "OfficeCLI inventory collected",
                {"object_kind_counts": observed_a["object_kind_counts"]},
            )
        )
        _record_manifest_check(report, "PPTX A normalized structure", first.manifest, observed_a)

        issues_a = str(_run_officecli("view", pptx_a, "issues"))
        issue_keys = issue_keys_from_officecli(issues_a, id_to_name)
        _record_officecli_issue_gate(report, issues_a)
        report.artifacts["pptx-a-issues"] = str(destination / "algeria-a.issues.txt")
        Path(report.artifacts["pptx-a-issues"]).write_text(issues_a, encoding="utf-8")

        _project_to_officehtml(pptx_a, officehtml_a)
        report.artifacts["officehtml-a"] = str(officehtml_a)
        report.checks.append(AcceptanceCheck("OfficeHTML projection", PASS, "OfficeCLI HTML projection was generated"))
        officehtml_contract = check_contract(officehtml_a, "officehtml")
        report.checks.append(
            AcceptanceCheck(
                "OfficeHTML contract",
                UNSUPPORTED_INPUT if officehtml_contract.blocked else PASS,
                "OfficeHTML projection is blocked" if officehtml_contract.blocked else "OfficeHTML projection is compatible",
                officehtml_contract.as_dict(),
            )
        )
        if officehtml_contract.blocked:
            report.status = UNSUPPORTED_INPUT
            report.error = "OfficeCLI HTML projection contains blocking contract findings."
            report.write()
            return report

        second = await compile_officecli(str(officehtml_a), "officehtml", str(pptx_b))
        report.artifacts["pptx-b"] = str(pptx_b)
        report.checks.append(AcceptanceCheck("OfficeHTML round-trip compilation", PASS, "PPTX B was compiled"))
        _validate_with_officecli(pptx_b)
        report.checks.append(AcceptanceCheck("PPTX B validation", PASS, "OfficeCLI validation passed"))
        observed_b, _ = _officecli_manifest(pptx_b)
        _record_manifest_check(report, "PPTX B normalized structure", second.manifest, observed_b)
        _record_manifest_check(report, "round-trip normalized manifest", first.manifest, second.manifest)

        visuals = destination / "visuals"
        (visuals / "author-html").mkdir(parents=True, exist_ok=True)
        (visuals / "side-by-side").mkdir(parents=True, exist_ok=True)
        html_shots = await screenshot_html_slides(input_path, visuals / "author-html")
        pptx_shots = _screenshot_pptx(pptx_a, visuals / "pptx-a", first.slide_count)
        comparisons = create_comparison(html_shots, pptx_shots, visuals / "side-by-side")
        if (
            len(html_shots) != first.slide_count
            or len(pptx_shots) != first.slide_count
            or len(comparisons) != first.slide_count
        ):
            raise _AcceptanceToolError(
                "Visual acceptance requires one Author HTML, PPTX, and side-by-side "
                f"screenshot per slide; got {len(html_shots)}, {len(pptx_shots)}, "
                f"and {len(comparisons)} for {first.slide_count} slides."
            )
        report.artifacts["author-html-screenshots"] = str((visuals / "author-html").resolve())
        report.artifacts["pptx-screenshots"] = str((visuals / "pptx-a").resolve())
        report.artifacts["side-by-side-screenshots"] = str((visuals / "side-by-side").resolve())
        report.checks.append(
            AcceptanceCheck(
                "visual screenshots",
                PASS,
                f"generated {len(html_shots)} HTML, {len(pptx_shots)} PPTX and {len(comparisons)} comparison images",
            )
        )
    except Exception as exc:
        report.error = str(exc)
        if isinstance(exc, OfficeCLICompilationError) and any(
            diagnostic.code.startswith(("unsupported_", "undecodable_", "invalid_"))
            for diagnostic in exc.diagnostics
        ):
            report.status = UNSUPPORTED_INPUT
        else:
            report.status = REGRESSION
    report.status = report.status if report.status == UNSUPPORTED_INPUT else _final_status(report, issue_keys)
    report.write()
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Run the Algeria OfficeCLI Contract v1 acceptance gate.")
    parser.add_argument("--input", default=str(DEFAULT_AUTHOR_HTML), help="Algeria Author HTML path")
    parser.add_argument("--output-dir", default="acceptance-output/algeria", help="empty output directory for artifacts")
    args = parser.parse_args(argv)
    report = asyncio.run(run_algeria_acceptance(args.input, args.output_dir))
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return {PASS: 0, KNOWN_BASELINE_DIFFERENCE: 0, UNSUPPORTED_INPUT: 2, REGRESSION: 1}[report.status]


__all__ = [
    "PASS",
    "KNOWN_BASELINE_DIFFERENCE",
    "UNSUPPORTED_INPUT",
    "REGRESSION",
    "KNOWN_BASELINE_ISSUES",
    "AcceptanceCheck",
    "AcceptanceReport",
    "compare_manifests",
    "issue_keys_from_officecli",
    "run_algeria_acceptance",
]


if __name__ == "__main__":
    raise SystemExit(main())
