"""The frozen V0.4.2 representative acceptance corpus (ticket #18).

This module is the corpus's own definition, not a test: it names the ten pages in
their frozen selection order, records every page's provenance, coverage purpose
and page-level scope note, and builds the two synthetic probes deterministically
through OfficeCLI.

It is importable by both halves of ticket #18 -- ``tests/test_v042_acceptance.py``
and the scripted acceptance run under ``.scratch/tools/`` -- so the corpus the
test asserts and the corpus the acceptance run publishes cannot drift apart.

The eight real pages are selected from one private business deck.  Only their
page numbers, composition and coverage purpose are recorded here; the deck, its
name, its path, its hash and its content stay outside the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# The frozen selection
# ---------------------------------------------------------------------------

CORPUS_SCHEMA_VERSION = 2

#: How many real source decks the frozen corpus draws pages from.  Ticket #18
#: requires eight real selected pages from *three* source decks, so a corpus that
#: reads one deck does not satisfy it however many pages it takes.
REAL_SOURCE_COUNT = 3


@dataclass(frozen=True)
class CorpusSource:
    """One real source deck of the frozen corpus, named by an opaque slot.

    The slot is what the committed corpus text and the public evidence use.  The
    deck itself -- its filename, its absolute path and its digest -- is supplied
    at run time by local configuration, so the repository never carries it.  See
    :func:`resolve_sources`.
    """

    slot: str
    pages: tuple[int, ...]
    purpose: str

    def as_dict(self) -> dict[str, Any]:
        return {"slot": self.slot, "pages": list(self.pages), "purpose": self.purpose}


#: The frozen three-deck selection.  Slot names are opaque on purpose: a slot is
#: a corpus position, not a business document.
CORPUS_SOURCES: tuple[CorpusSource, ...] = (
    CorpusSource(
        slot="source-a",
        pages=(2, 5, 12, 30),
        purpose=(
            "complex real composition: groups with owned connectors, theme-token "
            "text, an overlay KPI arrangement, a cropped compound product picture, "
            "a text-dense control page, and the highest object count in the corpus"
        ),
    ),
    CorpusSource(
        slot="source-b",
        pages=(3, 9),
        purpose=(
            "repeated cards with transparent pictures and several native tables, "
            "plus a picture group against an opaque panel -- the container case "
            "that is not the same risk as a cropped picture"
        ),
    ),
    CorpusSource(
        slot="source-c",
        pages=(2, 21),
        purpose=(
            "the negative control for machine-only evidence: a page whose "
            "structural issues read clean while the source picture already shows a "
            "title overlap, and a wide native table isolated from picture noise"
        ),
    ),
)

#: The eight real selected pages in frozen selection order, as
#: ``(source slot, page in that deck)``.
REAL_SELECTION: tuple[tuple[str, int], ...] = tuple(
    (source.slot, page) for source in CORPUS_SOURCES for page in source.pages
)

#: The two synthetic probes, in selection order, after the eight real pages.
#: Each probe is exactly one page, so the frozen corpus is exactly ten pages.
PROBE_A_PAGE = 1
PROBE_A_PAGES: tuple[int, ...] = (1,)
PROBE_B_PAGE = 1
PROBE_A_KEY = "probe-a"
PROBE_B_KEY = "probe-b"

#: The frozen selection order, as stable page identifiers.
SELECTION_ORDER: tuple[str, ...] = tuple(
    [f"{slot}:{page}" for slot, page in REAL_SELECTION] + [PROBE_A_KEY, PROBE_B_KEY]
)


@dataclass(frozen=True)
class CorpusPage:
    """One page of the frozen corpus, with everything a reviewer needs to read it."""

    order: int
    page_id: str
    label: str
    source_kind: str
    source_page: int
    composition: str
    coverage_purpose: str
    scope_note: str
    synthetic: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "page_id": self.page_id,
            "label": self.label,
            "source_kind": self.source_kind,
            "source_page": self.source_page,
            "composition": self.composition,
            "coverage_purpose": self.coverage_purpose,
            "scope_note": self.scope_note,
            "synthetic": self.synthetic,
        }


#: What a corpus page's source is.  A real page comes from one of the three
#: private source decks, named by its opaque slot; a synthetic page comes from a
#: probe this repository builds through OfficeCLI.
_SOURCE_KIND_REAL = "real source deck (opaque slot; deck supplied locally)"
_SOURCE_KIND_SYNTHETIC = "committed synthetic probe built through OfficeCLI"


#: Composition and coverage of the eight frozen real pages, keyed by
#: ``(source slot, page in that deck)``.  These are literals a reviewer can check
#: against the source decks; nothing here is read out of a projection.
_REAL_COVERAGE: Mapping[tuple[str, int], tuple[str, str, str]] = {
    ("source-a", 2): (
        "25 textbox, 6 shape (3 ellipse, 3 rightArrow), 2 group, 4 connector, "
        "4 picture; 1 source overflow",
        "groups with owned connectors, native ellipse/rightArrow, overlay KPI "
        "text over a filled shape, source-inherent overflow",
        "The two groups are locked container boundaries: their children and the "
        "four connectors they own are represented inside the container proxy and "
        "are never emitted again as siblings. The KPI text painted over the "
        "filled ellipse is the V0.4.1 proxy-isolation risk and must stay "
        "independent. The one text overflow is the source's own condition and "
        "stays a retained finding.",
    ),
    ("source-a", 5): (
        "2 picture, 8 shape, 1 table",
        "cropped picture (srcRect), compound product picture, native 6x4 table",
        "Inherited master/layout branding is not reconstructed, so the rebuilt "
        "page is painted on a blank layout; that omission is page-level scope "
        "evidence, never slide-owned projection loss. The cropped picture's "
        "source rectangle is baked into the emitted media, which is recorded.",
    ),
    ("source-a", 12): (
        "44 shape, 1 table; 13 source issues",
        "text-dense control page: paragraphs, numbered options, font metrics, "
        "gradient fills, many source-inherent overflows",
        "This page carries the corpus's highest source-issue count and its "
        "gradient fills, and it is the only selected page not dominated by "
        "pictures. Every issue is the source's own; none is introduced by the "
        "projection. Gradient-filled objects are not canonical-editable and keep "
        "their locked or base-only disposition.",
    ),
    ("source-a", 30): (
        "16 picture, 30 shape, 7 connector, 4 textbox; highest object count",
        "high object density, many pictures, top-level connectors, repeated "
        "brand matrix",
        "The densest page in the corpus. Every connector has exactly one "
        "disposition in the ledger, and the repeated brand cells exercise "
        "identity collision between near-identical objects.",
    ),
    ("source-b", 3): (
        "3 picture, 12 shape, 3 table",
        "three repeated cards with transparent pictures and three native 6x5 "
        "tables on one page",
        "Three tables on one page exercise per-table identity and independent "
        "row/column and cell-text readback. The transparent pictures must keep "
        "their transparency rather than being flattened onto a panel colour.",
    ),
    ("source-b", 9): (
        "2 group, 21 shape, 1 table",
        "picture group against an opaque panel, native 8x5 table",
        "The group is a locked container boundary. This page differs from "
        "source-a page 5 in what it tests: that page exercises a cropped picture, "
        "this one exercises a container, and the two must not be conflated.",
    ),
    ("source-c", 2): (
        "3 picture, 4 shape, 3 table, 16 textbox",
        "the negative control: structural issues read clean while the source "
        "picture already shows a title overlap",
        "This page exists to stop the machine gate being read as visual "
        "acceptance: OfficeCLI reports no issue on it, yet the source page itself "
        "shows an overlapping title. A structural PASS here is not evidence of "
        "visual fidelity.",
    ),
    ("source-c", 21): (
        "2 picture, 8 shape, 2 table",
        "wide native 10x5 table isolated from picture noise, shape container",
        "The wide table isolates the table path from picture interference, so a "
        "table regression cannot be masked by an unrelated picture difference.",
    ),
}


def _pages() -> tuple[CorpusPage, ...]:
    pages: list[CorpusPage] = []
    for slot, page in REAL_SELECTION:
        composition, purpose, note = _REAL_COVERAGE[(slot, page)]
        pages.append(
            CorpusPage(
                order=len(pages) + 1,
                page_id=f"{slot}:{page}",
                label=f"{slot} page {page}",
                source_kind=_SOURCE_KIND_REAL,
                source_page=page,
                composition=composition,
                coverage_purpose=purpose,
                scope_note=note,
                synthetic=False,
            )
        )
    pages.append(
        CorpusPage(
            order=len(pages) + 1,
            page_id=PROBE_A_KEY,
            label="synthetic probe A",
            source_kind=_SOURCE_KIND_SYNTHETIC,
            source_page=PROBE_A_PAGES[0],
            composition=(
                "1 slide: a text-free filled rect with three independent "
                "sibling textboxes painted inside its rectangle, one text-free "
                "ellipse, and one text-free rightArrow with one independent "
                "sibling textbox painted inside it"
            ),
            coverage_purpose=(
                "proxy/overlay isolation: no sibling text may be embedded in any "
                "raster payload, and no wording may appear twice in the rebuilt "
                "deck"
            ),
            scope_note=(
                "Every object on this probe is canonical-editable and no proxy "
                "is emitted, so the rebuilt deck must contain no raster payload "
                "for this page at all. The overlay wording is asserted to "
                "appear exactly once in the rebuilt deck; if the rect, the "
                "ellipse or the arrow were ever replaced by a picture, this "
                "probe's unaccounted picture count would show it."
            ),
            synthetic=True,
        )
    )
    pages.append(
        CorpusPage(
            order=len(pages) + 1,
            page_id=PROBE_B_KEY,
            label="synthetic probe B",
            source_kind=_SOURCE_KIND_SYNTHETIC,
            source_page=PROBE_B_PAGE,
            composition=(
                "2 slides: mixed runs, a hard break, an empty paragraph, nested "
                "bullet and numbering paragraphs, explicit Latin/CJK fonts, "
                "theme-token text, rect/roundRect/ellipse/rightArrow; one group "
                "owning a shape and a connector"
            ),
            coverage_purpose=(
                "rich text semantics and the locked container boundary: mixed "
                "runs, hard break, empty paragraph, bullet nesting, numbering, "
                "Latin/CJK fonts, theme-token evidence, fixed numeric strings, "
                "and one group with a bound connector represented exactly once"
            ),
            scope_note=(
                "OfficeCLI reports no inheritance source for the theme run's "
                "colour, so the gate classifies it canonical-editable and the "
                "projection emits it without a colour declaration; the theme "
                "token is preserved in the source and in the projection's "
                "evidence, and no semantic token round trip is claimed. The "
                "group is one locked container boundary whose child shape and "
                "connector are represented once inside it and never emitted "
                "again as siblings."
            ),
            synthetic=True,
        )
    )
    return tuple(pages)


CORPUS_PAGES: tuple[CorpusPage, ...] = _pages()


def corpus_manifest(
    *,
    source_hashes: Mapping[str, str] | None = None,
    synthetic_hashes: Mapping[str, str] | None = None,
    selection: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the corpus manifest document.

    ``source_hashes`` is keyed by page id for real pages.  A private deck's digest
    is private material under the spec, so the committed manifest is built with it
    withheld and the local-only record keeps the value; see
    :func:`local_verification_record`.
    """
    source_hashes = dict(source_hashes or {})
    synthetic_hashes = dict(synthetic_hashes or {})
    pages = []
    for page in CORPUS_PAGES:
        record = page.as_dict()
        if page.synthetic:
            record["fixture_sha256"] = synthetic_hashes.get(page.page_id)
        elif page.page_id in source_hashes:
            record["source_sha256"] = WITHHELD_PRIVATE
        else:
            record["source_sha256"] = WITHHELD_PRIVATE
        pages.append(record)
    manifest: dict[str, Any] = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "selection_order": list(SELECTION_ORDER),
        "real_page_count": len(REAL_SELECTION),
        "real_source_count": len(CORPUS_SOURCES),
        "synthetic_probe_count": len(CORPUS_PAGES) - len(REAL_SELECTION),
        "sources": [source.as_dict() for source in CORPUS_SOURCES],
        "pages": pages,
    }
    if selection is not None:
        manifest["seam_selection"] = [dict(item) for item in selection]
    return manifest


