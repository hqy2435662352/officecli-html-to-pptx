"""V0.4.2 multi-deck selected-page projection and disposition-ledger tests.

The external seam under test is::

    project_pptx_to_author_html(selection, output_html, proxy_dir=...)
        -> one Canonical Author HTML document, in selection order
         + per-source provenance
         + a per-object disposition ledger
         + source map + projection report + structured diagnostics

and the V0.4.1 single-deck spelling of the same call::

    project_pptx_to_author_html(deck, [1, 2], output_html, proxy_dir=...)

Every test drives that one seam and the result types it exports.  Nothing here
freezes the private reader calls, the OfficeCLI command shapes, or the internal
DTOs, because a caller must not have to depend on them.

The fixtures are small synthetic decks built through OfficeCLI itself, so no
private deck is ever committed.  Two of them are built with the same object
creation order on purpose: OfficeCLI then reports the very same
``/slide[1]/shape[@id=100000]`` path for objects of different decks, which is
exactly the source-identity collision a per-source key has to survive.  A third
fixture carries a group with an owned shape and an owned connector, and a fourth
is a file that is not a PowerPoint package at all.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Mapping, Sequence
import zipfile

import pytest

from officecli_html_to_pptx import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_UNRESOLVED,
    DISPOSITION_UNSUPPORTED,
    DISPOSITIONS,
    REASON_CODES,
    DispositionLedgerEntry,
    MissingPageError,
    OutputCollisionError,
    PageSelection,
    ProjectionBlockedError,
    ProjectionError,
    ProjectionResult,
    ProjectionSelectionError,
    ProjectionSourceError,
    ProjectionSourceRecord,
    SelectedPage,
    SourceChangedError,
    build_author_html,
    project_pptx_to_author_html,
)
from officecli_html_to_pptx.application import PUBLIC_COMMANDS
from officecli_html_to_pptx.contract import check_contract
from officecli_html_to_pptx.protocol import PRODUCT_VERSION

from officecli_html_to_pptx._internal import author_projector as projector
from officecli_html_to_pptx._internal.pptx_reader import (
    CapturedObject,
    CapturedParagraph,
    CapturedRun,
)

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V0.4.2 selected-page projection tests",
)

# ---------------------------------------------------------------------------
# Fixture literals.  Every expectation below is written from these, never from
# the projector's own output.
# ---------------------------------------------------------------------------

DECK_A = "alpha"
DECK_B = "beta"
DECK_GROUP = "group"
DECK_CORRUPT = "corrupt"
DECK_FOUR_THREE = "four-three"

A_TITLE = "Alpha deck page one 中文"
A_SECOND = "Alpha deck page two"
A_THIRD = "Alpha deck page three"
B_TITLE = "Beta deck page one"
B_SECOND = "Beta deck page two 🚀"
A_BOX_FILL = "#3366CC"
B_BOX_FILL = "#E8A33D"
CHEVRON_FILL = "#D96666"
TABLE_CELLS = (("REGION", "SHARE"), ("North", "42%"))
GROUP_CHILD_NAME = "inner-box"
GROUP_CONNECTOR_NAME = "inner-link"
GROUP_SIBLING_TEXT = "Ungrouped sibling text"
# The group page's children are authored *outside* the group's own rectangle, so
# the container cannot be represented: that is this deck's block.  A child the
# group's rectangle could hold is no longer a refusal, because the projection
# now tries OfficeCLI's reported rectangles as well as a declared child space.
GROUP_BOX_PT = (200.0, 200.0, 200.0, 120.0)
GROUP_CHILD_BOX_PT = (600.0, 300.0, 80.0, 40.0)
GROUP_CONNECTOR_BOX_PT = (600.0, 380.0, 80.0, 40.0)

PAGE_SIZE_PT = (960.0, 540.0)
CANVAS_PX = (1920.0, 1080.0)
PIXELS_PER_POINT = 2.0

# A 4x3 opaque PNG, small enough to inline as a base64 literal in the fixture
# (the same synthetic probe payload the V0.4.1 seam tests use).
_PICTURE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAHElEQVQI12P8//8/AzbAxMDA"
    "wMDAwMDAwMDAwAAAJhwEAX8lErwAAAAASUVORK5CYII="
)
_PICTURE_URI = "data:image/png;base64," + base64.b64encode(_PICTURE_PNG).decode("ascii")

# The scrambled multi-deck selection: two decks, both of them selected twice,
# and both decks' page 1 in the same run.
MULTI_SELECTION = (
    (DECK_B, 2),
    (DECK_A, 3),
    (DECK_B, 1),
    (DECK_A, 1),
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
        (argument for argument in args[1:] if argument.lower().endswith(".pptx")),
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slide(name: str) -> dict[str, Any]:
    return {"command": "add", "parent": "/", "type": "slide", "props": {"name": name}}


def _textbox(
    parent: str, name: str, text: str, *, x: str, y: str
) -> dict[str, Any]:
    return {
        "command": "add",
        "parent": parent,
        "type": "textbox",
        "props": {
            "name": name,
            "text": text,
            "x": x,
            "y": y,
            "width": "300pt",
            "height": "40pt",
            "size": "18pt",
            "font": "Microsoft YaHei",
            "color": "#14243A",
            "fill": "none",
            "line": "none",
        },
    }


def _rect(
    parent: str, name: str, *, x: str, y: str, fill: str
) -> dict[str, Any]:
    return {
        "command": "add",
        "parent": parent,
        "type": "shape",
        "props": {
            "name": name,
            "geometry": "rect",
            "x": x,
            "y": y,
            "width": "200pt",
            "height": "80pt",
            "fill": fill,
            "line": "none",
        },
    }


def _alpha_commands() -> list[dict[str, Any]]:
    """Three pages: text, a plain rect, and a page with a chevron and a table.

    The chevron is a preset the canonical Author object surface has no
    equivalent for, so it is the fixture's locked visual proxy.  Nothing here is
    an ellipse or a right arrow, because those presets are their own V0.4.2
    ticket and this file must not pin their classification.
    """
    return [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        _slide("alpha-1"),
        _slide("alpha-2"),
        _slide("alpha-3"),
        _textbox("/slide[1]", "alpha-title", A_TITLE, x="40pt", y="40pt"),
        _rect("/slide[1]", "alpha-box", x="40pt", y="120pt", fill=A_BOX_FILL),
        _textbox("/slide[2]", "alpha-second", A_SECOND, x="40pt", y="40pt"),
        {
            "command": "add",
            "parent": "/slide[2]",
            "type": "shape",
            "props": {
                "name": "alpha-chevron",
                "geometry": "chevron",
                "x": "400pt",
                "y": "300pt",
                "width": "120pt",
                "height": "60pt",
                "fill": CHEVRON_FILL,
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[2]",
            "type": "table",
            "props": {
                "name": "alpha-table",
                "x": "40pt",
                "y": "120pt",
                "width": "320pt",
                "height": "60pt",
                "rows": str(len(TABLE_CELLS)),
                "cols": str(len(TABLE_CELLS[0])),
                "colWidths": "160pt,160pt",
            },
        },
        _textbox("/slide[3]", "alpha-third", A_THIRD, x="40pt", y="40pt"),
    ]


def _beta_commands() -> list[dict[str, Any]]:
    """Two pages whose first page repeats Alpha's object creation order.

    OfficeCLI hands out object ids in creation order, so page 1 of both decks
    reports ``/slide[1]/shape[@id=100000]`` and ``/slide[1]/shape[@id=100001]``
    for objects that are not the same object at all.
    """
    return [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        _slide("beta-1"),
        _slide("beta-2"),
        _textbox("/slide[1]", "beta-title", B_TITLE, x="40pt", y="40pt"),
        _rect("/slide[1]", "beta-box", x="40pt", y="120pt", fill=B_BOX_FILL),
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "picture",
            "props": {
                "name": "beta-picture",
                "x": "400pt",
                "y": "120pt",
                "width": "80pt",
                "height": "60pt",
                "src": _PICTURE_URI,
            },
        },
        _textbox("/slide[2]", "beta-second", B_SECOND, x="40pt", y="40pt"),
    ]


def _group_commands() -> list[dict[str, Any]]:
    """One page whose container owns a shape and a connector it cannot represent.

    A group's own shape carries no paint, so this page is also the fixture for
    the container-representation boundary: the container is classified, its
    owned children are recorded as owned by it, and the run blocks instead of
    publishing a representation it could not produce.  The children sit outside
    the group's own rectangle, and no child space is declared that could bring
    them inside it, so no reading of the source reconciles them.
    """
    return [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        _slide("group-1"),
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "group",
            "props": {
                "name": "cluster",
                "x": f"{GROUP_BOX_PT[0]}pt",
                "y": f"{GROUP_BOX_PT[1]}pt",
                "width": f"{GROUP_BOX_PT[2]}pt",
                "height": f"{GROUP_BOX_PT[3]}pt",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]/group[1]",
            "type": "shape",
            "props": {
                "name": GROUP_CHILD_NAME,
                "geometry": "rect",
                "x": f"{GROUP_CHILD_BOX_PT[0]}pt",
                "y": f"{GROUP_CHILD_BOX_PT[1]}pt",
                "width": f"{GROUP_CHILD_BOX_PT[2]}pt",
                "height": f"{GROUP_CHILD_BOX_PT[3]}pt",
                "fill": "#CC3366",
                "line": "none",
            },
        },
        {
            "command": "add",
            "parent": "/slide[1]/group[1]",
            "type": "connector",
            "props": {
                "name": GROUP_CONNECTOR_NAME,
                "x": f"{GROUP_CONNECTOR_BOX_PT[0]}pt",
                "y": f"{GROUP_CONNECTOR_BOX_PT[1]}pt",
                "width": f"{GROUP_CONNECTOR_BOX_PT[2]}pt",
                "height": f"{GROUP_CONNECTOR_BOX_PT[3]}pt",
                "line": "#222222",
            },
        },
        _textbox("/slide[1]", "group-sibling", GROUP_SIBLING_TEXT, x="40pt", y="40pt"),
    ]


def _four_three_commands() -> list[dict[str, Any]]:
    """One page on a 4:3 slide, so the Author canvas cannot be derived from it."""
    return [
        {
            "command": "set",
            "path": "/",
            "props": {"slideWidth": "720pt", "slideHeight": "540pt"},
        },
        _slide("four-three-1"),
        _textbox("/slide[1]", "four-three-title", "Four three page", x="40pt", y="40pt"),
    ]


def _build_deck(
    path: Path,
    commands: Sequence[Mapping[str, Any]],
    *,
    cells: Sequence[tuple[str, str]] = (),
) -> Path:
    """Create one synthetic deck through OfficeCLI, then fill any table cells.

    OfficeCLI's table ``add`` does not carry cell text, so each cell is set by
    its own addressing command -- the same two-step the V0.4.1 fixture uses.
    """
    _officecli("create", str(path))
    _officecli(
        "batch", str(path), "--commands", json.dumps(commands, ensure_ascii=False)
    )
    for address, value in cells:
        _officecli("set", str(path), address, "--prop", f"text={value}")
    _officecli("close", str(path))
    return path


def _table_cells(deck_page: int, table_name: str) -> list[tuple[str, str]]:
    return [
        (
            f"/slide[{deck_page}]/table[@name={table_name}]"
            f"/tr[{row_index}]/tc[{column_index}]",
            value,
        )
        for row_index, row in enumerate(TABLE_CELLS, start=1)
        for column_index, value in enumerate(row, start=1)
    ]


@pytest.fixture(scope="session")
def decks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build the synthetic decks once, and remember their bytes.

    ``hashes`` is captured at fixture-build time so "the sources are byte
    identical after the run" can be asserted against the bytes that existed
    before the projection ever touched them.
    """
    directory = tmp_path_factory.mktemp("v042-fixtures")
    alpha = _build_deck(
        directory / "alpha.pptx",
        _alpha_commands(),
        cells=_table_cells(2, "alpha-table"),
    )
    beta = _build_deck(directory / "beta.pptx", _beta_commands())
    group = _build_deck(directory / "group.pptx", _group_commands())
    four_three = _build_deck(directory / "four-three.pptx", _four_three_commands())
    corrupt = directory / "corrupt.pptx"
    corrupt.write_bytes(b"this is not a PowerPoint package at all\n" * 16)
    paths = {
        DECK_A: alpha,
        DECK_B: beta,
        DECK_GROUP: group,
        DECK_FOUR_THREE: four_three,
        DECK_CORRUPT: corrupt,
    }
    return {**paths, "hashes": {str(path): _sha256(path) for path in paths.values()}}


