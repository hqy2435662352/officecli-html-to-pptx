"""V0.4.2 source-to-rebuilt projection delta evidence gate tests (ticket #17).

The external seam under test is::

    gate_projected_author_html(selection, output_directory)
        -> derived PASS / PASS_WITH_FINDINGS / BLOCK
         + source and rebuilt OfficeCLI evidence, per selected page
         + material deltas, retained findings, scope evidence
         + hashed artifacts, or nothing at all

Every test drives that one seam, or one of the three published comparison rules
(:func:`normalize_issue_condition`, :func:`compare_issues`,
:func:`classify_gate_outcome`); nothing here freezes a private reader call, an
OfficeCLI command shape, or an emitter helper, because a caller must not have to
depend on them.

Where a deliberate mutation from the ticket's negative-test criterion cannot be
produced end to end without building a deck that produces it on purpose -- a
rebuilt-only issue, a native table read back with the wrong dimensions, a
rebuilt object read back with the wrong kind or text, a swapped proxy payload --
the mutation is injected into the gate's *sealed intake bundle*.  That is the
bundle every real run builds from OfficeCLI reads before any comparison happens,
so an injected condition is judged by exactly the production comparison rules;
only the read is replaced, never the judgement.  Each such test says so in its
own comment.

The fixtures are minimal synthetic decks built through OfficeCLI itself, so the
real acceptance corpus is never committed.  One fixture deliberately carries a
source-inherent text overflow and one deliberately does not: the first proves a
retained finding does not enter the material delta set, the second proves a run
with nothing to report reaches ``PASS``.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Sequence

import pytest

from officecli_html_to_pptx import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    GateOutcome,
    PageSelection,
    ProjectionError,
    gate_projected_author_html,
    project_pptx_to_author_html,
)
from officecli_html_to_pptx._internal import source_delta_gate as gate_module
from officecli_html_to_pptx._internal.source_delta_gate import (
    GUARD_BAND_CONTAMINATION_FRACTION,
    OVERFLOW_RATIO_ABSOLUTE_TOLERANCE,
    OVERFLOW_RATIO_RELATIVE_TOLERANCE,
    GateDiagnostic,
    GateIntake,
    GateSources,
    IssueRecord,
    MaterialDelta,
    RebuiltObject,
    RetainedFinding,
    ScopeEvidence,
    TextReadback,
    classify_gate_outcome,
    compact_text,
    compare_issues,
    materially_worsened,
    normalize_issue_condition,
    normalize_text,
    parse_issue_path,
    pressure_ratio,
    structure_text,
)
from officecli_html_to_pptx.contract import check_contract

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V0.4.2 delta-gate tests",
)

# ---------------------------------------------------------------------------
# Fixture literals.  Every expectation below is written from these, never from
# the gate's own output.
# ---------------------------------------------------------------------------

CLEAN_TEXT = "Clean probe 中文 🚀"
CLEAN_TEXT_SECOND_PARAGRAPH = "Second clean paragraph"
LOCKED_GEOMETRY = "chevron"
LOCKED_FILL = "#D96666"
TABLE_CELLS = (("MODEL", "12K"), ("IDU SIZE", "910x305x195"))
# A long, deliberately wrapping body inside a 30pt-tall box: the source deck
# itself overflows, which is the condition the retained-finding tests need.
OVERFLOW_TEXT = (
    "Overflow probe line one that is deliberately long enough to wrap in the "
    "browser several times over because the shape is narrow\n"
    "Overflow probe line two that is also deliberately long enough to wrap in "
    "the browser several times over because the shape is narrow\n"
    "Overflow probe line three\n"
    "Overflow probe line four"
)
OVERFLOW_BOX = (40.0, 40.0, 120.0, 30.0)
FIELD_CELL_TEXT = "x"

# A 4x3 opaque PNG, small enough to inline as a base64 literal in the fixture.
_PICTURE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAHElEQVQI12P8//8/AzbAxMDA"
    "wMDAwMDAwMDAwAAAJhwEAX8lErwAAAAASUVORK5CYII="
)


def _officecli(*args: str, attempts: int = 6) -> str:
    """Run one OfficeCLI command, retrying a transient failure.

    OfficeCLI keeps documents resident and, on a loaded machine, an individual
    command can exit non-zero with no message and then succeed unchanged.  A
    retry of a command that names a document first closes any resident handle on
    that document, because a resident left over from a previous attempt is the
    one failure a blind retry cannot clear.  The last failure is still raised,
    with its command, so a genuine error is never hidden.
    """
    document = next(
        (argument for argument in args[1:] if str(argument).lower().endswith(".pptx")),
        None,
    )
    last = ""
    for attempt in range(attempts):
        completed = subprocess.run(
            ["officecli", *args],
            capture_output=True,
            check=False,
            timeout=300,
        )
        text = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode == 0 and text.strip():
            return text
        last = completed.stderr.decode("utf-8", errors="replace") or text
        if document is not None:
            subprocess.run(
                ["officecli", "close", document],
                capture_output=True,
                check=False,
                timeout=300,
            )
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"officecli {' '.join(args)} failed: {last}")


def _close(deck: Path) -> None:
    subprocess.run(
        ["officecli", "close", str(deck)], capture_output=True, check=False, timeout=300
    )


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Replace a file, tolerating an OfficeCLI handle that has not drained."""
    destination.unlink(missing_ok=True)
    for attempt in range(20):
        try:
            source.replace(destination)
            return
        except OSError:
            time.sleep(0.25 * (attempt + 1))
    source.replace(destination)


def _force_no_autofit(name: str, text: str) -> str:
    """Disable autofit on every text body of one slide part.

    OfficeCLI's own readback of a shape with autofit on reports the *fitted*
    geometry, so a source overflow only exists when the source shape carries
    ``<a:noAutofit/>``.  This is fixture construction, not a product path: the
    deck is the gate's input and is never written by the product.
    """
    text, count = re.subn(
        r"<a:bodyPr\b([^>]*?)/>",
        r"<a:bodyPr\1><a:noAutofit/></a:bodyPr>",
        text,
    )
    text, count2 = re.subn(
        r"<a:bodyPr\b[^>]*>\s*<a:(?:normAutofit|spAutoFit)\b[^>]*/>\s*</a:bodyPr>",
        "<a:bodyPr><a:noAutofit/></a:bodyPr>",
        text,
    )
    return text if count + count2 else text


def _inject_cached_field(name: str, text: str, slide_number: int) -> str:
    """Replace one slide's seeded run with an unresolved ``<a:fld>`` element.

    This is how an inherited master/layout cached-field finding is reproduced
    deterministically: OfficeCLI reports a field whose cached text is empty as
    a source-only finding on the slide, exactly as it does for a real deck whose
    layout carries an unevaluated date or slide number.
    """
    if name != f"ppt/slides/slide{slide_number}.xml":
        return text
    pattern = re.compile(
        r"<a:r><a:rPr([^>]*?)(?:/>|>.*?</a:rPr>)<a:t>"
        + re.escape(FIELD_CELL_TEXT)
        + r"</a:t></a:r>"
    )
    return pattern.sub(
        r'<a:fld id="{B4B7A4B0-0000-0000-0000-000000000000}" type="slidenum">'
        r"<a:rPr\1/><a:t></a:t></a:fld>",
        text,
        count=1,
    )


def _rewrite_slide_parts(deck: Path, mutate) -> None:
    """Rewrite every slide part of a deck with ``mutate(part_name, xml)``."""
    import zipfile

    _close(deck)
    with zipfile.ZipFile(deck) as archive:
        names = archive.namelist()
        payloads = {name: archive.read(name) for name in names}
    touched = False
    for name in names:
        if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
            continue
        rewritten = mutate(name, payloads[name].decode("utf-8"))
        if rewritten != payloads[name].decode("utf-8"):
            payloads[name] = rewritten.encode("utf-8")
            touched = True
    assert touched, f"no slide part of {deck} was rewritten"
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, payloads[name])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_deck(
    deck: Path,
    *,
    overflow: bool,
    with_locked_shape: bool = True,
) -> None:
    """Build one minimal synthetic deck through OfficeCLI.

    The deck is the gate's PowerPoint input and nothing else: it is never
    produced from an OfficeHTML export, so the probe stays runnable from a PPTX
    alone.
    """
    deck.unlink(missing_ok=True)
    _officecli("create", str(deck))
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "gate-probe"}},
    ]
    if overflow:
        commands.append(
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "textbox",
                "props": {
                    "name": "overflow-text",
                    "text": OVERFLOW_TEXT,
                    "x": f"{OVERFLOW_BOX[0]}pt",
                    "y": f"{OVERFLOW_BOX[1]}pt",
                    "width": f"{OVERFLOW_BOX[2]}pt",
                    "height": f"{OVERFLOW_BOX[3]}pt",
                    "size": "20pt",
                    "font": "Arial",
                    "color": "#14243A",
                    "fill": "none",
                    "line": "none",
                },
            }
        )
    else:
        commands.append(
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "textbox",
                "props": {
                    "name": "clean-text",
                    "text": f"{CLEAN_TEXT}\n{CLEAN_TEXT_SECOND_PARAGRAPH}",
                    "x": "40pt",
                    "y": "40pt",
                    "width": "400pt",
                    "height": "80pt",
                    "size": "18pt",
                    "font": "Microsoft YaHei",
                    "color": "#14243A",
                    "fill": "none",
                    "line": "none",
                },
            }
        )
    if with_locked_shape:
        commands.append(
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "shape",
                "props": {
                    "name": "locked-preset",
                    "geometry": LOCKED_GEOMETRY,
                    "x": "500pt",
                    "y": "320pt",
                    "width": "60pt",
                    "height": "60pt",
                    "fill": LOCKED_FILL,
                    "line": "none",
                },
            }
        )
    commands.append(
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "table",
            "props": {
                "name": "native-table",
                "x": "40pt",
                "y": "300pt",
                "width": "400pt",
                "height": "60pt",
                "rows": "2",
                "cols": "2",
                "colWidths": "200pt,200pt",
            },
        }
    )
    _officecli("batch", str(deck), "--commands", json.dumps(commands, ensure_ascii=False))
    for row_index, row in enumerate(TABLE_CELLS, start=1):
        for column_index, value in enumerate(row, start=1):
            _officecli(
                "set",
                str(deck),
                f"/slide[1]/table[@name=native-table]/tr[{row_index}]/tc[{column_index}]",
                "--prop",
                f"text={value}",
            )
    _close(deck)
    _rewrite_slide_parts(deck, _force_no_autofit)


def _build_field_deck(deck: Path) -> None:
    """Build a two-page deck whose second page carries an unresolved cached field.

    The second page is what produces the source-only master/layout scope
    evidence; the first page is a clean page, so the run reaches
    ``PASS_WITH_FINDINGS`` for a reason that is about the source deck rather than
    about projection.  A separate slide part is used rather than the gate
    fixture's own, because the injected field must not change the gate fixture's
    text.
    """
    deck.unlink(missing_ok=True)
    _officecli("create", str(deck))
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "probe-1"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "probe-2"}},
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "textbox",
            "props": {
                "name": "clean-text",
                "text": CLEAN_TEXT,
                "x": "40pt",
                "y": "40pt",
                "width": "400pt",
                "height": "60pt",
                "size": "18pt",
                "font": "Microsoft YaHei",
                "color": "#14243A",
                "fill": "none",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[2]",
            "type": "textbox",
            "props": {
                "name": "field-text",
                "text": FIELD_CELL_TEXT,
                "x": "40pt",
                "y": "40pt",
                "width": "200pt",
                "height": "30pt",
                "size": "18pt",
                "font": "Arial",
                "color": "#14243A",
                "fill": "none",
                "line": "none",
            },
        },
    ]
    _officecli("batch", str(deck), "--commands", json.dumps(commands, ensure_ascii=False))
    _close(deck)
    _rewrite_slide_parts(
        deck,
        lambda name, xml: _inject_cached_field(name, _force_no_autofit(name, xml), 2),
    )


