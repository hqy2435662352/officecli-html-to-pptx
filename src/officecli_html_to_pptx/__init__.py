"""Public V0.2 Author-facing API for ``officecli-html-to-pptx``."""

from importlib.metadata import PackageNotFoundError, version

from .application import (
    build_author_html,
    check_author_html,
    diagnose_environment,
    finalize_build,
    get_capabilities,
)
from .protocol import Artifact, CommandResult, Diagnostic

try:
    __version__ = version("officecli-html-to-pptx")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = [
    "Artifact",
    "CommandResult",
    "Diagnostic",
    "build_author_html",
    "check_author_html",
    "diagnose_environment",
    "finalize_build",
    "get_capabilities",
    "__version__",
]
