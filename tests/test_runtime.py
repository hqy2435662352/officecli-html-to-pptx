from __future__ import annotations

import subprocess

import pytest

import officecli_html_to_pptx.runtime as runtime


def _runner_factory(versions: dict[str, str]):
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        key = "node" if command[0].lower().endswith("node.exe") else "officecli"
        value = versions[key]
        return subprocess.CompletedProcess(command, 0, (value + "\n").encode(), b"")

    return runner


def test_doctor_reports_missing_external_tools_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime, "_playwright_chromium", lambda: (None, None, None))
    diagnosis = runtime.diagnose_environment(which=lambda _: None)

    codes = {item.code for item in diagnosis.diagnostics}
    assert not diagnosis.compatible
    assert {"missing_node", "missing_officecli", "missing_playwright", "missing_chromium"} <= codes


def test_doctor_accepts_the_exact_formal_pair(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"chrome")
    monkeypatch.setattr(
        runtime,
        "_playwright_chromium",
        lambda: ("1.62.0", "1234", str(executable)),
    )
    executables = {"node": "C:\\runtime\\node.exe", "officecli": "C:\\runtime\\officecli.exe"}
    versions = {"node": "v22.1.0", "officecli": "1.0.147"}
    diagnosis = runtime.diagnose_environment(
        which=executables.get,
        runner=_runner_factory(versions),
    )

    assert diagnosis.compatible
    assert diagnosis.snapshot["officecli"]["compatible"] is True
    assert diagnosis.snapshot["chromium"]["compatible"] is True


def test_doctor_blocks_mismatched_and_malformed_tools(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"chrome")
    monkeypatch.setattr(
        runtime,
        "_playwright_chromium",
        lambda: ("9.9.9", "9999", str(executable)),
    )
    executables = {"node": "C:\\runtime\\node.exe", "officecli": "C:\\runtime\\officecli.exe"}
    versions = {"node": "not-a-version", "officecli": "1.0.148"}
    diagnosis = runtime.diagnose_environment(
        which=executables.get,
        runner=_runner_factory(versions),
    )

    codes = {item.code for item in diagnosis.diagnostics}
    assert {"malformed_node_version", "officecli_version_mismatch", "playwright_version_mismatch", "chromium_revision_mismatch"} <= codes
