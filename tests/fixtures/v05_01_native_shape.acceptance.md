# V0.5.1 native shape geometry acceptance

This fixture is the focused #25 public Author slice. It is checked through the
Contract, compiled through the public Author compiler, validated by OfficeCLI,
and read back independently from the generated PPTX.

Acceptance checklist:

- `data-pptx-shape-geometry` is the only public geometry annotation.
- The exact case-sensitive tokens `rect`, `roundRect`, `ellipse`, `triangle`,
  `diamond`, `parallelogram`, `chevron`, `hexagon`, `leftArrow`, `rightArrow`,
  `upArrow`, `downArrow`, and `star5` lower to native shapes.
- The unannotated square `border-radius:50%` object is inferred as a native
  `ellipse`; an annotation and a CSS inference are separate evidence paths.
- Shape bounds, solid fill, uniform solid outline, opacity, rotation, and text
  remain editable native properties.
- Unknown tokens, case variants, arbitrary preset values, custom paths, shape
  adjustments, and the public use of the private `data-shape-geometry` spelling
  fail closed before output creation.
- OfficeCLI `validate` and `view ... issues` run on the fresh output; readback
  reports each accepted geometry as a shape rather than a picture.
- Public capability data names only `data-pptx-shape-geometry`; the legacy
  `data-shape-geometry` alias remains an internal projection seam only.
