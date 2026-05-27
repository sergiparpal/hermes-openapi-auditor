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

from ..model import Finding, Severity, Spec
from ..walker import WalkerLike

RULE_ID = "undocumented-errors"
DEFAULT_SEVERITY: Severity = "warning"


def _is_error_response(status: str) -> bool:
    status_str = str(status).strip()
    if not status_str:
        return False
    if status_str == "default":
        return True
    if status_str.upper() in {"4XX", "5XX"}:
        return True
    return status_str[0] in {"4", "5"}


def check(spec: Spec, walker: WalkerLike) -> list[Finding]:
    findings: list[Finding] = []
    for ctx in walker.iter_operations(spec):
        responses = walker.as_dict(ctx.op.get("responses"))
        if not any(_is_error_response(s) for s in responses):
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Operation {ctx.label} declares no 4xx/5xx "
                        "error responses (and no 'default' fallback)."
                    ),
                    path=f"{ctx.pointer}/responses",
                    operation=ctx.label,
                    suggestion=(
                        "Document at least one error response (e.g. 400, 404, "
                        "500) or add a 'default' catch-all."
                    ),
                )
            )
    return findings
