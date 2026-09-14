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

A track certifies only the environment it exercised. The gate keys are
`platform.system()` values and are therefore coarse — the single key `"Linux"`
matches every distribution — so the accepted environment is declared separately
and published beside the key:

- `capabilities --json` publishes `validated_platform_scope` with `enforced`,
  `accepted` (keyed by platform) and `not_implied`.
- The `doctor` snapshot publishes the same boundary per host as
  `platform.validated_scope` (the accepted environment for the discovered key,
  `null` when the key is not accepted), `platform.scope_enforced`, and
  `platform.not_implied`.

`enforced` is **false**, and that is the point rather than an oversight. The
platform gate matches an operating-system family and nothing else: it does not
inspect the distribution, the virtualisation, the CPU architecture, the user or
the fonts. A `PASS` therefore means the Rendering Compatibility Pair is
discoverable on this host — not that the host was acceptance-tested. Publishing
the scope without the `enforced` flag would let `PASS` read as a certification
of an environment the list below explicitly disclaims. Nothing verifies the
scope yet; ADR-0023's original caution that a track certifies only what it
exercised still holds, and closing the gap between "supported" and "validated"
is follow-up work rather than something this decision claims to have done.

```text
Accepted:
- Windows 10 or 11, x86_64, normal user account, declared fonts installed
- WSL2 on Ubuntu 24.04, x86_64, non-root user, Chromium-owning environment
  active, declared fonts installed

Not implied:
- other Linux distributions
- native (non-WSL2) Linux installations
- container images
- other CPU architectures
- macOS
```

Each of those needs its own Platform Acceptance Track, and will be added to the
accepted list only when it has one.

`capabilities --json` reports two separate facts, because one is not derivable
from the other: `platform` is where the command is running, and
`supported_platforms` is what this build supports. The unsupported-platform
diagnostic names every supported platform rather than the first one.

`capabilities.data.platform` is a **redefinition, not an addition**. It used to
report the single platform the build supported; it now reports where the command
is running, and the supported set moved to `supported_platforms`. The field keeps
its JSON type, so no consumer breaks structurally, but a consumer that read
`platform` as the support claim now reads the host. Any such consumer should
switch to `supported_platforms` and consult `validated_platform_scope` for the
evidence boundary. This is why the scope carries `enforced` rather than relying
on prose: the split only helps a caller that can tell the two questions apart.

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