@pytest.fixture(scope="session")
def multi_run(decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory) -> ProjectionResult:
    """One published run selecting four pages from two decks, out of order."""
    directory = tmp_path_factory.mktemp("v042-multi")
    selection = PageSelection(
        [SelectedPage(decks[name], page) for name, page in MULTI_SELECTION]
    )
    return project_pptx_to_author_html(
        selection, directory / "multi.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def pair_run(decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory) -> ProjectionResult:
    """A published two-page run: Alpha page 2 (proxy + table) and Beta page 1."""
    directory = tmp_path_factory.mktemp("v042-pair")
    selection = PageSelection(
        [SelectedPage(decks[DECK_A], 2), SelectedPage(decks[DECK_B], 1)]
    )
    return project_pptx_to_author_html(
        selection, directory / "pair.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def legacy_run(decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory) -> ProjectionResult:
    """The V0.4.1 call shape: one path, one slide-number list, one destination."""
    directory = tmp_path_factory.mktemp("v042-legacy")
    return project_pptx_to_author_html(
        decks[DECK_B], [2], directory / "legacy.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def blocked_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> tuple[ProjectionBlockedError, Path]:
    """The group page: a container with no representation of its own is blocking.

    Its children sit outside its rectangle and nothing declares a child space
    that could bring them inside, so the measured reconstruction fails and the
    run publishes nothing.  The failure carries the ledger, so the ownership
    facts of a page the run refused to publish are still auditable through the
    seam.
    """
    directory = tmp_path_factory.mktemp("v042-group")
    target = directory / "group.html"
    with pytest.raises(ProjectionBlockedError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_GROUP], 1)]),
            target,
            proxy_dir=directory / "proxies",
        )
    return error.value, target


@pytest.fixture(scope="session")
def rebuilt(
    pair_run: ProjectionResult, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Any, Path]:
    """Rebuild the projected pair through the existing New Deck path."""
    directory = tmp_path_factory.mktemp("v042-rebuilt")
    output = directory / "rebuilt.pptx"
    built = asyncio.run(build_author_html(str(pair_run.html_path), str(output)))
    return built, output


