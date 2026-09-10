"""Example: build an Author HTML deck through the V0.2 application API."""

import asyncio
from officecli_html_to_pptx import build_author_html


async def main():
    result = await build_author_html("demo.html", "demo.pptx")
    print(result.to_json())


asyncio.run(main())
