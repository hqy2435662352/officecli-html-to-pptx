"""Build-path preflight for the two host conditions that fail silently or late.

Neither check here re-implements a platform rule.  The font probe asks the same
pinned Chromium that measures the deck, and the renderer probe asks OfficeCLI
for the same screenshot the Evidence Bundle will need, so a diagnostic can never
disagree with the renderer it guards.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

from ._internal.acceptance import _screenshot_pptx
from ._internal.officecli_compiler import OfficeCLICompilationError, _run_officecli
from .protocol import Diagnostic
from .runtime import (
    PPTX_SCREENSHOT_DEFAULT_RENDER,
    officecli_pptx_screenshot_render,
)
from .styles import resolve_pptx_font

# The probe page is a few kilobytes of inline styles, so a generous navigation
# timeout buys nothing; the font work itself is bounded separately.
_NAVIGATION_TIMEOUT_MS = 120_000
_FONT_PROBE_TIMEOUT_MS = 120_000

_RENDERER_REQUIREMENT = (
    "OfficeCLI needs a headless browser for this render path: a PATH entry "
    "carrying a Playwright-capable python3, or a system Chromium "
    "(chromium / google-chrome / chromium-browser)."
)
_RENDERER_REMEDIATION = (
    "Install the pinned browser where OfficeCLI can discover it - run "
    "uv run playwright install chromium, or expose a system Chromium on PATH - "
    "then rerun the build. The product never installs a browser for you."
)


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FontStackResolution:
    """What Chromium did with one declared font stack."""

    stack: str
    weight: str
    families: tuple[str, ...]
    available: tuple[str, ...]
    missing: tuple[str, ...]
    resolved_family: str | None
    resolved_face: str | None
    source_slide: int | None = None
    source_object: str | None = None

    @property
    def mis_measured(self) -> bool:
        """Whether Chromium drew this text in a family the PPTX will not declare.

        Three ways the measured geometry and the declaration can disagree, and
        only the first two matter.  The host may land on a family the stack
        never named at all; it may fall through to a *later* family the PPTX
        does not declare; or it may simply skip over an absent family on its way
        to the one the PPTX declares, which measures exactly what the PPTX
        says and is therefore harmless.
        """
        if self.resolved_family is None:
            return bool(self.missing)
        declared = declared_family(self.stack)
        if declared.casefold() in _CSS_GENERIC_FAMILIES:
            # A stack of nothing but generic keywords names no typeface, so its
            # resolved family is the resolver's decision to make rather than a
            # host-supply condition this check can judge.
            return False
        return not _same_family(self.resolved_family, declared)

    @property
    def weight_substituted(self) -> bool:
        """Whether the requested weight was served by a lighter face.

        The reported failure is a host that cannot supply the requested weight
        and answers with something lighter, because the text is then drawn with
        narrower metrics than the weight asked for.  A heavier nearest face is
        not reported: the platform naming a black weight as its own family is
        how ``Arial`` at 900 legitimately becomes ``Arial Black``, and firing on
        it would fire on decks that are correct.

        The comparison uses the *rendered* family as well as the face name,
        because a platform may name the weight into the family
        (``Segoe UI Semibold``) or into the PostScript name
        (``SegoeUI-Semibold``).
        """
        requested = _weight_value(self.weight)
        rendered = _face_weight(self.resolved_face or "") or _face_weight(
            self.resolved_family or ""
        )
        if requested is None or rendered is None:
            return False
        return rendered < requested

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "stack": self.stack,
            "weight": self.weight,
            "families": list(self.families),
            "available": list(self.available),
            "missing": list(self.missing),
            "resolved_family": self.resolved_family,
            "resolved_face": self.resolved_face,
            "mis_measured": self.mis_measured,
        }
        if self.source_slide is not None:
            data["source_slide"] = self.source_slide
        if self.source_object is not None:
            data["source_object"] = self.source_object
        return data


@dataclass(frozen=True)
class FontReport:
    """The font findings of one Author HTML against one host."""

    stacks: tuple[FontStackResolution, ...] = ()
    probed: bool = True
    probe_error: str | None = None

    @property
    def mis_measured(self) -> tuple[FontStackResolution, ...]:
        return tuple(item for item in self.stacks if item.mis_measured)

    @property
    def weight_substitutions(self) -> tuple[FontStackResolution, ...]:
        return tuple(
            item
            for item in self.stacks
            if not item.mis_measured and item.weight_substituted
        )

    @property
    def skipped_families(self) -> tuple[FontStackResolution, ...]:
        """Stacks that name an absent family the host simply skips past.

        Reported because the declaration asks for a family this host lacks, but
        not blocked: Chromium measured in the family the PPTX declares, so the
        geometry is right and nothing is silently wrong.
        """
        return tuple(
            item for item in self.stacks if not item.mis_measured and item.missing
        )

    @property
    def compatible(self) -> bool:
        return not self.mis_measured

    def diagnostics(self) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []
        for item in self.mis_measured:
            diagnostics.append(
                Diagnostic(
                    code="declared_font_family_absent",
                    severity="error",
                    message=_missing_family_message(item),
                    blocking=True,
                    source_slide=item.source_slide,
                    source_object=item.source_object,
                    remediation=(
                        "Install the declared family on the build host, or change the "
                        "Author HTML to a family the host supplies. Chromium measured "
                        "this text in a substitute, so the geometry would be laid out "
                        "in a different face than the PPTX declares."
                    ),
                    recheck=(
                        "officecli-html-to-pptx build --json <author.html> <output.pptx>"
                    ),
                )
            )
        for item in self.skipped_families:
            absent = ", ".join(repr(name) for name in item.missing)
            diagnostics.append(
                Diagnostic(
                    code="declared_font_family_skipped",
                    severity="warning",
                    message=(
                        f"{_subject(item)} declares font stack [{item.stack}], and this "
                        f"build host cannot supply {absent}. Chromium skipped past it and "
                        f"measured in {item.resolved_family!r}, which is the family the "
                        "PPTX declares, so the geometry is correct."
                    ),
                    blocking=False,
                    source_slide=item.source_slide,
                    source_object=item.source_object,
                    remediation=(
                        "Install the skipped family if the deck is meant to render in it "
                        "on this host; otherwise no action is needed for this build."
                    ),
                    recheck=(
                        "officecli-html-to-pptx build --json <author.html> <output.pptx>"
                    ),
                )
            )
        for item in self.weight_substitutions:
            diagnostics.append(
                Diagnostic(
                    code="font_weight_face_substituted",
                    severity="warning",
                    message=(
                        f"Font weight {item.weight} of {item.resolved_family!r} resolved "
                        f"to {item.resolved_face!r}, not the requested weight face; text "
                        "metrics follow the substituted face."
                    ),
                    blocking=False,
                    source_slide=item.source_slide,
                    source_object=item.source_object,
                    remediation=(
                        "Install the family's weight face (ariblk.ttf is the Arial 900 "
                        "face), or accept the host's nearest face - the PPTX declares the "
                        "family, so PowerPoint substitutes the same way."
                    ),
                    recheck=(
                        "officecli-html-to-pptx build --json <author.html> <output.pptx>"
                    ),
                )
            )
        return tuple(diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "probed": self.probed,
            "probe_error": self.probe_error,
            "compatible": self.compatible,
            "stacks": [item.as_dict() for item in self.stacks],
        }


def _missing_family_message(item: FontStackResolution) -> str:
    absent = ", ".join(repr(name) for name in item.missing)
    declared = declared_family(item.stack)
    measured = (
        f"in {item.resolved_family!r}"
        if item.resolved_family
        else "in a system default rather than in any family the stack names"
    )
    return (
        f"{_subject(item)} declares font stack [{item.stack}], but this build host "
        f"cannot supply {absent}. Chromium measured that text {measured} while "
        f"the PPTX would declare {declared!r}, so the measured box and the declared "
        "font disagree."
    )


def _subject(item: FontStackResolution) -> str:
    if item.source_object and item.source_slide is not None:
        return f"Slide {item.source_slide} object {item.source_object}"
    if item.source_object:
        return f"Object {item.source_object}"
    if item.source_slide is not None:
        return f"Slide {item.source_slide}"
    return "This Author HTML"


def _strip_family(value: str) -> str:
    """Reduce one ``font-family`` list entry to a family name.

    Quotes delimit one family and are removed; an unquoted entry keeps its full
    text, because a task-oriented generator emits the family it means and
    truncating ``Arial Black`` to ``Arial`` would check the wrong typeface.
    """
    return value.strip().strip("'\"'")


def named_families(stack: str) -> tuple[str, ...]:
    """Every family a CSS font-family stack names, generic keywords included.

    These are the families the browser and the resolver both read off the
    declaration, so they are what the PPTX's declared family is compared
    against.  Generic keywords belong here rather than in the probe: they are
    not typefaces a host can fail to supply, and ``resolve_pptx_font`` maps each
    onto a concrete safe family.
    """
    names: list[str] = []
    for part in str(stack).split(","):
        name = _strip_family(part)
        if name and name not in names:
            names.append(name)
    return tuple(names)


def probed_families(stack: str) -> tuple[str, ...]:
    """The families of a stack that a host can actually supply or lack."""
    return tuple(
        name for name in named_families(stack) if name.casefold() not in _CSS_GENERIC_FAMILIES
    )


_CSS_GENERIC_FAMILIES = frozenset(
    {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-sans-serif",
        "ui-serif",
        "ui-monospace",
        "ui-rounded",
        "math",
        "emoji",
        "fangsong",
        "-apple-system",
        "blinkmacsystemfont",
    }
)


def declared_family(stack: str) -> str:
    """The family the PPTX will declare for this stack.

    Delegated to the Author compiler's own resolver rather than re-derived, so
    "what the PPTX declares" cannot drift from what ``build`` actually writes.
    """
    return resolve_pptx_font(str(stack))


def _same_family(resolved: str, declared: str) -> bool:
    """Whether a resolved name is the declared family or one of its weights.

    Platforms spell a heavy weight three different ways, and each is the host
    honestly rendering the declared family rather than substituting it:

    * into the family - ``Segoe UI Black`` for ``Segoe UI`` at 800;
    * into the PostScript style suffix - ``Arial-Black`` for ``Arial Black``;
    * not at all - ``SegoeUI-Bold`` for ``Segoe UI`` at 700.

    So a resolved name counts as the same family when either its style-stripped
    form extends the declared name, or its full form does.  Comparing family
    keys alone would report every heavy-weight deck as broken.

    The cost of that acceptance is bounded and deliberate: a genuinely different
    family whose name starts with a declared one (``Arial Narrow`` against
    ``Arial``) reads as the same family.  Missing that case is a false pass on a
    deck whose declared family *is* present, while the alternative fires on
    every correct deck that uses a heavy weight face.
    """
    declared_key = declared.replace(" ", "").casefold()
    if not declared_key:
        return False
    return any(
        candidate.startswith(declared_key)
        for candidate in (
            resolved.split("-", 1)[0].replace(" ", "").casefold(),
            resolved.replace(" ", "").casefold(),
        )
    )


_WEIGHT_FACE_BANDS: tuple[tuple[str, int], ...] = (
    ("extrablack", 900),
    ("ultrablack", 900),
    ("semibold", 600),
    ("demibold", 600),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("extralight", 200),
    ("ultralight", 200),
    ("black", 900),
    ("heavy", 900),
    ("bold", 700),
    ("medium", 500),
    ("light", 300),
    ("thin", 100),
)


def _face_weight(face: str) -> int | None:
    """The weight band a resolved face's own name claims, or ``None``."""
    key = face.replace(" ", "").casefold()
    for name, weight in _WEIGHT_FACE_BANDS:
        if name in key:
            return weight
    return None


