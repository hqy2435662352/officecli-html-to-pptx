"""The package's exported surface is exactly what ADR 0030 allows.

ADR 0030 exports **one** hidden projection seam and keeps everything behind it
internal, because "the reader stays private: the OfficeCLI command shapes, the
object-capture DTOs, the classification rules and the emitter are all
implementation a caller never names, so they can be reworked without a
compatibility promise."

The V0.4.2 gate briefly widened that: it exported its own evidence DTOs, its
normalization-rule constants and its mapping error, so the package root published
a second API beside the seam.  None of them is a name a caller has to write down
-- each is reachable through the record the seam returns -- so they are back in
``_internal``, and this module pins the surface so it cannot widen again by
accident.

A public name is a compatibility promise.  That is the whole cost, and it is why
the frozen set below is compared exactly rather than as a subset.
"""

from __future__ import annotations

import pytest

import officecli_html_to_pptx
from officecli_html_to_pptx._internal import source_delta_gate

#: Every public name this package exports.  Written out in full on purpose: a
#: tuple would let a rename slip past a set comparison, so the literal is the
#: expectation and the set comparison is only for order-insensitivity.
EXPORTED = (
    "Artifact",
    "CommandResult",
    "Diagnostic",
    "DISPOSITION_BASE_ONLY",
    "DISPOSITION_CANONICAL",
    "DISPOSITION_LOCKED",
    "DISPOSITION_UNRESOLVED",
    "DISPOSITION_UNSUPPORTED",
    "DISPOSITIONS",
    "REASON_CODES",
    "DispositionLedgerEntry",
    "GateOutcome",
    "MissingPageError",
    "OutputCollisionError",
    "PageSelection",
    "ProjectedObject",
    "ProjectedSlide",
    "ProjectionBlockedError",
    "ProjectionDiagnostic",
    "ProjectionError",
    "ProjectionGateResult",
    "ProjectionResult",
    "ProjectionSelectionError",
    "ProjectionSourceError",
    "ProjectionSourceRecord",
    "SelectedPage",
    "SourceChangedError",
    "build_author_html",
    "check_author_html",
    "diagnose_environment",
    "finalize_build",
    "gate_projected_author_html",
    "get_capabilities",
    "project_pptx_to_author_html",
    "__version__",
)

#: The names the V0.4.2 slice added to the package root and then withdrew.  They
#: are the gate's evidence records, its rule constants, and the mapping error it
#: raises -- reachable through ``ProjectionGateResult`` and never by name.
WITHDRAWN = (
    "AmbiguousMappingError",
    "ArtifactHash",
    "COMPARISON_RULES",
    "GateDiagnostic",
    "GatePageRecord",
    "MaterialDelta",
    "NormalizationRule",
    "ProxyIsolationProof",
    "RetainedFinding",
    "ScopeEvidence",
    "TableCheck",
    "TextReadback",
)

#: The two functions of the hidden slice, and the one of them ADR 0030 names.
PROJECTION_SEAM = "project_pptx_to_author_html"
GATE_SEAM = "gate_projected_author_html"


def test_the_exported_names_are_exactly_the_frozen_set() -> None:
    assert set(officecli_html_to_pptx.__all__) == set(EXPORTED)
    assert len(officecli_html_to_pptx.__all__) == len(EXPORTED), (
        "__all__ carries a duplicate"
    )


def test_every_exported_name_really_resolves() -> None:
    """``__all__`` is a promise, so every entry has to exist."""
    missing = [
        name for name in officecli_html_to_pptx.__all__
        if not hasattr(officecli_html_to_pptx, name)
    ]
    assert missing == [], f"__all__ names an attribute the package does not have: {missing}"


def test_the_withdrawn_names_are_not_on_the_package_root() -> None:
    """Not merely absent from ``__all__``: not reachable by attribute either."""
    reachable = [
        name for name in WITHDRAWN if hasattr(officecli_html_to_pptx, name)
    ]
    assert reachable == [], (
        "these names are still published at the package root: " + ", ".join(reachable)
    )


def test_the_withdrawn_names_are_still_where_the_seam_uses_them() -> None:
    """Withdrawn from the surface, not deleted: the internal modules still own them."""
    from officecli_html_to_pptx._internal import author_projector

    absent = [
        name
        for name in WITHDRAWN
        if not hasattr(source_delta_gate, name) and not hasattr(author_projector, name)
    ]
    assert absent == [], (
        "withdrawing a name from the public surface must not remove it from the "
        "module that implements it; missing: " + ", ".join(absent)
    )


def test_the_slice_exports_its_two_seams_and_no_third() -> None:
    """ADR 0030's rule, as a count rather than as an intention.

    The projection seam and the acceptance gate are the two functions this slice
    adds.  Every other exported callable predates the slice and belongs to the
    Author command surface, which is why the check is against the commands rather
    than against the whole list.
    """
    from officecli_html_to_pptx.application import PUBLIC_COMMANDS

    assert PROJECTION_SEAM in officecli_html_to_pptx.__all__
    assert GATE_SEAM in officecli_html_to_pptx.__all__
    # Neither seam is a command, and the hidden slice introduced no command.
    assert PROJECTION_SEAM not in PUBLIC_COMMANDS
    assert GATE_SEAM not in PUBLIC_COMMANDS
    assert PUBLIC_COMMANDS == (
        "capabilities",
        "doctor",
        "check",
        "build",
        "finalize",
    )
    added = {PROJECTION_SEAM, GATE_SEAM}
    exported_functions = {
        name
        for name in officecli_html_to_pptx.__all__
        if callable(getattr(officecli_html_to_pptx, name))
        and not isinstance(getattr(officecli_html_to_pptx, name), type)
    }
    # The Author surface's own five commands plus the two seams; anything else
    # would be a third entry point for the projection slice.
    assert exported_functions == {
        "build_author_html",
        "check_author_html",
        "diagnose_environment",
        "finalize_build",
        "get_capabilities",
    } | added, sorted(exported_functions)


def test_the_gate_result_is_readable_without_naming_its_records() -> None:
    """The reason the withdrawn names can be internal: the records nest.

    A caller reads the gate's evidence through the returned result's own fields.
    This asserts the shape that makes that true, so a future change that made one
    of them unreachable would fail here rather than silently forcing an export.
    """
    from officecli_html_to_pptx import ProjectionGateResult

    annotations = getattr(ProjectionGateResult, "__annotations__", {})
    for field in (
        "outcome",
        "published",
        "report_path",
        "diagnostics",
        "pages",
        "ledger",
        "projected",
    ):
        assert field in annotations, (
            f"ProjectionGateResult no longer exposes {field!r}, so a caller would "
            "have to name an internal record to read the decision"
        )


def test_the_hidden_seam_is_absent_from_the_capability_manifest() -> None:
    """No capability claim, no scope claim, no object kind comes with the slice."""
    from officecli_html_to_pptx import get_capabilities

    data = get_capabilities().data
    declared = set(data) | set(data.get("scope") or {})
    assert not any(
        token in name for name in declared for token in ("project", "gate", "ledger")
    ), sorted(declared)
    assert data["scope"]["existing_pptx_editing"] is False
    assert data["scope"]["officehtml_import"] is False


if __name__ == "__main__":  # pragma: no cover - manual run
    raise SystemExit(pytest.main([__file__, "-q"]))
