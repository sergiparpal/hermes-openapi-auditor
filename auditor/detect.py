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
        s = str(swagger)
        if s == "2.0":
            return "2.0"
        raise InvalidSpecError(f"unsupported swagger version: {s!r} (only '2.0' is recognized)")

    if openapi is not None:
        o = str(openapi)
        if o.startswith("3.0."):
            return "3.0"
        if o.startswith("3.1."):
            return "3.1"
        # Tolerate bare major.minor like "3.0" or "3.1".
        if o == "3.0":
            return "3.0"
        if o == "3.1":
            return "3.1"
        raise InvalidSpecError(
            f"unsupported openapi version: {o!r} (only 3.0.x and 3.1.x are recognized)"
        )

    raise InvalidSpecError("spec has neither 'swagger' nor 'openapi' field")
