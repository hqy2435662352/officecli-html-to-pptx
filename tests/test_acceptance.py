from __future__ import annotations

from html_to_pptx.acceptance import (
    AcceptanceReport,
    KNOWN_BASELINE_ISSUES,
    KNOWN_BASELINE_DIFFERENCE,
    PENDING,
    REGRESSION,
    _record_issue_subset_gate,
    _visual_review_payload,
    compare_manifests,
    issue_keys_from_officecli,
)


def test_issue_keys_include_slide_stable_identity_and_subtype() -> None:
    keys = issue_keys_from_officecli(
        """Found 2 issue(s):
  [O1] /slide[1]/shape[@id=7]: text overflow: 2 lines at 7pt need 19pt.
  [O2] /slide[2]/shape[@id=9]: text overflow: 3 lines at 8pt need 30pt.
""",
        {(1, 7): "slide-001-textbox-012", (2, 9): "slide-002-textbox-004"},
    )

    assert keys[0] == {
        "slide": 1,
        "object": "slide-001-textbox-012",
        "subtype": "text_overflow",
    }
    assert keys[1]["slide"] == 2
    assert all(set(key) == {"slide", "object", "subtype"} for key in keys)


def test_known_baseline_findings_are_not_regressions() -> None:
    assert KNOWN_BASELINE_ISSUES
    known = [next(iter(KNOWN_BASELINE_ISSUES))]
    status, findings = compare_manifests(
        {"slide_count": 1, "objects": [{"kind": "shape", "name": "x", "bounds_pt": [0, 0, 1, 1], "text": "A"}]},
        {"slide_count": 1, "objects": [{"kind": "shape", "name": "x", "bounds_pt": [0, 0, 1, 1], "text": "A"}]},
        known_issue_keys=known,
    )

    assert status == KNOWN_BASELINE_DIFFERENCE
    assert not findings


def test_manifest_text_difference_is_a_regression() -> None:
    status, findings = compare_manifests(
        {"slide_count": 1, "objects": [{"kind": "shape", "name": "x", "bounds_pt": [0, 0, 1, 1], "text": "A"}]},
        {"slide_count": 1, "objects": [{"kind": "shape", "name": "x", "bounds_pt": [0, 0, 1, 1], "text": "B"}]},
    )

    assert status == REGRESSION
    assert findings


def test_manifest_style_difference_is_a_regression() -> None:
    expected = {
        "slide_count": 1,
        "objects": [{
            "kind": "textbox",
            "name": "x",
            "bounds_pt": [0, 0, 100, 20],
            "text": "same",
            "properties": {
                "font": "Arial",
                "size": "18pt",
                "color": "#FF0000",
                "bold": "true",
            },
        }],
    }
    actual = {
        "slide_count": 1,
        "objects": [{
            "kind": "textbox",
            "name": "x",
            "bounds_pt": [0, 0, 100, 20],
            "text": "same",
            "properties": {
                "font": "Comic Sans MS",
                "size": "42pt",
                "color": "#000000",
                "bold": "false",
            },
        }],
    }

    status, findings = compare_manifests(expected, actual)

    assert status == REGRESSION
    assert any("supported properties" in item["message"] for item in findings)


def test_same_encoding_picture_content_difference_is_a_regression() -> None:
    expected = {
        "slide_count": 1,
        "object_kind_counts": {"picture": 1},
        "objects": [{
            "kind": "picture",
            "name": "picture-1",
            "bounds_pt": [0, 0, 100, 50],
            "text": "",
            "properties": {},
            "metadata": {
                "picture": {
                    "mime": "image/png",
                    "content_fingerprint": "a" * 64,
                    "intrinsic_size": [20, 10],
                    "object_fit": "fill",
                    "bounds_pt": [0, 0, 100, 50],
                    "fitting": {},
                }
            },
        }],
    }
    actual = {
        **expected,
        "objects": [{
            **expected["objects"][0],
            "metadata": {
                "picture": {
                    "content_type": "image/png",
                    "content_fingerprint": "b" * 64,
                    "intrinsic_size": [20, 10],
                    "object_fit": "fill",
                    "bounds_pt": [0, 0, 100, 50],
                    "fitting": {},
                }
            },
        }],
    }

    status, findings = compare_manifests(expected, actual)

    assert status == REGRESSION
    assert any(
        item["details"].get("different", {}).get("content_fingerprint")
        for item in findings
    )


