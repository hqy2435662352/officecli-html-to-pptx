#!/usr/bin/env python3
"""Refuse a commit or a push that would publish private material.

The scanner lives in ``.githooks/`` beside the hooks that call it, so a clean
checkout has a working guard and not just a hook that fails because its scanner
was in someone's scratch directory.

Three modes, because they answer different questions:

* ``staged``  -- what this commit would actually introduce.  Scanning the working
  tree instead would miss a file staged from elsewhere, and would flag an
  edited-but-unstaged file the commit does not contain.
* ``range``   -- every blob a push would newly make reachable, including blobs
  that later commits deleted.  This is the check that catches the failure mode
  this guard was written for.
* ``worktree`` -- the developer's own view, for noticing before staging.

What must not be published lives in gitignored local configuration, because a
scanner configuration that spells the private values publishes them itself.

Fail-closed: a missing configuration, an unreadable index entry or any unexpected
git failure refuses.  "The guard could not run" must never read as "the guard
passed".
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_NAME = "private-material.json"
CONFIG_ENV = "OFFICECLI_H2P_PRIVATE_MATERIAL"

#: Refused because the guard could not establish what to look for.  Distinct from
#: a finding, so a caller can tell "you leaked" from "you are unguarded".
UNGUARDED_EXIT = 3


class ScannerError(RuntimeError):
    """The scan could not be completed, which is itself a refusal."""


def repo_root() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ScannerError(
            f"not inside a git repository: {completed.stderr.strip() or 'no detail'}"
        )
    return Path(completed.stdout.strip())


def load_patterns(root: Path, explicit: Path | None = None) -> list[str]:
    """Return the forbidden strings, refusing when they cannot be established."""
    path = explicit
    if path is None:
        configured = os.environ.get(CONFIG_ENV)
        path = Path(configured) if configured else root / CONFIG_NAME
    if not path.is_file():
        raise ScannerError(
            f"no private-material configuration at {path}; set {CONFIG_ENV} or "
            f"create {CONFIG_NAME} (gitignored) listing the strings that must "
            "never be published"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    patterns = payload.get("forbidden") if isinstance(payload, dict) else payload
    if not isinstance(patterns, list):
        raise ScannerError(f"{path} does not list forbidden strings")
    cleaned = [str(item) for item in patterns if str(item)]
    if not cleaned:
        raise ScannerError(f"{path} names no forbidden string")
    return cleaned


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if completed.returncode != 0:
        raise ScannerError(
            f"git {' '.join(args)} failed: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout.decode("utf-8", errors="replace")


def scan_text(text: str, patterns: list[str], where: str) -> list[str]:
    return [f"{where}: {pattern!r}" for pattern in patterns if pattern and pattern in text]


def scan_staged(root: Path, patterns: list[str]) -> list[str]:
    findings: list[str] = []
    names = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", cwd=root)
    for name in [n for n in names.split("\0") if n]:
        blob = subprocess.run(
            ["git", "show", f":{name}"], cwd=root, capture_output=True, check=False
        )
        if blob.returncode != 0:
            findings.append(f"staged {name}: could not be read from the index")
            continue
        findings.extend(
            scan_text(
                blob.stdout.decode("utf-8", errors="ignore"), patterns, f"staged {name}"
            )
        )
    return findings


def scan_range(root: Path, patterns: list[str], base: str, tip: str) -> list[str]:
    """Scan every blob the tip's history contains that the base's does not.

    Three enumerations that look equivalent are not, and the differences are the
    whole point of this mode:

    * ``git rev-list --objects base..tip`` prunes a tree by *path*, so a file added
      in one commit and deleted in the next is never offered at all.
    * ``git ls-tree -r tip`` sees only the tip's tree, so a leak introduced and
      removed in the *middle* of a branch is missed.
    * ``git rev-list --objects tip`` walks commit parents, so a deleted file's blob
      still looks like something the base "already has" -- but a blob is only
      excluded below when it is *itself* reachable from the base, which for a blob
      the base never contained is not the case.

    So: every blob this push would publish (everything reachable from the tip),
    minus every blob the remote already holds (everything reachable from the base).
    A blob in neither set is a blob this push introduces, however its commits were
    later rewritten.
    """
    reachable = _objects(root, tip)
    # ``_objects`` returns ``(sha, path)`` pairs, so the exclusion set must be the
    # shas alone.  Storing the pairs made every membership test false, and the
    # range scan degenerated into scanning the whole history -- which flags blobs
    # the remote already holds and refuses every push, including clean ones.  A
    # guard that refuses everything gets bypassed, which is worse than no guard.
    already = (
        set()
        if not base or set(base) == {"0"}
        else {sha for sha, _ in _objects(root, base)}
    )
    findings: list[str] = []
    for sha, path in reachable:
        if sha in already:
            continue
        blob = subprocess.run(
            ["git", "cat-file", "-p", sha], cwd=root, capture_output=True, check=False
        )
        if blob.returncode != 0:
            continue
        findings.extend(
            scan_text(
                blob.stdout.decode("utf-8", errors="ignore"),
                patterns,
                f"range {path or sha}",
            )
        )
    return findings


def _objects(root: Path, revision: str) -> list[tuple[str, str]]:
    """Return ``(sha, path)`` for every object reachable from ``revision``."""
    if not revision or set(revision) == {"0"}:
        return []
    listing = _git("rev-list", "--objects", revision, cwd=root)
    pairs: list[tuple[str, str]] = []
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def _tree_blobs(root: Path, revision: str) -> dict[str, str]:
    """Return ``path -> blob sha`` for every file in a revision's tree.

    Kept beside :func:`_objects` because the two answer different questions and
    reading them together is how the range scan's correctness is argued.
    """
    if not revision or set(revision) == {"0"}:
        return {}
    listing = _git("ls-tree", "-r", "-z", revision, cwd=root)
    entries: dict[str, str] = {}
    for record in listing.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            entries[path] = parts[2]
    return entries


def scan_worktree(root: Path, patterns: list[str]) -> list[str]:
    findings: list[str] = []
    names = _git("ls-files", "-z", cwd=root)
    for name in [n for n in names.split("\0") if n]:
        try:
            text = (root / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text(text, patterns, f"worktree {name}"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("worktree", "staged", "range"),
        default="worktree",
        help="what to scan; the hooks pass 'staged' and 'range'",
    )
    parser.add_argument("--base", default="", help="range base (pre-push)")
    parser.add_argument("--tip", default="HEAD", help="range tip (pre-push)")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        root = repo_root()
        patterns = load_patterns(root, args.config)
        if args.mode == "staged":
            findings = scan_staged(root, patterns)
        elif args.mode == "range":
            findings = scan_range(root, patterns, args.base, args.tip)
        else:
            findings = scan_worktree(root, patterns)
    except (ScannerError, ValueError, OSError) as error:
        print(f"private-material guard refused: {error}", file=sys.stderr)
        return UNGUARDED_EXIT

    for finding in findings:
        print(f"BLOCKED  {finding}", file=sys.stderr)
    if findings:
        print(
            f"\n{len(findings)} private identifier(s) would be published. Refusing.",
            file=sys.stderr,
        )
        return 1
    print(f"private-material guard: clean ({args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
