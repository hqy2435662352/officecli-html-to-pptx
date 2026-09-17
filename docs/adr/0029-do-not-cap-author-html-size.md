---
status: accepted
---

# Do not cap Author HTML by file size

`measurement.extract_measurements` rejected any input over a hardcoded 10 MB
before Chromium was ever launched. Author HTML inlines pictures as
`data:image/...` URIs, so a real business deck is routinely tens or hundreds of
megabytes: a 204.4 MB / 27-slide deck with 34 tables and 45 inlined pictures was
refused outright while the pipeline itself handles it. The cap had no test, no
documentation and no recorded rationale, and it never measured what it was
guarding against. It is removed rather than raised: the browser navigation
timeout (`PLAYWRIGHT_TIMEOUT_MS`) still bounds a pathological input, and a deck
that really cannot be measured fails with a real diagnostic instead of a
pre-emptive size verdict.