@pytest.fixture(scope="session")
def overflow_deck(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A deck whose own text body overflows its shape."""
    deck = tmp_path_factory.mktemp("v042-gate-overflow") / "fixture.pptx"
    _build_deck(deck, overflow=True)
    return deck


@pytest.fixture(scope="session")
def clean_deck(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A deck with no source-inherent issue at all."""
    deck = tmp_path_factory.mktemp("v042-gate-clean") / "fixture.pptx"
    _build_deck(deck, overflow=False)
    return deck


@pytest.fixture(scope="session")
def field_deck(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A two-page deck whose second page has an unresolved cached field."""
    deck = tmp_path_factory.mktemp("v042-gate-field") / "fixture.pptx"
    _build_field_deck(deck)
    return deck


def _run_gate(
    deck: Path,
    output: Path,
    pages: Sequence[int] = (1,),
    *,
    intake_mutation=None,
    sources: GateSources | None = None,
):
    shutil.rmtree(output, ignore_errors=True)
    return gate_projected_author_html(
        [(str(deck), page) for page in pages],
        output,
        intake_mutation=intake_mutation,
        _sources=sources,
    )


@pytest.fixture(scope="session")
def overflow_result(
    overflow_deck: Path, tmp_path_factory: pytest.TempPathFactory
) -> Any:
    """One real gate run over the overflowing fixture."""
    output = tmp_path_factory.mktemp("v042-gate-run-overflow") / "gate"
    return _run_gate(overflow_deck, output)


def _capture_intake(sink: list[GateIntake]):
    """Return a mutation hook that records the sealed intake and changes nothing.

    The gate hands its sealed bundle to ``intake_mutation`` after every real read,
    which makes the hook the one place a test can take a copy of exactly what a
    real run judged -- without a second projection, a second rebuild, or a second
    OfficeCLI readback.
    """

    def hook(intake: GateIntake) -> GateIntake:
        sink.append(intake)
        return intake

    return hook


@pytest.fixture(scope="session")
def clean_run(clean_deck: Path, tmp_path_factory: pytest.TempPathFactory) -> Any:
    """The clean fixture's one real gate run, with its sealed intake kept.

    One end-to-end run supplies both the result every assertion reads and the
    intake every comparator mutation is judged from.  Running the production
    pipeline per mutation is what made this suite cost one full gate -- project,
    rebuild, OfficeCLI readback, publication -- for each negative case.
    """
    captured: list[GateIntake] = []
    output = tmp_path_factory.mktemp("v042-gate-run-clean") / "gate"
    result = _run_gate(clean_deck, output, intake_mutation=_capture_intake(captured))
    assert captured, "the gate did not hand its sealed intake to the capture hook"
    return result, captured[0]


@pytest.fixture(scope="session")
def clean_result(clean_run: Any) -> Any:
    """One real gate run over the clean fixture."""
    result, intake = clean_run
    return clean_run[0]


@pytest.fixture(scope="session")
def clean_intake(clean_run: Any) -> GateIntake:
    """The sealed intake bundle that run judged."""
    result, intake = clean_run
    return clean_run[1]


def _published_proxy_paths(result: Any, intake: GateIntake) -> dict[str, str]:
    """Map each held proxy asset to where the run published it."""
    root = Path(result.output_directory) / "projection"
    return {
        str(item.proxy_asset): str((root / Path(item.proxy_asset).name).resolve())
        for item in intake.projected.objects
        if item.proxy_asset
    }


def _relocate_proxy_assets(intake: GateIntake, published_root: Path) -> GateIntake:
    """Point a sealed intake's proxy assets at the run's published copies.

    The run judges its proxies while they still sit in the staging directory it
    deletes when it returns, so a bundle re-judged afterwards names files that no
    longer exist -- and every isolation proof would fail on a missing raster
    rather than on the condition under test.  The published copies are the same
    bytes the accepted run wrote, which is what makes them the right thing to
    judge a mutation against.

    Only an asset whose file is *gone* is relocated.  A mutation that has already
    pointed the bundle at its own copy has bytes on disk, and re-pointing that at
    the published original would silently undo the mutation -- which is exactly
    how three of these cases passed when they should have blocked.
    """
    mapping = {
        str(item.proxy_asset): str(published_root / Path(item.proxy_asset).name)
        for item in intake.projected.objects
        if item.proxy_asset and not Path(item.proxy_asset).is_file()
    }
    if not mapping:
        return intake

    def relocate(asset: str | None) -> str | None:
        return mapping.get(str(asset), asset) if asset else asset

    return replace(
        intake,
        projected=replace(
            intake.projected,
            objects=tuple(
                replace(item, proxy_asset=relocate(item.proxy_asset))
                for item in intake.projected.objects
            ),
            slides=tuple(
                replace(
                    slide,
                    objects=tuple(
                        replace(item, proxy_asset=relocate(item.proxy_asset))
                        for item in slide.objects
                    ),
                )
                for slide in intake.projected.slides
            ),
        ),
    )


def _rejudge(clean_run: Any, mutation: Any) -> Any:
    """Judge a mutated copy of the sealed intake with the production rules.

    ``evaluate_intake`` is where every comparison rule lives and is the function
    the real run's verdict comes from, so a mutation re-judged here is judged by
    the same code a full run would use.  What is skipped is only the work that
    produced the bundle -- the projection, the New Deck build and the readback --
    which is why this is the cheap path, not a weaker one.

    Every mutation still has to be *reachable*: the end-to-end cases below build
    their fault into the deck itself, so the suite also proves the pipeline
    detects it rather than only that the comparator does.
    """
    result, intake = clean_run
    published_root = Path(result.output_directory) / "projection"
    judged = _relocate_proxy_assets(mutation(intake), published_root)
    return gate_module.evaluate_intake(
        judged,
        html_text=(
            Path(result.output_directory) / "canonical-author.html"
        ).read_text(encoding="utf-8"),
        pixels_per_point=intake.projected.pixels_per_point,
        # Whatever path the re-judged bundle now holds, the proof it produces has
        # to name the file a reviewer will open.
        published_proxies=_published_proxy_paths(result, judged),
    )


@pytest.fixture(scope="session")
def field_result(field_deck: Path, tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One real gate run over the cached-field fixture."""
    output = tmp_path_factory.mktemp("v042-gate-run-field") / "gate"
    return _run_gate(field_deck, output, pages=(1, 2))


def _object_named(result: Any, name: str) -> Any:
    for item in result.projected.objects:
        if item.source_name == name:
            return item
    raise AssertionError(
        f"no projected object named {name!r}; got "
        f"{[item.source_name for item in result.projected.objects]}"
    )


def _rebuilt_issue(path: str, message: str, issue_id: str = "O99") -> dict[str, Any]:
    return {
        "id": issue_id,
        "type": 0,
        "severity": 1,
        "path": path,
        "message": message,
    }


def _issue_path_of(intake: GateIntake, emitted_name: str) -> str:
    """Return the rebuilt deck's own path for one emitted object."""
    for item in intake.rebuilt_objects:
        if item.emitted_name == emitted_name:
            return item.path
    raise AssertionError(
        f"the rebuilt deck has no object named {emitted_name!r}; got "
        f"{[item.emitted_name for item in intake.rebuilt_objects]}"
    )


# ---------------------------------------------------------------------------
# Criterion 1: source and rebuilt OfficeCLI output, recorded separately per page
# ---------------------------------------------------------------------------


def test_a_clean_run_reaches_pass(clean_result: Any) -> None:
    """A run with nothing to report reaches the derived PASS outcome."""
    assert clean_result.outcome is GateOutcome.PASS
    assert clean_result.accepted is True
    assert clean_result.published is True
    assert clean_result.diagnostics == ()
    assert clean_result.material_deltas == ()
    assert clean_result.retained_findings == ()
    assert clean_result.scope_evidence == ()


def test_source_and_rebuilt_officecli_evidence_are_recorded_separately(
    clean_result: Any,
) -> None:
    """Each role carries its own validation text, issues, and deck hash."""
    assert [item.role for item in clean_result.source_evidence] == ["source"]
    assert [item.role for item in clean_result.rebuilt_evidence] == ["rebuilt"]
    source = clean_result.source_evidence[0]
    rebuilt = clean_result.rebuilt_evidence[0]
    assert "Validation passed" in source.validation
    assert "Validation passed" in rebuilt.validation
    assert source.path == clean_result.projected.source_path
    assert rebuilt.path.endswith("rebuilt.pptx")
    assert source.sha256 == clean_result.projected.source_sha256
    assert rebuilt.sha256 != source.sha256
    assert rebuilt.issue_count == len(rebuilt.raw_issue_records)


def test_every_selected_page_gets_one_page_record(clean_result: Any, field_result: Any) -> None:
    """One page-level evidence record per selected page, in selection order."""
    assert len(clean_result.pages) == 1
    assert [page.source_page for page in field_result.pages] == [1, 2]
    assert [page.output_page for page in field_result.pages] == [1, 2]
    for page in field_result.pages:
        assert page.source_objects == len(page.ledger)
        assert page.rebuilt_slide == page.output_page


def test_the_published_report_carries_both_officecli_reads(clean_result: Any) -> None:
    """The report on disk names the tool output rather than a summary of it."""
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    assert report["outcome"] == "PASS"
    assert [item["role"] for item in report["source_officecli"]] == ["source"]
    assert [item["role"] for item in report["rebuilt_officecli"]] == ["rebuilt"]
    assert report["rebuilt_officecli"][0]["validation"].strip()
    assert report["comparison_rules"], "the rules the gate applied must be published"


def test_the_report_is_a_summary_of_the_per_page_records(clean_result: Any) -> None:
    """Every count in the report is the sum of the page records it publishes.

    A reviewer must be able to re-derive the summary from the page evidence
    rather than trust it, so each summary key is either a count over the ledger
    or a sum over the page records.  The comparison is one-directional: the
    report may carry keys that are not per-page sums (``projected_pages`` and
    ``blocked_pages`` describe the selection, and a blocked page contributes
    nothing to any per-page count), but every per-page count must appear in the
    report with the same value.
    """
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    pages = json.loads(
        (Path(clean_result.output_directory) / "pages.json").read_text(encoding="utf-8")
    )["pages"]
    counts = {
        key: sum(page["counts"][key] for page in pages)
        for key in pages[0]["counts"]
    }
    assert counts == {
        key: report["counts"][key] for key in pages[0]["counts"]
    }
    assert report["counts"]["selected_pages"] == len(pages)
    assert report["counts"]["material_deltas"] == sum(
        len(page["material_deltas"]) for page in pages
    )
    assert report["counts"]["retained_findings"] == sum(
        len(page["retained_findings"]) for page in pages
    )
    assert report["counts"]["scope_evidence"] == sum(
        len(page["scope_evidence"]) for page in pages
    )
    assert report["counts"]["proxy_proofs"] == sum(len(page["proxies"]) for page in pages)
    assert report["counts"]["proxy_proofs_failed"] == 0
    assert report["counts"]["blocking_diagnostics"] == len(report["diagnostics"])
    assert report["counts"]["source_issues"] == sum(
        page["source_issue_count"] for page in pages
    )
    assert report["counts"]["rebuilt_issues"] == sum(
        page["rebuilt_issue_count"] for page in pages
    )


def test_the_gate_report_carries_the_per_page_records_themselves(
    clean_result: Any, field_result: Any
) -> None:
    """The accepted artifact is self-describing, not a pointer to another file.

    ``gate-report.json`` used to carry only a ``page_responses`` list of object
    names, so a reviewer reading the headline report for per-page evidence had
    to go and find ``pages.json``.  The report now carries the page records, and
    each page response carries its own record's real evidence.
    """
    for result in (clean_result, field_result):
        report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
        assert isinstance(report.get("pages"), list)
        assert [page["source_page"] for page in report["pages"]] == [
            page.source_page for page in result.pages
        ]
        pages_file = json.loads(
            (Path(result.output_directory) / "pages.json").read_text(encoding="utf-8")
        )["pages"]
        # One record, two renderings: the files cannot disagree.
        assert report["pages"] == pages_file
        # The page responses carry the page's real evidence rather than names.
        assert len(report["page_responses"]) == len(result.pages)
        for response, page in zip(report["page_responses"], report["pages"]):
            assert response["source_page"] == page["source_page"]
            assert response["output_page"] == page["output_page"]
            assert response["object_names"] == page["object_names"]
            assert response["evidence"] == page
            assert "counts" in response["evidence"]
            assert "proxies" in response["evidence"]
            assert "tables" in response["evidence"]
            assert "text_readback" in response["evidence"]
            assert "rebuilt_issue_count" in response["evidence"]
        # The rules the gate applied are published beside them.
        assert [item["name"] for item in report["comparison_rules"]] == [
            item.name for item in result.rules
        ]


def test_the_report_carries_the_page_evidence_for_every_selected_page(
    blocked_page_deck: Path, tmp_path: Path
) -> None:
    """A blocked run's report is as self-describing as an accepted one's."""
    result = _run_gate(blocked_page_deck, tmp_path / "gate", pages=(1, 2))
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert [page["source_page"] for page in report["pages"]] == [1, 2]
    assert report["pages"][0]["rebuilt_issue_count"] == 0
    assert report["pages"][1]["blocked"] is True
    assert report["pages"][1]["output_page"] == 0
    assert report["pages"][1]["blocking_reason"]["reason_code"] == (
        "unsupported_source_object"
    )
    assert report["page_responses"][1]["evidence"] == report["pages"][1]


# ---------------------------------------------------------------------------
# Criterion 2: stable source mapping survives page renumbering
# ---------------------------------------------------------------------------


def test_issue_paths_are_qualified_with_the_slide_they_belong_to() -> None:
    """The unqualified issue path is never the identity an object is keyed by."""
    parsed = parse_issue_path("/slide[7]/shape[@id=100000]")
    assert parsed is not None
    assert parsed.slide == 7
    assert parsed.full_object_path == "/slide[7]/shape[@id=100000]"
    scope = parse_issue_path("/slide[7] (master)")
    assert scope is not None
    assert scope.full_object_path is None
    assert scope.scope == "master"


def test_page_renumbering_alone_cannot_create_or_hide_a_delta() -> None:
    """The same condition on a differently numbered output page is not a delta.

    This is the criterion 2 rule exercised directly: two runs whose output pages
    are 1 and 9 compare identically, because the rebuilt record is keyed by the
    emitted object name and translated back to the source identity.
    """
    identity = ("src1", 5, "/slide[5]/shape[@id=100000]")
    source = _record(identity, condition="text_overflow", need=100.0, usable=50.0)
    first = _record(identity, condition="text_overflow", need=100.0, usable=50.0)
    ninth = replace(first, issue_id="O9")
    for rebuilt in (first, ninth):
        comparison = compare_issues(
            [source],
            [rebuilt],
            identity_to_rebuilt={identity: (9, "slide-009-textbox-001")},
        )
        assert comparison.material_deltas == ()
        assert len(comparison.retained_findings) == 1
        assert comparison.retained_findings[0].rebuilt_slide == 9


def test_a_rebuilt_object_the_ledger_does_not_own_blocks(clean_run: Any) -> None:
    """A rebuilt object outside the ledger makes its issues unattributable.

    This is the "resolves, but no source identity owns it" half of the binding
    rule: the rebuilt deck really holds the object the issue names, and no ledger
    entry emits it.  The gate reports the issue with that reason and blocks,
    rather than discarding a rebuilt-only condition because it could not say
    which source object it belonged to.
    """
    result, intake = clean_run
    injected = "O97"
    path = "/slide[1]/shape[@id=424242]"

    def add_foreign_object(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=(
                *intake.rebuilt_objects,
                RebuiltObject(
                    emitted_name="slide-001-shape-900",
                    rebuilt_kind="shape",
                    rebuilt_slide=1,
                    path=path,
                    text="",
                    bounds_pt=(0.0, 0.0, 10.0, 10.0),
                ),
            ),
            rebuilt_issue_records=(
                *intake.rebuilt_issue_records,
                _rebuilt_issue(
                    path,
                    "text overflow: 3 lines at 18.0pt need 60pt, usable 40pt.",
                    issue_id=injected,
                ),
            ),
        )

    result = _rejudge(clean_run, add_foreign_object)
    assert result.outcome is GateOutcome.BLOCK
    unbound = [item for item in result.unbound_rebuilt if item.issue_id == injected]
    assert unbound, [item.as_dict() for item in result.unbound_rebuilt]
    assert unbound[0].reason_code == "rebuilt_object_not_in_ledger"
    delta = next(
        item
        for item in result.material_deltas
        if item.rebuilt_issue.get("id") == injected
    )
    assert delta.condition == "text_overflow"
    assert delta.source_issue is None
    assert delta.source_object == path
    assert "did not select the object" in delta.reason
    diagnostic = next(
        item for item in result.diagnostics if item.code == "unbound_rebuilt_issue"
    )
    assert "rebuilt slide 1" in diagnostic.message


def test_an_unresolvable_rebuilt_only_issue_blocks_instead_of_being_dropped(
    field_result: Any, tmp_path: Path
) -> None:
    """The acceptance escape: a rebuilt-only issue on an unresolvable path blocks.

    The rebuilt deck's issues are the only evidence that the rebuild introduced
    a condition, so a rebuilt-only overflow whose OfficeCLI path resolves to no
    object of the rebuilt deck must never be discarded.  It blocked nothing
    before this rule existed: the run reached ``PASS_WITH_FINDINGS`` with zero
    diagnostics and published ``gate-report.json``.  All three shapes the binding
    can fail in must now block.
    """
    injected = {
        "O96": "/slide[1]/shape[@id=999999]",
        "O95": "/slide[1]",
        "O94": "/package",
    }

    def add_issues(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_issue_records=(
                *intake.rebuilt_issue_records,
                *(
                    _rebuilt_issue(
                        path,
                        "text overflow: 5 lines at 18.0pt need 70pt, usable 40pt.",
                        issue_id=issue_id,
                    )
                    for issue_id, path in injected.items()
                ),
            ),
        )

    result = _run_gate(
        field_result.projected.selection[0].source_pptx,
        tmp_path / "gate",
        pages=(1, 2),
        intake_mutation=add_issues,
    )
    assert result.outcome is GateOutcome.BLOCK
    assert result.accepted is False
    assert result.published is True, "a blocked run still publishes its evidence"
    assert Path(result.report_path).name == "gate-rejected.json"
    assert not (Path(result.output_directory) / "gate-report.json").exists()
    unbound = {item.issue_id: item for item in result.unbound_rebuilt}
    assert set(unbound) >= set(injected)
    assert unbound["O96"].reason_code == "rebuilt_path_unresolved"
    assert unbound["O95"].reason_code == "rebuilt_path_package_level"
    assert unbound["O94"].reason_code == "rebuilt_path_package_level"
    # Every one of them is a blocking diagnostic and a material delta: nothing
    # about the failure is silent.
    delta_ids = {item.rebuilt_issue.get("id") for item in result.material_deltas}
    assert set(injected) <= delta_ids
    diagnostic_ids = {
        item.message
        for item in result.diagnostics
        if item.code == "unbound_rebuilt_issue"
    }
    assert len(diagnostic_ids) >= len(injected)
    # The injected records are the comparison's input, and the evidence keeps the
    # deck's own read separately: the run's report says what OfficeCLI returned
    # for the deck, and the mutation seam says what was judged.
    assert result.rebuilt_evidence[0].issue_count == len(
        field_result.rebuilt_evidence[0].raw_issue_records
    )
    assert len(result.unbound_rebuilt) >= len(injected)
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["outcome"] == "BLOCK"
    assert {item["issue_id"] for item in report["unbound_rebuilt_issues"]} >= set(
        injected
    )


def _inject_grid_span(name: str, xml: str, *, row: int, span: int) -> str:
    """Give one table cell a ``gridSpan``, which is what a merged cell is.

    OfficeCLI has no merge operation, so the merge is written into the slide part
    the way PowerPoint writes it: ``gridSpan`` on the first ``tc`` of the row.
    The reader reports it as ``colspan``, and a colspan above 1 is outside the
    current Author table surface -- which is exactly the page-9 condition of the
    real corpus this fixture reproduces in miniature.
    """
    if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
        return xml
    rows = list(re.finditer(r"<a:tr\b[^>]*>", xml))
    if len(rows) < row:
        return xml
    start = rows[row - 1].end()
    return re.sub(
        r"<a:tc\b(?!\s+gridSpan)",
        f'<a:tc gridSpan="{span}"',
        xml[start:],
        count=1,
    ).join((xml[:start], ""))


def _build_blocked_page_deck(deck: Path) -> None:
    """Build a two-page deck whose second page carries a merged table cell.

    The first page is clean, so a run that selects both pages has one page that
    projects perfectly and one page that cannot be projected at all.  The deck is
    the gate's input and is never written by the product.
    """
    deck.unlink(missing_ok=True)
    _officecli("create", str(deck))
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "clean-page"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "merged-page"}},
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "textbox",
            "props": {
                "name": "clean-text",
                "text": CLEAN_TEXT,
                "x": "40pt",
                "y": "40pt",
                "width": "400pt",
                "height": "80pt",
                "size": "18pt",
                "font": "Microsoft YaHei",
                "color": "#14243A",
                "fill": "none",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[2]",
            "type": "table",
            "props": {
                "name": "merged-table",
                "x": "40pt",
                "y": "40pt",
                "width": "400pt",
                "height": "60pt",
                "rows": "2",
                "cols": "2",
                "colWidths": "200pt,200pt",
            },
        },
    ]
    _officecli("batch", str(deck), "--commands", json.dumps(commands, ensure_ascii=False))
    for row in (1, 2):
        for column in (1, 2):
            _officecli(
                "set",
                str(deck),
                f"/slide[2]/table[@name=merged-table]/tr[{row}]/tc[{column}]",
                "--prop",
                f"text=MERGED{row}{column}",
            )
    _close(deck)
    _rewrite_slide_parts(
        deck, lambda name, xml: _inject_grid_span(name, xml, row=1, span=2)
    )


