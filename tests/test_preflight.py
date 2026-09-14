"""Build-path preflight: the font supply and the external renderer.

The font measurements asserted here are made against the real pinned Chromium,
because the whole point of the check is that it agrees with the renderer it
guards.  A mock would only prove the mock agrees with itself.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from officecli_html_to_pptx import preflight
from officecli_html_to_pptx.preflight import (
    FontReport,
    FontStackResolution,
    PreflightReport,
    declared_family,
    font_preflight,
    named_families,
    preflight as run_preflight,
    probed_families,
    renderer_preflight,
)

DECK = """<!doctype html><html><head><style>
.slide {{ width: 1920px; height: 1080px; display: none;
  flex-direction: column; justify-content: center; }}
.slide.active {{ display: flex; }}
</style></head><body>
<section class="slide active" style="background-color: #ffffff;">
  <h1 style="font-size: 64px; color: #0f172a; font-family: {heading};">Heading</h1>
  <p style="font-size: 24px; color: #475569; font-family: {body};">Body copy.</p>
</section>
</body></html>"""


def _deck(tmp_path: Path, heading: str, body: str) -> Path:
    path = tmp_path / "author.html"
    path.write_text(DECK.format(heading=heading, body=body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Stack parsing: what the PPTX declares versus what the host is asked for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stack", "named", "probed"),
    [
        (
            '"Segoe UI", "Microsoft YaHei", Arial, sans-serif',
            ("Segoe UI", "Microsoft YaHei", "Arial", "sans-serif"),
            ("Segoe UI", "Microsoft YaHei", "Arial"),
        ),
        ("Georgia, serif", ("Georgia", "serif"), ("Georgia",)),
        ("'Segoe Script', cursive", ("Segoe Script", "cursive"), ("Segoe Script",)),
        ("sans-serif", ("sans-serif",), ()),
        ("Arial Black, sans-serif", ("Arial Black", "sans-serif"), ("Arial Black",)),
        ("Segoe UI", ("Segoe UI",), ("Segoe UI",)),
    ],
)
def test_stack_parsing_separates_declared_families_from_generic_keywords(
    stack: str, named: tuple[str, ...], probed: tuple[str, ...]
) -> None:
    """Generics are not typefaces a host can lack, and multi-word names survive.

    Truncating an unquoted ``Arial Black`` to ``Arial`` would check the wrong
    typeface, and treating ``sans-serif`` as a family would report every correct
    deck that ends its stack the normal way.
    """
    assert named_families(stack) == named
    assert probed_families(stack) == probed


def test_declared_family_defers_to_the_compiler_resolver() -> None:
    """What the PPTX declares cannot drift from what build actually writes."""
    from officecli_html_to_pptx.styles import resolve_pptx_font

    for stack in (
        '"Segoe UI", "Microsoft YaHei", Arial, sans-serif',
        "Inter, sans-serif",
        "NotARealFont, Arial",
        "sans-serif",
        "",
    ):
        assert declared_family(stack) == resolve_pptx_font(stack)


# ---------------------------------------------------------------------------
# Font availability, measured in the real Chromium
# ---------------------------------------------------------------------------


def test_real_chromium_agrees_that_present_families_are_present() -> None:
    """The two mechanisms must agree, or the check is worse than none.

    ``FontFace(local())`` answers which families the host supplies, while
    ``CSS.getPlatformFontsForNode`` answers which face Chromium drew with.  The
    assertion is their agreement on the same page in the same browser.
    """
    stacks = [
        {
            "stack": family,
            "weight": "400",
            "families": [family],
            "source_slide": 1,
            "source_object": None,
        }
        for family in (
            "Arial",
            "Calibri",
            "Segoe UI",
            "Consolas",
            "Times New Roman",
            "Georgia",
            "Cambria",
            "Microsoft YaHei",
            "Arial Black",
        )
    ]
    resolved = asyncio.run(preflight._resolve_stacks_in_chromium(stacks))

    for item in resolved:
        family = item["stack"]
        assert item["missing"] == [], f"{family} should be supplied by this host"
        assert item["resolved_family"] is not None, family
        assert item["resolved_face"] is not None, family
        # Availability and the rendered face must name the same family.  A
        # platform may spell the weight into the family (``Segoe UI Black``) or
        # into the PostScript style suffix (``Arial-Black``), and both spellings
        # are the declared family rather than a substitution.
        assert preflight._same_family(item["resolved_family"], family), (
            family,
            item["resolved_family"],
        )


def test_real_chromium_reports_an_absent_family_as_absent() -> None:
    stacks = [
        {
            "stack": "ThisFontDoesNotExistZZZ, sans-serif",
            "weight": "400",
            "families": ["ThisFontDoesNotExistZZZ"],
            "source_slide": 1,
            "source_object": None,
        }
    ]
    resolved = asyncio.run(preflight._resolve_stacks_in_chromium(stacks))

    assert resolved[0]["available"] == []
    assert resolved[0]["missing"] == ["ThisFontDoesNotExistZZZ"]
    # A font-matching request that no available family satisfies cannot be
    # reported as "resolved as <default>"; leaving it null is what keeps the
    # classifier from inventing a family relationship that does not exist.
    assert resolved[0]["resolved_family"] is None


def test_a_host_supplied_deck_is_compatible_and_reports_no_violation(
    tmp_path: Path,
) -> None:
    """The regression gate: this must not fire on an already-correct deck.

    ``resolve_pptx_font`` declares ``Georgia`` here, this host supplies it, so
    the measured geometry and the declaration agree and nothing may be reported.
    """
    report = font_preflight(_deck(tmp_path, "Georgia, serif", "Georgia, serif"))

    assert report.probed is True
    assert report.probe_error is None
    assert {item.stack for item in report.stacks} == {"Georgia, serif"}
    assert report.compatible is True
    assert report.diagnostics() == ()


def test_an_absent_family_is_blocked_and_names_the_consequence(
    tmp_path: Path,
) -> None:
    """Issue #11's core case: an absent family is a silent mis-measurement."""
    report = font_preflight(_deck(tmp_path, "Inter, sans-serif", "Inter, sans-serif"))

    assert report.compatible is False
    blocking = [item for item in report.diagnostics() if item.blocking]
    assert [item.code for item in blocking] == ["declared_font_family_absent"] * 2
    message = blocking[0].message
    assert "'Inter'" in message
    assert "'Segoe UI'" in message  # the family the PPTX would declare
    assert "measure" in message
    assert "system default" in message
    assert blocking[0].remediation
    assert blocking[0].recheck
    assert blocking[0].source_slide == 1


