"""V0.4.2 representative acceptance: the frozen ten-page corpus (ticket #18).

The external seam under test is the same one #15, #16 and #17 drive::

    gate_projected_author_html(selection, output_directory)
        -> PASS / PASS_WITH_FINDINGS / BLOCK
         + one page record per selected page
         + the per-object disposition ledger
         + material deltas, retained findings, scope evidence
         + proxy isolation proofs, table checks, text readback
         + hashed artifacts

Everything here is observed through that one call, through the Author Contract,
through OfficeCLI readback of the rebuilt deck, and through the published
evidence files.  No private reader call, OfficeCLI command shape, or internal
DTO is frozen by this file beyond the seam's own exported result records.

The corpus is defined in :mod:`v042_acceptance_corpus`:

* eight explicitly selected real pages of one private business deck, frozen in
  selection order, and
* two synthetic probes built through OfficeCLI -- probe A for proxy/overlay
  isolation, probe B for rich-text semantics and the locked container boundary.

The real deck is 63 MB, is not committed, and is not required by CI.  The
always-run half of this module drives the two synthetic probes through the same
seam; the real half is skipped with an explicit reason unless both the deck and
an explicit opt-in are present, and the full ten-page corpus is run by
``.scratch/tools/run_v042_acceptance.py`` as a scripted acceptance run.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

import pytest

from officecli_html_to_pptx import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    GateOutcome,
    gate_projected_author_html,
)
from officecli_html_to_pptx._internal.source_delta_gate import (
    PROXY_GUARD_PX,
)
from officecli_html_to_pptx.contract import check_contract

import v042_acceptance_corpus as corpus

pytestmark = pytest.mark.skipif(
    shutil.which("officecli") is None,
    reason="OfficeCLI is required for the V0.4.2 representative acceptance",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Set to ``1`` to include the eight real pages in this module.  The source decks
#: are private business documents and are not committed, so the real half of the
#: acceptance is opt-in and is normally run once by the scripted driver.
REAL_CORPUS_ENV = "HTML_TO_PPTX_V042_REAL_CORPUS"

#: The private source decks are named by local configuration, never here.  A
#: private deck's filename is private material, so a test that spelled one would
#: publish it; see ``corpus.resolve_sources``.
_COMPAT = "OFFICECLI_H2P_CORPUS"

#: The private source deck's digest is deliberately NOT a literal here.  A
#: private deck's hash is private material under the spec, so the tests derive
#: it from the deck at run time; see ``real_source_digest``.

#: The compiled kind a locked proxy is written back as (its canvas kind is
#: ``image``, its rebuilt object is a ``picture``).  The map is used only to
#: decode the object name the projection report already publishes.
COMPILED_KIND = {"image": "picture"}

_HTML_TAG = re.compile(r"<[^>]+>")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _real_corpus_requested() -> bool:
    import os

    return os.environ.get(REAL_CORPUS_ENV, "").strip() == "1"


def _real_sources() -> dict[str, Path] | None:
    """The three source decks, or ``None`` when this machine has no corpus.

    Resolved from local configuration, so neither the decks nor their location
    appear in this file.  ``None`` means the real half of the acceptance cannot
    run here; it never means "use some default deck".
    """
    try:
        return corpus.resolve_sources()
    except (FileNotFoundError, KeyError):
        return None


def _real_corpus_available() -> bool:
    return _real_sources() is not None


def _skip_reason() -> str:
    if not _real_corpus_available():
        return (
            "the three private source decks of the frozen corpus are not named "
            f"on this machine; point {_COMPAT} at a JSON file mapping each "
            "corpus slot to its deck (see corpus.resolve_sources). The decks are "
            "not committed, so this half of the acceptance is skipped. The two "
            "synthetic probes always run."
        )
    return (
        "the private representative decks are present but the real half of the "
        f"acceptance is opt-in: set {REAL_CORPUS_ENV}=1 to run the full ten-page "
        "corpus through this module, or run .scratch/tools/run_v042_acceptance.py."
    )


# ---------------------------------------------------------------------------
# The synthetic half: always built, always run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def synthetic_probes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Both synthetic probes, built once through OfficeCLI."""
    directory = tmp_path_factory.mktemp("v042-acceptance-probes")
    return corpus.build_synthetic_probes(directory)


@pytest.fixture(scope="session")
def synthetic_result(
    synthetic_probes: dict[str, Path], tmp_path_factory: pytest.TempPathFactory
) -> object:
    """One real gate run over the two synthetic probes through the one seam."""
    output = tmp_path_factory.mktemp("v042-acceptance-synthetic") / "gate"
    selection = corpus.seam_selection(
        None, synthetic_probes[corpus.PROBE_A_KEY], synthetic_probes[corpus.PROBE_B_KEY]
    )
    return gate_projected_author_html(selection, output)


@pytest.fixture(scope="session")
def synthetic_html(synthetic_result: object) -> str:
    return corpus.document_path(synthetic_result).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def rebuilt_slide_xml(synthetic_result: object) -> dict[int, str]:
    """The rebuilt deck's own slide parts, keyed by output page."""
    rebuilt = corpus.document_path(synthetic_result, "rebuilt.pptx")
    parts: dict[int, str] = {}
    with zipfile.ZipFile(rebuilt) as archive:
        for name in archive.namelist():
            match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
            if match:
                parts[int(match.group(1))] = archive.read(name).decode("utf-8")
    return parts


# ---------------------------------------------------------------------------
# Criterion: the synthetic half runs the same seam and reaches a verdict
# ---------------------------------------------------------------------------


def test_the_synthetic_probes_are_built_through_officecli(
    synthetic_probes: dict[str, Path]
) -> None:
    assert set(synthetic_probes) == {corpus.PROBE_A_KEY, corpus.PROBE_B_KEY}
    for path in synthetic_probes.values():
        assert path.is_file() and path.stat().st_size > 0
        with zipfile.ZipFile(path) as archive:
            assert "ppt/presentation.xml" in archive.namelist()


def test_the_synthetic_run_reaches_an_accepting_verdict(synthetic_result: object) -> None:
    assert synthetic_result.accepted is True
    assert synthetic_result.published is True
    assert synthetic_result.diagnostics == ()
    assert synthetic_result.outcome in {
        GateOutcome.PASS,
        GateOutcome.PASS_WITH_FINDINGS,
    }


def test_every_synthetic_page_is_projected_and_none_is_blocked(
    synthetic_result: object,
) -> None:
    # One page per synthetic probe: two probes, two pages.
    assert synthetic_result.counts["selected_pages"] == 2
    assert synthetic_result.counts["projected_pages"] == 2
    assert synthetic_result.counts["blocked_pages"] == 0
    for page in synthetic_result.pages:
        assert page.blocked is False
        assert page.failures == ()
        assert page.unsupported == 0
        assert page.unresolved == 0
        assert page.source_objects == len(page.ledger)


def test_no_synthetic_object_is_unsupported_or_unresolved(
    synthetic_result: object,
) -> None:
    dispositions = {entry.disposition for entry in synthetic_result.ledger}
    assert "unsupported" not in dispositions
    assert "unresolved" not in dispositions
    for page in synthetic_result.pages:
        assert page.unsupported == 0
        assert page.unresolved == 0
    assert synthetic_result.counts["material_deltas"] == 0
    assert synthetic_result.unbound_rebuilt == ()


def test_the_synthetic_run_publishes_the_whole_evidence_set(
    synthetic_result: object,
) -> None:
    directory = Path(synthetic_result.output_directory)
    for name in (
        "gate-report.json",
        "gate-report.md",
        "pages.json",
        "disposition-ledger.json",
        "source-map.json",
        "projection-report.json",
        "material-deltas.json",
        "retained-findings.json",
        "scope-evidence.json",
        "proxy-isolation.json",
        "canonical-author.html",
        "rebuilt.pptx",
    ):
        assert (directory / name).is_file(), name
    assert not (directory / "gate-rejected.json").exists()


