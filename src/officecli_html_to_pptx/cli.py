"""The public ``officecli-html-to-pptx`` command."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping

from .application import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)
from .protocol import CommandResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="officecli-html-to-pptx",
        description=(
            "Build a new editable PowerPoint from Contract-checked Author HTML. "
            "Every command can return one JSON result envelope with --json."
        ),
        epilog=(
            "Exit classes: 0 operation completed; 2 actionable block or "
            "revision; 3 invalid invocation/input; 4 unexpected execution failure."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    capabilities = subparsers.add_parser(
        "capabilities",
        help="Describe formal Author support and the Rendering Compatibility Pair.",
    )
    capabilities.add_argument("--json", action="store_true", help="Write one JSON envelope to stdout.")

    doctor = subparsers.add_parser(
        "doctor",
        help="Read-only inspect the required local runtime and writable locations.",
    )
    doctor.add_argument("--output", help="Optional requested output path to inspect.")
    doctor.add_argument("--temp-dir", help="Optional temporary directory to inspect.")
    doctor.add_argument("--json", action="store_true", help="Write one JSON envelope to stdout.")

    check = subparsers.add_parser(
        "check",
        help="Check one Candidate HTML file against the Author Contract.",
    )
    check.add_argument("input", help="Candidate or Author HTML path.")
    check.add_argument("--json", action="store_true", help="Write one JSON envelope to stdout.")

    build = subparsers.add_parser(
        "build",
        help="Build one non-overwriting PPTX and matching Evidence Bundle.",
    )
    build.add_argument("input", help="Author HTML path that has passed check.")
    build.add_argument("output", help="New .pptx output path; its .evidence/ path is derived.")
    build.add_argument("--json", action="store_true", help="Write one JSON envelope to stdout.")

    finalize = subparsers.add_parser(
        "finalize",
        help="Validate an edited Visual Review and derive its final outcome.",
    )
    finalize.add_argument("evidence", help="The exact .evidence directory from build.")
    finalize.add_argument("--json", action="store_true", help="Write one JSON envelope to stdout.")
    return parser


def _write_human(result: CommandResult) -> None:
    """Keep human output concise and keep diagnostics off the JSON channel."""
    print(f"{result.command}: {result.status}")
    for name, artifact in result.artifacts.items():
        if hasattr(artifact, "path"):
            print(f"{name}: {artifact.path}")
        elif isinstance(artifact, Mapping):
            path = artifact.get("path")
            if path:
                print(f"{name}: {path}")
        else:
            print(f"{name}: {artifact}")
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.severity}: {diagnostic.message}", file=sys.stderr)


def _emit(result: CommandResult, json_mode: bool) -> int:
    if json_mode:
        print(result.to_json())
    else:
        _write_human(result)
    return result.exit_code


def _invalid_invocation(message: str, *, json_mode: bool = False) -> int:
    from .protocol import Diagnostic, result

    envelope = result(
        "invocation",
        "ERROR",
        diagnostics=(
            Diagnostic(
                code="invalid_invocation",
                severity="error",
                message=message,
                blocking=True,
                remediation="Run officecli-html-to-pptx --help for the supported commands.",
                recheck="officecli-html-to-pptx --help",
            ),
        ),
    )
    return _emit(envelope, json_mode)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = int(exc.code)
        if code != 0 and argv is not None and "--json" in argv:
            return _invalid_invocation("Invalid command invocation.", json_mode=True)
        return code if code == 0 else 3

    if args.command is None:
        return _invalid_invocation("A public command is required.")

    json_mode = bool(getattr(args, "json", False))
    if args.command == "capabilities":
        return _emit(get_capabilities(), json_mode)
    if args.command == "doctor":
        return _emit(diagnose_environment(args.output, args.temp_dir), json_mode)
    if args.command == "check":
        return _emit(check_author_html(args.input), json_mode)
    if args.command == "build":
        return _emit(asyncio.run(build_author_html(args.input, args.output)), json_mode)
    if args.command == "finalize":
        return _emit(finalize_build(args.evidence), json_mode)
    return _invalid_invocation(f"Unsupported command: {args.command!r}", json_mode=json_mode)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
