from __future__ import annotations

import subprocess

import pytest

import officecli_html_to_pptx.runtime as runtime

WINDOWS_TOOLS = {"node": "C:\\runtime\\node.exe", "officecli": "C:\\runtime\\officecli.exe"}
LINUX_TOOLS = {"node": "/usr/local/bin/node", "officecli": "/usr/local/bin/officecli"}


def _tool_key(executable: str) -> str:
    """Name the tool behind an executable path on any supported platform.

    Matching on ``node.exe`` would only work on Windows, so the leaf name is
    extracted without :mod:`pathlib`: a POSIX ``Path`` does not treat ``\\`` as a
    separator, so parsing ``C:\\runtime\\node.exe`` with it on Linux would not
    yield ``node``.
    """
    leaf = executable.replace("\\", "/").rsplit("/", 1)[-1]
    return "node" if leaf.split(".", 1)[0].lower() == "node" else "officecli"


def _runner_factory(versions: dict[str, str]):
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        value = versions[_tool_key(command[0])]
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
    executables = WINDOWS_TOOLS
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
        return subprocess.CompletedProcess(
            command, 0, (versions[_tool_key(command[0])] + "\n").encode(), b""
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
        which=WINDOWS_TOOLS.get,
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
    executables = WINDOWS_TOOLS
    versions = {"node": "not-a-version", "officecli": "1.0.146"}
    diagnosis = runtime.diagnose_environment(
        which=executables.get,
        runner=_runner_factory(versions),
    )

    codes = {item.code for item in diagnosis.diagnostics}
    assert {"malformed_node_version", "officecli_version_mismatch", "playwright_version_mismatch", "chromium_revision_mismatch"} <= codes


def test_doctor_accepts_linux_as_a_supported_build_platform(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux passed the WSL2 acceptance track, so the platform gate must not block it.

    The same runtime that Windows accepts is accepted here, on POSIX tool paths
    and with the render path OfficeCLI advertises off Windows.
    """
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    executable = tmp_path / "chrome"
    executable.write_bytes(b"chrome")
    monkeypatch.setattr(
        runtime,
        "_playwright_chromium",
        lambda: ("1.62.0", "1234", str(executable)),
    )

    diagnosis = runtime.diagnose_environment(
        which=LINUX_TOOLS.get,
        runner=_view_help_runner("Options:\n  --render <render>  Screenshot rendering path\n"),
    )

    assert diagnosis.compatible
    snapshot_platform = diagnosis.snapshot["platform"]
    assert snapshot_platform["required"] == list(runtime.SUPPORTED_PLATFORMS)
    assert snapshot_platform["discovered"] == "Linux"
    assert snapshot_platform["compatible"] is True
    # The supported key "Linux" is coarse, so the accepted environment must travel
    # with it and the not-implied list must be explicit.
    assert snapshot_platform["validated_scope"] == runtime.VALIDATED_PLATFORM_SCOPE["Linux"]
    assert snapshot_platform["not_implied"] == runtime.UNVALIDATED_PLATFORM_NOTE
    assert "Ubuntu 24.04" in snapshot_platform["validated_scope"]
    assert "other Linux distributions" in snapshot_platform["not_implied"]
    assert "unsupported_platform" not in {item.code for item in diagnosis.diagnostics}
    # The HTML projection is the only render path available without PowerPoint,
    # so it is the path a Linux build must record.
    assert diagnosis.snapshot["pptx_screenshot"]["render"] == runtime.FORMAL_PPTX_SCREENSHOT_RENDER


def test_doctor_blocks_a_platform_outside_the_supported_set(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widening the set must not accept an unaccepted platform."""
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    executable = tmp_path / "chrome"
    executable.write_bytes(b"chrome")
    monkeypatch.setattr(
        runtime,
        "_playwright_chromium",
        lambda: ("1.62.0", "1234", str(executable)),
    )

    diagnosis = runtime.diagnose_environment(
        which=LINUX_TOOLS.get,
        runner=_runner_factory({"node": "v22.23.2", "officecli": "1.0.149"}),
    )

    blocking = {item.code for item in diagnosis.diagnostics if item.blocking}
    assert blocking == {"unsupported_platform"}
    assert not diagnosis.compatible
    message = next(item.message for item in diagnosis.diagnostics if item.code == "unsupported_platform")
    # The diagnostic must name every supported platform, not only the first one.
    for supported in runtime.SUPPORTED_PLATFORMS:
        assert supported in message
