---
status: accepted
---

# Admit Linux as a validated build platform

Windows and Linux are both supported build platforms. The set lives in
`runtime.SUPPORTED_PLATFORMS` and is the only authority for platform policy; the
runtime diagnosis is a membership test against it. This supersedes ADR-0023
("Support Windows first and validate Linux in WSL2"), whose deferred WSL2 track
has now run and passed.

Membership is earned, not assumed. A platform joins the set by completing a
**Platform Acceptance Track**: the declared Rendering Compatibility Pair must be
discoverable on that system, and one real
`doctor` -> `check` -> `build` -> Visual Review -> `finalize` run must produce a
complete Artifact Pair with a derived outcome. Portability by dependency, a
passing unit suite, or a single successful command is not sufficient evidence.

Linux was admitted by the WSL2 track on Ubuntu 24.04. That run found the pair
already satisfied — Python 3.12, Node.js 22, OfficeCLI 1.0.149 from its official
`linux-x64` release, Playwright 1.62.0 and Chromium revision 1234 — with
`unsupported_platform` as the only blocking diagnostic. The track then built a
deterministic probe deck and a 214 MB, 27-slide deck end to end. A cross-platform
comparison of the larger deck found equal object inventories on both sides
(502 objects, equal kind counts, no source-object mismatch), an identical PPTX
part list, and all 45 media pixel-identical. The residual differences were the
PNG encoder, the theme East-Asian typeface, relationship GUIDs, and host text
stack behaviour.

A track certifies only the environment it exercised. WSL2 on Ubuntu 24.04 is
accepted; other distributions and native installations are not, and will be
recorded here only when they have their own run. macOS is not claimed.

`capabilities --json` reports two separate facts, because one is not derivable
from the other: `platform` is where the command is running, and
`supported_platforms` is what this build supports. The unsupported-platform
diagnostic names every supported platform rather than the first one.

Three host conditions are part of the Linux acceptance and are documented for
operators rather than enforced by `doctor`. The product launches Chromium
without `--no-sandbox`, so it must not run as root. OfficeCLI's PPTX screenshot
stage discovers a headless browser through a Playwright-capable `python3` on
`PATH`, so the environment owning the pinned Chromium must be active or the
build fails at its evidence stage. The build host must have the font families
and weight faces the Author HTML declares, because text geometry is measured on
the build host; a substitution there yields a visibly mis-measured deck while
`doctor` still reports `PASS`.

That last condition is the reason this ADR does not treat Linux support as
complete. Font availability is the largest remaining fidelity risk on any
platform and is not yet diagnosed by the product; it belongs with the
font-declaration work rather than with the platform set, and is tracked
separately. A preflight probe for OfficeCLI's headless-browser discovery, and
reporting upstream that OfficeCLI exits successfully while writing no screenshot
and caches that failure in its per-document resident process, are likewise
separate work.

Widening the set did not relax any Contract, capability, evidence or outcome
rule, and does not change the release gate: the gate still does not require a
platform matrix, and a fresh run of every track is not part of every release.