def _weight_value(value: str) -> int | None:
    """The numeric CSS weight a computed ``font-weight`` reports."""
    text = str(value).strip().casefold()
    if text.isdigit():
        return max(1, min(1000, int(text)))
    return {"normal": 400, "bold": 700, "bolder": 700, "lighter": 300}.get(text)


def family_names(stack: str) -> tuple[str, ...]:
    """The family names of one CSS font-family stack, in declared order."""
    return tuple(
        name for name in (_strip_family(part) for part in str(stack).split(",")) if name
    )


def _collect_font_stacks(elements: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return one record per distinct declared (stack, weight) pair."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for element in elements:
        stack = str(element.get("fontFamily") or "").strip()
        families = probed_families(stack)
        if not families:
            continue
        weight = str(element.get("fontWeight") or "400").strip() or "400"
        key = (stack, weight)
        if key in found:
            continue
        raw_slide = element.get("index")
        found[key] = {
            "stack": stack,
            "weight": weight,
            "families": families,
            "source_slide": int(raw_slide) + 1 if isinstance(raw_slide, int) else None,
            "source_object": _element_source_path(element),
        }
    return list(found.values())


def _element_source_path(element: Mapping[str, Any]) -> str | None:
    for key in ("sourcePath", "source_path", "dataPath", "path"):
        value = element.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _resolve_stacks_in_chromium(
    stacks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve every declared stack against the host's real font supply.

    Two renderer answers are combined.  ``FontFace`` with a ``local()`` source
    reports family availability, and the DevTools Protocol's
    ``CSS.getPlatformFontsForNode`` reports the face Chromium actually drew
    with, which is the only way the weight case can be answered at all.
    """
    from playwright.async_api import async_playwright

    pairs = [
        [str(item["stack"]), str(item["weight"]), list(item["families"])]
        for item in stacks
    ]
    if not pairs:
        return []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1024, "height": 768})
            page.set_default_timeout(_FONT_PROBE_TIMEOUT_MS)
            # A blank document: the probe builds its own elements, so a font
            # stack full of quotes can never be mis-parsed as markup.
            await page.set_content(
                "<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body style='margin:0'></body></html>",
                wait_until="load",
                timeout=_NAVIGATION_TIMEOUT_MS,
            )
            resolved = await page.evaluate(_FONT_RESOLUTION_SCRIPT, {"pairs": pairs})
            faces = await _resolved_faces(page, len(pairs))
        finally:
            await browser.close()

    for index, item in enumerate(resolved):
        item["source_slide"] = stacks[index].get("source_slide")
        item["source_object"] = stacks[index].get("source_object")
        if item.get("available"):
            family, face = faces.get(index, (None, None))
            item["resolved_family"] = family
            item["resolved_face"] = face
        else:
            # No family the stack named was supplied, so Chromium drew a default
            # that the request never mentioned.  Reporting that default as the
            # "resolved family" would let the classifier mistake it for a family
            # relationship, so the resolution is left empty and the absent family
            # is what gets reported.
            item["resolved_family"] = None
            item["resolved_face"] = None
    return list(resolved)


async def _resolved_faces(
    page: Any,
    count: int,
) -> dict[int, tuple[str | None, str | None]]:
    """Which face Chromium actually drew each probe div with.

    The ``ProbeFace`` the availability test registered is removed first, so the
    reported face is the host's own choice rather than the probe's.
    """
    session = await page.context.new_cdp_session(page)
    try:
        # Enabling DOM returns the document, which is also what makes
        # ``DOM.requestNode`` resolve remote objects to usable node ids.
        await session.send("DOM.enable")
        await session.send("CSS.enable")
        await session.send("DOM.getDocument")
        await page.evaluate(
            "document.fonts.forEach((face) => { if (face.family === 'ProbeFace') "
            "document.fonts.delete(face); })"
        )
        resolved: dict[int, tuple[str | None, str | None]] = {}
        for index in range(count):
            evaluated = await session.send(
                "Runtime.evaluate",
                {
                    "expression": f"document.querySelectorAll('.p')[{index}]",
                    "objectGroup": "preflight",
                },
            )
            object_id = (evaluated.get("result") or {}).get("objectId")
            if not object_id:
                continue
            try:
                node = await session.send("DOM.requestNode", {"objectId": object_id})
                fonts = await session.send(
                    "CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]}
                )
            finally:
                await session.send("Runtime.releaseObject", {"objectId": object_id})
            served = fonts.get("fonts") or []
            primary = served[0] if served else {}
            resolved[index] = (
                primary.get("familyName"),
                primary.get("postScriptName") or primary.get("familyName"),
            )
        return resolved
    finally:
        await session.detach()


def font_preflight(input_html: str | Path) -> FontReport:
    """Report whether this host can honour the families the Author HTML declares.

    Read-only: the Author HTML is opened in a disposable Chromium page, nothing
    is written, and no measurement pass runs.
    """
    path = Path(input_html).expanduser()
    try:
        elements = _load_declared_fonts(path)
    except Exception as exc:  # pragma: no cover - renderer dependent
        return FontReport(probed=False, probe_error=str(exc))
    stacks = _collect_font_stacks(elements)
    if not stacks:
        return FontReport()
    try:
        resolved = asyncio.run(_resolve_stacks_in_chromium(stacks))
    except Exception as exc:  # pragma: no cover - renderer dependent
        return FontReport(probed=False, probe_error=str(exc))
    return FontReport(stacks=tuple(_resolution(item) for item in resolved))


def _resolution(item: Mapping[str, Any]) -> FontStackResolution:
    return FontStackResolution(
        stack=str(item.get("stack", "")),
        weight=str(item.get("weight", "")),
        families=tuple(item.get("families") or ()),
        available=tuple(item.get("available") or ()),
        missing=tuple(item.get("missing") or ()),
        resolved_family=item.get("resolved_family"),
        resolved_face=item.get("resolved_face"),
        source_slide=item.get("source_slide"),
        source_object=item.get("source_object"),
    )


def _load_declared_fonts(path: Path) -> list[Mapping[str, Any]]:
    """Collect declared font stacks from the Author HTML in a disposable page."""
    if not path.is_file():
        raise FileNotFoundError(f"Author HTML input does not exist: {path}")

    async def collect() -> list[Mapping[str, Any]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1920, "height": 1080})
                await page.goto(
                    path.resolve().as_uri(),
                    wait_until="load",
                    timeout=_NAVIGATION_TIMEOUT_MS,
                )
                return await page.evaluate(_DECLARED_STACKS_SCRIPT)
            finally:
                await browser.close()

    return asyncio.run(collect())


# Runs in the Author HTML page: one record per (stack, weight) a text-bearing
# element actually asks for after the cascade, so inherited and class-based
# declarations are included and nothing is predicted from source text.  Elements
# hidden by the workbench's own slide switcher are skipped, because they are not
# measured either.  ``index`` is the slide the element belongs to, so a finding
# can name it.
_DECLARED_STACKS_SCRIPT = """
() => {
  const roots = document.querySelectorAll('.slide');
  const scopes = roots.length ? Array.from(roots) : [document.body];
  const out = [];
  const seen = new Set();
  scopes.forEach((scope, scopeIndex) => {
    scope.querySelectorAll('*').forEach((element) => {
      const text = (element.textContent || '').trim();
      if (!text) return;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return;
      const stack = style.fontFamily;
      if (!stack) return;
      const weight = style.fontWeight || '400';
      const key = stack + '\\u0000' + weight;
      if (seen.has(key)) return;
      seen.add(key);
      out.push({
        index: scopeIndex,
        fontFamily: stack,
        fontWeight: weight,
        sourcePath: element.getAttribute('data-path') || null,
      });
    });
  });
  return out;
}
"""

# Runs in the disposable probe page.  Every family of every declared stack is
# resolved on its own, so the answer does not depend on which other families
# happen to be installed: a stack's tails matter as much as its head.  The
# families arrive already parsed, and the probe elements are built here rather
# than in markup, so a stack that quotes its family names cannot be mis-parsed.
_FONT_RESOLUTION_SCRIPT = """
async (payload) => {
  const pairs = payload.pairs;
  const out = [];
  const host = document.body;

  const familyAvailable = async (family) => {
    if (!family) return false;
    try {
      const face = new FontFace('ProbeFace', `local(${JSON.stringify(family)})`);
      await face.load();
      return true;
    } catch (error) {
      return false;
    }
  };

  for (let index = 0; index < pairs.length; index += 1) {
    const stack = pairs[index][0];
    const weight = pairs[index][1];
    const families = pairs[index][2];

    const element = document.createElement('div');
    element.className = 'p';
    element.style.fontFamily = stack;
    element.style.fontWeight = weight;
    element.style.display = 'inline-block';
    element.textContent = 'Hamburgefonstiv';
    host.appendChild(element);

    const available = [];
    const missing = [];
    for (const family of families) {
      if (await familyAvailable(family)) available.push(family);
      else missing.push(family);
    }
    out.push({
      stack: stack,
      weight: weight,
      families: families,
      available: available,
      missing: missing,
      // The first family the host can supply is the one Chromium draws with,
      // so it is also the one the measured geometry came from.
      resolved_family: available.length ? available[0] : null,
      resolved_face: null,
    });
  }
  return out;
}
"""


# ---------------------------------------------------------------------------
# External renderer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RendererReport:
    """Whether OfficeCLI can still produce the screenshot the build needs."""

    available: bool
    render: str
    candidates: tuple[str, ...] = ()
    detail: str | None = None

    def diagnostics(self) -> tuple[Diagnostic, ...]:
        if self.available:
            return ()
        code = (
            "renderer_browser_unreachable"
            if self.candidates
            else "renderer_browser_missing"
        )
        return (
            Diagnostic(
                code=code,
                severity="error",
                message=self.message(),
                blocking=True,
                operation="view screenshot",
                remediation=_RENDERER_REMEDIATION,
                recheck="officecli-html-to-pptx doctor --json",
            ),
        )

    def message(self) -> str:
        head = (
            f"OfficeCLI cannot produce a PPTX screenshot through the {self.render!r} "
            "render path, which the Evidence Bundle's PPTX panel requires."
        )
        if self.candidates:
            found = ", ".join(self.candidates)
            return (
                f"{head} A browser is present on this host ({found}), so the "
                "requirement looks satisfied but OfficeCLI is not reaching it."
            )
        return (
            f"{head} No browser was found on PATH, at the Playwright-managed "
            f"location, or at a conventional install path. {_RENDERER_REQUIREMENT}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "render": self.render,
            "requirement": _RENDERER_REQUIREMENT,
            "browser_candidates": list(self.candidates),
            "detail": self.detail,
        }


def renderer_preflight(
    *,
    which: Callable[[str], str | None] = shutil.which,
    screenshot: Callable[[Path, Path, int], Sequence[Path]] | None = None,
    installed: Callable[[], Sequence[str]] | None = None,
) -> RendererReport:
    """Prove OfficeCLI can screenshot a disposable document before compiling.

    The probe checks for the written PNG, not the exit status: OfficeCLI exits
    ``0`` while writing no file, so a status-based probe would report a broken
    host as healthy.  The probe document is closed on every path, so a resident
    that cached a failed browser discovery never survives to poison a retry.
    """
    find_installed = _conventional_browser_paths if installed is None else installed
    render = officecli_pptx_screenshot_render()
    capture = screenshot or _probe_screenshot
    directory = Path(tempfile.mkdtemp(prefix=".renderer-preflight-"))
    probe_document = directory / "probe.pptx"
    try:
        try:
            _write_probe_document(probe_document)
        except (OSError, OfficeCLICompilationError, RuntimeError) as exc:
            return RendererReport(
                available=False,
                render=render,
                candidates=_browser_candidates(which, find_installed),
                detail=f"Could not create the probe document: {exc}",
            )
        try:
            produced = [
                Path(path)
                for path in capture(probe_document, directory / "capture", 1)
                if Path(path).is_file()
            ]
            detail = None
        except Exception as exc:
            produced = []
            detail = str(exc)
        if produced:
            return RendererReport(available=True, render=render, detail=detail)
        if detail is None:
            detail = (
                "OfficeCLI reported success for the probe screenshot but wrote no "
                "PNG file."
            )
        return RendererReport(
            available=False,
            render=render,
            candidates=_browser_candidates(which, find_installed),
            detail=detail,
        )
    finally:
        # The resident must not outlive the probe: browser discovery happens
        # inside it with the environment of the first caller, so a poisoned
        # resident would make a corrected environment fail on retry.
        try:
            _run_officecli(["close", str(probe_document)], check=False)
        except Exception:  # pragma: no cover - cleanup must not mask the verdict
            pass
        shutil.rmtree(directory, ignore_errors=True)


def _probe_screenshot(
    probe_document: Path, directory: Path, slide_count: int
) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return _screenshot_pptx(probe_document, directory, slide_count)


def _write_probe_document(path: Path) -> None:
    """Create one slide holding one text shape through the real OfficeCLI path.

    A blank document would leave the HTML projection with nothing to draw, so
    the probe would not exercise the text projection the evidence needs.
    """
    _run_officecli(["create", str(path)])
    for command in (
        {
            "command": "add",
            "parent": "/",
            "type": "slide",
            "props": {"name": "preflight"},
        },
        {
            "command": "add",
            "parent": "/slide[1]",
            "type": "shape",
            "props": {
                "name": "preflight-text",
                "text": "renderer preflight",
                "x": "1cm",
                "y": "1cm",
                "width": "8cm",
                "height": "2cm",
            },
        },
    ):
        _run_officecli(
            ["batch", str(path)],
            input_text=json.dumps([command], separators=(",", ":")),
        )


_PLATFORM_BROWSER_NAMES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "msedge",
)


def _browser_candidates(
    which: Callable[[str], str | None] = shutil.which,
    installed: Callable[[], Sequence[str]] | None = None,
) -> tuple[str, ...]:
    """Host browsers that exist but that OfficeCLI may still not be reaching.

    This lookup only chooses the diagnostic's wording; the probe's own file
    check decides pass or fail, so a candidate OfficeCLI cannot use is reported
    as *unreachable* rather than being mistaken for a pass.
    """
    find_installed = _conventional_browser_paths if installed is None else installed
    found: list[str] = []
    for name in _PLATFORM_BROWSER_NAMES:
        located = which(name)
        if located:
            found.append(f"{name} on PATH at {located}")
    if which("python3"):
        found.append("a python3 on PATH")
    elif which("python"):
        found.append("a python on PATH (OfficeCLI looks for python3)")
    found.extend(f"{path} (installed, not on PATH)" for path in find_installed())
    return tuple(found)


def _conventional_browser_paths() -> list[str]:
    """Browser installs OfficeCLI may find without them being on PATH."""
    if sys.platform != "win32":
        return []
    candidates: list[str] = []
    roots = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for root in filter(None, roots):
        for relative in (
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ):
            candidate = Path(root) / relative
            if candidate.is_file():
                candidates.append(str(candidate))
    return candidates


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreflightReport:
    """Both build-path preconditions, in the order they are reported."""

    renderer: RendererReport | None = None
    fonts: FontReport | None = None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    @property
    def compatible(self) -> bool:
        return not any(item.blocking for item in self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "renderer": self.renderer.as_dict() if self.renderer else None,
            "fonts": self.fonts.as_dict() if self.fonts else None,
        }


def preflight(
    input_html: str | Path,
    *,
    _font_preflight: Callable[[str | Path], FontReport] = font_preflight,
    _renderer_preflight: Callable[..., RendererReport] = renderer_preflight,
) -> PreflightReport:
    """Run both host preconditions before any compilation.

    They are independent and each is already synchronous (one Chromium launch,
    and a handful of OfficeCLI calls), so the caller decides whether to overlap
    them with anything else rather than paying for a thread pool here.
    """
    fonts = _font_preflight(input_html)
    renderer = _renderer_preflight()
    diagnostics: list[Diagnostic] = []
    for report in (renderer, fonts):
        diagnostics.extend(report.diagnostics())
    return PreflightReport(renderer=renderer, fonts=fonts, diagnostics=tuple(diagnostics))


__all__ = [
    "FontReport",
    "FontStackResolution",
    "PreflightReport",
    "RendererReport",
    "font_preflight",
    "named_families",
    "preflight",
    "probed_families",
    "renderer_preflight",
]
