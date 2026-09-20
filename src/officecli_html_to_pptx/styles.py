"""Renderer-neutral font-family normalization for the Author compiler.

The mapping keeps browser-authored font stacks in a safe Office family without
importing a PowerPoint renderer.
"""

from __future__ import annotations

# Fonts that ship with Windows/Office (and are Microsoft-metric-compatible on
# macOS/LibreOffice), so we can rely on them rendering without substitution.
_SAFE_FONTS = {
    "arial", "arial black", "calibri", "cambria", "candara", "consolas",
    "constantia", "corbel", "courier new", "georgia", "times new roman",
    "trebuchet ms", "verdana", "segoe ui", "microsoft yahei", "tahoma", "garamond",
    "book antiqua", "century gothic", "palatino linotype", "gill sans",
    "franklin gothic medium", "lucida sans", "impact",
}

# Explicit web-font -> metric/style-compatible safe equivalent. Grouped so the
# substitute stays in the SAME visual family (display-serif, humanist-sans,
# geometric-sans, monospace); keeping the family keeps glyph advance widths
# close, which stops headings from reflowing onto an extra line.
_FONT_EQUIVALENTS = {
    # ---- display / body serifs ----
    "playfair display": "Georgia",
    "playfair": "Georgia",
    "merriweather": "Georgia",
    "lora": "Georgia",
    "pt serif": "Georgia",
    "noto serif": "Georgia",
    "source serif pro": "Cambria",
    "source serif 4": "Cambria",
    "roboto slab": "Cambria",
    "dm serif display": "Georgia",
    "dm serif text": "Georgia",
    "cormorant": "Cambria",
    "cormorant garamond": "Cambria",
    "eb garamond": "Garamond",
    "crimson text": "Garamond",
    "crimson pro": "Garamond",
    "libre baskerville": "Georgia",
    "bitter": "Georgia",
    "spectral": "Cambria",
    "frank ruhl libre": "Georgia",
    # ---- humanist / grotesque sans ----
    "inter": "Segoe UI",
    "roboto": "Arial",
    "open sans": "Segoe UI",
    "lato": "Calibri",
    "noto sans": "Segoe UI",
    "source sans pro": "Segoe UI",
    "source sans 3": "Segoe UI",
    "work sans": "Segoe UI",
    "dm sans": "Segoe UI",
    "manrope": "Segoe UI",
    "ibm plex sans": "Segoe UI",
    "pt sans": "Segoe UI",
    "rubik": "Segoe UI",
    "karla": "Segoe UI",
    "mulish": "Segoe UI",
    "barlow": "Segoe UI",
    "titillium web": "Segoe UI",
    "figtree": "Segoe UI",
    "plus jakarta sans": "Segoe UI",
    "ubuntu": "Segoe UI",
    "helvetica": "Arial",
    "helvetica neue": "Arial",
    "nunito": "Calibri",
    "nunito sans": "Calibri",
    # ---- geometric sans ----
    "montserrat": "Century Gothic",
    "poppins": "Century Gothic",
    "raleway": "Century Gothic",
    "quicksand": "Century Gothic",
    "josefin sans": "Century Gothic",
    "comfortaa": "Century Gothic",
    # ---- monospace ----
    "jetbrains mono": "Consolas",
    "fira code": "Consolas",
    "fira mono": "Consolas",
    "source code pro": "Consolas",
    "roboto mono": "Consolas",
    "ibm plex mono": "Consolas",
    "space mono": "Consolas",
    "ubuntu mono": "Consolas",
    "inconsolata": "Consolas",
    "menlo": "Consolas",
    "monaco": "Consolas",
    "courier": "Courier New",
}

# CSS generic keyword -> concrete safe default (same family class).  This is
# every generic family keyword a browser can put in a computed ``font-family``,
# because each one asks the environment to choose a face rather than naming one:
# passing it through as a typeface would hand PowerPoint an unresolvable name
# and let it substitute silently.
_GENERIC_FALLBACK = {
    "serif": "Georgia",
    "sans-serif": "Calibri",
    "monospace": "Consolas",
    "cursive": "Segoe Script",
    "fantasy": "Segoe UI",
    "system-ui": "Segoe UI",
    "ui-sans-serif": "Segoe UI",
    "ui-serif": "Georgia",
    "ui-monospace": "Consolas",
    "ui-rounded": "Segoe UI",
    "math": "Cambria Math",
    "emoji": "Segoe UI Emoji",
    "fangsong": "FangSong",
    "-apple-system": "Segoe UI",
    "blinkmacsystemfont": "Segoe UI",
}
# CSS-wide keywords are not families at all: they inherit or reset, so the
# resolved typeface is whatever the cascade produced elsewhere.
_CSS_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})


def resolve_pptx_font(css_font: str) -> str:
    """Pick a rendering-safe font that stays in the source's visual family.

    Walks the CSS font-family stack in declared order and returns the first of:
      1. a family already known to be installed everywhere, else
      2. a known web font mapped to a metric-compatible safe equivalent, else
      3. the stack's own first concrete family, else
      4. the CSS generic keyword default.

    Step 3 exists because a font stack is a *request*.  An Author HTML deck that
    asks for a named typeface — including a CJK face such as ``Microsoft YaHei``
    that is installed on the target platform — is declaring that typeface, not
    asking for a substitution, and rewriting it to a generic Latin default would
    silently change the deck's typography.

    What step 3 must *not* accept is something that is not a family name at all.
    A CSS-wide keyword (``inherit``) or a functional value (``var(--deck-font)``)
    names no typeface, and writing either into the PPTX would hand PowerPoint an
    unresolvable name and let it substitute silently — the very failure this
    resolution exists to prevent.  Those fall through to the safe default.
    """
    if not css_font:
        return "Calibri"
    generic_seen: str | None = None
    declared_seen: str | None = None
    for raw in css_font.split(","):
        name = raw.strip().strip("'\"")
        if not name:
            continue
        low = name.lower()
        if low in _SAFE_FONTS:
            return name
        if low in _FONT_EQUIVALENTS:
            return _FONT_EQUIVALENTS[low]
        if low in _GENERIC_FALLBACK:
            if generic_seen is None:
                generic_seen = _GENERIC_FALLBACK[low]
            continue
        if low in _CSS_WIDE_KEYWORDS or "(" in name or ")" in name:
            continue
        if declared_seen is None:
            declared_seen = name
    return declared_seen or generic_seen or "Calibri"


# ---------------------------------------------------------------------------
