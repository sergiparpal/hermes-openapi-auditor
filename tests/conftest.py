"""Shared pytest fixtures and path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES_DIR / "synthetic"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the bundled fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def synthetic_dir() -> Path:
    """Absolute path to the per-rule synthetic fixtures directory."""
    return SYNTHETIC_DIR
