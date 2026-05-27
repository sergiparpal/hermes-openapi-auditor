"""Rule: operation is missing both ``summary`` and ``description``.

An operation that documents neither is opaque to LLM consumers (and
human readers) — the only signals left are the path and verb, which
rarely convey the operation's full intent.
"""

from __future__ import annotations

from types import ModuleType

from ..model import Finding, Severity, Spec

RULE_ID = "missing-descriptions"
DEFAULT_SEVERITY: Severity = "warning"


def check(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        summary = (op.get("summary") or "").strip()
        description = (op.get("description") or "").strip()
        if not summary and not description:
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Operation {verb.upper()} {path} has neither 'summary' nor 'description'."
                    ),
                    path=pointer,
                    operation=f"{verb.upper()} {path}",
                    suggestion=(
                        "Add a one-line 'summary' (≤120 chars) and a longer "
                        "'description' explaining when an LLM should call this."
                    ),
                )
            )
    return findings
