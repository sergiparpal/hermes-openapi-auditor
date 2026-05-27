"""Tool handlers — Hermes-facing entrypoints.

Per Hermes' handler contract (see plan §2.6.1):

- Signature: ``(args: dict, **kwargs) -> str``
- Return: a JSON string on every code path, including errors.
- Never raises — every exception is converted to an ``{"error": "..."}`` payload.

This module is intentionally thin: it translates the Hermes handler protocol
to the internal :mod:`auditor.runner` API which uses normal Python types.
"""

from __future__ import annotations

import json
from typing import Any

from .auditor.detect import InvalidSpecError
from .auditor.runner import audit_openapi_spec as _run_audit

_ALLOWED_PROFILES = {"public", "internal", "agent-consumed"}
_ALLOWED_THRESHOLDS = {"info", "warning", "error"}
_ALLOWED_FORMATS = {"json", "markdown"}


def audit_openapi_spec(args: dict[str, Any], **kwargs: Any) -> str:
    """Hermes handler for the ``audit_openapi_spec`` tool.

    Always returns a JSON string. Never raises. See plan §2.6.1 for the
    full contract.
    """
    try:
        path = args.get("path")
        if not path:
            return json.dumps({"error": "'path' argument is required"})

        profile = args.get("profile", "agent-consumed")
        if profile not in _ALLOWED_PROFILES:
            return json.dumps(
                {
                    "error": (
                        f"invalid profile {profile!r}; expected one of {sorted(_ALLOWED_PROFILES)}"
                    )
                }
            )

        threshold = args.get("severity_threshold", "warning")
        if threshold not in _ALLOWED_THRESHOLDS:
            return json.dumps(
                {
                    "error": (
                        f"invalid severity_threshold {threshold!r}; expected "
                        f"one of {sorted(_ALLOWED_THRESHOLDS)}"
                    )
                }
            )

        output_format = args.get("format", "json")
        if output_format not in _ALLOWED_FORMATS:
            return json.dumps(
                {
                    "error": (
                        f"invalid format {output_format!r}; expected one of "
                        f"{sorted(_ALLOWED_FORMATS)}"
                    )
                }
            )

        result = _run_audit(
            path=path,
            profile=profile,
            severity_threshold=threshold,
            output_format=output_format,
        )
        return json.dumps(result)

    except FileNotFoundError as e:
        return json.dumps({"error": f"file not found: {e}"})
    except InvalidSpecError as e:
        return json.dumps({"error": f"invalid spec: {e}"})
    except Exception as e:
        # Catch-all: handler MUST NOT raise.
        return json.dumps({"error": f"audit failed: {type(e).__name__}: {e}"})
