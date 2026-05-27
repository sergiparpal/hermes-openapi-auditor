"""End-to-end runner tests against the Petstore fixtures.

These exercise the full pipeline (load → walk → rules → profile filter →
render) without touching the Hermes handler shim. Each Petstore spec
should produce a non-empty findings list (they aren't pristine) but the
runner shouldn't crash on any of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hermes_openapi_auditor.auditor.runner import audit_openapi_spec


@pytest.mark.parametrize("version", ["2.0", "3.0", "3.1"])
class TestPetstoreEndToEnd:
    def test_default_profile_returns_findings_list(self, version: str, fixtures_dir: Path) -> None:
        result = audit_openapi_spec(
            path=str(fixtures_dir / f"petstore-{version}.yaml"),
        )
        assert result["version"] == version
        assert result["source"].endswith(f"petstore-{version}.yaml")
        assert isinstance(result["findings"], list)
        # Each finding has the documented shape.
        for f in result["findings"]:
            assert {"rule_id", "severity", "message", "path"} <= set(f)
            assert f["severity"] in {"info", "warning", "error"}

    def test_threshold_filters_lower_severities(self, version: str, fixtures_dir: Path) -> None:
        full = audit_openapi_spec(
            path=str(fixtures_dir / f"petstore-{version}.yaml"),
            severity_threshold="info",
        )
        errors_only = audit_openapi_spec(
            path=str(fixtures_dir / f"petstore-{version}.yaml"),
            severity_threshold="error",
        )
        assert len(errors_only["findings"]) <= len(full["findings"])
        assert all(f["severity"] == "error" for f in errors_only["findings"])

    def test_public_profile_escalates_descriptions_to_error(
        self, version: str, fixtures_dir: Path
    ) -> None:
        result = audit_openapi_spec(
            path=str(fixtures_dir / f"petstore-{version}.yaml"),
            profile="public",
            severity_threshold="error",
        )
        # Any missing-descriptions finding should now be at error severity.
        for f in result["findings"]:
            if f["rule_id"] == "missing-descriptions":
                assert f["severity"] == "error"

    def test_markdown_format(self, version: str, fixtures_dir: Path) -> None:
        result = audit_openapi_spec(
            path=str(fixtures_dir / f"petstore-{version}.yaml"),
            output_format="markdown",
        )
        assert "markdown" in result
        assert isinstance(result["markdown"], str)
        assert "# OpenAPI audit" in result["markdown"]


class TestRunnerSorting:
    def test_findings_sorted_by_severity_desc(self, fixtures_dir: Path) -> None:
        result = audit_openapi_spec(
            path=str(fixtures_dir / "petstore-3.0.yaml"),
            profile="public",
            severity_threshold="info",
        )
        ranks = {"error": 2, "warning": 1, "info": 0}
        sev_ranks = [ranks[f["severity"]] for f in result["findings"]]
        assert sev_ranks == sorted(sev_ranks, reverse=True)


class TestRunnerProfileSeverityOverrides:
    def test_internal_downgrades_descriptions_to_info(
        self, fixtures_dir: Path, synthetic_dir: Path
    ) -> None:
        result = audit_openapi_spec(
            path=str(synthetic_dir / "missing-descriptions-3.0.yaml"),
            profile="internal",
            severity_threshold="info",
        )
        relevant = [f for f in result["findings"] if f["rule_id"] == "missing-descriptions"]
        assert relevant, "missing-descriptions should fire on dirty fixture"
        assert all(f["severity"] == "info" for f in relevant)


class TestRunnerProfileOverridesFromConfig:
    def test_user_config_overrides_built_in(
        self,
        tmp_path: Path,
        synthetic_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = tmp_path / "openapi-auditor.yaml"
        config.write_text(
            "profiles:\n  agent-consumed:\n    missing-descriptions: error\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HERMES_OPENAPI_AUDITOR_CONFIG", str(config))
        result = audit_openapi_spec(
            path=str(synthetic_dir / "missing-descriptions-3.0.yaml"),
            severity_threshold="info",
        )
        rel = [f for f in result["findings"] if f["rule_id"] == "missing-descriptions"]
        assert rel, "rule should fire"
        assert all(f["severity"] == "error" for f in rel)

    def test_additional_properties_3_1_carveout_survives_override(
        self,
        tmp_path: Path,
        synthetic_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A 3.1 finding deliberately downgraded to info MUST survive a
        profile override that would otherwise escalate the rule.

        Without the rule emitting at a non-default severity (info vs the
        default warning), the runner cannot distinguish 'rule chose this'
        from 'rule fired at default'.
        """
        config = tmp_path / "openapi-auditor.yaml"
        config.write_text(
            "profiles:\n  agent-consumed:\n    additional-properties: error\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HERMES_OPENAPI_AUDITOR_CONFIG", str(config))
        result = audit_openapi_spec(
            path=str(synthetic_dir / "additional-properties-3.1.yaml"),
            severity_threshold="info",
        )
        rel = [f for f in result["findings"] if f["rule_id"] == "additional-properties"]
        assert rel, "rule should fire"
        # The Pet schema also carries unevaluatedProperties; the rule
        # downgrades severity to 'info' to signal a deliberate choice,
        # and the runner must preserve that over the 'error' override.
        assert all(f["severity"] == "info" for f in rel)


class TestRunnerCleanSpec:
    def test_clean_spec_has_zero_findings_at_warning(self, synthetic_dir: Path) -> None:
        result = audit_openapi_spec(
            path=str(synthetic_dir / "clean-3.0.yaml"),
            severity_threshold="warning",
        )
        assert result["findings"] == []
