"""OpenAPI/Swagger version detection.

The detector reads the ``swagger`` and ``openapi`` discriminator fields and
maps them to one of the three supported version buckets. Frankenstein
specs (both fields set, or mutually exclusive structural fields mixed)
are rejected.
"""

from __future__ import annotations

from typing import Any

from .model import Version


class InvalidSpecError(ValueError):
    """Raised when a spec is malformed or uses an unsupported version."""


def detect_version(spec: dict[str, Any]) -> Version:
    """Return the spec's version bucket.

    Raises:
        InvalidSpecError: if the spec lacks any version discriminator,
            sets both ``swagger`` and ``openapi``, or declares a version
            outside the 2.0 / 3.0.x / 3.1.x supported set.
    """
    swagger = spec.get("swagger")
    openapi = spec.get("openapi")

    if swagger is not None and openapi is not None:
        raise InvalidSpecError("spec declares both 'swagger' and 'openapi' fields; pick one")

    if swagger is not None:
        swagger_str = str(swagger)
        if swagger_str == "2.0":
            return "2.0"
        raise InvalidSpecError(
            f"unsupported swagger version: {swagger_str!r} (only '2.0' is recognized)"
        )

    if openapi is not None:
        openapi_str = str(openapi)
        # Accept bare major.minor (``3.0``) and patch-versioned (``3.0.3``) alike.
        if openapi_str == "3.0" or openapi_str.startswith("3.0."):
            return "3.0"
        if openapi_str == "3.1" or openapi_str.startswith("3.1."):
            return "3.1"
        raise InvalidSpecError(
            f"unsupported openapi version: {openapi_str!r} (only 3.0.x and 3.1.x are recognized)"
        )

    raise InvalidSpecError("spec has neither 'swagger' nor 'openapi' field")