def test_unapproved_paragraph_line_spacing_difference_is_a_regression() -> None:
    paragraph = {
        "text": "Line",
        "align": "left",
        "space_before_pt": 0,
        "space_after_pt": 0,
        "direction": "ltr",
        "runs": [{
            "text": "Line",
            "font_family": "Arial",
            "font_size_pt": 12,
            "bold": False,
            "italic": False,
            "underline": "none",
            "color": "#000000",
        }],
    }
    expected = {
        "slide_count": 1,
        "object_kind_counts": {"textbox": 1},
        "objects": [{
            "kind": "textbox",
            "name": "textbox-1",
            "bounds_pt": [0, 0, 100, 50],
            "text": "Line",
            "properties": {},
            "paragraphs": [{**paragraph, "line_spacing": "1.4x"}],
        }],
    }
    actual = {
        **expected,
        "objects": [{
            **expected["objects"][0],
            "paragraphs": [{**paragraph, "line_spacing": "1.0x"}],
        }],
    }

    status, findings = compare_manifests(
        expected,
        actual,
        allow_officehtml_projection_defaults=True,
    )

    assert status == REGRESSION
    assert any("paragraph/run formatting" in item["message"] for item in findings)


def test_empty_shape_text_defaults_are_tolerated_only_for_officehtml_projection() -> None:
    expected = {
        "slide_count": 1,
        "objects": [{
            "kind": "shape",
            "name": "background",
            "bounds_pt": [0, 0, 100, 20],
            "text": "",
            "properties": {
                "font": "Segoe UI",
                "size": "8pt",
                "color": "#202124",
                "margin": "12pt,9pt,12pt,9pt",
                "fill": "#FFFFFF",
                "geometry": "roundRect",
            },
        }],
    }
    actual = {
        "slide_count": 1,
        "objects": [{
            "kind": "shape",
            "name": "background",
            "bounds_pt": [0, 0, 100, 20],
            "text": "",
            "properties": {
                "font": "Calibri",
                "size": "8pt",
                "color": "#000000",
                "margin": "0cm",
                "fill": "#FFFFFF",
                "geometry": "roundRect",
            },
        }],
    }

    strict_status, strict_findings = compare_manifests(expected, actual)
    projection_status, projection_findings = compare_manifests(
        expected,
        actual,
        allow_officehtml_projection_defaults=True,
    )

    assert strict_status == REGRESSION
    assert strict_findings
    assert projection_status == "PASS"
    assert not projection_findings


def test_officehtml_projection_compares_effective_font_scale() -> None:
    expected = {
        "slide_count": 1,
        "objects": [{
            "kind": "textbox",
            "name": "label",
            "bounds_pt": [0, 0, 100, 20],
            "text": "Label",
            "properties": {"fontScale": "75"},
            "paragraphs": [{
                "text": "Label",
                "align": "left",
                "direction": "ltr",
                "runs": [{
                    "text": "Label",
                    "font_family": "Segoe UI",
                    "font_size_pt": 20,
                    "bold": True,
                    "italic": False,
                    "underline": "none",
                    "color": "#202124",
                }],
            }],
        }],
    }
    actual = {
        "slide_count": 1,
        "objects": [{
            "kind": "textbox",
            "name": "label",
            "bounds_pt": [0, 0, 100, 20],
            "text": "Label",
            "properties": {},
            "paragraphs": [{
                "text": "Label",
                "align": "left",
                "direction": "ltr",
                "runs": [{
                    "text": "Label",
                    "font_family": "Segoe UI",
                    "font_size_pt": 15,
                    "bold": True,
                    "italic": False,
                    "underline": "none",
                    "color": "#202124",
                }],
            }],
        }],
    }

    status, findings = compare_manifests(
        expected,
        actual,
        allow_officehtml_projection_defaults=True,
    )

    assert status == "PASS"
    assert not findings


def test_visual_gate_is_pending_without_one_result_per_slide() -> None:
    payload = _visual_review_payload(None, 2)

    assert payload["gate"] == PENDING
    assert [slide["status"] for slide in payload["slides"]] == [PENDING, PENDING]


def test_visual_gate_rejects_major_finding_even_when_slide_is_marked_pass() -> None:
    payload = _visual_review_payload(
        {
            "slides": [
                {"slide": 1, "status": "PASS", "findings": []},
                {
                    "slide": 2,
                    "status": "PASS",
                    "findings": [{"severity": "major", "message": "text clipped"}],
                },
            ]
        },
        2,
    )

    assert payload["gate"] == REGRESSION


def test_round_trip_issue_gate_requires_b_to_be_a_subset_of_a() -> None:
    report = AcceptanceReport("PASS", "input.html", "output")

    _record_issue_subset_gate(
        report,
        [{"slide": 1, "object": "shape-a", "subtype": "text_overflow"}],
        [
            {"slide": 1, "object": "shape-a", "subtype": "text_overflow"},
            {"slide": 2, "object": "shape-b", "subtype": "text_overflow"},
        ],
    )

    assert report.checks[-1].status == REGRESSION
