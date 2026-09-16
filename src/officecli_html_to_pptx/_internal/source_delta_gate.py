"""The V0.4.2 source-to-rebuilt projection delta evidence gate.

This is the acceptance gate that sits on top of the one hidden projection seam
(:func:`officecli_html_to_pptx.project_pptx_to_author_html`).  One call::

    explicit ordered selected pages (source PPTX + source page, one or more decks)
      -> source OfficeCLI validation + issues, per selected page
      -> Canonical Author HTML + source map + disposition ledger (the #15 seam)
      -> a fresh PPTX rebuilt through the existing New Deck path
      -> rebuilt OfficeCLI validation + issues + independent readback
      -> source-to-rebuilt comparison by *stable source identity*
      -> PASS / PASS_WITH_FINDINGS / BLOCK, with hashed evidence

It decides acceptance from **material deltas**, not from an absolute
zero-issue assumption: the source decks are private business artifacts that
already carry historical findings, and projection is not allowed to rewrite
their layout merely to reach a zero count.

What the outcome means
----------------------

``PASS``
    Every check passed.  There are no rebuilt-only conditions, no
    unsupported/unresolved disposition, no ambiguous mapping, no failed proxy
    isolation proof, and no retained finding or scope-only source finding
    either: the rebuilt deck reproduces the source pages with nothing left to
    review.

``PASS_WITH_FINDINGS``
    Every check passed and the material delta set is empty, but the report
    still carries explicit findings that a reviewer must read: *retained*
    source-inherent conditions the rebuilt object reproduces (for example the
    same text overflow at the same severity), and *scope evidence* that is
    about the source deck rather than about slide-owned projection (inherited
    master/layout cached-field findings, source objects that the projection
    does not emit because a container represents them).  These are not
    acceptance failures; they are the visible remainder of a real source deck.

``BLOCK``
    Acceptance is refused.  A blocking input or a material delta was found, and
    the report names every one of them with its source and rebuilt context.

The outcome is *derived* from the collected evidence by
:func:`classify_gate_outcome`.  It is never read from a subprocess exit code, an
Author Contract status, or an OfficeCLI ``validate`` PASS: OfficeCLI exits 0
and writes no file when it cannot render, and a structurally valid deck can
still be a projection regression.

The comparison rules
--------------------

Everything below is a documented rule rather than a heuristic, and all three
rules are recorded in the published evidence under ``comparison_rules`` so a
reviewer reads the rule the gate actually applied.

**Stable source mapping.**  Every issue is keyed by the *source* identity it
belongs to -- ``(source_key, source_page, source_object)`` -- never by output
position.  A rebuilt issue is located by the emitted object name the New Deck
compiler gives the projected object (``slide-NNN-<kind>-<ordinal>``, see
:attr:`ProjectedObject.emitted_name`) and mapped back through the disposition
ledger to its source identity.  Renumbering output pages therefore cannot
fabricate or hide a delta: an issue that moves because the selection order moved
still has the same source key, and an issue on a slide the gate never selected
is not part of the comparison at all.

**Issue normalization.**  Issue text is normalized to a *condition kind* with
its measured values retained as context:

* the OfficeCLI issue id (``O5``, ``U30``) and the ``/slide[N]/...`` path are
  stripped, because both are output-position artifacts;
* the leading sentence is lowercased and reduced to a slug, so
  ``text overflow: 2 lines at 27.2pt need 65pt, usable 33pt.`` becomes the
  condition ``text_overflow``;
* every number-with-unit and its nearest preceding label are extracted as
  ``label=value`` measurements (``need_pt``, ``usable_pt``, ``lines``, ...).

So a moved page compares equal, and a changed severity compares as the same
*kind* of condition with different measurements.

**Retained vs material.**  With ``S`` the source condition on one source
identity and ``R`` the rebuilt condition on the same source identity:

* ``R`` absent, ``S`` present -> **retained finding** (source-inherent, the
  rebuilt object is not worse).
* ``R`` present, ``S`` absent -> **material delta** (rebuilt-only condition).
* both present, different condition kind -> **material delta**.
* both present, same kind -> **retained**, unless materially worsened.

**Materially worsened.**  A same-kind condition is materially worsened when its
*pressure* grows.  For a text overflow, ``need_pt`` is the space the text
requires and ``usable_pt`` is the space the object offers, so the measured
value is the ratio ``need_pt / usable_pt`` (1.0 = exactly fits).  The rebuilt
ratio is compared against the source ratio with two thresholds
(:data:`OVERFLOW_RATIO_ABSOLUTE_TOLERANCE`, 0.02, and
:data:`OVERFLOW_RATIO_RELATIVE_TOLERANCE`, 0.05): a grow beyond *both* is
material, so rebuilding the same overflow with a marginally different usable
height -- which the source and the New Deck path legitimately disagree about by
a point or two -- stays retained.  A condition whose measurements cannot be read
is never declared "worse": it keeps its retained/material verdict from presence
alone.  Any other kind of condition gains this comparison by declaring its own
``pressure_ratio`` (for example ``aspect_ratio`` for clipping); until then,
presence alone decides it.

**Rebuilt-issue binding fails closed.**  Every rebuilt issue is either bound to
the source identity of the emitted object it names, or the binding failed and
the issue blocks.  There is no third outcome: the rebuilt deck holds only the
selected pages and this run built it, so an issue on an object the disposition
ledger does not know -- or on a path that resolves to no object of the deck at
all -- is evidence about *this* projection, not an unrelated record to skip.  An
unbound issue is reported as an :class:`UnboundRebuiltIssue` with the reason its
binding failed, and it is a material delta and a blocking diagnostic of its own.

Rejecting a whole selection
---------------------------

A selected page the projection refuses -- a source table with a merged cell, an
object with no representation -- is a blocking input *for that page*.  The gate
classifies a blocked selection page by page, keeps the pages that project, and
publishes a ``BLOCK`` verdict in which the blocking page is a page record with
its reason and every other selected page has its complete evidence.  Aborting
the run instead would destroy the evidence for every page that projects exactly
when a reviewer needs it.  A page that was never rebuilt reports no output page,
and a verdict with no projectable page at all has nothing to compare, so that
one still raises.

Independent readback
--------------------

Text and table structure are read back from the rebuilt PPTX through OfficeCLI
and compared with the source objects' own captured text and table matrix.  The
gate never compares a generated manifest with itself: the projected HTML, the
projection report, and the rebuilt deck are three separate artifacts, and the
rebuilt object is located by the name the New Deck compiler derives from the
HTML -- not by geometry, position, or ordinal guessing.

Atomic publication
------------------

All gate evidence is staged in a temporary directory beside the destination and
moved into place in one step, so the evidence a reviewer reads is either the
complete set or absent: nothing is written into the destination before every
artifact exists in the staging directory, and a failed run removes its staging
area and leaves no destination behind at all.

The verdict is carried by the *name* of the report, not by whether files exist:
a run that reaches ``PASS`` or ``PASS_WITH_FINDINGS`` writes
``gate-report.json``, and a blocked run writes ``gate-rejected.json`` with the
same complete evidence beside it.  Partial evidence therefore cannot appear as a
completed gate result -- the file that means "accepted" is only ever written by a
run that reached an accepting outcome -- and a rejected run's diagnostics,
per-page records, ledger, and proxy proofs all survive for the reviewer who has
to repair it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from .acceptance import _run_officecli
from .author_projector import (
    BLOCKING_DISPOSITIONS,
    COMPILED_KIND_BY_PROJECTED_KIND,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_BASE_ONLY,
    DispositionLedgerEntry,
    PageSelection,
    PROXY_GUARD_PX,
    ProjectedObject,
    ProjectionBlockedError,
    ProjectionError,
    ProjectionResult,
    SelectedPage,
    _sha256_file,
    _write_text_exact,
    project_pptx_to_author_html,
)
from .pptx_reader import PROXY_DENSITY_TOLERANCE

GATE_SCHEMA_VERSION = 1

# The one comparison whose thresholds are measurements rather than identities.
# Both must be exceeded before a same-kind condition counts as materially
# worsened, so a rebuild that disagrees with the source about a usable height by
# a rounding-level amount stays a retained finding rather than a regression.
OVERFLOW_RATIO_ABSOLUTE_TOLERANCE = 0.02
OVERFLOW_RATIO_RELATIVE_TOLERANCE = 0.05

# The condition kinds whose measured pressure is the overflow ratio.
_PRESSURE_RATIO_RULES: Mapping[str, tuple[str, str]] = {
    "text_overflow": ("need_pt", "usable_pt"),
}

# Fraction of a proxy's guard band that may be paint before the band is read as
# contamination from something other than the target object.  The target's own
# antialiased edge legitimately reaches into the band, so a *majority* of the
# band carrying paint is what distinguishes a sibling baked into the image.
GUARD_BAND_CONTAMINATION_FRACTION = 0.5
# How far a proxy pixel may sit from the proxy's own background and still count
# as background.  The same per-channel test the projector's isolation gates use.
PROXY_PAINT_TOLERANCE = 6
# A proxy must carry at least this fraction of its own raster as paint that is
# not its background.  It is not a quality threshold -- any raster at all clears
# it -- it is the boundary between "this image shows the object" and "this image
# is the empty background rectangle the object's content was supposed to be in".
PROXY_MINIMUM_PAINT_FRACTION = 0.0
# Whole-pixel rounding of a render, and of the projected rectangle the crop was
# taken from, when a proxy raster is measured against its declared geometry.
PROXY_RASTER_TOLERANCE_PX = 2

# The evidence file every published gate directory must contain.  Its absence is
# what "incomplete evidence" means, and it is deliberately absent from a rejected
# run's directory: the gate publishes its whole evidence set either way, and
# ``gate-report.json`` is the one artifact that only a run which reached
# ``PASS`` or ``PASS_WITH_FINDINGS`` writes.
GATE_REPORT_NAME = "gate-report.json"
LEDGER_NAME = "disposition-ledger.json"
SOURCE_MAP_NAME = "source-map.json"
PROJECTION_REPORT_NAME = "projection-report.json"
REBUILT_PPTX_NAME = "rebuilt.pptx"
CANONICAL_HTML_NAME = "canonical-author.html"
REJECTION_REPORT_NAME = "gate-rejected.json"
PROXY_DIRECTORY_NAME = "proxies"
# The projection's own artifacts (the #15 seam's Canonical Author HTML, source
# map, and projection report) and the object-local proxy assets it wrote are part
# of what the gate accepts, so they are published inside the gate directory
# rather than left in a temporary directory that disappears when the call
# returns.  A reviewer can re-read and re-hash the exact document and images the
# verdict describes.
PROJECTION_DIRECTORY_NAME = "projection"

_ISSUE_PATH_RE = re.compile(
    r"^\s*/slide\[(?P<slide>\d+)\](?P<rest>[^:]*?)(?:\s*\((?P<scope>master|layout)\))?\s*$",
    re.IGNORECASE,
)
# A measured value: a number with an optional unit token glued to it, always at
# a word boundary so ``27.2pt`` is one value and ``2 lines`` is a value and a
# separate word.
_ISSUE_MEASURE_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>pt|px|cm|mm|in|lines?|%)?\b",
    re.IGNORECASE,
)
# What a measured value must never be labelled with: the word that introduces
# the call it is part of, the unit words themselves, and the filler between a
# value and the next one.
_MEASUREMENT_STOP_WORDS = frozenset(
    {
        "a",
        "allow",
        "allowed",
        "an",
        "and",
        "at",
        "available",
        "by",
        "exceeds",
        "for",
        "in",
        "is",
        "it",
        "line",
        "lines",
        "max",
        "needs",
        "of",
        "on",
        "over",
        "than",
        "the",
        "to",
        "up",
        "use",
        "used",
        "uses",
        "using",
        "with",
    }
)
_CONDITION_SLUG_RE = re.compile(r"[^a-z0-9]+")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?\s*[a-z%]*", re.IGNORECASE)


class GateOutcome(str, Enum):
    """The derived acceptance outcome of one gate run.

    ``PASS`` and ``PASS_WITH_FINDINGS`` both mean acceptance; ``BLOCK`` means
    acceptance was refused.  See the module docstring for the exact meaning of
    each value.  The outcome is always derived from the collected evidence by
    :func:`classify_gate_outcome` -- never from a process status.
    """

    PASS = "PASS"
    PASS_WITH_FINDINGS = "PASS_WITH_FINDINGS"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class NormalizationRule:
    """One documented comparison rule, published with the evidence."""

    name: str
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "rule": self.rule}


COMPARISON_RULES: tuple[NormalizationRule, ...] = (
    NormalizationRule(
        name="source_identity_key",
        rule=(
            "Every issue is keyed by (source_key, source_page, source_object). "
            "A rebuilt issue is located by the New Deck compiler's object name "
            "'slide-NNN-<kind>-<ordinal>' and mapped back through the "
            "disposition ledger, so output page order and page renumbering "
            "cannot create or hide a delta."
        ),
    ),
    NormalizationRule(
        name="issue_normalization",
        rule=(
            "The OfficeCLI issue id and '/slide[N]/...' path are stripped; the "
            "leading sentence is lowercased and slugged into a condition kind "
            "(for example 'text overflow: ... need 65pt, usable 33pt' -> "
            "'text_overflow'); every number-with-unit and its nearest preceding "
            "label is kept as a measurement ('need_pt=65', 'usable_pt=33')."
        ),
    ),
    NormalizationRule(
        name="retained_vs_material",
        rule=(
            "Condition present on both sides with the same kind -> retained "
            "finding unless materially worsened. Condition present only in the "
            "rebuilt object -> material delta. Condition present only in the "
            "source object -> retained finding. Same identity, different "
            "condition kind -> material delta."
        ),
    ),
    NormalizationRule(
        name="materially_worsened",
        rule=(
            "A same-kind condition is materially worsened only when its "
            "pressure ratio grows past BOTH an absolute tolerance of "
            f"{OVERFLOW_RATIO_ABSOLUTE_TOLERANCE} and a relative tolerance of "
            f"{OVERFLOW_RATIO_RELATIVE_TOLERANCE}. For 'text_overflow' the "
            "pressure ratio is need_pt / usable_pt. A condition whose "
            "measurements are unreadable is never declared worse."
        ),
    ),
    NormalizationRule(
        name="scope_evidence",
        rule=(
            "A source issue whose path names a master or layout, or names the "
            "slide itself rather than an object on it, is scope evidence: it is "
            "never mapped onto a rebuilt slide-owned object and never reported "
            "as a repaired or lost slide-owned object."
        ),
    ),
    NormalizationRule(
        name="table_structure",
        rule=(
            "A native table's kind, row count, column count, cell count and "
            "whitespace-normalized cell text are read back from the rebuilt "
            "PPTX and compared with the source object's own table matrix; the "
            "source mapping is the data-cell-path recorded on every emitted "
            "cell."
        ),
    ),
    NormalizationRule(
        name="text_readback",
        rule=(
            "Canonical-editable text is read back from the rebuilt PPTX and "
            "compared with the source object's captured text under an explicit "
            "structure-preserving normalization (structure_text), NOT by removing "
            "whitespace. A paragraph break, a hard break and a page break all "
            "normalize to one newline; U+00A0 normalizes to a space (the one "
            "display-only rule the product documents); a run of spaces or tabs "
            "collapses to one space; whitespace touching a line boundary is "
            "dropped. Everything else compares exactly, so a dropped, changed or "
            "invented character blocks, AND so does a lost hard break, a lost "
            "paragraph boundary, or two words run together. A difference that is "
            "only whitespace placement *within* a line is accepted and reported as "
            "a retained finding with both spellings; a structural difference is a "
            "blocking finding, because the characters survive while the line "
            "boundary the source painted does not."
        ),
    ),
    NormalizationRule(
        name="table_cell_readback",
        rule=(
            "A native table's cell text is read back from the rebuilt PPTX and "
            "compared with the SOURCE DECK's own matrix, which is read from the "
            "source PPTX through OfficeCLI rather than from the projection's "
            "emitted HTML; comparing against the emitted HTML would only prove "
            "that the projection is consistent with itself. Cell text is compared "
            "under the same structure-preserving rule as object text, so a cell "
            "whose words ran together or whose line structure changed blocks. The "
            "table's kind, row count, column count and cell count are compared "
            "exactly; the per-cell source mapping is read from the emitted HTML, "
            "which is where that claim belongs. A source matrix that cannot be "
            "read, or that is ragged, is a blocking "
            "source_table_readback_unavailable diagnostic rather than an empty "
            "expectation."
        ),
    ),
    NormalizationRule(
        name="rebuilt_issue_binding",
        rule=(
            "The rebuilt deck holds only the selected pages, so every rebuilt "
            "issue either binds to the source identity of the emitted object it "
            "names, or the binding failed and the issue blocks. A rebuilt issue "
            "whose object resolves but whose identity is not in this run's "
            "ledger (the projection did not select that object) is reported as "
            "an out-of-scope rebuilt issue and blocks; a rebuilt issue whose "
            "path resolves to no object of the rebuilt deck at all is reported "
            "as an unresolvable rebuilt issue and blocks. Neither is ever "
            "discarded, because a rebuilt-only condition that nothing binds is "
            "exactly what this gate exists to catch."
        ),
    ),
    NormalizationRule(
        name="proxy_isolation",
        rule=(
            "Every locked proxy must prove: the target object survived (the "
            "rebuilt PPTX holds exactly one object of the emitted name and "
            "kind), the proxy's own raster carries visible paint -- the proxy "
            "must not be entirely its own sampled background, so an object "
            "whose content did not survive its reconstruction is refused rather "
            "than published as a blank image of the right size, where 'paint' "
            "is a pixel differing from the raster's sampled background by more "
            f"than {PROXY_PAINT_TOLERANCE} per channel and 'background' is the "
            "modal colour at the raster's four corners, so a legitimately "
            "near-white object still passes because it differs from the slide "
            "background rather than from white), raster density at least the "
            "Author canvas density, the "
            f"guard band ({PROXY_GUARD_PX}px per side) is present and its paint "
            "fraction is at most "
            f"{GUARD_BAND_CONTAMINATION_FRACTION} of the band, the target "
            "rectangle is inside the raster, and the asset bytes hash to the "
            "recorded value. Any failed proof blocks acceptance."
        ),
    ),
    NormalizationRule(
        name="artifact_hashing",
        rule=(
            "Every published artifact is hashed and listed in the report, "
            "except the report itself and its markdown twin: a document cannot "
            "contain its own SHA-256, so those two are verified by re-hashing "
            "the files. Every distinct source PPTX is re-hashed after the run, "
            "and a source whose bytes moved blocks acceptance."
        ),
    ),
)


@dataclass(frozen=True)
class ArtifactHash:
    """One published artifact, its size, and its SHA-256."""

    name: str
    path: str
    sha256: str
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class IssueMeasurement:
    """One measured value an OfficeCLI issue reported."""

    label: str
    value: float
    unit: str

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class IssueRecord:
    """One OfficeCLI issue, normalized and bound to a source identity.

    ``condition`` is the normalized kind, ``measurements`` keeps the measured
    values as comparison context, and ``source_identity`` is ``None`` for a
    finding that belongs to the deck rather than to one slide-owned object --
    an inherited master/layout cached field, for example.
    """

    source_key: str
    source_page: int
    source_object: str | None
    scope: str
    condition: str
    message: str
    severity: str
    issue_id: str
    measured: tuple[IssueMeasurement, ...] = ()

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.source_key, self.source_page, self.source_object or self.scope)

    @property
    def identity(self) -> tuple[str, int, str] | None:
        """The slide-owned source identity, or ``None`` for scope evidence."""
        if self.source_object is None:
            return None
        return (self.source_key, self.source_page, self.source_object)

    def measurement(self, label: str) -> float | None:
        for item in self.measured:
            if item.label == label:
                return item.value
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "scope": self.scope,
            "condition": self.condition,
            "message": self.message,
            "severity": self.severity,
            "issue_id": self.issue_id,
            "measured": [item.as_dict() for item in self.measured],
        }


@dataclass(frozen=True)
class OfficeCliEvidence:
    """One OfficeCLI read of one deck: validation plus issues, kept verbatim.

    ``validation`` and ``issues_text`` are the tool's own published output, so a
    reviewer can re-read exactly what was parsed rather than trusting a summary.
    """

    label: str
    path: str
    role: str
    sha256: str
    validation: str
    issues_text: str
    issue_count: int
    raw_issue_records: tuple[Mapping[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "path": self.path,
            "role": self.role,
            "sha256": self.sha256,
            "validation": self.validation,
            "issues_text": self.issues_text,
            "issue_count": self.issue_count,
        }


@dataclass(frozen=True)
class RebuiltStyle:
    """The supported text formatting of one rebuilt object, as OfficeCLI reports it.

    Read from the rebuilt PPTX, never from the generated HTML.  The gate used to
    build its "expected style" out of the emitted document and compare it with
    nothing at all, so changing a rebuilt object's font, size, colour or weight
    while leaving its characters intact would still pass.  These are the
    declaration names the canonical surface actually carries.
    """

    align: str | None = None
    line_spacing: str | None = None
    wrap: str | None = None
    auto_fit: str | None = None
    space_before: str | None = None
    space_after: str | None = None
    #: One entry per distinct resolved run style, in reading order.  Per-run, not
    #: a single representative value: a mixed-run body whose runs were flattened
    #: into one style must not read as faithful.
    runs: tuple[str, ...] = ()
    #: Set when the readback could not be established, which is a blocking
    #: condition rather than an empty style.
    unavailable: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "align": self.align,
            "line_spacing": self.line_spacing,
            "wrap": self.wrap,
            "auto_fit": self.auto_fit,
            "space_before": self.space_before,
            "space_after": self.space_after,
            "runs": list(self.runs),
        }
        if self.unavailable:
            payload["unavailable"] = self.unavailable
        return payload


def _style_token(value: Any) -> str | None:
    """Return a normalized declaration value, or ``None`` when it is not stated."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "false"}:
        return None
    return text.lower()


