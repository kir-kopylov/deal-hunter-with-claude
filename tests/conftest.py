"""Shared pytest fixtures and configuration."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts importable
SCRIPTS_DIR = Path.home() / ".claude" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests, no network, included in pre-commit")
    config.addinivalue_line("markers", "integration: tests that hit real Google Sheets API")
    config.addinivalue_line("markers", "expensive: tests that call Claude/Anthropic API (cost money)")


@pytest.fixture
def tmp_state_dir(tmp_path, monkeypatch):
    """Provide isolated state directory for each test."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    return state
