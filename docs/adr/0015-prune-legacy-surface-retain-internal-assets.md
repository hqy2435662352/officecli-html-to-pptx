---
status: accepted
---

# Prune the legacy surface while retaining internal technical assets

V0.2 will remove the inherited `python-pptx` Legacy Renderer and its
compatibility-facing entry points; preserved Git history is sufficient for
recovery. The old public `compare` and Algeria acceptance commands will also
be removed from the Product Command.

Chromium measurement and the PPT Object IR remain part of the supported Author
Compiler. OfficeHTML Import implementation and focused tests may remain only
in a clearly marked internal experimental area: they will not be exported from
the package's public API, exposed through the Product Command, reported by the
Capability Manifest as supported, or invoked by the Authoring Skill. The
Algeria deck and its acceptance workflow may remain as internal Release
Regression Assets, not as public commands, examples, APIs, or capability
claims.
