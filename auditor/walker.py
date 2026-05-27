"""Version-agnostic iterators over a loaded OpenAPI/Swagger spec.

The walker normalizes the differences between Swagger 2.0 and OpenAPI 3.x
so individual rules don't have to. Each iterator yields a small NamedTuple
or 2-tuple that includes a JSON pointer string so findings can carry a
precise location.

Pointer convention: ``#/paths/~1pets/get`` — RFC 6901 (``~0`` escapes
``~``, ``~1`` escapes ``/``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple, Protocol

from .model import Spec

_HTTP_VERBS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})


class WalkerLike(Protocol):
    """Structural interface that rule modules consume.

    The walker module satisfies this Protocol implicitly. Rules accept
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


class SchemaRef(NamedTuple):
    """A reusable schema entry: its name, body, and canonical JSON pointer."""

    name: str
    schema: dict[str, Any]
    pointer: str


def encode_pointer_segment(segment: Any) -> str:
    """RFC 6901 escape a single pointer segment.

    Accepts any value so the caller doesn't have to coerce YAML dict
    keys that PyYAML may have parsed as non-strings (e.g. bare ``on:``
    becomes ``True`` under YAML 1.1, bare ``42:`` becomes ``int``).
    """
    return str(segment).replace("~", "~0").replace("/", "~1")


def as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` unchanged if it's a dict, else an empty dict.

    Used to make every traversal site null-safe in the common case where
    a YAML key is present but its value is ``null`` (e.g. ``paths:`` on a
    line by itself), which would otherwise crash ``.items()``.
    """
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Return ``value`` unchanged if it's a list, else an empty list."""
    return value if isinstance(value, list) else []


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
