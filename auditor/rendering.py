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


def to_markdown(findings: list[Finding], spec: Spec) -> str:
    """Render ``findings`` for ``spec`` as a human-readable markdown report."""
    lines: list[str] = []
    lines.append("# OpenAPI audit")
    lines.append("")
    lines.append(f"- **Source:** `{spec.source}`")
    lines.append(f"- **Version:** {spec.version}")
    lines.append(f"- **Findings:** {len(findings)}")
    lines.append("")

    if not findings:
        lines.append("_No findings — nice spec._")
        return "\n".join(lines)

    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        key = f.operation if f.operation else "(spec-level)"
        grouped.setdefault(key, []).append(f)

    # Render groups in a stable order: operations sorted alphabetically,
    # (spec-level) bucket last.
    operation_keys = sorted(k for k in grouped if k != "(spec-level)")
    if "(spec-level)" in grouped:
        operation_keys.append("(spec-level)")

    for op_key in operation_keys:
        lines.append(f"## {op_key}")
        lines.append("")
        for f in grouped[op_key]:
            label = _SEVERITY_LABEL[f.severity]
            lines.append(f"- **[{label}] {f.rule_id}** — {f.message}")
            lines.append(f"  - Path: `{f.path}`")
            if f.suggestion:
                lines.append(f"  - Suggestion: {f.suggestion}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
