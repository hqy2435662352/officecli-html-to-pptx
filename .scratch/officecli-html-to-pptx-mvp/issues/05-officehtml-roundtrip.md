# 05 — Rehydrate OfficeCLI HTML into a structurally stable PPTX

**What to build:** Add the explicit `officehtml` input profile and prove object-level reversibility by projecting the generated Algeria PPTX to OfficeCLI HTML, compiling that projection into a second PPTX, and comparing normalized object manifests.

**Blocked by:** 04 — Compile the complete eight-slide Algeria deck.

**Status:** complete

- [x] The public compiler seam accepts the explicit `officehtml` profile.
- [x] The profile parses the slide DOM emitted by OfficeCLI 1.0.147.
- [x] Shape paths rehydrate as native shapes or text-bearing shapes.
- [x] Picture paths rehydrate as native picture objects.
- [x] Table paths rehydrate as native PowerPoint tables.
- [x] Cell paths associate every OfficeHTML cell with the correct table row and column.
- [x] Viewer sidebars, toolbars, thumbnails, counters, scripts, and navigation elements never enter the PPT Object IR.
- [x] Slide descendants without `data-path` that represent master/layout projections do not enter the slide-owned manifest.
- [x] Point-based OfficeHTML geometry is normalized correctly and is not scaled as if it were a 1920px Author HTML canvas.
- [x] PPTX A can be projected to OfficeHTML and compiled into PPTX B through the public seam.
- [x] PPTX A and PPTX B normalized manifests have equivalent supported object-kind counts.
- [x] Text and table-cell text are identical after documented non-breaking-space normalization.
- [x] Picture count, table count, table dimensions, and cell count are equivalent.
- [x] Object geometry differs by no more than 1pt and table row/column dimensions satisfy the narrower spec tolerance.
- [x] Supported fills, outlines, fonts, and alignments are equivalent.
- [x] `data-path` is documented and tested as source identity only, not as an automatic write-back promise.
- [x] Both PPTX outputs pass OfficeCLI validation.
