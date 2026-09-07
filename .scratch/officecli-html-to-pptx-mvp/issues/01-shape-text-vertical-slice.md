# 01 — Compile one Author HTML slide to native shapes and text

**What to build:** Compile Algeria slide 8 from Author HTML through Chromium measurement, the smallest required PPT Object IR, and an atomic OfficeCLI render into a one-slide widescreen PPTX containing editable native shapes and text. This is the first complete public compiler seam and must not route through the legacy renderer.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The OfficeCLI compiler entry accepts Author HTML, the `author` profile, and an output destination.
- [ ] Algeria slide 8 produces a one-slide standard 16:9 PPTX from a blank presentation.
- [ ] Visible text is emitted as native PowerPoint text.
- [ ] Card-like elements are emitted as native PowerPoint shapes.
- [ ] Rectangle, rounded rectangle, solid/no fill, uniform outline, text margins, alignment, and basic text formatting are supported for this slice.
- [ ] Geometry is normalized from the actual measured slide rectangle and does not depend on a hard-coded 1920px conversion constant.
- [ ] No whole-slide picture is present.
- [ ] Every emitted object has a unique deterministic stable name.
- [ ] The render uses an atomic OfficeCLI batch and stops on the first failure.
- [ ] Rendering first targets a temporary PPTX and only delivers the requested output after validation succeeds.
- [ ] OfficeCLI validation passes.
- [ ] Failure diagnostics identify the source slide and DOM object.
- [ ] The end-to-end test calls only the public compiler seam and asserts on OfficeCLI-observable PPTX behavior.

