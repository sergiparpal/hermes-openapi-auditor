"""Audit orchestration: load + walk + run rules + filter + format.

The runner is the single entry point used by the Hermes-facing handler
in ``tools.py``. It returns a Python dict (not a JSON string); the
handler is responsible for ``json.dumps()``. Separating the two keeps
the runner unit-testable without forcing every test to parse JSON.
"""

from __future__ import annotations

from typing import Any, Literal

from . import rendering, walker
from .loader import load_spec
from .model import Finding, Severity, severity_rank
from .profiles import load_user_overrides, severity_for
from .rules import REGISTRY

OutputFormat = Literal["json", "markdown"]


def audit_openapi_spec(
    *,
    path: str,
    profile: str = "agent-consumed",
    severity_threshold: Severity = "warning",
    output_format: OutputFormat = "json",
) -> dict[str, Any]:
    """Run the full audit pipeline against ``path``.

    Args:
        path: Path to the spec file.
        profile: ``public`` | ``internal`` | ``agent-consumed``. Unknown
            profile names are rejected upstream by the Hermes handler;
            if reached directly, they degrade to "no overrides" (each
            rule's default severity is used).
        severity_threshold: Findings below this level are filtered out.
        output_format: ``json`` returns a structured list; ``markdown``
            wraps a rendered string in a JSON-compatible envelope.

    Returns:
        A dict ready for ``json.dumps``. On success, contains
        ``version``, ``source``, ``findings`` (or ``markdown``). The
        handler in ``tools.py`` converts to a JSON string.
    """
    # validate_schema=False makes the audit maximally helpful: a spec
    # mid-migration (e.g. 3.0 → 3.1) still produces useful findings
    # rather than a hard validation error.
    spec = load_spec(path, validate_schema=False)

    overrides = load_user_overrides()

    findings: list[Finding] = []
    for rule in REGISTRY:
        rule_findings = rule.check(spec, walker)
        rule_default = rule.DEFAULT_SEVERITY
        rule_id = rule.RULE_ID
        effective = severity_for(profile, rule_id, rule_default, overrides=overrides)
        for f in rule_findings:
            # Apply profile-level override only to findings that came in
            # at the rule's default severity. A rule that pre-set a
            # finding to a non-default severity (e.g. the 3.1 nuance in
            # additional_properties) keeps its choice.
            if f.severity == rule_default and f.severity != effective:
                findings.append(
                    Finding(
                        rule_id=f.rule_id,
                        severity=effective,
                        message=f.message,
                        path=f.path,
                        operation=f.operation,
                        suggestion=f.suggestion,
                    )
                )
            else:
                findings.append(f)

    threshold_rank = severity_rank(severity_threshold)
    findings = [f for f in findings if severity_rank(f.severity) >= threshold_rank]

    findings.sort(key=lambda f: (-severity_rank(f.severity), f.rule_id, f.path))

    if output_format == "markdown":
        return {
            "version": spec.version,
            "source": spec.source,
            "markdown": rendering.to_markdown(findings, spec),
        }

    return {
        "version": spec.version,
        "source": spec.source,
        "findings": [f.to_dict() for f in findings],
    }
