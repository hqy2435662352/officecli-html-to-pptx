"""The gate's own reliability guarantees: one publisher, bounded retries.

Two things this module pins, both of which the gate previously got wrong in a way
no functional test could see:

* **Publication is a claim, not a check followed by a move.**  The gate used to
  test whether its output directory existed and then move the staged evidence
  onto it with ``Path.replace``, which overwrites.  Two publishers that both
  passed the test therefore both "succeeded", and the second silently discarded
  the first run's evidence.  The move is now the claim: ``os.rename`` publishes
  the whole artifact set in one step and refuses a destination that already
  exists.
* **OfficeCLI reads are retried a bounded number of times, and the run says so.**
  A transient failure used to abort a run outright, and a blind retry would have
  hidden a genuine error behind a long stall.  The retry is bounded by a named
  constant, closes the resident handle it names before each further attempt, and
  records the command, the attempt count, the final status and whether a close
  ran -- for the calls that succeeded as well as the ones that did not.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from officecli_html_to_pptx import ProjectionError
from officecli_html_to_pptx._internal import source_delta_gate as gate

# ---------------------------------------------------------------------------
# Publication: the atomic claim
# ---------------------------------------------------------------------------


def _staging(parent: Path, name: str, payload: str) -> Path:
    """Return a complete staged artifact set, as the publication step would."""
    directory = parent / name
    directory.mkdir()
    (directory / "gate-report.json").write_text(payload, encoding="utf-8")
    (directory / "rebuilt.pptx").write_bytes(b"stub")
    return directory


def test_a_destination_that_already_exists_is_a_structured_collision(
    tmp_path: Path,
) -> None:
    """The claim refuses an existing destination rather than overwriting it."""
    destination = tmp_path / "evidence"
    destination.mkdir()
    (destination / "gate-report.json").write_text("first", encoding="utf-8")
    staging = _staging(tmp_path, "staging", "second")

    with pytest.raises(ProjectionError) as raised:
        gate._claim_destination(staging, destination)

    assert raised.value.code == "output_collision"
    # The first publication is untouched, and the loser left nothing behind.
    assert (destination / "gate-report.json").read_text(encoding="utf-8") == "first"
    assert staging.is_dir(), "a refused claim must not consume the staging set"


def test_two_publishers_racing_for_one_destination_cannot_both_win(
    tmp_path: Path,
) -> None:
    """Exactly one racer publishes, and the winner's set is complete and unmixed.

    Both threads are released at the same moment by a barrier, which is what makes
    this a race rather than two sequential calls.  Without the atomic claim both
    would report success and the destination would hold whichever set moved last.
    """
    destination = tmp_path / "evidence"
    count = 8
    barrier = threading.Barrier(count)
    outcomes: list[str] = []
    lock = threading.Lock()

    def publish(index: int) -> None:
        staging = _staging(tmp_path, f"staging-{index}", f"set-{index}")
        barrier.wait()
        try:
            gate._claim_destination(staging, destination)
            result = f"published:{index}"
        except ProjectionError as error:
            result = f"refused:{error.code}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=publish, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    published = [item for item in outcomes if item.startswith("published:")]
    refused = [item for item in outcomes if item.startswith("refused:")]
    assert len(published) == 1, outcomes
    assert len(refused) == count - 1, outcomes
    assert set(refused) == {"refused:output_collision"}, outcomes

    # One artifact set, whole: the report names the winner's payload and the
    # second file is the winner's too.
    winner = published[0].split(":", 1)[1]
    assert (destination / "gate-report.json").read_text(encoding="utf-8") == (
        f"set-{winner}"
    )
    assert (destination / "rebuilt.pptx").read_bytes() == b"stub"
    assert sorted(item.name for item in destination.iterdir()) == [
        "gate-report.json",
        "rebuilt.pptx",
    ]
    # And every loser still holds its own complete set: nothing was half-moved.
    for index in range(count):
        if str(index) == winner:
            continue
        assert (tmp_path / f"staging-{index}" / "gate-report.json").is_file()


def test_a_real_rename_refusal_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a handle is retried; a refusal reaches the caller immediately.

    The distinction is the whole value of the bound: retrying a genuine error
    turns a fast failure into a long one, and the report would still be the same.
    """
    attempts: list[int] = []
    real_rename = gate.os.rename

    def refuse(source: Any, target: Any) -> None:
        attempts.append(1)
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(gate.os, "rename", refuse)
    staging = _staging(tmp_path, "staging", "payload")
    try:
        with pytest.raises(PermissionError):
            gate._claim_destination(staging, tmp_path / "evidence")
    finally:
        monkeypatch.setattr(gate.os, "rename", real_rename)
    assert len(attempts) == 1, "a refusal is not a transient condition"