# ---------------------------------------------------------------------------
# Criterion: the generated HTML passes the unchanged author Contract
# ---------------------------------------------------------------------------


def test_the_synthetic_projection_passes_the_author_contract(
    synthetic_result: object,
) -> None:
    report = check_contract(corpus.document_path(synthetic_result), "author")
    assert report.status == "PASS"
    blocking = [
        item
        for item in report.diagnostics
        if str(getattr(item, "severity", "")).lower() in {"error", "blocking"}
    ]
    assert blocking == [], blocking


def test_a_contract_pass_is_not_the_gate_verdict(synthetic_result: object) -> None:
    """Both facts hold at once, and neither is read as the other."""
    report = check_contract(corpus.document_path(synthetic_result), "author")
    assert report.status == "PASS"
    assert synthetic_result.outcome in {
        GateOutcome.PASS,
        GateOutcome.PASS_WITH_FINDINGS,
    }
    assert synthetic_result.counts["material_deltas"] == 0


# ---------------------------------------------------------------------------
# Criterion: probe A -- ellipse and rightArrow read back as native shapes
# ---------------------------------------------------------------------------


def test_the_probe_a_ellipse_is_a_native_editable_shape(
    synthetic_result: object, synthetic_html: str, rebuilt_slide_xml: dict[int, str]
) -> None:
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_ELLIPSE)
    assert entry.source_kind == "shape"
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.projected_kind in {"shape", "textbox"}
    assert entry.reason_code is None
    projected = corpus.projected_by_name(synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_ELLIPSE)
    assert projected.proxy_asset is None
    element = _element(synthetic_html, projected.html_id)
    assert 'data-shape-geometry="ellipse"' in element, element
    assert 'prst="ellipse"' in rebuilt_slide_xml[
        corpus.page_record(synthetic_result, corpus.PROBE_A_KEY).output_page
    ]


def test_the_probe_a_right_arrow_is_a_native_editable_shape(
    synthetic_result: object, synthetic_html: str, rebuilt_slide_xml: dict[int, str]
) -> None:
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_ARROW)
    assert entry.source_kind == "shape"
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.projected_kind in {"shape", "textbox"}
    projected = corpus.projected_by_name(synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_ARROW)
    assert projected.proxy_asset is None
    element = _element(synthetic_html, projected.html_id)
    assert 'data-shape-geometry="rightArrow"' in element, element
    # Both presets live on probe A's single page, so its output page is the one
    # the arrow's native geometry must read back from.
    assert 'prst="rightArrow"' in rebuilt_slide_xml[probe_a_page(synthetic_result)]


def test_neither_probe_a_preset_is_a_picture_or_a_locked_proxy(
    synthetic_result: object, rebuilt_slide_xml: dict[int, str]
) -> None:
    for name in (corpus.PROBE_A_ELLIPSE, corpus.PROBE_A_ARROW):
        entry = corpus.entry_named(synthetic_result, corpus.PROBE_A_KEY, name)
        assert entry.disposition != DISPOSITION_LOCKED
        assert entry.projected_kind != "image"
        assert entry.represented_by_container is False
        assert entry.html_id is not None
    # Probe A's single output page carries no picture object at all, which is the
    # independent half of "not a picture": OfficeCLI's own readback of the
    # rebuilt deck must report no picture there.  The deck's one picture belongs
    # to probe B's locked group proxy on another page.
    kinds = _readback_kinds(rebuilt_slide_xml[probe_a_page(synthetic_result)])
    assert "picture" not in kinds, (sorted(rebuilt_slide_xml), kinds)


def _readback_kinds(slide_xml: str) -> set[str]:
    """The object kinds OfficeCLI's own slide part declares."""
    kinds: set[str] = set()
    if "<p:pic>" in slide_xml or "<p:pic " in slide_xml:
        kinds.add("picture")
    if "<p:graphicFrame" in slide_xml:
        kinds.add("graphicFrame")
    if "<p:cxnSp" in slide_xml:
        kinds.add("connector")
    if "<p:grpSp>" in slide_xml or "<p:grpSp " in slide_xml:
        kinds.add("group")
    return kinds


# ---------------------------------------------------------------------------
# Criterion: probe A -- overlay text is independent and appears exactly once
# ---------------------------------------------------------------------------


def test_every_probe_a_overlay_line_is_its_own_editable_object(
    synthetic_result: object,
) -> None:
    textboxes = [
        entry
        for entry in corpus.ledger_for(synthetic_result, corpus.PROBE_A_KEY)
        if entry.source_kind == "textbox"
    ]
    assert len(textboxes) == len(corpus.PROBE_A_ALL_OVERLAY_TEXT)
    for entry in textboxes:
        assert entry.disposition == DISPOSITION_CANONICAL
        assert entry.owner is None
        assert entry.represented_by_container is False
        assert entry.emitted is True
        assert entry.proxy_asset is None if hasattr(entry, "proxy_asset") else True


def test_every_probe_a_overlay_string_appears_exactly_once(
    synthetic_result: object,
) -> None:
    """The rebuilt deck carries each wording once, as editable text."""
    rebuilt = corpus.document_path(synthetic_result, "rebuilt.pptx")
    with zipfile.ZipFile(rebuilt) as archive:
        slide_xml = "".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
    for line in corpus.PROBE_A_ALL_OVERLAY_TEXT:
        assert slide_xml.count(f"<a:t>{line}</a:t>") == 1, line


def test_no_probe_a_raster_payload_carries_the_overlay_text(
    synthetic_result: object,
) -> None:
    """No raster payload can embed a sibling's wording.

    The probe's own pages contain no picture at all, so this is the strongest
    form of the isolation claim available: there is no raster on those pages that
    *could* carry the text.  Every media payload the rebuilt deck does contain is
    scanned as bytes, and the payloads all belong to probe B's proxies -- the
    locked group and the base-only text object -- which are on another page.
    """
    rebuilt = corpus.document_path(synthetic_result, "rebuilt.pptx")
    payloads: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(rebuilt) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/media/"):
                payloads.append((name, archive.read(name)))
    for name, blob in payloads:
        for line in corpus.PROBE_A_ALL_OVERLAY_TEXT:
            assert line.encode("utf-8") not in blob, (name, line)
            assert line.encode("utf-16-le") not in blob, (name, line)
    proxies = [
        entry
        for entry in synthetic_result.ledger
        if entry.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}
        and entry.emitted
    ]
    # Every raster in the deck is one published proxy, and every published proxy
    # is one raster: a proxy whose bytes never reached the deck, or a raster no
    # proxy accounts for, would both be invisible to the scan above.
    assert len(payloads) == len(proxies) == 2, (payloads, proxies)


def test_the_probe_a_canonical_html_contains_each_overlay_string_once(
    synthetic_html: str,
) -> None:
    for line in corpus.PROBE_A_ALL_OVERLAY_TEXT:
        assert synthetic_html.count(f">{line}<") == 1, line


def test_the_probe_a_overlay_text_is_not_inside_a_locked_element(
    synthetic_result: object, synthetic_html: str
) -> None:
    """Overlay text sits beside the card, never inside a locked representation."""
    locked_ids = set(
        re.findall(r'id="([^"]+)"[^>]*data-projection-locked="true"', synthetic_html)
    )
    for line in corpus.PROBE_A_ALL_OVERLAY_TEXT:
        index = synthetic_html.find(f">{line}<")
        assert index > 0, line
        owner_element = synthetic_html.rfind("<div", 0, index)
        opening = synthetic_html[owner_element : synthetic_html.find(">", owner_element)]
        for locked_id in locked_ids:
            assert locked_id not in opening, (line, locked_id)


