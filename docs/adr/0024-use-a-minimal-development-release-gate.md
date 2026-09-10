---
status: accepted
---

# Use a minimal development release gate

V0.2 will use a small release gate so development remains focused on tool
capability. The gate consists of relevant tests plus the existing regression
suite; one representative Author HTML run through `doctor`, `check`, `build`,
OfficeCLI validation, Visual Review, and `finalize`; confirmation that the PPTX
opens with editable supported objects and a complete Evidence Bundle; and
successful `compileall` and `git diff --check` checks.

The gate will not require a clean-install matrix, separate end-to-end runs for
every Authoring Skill input role, a full Algeria replay for every release, or
WSL2 validation. Algeria remains an internal regression asset available when a
capability change warrants it, and each capability may receive proportional
targeted real-PPTX evidence without creating a larger release framework.
