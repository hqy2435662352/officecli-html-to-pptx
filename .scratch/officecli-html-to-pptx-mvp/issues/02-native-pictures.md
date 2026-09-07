# 02 — Compile SVG data-URI images to native pictures

**What to build:** Extend the complete Author HTML compiler path so Algeria slide 1 emits each SVG data-URI product image as an independent editable PowerPoint picture instead of silently losing it or flattening the slide.

**Blocked by:** 01 — Compile one Author HTML slide to native shapes and text.

**Status:** ready-for-agent

- [ ] SVG data-URI sources enter the Measurement DTO and PPT Object IR without truncation or silent omission.
- [ ] Each supported source image produces one independent PowerPoint picture object.
- [ ] The output contains no whole-slide screenshot or other slide-level raster fallback.
- [ ] Picture x, y, width, and height are within 1pt of the measured input geometry.
- [ ] Supported `object-fit` behavior is preserved visually.
- [ ] SVG is retained when supported by the installed OfficeCLI capability surface.
- [ ] When direct SVG insertion is unavailable, a deterministic raster fallback is applied only to the affected picture object.
- [ ] Raster fallback preserves the source image aspect ratio and measured picture box.
- [ ] An undecodable image fails explicitly with slide and DOM-object context.
- [ ] Algeria slide 1 contains all four expected product pictures.
- [ ] The full-deck acceptance target is fixed at 18 picture objects.
- [ ] OfficeCLI validation passes and the picture inventory is queryable through the public acceptance seam.
