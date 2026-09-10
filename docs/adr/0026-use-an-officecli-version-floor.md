---
status: accepted
---

# Use an OfficeCLI version floor and keep the browser pair pinned

V0.2 accepts OfficeCLI `>=1.0.147` because the Experimental Pilot was exercised
successfully with both the minimum and a newer installed version. The
Rendering Compatibility Pair now means the pinned Playwright version and its
managed Chromium revision; OfficeCLI is reported separately as the Minimum
Supported Version, and every build records the actual discovered version. This
supersedes ADR-0017's exact OfficeCLI pin without relaxing the browser pair.
