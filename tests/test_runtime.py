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


@pytest.mark.parametrize("officecli_version", ["1.0.147", "1.0.148"])
def test_doctor_accepts_the_minimum_and_newer_officecli(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    officecli_version: str,
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
    versions = {"node": "v22.1.0", "officecli": officecli_version}
    diagnosis = runtime.diagnose_environment(
        which=executables.get,
        runner=_runner_factory(versions),
    )

    assert diagnosis.compatible
    assert diagnosis.snapshot["formal_pair"]["officecli"] == ">=1.0.147"
    assert diagnosis.snapshot["officecli"]["required_version"] == ">=1.0.147"
    assert diagnosis.snapshot["officecli"]["compatible"] is True
    assert diagnosis.snapshot["chromium"]["compatible"] is True


def _view_help_runner(help_text: str):
    """A runner whose ``view --help`` advertises (or not) the render option."""
    versions = {"node": "v22.1.0", "officecli": "1.0.148"}

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        if command[1:3] == ["view", "--help"]:
            return subprocess.CompletedProcess(command, 0, help_text.encode(), b"")
        key = "node" if command[0].lower().endswith("node.exe") else "officecli"
        return subprocess.CompletedProcess(
            command, 0, (versions[key] + "\n").encode(), b""
        )

    return runner


@pytest.mark.parametrize(
    ("help_text", "expected_render", "expected_renderer"),
    [
        ("Options:\n  --render <render>  Screenshot rendering path\n",
         runtime.FORMAL_PPTX_SCREENSHOT_RENDER, "officecli-html-projection"),
        ("Options:\n  --page <page>  Page filter\n",
         runtime.PPTX_SCREENSHOT_DEFAULT_RENDER, "officecli-default"),
    ],
)
def test_doctor_records_the_pptx_screenshot_render_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    help_text: str,
    expected_render: str,
    expected_renderer: str,
) -> None:
    """The Evidence Bundle's PPTX panel is rendered by OfficeCLI, so the runtime
    in force is recorded instead of the rendering authority being assumed."""
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"chrome")
    monkeypatch.setattr(
        runtime, "_playwright_chromium", lambda: ("1.62.0", "1234", str(executable))
    )

    diagnosis = runtime.diagnose_environment(
        which={"node": "C:\\runtime\\node.exe", "officecli": "C:\\runtime\\officecli.exe"}.get,
        runner=_view_help_runner(help_text),
    )

    screenshot = diagnosis.snapshot["pptx_screenshot"]
    assert diagnosis.compatible
    assert screenshot["render"] == expected_render
    assert screenshot["renderer"] == expected_renderer
    assert screenshot["supported"] is (expected_render == runtime.FORMAL_PPTX_SCREENSHOT_RENDER)
    assert screenshot["option"] == ("--render" if screenshot["supported"] else None)


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
    versions = {"node": "not-a-version", "officecli": "1.0.146"}
    diagnosis = runtime.diagnose_environment(
        which=executables.get,
        runner=_runner_factory(versions),
    )

    codes = {item.code for item in diagnosis.diagnostics}
    assert {"malformed_node_version", "officecli_version_mismatch", "playwright_version_mismatch", "chromium_revision_mismatch"} <= codes
