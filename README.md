# html-to-pptx

Convert HTML slide decks into editable PowerPoint files.

Unlike screenshot-based approaches that produce flat images, `html-to-pptx` measures every DOM element in a headless browser and maps it to a native PPTX shape — text boxes you can edit, images you can resize, backgrounds you can restyle. The output is a real presentation, not a picture of one.

## Install

```bash
pip install html-to-pptx
python -m playwright install chromium
```

## Quick start

### CLI

```bash
html-to-pptx deck.html deck.pptx
```

### Python

```python
import asyncio
from html_to_pptx import convert

asyncio.run(convert("deck.html", "deck.pptx"))
```

### Two-stage API

For more control, separate the measurement and rendering steps:

```python
import asyncio
from html_to_pptx import extract_measurements, render_pptx

async def main():
    # Stage 1: measure DOM elements in a headless browser
    measurements = await extract_measurements("deck.html")

    # Stage 2: render measurements to python-pptx shapes
    prs = render_pptx(measurements)

    # Modify the presentation before saving
    prs.slides[0].shapes[0].text = "Custom title"
    prs.save("deck.pptx")

asyncio.run(main())
```

## HTML format

Your HTML file should contain `<section class="slide">` elements at a 1920×1080 canvas:

```html
<!DOCTYPE html>
<html>
<head>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; overflow: hidden; }
    .slide {
        width: 1920px;
        height: 1080px;
        display: none;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        font-family: sans-serif;
    }
    .slide.active { display: flex; }
</style>
</head>
<body>

<section class="slide active" style="background-color: #1e293b;">
    <h1 style="font-size: 64px; color: #f8fafc;">Hello World</h1>
</section>

<section class="slide" style="background-color: #ffffff;">
    <p style="font-size: 24px; color: #334155;">Second slide</p>
</section>

</body>
</html>
```

See [`examples/demo.html`](examples/demo.html) for a full five-slide deck.

## What gets converted

| HTML feature | PPTX output |
|---|---|
| Text with fonts, colors, weight, style | Editable text boxes with matching font properties |
| Background colors | Solid fills (with alpha transparency) |
| Rounded corners (`border-radius`) | OOXML adjustment guides on rounded rectangles |
| Base64-embedded images (`data:image/...`) | Native picture shapes |
| Borders | Shape outlines with color and width |
| Left-border accent bars | Separate narrow rectangle shapes |
| `text-transform` (uppercase, etc.) | Transformed text content |
| Hyperlinks | Preserved on text runs |
| Ordered/unordered lists | Bullet/number prefixes with marker colors |
| Element opacity | OOXML alpha on fill colors |

## How it works

```
HTML file
    │
    ▼
┌─────────────────────────┐
│  Headless Chromium       │  ← Playwright loads the HTML at 1920×1080
│  (Playwright)            │
│                          │
│  For each .slide:        │
│  • Show slide in isolation│
│  • Clear CSS transforms  │
│  • Measure every visible │
│    element recursively:  │
│    position, size, color,│
│    font, text, images    │
└───────────┬─────────────┘
            │
            ▼
    Measurement tree (JSON)
            │
            ▼
┌─────────────────────────┐
│  python-pptx renderer    │
│                          │
│  For each element:       │
│  • Text leaf → text box  │
│  • Image → picture shape │
│  • Background → rectangle│
│  • Border → outline/shape│
│                          │
│  Coordinates:            │
│  CSS px → inches using   │
│  13.333/1920 ratio       │
└───────────┬─────────────┘
            │
            ▼
      Editable .pptx
```

## Visual comparison tool

Verify conversion quality with side-by-side comparisons:

```bash
pip install html-to-pptx[compare]
html-to-pptx-compare deck.html -o results/
```

This screenshots the original HTML, converts to PPTX, renders the PPTX back to images via LibreOffice, and creates side-by-side comparison PNGs. Requires [LibreOffice](https://www.libreoffice.org/) on PATH.

Output structure:
```
results/deck/
├── html_slide_0.png      # ground truth (HTML screenshot)
├── html_slide_1.png
├── pptx_slide_0.png      # converter output (PPTX rendered via LibreOffice)
├── pptx_slide_1.png
├── compare_slide_0.png   # side-by-side comparison
├── compare_slide_1.png
└── output.pptx           # the generated file
```

## Limitations

- **External images** are not fetched — use base64 `data:` URIs for embedded images
- **CSS gradients** are captured as the computed `backgroundColor` (solid), not as gradient fills
- **Animations and transitions** are not represented in PPTX
- **Font availability** — the PPTX references font names from the HTML; if those fonts aren't installed on the machine opening the file, PowerPoint will substitute
- **Complex CSS layouts** (grid, advanced flexbox) are measured as-rendered, but deeply nested layouts may lose some positioning precision

## Development

```bash
git clone https://github.com/Design-Arena/html-to-pptx.git
cd html-to-pptx
pip install -e ".[dev]"
python -m playwright install chromium
pytest -v
```

## License

MIT
