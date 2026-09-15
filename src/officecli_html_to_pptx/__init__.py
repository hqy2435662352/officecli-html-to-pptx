"""Public Author-facing API for ``officecli-html-to-pptx``.

Besides the V0.2 Author commands, exactly one experimental development seam is
exported: :func:`project_pptx_to_author_html`, which projects an explicit
ordered selection of pages from one or more existing PPTX files into Canonical
Author HTML for the V0.4.2 representative-projection slice.  It is not a
supported command, is absent from ``PUBLIC_COMMANDS`` and from the capability
manifest, and carries no compatibility promise (see
``docs/adr/0030-export-one-hidden-projection-seam.md``).

The seam's own input and result records -- :class:`SelectedPage`,
:class:`PageSelection`, :class:`DispositionLedgerEntry`,
:class:`ProjectionSourceRecord`, and the projection error family -- are exported
because a caller has to be able to name its selection and read its ledger.  No
new command, manifest entry, or version change comes with them.

The V0.4.2 acceptance gate (:func:`gate_projected_author_html`) is the second
half of the same hidden seam.  Its caller-facing result
(:class:`ProjectionGateResult`) and the enumerated acceptance outcome
(:class:`GateOutcome`) are exported for the same reason: a caller has to be able
to read the decision and the evidence behind it.  It too is not a supported
command and carries no compatibility promise.
"""

from importlib.metadata import PackageNotFoundError, version

from .application import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)
from .protocol import Artifact, CommandResult, Diagnostic
from ._internal.author_projector import (
    DISPOSITION_BASE_ONLY,
    DISPOSITION_CANONICAL,
    DISPOSITION_LOCKED,
    DISPOSITION_UNRESOLVED,
    DISPOSITION_UNSUPPORTED,
    DISPOSITIONS,
    REASON_CODES,
    AmbiguousMappingError,
    DispositionLedgerEntry,
    MissingPageError,
    OutputCollisionError,
    PageSelection,
    ProjectedObject,
    ProjectedSlide,
    ProjectionBlockedError,
    ProjectionDiagnostic,
    ProjectionError,
    ProjectionResult,
    ProjectionSelectionError,
    ProjectionSourceError,
    ProjectionSourceRecord,
    SelectedPage,
    SourceChangedError,
    project_pptx_to_author_html,
)
from ._internal.source_delta_gate import (
    COMPARISON_RULES,
    ArtifactHash,
    GateDiagnostic,
    GateOutcome,
    GatePageRecord,
    MaterialDelta,
    NormalizationRule,
    ProjectionGateResult,
    ProxyIsolationProof,
    RetainedFinding,
    ScopeEvidence,
    TableCheck,
    TextReadback,
    gate_projected_author_html,
)

try:
    __version__ = version("officecli-html-to-pptx")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = [
    "Artifact",
    "ArtifactHash",
    "CommandResult",
    "COMPARISON_RULES",
    "Diagnostic",
    "DISPOSITION_BASE_ONLY",
    "DISPOSITION_CANONICAL",
    "DISPOSITION_LOCKED",
    "DISPOSITION_UNRESOLVED",
    "DISPOSITION_UNSUPPORTED",
    "DISPOSITIONS",
    "REASON_CODES",
    "AmbiguousMappingError",
    "DispositionLedgerEntry",
    "GateDiagnostic",
    "GateOutcome",
    "GatePageRecord",
    "MaterialDelta",
    "MissingPageError",
    "NormalizationRule",
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
    "ProxyIsolationProof",
    "RetainedFinding",
    "ScopeEvidence",
    "SelectedPage",
    "SourceChangedError",
    "TableCheck",
    "TextReadback",
    "build_author_html",
    "check_author_html",
    "diagnose_environment",
    "finalize_build",
    "gate_projected_author_html",
    "get_capabilities",
    "project_pptx_to_author_html",
    "__version__",
]
