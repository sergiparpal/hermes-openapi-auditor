"""Tests for the ``ambiguous-types`` rule (full version dispatch)."""

from __future__ import annotations

from pathlib import Path

from hermes_openapi_auditor.auditor import walker
from hermes_openapi_auditor.auditor.loader import load_spec
from hermes_openapi_auditor.auditor.rules import ambiguous_types


def _run(path: Path) -> list:
    # validate_schema=False because the 3.1 fixture intentionally contains
    # invalid 3.1 syntax (the exact thing the rule is meant to flag).
    spec = load_spec(path, validate_schema=False)
    return ambiguous_types.check(spec, walker)


class TestAmbiguousTypesClean:
    def test_clean_3_0_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-3.0.yaml") == []

    def test_clean_2_0_has_no_findings(self, synthetic_dir: Path) -> None:
        assert _run(synthetic_dir / "clean-2.0.yaml") == []


class TestAmbiguousTypes2_0:
    def test_bare_string_param_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-2.0.yaml")
        # `filter` is bare type: string with no constraints.
        assert any("'filter'" in f.message for f in findings)

    def test_constrained_params_do_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-2.0.yaml")
        # enum/format/pattern variants should NOT appear.
        names = {f.message for f in findings}
        assert not any("'status'" in m for m in names)
        assert not any("'since'" in m for m in names)
        assert not any("'code'" in m for m in names)

    def test_type_file_does_not_trigger(self, synthetic_dir: Path) -> None:
        """`type: file` is a legitimate 2.0 multipart idiom."""
        findings = _run(synthetic_dir / "ambiguous-types-2.0.yaml")
        assert not any("'photo'" in f.message for f in findings)


class TestAmbiguousTypes3_0:
    def test_nullable_without_type_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.0.yaml")
        assert any(
            "'nullable: true'" in f.message and "nothing to apply" in f.message for f in findings
        )

    def test_nullable_with_type_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.0.yaml")
        # `deactivated_at` has nullable + type: string -> should NOT trigger.
        assert not any("deactivated_at" in f.path for f in findings)

    def test_oneof_without_discriminator_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.0.yaml")
        assert any("oneOf" in f.message and "discriminator" in f.message for f in findings)

    def test_oneof_with_discriminator_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.0.yaml")
        # Animal has oneOf + discriminator -> no finding for Animal.
        assert not any(f.path.endswith("/Animal") for f in findings)


class TestAmbiguousTypes3_1:
    def test_nullable_anywhere_triggers(self, synthetic_dir: Path) -> None:
        """`nullable` was removed in 3.1; any use triggers."""
        findings = _run(synthetic_dir / "ambiguous-types-3.1.yaml")
        assert any(
            "'nullable: true'" in f.message and "removed in OpenAPI 3.1" in f.message
            for f in findings
        )

    def test_boolean_exclusive_minimum_triggers(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.1.yaml")
        assert any("exclusiveMinimum" in f.message and "boolean" in f.message for f in findings)

    def test_numeric_exclusive_minimum_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.1.yaml")
        # `weight` has exclusiveMinimum: 0 (numeric) -> no finding for weight.
        assert not any("/weight" in f.path for f in findings)

    def test_type_array_nullable_does_not_trigger(self, synthetic_dir: Path) -> None:
        findings = _run(synthetic_dir / "ambiguous-types-3.1.yaml")
        # `deactivated_at` uses type: [string, null] -- correct 3.1 syntax.
        assert not any("/deactivated_at" in f.path for f in findings)
