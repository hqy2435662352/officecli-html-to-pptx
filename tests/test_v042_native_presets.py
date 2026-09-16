"""V0.4.2 native ellipse and rightArrow projection tests.

The external seam under test is the same one the V0.4.1 and #15 files drive::

    project_pptx_to_author_html(deck, [page], output_html, proxy_dir=...)
        -> one Canonical Author HTML document
         + the per-object disposition ledger
         + source map + projection report
         + structured diagnostics

and the existing New Deck path that rebuilds it::

    build_author_html(output_html, rebuilt.pptx)

Everything here is observed through those two public entry points and through
independent OfficeCLI queries on the rebuilt deck.  No private reader call,
OfficeCLI command shape, or internal DTO is frozen by this file.

The fixtures are small synthetic decks built through OfficeCLI.  Two things the
fixtures need are not reachable through an OfficeCLI verb and are therefore
declared directly in the package:

* an ellipse's and a right arrow's native preset is *declared* on the emitted
  object, because no CSS declaration means "ellipse" the way ``border-radius``
  means "roundRect"; and
* a group's own child coordinate space (``a:chOff``/``a:chExt``) has no
  ``officecli set`` property, so the group fixtures declare it in the slide part
  exactly as PowerPoint writes it on every group it creates.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Mapping, Sequence
import zipfile
from xml.etree import ElementTree

import pytest

from officecli_html_to_pptx import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_UNRESOLVED,
    DISPOSITION_UNSUPPORTED,
    REASON_CODES,
    ProjectionBlockedError,
    ProjectionResult,
    build_author_html,
    project_pptx_to_author_html,
)
from officecli_html_to_pptx._internal import author_projector as projector
from officecli_html_to_pptx.contract import check_contract

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V0.4.2 native-preset tests",
)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EMU_PER_POINT = 12_700

CANVAS_PX = (1920.0, 1080.0)
PIXELS_PER_POINT = 2.0
PROXY_GUARD_PX = 2

# ---------------------------------------------------------------------------
# Fixture literals.  Every expectation below is written from these, never from
# the projector's own output.
# ---------------------------------------------------------------------------

SOLID_ELLIPSE = "solid-ellipse"
SOLID_ELLIPSE_BOX = (40.0, 40.0, 160.0, 80.0)
SOLID_ELLIPSE_FILL = "#D96666"

SOLID_ARROW = "solid-arrow"
SOLID_ARROW_BOX = (40.0, 160.0, 180.0, 60.0)
SOLID_ARROW_FILL = "#EE822F"
SOLID_ARROW_LINE = "#333333"
SOLID_ARROW_LINE_PT = 1.5

LABELLED_ELLIPSE = "labelled-ellipse"
LABELLED_ELLIPSE_BOX = (40.0, 280.0, 200.0, 90.0)
LABELLED_ELLIPSE_FILL = "#4874CB"
LABELLED_ELLIPSE_TEXT = "Ellipse caption 中文"
LABELLED_TEXT_SIZE_PT = 18.0
LABELLED_TEXT_FONT = "Arial"
LABELLED_TEXT_COLOR = "#FFFFFF"

LABELLED_ARROW = "labelled-arrow"
LABELLED_ARROW_BOX = (40.0, 400.0, 220.0, 60.0)
LABELLED_ARROW_FILL = "#75BD42"
LABELLED_ARROW_TEXT = "Arrow caption"

TRANSLUCENT_ELLIPSE = "translucent-ellipse"
TRANSLUCENT_BOX = (300.0, 40.0, 140.0, 70.0)
TRANSLUCENT_FILL = "#75BD42"
TRANSLUCENT_OPACITY = 0.5

ROTATED_ELLIPSE = "rotated-ellipse"
ROTATED_BOX = (300.0, 160.0, 160.0, 80.0)
ROTATED_DEGREES = 30.0
ROTATED_FILL = "#4874CB"

PLAIN_RECT = "plain-rect"
PLAIN_RECT_BOX = (300.0, 300.0, 200.0, 80.0)
PLAIN_RECT_FILL = "#3366CC"
ROUNDED_RECT = "rounded-rect"
ROUNDED_RECT_BOX = (300.0, 400.0, 200.0, 90.0)
ROUNDED_RECT_FILL = "#F5F5F5"
ROUNDED_RECT_LINE = "#D9D9D9"

# The overlay probe: a filled ellipse whose rectangle carries three independent
# textboxes, which is the arrangement a composited raster crop cannot represent
# without capturing its neighbours.
OVERLAY_ELLIPSE = "overlay-ellipse"
OVERLAY_BOX = (620.0, 300.0, 120.0, 120.0)
OVERLAY_FILL = "#C00000"
OVERLAY_LINES = ("In 2026", "9.50", "Million/USD")
OVERLAY_TEXT_TOP_PT = (315.0, 345.0, 375.0)

# Boundary deck: every way a simple preset fails to be canonical-editable.
THEME_FILL_ELLIPSE = "theme-fill-ellipse"
THEME_FILL_BOX = (40.0, 40.0, 140.0, 70.0)
THEME_LINE_ARROW = "theme-line-arrow"
THEME_LINE_BOX = (40.0, 160.0, 140.0, 60.0)
THEME_LINE_FILL = "#EE822F"
CHEVRON_SHAPE = "chevron-shape"
CHEVRON_BOX = (40.0, 260.0, 140.0, 60.0)
THEME_TEXT_ELLIPSE = "theme-text-ellipse"
THEME_TEXT_BOX = (40.0, 360.0, 220.0, 70.0)
THEME_TEXT_FILL = "#4874CB"
THEME_TEXT = "Theme resolved caption"
MIRRORED_ARROW = "mirrored-arrow"
MIRRORED_BOX = (300.0, 40.0, 160.0, 60.0)
ROTATED_RECT = "rotated-rect"
ROTATED_RECT_BOX = (300.0, 160.0, 160.0, 70.0)
BOUNDARY_CONTROL_ELLIPSE = "control-ellipse"
BOUNDARY_CONTROL_BOX = (300.0, 300.0, 140.0, 70.0)

# Container deck: one group that declares its own child coordinate space, one
# sibling textbox outside it, and one intruder textbox painted inside the
# container's rectangle.
GROUP_NAME = "cluster"
GROUP_BOX = (200.0, 200.0, 200.0, 120.0)
GROUP_CHILD_BOX = "inner-box"
GROUP_CHILD_BOX_FILL = "#CC3366"
GROUP_CHILD_LINK = "inner-link"
GROUP_CHILD_LINK_COLOR = "#222222"
GROUP_SIBLING = "group-sibling"
GROUP_SIBLING_TEXT = "Ungrouped sibling text"
GROUP_INTRUDER = "intruder-text"
GROUP_INTRUDER_TEXT = "Intruder"
GROUP_INTRUDER_COLOR = "#00AA00"
GROUP_INTRUDER_BOX = (260.0, 230.0, 120.0, 30.0)
# The child rectangles as authored inside the group's own child space, and the
# child space those rectangles are declared to live in.
GROUP_CHILD_RECT = (210.0, 210.0, 80.0, 40.0)
GROUP_CHILD_LINK_RECT = (210.0, 260.0, 80.0, 40.0)
GROUP_CHILD_OFFSET_PT = (210.0, 210.0)
GROUP_CHILD_EXTENT_PT = (80.0, 90.0)
# The unplaceable deck: the same group with its children authored *outside* its
# own rectangle, plus a declared child space whose transform throws them further
# out again.  Neither reading of the source can put their paint inside the
# container, so the container is reported rather than represented.
UNPLACEABLE_CHILD_RECT = (600.0, 300.0, 80.0, 40.0)
UNPLACEABLE_LINK_RECT = (600.0, 380.0, 80.0, 40.0)
UNPLACEABLE_CHILD_OFFSET_PT = (600.0, 300.0)
UNPLACEABLE_CHILD_EXTENT_PT = (40.0, 20.0)

# Connector deck: one standalone connector with a textbox painted over it.
STANDALONE_CONNECTOR = "free-link"
CONNECTOR_BOX = (100.0, 100.0, 200.0, 60.0)
CONNECTOR_COLOR = "#1166CC"
CONNECTOR_OVERLAY = "over-text"
CONNECTOR_OVERLAY_TEXT = "Overlapping label"
CONNECTOR_OVERLAY_COLOR = "#00AA00"
CONNECTOR_OVERLAY_BOX = (140.0, 110.0, 160.0, 30.0)

PRESET_DECK = "presets"
BOUNDARY_DECK = "boundary"
CONTAINER_DECK = "container"
UNRECONCILED_DECK = "unreconciled-container"
UNDECLARED_DECK = "undeclared-container"
HOLLOW_DECK = "hollow-container"
CONNECTOR_DECK = "connector"

# The two readings of a container's children that the projection tries, in
# order, and that a refusal names.
DECLARED_PLACEMENT = "declared"
REPORTED_PLACEMENT = "reported"

# A group whose only child paints nothing at all, so its reconstruction is bare
# background.  That is a failed representation, never a blank proxy.
HOLLOW_GROUP = "hollow"
HOLLOW_CHILD = "ghost-box"

SLIDE_PART = "ppt/slides/slide1.xml"


# ---------------------------------------------------------------------------
# OfficeCLI plumbing.  Same retry discipline as the V0.4.1 and #15 probes: a
# command that names a document first releases any resident handle on it,
# because a stale resident is the one failure a blind retry cannot clear.
# ---------------------------------------------------------------------------


def _officecli(*args: str, attempts: int = 6) -> str:
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


def _build_deck(path: Path, commands: Sequence[Mapping[str, Any]]) -> Path:
    _officecli("create", str(path))
    _officecli(
        "batch", str(path), "--commands", json.dumps(commands, ensure_ascii=False)
    )
    _officecli("close", str(path))
    return path


def _shape(
    name: str,
    geometry: str,
    box: Sequence[float],
    *,
    parent: str = "/slide[1]",
    **props: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "geometry": geometry,
        "x": f"{box[0]}pt",
        "y": f"{box[1]}pt",
        "width": f"{box[2]}pt",
        "height": f"{box[3]}pt",
    }
    payload.update(props)
    return {"command": "add", "parent": parent, "type": "shape", "props": payload}


def _textbox(
    name: str, text: str, box: Sequence[float], **props: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "text": text,
        "x": f"{box[0]}pt",
        "y": f"{box[1]}pt",
        "width": f"{box[2]}pt",
        "height": f"{box[3]}pt",
        "size": "14pt",
        "font": "Arial",
        "color": "#101010",
        "fill": "none",
        "line": "none",
    }
    payload.update(props)
    return {"command": "add", "parent": "/slide[1]", "type": "textbox", "props": payload}


def _slide_header() -> list[dict[str, Any]]:
    return [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}},
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": "probe"}},
    ]


def _preset_commands() -> list[dict[str, Any]]:
    commands = _slide_header()
    commands += [
        _shape(
            SOLID_ELLIPSE,
            "ellipse",
            SOLID_ELLIPSE_BOX,
            fill=SOLID_ELLIPSE_FILL,
            line="none",
        ),
        _shape(
            SOLID_ARROW,
            "rightArrow",
            SOLID_ARROW_BOX,
            fill=SOLID_ARROW_FILL,
            line=SOLID_ARROW_LINE,
            lineWidth=f"{SOLID_ARROW_LINE_PT}pt",
        ),
        _shape(
            LABELLED_ELLIPSE,
            "ellipse",
            LABELLED_ELLIPSE_BOX,
            fill=LABELLED_ELLIPSE_FILL,
            line="none",
            text=LABELLED_ELLIPSE_TEXT,
            size=f"{LABELLED_TEXT_SIZE_PT}pt",
            font=LABELLED_TEXT_FONT,
            color=LABELLED_TEXT_COLOR,
        ),
        _shape(
            LABELLED_ARROW,
            "rightArrow",
            LABELLED_ARROW_BOX,
            fill=LABELLED_ARROW_FILL,
            line="none",
            text=LABELLED_ARROW_TEXT,
            size="16pt",
            font="Arial",
            color="#FFFFFF",
        ),
        _shape(
            TRANSLUCENT_ELLIPSE,
            "ellipse",
            TRANSLUCENT_BOX,
            fill=TRANSLUCENT_FILL,
            line="none",
        ),
        _shape(
            ROTATED_ELLIPSE,
            "ellipse",
            ROTATED_BOX,
            fill=ROTATED_FILL,
            line="none",
            rotation=f"{ROTATED_DEGREES:g}",
        ),
        # The presets that were already canonical before this slice, so the
        # "rect and roundRect are unchanged" criterion has its own evidence.
        _shape(PLAIN_RECT, "rect", PLAIN_RECT_BOX, fill=PLAIN_RECT_FILL, line="none"),
        _shape(
            ROUNDED_RECT,
            "roundRect",
            ROUNDED_RECT_BOX,
            fill=ROUNDED_RECT_FILL,
            line=ROUNDED_RECT_LINE,
            lineWidth="1pt",
        ),
        _shape(
            OVERLAY_ELLIPSE,
            "ellipse",
            OVERLAY_BOX,
            fill=OVERLAY_FILL,
            line="none",
        ),
    ]
    for offset, line in zip(OVERLAY_TEXT_TOP_PT, OVERLAY_LINES):
        commands.append(
            _textbox(
                f"overlay-text-{line.replace('/', '-')}",
                line,
                (OVERLAY_BOX[0] + 10, offset, OVERLAY_BOX[2] - 20, 24),
                size="14pt",
                color="#FFFFFF",
            )
        )
    return commands


def _boundary_commands() -> list[dict[str, Any]]:
    return [
        *_slide_header(),
        # A theme expression is not a plain solid colour, so neither the fill
        # nor the outline may be declared editable.
        _shape(THEME_FILL_ELLIPSE, "ellipse", THEME_FILL_BOX, fill="accent1", line="none"),
        _shape(
            THEME_LINE_ARROW,
            "rightArrow",
            THEME_LINE_BOX,
            fill=THEME_LINE_FILL,
            line="accent2",
            lineWidth="2pt",
        ),
        # A preset outside this slice keeps its V0.4.1 reason.
        _shape(CHEVRON_SHAPE, "chevron", CHEVRON_BOX, fill="#D96666", line="none"),
        # Text whose visible formatting the slide does not own is base-only.
        _shape(
            THEME_TEXT_ELLIPSE,
            "ellipse",
            THEME_TEXT_BOX,
            fill=THEME_TEXT_FILL,
            line="none",
            text=THEME_TEXT,
        ),
        # A mirror is not an in-plane rotation.
        _shape(MIRRORED_ARROW, "rightArrow", MIRRORED_BOX, fill="#EE822F", line="none"),
        # A rotated rect keeps the V0.4.1 refusal: this slice admits rotation
        # only for the presets it adds.
        _shape(
            ROTATED_RECT,
            "rect",
            ROTATED_RECT_BOX,
            fill="#3366CC",
            line="none",
            rotation="30",
        ),
        _shape(
            BOUNDARY_CONTROL_ELLIPSE,
            "ellipse",
            BOUNDARY_CONTROL_BOX,
            fill="#75BD42",
            line="none",
        ),
    ]


def _container_commands(
    *,
    child_rect: Sequence[float] = GROUP_CHILD_RECT,
    link_rect: Sequence[float] = GROUP_CHILD_LINK_RECT,
) -> list[dict[str, Any]]:
    """One page whose group owns a shape and a connector.

    The two rectangles are parameters because the container boundary has two
    sides: a container whose children can be placed, and one whose children
    cannot be placed inside its rectangle under any reading of the source.
    """
    return [
        *_slide_header(),
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "group",
            "props": {
                "name": GROUP_NAME,
                "x": f"{GROUP_BOX[0]}pt",
                "y": f"{GROUP_BOX[1]}pt",
                "width": f"{GROUP_BOX[2]}pt",
                "height": f"{GROUP_BOX[3]}pt",
            },
        },
        _shape(
            GROUP_CHILD_BOX,
            "rect",
            child_rect,
            parent="/slide[1]/group[1]",
            fill=GROUP_CHILD_BOX_FILL,
            line="none",
        ),
        {
            "command": "add",
            "parent": "/slide[1]/group[1]",
            "type": "connector",
            "props": {
                "name": GROUP_CHILD_LINK,
                "x": f"{link_rect[0]}pt",
                "y": f"{link_rect[1]}pt",
                "width": f"{link_rect[2]}pt",
                "height": f"{link_rect[3]}pt",
                "line": GROUP_CHILD_LINK_COLOR,
            },
        },
        _textbox(GROUP_SIBLING, GROUP_SIBLING_TEXT, (40.0, 40.0, 300.0, 40.0)),
        _textbox(
            GROUP_INTRUDER,
            GROUP_INTRUDER_TEXT,
            GROUP_INTRUDER_BOX,
            color=GROUP_INTRUDER_COLOR,
        ),
    ]


def _hollow_commands() -> list[dict[str, Any]]:
    """One group whose only child paints nothing.

    The child is a real, slide-owned object with no fill and no outline, so the
    group has visible extent but nothing visible inside it.  Reconstructing the
    container therefore produces bare background, which must be reported rather
    than published as a proxy.
    """
    return [
        *_slide_header(),
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "group",
            "props": {
                "name": HOLLOW_GROUP,
                "x": f"{GROUP_BOX[0]}pt",
                "y": f"{GROUP_BOX[1]}pt",
                "width": f"{GROUP_BOX[2]}pt",
                "height": f"{GROUP_BOX[3]}pt",
            },
        },
        _shape(
            HOLLOW_CHILD,
            "rect",
            (210.0, 210.0, 80.0, 40.0),
            parent="/slide[1]/group[1]",
            fill="none",
            line="none",
        ),
    ]


def _connector_commands() -> list[dict[str, Any]]:
    return [
        *_slide_header(),
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "connector",
            "props": {
                "name": STANDALONE_CONNECTOR,
                "x": f"{CONNECTOR_BOX[0]}pt",
                "y": f"{CONNECTOR_BOX[1]}pt",
                "width": f"{CONNECTOR_BOX[2]}pt",
                "height": f"{CONNECTOR_BOX[3]}pt",
                "line": CONNECTOR_COLOR,
            },
        },
        _textbox(
            CONNECTOR_OVERLAY,
            CONNECTOR_OVERLAY_TEXT,
            CONNECTOR_OVERLAY_BOX,
            color=CONNECTOR_OVERLAY_COLOR,
        ),
    ]


def _declare_child_space(
    deck: Path,
    *,
    child_offset_pt: tuple[float, float],
    child_extent_pt: tuple[float, float],
    group_index: int = 1,
) -> None:
    """Declare a group's own child coordinate space, as PowerPoint writes it.

    A group's children are addressed in the group's child space, which the
    source records as ``a:chOff``/``a:chExt``.  OfficeCLI reads those back as
    ``childOffset``/``childExtent`` but has no property that writes them, so a
    synthetic group has none and a fixture that needs a real group transform
    declares it in the slide part.  Nothing else in the package is touched.
    """
    for prefix, uri in (("a", A_NS), ("p", P_NS), ("r", R_NS)):
        ElementTree.register_namespace(prefix, uri)
    with zipfile.ZipFile(deck) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = ElementTree.fromstring(parts[SLIDE_PART])
    groups = [node for node in root.iter(f"{{{P_NS}}}grpSp")]
    transform = groups[group_index - 1].find(f"{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
    assert transform is not None, "the fixture group has no a:xfrm"
    for tag in ("chOff", "chExt"):
        existing = transform.find(f"{{{A_NS}}}{tag}")
        if existing is not None:
            transform.remove(existing)
    offset = ElementTree.SubElement(transform, f"{{{A_NS}}}chOff")
    offset.set("x", str(int(round(child_offset_pt[0] * EMU_PER_POINT))))
    offset.set("y", str(int(round(child_offset_pt[1] * EMU_PER_POINT))))
    extent = ElementTree.SubElement(transform, f"{{{A_NS}}}chExt")
    extent.set("cx", str(int(round(child_extent_pt[0] * EMU_PER_POINT))))
    extent.set("cy", str(int(round(child_extent_pt[1] * EMU_PER_POINT))))
    parts[SLIDE_PART] = ElementTree.tostring(root, encoding="UTF-8", xml_declaration=True)
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)


@pytest.fixture(scope="session")
def decks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Build every synthetic probe deck once, through OfficeCLI."""
    directory = tmp_path_factory.mktemp("v042-presets")
    presets = _build_deck(directory / "presets.pptx", _preset_commands())
    # A semi-transparent fill is written by OfficeCLI's own opacity property,
    # which reports the alpha twice: once as the fill token's alpha byte and
    # once as `opacity`.  Both readings have to reach the canvas as one value.
    _officecli(
        "set",
        str(presets),
        f"/slide[1]/shape[@name={TRANSLUCENT_ELLIPSE}]",
        "--prop",
        f"opacity={TRANSLUCENT_OPACITY}",
    )
    _officecli("close", str(presets))

    boundary = _build_deck(directory / "boundary.pptx", _boundary_commands())
    _officecli(
        "set",
        str(boundary),
        f"/slide[1]/shape[@name={MIRRORED_ARROW}]",
        "--prop",
        "flipH=true",
    )
    _officecli("close", str(boundary))

    container = _build_deck(directory / "container.pptx", _container_commands())
    _declare_child_space(
        container,
        child_offset_pt=GROUP_CHILD_OFFSET_PT,
        child_extent_pt=GROUP_CHILD_EXTENT_PT,
    )
    undeclared = _build_deck(directory / "undeclared.pptx", _container_commands())
    # The unplaceable deck: children outside the group's rectangle *and* a
    # declared child space that scales them further out, so neither reading of
    # the source can put their paint inside the container.
    unreconciled = _build_deck(
        directory / "unreconciled.pptx",
        _container_commands(
            child_rect=UNPLACEABLE_CHILD_RECT, link_rect=UNPLACEABLE_LINK_RECT
        ),
    )
    _declare_child_space(
        unreconciled,
        child_offset_pt=UNPLACEABLE_CHILD_OFFSET_PT,
        child_extent_pt=UNPLACEABLE_CHILD_EXTENT_PT,
    )
    connector = _build_deck(directory / "connector.pptx", _connector_commands())
    hollow = _build_deck(directory / "hollow.pptx", _hollow_commands())
    _declare_child_space(
        hollow,
        child_offset_pt=(210.0, 210.0),
        child_extent_pt=(80.0, 40.0),
    )
    return {
        PRESET_DECK: presets,
        BOUNDARY_DECK: boundary,
        CONTAINER_DECK: container,
        UNDECLARED_DECK: undeclared,
        UNRECONCILED_DECK: unreconciled,
        HOLLOW_DECK: hollow,
        CONNECTOR_DECK: connector,
        "directory": directory,
    }


