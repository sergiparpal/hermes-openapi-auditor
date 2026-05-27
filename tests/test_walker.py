"""Tests for ``auditor.walker``.

The walker is supposed to hide version differences. We exploit that by
running the *same* assertion bodies against all three Petstore fixtures:
if the abstraction is sound, ``/pet`` POST and ``/pet/{petId}`` GET
should be discoverable identically regardless of OpenAPI version.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.walker import (
    encode_pointer_segment,
    iter_operations,
    iter_request_bodies,
    iter_responses,
    iter_schemas,
)


@pytest.fixture(scope="module", params=["2.0", "3.0", "3.1"])
def petstore_spec(request: pytest.FixtureRequest, fixtures_dir: Path):
    """Parametrize tests across all three Petstore versions."""
    return load_spec(fixtures_dir / f"petstore-{request.param}.yaml")


class TestIterOperations:
    """These assertions must hold for ALL three versions."""

    def test_pet_post_present(self, petstore_spec) -> None:
        ops = {(p, v) for p, v, _, _ in iter_operations(petstore_spec)}
        assert ("/pet", "post") in ops, f"missing POST /pet in {petstore_spec.version}"

    def test_pet_by_id_get_present(self, petstore_spec) -> None:
        ops = {(p, v) for p, v, _, _ in iter_operations(petstore_spec)}
        assert ("/pet/{petId}", "get") in ops, (
            f"missing GET /pet/{{petId}} in {petstore_spec.version}"
        )

    def test_operations_have_pointer(self, petstore_spec) -> None:
        for _, _, _, pointer in iter_operations(petstore_spec):
            assert pointer.startswith("#/paths/")

    def test_pointer_escapes_slashes(self, petstore_spec) -> None:
        for path, verb, _, pointer in iter_operations(petstore_spec):
            expected = f"#/paths/{encode_pointer_segment(path)}/{verb}"
            assert pointer == expected

    def test_non_verb_entries_skipped(self, petstore_spec) -> None:
        """`parameters` and `summary` at the path-item level are not verbs."""
        for _, verb, _, _ in iter_operations(petstore_spec):
            assert verb in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


class TestIterResponses:
    def test_pet_post_has_responses(self, petstore_spec) -> None:
        for path, verb, op, _ in iter_operations(petstore_spec):
            if path == "/pet" and verb == "post":
                statuses = {s for s, _ in iter_responses(op)}
                # Every Petstore documents at least one response for POST /pet
                # (2.0's POST /pet only documents 405 — that's still a response).
                assert statuses, "POST /pet should declare at least one response"
                return
        pytest.fail("POST /pet not found")


class TestIterRequestBodies:
    def test_pet_post_has_request_body(self, petstore_spec) -> None:
        """POST /pet has a request body in every Petstore version."""
        for path, verb, op, _ in iter_operations(petstore_spec):
            if path == "/pet" and verb == "post":
                media = list(iter_request_bodies(op, petstore_spec))
                assert media, f"no request body media for POST /pet in {petstore_spec.version}"
                # Each yielded tuple should be (media_type, dict-with-schema).
                for mime, m in media:
                    assert isinstance(mime, str) and "/" in mime
                    assert "schema" in m
                return
        pytest.fail("POST /pet not found")

    def test_get_has_no_request_body(self, petstore_spec) -> None:
        for path, verb, op, _ in iter_operations(petstore_spec):
            if path == "/pet/{petId}" and verb == "get":
                assert list(iter_request_bodies(op, petstore_spec)) == []
                return


class TestIterSchemas:
    def test_pet_schema_yielded(self, petstore_spec) -> None:
        names = {name for name, _, _ in iter_schemas(petstore_spec)}
        assert "Pet" in names, f"Pet schema missing in {petstore_spec.version}"

    def test_schemas_have_correct_pointer(self, petstore_spec) -> None:
        for name, _, pointer in iter_schemas(petstore_spec):
            if petstore_spec.version == "2.0":
                assert pointer == f"#/definitions/{encode_pointer_segment(name)}"
            else:
                assert pointer == f"#/components/schemas/{encode_pointer_segment(name)}"


class TestPointerEscaping:
    def test_basic(self) -> None:
        assert encode_pointer_segment("foo") == "foo"

    def test_slash_escaped(self) -> None:
        assert encode_pointer_segment("/pets") == "~1pets"

    def test_tilde_escaped(self) -> None:
        assert encode_pointer_segment("a~b") == "a~0b"

    def test_order_matters(self) -> None:
        # `~` is escaped first so `~1` doesn't get re-escaped as `~01`.
        assert encode_pointer_segment("~1") == "~01"


# Null-safety: a YAML key present with a null value must not crash the walker.
# Each scenario corresponds to a `.get(key, default)` site that would have
# crashed before because the default only fires when the key is *absent*.
_NULL_SAFETY_SPECS = {
    "paths_null": ("openapi: 3.0.3\ninfo: {title: T, version: '1.0'}\npaths: null\n"),
    "responses_null": (
        "openapi: 3.0.3\n"
        "info: {title: T, version: '1.0'}\n"
        "paths:\n"
        "  /x:\n"
        "    get:\n"
        "      summary: x\n"
        "      description: x\n"
        "      responses: null\n"
    ),
    "op_parameters_null": (
        "openapi: 3.0.3\n"
        "info: {title: T, version: '1.0'}\n"
        "paths:\n"
        "  /x:\n"
        "    get:\n"
        "      summary: x\n"
        "      description: x\n"
        "      parameters: null\n"
        "      responses:\n"
        "        '200': {description: ok}\n"
        "        '400': {description: bad}\n"
    ),
    "shared_params_set_op_params_null": (
        "openapi: 3.0.3\n"
        "info: {title: T, version: '1.0'}\n"
        "paths:\n"
        "  /x:\n"
        "    parameters:\n"
        "      - {name: shared, in: query, schema: {type: string}}\n"
        "    get:\n"
        "      summary: x\n"
        "      description: x\n"
        "      parameters: null\n"
        "      responses:\n"
        "        '200': {description: ok}\n"
        "        '400': {description: bad}\n"
    ),
    "definitions_null_2_0": (
        "swagger: '2.0'\ninfo: {title: T, version: '1.0'}\npaths: {}\ndefinitions: null\n"
    ),
    "components_schemas_null": (
        "openapi: 3.0.3\n"
        "info: {title: T, version: '1.0'}\n"
        "paths: {}\n"
        "components:\n"
        "  schemas: null\n"
    ),
}


@pytest.fixture(params=sorted(_NULL_SAFETY_SPECS.keys()))
def null_safety_spec(request: pytest.FixtureRequest, tmp_path: Path):
    """Load each pathological spec; runner-style (validate_schema=False)."""
    from hermes_openapi_auditor.auditor.loader import load_spec

    body = _NULL_SAFETY_SPECS[request.param]
    f = tmp_path / f"{request.param}.yaml"
    f.write_text(body, encoding="utf-8")
    return load_spec(f, validate_schema=False)


class TestNullSafeTraversal:
    def test_iter_operations(self, null_safety_spec) -> None:
        # Must not raise; may yield zero or more tuples.
        ops = list(iter_operations(null_safety_spec))
        assert isinstance(ops, list)

    def test_iter_schemas(self, null_safety_spec) -> None:
        list(iter_schemas(null_safety_spec))

    def test_iter_all_schemas(self, null_safety_spec) -> None:
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        list(iter_all_schemas(null_safety_spec))

    def test_iter_responses_and_request_bodies(self, null_safety_spec) -> None:
        for _, _, op, _ in iter_operations(null_safety_spec):
            list(iter_responses(op))
            list(iter_request_bodies(op, null_safety_spec))


class TestWebhooks3_1:
    def test_webhooks_iterated_as_operations(self, tmp_path: Path) -> None:
        body = (
            "openapi: 3.1.0\n"
            "info: {title: T, version: '1.0'}\n"
            "webhooks:\n"
            "  newPet:\n"
            "    post:\n"
            "      summary: ping\n"
            "      description: ping\n"
            "      responses:\n"
            "        '200': {description: ok}\n"
            "        '500': {description: bad}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec

        f = tmp_path / "webhook.yaml"
        f.write_text(body, encoding="utf-8")
        spec = load_spec(f, validate_schema=False)
        pointers = [p for _, _, _, p in iter_operations(spec)]
        assert "#/webhooks/newPet/post" in pointers

    def test_webhooks_skipped_on_3_0(self, tmp_path: Path) -> None:
        # Same shape but version 3.0.x has no webhooks field; if present it is ignored.
        body = (
            "openapi: 3.0.3\n"
            "info: {title: T, version: '1.0'}\n"
            "paths: {}\n"
            "webhooks:\n"
            "  newPet:\n"
            "    post:\n"
            "      summary: ping\n"
            "      description: ping\n"
            "      responses: {'200': {description: ok}}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec

        f = tmp_path / "no-webhook.yaml"
        f.write_text(body, encoding="utf-8")
        spec = load_spec(f, validate_schema=False)
        pointers = [p for _, _, _, p in iter_operations(spec)]
        assert not any(p.startswith("#/webhooks/") for p in pointers)


class TestComponentReusableSchemas:
    """Schemas defined in components.parameters / headers / requestBodies /
    responses get canonical pointers, not operation-site pointers."""

    def _load(self, tmp_path: Path) -> object:
        body = (
            "openapi: 3.0.3\n"
            "info: {title: T, version: '1.0'}\n"
            "paths:\n"
            "  /x:\n"
            "    get:\n"
            "      summary: x\n"
            "      description: x\n"
            "      parameters:\n"
            "        - {$ref: '#/components/parameters/Q'}\n"
            "      responses:\n"
            "        '200': {$ref: '#/components/responses/OK'}\n"
            "        '400': {description: bad}\n"
            "components:\n"
            "  parameters:\n"
            "    Q:\n"
            "      name: q\n"
            "      in: query\n"
            "      schema: {nullable: true}\n"
            "  headers:\n"
            "    X-Trace:\n"
            "      schema: {nullable: true}\n"
            "  requestBodies:\n"
            "    Pet:\n"
            "      content:\n"
            "        application/json:\n"
            "          schema: {nullable: true}\n"
            "  responses:\n"
            "    OK:\n"
            "      description: ok\n"
            "      headers:\n"
            "        X-Total: {schema: {nullable: true}}\n"
            "      content:\n"
            "        application/json:\n"
            "          schema: {nullable: true}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec

        f = tmp_path / "comps.yaml"
        f.write_text(body, encoding="utf-8")
        return load_spec(f, validate_schema=False)

    def test_all_canonical_pointers_present(self, tmp_path: Path) -> None:
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        spec = self._load(tmp_path)
        pointers = {p for _, p in iter_all_schemas(spec)}
        assert "#/components/parameters/Q/schema" in pointers
        assert "#/components/headers/X-Trace/schema" in pointers
        assert "#/components/requestBodies/Pet/content/application~1json/schema" in pointers
        assert "#/components/responses/OK/content/application~1json/schema" in pointers
        assert "#/components/responses/OK/headers/X-Total/schema" in pointers

    def test_operation_pointer_not_used_for_components_schema(self, tmp_path: Path) -> None:
        """The parameter Q referenced at /x's get must report its canonical
        components pointer, not the operation pointer."""
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        spec = self._load(tmp_path)
        pointers = {p for _, p in iter_all_schemas(spec)}
        assert not any(p == "#/paths/~1x/get/parameters/0/schema" for p in pointers), (
            "Q's schema should be reported at the components pointer, not the operation pointer"
        )


class TestOperationResponseHeadersAndParameterContent:
    def test_response_header_schema_walked(self, tmp_path: Path) -> None:
        body = (
            "openapi: 3.0.3\n"
            "info: {title: T, version: '1.0'}\n"
            "paths:\n"
            "  /x:\n"
            "    get:\n"
            "      summary: x\n"
            "      description: x\n"
            "      responses:\n"
            "        '200':\n"
            "          description: ok\n"
            "          headers:\n"
            "            X-Total: {schema: {nullable: true}}\n"
            "        '500': {description: bad}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        f = tmp_path / "respheader.yaml"
        f.write_text(body, encoding="utf-8")
        spec = load_spec(f, validate_schema=False)
        pointers = {p for _, p in iter_all_schemas(spec)}
        assert "#/paths/~1x/get/responses/200/headers/X-Total/schema" in pointers

    def test_parameter_content_schema_walked(self, tmp_path: Path) -> None:
        body = (
            "openapi: 3.0.3\n"
            "info: {title: T, version: '1.0'}\n"
            "paths:\n"
            "  /x:\n"
            "    get:\n"
            "      summary: x\n"
            "      description: x\n"
            "      parameters:\n"
            "        - name: filter\n"
            "          in: query\n"
            "          content:\n"
            "            application/json:\n"
            "              schema: {nullable: true}\n"
            "      responses:\n"
            "        '200': {description: ok}\n"
            "        '400': {description: bad}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        f = tmp_path / "paramcontent.yaml"
        f.write_text(body, encoding="utf-8")
        spec = load_spec(f, validate_schema=False)
        pointers = {p for _, p in iter_all_schemas(spec)}
        assert "#/paths/~1x/get/parameters/0/content/application~1json/schema" in pointers


class TestWalkSchema31Keywords:
    """The walker must recurse into 3.1 / JSON Schema 2020-12 sub-schemas
    (if/then/else, prefixItems, unevaluatedProperties, dependentSchemas,
    propertyNames, contains, unevaluatedItems)."""

    def test_recurses_into_if_then_else_and_prefix_items(self, tmp_path: Path) -> None:
        body = (
            "openapi: 3.1.0\n"
            "info: {title: T, version: '1.0'}\n"
            "paths:\n"
            "  /x:\n"
            "    get:\n"
            "      summary: x\n"
            "      description: x\n"
            "      responses:\n"
            "        '200':\n"
            "          description: ok\n"
            "          content:\n"
            "            application/json:\n"
            "              schema:\n"
            "                if: {properties: {flag: {type: string}}}\n"
            "                then: {properties: {enabled: {type: boolean}}}\n"
            "                else: {properties: {disabled: {type: boolean}}}\n"
            "                prefixItems:\n"
            "                  - {type: string}\n"
            "                propertyNames: {pattern: '^[a-z]+$'}\n"
            "                contains: {type: integer}\n"
            "                dependentSchemas:\n"
            "                  creditCard: {properties: {cvv: {type: string}}}\n"
            "                unevaluatedProperties: {type: string}\n"
            "                unevaluatedItems: {type: integer}\n"
            "              example: {flag: a}\n"
            "        '500': {description: bad}\n"
        )
        from hermes_openapi_auditor.auditor.loader import load_spec
        from hermes_openapi_auditor.auditor.walker import iter_all_schemas

        f = tmp_path / "kw.yaml"
        f.write_text(body, encoding="utf-8")
        spec = load_spec(f, validate_schema=False)
        pointers = {p for _, p in iter_all_schemas(spec)}
        base = "#/paths/~1x/get/responses/200/content/application~1json/schema"
        for sub in (
            "if",
            "then",
            "else",
            "prefixItems/0",
            "propertyNames",
            "contains",
            "dependentSchemas/creditCard",
            "unevaluatedProperties",
            "unevaluatedItems",
        ):
            assert f"{base}/{sub}" in pointers, f"missing {sub}"
