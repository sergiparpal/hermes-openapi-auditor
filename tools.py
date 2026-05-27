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
from .auditor.model import (
    DEFAULT_FORMAT,
    DEFAULT_PROFILE,
    DEFAULT_THRESHOLD,
    OUTPUT_FORMATS,
    PROFILE_NAMES,
    SEVERITY_LEVELS,
)
from .auditor.runner import audit_openapi_spec as _run_audit


def _enum_error(name: str, value: Any, allowed: tuple[str, ...]) -> str:
    """Build the JSON error payload for an out-of-range enum argument."""
    return json.dumps({"error": f"invalid {name} {value!r}; expected one of {list(allowed)}"})


def audit_openapi_spec(args: dict[str, Any], **kwargs: Any) -> str:
    """Hermes handler for the ``audit_openapi_spec`` tool.

    Always returns a JSON string. Never raises. See plan §2.6.1 for the
    full contract.
    """
    try:
        path = args.get("path")
        if not path:
            return json.dumps({"error": "'path' argument is required"})

        profile = args.get("profile", DEFAULT_PROFILE)
        if profile not in PROFILE_NAMES:
            return _enum_error("profile", profile, PROFILE_NAMES)

        threshold = args.get("severity_threshold", DEFAULT_THRESHOLD)
        if threshold not in SEVERITY_LEVELS:
            return _enum_error("severity_threshold", threshold, SEVERITY_LEVELS)

        output_format = args.get("format", DEFAULT_FORMAT)
        if output_format not in OUTPUT_FORMATS:
            return _enum_error("format", output_format, OUTPUT_FORMATS)

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
