---
status: accepted
---

# Export one hidden projection seam for the V0.4.1 probe

The V0.4.1 feasibility probe needs a caller to be able to go from an existing
PPTX to Canonical Author HTML, and it needs that path to be exercisable without
inspecting source. It must not, however, become a formal product capability: no
public command, no package-version change, and no new `capabilities` entry
belong to this work.

So exactly one function is exported —
`project_pptx_to_author_html(source_pptx, source_slide_numbers, output_html, proxy_dir=...)`
— together with the result and failure types it returns. It is deliberately
absent from `PUBLIC_COMMANDS` and from the capability manifest, which is why it
lives in the import namespace rather than behind the CLI: it is reachable by the
agent running the probe and by tests, and invisible to the product's supported
command surface.

Two consequences follow, and both are the point:

- **The reader stays private.** The OfficeCLI command shapes, the object-capture
  DTOs, the classification rules and the emitter are all implementation. A test
  or future caller drives the seam, not `get`/`query`/`view` orchestration, so
  the reader can be replaced — or its OfficeCLI usage reworked — without a
  compatibility promise. The spec's requirement that OfficeCLI implementation
  details stay hidden behind the seam is enforced by there being nothing else to
  import.
- **The seam accepts the PPTX as the sole presentation input.** Because the only
  entry point takes a deck path and slide numbers, an OfficeHTML export cannot
  become a hidden prerequisite: there is no parameter through which one could be
  passed, and no profile in which one could be read.

`tests/test_v041_projection_seam.py` imports the seam from
`officecli_html_to_pptx` and never touches the private modules, which keeps the
boundary honest rather than aspirational.

## A locked visual proxy is a render of the object alone

The same probe produces locked visual proxies, and their definition belongs to
this decision because it is the thing a reviewer is most likely to misread. A
proxy is an image of **one** source object, obtained by rendering a derived
working deck in which that object is the only object left on its slide.

Cropping the composited slide raster is explicitly rejected. It is the obvious
implementation — one render per slide, one crop per object — and it is wrong:
any sibling painted inside the target's rectangle is captured with it. On the
probe deck that meant a filled ellipse's proxy carried the text boxes layered
over it, while those same text boxes were also emitted as canonical text
objects, so the deck painted those words twice. Character-level readback could
not see it, because the duplicate lived inside image bytes. A representation
that contains another object's paint is not object-local whatever its rectangle
is, and must never be published as a proxy: when isolation fails, the object is
classified `unsupported` with a blocking diagnostic instead.