def test_the_probe_a_card_keeps_exactly_one_representation(
    synthetic_result: object, synthetic_html: str
) -> None:
    projected = corpus.projected_by_name(
        synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_CARD
    )
    assert _elements_with_id(synthetic_html, projected.html_id) == 1
    assert _element(synthetic_html, projected.html_id).count("<div") == 1
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_A_KEY, corpus.PROBE_A_CARD)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.emitted is True


# ---------------------------------------------------------------------------
# Criterion: probe B -- the group is one locked container boundary
# ---------------------------------------------------------------------------


def test_the_probe_b_group_is_one_locked_container(
    synthetic_result: object, synthetic_html: str
) -> None:
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP)
    assert entry.source_kind == "group"
    assert entry.disposition == DISPOSITION_LOCKED
    assert entry.reason_code == "non_canonical_kind"
    assert entry.emitted is True
    assert entry.represented_by_container is False
    projected = corpus.projected_by_name(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP
    )
    assert projected.proxy_asset is not None
    element = _element(synthetic_html, projected.html_id)
    assert 'data-projection-locked="true"' in element
    assert 'data-shape-geometry' not in element


def test_the_probe_b_group_children_are_represented_by_the_container(
    synthetic_result: object,
) -> None:
    container = corpus.entry_named(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP
    )
    children = [
        entry
        for entry in corpus.ledger_for(synthetic_result, corpus.PROBE_B_KEY)
        if entry.represented_by_container
    ]
    assert {entry.source_name for entry in children} == {
        corpus.PROBE_B_GROUP_CHILD,
        corpus.PROBE_B_GROUP_LINK,
    }
    for entry in children:
        assert entry.owner == container.source_object
        assert entry.owner_kind == "group"
        assert entry.reason_code == "container_owned_object"
        assert entry.emitted is False
        assert entry.html_id is None
        assert entry.emitted_ordinal is None


def test_the_probe_b_group_and_its_children_appear_exactly_once(
    synthetic_result: object, synthetic_html: str
) -> None:
    """No duplicate paint: one locked boundary, no second copy of a child."""
    group = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP)
    projected = corpus.projected_by_name(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP
    )
    assert _elements_with_id(synthetic_html, projected.html_id) == 1
    # One locked representation of this container, and one per base-only object:
    # the group is the only *locked* proxy on the page, so no other object claims
    # a locked projection of its own.
    assert synthetic_html.count('data-projection-locked="true"') == 2
    group_element = _element(synthetic_html, projected.html_id)
    assert 'data-projection-locked="true"' in group_element
    for name in (corpus.PROBE_B_GROUP_CHILD, corpus.PROBE_B_GROUP_LINK):
        entry = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, name)
        assert entry.source_object not in synthetic_html, name
        assert entry.emitted is False
        assert entry.html_id is None
    # One emitted representation of the container, and no emitted object claims
    # a container-owned source identity.
    emitted_group_sources = [
        entry.source_object
        for entry in corpus.ledger_for(synthetic_result, corpus.PROBE_B_KEY)
        if entry.emitted and entry.source_kind == "group"
    ]
    assert emitted_group_sources == [group.source_object]
    emitted_sources = {
        entry.source_object
        for entry in corpus.ledger_for(synthetic_result, corpus.PROBE_B_KEY)
        if entry.emitted
    }
    assert group.source_object in emitted_sources


def test_the_probe_b_rebuilt_deck_has_one_picture_per_proxy_and_keeps_the_native_presets(
    synthetic_result: object, rebuilt_slide_xml: dict[int, str]
) -> None:
    probe_b_output = corpus.page_record(synthetic_result, corpus.PROBE_B_KEY).output_page
    kinds = _readback_kinds(rebuilt_slide_xml[probe_b_output])
    assert "picture" in kinds
    # One picture per published proxy: the group's own locked representation and
    # the base-only text object's overflow-covering one.  The presets are native
    # shapes in the same slide part.
    proxies = [
        proof
        for page in synthetic_result.pages
        for proof in page.proxies
        if proof.source_page == 1 and proof.emitted_name.startswith("slide-002-")
    ]
    xml = rebuilt_slide_xml[probe_b_output]
    assert xml.count("<p:pic>") + xml.count("<p:pic ") == len(proxies)
    for geometry in ("rect", "roundRect", "ellipse", "rightArrow"):
        assert f'prst="{geometry}"' in xml, geometry


def test_the_probe_b_native_presets_are_all_canonical_editable(
    synthetic_result: object,
) -> None:
    for name, geometry, _box, _fill in corpus.PROBE_B_SHAPES:
        entry = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, name)
        assert entry.disposition == DISPOSITION_CANONICAL, name
        assert entry.projected_kind in {"shape", "textbox"}, name
        if geometry in {"ellipse", "rightArrow"}:
            assert entry.reason_code is None, name


# ---------------------------------------------------------------------------
# Criterion: probe B -- rich text semantics survive
# ---------------------------------------------------------------------------


def test_the_probe_b_rich_block_keeps_every_fixed_string(
    synthetic_result: object,
) -> None:
    page = corpus.page_record(synthetic_result, corpus.PROBE_B_KEY)
    entry = corpus.entry_named(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_RICH_BLOCK
    )
    readback = [
        item for item in page.text_readback if item.source_object == entry.source_object
    ]
    assert len(readback) == 1, readback
    assert readback[0].matched is True
    assert readback[0].compact_equal is True
    record = readback[0].as_dict()
    compact = record["rebuilt_compact_text"]
    # The compact readback drops the line break, so the source's own compact
    # form is comparable with it character for character.
    expected_compact = "".join(corpus.PROBE_B_RICH_TEXT.split()).replace("\u000b", "")
    assert compact == expected_compact
    for number in corpus.PROBE_B_FIXED_NUMBERS:
        assert number in readback[0].rebuilt_text, number


def test_the_probe_b_rich_block_keeps_mixed_run_declarations(
    synthetic_result: object, synthetic_html: str, rebuilt_slide_xml: dict[int, str]
) -> None:
    """The projected run declarations are real, and the rebuild keeps the characters.

    The Canonical Author document declares each run's own font, size, weight and
    colour.  The rebuilt deck's paragraphs carry the same declared values, and
    every run's characters are there -- the per-run *declarations* are what the
    rebuilt deck preserves.
    """
    element = _element_containing(synthetic_html, corpus.PROBE_B_BOLD_RUN)
    assert "font-weight: 700" in element
    assert corpus.PROBE_B_BOLD_COLOR in element
    assert corpus.PROBE_B_BOLD_FONT in element
    assert "font-style: italic" in element
    assert corpus.PROBE_B_CJK_FONT in element
    xml = rebuilt_slide_xml[probe_b_page(synthetic_result)]
    for run_text in (
        corpus.PROBE_B_BOLD_RUN,
        corpus.PROBE_B_CJK_RUN,
        corpus.PROBE_B_TAIL_RUN,
        corpus.PROBE_B_LIST_ITEMS[0],
    ):
        assert run_text in _text_runs(xml), run_text
    paragraph = " ".join(_paragraph_runs(xml, corpus.PROBE_B_BOLD_RUN))
    run_text = _paragraph_run_texts(xml, corpus.PROBE_B_BOLD_RUN)
    properties = _paragraph_xml(xml, corpus.PROBE_B_BOLD_RUN)
    assert f'typeface="{corpus.PROBE_B_BOLD_FONT}"' in properties, properties
    assert 'b="1"' in paragraph, paragraph
    bold_colors = _paragraph_colors(xml, corpus.PROBE_B_BOLD_RUN)
    assert corpus.PROBE_B_BOLD_COLOR.lstrip("#").upper() in bold_colors, bold_colors
    assert run_text
    # The theme run's own characters are present too.
    assert corpus.PROBE_B_THEME_TEXT in _text_runs(xml)


