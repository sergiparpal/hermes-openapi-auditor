"""Operation-level traversal: paths, responses, request bodies.

3.1 webhooks are surfaced through ``iter_operations`` with the
``#/webhooks/`` pointer prefix so rule code never has to know they exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

from ..model import Spec
from ._pointer import as_dict, as_list, encode_pointer_segment

_HTTP_VERBS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})


class OperationCtx(NamedTuple):
    """A single operation, with its URL path, verb, dict, and pointer.

    Tuple-unpacking still works (``for url_path, verb, op, pointer in ...``)
    so callers can stay positional, but attribute access (``ctx.label``,
    ``ctx.pointer``) is preferred — and ``label`` saves the recurring
    ``f"{verb.upper()} {url_path}"`` string in rule code.
    """

    url_path: str
    verb: str
    op: dict[str, Any]
    pointer: str

    @property
    def label(self) -> str:
        """Human-readable operation label used in finding messages."""
        return f"{self.verb.upper()} {self.url_path}"


def iter_operations(spec: Spec) -> Iterator[OperationCtx]:
    """Yield an :class:`OperationCtx` for every operation in the spec.

    Path-level shared parameters (``parameters`` keyed on a path item) are
    merged into each operation's parameter list so rules can treat each
    operation as self-contained. Verbs are returned lowercased.

    For OpenAPI 3.1, top-level ``webhooks`` are iterated as a second pass
    with pointer prefix ``#/webhooks/`` (3.0 and 2.0 have no webhooks).
    """
    yield from _iter_path_items_section(as_dict(spec.data.get("paths")), prefix="#/paths/")
    if spec.version == "3.1":
        yield from _iter_path_items_section(
            as_dict(spec.data.get("webhooks")), prefix="#/webhooks/"
        )


def _iter_path_items_section(
    section: dict[str, Any],
    *,
    prefix: str,
) -> Iterator[OperationCtx]:
    for url_path, path_item in section.items():
        if not isinstance(path_item, dict):
            continue
        shared_params = as_list(path_item.get("parameters"))
        for verb, op in path_item.items():
            if verb not in _HTTP_VERBS or not isinstance(op, dict):
                continue
            merged = dict(op)
            if shared_params:
                merged["parameters"] = [*shared_params, *as_list(op.get("parameters"))]
            pointer = f"{prefix}{encode_pointer_segment(url_path)}/{verb}"
            yield OperationCtx(url_path=url_path, verb=verb, op=merged, pointer=pointer)


def iter_responses(
    operation: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(status, response_obj)`` for an operation.

    Identical shape across all three OpenAPI versions: responses live at
    ``operation.responses`` keyed by status code (``"200"``, ``"4XX"``,
    ``"default"``).
    """
    for status, response in as_dict(operation.get("responses")).items():
        if isinstance(response, dict):
            yield str(status), response


def iter_request_bodies(
    operation: dict[str, Any],
    spec: Spec,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(media_type, media_obj)`` for each request body media.

    Swagger 2.0 uses a ``body`` parameter (``in: body``) with a ``schema``;
    we synthesize a single ``(application/json, {"schema": ...})`` entry
    so rules see a consistent shape. The 2.0 ``consumes`` list, when
    present, is used to set the media type instead of the json default.

    OpenAPI 3.x uses ``operation.requestBody.content`` keyed on media
    type; that mapping is yielded directly.
    """
    if spec.version == "2.0":
        body_param = next(
            (
                p
                for p in as_list(operation.get("parameters"))
                if isinstance(p, dict) and p.get("in") == "body"
            ),
            None,
        )
        if body_param is None:
            return
        consumes = as_list(operation.get("consumes")) or as_list(spec.data.get("consumes"))
        media_type = consumes[0] if consumes else "application/json"
        yield media_type, {"schema": body_param.get("schema", {})}
        return

    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return
    for media_type, media in as_dict(request_body.get("content")).items():
        if isinstance(media, dict):
            yield media_type, media
