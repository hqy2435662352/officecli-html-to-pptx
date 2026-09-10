---
status: accepted
---

# Use one product version while versioning contracts independently

The Python distribution, Codex Plugin, and GitHub release will share one
`officecli-html-to-pptx` SemVer, with the Authoring Skill shipped as part of the
Plugin; V0.2 is therefore product version `0.2.0`. Author Contract version and
OfficeCLI Minimum Supported Version remain independent because they describe the
input language and an external dependency rather than a product release. In
the independent repository, inherited tags will use the
`upstream/html-to-pptx/...` namespace so the product can use standard `v0.1.0`,
`v0.2.0`, and later release tags without losing provenance.
