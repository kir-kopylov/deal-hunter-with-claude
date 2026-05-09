"""Tier 1.4 — first_seen_at_almaty immutability + freshness recompute.

Проверяет ключевую конвенцию: first_seen_at_almaty ставится при первой записи и
никогда не меняется при последующих upsert'ах. minutes/hours_since_first_seen —
динамические, пересчитываются при каждом обращении.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.unit

ALMATY_TZ = timezone(timedelta(hours=5))


# Import the recompute helper from sheets_write.py
try:
    from sheets_write import _recompute_freshness, ALMATY_TZ as SW_TZ
except ImportError:
    pytest.skip("sheets_write.py not importable", allow_module_level=True)


class TestFreshnessRecompute:
    def test_zero_when_just_seen(self, monkeypatch):
        now = datetime.now(SW_TZ)
        row = {"first_seen_at_almaty": now.strftime("%Y-%m-%d %H:%M:%S")}
        result = _recompute_freshness(row.copy())
        assert result["minutes_since_first_seen"] in (0, 1)
        assert result["hours_since_first_seen"] in (0.0, 0.01)

    def test_30_minutes_ago(self):
        ago = datetime.now(SW_TZ) - timedelta(minutes=30)
        row = {"first_seen_at_almaty": ago.strftime("%Y-%m-%d %H:%M:%S")}
        result = _recompute_freshness(row.copy())
        assert 29 <= result["minutes_since_first_seen"] <= 31
        assert 0.48 <= result["hours_since_first_seen"] <= 0.52

    def test_2_hours_ago(self):
        ago = datetime.now(SW_TZ) - timedelta(hours=2)
        row = {"first_seen_at_almaty": ago.strftime("%Y-%m-%d %H:%M:%S")}
        result = _recompute_freshness(row.copy())
        assert 1.99 <= result["hours_since_first_seen"] <= 2.01

    def test_missing_first_seen_does_nothing(self):
        row = {"listing_url": "x"}
        result = _recompute_freshness(row.copy())
        assert "minutes_since_first_seen" not in result

    def test_invalid_first_seen_format_does_not_crash(self):
        row = {"first_seen_at_almaty": "not a date"}
        result = _recompute_freshness(row.copy())
        # Should silently skip, not raise
        assert result == {"first_seen_at_almaty": "not a date"}


class TestImmutabilityContract:
    """Документирует contract — first_seen_at_almaty НЕ должно меняться при upsert.
    Реальная проверка в integration test против тестового Sheet (test_sheets_writer.py)."""

    def test_immutability_is_documented(self):
        # This test exists to remind future devs: in cmd_upsert(), the existing
        # first_seen_at_almaty value is preserved from the sheet, not overwritten.
        # See sheets_write.py::cmd_upsert "preserved" branch.
        from sheets_write import cmd_upsert
        import inspect
        src = inspect.getsource(cmd_upsert)
        assert "first_seen_at_almaty" in src
        assert "preserved" in src or "existing_dict" in src
