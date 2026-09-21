# V0.5.2 public acceptance corpus

This tracked four-slide Author corpus is the public integration fixture for
GitHub issue #32. It is intentionally limited to the existing five-command
workflow and contains no local paths, private source references, or generated
PPTX/evidence.

| Slide | Coverage | Native chart expectations |
| --- | --- | --- |
| 1 | Categorical comparison | One column and one bar chart; two ordered series each |
| 2 | Trend | One multi-series line chart with axis titles and a semantic number format |
| 3 | Part to whole | One pie and one doughnut chart; percent/value labels and fixed doughnut default |
| 4 | Integrated business page | Contract 1.2 text/table/shape objects plus one native column chart |

The optional preview descendants under each `data-pptx-chart` container are
inert browser-authoring content. The Contract and measurement stages exclude
the entire descendant subtree from generic lowering, so the public gate expects
six authored, six compiled, and six independently read-back native chart
objects—never duplicate preview shapes, textboxes, pictures, or charts.

The release workflow is:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> semantic Gate 3 review of all four slides -> finalize
```

The acceptance result requires validation PASS, zero issues, native chart proof
for every chart, `unsupported=0`, `unresolved=0`, and `material_delta=0`.
