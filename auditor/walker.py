"""Version-agnostic iterators over a loaded OpenAPI/Swagger spec.

The walker normalizes the differences between Swagger 2.0 and OpenAPI 3.x
so individual rules don't have to. Each iterator yields tuples that
include a JSON pointer string so findings can carry a precise location.

Pointer convention: ``#/paths/~1pets/get`` — RFC 6901 (``~0`` escapes
``~``, ``~1`` escapes ``/``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .model import Spec

_HTTP_VERBS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})


def encode_pointer_segment(segment: str) -> str:
    """RFC 6901 escape a single pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


def iter_operations(spec: Spec) -> Iterator[tuple[str, str, dict[str, Any], str]]:
    """Yield ``(path, verb, operation_dict, json_pointer)`` for every operation.

    Path-level shared parameters (``parameters`` keyed on a path item) are
    merged into each operation's parameter list so rules can treat each
    operation as self-contained. Verbs are returned lowercased.
    """
    for path, path_item in spec.data.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", [])
        for verb, op in path_item.items():
            if verb not in _HTTP_VERBS:
                continue
            if not isinstance(op, dict):
                continue
            merged = dict(op)
            if shared_params:
                merged_params = list(shared_params)
                merged_params.extend(op.get("parameters", []))
                merged["parameters"] = merged_params
            pointer = f"#/paths/{encode_pointer_segment(path)}/{verb}"
            yield path, verb, merged, pointer


def iter_responses(
    operation: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(status, response_obj)`` for an operation.

    Identical shape across all three OpenAPI versions: responses live at
    ``operation.responses`` keyed by status code (``"200"``, ``"4XX"``,
    ``"default"``).
    """
    for status, response in operation.get("responses", {}).items():
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
                for p in operation.get("parameters", [])
                if isinstance(p, dict) and p.get("in") == "body"
            ),
            None,
        )
        if body_param is None:
            return
        consumes = operation.get("consumes") or spec.data.get("consumes") or []
        media_type = consumes[0] if consumes else "application/json"
        yield media_type, {"schema": body_param.get("schema", {})}
        return

    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return
    for media_type, media in request_body.get("content", {}).items():
        if isinstance(media, dict):
            yield media_type, media


def iter_schemas(spec: Spec) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Yield ``(name, schema_obj, json_pointer)`` over reusable schemas.

    Swagger 2.0 keeps reusable schemas at ``definitions``; 3.x moves them
    to ``components.schemas``. The walker hides the difference.
    """
    if spec.version == "2.0":
        for name, schema in spec.data.get("definitions", {}).items():
            if isinstance(schema, dict):
                pointer = f"#/definitions/{encode_pointer_segment(name)}"
                yield name, schema, pointer
        return

    components = spec.data.get("components", {})
    if not isinstance(components, dict):
        return
    for name, schema in components.get("schemas", {}).items():
        if isinstance(schema, dict):
            pointer = f"#/components/schemas/{encode_pointer_segment(name)}"
            yield name, schema, pointer


def iter_all_schemas(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield every schema-shaped dict reachable from the spec.

    Walks reusable schemas (``definitions`` / ``components.schemas``)
    plus every operation-embedded schema (parameter ``schema`` objects,
    request body media types, response bodies) and recurses into
    composition keywords (``properties``, ``items``, ``allOf``,
    ``oneOf``, ``anyOf``, ``not``, ``additionalProperties``,
    ``patternProperties``).

    Identity-tracks already-yielded schemas so circular ``$ref``
    structures (when ``resolve_refs=True`` produced shared dict
    instances) do not cause infinite recursion. Each unique dict is
    yielded exactly once, at the first pointer where it is encountered.
    """
    seen: set[int] = set()

    for _, schema, pointer in iter_schemas(spec):
        yield from _walk_schema(schema, pointer, seen)

    for _, _, op, op_pointer in iter_operations(spec):
        yield from _operation_schemas(op, op_pointer, spec, seen)


def _operation_schemas(
    op: dict[str, Any],
    op_pointer: str,
    spec: Spec,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for i, param in enumerate(op.get("parameters", [])):
        if not isinstance(param, dict):
            continue
        if spec.version == "2.0":
            # In 2.0, non-body params carry `type`/`format` etc. directly
            # on the parameter object (it IS the schema). Body params
            # wrap the schema in `schema:`.
            if param.get("in") == "body":
                schema = param.get("schema")
                if isinstance(schema, dict):
                    yield from _walk_schema(schema, f"{op_pointer}/parameters/{i}/schema", seen)
            else:
                yield from _walk_schema(param, f"{op_pointer}/parameters/{i}", seen)
        else:
            schema = param.get("schema")
            if isinstance(schema, dict):
                yield from _walk_schema(schema, f"{op_pointer}/parameters/{i}/schema", seen)

    if spec.version != "2.0":
        request_body = op.get("requestBody")
        if isinstance(request_body, dict):
            for mime, media in request_body.get("content", {}).items():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    yield from _walk_schema(
                        media["schema"],
                        f"{op_pointer}/requestBody/content/{encode_pointer_segment(mime)}/schema",
                        seen,
                    )

    for status, response in op.get("responses", {}).items():
        if not isinstance(response, dict):
            continue
        if spec.version == "2.0":
            schema = response.get("schema")
            if isinstance(schema, dict):
                yield from _walk_schema(schema, f"{op_pointer}/responses/{status}/schema", seen)
        else:
            for mime, media in response.get("content", {}).items():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    yield from _walk_schema(
                        media["schema"],
                        f"{op_pointer}/responses/{status}/content/"
                        f"{encode_pointer_segment(mime)}/schema",
                        seen,
                    )


def _walk_schema(
    schema: dict[str, Any] | Any,
    pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    if not isinstance(schema, dict):
        return
    sid = id(schema)
    if sid in seen:
        return
    seen.add(sid)

    yield schema, pointer

    for k, v in (schema.get("properties") or {}).items():
        yield from _walk_schema(v, f"{pointer}/properties/{encode_pointer_segment(k)}", seen)

    items = schema.get("items")
    if isinstance(items, dict):
        yield from _walk_schema(items, f"{pointer}/items", seen)
    elif isinstance(items, list):  # Swagger 2.0 array of item schemas
        for i, item in enumerate(items):
            yield from _walk_schema(item, f"{pointer}/items/{i}", seen)

    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        yield from _walk_schema(additional, f"{pointer}/additionalProperties", seen)

    for kw in ("allOf", "oneOf", "anyOf"):
        composites = schema.get(kw)
        if isinstance(composites, list):
            for i, sub in enumerate(composites):
                yield from _walk_schema(sub, f"{pointer}/{kw}/{i}", seen)

    not_schema = schema.get("not")
    if isinstance(not_schema, dict):
        yield from _walk_schema(not_schema, f"{pointer}/not", seen)

    for k, v in (schema.get("patternProperties") or {}).items():
        yield from _walk_schema(v, f"{pointer}/patternProperties/{encode_pointer_segment(k)}", seen)
