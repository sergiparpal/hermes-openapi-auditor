"""Tests for the ``missing-examples`` rule (version-divergent)."""

from __future__ import annotations

from pathlib import Path

from hermes_openapi_auditor.auditor import walker
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.rules import missing_examples


def _run(path: Path) -> list:
    spec = load_spec(path)
    return missing_examples.check(spec, walker)


class TestMissingExamplesClean:
    def test_clean_3_0(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-3.0.yaml") == []

    def test_clean_2_0(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-2.0.yaml") == []


class TestMissingExamples2_0:
    def test_body_param_without_example_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-2.0.yaml")
        assert any("Request body" in f.message for f in findings)

    def test_response_without_example_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-2.0.yaml")
        # POST /pets has a response 200 with a schema but no example.
        assert any(f.operation == "POST /pets" and "Response 200" in f.message for f in findings)

    def test_schema_level_example_satisfies(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-2.0.yaml")
        # GET /tags' response has `example` on the schema -- no finding for it.
        assert not any(f.operation == "GET /tags" for f in findings)


class TestMissingExamples3_0:
    def test_request_body_without_example_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-3.0.yaml")
        assert any("Request body" in f.message for f in findings)

    def test_response_without_example_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-3.0.yaml")
        assert any("Response 200" in f.message and f.operation == "POST /pets" for f in findings)

    def test_schema_level_example_satisfies(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-3.0.yaml")
        # GET /tags' schema has `example`; no finding for its 200 response.
        assert not any(f.operation == "GET /tags" for f in findings)


class TestMissingExamples3_1:
    def test_schema_examples_array_satisfies(self, synthetic_dir: Path) -> None:
        """A non-empty `examples: [...]` array on the schema counts (3.1 only)."""
        findings = _run(synthetic_dir / "missing-examples-3.1.yaml")
        # POST /pets has request without example -> triggers.
        # POST /pets response 200 has schema-level `examples: [{id: 1}]` -> does NOT trigger.
        msgs_for_post = [f.message for f in findings if f.operation == "POST /pets"]
        assert any("Request body" in m for m in msgs_for_post)
        assert not any("Response 200" in m for m in msgs_for_post)

    def test_empty_examples_array_does_not_satisfy(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-examples-3.1.yaml")
        # GET /tags has `examples: []` (empty) -> still triggers.
        assert any(f.operation == "GET /tags" for f in findings)