# ---------------------------------------------------------------------------
# Helpers that read the published artifacts, never the projector's internals
# ---------------------------------------------------------------------------


def _html(result: ProjectionResult) -> str:
    assert result.output_html is not None
    return Path(result.output_html).read_text(encoding="utf-8")


def _named(
    result: ProjectionResult, name: str, *, page: int | None = None
) -> DispositionLedgerEntry:
    matches = [
        item
        for item in result.ledger
        if item.source_name == name and (page is None or item.source_page == page)
    ]
    assert len(matches) == 1, (
        f"expected exactly one ledger entry named {name!r}"
        f"{'' if page is None else f' on page {page}'}; got "
        f"{[item.as_dict() for item in matches]}"
    )
    return matches[0]


def _section_heads(result: ProjectionResult) -> list[dict[str, str]]:
    """Return each emitted page's section attributes, in document order."""
    heads: list[dict[str, str]] = []
    for chunk in _html(result).split('<section class="slide"')[1:]:
        head = chunk.split(">", 1)[0]
        heads.append(dict(re.findall(r'([a-z-]+)="([^"]*)"', head)))
    return heads


def _selection_pairs(result: ProjectionResult) -> list[tuple[str, int]]:
    """Return the caller's selection as ``(source path, page)`` pairs."""
    return [(page.source_pptx, page.source_slide) for page in result.selection]


def _fresh_target(tmp_path: Path, name: str = "out.html") -> Path:
    directory = tmp_path / "out"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


# ---------------------------------------------------------------------------
# Criterion 1: one run, several decks, exactly the caller's order
# ---------------------------------------------------------------------------


def test_one_run_projects_pages_from_two_decks_in_selection_order(
    multi_run: ProjectionResult,
) -> None:
    """The emitted pages are the selection, in the selection's own order."""
    assert multi_run.published is True
    assert len(multi_run.sources) == 2
    assert [slide.source_key for slide in multi_run.slides] == [
        "src1",
        "src2",
        "src1",
        "src2",
    ]
    assert [slide.source_slide for slide in multi_run.slides] == [2, 3, 1, 1]
    assert [slide.output_slide for slide in multi_run.slides] == [1, 2, 3, 4]
    assert [slide.source_file for slide in multi_run.slides] == [
        "beta.pptx",
        "alpha.pptx",
        "beta.pptx",
        "alpha.pptx",
    ]


def test_the_published_document_repeats_the_selection_order(
    multi_run: ProjectionResult,
) -> None:
    """The DOM's section order is the selection order, not the decks' order."""
    heads = _section_heads(multi_run)
    assert [head["data-source-key"] for head in heads] == [
        "src1",
        "src2",
        "src1",
        "src2",
    ]
    assert [head["data-source-slide"] for head in heads] == ["2", "3", "1", "1"]
    assert [head["data-source-name"] for head in heads] == [
        "beta.pptx",
        "alpha.pptx",
        "beta.pptx",
        "alpha.pptx",
    ]
    # ``data-slide-number`` is the emitted position, which is what the New Deck
    # compiler numbers by; the source page number stays beside it.
    assert [head["data-slide-number"] for head in heads] == ["1", "2", "3", "4"]


def test_pages_of_one_deck_selected_out_of_order_keep_the_caller_order(
    multi_run: ProjectionResult,
) -> None:
    """Beta page 2 precedes Beta page 1 because the caller listed it first."""
    beta_pages = [
        slide.source_slide for slide in multi_run.slides if slide.source_file == "beta.pptx"
    ]
    assert beta_pages == [2, 1]
    heads = [
        head for head in _section_heads(multi_run) if head["data-source-name"] == "beta.pptx"
    ]
    assert [head["data-source-slide"] for head in heads] == ["2", "1"]
    assert [head["data-slide-number"] for head in heads] == ["1", "3"]
    # Two pages of one deck are two selected pages, not a duplicate, so the deck
    # is read once and contributes both in the caller's order.
    beta = next(item for item in multi_run.sources if item.source_path.endswith("beta.pptx"))
    assert beta.selected_pages == (2, 1)
    assert beta.slide_count == 2


def test_every_selected_page_is_emitted_exactly_once(
    multi_run: ProjectionResult,
) -> None:
    """One page in, one page out -- and nothing else."""
    assert _html(multi_run).count('class="slide"') == len(MULTI_SELECTION)
    emitted = {
        (slide.source_path, slide.source_slide) for slide in multi_run.slides
    }
    assert emitted == set(_selection_pairs(multi_run))
    assert len(emitted) == len(multi_run.slides)


# ---------------------------------------------------------------------------
# Criterion 2: stable structured diagnostics for a bad selection
# ---------------------------------------------------------------------------


def test_a_duplicate_selection_is_a_stable_structured_diagnostic(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """Selecting one source page twice is refused before anything is read."""
    target = _fresh_target(tmp_path)
    selection = PageSelection(
        [
            SelectedPage(decks[DECK_B], 1),
            SelectedPage(decks[DECK_A], 1),
            SelectedPage(decks[DECK_B], 1),
        ]
    )
    with pytest.raises(ProjectionSelectionError) as error:
        project_pptx_to_author_html(selection, target, proxy_dir=tmp_path / "p")
    assert error.value.code == "duplicate_selection"
    payload = error.value.as_dict()
    assert payload["code"] == "duplicate_selection"
    assert payload["blocking"] is True
    assert payload["source_slide"] == 1
    assert str(decks[DECK_B]) in str(error.value)
    assert not target.exists()
    assert not target.with_suffix(".source-map.json").exists()
    assert not target.with_suffix(".projection-report.json").exists()


def test_a_duplicate_selection_is_detected_across_two_spellings_of_one_path(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """Two spellings of one file are one source, so the page is a duplicate."""
    plain = SelectedPage(decks[DECK_A], 2)
    alternate = SelectedPage(Path(str(decks[DECK_A]).replace("\\", "/")), 2)
    assert plain.source_pptx == alternate.source_pptx
    with pytest.raises(ProjectionSelectionError) as error:
        project_pptx_to_author_html(
            PageSelection([plain, alternate]),
            _fresh_target(tmp_path),
            proxy_dir=tmp_path / "p",
        )
    assert error.value.code == "duplicate_selection"


def test_a_missing_source_is_a_stable_structured_diagnostic(tmp_path: Path) -> None:
    """A selected deck that does not exist is named, and nothing is produced."""
    absent = tmp_path / "absent.pptx"
    target = _fresh_target(tmp_path)
    with pytest.raises(ProjectionSelectionError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(absent, 1)]), target, proxy_dir=tmp_path / "p"
        )
    assert error.value.code == "missing_source"
    assert "absent.pptx" in str(error.value)
    assert not target.exists()


def test_a_missing_page_is_a_stable_structured_diagnostic(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """A page the deck does not have is refused, naming the deck it came from."""
    target = _fresh_target(tmp_path)
    with pytest.raises(MissingPageError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 4)]),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert isinstance(error.value, ProjectionError)
    assert error.value.code == "missing_page"
    assert error.value.slide_number == 4
    assert error.value.slide_count == 2
    assert str(decks[DECK_B]) in str(error.value)
    assert error.value.as_dict()["code"] == "missing_page"
    assert not target.exists()