def _font_size_pt(declarations: Mapping[str, Any]) -> float | None:
    """Return the source's font size in points, from its run declarations."""
    first: float | None = None
    for run in declarations.get("runs") or ():
        match = re.search(r"size=(-?\d+(?:\.\d+)?)pt", str(run))
        if match is None:
            continue
        size = float(match.group(1))
        if size > 0:
            first = size if first is None else min(first, size)
    return first


def rebuilt_style(detailed: Mapping[str, Any]) -> RebuiltStyle:
    """Read one rebuilt object's supported text formatting from its readback."""
    fmt = dict(detailed.get("format") or {})
    runs: list[str] = []
    for paragraph in detailed.get("children") or []:
        if str(paragraph.get("type")) != "paragraph":
            continue
        paragraph_format = dict(paragraph.get("format") or {})
        for run in paragraph.get("children") or []:
            if str(run.get("type")) != "run":
                continue
            run_format = dict(run.get("format") or {})
            sources = (run_format, paragraph_format, fmt)
            family = _resolved_value(sources, "font.latin", "effective.font.latin",
                                     "font", "effective.font")
            size = _resolved_value(sources, "size", "effective.size")
            colour = _resolved_value(sources, "color", "effective.color")
            bold = _resolved_value(sources, "bold", "effective.bold")
            italic = _resolved_value(sources, "italic", "effective.italic")
            underline = _resolved_value(sources, "underline", "effective.underline")
            runs.append(
                "|".join(
                    f"{name}={_style_token(value) or '-'}"
                    for name, value in (
                        ("font", family),
                        ("size", size),
                        ("color", colour),
                        ("bold", bold),
                        ("italic", italic),
                        ("underline", underline),
                    )
                )
            )
    return RebuiltStyle(
        align=_style_token(fmt.get("align") or fmt.get("effective.align")),
        line_spacing=_style_token(
            fmt.get("lineSpacing") or fmt.get("effective.lineSpacing")
        ),
        wrap=_style_token(fmt.get("wrap")),
        auto_fit=_style_token(fmt.get("autoFit")),
        space_before=_style_token(
            fmt.get("spaceBefore") or fmt.get("effective.spaceBefore")
        ),
        space_after=_style_token(
            fmt.get("spaceAfter") or fmt.get("effective.spaceAfter")
        ),
        runs=tuple(runs),
    )


def _resolved_value(
    sources: Sequence[Mapping[str, Any]], *names: str
) -> Any:
    """Return the first stated value for ``names`` across the fallbacks."""
    for mapping in sources:
        for name in names:
            value = mapping.get(name)
            if value is not None:
                return value
    return None


@dataclass(frozen=True)
class RebuiltObject:
    """One object of the rebuilt deck, as OfficeCLI reports it."""

    emitted_name: str
    rebuilt_kind: str
    rebuilt_slide: int
    path: str
    text: str
    bounds_pt: tuple[float, float, float, float]
    rows: int | None = None
    columns: int | None = None
    cells: tuple[str, ...] = ()
    #: The supported text formatting OfficeCLI reports for this rebuilt object.
    style: RebuiltStyle = RebuiltStyle()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "emitted_name": self.emitted_name,
            "rebuilt_kind": self.rebuilt_kind,
            "rebuilt_slide": self.rebuilt_slide,
            "path": self.path,
            "text": self.text,
            "bounds_pt": [round(value, 4) for value in self.bounds_pt],
            "style": self.style.as_dict(),
        }
        if self.rows is not None:
            payload["rows"] = self.rows
            payload["columns"] = self.columns
            payload["cells"] = list(self.cells)
        return payload


def _declaration_matches(
    expected: Any, actual: Any, *, name: str, font_size_pt: float | None = None
) -> bool:
    """Whether one object-level declaration survived the rebuild.

    Lengths are compared with a tolerance because a point value round-trips
    through pixels and back; a colour is compared by its digits, because a
    rebuild may spell the same colour with or without the leading hash.

    Line spacing is compared *by measurement*, not as a string.  PowerPoint states
    the same leading either as a multiple of the font size (``1.5x``) or as an
    absolute distance (``26pt``), and a rebuild may legitimately choose the other
    spelling.  Comparing the two spellings literally reports a faithful rebuild as
    a regression -- which is what the first run of this check did, on ``26pt``
    against ``0.597x`` for the same leading.

    When the two spellings are not comparable at all -- one a multiple, the other
    a distance, with no font size in hand -- the comparison declines to call it a
    regression.  Refusing to compare is honest here; inventing a conversion from a
    font size this function does not have would be a guess dressed as a check.
    """
    left = _style_token(expected)
    right = _style_token(actual)
    if left is None or right is None:
        return left == right
    if name == "lineSpacing":
        return _leading_matches(left, right, font_size_pt=font_size_pt)
    if name == "align":
        return left == right
    return left.lstrip("#") == right.lstrip("#")


def _leading_matches(left: Any, right: Any, *, font_size_pt: float | None) -> bool:
    """Whether two line-spacing spellings name the same leading.

    A multiple (``1.5x``) and a distance (``26pt``) are the same measurement once
    the font size is known, and PowerPoint states either one.  With the source's
    font size in hand the multiple is resolved and the two are compared as
    distances; without it the comparison declines rather than guessing.

    Declining matters as much as comparing: a check that reports a faithful
    rebuild as a regression gets switched off, and then it protects nothing.
    """
    left_points = _leading_points(left)
    right_points = _leading_points(right)
    if left_points is None and right_points is None:
        # Both are multiples; comparing the factors is exact.
        return _numbers_agree(left, right, tolerance=0.02)
    if font_size_pt and font_size_pt > 0:
        left_points = left_points if left_points is not None else _multiple_points(
            left, font_size_pt
        )
        right_points = right_points if right_points is not None else _multiple_points(
            right, font_size_pt
        )
    if left_points is None or right_points is None:
        return False
    return abs(left_points - right_points) <= max(0.5, 0.02 * left_points)


def _multiple_points(value: Any, font_size_pt: float) -> float | None:
    """Return a multiple of the font size as a distance in points."""
    text = _style_token(value)
    if text is None or not text.endswith("x"):
        return None
    try:
        return float(text[:-1]) * font_size_pt
    except ValueError:
        return None


def _leading_points(value: Any) -> float | None:
    """Return a leading stated as a distance, in points; ``None`` for a multiple."""
    text = _style_token(value)
    if text is None or text.endswith("x"):
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(pt|px|cm|mm|in)?", text)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "pt").lower()
    factors = {"pt": 1.0, "px": 0.5, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4, "in": 72.0}
    return amount * factors.get(unit, 1.0)


def _run_matches(expected: Any, actual: Any) -> bool:
    """Whether one run's resolved formatting survived the rebuild."""
    left = str(expected)
    right = str(actual)
    if left == right:
        return True
    left_fields = dict(part.split("=", 1) for part in left.split("|") if "=" in part)
    right_fields = dict(part.split("=", 1) for part in right.split("|") if "=" in part)
    for field, expected_value in left_fields.items():
        actual_value = right_fields.get(field)
        if actual_value is None:
            return False
        if field in {"size", "lineSpacing"}:
            if not _numbers_agree(expected_value, actual_value, tolerance=0.05):
                return False
            continue
        if field == "color":
            if expected_value.lstrip("#") != actual_value.lstrip("#"):
                return False
            continue
        if field in {"bold", "italic", "underline"}:
            if _style_token(expected_value) != _style_token(actual_value):
                return False
            continue
        if expected_value != actual_value:
            return False
    return True


def _numbers_agree(left: Any, right: Any, *, tolerance: float) -> bool:
    """Whether two declaration values name the same measurement."""
    import re as _re

    def number(value: Any) -> float | None:
        match = _re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        return float(match.group(0)) if match else None

    left_number = number(left)
    right_number = number(right)
    if left_number is None or right_number is None:
        return _style_token(left) == _style_token(right)
    return abs(left_number - right_number) <= tolerance


def expected_style_declarations(projected: Any) -> dict[str, Any]:
    """Return the supported formatting the *source object* declares.

    Read from the projection's own captured object rather than re-parsed out of
    the generated HTML.  The emitted HTML is the artifact under test; using it as
    the expectation would make the style check compare the projection with itself,
    which is the defect this replaces.
    """
    payload: dict[str, Any] = {}
    capabilities = getattr(projected, "capabilities", None) or {}
    if isinstance(capabilities, Mapping) and capabilities:
        payload["capabilities"] = dict(capabilities)

    paragraphs = list(getattr(projected, "text_style", ()) or ())
    if paragraphs:
        first = paragraphs[0]
        if first.get("align") and str(first["align"]).lower() not in {"left", "start"}:
            payload["text-align"] = first["align"]
        if first.get("line_spacing"):
            payload["line-height"] = first["line_spacing"]
        runs: list[str] = []
        for paragraph in paragraphs:
            for run in paragraph.get("runs") or ():
                if not isinstance(run, Mapping):
                    continue
                runs.append(
                    "|".join(
                        f"{name}={_style_token(value) or '-'}"
                        for name, value in (
                            ("font", run.get("font")),
                            ("size", run.get("size")),
                            ("color", run.get("color")),
                            ("bold", run.get("bold")),
                            ("italic", run.get("italic")),
                            ("underline", run.get("underline")),
                        )
                    )
                )
        if runs:
            payload["runs"] = runs
    return payload


@dataclass(frozen=True)
class TextReadback:
    """Independent text and supported-style readback of one canonical-editable object."""

    source_key: str
    source_page: int
    source_object: str
    emitted_name: str
    rebuilt_kind: str
    rebuilt_slide: int
    expected_text: str
    rebuilt_text: str
    style_declarations: Mapping[str, Any]
    #: The same formatting as OfficeCLI reports it *from the rebuilt PPTX*.  The
    #: evidence side is the source's own declaration and this is the artifact's, so
    #: the two sides are read from different places and the comparison can fail.
    rebuilt_style: RebuiltStyle = RebuiltStyle()

    @property
    def compact_equal(self) -> bool:
        """Whether the characters match with whitespace taken out of the compare.

        Reported for a reviewer; not the acceptance rule.  Two spellings that
        agree here but not under :meth:`matched` differ in structure -- a lost
        hard break, a lost paragraph boundary, or two words run together.
        """
        return compact_text(self.expected_text) == compact_text(self.rebuilt_text)

    @property
    def matched(self) -> bool:
        """Whether the readback is faithful enough to accept as this object's text.

        Compared under :func:`structure_text`: every character must survive in
        order and the paragraph and hard-break structure must survive with it.
        A whitespace-blind comparison used to stand here and could not see a
        dropped hard break at all.
        """
        return structure_text(self.expected_text) == structure_text(self.rebuilt_text)

    @property
    def structure_lost(self) -> bool:
        """Whether the structure differs while the characters do not.

        This is a blocking difference, not a cosmetic one: the words are still
        there but a line boundary the source painted is gone, so ``line one`` and
        ``line two`` read as one line whose words abut.
        """
        return not self.matched and self.compact_equal

    @property
    def whitespace_only_difference(self) -> bool:
        """Whether the two spellings differ in whitespace placement alone."""
        return self.matched and normalize_text(self.expected_text) != normalize_text(
            self.rebuilt_text
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "emitted_name": self.emitted_name,
            "rebuilt_kind": self.rebuilt_kind,
            "rebuilt_slide": self.rebuilt_slide,
            "expected_text": self.expected_text,
            "rebuilt_text": self.rebuilt_text,
            "expected_compact_text": compact_text(self.expected_text),
            "rebuilt_compact_text": compact_text(self.rebuilt_text),
            "expected_structure_text": structure_text(self.expected_text),
            "rebuilt_structure_text": structure_text(self.rebuilt_text),
            "matched": self.matched,
            "style_matched": self.style_matched,
            "structure_lost": self.structure_lost,
            "whitespace_only_difference": self.whitespace_only_difference,
            "expected_style": dict(self.style_declarations),
            "rebuilt_style": self.rebuilt_style.as_dict(),
        }

    @property
    def style_matched(self) -> bool:
        """Whether the supported formatting survived the rebuild.

        Part of acceptance, not a separate report: while only ``matched`` decided
        the verdict, a rebuilt object whose font, size, colour or weight changed
        passed as long as its characters were intact.
        """
        if self.rebuilt_style.unavailable:
            return False
        return not self.style_failures()

    def style_failures(self) -> tuple[str, ...]:
        """Name every supported declaration that did not survive, with both sides."""
        built = self.rebuilt_style
        found: list[str] = []
        # The source's own font size, so a leading stated as a multiple and one
        # stated as a distance can be compared as the same measurement.
        font_size_pt = _font_size_pt(self.style_declarations)
        for name, expected in (
            ("align", self.style_declarations.get("text-align")),
            ("lineSpacing", self.style_declarations.get("line-height")),
        ):
            if expected is None:
                continue
            actual = built.align if name == "align" else built.line_spacing
            if actual is None:
                found.append(
                    f"{name}: the source declares {expected!r} and the rebuilt "
                    "object reports none"
                )
            elif not _declaration_matches(
                expected, actual, name=name, font_size_pt=font_size_pt
            ):
                found.append(
                    f"{name}: expected {expected!r} from the source, rebuilt "
                    f"reports {actual!r}"
                )
        # Per-run formatting is compared run for run.  A body whose runs were
        # flattened into one style has fewer entries and fails here, which is the
        # point: a representative value is not a faithful readback.
        expected_runs = self.style_declarations.get("runs")
        if expected_runs:
            expected_list = list(expected_runs)
            if len(expected_list) != len(built.runs):
                found.append(
                    f"run count: the source declares {len(expected_list)} styled "
                    f"run(s) and the rebuilt object reports {len(built.runs)}"
                )
            else:
                for index, (expected_run, actual_run) in enumerate(
                    zip(expected_list, built.runs)
                ):
                    if not _run_matches(expected_run, actual_run):
                        found.append(
                            f"run {index}: expected {expected_run!r}, rebuilt "
                            f"reports {actual_run!r}"
                        )
        return tuple(found)


@dataclass(frozen=True)
class TableCheck:
    """Independent structural readback of one selected native table."""

    source_key: str
    source_page: int
    source_object: str
    emitted_name: str
    rebuilt_slide: int
    expected_kind: str
    rebuilt_kind: str
    expected_rows: int
    expected_columns: int
    rebuilt_rows: int
    rebuilt_columns: int
    expected_cells: tuple[str, ...]
    rebuilt_cells: tuple[str, ...]
    cell_paths: tuple[str, ...]

    def structure_cells_equal(self) -> bool:
        """Whether the matrices carry the same text under the object-text rule.

        Cell text is compared with the same explicit, structure-preserving
        normalization object text uses.  It used to be compared whitespace-blind,
        which was the rule this gate was already criticized for elsewhere: a cell
        whose words ran together, or whose paragraph break disappeared, matched.
        Two different strictness levels for "the same text" is one rule too many,
        and the looser one was on the path that is hardest to check by eye.
        """
        return tuple(map(structure_text, self.expected_cells)) == tuple(
            map(structure_text, self.rebuilt_cells)
        )

    def differing_cell_positions(self) -> tuple[int, ...]:
        """The cell positions whose text differs under that rule."""
        return tuple(
            index
            for index, (expected, rebuilt) in enumerate(
                zip(self.expected_cells, self.rebuilt_cells)
            )
            if structure_text(expected) != structure_text(rebuilt)
        )

    def space_only_cell_positions(self) -> tuple[int, ...]:
        """The cells that differ in space placement alone, structure intact.

        These are the ones worth reporting as a retained finding: the characters
        and the line structure survive, and only the spaces moved.  A cell that
        also fails :meth:`structure_cells_equal` is a blocking failure instead.
        """
        return tuple(
            index
            for index, (expected, rebuilt) in enumerate(
                zip(self.expected_cells, self.rebuilt_cells)
            )
            if expected != rebuilt
            and structure_text(expected) == structure_text(rebuilt)
        )

    def failures(self) -> tuple[str, ...]:
        """Return every way this table failed its independent readback."""
        found: list[str] = []
        if self.rebuilt_kind != "table" or self.expected_kind != "table":
            found.append(
                f"table kind is {self.expected_kind!r} in the source map but "
                f"{self.rebuilt_kind!r} in the rebuilt deck"
            )
        if (self.rebuilt_rows, self.rebuilt_columns) != (
            self.expected_rows,
            self.expected_columns,
        ):
            found.append(
                f"dimensions are {self.expected_rows}x{self.expected_columns} in "
                f"the source but {self.rebuilt_rows}x{self.rebuilt_columns} in "
                "the rebuilt deck"
            )
        if len(self.rebuilt_cells) != self.expected_rows * self.expected_columns:
            found.append(
                f"the rebuilt table reports {len(self.rebuilt_cells)} cell(s) for "
                f"a {self.expected_rows}x{self.expected_columns} matrix"
            )
        if not self.structure_cells_equal():
            positions = self.differing_cell_positions()
            found.append(
                "cell text differs from the SOURCE deck's matrix under the "
                f"structure-preserving rule at cell position(s) {list(positions[:8])}"
                + (" ..." if len(positions) > 8 else "")
            )
        if len(self.cell_paths) != self.expected_rows * self.expected_columns:
            found.append(
                f"{len(self.cell_paths)} emitted cell(s) carry a source mapping "
                f"for a {self.expected_rows}x{self.expected_columns} matrix"
            )
        return tuple(found)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "emitted_name": self.emitted_name,
            "rebuilt_slide": self.rebuilt_slide,
            "expected_kind": self.expected_kind,
            "rebuilt_kind": self.rebuilt_kind,
            "expected_rows": self.expected_rows,
            "expected_columns": self.expected_columns,
            "rebuilt_rows": self.rebuilt_rows,
            "rebuilt_columns": self.rebuilt_columns,
            "expected_cells": list(self.expected_cells),
            "rebuilt_cells": list(self.rebuilt_cells),
            "cell_paths": list(self.cell_paths),
            "differing_cell_positions": list(self.differing_cell_positions()),
            "failures": list(self.failures()),
        }


@dataclass(frozen=True)
class ProxyIsolationProof:
    """Object-isolation evidence for one locked proxy.

    All five facts the policy requires are here: target survival, raster
    density, guard band, target bounds, and contamination.  ``density_ok``,
    ``guard_band_ok``, ``bounds_ok``, ``contamination_ok`` and
    ``target_survived`` together are :attr:`passed`; any of them false blocks
    acceptance.
    """

    source_key: str
    source_page: int
    source_object: str
    emitted_name: str
    disposition: str
    asset: str | None
    asset_sha256: str | None
    recorded_asset_sha256: str | None
    raster_width_px: int
    raster_height_px: int
    expected_width_px: int
    expected_height_px: int
    raster_density: float
    required_density: float
    guard_band_px: int
    guard_band_paint_fraction: float
    target_bounds_pt: tuple[float, float, float, float]
    background_rgb: tuple[int, int, int] | None
    rebuilt_kind: str | None
    disposition_blocking: bool
    paint_pixels: int = 0
    raster_pixels: int = 0
    failures: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def paint_fraction(self) -> float:
        """The fraction of the proxy's own raster that is not its background."""
        if self.raster_pixels <= 0:
            return 0.0
        return self.paint_pixels / self.raster_pixels

    @property
    def carries_paint(self) -> bool:
        """Whether the proxy's own bytes show anything at all.

        This is target survival measured from the proxy rather than asserted
        from the rebuilt deck: an object whose content did not survive its
        reconstruction produces an image that is nothing but the background its
        rectangle was cropped out of.
        """
        return self.paint_fraction > PROXY_MINIMUM_PAINT_FRACTION

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "emitted_name": self.emitted_name,
            "disposition": self.disposition,
            "asset": self.asset,
            "asset_sha256": self.asset_sha256,
            "recorded_asset_sha256": self.recorded_asset_sha256,
            "raster_width_px": self.raster_width_px,
            "raster_height_px": self.raster_height_px,
            "expected_width_px": self.expected_width_px,
            "expected_height_px": self.expected_height_px,
            "raster_density": self.raster_density,
            "required_density": self.required_density,
            "guard_band_px": self.guard_band_px,
            "guard_band_paint_fraction": self.guard_band_paint_fraction,
            "target_bounds_pt": [round(value, 4) for value in self.target_bounds_pt],
            "background_rgb": list(self.background_rgb) if self.background_rgb else None,
            "rebuilt_kind": self.rebuilt_kind,
            "disposition_blocking": self.disposition_blocking,
            "raster_pixels": self.raster_pixels,
            "paint_pixels": self.paint_pixels,
            "paint_fraction": self.paint_fraction,
            "target_survived": self.rebuilt_kind is not None,
            "paint_measured": self.raster_pixels > 0 and self.background_rgb is not None,
            "carries_paint": self.carries_paint,
            "density_ok": not any("density" in item for item in self.failures),
            "guard_band_ok": not any("guard band" in item for item in self.failures),
            "bounds_ok": not any("bounds" in item for item in self.failures),
            "contamination_ok": not any(
                "contamination" in item for item in self.failures
            ),
            "passed": self.passed,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class MaterialDelta:
    """One rebuilt condition that the source object does not have.

    Both contexts travel with it so the blocking diagnostic can name the source
    page and object *and* the rebuilt page and object.
    """

    source_key: str
    source_page: int
    source_object: str
    condition: str
    reason: str
    rebuilt_slide: int
    rebuilt_object: str
    rebuilt_issue: Mapping[str, Any]
    source_issue: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "condition": self.condition,
            "reason": self.reason,
            "rebuilt_slide": self.rebuilt_slide,
            "rebuilt_object": self.rebuilt_object,
            "rebuilt_issue": dict(self.rebuilt_issue),
            "source_issue": dict(self.source_issue) if self.source_issue else None,
        }

    def describe(self) -> str:
        return (
            f"[{self.source_key} p{self.source_page} {self.source_object}] -> "
            f"[rebuilt slide {self.rebuilt_slide} {self.rebuilt_object}]: "
            f"{self.condition}: {self.reason}"
        )