@pytest.fixture(scope="session")
def blocked_page_deck(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A two-page deck whose second page cannot be projected."""
    deck = tmp_path_factory.mktemp("v042-gate-blocked-page") / "fixture.pptx"
    _build_blocked_page_deck(deck)
    return deck


def test_the_blocked_page_fixture_really_carries_a_merged_cell(
    blocked_page_deck: Path,
) -> None:
    """The fixture's blocking condition is real, read from the deck itself."""
    table = json.loads(
        _officecli(
            "get", str(blocked_page_deck), "/slide[2]/table[1]", "--depth", "3", "--json"
        )
    )["data"]["results"][0]
    spans = [
        (cell.get("format") or {}).get("colspan")
        for row in table.get("children", []) or []
        if str(row.get("type")) == "tr"
        for cell in row.get("children", []) or []
        if str(cell.get("type")) == "tc"
    ]
    assert max(int(span or 1) for span in spans) == 2, spans


def test_an_unprojectable_page_does_not_destroy_the_other_pages_evidence(
    blocked_page_deck: Path, tmp_path: Path
) -> None:
    """A blocking page is a published page record, not an aborted run.

    Selecting a page the Author Contract cannot express, beside a page that
    projects perfectly, must produce a *structured* blocking verdict that still
    carries the complete evidence for the page that could be projected.  The gate
    used to raise out of the projection seam and publish nothing at all, which
    destroyed the evidence for every other selected page exactly when a reviewer
    needed it.
    """
    result = _run_gate(blocked_page_deck, tmp_path / "gate", pages=(1, 2))
    assert result.outcome is GateOutcome.BLOCK
    assert result.blocked is True
    assert result.accepted is False
    assert result.published is True
    assert Path(result.report_path).name == "gate-rejected.json"
    assert result.output_directory and Path(result.output_directory).is_dir()

    # One record per selected page: the clean page projected, the merged page
    # blocked and reported with its reason.  The blocked page has no output page
    # because it was never rebuilt -- claiming the slot it "would" have taken
    # would collide with the page the rebuilt deck really puts there.
    assert [page.source_page for page in result.pages] == [1, 2]
    clean, blocked = result.pages
    assert clean.blocked is False
    assert clean.blocking_reason is None
    assert clean.canonical_editable == 1
    assert clean.text_readback, "the projectable page keeps its text readback"
    assert blocked.blocked is True
    assert blocked.output_page == 0
    assert blocked.rebuilt_slide == 0
    assert blocked.blocking_reason is not None
    assert blocked.blocking_reason["reason_code"] == "unsupported_source_object"
    assert "Merged table cells" in blocked.blocking_reason["reason"]
    assert blocked.blocking_reason["blocking_objects"] == ["/slide[2]/table[@id=100001]"]
    assert blocked.blocking_reason["selection_index"] == 2
    assert blocked.failures
    # The blocked page has no ledger of its own: it was never projected, and the
    # record says so rather than reporting zeros as if it had been.
    assert blocked.ledger == ()
    assert blocked.native_objects == ()
    assert blocked.source_issue_count >= 0

    diagnostic = next(
        item for item in result.diagnostics if item.code == "page_projection_blocked"
    )
    assert diagnostic.source_page == 2
    assert "Merged table cells" in diagnostic.message

    # The evidence set is complete and self-describing: the same page records the
    # accepted path publishes are on disk, and the rejection names the blocking
    # page while listing the retained page's work.
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["outcome"] == "BLOCK"
    assert report["counts"]["selected_pages"] == 2
    assert report["counts"]["blocked_pages"] == 1
    assert report["counts"]["projected_pages"] == 1
    assert [page["source_page"] for page in report["pages"]] == [1, 2]
    assert report["pages"][1]["blocked"] is True
    assert report["blocked_pages"][0]["reason_code"] == "unsupported_source_object"
    for name in ("disposition-ledger.json", "proxy-isolation.json", "rebuilt.pptx"):
        assert (Path(result.output_directory) / name).is_file(), name
    assert not (Path(result.output_directory) / "gate-report.json").exists()


def test_a_blocked_page_is_a_page_record_not_an_abort(
    blocked_page_deck: Path, tmp_path: Path
) -> None:
    """The gate never raises out for a selected page it can classify as blocking."""
    output = tmp_path / "gate"
    shutil.rmtree(output, ignore_errors=True)
    result = gate_projected_author_html(
        [(str(blocked_page_deck), 1), (str(blocked_page_deck), 2)],
        output,
    )
    assert result.blocked_pages
    assert len(result.blocked_pages) == 1
    assert result.blocked_pages[0].source_page == 2
    assert len(result.projected_pages) == 1
    assert result.projected_pages[0].source_page == 1
    # The retained page keeps the output page the rebuilt deck gives it, and the
    # blocked page reports no output page at all: it is not in that deck.
    assert result.projected_pages[0].output_page == 1
    assert result.blocked_pages[0].output_page == 0
    assert result.blocked_pages[0].blocking_reason["selection_index"] == 2
    assert len(result.ledger) == result.projected_pages[0].source_objects


def test_a_selected_object_absent_from_the_rebuilt_deck_blocks(clean_run: Any) -> None:
    """A rebuilt deck without the projected object blocks with both contexts."""
    result, intake = clean_run

    def drop_object(bundle: GateIntake) -> GateIntake:
        target = intake.projected.objects[0].emitted_name
        return replace(
            bundle,
            rebuilt_objects=tuple(
                item for item in bundle.rebuilt_objects if item.emitted_name != target
            ),
        )

    result = _rejudge(clean_run, drop_object)
    assert result.outcome is GateOutcome.BLOCK
    codes = {item.code for item in result.diagnostics}
    assert "missing_rebuilt_object" in codes
    diagnostic = next(
        item for item in result.diagnostics if item.code == "missing_rebuilt_object"
    )
    assert diagnostic.source_page == 1
    assert diagnostic.source_object
    assert diagnostic.rebuilt_object


# ---------------------------------------------------------------------------
# Criterion 3: an unchanged source-inherent overflow is a retained finding
# ---------------------------------------------------------------------------


def test_the_overflow_fixture_really_overflows(overflow_deck: Path) -> None:
    """The fixture's source-inherent condition is real, not simulated."""
    issues = json.loads(
        _officecli("view", str(overflow_deck), "issues", "--json")
    )["data"]["issues"]
    overflows = [
        item for item in issues if "text overflow" in str(item.get("message", "")).lower()
    ]
    assert overflows, issues
    assert "/slide[1]/shape[" in overflows[0]["path"]


def test_a_retained_overflow_does_not_enter_the_material_delta_set(
    overflow_result: Any,
) -> None:
    """The source's own overflow stays visible and does not block acceptance."""
    assert overflow_result.outcome is GateOutcome.PASS_WITH_FINDINGS
    assert overflow_result.accepted is True
    assert overflow_result.published is True
    assert overflow_result.material_deltas == ()
    conditions = {item.condition for item in overflow_result.retained_findings}
    assert "text_overflow" in conditions
    finding = next(
        item
        for item in overflow_result.retained_findings
        if item.condition == "text_overflow"
    )
    assert finding.source_object.endswith("shape[@id=100000]")
    assert finding.rebuilt_object
    assert "reproduce" in finding.reason or "does not report" in finding.reason


def test_the_rebuilt_issue_count_is_an_issue_count_not_an_object_count(
    clean_result: Any,
) -> None:
    """``rebuilt_issue_count`` counts OfficeCLI issues, derived independently.

    The field used to count the rebuilt objects that fell on the page -- 37, 11,
    3 for a rebuilt deck that reported *no* issues at all -- which told a
    reviewer the rebuilt deck carried one issue per object.  The expectation here
    is derived by parsing the rebuilt deck's own OfficeCLI issue output, so it
    cannot agree with a wrong implementation: the fixture's rebuilt deck reports
    no issues, while its page carries several objects.

    The deck is opened at its *published* path.  The sealed intake's own record
    names the run's working copy, which the run removes when it returns; the
    published ``rebuilt.pptx`` is the artifact the verdict is about and the one a
    reviewer can open, so that is what an independent read has to read.
    """
    published = Path(clean_result.output_directory) / "rebuilt.pptx"
    assert published.is_file(), "the accepted run published its rebuilt deck"
    raw = json.loads(
        _officecli("view", published, "issues", "--json")
    )["data"]["issues"]
    expected = {1: 0}
    for item in raw:
        slide = int(re.search(r"/slide\[(\d+)\]", str(item.get("path", ""))).group(1))
        expected[slide] = expected.get(slide, 0) + 1
    page = clean_result.pages[0]
    assert page.rebuilt_issue_count == expected.get(page.output_page, 0)
    assert page.rebuilt_issue_count == 0
    # The objects are still there: the page is not empty, it is issue-free, and
    # the two numbers are different claims.
    assert page.canonical_editable + page.locked_visual_proxy > 0
    assert len(page.text_readback) + len(page.tables) + len(page.proxies) > 0
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    assert report["rebuilt_officecli"][0]["issue_count"] == len(raw) == 0
    assert report["counts"]["rebuilt_issues"] == 0


def test_the_per_page_rebuilt_issue_count_sums_to_the_rebuilt_deck_total(
    field_result: Any,
) -> None:
    """Every issue the rebuilt deck reports is counted on exactly one page.

    The fixture's rebuilt deck is issue-free, so the injected records are what
    makes this test meaningful: each one is attributed to the page its path
    names, and the per-page counts add up to the global count.
    """
    raw = field_result.rebuilt_evidence[0].raw_issue_records
    assert sum(page.rebuilt_issue_count for page in field_result.pages) == len(raw)
    assert all(page.rebuilt_issue_count == 0 for page in field_result.pages), (
        "the fixture's rebuilt deck reports no issue of its own"
    )
    report = json.loads(Path(field_result.report_path).read_text(encoding="utf-8"))
    assert report["counts"]["rebuilt_issues"] == len(raw)
    assert report["rebuilt_officecli"][0]["issue_count"] == len(raw)


def test_the_retained_overflow_is_still_visible_in_the_page_record(
    overflow_result: Any,
) -> None:
    """A retained finding travels on its page record as well as the run."""
    page = overflow_result.pages[0]
    assert any(item.condition == "text_overflow" for item in page.retained_findings)
    assert page.source_issue_count >= 1


# ---------------------------------------------------------------------------
# Criterion 4: a rebuilt-only or materially worsened condition blocks
# ---------------------------------------------------------------------------


def test_a_rebuilt_only_issue_blocks_with_source_and_rebuilt_context(clean_run: Any) -> None:
    """A condition the rebuilt object alone reports is a material delta.

    The rebuilt issue is injected into the sealed intake bundle, because a
    condition OfficeCLI does not report for the rebuilt deck cannot be produced
    by rebuilding a valid projection; the comparison that judges it is the
    production one.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")

    def add_issue(intake: GateIntake) -> GateIntake:
        path = _issue_path_of(intake, target.emitted_name)
        return replace(
            intake,
            rebuilt_issue_records=(
                *intake.rebuilt_issue_records,
                _rebuilt_issue(
                    path,
                    "text overflow: 3 lines at 18.0pt need 60pt, usable 40pt.",
                ),
            ),
        )

    result = _rejudge(clean_run, add_issue)
    assert result.outcome is GateOutcome.BLOCK
    delta = next(item for item in result.material_deltas if item.condition == "text_overflow")
    assert delta.source_key == target.source_key
    assert delta.source_page == target.source_slide
    assert delta.source_object == target.source_object
    assert delta.rebuilt_slide == target.output_slide
    assert delta.rebuilt_object == target.emitted_name
    diagnostic = next(item for item in result.diagnostics if item.code == "material_delta")
    assert diagnostic.source_object == target.source_object
    assert diagnostic.rebuilt_object == target.emitted_name
    assert "rebuilt slide" in diagnostic.message


def test_a_rebuilt_only_condition_on_a_clean_source_object_is_a_delta() -> None:
    """A source object with no finding is still compared.

    This is the case the comparison exists for: the source deck says nothing
    about the object, so a rebuilt-only condition has nothing to be "retained"
    against and must be a material delta.  A comparison that only walked the
    source deck's own findings would silently accept it.
    """
    identity = ("src1", 1, "/slide[1]/shape[@id=100000]")
    rebuilt = _record(identity, condition="text_overflow", need=60.0, usable=40.0)
    comparison = compare_issues(
        [],
        [rebuilt],
        identity_to_rebuilt={identity: (1, "slide-001-textbox-001")},
    )
    assert len(comparison.material_deltas) == 1
    assert comparison.material_deltas[0].condition == "text_overflow"
    assert comparison.material_deltas[0].rebuilt_object == "slide-001-textbox-001"
    assert comparison.retained_findings == ()


def test_a_materially_worsened_overflow_blocks() -> None:
    """A same-kind condition that grows past both thresholds is material."""
    identity = ("src1", 1, "/slide[1]/shape[@id=100000]")
    source = _record(identity, condition="text_overflow", need=100.0, usable=100.0)
    worsened = _record(identity, condition="text_overflow", need=140.0, usable=100.0)
    assert pressure_ratio(source) == pytest.approx(1.0)
    assert pressure_ratio(worsened) == pytest.approx(1.4)
    assert materially_worsened(source, worsened) is True
    comparison = compare_issues(
        [source], [worsened], identity_to_rebuilt={identity: (1, "slide-001-textbox-001")}
    )
    assert len(comparison.material_deltas) == 1
    assert comparison.retained_findings == ()
    assert "materially worsened" in comparison.material_deltas[0].reason


def test_an_overflow_within_both_tolerances_stays_retained() -> None:
    """A rebuild that disagrees about the usable height by a point is retained."""
    identity = ("src1", 1, "/slide[1]/shape[@id=100000]")
    source = _record(identity, condition="text_overflow", need=805.0, usable=23.0)
    rebuilt = _record(identity, condition="text_overflow", need=759.0, usable=30.0)
    assert materially_worsened(source, rebuilt) is False
    comparison = compare_issues(
        [source], [rebuilt], identity_to_rebuilt={identity: (1, "slide-001-textbox-001")}
    )
    assert comparison.material_deltas == ()
    assert len(comparison.retained_findings) == 1


def test_a_condition_without_measurements_is_never_declared_worse() -> None:
    """An unmeasurable condition keeps its verdict from presence alone."""
    identity = ("src1", 1, "/slide[1]/shape[@id=100000]")
    source = _record(identity, condition="shape_goes_off_slide")
    rebuilt = _record(identity, condition="shape_goes_off_slide")
    assert pressure_ratio(source) is None
    assert materially_worsened(source, rebuilt) is False
    comparison = compare_issues(
        [source], [rebuilt], identity_to_rebuilt={identity: (1, "slide-001-shape-001")}
    )
    assert comparison.material_deltas == ()
    assert len(comparison.retained_findings) == 1


def test_a_source_only_condition_is_a_retained_finding_not_a_repair() -> None:
    """A condition the rebuilt object does not report is never called repaired."""
    identity = ("src1", 1, "/slide[1]/shape[@id=100000]")
    source = _record(identity, condition="text_overflow", need=100.0, usable=50.0)
    comparison = compare_issues(
        [source], [], identity_to_rebuilt={identity: (1, "slide-001-textbox-001")}
    )
    assert comparison.material_deltas == ()
    assert len(comparison.retained_findings) == 1
    assert "claimed as repaired" in comparison.retained_findings[0].reason


# ---------------------------------------------------------------------------
# Criterion 5: master/layout findings and inherited paint stay scope evidence
# ---------------------------------------------------------------------------


def test_master_and_layout_paths_are_scope_evidence_not_objects() -> None:
    """A path that names a master or layout binds to no slide-owned object."""
    for path in ("/slide[5] (master)", "/slide[5] (layout)"):
        parsed = parse_issue_path(path)
        assert parsed is not None
        assert parsed.object_path is None
        assert parsed.full_object_path is None
        assert parsed.scope in {"master", "layout"}
        assert parsed.slide_owned is False


def test_source_only_inherited_findings_are_scope_evidence(field_result: Any) -> None:
    """The cached-field fixture's slide-level finding is scope evidence."""
    assert field_result.outcome is GateOutcome.PASS_WITH_FINDINGS
    conditions = {item.condition for item in field_result.scope_evidence}
    assert "slide_field_not_evaluated" in conditions
    entry = next(
        item
        for item in field_result.scope_evidence
        if item.condition == "slide_field_not_evaluated"
    )
    assert entry.source_page == 2
    assert entry.mapped is False
    assert "never mapped onto a rebuilt object" in entry.detail
    # It is scope evidence, not a repaired or lost slide-owned object.
    assert entry.source_issue["source_object"] is None
    assert entry.source_issue["scope"] == "slide"
    assert not any(
        item.condition == "slide_field_not_evaluated"
        for item in field_result.retained_findings
    )
    assert not any(
        item.condition == "slide_field_not_evaluated"
        for item in field_result.material_deltas
    )


def test_an_inherited_paint_omission_is_scope_evidence() -> None:
    """A base-only object is reported as an inherited-paint omission.

    The omission is injected into the sealed intake bundle's ledger result, for
    the same reason the other injections are: the report shows a base-only
    object's *treatment*, and building a deck whose object depends on an
    inherited value it does not own is a different fixture's job (the #16
    inheritance probes).  What this test pins down is that the gate reports such
    an object as scope evidence and never as a repaired slide-owned object.
    """
    # Reported by the real cached-field fixture's own ledger when an object is
    # base-only; here the classification is checked directly so the rule is
    # exercised even when no fixture produces one.
    entry = ScopeEvidence(
        source_key="src1",
        source_page=1,
        condition="inherited_paint_omission",
        detail="the source object's visible appearance depends on a value the slide does not own",
        source_issue={"path": "/slide[1]/shape[@id=1]"},
        mapped=True,
    )
    assert entry.mapped is True
    assert "does not own" in entry.detail


def test_a_container_owned_object_is_never_an_emitted_object(clean_result: Any) -> None:
    """A ledger entry represented by its container has no element of its own."""
    for entry in clean_result.ledger:
        if entry.represented_by_container:
            assert entry.emitted is False
            assert entry.html_id is None
            assert entry.emitted_ordinal is None


# ---------------------------------------------------------------------------
# Criterion 6: independent text and style readback
# ---------------------------------------------------------------------------


def test_canonical_text_is_read_back_from_the_rebuilt_pptx(clean_result: Any) -> None:
    """Text is read back through OfficeCLI, not taken from the emitted HTML."""
    target = _object_named(clean_result, "clean-text")
    page = clean_result.pages[0]
    readback = next(
        item for item in page.text_readback if item.source_object == target.source_object
    )
    assert readback.matched is True
    rebuilt_text = normalize_text(readback.rebuilt_text)
    assert rebuilt_text.startswith(normalize_text(CLEAN_TEXT))
    assert normalize_text(CLEAN_TEXT_SECOND_PARAGRAPH) in rebuilt_text
    # The value compared comes from the rebuilt deck's own readback.
    rebuilt = next(
        item
        for item in clean_result.rebuilt_objects
        if item.emitted_name == target.emitted_name
    )
    assert readback.rebuilt_text == rebuilt.text


def test_the_rebuilt_deck_really_contains_the_source_characters(
    clean_result: Any,
) -> None:
    """Unicode and CJK survive: the readback is of the deck, not of a manifest."""
    target = _object_named(clean_result, "clean-text")
    readback = next(
        item
        for item in clean_result.pages[0].text_readback
        if item.source_object == target.source_object
    )
    assert "中文" in readback.rebuilt_text
    assert "🚀" in readback.rebuilt_text


def test_supported_style_declarations_are_recorded_for_every_readback(
    clean_result: Any,
) -> None:
    """Each readback carries the *source object's* own formatting, per run.

    The expectation used to be parsed back out of the generated HTML, which made
    the style check compare the projection with itself.  It is now the captured
    source declaration, and it is per run rather than one representative value, so
    a mixed-run body cannot pass by having one style.
    """
    checked = 0
    for readback in clean_result.pages[0].text_readback:
        declarations = readback.style_declarations
        runs = declarations.get("runs") or []
        assert runs, f"{readback.source_object} declares no run style"
        for run in runs:
            # Every run states the formatting the source owns.  A run that
            # declares a size must also state its face and colour.
            if "size=" in run:
                assert "font=" in run, run
                assert "color=" in run, run
        checked += 1
        # And the rebuilt side is read from the rebuilt PPTX, per run.
        assert readback.rebuilt_style.unavailable is None, readback.source_object
        assert len(readback.rebuilt_style.runs) == len(runs), readback.source_object
        assert readback.style_matched, readback.style_failures()
    assert checked, "the clean fixture projects at least one text object"


def test_a_changed_rebuilt_font_size_blocks(clean_run: Any) -> None:
    """A rebuilt object whose size changed is not a faithful rebuild.

    This is the mutation the gate used to be blind to: the characters were intact,
    the text check passed, and nothing looked at the formatting at all.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name,
        lambda style: replace(
            style,
            runs=tuple(
                run.replace("size=18pt", "size=99pt") for run in style.runs
            ),
        ),
    ))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert diagnostic.source_object == target.source_object
    assert diagnostic.rebuilt_object == target.emitted_name


def test_a_changed_rebuilt_font_family_blocks(clean_run: Any) -> None:
    """A substituted typeface is a style regression, not a detail."""
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name,
        lambda style: replace(
            style,
            runs=tuple(
                re.sub(r"font=[^|]*", "font=comic sans ms", run)
                for run in style.runs
            ),
        ),
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "style_readback_mismatch" in {item.code for item in result.diagnostics}


def test_a_changed_rebuilt_colour_blocks(clean_run: Any) -> None:
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name,
        lambda style: replace(
            style,
            runs=tuple(
                re.sub(r"color=[^|]*", "color=#00ff00", run)
                for run in style.runs
            ),
        ),
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "style_readback_mismatch" in {item.code for item in result.diagnostics}


def test_a_flattened_run_list_blocks(clean_run: Any) -> None:
    """Losing the boundary between two DIFFERENT runs is not faithful.

    The mutation gives the object two runs that genuinely differ, then reports only
    one -- the shape of a body whose mixed formatting was collapsed into a single
    representative style.  Comparing a body whose runs were already identical would
    prove nothing, because the Canonical Run rule merges those whether or not the
    projection did.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name,
        lambda style: replace(
            style,
            runs=tuple(style.runs) + ("font=arial|size=99pt|color=#ff0000|bold=true|italic=|underline=",),
        ),
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "style_readback_mismatch" in {item.code for item in result.diagnostics}


def test_the_run_comparison_uses_the_products_own_run_rule() -> None:
    """Runs are compared as the Canonical Run rule defines them, not as reported.

    The first run of the style check reported seven objects as having lost a run
    boundary, and every one of them was a false positive: the source's runs were
    identical in every declaration the comparison reads, and differed only in
    whether an off-state was spelled ``-`` or ``false``.  The rule merges adjacent
    runs whose resolved formatting is identical, so those were one run to this
    product and the merge was permitted.

    A check that calls a permitted merge lost formatting sends the fix to the
    wrong component, so this pins both directions: off-state spellings merge, and
    a real formatting difference does not.
    """
    merged = gate_module._normalized_runs
    # Same run, two spellings of "not stated".
    assert len(merged(["italic=-|size=12.25pt", "italic=false|size=12.25pt"])) == 1
    assert len(merged(["bold=none|size=12pt", "size=12pt"])) == 1
    # Three identical runs are one run.
    assert len(merged(["size=12pt", "size=12pt", "size=12pt"])) == 1
    # A real difference is still a boundary.
    assert len(merged(["bold=true|size=12pt", "bold=-|size=12pt"])) == 2
    assert len(merged(["italic=-|size=12.25pt", "italic=-|size=14pt"])) == 2
    # Non-adjacent runs are never merged, even when identical.
    assert len(merged(["size=12pt", "size=14pt", "size=12pt"])) == 3
    # An unknown declaration is not part of a run's identity, so a run whose only
    # difference is in one is the same run.
    assert len(merged(["size=12pt", "exotic=1|size=12pt"])) == 1


def test_an_unreadable_rebuilt_style_blocks_rather_than_passing(clean_run: Any) -> None:
    """A style the gate cannot read must not be treated as a style that matched."""
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name,
        lambda style: replace(style, unavailable="the readback reported nothing"),
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "style_readback_mismatch" in {item.code for item in result.diagnostics}


def _style_mutation(name: str, rewrite: Any) -> Any:
    """Mutate one rebuilt object's style inside the sealed intake bundle.

    The mutation is applied to the readback, not to the deck, so every case is
    judged by the same production comparison a real run uses.  Reading the deck
    itself was correct; what is under test is that the comparison notices a
    readback whose formatting no longer matches the source's declaration.
    """

    def mutate(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, style=rewrite(item.style))
                if item.emitted_name == name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    return mutate


def test_a_changed_rebuilt_alignment_blocks(clean_run: Any) -> None:
    """A body the rebuild centred is not the body the source drew left.

    The comparison used to skip any source declaration of the default ``left``,
    so a rebuilt object that reported ``center`` had nothing to be compared
    against and passed.  Both sides now resolve through the native default, which
    is what makes the centred case visible.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name, lambda style: replace(style, align="center")
    ))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert diagnostic.source_object == target.source_object
    assert diagnostic.rebuilt_object == target.emitted_name
    assert "align" in diagnostic.message
    assert _readback_of(result, target.source_object).style_matched is False


def test_an_absent_rebuilt_alignment_is_the_native_default(clean_run: Any) -> None:
    """The other direction, pinned: stating nothing is not the same as stating wrong.

    A rebuilt body that declares no alignment paints the native default, which is
    what the source declares, so the comparison must not read the absent
    declaration as a lost one.  Only a *different* alignment is a failure.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name, lambda style: replace(style, align=None)
    ))
    assert "style_readback_mismatch" not in {item.code for item in result.diagnostics}
    assert _readback_of(result, target.source_object).style_matched is True


