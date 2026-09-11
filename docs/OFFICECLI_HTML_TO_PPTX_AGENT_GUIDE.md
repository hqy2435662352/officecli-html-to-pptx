# OfficeCLI HTML-to-PPTX Agent Guide

Use this guide when an agent must turn controlled HTML slides into an editable,
native-object PowerPoint through the repository's OfficeCLI-first compiler, or
when it must recompile an OfficeCLI HTML projection into a new PPTX.

The required outcome is a validated PPTX plus evidence that the supported
content survived as independent PowerPoint objects. Compilation success alone
is not completion.

## Sources of truth

Use these authorities in order:

1. [`OFFICEHTML_CONTRACT_V1.md`](OFFICEHTML_CONTRACT_V1.md) defines accepted
   input, supported objects, explicit non-goals, issue statuses, and the pinned
   OfficeCLI compatibility baseline.
2. Installed `officecli help ...` output defines the local OfficeCLI command
   and property surface.
3. This guide defines the agent workflow and completion gates.

When they disagree, follow the Contract for compiler capability and installed
OfficeCLI help for CLI syntax. Do not import limitations from the legacy
`python-pptx` renderer into the OfficeCLI profile.

## Choose the branch before acting

| Input and goal | Branch | Profile |
|---|---|---|
| 1920×1080 Author HTML to a new native PPTX | Author compile | `author` |
| HTML produced by `officecli view <pptx> html` to a new native PPTX | OfficeHTML compile | `officehtml` |
| Prove the Algeria golden case end to end | Algeria gate | `author` then `officehtml` |
| Edit an existing PPTX in place | Direct OfficeCLI editing | Outside this compiler guide |
| Convert an arbitrary webpage or responsive site | Reframe the input first | Unsupported |

Profiles are explicit. Never infer one from CSS, `data-path`, filenames, or
page dimensions.

## Hard invariants

- Work from the repository root.
- Confirm OfficeCLI is exactly the Contract baseline before compiling.
- Run the matching Contract profile before compilation.
- Use a new output path whose parent directory already exists.
- Preserve authored-object granularity: one image remains one picture; one
  HTML table remains one native PowerPoint table.
- Treat unsupported visible content as a blocking diagnostic. Do not omit it,
  approximate it silently, or replace the slide with a screenshot.
- Use the public `compile_officecli(...)` seam. Do not orchestrate private
  measurement, IR, or OfficeCLI batch helpers.
- Validate the delivered PPTX with OfficeCLI, inspect text and structure, and
  review a screenshot of every slide.
- Report known baseline findings separately from regressions.

## Environment setup

The current Contract is pinned to OfficeCLI `1.0.147`. Windows and Linux are
supported build platforms; `doctor --json` decides for the machine in front of
you, and `capabilities --json` reports the running platform alongside the
supported set.

From the repository root on Windows PowerShell:

```powershell
Set-Location 'D:\Opencodeworkspace\html-to-pptx\officecli-html-to-pptx-mvp'

.\.venv\Scripts\python.exe --version
officecli --version
.\.venv\Scripts\python.exe -c "import html_to_pptx; print(html_to_pptx.__file__)"
```

On Linux use the same commands through `.venv/bin/`, and activate the
environment first: OfficeCLI discovers a headless browser through a
Playwright-capable `python3` on `PATH`, so its PPTX screenshot stage fails
without it. Do not run the product as root, and install the fonts the Author
HTML declares — see `DEPLOYMENT.zh-CN.md`, "在 Linux 上部署".

Expected OfficeCLI output:

```text
1.0.147
```

If the editable environment is not installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m playwright install chromium
```

If the virtual environment has no `pip`, use:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e .
```

An OfficeCLI version mismatch is a compatibility event, not a harmless local
difference. Replay the golden acceptance gate before relying on another
version; do not silently change the Contract baseline.

## Branch A — Author HTML to PPTX

### Step 1: author a browser-reviewable deck

Author HTML is both the editable visual workbench and compiler input. It must
contain one or more 1920×1080 `.slide` elements. Inline preview controls are
allowed when they do not rewrite slide content.

