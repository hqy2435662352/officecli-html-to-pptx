# 04 — Compile the complete eight-slide Algeria deck

**What to build:** Compile the full Algeria Author HTML into an OfficeCLI-native eight-slide PPTX that exercises every MVP object type and can be structurally and visually compared with the golden references.

**Blocked by:** 02 — Compile SVG data-URI images to native pictures; 03 — Compile one HTML table to a native PowerPoint table.

**Status:** ready-for-agent

- [ ] The generated presentation contains 8 slides in source order.
- [ ] It contains 9 native PowerPoint tables.
- [ ] Table distribution is slide 2: four; slides 3–7: one each; slides 1 and 8: none.
- [ ] Table dimensions are 5×8, 8×8, 5×8, 5×8, 15×4, 13×5, 13×5, 13×5, and 9×5 in slide order.
- [ ] The tables total 86 rows and 484 cells.
- [ ] It contains all 18 Author HTML pictures as independent picture objects.
- [ ] It contains no whole-slide picture.
- [ ] Visible slide text matches the Author HTML after the documented display-only whitespace normalization.
- [ ] Unicode characters, including `Φ` and `×`, are preserved.
- [ ] Every supported IR object is rendered exactly once.
- [ ] Stable object names are deterministic and unique.
- [ ] Object and table geometry satisfies the spec tolerances.
- [ ] Every unsupported visible source node produces a diagnostic; none is silently skipped.
- [ ] OfficeCLI validation passes.
- [ ] No schema, off-slide, missing-picture, or table-structure issue is reported.
- [ ] No new overflow exists outside the explicit reference allowlist.
- [ ] Side-by-side Author HTML/PPTX screenshots are generated and reviewed for all eight slides.
- [ ] The output does not introduce theme shadows or other effects absent from Author HTML.