@dataclass(frozen=True)
class UnboundRebuiltIssue:
    """A rebuilt issue the gate could not bind to a selected source identity.

    The binding fails closed: an issue the rebuilt deck reports that no source
    identity owns is a material delta in its own right, never a record that is
    quietly dropped.  ``reason_code`` says which binding step failed, so a
    reviewer reads *why* the gate could not attribute the issue rather than only
    that it could not:

    ``rebuilt_object_not_in_ledger``
        the issue's path names an object the rebuilt deck really holds, and that
        object's emitted name is not in this run's disposition ledger -- the
        projection did not select the source object behind it.
    ``rebuilt_path_unresolved``
        the issue's path names no object of the rebuilt deck at all.  The
        rebuilt deck holds only the selected pages and is built by this run, so
        a path that resolves to nothing means the source-to-rebuilt mapping is
        unsound, not that the issue is unimportant.
    ``rebuilt_path_package_level``
        the issue's path does not name a slide at all, so no page of this
        selection can own it.
    """

    reason_code: str
    condition: str
    message: str
    raw_issue: Mapping[str, Any]

    @property
    def path(self) -> str:
        return str(self.raw_issue.get("path", "") or "")

    @property
    def issue_id(self) -> str:
        return str(self.raw_issue.get("id", "") or "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "condition": self.condition,
            "message": self.message,
            "path": self.path,
            "issue_id": self.issue_id,
            "raw_issue": dict(self.raw_issue),
        }


@dataclass(frozen=True)
class RetainedFinding:
    """A source-inherent condition the rebuilt object reproduces."""

    source_key: str
    source_page: int
    source_object: str | None
    condition: str
    reason: str
    rebuilt_slide: int | None
    rebuilt_object: str | None
    source_issue: Mapping[str, Any]
    rebuilt_issue: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "condition": self.condition,
            "reason": self.reason,
            "rebuilt_slide": self.rebuilt_slide,
            "rebuilt_object": self.rebuilt_object,
            "source_issue": dict(self.source_issue),
            "rebuilt_issue": dict(self.rebuilt_issue) if self.rebuilt_issue else None,
        }


@dataclass(frozen=True)
class ScopeEvidence:
    """A source finding about the deck rather than about a slide-owned object.

    Inherited master/layout cached-field findings and expected inherited-paint
    omissions live here: they stay visible in the report and are never reported
    as a repaired or lost slide-owned object.
    """

    source_key: str
    source_page: int
    condition: str
    detail: str
    source_issue: Mapping[str, Any]
    mapped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "condition": self.condition,
            "detail": self.detail,
            "mapped": self.mapped,
            "source_issue": dict(self.source_issue),
        }


@dataclass(frozen=True)
class GateDiagnostic:
    """One blocking input or material finding, with its source and rebuilt context."""

    code: str
    message: str
    source_key: str | None = None
    source_page: int | None = None
    source_object: str | None = None
    rebuilt_slide: int | None = None
    rebuilt_object: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "source_key": self.source_key,
            "source_page": self.source_page,
            "source_object": self.source_object,
            "rebuilt_slide": self.rebuilt_slide,
            "rebuilt_object": self.rebuilt_object,
            "blocking": True,
        }


@dataclass(frozen=True)
class BlockedPage:
    """One selected page the projection refused to build, and why.

    A page whose source carries something the Author Contract cannot express --
    a merged table cell, an object with no representation -- is a blocking input
    for that page.  It travels as its own record so a run that selects it still
    reaches a verdict and still publishes the complete evidence for the pages
    that *could* be projected; the alternative, aborting the whole run, destroys
    the evidence for every other page exactly when a reviewer needs it most.

    ``selection_index`` is the page's 1-based position in the selection the
    caller asked for, which is the only ordering a page that was never rebuilt
    can be reported in: ``output_page`` belongs to the rebuilt deck, and a page
    with no place in that deck must not claim one.
    """

    source_key: str
    source_path: str
    source_page: int
    selection_index: int
    output_page: int
    reason_code: str
    reason: str
    detail: str
    blocking_objects: tuple[str, ...] = ()

    def describe(self) -> str:
        return (
            f"[{self.source_key} p{self.source_page} selection #{self.selection_index}] "
            f"{self.reason_code} on "
            f"{', '.join(self.blocking_objects) or 'the page'}: {self.reason}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_path": self.source_path,
            "source_page": self.source_page,
            "selection_index": self.selection_index,
            "output_page": self.output_page,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "detail": self.detail,
            "blocking_objects": list(self.blocking_objects),
        }


@dataclass(frozen=True)
class GatePageRecord:
    """One page-level evidence record -- one per selected page, always.

    ``blocked`` is true when the page could not be projected at all, in which
    case every projection-derived field is empty and ``blocking_reason`` says
    what refused it.  A blocked page is still a page record: the outcome it
    produces is a blocking one, and the page that blocked is named in the
    evidence rather than left as an exception.
    """

    source_key: str
    source_path: str
    source_page: int
    output_page: int
    rebuilt_slide: int
    source_objects: int
    canonical_editable: int
    locked_visual_proxy: int
    base_only_semantic: int
    unsupported: int
    unresolved: int
    native_objects: tuple[str, ...]
    proxy_objects: tuple[str, ...]
    ledger: tuple[DispositionLedgerEntry, ...]
    source_issue_count: int
    rebuilt_issue_count: int
    material_deltas: tuple[MaterialDelta, ...]
    retained_findings: tuple[RetainedFinding, ...]
    scope_evidence: tuple[ScopeEvidence, ...]
    text_readback: tuple[TextReadback, ...]
    tables: tuple[TableCheck, ...]
    proxies: tuple[ProxyIsolationProof, ...]
    failures: tuple[str, ...] = ()
    blocked: bool = False
    blocking_reason: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_path": self.source_path,
            "source_page": self.source_page,
            "output_page": self.output_page,
            "rebuilt_slide": self.rebuilt_slide,
            "blocked": self.blocked,
            "blocking_reason": (
                dict(self.blocking_reason) if self.blocking_reason else None
            ),
            "counts": {
                "source_objects": self.source_objects,
                "canonical_editable": self.canonical_editable,
                "locked_visual_proxy": self.locked_visual_proxy,
                "base_only_semantic": self.base_only_semantic,
                "unsupported": self.unsupported,
                "unresolved": self.unresolved,
            },
            "native_objects": list(self.native_objects),
            "proxy_objects": list(self.proxy_objects),
            "object_names": list(self.object_names),
            "source_issue_count": self.source_issue_count,
            "rebuilt_issue_count": self.rebuilt_issue_count,
            "material_deltas": [item.as_dict() for item in self.material_deltas],
            "retained_findings": [item.as_dict() for item in self.retained_findings],
            "scope_evidence": [item.as_dict() for item in self.scope_evidence],
            "text_readback": [item.as_dict() for item in self.text_readback],
            "tables": [item.as_dict() for item in self.tables],
            "proxies": [item.as_dict() for item in self.proxies],
            "failures": list(self.failures),
        }

    @property
    def object_names(self) -> tuple[str, ...]:
        """Every emitted object name this page carries, in emission order."""
        return tuple(sorted((*self.native_objects, *self.proxy_objects)))


@dataclass(frozen=True)
class PageResponse:
    """One selected page's readback, carrying that page's real evidence.

    This is the report's per-page surface.  It was once a list of object names,
    which a reviewer could not check anything against; it now carries the page's
    own :class:`GatePageRecord` -- its counts, its ledger, its text readbacks,
    its table checks and its proxy proofs -- so the page evidence and the
    summary of it are the same object rather than two renderings that can drift
    apart.  ``blocked`` and ``blocking_reason`` travel on the record too, so a
    page that could not be projected is reported exactly like a page that could.
    """

    page: GatePageRecord

    @property
    def source_key(self) -> str:
        return self.page.source_key

    @property
    def source_page(self) -> int:
        return self.page.source_page

    @property
    def output_page(self) -> int:
        return self.page.output_page

    @property
    def rebuilt_slide(self) -> int:
        return self.page.rebuilt_slide

    @property
    def object_names(self) -> tuple[str, ...]:
        return self.page.object_names

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_page": self.source_page,
            "output_page": self.output_page,
            "rebuilt_slide": self.rebuilt_slide,
            "object_names": list(self.object_names),
            "evidence": self.page.as_dict(),
        }


@dataclass(frozen=True)
class ProjectionGateResult:
    """The structured result of one source-to-rebuilt delta gate run.

    ``outcome`` is the derived, enumerated acceptance decision.  ``published``
    says whether the evidence directory exists: the complete evidence set is
    published for every run that got as far as a verdict, accepted or blocked
    alike, and an accepted run additionally writes ``gate-report.json`` while a
    blocked one writes ``gate-rejected.json`` instead.  A run that could not
    reach a verdict publishes nothing and raises.
    """

    outcome: GateOutcome
    published: bool
    output_directory: str | None
    report_path: str | None
    diagnostics: tuple[GateDiagnostic, ...]
    pages: tuple[GatePageRecord, ...]
    material_deltas: tuple[MaterialDelta, ...]
    retained_findings: tuple[RetainedFinding, ...]
    scope_evidence: tuple[ScopeEvidence, ...]
    artifacts: tuple[ArtifactHash, ...]
    source_verification: tuple[Mapping[str, Any], ...]
    source_evidence: tuple[OfficeCliEvidence, ...]
    rebuilt_evidence: tuple[OfficeCliEvidence, ...]
    ledger: tuple[DispositionLedgerEntry, ...]
    projected: ProjectionResult | None = None
    page_responses: tuple[PageResponse, ...] = ()
    rebuilt_objects: tuple[RebuiltObject, ...] = ()
    # The rebuilt issues this run could not bind to a selected source identity.
    # They are not a side list: every one of them is also a material delta and a
    # blocking diagnostic, and this is the reviewer's view of *why* the binding
    # failed for each.
    unbound_rebuilt: tuple[UnboundRebuiltIssue, ...] = ()
    rules: tuple[NormalizationRule, ...] = COMPARISON_RULES
    # Where the projection's own artifacts were published, keyed by role.  They
    # are the artifacts the verdict is about, so they travel with the result
    # instead of disappearing with a temporary directory.
    projection_artifacts: Mapping[str, str] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.outcome is GateOutcome.BLOCK

    @property
    def accepted(self) -> bool:
        return self.outcome is not GateOutcome.BLOCK

    @property
    def blocked_pages(self) -> tuple[GatePageRecord, ...]:
        """The selected pages that could not be projected at all."""
        return tuple(page for page in self.pages if page.blocked)

    @property
    def projected_pages(self) -> tuple[GatePageRecord, ...]:
        """The selected pages that were projected, rebuilt and read back."""
        return tuple(page for page in self.pages if not page.blocked)

    @property
    def source_map_path(self) -> str | None:
        """The published source map, if this run published one."""
        return self.projection_artifacts.get("source_map")

    @property
    def projection_report_path(self) -> str | None:
        """The published projection report, if this run published one."""
        return self.projection_artifacts.get("projection_report")

    @property
    def canonical_html_path(self) -> str | None:
        """The published Canonical Author HTML, if this run published one."""
        return self.projection_artifacts.get("canonical_author_html")

    @property
    def proxy_assets(self) -> tuple[str, ...]:
        """The published object-local proxy assets, in emission order.

        The projection writes its proxy assets beside the document it is
        producing, which is a temporary directory; publication copies them into
        the gate directory's ``projection`` folder, and this is where they can be
        found after the call returns.
        """
        if not self.published or not self.output_directory:
            return ()
        directory = Path(self.output_directory) / PROJECTION_DIRECTORY_NAME
        return tuple(
            str(path)
            for path in sorted(directory.glob("proxy-*.png"))
        )

    @property
    def counts(self) -> dict[str, int]:
        native = sum(1 for item in self.ledger if item.disposition == DISPOSITION_CANONICAL)
        locked = sum(1 for item in self.ledger if item.disposition == DISPOSITION_LOCKED)
        base_only = sum(
            1 for item in self.ledger if item.disposition == DISPOSITION_BASE_ONLY
        )
        return {
            "selected_pages": len(self.pages),
            "projected_pages": len(self.projected_pages),
            "blocked_pages": len(self.blocked_pages),
            "source_objects": len(self.ledger),
            "canonical_editable": native,
            "locked_visual_proxy": locked,
            "base_only_semantic": base_only,
            "native_round_trip": native,
            "excluded_from_native_round_trip": len(self.ledger) - native,
            "locked_proxies_proved": sum(
                1 for page in self.pages for proof in page.proxies if proof.passed
            ),
            "material_deltas": len(self.material_deltas),
            "retained_findings": len(self.retained_findings),
            "scope_evidence": len(self.scope_evidence),
            "blocking_diagnostics": len(self.diagnostics),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GATE_SCHEMA_VERSION,
            "outcome": self.outcome.value,
            "accepted": self.accepted,
            "blocked": self.blocked,
            "published": self.published,
            "output_directory": self.output_directory,
            "report_path": self.report_path,
            "counts": self.counts,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "pages": [item.as_dict() for item in self.pages],
            "page_responses": [item.as_dict() for item in self.page_responses],
            "material_deltas": [item.as_dict() for item in self.material_deltas],
            "retained_findings": [item.as_dict() for item in self.retained_findings],
            "scope_evidence": [item.as_dict() for item in self.scope_evidence],
            "unbound_rebuilt_issues": [
                item.as_dict() for item in self.unbound_rebuilt
            ],
            "artifacts": [item.as_dict() for item in self.artifacts],
            "source_verification": [dict(item) for item in self.source_verification],
            "source_evidence": [item.as_dict() for item in self.source_evidence],
            "rebuilt_evidence": [item.as_dict() for item in self.rebuilt_evidence],
            "comparison_rules": [item.as_dict() for item in self.rules],
        }


# ---------------------------------------------------------------------------
# Normalization and comparison rules
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    """Return text under the report's whitespace normalization.

    Every run of whitespace -- including the line breaks that separate native
    paragraphs -- becomes one space, then the ends are trimmed.  This is how the
    gate *reports* text: a reviewer reads the paragraph structure the source and
    the rebuilt deck each have.
    """
    return " ".join(str(value or "").split())


def compact_text(value: Any) -> str:
    """Return text with every whitespace character removed.

    This is *not* how the gate compares text any more -- see
    :func:`structure_text` for why -- but it stays as the report's
    whitespace-blind rendering, so a reviewer can still see that two spellings
    carry the same characters.
    """
    return "".join(str(value or "").split())


#: Characters that separate content in a way the comparison must preserve.  A
#: paragraph boundary and a hard break are not the same thing as a space, and
#: ``line one\\nline two`` collapsing into ``line oneline two`` is a text
#: corruption that a whitespace-blind comparison cannot see.
_STRUCTURE_BREAKS = {"\r\n": "\n", "\r": "\n", "\n": "\n", "\x0b": "\n", "\x0c": "\n"}

#: The one display-only normalization the product documents.  A non-breaking
#: space is the same character to a reader as a space, so a projection that
#: resolves one into the other has not changed the text.
#:
#: Nothing else is normalized.  In particular U+202F NARROW NO-BREAK SPACE is
#: deliberately absent: the product does not approve it, and a rule that silently
#: widens what may differ is a rule that stops being able to fail.  Python's
#: ``str.split()`` treats U+202F and the other Unicode space separators as
#: whitespace, so the collapse below is done with an explicit character class
#: rather than ``split()`` -- otherwise an unapproved character would be
#: normalized implicitly and this enumeration would be a fiction.
_DISPLAY_ONLY_SPACES = {"\u00a0": " "}

#: Exactly the characters the collapse may treat as a space: the ASCII space and
#: tab.  A Unicode space separator that is not in ``_DISPLAY_ONLY_SPACES`` is a
#: character, and if a projection drops or changes it the comparison must see it.
_COLLAPSIBLE_SPACE_RE = re.compile(r"[ \t]+")


def structure_text(value: Any) -> str:
    """Return text normalized for comparison with its structure preserved.

    The gate compares text under an explicit, enumerated normalization:

    * a paragraph boundary, a hard break and a page break all normalize to one
      ``\\n`` -- they are different PowerPoint constructs that a projection may
      legitimately interchange, and all three mean "a new line starts here";
      ``\\r\\n`` is normalized as one line ending, so a Windows newline does not
      become two;
    * a non-breaking space normalizes to an ordinary space, which is the one
      display-only normalization the product already documents;
    * a run of spaces and tabs becomes one space, so a run boundary cannot
      invent a difference;
    * whitespace touching a line boundary is dropped, so a space before a
      paragraph break is not a lost character;
    * empty trailing lines are dropped -- a trailing paragraph boundary carries
      no content.

    An empty line *between* content is preserved, because it is a paragraph the
    source painted.  Everything else is compared exactly, which is what makes the
    comparison able to fail: ``Hard break probe line\\nsecond visual line`` and
    ``Hard break probe linesecond visual line`` differ under this rule, and no
    character can be dropped, reordered or invented without changing the result.

    The earlier rule removed *all* whitespace, which meant a lost hard break, a
    lost paragraph boundary and two words run together were all invisible to the
    gate -- and were in fact found by visual review instead.
    """
    text = str(value or "")
    for source, replacement in _STRUCTURE_BREAKS.items():
        text = text.replace(source, replacement)
    for source, replacement in _DISPLAY_ONLY_SPACES.items():
        text = text.replace(source, replacement)

    pieces: list[str] = []
    for line in text.split("\n"):
        # Collapse runs of the characters this rule treats as a space, and drop
        # the ones touching either end: whitespace adjacent to a line boundary
        # cannot be a lost character, because it is not adjacent to any content.
        pieces.append(_COLLAPSIBLE_SPACE_RE.sub(" ", line).strip(" "))
    # Trailing empty lines carry no content and are not a structural difference.
    # An empty line between two content lines is kept: it is a paragraph the
    # source painted, and dropping it would hide an empty-paragraph regression.
    while pieces and not pieces[-1]:
        pieces.pop()
    return "\n".join(pieces)


def normalize_issue_condition(message: Any) -> str:
    """Return the condition kind of one OfficeCLI issue message.

    The message's leading sentence is lowercased, every measured number is
    dropped, and what remains is slugged::

        "text overflow: 2 lines at 27.2pt need 65pt, usable 33pt." -> "text_overflow"
        "Shape goes off slide by 10pt"                              -> "shape_goes_off_slide"

    A trailing stop-word fragment left behind by removing the numbers is
    trimmed, so the same condition keeps one stable name whatever values it
    reports.
    """
    text = str(message or "").strip()
    head = re.split(r"[:.;(]", text, maxsplit=1)[0]
    head = _NUMBER_RE.sub(" ", head)
    slug = _CONDITION_SLUG_RE.sub("_", head.lower()).strip("_")
    for suffix in ("_by", "_at", "_to", "_of", "_the", "_a"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return slug or "unclassified"


def issue_measurements(message: Any) -> tuple[IssueMeasurement, ...]:
    """Return the measured values one OfficeCLI issue message reports.

    A measured value is a number with a unit glued to it (``27.2pt``,
    ``65pt``); a bare number immediately followed by a word is not a
    measurement, it is a count that belongs to the sentence (``2 lines``).  The
    unit token is what carries the meaning, so it is used as the label and any
    short word that introduces it is prepended: ``need 65pt, usable 33pt``
    becomes ``need_pt=65`` and ``usable_pt=33``.  Values are always context for
    a condition, never the condition's identity.
    """
    text = str(message or "")
    measurements: list[IssueMeasurement] = []
    for match in _ISSUE_MEASURE_RE.finditer(text):
        unit = (match.group("unit") or "").lower()
        if not unit:
            # A unitless number is a count the sentence already explains; it is
            # not a measured value this rule compares.
            continue
        if unit.startswith("line"):
            unit = "lines"
        before = text[: match.start()].rstrip()
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.]*", before)
        label = unit
        if words:
            candidate = words[-1].lower()
            if candidate not in _MEASUREMENT_STOP_WORDS:
                label = f"{candidate}_{unit}"
        measurements.append(
            IssueMeasurement(
                label=label, value=float(match.group("value")), unit=unit
            )
        )
    return tuple(measurements)


