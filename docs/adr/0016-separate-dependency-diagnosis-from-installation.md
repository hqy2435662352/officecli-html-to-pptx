---
status: accepted
---

# Separate dependency diagnosis from installation

V0.2 product commands will never silently install, download, or upgrade
dependencies or rewrite environment configuration. The Python distribution
will declare its ordinary Python dependencies, while `doctor` will read-only
inspect external prerequisites such as OfficeCLI, Node.js, and Chromium and
return the required, discovered, and compatibility state in the versioned
Command Result Envelope. Every failed check will include an exact remediation
command and recheck instruction.

`check`, `build`, and `finalize` will fail explicitly when their prerequisites
are unavailable or incompatible rather than repairing the environment during an
operation. The skills-only Product Plugin will not bundle or manage the Core
Product or its runtimes. The Authoring Skill may explain a remediation and may
execute it only after explicit user authorization; a build request or failed
doctor result is not installation authorization.
