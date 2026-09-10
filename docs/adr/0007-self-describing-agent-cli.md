---
status: accepted
---

# Make the CLI a self-describing Agent protocol

V0.2 will add a read-only `capabilities` command alongside `doctor`, `check`,
and `build`, and all four commands will support a versioned JSON result
envelope. Comprehensive help will explain command choice, supported scope,
examples, artifacts, failure semantics, and exit classes, while precise
capability data will be generated from the installed contract authorities
rather than copied into help or Skills. This lets agents operate normally
without inspecting compiler source or scraping prose output.
