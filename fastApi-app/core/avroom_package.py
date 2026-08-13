from __future__ import annotations

"""Deferred imports of the ``avroom_object_removal`` AI package.

The package holds the heavy model stacks, so it is imported lazily at call
time rather than at module import. A missing install is by far the most common
setup failure here, so it is turned into one actionable ``RuntimeError``
instead of a bare ``ModuleNotFoundError`` from somewhere deep in a handler.
"""

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_PACKAGE = "avroom_object_removal"
_INSTALL_HINT = (
    f"Missing local package `{_PACKAGE}`. "
    "Install repo dependencies or run `pip install -e ./TestModules`."
)


def load_avroom_attr(attribute: str, module: str = _PACKAGE) -> Any:
    """Import one attribute from the AI package, or raise with an install hint.

    Args:
        attribute: Name exported by *module* (usually a facade or engine class).
        module: Fully-qualified module path; defaults to the package root.

    Raises:
        RuntimeError: When the package itself is not installed. Any other
            ``ModuleNotFoundError`` (a genuinely broken dependency inside the
            package) propagates untouched.
    """

    try:
        imported = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name == _PACKAGE:
            logger.error("%s not importable (module=%s)", _PACKAGE, module)
            raise RuntimeError(_INSTALL_HINT) from exc
        raise

    return getattr(imported, attribute)
