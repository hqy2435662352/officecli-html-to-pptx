---
status: accepted
---

# Hard-retire the old Skill without a redirect

V0.2 will stop publishing and maintaining `write-a-html-ppt` and will remove it
from maintained Skill directories and installable catalogs. It will not retain
a same-name deprecation stub, alias, or forwarding Skill because any such
artifact would remain triggerable and compete with `build-a-pptx-with-html`.

Git history and release migration notes will preserve the old name, its
replacement, behavioral differences, and the end of support for the original
Design-Arena conversion path. Product Plugin setup may detect an independently
installed copy of the old Skill and report a conflict with an exact removal
instruction, but it must not silently modify or delete the user's installation.
Actually removing that installation is a separately authorized migration
action.
