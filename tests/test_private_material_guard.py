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
import shutil
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
    """A throwaway repository with the guard's configuration and no history.

    It carries the real hooks and scanner, so a test can run the hook the way git
    runs it rather than only the scanner the hook calls.
    """
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "guard@example.invalid")
    _git(tmp_path, "config", "user.name", "guard test")
    (tmp_path / "private-material.json").write_text(
        json.dumps({"forbidden": [SECRET, OTHER_SECRET]}), encoding="utf-8"
    )
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    for name in ("pre-commit", "pre-push", "private_material_guard.py"):
        shutil.copy2(REPO_ROOT / ".githooks" / name, hooks / name)
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
    # The base the remote already holds is the state *before* the leak, so the
    # range is exactly the leak and its removal.
    base = _git(repo, "rev-parse", "HEAD~1").stdout.strip()
    _git(repo, "rm", "-q", "leak.txt")
    _git(repo, "commit", "-q", "-m", "remove the leak")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # The tip is clean by every other measure.
    assert not (repo / "leak.txt").exists()
    assert _guard(repo, "--mode", "worktree").returncode == 0

    # And the range still refuses.
    result = _guard(repo, "--mode", "range", "--base", base, "--tip", tip)
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


def test_a_leak_the_base_already_publishes_is_not_this_pushs_finding(repo: Path) -> None:
    """Blobs the remote already holds are excluded, so a clean push is not refused.

    A guard that refuses every push gets bypassed, which is worse than no guard.
    This pins the exclusion: the leak is committed *before* the base, so the base
    already publishes it and this range introduces nothing.  The exclusion set used
    to hold ``(sha, path)`` pairs rather than shas, which made every membership test
    false and turned the range scan into a whole-history scan.
    """
    (repo / "old.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-q", "-m", "an inherited leak")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "new.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-q", "-m", "an ordinary change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = _guard(repo, "--mode", "range", "--base", base, "--tip", tip)
    assert result.returncode == 0, result.stderr


def test_a_new_branch_range_scans_everything_reachable(repo: Path) -> None:
    """An all-zero base with no other base means the ref does not exist yet.

    With a repository that has published nothing, everything reachable from the tip
    is newly published -- so the leak that predates the branch is a finding, and the
    scan is not vacuous just because the base is empty.
    """
    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-q", "-m", "leak on a new branch")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    result = _guard(repo, "--mode", "range", "--base", "0" * 40, "--tip", tip)
    assert result.returncode == 1, result.stdout


