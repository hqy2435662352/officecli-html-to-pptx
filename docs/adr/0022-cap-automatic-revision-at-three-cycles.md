---
status: accepted
---

# Cap automatic revision at three cycles

The Authoring Skill may perform at most three automatic Revision Loop cycles
after the initial build. Each cycle consists of an Author HTML repair, a new
Artifact Pair, and a new Visual Review. The initial build does not consume the
budget, and infrastructure retries that do not create a new Author HTML
revision are not counted.

If major findings remain after the third automatic revision, the Skill will
stop before starting a fourth, preserve every Artifact Pair and finding, give
the user a concise account of progress and remaining blockers, and ask whether
to continue. User confirmation may authorize another bounded set of up to three
automatic revision cycles. This balances high-quality delivery with predictable
time and compute use.
