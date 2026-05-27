"""Tests for ``auditor.detect.detect_version``."""

from __future__ import annotations

import pytest
from hermes_openapi_auditor.auditor.detect import InvalidSpecError, detect_version


class TestDetectVersion:
    def test_swagger_2_0(self) -> None:
        assert detect_version({"swagger": "2.0", "info": {}}) == "2.0"

    def test_openapi_3_0_patch(self) -> None:
        assert detect_version({"openapi": "3.0.3", "info": {}}) == "3.0"

    def test_openapi_3_0_zero(self) -> None:
        assert detect_version({"openapi": "3.0.0"}) == "3.0"

    def test_openapi_3_1_patch(self) -> None:
        assert detect_version({"openapi": "3.1.0", "info": {}}) == "3.1"

    def test_bare_major_minor_3_0(self) -> None:
        # Some specs in the wild drop the patch component.
        assert detect_version({"openapi": "3.0"}) == "3.0"

    def test_bare_major_minor_3_1(self) -> None:
        assert detect_version({"openapi": "3.1"}) == "3.1"

    def test_both_fields_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="both"):
            detect_version({"swagger": "2.0", "openapi": "3.0.0"})

    def test_no_version_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="neither"):
            detect_version({"info": {}})

    def test_unsupported_swagger_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="unsupported swagger"):
            detect_version({"swagger": "1.2"})

    def test_unsupported_openapi_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="unsupported openapi"):
            detect_version({"openapi": "2.0.0"})

    def test_openapi_3_2_rejected(self) -> None:
        # 3.2 exists in some drafts but is out of scope for v0.1.0.
        with pytest.raises(InvalidSpecError, match="unsupported openapi"):
            detect_version({"openapi": "3.2.0"})

    def test_numeric_swagger_coerced_to_string(self) -> None:
        # YAML can parse `swagger: 2.0` as a float; we coerce to string.
        assert detect_version({"swagger": 2.0}) == "2.0"
