"""Audit rule registry.

Each rule module exposes:

- ``RULE_ID: str`` — stable identifier used in finding payloads.
- ``DEFAULT_SEVERITY: Severity`` — severity applied unless overridden by
  the active profile.
- ``check(spec, walker) -> list[Finding]`` — the rule body. The
  ``walker`` argument is the :mod:`auditor.walker` module itself, passed
  in so rules don't need their own imports of every helper.
"""

from __future__ import annotations

from types import ModuleType

from . import (
    additional_properties,
    ambiguous_types,
    missing_descriptions,
    missing_examples,
    undocumented_errors,
)

REGISTRY: list[ModuleType] = [
    missing_descriptions,
    undocumented_errors,
    additional_properties,
    missing_examples,
    ambiguous_types,
]

__all__ = ["REGISTRY"]
