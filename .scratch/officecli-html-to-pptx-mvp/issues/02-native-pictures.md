# 02 — Compile SVG data-URI images to native pictures

**What to build:** Extend the complete Author HTML compiler path so Algeria slide 1 emits each SVG data-URI product image as an independent editable PowerPoint picture instead of silently losing it or flattening the slide.

**Blocked by:** 01 — Compile one Author HTML slide to native shapes and text.

**Status:** complete

- [x] SVG data-URI sources enter the Measurement DTO and PPT Object IR without truncation or silent omission.
- [x] Each supported source image produces one independent PowerPoint picture object.
- [x] The output contains no whole-slide screenshot or other slide-level raster fallback.
- [x] Picture x, y, width, and height are within 1pt of the measured input geometry.
- [x] Supported `object-fit` behavior is preserved visually.
- [x] SVG is retained when supported by the installed OfficeCLI capability surface.
- [x] When direct SVG insertion is unavailable, a deterministic raster fallback is applied only to the affected picture object.
- [x] Raster fallback preserves the source image aspect ratio and measured picture box.
- [x] An undecodable image fails explicitly with slide and DOM-object context.
- [x] Algeria slide 1 contains all four expected product pictures.
- [x] The full-deck acceptance target is fixed at 18 picture objects.
- [x] OfficeCLI validation passes and the picture inventory is queryable through the public acceptance seam.
