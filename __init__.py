"""hermes-openapi-auditor — plugin registration entrypoint.

This module is loaded by the Hermes PluginManager at startup. It exposes a
single top-level :func:`register` function that wires the plugin's tool
schemas to their handlers.

Imports of the plugin's own submodules are deferred into :func:`register`
so that this file remains importable in contexts where the parent package
is not yet established (notably pytest's collection of the rootdir as a
``<Package>`` — the directory name has a hyphen, so an eager ``from .``
fails there with ``ImportError``).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__version__ = "0.1.0"


def register(ctx: Any) -> None:
    """Called once by Hermes' PluginManager at startup.

    ``ctx`` is a PluginContext instance. The type is not publicly exported
    by Hermes and may change between versions, so it is intentionally
    untyped at this boundary.
    """
    from . import schemas, tools

    ctx.register_tool(
        name="audit_openapi_spec",
        toolset="qa",
        schema=schemas.AUDIT_OPENAPI_SPEC,
        handler=tools.audit_openapi_spec,
    )
    logger.debug("hermes-openapi-auditor registered: 1 tool (audit_openapi_spec)")
