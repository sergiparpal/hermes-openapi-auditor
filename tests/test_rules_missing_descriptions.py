"""Tests for the ``missing-descriptions`` rule."""

from __future__ import annotations

from pathlib import Path

from hermes_openapi_auditor.auditor import walker
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.rules import missing_descriptions


def _run(path: Path) -> list:
    spec = load_spec(path)
    return missing_descriptions.check(spec, walker)


class TestMissingDescriptions:
    def test_clean_spec_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-3.0.yaml") == []

    def test_dirty_spec_flags_only_the_one_bare_operation(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-descriptions-3.0.yaml")
        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "missing-descriptions"
        assert f.severity == "warning"
        assert f.operation == "GET /pets"
        assert f.path == "#/paths/~1pets/get"

    def test_summary_only_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-descriptions-3.0.yaml")
        operations = {f.operation for f in findings}
        assert "POST /pets" not in operations

    def test_description_only_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "missing-descriptions-3.0.yaml")
        operations = {f.operation for f in findings}
        assert "PUT /tags" not in operations

    def test_whitespace_only_summary_counts_as_missing(self, tmp_path: Path) -> None:
        spec_yaml = (
            "openapi: 3.0.3\n"
            "info: {title: T, version: '1.0'}\n"
            "paths:\n"
            "  /x:\n"
            "    get:\n"
            "      summary: '   '\n"
            "      description: ''\n"
            "      responses:\n"
            "        '200': {description: ok}\n"
            "        '400': {description: bad}\n"
        )
        f = tmp_path / "spec.yaml"
        f.write_text(spec_yaml, encoding="utf-8")
        findings = _run(f)
        assert len(findings) == 1