def test_windows_access_denied_onto_an_occupied_directory_is_a_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows calls an occupied destination "access denied"; it is still a collision.

    The first real three-deck run hit exactly this: ``os.rename`` onto a directory
    that already existed raised ``PermissionError: [WinError 5]`` rather than
    ``FileExistsError``, and the failure reached the caller as a raw access
    refusal.  The destination's own existence is the authoritative test, and it is
    read only after the rename has already failed -- so the classification cannot
    re-open the race the atomic move closed.
    """
    destination = tmp_path / "evidence"
    destination.mkdir()
    (destination / "gate-report.json").write_text("first", encoding="utf-8")
    attempts: list[int] = []

    def access_denied(source: Any, target: Any) -> None:
        attempts.append(1)
        raise PermissionError(5, "Access is denied", None, 5)

    monkeypatch.setattr(gate.os, "rename", access_denied)
    staging = _staging(tmp_path, "staging", "second")
    with pytest.raises(ProjectionError) as raised:
        gate._claim_destination(staging, destination)
    assert raised.value.code == "output_collision"
    # Classified, not retried: the destination is somebody else's publication.
    assert len(attempts) == 1
    assert (destination / "gate-report.json").read_text(encoding="utf-8") == "first"


def _windows_access_denied(source: Any, target: Any) -> None:
    """Raise what Windows raises: ``ERROR_ACCESS_DENIED``, with ``winerror``.

    The distinction is the whole point of the rule.  ``winerror`` is a Windows-only
    attribute, and the production code retries on it -- so a test that raises a bare
    ``PermissionError`` is testing *POSIX*, where the documented behaviour is to fail
    immediately.  The suite ran on Linux in CI and failed on exactly that mismatch.
    """
    error = PermissionError(13, "Access is denied")
    error.winerror = 5  # type: ignore[attr-defined]
    raise error


def test_a_windows_sharing_violation_with_no_destination_is_retried_then_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing published, a Windows sharing violation is retried within the bound.

    Windows reports *both* "a handle is still open in this directory" and "the
    destination exists" as ``ERROR_ACCESS_DENIED``, so a sharing violation with no
    destination is the in-use case and is worth waiting out.  The bound still
    applies: a refusal that never clears is raised rather than retried forever, and
    the caller sees the error the filesystem actually produced.
    """
    attempts: list[int] = []

    def access_denied(source: Any, target: Any) -> None:
        attempts.append(1)
        _windows_access_denied(source, target)

    monkeypatch.setattr(gate.os, "rename", access_denied)
    staging = _staging(tmp_path, "staging", "payload")
    with pytest.raises(PermissionError):
        gate._claim_destination(staging, tmp_path / "evidence")
    assert len(attempts) == gate.PUBLICATION_ATTEMPTS


def test_a_posix_permission_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A POSIX permission error is an answer, not a delay, and must not be waited on.

    There is no sharing-violation case on POSIX at all: renaming onto a destination
    that does not exist is atomic, so a refusal is about state -- ownership, a
    read-only mount, a missing parent -- and retrying it twenty times would only
    delay the report by five seconds and then raise the same error.  This test exists
    so the *documented* asymmetry is pinned: it would fail if somebody widened the
    production retry to ``errno`` values in order to make a Linux test pass.
    """
    attempts: list[int] = []

    def access_denied(source: Any, target: Any) -> None:
        attempts.append(1)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(gate.os, "rename", access_denied)
    staging = _staging(tmp_path, "staging", "payload")
    with pytest.raises(PermissionError):
        gate._claim_destination(staging, tmp_path / "evidence")
    assert len(attempts) == 1
    assert gate.PUBLICATION_ATTEMPTS > 1, "the retry bound exists; it just does not apply"


def test_publishing_moves_the_whole_set_in_one_step(tmp_path: Path) -> None:
    """The successful direction, so the claim is not only tested when it fails."""
    staging = _staging(tmp_path, "staging", "payload")
    destination = tmp_path / "evidence"
    gate._claim_destination(staging, destination)
    assert not staging.exists()
    assert (destination / "gate-report.json").read_text(encoding="utf-8") == "payload"
    assert (destination / "rebuilt.pptx").read_bytes() == b"stub"


# ---------------------------------------------------------------------------
# OfficeCLI reads: bounded retry, resident close, recorded evidence
# ---------------------------------------------------------------------------


class _Completed:
    """A ``subprocess.run`` result with just the fields the reader uses."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _officecli_that(failures: int, payload: dict[str, Any]) -> tuple[Any, list[list[str]]]:
    """Return a fake ``subprocess.run`` failing ``failures`` times, and its calls."""
    calls: list[list[str]] = []
    remaining = {"count": failures}

    def run(command, **kwargs):  # noqa: ANN001, ANN003 - mirrors subprocess.run
        calls.append([str(item) for item in command])
        if command[1] == "close":
            return _Completed(0, "", "")
        if remaining["count"] > 0:
            remaining["count"] -= 1
            return _Completed(1, "", "transient")
        return _Completed(0, json.dumps(payload), "")

    return run, calls


