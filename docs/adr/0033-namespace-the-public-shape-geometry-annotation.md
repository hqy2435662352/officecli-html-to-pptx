---
status: accepted
---

# Namespace the public shape geometry annotation

Contract 1.1 will expose `data-pptx-shape-geometry` as the only public Author
HTML annotation for selecting an allowlisted native PowerPoint preset. The
existing projection seam may continue to accept `data-shape-geometry` as a
private legacy alias, but the public Contract, Capability Manifest, fixtures,
and Authoring Skill will not document that spelling or introduce a general
`data-pptx-kind` protocol. This keeps the first semantic annotation narrow and
leaves chart and fallback protocols to the releases that actually need them.
