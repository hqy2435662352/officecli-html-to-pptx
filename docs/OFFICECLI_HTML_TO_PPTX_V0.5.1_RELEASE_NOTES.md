# officecli-html-to-pptx 0.5.1

V0.5.1 is the first formal public native-depth release of the independent
`officecli-html-to-pptx` product. It keeps the five public commands and the
non-overwriting Artifact Pair workflow unchanged while advancing the Author
Contract to 1.1.

## Runtime and public authority

- Product version: `0.5.1`.
- Author Contract: `1.1`.
- Minimum OfficeCLI: `1.0.151`.
- Public commands: `capabilities`, `doctor`, `check`, `build`, and `finalize`.
- The actual OfficeCLI runtime is recorded by `capabilities` attestation,
  `doctor`, `runtime.json`, and `native-evidence.json`.

The compiler checks the discovered OfficeCLI version after Contract checking but
before Chromium measurement or temporary PPTX creation. A version below
`1.0.151` produces a stable blocking diagnostic and leaves no output artifact.

## Native slices

Contract 1.1 and the capability manifest share one authority for:

- authored paragraph boundaries, native hard breaks, exact empty-paragraph
  cardinality, CJK font application, and the frozen run/paragraph matrix;
- legal rectangular `rowspan`/`colspan` regions represented as one native table,
  with normalized merge topology and canonical anchor-owned outer borders; and
- the case-sensitive public `data-pptx-shape-geometry` allowlist, bounded
  rect/roundRect/ellipse inference, and whole-object rotation.

Browser `visualLines` remains measurement/evidence data and never becomes a
native paragraph or hard break. Unsupported typography, malformed table grids,
and unknown/custom geometry fail closed with source context.

## Evidence and verdicts

Every public build continues to produce a matching PPTX and `.evidence/`
directory. In addition to the existing Contract, capability, runtime,
manifest, validation, issue, result, visual-review, and Comparison Image
documents, the bundle contains:

- `readback.json`: an independent OfficeCLI structural read of the published
  PPTX; and
- `native-evidence.json`: text matrix/structure, normalized merge topology,
  native geometry, authored/compiled/readback object counts, actual runtime,
  diagnostics, material delta, and Gate 3 state.

Release acceptance requires `unsupported = 0`, `unresolved = 0`, and
`material_delta = 0`. A complete slide-by-slide Gate 3 review is still required;
minor findings retain the existing `PASS_WITH_FINDINGS` outcome, while a major
finding derives `REVISION_REQUIRED`.

## Public four-slide corpus

`tests/fixtures/v05_01_public_corpus.html` is the tracked Author corpus:

1. rich text, CJK, paragraph boundaries, hard breaks, and empty paragraphs;
2. one native table with horizontal, vertical, and combined rectangular merges;
3. every public geometry token, inferred ellipse, rotation, and text-bearing
   native shape; and
4. an integrated business page combining text, merged table, and shape geometry.

The public acceptance sequence is:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> Gate 3 visual review -> finalize
```

The V0.4 representative/projection corpus remains an independent hidden
regression path and contributes neither to V0.5.1 public gates nor capability
counts. Native charts are reserved for V0.5.2; general localized fallback is
reserved for V0.6. The existing verified SVG picture compatibility behavior is
unchanged.