def test_an_unreadable_source_is_a_stable_structured_diagnostic(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """A file that is not a PowerPoint package is reported, not half-projected."""
    target = _fresh_target(tmp_path)
    with pytest.raises(ProjectionSourceError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_CORRUPT], 1)]),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert error.value.code == "unreadable_source"
    assert "corrupt.pptx" in str(error.value)
    assert error.value.as_dict()["blocking"] is True
    assert not target.exists()


@pytest.mark.parametrize(
    ("label", "build_selection"),
    (
        ("empty", lambda path: PageSelection([])),
        ("page-zero", lambda path: PageSelection([SelectedPage(path, 0)])),
        ("page-text", lambda path: PageSelection([SelectedPage(path, "1")])),
        ("path-alone", lambda path: [path]),
        ("three-tuple", lambda path: [(path, 1, 2)]),
    ),
)
def test_an_invalid_selection_is_a_stable_structured_diagnostic(
    decks: Mapping[str, Any],
    tmp_path: Path,
    label: str,
    build_selection: Any,
) -> None:
    """A selection that does not name source pages fails as an invalid one.

    The selection is built inside the test so an invalid entry is refused by the
    seam under test rather than while the test module is being collected.
    """
    target = _fresh_target(tmp_path, f"{label}.html")
    with pytest.raises(ProjectionSelectionError) as error:
        project_pptx_to_author_html(
            build_selection(decks[DECK_B]), target, proxy_dir=tmp_path / "p"
        )
    assert error.value.code == "invalid_selection", label
    assert not target.exists()


def test_a_call_that_names_no_destination_is_refused(decks: Mapping[str, Any]) -> None:
    """The selection spelling is (selection, output_html); a missing one fails."""
    with pytest.raises(ProjectionSelectionError) as error:
        project_pptx_to_author_html(PageSelection([SelectedPage(decks[DECK_B], 1)]), None)  # type: ignore[arg-type]
    assert error.value.code == "invalid_selection"


def test_a_destination_in_a_missing_directory_is_refused(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """A destination that cannot be staged beside is refused, with a code."""
    target = tmp_path / "nowhere" / "out.html"
    with pytest.raises(ProjectionError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 1)]), target, proxy_dir=tmp_path / "p"
        )
    assert error.value.code == "invalid_output"
    assert not target.exists()


def test_a_deck_that_is_not_the_author_canvas_is_refused_not_rescaled(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """A 4:3 deck is refused rather than silently snapped onto 1920x1080."""
    target = _fresh_target(tmp_path, "four-three.html")
    with pytest.raises(ProjectionSourceError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_FOUR_THREE], 1)]),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert error.value.code == "canvas_mismatch"
    assert "720pt" in str(error.value) and "1920px" in str(error.value)
    assert not target.exists()


