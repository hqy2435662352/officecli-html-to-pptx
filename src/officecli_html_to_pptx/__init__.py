"""Public Author-facing API for ``officecli-html-to-pptx``.

Besides the V0.2 Author commands, exactly one experimental development seam is
exported: :func:`project_pptx_to_author_html`, which projects an existing PPTX
into Canonical Author HTML for the V0.4.1 feasibility probe.  It is not a
supported command, is absent from ``PUBLIC_COMMANDS`` and from the capability
manifest, and carries no compatibility promise (see
``docs/adr/0030-export-one-hidden-projection-seam.md``).
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
    OutputCollisionError,
    ProjectedObject,
    ProjectedSlide,
    ProjectionDiagnostic,
    ProjectionError,
    ProjectionResult,
    project_pptx_to_author_html,
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
    "OutputCollisionError",
    "ProjectedObject",
    "ProjectedSlide",
    "ProjectionDiagnostic",
    "ProjectionError",
    "ProjectionResult",
    "build_author_html",
    "check_author_html",
    "diagnose_environment",
    "finalize_build",
    "get_capabilities",
    "project_pptx_to_author_html",
    "__version__",
]
