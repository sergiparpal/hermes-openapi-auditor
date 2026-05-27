"""Rule: operation declares no 4xx/5xx (or ``default``) responses.

If a spec only documents success responses, an LLM consuming the spec
cannot tell the difference between recoverable input errors (400, 422)
and unrecoverable server failures (500). It is also a strong signal
that error handling was an afterthought.

We accept three signals as "errors documented":
- A status starting with ``4`` or ``5`` (e.g. ``"404"``).
- The 3.x wildcards ``4XX`` / ``5XX``.
- The ``default`` response (treated as a catch-all error in practice).
"""

from __future__ import annotations

from types import ModuleType

from ..model import Finding, Severity, Spec

RULE_ID = "undocumented-errors"
DEFAULT_SEVERITY: Severity = "warning"


def _is_error_response(status: str) -> bool:
    s = str(status).strip()
    if not s:
        return False
    if s == "default":
        return True
    up = s.upper()
    if up in {"4XX", "5XX"}:
        return True
    return s[0] in {"4", "5"}


def check(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        responses = op.get("responses") or {}
        if not any(_is_error_response(s) for s in responses):
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Operation {verb.upper()} {path} declares no 4xx/5xx "
                        "error responses (and no 'default' fallback)."
                    ),
                    path=f"{pointer}/responses",
                    operation=f"{verb.upper()} {path}",
                    suggestion=(
                        "Document at least one error response (e.g. 400, 404, "
                        "500) or add a 'default' catch-all."
                    ),
                )
            )
    return findings