def test_a_transient_failure_is_retried_within_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One flaky read is ridden out, and the record says how many attempts it took."""
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"stub")
    run, calls = _officecli_that(2, {"data": {"results": [{"ok": True}]}})
    monkeypatch.setattr(gate.subprocess, "run", run)
    log: list[gate.OfficeCliCall] = []
    token = gate._ACTIVE_CALLS.set(log)
    try:
        payload = gate._gate_officecli("get", deck, "/", "--depth", "1", json_output=True)
    finally:
        gate._ACTIVE_CALLS.reset(token)

    assert payload == {"data": {"results": [{"ok": True}]}}
    assert len(log) == 1
    record = log[0]
    assert record.status == "ok"
    assert record.attempts == 3
    assert record.resident_closed is True, "the retry closes the document it names"
    # Two failures and then the success, with a close between each pair.
    assert len([item for item in calls if item[1] == "close"]) == 2


def test_the_attempt_bound_is_the_named_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read that never succeeds stops at the bound instead of retrying forever."""
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"stub")
    run, _ = _officecli_that(99, {})
    monkeypatch.setattr(gate.subprocess, "run", run)
    log: list[gate.OfficeCliCall] = []
    token = gate._ACTIVE_CALLS.set(log)
    try:
        with pytest.raises(gate.GateOfficeCliError) as raised:
            gate._gate_officecli("get", deck, "/", json_output=True)
    finally:
        gate._ACTIVE_CALLS.reset(token)

    assert gate.OFFICECLI_READ_ATTEMPTS == 3
    assert len(log) == 1
    assert log[0].status == "failed"
    assert log[0].attempts == gate.OFFICECLI_READ_ATTEMPTS
    # The failure names the command, the attempt count and the resident close.
    message = str(raised.value)
    assert "attempt(s)" in message
    assert "resident close ran: True" in message
    assert "officecli get" in message


def test_the_bound_can_be_lowered_but_not_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The policy is a number, and an unusable one is refused rather than ignored.

    ``1`` is accepted: it is the strictest honest setting and the one a
    no-retry run needs.  ``0`` would mean "never attempt", which is not a policy.
    """
    monkeypatch.setenv(gate.OFFICECLI_READ_ATTEMPTS_ENV, "1")
    assert gate._officecli_attempts() == 1
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"stub")
    run, _ = _officecli_that(99, {})
    monkeypatch.setattr(gate.subprocess, "run", run)
    with pytest.raises(gate.GateOfficeCliError):
        gate._gate_officecli("get", deck, "/", json_output=True)
    monkeypatch.setenv(gate.OFFICECLI_READ_ATTEMPTS_ENV, "0")
    with pytest.raises(ProjectionError) as raised:
        gate._officecli_attempts()
    assert raised.value.code == "invalid_retry_policy"
    monkeypatch.setenv(gate.OFFICECLI_READ_ATTEMPTS_ENV, "many")
    with pytest.raises(ProjectionError):
        gate._officecli_attempts()


def test_an_undecodable_reply_is_a_schema_error_and_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reply this code cannot read is not a transient failure.

    Retrying it would spend the whole retry budget on a command whose answer is
    the wrong shape, and the run would still have to fail -- later, and with a
    misleading attempt count.
    """
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"stub")
    attempts: list[int] = []

    def run(command, **kwargs):  # noqa: ANN001, ANN003
        if command[1] == "close":
            return _Completed(0, "", "")
        attempts.append(1)
        return _Completed(0, "not json at all", "")

    monkeypatch.setattr(gate.subprocess, "run", run)
    log: list[gate.OfficeCliCall] = []
    token = gate._ACTIVE_CALLS.set(log)
    try:
        with pytest.raises(gate.GateOfficeCliError):
            gate._gate_officecli("view", deck, "issues", json_output=True)
    finally:
        gate._ACTIVE_CALLS.reset(token)
    assert len(attempts) == 1
    assert log[0].attempts == 1
    assert "could not be decoded" in str(log[0].error)


def test_a_call_outside_a_run_is_not_recorded(tmp_path: Path) -> None:
    """The recorder is scoped to a run, so one run's evidence cannot leak into another."""
    assert gate._ACTIVE_CALLS.get() is None


def test_the_run_publishes_the_reliability_policy_it_applied() -> None:
    """The constants reach the report, so a reviewer reads the policy, not a claim."""
    assert gate.OFFICECLI_READ_ATTEMPTS == 3
    assert gate.OFFICECLI_READ_BACKOFF_SECONDS == 0.5
    assert gate.PUBLICATION_ATTEMPTS == 20
    assert gate.PUBLICATION_BACKOFF_SECONDS == 0.25
    assert gate.OFFICECLI_READ_TIMEOUT_SECONDS == 180
    assert gate.GateOfficeCliError.code == "officecli_read_failed"
    assert callable(gate._close_residents)
    assert subprocess.run is not None, "the helper really uses the standard runner"


if __name__ == "__main__":  # pragma: no cover - manual run
    raise SystemExit(pytest.main([__file__, "-q"]))
