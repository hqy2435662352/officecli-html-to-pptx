"""V03-01 Canonical Run identity: one declaration, mechanically guarded.

``contract.CANONICAL_RUN_IDENTITY`` is the one place the identity dimensions of
a Canonical Run are declared.  ``capabilities`` publishes the mixed-run
attributes derived from it, the lowering pass builds its merge key from it, and
the soft-wrap decision asks it whether a paragraph is one run, so the published
surface, the implementation and every consumer cannot drift apart.

The guard below reads the *implementation*, not the declaration: it compares the
key of two runs that differ in exactly one declared dimension, and the key of
two runs that agree on every declared dimension but differ in every other run
attribute.  Nothing here is derived from the compiler's own output.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import pytest

import officecli_html_to_pptx._internal.officecli_compiler as officecli_compiler
from officecli_html_to_pptx._internal.officecli_compiler import (
    _canonical_run_key,
    _canonical_runs,
    _text_paragraphs,
)
from officecli_html_to_pptx.contract import (
    CANONICAL_RUN_IDENTITY,
    CANONICAL_RUN_IDENTITY_FIELDS,
    MIXED_RUN_ATTRIBUTES,
    SUPPORTED_CSS_PROPERTIES,
)
from officecli_html_to_pptx.measurement import EXTRACTION_JS

# One sample value per declared identity dimension, and one different value per
# dimension.  A new declared dimension has no sample here, which fails
# ``test_every_declared_identity_dimension_has_a_sample_and_a_variant`` until it
# is given one.
IDENTITY_SAMPLES: dict[str, Any] = {
    "font_family": "Georgia",
    "font_size_pt": 15.0,
    "bold": True,
    "italic": True,
    "underline": "single",
    "color": "#0F6B78",
}
IDENTITY_VARIANTS: dict[str, Any] = {
    "font_family": "Segoe UI",
    "font_size_pt": 17.0,
    "bold": False,
    "italic": False,
    "underline": "none",
    "color": "#9A3412",
}
# Run attributes that are not part of the declared identity.  ``text`` is the
# one the lowering emits besides the declared dimensions; the rest are the
# measurement-side names a second, hand-written key used to read.
NON_IDENTITY_RUN_ATTRIBUTES: dict[str, Any] = {
    "text": "changed",
    "textTransform": "uppercase",
    "letterSpacing": 3.5,
    "fontWeight": "800",
    "fontFamily": "Tahoma",
    "source_object": "slide[1]/span[9]",
}

# One resolved measurement run, in the shape ``measurement.py`` emits.
_MEASURED_RUN: dict[str, Any] = {
    "text": "North",
    "color": "#24324a",
    "fontSize": 30.0,
    "fontFamily": "Georgia",
    "fontWeight": "700",
    "fontStyle": "normal",
    "textTransform": "none",
    "textDecoration": "none",
    "href": None,
    "isGradientText": False,
    "backgroundImage": None,
}

_SCALE_X = 0.5
_SCALE_Y = 0.5
_BACKDROP = (248, 250, 252)


def _element(runs: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    """One measured element carrying ``runs`` as its authored paragraph."""
    element: dict[str, Any] = {
        "tag": "div",
        "x": 170.0,
        "y": 250.0,
        "width": 700.0,
        "height": 90.0,
        "text": "North",
        "color": "#24324a",
        "fontSize": 30.0,
        "fontFamily": "Segoe UI",
        "fontWeight": "400",
        "fontStyle": "normal",
        "textAlign": "left",
        "lineHeight": "1.45",
        "direction": "ltr",
        "opacity": 1.0,
        "paragraphs": [
            {
                "text": "".join(str(run["text"]) for run in runs),
                "align": "left",
                "lineHeight": "1.45",
                "spaceBefore": 0.0,
                "spaceAfter": 0.0,
                "direction": "ltr",
                "runs": runs,
            }
        ],
    }
    element.update(overrides)
    return element


def _emitted_run_fields() -> tuple[str, ...]:
    """Return the attribute set of the run dicts the lowering really emits."""
    element = _element([dict(_MEASURED_RUN), {**_MEASURED_RUN, "text": " Africa"}])
    paragraphs = _text_paragraphs(element, _SCALE_X, _SCALE_Y, _BACKDROP)
    assert [paragraph["text"] for paragraph in paragraphs] == ["North Africa"]
    return tuple(paragraphs[0]["runs"][0])


# ---------------------------------------------------------------------------
# The drift guard
# ---------------------------------------------------------------------------


def canonical_run_identity_drift(
    fields: Sequence[str],
    key: Callable[[Mapping[str, Any]], tuple],
    *,
    emitted_run_fields: Sequence[str],
) -> tuple[str, ...]:
    """Report every way an implemented run key disagrees with ``fields``.

    ``emitted_run_fields`` is the complete attribute set of the run dicts the
    lowering emits (the declared dimensions plus anything else it carries), so
    "the key reads an attribute the declaration does not name" is checked
    against what the lowering really produces, not against a literal list.
    """
    drift: list[str] = []
    reference: dict[str, Any] = dict(IDENTITY_SAMPLES)
    for field in fields:
        if field not in IDENTITY_SAMPLES:
            drift.append(f"{field}: declared, but the guard has no sample value")
            continue
        changed = {**reference, field: IDENTITY_VARIANTS[field]}
        if key(reference) == key(changed):
            drift.append(
                f"{field}: declared as an identity dimension, but the key ignores it"
            )
    candidates = {
        name: NON_IDENTITY_RUN_ATTRIBUTES.get(name, f"not-{name}")
        for name in (*emitted_run_fields, *NON_IDENTITY_RUN_ATTRIBUTES)
        if name not in fields
    }
    undeclared = [
        name
        for name, value in candidates.items()
        if key(reference) != key({**reference, name: value})
    ]
    if undeclared:
        drift.append(
            "the key reads attributes the declaration does not name: "
            + ", ".join(sorted(undeclared))
        )
    return tuple(drift)


def test_the_lowering_key_is_exactly_the_declared_canonical_run_identity() -> None:
    assert canonical_run_identity_drift(
        CANONICAL_RUN_IDENTITY_FIELDS,
        _canonical_run_key,
        emitted_run_fields=_emitted_run_fields(),
    ) == ()


def test_every_declared_identity_dimension_has_a_sample_and_a_variant() -> None:
    declared = set(CANONICAL_RUN_IDENTITY_FIELDS)
    assert set(IDENTITY_SAMPLES) == declared
    assert set(IDENTITY_VARIANTS) == declared
    for field in CANONICAL_RUN_IDENTITY_FIELDS:
        assert IDENTITY_SAMPLES[field] != IDENTITY_VARIANTS[field], field


def test_the_drift_guard_reports_a_declared_dimension_the_key_ignores() -> None:
    """The guard can fail: a declaration the implementation only partly reads."""

    def partial_key(run: Mapping[str, Any]) -> tuple:
        return tuple(
            run.get(field) for field in CANONICAL_RUN_IDENTITY_FIELDS[:3]
        )

    drift = canonical_run_identity_drift(
        CANONICAL_RUN_IDENTITY_FIELDS,
        partial_key,
        emitted_run_fields=_emitted_run_fields(),
    )

    assert drift
    assert drift[0].startswith("italic: declared as an identity dimension")
    assert {"italic", "color", "underline"} == {
        item.split(":")[0] for item in drift
    }


def test_the_drift_guard_reports_an_implemented_dimension_the_declaration_omits() -> None:
    """The guard can fail: an identity dimension the implementation reads alone."""
    drift = canonical_run_identity_drift(
        tuple(
            field
            for field in CANONICAL_RUN_IDENTITY_FIELDS
            if field != "color"
        ),
        _canonical_run_key,
        emitted_run_fields=_emitted_run_fields(),
    )

    assert drift == (
        "the key reads attributes the declaration does not name: color",
    )


def test_the_drift_guard_reports_a_key_that_reads_the_run_text() -> None:
    """The guard can fail: an over-eager key that splits on the run's own text."""

    def text_sensitive_key(run: Mapping[str, Any]) -> tuple:
        return (*_canonical_run_key(run), str(run.get("text")))

    drift = canonical_run_identity_drift(
        CANONICAL_RUN_IDENTITY_FIELDS,
        text_sensitive_key,
        emitted_run_fields=_emitted_run_fields(),
    )

    assert drift == (
        "the key reads attributes the declaration does not name: text",
    )


