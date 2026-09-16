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

Everything *behind* those two results stays internal on purpose.  The gate's
evidence records (the text readback, the table check, the proxy isolation proof,
the disposition page record, material deltas, retained findings, scope evidence,
artifact hashes), its normalization-rule constants, and the mapping error it
raises are reachable through the returned records but are not names a caller
needs to write down, so they live in ``_internal.source_delta_gate``.  ADR 0030
asks for one exported seam, not a second API beside it; a public name is a
compatibility promise, and these carry none.  ``test_v042_public_surface.py``
pins the exact set so the seam cannot widen again by accident.
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
    GateOutcome,
    ProjectionGateResult,
    gate_projected_author_html,
)

try:
    __version__ = version("officecli-html-to-pptx")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = [
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
]