#: What a page's source digest is in committed text.  The verification is real
#: and its verdict is published; the digest is not.
WITHHELD_PRIVATE = "withheld-private"


def local_verification_record(
    *,
    resolved: Mapping[str, Path],
    digests: Mapping[str, str],
    digests_after: Mapping[str, str] | None = None,
    unchanged: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Return the local-only record of what the run actually verified.

    This is where a source deck's identity, path and digest live.  It is written
    beside the evidence bundle and gitignored, so the public tree can carry the
    verdict -- "hashed before and after, identical" -- without carrying the
    private values that make it checkable.

    ``digests`` is each deck's hash before the run and ``digests_after`` its hash
    afterwards.  They are separate arguments because they are separate
    measurements: one deck's after-hash standing in for another's would make the
    per-source immutability claim unfalsifiable.
    """
    unchanged = dict(unchanged or {})
    after = dict(digests_after if digests_after is not None else digests)
    return {
        "note": (
            "Local-only record. Private source identity, paths and digests live "
            "here so the public evidence can stay free of them."
        ),
        "sources": [
            {
                "slot": source.slot,
                "path": str(resolved.get(source.slot, "")),
                "pages": list(source.pages),
                "sha256_before": digests.get(source.slot),
                "sha256_after": after.get(source.slot),
                "verified_unchanged": unchanged.get(source.slot),
            }
            for source in CORPUS_SOURCES
        ],
    }


def resolve_sources(config_path: Path | None = None) -> dict[str, Path]:
    """Return each corpus slot's deck, read from local configuration.

    The decks are private business documents: the repository does not name them,
    and it does not carry a search path back to them either.  A local JSON file
    maps a slot to a path, and its location is given by ``OFFICECLI_H2P_CORPUS``
    or by the conventional path below.  Nothing about a private deck reaches the
    committed tree.
    """
    import os

    configured = config_path or os.environ.get("OFFICECLI_H2P_CORPUS")
    path = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[1] / "local-corpus.json"
    )
    if not path.is_file():
        raise FileNotFoundError(
            f"no local corpus configuration at {path}; set OFFICECLI_H2P_CORPUS "
            "to a JSON file mapping each corpus slot to its deck path"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    slots = payload.get("sources") or payload
    resolved: dict[str, Path] = {}
    for source in CORPUS_SOURCES:
        entry = slots.get(source.slot)
        if not entry:
            raise KeyError(
                f"local corpus configuration does not name slot {source.slot!r}"
            )
        deck = Path(str(entry)).expanduser()
        if not deck.is_file():
            raise FileNotFoundError(f"{source.slot}: no deck at {deck}")
        resolved[source.slot] = deck
    return resolved


def seam_selection(
    sources: Mapping[str, Path] | None,
    probe_a: Path | None,
    probe_b: Path | None,
) -> list[tuple[str, int]]:
    """Return the frozen corpus's ``(deck, page)`` pairs in selection order.

    The full corpus is ten pages: eight real pages drawn from three source decks,
    then probe A's page, then probe B's page.  A ``None`` argument drops that
    source's pages, which is how the always-run synthetic half of the acceptance
    test drives the same seam over the two probes alone.

    ``sources`` maps a corpus slot to that slot's deck, resolved locally by
    :func:`resolve_sources`; the corpus text itself never carries a deck path.
    """
    selection: list[tuple[str, int]] = []
    if sources:
        for slot, page in REAL_SELECTION:
            deck = sources.get(slot)
            if deck is None:
                raise KeyError(f"corpus slot {slot!r} was not resolved to a deck")
            selection.append((str(deck), page))
    if probe_a is not None:
        selection.extend((str(probe_a), page) for page in PROBE_A_PAGES)
    if probe_b is not None:
        selection.append((str(probe_b), PROBE_B_PAGE))
    return selection


def expected_page_sequence(
    real_present: bool, probes_present: bool = True
) -> tuple[str, ...]:
    """The page ids the seam selection must produce, in order."""
    sequence = [f"{slot}:{page}" for slot, page in REAL_SELECTION] if real_present else []
    if probes_present:
        sequence.extend([*[PROBE_A_KEY] * len(PROBE_A_PAGES), PROBE_B_KEY])
    return tuple(sequence)


# ---------------------------------------------------------------------------
# Probe A -- proxy/overlay isolation
# ---------------------------------------------------------------------------

PROBE_A_DECK_NAME = "v042-probe-a-overlay.pptx"

#: The wording painted over the text-free card.  It is the contamination probe:
#: none of these strings may appear anywhere except once, as editable text.
PROBE_A_OVERLAY_LINES: tuple[str, ...] = ("In 2026", "9.50", "Million/USD")
PROBE_A_OVERLAY_BOXES: tuple[tuple[float, float, float, float], ...] = (
    (110.0, 216.0, 240.0, 26.0),
    (110.0, 246.0, 240.0, 26.0),
    (110.0, 276.0, 240.0, 26.0),
)
PROBE_A_CARD = "overlay-card"
PROBE_A_CARD_BOX = (100.0, 200.0, 260.0, 120.0)
PROBE_A_CARD_FILL = "#C00000"
PROBE_A_ELLIPSE = "probe-ellipse"
PROBE_A_ELLIPSE_BOX = (500.0, 200.0, 160.0, 90.0)
PROBE_A_ELLIPSE_FILL = "#4874CB"
PROBE_A_ARROW = "probe-arrow"
PROBE_A_ARROW_BOX = (500.0, 360.0, 180.0, 70.0)
PROBE_A_ARROW_FILL = "#EE822F"
PROBE_A_ARROW_OVERLAY = "arrow-caption"
PROBE_A_ARROW_OVERLAY_TEXT = "Continue"
PROBE_A_ARROW_OVERLAY_BOX = (520.0, 382.0, 140.0, 26.0)

#: Every string that must survive as independent editable text exactly once.
PROBE_A_ALL_OVERLAY_TEXT: tuple[str, ...] = (
    *PROBE_A_OVERLAY_LINES,
    PROBE_A_ARROW_OVERLAY_TEXT,
)

# ---------------------------------------------------------------------------
# Probe B -- rich text semantics and the locked container boundary
# ---------------------------------------------------------------------------

PROBE_B_DECK_NAME = "v042-probe-b-richtext.pptx"

PROBE_B_RICH_BLOCK = "rich-text-block"
PROBE_B_RICH_BOX = (50.0, 20.0, 500.0, 130.0)
PROBE_B_RICH_TEXT_SIZE_PT = 11.0
PROBE_B_RICH_TEXT_COLOR = "#24324A"

#: Paragraph 1 is three runs; paragraph 2 is empty; paragraph 3 carries a hard
#: break.  The text is one ``\\n``-separated body, which OfficeCLI turns into
#: one native ``a:p`` per newline.
PROBE_B_RICH_PARAGRAPH_1 = (
    "Mixed Latin 中文 run · 2026 · fixed 9.50 · 1,234,567.89"
)
PROBE_B_BOLD_RUN = "Mixed Latin"
PROBE_B_BOLD_SIZE_PT = 20.0
PROBE_B_BOLD_COLOR = "#B91C1C"
PROBE_B_BOLD_FONT = "Georgia"
PROBE_B_CJK_RUN = " 中文"
PROBE_B_CJK_FONT = "Microsoft YaHei"
#: A theme expression, not a plain colour: the gate must never claim this
#: round-tripped as a token.
PROBE_B_CJK_THEME_TOKEN = "accent2"
PROBE_B_TAIL_RUN = " run · 2026 · fixed 9.50 · 1,234,567.89"
PROBE_B_HARD_BREAK_PARAGRAPH = (
    "Hard break probe line\u000bsecond visual line"
)
#: A phrase that appears only in the hard-break paragraph, so the builder can
#: find that paragraph in OfficeCLI's own readback (which reports the paragraph
#: text without the break) and calibrate its character range against it.
PROBE_B_HARD_BREAK_MARKER = "Hard break probe line"
PROBE_B_HARD_BREAK_COLOR = "#1F7A3D"
PROBE_B_RICH_LINE_SPACING = "1.4x"
PROBE_B_FIXED_NUMBERS = ("2026", "9.50", "1,234,567.89")
#: The rich block is the corpus's editable rich-text probe, so it deliberately
#: declares only what the canonical surface can carry: a mixed-run paragraph and a
#: hard-break paragraph, and nothing else.
#:
#: It used to carry two more things -- an inter-paragraph spacing and an empty
#: paragraph -- and both are things the surface cannot express, so the object was
#: no longer representable as an editable body at all and the projection had to
#: classify it base-only.  That kept the page faithful and cost the corpus the only
#: place it proved hard-break and mixed-run fidelity *as editable text*, which is
#: coverage this probe exists to provide.  The two unrepresentable shapes are now
#: covered where they belong instead: by the classification's own unit tests, by
#: the gate's mutation suite, and by two real corpus objects that declare an empty
#: paragraph and are reported base-only with the reason.
PROBE_B_RICH_TEXT = (
    PROBE_B_RICH_PARAGRAPH_1
    + "\n"
    + PROBE_B_HARD_BREAK_PARAGRAPH
)

PROBE_B_LIST_BLOCK = "list-block"
PROBE_B_LIST_BOX = (50.0, 160.0, 500.0, 130.0)
PROBE_B_LIST_ITEMS: tuple[str, ...] = (
    "Level zero bullet item",
    "Nested level one bullet item",
    "Numbered item one",
    "Nested numbered item",
)
PROBE_B_LIST_TEXT = "\n".join(PROBE_B_LIST_ITEMS)
PROBE_B_LIST_PARAGRAPHS: tuple[tuple[str, int, float], ...] = (
    ("bullet", 0, 18.0),
    ("bullet", 1, 36.0),
    ("numbered", 0, 18.0),
    ("numbered", 1, 36.0),
)

PROBE_B_THEME_BLOCK = "theme-text-block"
PROBE_B_THEME_BOX = (50.0, 300.0, 400.0, 50.0)
PROBE_B_THEME_TEXT = "Theme resolved body 主题"
PROBE_B_THEME_TOKEN = "accent1"

PROBE_B_SHAPES: tuple[tuple[str, str, tuple[float, float, float, float], str], ...] = (
    ("probe-rect", "rect", (700.0, 40.0, 140.0, 60.0), "#3366CC"),
    ("probe-round-rect", "roundRect", (860.0, 40.0, 140.0, 60.0), "#F5F5F5"),
    ("probe-ellipse", "ellipse", (700.0, 130.0, 140.0, 60.0), "#4874CB"),
    ("probe-arrow", "rightArrow", (860.0, 130.0, 140.0, 60.0), "#EE822F"),
)

PROBE_B_GROUP = "probe-cluster"
PROBE_B_GROUP_BOX = (700.0, 240.0, 220.0, 150.0)
PROBE_B_GROUP_CHILD = "cluster-child"
PROBE_B_GROUP_CHILD_BOX = (710.0, 250.0, 90.0, 45.0)
PROBE_B_GROUP_CHILD_FILL = "#CC3366"
PROBE_B_GROUP_LINK = "cluster-link"
PROBE_B_GROUP_LINK_BOX = (710.0, 310.0, 90.0, 45.0)
PROBE_B_GROUP_LINK_COLOR = "#222222"
PROBE_B_SIBLING = "probe-sibling"
PROBE_B_SIBLING_TEXT = "Ungrouped sibling text"
PROBE_B_SIBLING_BOX = (50.0, 420.0, 400.0, 30.0)

#: A text object whose content overflows its own declared rectangle.
#:
#: PowerPoint draws a no-autofit line outside its box, and the source page shows
#: that overflow: the object's declared rectangle is a 120x14pt band while its
#: 22pt line is painted largely above and below it.  The typeface is left to the
#: theme (``/theme/minorFont``), which is the base-only condition -- the slide does
#: not own the object's visible text appearance -- so the object is represented by
#: an object-local visual proxy, and that proxy has to cover what the object
#: paints rather than only where it was declared.
PROBE_B_OVERFLOW_BLOCK = "clipped-text-block"
PROBE_B_OVERFLOW_BOX = (620.0, 120.0, 120.0, 14.0)
PROBE_B_OVERFLOW_TEXT = "Clipped overflow probe line"
PROBE_B_OVERFLOW_SIZE_PT = 22.0
#: The typeface OfficeCLI resolves for the probe through the theme, which is what
#: makes the object base-only rather than slide-owned.
PROBE_B_OVERFLOW_THEME_SOURCE = "/theme/minorFont"

#: Every fixed string Probe B must still carry after a rebuild.
PROBE_B_FIXED_STRINGS: tuple[str, ...] = (
    PROBE_B_RICH_PARAGRAPH_1,
    PROBE_B_HARD_BREAK_PARAGRAPH,
    *PROBE_B_LIST_ITEMS,
    PROBE_B_THEME_TEXT,
    PROBE_B_SIBLING_TEXT,
    PROBE_B_OVERFLOW_TEXT,
)


# ---------------------------------------------------------------------------
# Reading a gate result by corpus page
# ---------------------------------------------------------------------------


def ledger_for(result: Any, page_id: str) -> list[Any]:
    """Every ledger entry belonging to one corpus page, in emission order."""
    return [entry for entry in result.ledger if entry.source_key == _page_key(result, page_id)]


def _page_key(result: Any, page_id: str) -> str:
    """The projection's own source key for one corpus page.

    The key is read from the gate's per-page records, matched by position in the
    selection order the run actually processed, so nothing here depends on how
    the projection happens to name its sources.  A synthetic-only run carries
    the probes at the head of its selection; the full corpus carries them after
    the eight real pages.
    """
    pages = sorted(result.pages, key=lambda page: page.output_page)
    keys = [str(page.source_key) for page in pages]
    sequences = (
        expected_page_sequence(real_present=False),
        expected_page_sequence(real_present=True),
    )
    for sequence in sequences:
        if page_id in sequence and len(sequence) == len(keys):
            return keys[sequence.index(page_id)]
    for sequence in sequences:
        if page_id in sequence and sequence.index(page_id) < len(keys):
            return keys[sequence.index(page_id)]
    raise AssertionError(
        f"the gate published no page record for {page_id!r} "
        f"(published keys: {keys})"
    )


def page_record(result: Any, page_id: str, ordinal: int = 0) -> Any:
    """The gate's page record for one corpus page.

    ``ordinal`` selects between the pages a probe contributes: probe A's first
    page is its isolation page and its second is the arrow page.
    """
    key = _page_key(result, page_id)
    pages = [page for page in result.pages if page.source_key == key]
    pages.sort(key=lambda page: page.output_page)
    if ordinal >= len(pages):
        raise AssertionError(f"{page_id} has no page record at ordinal {ordinal}")
    return pages[ordinal]


def projected_by_name(result: Any, page_id: str, name: str) -> Any:
    """The projected object for one named synthetic object.

    The name is matched against the projection's own published report, which
    records the source name OfficeCLI reported next to the source identity; no
    geometry, ordinal or ordering guess is involved.
    """
    key = _page_key(result, page_id)
    report = json.loads(
        Path(result.projection_report_path).read_text(encoding="utf-8")
    )
    for source_object in _source_objects_by_name(report, key, name):
        for item in result.projected.objects:
            if item.source_object == source_object and item.source_key == key:
                return item
    raise AssertionError(f"no projected object named {name!r} on {page_id}")


def _source_objects_by_name(report: Mapping[str, Any], key: str, name: str) -> list[str]:
    found: list[str] = []
    for slide in report.get("slides") or []:
        if str(slide.get("source_key")) != key:
            continue
        for item in slide.get("objects") or []:
            if str(item.get("source_name") or "") == name:
                found.append(str(item.get("source_object")))
    return found


def entry_named(result: Any, page_id: str, name: str) -> Any:
    """The ledger entry for one named synthetic object.

    A named object that is emitted is found through the projection's own
    published report.  A name that is *not* in that report belongs to an object
    the projection did not emit as an object of its own -- a container's owned
    child -- so it is resolved through the source identity the deck itself
    carries, and the report's silence about it is part of the evidence.
    """
    key = _page_key(result, page_id)
    report = json.loads(
        Path(result.projection_report_path).read_text(encoding="utf-8")
    )
    wanted = set(_source_objects_by_name(report, key, name))
    entries = ledger_for(result, page_id)
    for entry in entries:
        if entry.source_object in wanted:
            return entry
    if not wanted:
        entries_with_path = [entry for entry in entries if entry.source_path]
        if entries_with_path:
            node = source_object_by_name(
                Path(entries_with_path[0].source_path), None, name
            )
            path = str(node.get("path") or "")
            for entry in entries:
                if entry.source_object == path:
                    return entry
    raise AssertionError(f"no ledger entry named {name!r} on {page_id}")


def document_path(result: Any, name: str = "canonical-author.html") -> Path:
    """One published document of an accepted gate run."""
    return Path(result.output_directory) / name


def source_object_by_name(deck: Path, slide: int | None, name: str) -> dict[str, Any]:
    """Read one named object out of a deck through OfficeCLI.

    This is the fixture-level readback: it observes the deck the acceptance run
    is *about*, not the projection's own reporting of it.  With ``slide``
    ``None`` the whole deck is searched, which is what a name that is unique in
    its fixture needs.
    """
    slides = [slide] if slide is not None else list(range(1, 33))
    for number in slides:
        try:
            payload = json.loads(
                officecli(
                    "get", str(deck), f"/slide[{number}]", "--depth", "3", "--json"
                )
            )
        except RuntimeError:
            # A slide that does not exist is where the walk ends.
            break
        results = payload.get("data", {}).get("results") or []
        if not results or results[0].get("type") != "slide":
            break
        for node in results:
            stack = [node, *(node.get("children") or [])]
            while stack:
                current = stack.pop(0)
                if object_name(current) == name:
                    return current
                stack.extend(current.get("children") or [])
    raise AssertionError(f"{name} is not in {deck}")


# ---------------------------------------------------------------------------
# OfficeCLI fixture construction
# ---------------------------------------------------------------------------


def officecli(*args: str, attempts: int = 6) -> str:
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
        "x": f"{box[0]:g}pt",
        "y": f"{box[1]:g}pt",
        "width": f"{box[2]:g}pt",
        "height": f"{box[3]:g}pt",
    }
    payload.update(props)
    return {"command": "add", "parent": parent, "type": "shape", "props": payload}


def object_name(node: Mapping[str, Any]) -> str:
    """Return an OfficeCLI node's object name, wherever that read reports it."""
    return str((node.get("format") or {}).get("name") or node.get("name") or "")


def _read_object(deck: Path, slide: int, name: str) -> dict[str, Any]:
    """Read one object back from a built deck, with its paragraphs and runs."""
    raw = officecli("get", str(deck), f"/slide[{slide}]", "--depth", "3", "--json")
    payload = json.loads(raw)
    results = payload.get("data", {}).get("results") or []
    for node in results:
        if object_name(node) == name:
            return node
        for child in node.get("children") or []:
            if object_name(child) == name:
                return child
    raise AssertionError(f"{name} is not on slide {slide} of {deck}")


def _paragraph_offset(object_node: Mapping[str, Any], marker: str) -> tuple[int, int]:
    """Return the calibrated range for the paragraph whose text contains ``marker``.

    OfficeCLI's range offsets are its own paragraph-sequence arithmetic, so the
    start is derived from OfficeCLI's own readback of the fixture's paragraphs
    plus one character per paragraph separator, and the length is the paragraph's
    read-back length plus the line breaks the readback drops.  The caller
    verifies the declaration landed on the marked paragraph, so a wrong offset
    can never pass silently.
    """
    offset = 0
    for paragraph in object_node.get("children") or []:
        text = str(paragraph.get("text") or "")
        if marker in text:
            return offset, len(text)
        offset += len(text) + 1
    raise AssertionError(
        f"no paragraph containing {marker!r} in {object_name(object_node)!r}"
    )


def _hard_break_range() -> tuple[int, int]:
    """The hard-break paragraph's own character span, derived from the body.

    The body is one ``\\n``-separated list of paragraphs, so the marked
    paragraph's characters start after the paragraphs above it and the separator
    each of them contributes.  How OfficeCLI counts the separator after the
    *marked* paragraph is its own arithmetic, and the builder calibrates against
    a readback rather than assuming it: this returns the offset and the length,
    and the caller tries the neighbouring end offsets OfficeCLI's own scope
    accepts, verifying each against a readback of the built fixture.
    """
    paragraphs = PROBE_B_RICH_TEXT.split("\n")
    offset = 0
    for paragraph in paragraphs:
        if PROBE_B_HARD_BREAK_MARKER in paragraph:
            return offset, len(paragraph.replace("\u000b", ""))
        offset += len(paragraph.replace("\u000b", "")) + 1
    raise AssertionError("the rich-text body has no hard-break paragraph")


def _hard_break_range_ends(start: int, length: int) -> tuple[int, ...]:
    """The end offsets to try for the marked paragraph, nearest first.

    The marked paragraph's characters occupy ``[start, start + length)`` and the
    scope OfficeCLI validates against may or may not count the separator that
    follows it, so the end offset nearest the paragraph's own last character is
    tried first and the neighbours after it.  Every candidate is verified by a
    readback, so trying one that OfficeCLI refuses costs a retry, never a wrong
    declaration.
    """
    return tuple(
        end for end in (start + length - 1, start + length, start + length - 2) if end > start
    )


def _run_colors(paragraph: Mapping[str, Any]) -> list[str]:
    return [
        str((run.get("format") or {}).get("color") or "")
        for run in paragraph.get("children") or []
    ]


def _apply_hard_break_declaration(
    rich_path: str, start: int, end: int
) -> list[dict[str, Any]]:
    return [
        {
            "command": "set",
            "path": rich_path,
            "props": {
                "range": f"{start}:{end}",
                "underline": "single",
                "color": PROBE_B_HARD_BREAK_COLOR,
            },
        }
    ]


def _hard_break_declaration_is_placed(paragraphs: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the hard-break declaration landed on the marked paragraph alone.

    OfficeCLI splits one styled character range into several runs, so the check
    is "some run of the marked paragraph carries the declaration" rather than
    "every run does", and "no earlier paragraph carries it at all".
    """
    marked = [
        paragraph
        for paragraph in paragraphs
        if PROBE_B_HARD_BREAK_MARKER in str(paragraph.get("text") or "")
    ]
    if len(marked) != 1:
        return False
    if PROBE_B_HARD_BREAK_COLOR not in _run_colors(marked[0]):
        return False
    earlier = [
        paragraph
        for paragraph in paragraphs
        if paragraph is not marked[0]
        and PROBE_B_HARD_BREAK_MARKER not in str(paragraph.get("text") or "")
    ]
    return all(
        PROBE_B_HARD_BREAK_COLOR not in _run_colors(paragraph)
        for paragraph in earlier
    )


def _textbox(
    name: str,
    text: str,
    box: Sequence[float],
    *,
    parent: str = "/slide[1]",
    **props: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "text": text,
        "x": f"{box[0]:g}pt",
        "y": f"{box[1]:g}pt",
        "width": f"{box[2]:g}pt",
        "height": f"{box[3]:g}pt",
        "size": f"{PROBE_B_RICH_TEXT_SIZE_PT:g}pt",
        "font": "Arial",
        "color": PROBE_B_RICH_TEXT_COLOR,
        "fill": "none",
        "line": "none",
    }
    payload.update(props)
    return {"command": "add", "parent": parent, "type": "textbox", "props": payload}


def _slides(*names: str) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {"command": "set", "path": "/", "props": {"slideSize": "widescreen"}}
    ]
    commands.extend(
        {"command": "add", "parent": "/", "type": "slide", "props": {"name": name}}
        for name in names
    )
    return commands


def probe_a_commands() -> list[dict[str, Any]]:
    """The OfficeCLI command list for probe A.

    The page is text-free where it matters: the card, the ellipse and the arrow
    carry no text of their own, so every character painted over them is an
    independent sibling object.  That is the arrangement a composited raster
    crop cannot represent without capturing its neighbours.
    """
    commands = _slides("probe-a-overlay")
    commands.append(
        _shape(
            PROBE_A_CARD,
            "rect",
            PROBE_A_CARD_BOX,
            fill=PROBE_A_CARD_FILL,
            line="none",
        )
    )
    for index, (line, box) in enumerate(
        zip(PROBE_A_OVERLAY_LINES, PROBE_A_OVERLAY_BOXES), start=1
    ):
        commands.append(
            _textbox(
                f"overlay-line-{index}",
                line,
                box,
                color="#FFFFFF",
            )
        )
    commands.append(
        _shape(
            PROBE_A_ELLIPSE,
            "ellipse",
            PROBE_A_ELLIPSE_BOX,
            fill=PROBE_A_ELLIPSE_FILL,
            line="none",
        )
    )
    commands.append(
        _shape(
            PROBE_A_ARROW,
            "rightArrow",
            PROBE_A_ARROW_BOX,
            fill=PROBE_A_ARROW_FILL,
            line="none",
        )
    )
    commands.append(
        _textbox(
            PROBE_A_ARROW_OVERLAY,
            PROBE_A_ARROW_OVERLAY_TEXT,
            PROBE_A_ARROW_OVERLAY_BOX,
            color="#FFFFFF",
        )
    )
    return commands


def probe_b_commands() -> list[dict[str, Any]]:
    """The OfficeCLI command list that lays out probe B.

    Every rich-text property is written through OfficeCLI's own paragraph and
    run setters -- ``list`` writes ``a:buChar`` and ``a:buAutoNum`` for the
    nested bullet and the numbering, and ``color=accent1`` writes a theme
    expression rather than a resolved colour.  The run ranges are *not* in this
    list: they are calibrated against OfficeCLI's readback of the built deck by
    :func:`probe_b_format_commands`, because OfficeCLI's range offsets are its
    own paragraph-sequence arithmetic and are not derivable from the authored
    string by inspection.
    """
    commands = _slides("probe-b")
    commands.append(
        _textbox(PROBE_B_RICH_BLOCK, PROBE_B_RICH_TEXT, PROBE_B_RICH_BOX)
    )
    commands.append(
        _textbox(PROBE_B_LIST_BLOCK, PROBE_B_LIST_TEXT, PROBE_B_LIST_BOX)
    )
    commands.append(
        _textbox(
            PROBE_B_THEME_BLOCK,
            PROBE_B_THEME_TEXT,
            PROBE_B_THEME_BOX,
            color=PROBE_B_THEME_TOKEN,
        )
    )
    commands.append(_overflow_textbox())
    for name, geometry, box, fill in PROBE_B_SHAPES:
        commands.append(
            _shape(
                name,
                geometry,
                box,
                parent="/slide[1]",
                fill=fill,
                line="none",
            )
        )
    commands.append(
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "group",
            "props": {
                "name": PROBE_B_GROUP,
                "x": f"{PROBE_B_GROUP_BOX[0]:g}pt",
                "y": f"{PROBE_B_GROUP_BOX[1]:g}pt",
                "width": f"{PROBE_B_GROUP_BOX[2]:g}pt",
                "height": f"{PROBE_B_GROUP_BOX[3]:g}pt",
            },
        }
    )
    commands.append(
        _shape(
            PROBE_B_GROUP_CHILD,
            "rect",
            PROBE_B_GROUP_CHILD_BOX,
            parent="/slide[1]/group[1]",
            fill=PROBE_B_GROUP_CHILD_FILL,
            line="none",
        )
    )
    commands.append(
        {
            "command": "add",
            "parent": "/slide[1]/group[1]",
            "type": "connector",
            "props": {
                "name": PROBE_B_GROUP_LINK,
                "x": f"{PROBE_B_GROUP_LINK_BOX[0]:g}pt",
                "y": f"{PROBE_B_GROUP_LINK_BOX[1]:g}pt",
                "width": f"{PROBE_B_GROUP_LINK_BOX[2]:g}pt",
                "height": f"{PROBE_B_GROUP_LINK_BOX[3]:g}pt",
                "line": PROBE_B_GROUP_LINK_COLOR,
            },
        }
    )
    commands.append(
        _textbox(
            PROBE_B_SIBLING,
            PROBE_B_SIBLING_TEXT,
            PROBE_B_SIBLING_BOX,
            parent="/slide[1]",
        )
    )
    return commands


def _overflow_textbox() -> dict[str, Any]:
    """The probe's overflowing base-only text object, as an OfficeCLI command.

    The typeface is deliberately *not* declared: OfficeCLI then resolves it from
    the theme, which is the base-only condition the classification is built on,
    so the object is represented by an object-local visual proxy.  Its declared
    rectangle is much shorter than its 22pt line, which is what makes the line
    paint outside it -- exactly the arrangement the proxy crop has to cover.
    """
    payload = _textbox(
        PROBE_B_OVERFLOW_BLOCK,
        PROBE_B_OVERFLOW_TEXT,
        PROBE_B_OVERFLOW_BOX,
        size=f"{PROBE_B_OVERFLOW_SIZE_PT:g}pt",
        lineSpacing="0.5x",
    )
    payload["props"].pop("font", None)
    return payload


def probe_b_format_commands(rich_object: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the run and paragraph setters for probe B.

    ``rich_object`` is OfficeCLI's own readback of the built rich-text block, so
    the run ranges below are derived from the paragraphs the fixture really has.
    The hard-break paragraph's range is applied separately by
    :func:`_apply_hard_break_declaration`, because its placement is verified
    against a readback.
    """
    rich_path = "/slide[1]/shape[@name=" + PROBE_B_RICH_BLOCK + "]"
    bold_end = len(PROBE_B_BOLD_RUN)
    cjk_end = bold_end + len(PROBE_B_CJK_RUN)
    tail_end = len(PROBE_B_RICH_PARAGRAPH_1)
    commands: list[dict[str, Any]] = [
        {
            "command": "set",
            "path": rich_path,
            "props": {
                "range": f"0:{bold_end}",
                "bold": "true",
                "size": f"{PROBE_B_BOLD_SIZE_PT:g}pt",
                "color": PROBE_B_BOLD_COLOR,
                "font": PROBE_B_BOLD_FONT,
            },
        },
        {
            "command": "set",
            "path": rich_path,
            "props": {
                "range": f"{bold_end}:{cjk_end}",
                "font": PROBE_B_CJK_FONT,
                "color": PROBE_B_CJK_THEME_TOKEN,
            },
        },
        {
            "command": "set",
            "path": rich_path,
            "props": {
                "range": f"{cjk_end}:{tail_end}",
                "italic": "true",
            },
        },
        {
            "command": "set",
            "path": f"{rich_path}/p[1]",
            "props": {
                "align": "left",
                "lineSpacing": PROBE_B_RICH_LINE_SPACING,
            },
        },
    ]
    list_path = "/slide[1]/shape[@name=" + PROBE_B_LIST_BLOCK + "]"
    for index, (marker, level, margin) in enumerate(PROBE_B_LIST_PARAGRAPHS, start=1):
        commands.append(
            {
                "command": "set",
                "path": f"{list_path}/p[{index}]",
                "props": {
                    "list": marker,
                    "level": str(level),
                    "marginLeft": f"{margin:g}pt",
                    "indent": f"{-PROBE_B_RICH_TEXT_SIZE_PT:g}pt",
                },
            }
        )
    return commands


def _build_deck(path: Path, commands: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["officecli", "close", str(path)], capture_output=True, check=False)
    path.unlink(missing_ok=True)
    officecli("create", str(path))
    payload = list(commands)
    reply = officecli(
        "batch", str(path), "--commands", json.dumps(payload, ensure_ascii=False)
    )
    if "failed" in reply and "0 failed" not in reply:
        raise RuntimeError(
            "the OfficeCLI batch that builds the synthetic probe did not apply "
            f"every command:\n{reply}"
        )
    officecli("close", str(path))
    return path


def build_probe_a(directory: Path) -> Path:
    """Build probe A through OfficeCLI and return its deck path."""
    return _build_deck(directory / PROBE_A_DECK_NAME, probe_a_commands())


def build_probe_b(directory: Path) -> Path:
    """Build probe B through OfficeCLI and return its deck path.

    Three OfficeCLI passes: the layout, the run and paragraph declarations whose
    ranges are calibrated against the built deck's own readback, and the
    hard-break declaration.  The hard-break range's end offset is calibrated the
    same way: OfficeCLI's own scope arithmetic decides whether the separator
    after the marked paragraph counts, so the nearest end offsets are tried in
    turn and every attempt is verified against a readback of the built deck.
    """
    deck = _build_deck(directory / PROBE_B_DECK_NAME, probe_b_commands())
    rich = _read_object(deck, 1, PROBE_B_RICH_BLOCK)
    rich_path = "/slide[1]/shape[@name=" + PROBE_B_RICH_BLOCK + "]"
    start, length = _hard_break_range()
    commands = probe_b_format_commands(rich)
    # The run and paragraph declarations and the hard-break declaration go in as
    # one batch, so no range is applied twice and no attempt can leave formatting
    # behind on a paragraph it should not have touched.
    for candidate in (start, start - 1, start + 1):
        if candidate < 0:
            continue
        for end in _hard_break_range_ends(candidate, length):
            try:
                officecli(
                    "batch",
                    str(deck),
                    "--commands",
                    json.dumps(
                        [
                            *commands,
                            *_apply_hard_break_declaration(
                                rich_path, candidate, end
                            ),
                        ],
                        ensure_ascii=False,
                    ),
                )
            except RuntimeError:
                # An out-of-bounds range is OfficeCLI refusing the offset, which
                # is exactly the signal this calibration loop is looking for.
                continue
            paragraphs = (
                _read_object(deck, 1, PROBE_B_RICH_BLOCK).get("children") or []
            )
            if _hard_break_declaration_is_placed(paragraphs):
                officecli("close", str(deck))
                return deck
    officecli("close", str(deck))
    raise AssertionError(
        "the hard-break declaration could not be placed on the marked "
        "paragraph of the probe B fixture"
    )


def build_synthetic_probes(directory: Path) -> dict[str, Path]:
    """Build both probes once and return them keyed by corpus page id."""
    return {
        PROBE_A_KEY: build_probe_a(directory),
        PROBE_B_KEY: build_probe_b(directory),
    }
