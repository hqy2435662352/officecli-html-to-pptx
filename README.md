# officecli-html-to-pptx

`officecli-html-to-pptx` 0.5.2 builds a new editable PowerPoint deck from
Contract-checked Author HTML. Chromium supplies final layout measurements and
OfficeCLI creates the native PowerPoint objects. The supported public path is
task-oriented and produces a matching PPTX/Evidence Pair:

```text
capabilities -> doctor -> check -> fresh build -> independent readback
  -> validate/issues -> Gate 3 visual review -> finalize
```

The product does not edit an existing presentation and does not replace a
slide with a screenshot. Supported visible objects are native text-bearing
shapes, rectangles, pictures, merged tables, the Contract 1.2 text and
geometry surface, and explicitly authored native `column`, `bar`, `line`,
`pie`, and `doughnut` charts reported by the installed command. General
localized fallback remains out of scope.

## Install

For a packaged V0.5.2 release, install the bundled wheel from the ZIP
root and then install its Playwright-managed Chromium:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\core\officecli_html_to_pptx-0.5.2-py3-none-any.whl
.\.venv\Scripts\python.exe -m playwright install chromium
```

See [`DEPLOYMENT.zh-CN.md`](DEPLOYMENT.zh-CN.md) for the complete deployment,
Codex Plugin, five-command workflow, evidence, and troubleshooting guide. It
covers the Windows path and the Linux host requirements.
Package-index installation is available only after the distribution has been
published to the configured index:

```bash
pip install officecli-html-to-pptx
python -m playwright install chromium
```

OfficeCLI and Node.js are external prerequisites. The product never installs,
downloads, upgrades, or rewrites runtime configuration. Formal builds use
Windows or Linux, OfficeCLI `1.0.151` or newer, Playwright `1.62.0`, and its
accepted Chromium revision. `capabilities --json` reports both the platform the
command is running on and the platforms the build supports. Check the local
state without mutation:

```bash
officecli-html-to-pptx doctor --json
```

## Public command

All commands share one versioned JSON envelope. With `--json`, stdout contains
exactly one UTF-8 JSON document; human diagnostics go to stderr.

```bash
officecli-html-to-pptx capabilities --json
officecli-html-to-pptx doctor --json
officecli-html-to-pptx check deck.html --json
officecli-html-to-pptx build deck.html deck.pptx --json
officecli-html-to-pptx finalize deck.evidence --json
```

Exit classes are stable: `0` means the defined operation completed, `2` means
an actionable block or revision decision, `3` means invalid invocation or
input, and `4` means an unexpected runtime or external-tool failure. A
successful build returns `VISUAL_REVIEW_REQUIRED` with exit `0`; finalization
derives `PASS`, `PASS_WITH_FINDINGS`, or `REVISION_REQUIRED`.

The public Python API mirrors those operations:

```python
import asyncio

from officecli_html_to_pptx import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)

print(get_capabilities().as_dict())
print(check_author_html("deck.html").as_dict())
build_result = asyncio.run(build_author_html("deck.html", "deck.pptx"))
print(build_result.as_dict())
# An agent records its completed visual review, then:
print(finalize_build("deck.evidence").as_dict())
```

## Author HTML

Author HTML contains fixed widescreen slide sections. The Contract check is
the promotion gate, so run it before build:

```html
<!doctype html>
<html>
  <head>
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; overflow: hidden; }
      .slide {
        width: 1920px;
        height: 1080px;
        display: none;
        font-family: sans-serif;
      }
      .slide.active { display: flex; }
    </style>
  </head>
  <body>
    <section class="slide active" style="background:#172033">
      <h1 style="color:#fff;font-size:64px">Hello World</h1>
    </section>
  </body>
</html>
```

Use `capabilities --json` as the executable support authority for supported
HTML and object kinds. It also answers the platform question, in two parts:
`platform` is where the command is running and `supported_platforms` is what
this build supports, with `validated_platform_scope` recording the environment
each key was accepted in and whether that was verified (it is not — the gate
matches an operating-system family only). `doctor --json` decides for the
machine in front of you. External resources and unsupported visible content are
rejected explicitly. Pictures must be deterministic `data:image/...` sources.
Contract 1.2 accepts legal rectangular `rowspan`/`colspan` regions with
normalized merge-topology readback and exposes the closed
`data-pptx-shape-geometry` allowlist. It also accepts one atomic
`data-pptx-chart` container with exactly one inert JSON
`data-pptx-chart-spec` script. The closed chart surface preserves ordered
categories and series, supports the five native chart types, and exposes only
semantic presentation tokens. The outer chart container supplies geometry;
every preview descendant is excluded from generic lowering. Unknown fields,
unsupported combinations, and chart fallback fail closed.

## Evidence Bundle

For `deck.pptx`, build derives the non-overwriting companion
`deck.evidence/`. The pair is staged and published together only after
structural and visual evidence is complete:

```text
deck.pptx
deck.evidence/
  contract.json
  capabilities.json
  runtime.json
  manifest.json
  readback.json
  native-evidence.json
  validate.json
  issues.json
  result.json
  visual-review.json
  comparisons/
    slide-001.png
    ...
```

Only combined per-slide Comparison Images are retained; source and output
screenshots are temporary build inputs. `readback.json` is an independent
OfficeCLI object read, while `native-evidence.json` records the frozen text
matrix and authored structure, normalized merge topology, native geometry,
native chart count and normalized chart structures, compiled/readback counts,
actual OfficeCLI runtime, diagnostics/material delta, and Gate 3 state. No
V0.6 `native/rasterized/degraded` taxonomy is introduced.
`visual-review.json` is seeded with a complete image inventory and immutable
hashes. An independent reviewer marks every slide and records only `major` or
`minor` findings. A major finding requires an actionable revision instruction.
`finalize` verifies the exact build identity, HTML/PPTX hashes, comparison paths
and hashes, native evidence, and slide coverage before deriving its outcome. It
does not rebuild or rerender.

If either requested target already exists, build stops without overwriting it.
Choose a new output path or an agent-managed revision suffix.

## Development

```bash
uv sync --extra dev
uv run pytest -q
uv run python -m compileall -q src
git diff --check
```

The maintained product surface is Author HTML plus the five commands above.
The tracked four-slide Author corpus at
`tests/fixtures/v05_02_public_corpus.html` is the V0.5.2 public acceptance
corpus for categorical, trend, part-to-whole, and integrated native-chart
behavior. The V0.5.1 corpus remains a focused regression fixture. V0.4
projection experiments remain a separate internal regression corpus and do not
contribute to public gates or capability counts. The MIT license and upstream
history are preserved.