Minimum structure:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { width: 100%; height: 100%; overflow: hidden; }
    body { background: #17181b; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }

    .slide {
      position: relative;
      width: 1920px;
      height: 1080px;
      display: none;
      overflow: hidden;
      background: #ffffff;
      padding: 72px;
    }
    .slide.active { display: block; }
    .title { font-size: 64px; line-height: 1.1; color: #202124; }
    .card {
      position: absolute;
      left: 72px;
      top: 210px;
      width: 760px;
      height: 260px;
      padding: 32px;
      border: 2px solid #d7d8da;
      border-radius: 28px;
      background: #f3f4f5;
    }
    .card h2 { font-size: 34px; color: #202124; }
    .card p { margin-top: 18px; font-size: 24px; line-height: 1.3; color: #55585d; }
    table {
      position: absolute;
      left: 900px;
      top: 210px;
      width: 900px;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 22px;
    }
    th, td { height: 72px; padding: 12px; border: 2px solid #d7d8da; }
    th { background: #e60012; color: #ffffff; }
    .preview-only {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 9999;
      color: white;
    }
  </style>
</head>
<body>
  <section class="slide active">
    <h1 class="title">Quarterly product review</h1>
    <article class="card">
      <h2>Native objects</h2>
      <p>Text and cards remain editable after conversion.</p>
    </article>
    <table>
      <thead><tr><th>Model</th><th>Capacity</th></tr></thead>
      <tbody>
        <tr><td>Alpha</td><td>12K</td></tr>
        <tr><td>Beta</td><td>18K</td></tr>
      </tbody>
    </table>
  </section>

  <div class="preview-only"><span id="counter">1 / 1</span></div>
  <script>
    const slides = [...document.querySelectorAll('.slide')];
    let current = 0;
    function goTo(index) {
      current = Math.max(0, Math.min(slides.length - 1, index));
      slides.forEach((slide, i) => slide.classList.toggle('active', i === current));
      document.querySelector('#counter').textContent = `${current + 1} / ${slides.length}`;
    }
    function next() { goTo(current + 1); }
    function previous() { goTo(current - 1); }
    addEventListener('keydown', event => {
      if (['ArrowRight', 'PageDown', ' '].includes(event.key)) next();
      if (['ArrowLeft', 'PageUp'].includes(event.key)) previous();
      if (event.key === 'Home') goTo(0);
      if (event.key === 'End') goTo(slides.length - 1);
    });
    goTo(0);
  </script>
</body>
</html>
```

Authoring constraints that must be settled before preflight:

- Put all slide content inside `.slide` elements.
- Use shallow Flexbox or Grid and let Chromium resolve final geometry.
- Give important objects explicit dimensions and keep them inside the canvas.
- Use real `data:image/...;base64,...` sources for pictures. A placeholder or
  local/http image path is not a valid deliverable.
- Use semantic `<table>`, `<tr>`, `<th>`, and `<td>` elements for native tables.
- Keep every `rowspan` and `colspan` equal to one.
- Keep preview JavaScript inline and content-preserving.
- Keep external scripts, stylesheets, fonts, and other network resources out of
  the input.
- Replace unsupported visible content with a supported authored representation
  before compiling.

Completion criterion: the HTML opens in a browser, every slide is reachable,
and all authored content is visible without relying on a network request.

### Step 2: run the Author Contract

```powershell
$AuthorHtml = 'D:\path\to\deck.html'
$ArtifactDir = 'C:\TEMP\deck-officecli-acceptance-001'

if (Test-Path -LiteralPath $ArtifactDir) {
  throw "Use a fresh artifact directory: $ArtifactDir"
}
New-Item -ItemType Directory -Path $ArtifactDir | Out-Null

.\.venv\Scripts\html-to-pptx-contract.exe `
  $AuthorHtml `
  --profile author `
  --json "$ArtifactDir\author-contract.json"
```

Completion criterion:

- process exit code is `0`;
- report status is `PASS`;
- `blocked` is `false`;
- `diagnostics` contains no blocking item.

Exit code `2` means the input is outside the Contract. Fix the input; do not
bypass the checker.

### Step 3: compile through the public seam

The ordinary `html-to-pptx input output` CLI still selects the legacy renderer.
Use the exported Python API for the OfficeCLI-first path.

Write a small task-local driver to
`$ArtifactDir\compile_officecli_task.py`; keep it with the generated evidence,
not in the repository:

```python
import asyncio
import json
import sys

from html_to_pptx import OfficeCLICompilationError, compile_officecli


async def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: compile_officecli_task.py INPUT_HTML OUTPUT_PPTX PROFILE"
        )

    input_html, output_pptx, profile = sys.argv[1:]
    try:
        result = await compile_officecli(
            input_html,
            profile,
            output_pptx,
        )
    except OfficeCLICompilationError as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "message": str(exc),
                    "diagnostics": [item.as_dict() for item in exc.diagnostics],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    print(
        json.dumps(
            {
                "status": "PASS",
                "output_path": result.output_path,
                "profile": result.profile,
                "slide_count": result.slide_count,
                "object_count": result.object_count,
                "object_kind_counts": result.manifest["object_kind_counts"],
                "diagnostics": [item.as_dict() for item in result.diagnostics],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


raise SystemExit(asyncio.run(main()))
```

Run it with a new output path:

```powershell
$PptxA = "$ArtifactDir\deck-a.pptx"
$CompileDriver = "$ArtifactDir\compile_officecli_task.py"

.\.venv\Scripts\python.exe $CompileDriver `
  $AuthorHtml `
  $PptxA `
  author
```

`slide_indices` is zero-based when a task needs only selected source slides:

```python
result = await compile_officecli(
    input_html,
    "author",
    output_pptx,
    slide_indices=[0, 3, 7],
)
```

The destination parent must already exist, and the destination PPTX must not.
Use a new path rather than deleting or overwriting prior evidence.

Completion criterion: the result reports the expected slide count, object
count, kind counts, an empty diagnostic list, and the output file exists.

### Step 4: run structural and content gates

```powershell
officecli validate $PptxA
officecli view $PptxA stats
officecli view $PptxA issues
officecli view $PptxA text
officecli query $PptxA 'table' --json
officecli query $PptxA 'picture' --json
```

Judge the outputs rather than recording only exit codes:

- `validate` must report no schema error.
- Slide count and object-kind counts must match the compilation result and task
  expectations.
- Required text must be present character-for-character.
- Every authored image must appear as an independent picture.
- Every authored table must appear as one native table with the expected
  dimensions.
- A whole-slide picture is a flattening failure.
- A shape-per-cell table is a structure failure.
- Every `view issues` line must be resolved or explicitly classified. An
  arbitrary deck has no automatic Algeria allowlist.

OfficeCLI `view stats` reports pictures separately from `Total shapes`. Do not
mistake that presentation for an object-count mismatch. Blank-layout decks may
also report `Slides without title` because authored titles are ordinary shapes;
confirm the visible title instead of treating that line alone as a defect.

Completion criterion: schema, counts, native-object structure, required text,
and issue classification are all accounted for.

### Step 5: run the visual gate

Render every slide, not only a representative sample. Consult
`officecli help view` when the installed version's multi-page output naming is
unclear; the portable path is one explicit command per page:

```powershell
$VisualDir = "$ArtifactDir\visuals"
New-Item -ItemType Directory -Path $VisualDir | Out-Null

officecli view $PptxA screenshot --page 1 -o "$VisualDir\slide-001.png"
officecli view $PptxA screenshot --page 2 -o "$VisualDir\slide-002.png"
```

Continue through the final page.

Review every rendered slide for:

- missing content;
- overlap or clipping;
- unexpected line wrapping;
- text or shapes outside the slide;
- dark-on-dark content;
- distorted, blank, or incorrectly cropped pictures;
- table row, column, border, and alignment drift;
- unintended theme effects;
- placeholder text;
- slide-sized raster flattening.

When a defect originates in Author HTML, fix that source and compile to a new
artifact path. Use direct OfficeCLI post-processing only when the task
explicitly requires it, and record that the added object may be outside the
OfficeHTML round-trip Contract.

Visual review is the only proof for appearance. `validate`, manifests, and
OfficeHTML do not prove that a picture rendered visibly or that two objects did
not overlap.

Completion criterion: every slide has a screenshot and an explicit `PASS` or
recorded finding. The final deck is not deliverable while any blocker remains.

## Branch B — OfficeHTML to PPTX

OfficeHTML is the fixed-coordinate object projection produced by OfficeCLI
`1.0.147`. It is a decompiler projection and verification oracle, not a
responsive authoring format and not an in-place patch protocol.

### Step 1: export OfficeHTML to a file

Always provide `-o`; otherwise `officecli view ... html` writes the full HTML to
stdout.

```powershell
$PptxA = 'C:\TEMP\deck-officecli-acceptance-001\deck-a.pptx'
$ArtifactDir = Split-Path -Parent $PptxA
$CompileDriver = "$ArtifactDir\compile_officecli_task.py"
$OfficeHtml = 'C:\TEMP\deck-officecli-acceptance-001\deck-a.officehtml.html'

officecli view $PptxA html -o $OfficeHtml
```

### Step 2: run the OfficeHTML Contract

```powershell
.\.venv\Scripts\html-to-pptx-contract.exe `
  $OfficeHtml `
  --profile officehtml `
  --json "$ArtifactDir\officehtml-contract.json"
```

The profile recognizes slide-owned `/shape[...]`, `/picture[...]`, and
`/table[...]` objects through `data-path`; table cells use `data-cell-path`.
Viewer chrome, thumbnails, navigation, and unowned master/layout projections
are excluded. Owned deferred objects are blocking findings rather than ignored
content.

### Step 3: compile to a new PPTX

```powershell
$PptxB = "$ArtifactDir\deck-b.pptx"

.\.venv\Scripts\python.exe $CompileDriver `
  $OfficeHtml `
  $PptxB `
  officehtml
```

### Step 4: validate the round trip

```powershell
officecli validate $PptxB
officecli view $PptxB stats
officecli view $PptxB issues
officecli view $PptxB text
```

Compare A and B across the supported surface:

- slide count and slide dimensions;
- object-kind counts;
- stable object identities;
- Unicode text and paragraph boundaries;
- picture count;
- table count, dimensions, and cell content;
- geometry and supported formatting;
- OfficeCLI issue keys and severity;
- per-slide screenshots.

Do not require binary PPTX equality, ZIP ordering, relationship IDs, or raw XML
ordering. For the Algeria golden case, use the built-in acceptance comparator
instead of inventing a second tolerance policy.

Completion criterion: PPTX B validates, the supported manifest is equivalent
within Contract tolerances, B introduces no new issue, and every B screenshot
has been reviewed.

## Branch C — Algeria golden acceptance

Use this branch to verify the compiler, Contract, or an OfficeCLI version
change against the canonical eight-slide golden case.

The output directory must be new and empty:

```powershell
$AlgeriaHtml = 'D:\path\to\Algeria_AC_Product_Portfolio_20260906_v3_pptx.html'
$AcceptanceDir = 'C:\TEMP\officecli-algeria-acceptance-001'

.\.venv\Scripts\html-to-pptx-algeria-acceptance.exe `
  --input $AlgeriaHtml `
  --output-dir $AcceptanceDir
```

The gate produces PPTX A, OfficeHTML A, PPTX B, Contract reports, issue reports,
normalized structure evidence, and per-slide comparison images. Without a
visual-review document, Gate 3 remains `PENDING`; generated screenshots alone
are not a visual PASS.

Review every image under the draft run's `visuals\side-by-side` directory,
then replace the generated `PENDING` entries in
`$AcceptanceDir\visual-review.json` with one evidence-backed `PASS` or `FAIL`
entry per slide. Preserve concrete findings and reviewer notes in that file.

Visual-review schema:

```json
{
  "slides": [
    {
      "slide": 1,
      "status": "PASS",
      "findings": [],
      "notes": "Title, product images, and card geometry reviewed."
    }
  ],
  "notes": "One entry is required for every slide."
}
```

Allowed slide statuses are `PASS`, `PENDING`, and `FAIL`. A `FAIL` slide or a
finding whose severity is `blocker` or `major` makes Gate 3 a regression.

When a reviewed file is ready, run the final gate into another new output
directory and pass the review file explicitly:

```powershell
$FinalAcceptanceDir = 'C:\TEMP\officecli-algeria-acceptance-final-001'

.\.venv\Scripts\html-to-pptx-algeria-acceptance.exe `
  --input $AlgeriaHtml `
  --output-dir $FinalAcceptanceDir `
  --visual-review "$AcceptanceDir\visual-review.json"
```

The review must correspond to the same input and compiler state. Recheck the
final run's screenshots before accepting the report.

Interpret the final status precisely:

- `PASS`: no issue or failed gate remains.
- `KNOWN_BASELINE_DIFFERENCE`: only the exact allowlisted issue keys remain.
- `UNSUPPORTED_INPUT`: Contract or compiler rejected the source.
- `REGRESSION`: a structural, round-trip, issue, screenshot, or visual-review
  failure occurred.

Completion criterion: all checks are present, all eight slides have a reviewed
comparison, and the final status is `PASS` or a fully accounted-for
`KNOWN_BASELINE_DIFFERENCE`.

## Diagnostics and failure handling

Contract reports expose:

```text
profile, severity, code, message, source_object, blocking
```

Compiler diagnostics expose:

```text
severity, code, message, source_slide, source_object, operation
```

Branch on diagnostic `code`; keep `message` for humans. Preserve slide and DOM
source context in the final report.

Common top-level failures require different action:

| Failure | Agent action |
|---|---|
| `ContractReport.blocked` | Fix or explicitly reject the input; do not compile |
| `OfficeCLICompilationError` | Report every structured diagnostic and preserve the absent/previous deliverable |
| `FileExistsError` | Choose a new output path |
| `FileNotFoundError` for the parent | Create the exact task-local output directory |
| Unsupported profile `ValueError` | Select exactly `author` or `officehtml` |
| OfficeCLI unavailable/version mismatch | Restore the baseline environment before judging output |
| New `view issues` entry | Treat as a regression until explained and approved |
| Blank or missing rendered picture | Treat as a visual failure even if `validate` passed |

The compiler renders to a temporary PPTX, validates it, closes the OfficeCLI
resident, and atomically moves it to the destination. A failed compile should
not leave a new deliverable. Verify that invariant when diagnosing a failure.

## Windows UTF-8 and large-output adapter

When OfficeCLI output contains Chinese or other non-ASCII text, or a direct
PowerShell call produces replacement characters, call OfficeCLI through Python
`subprocess.run()` and decode the raw bytes as UTF-8:

```python
import json
import subprocess


def run_officecli(*args: str) -> str:
    completed = subprocess.run(
        ["officecli", *args],
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="strict")
    stderr = completed.stderr.decode("utf-8", errors="strict")
    if completed.returncode:
        raise RuntimeError(
            json.dumps(
                {
                    "args": args,
                    "exit_code": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                ensure_ascii=False,
            )
        )
    return stdout


print(run_officecli("view", r"C:\TEMP\deck.pptx", "text"))
```

For table cells, begin with `--depth 0`. Increase depth only when the required
field is absent; deep table reads can emit large embedded XML and trigger a
process kill.

```python
print(
    run_officecli(
        "get",
        r"C:\TEMP\deck.pptx",
        "/slide[2]/table[1]/tr[1]/tc[1]",
        "--depth",
        "0",
        "--json",
    )
)
```

Pass paths as subprocess arguments. If a particular OfficeCLI build still
fails on a Chinese path, copy the input to an ASCII-only task directory and
record the original and temporary paths.

## Supported surface and non-goals

Contract v1 supports:

- slides and slide backgrounds;
- rectangles and rounded rectangles;
- text boxes and text-bearing shapes;
- paragraphs and direct text runs;
- data-URI pictures, including SVG with deterministic picture-level fallback;
- native tables, rows, columns, and cells;
- the formatting fields enumerated by the Contract.

Contract v1 does not promise merged table cells, editable charts, master/theme
reconstruction, connectors, groups, SmartArt, equations, media, animations,
notes, comments, complete hyperlink round trips, complex gradients, filters,
clipping paths, complex shadows, arbitrary SVG-to-path conversion, automatic
slide design, arbitrary HTML, responsive websites, or in-place PPTX patching
through `data-path`.

If requested content needs one of those capabilities, stop before authoring it
into an unsupported representation. Ask for a product-level decision: simplify
the design, post-process the compiled PPTX with direct OfficeCLI operations, or
use another renderer. Never hide the loss.

## Final agent checklist

- [ ] Correct repository root and task input confirmed.
- [ ] Installed OfficeCLI version matches Contract v1.
- [ ] Explicit `author` or `officehtml` profile selected.
- [ ] Author HTML remains a browser-reviewable workbench when applicable.
- [ ] Matching Contract report is `PASS`.
- [ ] Fresh output directory and non-existing PPTX path used.
- [ ] Public `compile_officecli(...)` seam completed without diagnostics.
- [ ] Slide count and object-kind counts match expectations.
- [ ] Required text is preserved character-for-character.
- [ ] Pictures are independent, visible objects.
- [ ] Tables are native and have the expected dimensions.
- [ ] `officecli validate` passed.
- [ ] Every `officecli view issues` entry is resolved or classified.
- [ ] Every slide has a reviewed screenshot.
- [ ] OfficeHTML round trip completed when reversibility is in scope.
- [ ] Final report links the PPTX, Contract JSON, issue output, screenshots, and
      round-trip artifacts.
- [ ] Known baseline differences are named; regressions are not relabeled.

The task is complete only when every applicable item is evidenced in the final
handoff.