@dataclass(frozen=True)
class IssuePath:
    """The source binding an OfficeCLI issue path carries.

    ``object_path`` is the path as the issue wrote it (``/shape[@id=100000]``)
    and ``full_object_path`` is that path qualified with the slide it belongs to
    (``/slide[1]/shape[@id=100000]``).  The qualified form is the identity every
    OfficeCLI read of a deck agrees on, so it is what a source object's own
    captured path is compared against -- the unqualified form never is.
    """

    slide: int
    object_path: str | None
    scope: str

    @property
    def full_object_path(self) -> str | None:
        if self.object_path is None:
            return None
        return f"/slide[{self.slide}]/{self.object_path.lstrip('/')}"

    @property
    def slide_owned(self) -> bool:
        return self.object_path is not None and self.scope == "object"


def parse_issue_path(path: Any) -> IssuePath | None:
    """Parse ``/slide[N]/shape[@id=M]``, ``/slide[N]``, ``/slide[N] (master)``.

    A path that does not name a slide at all (a package-level finding) is
    ``None``: the gate cannot bind it to a selected page, so it is not part of
    the source-to-rebuilt comparison.
    """
    match = _ISSUE_PATH_RE.match(str(path or ""))
    if match is None:
        return None
    slide = int(match.group("slide"))
    scope = (match.group("scope") or "slide").lower()
    rest = (match.group("rest") or "").strip()
    if scope in {"master", "layout"}:
        return IssuePath(slide=slide, object_path=None, scope=scope)
    if not rest:
        # The finding is about the slide itself -- an inherited cached field on
        # the slide, or a slide-level structural note.  It belongs to no
        # slide-owned object, so it is scope evidence rather than a mapping.
        return IssuePath(slide=slide, object_path=None, scope="slide")
    return IssuePath(slide=slide, object_path=rest, scope="object")


def issue_records(
    raw_issues: Sequence[Mapping[str, Any]],
    *,
    source_key: str,
    slide_to_source_page: Mapping[int, int] | None = None,
) -> tuple[IssueRecord, ...]:
    """Normalize OfficeCLI issue records into source-identity-bound records.

    ``slide_to_source_page`` maps a *rebuilt* slide number to the source page it
    came from; on the rebuilt side it is what lets an issue be compared against
    the source identity instead of the output position.  It is ``None`` when the
    records already come from a source deck, whose slide numbers *are* the
    source page numbers.
    """
    records: list[IssueRecord] = []
    for raw in raw_issues:
        message = str(raw.get("message", "") or "")
        subtype = str(raw.get("subtype", "") or "").strip()
        path = parse_issue_path(raw.get("path"))
        if path is None:
            continue
        source_page = (
            path.slide
            if slide_to_source_page is None
            else slide_to_source_page.get(path.slide, 0)
        )
        if not source_page:
            continue
        records.append(
            IssueRecord(
                source_key=source_key,
                source_page=source_page,
                source_object=path.full_object_path,
                scope=path.scope,
                condition=(
                    _CONDITION_SLUG_RE.sub("_", subtype.lower()).strip("_")
                    or normalize_issue_condition(message)
                ),
                message=message,
                severity=str(raw.get("severity", "")),
                issue_id=str(raw.get("id", "")),
                measured=issue_measurements(message),
            )
        )
    return tuple(records)


def pressure_ratio(record: IssueRecord) -> float | None:
    """Return a condition's measured pressure ratio, or ``None`` if unreadable.

    Only ``text_overflow`` declares one today: ``need_pt / usable_pt``.  A
    condition with no declared rule has no measurable pressure, so presence
    alone decides whether it is worse -- which is what the report's
    ``materially_worsened`` rule says.
    """
    rule = _PRESSURE_RATIO_RULES.get(record.condition)
    if rule is None:
        return None
    numerator = record.measurement(rule[0])
    denominator = record.measurement(rule[1])
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def materially_worsened(source: IssueRecord, rebuilt: IssueRecord) -> bool:
    """Whether a rebuilt same-kind condition is materially worse than the source.

    The two thresholds are both required, so a rebuild that disagrees with the
    source about a usable height by a point stays a retained finding.  A
    condition whose pressure cannot be measured is never declared worse.
    """
    before = pressure_ratio(source)
    after = pressure_ratio(rebuilt)
    if before is None or after is None:
        return False
    delta = after - before
    return (
        delta > OVERFLOW_RATIO_ABSOLUTE_TOLERANCE
        and delta > OVERFLOW_RATIO_RELATIVE_TOLERANCE * max(before, 1e-9)
    )


@dataclass(frozen=True)
class IssueComparison:
    """The three-way split of one source-to-rebuilt issue comparison."""

    material_deltas: tuple[MaterialDelta, ...]
    retained_findings: tuple[RetainedFinding, ...]
    scope_evidence: tuple[ScopeEvidence, ...]
    unbound_rebuilt: tuple[UnboundRebuiltIssue, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "material_deltas": [item.as_dict() for item in self.material_deltas],
            "retained_findings": [item.as_dict() for item in self.retained_findings],
            "scope_evidence": [item.as_dict() for item in self.scope_evidence],
            "unbound_rebuilt": [item.as_dict() for item in self.unbound_rebuilt],
        }


def compare_issues(
    source_records: Sequence[IssueRecord],
    rebuilt_records: Sequence[IssueRecord],
    *,
    identity_to_rebuilt: Mapping[tuple[str, int, str], tuple[int, str]],
    source_identity_selected: Callable[[tuple[str, int, str]], bool] | None = None,
    source_page_selected: Callable[[str, int], bool] | None = None,
    unbound_rebuilt: Sequence[UnboundRebuiltIssue] = (),
) -> IssueComparison:
    """Compare source and rebuilt issues by stable source identity.

    ``identity_to_rebuilt`` maps a source identity to ``(rebuilt_slide,
    emitted_name)``; a rebuilt record is only comparable when its own identity is
    in that map, which is what makes a rebuilt issue attributable to a source
    object at all.  ``source_identity_selected`` decides whether a source
    identity is in this run's scope and ``source_page_selected`` whether a
    slide-level finding's page is; a source finding outside the selected pages is
    neither retained nor a delta, because the gate never read that page.

    ``unbound_rebuilt`` carries the rebuilt issues whose binding failed.  They
    are passed through into the comparison's own ``unbound_rebuilt`` set so the
    one place that decides what a rebuilt issue *means* also decides what an
    unattributable one means -- a material delta -- instead of a caller having
    to remember to consult a second list.

    A source object with *no* finding is compared too: the whole point of the
    comparison is to catch a condition the rebuilt deck introduces, and a clean
    source object is exactly where one would appear.
    """
    selected = source_identity_selected or (lambda _identity: True)
    page_selected = source_page_selected or (lambda _key, _page: True)
    material: list[MaterialDelta] = []
    retained: list[RetainedFinding] = []
    scope: list[ScopeEvidence] = []

    source_by_identity: dict[tuple[str, int, str], list[IssueRecord]] = {}
    for record in source_records:
        identity = record.identity
        if identity is None:
            # A finding about the deck rather than about one slide-owned object:
            # it stays scope evidence, but only for a page this run selected --
            # the gate read exactly the selected pages and reports nothing about
            # the ones it did not read.
            if not page_selected(record.source_key, record.source_page):
                continue
            scope.append(
                ScopeEvidence(
                    source_key=record.source_key,
                    source_page=record.source_page,
                    condition=record.condition,
                    detail=(
                        f"the finding names the slide ({record.scope}) rather than "
                        "a slide-owned object, so it is inherited or slide-level "
                        "scope evidence and is never mapped onto a rebuilt object"
                    ),
                    source_issue=record.as_dict(),
                )
            )
            continue
        if not selected(identity):
            continue
        source_by_identity.setdefault(identity, []).append(record)

    rebuilt_by_identity: dict[tuple[str, int, str], list[IssueRecord]] = {}
    for record in rebuilt_records:
        identity = record.identity
        if identity is None or identity not in identity_to_rebuilt:
            continue
        rebuilt_by_identity.setdefault(identity, []).append(record)

    # Every selected source identity is compared, whether or not the source deck
    # reports anything about it.
    compared = set(source_by_identity) | set(identity_to_rebuilt)
    for identity in sorted(compared):
        source_group = source_by_identity.get(identity, [])
        rebuilt_group = rebuilt_by_identity.get(identity, [])
        mapped = identity_to_rebuilt.get(identity)
        rebuilt_slide, rebuilt_object = mapped if mapped else (0, "")
        source_conditions = {record.condition for record in source_group}
        rebuilt_conditions = {record.condition for record in rebuilt_group}

        for record in source_group:
            if record.condition in rebuilt_conditions:
                worsened_by = next(
                    (
                        candidate
                        for candidate in rebuilt_group
                        if candidate.condition == record.condition
                        and materially_worsened(record, candidate)
                    ),
                    None,
                )
                if worsened_by is not None:
                    material.append(
                        MaterialDelta(
                            source_key=identity[0],
                            source_page=identity[1],
                            source_object=identity[2],
                            condition=record.condition,
                            reason=(
                                "the same condition is materially worsened: "
                                f"pressure ratio {pressure_ratio(record):.4f} -> "
                                f"{pressure_ratio(worsened_by):.4f} exceeds both the "
                                f"absolute tolerance "
                                f"{OVERFLOW_RATIO_ABSOLUTE_TOLERANCE} and the "
                                f"relative tolerance "
                                f"{OVERFLOW_RATIO_RELATIVE_TOLERANCE}"
                            ),
                            rebuilt_slide=rebuilt_slide,
                            rebuilt_object=rebuilt_object,
                            rebuilt_issue=worsened_by.as_dict(),
                            source_issue=record.as_dict(),
                        )
                    )
                else:
                    retained.append(
                        RetainedFinding(
                            source_key=identity[0],
                            source_page=identity[1],
                            source_object=identity[2],
                            condition=record.condition,
                            reason=(
                                "the source object already carries this condition "
                                "and the rebuilt object reproduces it without "
                                "materially worsening its measured pressure"
                            ),
                            rebuilt_slide=rebuilt_slide,
                            rebuilt_object=rebuilt_object,
                            source_issue=record.as_dict(),
                            rebuilt_issue=next(
                                (
                                    candidate.as_dict()
                                    for candidate in rebuilt_group
                                    if candidate.condition == record.condition
                                ),
                                None,
                            ),
                        )
                    )
            elif record.condition in rebuilt_conditions:
                continue
            else:
                # The condition exists only in the source object.  It is still a
                # source-inherent finding, not a repair: the gate does not claim
                # that projection fixed anything.
                retained.append(
                    RetainedFinding(
                        source_key=identity[0],
                        source_page=identity[1],
                        source_object=identity[2],
                        condition=record.condition,
                        reason=(
                            "the source object carries this condition and the "
                            "rebuilt object does not report it; it stays visible "
                            "as a source-inherent finding rather than being "
                            "claimed as repaired"
                        ),
                        rebuilt_slide=rebuilt_slide or None,
                        rebuilt_object=rebuilt_object or None,
                        source_issue=record.as_dict(),
                    )
                )

        for record in rebuilt_group:
            if record.condition in source_conditions:
                continue
            material.append(
                MaterialDelta(
                    source_key=identity[0],
                    source_page=identity[1],
                    source_object=identity[2],
                    condition=record.condition,
                    reason=(
                        "the rebuilt object reports this condition and the source "
                        "object does not; it is rebuilt-only"
                    ),
                    rebuilt_slide=rebuilt_slide,
                    rebuilt_object=rebuilt_object,
                    rebuilt_issue=record.as_dict(),
                    source_issue=None,
                )
            )

    return IssueComparison(
        material_deltas=tuple(material),
        retained_findings=tuple(retained),
        scope_evidence=tuple(scope),
        unbound_rebuilt=tuple(unbound_rebuilt),
    )