def test_the_lowering_key_is_computed_from_the_declaration_it_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key is driven by the declaration object, not by a second literal."""
    monkeypatch.setattr(
        officecli_compiler, "CANONICAL_RUN_IDENTITY_FIELDS", ("color",)
    )
    merged = _canonical_runs(
        [
            {**IDENTITY_SAMPLES, "text": "North"},
            {
                **IDENTITY_SAMPLES,
                "font_family": "Tahoma",
                "font_size_pt": 27.5,
                "underline": "none",
                "text": " Africa",
            },
        ]
    )

    # Only ``color`` is declared now, and the two runs agree on it, so they are
    # one Canonical Run.  A key that restated the dimensions itself would keep
    # them apart.
    assert [run["text"] for run in merged] == ["North Africa"]


def test_the_published_mixed_run_attributes_are_the_declared_identity_rows() -> None:
    published: dict[str, str] = {}
    for field, attribute, css_property in CANONICAL_RUN_IDENTITY:
        assert field
        # Contract 1.1 keeps the run matrix closed: every identity dimension
        # has a published measurement attribute and a lowered CSS property.
        assert attribute is not None and css_property is not None, field
        if attribute is not None:
            assert attribute not in published, attribute
            published[attribute] = css_property

    assert MIXED_RUN_ATTRIBUTES == published
    # Every published attribute names a CSS property the contract classifies.
    assert set(published.values()) <= set(SUPPORTED_CSS_PROPERTIES)
    assert "href" not in CANONICAL_RUN_IDENTITY_FIELDS


# ---------------------------------------------------------------------------
# The identity the one declaration describes
# ---------------------------------------------------------------------------


# The measured flow the converged extraction produces for the ordinary
# ``Chromium decides <span>this bilingual </span>soft wrap`` shape: three
# adjacent nodes with identical resolved formatting, so one Canonical Run.
_SOFT_WRAP_RUNS: tuple[str, ...] = (
    "Chromium decides ",
    "this bilingual ",
    "soft wrap：浏览器决定",
)
_SOFT_WRAP_VISUAL_LINES: tuple[str, ...] = (
    "Chromium decides",
    "this bilingual",
    "soft wrap：浏览器决定",
)


def test_soft_wrap_measurement_never_changes_authored_paragraph_structure() -> None:
    """Browser visual rows remain evidence; authored text stays one paragraph."""
    element = _element(
        [{**_MEASURED_RUN, "text": text} for text in _SOFT_WRAP_RUNS],
        visualLines=list(_SOFT_WRAP_VISUAL_LINES),
    )

    paragraphs = _text_paragraphs(element, _SCALE_X, _SCALE_Y, _BACKDROP)

    assert [paragraph["text"] for paragraph in paragraphs] == [
        "".join(_SOFT_WRAP_RUNS)
    ]
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [1]


def test_soft_wrap_with_mixed_formatting_keeps_the_authored_paragraph() -> None:
    """A differently formatted neighbour still cannot create soft paragraphs."""
    runs = [{**_MEASURED_RUN, "text": text} for text in _SOFT_WRAP_RUNS]
    runs[-1] = {**runs[-1], "fontFamily": "Tahoma", "color": "#9a3412"}
    element = _element(runs, visualLines=list(_SOFT_WRAP_VISUAL_LINES))

    paragraphs = _text_paragraphs(element, _SCALE_X, _SCALE_Y, _BACKDROP)

    assert [paragraph["text"] for paragraph in paragraphs] == [
        "".join(_SOFT_WRAP_RUNS)
    ]
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [2]


def test_adjacent_runs_identical_on_every_declared_dimension_are_one_canonical_run() -> None:
    merged = _canonical_runs(
        [
            {**IDENTITY_SAMPLES, "text": "North"},
            {**IDENTITY_SAMPLES, "text": " Africa"},
        ]
    )

    assert len(merged) == 1
    # The authored boundary space is neither trimmed nor re-attributed.
    assert merged[0]["text"] == "North Africa"
    assert {
        key: value for key, value in merged[0].items() if key != "text"
    } == IDENTITY_SAMPLES


def test_a_difference_in_any_declared_dimension_keeps_a_native_run_boundary() -> None:
    for field in CANONICAL_RUN_IDENTITY_FIELDS:
        merged = _canonical_runs(
            [
                {**IDENTITY_SAMPLES, "text": "North"},
                {
                    **IDENTITY_SAMPLES,
                    field: IDENTITY_VARIANTS[field],
                    "text": " Africa",
                },
            ]
        )
        assert [run["text"] for run in merged] == ["North", " Africa"], field


def test_canonical_merging_never_crosses_a_hard_break_boundary() -> None:
    """Two identically formatted runs around a ``<br>`` stay native ranges."""
    element = _element([])
    element.pop("paragraphs")
    element["inlineRuns"] = [
        dict(_MEASURED_RUN),
        {**_MEASURED_RUN, "text": "\n", "br": True},
        {**_MEASURED_RUN, "text": " Africa"},
    ]

    paragraphs = _text_paragraphs(element, _SCALE_X, _SCALE_Y, _BACKDROP)

    assert [paragraph["text"] for paragraph in paragraphs] == ["North\v Africa"]
    assert [paragraph["hard_break_offsets"] for paragraph in paragraphs] == [[5]]
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [2]
    assert [
        run["text"]
        for paragraph in paragraphs
        for run in paragraph["runs"]
        if "\n" in run["text"]
    ] == []


def test_canonical_merging_never_crosses_a_paragraph_boundary() -> None:
    """Identical formatting in the next paragraph is never merged backwards."""
    first = _element([dict(_MEASURED_RUN)])
    first["paragraphs"].append(
        {
            "text": " Africa",
            "align": "left",
            "lineHeight": "1.45",
            "spaceBefore": 0.0,
            "spaceAfter": 0.0,
            "direction": "ltr",
            "runs": [{**_MEASURED_RUN, "text": " Africa"}],
        }
    )

    paragraphs = _text_paragraphs(first, _SCALE_X, _SCALE_Y, _BACKDROP)

    assert [paragraph["text"] for paragraph in paragraphs] == ["North", " Africa"]
    assert [len(paragraph["runs"]) for paragraph in paragraphs] == [1, 1]


# ---------------------------------------------------------------------------
# The measurement pass owns no second identity
# ---------------------------------------------------------------------------


def test_the_measurement_pass_collapses_whitespace_without_a_run_identity() -> None:
    """Whitespace collapse stays; a second Canonical Run identity must not."""
    assert "collapseSegment" in EXTRACTION_JS
    assert "inlineRunFormat" not in EXTRACTION_JS
    assert "_format" not in EXTRACTION_JS
    assert "\\u0000" not in EXTRACTION_JS