def test_a_new_branch_that_reuses_a_published_leak_passes(repo: Path) -> None:
    """A new ref's base is what the remote already holds, not nothing.

    The remote does not have the *ref*; it has the *repository*.  Passing every ref
    the remote holds as a base is what makes a branch off a history that already
    contains a published identifier pushable at all -- without it, no new branch could
    ever be pushed from this repository, which is how the defect was found: the guard
    refused a clean one-commit follow-up branch because `main`'s own history carries
    an inherited absolute path.

    The union is the two properties together: the inherited blob is not a finding for
    this push, and a string *this* branch introduces still is.
    """
    (repo / "published.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "published.txt")
    _git(repo, "commit", "-q", "-m", "an identifier the remote already holds")
    published = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "branch.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "branch.txt")
    _git(repo, "commit", "-q", "-m", "the branch's own change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # The ref is new (all-zero base) but the remote holds `published`.
    result = _guard(
        repo,
        "--mode",
        "range",
        "--base",
        "0" * 40,
        "--base",
        published,
        "--tip",
        tip,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # And the same shape with a string this branch introduces is still refused.
    (repo / "mine.txt").write_text(f"token={OTHER_SECRET}\n", encoding="utf-8")
    _git(repo, "add", "mine.txt")
    _git(repo, "commit", "-q", "-m", "this branch introduces a new identifier")
    leaked_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    refused = _guard(
        repo,
        "--mode",
        "range",
        "--base",
        "0" * 40,
        "--base",
        published,
        "--tip",
        leaked_tip,
    )
    assert refused.returncode == 1, refused.stdout


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


def test_the_installer_wires_a_clone_that_has_never_been_wired(tmp_path: Path) -> None:
    """The installer is proved on a clone with no configuration, not on this one.

    ``core.hooksPath`` lives in ``.git/config``, which is not cloned, so the state of
    *this* checkout is not something a test may assume: CI ran this suite in a fresh
    clone and every job failed on the assertion below until the workflow wired the
    gate in its own setup step.  The repository's own property -- that the installer
    exists, is tracked, and does the wiring -- is what has to hold anywhere, so it is
    proved here on a temporary clone created for the purpose.
    """
    installer = REPO_ROOT / "scripts" / "install_hooks.py"
    assert installer.is_file(), "scripts/install_hooks.py is missing"

    clone = tmp_path / "clone"
    clone.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=clone, check=True)
    hooks = clone / ".githooks"
    hooks.mkdir()
    names = ("pre-commit", "pre-push", "private_material_guard.py")
    for name in names:
        shutil.copy2(REPO_ROOT / ".githooks" / name, hooks / name)
    scripts = clone / "scripts"
    scripts.mkdir()
    shutil.copy2(installer, scripts / "install_hooks.py")

    # The installer refuses to report health for hooks git does not track, or that
    # are tracked without the executable bit a clone needs -- so the clone has to be
    # a real one: the hooks committed, at the mode the repository stores.
    subprocess.run(
        ["git", "add", "--", "scripts/install_hooks.py", "scripts/install_hooks.py"],
        cwd=clone,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--chmod=+x",
            *(f".githooks/{name}" for name in names),
        ],
        cwd=clone,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=guard@example.invalid",
            "-c",
            "user.name=guard",
            "commit",
            "--quiet",
            "-m",
            "hooks",
        ],
        cwd=clone,
        check=True,
    )

    # Nothing is wired in the new clone, and the installer says so instead of
    # reporting health it does not have.
    before = subprocess.run(
        [sys.executable, str(scripts / "install_hooks.py"), "--check"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    )
    assert before.returncode == 1, before.stdout + before.stderr
    assert "not installed" in before.stdout

    installed = subprocess.run(
        [sys.executable, str(scripts / "install_hooks.py")],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert configured == ".githooks", configured

    after = subprocess.run(
        [sys.executable, str(scripts / "install_hooks.py"), "--check"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    )
    assert after.returncode == 0, after.stdout + after.stderr


def test_the_hooks_are_installed_and_executable() -> None:
    """A hook that is not wired into git is a document, not a gate.

    This is the check the earlier claim ("the guard now runs before every commit")
    would have failed: the scanner existed and was run by hand.

    The executable bit is read from the **index**, not the filesystem.  On Windows
    a checked-out file has no POSIX mode at all, so a filesystem check would report
    every hook as non-executable on the development machine while a Linux clone
    got the right bit from git -- the test would be measuring the wrong thing and
    would fail for the wrong reason.

    ``core.hooksPath`` lives in ``.git/config``, which is not cloned, so this
    assertion is about the clone it runs in: a fresh checkout fails it until
    ``python scripts/install_hooks.py`` has been run once.  That is deliberate --
    the failure is loud and it names the command -- and CI runs that command in its
    own setup step rather than letting the suite tolerate an unwired clone.  The
    installer's own behaviour is proved separately, on a clone built for it, by
    ``test_the_installer_wires_a_clone_that_has_never_been_wired``.
    """
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hooks_path = configured.stdout.strip()
    assert hooks_path, (
        "core.hooksPath is not set, so no hook runs in this clone; run "
        "`python scripts/install_hooks.py`"
    )

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


def test_the_hooks_installer_is_tracked_and_reports_the_wiring() -> None:
    """The wiring step is a command in the repository, not a paragraph in a doc.

    A fresh clone has no hooks until something sets ``core.hooksPath``, so the
    repository has to ship the something.  This asserts the installer exists, that
    git tracks it, and that its ``--check`` mode agrees with the clone it runs in
    -- so the setup step cannot rot into a stale instruction.
    """
    installer = REPO_ROOT / "scripts" / "install_hooks.py"
    assert installer.is_file(), "scripts/install_hooks.py is missing"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "scripts/install_hooks.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, "scripts/install_hooks.py is not tracked by git"

    checked = subprocess.run(
        [sys.executable, str(installer), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if configured:
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert "installed" in checked.stdout
    else:
        # Nothing is wired, and the installer must say so rather than claim health.
        assert checked.returncode == 1, checked.stdout
        assert "not installed" in checked.stdout


def test_every_command_the_installer_prints_exists() -> None:
    """A hint that names a file the repository does not carry is a trap.

    The installer told a reader to run `python scripts/install-hooks.py` -- with a
    hyphen -- and no such file exists, so the one command it offers for fixing an
    unwired clone failed if followed.  Every `scripts/...` path either hook or
    message mentions is checked here against the working tree.
    """
    import re as _re

    for name in ("install_hooks.py",):
        source = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        for reference in set(_re.findall(r"scripts/[A-Za-z0-9_.-]+\.py", source)):
            assert (REPO_ROOT / reference).is_file(), (
                f"{name} tells a reader to run `{reference}`, which the repository "
                "does not carry"
            )

    for hook in ("pre-commit", "pre-push"):
        source = (REPO_ROOT / ".githooks" / hook).read_text(encoding="utf-8")
        for reference in set(_re.findall(r"scripts/[A-Za-z0-9_.-]+\.py", source)):
            assert (REPO_ROOT / reference).is_file(), (
                f"{hook} refers to `{reference}`, which the repository does not carry"
            )


# ---------------------------------------------------------------------------
# The hook's own choice of base
# ---------------------------------------------------------------------------
#
# The tests above give the scanner a `--base` and check what it does with it.  These
# run the *hook*, because the base it chooses is the part that was wrong: it read the
# local `refs/remotes/origin` cache instead of asking the remote being pushed to, so a
# stale cache could excuse a blob the remote no longer held, and a push to any remote
# that is not `origin` queried the wrong repository.


def _bare_remote(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "--quiet", "--bare", "--initial-branch=main")
    return path


def _shell(repo: Path) -> str:
    """Return a shell that can actually run the hook here, or skip.

    The hook is a shell script because git runs it that way everywhere.  Two things
    make "is a shell on PATH" the wrong question on Windows: `sh` is usually absent,
    and a `bash` that belongs to WSL cannot see the repository's drive the way the
    hook's own `git` calls need.  So each candidate is asked to do the hook's own
    first step -- find the file and find git -- and a machine with no shell that can
    is skipped rather than failed.
    """
    for candidate in ("bash", "sh"):
        if not shutil.which(candidate):
            continue
        probe = subprocess.run(
            [candidate, "-c", "test -f .githooks/pre-push && command -v git >/dev/null"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    pytest.skip("no POSIX shell on PATH that can run the hook in this checkout")


def _relative(target: Path, start: Path) -> str:
    """Return ``target`` relative to ``start`` in POSIX spelling.

    Relative paths are what a shell reads without having to agree with Python about
    how a drive letter is spelled, and the remote URL is consumed by `git` running in
    the repository, so it resolves either way.
    """
    import os

    return os.path.relpath(target, start).replace("\\", "/")


def _run_hook(
    repo: Path,
    remote_name: str,
    remote_url: Path,
    local_ref: str,
    local_sha: str,
    remote_ref: str,
    remote_sha: str = "0" * 40,
) -> subprocess.CompletedProcess[str]:
    """Run the pre-push hook the way git runs it: args plus a ref line on stdin."""
    hook = repo / ".githooks" / "pre-push"
    hook.chmod(0o755)
    # Git writes the hook's ref lines with LF, on every platform, so the test does
    # too: feeding them through a text-mode pipe on Windows would add carriage
    # returns git never sends, and the hook would be judged on an input it cannot
    # receive.  (It strips a stray CR anyway -- see the note in the hook -- and the
    # test for that is separate.)
    return subprocess.run(
        [
            _shell(repo),
            ".githooks/pre-push",
            remote_name,
            _relative(remote_url, repo),
        ],
        cwd=repo,
        input=f"{local_ref} {local_sha} {remote_ref} {remote_sha}\n".encode(),
        capture_output=True,
        check=False,
    )


def test_the_hook_refuses_a_leak_the_local_cache_claims_is_published(
    repo: Path, tmp_path: Path
) -> None:
    """A stale cache must not excuse a blob the remote does not hold.

    `refs/remotes/origin/main` is a cache.  When it still points at a commit whose blob
    is private and the remote has since dropped that history, treating the cache as the
    base means the scan *skips* the blob and the push publishes it while the guard says
    clean.  The hook asks the remote instead, finds it empty, and refuses.
    """
    remote = _bare_remote(tmp_path / "remote.git")

    (repo / "leak.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-q", "-m", "a leak the remote never received")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # The stale cache: it claims the remote publishes this commit.
    _git(repo, "update-ref", "refs/remotes/origin/main", tip)

    result = _run_hook(
        repo, "origin", remote, "refs/heads/topic", tip, "refs/heads/topic"
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert b"private identifier" in (result.stdout + result.stderr) or result.returncode == 3


def test_the_hook_passes_a_new_branch_onto_a_remote_that_holds_the_history(
    repo: Path, tmp_path: Path
) -> None:
    """The same shape, with the remote genuinely holding the history: allowed through.

    This is the push the hook used to refuse for *every* new branch, and the direction
    that must keep working: an identifier the remote already publishes is not this
    push's finding.
    """
    remote = _bare_remote(tmp_path / "remote.git")

    (repo / "published.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "published.txt")
    _git(repo, "commit", "-q", "-m", "an identifier the remote already holds")
    published = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "--quiet", str(remote), f"{published}:refs/heads/main")

    (repo / "branch.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "branch.txt")
    _git(repo, "commit", "-q", "-m", "the branch's own change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = _run_hook(
        repo, "origin", remote, "refs/heads/topic", tip, "refs/heads/topic"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # And a string this branch introduces is still refused, on the same remote.
    (repo / "mine.txt").write_text(f"token={OTHER_SECRET}\n", encoding="utf-8")
    _git(repo, "add", "mine.txt")
    _git(repo, "commit", "-q", "-m", "this branch introduces an identifier")
    leaked = _git(repo, "rev-parse", "HEAD").stdout.strip()
    refused = _run_hook(
        repo, "origin", remote, "refs/heads/topic", leaked, "refs/heads/topic"
    )
    assert refused.returncode == 1, refused.stdout + refused.stderr


def test_the_hook_asks_the_remote_git_was_told_to_push_to(
    repo: Path, tmp_path: Path
) -> None:
    """A remote that is not `origin` is queried, not the cache named `origin`.

    The cache under `refs/remotes/origin` says nothing about `upstream`; reading it
    would choose a base from the wrong repository.  Here `upstream` holds the history
    and `origin`'s cache does not exist at all, so only asking the push target can
    produce a clean verdict.
    """
    upstream = _bare_remote(tmp_path / "upstream.git")

    (repo / "published.txt").write_text(f"token={SECRET}\n", encoding="utf-8")
    _git(repo, "add", "published.txt")
    _git(repo, "commit", "-q", "-m", "an identifier upstream already holds")
    published = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "--quiet", str(upstream), f"{published}:refs/heads/main")

    (repo / "branch.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "branch.txt")
    _git(repo, "commit", "-q", "-m", "the branch's own change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = _run_hook(
        repo, "upstream", upstream, "refs/heads/topic", tip, "refs/heads/topic"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_hook_refuses_when_it_cannot_ask_the_remote(
    repo: Path, tmp_path: Path
) -> None:
    """No answer from the remote means no scan, and no scan means no push.

    The alternative -- falling back to the local cache -- is the defect this replaced:
    an unknown base is not a clean base.
    """
    missing = tmp_path / "not-a-remote.git"
    (repo / "new.txt").write_text("ordinary content\n", encoding="utf-8")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-q", "-m", "an ordinary change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = _run_hook(
        repo, "origin", missing, "refs/heads/topic", tip, "refs/heads/topic"
    )
    assert result.returncode == 3, result.stdout + result.stderr
    assert b"could not ask" in result.stderr