def classify_gate_outcome(
    *,
    diagnostics: Sequence[GateDiagnostic],
    material_deltas: Sequence[MaterialDelta],
    retained_findings: Sequence[RetainedFinding],
    scope_evidence: Sequence[ScopeEvidence],
    checks_complete: bool,
) -> GateOutcome:
    """Derive the acceptance outcome from the collected evidence.

    This is the only place the outcome is decided, and it reads evidence only:
    not a subprocess exit code, not a Contract status, not an OfficeCLI
    ``validate`` result.  ``checks_complete`` is false when some check could not
    be run at all (incomplete evidence), which blocks.
    """
    if not checks_complete or diagnostics or material_deltas:
        return GateOutcome.BLOCK
    if retained_findings or scope_evidence:
        return GateOutcome.PASS_WITH_FINDINGS
    return GateOutcome.PASS


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _object_paths_by_name(nodes: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Return the OfficeCLI nodes of one deck, keyed by their stable object name."""
    found: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        name = str((node.get("format") or {}).get("name", "") or "")
        if name:
            found[name] = node
    return found


def _rebuilt_objects(
    shallow: Mapping[str, Any],
    deep: Mapping[str, Any],
) -> tuple[RebuiltObject, ...]:
    """Read every object of the rebuilt deck as OfficeCLI reports it."""
    deep_by_name = _object_paths_by_name(_walk_nodes(deep))
    objects: list[RebuiltObject] = []
    for slide_index, children in enumerate(_children_by_slide(shallow), start=1):
        for child in children:
            format_data = child.get("format") or {}
            name = str(format_data.get("name", "") or "")
            if not name:
                continue
            detailed = deep_by_name.get(name, child)
            detailed_format = detailed.get("format") or format_data
            rows = detailed_format.get("rows")
            columns = detailed_format.get("cols")
            cells: tuple[str, ...] = ()
            if str(child.get("type", "")) == "table":
                cells = tuple(
                    normalize_text(cell.get("text", ""))
                    for row in detailed.get("children", []) or []
                    if str(row.get("type", "")) == "tr"
                    for cell in row.get("children", []) or []
                    if str(cell.get("type", "")) == "tc"
                )
            objects.append(
                RebuiltObject(
                    emitted_name=name,
                    rebuilt_kind=str(child.get("type", "")),
                    rebuilt_slide=slide_index,
                    path=str(child.get("path", "")),
                    text=str(child.get("text", "") or ""),
                    bounds_pt=tuple(
                        _length_points(detailed_format.get(key))
                        for key in ("x", "y", "width", "height")
                    ),  # type: ignore[arg-type]
                    rows=int(rows) if rows is not None else None,
                    columns=int(columns) if columns is not None else None,
                    cells=cells,
                    style=rebuilt_style(detailed),
                )
            )
    return tuple(objects)


def _walk_nodes(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in node.get("children", []) or []:
        yield from _walk_nodes(child)


def _children_by_slide(root: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    return [slide.get("children", []) or [] for slide in root.get("children", []) or []]


_LENGTH_RE = re.compile(
    r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(pt|emu|cm|mm|in|px)?\s*$", re.IGNORECASE
)


def _length_points(value: Any) -> float:
    """Convert an OfficeCLI length to points; an unreadable value is 0.0."""
    if isinstance(value, (int, float)):
        return float(value)
    match = _LENGTH_RE.match(str(value or ""))
    if match is None:
        return 0.0
    amount = float(match.group(1))
    unit = (match.group(2) or "pt").lower()
    return {
        "pt": amount,
        "px": amount * 0.75,
        "cm": amount * 72 / 2.54,
        "mm": amount * 72 / 25.4,
        "in": amount * 72,
        "emu": amount / 12_700,
    }[unit]


def issue_lines(raw_issues: Sequence[Mapping[str, Any]]) -> str:
    """Render structured issue records the way OfficeCLI renders them in prose.

    The gate reads the structured form because it carries the subtype and the
    object path as separate fields, but the evidence keeps the same readable
    one-line-per-issue shape the tool prints, so a reviewer reads a familiar
    rendering of exactly the records that were compared.
    """
    return "\n".join(
        f"[{item.get('id', '')}] {item.get('path', '')}: "
        f"{item.get('message', '')}".strip()
        for item in raw_issues
    )


def collect_issue_records(deck: str | Path) -> tuple[Mapping[str, Any], ...]:
    """Read one deck's structured OfficeCLI issues.

    The structured form is used rather than the prose form because it carries
    the issue subtype and the object path as separate fields, so the gate reads
    the tool's own classification instead of reparsing a sentence.
    """
    payload = _run_officecli("view", deck, "issues", "--json", json_output=True)
    data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
    issues = data.get("issues", []) if isinstance(data, Mapping) else []
    return tuple(item for item in issues if isinstance(item, Mapping))


def collect_deck_tree(deck: str | Path) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Return the rebuilt deck's shallow and deep OfficeCLI reads.

    ``--depth 1`` carries every slide and object identity; ``--depth 5`` carries
    the table matrix and the object properties the readback checks compare.
    """
    shallow_payload = _run_officecli("get", deck, "/", "--depth", "1", json_output=True)
    deep_payload = _run_officecli("get", deck, "/", "--depth", "5", json_output=True)
    shallow = shallow_payload["data"]["results"][0]
    deep = deep_payload["data"]["results"][0]
    return shallow, deep


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateIntake:
    """Everything the comparison step reads, collected but not yet judged.

    The gate seals this bundle and hands it to :func:`evaluate_intake`, which is
    where every comparison rule lives.  Tests that must exercise the rules
    against a condition OfficeCLI cannot be made to produce at will (a native
    table rebuilt with the wrong dimensions, a rebuilt-only issue, a proxy whose
    bytes were swapped) mutate *this* bundle through the ``intake_mutation``
    hook rather than the deck, and every mutation is then judged by the same
    production rules the real run uses.
    """

    projected: ProjectionResult
    rebuilt_path: str
    rebuilt_sha256: str
    source_evidence: tuple[OfficeCliEvidence, ...]
    rebuilt_evidence: tuple[OfficeCliEvidence, ...]
    rebuilt_objects: tuple[RebuiltObject, ...]
    rebuilt_issue_records: tuple[Mapping[str, Any], ...]
    # The selected pages the projection refused to build, in selection order.
    # They are part of the sealed bundle because they are part of what this run
    # read: a page the projection classifies as blocking is evidence about the
    # source deck, and the verdict has to carry it.
    blocked_pages: tuple[BlockedPage, ...] = ()


@dataclass(frozen=True)
class GateEvaluation:
    """The judgement of one sealed intake bundle, before publication."""

    outcome: GateOutcome
    diagnostics: tuple[GateDiagnostic, ...]
    pages: tuple[GatePageRecord, ...]
    material_deltas: tuple[MaterialDelta, ...]
    retained_findings: tuple[RetainedFinding, ...]
    scope_evidence: tuple[ScopeEvidence, ...]
    checks_complete: bool
    projected: ProjectionResult
    source_verification: tuple[Mapping[str, Any], ...]
    source_evidence: tuple[OfficeCliEvidence, ...]
    rebuilt_evidence: tuple[OfficeCliEvidence, ...]
    page_responses: tuple[PageResponse, ...]
    rebuilt_objects: tuple[RebuiltObject, ...]
    unbound_rebuilt: tuple[UnboundRebuiltIssue, ...] = ()
    blocked_pages: tuple[BlockedPage, ...] = ()


@dataclass(frozen=True)
class GateSources:
    """The helpers one gate run uses, so a test can drive the gate without a deck.

    The defaults are the production helpers: the #15 projection seam, the New
    Deck build path, and OfficeCLI's own validation/issues/get reads.  A caller
    that replaces one is responsible for the same behaviour; nothing in the gate
    assumes a helper is the default one.
    """

    project: Callable[[Sequence[SelectedPage], Path, Path | None], ProjectionResult]
    rebuild: Callable[[str, str], Any]
    validate: Callable[[str | Path], str]
    issues: Callable[[str | Path], tuple[Mapping[str, Any], ...]]
    tree: Callable[[str | Path], tuple[Mapping[str, Any], Mapping[str, Any]]]


def _default_sources() -> GateSources:
    def project(
        pages: Sequence[SelectedPage], html_path: Path, proxy_dir: Path | None
    ) -> ProjectionResult:
        return project_pptx_to_author_html(
            PageSelection(pages), html_path, proxy_dir=proxy_dir
        )

    def rebuild(html_path: str, pptx_path: str) -> Any:
        from ..application import build_author_html

        return build_author_html(html_path, pptx_path)

    def validate(deck: str | Path) -> str:
        # The prose form is what OfficeCLI publishes for a human and what the
        # product's existing build path records, so the gate records the same
        # text rather than a second projection of it.
        return str(_run_officecli("validate", deck))

    return GateSources(
        project=project,
        rebuild=rebuild,
        validate=validate,
        issues=collect_issue_records,
        tree=collect_deck_tree,
    )


def _select_build_reply(reply: Any) -> Any:
    """Resolve the New Deck build helper's reply.

    The production helper is ``async`` and returns a ``CommandResult``; a test
    double may return either an awaitable or the result directly, so both are
    accepted and nothing else is.
    """
    if isinstance(reply, Awaitable):
        import asyncio

        return asyncio.run(reply)  # type: ignore[arg-type]
    return reply


def _build_failed(reply: Any) -> str | None:
    """Return why the New Deck build did not produce a usable deck, or ``None``."""
    status = str(getattr(reply, "status", "PASS"))
    if status in {"PASS", "VISUAL_REVIEW_REQUIRED"}:
        return None
    messages = [
        f"{item.code}: {item.message}"
        for item in getattr(reply, "diagnostics", ()) or ()
    ]
    return f"the New Deck build returned {status}: " + "; ".join(messages)


def _emitted_name_conflicts(
    objects: Sequence[RebuiltObject],
) -> tuple[str, ...]:
    """Return the names the rebuilt deck reports more than once."""
    seen: dict[str, int] = {}
    for item in objects:
        seen[item.emitted_name] = seen.get(item.emitted_name, 0) + 1
    return tuple(sorted(name for name, count in seen.items() if count != 1))


def _mapping_failures(projected: ProjectionResult) -> tuple[str, ...]:
    """Prove the disposition ledger and the emitted object set are one-to-one.

    This is an independent re-derivation from the *published* artifacts: the
    ledger that travels with the result, the emitted objects, and the object
    elements the Canonical Author HTML actually contains.  A projection whose
    evidence disagrees with its own artifact is not accepted even if the seam's
    own pre-publication check passed.
    """
    failures: list[str] = []
    ledger = projected.ledger
    identity_seen: dict[tuple[str, int, str], DispositionLedgerEntry] = {}
    for entry in ledger:
        if entry.disposition not in {
            DISPOSITION_CANONICAL,
            DISPOSITION_LOCKED,
            DISPOSITION_BASE_ONLY,
            "unsupported",
            "unresolved",
        }:
            failures.append(
                f"the ledger reports unknown disposition {entry.disposition!r} "
                f"for {entry.source_object}"
            )
        if entry.identity in identity_seen:
            failures.append(
                f"two ledger entries share the source identity {entry.identity}"
            )
        identity_seen[entry.identity] = entry
        if entry.represented_by_container and entry.emitted:
            failures.append(
                f"{entry.source_object} is container-owned and emitted as its own "
                "object at the same time"
            )

    mapped = {entry.html_id: entry for entry in ledger if entry.html_id is not None}
    emitted = {item.html_id: item for item in projected.objects}
    if len(emitted) != len(projected.objects):
        failures.append("two emitted objects share one html id")
    if set(mapped) != set(emitted):
        failures.append(
            "the ledger and the emitted objects disagree about which source "
            f"objects have an element: ledger-only="
            f"{sorted(set(mapped) - set(emitted))}, emitted-only="
            f"{sorted(set(emitted) - set(mapped))}"
        )
    for html_id, entry in mapped.items():
        item = emitted.get(html_id)
        if item is None:
            continue
        if item.identity != entry.identity:
            failures.append(
                f"the emitted object {html_id!r} maps to {item.identity} but its "
                f"ledger entry maps to {entry.identity}"
            )
        if item.disposition != entry.disposition:
            failures.append(
                f"the emitted object {html_id!r} is {item.disposition!r} but its "
                f"ledger entry is {entry.disposition!r}"
            )
    return tuple(failures)


def _artifact_element_ids(html_text: str) -> tuple[str, ...]:
    """Return every object element id the emitted HTML actually contains."""
    return tuple(
        match.group(1)
        for match in re.finditer(r'<[a-z]+ id="([^"]+)"', html_text)
    )


def _identity_failures(intake: GateIntake) -> tuple[str, ...]:
    """Prove the projection result and the rebuilt readback agree on identity.

    Two independent halves of the same invariant, both re-derived from what the
    run collected rather than from the projection's report:

    * the emitted object set is one-to-one with the disposition ledger
      (:func:`_mapping_failures`), and
    * every emitted slot names exactly one source identity, and that identity is
      the one the ledger classified.
    """
    failures = list(_mapping_failures(intake.projected))
    identities: dict[tuple[str, int, str], str] = {}
    for item in intake.projected.objects:
        previous = identities.get(item.identity)
        if previous is not None:
            failures.append(
                f"two emitted objects ({previous!r} and {item.html_id!r}) claim "
                f"the same source identity {item.identity}"
            )
        identities[item.identity] = item.html_id
    return tuple(failures)


def _source_map_failures(projected: ProjectionResult) -> tuple[str, ...]:
    """Prove the published source map agrees with the published artifacts."""
    failures: list[str] = []
    source_map = projected.source_map
    objects = source_map.get("objects", []) if isinstance(source_map, Mapping) else []
    if len(objects) != len(projected.objects):
        failures.append(
            f"the source map lists {len(objects)} object(s) but the projection "
            f"emitted {len(projected.objects)}"
        )
    by_id = {str(item.get("html_id")): item for item in objects if isinstance(item, Mapping)}
    for item in projected.objects:
        record = by_id.get(item.html_id)
        if record is None:
            failures.append(f"the source map has no entry for {item.html_id!r}")
            continue
        if record.get("source_object") != item.source_object:
            failures.append(
                f"the source map binds {item.html_id!r} to "
                f"{record.get('source_object')!r} instead of {item.source_object!r}"
            )
        if record.get("emitted_name") != item.emitted_name:
            failures.append(
                f"the source map records emitted name "
                f"{record.get('emitted_name')!r} for {item.html_id!r} instead of "
                f"{item.emitted_name!r}"
            )
    ledger = source_map.get("ledger", []) if isinstance(source_map, Mapping) else []
    if len(ledger) != len(projected.ledger):
        failures.append(
            f"the source map carries {len(ledger)} ledger entr(ies) but the "
            f"projection classified {len(projected.ledger)} source object(s)"
        )
    for entry in projected.ledger:
        if entry.source_sha256 == "":
            failures.append(
                f"the ledger entry for {entry.source_object} is not bound to a "
                "source hash"
            )
    return tuple(failures)


def _proxy_proof(
    item: ProjectedObject,
    *,
    pixels_per_point: float,
    rebuilt: RebuiltObject | None,
    recorded_sha256: str | None = None,
    published_asset: str | None = None,
) -> ProxyIsolationProof:
    """Measure one locked proxy's object-isolation evidence.

    The asset is treated as untrusted bytes: its PNG header is read, its raster
    density is measured against the slide width the object came from, the guard
    band is re-measured for paint that cannot belong to the target, the raster is
    measured for paint of its own so a proxy that shows nothing is refused rather
    than accepted as an image of the right size, and the bytes are hashed so a
    swapped or recompressed asset is visible.  Nothing is read back from the
    projection's own report: those are the claims this proof exists to check, and
    the proxy's payload as the emitted document carries it is one of them.
    """
    from PIL import Image

    failures: list[str] = []
    recorded_path = published_asset or item.proxy_asset
    # The bytes that are measured are the ones the run is holding; the path that
    # is *recorded* is where the evidence directory will hold them, so a reviewer
    # opens a file that survives the run.
    asset_path = item.proxy_asset
    asset_sha256: str | None = None
    width = height = 0
    guard_fraction = 0.0
    background: tuple[int, int, int] | None = None
    paint_pixels = 0
    raster_pixels = 0

    # The crop is the union of the object's declared rectangle and the rectangle
    # its paint actually occupies, so the declared rectangle plus the guard band
    # is a floor rather than the whole image: a no-autofit line painted outside
    # its own box widens the crop, and the evidence has to measure that crop
    # rather than refuse it.  ``proxy_geometry`` is re-derived from the published
    # image further down and the two are compared, so this is the claim being
    # checked, not the check itself.
    geometry = item.proxy_geometry
    declared_left = int(round(item.bounds_px[0])) - PROXY_GUARD_PX
    declared_top = int(round(item.bounds_px[1])) - PROXY_GUARD_PX
    floor_width = int(round(item.bounds_px[2])) + PROXY_GUARD_PX * 2
    floor_height = int(round(item.bounds_px[3])) + PROXY_GUARD_PX * 2
    expected_width = (
        geometry.rect_px[2] if geometry is not None else floor_width
    )
    expected_height = (
        geometry.rect_px[3] if geometry is not None else floor_height
    )
    if geometry is not None:
        # Where the declared rectangle sits inside the published crop, which is
        # also where the guard band around it sits.
        band_left = int(round(item.bounds_px[0])) - geometry.rect_px[0] - PROXY_GUARD_PX
        band_top = int(round(item.bounds_px[1])) - geometry.rect_px[1] - PROXY_GUARD_PX
        band_width = floor_width
        band_height = floor_height
    else:
        band_left = band_top = 0
        band_width, band_height = floor_width, floor_height
    # The guard band can only be judged where it exists.  When the crop expanded
    # to cover paint the object's own text put outside its rectangle, the paint
    # reaches the image's edge on that axis and the frame around the declared
    # rectangle is no longer inside the image at all; what the expanded crop is
    # judged on instead is that it covers the declared rectangle it stands for.
    # The frame is present exactly when the crop is the declared rectangle plus
    # the band, which is what a crop that did not expand is.
    band_measured = geometry is None
    if not asset_path:
        failures.append("the locked proxy has no asset on disk")
    else:
        path = Path(asset_path)
        if not path.is_file():
            failures.append(f"the locked proxy asset does not exist: {path}")
        else:
            payload = path.read_bytes()
            asset_sha256 = hashlib.sha256(payload).hexdigest()
            try:
                with Image.open(path) as image:
                    rgb = image.convert("RGB")
                    width, height = rgb.size
                    raster_pixels = width * height
                    background, guard_fraction = _guard_band_paint(
                        rgb, band_width, band_height, left=band_left, top=band_top
                    )
                    paint_pixels = _painted_pixels(rgb, background)
                if geometry is not None:
                    band_measured = (
                        band_left >= 0
                        and band_top >= 0
                        and band_left + band_width <= width
                        and band_top + band_height <= height
                    )
            except Exception as exc:  # noqa: BLE001 - any decode failure blocks
                failures.append(f"the locked proxy asset is not a readable PNG: {exc}")
    if recorded_sha256 is not None and asset_sha256 is not None:
        if recorded_sha256 != asset_sha256:
            failures.append(
                "the emitted document's proxy payload does not match the asset "
                "the projection published"
            )

    if width and width < expected_width - PROXY_RASTER_TOLERANCE_PX:
        failures.append(
            f"target bounds: the proxy raster is {width}px wide but the object's "
            f"declared rectangle plus a {PROXY_GUARD_PX}px guard band on each side "
            f"is {floor_width}px, so the crop does not even cover the rectangle it "
            "represents"
        )
    elif (
        width
        and geometry is None
        and abs(width - expected_width) > PROXY_RASTER_TOLERANCE_PX
    ):
        failures.append(
            f"target bounds: the proxy raster is {width}px wide but the target "
            f"rectangle plus a {PROXY_GUARD_PX}px guard band on each side is "
            f"{expected_width}px"
        )
    if height and height < expected_height - PROXY_RASTER_TOLERANCE_PX:
        failures.append(
            f"target bounds: the proxy raster is {height}px high but the object's "
            f"declared rectangle plus a {PROXY_GUARD_PX}px guard band on each side "
            f"is {floor_height}px, so the crop does not even cover the rectangle it "
            "represents"
        )
    elif (
        height
        and geometry is None
        and abs(height - expected_height) > PROXY_RASTER_TOLERANCE_PX
    ):
        failures.append(
            f"target bounds: the proxy raster is {height}px high but the target "
            f"rectangle plus a {PROXY_GUARD_PX}px guard band on each side is "
            f"{expected_height}px"
        )
    if geometry is not None and width and height:
        if (
            geometry.rect_px[2] != width
            or geometry.rect_px[3] != height
            or declared_left + geometry.origin_px[0] != geometry.rect_px[0]
            or declared_top + geometry.origin_px[1] != geometry.rect_px[1]
        ):
            failures.append(
                "target bounds: the projection reports the proxy at "
                f"{geometry.rect_px} but the published raster is {width}x{height}px "
                f"at origin {geometry.origin_px} from a declared rectangle at "
                f"({declared_left}, {declared_top})"
            )

    # The density is the render's own pixels-per-point, recovered from the
    # raster: the crop is the target rectangle plus the guard band, so the band
    # is removed before the raster is measured against the target's extent.  A
    # zero-extent rectangle -- a vertical connector, whose width OfficeCLI
    # reports as 0pt and whose raster is therefore nothing but the guard band --
    # carries no information about the scale on that axis, so the other axis is
    # measured instead.  When neither axis has an extent there is no scale to
    # recover and the proxy is not judged on one.  An expanded crop is measured
    # on the declared rectangle's own span, which is what the density is the
    # density *of*; the rest of the image is the object's overflow, at the same
    # scale because it came out of the same render.
    density = _raster_density(
        width=floor_width if geometry is not None else width,
        height=floor_height if geometry is not None else height,
        bounds_pt=item.bounds_pt,
        guard_px=PROXY_GUARD_PX,
    )
    if density is not None and density + PROXY_DENSITY_TOLERANCE < pixels_per_point:
        failures.append(
            f"raster density: the proxy renders at {density:.4f} px/pt but the "
            f"Author canvas draws it at {pixels_per_point:.4f} px/pt"
        )
    if width and band_measured and guard_fraction > GUARD_BAND_CONTAMINATION_FRACTION:
        failures.append(
            f"contamination: {guard_fraction:.4f} of the {PROXY_GUARD_PX}px guard "
            "band carries paint that cannot belong to the target object, which "
            f"exceeds the allowed {GUARD_BAND_CONTAMINATION_FRACTION}"
        )
    if raster_pixels and background is not None and paint_pixels == 0:
        # Measured from the proxy's own bytes, not asserted from the rebuilt
        # deck: a rebuilt object of the right name and kind can still be an
        # image of nothing.  The comparison is against the raster's own sampled
        # background, so an object whose paint is a legitimate near-white still
        # differs from the slide's background and still passes.
        failures.append(
            "target survival: the proxy's own raster carries no paint at all -- "
            f"all {raster_pixels} pixel(s) of the {width}x{height} proxy are the "
            f"background {background} it was cropped out of, so the object's "
            "content did not survive its reconstruction and the image is not a "
            "representation of it"
        )
    if rebuilt is None:
        failures.append(
            "target survival: the rebuilt PPTX holds no object with the emitted "
            f"name {item.emitted_name!r}"
        )
    elif item.projected_kind in {"picture", "image"} and rebuilt.rebuilt_kind != "picture":
        failures.append(
            "target survival: the rebuilt object is "
            f"{rebuilt.rebuilt_kind!r} rather than a picture, so the proxy's own "
            "paint is not what the rebuilt deck carries"
        )
    if item.disposition in BLOCKING_DISPOSITIONS:
        failures.append(
            f"the object's disposition is {item.disposition!r}, which blocks "
            "acceptance"
        )

    return ProxyIsolationProof(
        source_key=item.source_key,
        source_page=item.source_slide,
        source_object=item.source_object,
        emitted_name=item.emitted_name,
        disposition=item.disposition,
        asset=recorded_path,
        asset_sha256=asset_sha256,
        recorded_asset_sha256=recorded_sha256,
        raster_width_px=width,
        raster_height_px=height,
        expected_width_px=expected_width,
        expected_height_px=expected_height,
        raster_density=density if density is not None else 0.0,
        required_density=pixels_per_point,
        guard_band_px=PROXY_GUARD_PX,
        guard_band_paint_fraction=guard_fraction,
        target_bounds_pt=item.bounds_pt,
        background_rgb=background,
        rebuilt_kind=rebuilt.rebuilt_kind if rebuilt else None,
        disposition_blocking=item.disposition in BLOCKING_DISPOSITIONS,
        paint_pixels=paint_pixels,
        raster_pixels=raster_pixels,
        failures=tuple(failures),
    )


def _raster_density(
    *,
    width: int,
    height: int,
    bounds_pt: tuple[float, float, float, float],
    guard_px: int,
) -> float | None:
    """Return a proxy raster's own pixels-per-point, or ``None`` if unmeasurable.

    The raster is the target rectangle plus one guard band per side, so the band
    is removed from the raster and the remainder is divided by the target's
    extent on that axis.  The axis with the larger extent is used, because both
    axes of one render share one scale and a rectangle with no extent on one axis
    -- OfficeCLI reports a vertical connector's width as ``0pt``, and its raster
    is then nothing but the two guard bands -- says nothing about the scale.

    ``None`` means the proxy carries no measurable scale at all, which is a
    different statement from "the scale is zero": the density rule compares a
    measurement against the canvas density, and there is nothing to compare.
    """
    if not width or not height:
        return None
    if bounds_pt[2] >= bounds_pt[3]:
        rasters = (width, height)
        extents = (bounds_pt[2], bounds_pt[3])
    else:
        rasters = (height, width)
        extents = (bounds_pt[3], bounds_pt[2])
    for raster, extent in zip(rasters, extents):
        if extent > 0:
            return max(0.0, (raster - guard_px * 2) / extent)
    return None


def _guard_band_paint(
    rgb: Any,
    expected_width: int,
    expected_height: int,
    *,
    left: int = 0,
    top: int = 0,
) -> tuple[tuple[int, int, int] | None, float]:
    """Return ``(background, paint fraction of the guard band)`` for one proxy.

    The guard band is the ``PROXY_GUARD_PX``-wide frame around the *declared*
    rectangle inside the published crop, which for an object whose paint stays
    inside its own rectangle is the whole raster and for an object that overflows
    is a frame somewhere inside it.  ``left``/``top`` place that frame, so the
    band is measured where it really is instead of at the image's edge, where an
    expanded crop legitimately carries the object's own overflow.

    The background is the modal colour at the raster's four corners -- the bare
    background the crop was taken out of -- so the test is "does the band carry
    paint other than that", not "is the band exactly one colour".  A raster too
    small to hold a band reports no measurable contamination and lets the bounds
    failure speak.
    """
    # The guard band is the frame immediately *outside* the declared rectangle,
    # which is also the frame immediately inside the published crop when the crop
    # is exactly the declared rectangle plus that band.  ``left``/``top`` place
    # the frame's own outer corner, so the declared rectangle begins one band in
    # and the frame reaches one band out again.
    #
    # A crop the object's own overflow widened does not necessarily hold that
    # whole frame -- the paint reaches the image's own edge on the axis it
    # overflowed -- so the frame is measured where it exists and the caller judges
    # contamination only on a crop that really contains it.  Nothing is excused:
    # an expanded crop is judged on coverage instead, which is what says whether
    # the object's overflow had anywhere to go.
    band = PROXY_GUARD_PX
    if rgb.width <= band * 2 or rgb.height <= band * 2:
        return None, 0.0
    corners = (
        (0, 0),
        (rgb.width - 1, 0),
        (0, rgb.height - 1),
        (rgb.width - 1, rgb.height - 1),
    )
    samples = [
        tuple(int(channel) for channel in rgb.getpixel(point)[:3]) for point in corners
    ]
    background = max(set(samples), key=samples.count)

    declared_left = left + band
    declared_top = top + band
    declared_right = declared_left + expected_width
    declared_bottom = declared_top + expected_height
    band_pixels: list[tuple[int, int, int]] = []
    for y in range(max(0, top), min(rgb.height, top + expected_height + band * 2)):
        for x in range(max(0, left), min(rgb.width, left + expected_width + band * 2)):
            if (
                declared_left <= x < declared_right
                and declared_top <= y < declared_bottom
            ):
                # Inside the declared rectangle: the object's own paint.
                continue
            band_pixels.append(tuple(int(c) for c in rgb.getpixel((x, y))[:3]))
    if not band_pixels:
        return background, 0.0
    painted = sum(
        1
        for pixel in band_pixels
        if max(abs(a - b) for a, b in zip(pixel, background)) > PROXY_PAINT_TOLERANCE
    )
    return background, painted / len(band_pixels)


def _painted_pixels(rgb: Any, background: tuple[int, int, int] | None) -> int:
    """Return how many of a proxy's own pixels are paint rather than background.

    Target survival measured from the proxy instead of asserted from the rebuilt
    deck.  ``background`` is the raster's own sampled background, so the question
    is "does this image show anything that is not the empty space it was cropped
    out of" rather than "is this image not white": a legitimately near-white
    object differs from a background it does not fill and is counted as paint,
    while an object whose content never reached the reconstruction is nothing but
    background and counts zero.

    The colour histogram is bucketed rather than scanned pixel by pixel, so the
    count is complete without iterating a raster that can hold a full slide.
    """
    if background is None:
        return 0
    counts = rgb.getcolors(rgb.width * rgb.height + 1)
    if counts is None:  # pragma: no cover - unreachable for a finite raster
        return 0
    return sum(
        count
        for count, colour in counts
        if max(abs(channel - expected) for channel, expected in zip(colour, background))
        > PROXY_PAINT_TOLERANCE
    )


def _img_source(html_text: str, html_id: str) -> str | None:
    """Return the ``src`` of one emitted ``<img>`` object, or ``None``.

    A proxy's emitted bytes are part of the published artifact: the ``src`` the
    compiler consumed is the same payload the projector wrote to disk, so the
    two can be compared and a report that describes an image the artifact does
    not contain is a failure rather than a summary.
    """
    match = re.search(
        rf'<img id="{re.escape(html_id)}"[^>]*\ssrc="([^"]*)"', html_text
    )
    return match.group(1) if match else None


def _data_uri_sha256(source: str | None) -> str | None:
    """Return the SHA-256 of a data URI's payload, or ``None``."""
    if not source or not source.startswith("data:"):
        return None
    _, _, payload = source.partition(",")
    try:
        return hashlib.sha256(base64.b64decode(payload, validate=True)).hexdigest()
    except (ValueError, TypeError):
        return None


def source_table_matrix(
    source_path: str, source_object: str
) -> tuple[tuple[str, ...], ...]:
    """Return one *source* native table's cell matrix, read from the source deck.

    The gate's table check used to build its expected matrix from the projection's
    own Canonical Author HTML -- the artifact the New Deck compiler consumed -- so
    it compared the rebuilt table against the deck rebuilt from that same HTML.  A
    row, column or cell the projector dropped on the way out was therefore carried
    faithfully into the rebuilt deck and reported as a pass, which is the opposite
    of an independent readback.

    Reading the source deck is what makes the comparison able to fail: the target
    is the table the source actually contains, not a restatement of the
    projection's own output.

    Raises :class:`SourceTableUnavailable` when the source matrix cannot be read,
    so a read failure is reported as its own blocking condition instead of
    arriving as an empty table that happens to disagree with the rebuilt one.
    """
    if not source_path or not source_object:
        raise SourceTableUnavailable(
            f"the projection recorded no source identity for {source_object!r}"
        )
    try:
        node = _read_source_node(source_path, source_object)
    except Exception as error:  # noqa: BLE001 - re-raised as a gate condition
        raise SourceTableUnavailable(
            f"OfficeCLI could not read {source_object} from the source deck: "
            f"{type(error).__name__}: {error}"
        ) from error
    rows: list[tuple[str, ...]] = []
    for row in node.get("children") or []:
        if str(row.get("type")) != "tr":
            continue
        values = [
            normalize_text(cell.get("text", ""))
            for cell in (row.get("children") or [])
            if str(cell.get("type")) == "tc"
        ]
        rows.append(tuple(values))
    if not rows:
        raise SourceTableUnavailable(
            f"the source readback of {source_object} names no table row, so the "
            "source matrix cannot be established"
        )
    widths = {len(row) for row in rows}
    if len(widths) != 1:
        # The column count cannot come from the first row alone: a ragged matrix
        # is a source readback this check cannot trust, so it says so instead of
        # picking one row's width as the truth.
        raise SourceTableUnavailable(
            f"the source readback of {source_object} is ragged: its rows report "
            f"column counts {sorted(widths)}"
        )
    return tuple(rows)


class SourceTableUnavailable(RuntimeError):
    """A source native table could not be read, so its matrix cannot be checked.

    Distinct from "the rebuilt table is wrong": this says the *expectation* could
    not be established.  It blocks, and it reports itself under its own code, so a
    reviewer can tell a genuine empty table from a source read that failed.
    """

    code = "source_table_readback_unavailable"


def _read_source_node(source_path: str, source_object: str) -> Mapping[str, Any]:
    """Read one node of a source deck through OfficeCLI, with the seam's retry."""
    from .acceptance import _run_officecli

    text = _run_officecli(
        "get", source_path, source_object, "--depth", "2", "--json"
    )
    payload = json.loads(text)
    results = payload.get("data", {}).get("results")
    if not isinstance(results, list) or not results:
        raise ValueError(f"no result for {source_object} in {source_path}")
    return results[0]


def _table_readback(
    item: ProjectedObject,
    *,
    html_text: str,
    rebuilt: RebuiltObject | None,
) -> TableCheck:
    """Check one native table against the *source* table and the rebuilt one.

    ``expected_*`` is the source deck's own matrix; the emitted HTML is read only
    for the per-cell source mapping, which is a property of the projection rather
    than a claim about the source.
    """
    cell_paths = _emitted_table_cell_paths(html_text, item.html_id)
    cells = source_table_matrix(item.source_path, item.source_object)
    return TableCheck(
        source_key=item.source_key,
        source_page=item.source_slide,
        source_object=item.source_object,
        emitted_name=item.emitted_name,
        rebuilt_slide=rebuilt.rebuilt_slide if rebuilt else 0,
        expected_kind=item.projected_kind,
        rebuilt_kind=rebuilt.rebuilt_kind if rebuilt else "",
        expected_rows=len(cells),
        expected_columns=len(cells[0]) if cells else 0,
        rebuilt_rows=rebuilt.rows or 0 if rebuilt else 0,
        rebuilt_columns=rebuilt.columns or 0 if rebuilt else 0,
        expected_cells=tuple(value for row in cells for value in row),
        rebuilt_cells=rebuilt.cells if rebuilt else (),
        cell_paths=cell_paths,
    )


def _emitted_table_cell_paths(html_text: str, html_id: str) -> tuple[str, ...]:
    """Return the emitted table's per-cell source mapping, in reading order.

    Only the mapping, not a matrix.  This function used to return the emitted
    cell text as well and the table check used it as the *expectation*, which made
    the check compare the rebuilt table against the deck rebuilt from the same
    HTML.  The expectation now comes from the source deck
    (:func:`source_table_matrix`), so the emitted HTML is read for the one thing
    that really is a property of the projection: which source cell each emitted
    cell claims to come from.
    """
    from lxml import html as lxml_html

    document = lxml_html.fromstring(html_text)
    nodes = document.xpath(f'//*[@id="{html_id}"]')
    if not nodes:
        return ()
    return tuple(
        str(cell.get("data-cell-path", ""))
        for row in nodes[0].xpath(".//tr")
        for cell in row.xpath("./td|./th")
    )


def _style_declarations(html_text: str, html_id: str) -> dict[str, str]:
    """Return the emitted object's own inline style declarations.

    The declaration names are the canonical surface's supported formatting
    vocabulary; the values are what the emitted object declares and what the
    rebuilt object's readback is compared against.
    """
    from lxml import html as lxml_html

    document = lxml_html.fromstring(html_text)
    nodes = document.xpath(f'//*[@id="{html_id}"]')
    if not nodes:
        return {}
    node = nodes[0]
    element = node if node.tag == "div" else None
    if element is None:
        # A proxy is an <img> whose guard-band style is not a formatting
        # declaration, so a non-div object declares no text style of its own.
        element = node
    declarations: dict[str, str] = {}
    for part in str(element.get("style", "") or "").split(";"):
        name, _, value = part.partition(":")
        name = name.strip()
        if name and value.strip():
            declarations[name] = value.strip()
    return declarations


def _collapse_findings(
    findings: Sequence[RetainedFinding],
) -> tuple[RetainedFinding, ...]:
    """Return one retained finding per (source identity, condition).

    A condition can be reported by more than one check -- an overflow and a
    whitespace-only text difference can sit on the same object -- and each check
    describes its own evidence.  Collapsing keeps the first spelling of each
    identity/condition pair, so the report reads as a list of conditions rather
    than as a list of checks.
    """
    collapsed: dict[tuple[Any, ...], RetainedFinding] = {}
    for item in findings:
        key = (item.source_key, item.source_page, item.source_object, item.condition)
        collapsed.setdefault(key, item)
    return tuple(collapsed.values())


def _whitespace_only_findings(
    readbacks: Sequence[TextReadback], tables: Sequence[TableCheck]
) -> tuple[RetainedFinding, ...]:
    """Return the findings for text that differs in whitespace placement alone."""
    findings: list[RetainedFinding] = []
    for readback in readbacks:
        if not readback.whitespace_only_difference:
            continue
        findings.append(
            RetainedFinding(
                source_key=readback.source_key,
                source_page=readback.source_page,
                source_object=readback.source_object,
                condition="text_whitespace_placement",
                reason=(
                    "the rebuilt object and the source object carry the same "
                    "characters but place their whitespace differently; the "
                    "difference is reported here and does not block acceptance"
                ),
                rebuilt_slide=readback.rebuilt_slide,
                rebuilt_object=readback.emitted_name,
                source_issue={
                    "expected": normalize_text(readback.expected_text),
                    "rebuilt": normalize_text(readback.rebuilt_text),
                },
                rebuilt_issue={
                    "expected_compact": compact_text(readback.expected_text),
                    "rebuilt_compact": compact_text(readback.rebuilt_text),
                },
            )
        )
    for check in tables:
        # A cell whose text differs under the structure-preserving rule is already
        # a blocking table failure; it must not also be reported here as an
        # accepted whitespace detail, or the same condition would be both a
        # failure and a finding.
        positions = check.space_only_cell_positions()
        if not positions:
            continue
        findings.append(
            RetainedFinding(
                source_key=check.source_key,
                source_page=check.source_page,
                source_object=check.source_object,
                condition="table_cell_whitespace_placement",
                reason=(
                    f"{len(positions)} table cell(s) carry the same characters "
                    "and the same line structure but place their spaces "
                    "differently; the difference is reported here and does not "
                    "block acceptance"
                ),
                rebuilt_slide=check.rebuilt_slide or None,
                rebuilt_object=check.emitted_name,
                source_issue={
                    "expected": [check.expected_cells[index] for index in positions],
                },
                rebuilt_issue={
                    "rebuilt": [check.rebuilt_cells[index] for index in positions],
                },
            )
        )
    return tuple(findings)


def evaluate_intake(
    intake: GateIntake,
    *,
    html_text: str,
    pixels_per_point: float,
    published_proxies: Mapping[str, str] | None = None,
) -> GateEvaluation:
    """Judge one sealed intake bundle.

    Every comparison rule lives here and nowhere else, so a test that feeds the
    bundle a mutated condition is judged by exactly the rules a real run uses.
    ``published_proxies`` maps each proxy asset the run is holding to the path it
    will occupy in the published evidence directory, so the isolation proof a
    reviewer reads names a file that will still exist.
    """
    proxy_published_paths = published_proxies or {}
    projected = intake.projected
    diagnostics: list[GateDiagnostic] = []

    # -- the projection's own identity invariants, re-derived from artifacts --
    checks_complete = True
    for failure in _mapping_failures(projected):
        diagnostics.append(
            GateDiagnostic(
                code="ambiguous_mapping",
                message=failure,
            )
        )
    for failure in _source_map_failures(projected):
        diagnostics.append(
            GateDiagnostic(code="incomplete_evidence", message=failure)
        )
    for failure in _identity_failures(intake):
        diagnostics.append(GateDiagnostic(code="ambiguous_mapping", message=failure))

    # -- stable source mapping: identity -> (rebuilt slide, emitted name) ------
    identity_to_rebuilt: dict[tuple[str, int, str], tuple[int, str]] = {}
    for item in projected.objects:
        identity_to_rebuilt[item.identity] = (item.output_slide, item.emitted_name)
        if item.disposition in BLOCKING_DISPOSITIONS:
            diagnostics.append(
                GateDiagnostic(
                    code="blocking_disposition",
                    message=(
                        f"the source object is {item.disposition!r}: "
                        f"{item.reason or item.reason_code}"
                    ),
                    source_key=item.source_key,
                    source_page=item.source_slide,
                    source_object=item.source_object,
                    rebuilt_slide=item.output_slide,
                    rebuilt_object=item.emitted_name,
                )
            )

    selected_identities = set(identity_to_rebuilt)
    selected_page_keys = {
        (item.source_key, item.source_slide) for item in projected.objects
    }
    for slide in projected.slides:
        selected_page_keys.add((slide.source_key, slide.source_slide))
    rebuilt_by_name = {item.emitted_name: item for item in intake.rebuilt_objects}
    for name in _emitted_name_conflicts(intake.rebuilt_objects):
        diagnostics.append(
            GateDiagnostic(
                code="ambiguous_mapping",
                message=(
                    f"the rebuilt deck reports the object name {name!r} more than "
                    "once, so no source identity can be bound to it"
                ),
            )
        )

    # -- issues, compared by stable source identity ---------------------------
    source_records: list[IssueRecord] = []
    for evidence in intake.source_evidence:
        source_records.extend(
            issue_records(evidence.raw_issue_records, source_key=evidence.label)
        )
    # A rebuilt issue can only be attributed to a source object when the
    # compiler's emitted name for that identity is the object the issue is on,
    # so every rebuilt record is re-keyed through the emitted-name map rather
    # than through the output slide number.  The binding reports what it could
    # not bind as well as what it could: a rebuilt issue nothing owns blocks.
    rebuilt_by_identity, unbound_rebuilt = _rebuilt_records_by_identity(
        intake.rebuilt_issue_records,
        projected=projected,
        rebuilt_by_name=rebuilt_by_name,
    )

    comparison = compare_issues(
        source_records,
        rebuilt_by_identity,
        identity_to_rebuilt=identity_to_rebuilt,
        source_identity_selected=lambda identity: identity in selected_identities,
        source_page_selected=lambda key, page: (key, page) in selected_page_keys,
        unbound_rebuilt=unbound_rebuilt,
    )
    unbound_deltas = tuple(
        _unbound_rebuilt_material_delta(item) for item in comparison.unbound_rebuilt
    )
    for item in comparison.unbound_rebuilt:
        delta = _unbound_rebuilt_material_delta(item)
        diagnostics.append(
            GateDiagnostic(
                code="unbound_rebuilt_issue",
                message=delta.describe(),
                rebuilt_slide=delta.rebuilt_slide or None,
                rebuilt_object=item.path or None,
            )
        )
    for delta in comparison.material_deltas:
        diagnostics.append(
            GateDiagnostic(
                code="material_delta",
                message=delta.describe(),
                source_key=delta.source_key,
                source_page=delta.source_page,
                source_object=delta.source_object,
                rebuilt_slide=delta.rebuilt_slide,
                rebuilt_object=delta.rebuilt_object,
            )
        )

    # -- independent readback -------------------------------------------------
    # The kind the New Deck compiler is asked to create for each projected
    # object, in the readback's own vocabulary.  A locked proxy is compiled as
    # one native picture; everything else keeps the compiler's own kind word.
    # The map is the projection seam's own, so the name the gate looks the object
    # up by and the kind it expects back cannot drift apart.
    expected_kind_by_projected_kind = COMPILED_KIND_BY_PROJECTED_KIND
    text_readbacks: list[TextReadback] = []
    table_checks: list[TableCheck] = []
    proxy_proofs: list[ProxyIsolationProof] = []
    for item in projected.objects:
        rebuilt = rebuilt_by_name.get(item.emitted_name)
        if rebuilt is None:
            diagnostics.append(
                GateDiagnostic(
                    code="missing_rebuilt_object",
                    message=(
                        f"the rebuilt PPTX holds no object named "
                        f"{item.emitted_name!r}, so the projection's own claim "
                        "about this object cannot be verified"
                    ),
                    source_key=item.source_key,
                    source_page=item.source_slide,
                    source_object=item.source_object,
                    rebuilt_slide=item.output_slide,
                    rebuilt_object=item.emitted_name,
                )
            )
            continue
        expected_kind = expected_kind_by_projected_kind.get(
            item.projected_kind, item.projected_kind
        )
        if item.disposition == DISPOSITION_CANONICAL and rebuilt.rebuilt_kind != expected_kind:
            # The emitted name the compiler gives an object encodes the kind it
            # compiled, so a readback whose kind disagrees was not compiled from
            # this projection slot at all.
            diagnostics.append(
                GateDiagnostic(
                    code="native_kind_mismatch",
                    message=(
                        f"the source object projects as {item.projected_kind!r} "
                        f"but the rebuilt object named {item.emitted_name!r} "
                        f"reads back as {rebuilt.rebuilt_kind!r}"
                    ),
                    source_key=item.source_key,
                    source_page=item.source_slide,
                    source_object=item.source_object,
                    rebuilt_slide=rebuilt.rebuilt_slide,
                    rebuilt_object=item.emitted_name,
                )
            )
        if item.disposition == DISPOSITION_CANONICAL:
            if item.projected_kind in {"shape", "textbox"}:
                readback = TextReadback(
                    source_key=item.source_key,
                    source_page=item.source_slide,
                    source_object=item.source_object,
                    emitted_name=item.emitted_name,
                    rebuilt_kind=rebuilt.rebuilt_kind,
                    rebuilt_slide=rebuilt.rebuilt_slide,
                    expected_text=item.text,
                    rebuilt_text=rebuilt.text,
                    # The expectation is the SOURCE object's own captured
                    # declaration; the actual is read from the rebuilt PPTX.  The
                    # generated HTML used to stand in for the expectation, which
                    # made this check compare the projection with itself.
                    style_declarations=expected_style_declarations(item),
                    rebuilt_style=rebuilt.style,
                )
                text_readbacks.append(readback)
                if not readback.matched:
                    diagnostics.append(
                        GateDiagnostic(
                            code="text_readback_mismatch",
                            message=(
                                "the rebuilt object's text does not match the "
                                "source object's text under the explicit "
                                "structure-preserving normalization: expected "
                                f"{structure_text(item.text)!r}, rebuilt "
                                f"{structure_text(rebuilt.text)!r}"
                            ),
                            source_key=item.source_key,
                            source_page=item.source_slide,
                            source_object=item.source_object,
                            rebuilt_slide=rebuilt.rebuilt_slide,
                            rebuilt_object=item.emitted_name,
                        )
                    )
                if not readback.style_matched:
                    # A style mismatch is its own blocking condition with its own
                    # code, so the report says which formatting was lost rather
                    # than only that "the text readback failed".
                    for failure in readback.style_failures() or (
                        readback.rebuilt_style.unavailable
                        or "the rebuilt object reports no readable style",
                    ):
                        diagnostics.append(
                            GateDiagnostic(
                                code="style_readback_mismatch",
                                message=(
                                    "supported formatting did not survive the "
                                    f"rebuild: {failure}"
                                ),
                                source_key=item.source_key,
                                source_page=item.source_slide,
                                source_object=item.source_object,
                                rebuilt_slide=rebuilt.rebuilt_slide,
                                rebuilt_object=item.emitted_name,
                            )
                        )
            elif item.projected_kind == "table":
                try:
                    check = _table_readback(item, html_text=html_text, rebuilt=rebuilt)
                except SourceTableUnavailable as unavailable:
                    # The expectation could not be established, which is its own
                    # blocking condition: reporting it as a dimension mismatch
                    # would blame the rebuilt table for a source read that failed.
                    checks_complete = False
                    diagnostics.append(
                        GateDiagnostic(
                            code=SourceTableUnavailable.code,
                            message=str(unavailable),
                            source_key=item.source_key,
                            source_page=item.source_slide,
                            source_object=item.source_object,
                            rebuilt_slide=rebuilt.rebuilt_slide,
                            rebuilt_object=item.emitted_name,
                        )
                    )
                    continue
                table_checks.append(check)
                for failure in check.failures():
                    diagnostics.append(
                        GateDiagnostic(
                            code="table_structure_mismatch",
                            message=failure,
                            source_key=item.source_key,
                            source_page=item.source_slide,
                            source_object=item.source_object,
                            rebuilt_slide=rebuilt.rebuilt_slide,
                            rebuilt_object=item.emitted_name,
                        )
                    )
        if item.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}:
            proof = _proxy_proof(
                item,
                pixels_per_point=pixels_per_point,
                rebuilt=rebuilt,
                recorded_sha256=_data_uri_sha256(
                    _img_source(html_text, item.html_id)
                ),
                published_asset=proxy_published_paths.get(item.proxy_asset or ""),
            )
            proxy_proofs.append(proof)
            for failure in proof.failures:
                diagnostics.append(
                    GateDiagnostic(
                        code="proxy_isolation_failed",
                        message=failure,
                        source_key=item.source_key,
                        source_page=item.source_slide,
                        source_object=item.source_object,
                        rebuilt_slide=item.output_slide,
                        rebuilt_object=item.emitted_name,
                    )
                )

    # -- expected inherited-paint omissions -----------------------------------
    scope_evidence = list(comparison.scope_evidence)
    for entry in projected.ledger:
        if entry.disposition != DISPOSITION_BASE_ONLY:
            continue
        scope_evidence.append(
            ScopeEvidence(
                source_key=entry.source_key,
                source_page=entry.source_page,
                condition="inherited_paint_omission",
                detail=(
                    "the source object's visible appearance depends on a value the "
                    "slide does not own, so the rebuilt deck legitimately omits "
                    "that inherited paint; the object is reported as base-only "
                    "scope evidence and never as a repaired slide-owned object"
                ),
                source_issue={
                    "path": entry.source_object,
                    "reason_code": entry.reason_code,
                    "reason": entry.reason,
                },
                mapped=True,
            )
        )

    # -- findings from the readback checks ------------------------------------
    # A character-level match that differs only in whitespace placement is a real
    # difference a reviewer should see, and it is not a projection regression, so
    # it joins the retained findings rather than the material delta set.
    retained_findings = _collapse_findings(
        (
            *comparison.retained_findings,
            *_whitespace_only_findings(text_readbacks, table_checks),
        )
    )

    # -- page records ---------------------------------------------------------
    # One record per *selected* page, in selection order: the pages that were
    # projected carry the whole of their evidence, and the pages the projection
    # refused carry the reason it refused.  A page that cannot be projected is
    # still a page this run read, so it is reported like every other one instead
    # of failing the run before anything is written.
    pages: list[GatePageRecord] = []
    rebuilt_by_slide: dict[int, list[RebuiltObject]] = {}
    for item in intake.rebuilt_objects:
        rebuilt_by_slide.setdefault(item.rebuilt_slide, []).append(item)
    for slide in projected.slides:
        page_identity = (slide.source_key, slide.source_slide)
        page_objects = [
            item
            for item in projected.objects
            if (item.source_key, item.source_slide) == page_identity
        ]
        slide_ledger = tuple(
            entry for entry in projected.ledger if entry.identity[:2] == page_identity
        )
        counts = {
            "canonical_editable": sum(
                1 for entry in slide_ledger if entry.disposition == DISPOSITION_CANONICAL
            ),
            "locked_visual_proxy": sum(
                1 for entry in slide_ledger if entry.disposition == DISPOSITION_LOCKED
            ),
            "base_only_semantic": sum(
                1 for entry in slide_ledger if entry.disposition == DISPOSITION_BASE_ONLY
            ),
            "unsupported": sum(
                1 for entry in slide_ledger if entry.disposition == "unsupported"
            ),
            "unresolved": sum(
                1 for entry in slide_ledger if entry.disposition == "unresolved"
            ),
        }
        page_source_records = [
            record
            for record in source_records
            if (record.source_key, record.source_page) == page_identity
        ]
        pages.append(
            GatePageRecord(
                source_key=slide.source_key,
                source_path=slide.source_path,
                source_page=slide.source_slide,
                output_page=slide.output_slide,
                rebuilt_slide=slide.output_slide,
                source_objects=len(slide_ledger),
                canonical_editable=counts["canonical_editable"],
                locked_visual_proxy=counts["locked_visual_proxy"],
                base_only_semantic=counts["base_only_semantic"],
                unsupported=counts["unsupported"],
                unresolved=counts["unresolved"],
                native_objects=tuple(
                    item.emitted_name
                    for item in page_objects
                    if item.disposition == DISPOSITION_CANONICAL
                ),
                proxy_objects=tuple(
                    item.emitted_name
                    for item in page_objects
                    if item.disposition in {DISPOSITION_LOCKED, DISPOSITION_BASE_ONLY}
                ),
                ledger=slide_ledger,
                source_issue_count=len(page_source_records),
                rebuilt_issue_count=_page_rebuilt_issue_count(
                    page_identity,
                    output_slide=slide.output_slide,
                    rebuilt_records=rebuilt_by_identity,
                    unbound=comparison.unbound_rebuilt,
                ),
                material_deltas=tuple(
                    item
                    for item in comparison.material_deltas
                    if (item.source_key, item.source_page) == page_identity
                ),
                retained_findings=tuple(
                    item
                    for item in retained_findings
                    if (item.source_key, item.source_page) == page_identity
                ),
                scope_evidence=tuple(
                    item
                    for item in scope_evidence
                    if (item.source_key, item.source_page) == page_identity
                ),
                text_readback=tuple(
                    item
                    for item in text_readbacks
                    if (item.source_key, item.source_page) == page_identity
                ),
                tables=tuple(
                    item
                    for item in table_checks
                    if (item.source_key, item.source_page) == page_identity
                ),
                proxies=tuple(
                    item
                    for item in proxy_proofs
                    if (item.source_key, item.source_page) == page_identity
                ),
            )
        )
    # A blocked page has no place in the rebuilt deck, so it is ordered after the
    # pages that do, by its position in the caller's selection -- the only order a
    # page that was never built can honestly be reported in.
    for blocked in intake.blocked_pages:
        pages.append(
            GatePageRecord(
                source_key=blocked.source_key,
                source_path=blocked.source_path,
                source_page=blocked.source_page,
                output_page=blocked.output_page,
                # The page was not rebuilt, so it has no rebuilt slide either.
                rebuilt_slide=0,
                source_objects=0,
                canonical_editable=0,
                locked_visual_proxy=0,
                base_only_semantic=0,
                unsupported=0,
                unresolved=0,
                native_objects=(),
                proxy_objects=(),
                ledger=(),
                source_issue_count=sum(
                    1
                    for record in source_records
                    if (record.source_key, record.source_page)
                    == (blocked.source_key, blocked.source_page)
                ),
                rebuilt_issue_count=0,
                material_deltas=(),
                retained_findings=(),
                scope_evidence=(),
                text_readback=(),
                tables=(),
                proxies=(),
                failures=(blocked.describe(),),
                blocked=True,
                blocking_reason=blocked.as_dict(),
            )
        )
    pages.sort(
        key=lambda page: (
            page.output_page
            if page.output_page
            else len(pages) + int((page.blocking_reason or {}).get("selection_index", 0))
        )
    )
    for blocked in intake.blocked_pages:
        diagnostics.append(
            GateDiagnostic(
                code="page_projection_blocked",
                message=(
                    f"the selected page {blocked.source_page} (selection position "
                    f"{blocked.selection_index}) cannot be projected and was not "
                    f"rebuilt: {blocked.reason} ({blocked.reason_code})"
                ),
                source_key=blocked.source_key,
                source_page=blocked.source_page,
                source_object=", ".join(blocked.blocking_objects) or None,
            )
        )
    page_responses = [PageResponse(page=page) for page in pages]

    # -- source hashes, re-read after the run ---------------------------------
    verification: list[Mapping[str, Any]] = []
    for record in projected.sources:
        current = _sha256_file(record.source_path)
        matched = current == record.source_sha256
        verification.append(
            {
                "source_key": record.source_key,
                "path": record.source_path,
                "sha256_at_capture": record.source_sha256,
                "sha256_after_run": current,
                "verified": matched,
            }
        )
        if not matched:
            diagnostics.append(
                GateDiagnostic(
                    code="stale_source_hash",
                    message=(
                        f"the source PPTX no longer hashes to the fingerprint the "
                        f"evidence was bound to ({record.source_sha256[:12]}... at "
                        f"capture, {current[:12]}... now)"
                    ),
                    source_key=record.source_key,
                )
            )

    # A rebuilt issue that could not be attributed to a source object is a
    # material delta of its own, so it enters the same set the outcome is
    # derived from rather than living beside it as a diagnostic only.
    material = (*comparison.material_deltas, *unbound_deltas)
    retained = retained_findings
    outcome = classify_gate_outcome(
        diagnostics=diagnostics,
        material_deltas=material,
        retained_findings=retained,
        scope_evidence=scope_evidence,
        checks_complete=checks_complete,
    )
    return GateEvaluation(
        outcome=outcome,
        diagnostics=tuple(diagnostics),
        pages=tuple(pages),
        material_deltas=tuple(material),
        retained_findings=tuple(retained),
        scope_evidence=tuple(scope_evidence),
        checks_complete=checks_complete,
        projected=projected,
        source_verification=tuple(verification),
        source_evidence=intake.source_evidence,
        rebuilt_evidence=intake.rebuilt_evidence,
        page_responses=tuple(page_responses),
        rebuilt_objects=intake.rebuilt_objects,
        unbound_rebuilt=comparison.unbound_rebuilt,
        blocked_pages=intake.blocked_pages,
    )


