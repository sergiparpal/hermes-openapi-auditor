"""Helper for rules that branch by ``spec.version``.

Several rules emit different checks for Swagger 2.0, OpenAPI 3.0, and
3.1 (``nullable`` only exists in 3.0; ``exclusiveMinimum: bool`` is a
3.0→3.1 migration error; etc.). The :func:`by_version` adapter turns
that branching into a small declarative dict so rule bodies stay
focused on the check, not the dispatch.

Rules that don't branch by version use plain functions — there's no
need to round-trip through this helper.
"""

from __future__ import annotations

from collections.abc import Callable

from ..model import Finding, Spec, Version
from ..walker import WalkerLike

VersionCheck = Callable[[Spec, WalkerLike], list[Finding]]


def by_version(handlers: dict[Version, VersionCheck]) -> VersionCheck:
    """Return a ``check`` callable that dispatches on ``spec.version``.

    Versions not present in ``handlers`` produce no findings — this is a
    deliberate fail-open: a future 3.2 spec passing through a rule that
    only knows about 2.0/3.0/3.1 should silently skip that rule rather
    than crash the whole audit.
    """

    def check(spec: Spec, walker: WalkerLike) -> list[Finding]:
        handler = handlers.get(spec.version)
        if handler is None:
            return []
        return handler(spec, walker)

    return check
