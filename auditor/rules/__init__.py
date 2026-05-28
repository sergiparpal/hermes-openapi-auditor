"""Audit rule registry.

Each entry in :data:`REGISTRY` is a module that satisfies the :class:`Rule`
Protocol — it exposes:

- ``RULE_ID: str`` — stable identifier used in finding payloads.
- ``DEFAULT_SEVERITY: Severity`` — severity applied unless overridden by
  the active profile.
- ``check(spec, walker) -> list[Finding]`` — the rule body. The
  ``walker`` argument is the :mod:`auditor.walker` package itself,
  passed in so rules don't need their own imports of every helper.

Typing the registry against the Protocol means mypy ``--strict`` can
prove every entry has the three attributes, which the previous
``list[ModuleType]`` annotation couldn't.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..model import Finding, Severity
from . import (
    additional_properties,
    ambiguous_types,
    missing_descriptions,
    missing_examples,
    undocumented_errors,
)


class Rule(Protocol):
    """Structural contract for an audit rule.

    ``check`` is declared as ``Callable[..., list[Finding]]`` rather than
    a fully typed callable. The looser arg-list lets plain Python modules
    — whose ``check`` is a free function with named parameters — satisfy
    the Protocol; mypy's strict mode otherwise rejects a named-parameter
    function as an implementation of a positional ``Callable[[A, B], C]``.
    Each rule module still declares its own ``check(spec, walker)``
    signature, so the *implementation* is type-checked when mypy descends
    into the rule body — only the registry-level call boundary is loose.
    """

    RULE_ID: str
    DEFAULT_SEVERITY: Severity
    check: Callable[..., list[Finding]]


REGISTRY: list[Rule] = [
    missing_descriptions,
    undocumented_errors,
    additional_properties,
    missing_examples,
    ambiguous_types,
]

__all__ = ["REGISTRY", "Rule"]