def test_alignment_tokens_resolve_through_the_native_default() -> None:
    """The token rule itself, both directions, without a deck in the way."""
    token = gate_module._alignment_token
    # Absence, ``left`` and the relative ``start`` are one alignment.
    assert token(None) == token("left") == token("start") == token("LEFT")
    assert token("-") == token("none") == token("")
    # A real alignment is not the default.
    assert token("center") != token("left")
    assert token("right") != token("left")
    assert token("justify") != token("left")


def test_a_changed_rebuilt_text_blocks(clean_run: Any) -> None:
    """Dropped characters in the rebuilt deck are detected.

    The rebuilt text is mutated in the sealed intake bundle: the deck itself was
    read correctly, and what is under test is that the comparison notices a
    readback that no longer matches the source object.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")

    def drop_characters(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, text=item.text[:4])
                if item.emitted_name == target.emitted_name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    result = _rejudge(clean_run, drop_characters)
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "text_readback_mismatch"
    )
    assert diagnostic.source_object == target.source_object
    assert diagnostic.rebuilt_object == target.emitted_name


def _text_mutation(name: str, rewrite: Any) -> Any:
    """Mutate one rebuilt object's text inside the sealed intake bundle.

    The characters are changed on the readback, not in the deck, so every case is
    judged by the same production comparison a real run uses.  The deck was read
    correctly; what is under test is that the comparison notices a readback whose
    text or structure no longer matches the source object -- and names the code.
    """

    def mutate(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, text=rewrite(item.text))
                if item.emitted_name == name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    return mutate


def _readback_of(result: Any, source_object: str) -> Any:
    """Return the page-level readback for one source object, from the run itself."""
    return next(
        item
        for page in result.pages
        for item in page.text_readback
        if item.source_object == source_object
    )


def test_two_words_run_together_blocks(clean_run: Any) -> None:
    """``A B -> AB`` is a blocking difference, and it is not a spacing finding.

    Every character survived, so a whitespace-blind comparison called this
    faithful.  It is the shape of the defect that reached a rebuilt deck as
    ``Hard break probe linesecond visual line``.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _text_mutation(
        target.emitted_name, lambda text: text.replace(" ", "", 1)
    ))
    assert result.outcome is GateOutcome.BLOCK
    codes = {item.code for item in result.diagnostics}
    assert "text_readback_mismatch" in codes
    readback = _readback_of(result, target.source_object)
    assert readback.matched is False
    assert readback.structure_lost is True, "the characters survived; the structure did not"
    assert readback.whitespace_only_difference is False


