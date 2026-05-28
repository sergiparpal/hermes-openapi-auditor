"""Schema discovery and recursion.

Two public iterators:

- :func:`iter_schemas` — only the canonical reusable schemas (2.0
  ``definitions`` / 3.x ``components.schemas``).
- :func:`iter_all_schemas` — every schema-shaped dict reachable from the
  spec, including reusable component sections (parameters, headers,
  request bodies, responses) and every operation-embedded site. Deduped
  by ``id`` so the first canonical pointer wins.

The component-traversal helpers live alongside the recursion because
they call back into ``_walk_schema``; keeping them in the same module
avoids a circular import.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

from ..model import Spec
from ._operations import iter_operations
from ._pointer import as_dict, as_list, encode_pointer_segment


class SchemaRef(NamedTuple):
    """A reusable schema entry: its name, body, and canonical JSON pointer."""

    name: str
    schema: dict[str, Any]
    pointer: str


def iter_schemas(spec: Spec) -> Iterator[SchemaRef]:
    """Yield a :class:`SchemaRef` for every reusable schema.

    Swagger 2.0 keeps reusable schemas at ``definitions``; 3.x moves them
    to ``components.schemas``. The walker hides the difference.
    """
    if spec.version == "2.0":
        for name, schema in as_dict(spec.data.get("definitions")).items():
            if isinstance(schema, dict):
                yield SchemaRef(
                    name=name,
                    schema=schema,
                    pointer=f"#/definitions/{encode_pointer_segment(name)}",
                )
        return

    components = as_dict(spec.data.get("components"))
    for name, schema in as_dict(components.get("schemas")).items():
        if isinstance(schema, dict):
            yield SchemaRef(
                name=name,
                schema=schema,
                pointer=f"#/components/schemas/{encode_pointer_segment(name)}",
            )


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

    for ref in iter_schemas(spec):
        yield from _walk_schema(ref.schema, ref.pointer, seen)

    for schema, pointer in _iter_reusable_component_schemas(spec):
        yield from _walk_schema(schema, pointer, seen)

    for ctx in iter_operations(spec):
        yield from _operation_schemas(ctx.op, ctx.pointer, spec, seen)


def _iter_reusable_component_schemas(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield schemas reachable from reusable parameter / response / etc. definitions.

    For Swagger 2.0 these are top-level ``parameters`` and ``responses``
    objects. For 3.x they are ``components.parameters``,
    ``components.headers``, ``components.requestBodies``, and
    ``components.responses``.
    """
    if spec.version == "2.0":
        yield from _iter_reusable_v2(spec)
    else:
        yield from _iter_reusable_v3(spec)


def _iter_reusable_v2(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    for name, param in as_dict(spec.data.get("parameters")).items():
        if not isinstance(param, dict):
            continue
        base = f"#/parameters/{encode_pointer_segment(name)}"
        if param.get("in") == "body":
            schema = param.get("schema")
            if isinstance(schema, dict):
                yield schema, f"{base}/schema"
        else:
            yield param, base
    for name, resp in as_dict(spec.data.get("responses")).items():
        if not isinstance(resp, dict):
            continue
        schema = resp.get("schema")
        if isinstance(schema, dict):
            yield schema, f"#/responses/{encode_pointer_segment(name)}/schema"


def _iter_reusable_v3(spec: Spec) -> Iterator[tuple[dict[str, Any], str]]:
    components = as_dict(spec.data.get("components"))
    yield from _iter_component_parameters(as_dict(components.get("parameters")))
    yield from _iter_component_headers(as_dict(components.get("headers")))
    yield from _iter_component_request_bodies(as_dict(components.get("requestBodies")))
    yield from _iter_component_responses(as_dict(components.get("responses")))


def _iter_component_parameters(
    parameters: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str]]:
    for name, param in parameters.items():
        if not isinstance(param, dict):
            continue
        base = f"#/components/parameters/{encode_pointer_segment(name)}"
        yield from _iter_schema_and_content(param, base)


def _iter_component_headers(
    headers: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str]]:
    for name, header in headers.items():
        if not isinstance(header, dict):
            continue
        schema = header.get("schema")
        if isinstance(schema, dict):
            yield schema, f"#/components/headers/{encode_pointer_segment(name)}/schema"


def _iter_component_request_bodies(
    request_bodies: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str]]:
    for name, body_def in request_bodies.items():
        if not isinstance(body_def, dict):
            continue
        base = f"#/components/requestBodies/{encode_pointer_segment(name)}"
        yield from _iter_content_schemas(as_dict(body_def.get("content")), base)


def _iter_component_responses(
    responses: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str]]:
    for name, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        base = f"#/components/responses/{encode_pointer_segment(name)}"
        yield from _iter_content_schemas(as_dict(resp.get("content")), base)
        for header_name, header in as_dict(resp.get("headers")).items():
            if isinstance(header, dict) and isinstance(header.get("schema"), dict):
                yield (
                    header["schema"],
                    (f"{base}/headers/{encode_pointer_segment(header_name)}/schema"),
                )


