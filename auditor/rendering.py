"""Output formatting for audit findings.

Each output format is a small callable that turns ``(findings, spec)``
into the dict returned by the runner. The runner does not know which
formats exist — it just looks up the requested key in :data:`RENDERERS`.
Adding a format (e.g. SARIF, HTML) is a new callable plus one line in
:data:`RENDERERS`; the runner is closed for modification.

The markdown renderer's body lives in :func:`to_markdown` so callers
that want only the rendered string (without the JSON envelope) can use
it directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .model import OUTPUT_FORMATS, Finding, OutputFormat, Severity, Spec

Renderer = Callable[[list[Finding], Spec], dict[str, Any]]
"""The output-format strategy type. Returns a JSON-serialisable envelope."""

_SEVERITY_LABEL: dict[Severity, str] = {
    "error": "ERROR",
    "warning": "WARN",
    "info": "INFO",
}

_SPEC_LEVEL_GROUP = "(spec-level)"
"""Group key used for findings that aren't attached to a specific operation."""


def to_markdown(findings: list[Finding], spec: Spec) -> str:
    """Render ``findings`` for ``spec`` as a human-readable markdown report."""
    lines: list[str] = [
        "# OpenAPI audit",
        "",
        f"- **Source:** `{spec.source}`",
        f"- **Version:** {spec.version}",
        f"- **Findings:** {len(findings)}",
        "",
    ]

    if not findings:
        lines.append("_No findings — nice spec._")
        return "\n".join(lines)

    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        key = finding.operation if finding.operation else _SPEC_LEVEL_GROUP
        grouped.setdefault(key, []).append(finding)

    # Render groups in a stable order: operations sorted alphabetically,
    # the spec-level bucket last.
    operation_keys = sorted(k for k in grouped if k != _SPEC_LEVEL_GROUP)
    if _SPEC_LEVEL_GROUP in grouped:
        operation_keys.append(_SPEC_LEVEL_GROUP)

    for op_key in operation_keys:
        lines.append(f"## {op_key}")
        lines.append("")
        for finding in grouped[op_key]:
            label = _SEVERITY_LABEL[finding.severity]
            lines.append(f"- **[{label}] {finding.rule_id}** — {finding.message}")
            lines.append(f"  - Path: `{finding.path}`")
            if finding.suggestion:
                lines.append(f"  - Suggestion: {finding.suggestion}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_json(findings: list[Finding], spec: Spec) -> dict[str, Any]:
    return {
        "version": spec.version,
        "source": spec.source,
        "findings": [f.to_dict() for f in findings],
    }


def _render_markdown(findings: list[Finding], spec: Spec) -> dict[str, Any]:
    return {
        "version": spec.version,
        "source": spec.source,
        "markdown": to_markdown(findings, spec),
    }


RENDERERS: dict[OutputFormat, Renderer] = {
    "json": _render_json,
    "markdown": _render_markdown,
}
"""Map of supported output formats to their renderer callables.

Kept in sync with :data:`auditor.model.OUTPUT_FORMATS` by the assertion
below: a missing or extra key fails fast at import time.
"""

assert set(RENDERERS) == set(OUTPUT_FORMATS), (
    f"RENDERERS keys {sorted(RENDERERS)} do not match OUTPUT_FORMATS {sorted(OUTPUT_FORMATS)}"
)
