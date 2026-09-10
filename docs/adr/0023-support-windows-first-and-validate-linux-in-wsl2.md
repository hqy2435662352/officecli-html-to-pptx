---
status: accepted
---

# Support Windows first and validate Linux in WSL2

Windows will be the only formally supported V0.2 operating-system environment.
Its `doctor`, build, validation, path, UTF-8 subprocess, and visual-evidence
behavior will be accepted against the pinned Rendering Compatibility Pair.
The implementation should avoid gratuitous Windows-only coupling, but neither
the Capability Manifest nor release documentation will claim macOS or Linux
support from theoretical portability alone.

Linux validation is deferred to a later WSL2 acceptance run on the current
machine. Until that end-to-end track passes and a later product decision expands
the support matrix, WSL2 and other Linux executions are experimental. WSL2
evidence will establish only the tested WSL2 environment and will not
automatically certify arbitrary Linux distributions or native installations.
