---
status: accepted
---

# Declare text-transform unsupported until lowering carries it

`text-transform` was classified `rendered` while nothing lowered it: measured
runs keep the authored case, no Canonical Run key or run property carries the
transform, and OfficeCLI readback has no equivalent. A browser therefore showed
`uppercase` text that the Contract accepted and the PPTX silently did not
reproduce. The property is classified `unsupported` instead, so `check` blocks
it with source context (`tests/fixtures/unsupported_text_transform.html`) rather
than promising a surface the product does not have. Restoring it requires
lowering, readback and visual evidence first.
