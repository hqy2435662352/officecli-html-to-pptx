"""Command-line interface for html-to-pptx."""

from __future__ import annotations

import argparse
import asyncio
import logging


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="html-to-pptx",
        description="Convert an HTML slide deck to an editable PPTX file.",
    )
    parser.add_argument("input", help="Path to the HTML slide deck")
    parser.add_argument(
        "output",
        nargs="?",
        default="output.pptx",
        help="Output .pptx path (default: output.pptx)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from html_to_pptx.converter import convert

    asyncio.run(convert(args.input, args.output))


if __name__ == "__main__":
    main()
