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


def encode_pointer_segment(segment: Any) -> str:
    """RFC 6901 escape a single pointer segment.

    Accepts any value so the caller doesn't have to coerce YAML dict
    keys that PyYAML may have parsed as non-strings (e.g. bare ``on:``
    becomes ``True`` under YAML 1.1, bare ``42:`` becomes ``int``).
    """
    return str(segment).replace("~", "~0").replace("/", "~1")


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` unchanged if it's a dict, else an empty dict.

    Used to make every traversal site null-safe in the common case where
    a YAML key is present but its value is ``null`` (e.g. ``paths:`` on a
    line by itself), which would otherwise crash ``.items()``.
    """
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return ``value`` unchanged if it's a list, else an empty list."""
    return value if isinstance(value, list) else []


def iter_operations(spec: Spec) -> Iterator[tuple[str, str, dict[str, Any], str]]:
    """Yield ``(path, verb, operation_dict, json_pointer)`` for every operation.

    Path-level shared parameters (``parameters`` keyed on a path item) are
    merged into each operation's parameter list so rules can treat each
    operation as self-contained. Verbs are returned lowercased.

    For OpenAPI 3.1, top-level ``webhooks`` are iterated as a second pass
    with pointer prefix ``#/webhooks/`` (3.0 and 2.0 have no webhooks).
    """
    yield from _iter_path_items_section(_as_dict(spec.data.get("paths")), prefix="#/paths/")
    if spec.version == "3.1":
        yield from _iter_path_items_section(
            _as_dict(spec.data.get("webhooks")), prefix="#/webhooks/"
        )


def _iter_path_items_section(
    section: dict[str, Any],
    *,
    prefix: str,
) -> Iterator[tuple[str, str, dict[str, Any], str]]:
    for path, path_item in section.items():
        if not isinstance(path_item, dict):
            continue
        shared_params = _as_list(path_item.get("parameters"))
        for verb, op in path_item.items():
            if verb not in _HTTP_VERBS:
                continue
            if not isinstance(op, dict):
                continue
            merged = dict(op)
            if shared_params:
                merged_params = list(shared_params)
                merged_params.extend(_as_list(op.get("parameters")))
                merged["parameters"] = merged_params
            pointer = f"{prefix}{encode_pointer_segment(path)}/{verb}"
            yield path, verb, merged, pointer


def iter_responses(
    operation: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(status, response_obj)`` for an operation.

    Identical shape across all three OpenAPI versions: responses live at
    ``operation.responses`` keyed by status code (``"200"``, ``"4XX"``,
    ``"default"``).
    """
    for status, response in _as_dict(operation.get("responses")).items():
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
                for p in _as_list(operation.get("parameters"))
                if isinstance(p, dict) and p.get("in") == "body"
            ),
            None,
        )
        if body_param is None:
            return
        consumes = _as_list(operation.get("consumes")) or _as_list(spec.data.get("consumes"))
        media_type = consumes[0] if consumes else "application/json"
        yield media_type, {"schema": body_param.get("schema", {})}
        return

    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return
    for media_type, media in _as_dict(request_body.get("content")).items():
        if isinstance(media, dict):
            yield media_type, media


def iter_schemas(spec: Spec) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Yield ``(name, schema_obj, json_pointer)`` over reusable schemas.

    Swagger 2.0 keeps reusable schemas at ``definitions``; 3.x moves them
    to ``components.schemas``. The walker hides the difference.
    """
    if spec.version == "2.0":
        for name, schema in _as_dict(spec.data.get("definitions")).items():
            if isinstance(schema, dict):
                pointer = f"#/definitions/{encode_pointer_segment(name)}"
                yield name, schema, pointer
        return

    components = _as_dict(spec.data.get("components"))
    for name, schema in _as_dict(components.get("schemas")).items():
        if isinstance(schema, dict):
            pointer = f"#/components/schemas/{encode_pointer_segment(name)}"
            yield name, schema, pointer


def iter_all_schemas(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield every schema-shaped dict reachable from the spec.

    Walks reusable schemas (``definitions`` / ``components.schemas``),
    then other reusable component sections (``components.parameters``,
    ``components.headers``, ``components.responses``,
    ``components.requestBodies``; for 2.0 the top-level ``parameters``
    and ``responses``), then every operation-embedded schema (parameter
    ``schema`` / ``content`` objects, request body media types, response
    bodies, response headers).

    Visit order matters for dedup-by-id: canonical reusable locations
    first, then operation-embedded sites. The first pointer where a
    given schema is encountered is the one reported in findings, so
    schemas defined in ``components.*`` get the canonical pointer even
    when they are reached transitively via a ``$ref``.

    Recursion covers all composition keywords: ``properties``, ``items``,
    ``prefixItems``, ``allOf``, ``oneOf``, ``anyOf``, ``not``, ``if``,
    ``then``, ``else``, ``additionalProperties``, ``unevaluatedProperties``,
    ``unevaluatedItems``, ``patternProperties``, ``dependentSchemas``,
    ``propertyNames``, ``contains``.
    """
    seen: set[int] = set()

    for _, schema, pointer in iter_schemas(spec):
        yield from _walk_schema(schema, pointer, seen)

    for schema, pointer in _iter_reusable_component_schemas(spec):
        yield from _walk_schema(schema, pointer, seen)

    for _, _, op, op_pointer in iter_operations(spec):
        yield from _operation_schemas(op, op_pointer, spec, seen)


def _iter_reusable_component_schemas(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield schemas reachable from reusable parameter / response / etc. definitions.

    For Swagger 2.0 these are top-level ``parameters`` and ``responses``
    objects. For 3.x they are ``components.parameters``,
    ``components.headers``, ``components.requestBodies``, and
    ``components.responses``.
    """
    if spec.version == "2.0":
        for name, param in _as_dict(spec.data.get("parameters")).items():
            if not isinstance(param, dict):
                continue
            base = f"#/parameters/{encode_pointer_segment(name)}"
            if param.get("in") == "body":
                schema = param.get("schema")
                if isinstance(schema, dict):
                    yield schema, f"{base}/schema"
            else:
                yield param, base
        for name, resp in _as_dict(spec.data.get("responses")).items():
            if not isinstance(resp, dict):
                continue
            schema = resp.get("schema")
            if isinstance(schema, dict):
                yield schema, f"#/responses/{encode_pointer_segment(name)}/schema"
        return

    components = _as_dict(spec.data.get("components"))

    for name, param in _as_dict(components.get("parameters")).items():
        if not isinstance(param, dict):
            continue
        base = f"#/components/parameters/{encode_pointer_segment(name)}"
        schema = param.get("schema")
        if isinstance(schema, dict):
            yield schema, f"{base}/schema"
        for mime, media in _as_dict(param.get("content")).items():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                yield media["schema"], f"{base}/content/{encode_pointer_segment(mime)}/schema"

    for name, header in _as_dict(components.get("headers")).items():
        if not isinstance(header, dict):
            continue
        base = f"#/components/headers/{encode_pointer_segment(name)}"
        schema = header.get("schema")
        if isinstance(schema, dict):
            yield schema, f"{base}/schema"

    for name, rb in _as_dict(components.get("requestBodies")).items():
        if not isinstance(rb, dict):
            continue
        base = f"#/components/requestBodies/{encode_pointer_segment(name)}"
        for mime, media in _as_dict(rb.get("content")).items():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                yield media["schema"], f"{base}/content/{encode_pointer_segment(mime)}/schema"

    for name, resp in _as_dict(components.get("responses")).items():
        if not isinstance(resp, dict):
            continue
        base = f"#/components/responses/{encode_pointer_segment(name)}"
        for mime, media in _as_dict(resp.get("content")).items():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                yield media["schema"], f"{base}/content/{encode_pointer_segment(mime)}/schema"
        for hname, header in _as_dict(resp.get("headers")).items():
            if isinstance(header, dict) and isinstance(header.get("schema"), dict):
                yield header["schema"], (f"{base}/headers/{encode_pointer_segment(hname)}/schema")


def _operation_schemas(
    op: dict[str, Any],
    op_pointer: str,
    spec: Spec,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for i, param in enumerate(_as_list(op.get("parameters"))):
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
            # 3.x parameters may use `content` instead of `schema`.
            for mime, media in _as_dict(param.get("content")).items():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    yield from _walk_schema(
                        media["schema"],
                        f"{op_pointer}/parameters/{i}/content/"
                        f"{encode_pointer_segment(mime)}/schema",
                        seen,
                    )

    if spec.version != "2.0":
        request_body = op.get("requestBody")
        if isinstance(request_body, dict):
            for mime, media in _as_dict(request_body.get("content")).items():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    yield from _walk_schema(
                        media["schema"],
                        f"{op_pointer}/requestBody/content/{encode_pointer_segment(mime)}/schema",
                        seen,
                    )

    for status, response in _as_dict(op.get("responses")).items():
        if not isinstance(response, dict):
            continue
        if spec.version == "2.0":
            schema = response.get("schema")
            if isinstance(schema, dict):
                yield from _walk_schema(schema, f"{op_pointer}/responses/{status}/schema", seen)
        else:
            for mime, media in _as_dict(response.get("content")).items():
                if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                    yield from _walk_schema(
                        media["schema"],
                        f"{op_pointer}/responses/{status}/content/"
                        f"{encode_pointer_segment(mime)}/schema",
                        seen,
                    )
            for hname, header in _as_dict(response.get("headers")).items():
                if isinstance(header, dict) and isinstance(header.get("schema"), dict):
                    yield from _walk_schema(
                        header["schema"],
                        f"{op_pointer}/responses/{status}/headers/"
                        f"{encode_pointer_segment(hname)}/schema",
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

    # JSON Schema 2020-12 (OpenAPI 3.1) tuple validation.
    prefix_items = schema.get("prefixItems")
    if isinstance(prefix_items, list):
        for i, item in enumerate(prefix_items):
            yield from _walk_schema(item, f"{pointer}/prefixItems/{i}", seen)

    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        yield from _walk_schema(additional, f"{pointer}/additionalProperties", seen)

    unevaluated_props = schema.get("unevaluatedProperties")
    if isinstance(unevaluated_props, dict):
        yield from _walk_schema(unevaluated_props, f"{pointer}/unevaluatedProperties", seen)

    unevaluated_items = schema.get("unevaluatedItems")
    if isinstance(unevaluated_items, dict):
        yield from _walk_schema(unevaluated_items, f"{pointer}/unevaluatedItems", seen)

    for kw in ("allOf", "oneOf", "anyOf"):
        composites = schema.get(kw)
        if isinstance(composites, list):
            for i, sub in enumerate(composites):
                yield from _walk_schema(sub, f"{pointer}/{kw}/{i}", seen)

    for kw in ("not", "if", "then", "else", "propertyNames", "contains"):
        sub = schema.get(kw)
        if isinstance(sub, dict):
            yield from _walk_schema(sub, f"{pointer}/{kw}", seen)

    for k, v in (schema.get("patternProperties") or {}).items():
        yield from _walk_schema(v, f"{pointer}/patternProperties/{encode_pointer_segment(k)}", seen)

    for k, v in (schema.get("dependentSchemas") or {}).items():
        yield from _walk_schema(v, f"{pointer}/dependentSchemas/{encode_pointer_segment(k)}", seen)
