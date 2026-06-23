"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import re
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


class FakeWorksheet:
    """In-memory заглушка для gspread Worksheet.

    Реализует ровно ту поверхность, которой пользуется sheets_write.py:
    row_values / col_values / append_row(s) / update / update_cell / get_all_records.
    Хранит данные как список строк (список ячеек); строка 0 — заголовки.
    """

    def __init__(self, title: str = "Sheet1", rows: list[list] | None = None):
        self.title = title
        self._rows: list[list] = [list(r) for r in (rows or [])]

    # --- внутреннее ---
    @staticmethod
    def _parse_a1(a1: str) -> tuple[int, int]:
        """'A1' / 'A12' → (row, col) 1-индексные."""
        m = re.match(r"^([A-Za-z]+)(\d+)$", a1)
        if not m:
            raise ValueError(f"Unsupported A1 range: {a1!r}")
        letters, row = m.group(1).upper(), int(m.group(2))
        col = 0
        for ch in letters:
            col = col * 26 + (ord(ch) - ord("A") + 1)
        return row, col

    def _ensure_size(self, row_idx: int, col_idx: int) -> None:
        while len(self._rows) <= row_idx:
            self._rows.append([])
        row = self._rows[row_idx]
        while len(row) <= col_idx:
            row.append("")

    @staticmethod
    def _rtrim(values: list) -> list:
        out = list(values)
        while out and (out[-1] == "" or out[-1] is None):
            out.pop()
        return out

    # --- gspread-совместимый API ---
    def row_values(self, n: int) -> list:
        if n - 1 >= len(self._rows):
            return []
        return self._rtrim(self._rows[n - 1])

    def col_values(self, idx: int) -> list:
        col = [(row[idx - 1] if idx - 1 < len(row) else "") for row in self._rows]
        return self._rtrim(col)

    def append_row(self, values: list, value_input_option: str | None = None) -> None:
        self._rows.append(list(values))

    def append_rows(self, rows: list[list], value_input_option: str | None = None) -> None:
        for r in rows:
            self._rows.append(list(r))

    def update(self, a1: str, values: list[list], value_input_option: str | None = None) -> None:
        start_row, start_col = self._parse_a1(a1)
        for r_off, row_vals in enumerate(values):
            for c_off, val in enumerate(row_vals):
                ri, ci = start_row - 1 + r_off, start_col - 1 + c_off
                self._ensure_size(ri, ci)
                self._rows[ri][ci] = val

    def update_cell(self, row: int, col: int, value) -> None:
        self._ensure_size(row - 1, col - 1)
        self._rows[row - 1][col - 1] = value

    def get_all_records(self) -> list[dict]:
        if not self._rows:
            return []
        headers = self._rows[0]
        out = []
        for row in self._rows[1:]:
            out.append({h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)})
        return out


@pytest.fixture
def make_ws():
    """Фабрика чистых FakeWorksheet (по одному на вызов)."""

    def _make(rows: list[list] | None = None, title: str = "Sheet1") -> FakeWorksheet:
        return FakeWorksheet(title=title, rows=rows)

    return _make