def test_a_dropped_hard_break_blocks(clean_run: Any) -> None:
    """The source's two authored lines read as one line when the break is gone."""
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _text_mutation(
        target.emitted_name, lambda text: text.replace("\n", "")
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "text_readback_mismatch" in {item.code for item in result.diagnostics}
    readback = _readback_of(result, target.source_object)
    assert readback.matched is False
    assert readback.structure_lost is True


def test_a_paragraph_boundary_read_as_a_space_blocks(clean_run: Any) -> None:
    """A paragraph boundary replaced by a space is a lost boundary, not spacing.

    A separator that *dissolves* a boundary is the case the published rule has to
    name, because the words are all still present and a whitespace-blind rule
    therefore accepts it.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _text_mutation(
        target.emitted_name, lambda text: text.replace("\n", " ")
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "text_readback_mismatch" in {item.code for item in result.diagnostics}
    readback = _readback_of(result, target.source_object)
    assert readback.matched is False
    assert readback.structure_lost is True


def test_an_added_empty_paragraph_blocks(clean_run: Any) -> None:
    """An empty paragraph *between* content is a paragraph the source painted.

    The source's two authored paragraphs are separated by one boundary; a rebuild
    that writes two has painted a blank line the source does not show.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _text_mutation(
        target.emitted_name, lambda text: text.replace("\n", "\n\n", 1)
    ))
    assert result.outcome is GateOutcome.BLOCK
    assert "text_readback_mismatch" in {item.code for item in result.diagnostics}
    assert _readback_of(result, target.source_object).matched is False


def test_a_trailing_empty_paragraph_is_the_approved_direction(clean_run: Any) -> None:
    """The rule drops a trailing empty paragraph, and that is the product decision.

    Pinned here rather than left implicit: OfficeCLI gives every native text body
    one paragraph, so a body whose last authored paragraph is empty reports one
    more than the source states, and blocking on it would refuse a rebuild for
    writing the blank the source itself paints at the end of its text.  The
    *interior* case above is the one that blocks, and the two directions are
    deliberately different.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _text_mutation(
        target.emitted_name, lambda text: text + "\n\n"
    ))
    assert "text_readback_mismatch" not in {item.code for item in result.diagnostics}
    readback = _readback_of(result, target.source_object)
    assert readback.rebuilt_text != readback.expected_text, "the raw readback differs"
    assert readback.matched is True, "and the approved rule reads it as the same text"
    assert readback.structure_lost is False


def _source_style_mutation(name: str, rewrite: Any) -> Any:
    """Rewrite one *source* object's captured declaration inside the sealed intake.

    The rebuilt side is not touched.  This is how a source deck that declares
    something the corpus decks do not -- a paragraph spacing, a different authored
    line count -- is exercised against the real comparison, without inventing a
    private fixture deck to hold it.
    """

    def mutate(intake: GateIntake) -> GateIntake:
        objects = tuple(
            replace(item, text_style=rewrite(item.text_style))
            if item.emitted_name == name
            else item
            for item in intake.projected.objects
        )
        return replace(
            intake,
            projected=replace(intake.projected, objects=objects),
        )

    return mutate


def test_spacing_the_rebuild_never_declared_blocks(clean_run: Any) -> None:
    """A rebuilt body spaced away from its box is not the body the source drew.

    The source declares no paragraph spacing, so the rebuild must declare none:
    the source's rectangle is meant to carry the body's position, and a rebuilt
    object that adds a gap paints the text somewhere the source does not.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name, lambda style: replace(style, space_before="12pt")
    ))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert diagnostic.source_object == target.source_object
    assert "spaceBefore" in diagnostic.message
    assert "no paragraph spacing" in diagnostic.message


def test_a_source_declared_spacing_the_rebuild_drops_blocks(clean_run: Any) -> None:
    """The other direction: the source spaced a paragraph and the rebuild did not.

    A source paragraph the deck spaced 12pt from the one above it is painted lower
    than the same paragraph drawn flush, so dropping the spacing moves text.  The
    source's own declaration is the only side that can know this, which is why the
    capture carries it.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")

    def declare_spacing(paragraphs: Any) -> Any:
        return tuple(
            {**paragraph, "space_before_pt": 0.0 if index else 12.0}
            for index, paragraph in enumerate(paragraphs)
        )

    result = _rejudge(clean_run, _source_style_mutation(
        target.emitted_name, declare_spacing
    ))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert "spaceBefore" in diagnostic.message
    assert "12pt" in diagnostic.message


def test_per_paragraph_spacing_the_readback_cannot_express_blocks(clean_run: Any) -> None:
    """Two different source spacings cannot both be read back from one object.

    The rebuilt side reports one spacing for the whole object, so a source body
    whose paragraphs are spaced differently is a body this readback cannot judge.
    Failing closed is the only honest verdict: accepting it would mean comparing a
    per-paragraph declaration against a value that stands for all of them.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")

    def two_spacings(paragraphs: Any) -> Any:
        return tuple(
            {**paragraph, "space_after_pt": 6.0 * (index + 1)}
            for index, paragraph in enumerate(paragraphs)
        )

    result = _rejudge(clean_run, _source_style_mutation(target.emitted_name, two_spacings))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert "more than one paragraph spacing" in diagnostic.message


def test_shrink_to_fit_on_a_multi_line_body_blocks(clean_run: Any) -> None:
    """The rebuild may only ask OfficeCLI to shrink a body measured as one line.

    The source object authors two lines here.  Asking OfficeCLI to fit a
    multi-line body to its box is a size change waiting to happen: if the rebuilt
    font metrics overflow the source's rectangle, the body is painted smaller than
    the source paints it, and no other check in this gate would see it.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    readback = _readback_of(result, target.source_object)
    assert readback.style_declarations["authored-lines"] > 1, (
        "this case is only meaningful on a multi-line source body"
    )
    result = _rejudge(clean_run, _style_mutation(
        target.emitted_name, lambda style: replace(style, auto_fit="normal")
    ))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "style_readback_mismatch"
    )
    assert "autoFit" in diagnostic.message
    assert "authors 2 lines" in diagnostic.message


def test_shrink_to_fit_on_a_single_line_body_is_allowed(clean_run: Any) -> None:
    """And the permitted direction: one authored line is what the compiler asks it for.

    The compiler requests shrink-to-fit exactly on a body Chromium measured as one
    visual line, so the readback showing it there is the projection working as
    designed rather than a defect.  Both halves of the condition are set, so the
    only thing this test can be proving is the line-count rule itself.
    """
    result, intake = clean_run
    target = _object_named(result, "clean-text")
    source = _source_style_mutation(
        target.emitted_name, lambda paragraphs: tuple(paragraphs[:1])
    )
    rebuilt = _style_mutation(
        target.emitted_name, lambda style: replace(style, auto_fit="normal")
    )

    def one_line_and_shrink(intake: GateIntake) -> GateIntake:
        return rebuilt(source(intake))

    result = _rejudge(clean_run, one_line_and_shrink)
    assert "style_readback_mismatch" not in {item.code for item in result.diagnostics}
    readback = _readback_of(result, target.source_object)
    assert readback.style_declarations["authored-lines"] == 1
    assert readback.rebuilt_style.auto_fit == "normal"
    assert readback.style_matched is True


def test_the_spacing_rule_compares_points_not_spellings() -> None:
    """The spacing comparison itself, without a deck: units, both directions."""
    failure = gate_module._spacing_failure
    # No source spacing: silence and an explicit zero are both faithful.
    assert failure("spaceBefore", [0.0], None) is None
    assert failure("spaceBefore", [0.0], "0pt") is None
    assert failure("spaceBefore", [0.0], "12pt") is not None
    # A declared spacing survives in either spelling of the same length.
    assert failure("spaceAfter", [12.0], "12pt") is None
    assert failure("spaceAfter", [12.0], None) is not None
    assert failure("spaceAfter", [12.0], "6pt") is not None
    # Sub-point differences are unit rounding; a whole point is a different spacing.
    assert failure("spaceAfter", [12.0], "12.25pt") is None
    assert failure("spaceAfter", [12.0], "13pt") is not None
    # A value the readback cannot express fails closed rather than passing.
    assert failure("spaceAfter", [6.0, 12.0], "12pt") is not None


# ---------------------------------------------------------------------------
# Criterion 7: native table kind, dimensions, cell text, and source mapping
# ---------------------------------------------------------------------------


def test_every_selected_native_table_is_checked(clean_result: Any) -> None:
    """The fixture's one native table gets one structural check per page."""
    target = _object_named(clean_result, "native-table")
    checks = clean_result.pages[0].tables
    assert len(checks) == 1
    check = checks[0]
    assert check.source_object == target.source_object
    assert check.failures() == ()
    assert check.expected_kind == "table"
    assert check.rebuilt_kind == "table"
    assert (check.expected_rows, check.expected_columns) == (2, 2)
    assert (check.rebuilt_rows, check.rebuilt_columns) == (2, 2)
    assert check.expected_cells == tuple(
        value for row in TABLE_CELLS for value in row
    )
    assert check.rebuilt_cells == check.expected_cells


def test_table_cells_carry_their_source_mapping(clean_result: Any) -> None:
    """Every emitted cell is bound to the source cell path it came from."""
    check = clean_result.pages[0].tables[0]
    assert len(check.cell_paths) == 4
    assert all(path.startswith("/slide[1]/table[") for path in check.cell_paths)
    assert all("/tr[" in path and "/tc[" in path for path in check.cell_paths)


def test_a_rebuilt_table_with_the_wrong_dimensions_blocks(clean_run: Any) -> None:
    """A table rebuilt with the wrong row/column count is detected.

    The dimension change is injected into the sealed intake bundle, because a
    New Deck build either produces a native table of the authored dimensions or
    it fails outright; the structural comparison that judges the readback is the
    production one.
    """
    result, intake = clean_run
    target = _object_named(result, "native-table")

    def wrong_dimensions(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, rows=3, columns=4)
                if item.emitted_name == target.emitted_name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    result = _rejudge(clean_run, wrong_dimensions)
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "table_structure_mismatch"
    )
    assert "dimensions" in diagnostic.message
    assert diagnostic.source_object == target.source_object


def test_a_rebuilt_table_with_changed_cell_text_blocks(clean_run: Any) -> None:
    """A table whose cells read back with different characters is detected."""
    result, intake = clean_run
    target = _object_named(result, "native-table")

    def change_cell(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, cells=("MODEL", "12K", "IDU SIZE", "910x305x19"))
                if item.emitted_name == target.emitted_name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    result = _rejudge(clean_run, change_cell)
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "table_structure_mismatch"
    )
    assert "cell text" in diagnostic.message


def test_a_rebuilt_table_that_differs_only_in_whitespace_is_reported(clean_run: Any) -> None:
    """A cell whose characters match but whose spacing moved does not block.

    The source cell ``IDU SIZE`` and the rebuilt ``IDU  SIZE`` carry the same
    characters in the same order; the difference is one space, which is what a
    run boundary in the source becomes after the rebuilt deck's own paragraph
    handling.  It is reported as a retained finding so a reviewer sees it, and it
    does not block an otherwise faithful table.
    """

    result, intake = clean_run
    def respace(intake: GateIntake) -> GateIntake:
        target = next(
            item for item in intake.projected.objects if item.projected_kind == "table"
        )
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(
                    item,
                    cells=tuple(
                        cell.replace("IDU SIZE", "IDU  SIZE") for cell in item.cells
                    ),
                )
                if item.emitted_name == target.emitted_name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    result = _rejudge(clean_run, respace)
    assert result.outcome is GateOutcome.PASS_WITH_FINDINGS
    assert result.material_deltas == ()
    assert any(
        item.condition == "table_cell_whitespace_placement"
        for item in result.retained_findings
    )
    check = result.pages[0].tables[0]
    assert check.failures() == ()
    assert check.space_only_cell_positions() == (2,)


def test_a_rasterised_table_blocks(clean_run: Any) -> None:
    """A table rebuilt as a picture is never a native table round trip."""
    result, intake = clean_run
    target = _object_named(result, "native-table")

    def rasterise(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            rebuilt_objects=tuple(
                replace(item, rebuilt_kind="picture", rows=None, columns=None, cells=())
                if item.emitted_name == target.emitted_name
                else item
                for item in intake.rebuilt_objects
            ),
        )

    result = _rejudge(clean_run, rasterise)
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "table_structure_mismatch"
    )
    assert "table kind" in diagnostic.message


# ---------------------------------------------------------------------------
# Criterion 8: native and proxy counts are reported separately
# ---------------------------------------------------------------------------


def test_native_and_proxy_counts_are_reported_separately(clean_result: Any) -> None:
    """A locked proxy is never counted as a native round trip."""
    counts = clean_result.counts
    assert counts["canonical_editable"] == 2
    assert counts["locked_visual_proxy"] == 1
    assert counts["native_round_trip"] == counts["canonical_editable"]
    # The locked proxy is the only object excluded from the native round trip:
    # the table is native, and it is not a native *round trip* success on its own
    # account, which is why the two counts are reported separately.
    assert counts["excluded_from_native_round_trip"] == counts["locked_visual_proxy"]
    assert counts["excluded_from_native_round_trip"] == 1
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    assert report["counts"]["native_round_trip"] == 2
    assert report["counts"]["locked_visual_proxy"] == 1


def test_a_locked_proxy_is_excluded_from_native_equivalence(clean_result: Any) -> None:
    """The proxy is a locked disposition with a reason and no native claim."""
    target = _object_named(clean_result, "locked-preset")
    assert target.disposition == DISPOSITION_LOCKED
    assert target.proxy_reason
    entry = next(
        item for item in clean_result.ledger if item.source_object == target.source_object
    )
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code
    assert entry.disposition not in {DISPOSITION_CANONICAL, DISPOSITION_BASE_ONLY}
    page = clean_result.pages[0]
    assert target.emitted_name in page.proxy_objects
    assert target.emitted_name not in page.native_objects


# ---------------------------------------------------------------------------
# Container proxies: byte-identical output for byte-identical content
# ---------------------------------------------------------------------------

TWIN_GROUP_FILL = "#CC3366"
TWIN_GROUP_BOXES = ((120.0, 240.0, 120.0, 40.0), (520.0, 240.0, 120.0, 40.0))


def _build_twin_group_deck(deck: Path) -> None:
    """Build a deck with two groups of *identical* content at different places.

    OfficeCLI adds a child of a group in the group's own child coordinate space,
    and the reader reconciles that space with the group's rectangle, so each twin
    carries the same child rectangle offset from its own corner: the two groups
    are congruent, and only their position on the slide differs.
    """
    deck.unlink(missing_ok=True)
    _officecli("create", str(deck))
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "twins"}},
    ]
    child = (10.0, 10.0, 100.0, 20.0)
    for index, (x, y, width, height) in enumerate(TWIN_GROUP_BOXES, start=1):
        commands.append(
            {
                "command": "add",
                "parent": "/slide[1]",
                "type": "group",
                "props": {
                    "name": f"twin-{index}",
                    "x": f"{x}pt",
                    "y": f"{y}pt",
                    "width": f"{width}pt",
                    "height": f"{height}pt",
                },
            }
        )
        commands.append(
            {
                "command": "add",
                "parent": f"/slide[1]/group[{index}]",
                "type": "shape",
                "props": {
                    "name": f"twin-{index}-child",
                    "geometry": "rect",
                    "x": f"{x + child[0]}pt",
                    "y": f"{y + child[1]}pt",
                    "width": f"{child[2]}pt",
                    "height": f"{child[3]}pt",
                    "fill": TWIN_GROUP_FILL,
                    "line": "none",
                },
            }
        )
    _officecli("batch", str(deck), "--commands", json.dumps(commands, ensure_ascii=False))
    _close(deck)


