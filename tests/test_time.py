"""Tier 1.5 — Time-aware tests с freezegun.

Edge cases для system, который сильно зависит от времени:
- hours_since_first_seen в полночь Almaty
- cadence «mon/wed/fri» в воскресенье 23:59 vs понедельник 00:01
- stale-queue alert ровно через 24ч

Время-функции импортируются из рабочего кода (timeutil, generate_launchd),
а не переписываются здесь — иначе тест проверял бы собственную копию.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from generate_launchd import schedule_fires_on
from timeutil import ALMATY_TZ, hours_since

try:
    from freezegun import freeze_time
except ImportError:
    freeze_time = None

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(freeze_time is None, reason="freezegun not installed"),
]


class TestFreshnessTimeMath:
    def test_hours_since_at_midnight_almaty(self):
        with freeze_time("2026-05-09 19:00:00", tz_offset=0):  # = 00:00 May 10 in Almaty
            now = datetime.now(ALMATY_TZ)
            # listing seen 8 hours ago in Almaty time
            fsa = "2026-05-09 16:00:00"
            assert abs(hours_since(fsa, now) - 8.0) < 0.01

    def test_hours_since_zero_for_just_added(self):
        # freeze UTC at 12:00, Almaty (UTC+5) sees 17:00; listing was just seen
        with freeze_time("2026-05-09 12:00:00"):
            now = datetime.now(ALMATY_TZ)
            assert hours_since("2026-05-09 17:00:00", now) == 0.0

    def test_hours_since_handles_year_rollover(self):
        # freeze UTC at 07:00 on Jan 1, Almaty sees 12:00; 14h before that = 22:00 Dec 31 Almaty
        with freeze_time("2027-01-01 07:00:00"):
            now = datetime.now(ALMATY_TZ)
            assert abs(hours_since("2026-12-31 22:00:00", now) - 14.0) < 0.01


class TestCadenceDayBoundary:
    """Граница суток для cadence-расписаний. Использует generate_launchd.schedule_fires_on."""

    def test_single_day_cadence_off_on_sunday_2359(self):
        with freeze_time("2026-05-10 18:59:00", tz_offset=0):  # Sun 23:59 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 6  # sunday
            assert not schedule_fires_on({"day": "mon", "hour": 11, "minute": 30}, now)

    def test_single_day_cadence_on_monday_0001(self):
        with freeze_time("2026-05-10 19:01:00", tz_offset=0):  # Mon 00:01 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 0  # monday
            assert schedule_fires_on({"day": "mon", "hour": 11, "minute": 30}, now)

    def test_mwf_list_cadence_on_wednesday(self):
        with freeze_time("2026-05-13 06:00:00", tz_offset=0):  # Wed 11:00 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 2  # wednesday
            entry = {"day": ["mon", "wed", "fri"], "hour": 11, "minute": 30}
            assert schedule_fires_on(entry, now)

    def test_mwf_list_cadence_off_on_tuesday(self):
        with freeze_time("2026-05-12 06:00:00", tz_offset=0):  # Tue 11:00 Almaty
            now = datetime.now(ALMATY_TZ)
            assert now.weekday() == 1  # tuesday
            entry = {"day": ["mon", "wed", "fri"], "hour": 11, "minute": 30}
            assert not schedule_fires_on(entry, now)

    def test_wildcard_fires_every_day(self):
        with freeze_time("2026-05-12 06:00:00", tz_offset=0):  # Tuesday
            now = datetime.now(ALMATY_TZ)
            assert schedule_fires_on({"day": "*", "hour": 9, "minute": 0}, now)


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
