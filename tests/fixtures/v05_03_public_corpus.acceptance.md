# V0.5.3 public acceptance corpus

This tracked four-slide Author corpus is the Product 0.5.3 integration gate for
explicit localized visual fallback. It is intentionally separate from the
negative safety fixtures under `tests/fixtures/v05_03_negative/`.

| Slide | Purpose | Expected localized regions |
| --- | --- | ---: |
| 1 | Contained complex CSS effects: gradient, inset shadow, filter, rounded corners, and padding | 1 |
| 2 | Static inline SVG with gradient, vector path, circle, and text | 1 |
| 3 | Two nonoverlapping local regions among native slide content | 2 |
| 4 | Contract 1.3 native text, merged table, native shape, and native chart beside one local visual | 1 |

The five fallback regions are explicitly opted in with the exact
`data-pptx-rasterize="localized"` token. Each accepted region is expected to
be one `picture` with `disposition: rasterized`, `editable: false`, a fixed
2-pixels-per-point capture, nonblank paint, zero contamination, and independent
picture readback. Rasterized objects are excluded from native counts. The
integrated slide must retain native `shape`, `textbox`, `table`, and `chart`
objects around the fallback picture.

The release workflow is:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> semantic Gate 3 review of all four slides -> finalize
```

The final gate requires `rasterized_count == 5` and zero
`unapproved_rasterized`, `blank_rasterized`, `contaminated_rasterized`,
`failed_isolation`, `unsupported`, `unresolved`, and `material_delta`.
