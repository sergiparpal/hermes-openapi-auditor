"""Version-agnostic iterators over a loaded OpenAPI/Swagger spec.

The walker normalises the differences between Swagger 2.0 and OpenAPI 3.x
so individual rules don't have to. Each iterator yields a small NamedTuple
or 2-tuple that includes a JSON pointer string so findings can carry a
precise location.

Pointer convention: ``#/paths/~1pets/get`` — RFC 6901 (``~0`` escapes
``~``, ``~1`` escapes ``/``).

This package re-exports the public surface; implementation lives in
``_pointer``, ``_operations`` and ``_schemas`` sub-modules.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

from ..model import Spec
from ._operations import (
    OperationCtx,
    iter_operations,
    iter_request_bodies,
    iter_responses,
)
from ._pointer import as_dict, as_list, encode_pointer_segment
from ._schemas import SchemaRef, iter_all_schemas, iter_schemas


class WalkerLike(Protocol):
    """Structural interface that rule modules consume.

    The walker package satisfies this Protocol implicitly. Rules accept
    ``walker: WalkerLike`` instead of ``ModuleType`` so mypy can verify
    that every walker function the rule reaches for actually exists and
    has the expected signature.
    """

    @staticmethod
    def iter_operations(spec: Spec) -> Iterator[OperationCtx]: ...

    @staticmethod
    def iter_responses(
        operation: dict[str, Any],
    ) -> Iterator[tuple[str, dict[str, Any]]]: ...

    @staticmethod
    def iter_request_bodies(
        operation: dict[str, Any],
        spec: Spec,
    ) -> Iterator[tuple[str, dict[str, Any]]]: ...

    @staticmethod
    def iter_schemas(spec: Spec) -> Iterator[SchemaRef]: ...

    @staticmethod
    def iter_all_schemas(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]: ...

    @staticmethod
    def encode_pointer_segment(segment: Any) -> str: ...

    @staticmethod
    def as_dict(value: Any) -> dict[str, Any]: ...

    @staticmethod
    def as_list(value: Any) -> list[Any]: ...


__all__ = [
    "OperationCtx",
    "SchemaRef",
    "WalkerLike",
    "as_dict",
    "as_list",
    "encode_pointer_segment",
    "iter_all_schemas",
    "iter_operations",
    "iter_request_bodies",
    "iter_responses",
    "iter_schemas",
]
