---
status: accepted
---

# Raise the OfficeCLI floor for Contract 1.1

V0.5.1 and Author Contract 1.1 require OfficeCLI `>=1.0.151`, whose native
line-break and table-merge surfaces are part of the release acceptance. A
lower discovered version fails before measurement or output creation, while
the Capability Manifest and every Evidence Bundle continue to record the
actual runtime version. This supersedes ADR-0026's `>=1.0.147` floor for
Contract 1.1 without changing the historical V0.2 requirement.
