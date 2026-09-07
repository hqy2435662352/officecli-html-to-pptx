# 06 — Publish Reversible OfficeHTML Contract v1 and the MVP acceptance gate

**What to build:** Publish a staged, version-pinned contract for AI authors and compiler maintainers, plus one repeatable Algeria acceptance entry that compiles, validates, inventories, round-trips, and renders the golden case without depending on `python-pptx` output inspection.

**Blocked by:** 05 — Rehydrate OfficeCLI HTML into a structurally stable PPTX.

**Status:** ready-for-agent

- [ ] The contract separates Authoring Runtime, Chromium Measurement, PPT Object Lowering, OfficeCLI Rendering, and Round-trip Validation rules.
- [ ] The contract records OfficeCLI 1.0.147 as the compatibility baseline.
- [ ] Supported object kinds and CSS properties are explicit.
- [ ] Merged cells, charts, masters/layout reconstruction, and other non-goals are explicit.
- [ ] The contract checker distinguishes `author` and `officehtml` profiles.
- [ ] Unsupported visible content is a blocking failure rather than a silent warning.
- [ ] Preview-only Author HTML DOM and OfficeHTML viewer chrome have explicit ignore rules.
- [ ] Rules caused only by the legacy renderer are not presented as limitations of the OfficeCLI profile.
- [ ] One Algeria acceptance entry runs compilation, OfficeCLI validation, normalized structure-manifest comparison, round-trip manifest comparison, and screenshot generation.
- [ ] The acceptance report distinguishes `PASS`, known baseline difference, unsupported input, and regression.
- [ ] Known overflow findings are keyed by slide, stable object identity, and subtype rather than only by total count.
- [ ] Existing legacy-renderer tests continue to pass.
- [ ] OfficeCLI MVP output structure is asserted through OfficeCLI rather than `python-pptx` internals.
- [ ] The HTML authoring skill can reference the new contract without duplicating OfficeCLI capability rules.
