"""The PPTX screenshot render path used for Comparison Image evidence.

The Comparison Image is Gate 3 evidence, so which renderer drew its PPTX panel
is part of what the product claims.  OfficeCLI's default Windows path is a
native rasterizer that cannot compose a keycap cluster (it draws a missing-glyph
box for U+20E3) and draws monochrome emoji while the PPTX itself is correct; the
HTML projection renders both.  These tests pin the request the product makes and
the fact ``doctor`` publishes about the runtime in force.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from officecli_html_to_pptx._internal import acceptance
from officecli_html_to_pptx.runtime import (
    FORMAL_PPTX_SCREENSHOT_RENDER,
    PPTX_SCREENSHOT_DEFAULT_RENDER,
    officecli_pptx_screenshot_render,
)

HAS_OFFICECLI = shutil.which("officecli") is not None


def _record_view_commands(
    monkeypatch: pytest.MonkeyPatch,
    render: str,
) -> list[list[str]]:
    """Capture the OfficeCLI view invocations ``_screenshot_pptx`` makes."""
    calls: list[list[str]] = []

    def fake_run_officecli(*args: object, **_: object) -> str:
        command = [str(arg) for arg in args]
        calls.append(command)
        Path(command[command.index("--out") + 1]).write_bytes(b"png")
        return ""

    monkeypatch.setattr(acceptance, "officecli_pptx_screenshot_render", lambda: render)
    monkeypatch.setattr(acceptance, "_run_officecli", fake_run_officecli)
    return calls


def test_screenshot_requests_the_html_projection_when_the_runtime_supports_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_view_commands(monkeypatch, FORMAL_PPTX_SCREENSHOT_RENDER)

    screenshots = acceptance._screenshot_pptx(tmp_path / "deck.pptx", tmp_path, 2)

    assert [path.name for path in screenshots] == ["slide_01.png", "slide_02.png"]
    assert len(calls) == 2
    for index, command in enumerate(calls, start=1):
        assert command[:3] == ["view", str(tmp_path / "deck.pptx"), "screenshot"]
        assert command[3:5] == ["--render", FORMAL_PPTX_SCREENSHOT_RENDER]
        assert command[command.index("--page") + 1] == str(index)


def test_screenshot_keeps_the_default_path_on_a_runtime_without_the_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_view_commands(monkeypatch, PPTX_SCREENSHOT_DEFAULT_RENDER)

    screenshots = acceptance._screenshot_pptx(tmp_path / "deck.pptx", tmp_path, 1)

    assert [path.name for path in screenshots] == ["slide_01.png"]
    assert "--render" not in calls[0]


@pytest.mark.skipif(not HAS_OFFICECLI, reason="OfficeCLI is required")
def test_the_installed_runtime_is_probed_for_the_render_option() -> None:
    advertised = "--render" in subprocess.run(
        ["officecli", "view", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout

    render = officecli_pptx_screenshot_render()

    assert render == (
        FORMAL_PPTX_SCREENSHOT_RENDER if advertised else PPTX_SCREENSHOT_DEFAULT_RENDER
    )
    assert render in {FORMAL_PPTX_SCREENSHOT_RENDER, PPTX_SCREENSHOT_DEFAULT_RENDER}
