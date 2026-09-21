# Author HTML

Read this reference only while creating, reconstructing, or materially
repairing the Candidate HTML. It is practical authoring guidance; the
installed Author Contract and generated capability data remain authoritative
for exact supported properties, object kinds, and versions.

## Workbench target

Create a browsable slide workbench with one clear slide boundary per intended
slide. Keep visible content as independent authored DOM objects so the Core
Product can lower it to editable text, shapes, pictures, and tables. Keep
source and reconstructed work in a new `.author.html` file; the user's
original HTML and reference files remain unchanged.

Treat the supplied content brief as content and composition context, not as a
compiler input. Treat each supplied reference image as appearance context. If
references are supplied, inspect every image before authoring and preserve the
meaningful visible details that the brief or reference establishes.

## Contract-first authoring

1. Start from the installed Contract and `check --json`. Read
   `capabilities --json` when a choice depends on whether a CSS property,
   object kind, or resource form is supported. Do not copy a capability matrix
   into this reference; those commands are the source of truth.
2. Author with native text, shapes, pictures, and tables inside that reported
   surface. Keep measurement-only or preview-only concerns separate from
   authored content so they cannot silently become visible output.
3. Keep every intended visible item represented. At an unsupported boundary,
   preserve the source context and emit an explicit diagnostic or route the
   item to an authorized product-development decision. A missing object is not
   a successful approximation.
4. Use deterministic, locally available inputs supported by the Contract. Keep
   visible external resources out of the normal workbench unless the Contract
   explicitly accepts that form.

### Explicit native charts (Contract 1.3)

When a chart is needed, make its semantics explicit instead of drawing bars,
lines, or slices as ordinary HTML. Mark one measured outer container with
`data-pptx-chart` and put exactly one inert
`<script type="application/json" data-pptx-chart-spec>` inside it. The strict
JSON spec is the sole source of chart type, ordered categories, ordered series,
values, and closed presentation tokens; do not put a second spec in the
container or use OfficeCLI command syntax in Author HTML.

The case-sensitive `type` must be one of `column`, `bar`, `line`, `pie`, or
`doughnut`. Category charts accept 1–3 series and 1–12 categories. Pie and
doughnut charts accept one series, 2–6 categories, finite non-negative values,
and a positive total. Categories must be non-empty strings after trimming and
may repeat; series names must be unique after trimming; values must be finite
JSON numbers. Use only the semantic presentation tokens reported by
`capabilities --json`: title, legend `none`/`top`/`bottom`/`left`/`right`,
labels `none`/`value`/`percent`, Cartesian axis titles, the seven semantic
number formats, and optional six-digit `#RRGGBB` series colors. Omit a color to
record authored `auto`. `percent` labels and axes are type-specific; authored
`holeSize` is rejected and doughnut uses its fixed private default.

The outer container's measured box controls placement and size. A browser
preview may be included for authoring, but every descendant is excluded from
generic lowering and never becomes a second native object. Keep the container
visible, measurable, and non-zero-sized. Unknown fields, duplicate JSON keys,
non-finite constants, nested chart containers, unsupported combinations, and
chart fallback fail the Contract check.

### Explicit localized visual fallback (Contract 1.3)

When a complex local visual cannot be represented by the native surface, opt in
with exactly `data-pptx-rasterize="localized"` on its outer element. The
element is one atomic authored object: all descendants are captured into one
PNG and excluded from generic lowering. Use the ordinary trimmed HTML `id` for
identity; without one, the product records a deterministic source path.

The CSS border box is both capture geometry and PowerPoint picture geometry.
Keep shadows, filters, and other visual effects inside that box with authored
padding; paint that overflows the box blocks the build. Capture density is
fixed at 2 pixels per point and cannot be set by Author HTML. The result is a
native picture whose internal content is not editable and must not be described
as native semantics or editable text.

Only static HTML/CSS, inline SVG, and deterministic data-URI or permitted local
images are admitted. Scripts, runtime canvas, iframe/network resources,
audio/video, WebGL, animation, interaction-dependent states, nested or
overlapping regions, whole-slide regions, and regions containing another
atomic object are rejected. Unannotated unsupported content remains blocking;
the public dispositions are `native`, `rasterized`, `unsupported`, and
`unresolved` only.

### Native shape geometry

For a visible shape that needs a non-rectangular native PowerPoint preset, use
the exact, case-sensitive `data-pptx-shape-geometry` attribute. The supported
tokens are `rect`, `roundRect`, `ellipse`, `triangle`, `diamond`,
`parallelogram`, `chevron`, `hexagon`, `leftArrow`, `rightArrow`, `upArrow`,
`downArrow`, and `star5`. Unknown tokens and custom geometry are rejected by
the Contract; do not rely on arbitrary backend preset names. An unannotated
block remains a `rect`, a positive `border-radius` remains a `roundRect`, and
an approximately square `border-radius: 50%` block may be inferred as an
`ellipse` within the published Contract tolerance.

After authoring, inspect the workbench at enough scale to catch missing slides,
obvious overflow, unreadable text, missing images, unintended overlap, and
Contract-visible unsupported content. Then run `check --json`; fix the exact
diagnostics and check again. Use the first successful Build's Comparison
Images for Build-Driven Visual Discovery instead of delaying the first build
for speculative polish.

**Authoring completion criterion:** the separate `.author.html` is browsable,
contains all intended slides and visible objects, and the exact file passes the
installed Author Contract with no unresolved blocking diagnostics.
