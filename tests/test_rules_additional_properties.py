"""Tests for the ``additional-properties`` rule."""

from __future__ import annotations

from pathlib import Path

from hermes_openapi_auditor.auditor import walker
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.rules import additional_properties


def _run(path: Path) -> list:
    spec = load_spec(path)
    return additional_properties.check(spec, walker)


class TestAdditionalProperties:
    def test_clean_spec_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-3.0.yaml") == []

    def test_named_props_plus_ap_true_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "additional-properties-3.0.yaml")
        # Only Pet has both named properties AND additionalProperties: true.
        # Owner has AP:false; Tag has AP:true but no named properties.
        assert len(findings) == 1, [f.message for f in findings]
        f = findings[0]
        assert f.rule_id == "additional-properties"
        assert "Pet" in f.path

    def test_default_severity_is_warning(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "additional-properties-3.0.yaml")
        assert all(f.severity == "warning" for f in findings)

    def test_ap_false_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "additional-properties-3.0.yaml")
        assert not any("Owner" in f.path for f in findings)

    def test_no_named_properties_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "additional-properties-3.0.yaml")
        assert not any("Tag" in f.path for f in findings)

    def test_3_1_unevaluated_properties_keeps_info(self, synthetic_dir: Path) -> None:
        """unevaluatedProperties means the author thought about it; stay at info."""
        findings = _run(synthetic_dir / "additional-properties-3.1.yaml")
        assert len(findings) == 1
        assert findings[0].severity == "info"