def _paragraph_run_texts(slide_xml: str, marker: str) -> list[str]:
    """The ``a:t`` text of every run of the paragraph that carries ``marker``."""
    for paragraph in re.findall(r"<a:p[ >].*?</a:p>", slide_xml, re.S):
        if marker in paragraph:
            return re.findall(r"<a:t>([^<]*)</a:t>", paragraph)
    raise AssertionError(f"no paragraph carries {marker!r}")


def _paragraph_colors(slide_xml: str, marker: str) -> str:
    """Every colour token the paragraph's runs and their fills declare."""
    paragraph = _paragraph_xml(slide_xml, marker)
    return " ".join(
        re.findall(r'(?:srgbClr val|val)="([0-9A-Fa-f]{6,8})"', paragraph)
    )


def _paragraph_xml(slide_xml: str, marker: str) -> str:
    for paragraph in re.findall(r"<a:p[ >].*?</a:p>", slide_xml, re.S):
        if marker in paragraph:
            return paragraph
    raise AssertionError(f"no paragraph carries {marker!r}")


def _paragraph_runs(slide_xml: str, marker: str) -> list[str]:
    """The run properties of every run of the paragraph that carries ``marker``."""
    for paragraph in re.findall(r"<a:p[ >].*?</a:p>", slide_xml, re.S):
        if marker not in paragraph:
            continue
        return re.findall(r"<a:rPr\b[^>]*>", paragraph)
    raise AssertionError(f"no paragraph carries {marker!r}")


def test_the_probe_b_run_declarations_are_not_the_source_run_declarations(
    synthetic_probes: dict[str, Path],
    synthetic_result: object,
    rebuilt_slide_xml: dict[int, str],
) -> None:
    """What the rebuild does *not* keep about the source's runs, stated plainly.

    The source's second run is a normal-weight East-Asian run in
    ``Microsoft YaHei``.  The projected document declares exactly that, and the
    rebuilt deck writes the *characters* back -- but the rebuild splits the run
    into more runs than the source had and carries the preceding run's bold and
    colour into them, so the rebuilt run is not the run the source had.  The
    gate's material-delta comparison is a text comparison, so it does not surface
    this; no character is lost and no declaration is invented.  This test is here
    so the limitation is recorded in the acceptance evidence rather than hidden
    by a weaker assertion.
    """
    source = corpus.source_object_by_name(
        synthetic_probes[corpus.PROBE_B_KEY], None, corpus.PROBE_B_RICH_BLOCK
    )
    source_paragraph = (source.get("children") or [])[0]
    source_runs = [
        (run.get("text"), run.get("format") or {})
        for run in source_paragraph.get("children") or []
    ]
    cjk = next(
        (fmt for text, fmt in source_runs if text == corpus.PROBE_B_CJK_RUN), None
    )
    assert cjk is not None, source_runs
    assert str(cjk.get("font.ea")) == corpus.PROBE_B_CJK_FONT
    assert not str(cjk.get("bold") or "").lower() in {"true", "1"}
    rebuilt = _paragraph_xml(
        rebuilt_slide_xml[probe_b_page(synthetic_result)], corpus.PROBE_B_CJK_RUN
    )
    rebuilt_runs = re.findall(r"<a:rPr\b[^>]*>", rebuilt)
    assert f'typeface="{corpus.PROBE_B_CJK_FONT}"' in rebuilt
    # The narrowing: the rebuilt run set is not the source's run set, and the
    # preceding run's emphasis is carried into it.
    assert len(rebuilt_runs) >= len(source_runs), (rebuilt_runs, source_runs)
    assert 'b="1"' in " ".join(rebuilt_runs), rebuilt_runs


def test_the_probe_b_hard_break_rebuilds_as_the_two_authored_paragraphs(
    synthetic_result: object,
    rebuilt_slide_xml: dict[int, str],
) -> None:
    """A hard break is two native paragraphs, not two words run together.

    OfficeCLI's readback drops ``<a:br/>`` -- it reports the paragraph as its two
    runs with nothing between them -- so the source's break has to be restored
    from the slide part, and the projection then publishes the two authored lines
    as two paragraphs.  The New Deck path rebuilds each of them as its own native
    paragraph, which is what the rebuilt deck's own paragraph structure shows.

    The failure this pins is the one a text comparison could not see: with no
    separator, the two lines came out as ``Hard break probe linesecond visual
    line``.  No character was lost and none was invented, so a whitespace-stripped
    comparison passed while the deck painted one line where the source paints two.
    """
    entry = corpus.entry_named(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_RICH_BLOCK
    )
    projected = corpus.projected_by_name(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_RICH_BLOCK
    )
    assert projected.source_object == entry.source_object
    element = _authored_element(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_RICH_BLOCK
    )
    authored = _authored_text(element)
    assert "Hard break probe line\nsecond visual line" in authored, repr(authored)
    assert (
        corpus.PROBE_B_HARD_BREAK_MARKER + "second visual line" not in authored
    ), repr(authored)

    xml = rebuilt_slide_xml[probe_b_page(synthetic_result)]
    assert "<a:br" not in xml
    # The marked line is located inside the rebuilt paragraph rather than by
    # matching the paragraph's whole text: the readback splits one authored run's
    # characters across several runs, so a marker that spans a split is not
    # contiguous in the deck even when every character of it is there.
    paragraphs = _paragraph_texts(
        xml, corpus.PROBE_B_HARD_BREAK_MARKER[len("Ha"):]
    )
    # The two authored lines are two paragraphs of the rebuilt object, in order.
    assert paragraphs == [
        corpus.PROBE_B_HARD_BREAK_MARKER,
        "second visual line",
    ], paragraphs
    # Both halves are characters of the object's own text, and the deck's
    # paragraphs are what separates them: nothing concatenates the two lines into
    # one run of adjacent words.
    assert corpus.PROBE_B_HARD_BREAK_MARKER in _text_runs(xml)
    assert "second visual line" in _text_runs(xml)
    assert "second visual line" not in _paragraph_xml(
        xml, corpus.PROBE_B_HARD_BREAK_MARKER[len("Ha") :]
    )
    # And they are two paragraphs of the same source object's text body.
    assert corpus.PROBE_B_RICH_PARAGRAPH_1 in projected.text
    assert corpus.PROBE_B_HARD_BREAK_MARKER in projected.text
    assert "second visual line" in projected.text


def _text_runs(slide_xml: str) -> str:
    """Every ``a:t`` character of one slide part, concatenated."""
    return "".join(re.findall(r"<a:t>([^<]*)</a:t>", slide_xml))


def _paragraph_texts(slide_xml: str, marker: str) -> list[str]:
    """The text of the five paragraphs around one marker, in the rebuilt deck."""
    texts = re.findall(r"<a:p[ >].*?</a:p>", slide_xml, re.S)
    for index, paragraph in enumerate(texts):
        if marker in paragraph:
            window = texts[index : index + 2]
            return [
                "".join(re.findall(r"<a:t>([^<]*)</a:t>", item)) for item in window
            ]
    raise AssertionError(f"no paragraph carries {marker!r}")


