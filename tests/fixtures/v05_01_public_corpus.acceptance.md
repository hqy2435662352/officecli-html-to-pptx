# V0.5.1 public acceptance corpus

This tracked Author HTML is the four-slide public corpus for ticket #26. It is
deliberately separate from `acceptance/v0.4.2/`, which remains the hidden
projection regression corpus and is not part of this release gate.

| Slide | Proof target | Required independent evidence |
| --- | --- | --- |
| 1 | Latin/CJK runs, authored paragraph boundaries, `<br>`, empty paragraphs, direction and line-height | normalized paragraph order/cardinality, hard-break offsets, run matrix, CJK readback and Gate 3 |
| 2 | One native table with combined, vertical and horizontal rectangular merges | one table object, logical dimensions, normalized `(anchorRow, anchorColumn, rowSpan, columnSpan)` topology, canonical borders and Gate 3 |
| 3 | Public `data-pptx-shape-geometry` allowlist, inferred ellipse, rotation and text-bearing shape | native geometry readback, no picture substitute, object counts and Gate 3 |
| 4 | Integrated business page combining text, merged table and native geometry | independent readback, OfficeCLI validation/issues, diagnostics/material delta and Gate 3 |

The public workflow is intentionally unchanged:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> Gate 3 visual review -> finalize
```

Acceptance is complete only when `unsupported`, `unresolved`, and
`material_delta` are all zero, every comparison image has a real review entry,
and the derived outcome is `PASS` or `PASS_WITH_FINDINGS`. Charts and the V0.6
general localized fallback taxonomy are not represented here.