def _rebuilt_records_by_identity(
    raw_issues: Sequence[Mapping[str, Any]],
    *,
    projected: ProjectionResult,
    rebuilt_by_name: Mapping[str, RebuiltObject],
) -> tuple[tuple[IssueRecord, ...], tuple[UnboundRebuiltIssue, ...]]:
    """Re-key rebuilt issues from output position onto source identity.

    The rebuilt deck's issue path names an object by id, so the object's emitted
    name is read from the rebuilt deck's own readback and then translated through
    the disposition ledger into ``(source_key, source_page, source_object)``.
    That translation is the whole point of the stable mapping: the rebuilt slide
    number is never compared with the source page number.

    The binding **fails closed**.  Every rebuilt issue is either bound to a
    selected source identity or returned as an :class:`UnboundRebuiltIssue` with
    the reason its binding failed; none is ever dropped.  The rebuilt deck holds
    only the selected pages and this run built it, so an issue that cannot be
    attributed to a selected source object is itself a finding: either the
    projection did not select the object the issue is on, or the path OfficeCLI
    reported resolves to no object of the deck at all -- and the second case
    means the mapping this whole comparison rests on is unsound.
    """
    by_path: dict[str, RebuiltObject] = {
        item.path: item for item in rebuilt_by_name.values() if item.path
    }
    by_slide_and_id: dict[tuple[int, int], RebuiltObject] = {}
    for item in rebuilt_by_name.values():
        match = re.search(r"\[@id=(\d+)\]", item.path)
        if match:
            by_slide_and_id[(item.rebuilt_slide, int(match.group(1)))] = item
    identity_by_name = {item.emitted_name: item.identity for item in projected.objects}

    records: list[IssueRecord] = []
    unbound: list[UnboundRebuiltIssue] = []
    for raw in raw_issues:
        message = str(raw.get("message", "") or "")
        subtype = str(raw.get("subtype", "") or "").strip()
        condition = (
            _CONDITION_SLUG_RE.sub("_", subtype.lower()).strip("_")
            or normalize_issue_condition(message)
        )
        path = parse_issue_path(raw.get("path"))
        if path is None or path.full_object_path is None:
            unbound.append(
                UnboundRebuiltIssue(
                    reason_code="rebuilt_path_package_level",
                    condition=condition,
                    message=message,
                    raw_issue=raw,
                )
            )
            continue
        rebuilt = by_path.get(path.full_object_path)
        if rebuilt is None:
            match = re.search(r"\[@id=(\d+)\]", path.object_path or "")
            if match:
                rebuilt = by_slide_and_id.get((path.slide, int(match.group(1))))
        if rebuilt is None:
            unbound.append(
                UnboundRebuiltIssue(
                    reason_code="rebuilt_path_unresolved",
                    condition=condition,
                    message=message,
                    raw_issue=raw,
                )
            )
            continue
        identity = identity_by_name.get(rebuilt.emitted_name)
        if identity is None:
            unbound.append(
                UnboundRebuiltIssue(
                    reason_code="rebuilt_object_not_in_ledger",
                    condition=condition,
                    message=message,
                    raw_issue=raw,
                )
            )
            continue
        records.append(
            IssueRecord(
                source_key=identity[0],
                source_page=identity[1],
                source_object=identity[2],
                scope="object",
                condition=condition,
                message=message,
                severity=str(raw.get("severity", "")),
                issue_id=str(raw.get("id", "")),
                measured=issue_measurements(message),
            )
        )
    return tuple(records), tuple(unbound)