def test_a_family_whose_weight_lands_on_a_lighter_face_is_reported_not_blocked() -> None:
    """A weight substitution is visible but must not be able to block a deck.

    The family is present, so nothing was mis-measured in a *different* family;
    but the host had only a light face, so a bold request is drawn with lighter
    metrics than the weight asked for.
    """
    item = FontStackResolution(
        stack="Some Light Font, sans-serif",
        weight="700",
        families=("Some Light Font",),
        available=("Some Light Font",),
        missing=(),
        resolved_family="Some Light Font",
        resolved_face="SomeLightFont-Light",
    )
    report = FontReport(stacks=(item,))

    assert report.mis_measured == ()
    assert report.compatible is True
    diagnostics = report.diagnostics()
    assert [(item.code, item.blocking) for item in diagnostics] == [
        ("font_weight_face_substituted", False)
    ]
    assert "700" in diagnostics[0].message
    assert "Light" in diagnostics[0].message


def test_a_heavier_nearest_face_is_not_reported_as_a_substitution() -> None:
    """``Arial`` at 900 legitimately becomes ``Arial Black``; it must not fire.

    The platform names a black weight as its own family, and reporting it would
    fire on decks that are correct - which is how a check like this gets
    switched off.
    """
    item = FontStackResolution(
        stack="Arial, sans-serif",
        weight="900",
        families=("Arial",),
        available=("Arial",),
        missing=(),
        resolved_family="Arial Black",
        resolved_face="Arial-Black",
    )
    report = FontReport(stacks=(item,))

    assert item.weight_substituted is False
    assert report.compatible is True
    assert report.diagnostics() == ()


def test_a_heavy_weight_named_into_the_family_is_the_same_family() -> None:
    """``Segoe UI Black`` is ``Segoe UI`` at 800, not a different family."""
    item = FontStackResolution(
        stack='"Segoe UI", Arial, sans-serif',
        weight="800",
        families=("Segoe UI", "Arial"),
        available=("Segoe UI", "Arial"),
        missing=(),
        resolved_family="Segoe UI Black",
        resolved_face="SegoeUIBlack",
    )

    assert item.mis_measured is False
    assert item.weight_substituted is False


def test_an_absent_family_the_host_skips_past_is_reported_without_blocking() -> None:
    """The host never used the absent family, so the geometry is still right."""
    item = FontStackResolution(
        stack='"Segoe UI", "Brand Font", Arial, sans-serif',
        weight="400",
        families=("Segoe UI", "Brand Font", "Arial"),
        available=("Segoe UI", "Arial"),
        missing=("Brand Font",),
        resolved_family="Segoe UI",
        resolved_face="SegoeUI",
    )
    report = FontReport(stacks=(item,))

    assert report.compatible is True
    codes = [(diagnostic.code, diagnostic.blocking) for diagnostic in report.diagnostics()]
    assert codes == [("declared_font_family_skipped", False)]