def _iter_schema_and_content(
    holder: dict[str, Any],
    base_pointer: str,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield the ``schema`` and any ``content[*].schema`` under ``holder``.

    Used for component parameters (which carry either form). The single
    helper avoids duplicating the two-shape branching at every call site.
    """
    schema = holder.get("schema")
    if isinstance(schema, dict):
        yield schema, f"{base_pointer}/schema"
    yield from _iter_content_schemas(as_dict(holder.get("content")), base_pointer)


def _iter_content_schemas(
    content: dict[str, Any],
    base_pointer: str,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield ``(schema, pointer)`` for every ``content[mime].schema``."""
    for mime, media in content.items():
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            yield media["schema"], f"{base_pointer}/content/{encode_pointer_segment(mime)}/schema"


def _operation_schemas(
    op: dict[str, Any],
    op_pointer: str,
    spec: Spec,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    yield from _operation_parameter_schemas(op, op_pointer, spec, seen)
    if spec.version != "2.0":
        yield from _operation_request_body_schemas(op, op_pointer, seen)
    yield from _operation_response_schemas(op, op_pointer, spec, seen)


def _operation_parameter_schemas(
    op: dict[str, Any],
    op_pointer: str,
    spec: Spec,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for i, param in enumerate(as_list(op.get("parameters"))):
        if not isinstance(param, dict):
            continue
        param_pointer = f"{op_pointer}/parameters/{i}"
        if spec.version == "2.0":
            # In 2.0, non-body params carry `type`/`format` etc. directly
            # on the parameter object (it IS the schema). Body params
            # wrap the schema in `schema:`.
            if param.get("in") == "body":
                schema = param.get("schema")
                if isinstance(schema, dict):
                    yield from _walk_schema(schema, f"{param_pointer}/schema", seen)
            else:
                yield from _walk_schema(param, param_pointer, seen)
            continue
        schema = param.get("schema")
        if isinstance(schema, dict):
            yield from _walk_schema(schema, f"{param_pointer}/schema", seen)
        # 3.x parameters may use `content` instead of `schema`.
        for schema, pointer in _iter_content_schemas(as_dict(param.get("content")), param_pointer):
            yield from _walk_schema(schema, pointer, seen)


def _operation_request_body_schemas(
    op: dict[str, Any],
    op_pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    request_body = op.get("requestBody")
    if not isinstance(request_body, dict):
        return
    base = f"{op_pointer}/requestBody"
    for schema, pointer in _iter_content_schemas(as_dict(request_body.get("content")), base):
        yield from _walk_schema(schema, pointer, seen)


def _operation_response_schemas(
    op: dict[str, Any],
    op_pointer: str,
    spec: Spec,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for status, response in as_dict(op.get("responses")).items():
        if not isinstance(response, dict):
            continue
        response_pointer = f"{op_pointer}/responses/{status}"
        if spec.version == "2.0":
            schema = response.get("schema")
            if isinstance(schema, dict):
                yield from _walk_schema(schema, f"{response_pointer}/schema", seen)
            continue
        for schema, pointer in _iter_content_schemas(
            as_dict(response.get("content")), response_pointer
        ):
            yield from _walk_schema(schema, pointer, seen)
        for header_name, header in as_dict(response.get("headers")).items():
            if isinstance(header, dict) and isinstance(header.get("schema"), dict):
                yield from _walk_schema(
                    header["schema"],
                    f"{response_pointer}/headers/{encode_pointer_segment(header_name)}/schema",
                    seen,
                )


def _walk_schema(
    schema: Any,
    pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield every nested schema starting from ``schema``, deduped by id."""
    if not isinstance(schema, dict):
        return
    schema_id = id(schema)
    if schema_id in seen:
        return
    seen.add(schema_id)

    yield schema, pointer
    yield from _walk_named_subschemas(schema, pointer, seen)
    yield from _walk_indexed_subschemas(schema, pointer, seen)
    yield from _walk_single_subschemas(schema, pointer, seen)


# Keywords whose value is a {name: schema} mapping (RFC: yield each entry
# with its key appended to the parent pointer, encoded per RFC 6901).
_NAMED_SUBSCHEMA_KEYWORDS = ("properties", "patternProperties", "dependentSchemas")

# Keywords whose value is a [schema, schema, ...] list.
_INDEXED_SUBSCHEMA_KEYWORDS = ("allOf", "oneOf", "anyOf", "prefixItems")

# Keywords whose value is a single sub-schema (or list-of-schemas, for 2.0's
# ``items``). Handled individually because their semantics around the array
# shape differ from the index keywords above.
_SINGLE_SUBSCHEMA_KEYWORDS = (
    "not",
    "if",
    "then",
    "else",
    "additionalProperties",
    "unevaluatedProperties",
    "unevaluatedItems",
    "propertyNames",
    "contains",
)


def _walk_named_subschemas(
    schema: dict[str, Any],
    pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for keyword in _NAMED_SUBSCHEMA_KEYWORDS:
        for name, sub in as_dict(schema.get(keyword)).items():
            yield from _walk_schema(
                sub, f"{pointer}/{keyword}/{encode_pointer_segment(name)}", seen
            )


def _walk_indexed_subschemas(
    schema: dict[str, Any],
    pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    for keyword in _INDEXED_SUBSCHEMA_KEYWORDS:
        for i, sub in enumerate(as_list(schema.get(keyword))):
            yield from _walk_schema(sub, f"{pointer}/{keyword}/{i}", seen)


def _walk_single_subschemas(
    schema: dict[str, Any],
    pointer: str,
    seen: set[int],
) -> Iterator[tuple[dict[str, Any], str]]:
    # `items` is special: in 2.0 it can be a list-of-schemas (tuple
    # validation), in 3.x it's a single schema. Handle both shapes.
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _walk_schema(items, f"{pointer}/items", seen)
    elif isinstance(items, list):
        for i, item in enumerate(items):
            yield from _walk_schema(item, f"{pointer}/items/{i}", seen)

    for keyword in _SINGLE_SUBSCHEMA_KEYWORDS:
        sub = schema.get(keyword)
        if isinstance(sub, dict):
            yield from _walk_schema(sub, f"{pointer}/{keyword}", seen)
