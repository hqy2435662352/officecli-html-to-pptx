# officecli-html-to-pptx 0.5.3

V0.5.3 adds an explicit, opt-in localized visual fallback to the public Author
Compiler surface. The existing five-command workflow and non-overwriting
Artifact Pair remain unchanged while the Author Contract advances to 1.3.

## Runtime and public authority

- Product version: `0.5.3`.
- Author Contract: `1.3`.
- Minimum OfficeCLI: `1.0.151` (`>=1.0.151`).
- Public commands: `capabilities`, `doctor`, `check`, `build`, and `finalize`.
- The actual OfficeCLI runtime is recorded by `capabilities` attestation,
  `doctor`, `runtime.json`, and `native-evidence.json`.

The runtime floor is global and fixed. A lower runtime blocks before Chromium
measurement or output creation; Contract behavior is never branched by the
discovered runtime.

## Explicit localized visual fallback

The only public marker is the case-sensitive
`data-pptx-rasterize="localized"` attribute. A marked node is one atomic
authored object: all descendants are excluded before generic object discovery,
so the compiler cannot emit a fallback picture and duplicate native text,
shape, or image descendants.

The node's CSS border box is both the capture bound and the PowerPoint picture
bound. Capture is truly local and isolated from sibling nodes, slide
backgrounds, and master/layout content; it is not a crop of a full-slide
screenshot. Rendering uses the fixed `2 pixels per point` density and produces
a deterministic PNG through the existing picture lowering/readback path.
Overflow from shadows, filters, or other visual paint is not silently clipped:
the author must provide padding and out-of-bounds paint blocks publication.

The initial allowlist is static HTML/CSS, inline SVG, data URIs, and the local
images permitted by the current policy. Script execution, runtime canvas,
iframes, network resources, audio/video, WebGL, animation, interaction state,
and cross-slide capture are rejected. Existing SVG picture fallback remains a
separate compatibility path and is not reclassified as localized fallback.

Public dispositions are exactly `native`, `rasterized`, `unsupported`, and
`unresolved`. `rasterized` means an approved successful visual result, not a
native object; the PNG contents, including text, are not editable. Both
`unsupported` and `unresolved` block publication.

## Evidence and release gates

Localized evidence records identity, deterministic source path, source slide,
border-box bounds, disposition, compiled kind, PNG hash, pixel dimensions,
density, nonblank paint, isolation, and independent readback. A material
comparison covers the same fields and does not require the packaged PPTX image
bytes to equal the capture PNG bytes byte-for-byte.

The fixed publication gate is:

```text
unapproved_rasterized = 0
blank_rasterized = 0
contaminated_rasterized = 0
failed_isolation = 0
unsupported = 0
unresolved = 0
material_delta = 0
```

## Public four-slide corpus

`tests/fixtures/v05_03_public_corpus.html` is the tracked Author corpus:

1. contained CSS effects with one localized fallback;
2. inline SVG with one localized fallback;
3. two independent non-overlapping localized regions on one slide; and
4. an integrated page combining native text, merged table, shape, and chart
   objects with one localized fallback.

The corpus contains five authored localized regions and is expected to produce
exactly five approved rasterized picture objects. V0.5.2's six-chart corpus,
the V0.5.1 native corpus, and the V0.4 projection corpus remain independent
regression fixtures and do not contribute to the V0.5.3 fallback gate.

The public acceptance sequence is:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> semantic Gate 3 review of all four slides -> finalize
```

The release does not add a command, does not add editable text overlays, does
not weaken native chart/table/text/shape behavior, and does not absorb missing
core implementation from the V0.5.3 vertical-slice issues.