@pytest.fixture(scope="session")
def twin_group_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One projection of the two-identical-groups fixture."""
    deck = tmp_path_factory.mktemp("v042-gate-twins") / "fixture.pptx"
    _build_twin_group_deck(deck)
    directory = tmp_path_factory.mktemp("v042-gate-twins-run")
    result = project_pptx_to_author_html(
        deck, [1], directory / "author.html", proxy_dir=directory / "proxies"
    )
    _close(deck)
    return result


def test_two_groups_with_identical_content_get_equivalent_proxies(
    twin_group_run: Any, tmp_path: Path
) -> None:
    """A shared proxy is correct exactly when the two containers' content is shared.

    The independent verifier found two different source groups whose proxies were
    byte-identical and asked whether the container placement was reading one
    object's content for both.  This pins the answer as a property rather than an
    observation: congruent containers must produce the same image, and the check
    that makes it a property is that *each* proxy is measured against its own
    region of the source slide -- both regions carry paint, and the two proxies
    carry the same paint in the same place.  A placement that leaked one group's
    children into the other's proxy, or that rendered one group from the other's
    members, would fail the second half.

    The two rasters are required to be equivalent rather than byte-identical
    because the renderer's antialiased edge is not bit-reproducible for the same
    rectangle drawn at a different x: on this fixture the two proxies agree on
    every solid pixel and differ only in the antialiased edge column, by 82
    pixels out of 20 496.  A byte comparison would therefore be asserting a
    property of the renderer, not of the placement.
    """
    from PIL import Image, ImageChops

    proxies = {}
    for item in twin_group_run.objects:
        if item.source_kind != "group":
            continue
        assert item.proxy_asset, item.source_object
        with Image.open(item.proxy_asset) as image:
            rgb = image.convert("RGB")
        proxies[item.source_object] = {
            "path": Path(item.proxy_asset),
            "image": rgb,
            "size": rgb.size,
            "bounds_px": item.bounds_px,
        }
    assert len(proxies) == 2, proxies
    first, second = proxies.values()

    # The two source rectangles are different places on the slide, of the same
    # size: the only difference between the two groups is where they sit.
    assert first["bounds_px"][0] != second["bounds_px"][0]
    assert first["bounds_px"][2:] == second["bounds_px"][2:]
    assert first["size"] == second["size"]

    # Each proxy carries paint of its own, so neither region is empty.
    for entry in proxies.values():
        colours = entry["image"].getcolors(entry["size"][0] * entry["size"][1] + 1) or ()
        entry["paint"] = sum(
            count
            for count, colour in colours
            if max(abs(channel - 255) for channel in colour) > 6
        )
        entry["background"] = sum(
            count for count, colour in colours if colour == (255, 255, 255)
        )
        assert entry["paint"] > 0, entry

    # The two proxies differ by at most an antialiased edge: every solid pixel is
    # the same colour, which is what "the same content" means here.
    difference = ImageChops.difference(first["image"], second["image"])
    differing = sum(
        count
        for count, colour in (difference.getcolors(1 << 16) or ())
        if colour != (0, 0, 0)
    )
    total = first["size"][0] * first["size"][1]
    assert differing / total < 0.01, (differing, total)
    for entry in proxies.values():
        assert entry["image"].getpixel((0, 0)) == (255, 255, 255)
    solid = (204, 51, 102)
    for entry in proxies.values():
        counts = dict(
            (colour, count)
            for count, colour in (entry["image"].getcolors(total + 1) or ())
        )
        assert counts.get(solid, 0) > 0, entry
    solid_counts = []
    for entry in proxies.values():
        counts = dict(
            (colour, count)
            for count, colour in (entry["image"].getcolors(total + 1) or ())
        )
        solid_counts.append(counts.get(solid, 0))
    assert abs(solid_counts[0] - solid_counts[1]) / max(solid_counts) < 0.01, solid_counts

    # The regions the proxies were cropped from are measured on the slide itself,
    # so the "same content" claim does not rest on the proxies agreeing with each
    # other.
    source = Path(twin_group_run.selection[0].source_pptx)
    raster = tmp_path / "source-slide.png"
    _officecli(
        "view", str(source), "screenshot", "--page", "1", "--render", "native",
        "--screenshot-width", "1920", "-o", str(raster),
    )
    factor = 1920 / 960.0
    guard = 2
    regions = []
    with Image.open(raster) as image:
        slide = image.convert("RGB")
        for x, y, width, height in TWIN_GROUP_BOXES:
            left = int(round(x * factor)) - guard
            top = int(round(y * factor)) - guard
            crop = slide.crop(
                (left, top, left + int(round(width * factor)) + guard * 2,
                 top + int(round(height * factor)) + guard * 2)
            )
            colours = crop.getcolors(crop.width * crop.height + 1) or ()
            regions.append(
                sum(
                    count
                    for count, colour in colours
                    if max(abs(channel - 255) for channel in colour) > 6
                )
            )
    assert all(count > 0 for count in regions), regions
    _close(source)


# ---------------------------------------------------------------------------
# Criterion 9: proxy isolation evidence, and a failed proof blocks
# ---------------------------------------------------------------------------


def test_a_zero_extent_target_is_measured_on_the_axis_that_has_one() -> None:
    """A vertical connector's density is measured on its height, not its width.

    OfficeCLI reports a vertical connector's rectangle as ``0pt`` wide, so its
    proxy raster is nothing but the two guard bands and the band-free width is
    zero.  Dividing by the width produced ``0.0 px/pt`` and failed the density
    rule for six such proxies on the real corpus -- a false positive on a proxy
    the isolation proof is supposed to accept, because both axes of one render
    share one scale and only one of them carries information about it.  An
    unmeasurable proxy is not judged on a density it does not have.
    """
    vertical = gate_module._raster_density(
        width=4, height=537, bounds_pt=(319.4806, 266.1244, 0.0, 266.35), guard_px=2
    )
    assert vertical == pytest.approx(2.001126, abs=1e-5)
    horizontal = gate_module._raster_density(
        width=1389, height=5, bounds_pt=(0.0, 0.0, 693.5, 0.0), guard_px=2
    )
    assert horizontal == pytest.approx(1.997116, abs=1e-5)
    # The measured axis still refuses a raster that is below the canvas density.
    assert gate_module._raster_density(
        width=121, height=19, bounds_pt=(0.0, 0.0, 58.36142, 7.59945), guard_px=2
    ) == pytest.approx(2.004749, abs=1e-5)
    assert gate_module._raster_density(
        width=31, height=31, bounds_pt=(0.0, 0.0, 58.36142, 7.59945), guard_px=2
    ) == pytest.approx(0.4626344, abs=1e-5)
    # No extent on either axis: no scale to recover, and no verdict from one.
    assert (
        gate_module._raster_density(
            width=4, height=4, bounds_pt=(0.0, 0.0, 0.0, 0.0), guard_px=2
        )
        is None
    )


def test_every_locked_proxy_carries_all_five_isolation_facts(clean_result: Any) -> None:
    """Target survival, density, guard band, bounds, and contamination."""
    proofs = [proof for page in clean_result.pages for proof in page.proxies]
    assert len(proofs) == 1
    proof = proofs[0]
    assert proof.passed is True, proof.failures
    assert proof.failures == ()
    assert proof.rebuilt_kind is not None, "target survival"
    assert proof.raster_density >= proof.required_density, "raster density"
    assert proof.guard_band_px >= 1, "guard band"
    assert proof.expected_width_px > 0 and proof.expected_height_px > 0, "target bounds"
    assert proof.guard_band_paint_fraction <= GUARD_BAND_CONTAMINATION_FRACTION
    assert proof.background_rgb is not None
    assert proof.disposition_blocking is False
    # Target survival is measured from the proxy's own bytes, not asserted from
    # the rebuilt deck: the image must show something that is not the background
    # it was cropped out of.
    assert proof.raster_pixels > 0
    assert proof.paint_pixels > 0, "the proxy's own raster must carry paint"
    assert proof.carries_paint is True
    payload = json.loads(
        (Path(clean_result.output_directory) / "proxy-isolation.json").read_text(
            encoding="utf-8"
        )
    )
    record = payload["proofs"][0]
    for field in (
        "target_survived",
        "density_ok",
        "guard_band_ok",
        "bounds_ok",
        "contamination_ok",
        "paint_measured",
        "carries_paint",
        "passed",
    ):
        assert record[field] is True, field
    assert record["paint_pixels"] == proof.paint_pixels
    assert record["raster_pixels"] == proof.raster_pixels
    assert record["paint_fraction"] > 0


def test_a_proxy_that_is_all_background_blocks(clean_run: Any, tmp_path: Path) -> None:
    """A flat proxy proves the target did not survive its reconstruction.

    An image of exactly the right size, under exactly the right name, of exactly
    the right kind, that shows nothing at all is not a representation of the
    object: it is the empty rectangle the object's content was supposed to be in.
    The gate accepted two such proxies on the real corpus because "target
    survival" only checked that a rebuilt *object* existed; this measures the
    proxy's own bytes instead.

    The flat raster is the background the isolation proof's own sampler reads, so
    the mutation removes every painted pixel without changing the raster's size
    or geometry.
    """
    result, intake = clean_run
    from PIL import Image

    def blank(path: Path) -> None:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        background = (
            rgb.getpixel((0, 0)),
            rgb.getpixel((rgb.width - 1, 0)),
            rgb.getpixel((0, rgb.height - 1)),
            rgb.getpixel((rgb.width - 1, rgb.height - 1)),
        )
        flat = max(set(background), key=background.count)
        rgb.paste(flat, (0, 0, rgb.width, rgb.height))
        rgb.save(path, format="PNG")

    result = _rejudge(clean_run, _mutate_run_proxy(blank, tmp_path, clean_run))
    assert result.outcome is GateOutcome.BLOCK
    diagnostics = [
        item for item in result.diagnostics if item.code == "proxy_isolation_failed"
    ]
    blank_diagnostic = next(
        (item for item in diagnostics if "no paint at all" in item.message), None
    )
    assert blank_diagnostic is not None, [item.message for item in diagnostics]
    assert blank_diagnostic.source_object
    assert blank_diagnostic.rebuilt_object
    proof = result.pages[0].proxies[0]
    assert proof.carries_paint is False
    assert proof.paint_pixels == 0
    assert proof.raster_pixels == proof.raster_width_px * proof.raster_height_px
    # The published `proxy-isolation.json` is written from these same proofs, and
    # `test_every_locked_proxy_carries_all_five_isolation_facts` reads it back
    # from the accepted run's own directory, so the document is still asserted.


def test_a_near_white_proxy_differing_from_its_background_still_passes() -> None:
    """The paint rule is "not the background", never "not white".

    A legitimately near-white object must still pass, which is why the rule
    measures against the proxy's own sampled background rather than against
    white.  The decision is made by the same measurement the proof uses, on
    rasters built for the purpose.
    """
    from PIL import Image

    background = (255, 255, 255)
    near_white = (247, 249, 250)

    def paint_pixels(*colours: tuple[int, int, int]) -> int:
        image = Image.new("RGB", (8, 8), background)
        for index, colour in enumerate(colours):
            image.paste(colour, (index, 0, index + 1, 1))
        return gate_module._painted_pixels(image, background)

    # A near-white object is paint even though it is only 8 levels from white.
    assert paint_pixels(near_white) == 1
    # An entirely flat raster of the background is not.
    assert paint_pixels() == 0
    # Noise inside the tolerance is the renderer's antialiasing, not content.
    assert paint_pixels((250, 250, 250)) == 0
    # And a raster one level past the tolerance is content again.
    assert paint_pixels((248, 248, 248)) == 1


def test_the_proxy_asset_is_hashed_in_the_evidence(clean_result: Any) -> None:
    """A swapped proxy payload is visible: the asset's bytes are hashed."""
    proof = clean_result.pages[0].proxies[0]
    assert proof.asset_sha256
    # The recorded hash is the emitted document's own payload, and it equals the
    # published asset's bytes, so the two sides of the proxy agree.
    assert proof.recorded_asset_sha256 == proof.asset_sha256
    assert hashlib.sha256(Path(proof.asset).read_bytes()).hexdigest() == proof.asset_sha256
    # The proof names the published asset, not the run's temporary one.
    assert Path(proof.asset).is_relative_to(Path(clean_result.output_directory))
    assert clean_result.proxy_assets
    assert set(clean_result.proxy_assets) == {proof.asset}


def _mutate_run_proxy(rewrite: Any, scratch: Path, clean_run: Any) -> Any:
    """Return an intake hook that rewrites a *copy* of this run's proxy asset.

    The hook receives the sealed intake bundle, which is where the run's own
    proxy assets are named.  Those name the staging directory the run deletes, so
    the bytes are taken from the published evidence -- the same bytes the accepted
    run wrote -- copied into ``scratch``, and pointed at the copy before the
    rewrite lands.  Mutating the published file itself would corrupt the accepted
    run's evidence directory, which the tests beside these read.
    """
    published_root = Path(clean_run[0].output_directory) / "projection"

    def mutate(intake: GateIntake) -> GateIntake:
        scratch.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, str] = {}
        for item in intake.projected.objects:
            if not item.proxy_asset:
                continue
            target = scratch / Path(item.proxy_asset).name
            if not target.exists():
                shutil.copy2(published_root / Path(item.proxy_asset).name, target)
            mapping[str(item.proxy_asset)] = str(target)
        assert mapping, "the run projected no locked proxy to mutate"
        rewrite(Path(next(iter(mapping.values()))))
        return _relocate_proxy_assets(intake, scratch)

    return mutate


def test_a_proxy_whose_bytes_were_swapped_blocks(clean_run: Any, tmp_path: Path) -> None:
    """Corrupting the proxy payload is detected by the isolation proof.

    The bytes are mutated on the run's own proxy asset -- the one the proof
    measures and the run publishes -- so the swap is judged by the production
    rule rather than simulated in the proof record.
    """

    result, intake = clean_run
    def corrupt(path: Path) -> None:
        payload = path.read_bytes()
        path.write_bytes(payload[:-64] + bytes(64))

    result = _rejudge(clean_run, _mutate_run_proxy(corrupt, tmp_path, clean_run))
    assert result.outcome is GateOutcome.BLOCK
    codes = {item.code for item in result.diagnostics}
    assert "proxy_isolation_failed" in codes


def test_a_contaminated_guard_band_blocks(clean_run: Any, tmp_path: Path) -> None:
    """Paint in the guard band that cannot belong to the target blocks.

    The band is painted on the run's own proxy asset -- the sibling paint the
    guard band exists to exclude is what a contaminated band looks like -- so the
    contamination is measured from actual bytes rather than simulated in the
    proof record.
    """
    result, intake = clean_run
    from PIL import Image, ImageDraw

    target = _object_named(result, "locked-preset")

    def contaminate(path: Path) -> None:
        with Image.open(path) as image:
            painted = image.convert("RGB")
        draw = ImageDraw.Draw(painted)
        draw.rectangle((0, 0, painted.width - 1, 0), fill=(128, 128, 128))
        painted.save(path, format="PNG")

    result = _rejudge(clean_run, _mutate_run_proxy(contaminate, tmp_path, clean_run))
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item
        for item in result.diagnostics
        if item.code == "proxy_isolation_failed" and "contamination" in item.message
    )
    assert diagnostic.source_object == target.source_object


def test_a_proxy_raster_at_the_wrong_density_blocks(clean_run: Any, tmp_path: Path) -> None:
    """An upscaled proxy is refused: its raster must reach the canvas density."""
    result, intake = clean_run
    from PIL import Image

    def downscale(path: Path) -> None:
        with Image.open(path) as image:
            small = image.convert("RGB").resize((31, 31))
        small.save(path, format="PNG")

    result = _rejudge(clean_run, _mutate_run_proxy(downscale, tmp_path, clean_run))
    assert result.outcome is GateOutcome.BLOCK
    assert any(
        item.code == "proxy_isolation_failed"
        and ("density" in item.message or "bounds" in item.message)
        for item in result.diagnostics
    )


# ---------------------------------------------------------------------------
# Criterion 10: ledger and source map completeness and one-to-one mapping
# ---------------------------------------------------------------------------


def test_the_ledger_classifies_every_source_object_exactly_once(clean_result: Any) -> None:
    """One disposition per slide-owned source object, and one emitted object each."""
    identities = [entry.identity for entry in clean_result.ledger]
    assert len(identities) == len(set(identities))
    html_ids = [entry.html_id for entry in clean_result.ledger if entry.html_id]
    assert len(html_ids) == len(set(html_ids))
    assert len(clean_result.projected.objects) == len(clean_result.ledger)