# What each failed binding step means to a reviewer, and where a diagnostic that
# names it points.
_BINDING_REASONS: Mapping[str, str] = {
    "rebuilt_path_unresolved": (
        "the rebuilt deck holds only the pages this run selected and was built by "
        "this run, so a rebuilt issue whose path resolves to none of its objects "
        "means the source-to-rebuilt mapping is unsound"
    ),
    "rebuilt_object_not_in_ledger": (
        "the rebuilt deck really holds the object the issue names, and no source "
        "identity in this run's disposition ledger emits it, so the projection "
        "did not select the object this issue belongs to"
    ),
    "rebuilt_path_package_level": (
        "the issue's path names no slide at all, so no selected page can own it "
        "and the gate has no way to attribute it"
    ),
}


def _page_rebuilt_issue_count(
    page_identity: tuple[str, int],
    *,
    output_slide: int,
    rebuilt_records: Sequence[IssueRecord],
    unbound: Sequence[UnboundRebuiltIssue],
) -> int:
    """Return how many OfficeCLI *issues* one page's rebuilt slide reports.

    An issue is a record, not an object: a page whose rebuilt slide holds 37
    perfectly valid objects and reports nothing has zero issues, and a slide
    that reports one overflow on one of them has one.  Counting the objects
    instead would tell a reviewer the rebuilt deck carries one issue per object,
    which is a different and much larger claim than the deck makes.

    A record is attributed to the page its own source identity names; one that
    could not be bound is attributed to the rebuilt slide its path names, so
    every issue the rebuilt deck reports is counted on exactly one page.  A
    repeated issue id is counted once, because it is one issue.
    """
    issue_ids: set[str] = set()
    for record in rebuilt_records:
        if (record.source_key, record.source_page) == page_identity:
            issue_ids.add(record.issue_id or f"{record.condition}@{record.source_object}")
    for item in unbound:
        path = parse_issue_path(item.path)
        if path is not None and path.slide == output_slide:
            issue_ids.add(item.issue_id or f"{item.condition}@{item.path}")
    return len(issue_ids)


def _unbound_rebuilt_material_delta(item: UnboundRebuiltIssue) -> MaterialDelta:
    """Return the material delta one unattributable rebuilt issue *is*.

    A rebuilt-only condition blocks acceptance.  Whether the gate managed to
    attribute it to a source object changes what the report can say about it,
    never whether it blocks: a binding that succeeds decides *where* a delta is
    recorded, and a binding that fails is its own delta.
    """
    identity = parse_issue_path(item.path)
    reason = _BINDING_REASONS.get(item.reason_code, item.reason_code)
    return MaterialDelta(
        source_key="unbound",
        source_page=identity.slide if identity is not None else 0,
        source_object=item.path or "(no path)",
        condition=item.condition,
        reason=(
            f"the rebuilt deck reports this condition and no source identity "
            f"could be bound to it: {reason}"
        ),
        rebuilt_slide=identity.slide if identity is not None else 0,
        rebuilt_object=item.path or "(no path)",
        rebuilt_issue=dict(item.raw_issue),
        source_issue=None,
    )


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


def _evidence_document(evaluation: GateEvaluation) -> dict[str, Any]:
    """Return the published gate report for one evaluation.

    The report is self-describing: it carries the per-page records themselves,
    not only a summary of them, so a reviewer who opens ``gate-report.json``
    alone has the page evidence, the ledger, the proxy proofs and the text
    readbacks in front of them.  ``pages.json`` remains as the page-only view of
    the same records.
    """
    projected = evaluation.projected
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "outcome": evaluation.outcome.value,
        "accepted": evaluation.outcome is not GateOutcome.BLOCK,
        "checks_complete": evaluation.checks_complete,
        "comparison_rules": [item.as_dict() for item in COMPARISON_RULES],
        "selection": [page.as_dict() for page in projected.selection],
        "sources": [record.as_dict() for record in projected.sources],
        "counts": {
            "selected_pages": len(evaluation.pages),
            "projected_pages": sum(
                1 for page in evaluation.pages if not page.blocked
            ),
            "blocked_pages": sum(1 for page in evaluation.pages if page.blocked),
            "source_objects": len(projected.ledger),
            "canonical_editable": sum(
                1 for item in projected.ledger if item.disposition == DISPOSITION_CANONICAL
            ),
            "locked_visual_proxy": sum(
                1 for item in projected.ledger if item.disposition == DISPOSITION_LOCKED
            ),
            "base_only_semantic": sum(
                1 for item in projected.ledger if item.disposition == DISPOSITION_BASE_ONLY
            ),
            "unsupported": sum(
                1 for item in projected.ledger if item.disposition == "unsupported"
            ),
            "unresolved": sum(
                1 for item in projected.ledger if item.disposition == "unresolved"
            ),
            "native_round_trip": sum(
                1 for item in projected.ledger if item.disposition == DISPOSITION_CANONICAL
            ),
            "excluded_from_native_round_trip": sum(
                1
                for item in projected.ledger
                if item.disposition != DISPOSITION_CANONICAL
            ),
            "proxy_proofs": sum(len(page.proxies) for page in evaluation.pages),
            "proxy_proofs_failed": sum(
                1
                for page in evaluation.pages
                for proof in page.proxies
                if not proof.passed
            ),
            "source_issues": sum(page.source_issue_count for page in evaluation.pages),
            "rebuilt_issues": sum(
                page.rebuilt_issue_count for page in evaluation.pages
            ),
            "unbound_rebuilt_issues": len(evaluation.unbound_rebuilt),
            "material_deltas": len(evaluation.material_deltas),
            "retained_findings": len(evaluation.retained_findings),
            "scope_evidence": len(evaluation.scope_evidence),
            "blocking_diagnostics": len(evaluation.diagnostics),
        },
        "diagnostics": [item.as_dict() for item in evaluation.diagnostics],
        "source_verification": [dict(item) for item in evaluation.source_verification],
        "source_officecli": [item.as_dict() for item in evaluation.source_evidence],
        "rebuilt_officecli": [item.as_dict() for item in evaluation.rebuilt_evidence],
        "page_responses": [item.as_dict() for item in evaluation.page_responses],
        "pages": [item.as_dict() for item in evaluation.pages],
        "rebuilt_objects": [item.as_dict() for item in evaluation.rebuilt_objects],
        "retained_findings": [
            item.as_dict() for item in evaluation.retained_findings
        ],
        "material_deltas": [item.as_dict() for item in evaluation.material_deltas],
        "scope_evidence": [item.as_dict() for item in evaluation.scope_evidence],
        "unbound_rebuilt_issues": [
            item.as_dict() for item in evaluation.unbound_rebuilt
        ],
        "blocked_pages": [item.as_dict() for item in evaluation.blocked_pages],
    }


def _markdown_report(evaluation: GateEvaluation, artifacts: Mapping[str, str]) -> str:
    """Return a reviewer-readable rendering of the same gate report."""
    lines = [
        "# Source-to-rebuilt projection delta gate",
        "",
        f"- Outcome: `{evaluation.outcome.value}`",
        f"- Selected pages: {len(evaluation.pages)}",
        f"- Blocked pages: {sum(1 for page in evaluation.pages if page.blocked)}",
        f"- Material deltas: {len(evaluation.material_deltas)}",
        f"- Retained findings: {len(evaluation.retained_findings)}",
        f"- Scope evidence: {len(evaluation.scope_evidence)}",
        "",
    ]
    if evaluation.outcome is GateOutcome.PASS_WITH_FINDINGS:
        lines.extend(
            [
                "Accepted with findings: the material delta set is empty, and the "
                "findings below are source-inherent conditions or scope evidence.",
                "",
            ]
        )
    if evaluation.diagnostics:
        lines.extend(["## Blocking diagnostics", ""])
        lines.extend(f"- `{item.code}` {item.message}" for item in evaluation.diagnostics)
        lines.append("")
    if evaluation.retained_findings:
        lines.extend(["## Retained findings", ""])
        for item in evaluation.retained_findings:
            lines.append(
                f"- `{item.condition}` on `{item.source_key}` page "
                f"{item.source_page} `{item.source_object}` — {item.reason}"
            )
        lines.append("")
    if evaluation.scope_evidence:
        lines.extend(["## Scope evidence", ""])
        for item in evaluation.scope_evidence:
            lines.append(
                f"- `{item.condition}` on `{item.source_key}` page "
                f"{item.source_page} — {item.detail}"
            )
        lines.append("")
    lines.extend(["## Pages", ""])
    for page in evaluation.pages:
        if page.blocked:
            lines.append(
                f"- `{page.source_key}` page {page.source_page} -> rebuilt slide "
                f"{page.rebuilt_slide}: **BLOCKED** — {page.failures[0]}"
            )
            continue
        lines.append(
            f"- `{page.source_key}` page {page.source_page} -> rebuilt slide "
            f"{page.rebuilt_slide}: {page.canonical_editable} canonical-editable, "
            f"{page.locked_visual_proxy} locked proxy, "
            f"{page.base_only_semantic} base-only, {page.unsupported} unsupported, "
            f"{page.unresolved} unresolved; {page.source_issue_count} source / "
            f"{page.rebuilt_issue_count} rebuilt issue(s)"
        )
    lines.extend(["", "## Artifacts", ""])
    for name, digest in sorted(artifacts.items()):
        lines.append(f"- `{name}`: `{digest}`")
    return "\n".join(lines) + "\n"


