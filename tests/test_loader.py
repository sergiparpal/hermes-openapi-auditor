"""Tests for ``auditor.loader.load_spec``."""

from __future__ import annotations

from pathlib import Path

import pytest
from hermes_openapi_auditor.auditor.detect import InvalidSpecError
from hermes_openapi_auditor.auditor.loader import load_spec


class TestLoadSpecPetstore:
    """Smoke-tests against the three vendored Petstore samples."""

    def test_petstore_2_0(self, fixtures_dir: Path) -> None:
        spec = load_spec(fixtures_dir / "petstore-2.0.yaml")
        assert spec.version == "2.0"
        assert spec.source.endswith("petstore-2.0.yaml")
        assert "paths" in spec.data

    def test_petstore_3_0(self, fixtures_dir: Path) -> None:
        spec = load_spec(fixtures_dir / "petstore-3.0.yaml")
        assert spec.version == "3.0"
        assert "paths" in spec.data
        assert "components" in spec.data

    def test_petstore_3_1(self, fixtures_dir: Path) -> None:
        spec = load_spec(fixtures_dir / "petstore-3.1.yaml")
        assert spec.version == "3.1"
        assert "paths" in spec.data

    def test_ref_resolution_default_on(self, fixtures_dir: Path) -> None:
        """Loaded 3.0 spec should have $refs to schemas resolved inline."""
        spec = load_spec(fixtures_dir / "petstore-3.0.yaml", resolve_refs=True)
        # Walk to a known $ref site and verify it's not still {"$ref": "..."}
        # Find a response with a schema reference.
        for _, path_item in spec.data.get("paths", {}).items():
            for verb, op in path_item.items():
                if not isinstance(op, dict) or verb not in {"get", "post", "put", "delete"}:
                    continue
                for resp in op.get("responses", {}).values():
                    for media in resp.get("content", {}).values():
                        schema = media.get("schema", {})
                        # Should NOT be a {"$ref": "..."} terminal node any more.
                        assert list(schema.keys()) != ["$ref"], "$ref should have been resolved"

    def test_ref_resolution_off_preserves_refs(self, fixtures_dir: Path) -> None:
        """With resolve_refs=False the raw $ref nodes survive."""
        spec = load_spec(fixtures_dir / "petstore-3.0.yaml", resolve_refs=False)
        # At least one $ref should still be present somewhere in the spec.
        s = repr(spec.data)
        assert "$ref" in s


class TestLoadSpecInvalid:
    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_spec("/nonexistent/spec.yaml")

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.txt"
        f.write_text("openapi: 3.0.0", encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="unsupported file extension"):
            load_spec(f)

    def test_unparseable_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.yaml"
        f.write_text("foo: [unterminated", encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="parse YAML"):
            load_spec(f)

    def test_unparseable_json(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.json"
        f.write_text("{not json", encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="parse JSON"):
            load_spec(f)

    def test_root_must_be_mapping(self, tmp_path: Path) -> None:
        f = tmp_path / "list.yaml"
        f.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="mapping"):
            load_spec(f)

    def test_frankenstein_rejected(self, fixtures_dir: Path) -> None:
        with pytest.raises(InvalidSpecError, match="both"):
            load_spec(fixtures_dir / "invalid-frankenstein.yaml")

    def test_no_version_rejected(self, fixtures_dir: Path) -> None:
        with pytest.raises(InvalidSpecError, match="neither"):
            load_spec(fixtures_dir / "invalid-no-version.json")

    def test_swagger_with_components_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.yaml"
        f.write_text(
            "swagger: '2.0'\n"
            "info: {title: T, version: '1.0'}\n"
            "paths: {}\n"
            "components: {schemas: {}}\n",
            encoding="utf-8",
        )
        with pytest.raises(InvalidSpecError):
            load_spec(f)

    def test_openapi_with_definitions_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.yaml"
        f.write_text(
            "openapi: '3.0.3'\ninfo: {title: T, version: '1.0'}\npaths: {}\ndefinitions: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(InvalidSpecError, match="definitions"):
            load_spec(f)

    def test_meta_schema_violation(self, tmp_path: Path) -> None:
        # Valid version field, but missing required 'info' and 'paths'.
        f = tmp_path / "skeletal.yaml"
        f.write_text("openapi: '3.0.3'\n", encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="meta-schema"):
            load_spec(f)
