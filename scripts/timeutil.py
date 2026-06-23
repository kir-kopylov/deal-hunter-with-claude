"""Помощники для работы со временем Алматы (UTC+5, без DST).

Единый источник правды для меток времени и расчёта «свежести» листинга.
Раньше эта математика дублировалась в sheets_write.py и копией в test_time.py —
теперь обе стороны импортируют отсюда.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

ALMATY_TZ = timezone(timedelta(hours=5))  # UTC+5 без DST
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_almaty_iso() -> str:
    """Текущее время Алматы в формате 'YYYY-MM-DD HH:MM:SS'."""
    return datetime.now(ALMATY_TZ).strftime(TS_FORMAT)


def parse_almaty(ts: str) -> datetime:
    """Разобрать метку 'YYYY-MM-DD HH:MM:SS' как время Алматы. Бросает ValueError."""
    return datetime.strptime(ts, TS_FORMAT).replace(tzinfo=ALMATY_TZ)


def hours_since(first_seen_iso: str, now: datetime) -> float:
    """Сколько часов прошло с first_seen_iso до now (float, без округления)."""
    return (now - parse_almaty(first_seen_iso)).total_seconds() / 3600


def minutes_since(first_seen_iso: str, now: datetime) -> int:
    """Сколько полных минут прошло с first_seen_iso до now."""
    return int((now - parse_almaty(first_seen_iso)).total_seconds() // 60)
