"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Resolve repo root: tests/ is a sibling of scripts/, so parent of tests/ = repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent

# DEAL_HUNTER_HOME defaults to ~/.claude for runtime; for tests, default to repo root
# so pytest can find data/, scripts/, prompts/ even when run from a fresh clone.
DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(REPO_ROOT)))
os.environ["DEAL_HUNTER_HOME"] = str(DEAL_HUNTER_HOME)

# Make scripts importable
SCRIPTS_DIR = DEAL_HUNTER_HOME / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests, no network, included in pre-commit")
    config.addinivalue_line("markers", "integration: tests that hit real Google Sheets API")
    config.addinivalue_line(
        "markers", "expensive: tests that call Claude/Anthropic API (cost money)"
    )


@pytest.fixture
def tmp_state_dir(tmp_path, monkeypatch):
    """Provide isolated state directory for each test."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    return state
