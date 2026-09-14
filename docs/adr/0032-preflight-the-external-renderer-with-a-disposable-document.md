---
status: accepted
---

# Preflight the external renderer with a disposable document

`build` compiles the PPTX and only then fails at the evidence stage, because
OfficeCLI cannot find a headless browser for `officecli view <pptx> screenshot
--render html`. The whole build is discarded after the most expensive part is
done. Three behaviours made it undiagnosable rather than merely late: OfficeCLI
exits `0` while writing no file, so the process status carries no information;
the per-document resident caches the failed browser discovery with the
environment of the first caller, so a user who installs a browser and retries
still fails; and the diagnostic never named the requirement.

The renderer dependency therefore becomes a precondition that is probed before
compilation. The probe performs one real screenshot of a throwaway document
through the same render path the Evidence Bundle will use, because the only
honest question is whether the thing `build` actually needs can be produced —
OfficeCLI's own discovery rules are not re-implemented, and the browser
requirement is not inferred from a version string.

The probe document is disposable and is closed in `finally`. That is not
housekeeping: it is what makes the resident cache stop mattering. A poisoned
resident is only ever a resident holding a document nobody needs again, so a
corrected environment recovers on the next attempt without a manual cleanup.

A failed probe is then classified by looking for a browser candidate on the host
— on `PATH`, at the Playwright-managed Chromium, and at the platform's
conventional install locations. Nothing found means *no browser at all*;
something found means *browser present but OfficeCLI cannot see it*, which is
the common case and has a different fix. That lookup only chooses the message,
never the verdict: the probe's own exit state decides pass or fail, so the
diagnostic cannot pass a host the renderer will fail on.

`doctor` does not gain this probe. It reports host health and remediation for a
missing prerequisite, and the browser condition is already documented for
operators; the probe is document-independent but it is on the build path because
that is where its cost is affordable and where its failure has a build to block.
