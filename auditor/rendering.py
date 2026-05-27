"""Markdown rendering for audit findings.

The renderer is intentionally simple: a short header with the spec
source and version, followed by a table-of-findings grouped by
operation (or by schema for operation-level-less findings). The
renderer assumes ``findings`` is already sorted by the runner (severity
desc, rule_id, path) — preserve that order within each group.
"""

from __future__ import annotations

from .model import Finding, Severity, Spec

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