def test_a_missing_input_reports_a_probe_error_rather_than_a_verdict(
    tmp_path: Path,
) -> None:
    report = font_preflight(tmp_path / "absent.html")

    assert report.probed is False
    assert report.probe_error
    assert report.compatible is True


# ---------------------------------------------------------------------------
# The external renderer
# ---------------------------------------------------------------------------


def test_renderer_preflight_passes_on_an_accepted_host() -> None:
    """The real OfficeCLI on this host must produce the real probe PNG."""
    report = renderer_preflight()

    assert report.available is True
    assert report.render
    assert report.diagnostics() == ()


def test_renderer_preflight_classifies_no_browser_at_all() -> None:
    """Nothing found on the host is a different fix than a browser it cannot see."""
    report = renderer_preflight(
        which=lambda _: None,
        installed=lambda: (),
        screenshot=lambda *_: [],
    )

    assert report.available is False
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "renderer_browser_missing"
    assert diagnostic.blocking is True
    assert "python3" in diagnostic.message
    assert "Chromium" in diagnostic.message
    assert diagnostic.remediation


def test_renderer_preflight_classifies_a_browser_officecli_cannot_reach() -> None:
    """The common case: the browser exists, so the message must say so."""
    report = renderer_preflight(
        which={"chromium": "/usr/bin/chromium"}.get,
        installed=lambda: (),
        screenshot=lambda *_: [],
    )

    assert report.available is False
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "renderer_browser_unreachable"
    assert "/usr/bin/chromium" in diagnostic.message
    assert "present on this host" in diagnostic.message


def test_renderer_preflight_does_not_trust_officecli_writing_no_file() -> None:
    """OfficeCLI exits 0 while writing nothing, so the file is the verdict."""
    report = renderer_preflight(
        which=lambda _: None,
        installed=lambda: (),
        screenshot=lambda *_: [],
    )

    assert report.available is False
    assert report.detail is not None
    assert "wrote no" in report.detail


def test_renderer_preflight_closes_its_disposable_document_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poisoned resident must never outlive the probe.

    Browser discovery happens inside the per-document resident with the
    environment of the first caller, so a probe that failed and left its
    resident alive would make the corrected retry fail too.
    """
    closed: list[list[str]] = []

    def fake_run_officecli(args, **_: object) -> subprocess.CompletedProcess[str]:
        closed.append(list(args))
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(preflight, "_run_officecli", fake_run_officecli)
    monkeypatch.setattr(preflight, "_screenshot_pptx", lambda *_: [])

    report = renderer_preflight(which=lambda _: None, installed=lambda: ())

    assert report.available is False
    assert any(args[0] == "create" for args in closed)
    assert any(args[:2] == ["close", args[1]] for args in closed if len(args) == 2)


def test_a_broken_officecli_is_reported_before_any_compilation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole ticket: fail on the precondition, not at the evidence stage."""
    from officecli_html_to_pptx._internal.officecli_compiler import _OfficeCLICommandError

    def exploding(args, **_: object):
        raise _OfficeCLICommandError("create", list(args), 1, "", "create failed")

    monkeypatch.setattr(preflight, "_run_officecli", exploding)
    report = renderer_preflight(which=lambda _: None, installed=lambda: ())

    assert report.available is False
    (diagnostic,) = report.diagnostics()
    assert diagnostic.blocking is True


# ---------------------------------------------------------------------------
# The combined preflight
# ---------------------------------------------------------------------------


def test_combined_preflight_reports_the_renderer_before_the_fonts(
    tmp_path: Path,
) -> None:
    """A broken renderer is the more fundamental failure, so it is named first."""
    author = _deck(tmp_path, "Inter, sans-serif", "Inter, sans-serif")
    renderer = preflight.RendererReport(available=False, render="html")
    fonts = FontReport(
        stacks=(
            FontStackResolution(
                stack="Inter, sans-serif",
                weight="400",
                families=("Inter",),
                available=(),
                missing=("Inter",),
                resolved_family=None,
                resolved_face=None,
            ),
        )
    )
    report = run_preflight(
        author,
        _font_preflight=lambda _: fonts,
        _renderer_preflight=lambda: renderer,
    )

    codes = [item.code for item in report.diagnostics]
    assert codes == ["renderer_browser_missing", "declared_font_family_absent"]
    assert report.compatible is False
    assert report.as_dict()["renderer"]["available"] is False
    assert report.as_dict()["fonts"]["compatible"] is False


def test_combined_preflight_is_compatible_when_both_preconditions_hold() -> None:
    report = run_preflight(
        "unused.html",
        _font_preflight=lambda _: FontReport(),
        _renderer_preflight=lambda: preflight.RendererReport(
            available=True, render="html"
        ),
    )

    assert isinstance(report, PreflightReport)
    assert report.compatible is True
    assert report.diagnostics == ()
