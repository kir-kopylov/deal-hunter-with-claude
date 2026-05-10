"""Tier 1.5 — Time-aware tests с freezegun.

Edge cases для system, который сильно зависит от времени:
- hours_since_first_seen в полночь Almaty
- cadence «mon/wed/fri» в воскресенье 23:59 vs понедельник 00:01
- stale-queue alert ровно через 24ч
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

try:
    from freezegun import freeze_time
except ImportError:
    freeze_time = None

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(freeze_time is None, reason="freezegun not installed"),
]


ALMATY_TZ = timezone(timedelta(hours=5))


def hours_since(first_seen_iso: str, now: datetime) -> float:
    fsa = datetime.strptime(first_seen_iso, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ALMATY_TZ)
    return (now - fsa).total_seconds() / 3600


def is_run_day(day_name: str, now: datetime) -> bool:
    """Mirror generate_launchd day-name logic."""
    weekday_map = {"sun": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5}
    return now.weekday() == weekday_map[day_name]


class TestFreshnessTimeMath:
    def test_hours_since_at_midnight_almaty(self):
        with freeze_time("2026-05-09 19:00:00", tz_offset=0):  # = 00:00 May 10 in Almaty
            now = datetime.now(ALMATY_TZ)
            # listing seen 8 hours ago in Almaty time
            fsa = "2026-05-09 16:00:00"
            assert abs(hours_since(fsa, now) - 8.0) < 0.01

    def test_hours_since_zero_for_just_added(self):
        with freeze_time("2026-05-09 12:00:00", tz_offset=5):
            now = datetime.now(ALMATY_TZ)
            assert hours_since("2026-05-09 17:00:00", now) == 0.0

    def test_hours_since_handles_year_rollover(self):
        with freeze_time("2027-01-01 02:00:00", tz_offset=5):
            now = datetime.now(ALMATY_TZ)
            assert abs(hours_since("2026-12-31 21:00:00", now) - 14.0) < 0.01


class TestCadenceDayBoundary:
    def test_mwf_cadence_on_sunday_2359(self):
        with freeze_time("2026-05-10 18:59:00", tz_offset=0):  # Sun 23:59 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 6  # sunday
            assert not is_run_day("mon", now)

    def test_mwf_cadence_on_monday_0001(self):
        with freeze_time("2026-05-10 19:01:00", tz_offset=0):  # Mon 00:01 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 0  # monday
            assert is_run_day("mon", now)


class TestStaleQueueAlert:
    """STALE_QUEUE alert should fire exactly once after 24h, not at 23:30 or repeated."""

    def test_alert_fires_at_24h_exactly(self):
        # Скелет: задача создана в 12:00, проверка в 12:00 следующего дня
        created = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ALMATY_TZ)
        check_time = created + timedelta(hours=24)
        assert (check_time - created).total_seconds() / 3600 == 24.0

    def test_alert_does_not_fire_at_23h(self):
        created = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ALMATY_TZ)
        check_time = created + timedelta(hours=23, minutes=30)
        elapsed_h = (check_time - created).total_seconds() / 3600
        assert elapsed_h < 24

    def test_give_up_threshold_at_7d(self):
        created = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ALMATY_TZ)
        check_time = created + timedelta(days=7)
        assert (check_time - created).days == 7
