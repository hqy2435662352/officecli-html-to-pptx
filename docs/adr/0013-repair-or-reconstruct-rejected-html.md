---
status: accepted
---

# Repair or reconstruct rejected Candidate HTML without bypassing Contract

All user-supplied HTML must pass the current Author Contract before build. The
Authoring Skill will use Focused Repair when local changes can preserve the
page composition, and Reconstruction when compliance would otherwise require
material reauthoring; it will not use diagnostic counts or similarity scores
to choose. Rejected input remains unchanged, remediation is written to a
separate `.author.html` workbench, and the result must pass Contract again
before entering the supported build path.
