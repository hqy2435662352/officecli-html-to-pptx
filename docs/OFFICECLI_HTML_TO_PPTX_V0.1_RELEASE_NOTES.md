# officecli-html-to-pptx v0.1

`officecli-html-to-pptx` is this repository's Contract-governed compiler path
for producing editable PowerPoint files through OfficeCLI. This release name
does not refer to OfficeCLI itself. The compiler remains pinned to OfficeCLI
`1.0.147` as its execution, validation, and projection baseline.

The Python package version remains `0.3.0`. The independent capability line is
identified by the Git tag `officecli-html-to-pptx-v0.1.0`, avoiding collision
with the repository's existing general-package tags.

## Released workflows

### OfficeCLI-exported OfficeHTML to a new PPTX

The explicit `officehtml` profile now handles more of the fixed-coordinate HTML
that `officecli view <pptx> html` emits:

- data-URI pictures may come from either `<img src>` or an owned picture's CSS
  `background-image: url(...)` projection;
- inline CSS declarations preserve semicolons inside data URIs and quoted or
  functional values;
- the HTML parser retains very large embedded picture sources;
- SVG pictures receive an object-level PNG fallback when direct SVG handling is
  unsafe, without flattening the slide;
- PowerPoint text ranges use OfficeCLI's UTF-16 addressing and exclude line
  break characters;
- large OfficeCLI command arrays are submitted in 32 MiB chunks; and
- cover-style picture geometry is emitted as native picture crop properties.

This route creates a new PPTX from the supported OfficeHTML projection. It is
not an in-place edit protocol and does not reconstruct masters, layouts, themes,
groups, connectors, merged cells, or other object kinds outside Contract v1.

### Contract Author HTML to a new editable deck

The explicit `author` profile now treats Chromium's measured visual layout as
the source of truth more consistently:

- actual browser soft-wrap lines are preserved as editable PowerPoint
  paragraphs;
- standalone text boxes no longer reapply CSS block margins already reflected
  in their measured bounds, while table-cell paragraph spacing is retained;
- content-specific width expansion and broad single-line font shrinking have
  been removed; and
- the narrow `fontScale=95` compatibility adjustment is applied only when
  Chromium actually produced multiple visual lines.

The result remains a set of independent native text boxes, shapes, pictures,
and tables. It is not a screenshot conversion and does not claim browser-level
support for arbitrary CSS, animation, filters, or content outside Contract v1.

## Acceptance evidence

The OfficeHTML reverse improvements were accepted before release against two
real decks using OfficeCLI `1.0.147`:

- both generated PPTX files passed `officecli validate`;
- all 45 slide screenshots were inspected (33 plus 12); and
- the known unsupported-object and text-overflow baselines did not regress.

The Author HTML improvements were accepted against `review.html` as a complete
25-slide deck containing 462 native objects: 303 text boxes, 88 shapes, 41
pictures, and 30 native tables. The reported final artifact passed
`officecli validate`, had zero `view issues`, preserved the intended wrapped
and single-line capacity labels, and had screenshots generated and checked for
all 25 slides.

These real-deck acceptances are recorded results supplied for this release; the
release-organizing commit does not rerun them. Repository regression tests cover
the public `compile_officecli(...)` seam, Contract classification, CSS picture
sources, large embedded sources, SVG fallback, UTF-16/newline ranges, batch
chunking, Chromium soft wraps, standalone margins, and `<wbr>` table text.

## Entry points and limits

- Contract: [`OFFICEHTML_CONTRACT_V1.md`](OFFICEHTML_CONTRACT_V1.md)
- Agent workflow: [`OFFICECLI_HTML_TO_PPTX_AGENT_GUIDE.md`](OFFICECLI_HTML_TO_PPTX_AGENT_GUIDE.md)
- Public API: `compile_officecli(input_html, profile, output_pptx)`
- Profiles: exactly `author` or `officehtml`

Unsupported visible content remains a blocking diagnostic. Consumers must not
silently omit it, simulate a native table with cell-shaped rectangles, or
replace an unsupported slide with a full-slide screenshot.
