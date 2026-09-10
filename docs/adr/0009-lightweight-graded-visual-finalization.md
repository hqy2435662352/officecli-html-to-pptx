---
status: accepted
---

# Keep visual finalization lightweight and graded

V0.2 will finalize a build by validating only the Visual Review schema, slide
coverage, and association with the originating Evidence Bundle; finalization
will not recompile, rerender, or run pixel analysis. Material visual deviations
trigger a Revision Loop with a new build and evidence set, while detail
deviations are recorded and allow the workflow to finish with findings. This
keeps the acceptance record durable without turning finalization into a second
compiler or an open-ended polish loop.