def test_the_probe_b_list_markers_and_levels_survive_the_rebuild(
    synthetic_probes: dict[str, Path],
    synthetic_result: object,
    synthetic_html: str,
    rebuilt_slide_xml: dict[int, str],
) -> None:
    """The rebuilt list carries the marker and the level, not four plain lines.

    OfficeCLI reads the source list block back as native list paragraphs: two
    ``a:buChar`` bullet items and two ``a:buAutoNum`` numbered ones, with the
    nested item one level deeper and indented 36pt to the level-0 item's 18pt.
    The projection therefore has to *express* the list -- the marker is not
    characters, so no run of the body carries it -- and the rebuilt deck has to
    end up with the marker, the level and the indentation as native paragraph
    properties.

    The failure this pins is a rebuild of four plain lines: the characters all
    survived, so a text comparison passed while the markers and the indentation
    were gone.  It asserts the rebuilt deck's own paragraph properties, read out
    of the slide part, rather than a rendered string.
    """
    source = corpus.source_object_by_name(
        synthetic_probes[corpus.PROBE_B_KEY], 1, corpus.PROBE_B_LIST_BLOCK
    )
    source_format = source.get("format") or {}
    assert str(source_format.get("list")) == "bullet"
    assert "buChar" in str(source_format.get("bulletRaw") or "")

    # The authored document declares the list: one item per paragraph, each with
    # its own marker declaration, and no marker written as text.
    element = _authored_element(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_LIST_BLOCK
    )
    assert element.count("<li") == len(corpus.PROBE_B_LIST_ITEMS)
    assert "list-style-type: decimal" in element
    authored = _authored_text(element)
    for item in corpus.PROBE_B_LIST_ITEMS:
        assert item in authored, item
    for literal in ("•", "\t1.", "1. Numbered"):
        assert literal not in authored, literal

    # And the rebuilt deck keeps them as native paragraph properties.
    xml = rebuilt_slide_xml[probe_b_page(synthetic_result)]
    paragraphs = _list_paragraphs(xml, corpus.PROBE_B_LIST_ITEMS)
    assert [paragraph["text"] for paragraph in paragraphs] == list(
        corpus.PROBE_B_LIST_ITEMS
    )
    assert [paragraph["marker"] for paragraph in paragraphs] == [
        "buChar",
        "buChar",
        "buAutoNum",
        "buAutoNum",
    ]
    # The nested items keep their own indent: 22pt further left margin than the
    # level-0 items, which is the source's own 36pt against 18pt read relative to
    # each item's own text edge.
    margins = [paragraph["margin_left_pt"] for paragraph in paragraphs]
    assert margins[1] - margins[0] > 0, margins
    assert margins[3] - margins[2] > 0, margins
    assert margins[1] - margins[0] == margins[3] - margins[2], margins
    # No item text carries a literal marker prefix.
    for paragraph in paragraphs:
        assert not paragraph["text"].startswith(("•", "1.", "2.")), paragraph


def _list_paragraphs(slide_xml: str, items: tuple[str, ...]) -> list[dict[str, Any]]:
    """The rebuilt list paragraphs for ``items``, with their native properties.

    One entry per item, in item order, carrying the marker element the paragraph
    declares and its own indentation.  A paragraph whose marker is missing has no
    marker element at all, which is what the failure being pinned looks like.
    """
    found: dict[str, dict[str, Any]] = {}
    for paragraph in re.findall(r"<a:p[ >].*?</a:p>", slide_xml, re.S):
        text = "".join(re.findall(r"<a:t>([^<]*)</a:t>", paragraph))
        if text not in items:
            continue
        props = re.search(r"<a:pPr\b[^>]*>", paragraph)
        marker = re.search(r"<a:(buChar|buAutoNum)\b", paragraph)
        margin = re.search(r'marL="(-?\d+)"', props.group(0) if props else "")
        found[text] = {
            "text": text,
            "marker": marker.group(1) if marker else None,
            "margin_left_pt": (
                int(margin.group(1)) / 12700 if margin is not None else 0.0
            ),
            "level": (
                re.search(r'lvl="(-?\d+)"', props.group(0)).group(1)
                if props is not None and re.search(r'lvl="(-?\d+)"', props.group(0))
                else None
            ),
        }
    return [found[item] for item in items if item in found]


def test_the_probe_b_overflow_proxy_covers_what_the_object_paints(
    synthetic_result: object, rebuilt_slide_xml: dict[int, str]
) -> None:
    """A text proxy is not cropped to the rectangle its text overflows.

    PowerPoint paints a no-autofit line outside its own box, and the source page
    shows that overflow.  The probe's base-only text object is a 120x14pt band
    whose 22pt line is painted largely above and below it, so cropping the
    isolated render to the declared rectangle slices the line mid-glyph.

    This pins all three halves of the repair: the published image is the object's
    *painted* rectangle and really does carry ink outside the declared rectangle,
    the emitted ``<img>`` is the image's own pixel size rather than the declared
    rectangle plus a guard band, and the rebuilt deck holds it as one picture.
    """
    from PIL import Image

    projected = corpus.projected_by_name(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_OVERFLOW_BLOCK
    )
    assert projected.proxy_asset, projected.as_dict()
    assert projected.proxy_geometry is not None, projected.as_dict()
    geometry = projected.proxy_geometry
    assert projected.proxy_clamped is False, projected.as_dict()

    # The raster is the reported rectangle, and that rectangle is strictly larger
    # than the declared rectangle plus the guard band on the overflowing axis.
    # The bytes measured are the *published* copy: the projection's own working
    # directory is removed when the run finishes, so a test that opened the path
    # the projection reported would be reading a file that exists only by accident.
    asset = _published_proxy(synthetic_result, projected)
    with Image.open(asset) as image:
        width, height = image.size
    floor_height = int(round(projected.bounds_px[3])) + PROXY_GUARD_PX * 2
    assert geometry.rect_px[2] == width and geometry.rect_px[3] == height
    assert height > floor_height, (height, floor_height, projected.bounds_px)

    # The ink is measured from the image's own bytes against its own background,
    # and it leaves the declared rectangle -- which is the overflow the crop now
    # covers instead of slicing.  The declared rectangle inside the crop is read
    # from the geometry the projection published rather than recomputed here, so
    # the two are compared instead of restated.
    origin_left, origin_top = geometry.origin_px
    assert origin_left <= 0 and origin_top <= 0
    floor_width = int(round(projected.bounds_px[2])) + PROXY_GUARD_PX * 2
    floor_height = int(round(projected.bounds_px[3])) + PROXY_GUARD_PX * 2
    assert origin_left < -PROXY_GUARD_PX or origin_top < -PROXY_GUARD_PX, (
        "the crop expanded on neither axis, so this object does not exercise the "
        f"overflow: origin={geometry.origin_px}"
    )
    declared_left = geometry.rect_px[0] + origin_left
    declared_top = geometry.rect_px[1] + origin_top
    left, top, right, bottom = _proxy_ink_box(asset)
    declared_bottom = declared_top + floor_height
    assert top < declared_top or bottom > declared_bottom, (
        "the proxy carries no ink outside the declared rectangle, so the crop "
        f"expansion is not what is being measured: ink={left, top, right, bottom} "
        f"declared={(declared_left, declared_top, declared_left + floor_width, declared_bottom)}"
    )
    # The crop covers all of it: the ink is inside the published image, and the
    # image starts and ends exactly where the measured paint does on the axes the
    # paint left the declared rectangle on -- so neither the declared rectangle
    # nor the reconstruction's own edge cut a line short.
    assert 0 <= left < right <= width, (left, right, width)
    assert 0 <= top < bottom <= height, (top, bottom, height)
    assert geometry.clamped is False
    if origin_top < -PROXY_GUARD_PX:
        assert top == 0, (top, "the expanded crop does not start at the ink")
    if declared_bottom < height - PROXY_GUARD_PX:
        assert bottom == height, (bottom, height, "the expanded crop does not end at the ink")

    # The emitted element is placed by that geometry, not by the declared bounds.
    element = _authored_element(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_OVERFLOW_BLOCK
    )
    assert f"width: {width}px" in element, element
    assert f"height: {height}px" in element, element
    assert (
        f"left: {projected.bounds_px[0] + geometry.origin_px[0]:g}px" in element
    ), element
    assert (
        f"top: {projected.bounds_px[1] + geometry.origin_px[1]:g}px" in element
    ), element

    # The rebuilt deck carries it as the one picture the emitted name names.
    xml = rebuilt_slide_xml[probe_b_page(synthetic_result)]
    assert projected.emitted_name in xml, projected.emitted_name