def test_two_sources_that_disagree_about_slide_size_block_the_run(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """One document, one canvas: disagreeing sources are a blocking diagnostic."""
    target = _fresh_target(tmp_path, "mixed-canvas.html")
    with pytest.raises(ProjectionSourceError) as error:
        project_pptx_to_author_html(
            PageSelection(
                [
                    SelectedPage(decks[DECK_FOUR_THREE], 1),
                    SelectedPage(decks[DECK_B], 1),
                ]
            ),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert error.value.code == "canvas_mismatch"
    assert str(decks[DECK_FOUR_THREE]) in str(error.value)
    assert str(decks[DECK_B]) in str(error.value)
    blocking = [item for item in error.value.diagnostics if item.blocking]
    assert {item.source_key for item in blocking} == {"src1", "src2"}
    assert all("slide." in item.message for item in blocking)
    assert not target.exists()
    assert not target.with_suffix(".source-map.json").exists()


# ---------------------------------------------------------------------------
# Criterion 3: sources are hashed before capture, and every record says where
# it came from
# ---------------------------------------------------------------------------


def test_every_source_is_hashed_before_capture_and_rechecked_before_publication(
    multi_run: ProjectionResult, decks: Mapping[str, Any]
) -> None:
    """Both hash moments are proved by the run's own source records."""
    assert len(multi_run.sources) == 2
    for record in multi_run.sources:
        assert isinstance(record, ProjectionSourceRecord)
        assert record.source_key.startswith("src")
        assert record.hash_verified_before_capture is True
        assert record.hash_verified_before_publication is True
        path = Path(record.source_path)
        assert path.is_file()
        assert record.source_sha256 == _sha256(path)
        assert record.source_sha256 == decks["hashes"][str(path)]
        assert record.slide_size_pt == PAGE_SIZE_PT
        assert record.slide_count >= len(record.selected_pages)
    assert {record.source_key for record in multi_run.sources} == {"src1", "src2"}
    # The source map records the same two hash moments and the same pages.
    assert multi_run.source_map["sources"][0]["hash_verified_before_capture"] is True
    assert multi_run.source_map["sources"][0]["selected_pages"] == [2, 1]
    assert multi_run.source_map["schema_version"] == 2


def test_the_primary_source_binding_is_the_first_selected_deck(
    multi_run: ProjectionResult,
) -> None:
    """The V0.4.1 single-source readings stay exact for the first deck."""
    first = multi_run.sources[0]
    assert multi_run.source_path == first.source_path
    assert multi_run.source_sha256 == first.source_sha256
    assert multi_run.source_slide_size_pt == first.slide_size_pt
    assert multi_run.source_slide_count == first.slide_count
    assert multi_run.source_map["source"]["sha256"] == first.source_sha256


def test_each_emitted_page_records_its_source_and_original_page_number(
    multi_run: ProjectionResult,
) -> None:
    """Per-page provenance is emitted, persisted, and matches the selection."""
    records = {record.source_key: record for record in multi_run.sources}
    for index, slide in enumerate(multi_run.slides):
        record = records[slide.source_key]
        assert slide.source_path == record.source_path
        assert slide.source_sha256 == record.source_sha256
        assert slide.source_file == Path(record.source_path).name
        assert slide.output_slide == index + 1
        persisted = multi_run.source_map["slides"][index]
        assert persisted["source_key"] == slide.source_key
        assert persisted["source_slide"] == slide.source_slide
        assert persisted["source_sha256"] == record.source_sha256
        assert persisted["output_slide"] == slide.output_slide
    assert [item["source_slide"] for item in multi_run.projection_report["selected_pages"]] == [
        2,
        3,
        1,
        1,
    ]


def test_every_ledger_entry_records_its_source_fingerprint_and_page(
    multi_run: ProjectionResult,
) -> None:
    """No ledger entry is anonymous: each names its deck, bytes, and page."""
    records = {record.source_key: record for record in multi_run.sources}
    for entry in multi_run.ledger:
        record = records[entry.source_key]
        assert entry.source_path == record.source_path
        assert entry.source_sha256 == record.source_sha256
        assert entry.source_page >= 1
        assert entry.source_page <= record.slide_count
        assert entry.source_object.startswith(f"/slide[{entry.source_page}]/")
        assert len(entry.source_fingerprint) == 64


# ---------------------------------------------------------------------------
# Criterion 4: the source hash is re-checked before publication
# ---------------------------------------------------------------------------


def test_a_source_that_changes_between_capture_and_publication_blocks_the_run(
    decks: Mapping[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that changes mid-run blocks publication and leaves nothing.

    The re-hash is a time-of-check/time-of-use guard, so a black-box test could
    only reach it by racing the run.  The guard's boundary -- the digest of one
    named source -- is therefore faulted deterministically: the second digest a
    path is asked for is the digest of *different* bytes, which is exactly what
    a source rewritten after capture looks like.
    """
    from officecli_html_to_pptx._internal import author_projector

    real = author_projector._sha256_file
    seen: dict[str, int] = {}

    def second_read_is_stale(path: Any) -> str:
        key = str(path)
        seen[key] = seen.get(key, 0) + 1
        return real(path) if seen[key] == 1 else "0" * 64

    monkeypatch.setattr(author_projector, "_sha256_file", second_read_is_stale)
    target = _fresh_target(tmp_path, "stale.html")
    with pytest.raises(SourceChangedError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 2)]),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert error.value.code == "source_changed"
    assert any(item.blocking for item in error.value.diagnostics)
    assert any(item.code == "source_changed" for item in error.value.diagnostics)
    assert str(decks[DECK_B]) in str(error.value)
    assert not target.exists()
    assert not target.with_suffix(".source-map.json").exists()
    assert not target.with_suffix(".projection-report.json").exists()
    assert not list(target.parent.glob(".*projection-*"))


def test_a_changed_source_no_longer_matches_the_published_binding(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """The binding names the bytes that were read, so a change is detectable."""
    changed = tmp_path / "beta-changed.pptx"
    shutil.copy2(decks[DECK_B], changed)
    _officecli("close", str(changed))
    target = tmp_path / "first.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    first = project_pptx_to_author_html(
        PageSelection([SelectedPage(changed, 2)]),
        target,
        proxy_dir=tmp_path / "p1",
    )
    before = _sha256(changed)
    assert first.source_sha256 == before
    assert first.sources[0].source_sha256 == before

    _officecli(
        "batch",
        str(changed),
        "--commands",
        json.dumps(
            [
                {
                    "command": "add",
                    "parent": "/slide[2]",
                    "type": "textbox",
                    "props": {
                        "name": "added-later",
                        "text": "added after the projection",
                        "x": "40pt",
                        "y": "200pt",
                        "width": "300pt",
                        "height": "30pt",
                        "fill": "none",
                        "line": "none",
                    },
                }
            ]
        ),
    )
    _officecli("close", str(changed))
    after = _sha256(changed)
    assert after != before

    # The published evidence describes bytes that no longer exist, which is
    # exactly the condition that blocks acceptance of a stale result...
    assert first.source_map["source"]["sha256"] == before != after
    assert first.sources[0].source_sha256 != after
    # ... and a new run binds the new bytes instead of inheriting the old ones.
    second = project_pptx_to_author_html(
        PageSelection([SelectedPage(changed, 2)]),
        tmp_path / "second.html",
        proxy_dir=tmp_path / "p2",
    )
    assert second.source_sha256 == after
    assert second.html_sha256 != first.html_sha256


# ---------------------------------------------------------------------------
# Criteria 5 and 6: one ledger entry per slide-owned source object, with the
# whole classification on it
# ---------------------------------------------------------------------------


def test_every_slide_owned_source_object_has_exactly_one_ledger_entry(
    multi_run: ProjectionResult,
) -> None:
    """No selected object is missing from the ledger, and none appears twice."""
    identities = [entry.identity for entry in multi_run.ledger]
    assert len(identities) == len(set(identities))
    assert len(multi_run.ledger) == multi_run.projection_report["counts"]["source_objects"]
    for entry in multi_run.ledger:
        assert entry.source_object, entry.as_dict()
        assert entry.source_kind
        assert entry.disposition in DISPOSITIONS
        assert entry.projected_kind
    # Every selected page contributes at least one object, and every object
    # belongs to a selected page.
    selected = {
        (slide.source_path, slide.source_slide) for slide in multi_run.slides
    }
    ledger_pages = {(entry.source_path, entry.source_page) for entry in multi_run.ledger}
    assert ledger_pages == selected


def test_unselected_pages_of_a_partly_selected_deck_are_never_classified(
    multi_run: ProjectionResult,
) -> None:
    """Alpha has three pages and two are selected; the third is not in the run."""
    alpha = next(item for item in multi_run.sources if item.source_path.endswith("alpha.pptx"))
    assert alpha.slide_count == 3
    assert alpha.selected_pages == (3, 1)
    assert 2 not in alpha.selected_pages
    assert 2 not in {
        entry.source_page for entry in multi_run.ledger if entry.source_path.endswith("alpha.pptx")
    }
    assert all(
        item["source_slide"] != 2
        for item in multi_run.source_map["slides"]
        if item["source_path"].endswith("alpha.pptx")
    )
    assert A_SECOND not in _html(multi_run)


def test_the_ledger_records_every_required_field_for_every_entry(
    pair_run: ProjectionResult,
) -> None:
    """Identity, ownership, projected kind, emitted identity, disposition, reason."""
    records = {record.source_key: record for record in pair_run.sources}
    element_ids = {item.html_id for item in pair_run.objects}
    for entry in pair_run.ledger:
        payload = entry.as_dict()
        for field in (
            "source_key",
            "source_path",
            "source_sha256",
            "source_page",
            "source_object",
            "source_kind",
            "source_name",
            "source_fingerprint",
            "owner",
            "owner_kind",
            "represented_by_container",
            "projected_kind",
            "html_id",
            "emitted_ordinal",
            "emitted_name",
            "disposition",
            "reason_code",
            "reason",
            "emitted",
            "blocking",
        ):
            assert field in payload, (field, payload)
        assert entry.source_path == records[entry.source_key].source_path
        assert entry.source_sha256 == records[entry.source_key].source_sha256
        assert entry.disposition in DISPOSITIONS
        assert entry.represented_by_container is (entry.owner is not None)
        if entry.html_id is not None:
            # The object has an element of its own, so it carries the emitted
            # identity the New Deck compiler will give that slot.
            assert entry.html_id in element_ids
            assert entry.emitted_ordinal and entry.emitted_ordinal >= 1
            assert entry.emitted_name.startswith("slide-")
            assert entry.emitted is True
        else:
            assert entry.emitted_ordinal is None
            assert entry.emitted_name is None
            assert entry.emitted is False
            assert entry.represented_by_container is True


def test_a_non_canonical_entry_carries_a_machine_readable_reason_code(
    pair_run: ProjectionResult,
) -> None:
    """Every non-canonical disposition explains itself; a canonical one does not."""
    non_canonical = [
        entry for entry in pair_run.ledger if entry.disposition != DISPOSITION_CANONICAL
    ]
    assert non_canonical, "the fixture must exercise at least one locked object"
    for entry in non_canonical:
        assert entry.reason_code in REASON_CODES, entry.as_dict()
        assert entry.reason
    for entry in pair_run.ledger:
        if entry.disposition == DISPOSITION_CANONICAL:
            assert entry.reason_code is None, entry.as_dict()
            assert entry.reason is None, entry.as_dict()
    chevron = _named(pair_run, "alpha-chevron")
    assert chevron.disposition == DISPOSITION_LOCKED
    assert chevron.reason_code == "geometry_not_canonical"
    assert "chevron" in (chevron.reason or "")
    assert chevron.projected_kind == "image"


def test_the_disposition_vocabulary_is_the_existing_one(
    multi_run: ProjectionResult, pair_run: ProjectionResult
) -> None:
    """The V0.4.1 vocabulary is reused, not replaced."""
    assert DISPOSITIONS == (
        DISPOSITION_CANONICAL,
        DISPOSITION_LOCKED,
        DISPOSITION_BASE_ONLY,
        DISPOSITION_UNSUPPORTED,
        DISPOSITION_UNRESOLVED,
    )
    counts = pair_run.disposition_counts()
    assert set(counts) == set(DISPOSITIONS)
    assert sum(counts.values()) == len(pair_run.ledger)
    report_counts = pair_run.projection_report["counts"]
    for name, key in (
        (DISPOSITION_CANONICAL, "canonical_editable"),
        (DISPOSITION_LOCKED, "locked_visual_proxy"),
        (DISPOSITION_BASE_ONLY, "base_only_semantic"),
        (DISPOSITION_UNSUPPORTED, "unsupported"),
        (DISPOSITION_UNRESOLVED, "unresolved"),
    ):
        assert counts[name] == report_counts[key], name
    assert report_counts["native_round_trip"] == counts[DISPOSITION_CANONICAL]
    assert report_counts["source_objects"] == len(pair_run.ledger)
    assert report_counts["dom_objects"] == len(pair_run.objects)
    assert report_counts["emitted_objects"] == len(pair_run.objects)
    assert report_counts["container_owned"] == sum(
        1 for entry in pair_run.ledger if entry.represented_by_container
    )
    assert multi_run.disposition_counts()[DISPOSITION_UNSUPPORTED] == 0
    assert multi_run.disposition_counts()[DISPOSITION_UNRESOLVED] == 0


def test_the_ledger_is_persisted_in_the_evidence_payloads(
    pair_run: ProjectionResult,
) -> None:
    """The ledger travels with the run instead of only in memory."""
    persisted_map = pair_run.source_map["ledger"]
    persisted_report = pair_run.projection_report["ledger"]
    assert [item["source_object"] for item in persisted_map] == [
        entry.source_object for entry in pair_run.ledger
    ]
    assert persisted_map == persisted_report
    for item in persisted_map:
        assert item["source_key"] and item["source_sha256"] and item["disposition"]
    on_disk = json.loads(Path(pair_run.source_map_path).read_text(encoding="utf-8"))
    assert on_disk["ledger"] == persisted_map
    assert on_disk["schema_version"] == pair_run.source_map["schema_version"]


# ---------------------------------------------------------------------------
# Criterion 7: the mapping is one-to-one in both directions
# ---------------------------------------------------------------------------


def test_every_emitted_object_maps_to_exactly_one_source_object(
    multi_run: ProjectionResult,
) -> None:
    """Both directions of the mapping hold, with no ambiguity anywhere."""
    by_id = {item.html_id: item for item in multi_run.objects}
    assert len(by_id) == len(multi_run.objects)
    mapped = {entry.html_id: entry for entry in multi_run.ledger if entry.emitted}
    assert set(mapped) == set(by_id)
    for html_id, item in by_id.items():
        entry = mapped[html_id]
        assert entry.identity == item.identity
        assert entry.disposition == item.disposition
        assert entry.projected_kind == item.projected_kind
        assert entry.source_kind == item.source_kind
        # One source object, one emitted object: no second entry claims it.
        assert len([e for e in multi_run.ledger if e.identity == item.identity]) == 1


def test_every_emitted_identity_appears_exactly_once_in_the_document(
    multi_run: ProjectionResult,
) -> None:
    """The document holds one element per emitted object and no duplicates."""
    html = _html(multi_run)
    assert html.count('data-projection-id="') == len(multi_run.objects)
    for item in multi_run.objects:
        # The element's own ``id`` and its ``data-projection-id`` are the two
        # places an emitted identity may appear, and each appears exactly once.
        assert html.count(f' id="{item.html_id}"') == 1, item.html_id
        assert html.count(f'data-projection-id="{item.html_id}"') == 1, item.html_id
        assert html.count(f'data-source-object="{item.source_object}"') >= 1


def test_two_decks_that_report_the_same_source_object_path_stay_distinct(
    multi_run: ProjectionResult,
) -> None:
    """Identical object paths in two decks are two objects, not one ambiguity."""
    by_path: dict[tuple[int, str], set[str]] = {}
    for entry in multi_run.ledger:
        by_path.setdefault((entry.source_page, entry.source_object), set()).add(
            entry.source_key
        )
    shared = {
        key: keys for key, keys in by_path.items() if len(keys) > 1
    }
    assert shared, (
        "the two fixture decks were expected to report the same object path; "
        f"got {sorted(by_path)}"
    )
    for (page, source_object), keys in shared.items():
        entries = [
            entry
            for entry in multi_run.ledger
            if entry.source_page == page and entry.source_object == source_object
        ]
        assert len(entries) == len(keys)
        assert len({entry.identity for entry in entries}) == len(entries)
        assert len({entry.source_sha256 for entry in entries}) == len(entries)
        assert len({entry.html_id for entry in entries}) == len(entries)
        for entry in entries:
            assert f'id="{entry.html_id}"' in _html(multi_run)
    # And the emitted ids are unique document-wide, which is what the source key
    # in the id buys.
    ids = [item.html_id for item in multi_run.objects]
    assert len(ids) == len(set(ids))


def test_the_legacy_single_deck_call_shape_still_projects(
    legacy_run: ProjectionResult,
) -> None:
    """The V0.4.1 spelling keeps working, ledger and all."""
    assert legacy_run.published is True
    assert len(legacy_run.sources) == 1
    assert legacy_run.sources[0].source_key == "src1"
    assert [(page.source_pptx, page.source_slide) for page in legacy_run.selection] == [
        (legacy_run.sources[0].source_path, 2)
    ]
    assert len(legacy_run.ledger) == 1
    entry = legacy_run.ledger[0]
    assert entry.source_page == 2
    assert entry.disposition == DISPOSITION_CANONICAL
    # The V0.4.1 source-object attribute value is unchanged: the source's own
    # OfficeCLI path, with the per-source key beside it rather than inside it.
    assert entry.source_object == "/slide[2]/shape[@id=100003]"
    assert entry.html_id.startswith("src1-s002-o001-")
    assert f'data-source-object="{entry.source_object}"' in _html(legacy_run)
    assert legacy_run.source_map["source"]["sha256"] == legacy_run.source_sha256


# ---------------------------------------------------------------------------
# Criterion 8: a container is represented once; its owned objects are owned
# ---------------------------------------------------------------------------


def test_group_owned_children_are_recorded_as_owned_by_the_container(
    blocked_run: tuple[ProjectionBlockedError, Path],
) -> None:
    """Every child records its container, and that it is not its own object."""
    error, _ = blocked_run
    container = next(
        entry for entry in error.ledger if entry.source_kind == "group"
    )
    children = [entry for entry in error.ledger if entry.represented_by_container]
    assert {entry.source_kind for entry in children} == {"shape", "connector"}
    assert len(children) == 2
    for entry in children:
        assert entry.owner == container.source_object
        assert entry.owner_kind == "group"
        assert entry.represented_by_container is True
        assert entry.html_id is None
        assert entry.projected_kind
        assert entry.reason_code in REASON_CODES
        assert entry.source_object.startswith(f"{container.source_object}/")
    assert {entry.source_name for entry in children} == {
        GROUP_CHILD_NAME,
        GROUP_CONNECTOR_NAME,
    }


def test_group_owned_children_are_not_emitted_as_top_level_objects(
    blocked_run: tuple[ProjectionBlockedError, Path],
) -> None:
    """An owned child never gets an emitted identity of its own."""
    error, _ = blocked_run
    owned_paths = {
        entry.source_object
        for entry in error.ledger
        if entry.represented_by_container
    }
    assert owned_paths
    for entry in error.ledger:
        if entry.source_object in owned_paths and not entry.represented_by_container:
            raise AssertionError(
                f"{entry.source_object} is emitted as a sibling as well: "
                f"{entry.as_dict()}"
            )
    with_elements = [entry for entry in error.ledger if entry.html_id is not None]
    assert {entry.source_name for entry in with_elements} == {"cluster", "group-sibling"}
    assert not owned_paths & {entry.source_object for entry in with_elements}
    # The sibling textbox is still its own object, so ownership is not
    # contagious.
    sibling = next(entry for entry in error.ledger if entry.source_name == "group-sibling")
    assert sibling.disposition == DISPOSITION_CANONICAL
    assert sibling.owner is None
    assert sibling.emitted is True


def test_a_container_without_a_representation_blocks_the_run(
    blocked_run: tuple[ProjectionBlockedError, Path],
) -> None:
    """The container's own failure is a blocking diagnostic, not a silent skip.

    The fixture's children cannot be placed inside its rectangle under any
    reading of the source, so the container carries the container-specific
    reason rather than the generic isolation failure.
    """
    error, target = blocked_run
    assert error.code == "projection_blocked"
    container = next(entry for entry in error.ledger if entry.source_kind == "group")
    assert container.disposition == DISPOSITION_UNSUPPORTED
    assert container.reason_code == "container_child_space_unreconciled"
    # It keeps an identity in the workbench so the failure is reviewable, but it
    # is not part of what the run claims to have emitted.
    assert container.html_id is not None
    assert container.emitted is False
    assert container.blocking is True
    blocking = [item for item in error.diagnostics if item.blocking]
    assert blocking
    assert {item.code for item in blocking} == {
        "container_child_space_unreconciled",
        "unsupported_source_object",
    }
    assert all(item.source_key == "src1" for item in blocking)
    assert not target.exists()


# ---------------------------------------------------------------------------
# Criterion 9: the unchanged author Contract, and the existing New Deck path
# ---------------------------------------------------------------------------


def test_the_multi_source_document_passes_the_author_contract_unchanged(
    multi_run: ProjectionResult, pair_run: ProjectionResult
) -> None:
    """The generated document is Canonical Author HTML by the existing meaning."""
    for result in (multi_run, pair_run):
        report = check_contract(result.html_path, "author")
        assert report.status == "PASS", [item.message for item in report.diagnostics]
        assert report.blocked is False
        assert report.diagnostics == ()
    assert _html(multi_run).count("width: 1920px") == len(multi_run.slides)
    assert multi_run.canvas_px == CANVAS_PX
    assert multi_run.pixels_per_point == pytest.approx(PIXELS_PER_POINT)
    assert pair_run.pixels_per_point == pytest.approx(PIXELS_PER_POINT)


def test_the_projected_pair_rebuilds_through_the_new_deck_path(
    rebuilt: tuple[Any, Path], pair_run: ProjectionResult
) -> None:
    """The projection is useful, not merely inspectable: it compiles."""
    built, output = rebuilt
    assert built.status == "VISUAL_REVIEW_REQUIRED", [
        item.message for item in built.diagnostics
    ]
    assert built.exit_code == 0
    assert output.is_file()
    assert output.stat().st_size > 0
    assert built.data["slide_count"] == len(pair_run.slides) == 2
    assert built.data["author_html"]["sha256"] == pair_run.html_sha256
    evidence = output.parent / f"{output.stem}.evidence"
    assert evidence.is_dir()
    assert (evidence / "result.json").is_file()


def test_the_rebuilt_deck_holds_the_selected_pages_in_selection_order(
    rebuilt: tuple[Any, Path],
) -> None:
    """Independent readback: the rebuilt slides carry the pages in order."""
    _, output = rebuilt
    with zipfile.ZipFile(output) as archive:
        slides = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
        assert len(slides) == 2
        texts = [
            "".join(re.findall(r"<a:t>(.*?)</a:t>", archive.read(name).decode("utf-8"), re.S))
            for name in slides
        ]
    assert A_SECOND in texts[0], texts
    assert B_TITLE in texts[1], texts


# ---------------------------------------------------------------------------
# Criterion 10: collisions and failed runs leave nothing that looks complete
# ---------------------------------------------------------------------------


def test_an_output_collision_on_the_document_is_refused(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """An existing document is never overwritten by a projection run."""
    target = _fresh_target(tmp_path)
    target.write_text("existing author document", encoding="utf-8")
    with pytest.raises(OutputCollisionError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 1)]), target, proxy_dir=tmp_path / "p"
        )
    assert error.value.code == "output_collision"
    assert target.read_text(encoding="utf-8") == "existing author document"


@pytest.mark.parametrize("suffix", (".source-map.json", ".projection-report.json"))
def test_an_output_collision_on_either_evidence_artifact_is_refused(
    decks: Mapping[str, Any], tmp_path: Path, suffix: str
) -> None:
    """Half an evidence pair is a collision too, and it is not overwritten."""
    target = _fresh_target(tmp_path, f"collide{suffix[:6]}.html")
    owned = target.with_suffix(suffix)
    owned.write_text("existing evidence", encoding="utf-8")
    with pytest.raises(OutputCollisionError) as error:
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 1)]), target, proxy_dir=tmp_path / "p"
        )
    assert error.value.code == "output_collision"
    assert owned.read_text(encoding="utf-8") == "existing evidence"
    assert not target.exists()


def test_a_blocked_run_leaves_no_artifact_set(
    blocked_run: tuple[ProjectionBlockedError, Path],
) -> None:
    """A blocked projection publishes neither the document nor its evidence."""
    _, target = blocked_run
    assert not target.exists()
    assert not target.with_suffix(".source-map.json").exists()
    assert not target.with_suffix(".projection-report.json").exists()
    assert not list(target.parent.glob(f".{target.stem}-projection-*"))


def test_a_failed_selection_leaves_no_artifact_set(
    decks: Mapping[str, Any], tmp_path: Path
) -> None:
    """A refused selection leaves no directory, no staging, and no evidence."""
    target = _fresh_target(tmp_path, "refused.html")
    with pytest.raises(ProjectionSelectionError):
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_B], 1), SelectedPage(decks[DECK_B], 1)]),
            target,
            proxy_dir=tmp_path / "p",
        )
    assert sorted(path.name for path in target.parent.iterdir()) == []


# ---------------------------------------------------------------------------
# Criterion 11: the sources are never opened for writing
# ---------------------------------------------------------------------------


def test_sources_are_byte_identical_after_a_successful_run(
    decks: Mapping[str, Any],
    multi_run: ProjectionResult,
    pair_run: ProjectionResult,
    legacy_run: ProjectionResult,
) -> None:
    """Successful runs leave every source exactly as it was."""
    for name in (DECK_A, DECK_B):
        path = decks[name]
        assert _sha256(path) == decks["hashes"][str(path)], name
    for result in (multi_run, pair_run, legacy_run):
        for record in result.sources:
            assert _sha256(Path(record.source_path)) == record.source_sha256


def test_sources_are_byte_identical_after_a_failed_run(
    decks: Mapping[str, Any],
    blocked_run: tuple[ProjectionBlockedError, Path],
    tmp_path: Path,
) -> None:
    """A blocked run and an unreadable run leave every source as it was."""
    with pytest.raises(ProjectionSourceError):
        project_pptx_to_author_html(
            PageSelection([SelectedPage(decks[DECK_CORRUPT], 1)]),
            _fresh_target(tmp_path, "corrupt.html"),
            proxy_dir=tmp_path / "p",
        )
    for name, path in decks.items():
        if name == "hashes":
            continue
        assert _sha256(path) == decks["hashes"][str(path)], name


# ---------------------------------------------------------------------------
# Criteria 12 and 13: one hidden seam, and no new public surface
# ---------------------------------------------------------------------------


def test_the_seam_remains_the_only_caller_facing_projection_entry_point() -> None:
    """One exported function, two accepted spellings, no second entry point."""
    import officecli_html_to_pptx

    exported = [name for name in officecli_html_to_pptx.__all__ if name.startswith("project")]
    assert exported == ["project_pptx_to_author_html"]
    parameters = list(inspect.signature(project_pptx_to_author_html).parameters)
    assert parameters == ["source", "source_slide_numbers", "output_html", "proxy_dir"]
    for absent in (
        "project_pptx_to_author_html_whole_deck",
        "project_all_slides",
        "select_representative_pages",
        "capture_presentation",
    ):
        assert not hasattr(officecli_html_to_pptx, absent), absent


def test_no_public_command_manifest_entry_or_version_change_is_added() -> None:
    """The hidden slice stays hidden: same commands, scope, and product version."""
    from officecli_html_to_pptx import get_capabilities

    envelope = get_capabilities()
    capabilities = envelope.data
    assert envelope.as_dict()["product"] == {
        "name": "officecli-html-to-pptx",
        "version": PRODUCT_VERSION,
    }
    assert PUBLIC_COMMANDS == (
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
        "workbench",
    )
    assert capabilities["commands"] == list(PUBLIC_COMMANDS)
    assert PRODUCT_VERSION == "0.6.2"
    # The declared scope is unchanged too: this seam adds no capability claim,
    # and it still does not edit an existing deck.
    assert capabilities["scope"] == {
        "creates_new_pptx": True,
        "officehtml_import": False,
        "existing_pptx_editing": False,
    }
    declared_names = set(capabilities) | set(capabilities["scope"])
    assert not any(
        token in name for name in declared_names for token in ("project", "ledger")
    ), declared_names


def test_the_projection_reports_that_it_is_not_a_whole_slide_screenshot_fallback(
    multi_run: ProjectionResult, pair_run: ProjectionResult
) -> None:
    """The declaration the V0.4.1 probe made still holds for a multi-deck run."""
    for result in (multi_run, pair_run):
        assert result.projection_report["whole_slide_screenshot_fallback"] is False
        assert result.published is True
        assert result.blocking is False
        assert [slide.output_slide for slide in result.slides] == list(
            range(1, len(result.slides) + 1)
        )


# ---------------------------------------------------------------------------
# The paragraph layouts the canonical orthography cannot carry
# ---------------------------------------------------------------------------


def _captured_body(*paragraphs: CapturedParagraph) -> CapturedObject:
    """Return a captured text body holding these paragraphs, and nothing else."""
    text = "\n".join(paragraph.text for paragraph in paragraphs)
    return CapturedObject(
        source_slide=1,
        source_object="/slide[1]/shape[@id=1]",
        source_kind="textbox",
        name="body",
        officecli_id=1,
        z_order=1,
        bounds_pt=(0.0, 0.0, 100.0, 50.0),
        geometry="rect",
        fill=None,
        line_color=None,
        line_width_pt=0.0,
        rotation_deg=0.0,
        explicit_properties=frozenset(),
        base_only=(),
        opaque_properties={},
        raw_format={},
        text=text,
        paragraphs=tuple(paragraphs),
    )


def _paragraph(
    text: str, *, before: float = 0.0, after: float = 0.0, runs: int = 1
) -> CapturedParagraph:
    return CapturedParagraph(
        text=text,
        align="left",
        line_spacing=None,
        space_before_pt=before,
        space_after_pt=after,
        direction="ltr",
        bullet="none",
        level=0,
        runs=tuple(
            CapturedRun(
                text=text,
                font_family="Arial",
                font_size_pt=11.0,
                bold=False,
                italic=False,
                underline="none",
                color="#000000",
            )
            for _ in range(runs)
        ),
    )


def test_a_body_that_declares_paragraph_spacing_is_not_canonical() -> None:
    """The canonical orthography carries no inter-paragraph spacing.

    A source paragraph the deck spaces 6pt from the one above it is painted lower
    than the same paragraph drawn flush, and the projection has no surface to carry
    the gap: the Author Contract emits paragraph spacing for a table cell's
    paragraphs, because a cell folds its child paragraphs into one body.  So the
    object is classified base-only and represented by its own object-local paint,
    which keeps the page faithful at the cost of editability -- and never by
    comparing a representative value that hides the difference.
    """
    body = _captured_body(
        _paragraph("first", after=6.0),
        _paragraph("second"),
    )
    reason = projector._paragraph_layout_reason(body)
    assert reason is not None
    assert "paragraph spacing" in reason
    assert "space after 6pt" in reason
    disposition, message, _, code = projector._classify(body)
    assert disposition == DISPOSITION_BASE_ONLY
    assert code == "text_paragraph_layout_base_only"
    assert code in REASON_CODES
    assert message == reason


def test_a_body_with_an_empty_paragraph_is_not_canonical() -> None:
    """An empty paragraph is a line, and the rebuild sizes it from the wrong run.

    OfficeCLI gives the rebuilt blank line the *preceding* paragraph's first run
    formatting -- a 20pt blank line after a 20pt heading where the source paints
    its body's 11pt one -- which makes the rebuilt body taller than the source and
    can materially worsen an overflow the source already has.  The compiler writes
    no per-paragraph size, so the height is not writable either.
    """
    body = _captured_body(
        _paragraph("first"),
        _paragraph("", runs=0),
        _paragraph("third"),
    )
    reason = projector._paragraph_layout_reason(body)
    assert reason is not None
    assert "empty paragraph" in reason
    assert projector._classify(body)[3] == "text_paragraph_layout_base_only"


def test_a_body_whose_paragraph_layout_is_writable_stays_canonical() -> None:
    """And the negative direction, so the rule is a rule and not a blanket refusal.

    Three paragraphs, one run each, no spacing and no empty line: everything the
    surface carries, so the object is canonical.  The rule keys on the two shapes
    that cannot be written and on nothing else.
    """
    body = _captured_body(
        _paragraph("first"),
        _paragraph("second"),
        _paragraph("third"),
    )
    assert projector._paragraph_layout_reason(body) is None
    assert projector._classify(body)[0] == DISPOSITION_CANONICAL


def test_a_single_paragraph_body_is_never_affected_by_the_rule() -> None:
    """One paragraph is not a paragraph *layout*, whatever it declares."""
    body = _captured_body(_paragraph("only", after=12.0))
    assert projector._paragraph_layout_reason(body) is None
    assert projector._classify(body)[0] == DISPOSITION_CANONICAL
