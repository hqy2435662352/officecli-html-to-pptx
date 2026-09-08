from __future__ import annotations

from html_to_pptx.acceptance import (
    KNOWN_BASELINE_ISSUES,
    KNOWN_BASELINE_DIFFERENCE,
    REGRESSION,
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
