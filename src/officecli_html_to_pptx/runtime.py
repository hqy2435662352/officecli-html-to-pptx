"""Read-only runtime discovery and the formal rendering-pair authority."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Sequence

from .protocol import Diagnostic

FORMAL_OFFICECLI_VERSION = "1.0.151"
FORMAL_PLAYWRIGHT_VERSION = "1.62.0"
FORMAL_CHROMIUM_REVISION = "1234"
# The Comparison Image is Gate 3 evidence, so its PPTX panel is rendered
# through OfficeCLI's HTML projection rather than the native rasterizer that
# ``auto`` selects on Windows.  The native rasterizer cannot compose a keycap
# cluster (it draws a missing-glyph box for U+20E3) and draws monochrome emoji,
# which would present a correct PPTX as broken content to a reviewer.
FORMAL_PPTX_SCREENSHOT_RENDER = "html"
PPTX_SCREENSHOT_DEFAULT_RENDER = "default"
PYTHON_TESTED_RANGE = ">=3.10,<3.15"
NODE_TESTED_RANGE = ">=20,<23"
# The platform keys the gate accepts.  These are ``platform.system()`` values, so
# they are inherently coarse: the single key "Linux" covers every distribution.
# The gate matches that key and nothing else -- it does not inspect the
# distribution, the virtualisation, the CPU architecture, the user or the fonts --
# so an accepted key means "this operating-system family is supported", never
# "this host was acceptance-tested".  What was accepted is narrower and is
# declared in ``VALIDATED_PLATFORM_SCOPE``.
SUPPORTED_PLATFORMS = ("Windows", "Linux")

# Whether ``diagnose_environment`` verifies that the host matches the scope below.
# It does not, and the boundary is published rather than implied so that a coarse
# key cannot be read as a certification.  What the gate does check is the
# Rendering Compatibility Pair, which is discoverable on environments that were
# never acceptance-tested; the known silent failure those carry is fonts, which
# produce a mis-measured deck while ``doctor`` still reports ``PASS``.
PLATFORM_SCOPE_ENFORCED = False

# What each accepted key actually stands for: the environment that ran the
# Platform Acceptance Track, not every system the key matches.
VALIDATED_PLATFORM_SCOPE = {
    "Windows": (
        "Windows 10 or 11, x86_64, a normal user account, with the declared "
        "fonts installed"
    ),
    "Linux": (
        "WSL2 on Ubuntu 24.04, x86_64, a non-root user, the environment owning "
        "the pinned Playwright Chromium active, and the declared fonts installed"
    ),
}

# Published next to the scope so a supported key is never read as a broader claim
# than the evidence supports.  Kept in step with the "Not implied" list in
# ADR-0031.
UNVALIDATED_PLATFORM_NOTE = (
    "A supported platform key certifies the operating-system family only. Not "
    "implied: other Linux distributions, native (non-WSL2) Linux installations, "
    "container images, other CPU architectures, and macOS. None of these is "
    "verified by the platform gate, and each needs its own Platform Acceptance "
    "Track before it can be relied on."
)


def current_platform() -> str:
    """Return the platform this process runs on, as ``platform.system()`` reports it.

    Kept here so that platform knowledge has one owner: callers ask the runtime
    module instead of importing :mod:`platform` and comparing strings themselves.
    """
    return platform.system()


def supported_platforms_text() -> str:
    """Render the supported set for a human-readable diagnostic."""
    names = list(SUPPORTED_PLATFORMS)
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" or {names[-1]}"


@dataclass(frozen=True)
class RuntimeDiagnosis:
    """A discovered runtime snapshot and any blocks it produced."""

    snapshot: dict[str, Any]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def compatible(self) -> bool:
        return not self.diagnostics


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if value is None:
        return None
    match = re.search(r"(?<!\d)(\d+)(?:\.(\d+))(?:\.(\d+))?", value)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _version_text(value: tuple[int, ...] | None) -> str | None:
    return ".".join(str(part) for part in value) if value is not None else None


def officecli_runtime_snapshot(
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    """Return the discovered OfficeCLI version and the Contract 1.2 floor.

    This narrow probe is shared by the direct compiler seam and ``doctor``.
    It deliberately does not inspect Chromium, Node, or output locations, so a
    compiler can fail before Chromium measurement or PPTX creation while still
    recording the exact external runtime it observed.
    """

    executable = which("officecli")
    raw_version = version_text = None
    if executable:
        raw_version, version_text = _run_version(executable, runner=runner)
    discovered = _version_tuple(raw_version)
    required = _version_tuple(FORMAL_OFFICECLI_VERSION)
    compatible = (
        discovered is not None
        and required is not None
        and discovered >= required
    )
    return {
        "required_version": f">={FORMAL_OFFICECLI_VERSION}",
        "executable": executable,
        "discovered_version": version_text,
        "compatible": compatible,
    }


def _run_version(
    executable: str,
    args: Sequence[str] = ("--version",),
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> tuple[str | None, str]:
    try:
        completed = runner(
            [executable, *args],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    stdout = completed.stdout.decode("utf-8", errors="replace") if isinstance(completed.stdout, bytes) else str(completed.stdout or "")
    stderr = completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else str(completed.stderr or "")
    raw = (stdout.strip() or stderr.strip()).splitlines()
    text = raw[0].strip() if raw else ""
    return text or None, text


def _run_help_text(
    executable: str,
    args: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> str:
    """Return a command's full standard output, or ``""`` when it cannot run."""
    try:
        completed = runner(
            [executable, *args],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    stdout = completed.stdout
    if isinstance(stdout, bytes):
        return stdout.decode("utf-8", errors="replace")
    return str(stdout or "")


def _supports_pptx_screenshot_render(
    executable: str | None,
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> bool:
    """Whether this OfficeCLI advertises the HTML PPTX screenshot render path."""
    if not executable:
        return False
    return "--render" in _run_help_text(executable, ("view", "--help"), runner=runner)


_PPTX_SCREENSHOT_RENDER: str | None = None


def officecli_pptx_screenshot_render(
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> str:
    """Return the render path the Comparison Image's PPTX panel must use.

    Returns :data:`FORMAL_PPTX_SCREENSHOT_RENDER` when the installed OfficeCLI
    supports it, otherwise :data:`PPTX_SCREENSHOT_DEFAULT_RENDER`.  A runtime
    that does not advertise ``--render`` keeps the default path rather than
    failing the build, and ``doctor`` records which path is in force so the
    Evidence Bundle never claims a rendering authority it did not use.
    """
    global _PPTX_SCREENSHOT_RENDER
    if _PPTX_SCREENSHOT_RENDER is None:
        supported = _supports_pptx_screenshot_render(
            shutil.which("officecli"), runner
        )
        _PPTX_SCREENSHOT_RENDER = (
            FORMAL_PPTX_SCREENSHOT_RENDER
            if supported
            else PPTX_SCREENSHOT_DEFAULT_RENDER
        )
    return _PPTX_SCREENSHOT_RENDER


def _playwright_chromium() -> tuple[str | None, str | None, str | None]:
    """Return installed Playwright version, Chromium revision, and executable."""
    try:
        version = importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return None, None, None

    try:
        from playwright.async_api import async_playwright

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return version, None, None

        async def read_executable_path() -> str:
            async with async_playwright() as playwright:
                return str(playwright.chromium.executable_path)

        executable = asyncio.run(read_executable_path())
    except Exception:
        return version, None, None
    match = re.search(r"(?:chromium|chromium_headless_shell)-([0-9]+)", executable)
    return version, match.group(1) if match else None, executable


def _location_check(
    value: str | Path | None,
    label: str,
) -> tuple[dict[str, Any] | None, Diagnostic | None]:
    if value is None:
        return None, None
    path = Path(value).expanduser()
    directory = path if path.is_dir() else path.parent
    if not directory.is_dir() or not os.access(directory, os.W_OK):
        return (
            {"requested": str(path.resolve()), "directory": str(directory.resolve()), "writable": False},
            Diagnostic(
                "unwritable_location",
                "error",
                f"Requested {label} location is missing or not writable: {path.resolve()}.",
                True,
                remediation=f"Choose an existing writable {label} directory and retry.",
                recheck="officecli-html-to-pptx doctor --json",
            ),
        )
    return (
        {"requested": str(path.resolve()), "directory": str(directory.resolve()), "writable": True},
        None,
    )


def diagnose_environment(
    output_path: str | Path | None = None,
    temp_dir: str | Path | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> RuntimeDiagnosis:
    """Inspect prerequisites without installing or mutating anything."""
    diagnostics: list[Diagnostic] = []
    actual_platform = current_platform()
    platform_ok = actual_platform in SUPPORTED_PLATFORMS
    snapshot: dict[str, Any] = {
        "platform": {
            "required": list(SUPPORTED_PLATFORMS),
            "discovered": actual_platform,
            "compatible": platform_ok,
            # A supported key is coarse ("Linux" matches every distribution), so
            # the accepted environment travels with it, along with the fact that
            # the gate does not verify it.
            "validated_scope": VALIDATED_PLATFORM_SCOPE.get(actual_platform),
            "scope_enforced": PLATFORM_SCOPE_ENFORCED,
            "not_implied": UNVALIDATED_PLATFORM_NOTE,
        },
        "formal_pair": {
            "officecli": f">={FORMAL_OFFICECLI_VERSION}",
            "playwright": FORMAL_PLAYWRIGHT_VERSION,
            "chromium_revision": FORMAL_CHROMIUM_REVISION,
        },
        "python": {},
        "node": {},
        "officecli": {},
        "playwright": {},
        "chromium": {},
    }
    if not platform_ok:
        supported = supported_platforms_text()
        diagnostics.append(
            Diagnostic(
                "unsupported_platform",
                "error",
                f"Formal builds support {supported}; discovered {actual_platform or 'unknown'}.",
                True,
                remediation=(
                    f"Run the formal build on {supported}. "
                    "`officecli-html-to-pptx capabilities --json` reports every "
                    "supported platform and the environment each one was "
                    "accepted in. A platform joins the set only after it passes "
                    "the Platform Acceptance Track against the Rendering "
                    "Compatibility Pair."
                ),
                recheck="officecli-html-to-pptx doctor --json",
            )
        )

    python_version = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    python_ok = python_version[:2] >= (3, 10) and python_version[:2] < (3, 15)
    snapshot["python"] = {
        "required_range": PYTHON_TESTED_RANGE,
        "discovered_version": _version_text(python_version),
        "compatible": python_ok,
    }
    if not python_ok:
        diagnostics.append(
            Diagnostic(
                "python_version_mismatch",
                "error",
                f"Python {snapshot['python']['discovered_version']} is outside the tested range {PYTHON_TESTED_RANGE}.",
                True,
                remediation=f"Run the product with a Python version in {PYTHON_TESTED_RANGE}.",
                recheck="officecli-html-to-pptx doctor --json",
            )
        )

    node_executable = which("node")
    node_raw = node_text = None
    if node_executable:
        node_raw, node_text = _run_version(node_executable, runner=runner)
    node_version = _version_tuple(node_raw)
    node_ok = node_version is not None and (20, 0) <= node_version[:2] < (23, 0)
    snapshot["node"] = {
        "required_range": NODE_TESTED_RANGE,
        "executable": node_executable,
        "discovered_version": node_text,
        "compatible": node_ok,
    }
    if node_executable is None:
        code = "missing_node"
        message = "Node.js is required by the Playwright runtime but was not found on PATH."
        remediation = "Install Node.js 20.x through 22.x, then verify with node --version."
    elif node_version is None:
        code = "malformed_node_version"
        message = f"Node.js returned an unparseable version: {node_text!r}."
        remediation = "Repair the Node.js installation so node --version returns a semantic version."
    elif not node_ok:
        code = "node_version_mismatch"
        message = f"Node.js {node_text} is outside the tested range {NODE_TESTED_RANGE}."
        remediation = f"Run the product with Node.js in {NODE_TESTED_RANGE}."
    else:
        code = message = remediation = ""
    if code:
        diagnostics.append(Diagnostic(code, "error", message, True, remediation=remediation, recheck="officecli-html-to-pptx doctor --json"))

    officecli_info = officecli_runtime_snapshot(which=which, runner=runner)
    officecli_executable = officecli_info["executable"]
    officecli_text = officecli_info["discovered_version"]
    officecli_version = _version_tuple(officecli_text)
    officecli_ok = bool(officecli_info["compatible"])
    snapshot["officecli"] = officecli_info
    if officecli_executable is None:
        code = "missing_officecli"
        message = "OfficeCLI was not found on PATH."
        remediation = "Install OfficeCLI 1.0.151 or newer through the approved OfficeCLI package source, then verify with officecli --version."
    elif officecli_version is None:
        code = "malformed_officecli_version"
        message = f"OfficeCLI returned an unparseable version: {officecli_text!r}."
        remediation = "Repair the OfficeCLI installation so officecli --version returns 1.0.151 or newer."
    elif not officecli_ok:
        code = "officecli_version_mismatch"
        message = f"OfficeCLI {officecli_text} is below the minimum supported version {FORMAL_OFFICECLI_VERSION}."
        remediation = f"Install or select OfficeCLI {FORMAL_OFFICECLI_VERSION} or newer, then verify with officecli --version."
    else:
        code = message = remediation = ""
    if code:
        diagnostics.append(Diagnostic(code, "error", message, True, remediation=remediation, recheck="officecli-html-to-pptx doctor --json"))

    # The Evidence Bundle's PPTX panel is rendered by OfficeCLI, so record which
    # render path that runtime will use instead of leaving it implicit.
    screenshot_supported = _supports_pptx_screenshot_render(officecli_executable, runner)
    snapshot["pptx_screenshot"] = {
        "render": (
            FORMAL_PPTX_SCREENSHOT_RENDER
            if screenshot_supported
            else PPTX_SCREENSHOT_DEFAULT_RENDER
        ),
        "option": "--render" if screenshot_supported else None,
        "supported": screenshot_supported,
        "renderer": (
            "officecli-html-projection" if screenshot_supported else "officecli-default"
        ),
    }

    playwright_version, chromium_revision, chromium_executable = _playwright_chromium()
    playwright_ok = playwright_version == FORMAL_PLAYWRIGHT_VERSION
    chromium_installed = bool(chromium_executable and Path(chromium_executable).is_file())
    chromium_ok = chromium_installed and chromium_revision == FORMAL_CHROMIUM_REVISION
    snapshot["playwright"] = {
        "required_version": FORMAL_PLAYWRIGHT_VERSION,
        "discovered_version": playwright_version,
        "compatible": playwright_ok,
    }
    snapshot["chromium"] = {
        "required_revision": FORMAL_CHROMIUM_REVISION,
        "discovered_revision": chromium_revision,
        "executable": chromium_executable,
        "installed": chromium_installed,
        "compatible": chromium_ok,
    }
    if playwright_version is None:
        diagnostics.append(
            Diagnostic(
                "missing_playwright",
                "error",
                "The pinned Playwright package was not found in the active Python environment.",
                True,
                remediation="Install the declared dependency with uv sync, then run uv run playwright install chromium.",
                recheck="officecli-html-to-pptx doctor --json",
            )
        )
    elif not playwright_ok:
        diagnostics.append(
            Diagnostic(
                "playwright_version_mismatch",
                "error",
                f"Playwright {playwright_version} does not match the formal pair version {FORMAL_PLAYWRIGHT_VERSION}.",
                True,
                remediation=f"Install Playwright {FORMAL_PLAYWRIGHT_VERSION}, then run uv run playwright install chromium.",
                recheck="officecli-html-to-pptx doctor --json",
            )
        )
    if not chromium_installed:
        diagnostics.append(
            Diagnostic(
                "missing_chromium",
                "error",
                f"Playwright Chromium revision {FORMAL_CHROMIUM_REVISION} is not installed or its executable cannot be found.",
                True,
                remediation="Run uv run playwright install chromium after confirming the pinned Playwright package.",
                recheck="officecli-html-to-pptx doctor --json",
            )
        )
    elif chromium_revision != FORMAL_CHROMIUM_REVISION:
        diagnostics.append(
            Diagnostic(
                "chromium_revision_mismatch",
                "error",
                f"Playwright discovered Chromium revision {chromium_revision}, not the formal revision {FORMAL_CHROMIUM_REVISION}.",
                True,
                remediation="Install the Chromium revision owned by the pinned Playwright package, then recheck the doctor.",
                recheck="officecli-html-to-pptx doctor --json",
            )
        )

    output_info, output_diagnostic = _location_check(output_path, "output")
    temp_info, temp_diagnostic = _location_check(temp_dir, "temporary")
    if output_info is not None:
        snapshot["locations"]=snapshot.get("locations", {})
        snapshot["locations"]["output"] = output_info
    if temp_info is not None:
        snapshot.setdefault("locations", {})["temporary"] = temp_info
    if output_diagnostic:
        diagnostics.append(output_diagnostic)
    if temp_diagnostic:
        diagnostics.append(temp_diagnostic)

    snapshot["compatible"] = not diagnostics
    return RuntimeDiagnosis(snapshot, tuple(diagnostics))


__all__ = [
    "FORMAL_CHROMIUM_REVISION",
    "FORMAL_OFFICECLI_VERSION",
    "FORMAL_PLAYWRIGHT_VERSION",
    "FORMAL_PPTX_SCREENSHOT_RENDER",
    "NODE_TESTED_RANGE",
    "PPTX_SCREENSHOT_DEFAULT_RENDER",
    "PYTHON_TESTED_RANGE",
    "PLATFORM_SCOPE_ENFORCED",
    "SUPPORTED_PLATFORMS",
    "UNVALIDATED_PLATFORM_NOTE",
    "VALIDATED_PLATFORM_SCOPE",
    "RuntimeDiagnosis",
    "current_platform",
    "diagnose_environment",
    "officecli_pptx_screenshot_render",
    "officecli_runtime_snapshot",
    "supported_platforms_text",
]
