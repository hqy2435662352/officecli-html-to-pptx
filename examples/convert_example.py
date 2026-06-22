"""Example: convert an HTML slide deck to PPTX using the Python API."""

import asyncio
from html_to_pptx import convert


async def main():
    output = await convert("demo.html", "demo.pptx")
    print(f"Created {output}")


asyncio.run(main())
