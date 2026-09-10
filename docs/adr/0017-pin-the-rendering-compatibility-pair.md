---
status: superseded by ADR-0026
---

# Pin the rendering compatibility pair for formal builds

V0.2 formal builds will accept only the exact rendering pair validated for the
release: OfficeCLI `1.0.147` and the Chromium revision belonging to the pinned
Playwright version. They will not use an arbitrary system Chrome installation
or assume that an unverified newer OfficeCLI or Chromium version is compatible.
`doctor` will report the required version, discovered version, and executable
source for each component, and ordinary `build` will fail explicitly on a
mismatch.

Other renderer versions may be exercised only through an explicitly authorized
Development Path. The resulting Experimental Build must record every actual
runtime version and is not evidence of formal support. A later Product Version
may change or expand the supported rendering pair after acceptance testing.
Python and Node.js runtimes may use separately documented tested ranges because
they do not directly define the accepted rendering pair.