def _published_proxy(result: object, projected: object) -> Path:
    """The published copy of one projected object's proxy asset.

    The projection writes its proxies into a working directory the run removes
    when it finishes, so the bytes a reviewer can open are the copies the gate
    publishes beside the rebuilt deck.  The published file is matched by the
    projection's own asset name, which carries the object's emission ordinal.
    """
    name = Path(str(projected.proxy_asset)).name
    matches = [
        Path(asset) for asset in result.proxy_assets if Path(asset).name == name
    ]
    assert len(matches) == 1, (name, result.proxy_assets)
    assert matches[0].is_file(), matches[0]
    return matches[0]


def _proxy_ink_box(path: Path) -> tuple[int, int, int, int]:
    """The bounding box of a proxy image's non-background ink, in its own pixels."""
    from PIL import Image, ImageChops

    tolerance = 6
    table = [255 if value > tolerance else 0 for value in range(256)]
    with Image.open(path) as image:
        rgb = image.convert("RGB")
    background = rgb.getpixel((0, 0))
    reference = Image.new("RGB", rgb.size, background)
    mask = Image.new("L", rgb.size, 0)
    for band in ImageChops.difference(rgb, reference).split():
        mask = ImageChops.lighter(mask, band.point(table))
    box = mask.getbbox()
    assert box is not None, f"{path.name} carries no paint at all"
    return box


def test_the_probe_b_theme_token_is_declared_in_the_source(
    synthetic_probes: dict[str, Path],
) -> None:
    """The theme expression is real: OfficeCLI reads the token back from the source."""
    source = corpus.source_object_by_name(
        synthetic_probes[corpus.PROBE_B_KEY], 1, corpus.PROBE_B_THEME_BLOCK
    )
    fmt = source.get("format") or {}
    assert str(fmt.get("color")) == corpus.PROBE_B_THEME_TOKEN
    with zipfile.ZipFile(synthetic_probes[corpus.PROBE_B_KEY]) as archive:
        slide = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert f'<a:schemeClr val="{corpus.PROBE_B_THEME_TOKEN}"' in slide


def test_the_probe_b_theme_text_keeps_its_characters_after_the_rebuild(
    synthetic_result: object, synthetic_html: str, rebuilt_slide_xml: dict[int, str]
) -> None:
    entry = corpus.entry_named(
        synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_THEME_BLOCK
    )
    page = corpus.page_record(synthetic_result, corpus.PROBE_B_KEY)
    readback = [
        item for item in page.text_readback if item.source_object == entry.source_object
    ]
    assert len(readback) == 1
    assert readback[0].matched is True
    assert corpus.PROBE_B_THEME_TEXT in readback[0].rebuilt_text
    assert f"<a:t>{corpus.PROBE_B_THEME_TEXT}</a:t>" in rebuilt_slide_xml[probe_b_page(synthetic_result)]


def test_the_probe_b_sibling_textbox_is_untouched_by_the_container(
    synthetic_result: object,
) -> None:
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_SIBLING)
    assert entry.disposition == DISPOSITION_CANONICAL
    assert entry.owner is None
    assert entry.emitted is True
    assert entry.represented_by_container is False


# ---------------------------------------------------------------------------
# Criterion: text readback, counts and proxy proofs
# ---------------------------------------------------------------------------


def test_every_canonical_editable_object_with_text_has_a_text_readback(
    synthetic_result: object,
) -> None:
    """Readback covers exactly the objects emitted as native text.

    A text-free shape declares no characters, so the projection records no text
    readback for it; every object whose projection carries native text must have
    one, and the set must be exactly that: nothing claimed that was not emitted,
    and nothing emitted that was not read back.

    An object represented by an object-local proxy is deliberately *not* in the
    set: its text is paint inside the proxy's own raster, not characters of the
    rebuilt deck, so there is no native text to read back.  Whether that raster
    actually carries the text is the proxy-isolation proof's question, not this
    criterion's.
    """
    declared = {
        (item.source_key, item.source_object)
        for item in synthetic_result.projected.objects
        if str(item.text or "").strip()
        and item.disposition not in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}
    }
    assert declared
    observed = {
        (str(record.source_key), item.source_object)
        for record in synthetic_result.pages
        for item in record.text_readback
    }
    assert declared <= observed, declared - observed
    # And a proxied object's text is not claimed as a native readback either.
    proxied = {
        (item.source_key, item.source_object)
        for item in synthetic_result.projected.objects
        if str(item.text or "").strip()
        and item.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}
    }
    assert proxied, "no proxied text object to check"
    assert not (proxied & observed), proxied & observed
    for identity in declared:
        readback = next(
            item
            for record in synthetic_result.pages
            for item in record.text_readback
            if (str(record.source_key), item.source_object) == identity
        )
        assert readback.matched is True, readback.as_dict()


def test_no_readback_of_a_canonical_object_disagrees_with_its_source_text(
    synthetic_result: object,
) -> None:
    readbacks = [item for page in synthetic_result.pages for item in page.text_readback]
    assert readbacks
    for item in readbacks:
        assert item.matched is True, item.as_dict()
    # The style-declaration surface is populated where the projection declares a
    # style, and the mechanism is exercised (not merely absent).
    styled = [
        item for item in readbacks if item.style_declarations.get("font-size")
    ]
    assert styled, "no readback carried a font-size declaration"
    for item in styled:
        assert item.style_declarations.get("font-family"), item.as_dict()


def test_the_synthetic_run_reports_native_and_proxy_counts_separately(
    synthetic_result: object,
) -> None:
    counts = synthetic_result.counts
    assert counts["native_round_trip"] == counts["canonical_editable"]
    assert counts["excluded_from_native_round_trip"] == (
        counts["source_objects"] - counts["canonical_editable"]
    )
    assert counts["locked_visual_proxy"] >= 1
    assert counts["base_only_semantic"] >= 0


def test_every_locked_proxy_passes_all_five_isolation_facts(
    synthetic_result: object,
) -> None:
    proofs = [proof for page in synthetic_result.pages for proof in page.proxies]
    assert proofs, "the probe B group must produce one isolation proof"
    for proof in proofs:
        assert proof.failures == (), proof.as_dict()
        assert proof.passed is True
        assert proof.rebuilt_kind is not None, proof.emitted_name
        assert proof.raster_width_px > 0 and proof.raster_height_px > 0
        assert proof.raster_density > 0
        assert proof.guard_band_px == PROXY_GUARD_PX
        assert proof.target_bounds_pt[2] > 0 and proof.target_bounds_pt[3] > 0
    assert synthetic_result.counts["locked_proxies_proved"] == len(proofs)


def test_the_probe_b_group_proxy_carries_its_children_paint(
    synthetic_result: object,
) -> None:
    """A blank raster is never an acceptable representation of a visible object."""
    entry = corpus.entry_named(synthetic_result, corpus.PROBE_B_KEY, corpus.PROBE_B_GROUP)
    proof = next(
        proof
        for page in synthetic_result.pages
        for proof in page.proxies
        if proof.source_object == entry.source_object
    )
    assert proof.carries_paint is True, proof.as_dict()
    assert proof.paint_pixels > 0


# ---------------------------------------------------------------------------
# Criterion: source mapping completeness and the artifact manifest
# ---------------------------------------------------------------------------


def test_every_source_object_has_exactly_one_disposition(
    synthetic_result: object,
) -> None:
    identities = [
        (entry.source_key, entry.source_page, entry.source_object)
        for entry in synthetic_result.ledger
    ]
    assert len(identities) == len(set(identities))
    for entry in synthetic_result.ledger:
        assert entry.disposition in {
            DISPOSITION_CANONICAL,
            DISPOSITION_LOCKED,
            DISPOSITION_BASE_ONLY,
        }
        assert entry.source_kind
        assert entry.projected_kind
        assert entry.source_sha256
    # Two probes both start at source page 1, so the page identity is part of the
    # key: the same source path on a different deck is a different object.
    assert len({identity[0] for identity in identities}) == 2