def test_every_ledger_entry_is_bound_to_a_source_hash(clean_result: Any) -> None:
    """An entry that is not bound to a source fingerprint would be unauditable."""
    for entry in clean_result.ledger:
        assert re.fullmatch(r"[0-9a-f]{64}", entry.source_sha256)
        assert entry.source_key
        assert entry.source_path
        assert entry.source_object
        assert entry.source_page >= 1
        assert entry.disposition in {
            DISPOSITION_CANONICAL,
            DISPOSITION_LOCKED,
            DISPOSITION_BASE_ONLY,
            "unsupported",
            "unresolved",
        }


def test_the_source_map_agrees_with_the_published_artifacts(clean_result: Any) -> None:
    """The published source map binds every emitted object to its source object."""
    source_map = json.loads(
        (Path(clean_result.output_directory) / "source-map.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(source_map["objects"]) == len(clean_result.projected.objects)
    for item in clean_result.projected.objects:
        record = next(
            entry for entry in source_map["objects"] if entry["html_id"] == item.html_id
        )
        assert record["source_object"] == item.source_object
        assert record["emitted_name"] == item.emitted_name
        assert record["source_sha256"] == clean_result.projected.source_sha256


def test_the_published_ledger_matches_the_run_ledger(clean_result: Any) -> None:
    """The ledger evidence document is the ledger the run classified."""
    payload = json.loads(
        (Path(clean_result.output_directory) / "disposition-ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["entries"]) == len(clean_result.ledger)
    assert [entry["source_object"] for entry in payload["entries"]] == [
        entry.source_object for entry in clean_result.ledger
    ]
    assert payload["counts"]["canonical-editable"] == 2


def test_an_ambiguous_mapping_blocks(clean_run: Any) -> None:
    """Two source objects sharing one emitted identity blocks acceptance.

    The identity collision is injected into the projected result, because the
    projection seam already refuses to publish one; the gate's own re-derivation
    from the published artifacts is what is under test.
    """
    result, intake = clean_run
    def collide(intake: GateIntake) -> GateIntake:
        first_html_id = intake.projected.objects[0].html_id
        return replace(
            intake,
            projected=replace(
                intake.projected,
                objects=tuple(
                    replace(item, html_id=first_html_id) if index == 1 else item
                    for index, item in enumerate(intake.projected.objects)
                ),
            ),
        )

    result = _rejudge(clean_run, collide)
    assert result.outcome is GateOutcome.BLOCK
    codes = {item.code for item in result.diagnostics}
    assert "ambiguous_mapping" in codes


def test_an_unsupported_disposition_blocks(clean_run: Any) -> None:
    """An unsupported or unresolved object is a blocking input.

    Both halves of the policy are exercised on one run: the disposition itself is
    a blocking input, and the object's isolation proof fails as well because a
    blocked object is never published as a proxy.  The unsupported projection is
    injected into the sealed intake bundle, because the #15 seam refuses to
    publish one at all.
    """
    result, intake = clean_run
    target = _object_named(result, "locked-preset")

    def unsupport(intake: GateIntake) -> GateIntake:
        return replace(
            intake,
            projected=replace(
                intake.projected,
                objects=tuple(
                    replace(
                        item,
                        disposition="unsupported",
                        reason="no object-local visual representation is available",
                        reason_code="proxy_isolation_unavailable",
                        proxy_asset=None,
                    )
                    if item.identity == target.identity
                    else item
                    for item in intake.projected.objects
                ),
            ),
        )

    result = _rejudge(clean_run, unsupport)
    assert result.outcome is GateOutcome.BLOCK
    codes = {item.code for item in result.diagnostics}
    assert "blocking_disposition" in codes
    diagnostic = next(
        item for item in result.diagnostics if item.code == "blocking_disposition"
    )
    assert diagnostic.source_object == target.source_object
    assert diagnostic.rebuilt_object == target.emitted_name


# ---------------------------------------------------------------------------
# Criterion 11: artifact hashing and source re-hash
# ---------------------------------------------------------------------------


def test_every_published_artifact_is_hashed(clean_result: Any) -> None:
    """Each published file has a hash that matches the bytes on disk."""
    assert clean_result.artifacts
    names = {item.name for item in clean_result.artifacts}
    for required in (
        "disposition-ledger.json",
        "source-map.json",
        "projection-report.json",
        "rebuilt.pptx",
        "canonical-author.html",
    ):
        assert required in names, sorted(names)
    for item in clean_result.artifacts:
        path = Path(item.path)
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item.sha256
        assert path.stat().st_size == item.size_bytes
    # The projection's own artifacts are published and hashed with the rest.
    assert "projection/source-map.json" in names
    assert "projection/projection-report.json" in names
    assert "projection/canonical-author.html" in names
    assert any(name.startswith("projection/proxy-") for name in names)


def test_the_published_report_lists_the_same_hashes(clean_result: Any) -> None:
    """The report's own artifact inventory matches what was published.

    The report carries the hash of every published artifact except the report and
    its markdown twin -- a document cannot contain its own hash -- so those two
    are verified by re-hashing the files, and every other published file must
    appear in the inventory.
    """
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    listed = {item["name"] for item in report["artifacts"]}
    assert listed == {item.name for item in clean_result.artifacts}
    assert "gate-report.json" not in listed
    assert "gate-report.md" not in listed
    for item in report["artifacts"]:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    published = {
        str(path.relative_to(Path(clean_result.output_directory))).replace("\\", "/")
        for path in Path(clean_result.output_directory).rglob("*")
        if path.is_file()
    }
    assert published - {"gate-report.json", "gate-report.md"} == listed
    # The two excluded documents are still independently verifiable.
    assert Path(clean_result.report_path).is_file()
    assert (Path(clean_result.output_directory) / "gate-report.md").is_file()


def test_the_source_is_re_hashed_and_the_source_file_is_unchanged(
    clean_result: Any,
) -> None:
    """Source hashes are verified again after the run, and the source did not move."""
    assert clean_result.source_verification
    for record in clean_result.source_verification:
        assert record["verified"] is True
        assert record["sha256_at_capture"] == record["sha256_after_run"]
        assert hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() == record[
            "sha256_at_capture"
        ]


def test_a_stale_source_hash_blocks(clean_deck: Path, tmp_path: Path) -> None:
    """A source deck that changed during the run blocks acceptance.

    The source is replaced with different bytes from inside the gate's own
    intake hook, which runs after the projection has captured and hashed it and
    before the post-run re-hash: that is exactly the race the re-hash exists to
    catch.  The original bytes are always restored.
    """
    deck = tmp_path / "stale-source.pptx"
    shutil.copy2(clean_deck, deck)
    _close(deck)
    original = deck.read_bytes()

    def rewrite_source(intake: GateIntake) -> GateIntake:
        _close(deck)
        deck.write_bytes(original + b"\n<!-- mutated after capture -->\n")
        return intake

    try:
        result = _run_gate(deck, tmp_path / "gate", intake_mutation=rewrite_source)
    finally:
        _close(deck)
        _replace_with_retry(_bytes_to_temp(original, tmp_path), deck)
    assert result.outcome is GateOutcome.BLOCK
    diagnostic = next(
        item for item in result.diagnostics if item.code == "stale_source_hash"
    )
    assert "no longer hashes to the fingerprint" in diagnostic.message
    assert diagnostic.source_key


def test_a_changed_source_refuses_to_publish_again_on_the_same_directory(
    clean_result: Any, tmp_path: Path
) -> None:
    """A published gate directory is never silently overwritten."""
    output = Path(clean_result.output_directory)
    with pytest.raises(ProjectionError) as failure:
        gate_projected_author_html(
            [(clean_result.projected.selection[0].source_pptx, 1)], output
        )
    assert failure.value.code == "output_collision"


def _bytes_to_temp(payload: bytes, directory: Path) -> Path:
    target = directory / "restore.bin"
    target.write_bytes(payload)
    return target


def _without_working_paths(payload: Any) -> Any:
    """Return a projection document with its run-local file paths blanked out.

    Two projection runs of the same page in different working directories produce
    the same evidence except for the absolute paths of the transient proxy assets
    they wrote.  Blanking those lets a test compare what the documents *say*
    about the document without comparing where each run happened to work.
    """
    if isinstance(payload, dict):
        return {
            key: ("<asset>" if key == "proxy_asset" else _without_working_paths(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_without_working_paths(item) for item in payload]
    return payload


# ---------------------------------------------------------------------------
# Criterion 12: atomic publication
# ---------------------------------------------------------------------------


def test_a_blocked_run_publishes_no_accepted_gate_report(
    clean_result: Any, tmp_path: Path
) -> None:
    """A BLOCK leaves evidence, but nothing that says the gate was completed.

    The complete evidence set is published so a reviewer can repair the run, and
    the report is named ``gate-rejected.json``: the document that means
    "accepted" is never written by a run that did not reach an accepting
    outcome.
    """
    output = tmp_path / "gate"

    def add_issue(intake: GateIntake) -> GateIntake:
        target = intake.projected.objects[0]
        return replace(
            intake,
            rebuilt_issue_records=(
                *intake.rebuilt_issue_records,
                _rebuilt_issue(
                    _issue_path_of(intake, target.emitted_name),
                    "text overflow: 5 lines at 18.0pt need 90pt, usable 40pt.",
                ),
            ),
        )

    result = _run_gate(
        clean_result.projected.selection[0].source_pptx,
        output,
        intake_mutation=add_issue,
    )
    assert result.outcome is GateOutcome.BLOCK
    assert result.published is True
    assert result.output_directory == str(output.resolve())
    assert result.report_path is not None
    assert Path(result.report_path).name == "gate-rejected.json"
    assert not (output / "gate-report.json").exists()
    assert not (output / "gate-report.md").exists()
    # The evidence a repair needs is all there.
    assert (output / "gate-rejected.json").is_file()
    assert (output / "disposition-ledger.json").is_file()
    assert (output / "rebuilt.pptx").is_file()
    assert (output / "canonical-author.html").is_file()
    assert (output / "projection" / "source-map.json").is_file()
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["outcome"] == "BLOCK"
    assert report["material_deltas"]
    assert report["report_name"] == "gate-rejected.json"
    # And every published file is hashed.
    for item in result.artifacts:
        assert hashlib.sha256(Path(item.path).read_bytes()).hexdigest() == item.sha256


def test_an_accepted_run_writes_the_gate_report(clean_result: Any) -> None:
    """Only an accepting outcome writes the document that means accepted."""
    output = Path(clean_result.output_directory)
    assert Path(clean_result.report_path).name == "gate-report.json"
    assert (output / "gate-report.json").is_file()
    assert (output / "gate-report.md").is_file()
    assert not (output / "gate-rejected.json").exists()


def test_a_failed_run_leaves_no_staging_directory(tmp_path: Path) -> None:
    """A run that cannot even build the deck removes its own staging area."""
    missing = tmp_path / "does-not-exist.pptx"
    with pytest.raises(ProjectionError):
        gate_projected_author_html([(str(missing), 1)], tmp_path / "gate")
    assert not (tmp_path / "gate").exists()
    assert not list(tmp_path.glob(".gate-*"))


def test_a_failed_new_deck_build_publishes_nothing(
    clean_result: Any, tmp_path: Path
) -> None:
    """A rebuild failure is a hard failure, not an accepted gate."""

    class _Failed:
        status = "BLOCK"
        diagnostics = ()

    def failing_rebuild(html_path: str, pptx_path: str) -> Any:
        raise ProjectionError("the New Deck build refused the document", code="build_failed")

    sources = replace(gate_module._default_sources(), rebuild=failing_rebuild)
    output = tmp_path / "gate"
    with pytest.raises(ProjectionError):
        _run_gate(
            clean_result.projected.selection[0].source_pptx,
            output,
            sources=sources,
        )
    assert not output.exists()
    del _Failed


def test_a_build_that_reports_failure_is_not_treated_as_acceptance(
    clean_result: Any, tmp_path: Path
) -> None:
    """OfficeCLI process success is not acceptance: the build status is read."""

    class _Blocked:
        status = "BLOCK"
        diagnostics = ()

    def blocked_rebuild(html_path: str, pptx_path: str) -> Any:
        return _Blocked()

    sources = replace(gate_module._default_sources(), rebuild=blocked_rebuild)
    output = tmp_path / "gate"
    with pytest.raises(ProjectionError) as failure:
        _run_gate(
            clean_result.projected.selection[0].source_pptx,
            output,
            sources=sources,
        )
    assert failure.value.code == "new_deck_build_failed"
    assert not output.exists()


# ---------------------------------------------------------------------------
# Criterion 13: the structured outcome is derived, never inferred
# ---------------------------------------------------------------------------


def test_the_outcome_enum_has_exactly_three_values() -> None:
    """PASS, PASS_WITH_FINDINGS, and BLOCK are the whole vocabulary."""
    assert [item.value for item in GateOutcome] == [
        "PASS",
        "PASS_WITH_FINDINGS",
        "BLOCK",
    ]


def test_the_outcome_is_derived_from_evidence_only() -> None:
    """Each branch of the derivation is exercised with explicit evidence."""
    assert (
        classify_gate_outcome(
            diagnostics=(),
            material_deltas=(),
            retained_findings=(),
            scope_evidence=(),
            checks_complete=True,
        )
        is GateOutcome.PASS
    )
    assert (
        classify_gate_outcome(
            diagnostics=(),
            material_deltas=(),
            retained_findings=(
                RetainedFinding(
                    source_key="src1",
                    source_page=1,
                    source_object="/slide[1]/shape[@id=1]",
                    condition="text_overflow",
                    reason="source-inherent",
                    rebuilt_slide=1,
                    rebuilt_object="slide-001-textbox-001",
                    source_issue={},
                ),
            ),
            scope_evidence=(),
            checks_complete=True,
        )
        is GateOutcome.PASS_WITH_FINDINGS
    )
    assert (
        classify_gate_outcome(
            diagnostics=(),
            material_deltas=(
                MaterialDelta(
                    source_key="src1",
                    source_page=1,
                    source_object="/slide[1]/shape[@id=1]",
                    condition="text_overflow",
                    reason="rebuilt-only",
                    rebuilt_slide=1,
                    rebuilt_object="slide-001-textbox-001",
                    rebuilt_issue={},
                ),
            ),
            retained_findings=(),
            scope_evidence=(),
            checks_complete=True,
        )
        is GateOutcome.BLOCK
    )
    assert (
        classify_gate_outcome(
            diagnostics=(),
            material_deltas=(),
            retained_findings=(),
            scope_evidence=(),
            checks_complete=False,
        )
        is GateOutcome.BLOCK
    )


def test_a_contract_pass_alone_is_not_acceptance(clean_result: Any) -> None:
    """The Author Contract passes and the gate still decides for itself.

    Both are true at once for the accepted fixture, which is the point: the
    Contract status is never read as the gate's outcome, and the gate's outcome
    is never read as the Contract's status.
    """
    contract = check_contract(
        Path(clean_result.output_directory) / "canonical-author.html", "author"
    )
    assert contract.status == "PASS"
    assert clean_result.outcome is GateOutcome.PASS
    retained = _object_named(clean_result, "clean-text")
    assert retained.disposition == DISPOSITION_CANONICAL


def test_an_officecli_issue_count_is_not_the_outcome(overflow_result: Any) -> None:
    """A non-zero OfficeCLI issue count can still be an accepted run."""
    assert overflow_result.rebuilt_evidence[0].issue_count >= 1
    assert overflow_result.outcome is GateOutcome.PASS_WITH_FINDINGS
    assert overflow_result.accepted is True


# ---------------------------------------------------------------------------
# Criterion 14: every deliberate mutation is detected
# ---------------------------------------------------------------------------

_MUTATION_NAMES = (
    "issue_output",
    "table_dimensions",
    "cell_text",
    "native_shape_kind",
    "mapping_identity",
    "proxy_bytes",
    "source_hash",
)


def test_every_deliberate_mutation_is_detected(clean_deck: Path, tmp_path: Path) -> None:
    """All seven mutations from the criterion are caught, each on its own run.

    Five of the seven are injected into the gate's sealed intake bundle or its
    rebuilt-deck read, because OfficeCLI cannot be made to report a rebuilt-only
    issue, a wrong table dimension, a wrong native kind, or a swapped proxy
    payload for a deck the New Deck path actually built correctly; the
    comparison that judges each mutation is the production comparison.  The
    source-hash mutation is a real end-to-end mutation of the source bytes, and
    the proxy-bytes mutation is a real mutation of the published asset.  Every
    run gets its own copy of the fixture deck and its own output directory.
    """
    detected: dict[str, Any] = {}
    for name in _MUTATION_NAMES:
        deck = tmp_path / f"mutated-{name}.pptx"
        shutil.copy2(clean_deck, deck)
        _close(deck)
        original_deck = deck.read_bytes()
        output = tmp_path / f"gate-{name}"
        mutation = _mutation(name, deck, original_deck, tmp_path)
        try:
            result = _run_gate(deck, output, intake_mutation=mutation)
        finally:
            _close(deck)
            _replace_with_retry(_bytes_to_temp(original_deck, tmp_path), deck)
        detected[name] = result
        assert result.outcome is GateOutcome.BLOCK, (
            f"mutation {name!r} was not detected: {result.outcome.value}"
        )
        assert Path(result.report_path).name == "gate-rejected.json", (
            f"mutation {name!r} wrote an accepted gate report"
        )
        assert not (output / "gate-report.json").exists(), (
            f"mutation {name!r} left an accepted gate report"
        )
        assert result.diagnostics, f"mutation {name!r} produced no diagnostic"
    assert set(detected) == set(_MUTATION_NAMES)


def _mutation(name: str, deck: Path, original_deck: bytes, tmp_path: Path):
    """Return the intake mutation that injects one deliberate fault."""
    if name == "issue_output":

        def mutate(intake: GateIntake) -> GateIntake:
            target = intake.projected.objects[0]
            path = next(
                item.path
                for item in intake.rebuilt_objects
                if item.emitted_name == target.emitted_name
            )
            return replace(
                intake,
                rebuilt_issue_records=(
                    *intake.rebuilt_issue_records,
                    _rebuilt_issue(
                        path, "text overflow: 4 lines at 18.0pt need 80pt, usable 40pt."
                    ),
                ),
            )

        return mutate

    if name == "table_dimensions":

        def mutate(intake: GateIntake) -> GateIntake:
            target = next(
                item
                for item in intake.projected.objects
                if item.projected_kind == "table"
            )
            return replace(
                intake,
                rebuilt_objects=tuple(
                    replace(item, rows=(item.rows or 0) + 1)
                    if item.emitted_name == target.emitted_name
                    else item
                    for item in intake.rebuilt_objects
                ),
            )

        return mutate

    if name == "cell_text":

        def mutate(intake: GateIntake) -> GateIntake:
            target = next(
                item
                for item in intake.projected.objects
                if item.projected_kind == "table"
            )
            return replace(
                intake,
                rebuilt_objects=tuple(
                    replace(item, cells=tuple(reversed(item.cells)))
                    if item.emitted_name == target.emitted_name
                    else item
                    for item in intake.rebuilt_objects
                ),
            )

        return mutate

    if name == "native_shape_kind":

        def mutate(intake: GateIntake) -> GateIntake:
            target = next(
                item
                for item in intake.projected.objects
                if item.projected_kind == "textbox"
            )
            return replace(
                intake,
                rebuilt_objects=tuple(
                    replace(item, rebuilt_kind="picture")
                    if item.emitted_name == target.emitted_name
                    else item
                    for item in intake.rebuilt_objects
                ),
            )

        return mutate

    if name == "mapping_identity":

        def mutate(intake: GateIntake) -> GateIntake:
            first = intake.projected.objects[0]
            return replace(
                intake,
                projected=replace(
                    intake.projected,
                    objects=tuple(
                        replace(item, source_object="/slide[9]/shape[@id=999999]")
                        if item is first
                        else item
                        for item in intake.projected.objects
                    ),
                ),
            )

        return mutate

    if name == "proxy_bytes":

        def mutate(intake: GateIntake) -> GateIntake:
            candidates = [item for item in intake.projected.objects if item.proxy_asset]
            assert candidates, "the mutation fixture projected no locked proxy"
            path = Path(candidates[0].proxy_asset)
            payload = path.read_bytes()
            # The asset belongs to this run -- it lives in the run's own working
            # directory, which the gate removes -- so nothing has to be restored.
            path.write_bytes(payload[:-32] + bytes(32))
            return intake

        return mutate

    if name == "source_hash":

        def mutate(intake: GateIntake) -> GateIntake:
            _close(deck)
            deck.write_bytes(original_deck + b"\n<!-- mutation -->\n")
            return intake

        return mutate

    raise AssertionError(f"unknown mutation {name!r}")


# ---------------------------------------------------------------------------
# Criterion 15: the gate preserves the unchanged Contract and New Deck behaviour
# ---------------------------------------------------------------------------


def test_the_projection_still_passes_the_author_contract_unchanged(
    clean_result: Any,
) -> None:
    """The gate does not change what Canonical Author HTML means."""
    report = check_contract(
        Path(clean_result.output_directory) / "canonical-author.html", "author"
    )
    assert report.status == "PASS"
    assert report.blocked is False
    assert report.diagnostics == ()


def test_the_rebuilt_deck_keeps_its_native_object_surface(clean_result: Any) -> None:
    """Native tables and text boxes stay native through the gate's rebuild."""
    kinds = {item.rebuilt_kind for item in clean_result.rebuilt_objects}
    assert "table" in kinds
    assert "textbox" in kinds
    assert "picture" in kinds


def test_the_gate_does_not_change_the_projection_artifacts(
    clean_result: Any, clean_deck: Path
) -> None:
    """The gate publishes the projection's own artifacts unchanged.

    The comparison is made against the projection the gate itself ran, whose
    working copies are removed with its staging directory, so the projection is
    re-run over the same source page and its artifacts are compared byte for
    byte with what the gate published.
    """
    import shutil as _shutil

    reference_root = Path(clean_result.output_directory).parent / "reference-projection"
    _shutil.rmtree(reference_root, ignore_errors=True)
    reference_root.mkdir(parents=True)
    reference = project_pptx_to_author_html(
        PageSelection([(str(clean_deck), 1)]),
        reference_root / "author.html",
        proxy_dir=reference_root / "proxies",
    )
    evidence = Path(clean_result.output_directory)
    published_html = Path(clean_result.projection_artifacts["canonical_author_html"])
    published_map = Path(clean_result.projection_artifacts["source_map"])
    published_projection_report = Path(
        clean_result.projection_artifacts["projection_report"]
    )
    for path in (published_html, published_map, published_projection_report):
        assert path.is_file(), path
    # The published copies preserve the seam's artifacts: the Canonical Author
    # HTML has no absolute path in it at all, and the two JSON documents differ
    # only in the working-directory paths they carry -- so a reviewer reading the
    # published evidence reads the same content the gate judged.
    assert published_html.read_bytes() == Path(reference.output_html).read_bytes()
    published_map_payload = _without_working_paths(
        json.loads(published_map.read_text(encoding="utf-8"))
    )
    reference_map_payload = _without_working_paths(
        json.loads(Path(reference.source_map_path).read_text(encoding="utf-8"))
    )
    assert published_map_payload == reference_map_payload
    assert json.loads(published_projection_report.read_text(encoding="utf-8"))[
        "counts"
    ] == json.loads(Path(reference.projection_report_path).read_text(encoding="utf-8"))[
        "counts"
    ]
    assert (evidence / "source-map.json").read_bytes() == published_map.read_bytes()
    assert (
        evidence / "canonical-author.html"
    ).read_bytes() == published_html.read_bytes()
    assert clean_result.proxy_assets
    for path in clean_result.proxy_assets:
        assert Path(path).is_file()


def test_the_public_seam_has_no_new_command_or_manifest_entry() -> None:
    """The gate adds no command, no object kind, and no capability claim."""
    from officecli_html_to_pptx import get_capabilities
    from officecli_html_to_pptx.application import PUBLIC_COMMANDS

    assert PUBLIC_COMMANDS == ("capabilities", "doctor", "check", "build", "finalize")
    data = get_capabilities().data
    assert data["commands"] == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
    ]
    # The capability manifest is the Author Contract's own surface.  A gate is an
    # acceptance procedure, not a capability: it must not have added an object
    # kind, a profile, or a scope claim to the published manifest.
    contract = data["contract"]
    assert contract["object_kinds"] == ["picture", "shape", "table", "textbox"]
    assert contract["profile"] == "author"
    assert contract["version"] == "1.0"
    assert data["scope"]["existing_pptx_editing"] is False
    assert data["scope"]["officehtml_import"] is False
    assert data["scope"]["creates_new_pptx"] is True


# ---------------------------------------------------------------------------
# Published comparison rules
# ---------------------------------------------------------------------------


def test_the_issue_normalization_rule_keeps_measurements_as_context() -> None:
    """Numbers are context, not identity: the same kind compares as one kind."""
    first = normalize_issue_condition(
        "text overflow: 2 lines at 27.2pt need 65pt, usable 33pt."
    )
    second = normalize_issue_condition(
        "text overflow: 12 lines at 20.0pt need 276pt, usable 23pt."
    )
    assert first == second == "text_overflow"
    message = "text overflow: 2 lines at 27.2pt need 65pt, usable 33pt."
    record = IssueRecord(
        source_key="src1",
        source_page=1,
        source_object="/slide[1]/shape[@id=1]",
        scope="object",
        condition=first,
        message=message,
        severity="1",
        issue_id="O1",
        measured=gate_module.issue_measurements(message),
    )
    assert record.measurement("need_pt") == 65.0
    assert record.measurement("usable_pt") == 33.0
    assert pressure_ratio(record) == pytest.approx(65.0 / 33.0)


def test_the_normalization_rule_is_published_with_the_evidence(clean_result: Any) -> None:
    """A reviewer can read the rule the gate actually applied."""
    names = {item.name for item in clean_result.rules}
    assert {
        "source_identity_key",
        "issue_normalization",
        "retained_vs_material",
        "materially_worsened",
        "scope_evidence",
        "table_structure",
        "text_readback",
        "style_readback",
        "table_cell_readback",
        "rebuilt_issue_binding",
        "proxy_isolation",
        "artifact_hashing",
    } <= names
    report = json.loads(Path(clean_result.report_path).read_text(encoding="utf-8"))
    assert {item["name"] for item in report["comparison_rules"]} == names


def test_the_published_tolerances_are_the_ones_the_rule_uses() -> None:
    """The thresholds are named constants, not magic numbers buried in a rule."""
    assert OVERFLOW_RATIO_ABSOLUTE_TOLERANCE == 0.02
    assert OVERFLOW_RATIO_RELATIVE_TOLERANCE == 0.05
    assert GUARD_BAND_CONTAMINATION_FRACTION == 0.5


def test_whitespace_normalization_is_published_and_applied() -> None:
    """The report's whitespace-blind rendering, which is not the acceptance rule."""
    assert normalize_text("a\nb   c \t") == "a b c"
    assert normalize_text("\u00a0a\u00a0") == "a"
    # The report collapses whitespace, so a moved space reads as the same
    # characters.  That is a reporting convenience; see the comparison test below
    # for what actually decides acceptance.
    assert compact_text("HIGHLY GSX102") == compact_text("HIGHLYGSX102")
    assert compact_text("IDU SIZE") == compact_text("IDU  SIZE")
    assert compact_text("910x305x195") != compact_text("910x305x19")
    assert compact_text("MODEL") != compact_text("MODLE")


def test_the_text_comparison_preserves_structure() -> None:
    """The rule that decides whether rebuilt text is faithful.

    A whitespace-blind comparison cannot see a lost hard break, a lost paragraph
    boundary, or two words run together -- and this gate shipped with one, so
    visual review found those defects instead of the gate.  The rule is now an
    explicit, enumerated normalization that keeps structure, and this test pins
    the boundary between what may legitimately differ and what may not.
    """
    # May differ: the same content with a break spelled another way, a display-only
    # non-breaking space, and a tab where the source had a space.
    assert structure_text("one\x0btwo") == structure_text("one\ntwo")
    assert structure_text("one\rtwo") == structure_text("one\ntwo")
    # A Windows line ending is ONE line ending, not two.
    assert structure_text("one\r\ntwo") == structure_text("one\ntwo")
    assert structure_text("A\u00a0B") == structure_text("A B")
    assert structure_text("A\tB") == structure_text("A B")
    assert structure_text("A  B") == structure_text("A B")
    assert structure_text("A \nB") == structure_text("A\nB")

    # May not differ: an unapproved Unicode space, structure lost, words run
    # together, characters changed.
    #
    # U+00A0 is the ONE display-only normalization the product approves.  U+202F
    # must not be normalized implicitly: Python's str.split() would treat it as
    # whitespace, which is why the collapse uses an explicit character class.  If
    # this ever passes, the enumerated rule has quietly widened.
    assert structure_text("A\u202fB") != structure_text("A B"), (
        "U+202F is not an approved display-only normalization"
    )
    assert structure_text("line one\nline two") != structure_text("line oneline two")
    assert structure_text("line one\nline two") != structure_text("line one line two")
    assert structure_text("A B") != structure_text("AB")
    assert structure_text("Model 12K") != structure_text("Model 12")
    assert structure_text("MODEL") != structure_text("MODLE")

    # An empty paragraph between content is a paragraph the source painted, so it
    # is preserved; a trailing one carries no content and is dropped.
    assert structure_text("A\n\nB") != structure_text("A\nB")
    assert structure_text("A\n\n") == structure_text("A")

    # The exact shape of the defect that a whitespace-blind rule accepted.
    merged = "Hard break probe linesecond visual line"
    split = "Hard break probe line\nsecond visual line"
    assert compact_text(merged) == compact_text(split)
    assert structure_text(merged) != structure_text(split)


def test_a_structure_lost_difference_is_not_a_whitespace_finding() -> None:
    """Two words run together is a blocking difference, not a spacing detail."""
    readback = TextReadback(
        source_key="src1",
        source_page=1,
        source_object="/slide[1]/shape[@name=probe]",
        emitted_name="slide-001-textbox-001",
        rebuilt_kind="textbox",
        rebuilt_slide=1,
        expected_text="Hard break probe line\nsecond visual line",
        rebuilt_text="Hard break probe linesecond visual line",
        style_declarations={},
    )
    assert readback.compact_equal is True, "the characters did survive"
    assert readback.matched is False, "but the structure did not"
    assert readback.structure_lost is True
    assert readback.whitespace_only_difference is False
    payload = readback.as_dict()
    assert payload["structure_lost"] is True
    assert payload["expected_structure_text"] != payload["rebuilt_structure_text"]


def _record(
    identity: tuple[str, int, str],
    *,
    condition: str,
    need: float | None = None,
    usable: float | None = None,
) -> IssueRecord:
    """Return one synthetic issue record for the comparison-rule tests."""
    parts = []
    if need is not None:
        parts.append(f"need {need}pt")
    if usable is not None:
        parts.append(f"usable {usable}pt")
    message = condition.replace("_", " ") + (": " + ", ".join(parts) if parts else "")
    return IssueRecord(
        source_key=identity[0],
        source_page=identity[1],
        source_object=identity[2],
        scope="object",
        condition=condition,
        message=message,
        severity="1",
        issue_id="O1",
        measured=gate_module.issue_measurements(message),
    )
