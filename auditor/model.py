"""Domain model: ``Finding``, ``Spec``, and the enumerated public values.

The model layer is independent of Hermes. Every type defined here uses
ordinary Python data structures so the engine can be unit-tested in
isolation.

This module is the single source of truth for the enumerated values of
the public types — ``Severity``, ``Version``, ``ProfileName``,
``OutputFormat`` — and for the documented defaults. The Hermes-facing
schema (:mod:`hermes_openapi_auditor.schemas`) and runtime validator
(:mod:`hermes_openapi_auditor.tools`) both derive from these constants
so the two cannot drift apart.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Literal

Version = Literal["2.0", "3.0", "3.1"]
"""The three OpenAPI/Swagger versions this plugin supports."""

Severity = Literal["info", "warning", "error"]
"""Finding severity levels, ordered low to high."""

OutputFormat = Literal["json", "markdown"]
"""Supported output formats."""

# Profile names are open-ended: the user config (~/.hermes/openapi-auditor.yaml)
# can introduce additional profile names beyond the built-ins. The alias is
# kept so call sites read more intent-fully than a bare ``str``.
ProfileName = str

SEVERITY_LEVELS: tuple[Severity, ...] = ("info", "warning", "error")
"""All severity levels in ascending order."""

PROFILE_NAMES: tuple[str, ...] = ("public", "internal", "agent-consumed")
"""The built-in profile names. Used by the LLM-facing schema and the
runtime validator; user config may register additional names at runtime."""

OUTPUT_FORMATS: tuple[OutputFormat, ...] = ("json", "markdown")
"""All supported output formats."""

DEFAULT_PROFILE: str = "agent-consumed"
DEFAULT_THRESHOLD: Severity = "warning"
DEFAULT_FORMAT: OutputFormat = "json"

_SEVERITY_ORDER: dict[Severity, int] = {level: i for i, level in enumerate(SEVERITY_LEVELS)}


def severity_rank(level: Severity) -> int:
    """Numeric rank for ``level``; higher is more severe."""
    return _SEVERITY_ORDER[level]


# Fields that are internal book-keeping and must not leak into the JSON
# output payload. See :attr:`Finding.severity_pinned`.
_INTERNAL_FIELDS: frozenset[str] = frozenset({"severity_pinned"})


@dataclass(frozen=True, slots=True)
class Finding:
    """A single audit finding.

    Findings are produced by rules and consumed by the runner. They are
    immutable so a rule can't accidentally mutate a finding already
    appended to another list.

    ``severity_pinned`` marks findings whose severity was a deliberate
    per-finding decision by the rule (e.g. the ``additional_properties``
    rule downgrades to ``info`` when ``unevaluatedProperties`` is also
    set). Pinned severities survive profile overrides; the field is
    not part of the public output payload.
    """

    rule_id: str
    severity: Severity
    message: str
    path: str
    operation: str | None = None
    suggestion: str | None = None
    severity_pinned: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serializable representation used in the JSON output payload.

        Optional fields (``operation``, ``suggestion``) are omitted when
        ``None`` to keep the payload tight. Internal book-keeping fields
        (``severity_pinned``) are always excluded. Field order matches
        the dataclass declaration order.
        """
        return {
            k: v
            for k, v in dataclasses.asdict(self).items()
            if v is not None and k not in _INTERNAL_FIELDS
        }


@dataclass(slots=True)
class Spec:
    """A loaded, validated OpenAPI/Swagger spec.

    Attributes:
        version: One of ``"2.0"``, ``"3.0"``, ``"3.1"``.
        data: The parsed spec (a dict with ``$ref``\\ s resolved when
            ``resolve_refs=True`` was passed to ``load_spec``).
        source: The path the spec was loaded from. Used in the output
            payload so the agent can refer to it back to the user.
    """

    version: Version
    data: dict[str, Any]
    source: str