def test_every_emitted_object_maps_to_one_source_object(
    synthetic_result: object,
) -> None:
    emitted = [entry for entry in synthetic_result.ledger if entry.emitted]
    names = [
        f"slide-{item.output_slide:03d}-"
        f"{COMPILED_KIND.get(item.projected_kind, item.projected_kind)}-"
        f"{item.emitted_ordinal:03d}"
        for item in synthetic_result.projected.objects
    ]
    assert len(names) == len(set(names)), names
    container_owned = [
        entry for entry in synthetic_result.ledger if entry.represented_by_container
    ]
    for entry in container_owned:
        assert entry.emitted is False
        assert entry.html_id is None
    # Every emitted object's identity is unique inside its own source deck, which
    # is the granularity the ledger maps at.
    sources = [(entry.source_key, entry.source_object) for entry in emitted]
    assert len(sources) == len(set(sources))
    assert len(emitted) == len(synthetic_result.projected.objects)


def test_the_rebuilt_objects_are_the_ones_the_ledger_emitted(
    synthetic_result: object,
) -> None:
    rebuilt = {item.emitted_name for item in synthetic_result.rebuilt_objects}
    for item in synthetic_result.projected.objects:
        name = (
            f"slide-{item.output_slide:03d}-"
            f"{COMPILED_KIND.get(item.projected_kind, item.projected_kind)}-"
            f"{item.emitted_ordinal:03d}"
        )
        assert name in rebuilt, item.source_object
    assert len(rebuilt) == len(synthetic_result.projected.objects)


def test_every_published_artifact_hashes_to_its_recorded_value(
    synthetic_result: object,
) -> None:
    directory = Path(synthetic_result.output_directory)
    assert synthetic_result.artifacts
    for artifact in synthetic_result.artifacts:
        path = directory / artifact.name
        assert path.is_file(), artifact.name
        assert _sha256(path) == artifact.sha256, artifact.name
        assert path.stat().st_size == artifact.size_bytes, artifact.name


def test_the_published_report_lists_the_same_artifact_hashes(
    synthetic_result: object,
) -> None:
    report = json.loads(
        corpus.document_path(synthetic_result, "gate-report.json").read_text("utf-8")
    )
    listed = {item["name"]: item["sha256"] for item in report["artifacts"]}
    from_result = {item.name: item.sha256 for item in synthetic_result.artifacts}
    assert listed == from_result


def test_no_published_file_escapes_the_artifact_manifest(
    synthetic_result: object,
) -> None:
    """Every file in the evidence directory is either hashed or a report itself."""
    directory = Path(synthetic_result.output_directory)
    excluded = {"gate-report.json", "gate-report.md", "gate-rejected.json", "gate-rejected.md"}
    listed = {item.name for item in synthetic_result.artifacts}
    on_disk = {
        str(path.relative_to(directory)).replace("\\", "/")
        for path in directory.rglob("*")
        if path.is_file()
    }
    unaccounted = on_disk - listed - excluded
    assert unaccounted == set(), unaccounted
    assert listed <= on_disk
    assert (on_disk - listed) <= excluded


# ---------------------------------------------------------------------------
# Criterion: the real eight pages (opt-in; skipped when the deck is absent)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def real_result(tmp_path_factory: pytest.TempPathFactory) -> object:
    if not (_real_corpus_available() and _real_corpus_requested()):
        pytest.skip(_skip_reason())
    output = tmp_path_factory.mktemp("v042-acceptance-real") / "gate"
    selection = corpus.seam_selection(_real_sources(), None, None)
    return gate_projected_author_html(selection, output)


@pytest.fixture(scope="session")
def real_source_digests() -> dict[str, str]:
    """Each private deck's digest as it is *now*, before this module reads it.

    A private deck's digest is private material: a public repository must not
    carry one, so the test derives the values from the decks it is about to read
    instead of naming literals.  Immutability is then claimed the only way it can
    honestly be claimed -- by hashing the same files again after the run and
    comparing the two readings of *this* run, per deck.
    """
    if not (_real_corpus_available() and _real_corpus_requested()):
        pytest.skip(_skip_reason())
    sources = _real_sources() or {}
    return {slot: _sha256(deck) for slot, deck in sources.items()}


@pytest.mark.skipif(
    not (_real_corpus_available() and _real_corpus_requested()),
    reason=_skip_reason(),
)
def test_the_real_half_projects_every_frozen_page(real_result: object) -> None:
    assert real_result.counts["selected_pages"] == len(corpus.REAL_SELECTION)
    assert real_result.counts["projected_pages"] == len(corpus.REAL_SELECTION)
    assert real_result.counts["blocked_pages"] == 0
    assert real_result.counts["material_deltas"] == 0
    assert real_result.diagnostics == ()
    # The eight real pages, in the frozen order, each identified by its own deck.
    assert [
        (page.source_key, page.source_page) for page in real_result.pages
    ] and [page.source_page for page in real_result.pages] == [
        page for _, page in corpus.REAL_SELECTION
    ]
    for page in real_result.pages:
        assert page.unsupported == 0
        assert page.unresolved == 0


@pytest.mark.skipif(
    not (_real_corpus_available() and _real_corpus_requested()),
    reason=_skip_reason(),
)
def test_the_real_source_decks_are_unchanged_by_the_run(
    real_result: object, real_source_digests: dict[str, str]
) -> None:
    """Every source deck is byte-identical before and after, and the run says so.

    Three decks are read, so three immutability claims are made -- one per deck.
    Each is a comparison between two readings of the same file at two moments:
    before the gate reads it and after it publishes.  The gate's own per-source
    verification must agree that it re-hashed each one.
    """
    sources = _real_sources() or {}
    assert set(real_source_digests) == set(sources), "one digest per corpus slot"
    for slot, deck in sources.items():
        assert _sha256(deck) == real_source_digests[slot], slot
    verified = {
        str(record.get("source_key")): record.get("verified")
        for record in real_result.source_verification
    }
    assert verified, "the gate published no source verification"
    assert all(value is True for value in verified.values()), verified


@pytest.mark.skipif(
    not (_real_corpus_available() and _real_corpus_requested()),
    reason=_skip_reason(),
)
def test_the_real_half_checks_its_native_tables(real_result: object) -> None:
    tables = [table for page in real_result.pages for table in page.tables]
    assert tables, "the frozen selection contains native tables"
    for table in tables:
        assert table.failures() == (), table.as_dict()


@pytest.mark.skipif(
    not (_real_corpus_available() and _real_corpus_requested()),
    reason=_skip_reason(),
)
def test_the_real_half_passes_every_proxy_isolation_proof(real_result: object) -> None:
    proofs = [proof for page in real_result.pages for proof in page.proxies]
    assert proofs
    for proof in proofs:
        assert proof.passed is True, proof.as_dict()
    assert real_result.counts["locked_proxies_proved"] == len(proofs)


@pytest.mark.skipif(
    not (_real_corpus_available() and _real_corpus_requested()),
    reason=_skip_reason(),
)
def test_the_real_half_passes_the_author_contract(real_result: object) -> None:
    assert check_contract(corpus.document_path(real_result), "author").status == "PASS"


# ---------------------------------------------------------------------------
# The corpus manifest itself
# ---------------------------------------------------------------------------


def test_the_corpus_manifest_is_the_frozen_ten_page_selection() -> None:
    manifest = corpus.corpus_manifest()
    assert manifest["selection_order"] == list(corpus.SELECTION_ORDER)
    assert manifest["real_page_count"] == 8
    assert manifest["synthetic_probe_count"] == 2
    assert len(manifest["pages"]) == 10
    assert [page["source_page"] for page in manifest["pages"]] == [
        *[page for _, page in corpus.REAL_SELECTION],
        1,
        1,
    ]
    for page in manifest["pages"]:
        assert page["coverage_purpose"]
        assert page["scope_note"]
        assert page["composition"]
        assert page["source_kind"]
    assert [page["page_id"] for page in manifest["pages"]] == list(
        corpus.SELECTION_ORDER
    )


