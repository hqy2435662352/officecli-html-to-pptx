---
status: accepted
---

# Treat officecli-html-to-pptx as an independent product from V0.2

Beginning with V0.2, `officecli-html-to-pptx` is an independent product rather
than a compatible renderer backend or release line of the original
`html-to-pptx`. This allows its Author Contract, OfficeCLI dependency, CLI,
versioning, and supported user workflow to evolve as one coherent promise
without carrying the original product's legacy-renderer compatibility surface.
The repository migration shape and long-term treatment of reused upstream code
remain separate decisions.
