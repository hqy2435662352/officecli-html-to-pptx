---
status: accepted
---

# Use an independent repository while preserving Git history

`officecli-html-to-pptx` V0.2 will live in a new independent GitHub repository
named `officecli-html-to-pptx`. The repository will preserve the existing Git
commit ancestry and MIT provenance but will not remain in GitHub's fork
network; `Design-Arena/html-to-pptx` will be retained only as an optional
upstream source for selectively adopted changes. This separates product
governance, issues, releases, and compatibility promises without discarding
authorship or the reasons behind the inherited implementation.
