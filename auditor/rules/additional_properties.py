"""Rule: ``additionalProperties: true`` on a schema with named ``properties``.

A schema that lists named properties AND allows arbitrary extras is
ambiguous: the LLM cannot tell whether the named set is exhaustive
or merely illustrative. The fix is usually to either:

- Drop ``additionalProperties`` (defaults to ``true`` in JSON Schema
  but its presence here is at least intentional, which is worse than
  default-by-omission), or
- Set ``additionalProperties: false`` to close the shape, or
- Replace with a typed value such as ``additionalProperties: {type: string}``.

3.1 nuance: if the schema also carries ``unevaluatedProperties`` (an
OpenAPI 3.1 / JSON Schema 2020-12 keyword), the author has explicitly
considered open-ended composition. We downgrade severity to ``info``
and the runner preserves that choice across profile overrides.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from ..model import Finding, Severity, Spec

RULE_ID = "additional-properties"
DEFAULT_SEVERITY: Severity = "warning"


def _has_named_properties(schema: dict[str, Any]) -> bool:
    props = schema.get("properties")
    return isinstance(props, dict) and len(props) > 0


def check(spec: Spec, walker: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    for schema, pointer in walker.iter_all_schemas(spec):
        if schema.get("additionalProperties") is not True:
            continue
        if not _has_named_properties(schema):
            continue

        severity: Severity = DEFAULT_SEVERITY
        if spec.version == "3.1" and "unevaluatedProperties" in schema:
            # Author has explicitly addressed open-ended composition.
            severity = "info"

        findings.append(
            Finding(
                rule_id=RULE_ID,
                severity=severity,
                message=(
                    f"Schema at {pointer} declares named properties AND "
                    "'additionalProperties: true'; the open contract is "
                    "ambiguous for LLM consumers."
                ),
                path=pointer,
                operation=None,
                suggestion=(
                    "Set 'additionalProperties: false' to close the shape, "
                    "or specify a value schema (e.g. 'additionalProperties: "
                    "{type: string}')."
                ),
            )
        )
    return findings
