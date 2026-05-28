"""Audit orchestration: load + walk + run rules + filter + format.

The runner is the single entry point used by the Hermes-facing handler
in ``tools.py``. It returns a Python dict (not a JSON string); the
handler is responsible for ``json.dumps()``. Separating the two keeps
the runner unit-testable without forcing every test to parse JSON.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from . import walker
from .loader import load_spec
from .model import (
    DEFAULT_FORMAT,
    DEFAULT_PROFILE,
    DEFAULT_THRESHOLD,
    Finding,
    OutputFormat,
    ProfileName,
    Severity,
    severity_rank,
)
from .profiles import load_user_overrides, severity_for
from .rendering import RENDERERS
from .rules import REGISTRY


def audit_openapi_spec(
    *,
    path: str,
    profile: str = DEFAULT_PROFILE,
    severity_threshold: Severity = DEFAULT_THRESHOLD,
    output_format: OutputFormat = DEFAULT_FORMAT,
    user_overrides: dict[ProfileName, dict[str, Severity]] | None = None,
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
        user_overrides: Caller-supplied per-rule severity overrides.
            When ``None`` (the default), the runner loads the user
            config from disk via :func:`load_user_overrides`. Pass an
            explicit mapping (including ``{}``) to bypass disk I/O —
            useful in tests and for callers that already hold parsed
            config.

    Returns:
        A dict ready for ``json.dumps``. On success, contains
        ``version``, ``source``, ``findings`` (or ``markdown``). The
        handler in ``tools.py`` converts to a JSON string.
    """
    # validate_schema=False makes the audit maximally helpful: a spec
    # mid-migration (e.g. 3.0 → 3.1) still produces useful findings
    # rather than a hard validation error.
    spec = load_spec(path, validate_schema=False)

    overrides = load_user_overrides() if user_overrides is None else user_overrides

    findings: list[Finding] = []
    for rule in REGISTRY:
        rule_findings = rule.check(spec, walker)
        effective = severity_for(profile, rule.RULE_ID, rule.DEFAULT_SEVERITY, overrides=overrides)
        for f in rule_findings:
            findings.append(_apply_profile_severity(f, effective))

    threshold_rank = severity_rank(severity_threshold)
    findings = [f for f in findings if severity_rank(f.severity) >= threshold_rank]

    findings.sort(key=lambda f: (-severity_rank(f.severity), f.rule_id, f.path))

    return RENDERERS[output_format](findings, spec)


def _apply_profile_severity(finding: Finding, effective: Severity) -> Finding:
    """Re-stamp ``finding.severity`` to the profile-effective level.

    Findings flagged ``severity_pinned`` are left alone: the rule has
    expressed a contextual decision (e.g. ``additional_properties``
    downgrades to ``info`` when ``unevaluatedProperties`` is set) and
    that choice must survive any profile-level override.
    """
    if finding.severity_pinned or finding.severity == effective:
        return finding
    return dataclasses.replace(finding, severity=effective)
