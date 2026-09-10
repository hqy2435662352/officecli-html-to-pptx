---
status: accepted
---

# Use an Agent-authored review record with derived outcomes

`build` will seed `visual-review.json` with its schema version, build
identifier, PPTX and Author HTML hashes, and a complete inventory of slide
numbers plus Comparison Image paths and hashes. Its initial state is pending.
The visual reviewer must mark every slide reviewed and record zero or more
findings containing only `major` or `minor` severity, a short category, visible
location, and factual description. Every major finding must also include an
actionable revision instruction.

The reviewer does not authoritatively set the build outcome. `finalize` will
validate schema, complete slide coverage, immutable comparison hashes, and
association with the exact Artifact Pair, then derive `PASS` when no finding
exists, `PASS_WITH_FINDINGS` when only minor findings exist, or
`REVISION_REQUIRED` when any major finding exists. The Skill and Agents manage
the JSON record; the user is not asked to edit it.

The Authoring Skill will keep visual judgment independent from the authoring
pass and, when independent Subagent review is available, delegate the complete
Comparison Image set. This is an independence invariant rather than a required
prompt sentence or a Subagent protocol.
