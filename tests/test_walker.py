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