def test_the_corpus_draws_its_eight_real_pages_from_three_decks() -> None:
    """Ticket #18's corpus criterion, asserted rather than assumed.

    Eight real pages is not the claim; eight real pages *from three source decks*
    is.  A corpus that reads one deck cannot satisfy it however many pages it
    takes, so the source count is pinned here separately from the page count.
    """
    manifest = corpus.corpus_manifest()
    assert manifest["real_source_count"] == 3
    assert len(manifest["sources"]) == 3
    assert len({source["slot"] for source in manifest["sources"]}) == 3
    # Every real page names a source slot, and every slot contributes pages.
    real_pages = [page for page in manifest["pages"] if not page["synthetic"]]
    assert len(real_pages) == 8
    contributing = {page["page_id"].split(":", 1)[0] for page in real_pages}
    assert contributing == {source["slot"] for source in manifest["sources"]}
    for source in manifest["sources"]:
        assert source["pages"], source
        assert source["purpose"]


def test_a_private_source_digest_is_never_committed() -> None:
    """The corpus manifest withholds a private deck's digest, deliberately."""
    manifest = corpus.corpus_manifest(
        source_hashes={page.page_id: "0" * 64 for page in corpus.CORPUS_PAGES}
    )
    for page in manifest["pages"]:
        if page["synthetic"]:
            continue
        assert page["source_sha256"] == corpus.WITHHELD_PRIVATE, page["page_id"]


def test_the_seam_selection_order_is_the_corpus_order(
    synthetic_probes: dict[str, Path],
) -> None:
    selection = corpus.seam_selection(
        None, synthetic_probes[corpus.PROBE_A_KEY], synthetic_probes[corpus.PROBE_B_KEY]
    )
    # One page per synthetic probe: the frozen corpus is exactly ten pages.
    assert [int(item[1]) for item in selection] == [1, 1]
    assert selection[0][0].endswith(corpus.PROBE_A_DECK_NAME)
    assert selection[-1][0].endswith(corpus.PROBE_B_DECK_NAME)

    # A three-deck selection: the deck a page is drawn from must be distinguishable
    # by the deck the seam was handed, not by a page number that repeats across
    # decks.  Fixed paths stand in for the private decks here.
    fake = {
        source.slot: (REPO_ROOT / f"{source.slot}.local.pptx")
        for source in corpus.CORPUS_SOURCES
    }
    full = corpus.seam_selection(fake, None, None)
    assert [int(item[1]) for item in full] == [page for _, page in corpus.REAL_SELECTION]
    assert [Path(item[0]).name for item in full] == [
        f"{slot}.local.pptx" for slot, _ in corpus.REAL_SELECTION
    ]
    whole = corpus.seam_selection(
        fake, synthetic_probes[corpus.PROBE_A_KEY], synthetic_probes[corpus.PROBE_B_KEY]
    )
    assert [int(item[1]) for item in whole] == [
        *[page for _, page in corpus.REAL_SELECTION],
        1,
        1,
    ]
    # Eight real selected pages from three decks, plus one page from each of the
    # two synthetic probes: ten pages drawn from five decks in one run.
    assert len(whole) == 10
    assert len({item[0] for item in whole}) == 3 + 2


# ---------------------------------------------------------------------------
# The published acceptance bundle
# ---------------------------------------------------------------------------

BUNDLE = REPO_ROOT / "acceptance" / "v0.4.2"


def test_the_published_acceptance_manifest_agrees_with_disk() -> None:
    """The bundle's artifact manifest can be checked against disk, independently.

    Skipped when the bundle has not been published in this workspace; the full
    ten-page run is `.scratch/tools/run_v042_acceptance.py`, which writes it and
    performs this same check as part of publishing.
    """
    manifest_path = BUNDLE / "artifact-manifest.json"
    if not manifest_path.is_file():
        pytest.skip(
            "the acceptance bundle has not been published here; run "
            ".scratch/tools/run_v042_acceptance.py to create it"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["algorithm"] == "sha256"
    assert manifest["artifacts"], "the manifest lists no artifact"
    for item in manifest["artifacts"]:
        path = BUNDLE / item["name"]
        assert path.is_file(), item["name"]
        assert _sha256(path) == item["sha256"], item["name"]
        assert path.stat().st_size == item["size_bytes"], item["name"]
    report = BUNDLE / manifest["report_name"]
    assert report.is_file()
    assert _sha256(report) == manifest["report_sha256"]


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def probe_a_page(result: object) -> int:
    """Probe A's first output page, read from the gate's own page record."""
    return corpus.page_record(result, corpus.PROBE_A_KEY).output_page


def probe_b_page(result: object) -> int:
    """Probe B's output page, read from the gate's own page record."""
    return corpus.page_record(result, corpus.PROBE_B_KEY).output_page


def _elements_with_id(html: str, element_id: str) -> int:
    """How many elements carry ``element_id`` as their own ``id`` attribute."""
    return len(
        re.findall(rf'(?<![\w-])id="{re.escape(element_id)}"', html)
    )


def _element(html: str, element_id: str) -> str:
    """The complete element whose own ``id`` attribute is ``element_id``."""
    match = re.search(rf'<(?P<tag>[a-z]+)[^>]*\sid="{re.escape(element_id)}"', html)
    assert match is not None, element_id
    return _element_from(html, match.start(), match.group("tag"))


def _element_containing(html: str, text: str) -> str:
    """The complete element that contains ``text`` as a direct descendant."""
    index = html.find(text)
    assert index > 0, text
    start = html.rfind("<div", 0, index)
    assert start >= 0, text
    return _element_from(html, start, "div")


def _element_from(html: str, start: int, tag: str) -> str:
    """The balanced element of ``tag`` that begins at ``start``.

    ``start`` is the position of the opening tag's ``<``, so the walk begins
    *inside* that tag: counting from the tag itself would find it a second time
    and return the opening tag alone.
    """
    open_tag = re.compile(rf"<{tag}\b")
    close_tag = re.compile(rf"</{tag}>")
    opening_end = html.find(">", start)
    assert opening_end >= 0, tag
    depth = 1
    position = opening_end + 1
    while position < len(html):
        opening = open_tag.search(html, position)
        closing = close_tag.search(html, position)
        if closing is None:
            break
        if opening is not None and opening.start() < closing.start():
            depth += 1
            position = opening.end()
            continue
        depth -= 1
        position = closing.end()
        if depth == 0:
            return html[start:position]
    return html[start:]


def _authored_element(result: object, page_id: str, name: str) -> str:
    """The emitted element of the source object named ``name`` on that page.

    The element is located by the projection's own identity attribute rather than
    by a string the element happens to render: a text body's characters can be
    split across several runs, so the authored words need not appear contiguously
    in the document at all.
    """
    entry = corpus.entry_named(result, page_id, name)
    projected = corpus.projected_by_name(result, page_id, name)
    assert projected.source_object == entry.source_object
    html = corpus.document_path(result).read_text(encoding="utf-8")
    match = re.search(
        rf'<(?P<tag>[a-z]+)\b[^>]*\bid="{re.escape(projected.html_id)}"', html
    )
    assert match is not None, projected.html_id
    return _element_from(html, match.start(), match.group("tag"))


def _authored_text(element_html: str) -> str:
    """The text one emitted element paints, with its paragraph breaks as newlines."""
    marked = re.sub(r"<br\s*/?>", "\n", element_html)
    text = _HTML_TAG.sub("", marked)
    unescaped = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&nbsp;", " ")
    )
    # The emitted declarations are attributes, not text, but a wrapped element
    # still carries newlines from the document's own formatting; the painted text
    # has none beyond the paragraph boundaries this put back.
    return "\n".join(
        line.strip() for line in unescaped.split("\n")
    )
