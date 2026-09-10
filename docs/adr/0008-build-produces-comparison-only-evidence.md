---
status: accepted
---

# Build complete evidence but retain only per-slide comparisons

V0.2 `build` will produce the PPTX plus Contract, manifest, validation, issues,
result, visual-review, and complete per-slide HTML/PPTX comparison evidence.
The renderer may create separate HTML and PPTX screenshots temporarily, but it
will persist only one side-by-side Comparison Image per slide and will remove
the intermediate screenshots. A structurally successful build remains
`VISUAL_REVIEW_REQUIRED` until every comparison has been reviewed; this keeps
the evidence complete without storing three visual copies of every slide.
