# Product 0.6.2 installed Inspector acceptance

This public corpus is the real Author HTML input for ticket #49. It has seven
slides. The Author-side chart projector runs after DOM parsing and reads only
the chart's inert `data-pptx-chart-spec`; its generated table is a browser
observation, never source or compiler input. The installed Workbench creates a
separate semantic Preview from the same spec.

| Slides | Corpus cases |
| --- | --- |
| 1 | Simple Unicode text leaf, two objects sharing a class, one bounded data image |
| 2 | Native Shape geometry token and solid property surface |
| 3 | Rectangular merged table with a 2 × 2 anchor and covered coordinates |
| 4–6 | Native column/bar/line charts at 1, 2, and 3 series; native pie/doughnut at one series; title, categories, names, values, colors, legend, labels, and axis presentation |
| 7 | Explicit localized fallback with a read-only Inspector summary |

The canonical chart projector is a semantic table, not a second data model or
a chart-rendering implementation. Each row identifies the series and its
color; each column identifies a category; cells show the authored values. The
caption and summary show the type and supported presentation tokens. Gate 3
reviews that semantic representation against the native PowerPoint chart and
records visible representation differences as findings; it does not claim
pixel equality.

## Installed run

Run from a clean virtual environment with the wheel built from this revision.
The runtime requirements are Python 3.12, OfficeCLI `>=1.0.151`, Node.js, and
Playwright 1.62.0 with its matching Chromium. Do not import the checkout while
running the acceptance; use the installed `officecli-html-to-pptx` command.

1. Run `capabilities --json` and `doctor --json`; confirm Product 0.6.2,
   Contract 1.3, OfficeCLI floor `>=1.0.151`, and the Inspector surface.
2. Start `workbench tests/fixtures/v06_02_inspector_corpus.html --no-browser
   --json` and open the returned loopback URL in Chromium.
3. On slide 1 edit `#editable-text`, change its class-derived text color, and
   confirm the Inspector labels the change as a local override while
   `#shared-sibling` remains unchanged. Replace `#editable-picture` with a
   PNG under 10 MiB and verify its new data URI is in the focused diff.
4. On slide 2 change `#editable-shape` geometry from `rect` to `ellipse` and
   edit its solid fill. Confirm the Preview ellipse and source CSS selector
   follow the patched geometry token.
5. On slide 3 edit the merged anchor's text and fill. Click the covered
   coordinate: it must map to the anchor or remain read-only. Preserve
   rowspan/colspan.
6. Edit one ChartSpec field on a category chart and one on a part-to-whole
   chart. Verify the semantic Preview names the same type/categories/series/
   values/presentation from the current sole spec.
7. Confirm slide 7 has no native property controls and reports the localized
   visual-only reason.
8. Confirm the focused diff contains only the chosen source tokens. Preview
   markers, computed state, generated semantic tables/SVGs, and hidden chart
   semantics must not enter the source or build input.
9. Click Save, then Check the saved SHA and require Contract PASS. Build one
   ordinary revision and retain the `.pptx`/`.evidence` Artifact Pair.
10. Independently inspect `readback.json`, `validate.json`, `issues.json`,
    `native-evidence.json`, every `comparisons/slide-*.png`, and
    `visual-review.json`. Record one Gate 3 decision per slide and run
    `finalize` against that exact Pair.

## Results

Measured on 2026-09-23 from a freshly installed wheel. Python was 3.12.13,
OfficeCLI 1.0.152, Node.js 22.22.3, Playwright 1.62.0, and Chromium revision
1234. Installed `doctor --json` returned `PASS`; installed `capabilities`
published Product 0.6.2, Author Contract 1.3, and OfficeCLI `>=1.0.151`.
The installed UI completed ten Inspector edits with ten nonempty focused
diffs. The source file remained byte-identical until explicit Save; Check of
that saved SHA returned Contract `PASS`, then ordinary Build Revision created
the Pair below.

