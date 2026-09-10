---
status: accepted
---

# Combine input roles around one primary starting artifact

The `build-a-pptx-with-html` Skill will accept existing HTML, visual references,
and content briefs separately or together. When usable HTML is supplied, it is
the Candidate HTML and primary starting artifact; references and briefs may
add appearance, content, or composition constraints. When no HTML exists, the
Skill creates a new `.author.html` workbench from the supplied references,
brief, or both.

Every input combination must converge on Author HTML before Core Build.
User-supplied HTML must run through the current Author Contract; the Skill may
remediate or reconstruct rejected input but may never assume compatibility or
bypass the checker. Existing-PPTX editing remains outside the Skill and V0.2
supported product surface.
