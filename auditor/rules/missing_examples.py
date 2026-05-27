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

from types import ModuleType
from typing import Any

from ..model import Finding, Severity, Spec

RULE_ID = "missing-examples"
DEFAULT_SEVERITY: Severity = "warning"


def check(spec: Spec, walker: ModuleType) -> list[Finding]:
    if spec.version == "2.0":
        return _check_v2(spec, walker)
    if spec.version == "3.0":
        return _check_v3_0(spec, walker)
    return _check_v3_1(spec, walker)


def _is_documented_response(status: str) -> bool:
    """Only count 2xx/4xx/5xx and 'default' responses; ignore informational/redirect."""
    s = str(status).upper()
    if s == "DEFAULT":
        return True
    if s in {"2XX", "4XX", "5XX"}:
        return True
    return bool(s) and s[0] in {"2", "4", "5"}


def _check_v2(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        body_param = next(
            (p for p in op.get("parameters", []) if isinstance(p, dict) and p.get("in") == "body"),
            None,
        )
        if body_param is not None:
            schema = body_param.get("schema") or {}
            if "example" not in schema:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=(
                            f"Request body of {verb.upper()} {path} has no 'example' on its schema."
                        ),
                        path=f"{pointer}/parameters",
                        operation=f"{verb.upper()} {path}",
                        suggestion=("Add an 'example' field to the body parameter's schema."),
                    )
                )

        for status, response in op.get("responses", {}).items():
            if not _is_documented_response(status):
                continue
            schema = response.get("schema")
            if not schema:
                continue
            if not response.get("examples") and "example" not in schema:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=(f"Response {status} of {verb.upper()} {path} has no example."),
                        path=f"{pointer}/responses/{status}",
                        operation=f"{verb.upper()} {path}",
                        suggestion=(
                            "Add 'examples' (keyed by mime) on the response, "
                            "or 'example' on the schema."
                        ),
                    )
                )
    return findings


def _check_v3_0(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        request_body = op.get("requestBody")
        if isinstance(request_body, dict):
            for mime, media in request_body.get("content", {}).items():
                if not _media_or_schema_has_example_v3_0(media):
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=DEFAULT_SEVERITY,
                            message=(
                                f"Request body {mime} of {verb.upper()} {path} has no example."
                            ),
                            path=(
                                f"{pointer}/requestBody/content/"
                                f"{walker.encode_pointer_segment(mime)}"
                            ),
                            operation=f"{verb.upper()} {path}",
                            suggestion=(
                                "Add 'example'/'examples' on the mediaType or "
                                "'example' on the schema."
                            ),
                        )
                    )

        for status, response in op.get("responses", {}).items():
            if not _is_documented_response(status):
                continue
            for mime, media in response.get("content", {}).items():
                if not _media_or_schema_has_example_v3_0(media):
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=DEFAULT_SEVERITY,
                            message=(
                                f"Response {status} ({mime}) of {verb.upper()} "
                                f"{path} has no example."
                            ),
                            path=(
                                f"{pointer}/responses/{status}/content/"
                                f"{walker.encode_pointer_segment(mime)}"
                            ),
                            operation=f"{verb.upper()} {path}",
                            suggestion=(
                                "Add 'example'/'examples' on the mediaType or "
                                "'example' on the schema."
                            ),
                        )
                    )
    return findings


def _check_v3_1(spec: Spec, walker: ModuleType) -> list[Finding]:
    """Same shape as 3.0 plus schema-level ``examples: [...]`` arrays count."""
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        request_body = op.get("requestBody")
        if isinstance(request_body, dict):
            for mime, media in request_body.get("content", {}).items():
                if not _media_or_schema_has_example_v3_1(media):
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=DEFAULT_SEVERITY,
                            message=(
                                f"Request body {mime} of {verb.upper()} {path} has no example."
                            ),
                            path=(
                                f"{pointer}/requestBody/content/"
                                f"{walker.encode_pointer_segment(mime)}"
                            ),
                            operation=f"{verb.upper()} {path}",
                            suggestion=(
                                "Add 'example'/'examples' on the mediaType, "
                                "or 'example'/'examples' (array) on the schema."
                            ),
                        )
                    )

        for status, response in op.get("responses", {}).items():
            if not _is_documented_response(status):
                continue
            for mime, media in response.get("content", {}).items():
                if not _media_or_schema_has_example_v3_1(media):
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=DEFAULT_SEVERITY,
                            message=(
                                f"Response {status} ({mime}) of {verb.upper()} "
                                f"{path} has no example."
                            ),
                            path=(
                                f"{pointer}/responses/{status}/content/"
                                f"{walker.encode_pointer_segment(mime)}"
                            ),
                            operation=f"{verb.upper()} {path}",
                            suggestion=(
                                "Add 'example'/'examples' on the mediaType or "
                                "on the schema (3.1 supports 'examples: [...]')."
                            ),
                        )
                    )
    return findings


def _media_or_schema_has_example_v3_0(media: Any) -> bool:
    if not isinstance(media, dict):
        return True  # nothing to check — don't false-positive
    if "example" in media or media.get("examples"):
        return True
    schema = media.get("schema") or {}
    return "example" in schema


def _media_or_schema_has_example_v3_1(media: Any) -> bool:
    if not isinstance(media, dict):
        return True
    if "example" in media or media.get("examples"):
        return True
    schema = media.get("schema") or {}
    if "example" in schema:
        return True
    schema_examples = schema.get("examples")
    return isinstance(schema_examples, list) and len(schema_examples) > 0
