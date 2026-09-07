"""Convert HTML slide decks to editable PowerPoint files.

Usage::

    import asyncio
    from html_to_pptx import convert

    asyncio.run(convert("deck.html", "deck.pptx"))

Or use the two-stage API for more control::

    from html_to_pptx import extract_measurements, render_pptx

    measurements = asyncio.run(extract_measurements("deck.html"))
    prs = render_pptx(measurements)
    prs.save("deck.pptx")
"""

from importlib.metadata import version

from html_to_pptx.converter import convert, extract_measurements, render_pptx
from html_to_pptx.officecli_compiler import (
    CompilationDiagnostic,
    OfficeCLICompilationError,
    OfficeCLICompilationResult,
    compile_officecli,
)

__all__ = [
    "convert",
    "extract_measurements",
    "render_pptx",
    "compile_officecli",
    "CompilationDiagnostic",
    "OfficeCLICompilationError",
    "OfficeCLICompilationResult",
]
__version__ = version("html-to-pptx")
