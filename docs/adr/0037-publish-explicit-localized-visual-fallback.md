---
status: accepted
---

# Publish explicit localized visual fallback in Contract 1.3

V0.5.3 publishes a narrow, explicit visual fallback for authored regions that
cannot be represented as one native PowerPoint object. The fallback is
opt-in, using only the case-sensitive
`data-pptx-rasterize="localized"` marker, and applies to one atomic authored
node. Its descendants are removed from generic discovery so the public result
has one auditable picture rather than a picture plus duplicate native
descendants.

Capture uses the node CSS border box, local isolation, and a fixed
`2 pixels per point` density. The result is a deterministic PNG lowered through
the existing picture path. The initial static allowlist is deliberately small;
scripts, runtime canvas, frames, network resources, media, WebGL, animation,
interaction state, cross-slide capture, and paint outside the border box are
unsupported or unresolved and block publication. Existing SVG picture fallback
remains a separate compatibility behavior.

The public disposition vocabulary is `native`, `rasterized`, `unsupported`,
and `unresolved`. Rasterized content is visual-only and is never represented as
editable text. Evidence and material comparison must prove source identity,
source path, slide, bounds, disposition, compiled kind, PNG hash, dimensions,
density, nonblank paint, isolation, and independent readback. The release gate
requires zero unapproved, blank, contaminated, failed-isolation, unsupported,
unresolved, and material-delta findings.

This decision supersedes the V0.5 sequencing deferral in ADR 0032 only for
this explicit localized seam. It does not introduce a general Object IR, kind
registry, runtime-dependent Contract semantics, or a whole-slide raster
fallback. The four-slide public corpus and the existing five-command workflow
are the release acceptance surface.
