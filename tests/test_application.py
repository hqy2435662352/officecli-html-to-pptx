"""Public V0.2 application and protocol seam tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import officecli_html_to_pptx.application as application
from officecli_html_to_pptx import cli
from officecli_html_to_pptx._internal.officecli_compiler import OfficeCLICompilationResult
from officecli_html_to_pptx.protocol import Diagnostic, exit_code_for_status, result


AUTHOR_HTML = """<!doctype html><html><head><style>
.slide { width: 1920px; height: 1080px; }
</style></head><body><section class="slide"><h1>Hello</h1></section></body></html>"""


def _author(tmp_path: Path) -> Path:
    path = tmp_path / "author.html"
    path.write_text(AUTHOR_HTML, encoding="utf-8")
    return path


def test_capabilities_are_author_only_and_use_product_envelope() -> None:
    payload = application.get_capabilities().as_dict()

    assert payload["status"] == "PASS"
    assert payload["product"] == {
        "name": "officecli-html-to-pptx",
        "version": "0.2.0",
    }
    assert payload["data"]["commands"] == [
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
    ]
    assert payload["data"]["contract"]["profile"] == "author"
    assert payload["data"]["rendering_compatibility"]["officecli"] == ">=1.0.147"
    assert payload["data"]["scope"]["officehtml_import"] is False
    assert "profile" not in payload["data"]["contract"]["css_properties"]


def test_protocol_exit_classes_and_cli_json_stdout_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert exit_code_for_status("PASS") == 0
    assert exit_code_for_status("VISUAL_REVIEW_REQUIRED") == 0
    assert exit_code_for_status("BLOCK") == 2
    assert exit_code_for_status("REVISION_REQUIRED") == 2
    assert exit_code_for_status(
        "ERROR",
        (Diagnostic("invalid_input", "error", "bad"),),
    ) == 3
    assert exit_code_for_status(
        "ERROR",
        (Diagnostic("unexpected_error", "error", "bad"),),
    ) == 4

    code = cli.main(["check", str(tmp_path / "missing.html"), "--json"])
    captured = capsys.readouterr()
    assert code == 3
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "ERROR"


def test_check_pass_and_block_keep_contract_detail(tmp_path: Path) -> None:
    author = _author(tmp_path)
    passed = application.check_author_html(author)
    assert passed.status == "PASS"
    assert passed.data["contract"]["profile"] == "author"

    blocked = tmp_path / "blocked.html"
    blocked.write_text(
        AUTHOR_HTML.replace("<h1>Hello</h1>", "<canvas>bad</canvas>"),
        encoding="utf-8",
    )
    result_value = application.check_author_html(blocked)
    assert result_value.status == "BLOCK"
    assert result_value.exit_code == 2
    assert any(item.code == "unsupported_visible_tag" for item in result_value.diagnostics)
    assert result_value.data["contract"]["css_classifications"]


def test_check_invalid_input_is_exit_class_three(tmp_path: Path) -> None:
    result_value = application.check_author_html(tmp_path / "missing.html")
    assert result_value.status == "ERROR"
    assert result_value.exit_code == 3
    assert result_value.diagnostics[0].code == "invalid_input"


def test_publish_file_retries_windows_sharing_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    sleeps: list[float] = []

    def fake_rename(source: Path, target: Path) -> Path:
        calls.append((source, target))
        if len(calls) < 3:
            error = OSError("file is still in use")
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        return target

    monkeypatch.setattr(Path, "rename", fake_rename)
    monkeypatch.setattr(application.time, "sleep", sleeps.append)

    source = Path("C:/staged.pptx")
    target = Path("C:/published.pptx")
    application._publish_file(source, target)

    assert calls == [(source, target)] * 3
    assert sleeps == [application._PUBLISH_RETRY_DELAY_SECONDS] * 2


def _patch_successful_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        application,
        "diagnose_environment",
        lambda **_: result(
            "doctor",
            "PASS",
            data={"runtime": {"formal_pair": {"officecli": ">=1.0.147"}}},
        ),
    )

    async def fake_compile(input_html: str, profile: str, output: str) -> OfficeCLICompilationResult:
        assert profile == "author"
        Path(output).write_bytes(b"fake-pptx")
        return OfficeCLICompilationResult(output, "author", 1, 1, (), {"slide_count": 1})

    monkeypatch.setattr(application, "compile_officecli", fake_compile)
    monkeypatch.setattr(application, "_run_officecli", lambda *args: "")
    monkeypatch.setattr(application, "_validate_build_output", lambda _: {"status": "PASS"})
    monkeypatch.setattr(application, "_collect_issues", lambda _: {"status": "PASS", "output": ""})

    async def fake_comparisons(_: Path, __: Path, destination: Path, ___: int) -> list[dict[str, str | int]]:
        destination.mkdir(parents=True, exist_ok=True)
        image = destination / "slide-001.png"
        image.write_bytes(b"comparison")
        return [{"slide": 1, "path": str(image), "sha256": application._sha256(image)}]

    monkeypatch.setattr(application, "_make_comparisons", fake_comparisons)


def test_build_publishes_bound_pair_and_finalize_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"

    built = asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    assert built.status == "VISUAL_REVIEW_REQUIRED"
    assert built.exit_code == 0
    assert output.is_file()
    assert evidence.is_dir()
    assert sorted(item.name for item in evidence.iterdir()) == sorted(
        [
            "capabilities.json",
            "comparisons",
            "contract.json",
            "issues.json",
            "manifest.json",
            "result.json",
            "runtime.json",
            "validate.json",
            "visual-review.json",
        ]
    )
    assert (evidence / "comparisons" / "slide-001.png").is_file()
    assert not list(evidence.rglob("*html_slide*"))
    assert not list(evidence.rglob("*pptx_slide*"))

    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["status"] = "REVIEWED"
    review["slides"][0]["status"] = "PASS"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    finalized = application.finalize_build(evidence)
    assert finalized.status == "PASS"
    assert finalized.exit_code == 0
    assert (evidence / "finalization.json").is_file()


def test_build_refuses_either_pair_target_before_compilation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    (tmp_path / "deck.evidence").mkdir()
    called = False

    async def should_not_compile(*_: object, **__: object) -> OfficeCLICompilationResult:
        nonlocal called
        called = True
        raise AssertionError("compiler should not run on collision")

    monkeypatch.setattr(application, "compile_officecli", should_not_compile)
    value = asyncio.run(application.build_author_html(author, output))
    assert value.status == "BLOCK"
    assert value.diagnostics[0].code == "artifact_exists"
    assert not called
    assert not output.exists()


def test_build_failure_removes_staging_and_publishes_neither_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"

    async def fail_comparisons(*_: object, **__: object) -> list[dict[str, str | int]]:
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(application, "_make_comparisons", fail_comparisons)
    value = asyncio.run(application.build_author_html(author, output))
    assert value.status == "ERROR"
    assert value.exit_code == 4
    assert not output.exists()
    assert not (tmp_path / "deck.evidence").exists()
    assert not list(tmp_path.glob(".deck-*-*"))


def test_finalize_derives_minor_and_major_outcomes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    review_path = evidence / "visual-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["slides"][0]["status"] = "PASS"
    review["slides"][0]["findings"] = [
        {
            "severity": "minor",
            "category": "spacing",
            "location": "title",
            "description": "Two pixels of extra space.",
        }
    ]
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    minor = application.finalize_build(evidence)
    assert minor.status == "PASS_WITH_FINDINGS"
    assert minor.exit_code == 0

    review["slides"][0]["findings"][0] = {
        "severity": "major",
        "category": "content",
        "location": "title",
        "description": "Title is missing.",
        "revision": "Restore the title text.",
    }
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    major = application.finalize_build(evidence)
    assert major.status == "REVISION_REQUIRED"
    assert major.exit_code == 2


def test_finalize_rejects_tampered_comparison_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_build(monkeypatch)
    author = _author(tmp_path)
    output = tmp_path / "deck.pptx"
    asyncio.run(application.build_author_html(author, output))
    evidence = tmp_path / "deck.evidence"
    comparison = evidence / "comparisons" / "slide-001.png"
    comparison.write_bytes(b"tampered")
    value = application.finalize_build(evidence)
    assert value.status == "ERROR"
    assert value.exit_code == 3
    assert value.diagnostics[0].code == "invalid_evidence"
