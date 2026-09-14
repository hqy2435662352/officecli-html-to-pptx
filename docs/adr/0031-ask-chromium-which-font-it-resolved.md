---
status: accepted
---

# Ask Chromium which font it resolved

Nothing verified that the build host could supply the font families and weight
faces the Author HTML declares. Chromium measures text on the build host and the
PPTX then declares the family `styles.resolve_pptx_font` resolved, so a host
without that family silently substitutes, sizes the text box from the substitute,
and produces a visibly wrong deck while `doctor`, `check` and `build` all report
success. A family can also be present while the requested weight face is not:
`Arial` has no 900 face, and the host's choice between `Arial Black` and a
synthesized bold moved one object per slide on a real 27-slide deck.

The check therefore asks Chromium, because Chromium is the authority. Four
candidate mechanisms were measured in the pinned Chromium before this decision,
and three of them are rejected. `navigator.fonts.query()` (Local Font Access) is
undefined in headless Chromium, so there is no host font inventory to read.
`document.fonts.check()` returns `true` for a family that does not exist, so it
cannot detect anything. Canvas advance-width comparison looks plausible and is
wrong: `Consolas` at weight 700 draws the real `Consolas-Bold` face while its
advance is byte-identical to the regular face, so equal advances do not prove a
face is missing.

What is left is two mechanisms that each answer one question truthfully. A
`FontFace` built with a `local()` source resolves for a family the host can
supply and rejects with `NetworkError` for one it cannot, which is a family
oracle that shares Blink's own font lookup. The DevTools Protocol's
`CSS.getPlatformFontsForNode` reports the family and PostScript name Chromium
actually drew with, which is what makes the weight case answerable at all:
`Arial` at 900 comes back as `Arial-Black`, and `Segoe UI` at 600 comes back as
`Segoe UI Semibold` rather than being silently rounded.

The two answers are then classified, not conflated. A declared family that is
absent from the host **blocks**, because that is the silent mis-measurement: the
geometry was measured in a family the PPTX does not declare. A family that is
present but whose requested weight resolved to a differently named face is
reported **without blocking**, because the host's font matching choosing the
nearest face is exactly what PowerPoint will do with the same declaration. That
severity split is the escape hatch the deck relying on a documented substitution
needs, so no separate acknowledgement flag is introduced.

Every family in a declared stack is resolved on its own rather than only the one
`resolve_pptx_font` selects, because the difference between the two failures is
the stack's tail. An Author HTML that asks for `'Microsoft YaHei', Arial,
sans-serif` on a host without YaHei measures in Arial; only naming YaHei makes
that visible instead of reporting a clean pass.
