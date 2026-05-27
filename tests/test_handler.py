"""Tests for the Hermes-facing handler in ``tools.py``.

Verifies the handler contract (plan §2.6.1):

- Always returns a JSON string.
- Never raises.
- Accepts and ignores unexpected ``**kwargs``.
- Validates ``profile``, ``severity_threshold``, ``format`` enums.
"""

from __future__ import annotations

import json
from pathlib import Path

from hermes_openapi_auditor.tools import audit_openapi_spec


def _parse(s: str) -> dict:
    assert isinstance(s, str)
    parsed = json.loads(s)
    assert isinstance(parsed, dict)
    return parsed


class TestHandlerContract:
    def test_missing_path_returns_error_json(self) -> None:
        d = _parse(audit_openapi_spec({}))
        assert "error" in d
        assert "path" in d["error"]

    def test_empty_path_returns_error_json(self) -> None:
        d = _parse(audit_openapi_spec({"path": ""}))
        assert "error" in d

    def test_missing_file_returns_error_json(self) -> None:
        d = _parse(audit_openapi_spec({"path": "/no/such/file.yaml"}))
        assert "error" in d
        assert "not found" in d["error"]

    def test_extra_kwargs_ignored(self, fixtures_dir: Path) -> None:
        # **kwargs forwards-compatibility: passing extras must not break.
        out = audit_openapi_spec(
            {"path": str(fixtures_dir / "petstore-3.0.yaml")},
            hermes_request_id="abc-123",
            unknown_future_key=42,
        )
        d = _parse(out)
        assert "findings" in d

    def test_invalid_profile_returns_error_json(self, fixtures_dir: Path) -> None:
        d = _parse(
            audit_openapi_spec(
                {
                    "path": str(fixtures_dir / "petstore-3.0.yaml"),
                    "profile": "totally-made-up",
                }
            )
        )
        assert "error" in d
        assert "profile" in d["error"]

    def test_invalid_threshold_returns_error_json(self, fixtures_dir: Path) -> None:
        d = _parse(
            audit_openapi_spec(
                {
                    "path": str(fixtures_dir / "petstore-3.0.yaml"),
                    "severity_threshold": "critical",
                }
            )
        )
        assert "error" in d

    def test_invalid_format_returns_error_json(self, fixtures_dir: Path) -> None:
        d = _parse(
            audit_openapi_spec(
                {
                    "path": str(fixtures_dir / "petstore-3.0.yaml"),
                    "format": "xml",
                }
            )
        )
        assert "error" in d

    def test_invalid_spec_returns_error_json(self, fixtures_dir: Path) -> None:
        d = _parse(audit_openapi_spec({"path": str(fixtures_dir / "invalid-no-version.json")}))
        assert "error" in d

    def test_success_returns_findings_list(self, fixtures_dir: Path) -> None:
        d = _parse(
            audit_openapi_spec(
                {
                    "path": str(fixtures_dir / "petstore-3.0.yaml"),
                    "severity_threshold": "info",
                }
            )
        )
        assert "findings" in d
        assert isinstance(d["findings"], list)
        assert d["version"] == "3.0"

    def test_markdown_format_returns_string(self, fixtures_dir: Path) -> None:
        d = _parse(
            audit_openapi_spec(
                {
                    "path": str(fixtures_dir / "petstore-3.0.yaml"),
                    "format": "markdown",
                }
            )
        )
        assert "markdown" in d
        assert isinstance(d["markdown"], str)

    def test_handler_does_not_raise_on_unexpected_internal_error(self, monkeypatch) -> None:
        """Even if the runner itself blows up, the handler returns JSON."""
        from hermes_openapi_auditor import tools as tools_module

        def kaboom(**_kwargs):
            raise RuntimeError("simulated internal error")

        monkeypatch.setattr(tools_module, "_run_audit", kaboom)
        d = _parse(audit_openapi_spec({"path": "/anything.yaml"}))
        assert "error" in d
        assert "RuntimeError" in d["error"]