@pytest.fixture(scope="session")
def preset_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> ProjectionResult:
    directory = tmp_path_factory.mktemp("v042-preset-run")
    return project_pptx_to_author_html(
        decks[PRESET_DECK], [1], directory / "presets.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def rebuilt(
    preset_run: ProjectionResult, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Any, Path]:
    """Rebuild the preset projection through the existing New Deck path."""
    directory = tmp_path_factory.mktemp("v042-preset-rebuilt")
    output = directory / "presets.pptx"
    built = asyncio.run(build_author_html(str(preset_run.html_path), str(output)))
    return built, output


@pytest.fixture(scope="session")
def boundary_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> ProjectionResult:
    directory = tmp_path_factory.mktemp("v042-boundary-run")
    return project_pptx_to_author_html(
        decks[BOUNDARY_DECK], [1], directory / "boundary.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def container_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> ProjectionResult:
    directory = tmp_path_factory.mktemp("v042-container-run")
    return project_pptx_to_author_html(
        decks[CONTAINER_DECK], [1], directory / "container.html", proxy_dir=directory / "proxies"
    )


@pytest.fixture(scope="session")
def connector_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> ProjectionResult:
    directory = tmp_path_factory.mktemp("v042-connector-run")
    return project_pptx_to_author_html(
        decks[CONNECTOR_DECK], [1], directory / "connector.html", proxy_dir=directory / "proxies"
    )


def _blocked(deck: Path, target: Path) -> ProjectionBlockedError:
    with pytest.raises(ProjectionBlockedError) as error:
        project_pptx_to_author_html(
            deck, [1], target, proxy_dir=target.parent / f"{target.stem}-proxies"
        )
    return error.value


@pytest.fixture(scope="session")
def undeclared_run(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> ProjectionResult:
    """The group page with no declared child space: it publishes a container.

    Nothing about the page changed except the reading the projection is willing
    to try, so the run completes and the container is represented once.
    """
    directory = tmp_path_factory.mktemp("v042-undeclared")
    return project_pptx_to_author_html(
        decks[UNDECLARED_DECK],
        [1],
        directory / "undeclared.html",
        proxy_dir=directory / "proxies",
    )


@pytest.fixture(scope="session")
def unreconciled_blocked(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> tuple[ProjectionBlockedError, Path]:
    directory = tmp_path_factory.mktemp("v042-unreconciled")
    target = directory / "unreconciled.html"
    return _blocked(decks[UNRECONCILED_DECK], target), target


@pytest.fixture(scope="session")
def hollow_blocked(
    decks: Mapping[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> tuple[ProjectionBlockedError, Path]:
    directory = tmp_path_factory.mktemp("v042-hollow")
    target = directory / "hollow.html"
    return _blocked(decks[HOLLOW_DECK], target), target


# ---------------------------------------------------------------------------
# Readers of the published artifacts and of the rebuilt deck.  Nothing here
# reaches into the projector: the rebuilt deck is read with independent
# OfficeCLI queries and with the package's own XML.
# ---------------------------------------------------------------------------


def _html(result: ProjectionResult) -> str:
    return Path(result.output_html).read_text(encoding="utf-8")


def _entry(result: ProjectionResult, name: str) -> Any:
    matches = [item for item in result.ledger if item.source_name == name]
    assert len(matches) == 1, (
        f"expected exactly one ledger entry named {name!r}; got "
        f"{[item.as_dict() for item in matches]}"
    )
    return matches[0]


def _projected(result: ProjectionResult, name: str) -> Any:
    matches = [item for item in result.objects if item.source_name == name]
    assert len(matches) == 1, f"expected one emitted object named {name!r}"
    return matches[0]


def _element(html: str, html_id: str) -> str:
    """Return the opening tag of one emitted element."""
    assert f'id="{html_id}"' in html, html_id
    return html.split(f'id="{html_id}"', 1)[1].split(">", 1)[0]


def _full_element(html: str, html_id: str) -> str:
    body = html.split(f'id="{html_id}"', 1)[1]
    if body.startswith("/>"):
        return body.split(">", 1)[0]
    return body.split("</div>", 1)[0]


def _slide_objects(pptx: Path, page: int = 1, depth: int = 1) -> list[dict[str, Any]]:
    """Independently query one rebuilt slide's objects through OfficeCLI."""
    payload = json.loads(
        _officecli("get", str(pptx), f"/slide[{page}]", "--depth", str(depth), "--json")
    )
    return payload["data"]["results"][0].get("children") or []


def _readback(pptx: Path, emitted_name: str, page: int = 1) -> dict[str, Any]:
    """Locate one rebuilt object by the identity the projection published."""
    for node in _slide_objects(pptx, page):
        if str((node.get("format") or {}).get("name") or "") == emitted_name:
            return node
    raise AssertionError(
        f"no rebuilt object named {emitted_name!r}; got "
        f"{[(node.get('format') or {}).get('name') for node in _slide_objects(pptx, page)]}"
    )


def _slide_xml(pptx: Path, page: int = 1) -> str:
    with zipfile.ZipFile(pptx) as archive:
        return archive.read(f"ppt/slides/slide{page}.xml").decode("utf-8")


def _pt(value: Any) -> float:
    from officecli_html_to_pptx._internal.pptx_reader import length_to_points

    return length_to_points(value)


def _hex(value: Any) -> str:
    return str(value or "").strip().lstrip("#").upper()


def _pixel_count_near(image: Any, color: tuple[int, int, int], tolerance: int = 26) -> int:
    """Count pixels close to one colour.

    This is the overlay probe's reader: a proxy that carries a sibling's paint
    contains that sibling's own colour, and a genuinely object-local proxy
    contains none of it.
    """
    rgb = image.convert("RGB")
    counts = rgb.getcolors(rgb.width * rgb.height + 1) or ()
    return sum(
        count
        for count, pixel in counts
        if all(abs(channel - expected) <= tolerance for channel, expected in zip(pixel, color))
    )


def _hex_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _near_color(
    pixel: tuple[int, int, int], color: tuple[int, int, int], tolerance: int = 26
) -> bool:
    """Return whether one painted pixel is the expected colour."""
    return all(
        abs(channel - expected) <= tolerance
        for channel, expected in zip(pixel, color)
    )


def _proxy_pixel(
    rgb: Any, projected: Any, x_pt: float, y_pt: float
) -> tuple[int, int, int]:
    """Return the proxy pixel that sits at one point of the slide.

    A proxy is the object's own rectangle cropped out of a render at the Author
    canvas density, with the guard band on every side, so a point of the slide
    maps onto it by subtracting the object's origin and adding the guard back.
    """
    x = int(round(x_pt * PIXELS_PER_POINT - projected.bounds_px[0])) + PROXY_GUARD_PX
    y = int(round(y_pt * PIXELS_PER_POINT - projected.bounds_px[1])) + PROXY_GUARD_PX
    assert 0 <= x < rgb.width and 0 <= y < rgb.height, (x, y, rgb.size)
    return tuple(rgb.getpixel((x, y)))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Criterion: a text-free solid ellipse / rightArrow is a canonical shape
# ---------------------------------------------------------------------------


def test_a_text_free_solid_ellipse_is_a_canonical_shape(
    preset_run: ProjectionResult,
) -> None:
    entry = _entry(preset_run, SOLID_ELLIPSE)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.reason_code is None
    assert entry.projected_kind == "shape"
    assert entry.emitted is True
    projected = _projected(preset_run, SOLID_ELLIPSE)
    assert projected.proxy_asset is None, "a canonical object is never a raster proxy"


def test_a_text_free_solid_right_arrow_is_a_canonical_shape(
    preset_run: ProjectionResult,
) -> None:
    entry = _entry(preset_run, SOLID_ARROW)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.projected_kind == "shape"
    assert _projected(preset_run, SOLID_ARROW).proxy_asset is None


def test_the_emitted_preset_declares_its_native_geometry(
    preset_run: ProjectionResult,
) -> None:
    """The shape lowering needs the preset named, because CSS cannot imply it."""
    html = _html(preset_run)
    for name, geometry in (
        (SOLID_ELLIPSE, "ellipse"),
        (SOLID_ARROW, "rightArrow"),
        (LABELLED_ELLIPSE, "ellipse"),
    ):
        element = _element(html, _projected(preset_run, name).html_id)
        assert f'data-shape-geometry="{geometry}"' in element, element


def test_an_ellipse_is_drawn_as_an_ellipse_on_the_author_canvas(
    preset_run: ProjectionResult,
) -> None:
    """The canvas draws what the deck will contain, at the canvas factor.

    The width carries one Chromium layout unit more than the measurement, because
    Blink snaps layout to a 1/64 px grid and a box declared at exactly its measured
    size is laid out a unit narrower -- see
    ``test_object_bounds_are_normalized_at_the_canvas_factor``.
    """
    element = _element(_html(preset_run), _projected(preset_run, SOLID_ELLIPSE).html_id)
    assert "border-radius: 50%" in element
    expected = SOLID_ELLIPSE_BOX[2] * PIXELS_PER_POINT + projector._LAYOUT_UNIT_PX
    assert f"width: {expected:g}px" in element


# ---------------------------------------------------------------------------
# Criterion: the rebuilt PPTX carries the native geometry, not a picture
# ---------------------------------------------------------------------------


def test_the_rebuilt_ellipse_has_native_ellipse_geometry(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    """Independent OfficeCLI query: the object is a shape with prst=ellipse."""
    _, output = rebuilt
    node = _readback(output, _projected(preset_run, SOLID_ELLIPSE).emitted_name)
    assert str(node.get("type")) == "shape", node
    assert node["format"]["geometry"] == "ellipse", node["format"]


def test_the_rebuilt_right_arrow_has_native_right_arrow_geometry(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    _, output = rebuilt
    node = _readback(output, _projected(preset_run, SOLID_ARROW).emitted_name)
    assert str(node.get("type")) == "shape", node
    assert node["format"]["geometry"] == "rightArrow", node["format"]


def test_the_rebuilt_slide_declares_the_presets_in_its_own_xml(
    rebuilt: tuple[Any, Path]
) -> None:
    """The preset is in the DrawingML, not only in a readback summary."""
    _, output = rebuilt
    xml = _slide_xml(output)
    assert 'prst="ellipse"' in xml
    assert 'prst="rightArrow"' in xml
    # Neither preset became a raster: the deck holds no picture object at all.
    assert "<p:pic>" not in xml
    assert "a:blip" not in xml


def test_the_rebuilt_deck_passes_officecli_validation(
    rebuilt: tuple[Any, Path]
) -> None:
    _, output = rebuilt
    _officecli("validate", str(output))
    assert output.stat().st_size > 0


def test_the_projection_does_not_count_a_proxy_as_a_native_round_trip(
    preset_run: ProjectionResult,
) -> None:
    counts = preset_run.projection_report["counts"]
    assert counts["native_round_trip"] == counts["canonical_editable"]
    assert counts["unsupported"] == 0
    assert counts["unresolved"] == 0
    assert counts["native_round_trip"] >= 8, counts


# ---------------------------------------------------------------------------
# Criterion: fill, outline, bounds and z-order round-trip
# ---------------------------------------------------------------------------


def test_supported_fill_outline_and_line_width_round_trip(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    _, output = rebuilt
    ellipse = _readback(output, _projected(preset_run, SOLID_ELLIPSE).emitted_name)
    assert _hex(ellipse["format"]["fill"]) == _hex(SOLID_ELLIPSE_FILL)
    assert str(ellipse["format"].get("line", "none")).lower() == "none"

    arrow = _readback(output, _projected(preset_run, SOLID_ARROW).emitted_name)
    assert _hex(arrow["format"]["fill"]) == _hex(SOLID_ARROW_FILL)
    assert _hex(arrow["format"]["line"]) == _hex(SOLID_ARROW_LINE)
    assert _pt(arrow["format"]["lineWidth"]) == pytest.approx(
        SOLID_ARROW_LINE_PT, abs=0.2
    )


def test_bounds_round_trip_within_the_contract_tolerance(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    _, output = rebuilt
    for name, box in (
        (SOLID_ELLIPSE, SOLID_ELLIPSE_BOX),
        (SOLID_ARROW, SOLID_ARROW_BOX),
        (ROTATED_ELLIPSE, ROTATED_BOX),
    ):
        node = _readback(output, _projected(preset_run, name).emitted_name)
        fmt = node["format"]
        emitted = tuple(_pt(fmt[key]) for key in ("x", "y", "width", "height"))
        for source_value, emitted_value in zip(box, emitted):
            assert emitted_value == pytest.approx(source_value, abs=0.5), name


def test_the_emitted_geometry_is_the_source_rectangle_at_the_canvas_factor(
    preset_run: ProjectionResult,
) -> None:
    """Position is the source rectangle at the canvas factor; extent adds one unit.

    The one unit is Chromium's: Blink snaps layout to a 1/64 px grid, so a box
    declared at exactly its measured width is laid out a unit narrower and a box
    whose text fills it then wraps where the source does not.  Position is not
    biased.
    """
    bias = projector._LAYOUT_UNIT_PX
    for item in preset_run.objects:
        assert item.bounds_px[0] == pytest.approx(item.bounds_pt[0] * PIXELS_PER_POINT, abs=0.01)
        assert item.bounds_px[1] == pytest.approx(item.bounds_pt[1] * PIXELS_PER_POINT, abs=0.01)
        for source_value, emitted_value in zip(item.bounds_pt[2:], item.bounds_px[2:]):
            assert emitted_value == pytest.approx(
                source_value * PIXELS_PER_POINT + bias, abs=0.01
            ), (item.source_object, source_value, emitted_value)
    assert preset_run.canvas_px == CANVAS_PX
    assert preset_run.pixels_per_point == pytest.approx(PIXELS_PER_POINT)


def test_objects_are_emitted_and_rebuilt_in_source_paint_order(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    """Z-order is preserved in the document and in the rebuilt deck."""
    html = _html(preset_run)
    positions = [html.index(f'id="{item.html_id}"') for item in preset_run.objects]
    assert positions == sorted(positions)

    _, output = rebuilt
    names = [
        str((node.get("format") or {}).get("name") or "")
        for node in _slide_objects(output)
    ]
    expected = [item.emitted_name for item in preset_run.objects]
    assert names == expected, (names, expected)


# ---------------------------------------------------------------------------
# Criterion: opacity and rotation
# ---------------------------------------------------------------------------


def test_a_semi_transparent_ellipse_keeps_its_opacity(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    """OfficeCLI reports the alpha twice; the canvas must carry it once."""
    entry = _entry(preset_run, TRANSLUCENT_ELLIPSE)
    assert entry.disposition == DISPOSITION_CANONICAL
    element = _element(_html(preset_run), _projected(preset_run, TRANSLUCENT_ELLIPSE).html_id)
    assert "rgba(" in element, element
    assert "0.5020)" in element or "0.5000)" in element, element

    _, output = rebuilt
    fmt = _readback(output, _projected(preset_run, TRANSLUCENT_ELLIPSE).emitted_name)["format"]
    assert float(fmt["opacity"]) == pytest.approx(TRANSLUCENT_OPACITY, abs=0.03)
    # OfficeCLI writes a semi-transparent fill back as an eight-digit token, so
    # the colour claim is its first six digits and the alpha is its last byte.
    token = _hex(fmt["fill"])
    assert token[:6] == _hex(TRANSLUCENT_FILL)
    assert len(token) == 8, token
    assert int(token[6:8], 16) / 255.0 == pytest.approx(
        TRANSLUCENT_OPACITY, abs=0.03
    )


def test_a_rotated_ellipse_round_trips_its_rotation(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    entry = _entry(preset_run, ROTATED_ELLIPSE)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.reason_code is None
    element = _element(_html(preset_run), _projected(preset_run, ROTATED_ELLIPSE).html_id)
    assert f"transform: rotate({ROTATED_DEGREES:g}deg)" in element, element

    _, output = rebuilt
    fmt = _readback(output, _projected(preset_run, ROTATED_ELLIPSE).emitted_name)["format"]
    assert fmt["geometry"] == "ellipse"
    assert float(fmt["rotation"]) == pytest.approx(ROTATED_DEGREES, abs=0.01)


def test_a_mirrored_preset_is_locked_and_never_claimed_editable(
    boundary_run: ProjectionResult,
) -> None:
    """A mirror is not an in-plane rotation, so no transform reproduces it."""
    entry = _entry(boundary_run, MIRRORED_ARROW)
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "rotation_not_supported"
    assert "mirror" in (entry.reason or "").lower()
    assert entry.projected_kind == "image"
    assert _projected(boundary_run, MIRRORED_ARROW).proxy_asset


def test_a_rotated_rect_keeps_the_v041_refusal(
    boundary_run: ProjectionResult,
) -> None:
    """This slice admits rotation only for the presets it adds."""
    entry = _entry(boundary_run, ROTATED_RECT)
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "rotation_not_supported"
    assert entry.unsupported_properties == ("rotation",)


# ---------------------------------------------------------------------------
# Criterion: supported text stays native editable text
# ---------------------------------------------------------------------------


def test_supported_text_on_an_ellipse_stays_native_editable_text(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    entry = _entry(preset_run, LABELLED_ELLIPSE)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.projected_kind == "shape", "a preset with text is still a shape"
    body = _full_element(_html(preset_run), _projected(preset_run, LABELLED_ELLIPSE).html_id)
    assert LABELLED_ELLIPSE_TEXT in body

    _, output = rebuilt
    xml = _slide_xml(output)
    assert xml.count(f"<a:t>{LABELLED_ELLIPSE_TEXT}</a:t>") == 1
    node = _readback(output, _projected(preset_run, LABELLED_ELLIPSE).emitted_name)
    assert node["format"]["geometry"] == "ellipse"


def test_supported_text_formatting_on_an_ellipse_is_read_back(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    """Character and formatting readback comes from the rebuilt deck itself."""
    _, output = rebuilt
    runs = [
        run
        for child in _slide_objects(output, depth=3)
        for paragraph in (child.get("children") or [])
        for run in (paragraph.get("children") or [])
        if str(run.get("type")) == "run"
    ]
    matching = [run for run in runs if LABELLED_ELLIPSE_TEXT in str(run.get("text") or "")]
    assert len(matching) == 1, runs
    fmt = matching[0]["format"]
    assert _hex(fmt["color"]) == _hex(LABELLED_TEXT_COLOR)
    assert _pt(fmt["size"]) == pytest.approx(LABELLED_TEXT_SIZE_PT, abs=0.5)
    assert str(fmt.get("font.latin") or fmt.get("font")) == LABELLED_TEXT_FONT


def test_supported_text_on_a_right_arrow_stays_native_editable_text(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    entry = _entry(preset_run, LABELLED_ARROW)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert _projected(preset_run, LABELLED_ARROW).text.strip() == LABELLED_ARROW_TEXT
    _, output = rebuilt
    assert _slide_xml(output).count(f"<a:t>{LABELLED_ARROW_TEXT}</a:t>") == 1
    node = _readback(output, _projected(preset_run, LABELLED_ARROW).emitted_name)
    assert node["format"]["geometry"] == "rightArrow"


# ---------------------------------------------------------------------------
# Criterion: overlapping sibling textboxes stay independent and appear once
# ---------------------------------------------------------------------------


def test_overlapping_sibling_textboxes_stay_independent_canonical_objects(
    preset_run: ProjectionResult,
) -> None:
    ellipse = _entry(preset_run, OVERLAY_ELLIPSE)
    assert ellipse.disposition == DISPOSITION_CANONICAL
    assert _projected(preset_run, OVERLAY_ELLIPSE).proxy_asset is None
    for line in OVERLAY_LINES:
        sibling = _entry(preset_run, f"overlay-text-{line.replace('/', '-')}")
        assert sibling.disposition == DISPOSITION_CANONICAL
        assert sibling.emitted is True
        assert sibling.owner is None


def test_the_preset_carries_no_sibling_text_in_its_element(
    preset_run: ProjectionResult,
) -> None:
    """A promoted preset is a shape; nothing of its neighbours is baked in."""
    body = _full_element(_html(preset_run), _projected(preset_run, OVERLAY_ELLIPSE).html_id)
    for line in OVERLAY_LINES:
        assert line not in body
    assert "data:image" not in body


def test_every_overlapping_text_appears_exactly_once_in_the_rebuilt_deck(
    rebuilt: tuple[Any, Path]
) -> None:
    _, output = rebuilt
    xml = _slide_xml(output)
    for line in OVERLAY_LINES:
        assert xml.count(f"<a:t>{line}</a:t>") == 1, (line, xml.count(f"<a:t>{line}</a:t>"))


def test_no_raster_payload_carries_an_overlapping_text(
    preset_run: ProjectionResult,
) -> None:
    """The raster contamination probe: no proxy may enclose foreign paint.

    The probe is proved able to fail before it is trusted: a flat fill that
    encloses a contrasting bar is detected, and the same fill without it is not.
    """
    from PIL import Image

    fill = _hex_rgb(OVERLAY_FILL)
    flat = Image.new("RGB", (160, 80), fill)
    contaminated = Image.new("RGB", (160, 80), fill)
    white = (255, 255, 255)
    for x in range(40, 120):
        for y in range(30, 50):
            contaminated.putpixel((x, y), white)
    assert _pixel_count_near(flat, white) == 0
    assert _pixel_count_near(contaminated, white) > 0

    proxies = [item for item in preset_run.objects if item.proxy_asset]
    assert proxies == [], "every object on this page is canonical, so none is a proxy"


def test_no_proxy_asset_on_any_run_contains_a_neighbour_colour(
    container_run: ProjectionResult, connector_run: ProjectionResult
) -> None:
    """Every published proxy is checked, not just the ones under test."""
    from PIL import Image

    intruder = _hex_rgb(GROUP_INTRUDER_COLOR)
    for result in (container_run, connector_run):
        for item in result.objects:
            if not item.proxy_asset:
                continue
            with Image.open(item.proxy_asset) as image:
                assert _pixel_count_near(image, intruder) == 0, item.source_name


# ---------------------------------------------------------------------------
# Criterion: a negative case keeps its existing disposition and reason
# ---------------------------------------------------------------------------


def test_a_non_solid_fill_is_a_locked_proxy_with_fill_not_solid(
    boundary_run: ProjectionResult,
) -> None:
    entry = _entry(boundary_run, THEME_FILL_ELLIPSE)
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "fill_not_solid"
    assert entry.unsupported_properties == ("fill",)
    assert "accent1" in (entry.reason or "")
    assert _projected(boundary_run, THEME_FILL_ELLIPSE).proxy_asset


def test_an_unsupported_outline_is_a_locked_proxy_with_line_not_solid(
    boundary_run: ProjectionResult,
) -> None:
    entry = _entry(boundary_run, THEME_LINE_ARROW)
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "line_not_solid"
    assert entry.unsupported_properties == ("line",)


def test_another_preset_keeps_its_v041_geometry_reason(
    boundary_run: ProjectionResult,
) -> None:
    entry = _entry(boundary_run, CHEVRON_SHAPE)
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "geometry_not_canonical"
    assert "chevron" in (entry.reason or "")


def test_the_boundary_page_still_promotes_the_preset_it_can(
    boundary_run: ProjectionResult,
) -> None:
    """The negatives are the boundary, not a refusal of the whole slice."""
    entry = _entry(boundary_run, BOUNDARY_CONTROL_ELLIPSE)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert boundary_run.disposition_counts()[DISPOSITION_UNSUPPORTED] == 0
    assert boundary_run.disposition_counts()[DISPOSITION_UNRESOLVED] == 0


def test_no_locked_preset_is_counted_as_a_native_round_trip(
    boundary_run: ProjectionResult,
) -> None:
    counts = boundary_run.projection_report["counts"]
    assert counts["native_round_trip"] == counts["canonical_editable"] == 1
    assert counts["locked_visual_proxy"] == 5
    assert counts["base_only_semantic"] == 1
    for entry in boundary_run.ledger:
        if entry.disposition == DISPOSITION_CANONICAL:
            assert entry.reason is None and entry.reason_code is None
        else:
            assert entry.reason_code in REASON_CODES
            assert entry.reason


def test_the_new_reason_code_is_part_of_the_declared_vocabulary() -> None:
    assert "container_child_space_unreconciled" in REASON_CODES


# ---------------------------------------------------------------------------
# Criterion: theme-token text stays base-only
# ---------------------------------------------------------------------------


def test_theme_token_text_on_an_ellipse_stays_base_only(
    boundary_run: ProjectionResult,
) -> None:
    """A resolved RGB approximation is not a reconstructible theme expression."""
    entry = _entry(boundary_run, THEME_TEXT_ELLIPSE)
    assert entry.disposition == DISPOSITION_BASE_ONLY
    assert entry.reason_code == "text_base_only"
    assert entry.projected_kind == "image", "a base-only object is a locked proxy"
    assert entry.emitted is True
    assert _projected(boundary_run, THEME_TEXT_ELLIPSE).base_only, entry.as_dict()


def test_the_resolved_theme_value_is_evidence_not_a_promotion(
    boundary_run: ProjectionResult,
) -> None:
    entry = _entry(boundary_run, THEME_TEXT_ELLIPSE)
    claims = _projected(boundary_run, THEME_TEXT_ELLIPSE).base_only
    assert claims
    for claim in claims:
        assert claim.source.startswith("/theme"), claim.as_dict()
        assert claim.value, claim.as_dict()
    assert entry.disposition != DISPOSITION_CANONICAL
    assert entry.reason_code == "text_base_only"


def test_a_base_only_preset_keeps_a_locked_visual_representation(
    boundary_run: ProjectionResult,
) -> None:
    projected = _projected(boundary_run, THEME_TEXT_ELLIPSE)
    assert projected.proxy_reason
    assert projected.proxy_asset and Path(projected.proxy_asset).is_file()
    element = _element(_html(boundary_run), projected.html_id)
    assert 'data-projection-locked="true"' in element
    assert "data-shape-geometry" not in element


# ---------------------------------------------------------------------------
# Criterion: a group with a bound connector is one locked container
# ---------------------------------------------------------------------------


def test_a_group_with_a_child_space_is_one_locked_container_representation(
    container_run: ProjectionResult,
) -> None:
    entry = _entry(container_run, GROUP_NAME)
    assert entry.source_kind == "group"
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "non_canonical_kind"
    assert entry.projected_kind == "image"
    assert entry.emitted is True
    projected = _projected(container_run, GROUP_NAME)
    assert projected.proxy_asset and Path(projected.proxy_asset).is_file()


def test_the_group_proxy_is_the_groups_own_rectangle_at_the_canvas_factor(
    container_run: ProjectionResult,
) -> None:
    from PIL import Image

    projected = _projected(container_run, GROUP_NAME)
    with Image.open(projected.proxy_asset) as image:
        size = image.size
    expected = (
        int(round(projected.bounds_px[2])) + PROXY_GUARD_PX * 2,
        int(round(projected.bounds_px[3])) + PROXY_GUARD_PX * 2,
    )
    assert size == expected, (size, expected, projected.bounds_px)


def test_the_group_proxy_carries_its_children_paint(
    container_run: ProjectionResult,
) -> None:
    """A blank image is never published as a representation.

    This is also the projector-side half of the delta gate's target-survival
    rule: the gate measures a proxy's own bytes and refuses one that is nothing
    but its own background, so a reconstruction that publishes an image here has
    to carry paint here.
    """
    from PIL import Image

    projected = _projected(container_run, GROUP_NAME)
    with Image.open(projected.proxy_asset) as image:
        rgb = image.convert("RGB")
        colors = rgb.getcolors(1 << 16)
        child_fill = _pixel_count_near(image, _hex_rgb(GROUP_CHILD_BOX_FILL))
        background = rgb.getpixel((0, 0))
        exact_background = sum(
            count for count, colour in (colors or ()) if colour == background
        )
    assert colors is not None and len(colors) > 1, "the proxy must not be blank"
    assert child_fill > 0, "the container's own child must be visible in its proxy"
    assert exact_background < rgb.width * rgb.height, (
        "the proxy's own bytes must carry paint, not just the background it was "
        "cropped out of"
    )


def test_group_owned_children_are_recorded_as_owned_without_an_identity(
    container_run: ProjectionResult,
) -> None:
    container = _entry(container_run, GROUP_NAME)
    children = [entry for entry in container_run.ledger if entry.represented_by_container]
    assert {entry.source_name for entry in children} == {
        GROUP_CHILD_BOX,
        GROUP_CHILD_LINK,
    }
    for entry in children:
        assert entry.owner == container.source_object
        assert entry.owner_kind == "group"
        assert entry.html_id is None
        assert entry.emitted_ordinal is None
        assert entry.emitted is False
        assert entry.reason_code == "container_owned_object"


def test_the_group_and_its_children_are_each_represented_exactly_once(
    container_run: ProjectionResult,
) -> None:
    """The children are inside the container's proxy, never emitted beside it."""
    html = _html(container_run)
    emitted = [item for item in container_run.objects]
    assert len({item.html_id for item in emitted}) == len(emitted)
    for item in emitted:
        assert html.count(f' id="{item.html_id}"') == 1, item.html_id
        assert html.count(f'data-projection-id="{item.html_id}"') == 1, item.html_id
    # No element claims a container-owned source object.
    for entry in container_run.ledger:
        if entry.represented_by_container:
            assert entry.source_object not in html
    # The sibling textboxes are untouched by the ownership.
    for name in (GROUP_SIBLING, GROUP_INTRUDER):
        sibling = _entry(container_run, name)
        assert sibling.disposition == DISPOSITION_CANONICAL
        assert sibling.owner is None
        assert sibling.emitted is True


def test_the_container_proxy_does_not_capture_an_overlapping_sibling(
    container_run: ProjectionResult,
) -> None:
    """The intruder paints inside the container's rectangle and must not be in it."""
    from PIL import Image

    projected = _projected(container_run, GROUP_NAME)
    intruder = _projected(container_run, GROUP_INTRUDER)
    # The fixture really is an overlay: the intruder's box is inside the group.
    assert intruder.bounds_px[0] >= projected.bounds_px[0]
    assert intruder.bounds_px[1] >= projected.bounds_px[1]
    with Image.open(projected.proxy_asset) as image:
        assert _pixel_count_near(image, _hex_rgb(GROUP_INTRUDER_COLOR)) == 0


def test_a_group_without_a_declared_child_space_is_still_one_container(
    undeclared_run: ProjectionResult,
) -> None:
    """No declared child space is no longer a block: the reported rects are tried.

    OfficeCLI places a group's children by a convention of its own -- it neither
    reports the rectangles it paints them at nor always applies the DrawingML
    transform -- so the projection does not pick a rule.  It rebuilds the
    children where OfficeCLI *reports* them, renders that, and keeps it because
    the measured paint really does land inside the container's rectangle.
    """
    entry = _entry(undeclared_run, GROUP_NAME)
    assert entry.source_kind == "group"
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "non_canonical_kind"
    assert entry.projected_kind == "image"
    assert entry.emitted is True
    assert entry.blocking is False
    assert undeclared_run.disposition_counts()[DISPOSITION_UNSUPPORTED] == 0
    assert undeclared_run.disposition_counts()[DISPOSITION_UNRESOLVED] == 0
    projected = _projected(undeclared_run, GROUP_NAME)
    assert projected.proxy_asset and Path(projected.proxy_asset).is_file()
    element = _element(_html(undeclared_run), projected.html_id)
    assert 'data-projection-locked="true"' in element
    assert "data-shape-geometry" not in element


def test_the_undeclared_group_proxy_is_the_groups_own_rectangle_at_canvas_factor(
    undeclared_run: ProjectionResult,
) -> None:
    from PIL import Image

    projected = _projected(undeclared_run, GROUP_NAME)
    with Image.open(projected.proxy_asset) as image:
        size = image.size
    expected = (
        int(round(projected.bounds_px[2])) + PROXY_GUARD_PX * 2,
        int(round(projected.bounds_px[3])) + PROXY_GUARD_PX * 2,
    )
    assert size == expected, (size, expected, projected.bounds_px)


def test_the_undeclared_group_proxy_places_the_children_where_they_are_reported(
    undeclared_run: ProjectionResult,
) -> None:
    """The published proxy is the reported reading, and only that reading.

    The child rectangle OfficeCLI reports starts 10pt inside the group's own
    rectangle, so a point just inside it is painted and a point inside the group
    but outside the reported rectangle is bare background.  That is the
    difference between "the children were placed where the source reports them"
    and "something was painted somewhere in the rectangle".
    """
    from PIL import Image

    projected = _projected(undeclared_run, GROUP_NAME)
    with Image.open(projected.proxy_asset) as image:
        rgb = image.convert("RGB")
        inside = _proxy_pixel(rgb, projected, 215.0, 215.0)
        outside = _proxy_pixel(rgb, projected, 380.0, 310.0)
    assert _near_color(inside, _hex_rgb(GROUP_CHILD_BOX_FILL)), inside
    assert not _near_color(outside, _hex_rgb(GROUP_CHILD_BOX_FILL)), outside


def test_the_undeclared_group_proxy_carries_no_sibling_paint(
    undeclared_run: ProjectionResult,
) -> None:
    """Proof the representation is a reconstruction, not a composited crop.

    The intruder textbox paints inside the container's own rectangle on the
    source page, so a crop of the composited slide would contain its colour; the
    reconstruction contains the container's children and nothing else.
    """
    from PIL import Image

    projected = _projected(undeclared_run, GROUP_NAME)
    intruder = _projected(undeclared_run, GROUP_INTRUDER)
    assert intruder.bounds_px[0] >= projected.bounds_px[0]
    assert intruder.bounds_px[1] >= projected.bounds_px[1]
    with Image.open(projected.proxy_asset) as image:
        child_fill = _pixel_count_near(image, _hex_rgb(GROUP_CHILD_BOX_FILL))
        intruder_paint = _pixel_count_near(image, _hex_rgb(GROUP_INTRUDER_COLOR))
    assert child_fill > 0, "the container's own child must still be in the proxy"
    assert intruder_paint == 0, "a sibling's paint must never be composited in"


def test_the_undeclared_groups_children_are_owned_and_emitted_once(
    undeclared_run: ProjectionResult,
) -> None:
    """One representation, one owner, and no second copy of either child."""
    container = _entry(undeclared_run, GROUP_NAME)
    children = [entry for entry in undeclared_run.ledger if entry.represented_by_container]
    assert {entry.source_name for entry in children} == {
        GROUP_CHILD_BOX,
        GROUP_CHILD_LINK,
    }
    for entry in children:
        assert entry.owner == container.source_object
        assert entry.owner_kind == "group"
        assert entry.reason_code == "container_owned_object"
        assert entry.html_id is None
        assert entry.emitted_ordinal is None
        assert entry.emitted is False
    html = _html(undeclared_run)
    assert html.count(f'data-projection-id="{container.html_id}"') == 1
    for entry in children:
        assert entry.source_object not in html
    for name in (GROUP_SIBLING, GROUP_INTRUDER):
        sibling = _entry(undeclared_run, name)
        assert sibling.disposition == DISPOSITION_CANONICAL
        assert sibling.owner is None
        assert sibling.emitted is True


def test_a_reconciling_declared_child_space_is_the_placement_that_is_published(
    container_run: ProjectionResult,
) -> None:
    """The declared transform is tried first, so it is the accepted reading.

    The declared transform maps the group's child to a rectangle that starts at
    the group's own corner, while the reported rectangle starts 10pt inside it.
    The proxy paints the group's corner, which only the declared placement does
    -- so this pins the candidate order, not merely "a proxy exists".
    """
    from PIL import Image

    projected = _projected(container_run, GROUP_NAME)
    with Image.open(projected.proxy_asset) as image:
        rgb = image.convert("RGB")
        declared_only = _proxy_pixel(rgb, projected, 205.0, 205.0)
        reported_only = _proxy_pixel(rgb, projected, 380.0, 310.0)
    assert _near_color(declared_only, _hex_rgb(GROUP_CHILD_BOX_FILL)), declared_only
    assert not _near_color(reported_only, _hex_rgb(GROUP_CHILD_BOX_FILL)), reported_only


def test_a_group_whose_children_cannot_be_placed_gets_the_specific_reason(
    unreconciled_blocked: tuple[ProjectionBlockedError, Path],
) -> None:
    """A container no reading of the source can place is its own condition.

    The fixture's children sit outside the group's rectangle, and the declared
    child space scales them further out again, so *both* candidate placements are
    built, rendered and refused on their measured paint.  Nothing is published
    for it, and the reason names both readings.
    """
    error, target = unreconciled_blocked
    assert error.code == "projection_blocked"
    container = next(entry for entry in error.ledger if entry.source_kind == "group")
    assert container.disposition == DISPOSITION_UNSUPPORTED
    assert container.reason_code == "container_child_space_unreconciled"
    reason = container.reason or ""
    assert "outside the container's own rectangle" in reason
    assert f"its {DECLARED_PLACEMENT} placement painted" in reason
    assert f"its {REPORTED_PLACEMENT} placement painted" in reason
    blocking = [item for item in error.diagnostics if item.blocking]
    assert {item.code for item in blocking} == {
        "container_child_space_unreconciled",
        "unsupported_source_object",
    }
    assert not target.exists()
    assert not list(target.parent.glob("**/*.png")), "no proxy may be published"


def test_an_owned_child_of_an_unrepresented_container_is_honestly_reported(
    unreconciled_blocked: tuple[ProjectionBlockedError, Path],
) -> None:
    error, _ = unreconciled_blocked
    children = [entry for entry in error.ledger if entry.represented_by_container]
    assert children
    for entry in children:
        assert entry.disposition == DISPOSITION_UNSUPPORTED
        assert entry.reason_code == "container_representation_unavailable"
        assert entry.html_id is None


def test_a_container_reconstruction_with_no_paint_is_never_published(
    hollow_blocked: tuple[ProjectionBlockedError, Path],
) -> None:
    """A blank render is a failed representation, not a blank proxy.

    The fixture group's only child paints nothing, so *both* candidate readings
    of its children reconstruct to bare slide background.  Publishing that image
    would put an empty rectangle where the source has an object, so the container
    is reported instead -- with the specific reason, and with no image on disk.
    """
    error, target = hollow_blocked
    container = next(entry for entry in error.ledger if entry.source_kind == "group")
    assert container.disposition == DISPOSITION_UNSUPPORTED
    assert container.reason_code == "container_child_space_unreconciled"
    reason = container.reason or ""
    assert "no visible paint" in reason
    assert f"its {DECLARED_PLACEMENT} placement painted no visible paint" in reason
    assert f"its {REPORTED_PLACEMENT} placement painted no visible paint" in reason
    assert not target.exists()
    assert not list(target.parent.glob("**/*.png")), "no blank proxy may be published"


# ---------------------------------------------------------------------------
# Criterion: a standalone connector gets a representation, not a block
# ---------------------------------------------------------------------------


def test_a_standalone_connector_gets_a_locked_representation(
    connector_run: ProjectionResult,
) -> None:
    entry = _entry(connector_run, STANDALONE_CONNECTOR)
    assert entry.source_kind == "connector"
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "non_canonical_kind"
    assert entry.emitted is True
    projected = _projected(connector_run, STANDALONE_CONNECTOR)
    assert projected.proxy_asset and Path(projected.proxy_asset).is_file()
    assert connector_run.published is True
    assert connector_run.blocking is False


def test_the_connector_proxy_is_object_local_and_not_a_composited_crop(
    connector_run: ProjectionResult,
) -> None:
    """A sibling textbox is painted across the connector and must not appear."""
    from PIL import Image

    projected = _projected(connector_run, STANDALONE_CONNECTOR)
    with Image.open(projected.proxy_asset) as image:
        size = image.size
        assert _pixel_count_near(image, _hex_rgb(CONNECTOR_COLOR)) > 0
        assert _pixel_count_near(image, _hex_rgb(CONNECTOR_OVERLAY_COLOR)) == 0
    assert size == (
        int(round(projected.bounds_px[2])) + PROXY_GUARD_PX * 2,
        int(round(projected.bounds_px[3])) + PROXY_GUARD_PX * 2,
    )


def test_a_textbox_overlapping_a_connector_stays_its_own_canonical_object(
    connector_run: ProjectionResult,
) -> None:
    entry = _entry(connector_run, CONNECTOR_OVERLAY)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert _projected(connector_run, CONNECTOR_OVERLAY).text.strip() == CONNECTOR_OVERLAY_TEXT
    assert entry.owner is None
    body = _full_element(_html(connector_run), _projected(connector_run, CONNECTOR_OVERLAY).html_id)
    assert CONNECTOR_OVERLAY_TEXT in body


# ---------------------------------------------------------------------------
# Criterion: rect and roundRect behave exactly as before
# ---------------------------------------------------------------------------


def test_rect_and_round_rect_keep_their_existing_projection(
    preset_run: ProjectionResult,
) -> None:
    html = _html(preset_run)
    rect = _element(html, _projected(preset_run, PLAIN_RECT).html_id)
    assert "border-radius" not in rect
    assert "data-shape-geometry" not in rect
    assert f"background-color: {PLAIN_RECT_FILL}" in rect

    rounded = _element(html, _projected(preset_run, ROUNDED_RECT).html_id)
    assert "data-shape-geometry" not in rounded
    radius = round(min(ROUNDED_RECT_BOX[2], ROUNDED_RECT_BOX[3]) * PIXELS_PER_POINT * 0.16667, 4)
    assert f"border-radius: {radius:g}px" in rounded
    for name in (PLAIN_RECT, ROUNDED_RECT):
        assert _entry(preset_run, name).disposition == DISPOSITION_CANONICAL


def test_rect_and_round_rect_rebuild_with_their_existing_geometry(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    _, output = rebuilt
    rect = _readback(output, _projected(preset_run, PLAIN_RECT).emitted_name)
    assert rect["format"]["geometry"] == "rect"
    rounded = _readback(output, _projected(preset_run, ROUNDED_RECT).emitted_name)
    assert rounded["format"]["geometry"] == "roundRect"
    assert "adj" in rounded["format"], rounded["format"]


# ---------------------------------------------------------------------------
# Criterion: the unchanged Contract, the New Deck path, and one-to-one mapping
# ---------------------------------------------------------------------------


def test_the_preset_projection_passes_the_author_contract_unchanged(
    preset_run: ProjectionResult,
) -> None:
    report = check_contract(preset_run.html_path, "author")
    assert report.status == "PASS", [item.message for item in report.diagnostics]
    assert report.diagnostics == ()
    assert preset_run.published is True


def test_the_preset_projection_rebuilds_through_the_new_deck_path(
    rebuilt: tuple[Any, Path], preset_run: ProjectionResult
) -> None:
    built, output = rebuilt
    assert built.status == "VISUAL_REVIEW_REQUIRED", [
        item.message for item in built.diagnostics
    ]
    assert built.exit_code == 0
    assert output.is_file()
    assert built.data["author_html"]["sha256"] == preset_run.html_sha256
    assert (output.parent / f"{output.stem}.evidence" / "result.json").is_file()


def test_every_source_object_has_exactly_one_disposition_and_one_mapping(
    preset_run: ProjectionResult,
) -> None:
    identities = [entry.identity for entry in preset_run.ledger]
    assert len(identities) == len(set(identities))
    emitted = {item.html_id: item for item in preset_run.objects}
    assert len(emitted) == len(preset_run.objects)
    for entry in preset_run.ledger:
        if entry.html_id is None:
            assert entry.represented_by_container is True
            continue
        assert entry.html_id in emitted
        assert emitted[entry.html_id].identity == entry.identity
    assert len(preset_run.objects) == sum(
        1 for entry in preset_run.ledger if entry.emitted
    )


def test_the_source_deck_is_never_opened_for_writing(
    preset_run: ProjectionResult, decks: Mapping[str, Any]
) -> None:
    import hashlib

    path = Path(preset_run.source_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == preset_run.source_sha256
    assert preset_run.source_map["source"]["sha256"] == digest
    assert path == decks[PRESET_DECK]
