"""Rule: ambiguous or version-incorrect type declarations.

Findings per version (per the plan):

- **2.0:** parameters declared as ``type: string`` with no
  ``format`` / ``enum`` / ``pattern`` constraints. The LLM has no
  signal for what string shape to produce. ``type: file`` is a
  legitimate 2.0 idiom for multipart uploads — not flagged.
- **3.0:** schemas with ``nullable: true`` but no ``type``; and
  ``oneOf`` / ``anyOf`` without a ``discriminator`` hint.
- **3.1:** ``nullable`` was removed in 3.1 (use ``type: [..., "null"]``);
  ``exclusiveMinimum`` / ``exclusiveMaximum`` changed from booleans to
  numbers per JSON Schema 2020-12. Both are common copy-paste errors
  from 3.0 specs.
"""

from __future__ import annotations

from types import ModuleType

from ..model import Finding, Severity, Spec

RULE_ID = "ambiguous-types"
DEFAULT_SEVERITY: Severity = "warning"


def check(spec: Spec, walker: ModuleType) -> list[Finding]:
    if spec.version == "2.0":
        return _check_v2(spec, walker)
    if spec.version == "3.0":
        return _check_v3_0(spec, walker)
    return _check_v3_1(spec, walker)


def _check_v2(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, op_pointer in walker.iter_operations(spec):
        for i, param in enumerate(op.get("parameters", [])):
            if not isinstance(param, dict):
                continue
            location = param.get("in")
            if location == "body":
                # Body params have their type in 'schema'; covered by the
                # generic schema walk below.
                continue
            ptype = param.get("type")
            if ptype != "string":
                continue
            if param.get("format") or param.get("enum") or param.get("pattern"):
                continue
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Parameter {param.get('name', '?')!r} of "
                        f"{verb.upper()} {path} is a bare 'type: string' "
                        "with no format / enum / pattern."
                    ),
                    path=f"{op_pointer}/parameters/{i}",
                    operation=f"{verb.upper()} {path}",
                    suggestion=(
                        "Constrain the string: add 'format' (e.g. 'uuid', "
                        "'date-time'), 'enum' (closed set), or 'pattern' "
                        "(regex)."
                    ),
                )
            )
    return findings


def _check_v3_0(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for schema, pointer in walker.iter_all_schemas(spec):
        if schema.get("nullable") is True and not schema.get("type"):
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Schema at {pointer} declares 'nullable: true' "
                        "without a 'type' — the nullable modifier has nothing "
                        "to apply to."
                    ),
                    path=pointer,
                    operation=None,
                    suggestion="Add an explicit 'type' alongside 'nullable: true'.",
                )
            )
        for kw in ("oneOf", "anyOf"):
            variants = schema.get(kw)
            if isinstance(variants, list) and len(variants) > 1 and "discriminator" not in schema:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=(
                            f"Schema at {pointer} uses '{kw}' with "
                            f"{len(variants)} variants but no 'discriminator' "
                            "— LLMs cannot tell which variant to produce."
                        ),
                        path=pointer,
                        operation=None,
                        suggestion=(
                            "Add a 'discriminator' (with 'propertyName' and "
                            "optional 'mapping') to disambiguate the variants."
                        ),
                    )
                )
                break  # one finding per schema, even if both oneOf and anyOf are present
    return findings


def _check_v3_1(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for schema, pointer in walker.iter_all_schemas(spec):
        if schema.get("nullable") is True:
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=DEFAULT_SEVERITY,
                    message=(
                        f"Schema at {pointer} uses 'nullable: true' — this "
                        "keyword was removed in OpenAPI 3.1."
                    ),
                    path=pointer,
                    operation=None,
                    suggestion=(
                        "Replace with 'type: [..., \"null\"]' (3.1 allows "
                        "type arrays per JSON Schema 2020-12)."
                    ),
                )
            )
        for kw in ("exclusiveMinimum", "exclusiveMaximum"):
            value = schema.get(kw)
            if isinstance(value, bool):
                # Important: bool is a subclass of int in Python — check bool
                # FIRST so True/False isn't accidentally treated as numeric.
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=DEFAULT_SEVERITY,
                        message=(
                            f"Schema at {pointer} has '{kw}: {value}' as a "
                            "boolean — 3.1 (JSON Schema 2020-12) requires a "
                            "number here."
                        ),
                        path=pointer,
                        operation=None,
                        suggestion=(
                            f"Move the bound numeric value into '{kw}' "
                            "directly (e.g. 'exclusiveMinimum: 0')."
                        ),
                    )
                )
    return findings
