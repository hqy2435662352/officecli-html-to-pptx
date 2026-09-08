from __future__ import annotations

from pathlib import Path

from html_to_pptx.contract import (
    CONTRACT_VERSION,
    OFFICECLI_COMPATIBILITY_BASELINE,
    check_contract,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "deck.html"
    path.write_text(text, encoding="utf-8")
    return path


def test_contract_publishes_version_and_officecli_baseline() -> None:
    assert CONTRACT_VERSION == "1.0"
    assert OFFICECLI_COMPATIBILITY_BASELINE == "1.0.147"


def test_author_profile_blocks_visible_unsupported_content_but_ignores_preview_runtime(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        .slide { width: 1920px; height: 1080px; }
        </style></head><body>
        <section class="slide active">
          <div class="slide-counter">1 / 1</div>
          <canvas width="20" height="20"></canvas>
          <p>Visible text</p>
        </section>
        <script>document.querySelector('.slide').classList.add('active')</script>
        </body></html>""",
    )

    report = check_contract(path, "author")

    assert report.blocked
    assert any(item.code == "unsupported_visible_tag" for item in report.diagnostics)
    assert not any(item.source_object and "script" in item.source_object for item in report.diagnostics)
    assert not any(item.source_object and "slide-counter" in item.source_object for item in report.diagnostics)


def test_officehtml_profile_ignores_viewer_chrome_and_pathless_master_projection(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><body>
        <div class="sidebar"><button data-path="/viewer/button">Ignore</button></div>
        <div class="slide-container"><div class="slide" style="width:960pt;height:540pt;background:#fff">
          <div class="shape" style="left:0pt;top:0pt;width:20pt;height:20pt;background:#000">master</div>
          <div class="shape" data-path="/slide[1]/shape[@id=2]"
               style="left:10pt;top:10pt;width:80pt;height:24pt;background:#e60012">Owned</div>
        </div></div>
        <script>document.body.append('Ignore')</script>
        </body></html>""",
    )

    report = check_contract(path, "officehtml")

    assert not report.blocked
    assert not any(item.code == "legacy_renderer_table_limit" for item in report.diagnostics)


def test_officehtml_profile_blocks_an_owned_deferred_object_kind(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><body><div class="slide" style="width:960pt;height:540pt">
          <div class="chart" data-path="/slide[1]/chart[1]"
               style="left:10pt;top:10pt;width:80pt;height:24pt">Chart</div>
        </div></body></html>""",
    )

    report = check_contract(path, "officehtml")

    assert report.blocked
    diagnostic = next(item for item in report.diagnostics if item.code == "unsupported_object_kind")
    assert diagnostic.source_object == "/slide[1]/chart[1]"


def test_author_profile_blocks_external_runtime_resources(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head>
        <link rel="stylesheet" href="https://example.invalid/deck.css">
        <style>.slide { width:1920px; height:1080px; }</style>
        </head><body><section class="slide"></section>
        <script src="https://example.invalid/deck.js"></script></body></html>""",
    )

    report = check_contract(path, "author")

    assert report.blocked
    assert sum(item.code == "external_resource" for item in report.diagnostics) == 2


def test_author_profile_classifies_visible_css_and_blocks_box_shadow(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        .slide { width:1920px; height:1080px; display:block; }
        .card { position:absolute; left:10px; top:10px; width:100px; height:50px;
                background:#fff; box-shadow:0 2px 4px #000; }
        </style></head><body><section class="slide"><div class="card">Text</div>
        </section></body></html>""",
    )

    report = check_contract(path, "author")

    assert report.blocked
    diagnostic = next(
        item for item in report.diagnostics if item.code == "unsupported_visible_css"
    )
    assert "box-shadow" in diagnostic.message
    classifications = report.as_dict()["css_classifications"]
    by_property = {item["property"]: item["classification"] for item in classifications}
    assert by_property["display"] == "measurement-only"
    assert by_property["background"] == "rendered"
    assert by_property["box-shadow"] == "unsupported"


def test_author_profile_ignores_unused_and_hidden_unsupported_css(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        .slide { width:1920px; height:1080px; }
        .unused { box-shadow:0 2px 4px #000; }
        .hidden { display:none; box-shadow:0 2px 4px #000; }
        </style></head><body><section class="slide">
          <div class="hidden">Not painted</div>
          <div style="display:none; box-shadow:0 2px 4px #000">Not painted</div>
          <div>Visible text</div>
        </section></body></html>""",
    )

    report = check_contract(path, "author")

    assert not report.blocked
    assert not any(item.code == "unsupported_visible_css" for item in report.diagnostics)
    assert any(
        item["property"] == "box-shadow" and item["classification"] == "unsupported"
        for item in report.as_dict()["css_classifications"]
    )


def test_author_profile_uses_visible_slide_selector_for_canvas_dimensions(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        .slide { width:1920px; height:1080px; }
        .slide .content { width:11px; height:22px; }
        </style></head><body><section class="slide"><div class="content">Visible</div>
        </section></body></html>""",
    )

    report = check_contract(path, "author")

    assert not report.blocked
    assert not any(item.code == "invalid_author_canvas" for item in report.diagnostics)


def test_author_profile_ignores_stylesheet_hidden_and_zero_opacity_nodes(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        .slide { width:1920px; height:1080px; }
        .hidden { display:none; }
        .hidden .effect { box-shadow:0 2px 4px #000; }
        .transparent { opacity:0; }
        .transparent .effect { filter:blur(4px); }
        </style></head><body><section class="slide">
          <div class="hidden"><div class="effect">Not painted</div></div>
          <div class="transparent"><div class="effect">Not painted</div></div>
          <div>Visible text</div>
        </section></body></html>""",
    )

    report = check_contract(path, "author")

    assert not report.blocked
    assert not any(item.code == "unsupported_visible_css" for item in report.diagnostics)


def test_author_profile_rejects_external_font_face_source(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """<!doctype html><html><head><style>
        @font-face { font-family: Example; src: url(https://example.invalid/font.woff2); }
        .slide { width:1920px; height:1080px; }
        </style></head><body><section class="slide">Visible</section></body></html>""",
    )

    report = check_contract(path, "author")

    assert report.blocked
    assert any(
        item.code == "external_resource" and "font-face" in item.message
        for item in report.diagnostics
    )
