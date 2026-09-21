---
status: accepted
---

# Preserve authored text boundaries instead of lowering visual lines

Contract 1.1 distinguishes authored paragraph boundaries, intra-paragraph hard
breaks, and automatic browser wrapping. A paragraph boundary lowers to a native
PowerPoint paragraph, `<br>` lowers to a native line break inside its paragraph,
and `visualLines` is retained only for measurement, evidence, and visual review;
it never creates native paragraphs or hard breaks. Leading, intervening,
consecutive, and trailing empty paragraphs preserve their exact order and
cardinality. The trailing rule is fixed rather than runtime-dependent because
OfficeCLI 1.0.151 preserved one and two trailing empty paragraphs in all three
fresh public create/readback repetitions for each fixture.
