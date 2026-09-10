---
status: accepted
---

# Ship a CLI core with a skills-only Codex Plugin

V0.2 will be a two-layer product: an independently usable Python package, API,
and CLI will own Contract checking, compilation, diagnostics, validation, and
evidence, while a same-repository Codex Plugin will provide the Agent-facing
New Deck Creation workflow. The Plugin will initially contain an Authoring
Skill only, with no MCP server or custom UI, because existing local tools are
sufficient and the compiler must remain the single implementation and contract
authority.
