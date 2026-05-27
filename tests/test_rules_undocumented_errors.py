"""Tests for the ``undocumented-errors`` rule."""

from __future__ import annotations

from pathlib import Path

from hermes_openapi_auditor.auditor import walker
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.rules import undocumented_errors


def _run(path: Path) -> list:
    spec = load_spec(path)
    return undocumented_errors.check(spec, walker)


class TestUndocumentedErrors:
    def test_clean_spec_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-3.0.yaml") == []

    def test_clean_spec_2_0_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-2.0.yaml") == []

    def test_2xx_only_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "undocumented-errors-3.0.yaml")
        operations = {f.operation for f in findings}
        assert "GET /pets" in operations

    def test_wildcard_4xx_counts(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "undocumented-errors-3.0.yaml")
        operations = {f.operation for f in findings}
        assert "GET /tags" not in operations  # has '4XX' wildcard

    def test_default_response_counts(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "undocumented-errors-3.0.yaml")
        operations = {f.operation for f in findings}
        assert "GET /owners" not in operations  # has 'default'

    def test_finding_points_at_responses(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "undocumented-errors-3.0.yaml")
        assert len(findings) == 1
        assert findings[0].path.endswith("/responses")
        assert findings[0].severity == "warning"