def _publish(
    evaluation: GateEvaluation,
    *,
    destination: Path,
    html_text: str,
    rebuilt_path: Path,
    proxy_paths: Sequence[Path],
) -> tuple[tuple[ArtifactHash, ...], Mapping[str, str], str, str]:
    """Stage, hash, and move the whole evidence set into place in one step.

    Nothing is written into ``destination`` before every artifact exists in the
    staging directory beside it, so a blocked or failed run cannot leave a
    directory that looks like a completed gate result.  The projection's own
    artifacts are staged inside the same directory, so the document the gate
    accepted and the images it proved isolated are part of the published
    evidence rather than handles into a temporary directory that disappears when
    the call returns.
    """
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-gate-", dir=str(destination.parent))
    )
    blocked = evaluation.outcome is GateOutcome.BLOCK
    report_name = REJECTION_REPORT_NAME if blocked else GATE_REPORT_NAME
    markdown_name = "gate-rejected.md" if blocked else "gate-report.md"
    published = False
    try:
        projection_directory = staging / PROJECTION_DIRECTORY_NAME
        projection_directory.mkdir()
        shadow = destination / PROJECTION_DIRECTORY_NAME
        projection_artifacts = {
            "canonical_author_html": str(
                (shadow / CANONICAL_HTML_NAME).resolve()
            ),
            "source_map": str((shadow / SOURCE_MAP_NAME).resolve()),
            "projection_report": str((shadow / PROJECTION_REPORT_NAME).resolve()),
        }
        report = _write_evaluation_documents(
            staging, evaluation, report_name=report_name
        )
        report["projection_artifacts"] = dict(projection_artifacts)
        _write_text_exact(staging / CANONICAL_HTML_NAME, html_text)
        _write_text_exact(projection_directory / CANONICAL_HTML_NAME, html_text)
        shutil.copy2(evaluation.projected.source_map_path, staging / SOURCE_MAP_NAME)
        shutil.copy2(
            evaluation.projected.source_map_path,
            projection_directory / SOURCE_MAP_NAME,
        )
        shutil.copy2(
            evaluation.projected.projection_report_path, staging / PROJECTION_REPORT_NAME
        )
        shutil.copy2(
            evaluation.projected.projection_report_path,
            projection_directory / PROJECTION_REPORT_NAME,
        )
        shutil.copy2(rebuilt_path, staging / REBUILT_PPTX_NAME)
        proxy_directory = staging / PROXY_DIRECTORY_NAME
        proxy_directory.mkdir()
        for path in proxy_paths:
            if path.is_file():
                shutil.copy2(path, proxy_directory / path.name)
                shutil.copy2(path, projection_directory / path.name)

        # The report is written once for the inventory and once more once the
        # last artifact exists, because the inventory must not describe a file
        # that has not been written yet.  The report and its markdown twin are
        # excluded from the inventory: a document cannot contain its own hash.
        # Every other published file is listed, and a reviewer re-hashes them
        # with the algorithm this rule names.
        artifacts, _ = _artifact_inventory(
            staging, destination, report_name=report_name
        )
        report["artifacts"] = [item.as_dict() for item in artifacts]
        _json_dump(staging / report_name, report)
        markdown = _markdown_report(
            evaluation, {item.name: item.sha256 for item in artifacts}
        )
        _write_text_exact(staging / markdown_name, markdown)
        # The markdown twin is new, so the inventory is taken again.
        artifacts, _ = _artifact_inventory(
            staging, destination, report_name=report_name
        )
        report["artifacts"] = [item.as_dict() for item in artifacts]
        _json_dump(staging / report_name, report)

        required = (
            staging / report_name,
            staging / LEDGER_NAME,
            staging / SOURCE_MAP_NAME,
            staging / PROJECTION_REPORT_NAME,
            staging / REBUILT_PPTX_NAME,
            staging / CANONICAL_HTML_NAME,
        )
        missing = [str(item) for item in required if not item.is_file()]
        if missing:
            raise ProjectionError(
                "Gate evidence is incomplete and was not published: "
                + ", ".join(missing),
                code="incomplete_evidence",
            )
        if destination.exists():
            raise ProjectionError(
                f"Gate output appeared during the run: {destination}",
                code="output_collision",
            )
        _atomic_replace(staging, destination)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)

    published_artifacts = tuple(
        ArtifactHash(
            name=item.name,
            path=str((destination / item.name).resolve()),
            sha256=_sha256_file(destination / item.name),
            size_bytes=(destination / item.name).stat().st_size,
        )
        for item in artifacts
    )
    # The artifact list is written into the report, so re-verify that the bytes
    # which moved are the bytes the report describes.
    for item in published_artifacts:
        if item.sha256 != _sha256_file(destination / item.name):
            raise ProjectionError(
                f"The published artifact {item.name} does not hash to the value "
                "the report recorded for it.",
                code="hash_mismatch",
            )
    report_sha = _sha256_file(destination / report_name)
    return (
        published_artifacts,
        dict(projection_artifacts),
        str(destination / report_name),
        report_sha,
    )


def _atomic_replace(staging: Path, destination: Path) -> None:
    """Move a complete staging directory onto its destination, retrying briefly.

    The move is still one step -- the destination never exists in a partial
    state -- but on Windows a handle the run's own subprocesses opened on an
    artifact can outlive the process that opened it for a moment, and the move
    then fails with a sharing violation rather than publishing evidence that is
    already complete.  A short retry is what distinguishes "a reader has not let
    go yet" from "this cannot be published", and the final attempt raises the
    real error so a genuine failure still reaches the caller.
    """
    last: OSError | None = None
    for attempt in range(20):
        try:
            staging.replace(destination)
            return
        except OSError as error:
            last = error
            time.sleep(0.25 * (attempt + 1))
    assert last is not None
    raise last


def _json_dump(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _relocate_proxy_assets(
    projected: ProjectionResult, asset_map: Mapping[str, str]
) -> ProjectionResult:
    """Return ``projected`` with every record's proxy asset path re-pointed.

    The projection writes each object-local proxy beside the document it is
    producing, which is the projection's own working directory.  The gate moves
    those assets to a stable per-run directory and re-derives every record that
    names one -- the emitted objects, and the slides that hold them -- so the
    isolation proofs, the published evidence, and the result the caller holds all
    name the same file.
    """
    if not asset_map:
        return projected
    import dataclasses

    def relocate(asset: str | None) -> str | None:
        if not asset:
            return asset
        return asset_map.get(asset, asset)

    return dataclasses.replace(
        projected,
        objects=tuple(
            dataclasses.replace(item, proxy_asset=relocate(item.proxy_asset))
            for item in projected.objects
        ),
        slides=tuple(
            dataclasses.replace(
                slide,
                objects=tuple(
                    dataclasses.replace(item, proxy_asset=relocate(item.proxy_asset))
                    for item in slide.objects
                ),
            )
            for slide in projected.slides
        ),
    )


def _write_evaluation_documents(
    staging: Path, evaluation: GateEvaluation, *, report_name: str
) -> dict[str, Any]:
    """Write every document that is a projection of one evaluation.

    These are the files the gate owns: the page records, the disposition ledger
    the run classified, the three finding sets, and the isolation proofs.  They
    are written from the evaluation the report describes, so the report a
    reviewer reads and the result the caller holds cannot disagree.  The report
    itself is named for the verdict -- ``gate-report.json`` for an accepted run,
    ``gate-rejected.json`` for a blocked one -- which is what keeps partial
    evidence from ever appearing as a completed gate result.
    """
    report = _evidence_document(evaluation)
    report["report_name"] = report_name
    _json_dump(staging / report_name, report)
    _json_dump(staging / "pages.json", {"pages": [item.as_dict() for item in evaluation.pages]})
    _json_dump(
        staging / LEDGER_NAME,
        {
            "schema_version": GATE_SCHEMA_VERSION,
            "selection": [page.as_dict() for page in evaluation.projected.selection],
            "sources": [record.as_dict() for record in evaluation.projected.sources],
            "entries": [item.as_dict() for item in evaluation.projected.ledger],
            "counts": evaluation.projected.disposition_counts(),
        },
    )
    _json_dump(
        staging / "material-deltas.json",
        {"material_deltas": [item.as_dict() for item in evaluation.material_deltas]},
    )
    _json_dump(
        staging / "retained-findings.json",
        {"retained_findings": [item.as_dict() for item in evaluation.retained_findings]},
    )
    _json_dump(
        staging / "scope-evidence.json",
        {"scope_evidence": [item.as_dict() for item in evaluation.scope_evidence]},
    )
    _json_dump(
        staging / "proxy-isolation.json",
        {"proofs": [proof.as_dict() for page in evaluation.pages for proof in page.proxies]},
    )
    return report


def _artifact_inventory(
    staging: Path, destination: Path, *, report_name: str
) -> tuple[tuple[ArtifactHash, ...], str]:
    """Return the hash of every publishable artifact, and the report's own hash.

    The report carries the hash of every artifact *including itself*, which is
    impossible in one document: writing a hash of the report into the report
    changes the report.  So the inventory covers every artifact except the report
    and its markdown twin, and those two are verified by re-hashing the files.
    """
    excluded = {report_name, "gate-report.md", "gate-rejected.md"}
    artifacts = tuple(
        ArtifactHash(
            name=str(item.relative_to(staging)).replace("\\", "/"),
            path=str((destination / item.relative_to(staging)).resolve()),
            sha256=_sha256_file(item),
            size_bytes=item.stat().st_size,
        )
        for item in sorted(staging.rglob("*"))
        if item.is_file() and item.name not in excluded
    )
    return artifacts, _sha256_file(staging / report_name)


# ---------------------------------------------------------------------------
# The one caller-facing entry point
# ---------------------------------------------------------------------------


def gate_projected_author_html(
    source: PageSelection | SelectedPage | Sequence[SelectedPage] | Sequence[Any],
    output_directory: str | Path,
    *,
    proxy_dir: str | Path | None = None,
    intake_mutation: Callable[[GateIntake], GateIntake] | None = None,
    _sources: GateSources | None = None,
) -> ProjectionGateResult:
    """Gate one selected-page projection against its own rebuilt deck.

    The selection has exactly the meaning :func:`project_pptx_to_author_html`
    gives it: an explicit ordered list of ``(source_pptx, source_page)`` pairs
    from one or more decks, emitted in that order.  ``output_directory`` is where
    the evidence set is published; it must not already exist, so a previous
    accepted run is never silently overwritten.

    The gate projects, rebuilds the projection through the existing New Deck
    path, reads the rebuilt PPTX back through OfficeCLI, compares it with the
    source by stable source identity, and returns a :class:`ProjectionGateResult`
    whose ``outcome`` is one of ``PASS``, ``PASS_WITH_FINDINGS``, or ``BLOCK``.
    The complete evidence set is published for an accepting and a blocking
    verdict alike -- a blocked run's diagnostics, page records, ledger, and proxy
    proofs are what a reviewer repairs from -- and the verdict is carried by
    which report document exists: ``gate-report.json`` for an accepted run,
    ``gate-rejected.json`` for a blocked one.  No ``gate-report.json`` is ever
    written by a run that did not reach an accepting outcome.

    ``intake_mutation`` is a test seam.  It receives the sealed
    :class:`GateIntake` bundle after every real read, once the projection's proxy
    assets have been moved to their per-run directory, and may return a mutated
    copy or mutate an asset in place; the mutations are then judged by the same
    production comparison rules a real run uses.  It exists so a negative test
    can exercise a condition OfficeCLI cannot be made to produce at will (a
    rebuilt-only issue, a native table read back with the wrong dimensions, a
    proxy whose bytes were swapped) without first having to build a deck that
    produces it.  Production callers never pass it.
    """
    destination = Path(output_directory).expanduser().resolve()
    if destination.exists():
        raise ProjectionError(
            "Gate output already exists: " + str(destination),
            code="output_collision",
        )
    if not destination.parent.is_dir():
        raise ProjectionError(
            f"Gate output directory does not exist: {destination.parent}",
            code="invalid_output",
        )
    if not isinstance(source, PageSelection):
        try:
            pages = tuple(_coerce_selection(source))
        except ProjectionError:
            raise
    else:
        pages = source.pages
    if not pages:
        raise ProjectionError(
            "The gate needs at least one selected source page.",
            code="invalid_selection",
        )

    sources = _sources or _default_sources()
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-gate-run-", dir=str(destination.parent))
    )
    rebuilt_path = staging / REBUILT_PPTX_NAME
    html_path = staging / "projection-author.html"
    proxy_directory = (
        Path(proxy_dir).expanduser().resolve()
        if proxy_dir is not None
        else staging / "projection-proxies"
    )
    mutated = False

    def apply_mutation(bundle: GateIntake) -> GateIntake:
        """Apply the test seam, exactly once, after the assets are stable."""
        nonlocal mutated
        if intake_mutation is None or mutated:
            return bundle
        mutated = True
        return intake_mutation(bundle)

    try:
        blocked_pages: tuple[BlockedPage, ...] = ()
        try:
            projected = sources.project(pages, html_path, proxy_directory)
        except ProjectionBlockedError:
            # The projection refuses a selection as a whole, so one page that
            # cannot be projected would otherwise cost every other selected page
            # its evidence.  Each page is classified on its own, the pages that
            # project are projected together, and the pages that cannot are
            # carried as blocked page records inside a verdict this run still
            # publishes.  A run with no projectable page has nothing to rebuild
            # and no comparison to make, so it keeps the projection's own
            # refusal.
            retained, blocked_pages = _classify_blocked_pages(
                pages,
                sources=sources,
                probe_directory=staging / "page-probes",
            )
            if not retained:
                raise
            projected = sources.project(retained, html_path, proxy_directory)
        reply = _select_build_reply(sources.rebuild(str(html_path), str(rebuilt_path)))
        failure = _build_failed(reply)
        if failure is not None:
            raise ProjectionError(failure, code="new_deck_build_failed")
        if not rebuilt_path.is_file():
            raise ProjectionError(
                "The New Deck build did not produce a PPTX at "
                f"{rebuilt_path}.",
                code="new_deck_build_failed",
            )
        rebuilt_sha = _sha256_file(rebuilt_path)

        source_evidence: list[OfficeCliEvidence] = []
        for record in projected.sources:
            raw_source_issues = tuple(sources.issues(record.source_path))
            source_evidence.append(
                OfficeCliEvidence(
                    label=record.source_key,
                    path=record.source_path,
                    role="source",
                    sha256=record.source_sha256,
                    validation=sources.validate(record.source_path),
                    issues_text=issue_lines(raw_source_issues),
                    issue_count=len(raw_source_issues),
                    raw_issue_records=raw_source_issues,
                )
            )
        rebuilt_issues = sources.issues(rebuilt_path)
        rebuilt_evidence = (
            OfficeCliEvidence(
                label="rebuilt",
                path=str(rebuilt_path),
                role="rebuilt",
                sha256=rebuilt_sha,
                validation=sources.validate(rebuilt_path),
                issues_text=issue_lines(rebuilt_issues),
                issue_count=len(rebuilt_issues),
                raw_issue_records=tuple(rebuilt_issues),
            ),
        )
        shallow, deep = sources.tree(rebuilt_path)
        # The projection's proxy assets are moved to a stable per-run directory
        # before anything is compared, and every record that names them is
        # re-derived from the moved copies.  Otherwise the gate would be reading
        # a path that its own publication step is about to delete, and a proxy's
        # isolation proof would describe an image nobody can open afterwards.
        proxy_staging = staging / PROJECTION_DIRECTORY_NAME
        proxy_staging.mkdir()
        asset_map: dict[str, str] = {}
        for item in projected.objects:
            if not item.proxy_asset:
                continue
            source_path = Path(item.proxy_asset)
            if not source_path.is_file():
                continue
            target_path = proxy_staging / source_path.name
            if source_path.resolve() != target_path.resolve():
                shutil.copy2(source_path, target_path)
            asset_map[str(source_path)] = str(target_path)
        projected = _relocate_proxy_assets(projected, asset_map)
        intake = GateIntake(
            projected=projected,
            rebuilt_path=str(rebuilt_path),
            rebuilt_sha256=rebuilt_sha,
            source_evidence=tuple(source_evidence),
            rebuilt_evidence=rebuilt_evidence,
            rebuilt_objects=_rebuilt_objects(shallow, deep),
            rebuilt_issue_records=tuple(rebuilt_issues),
            blocked_pages=blocked_pages,
        )
        if intake_mutation is not None:
            intake = apply_mutation(intake)
        html_text = html_path.read_text(encoding="utf-8")
        # The proof records name the copy that survives the run: publication
        # copies every object-local proxy into the evidence directory, so the
        # path the proof reports has to be the published one.
        published_proxies = {
            str(Path(item.proxy_asset)): str(
                (destination / PROJECTION_DIRECTORY_NAME / Path(item.proxy_asset).name).resolve()
            )
            for item in projected.objects
            if item.proxy_asset
        }
        evaluation = evaluate_intake(
            intake,
            html_text=html_text,
            pixels_per_point=projected.pixels_per_point,
            published_proxies=published_proxies,
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    proxy_paths = [Path(item.proxy_asset) for item in projected.objects if item.proxy_asset]
    try:
        (
            artifacts,
            projection_artifacts,
            report_path,
            _,
        ) = _publish(
            evaluation,
            destination=destination,
            html_text=html_text,
            rebuilt_path=rebuilt_path,
            proxy_paths=proxy_paths,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return ProjectionGateResult(
        outcome=evaluation.outcome,
        published=True,
        output_directory=str(destination),
        report_path=report_path,
        diagnostics=evaluation.diagnostics,
        pages=evaluation.pages,
        material_deltas=evaluation.material_deltas,
        retained_findings=evaluation.retained_findings,
        scope_evidence=evaluation.scope_evidence,
        artifacts=artifacts,
        source_verification=evaluation.source_verification,
        source_evidence=evaluation.source_evidence,
        rebuilt_evidence=evaluation.rebuilt_evidence,
        ledger=projected.ledger,
        projected=projected,
        page_responses=evaluation.page_responses,
        rebuilt_objects=evaluation.rebuilt_objects,
        unbound_rebuilt=evaluation.unbound_rebuilt,
        projection_artifacts=projection_artifacts,
    )


def _blocked_page_reason(projected: ProjectionResult | None, error: Any) -> tuple[str, str, tuple[str, ...]]:
    """Return ``(reason_code, reason, blocking objects)`` for a blocked page.

    The projection reports why it refused through its own blocking diagnostics,
    so the gate does not have to interpret the failure: it reads the codes and
    objects the projection already classified.  A failure with no diagnostic at
    all still names its own class, so a blocked page is never reported with an
    empty reason.
    """
    diagnostics = tuple(getattr(error, "diagnostics", ()) or ())
    blocking = tuple(item for item in diagnostics if getattr(item, "blocking", False))
    if blocking:
        first = blocking[0]
        reason_code = str(getattr(first, "code", "") or "projection_blocked")
        objects = tuple(
            sorted(
                {
                    str(getattr(item, "source_object", "") or "")
                    for item in blocking
                    if getattr(item, "source_object", None)
                }
            )
        )
        return reason_code, str(getattr(first, "message", "") or ""), objects
    return (
        "projection_blocked",
        str(error).strip() or "the projection refused this page",
        (),
    )


def _classify_blocked_pages(
    pages: Sequence[SelectedPage],
    *,
    sources: GateSources,
    probe_directory: Path,
    source_keys: Mapping[str, str] | None = None,
) -> tuple[tuple[SelectedPage, ...], tuple[BlockedPage, ...]]:
    """Split a selection into the pages that project and the pages that block.

    The projection seam refuses a whole selection when any one selected page
    carries something the Author Contract cannot express, which would destroy
    the evidence for every other page in the run.  Each page is therefore
    projected on its own to find out which it is, and only the pages that
    project are re-projected together.

    The probe is the same projection seam over the same source page with its own
    destination, so a page is classified by the production classifier rather
    than by a second reading of the source.

    Returns the retained pages *in selection order* and one
    :class:`BlockedPage` for each page that could not be projected.
    """
    probe_directory.mkdir(parents=True, exist_ok=True)
    keys = source_keys or {}
    retained: list[SelectedPage] = []
    blocked: list[BlockedPage] = []
    for index, page in enumerate(pages):
        destination = probe_directory / f"page-{index + 1:03d}.html"
        try:
            sources.project((page,), destination, probe_directory / f"page-{index + 1:03d}")
        except ProjectionBlockedError as error:
            reason_code, reason, objects = _blocked_page_reason(None, error)
            blocked.append(
                BlockedPage(
                    source_key=keys.get(str(Path(page.source_pptx).resolve()), "src1"),
                    source_path=page.source_pptx,
                    source_page=page.source_slide,
                    selection_index=index + 1,
                    # Zero is not an output page: this page has no place in the
                    # rebuilt deck, and reporting the slot it would have taken
                    # would collide with the page that really occupies it.
                    output_page=0,
                    reason_code=reason_code,
                    reason=reason,
                    detail=(
                        "the projection refused this page on its own, so the page "
                        "is carried as a blocked page record inside a published "
                        "BLOCK verdict rather than aborting the whole run and "
                        "destroying the other selected pages' evidence; the page "
                        "was not rebuilt, so it has no output page"
                    ),
                    blocking_objects=objects,
                )
            )
            continue
        retained.append(page)
    return tuple(retained), tuple(blocked)


def _coerce_selection(source: Any) -> Iterable[SelectedPage]:
    """Coerce a caller's selection into ``SelectedPage`` entries.

    The gate accepts exactly the selection spellings the projection seam
    accepts, so a caller never has to learn a second selection vocabulary.
    """
    from .author_projector import _coerce_pages

    return _coerce_pages(source)


__all__ = [
    "ArtifactHash",
    "BlockedPage",
    "COMPARISON_RULES",
    "GateDiagnostic",
    "GateEvaluation",
    "GateIntake",
    "GateOutcome",
    "GatePageRecord",
    "GateSources",
    "GUARD_BAND_CONTAMINATION_FRACTION",
    "IssueComparison",
    "IssueMeasurement",
    "IssueRecord",
    "MaterialDelta",
    "NormalizationRule",
    "OVERFLOW_RATIO_ABSOLUTE_TOLERANCE",
    "OVERFLOW_RATIO_RELATIVE_TOLERANCE",
    "OfficeCliEvidence",
    "PageResponse",
    "ProjectionGateResult",
    "ProxyIsolationProof",
    "RebuiltObject",
    "RetainedFinding",
    "ScopeEvidence",
    "TableCheck",
    "TextReadback",
    "classify_gate_outcome",
    "collect_deck_tree",
    "collect_issue_records",
    "compact_text",
    "compare_issues",
    "evaluate_intake",
    "gate_projected_author_html",
    "issue_lines",
    "issue_measurements",
    "issue_records",
    "materially_worsened",
    "normalize_issue_condition",
    "normalize_text",
    "parse_issue_path",
    "pressure_ratio",
]
