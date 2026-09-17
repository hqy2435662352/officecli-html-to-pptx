#!/usr/bin/env python3
"""Wire the repository's guard hooks into this clone, and prove they are wired.

A hook file in the working tree is a document, not a gate: git only runs what
`core.hooksPath` points at, and that setting lives in `.git/config`, which is not
cloned.  The guard therefore has to be *installed* once per clone — and the test
suite fails loudly when it has not been, because a guard that silently does not run
is the exact failure this project already made once.

    python scripts/install_hooks.py

It is idempotent, it verifies what it did, and it refuses rather than pretending
when the hook files are missing or are not executable in the index.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS_PATH = ".githooks"
REQUIRED = ("pre-commit", "pre-push")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the wiring without changing anything",
    )
    args = parser.parse_args(argv)

    for name in REQUIRED:
        path = REPO / HOOKS_PATH / name
        if not path.is_file():
            print(f"refusing: {HOOKS_PATH}/{name} is missing from the working tree")
            return 2

    # The executable bit is read from the index, not the filesystem: on Windows a
    # checked-out file has no POSIX mode, so a filesystem check would report every
    # hook as non-executable here while a Linux clone got the right bit from git.
    staged = _git("ls-files", "-s", HOOKS_PATH)
    if staged.returncode != 0:
        print(f"refusing: git ls-files failed: {staged.stderr.strip()}")
        return 2
    modes = {}
    for line in staged.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            modes[parts[3].strip()] = parts[0]
    for name in REQUIRED:
        tracked = f"{HOOKS_PATH}/{name}"
        if tracked not in modes:
            print(f"refusing: {tracked} is not tracked by git")
            return 2
        if modes[tracked] != "100755":
            print(f"refusing: {tracked} is mode {modes[tracked]}, not 100755")
            return 2

    configured = _git("config", "--get", "core.hooksPath")
    current = configured.stdout.strip()
    if args.check:
        if current != HOOKS_PATH:
            print(
                f"not installed: core.hooksPath is {current or '(unset)'}, so no "
                f"hook runs.  Run `python scripts/install_hooks.py`."
            )
            return 1
        print(f"installed: core.hooksPath={current}")
        return 0

    if current == HOOKS_PATH:
        print(f"already installed: core.hooksPath={current}")
    else:
        written = _git("config", "core.hooksPath", HOOKS_PATH)
        if written.returncode != 0:
            print(f"refusing: could not set core.hooksPath: {written.stderr.strip()}")
            return 2
        print(
            f"installed: core.hooksPath={HOOKS_PATH} "
            f"(was {current or '(unset)'})"
        )

    verified = _git("config", "--get", "core.hooksPath").stdout.strip()
    if verified != HOOKS_PATH:
        print(f"refusing: the setting did not take: {verified!r}")
        return 2
    print(
        "the guard now runs on this clone's commits and pushes; "
        "the test suite fails if it is unwired"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
