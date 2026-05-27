"""Domain model: ``Finding``, ``Spec``, and the ``Severity``/``Version`` literals.

The model layer is independent of Hermes. Every type defined here uses
ordinary Python data structures so the engine can be unit-tested in
isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Version = Literal["2.0", "3.0", "3.1"]
"""The three OpenAPI/Swagger versions this plugin supports."""

Severity = Literal["info", "warning", "error"]
"""Finding severity levels, ordered low to high."""

_SEVERITY_ORDER: dict[Severity, int] = {"info": 0, "warning": 1, "error": 2}


def severity_rank(level: Severity) -> int:
    """Numeric rank for ``level``; higher is more severe."""
    return _SEVERITY_ORDER[level]


@dataclass(frozen=True, slots=True)
class Finding:
    """A single audit finding.

    Findings are produced by rules and consumed by the runner. They are
    immutable so a rule can't accidentally mutate a finding already
    appended to another list.
    """

    rule_id: str
    severity: Severity
    message: str
    path: str
    operation: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializable representation used in the JSON output payload."""
        out: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }
        if self.operation is not None:
            out["operation"] = self.operation
        if self.suggestion is not None:
            out["suggestion"] = self.suggestion
        return out


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
    raw: dict[str, Any] = field(default_factory=dict)
    """Original spec dict *before* ``$ref`` resolution. Useful when a rule
    needs to inspect the actual reference rather than its resolved target
    (e.g. to report the pointer the user wrote). Defaults to an empty
    dict when ``resolve_refs=False`` (raw and data are identical)."""
