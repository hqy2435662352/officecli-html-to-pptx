# officecli-html-to-pptx

`officecli-html-to-pptx` 0.2.0 builds a new editable PowerPoint deck from
Contract-checked Author HTML. Chromium supplies final layout measurements and
OfficeCLI creates the native PowerPoint objects. The supported public path is
task-oriented and produces a matching PPTX/Evidence Pair:

```text
Candidate HTML -> check -> build -> visual review -> finalize
```

The product does not edit an existing presentation and does not replace a
slide with a screenshot. Supported visible objects are native text-bearing
shapes, rectangles, pictures, and tables, within the capability data reported
by the installed command.

## Install

```bash
pip install officecli-html-to-pptx
uv run playwright install chromium
```

OfficeCLI and Node.js are external prerequisites. The product never installs,
downloads, upgrades, or rewrites runtime configuration. Formal V0.2 builds use
Windows, OfficeCLI `1.0.147`, Playwright `1.62.0`, and its accepted Chromium
revision. Check the local state without mutation:

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

Use `capabilities --json` as the executable support authority. External
resources and unsupported visible content are rejected explicitly. Pictures
must be deterministic `data:image/...` sources; table merges remain outside
the V0.2 Contract.

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
  validate.json
  issues.json
  result.json
  visual-review.json
  comparisons/
    slide-001.png
    ...
```

Only combined per-slide Comparison Images are retained; source and output
screenshots are temporary build inputs. `visual-review.json` is seeded with a
complete image inventory and immutable hashes. An independent reviewer marks
every slide and records only `major` or `minor` findings. A major finding
requires an actionable revision instruction. `finalize` verifies the exact
build identity, HTML/PPTX hashes, comparison paths and hashes, and slide
coverage before deriving its outcome. It does not rebuild or rerender.

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
OfficeCLI projection experiments and the Algeria deck remain internal release
regression assets. The MIT license and upstream history are preserved.
