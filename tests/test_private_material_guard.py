"""Prove the private-material guard blocks, in a throwaway repository.

A guard that has never been seen to refuse is a guard nobody can rely on, and the
failure this one exists to catch -- a private string committed in one commit and
deleted in the next -- is invisible to any check that only looks at the tip.

Every case runs against a temporary repository built for it, so the test never
depends on this repository's own history and never writes to it.  The strings are
synthetic: the real forbidden values live in gitignored local configuration, and a
test that spelled them would publish them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / ".githooks" / "private_material_guard.py"

#: A value that stands in for a private identifier.  Synthetic on purpose.
SECRET = "SYNTHETIC-PRIVATE-TOKEN-9c1f"
OTHER_SECRET = "SYNTHETIC-PRIVATE-TOKEN-4b7e"

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10), reason="the guard targets the product's Python floor"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def _guard(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repository with the guard's configuration and no history."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "guard@example.invalid")
    _git(tmp_path, "config", "user.name", "guard test")
    (tmp_path / "private-material.json").write_text(
        json.dumps({"forbidden": [SECRET, OTHER_SECRET]}), encoding="utf-8"
    )
    (tmp_path / "keep.txt").write_text("nothing private here\n", encoding="utf-8")
    _git(tmp_path, "add", "keep.txt")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_the_guard_passes_a_clean_tree(repo: Path) -> None:
    result = _guard(repo, "--mode", "worktree")
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_a_staged_private_string_blocks_the_commit(repo: Path) -> None:
    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    result = _guard(repo, "--mode", "staged")
    assert result.returncode == 1, result.stdout
    assert SECRET in result.stderr


def test_the_working_tree_mode_does_not_see_the_index(repo: Path) -> None:
    """The two modes answer different questions, and this proves they differ.

    A file that is staged but has since been cleaned on disk is still what the
    commit would contain, so ``staged`` must flag it while ``worktree`` does not.
    A guard that scanned only the working tree would let it through.
    """
    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    (repo / "leak.txt").write_text("cleaned\n", encoding="utf-8")
    assert _guard(repo, "--mode", "worktree").returncode == 0
    assert _guard(repo, "--mode", "staged").returncode == 1


def test_a_deleted_leak_still_blocks_the_push(repo: Path) -> None:
    """The failure mode this guard was written for.

    The leak is committed and then deleted.  The tip is clean and the working tree
    is clean; the private string is still in the range a push would publish.  Only
    a range scan sees it, which is why the working-tree check alone was not enough
    the first time.
    """
    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-q", "-m", "introduce a leak")
    leak_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "rm", "-q", "leak.txt")
    _git(repo, "commit", "-q", "-m", "remove the leak")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # The tip is clean by every other measure.
    assert SECRET not in (repo / "keep.txt").read_text(encoding="utf-8")
    assert _guard(repo, "--mode", "worktree").returncode == 0

    # And the range still refuses.
    result = _guard(repo, "--mode", "range", "--base", leak_commit, "--tip", tip)
    assert result.returncode == 1, result.stdout
    assert SECRET in result.stderr


def test_a_range_that_does_not_contain_the_leak_passes(repo: Path) -> None:
    """The range check is not vacuous: a clean range is allowed through."""
    (repo / "fine.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "fine.txt")
    _git(repo, "commit", "-q", "-m", "ordinary change")
    base = _git(repo, "rev-parse", "HEAD~1").stdout.strip()
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    result = _guard(repo, "--mode", "range", "--base", base, "--tip", tip)
    assert result.returncode == 0, result.stderr


def test_a_new_branch_range_scans_everything_reachable(repo: Path) -> None:
    """An all-zero base means the ref does not exist yet, so all of it publishes."""
    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-q", "-m", "leak on a new branch")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    result = _guard(repo, "--mode", "range", "--base", "0" * 40, "--tip", tip)
    assert result.returncode == 1, result.stdout


def test_ignored_local_evidence_is_not_a_finding(repo: Path) -> None:
    """Local-only material is expected to contain private values.

    The guard reports what a *commit or push* would publish, so an ignored file
    holding the real values must not make every operation fail -- otherwise the
    only way to work is to stop running the guard.
    """
    (repo / ".gitignore").write_text("acceptance/local/\n", encoding="utf-8")
    local = repo / "acceptance" / "local"
    local.mkdir(parents=True)
    (local / "source-verification.json").write_text(
        json.dumps({"path": SECRET}), encoding="utf-8"
    )
    assert _guard(repo, "--mode", "worktree").returncode == 0
    assert _guard(repo, "--mode", "staged").returncode == 0


def test_a_missing_configuration_refuses_rather_than_passing(repo: Path) -> None:
    """Fail closed: an unguarded tree must not read as a clean one."""
    (repo / "private-material.json").unlink()
    result = _guard(repo, "--mode", "worktree")
    assert result.returncode == 3, (result.returncode, result.stdout)
    assert "refused" in result.stderr


def test_an_empty_configuration_refuses_rather_than_passing(repo: Path) -> None:
    (repo / "private-material.json").write_text(
        json.dumps({"forbidden": []}), encoding="utf-8"
    )
    assert _guard(repo, "--mode", "worktree").returncode == 3


def test_a_scanner_error_refuses_rather_than_passing(tmp_path: Path) -> None:
    """Outside a repository the guard cannot answer, so it refuses."""
    result = subprocess.run(
        [sys.executable, str(GUARD), "--mode", "worktree"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3, (result.returncode, result.stdout)
    assert "refused" in result.stderr


def test_the_hooks_are_installed_and_executable() -> None:
    """A hook that is not wired into git is a document, not a gate.

    This is the check the earlier claim ("the guard now runs before every commit")
    would have failed: the scanner existed and was run by hand.

    The executable bit is read from the **index**, not the filesystem.  On Windows
    a checked-out file has no POSIX mode at all, so a filesystem check would report
    every hook as non-executable on the development machine while a Linux clone
    got the right bit from git -- the test would be measuring the wrong thing and
    would fail for the wrong reason.
    """
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hooks_path = configured.stdout.strip()
    assert hooks_path, "core.hooksPath is not set, so no hook runs"

    staged = subprocess.run(
        ["git", "ls-files", "-s", hooks_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    modes = {}
    for line in staged.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            modes[parts[3].strip()] = parts[0]

    for name in ("pre-commit", "pre-push"):
        path = f"{hooks_path}/{name}"
        assert path in modes, f"{path} is not tracked"
        assert modes[path] == "100755", f"{path} is mode {modes[path]}, not 100755"

        hook = REPO_ROOT / hooks_path / name
        body = hook.read_text(encoding="utf-8")
        # The hook must call the guard, and must refuse when it cannot.
        assert "private_material_guard.py" in body
        assert "exit 3" in body or "refused" in body
        # POSIX shell scripts must not be CRLF: a shebang ending in CR does not
        # run, so a hook that works here would fail on a Linux clone.
        assert b"\r\n" not in hook.read_bytes(), f"{path} has CRLF line endings"
