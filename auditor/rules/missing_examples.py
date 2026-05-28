"""Rule: request/response bodies are missing example values.

Examples are the single most useful signal an LLM has for understanding
what a request or response actually looks like. A spec without examples
forces the LLM to guess plausible shapes from the schema alone.

Divergences by version:

- 2.0: ``examples`` (dict keyed by mime) on responses; ``example``
  (singular) on schemas. Body parameters carry their schema inline.
- 3.0: ``example`` or ``examples`` (named, plural) inside each media
  type object.
- 3.1: same as 3.0 plus the JSON Schema 2020-12 ``examples: [...]``
  array at the schema level — that satisfies the rule too.
"""

from __future__ import annotations

from typing import Any

from ..model import Finding, Severity, Spec
from ..walker import OperationCtx, WalkerLike
from ._dispatch import by_version

RULE_ID = "missing-examples"
DEFAULT_SEVERITY: Severity = "warning"


def _is_documented_response(status: str) -> bool:
    """Only count 2xx/4xx/5xx and 'default' responses; ignore informational/redirect."""
    status_str = str(status)
    if status_str == "default":
        return True
    if status_str.upper() in {"2XX", "4XX", "5XX"}:
        return True
    return bool(status_str) and status_str[0] in {"2", "4", "5"}


def _check_v2(spec: Spec, walker: WalkerLike) -> list[Finding]:
    findings: list[Finding] = []
    for ctx in walker.iter_operations(spec):
        body_param = next(
            (
                p
                for p in walker.as_list(ctx.op.get("parameters"))
                if isinstance(p, dict) and p.get("in") == "body"
            ),
            None,
        )
        if body_param is not None:
            schema = body_param.get("schema") or {}
            if "example" not in schema:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=f"Request body of {ctx.label} has no 'example' on its schema.",
                        path=f"{ctx.pointer}/parameters",
                        operation=ctx.label,
                        suggestion="Add an 'example' field to the body parameter's schema.",
                    )
                )

        for status, response in walker.as_dict(ctx.op.get("responses")).items():
            if not _is_documented_response(status):
                continue
            if not isinstance(response, dict):
                continue
            schema = response.get("schema")
            if not schema:
                continue
            if not response.get("examples") and "example" not in schema:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=f"Response {status} of {ctx.label} has no example.",
                        path=f"{ctx.pointer}/responses/{status}",
                        operation=ctx.label,
                        suggestion=(
                            "Add 'examples' (keyed by mime) on the response, "
                            "or 'example' on the schema."
                        ),
                    )
                )
    return findings


def _check_v3(
    spec: Spec,
    walker: WalkerLike,
    *,
    allow_schema_examples_array: bool,
) -> list[Finding]:
    """Shared body for OpenAPI 3.0 and 3.1.

    The only behavioral difference between the two is whether a schema-
    level ``examples: [...]`` array (JSON Schema 2020-12, 3.1-only)
    counts as documenting the example. Everything else — message
    wording, paths, suggestions, response filtering — is identical.
    """
    suggestion = _suggestion_text(allow_schema_examples_array)
    findings: list[Finding] = []
    for ctx in walker.iter_operations(spec):
        findings.extend(
            _request_body_findings(ctx, walker, allow_schema_examples_array, suggestion)
        )
        findings.extend(_response_findings(ctx, walker, allow_schema_examples_array, suggestion))
    return findings


def _request_body_findings(
    ctx: OperationCtx,
    walker: WalkerLike,
    allow_schema_examples_array: bool,
    suggestion: str,
) -> list[Finding]:
    request_body = ctx.op.get("requestBody")
    if not isinstance(request_body, dict):
        return []
    findings: list[Finding] = []
    for mime, media in walker.as_dict(request_body.get("content")).items():
        if _has_example(media, allow_schema_examples_array):
            continue
        findings.append(
            Finding(
                rule_id=RULE_ID,
                severity=DEFAULT_SEVERITY,
                message=f"Request body {mime} of {ctx.label} has no example.",
                path=(f"{ctx.pointer}/requestBody/content/{walker.encode_pointer_segment(mime)}"),
                operation=ctx.label,
                suggestion=suggestion,
            )
        )
    return findings


def _response_findings(
    ctx: OperationCtx,
    walker: WalkerLike,
    allow_schema_examples_array: bool,
    suggestion: str,
) -> list[Finding]:
    findings: list[Finding] = []
    for status, response in walker.as_dict(ctx.op.get("responses")).items():
        if not _is_documented_response(status) or not isinstance(response, dict):
            continue
        for mime, media in walker.as_dict(response.get("content")).items():
            if _has_example(media, allow_schema_examples_array):
                continue
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(f"Response {status} ({mime}) of {ctx.label} has no example."),
                    path=(
                        f"{ctx.pointer}/responses/{status}/content/"
                        f"{walker.encode_pointer_segment(mime)}"
                    ),
                    operation=ctx.label,
                    suggestion=suggestion,
                )
            )
    return findings


def _has_example(media: Any, allow_schema_examples_array: bool) -> bool:
    """Return True if ``media`` (or its schema) documents at least one example."""
    if not isinstance(media, dict):
        return True  # nothing to check — don't false-positive
    if "example" in media or media.get("examples"):
        return True
    schema = media.get("schema") or {}
    if "example" in schema:
        return True
    if allow_schema_examples_array:
        schema_examples = schema.get("examples")
        return isinstance(schema_examples, list) and bool(schema_examples)
    return False


def _suggestion_text(allow_schema_examples_array: bool) -> str:
    if allow_schema_examples_array:
        return (
            "Add 'example'/'examples' on the mediaType or "
            "on the schema (3.1 supports 'examples: [...]')."
        )
    return "Add 'example'/'examples' on the mediaType or 'example' on the schema."


def _check_v3_0(spec: Spec, walker: WalkerLike) -> list[Finding]:
    return _check_v3(spec, walker, allow_schema_examples_array=False)


def _check_v3_1(spec: Spec, walker: WalkerLike) -> list[Finding]:
    return _check_v3(spec, walker, allow_schema_examples_array=True)


check = by_version(
    {
        "2.0": _check_v2,
        "3.0": _check_v3_0,
        "3.1": _check_v3_1,
    }
)
