---
status: accepted
---

# Use Agent-managed non-overwriting artifact pairs

Every V0.2 build will create one non-overwriting Artifact Pair: a requested
`name.pptx` and its fixed same-directory companion `name.evidence/`. The
evidence path is derived rather than separately configurable. If either target
already exists, `build` will fail before writing and will not offer `--force`,
directory clearing, or replacement behavior. Delivery will be transactional so
a failed build cannot leave a half-published pair.

The Evidence Bundle will bind the pair using a unique build identifier, PPTX
content hash, Author HTML hash, and Product, Contract, OfficeCLI, and Chromium
versions. `finalize` will accept only the exact matching pair. Each Revision
Loop will preserve the prior attempt and create a newly suffixed pair such as
`name-r01.pptx` plus `name-r01.evidence/`.

These mechanics are Agent-facing safeguards, not a user-operated file protocol.
The user states the intended deliverable name or location at a product level;
the Authoring Skill and Agent choose command arguments, allocate revision
suffixes, interpret structured collision diagnostics, and retry without asking
the user to manage build directories. A location change that alters the user's
requested delivery target still requires confirmation.
