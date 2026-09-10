---
status: accepted
---

# Expose a task-oriented Author CLI without profiles

V0.2 will expose `officecli-html-to-pptx doctor`, `check`, and `build`, with
`build` as the only formally supported conversion command. The public CLI and
Authoring Skill will not expose a profile selector: Author HTML to a new
editable PPTX is the product contract, while OfficeHTML Import remains an
experimental internal capability. Because agents operating through the Skill
will be the dominant CLI callers, command help and structured results must be
sufficient for normal operation without source-code exploration.
