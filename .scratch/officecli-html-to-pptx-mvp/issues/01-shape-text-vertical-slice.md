# 01 — Compile one Author HTML slide to native shapes and text

**What to build:** Compile Algeria slide 8 from Author HTML through Chromium measurement, the smallest required PPT Object IR, and an atomic OfficeCLI render into a one-slide widescreen PPTX containing editable native shapes and text. This is the first complete public compiler seam and must not route through the legacy renderer.

**Blocked by:** None — can start immediately.

**Status:** complete

- [x] The OfficeCLI compiler entry accepts Author HTML, the `author` profile, and an output destination.
- [x] Algeria slide 8 produces a one-slide standard 16:9 PPTX from a blank presentation.
- [x] Visible text is emitted as native PowerPoint text.
- [x] Card-like elements are emitted as native PowerPoint shapes.
- [x] Rectangle, rounded rectangle, solid/no fill, uniform outline, text margins, alignment, and basic text formatting are supported for this slice.
- [x] Geometry is normalized from the actual measured slide rectangle and does not depend on a hard-coded 1920px conversion constant.
- [x] No whole-slide picture is present.
- [x] Every emitted object has a unique deterministic stable name.
- [x] The render uses an atomic OfficeCLI batch and stops on the first failure.
- [x] Rendering first targets a temporary PPTX and only delivers the requested output after validation succeeds.
- [x] OfficeCLI validation passes.
- [x] Failure diagnostics identify the source slide and DOM object.
- [x] The end-to-end test calls only the public compiler seam and asserts on OfficeCLI-observable PPTX behavior.