| Artifact | SHA-256 |
| --- | --- |
| Installed wheel `officecli_html_to_pptx-0.6.2-py3-none-any.whl` | `829a7610fc05f87ddb383d8f81e0806367d075b4ba98a5c7b32b3cd69eb90e74` |
| Saved Author `C:\TEMP\officecli-v062-49-acceptance\author.html` | `8feb7a217cab2f026fda652d0020382e8e821f7115f9734872e49ddc8105bdb0` |
| PPTX `C:\TEMP\officecli-v062-49-acceptance\.officecli-workbench\author-r01.pptx` | `d09f100a41ebefc814dcf249c56e6839e71025402e8ff9754846d628c714393d` |
| Evidence `result.json` | `804505d5284bb1d4c9d58d0a33cecfad2e0208bd966a2063b41d76c116cd7007` |
| Evidence `finalization.json` | `aac7925686c93d24b8cc0625ee13fa1c1d15679fd37eea4940d9731f53b5e6d7` |

The Evidence directory is the PPTX path with `.pptx` replaced by `.evidence`.
Its `visual-review.json` binds the exact source/PPTX hashes, build ID, and
seven comparison-image paths and hashes. Independent readback matched all 38
compiled objects. It found 37 native objects (21 textboxes, 3 shapes, one
Picture, one Table, and 11 Charts) and the one explicitly localized raster
fallback. Every one of the 11 native charts matched its sole saved ChartSpec
for type, categories, names, values, colors, and supported presentation.
The merged Table, edited Shape, fitted Picture, and fallback were also read
back. `validate.json` and `issues.json` were `PASS` with zero issues;
`native-evidence.json` reported zero unsupported, unresolved, and material
delta diagnostics.

| Slide | Gate 3 observation |
| --- | --- |
| 1 | Text, CJK/markup escaping, sibling color, and fitted Picture visibly match. |
| 2 | Native ellipse geometry, solid fill, border, and text visibly match. |
| 3 | Native merged anchor text/fill and 2 × 2 span visibly match. A separate installed Workbench read-only check clicked both the anchor's upper-left and its covered lower-right quadrant; both selected the same anchor text, and source bytes stayed unchanged. |
| 4 | Four column/bar charts preserve all semantics; minor finding: native axis/legend text is crowded in the four-up layout, while the Author projection is a semantic table. |
| 5 | Four bar/line charts preserve all semantics; the same minor representation/layout finding. |
| 6 | Three line/pie/doughnut charts preserve all semantics; the same minor representation/layout finding. |
| 7 | One localized visual-only object matches visually and remains read-only. |

All seven comparisons were reviewed and bound to this Pair. Installed
`finalize --json` returned `PASS_WITH_FINDINGS`: Gate 3 `PASS`, seven reviewed
slides, zero major and three minor findings. The chart projection is deliberately
semantic rather than pixel-equivalent to editable native PowerPoint plots.
The additional covered-cell selection record is
`C:\TEMP\officecli-v062-49-acceptance\covered-cell-selection.json` (SHA-256
`20eeb9a36ce7467eb72e31b113fc0a3f83758c384826624ad890bfe91c0fbc2e`).

## Historical full-suite gate

The primary agent ran the full suite once on the integrated
`codex/v0.6.2-inspector` branch at `b6e2b39a50169b3a815b375444d139ba90489d34`,
using the 0.6.1 virtual environment, `PYTHONPATH=src`, and `pytest -q` with
JUnit output. The result was **21 failed, 782 passed, 5 skipped, 39 errors in
2954.81s**. The frozen 0.6.1 baseline is **21 failed, 738 passed, 5 skipped,
39 errors**. Exact failing/error test-node identity sets are identical:
zero new and zero resolved failures; zero new and zero resolved errors. The four
new `test_v062_workbench_release.py` checks all passed.

Failure-cause review compared the historical full pytest log with this run.
Twenty failure sections have the same first assertion or exception text; the
remaining missing historical Gate report has the same `FileNotFoundError` and
differs only in the checkout-root path. The 39 V0.4.2 setup errors retain the
same OfficeCLI `range end 93 out of bounds (scope text has 92 chars)` cause.
The six V0.5.2 chart-version failures still assert OfficeCLI 1.0.151 against
the installed 1.0.152. No historical expectation was weakened to obtain this
result.

Local full-run artifacts are `C:\TEMP\officecli-v062-final-full.xml` (SHA-256
`b9d958c12666264d2a16f35608f7dedadfc1513a47f83f67072b3f8681ef903e`)
and `C:\TEMP\officecli-v062-final-full.log` (SHA-256
`3710dd54ea424a9dcc7cad844888074129f344c952f5eeb524c020da8967efd8`).
