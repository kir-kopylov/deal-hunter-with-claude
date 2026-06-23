"""P0 — тесты для generate_launchd.

calendar_intervals_for_group — чистая функция, превращающая записи schedule.yaml
в launchd StartCalendarInterval. Раньше у файла было 0% покрытия. Здесь же
фиксируем маппинг дней недели sun=0..sat=6 (конвенция launchd), чтобы он не
разъехался незаметно с другими частями кода.
"""

from __future__ import annotations

import generate_launchd as gl
import pytest
from generate_launchd import (
    DAY_NAME_TO_NUM,
    calendar_intervals_for_group,
    render_plist,
)

pytestmark = pytest.mark.unit


class TestDayNameMapping:
    def test_launchd_weekday_convention(self):
        # launchd: воскресенье=0, понедельник=1, ..., суббота=6.
        # Этот тест — якорь: если кто-то поменяет маппинг, тест упадёт.
        assert DAY_NAME_TO_NUM == {
            "sun": 0,
            "mon": 1,
            "tue": 2,
            "wed": 3,
            "thu": 4,
            "fri": 5,
            "sat": 6,
        }


class TestCalendarIntervals:
    def test_wildcard_day_has_no_weekday(self):
        out = calendar_intervals_for_group([{"day": "*", "hour": 8, "minute": 30}])
        assert out == [{"Hour": 8, "Minute": 30}]
        assert "Weekday" not in out[0]

    def test_single_day(self):
        out = calendar_intervals_for_group([{"day": "mon", "hour": 9, "minute": 0}])
        assert out == [{"Weekday": 1, "Hour": 9, "Minute": 0}]

    def test_day_list_expands_to_multiple_intervals(self):
        out = calendar_intervals_for_group(
            [{"day": ["mon", "wed", "fri", "sat"], "hour": 11, "minute": 30}]
        )
        assert len(out) == 4
        assert {iv["Weekday"] for iv in out} == {1, 3, 5, 6}
        assert all(iv["Hour"] == 11 and iv["Minute"] == 30 for iv in out)

    def test_multiple_entries_accumulate(self):
        out = calendar_intervals_for_group(
            [
                {"day": "*", "hour": 9, "minute": 0},
                {"day": "*", "hour": 14, "minute": 0},
                {"day": "*", "hour": 20, "minute": 0},
            ]
        )
        assert len(out) == 3
        assert [iv["Hour"] for iv in out] == [9, 14, 20]

    def test_hour_and_minute_coerced_to_int(self):
        out = calendar_intervals_for_group([{"day": "*", "hour": "8", "minute": "05"}])
        assert out == [{"Hour": 8, "Minute": 5}]

    def test_unknown_day_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown day"):
            calendar_intervals_for_group([{"day": "funday", "hour": 9, "minute": 0}])

    def test_unknown_day_inside_list_raises(self):
        with pytest.raises(ValueError, match="Unknown day"):
            calendar_intervals_for_group([{"day": ["mon", "blursday"], "hour": 9, "minute": 0}])

    def test_empty_schedule_returns_empty(self):
        assert calendar_intervals_for_group([]) == []


class TestRenderPlist:
    def test_plist_contains_label_and_group(self):
        intervals = [{"Weekday": 1, "Hour": 9, "Minute": 0}]
        xml = render_plist("com.kkopylov.deals.A1", "A1", intervals)
        assert "<?xml" in xml
        assert "<string>com.kkopylov.deals.A1</string>" in xml
        # Имя группы передаётся и в ProgramArguments, и в SOURCE_GROUP.
        assert xml.count("<string>A1</string>") >= 2

    def test_plist_renders_each_interval(self):
        intervals = [
            {"Weekday": 1, "Hour": 9, "Minute": 0},
            {"Hour": 14, "Minute": 0},
        ]
        xml = render_plist("lbl", "A1", intervals)
        assert "<key>Weekday</key><integer>1</integer>" in xml
        assert "<key>Hour</key><integer>9</integer>" in xml
        assert "<key>Hour</key><integer>14</integer>" in xml

    def test_plist_escapes_xml_special_chars(self):
        # Label с амперсандом должен экранироваться в &amp; (валидный XML).
        xml = render_plist("a & b", "A1", [{"Hour": 8, "Minute": 0}])
        assert "<string>a &amp; b</string>" in xml
        assert "a & b</string>" not in xml


class TestMain:
    def test_main_writes_plist_per_group(self, monkeypatch, tmp_path):
        sched = tmp_path / "schedule.yaml"
        sched.write_text(
            "groups:\n"
            "  A1:\n"
            "    schedule:\n"
            "      - {day: '*', hour: 9, minute: 0}\n"
            "  A3:\n"
            "    schedule:\n"
            "      - {day: ['mon', 'wed'], hour: 11, minute: 30}\n"
        )
        monkeypatch.setattr(gl, "SCHEDULE_YAML", sched)
        monkeypatch.setattr(gl, "LAUNCH_AGENTS", tmp_path / "agents")
        monkeypatch.setattr(gl, "LOG_DIR", tmp_path / "logs")

        assert gl.main() == 0
        a1 = tmp_path / "agents" / "com.kkopylov.deals.A1.plist"
        a3 = tmp_path / "agents" / "com.kkopylov.deals.A3.plist"
        assert a1.exists() and a3.exists()
        assert "<string>A1</string>" in a1.read_text()
        # A3 — два дня → два StartCalendarInterval-словаря.
        assert a3.read_text().count("<key>Weekday</key>") == 2

    def test_main_missing_schedule_returns_1(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(gl, "SCHEDULE_YAML", tmp_path / "nope.yaml")
        assert gl.main() == 1
        assert "not found" in capsys.readouterr().err
