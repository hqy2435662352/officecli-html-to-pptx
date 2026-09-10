---
status: accepted
---

# Supersede the old authoring Skill

V0.2 deprecates `write-a-html-ppt` instead of maintaining a routing split
between old and new workflows. `build-a-pptx-with-html` is the sole supported
Authoring Skill for requirements-led, reference-led, and Candidate-HTML-led
creation of editable PPTX deliverables with the independent product.

The new Skill will contain the Author HTML guidance it needs and will never
call, compose with, or fall back to `write-a-html-ppt`. The deprecated Skill is
not a Product Plugin dependency or an alternate route around Contract checks.
This decision defines product ownership and support status; removal or
replacement of an already installed external Skill is a separate migration
action and is not performed merely by adopting this ADR.
