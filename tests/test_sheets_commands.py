"""P1 — тесты команд sheets_write поверх in-memory FakeWorksheet.

Раньше cmd_append/cmd_upsert/cmd_mark_unavailable/cmd_read не покрывались вообще
(требовался живой gspread). FakeWorksheet (в conftest) закрывает этот пробел —
самую ценную непокрытую логику записи в Sheet.
"""

from __future__ import annotations

import pytest
from sheets_write import (
    cmd_append,
    cmd_mark_unavailable,
    cmd_read,
    cmd_upsert,
    ensure_headers,
    find_row_by_key,
    load_column_mapping,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def deals_mapping():
    return load_column_mapping("Deals")


@pytest.fixture
def scl_mapping():
    return load_column_mapping("Source_Check_Log")


class TestEnsureHeaders:
    def test_writes_headers_to_empty_sheet(self, make_ws, scl_mapping):
        ws = make_ws()
        headers = ensure_headers(ws, scl_mapping)
        assert ws.row_values(1) == headers
        assert "ID запуска" in headers
        assert "Источник" in headers

    def test_idempotent_on_second_call(self, make_ws, scl_mapping):
        ws = make_ws()
        first = ensure_headers(ws, scl_mapping)
        second = ensure_headers(ws, scl_mapping)
        assert first == second

    def test_appends_missing_headers(self, make_ws, scl_mapping):
        # Лист уже содержит только один заголовок — остальные должны допиститься.
        ws = make_ws(rows=[["ID запуска"]])
        headers = ensure_headers(ws, scl_mapping)
        assert headers[0] == "ID запуска"  # существующий порядок сохранён
        assert "Источник" in headers
        assert len(headers) == len([k for k in scl_mapping if k != "use_mapping_from"])


class TestFindRowByKey:
    def test_finds_existing(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(
            ws, deals_mapping, [{"listing_url": "u1"}, {"listing_url": "u2"}], key="listing_url"
        )
        key_col = deals_mapping["listing_url"]
        assert find_row_by_key(ws, key_col, "u1") == 2  # row1=headers, row2=u1
        assert find_row_by_key(ws, key_col, "u2") == 3

    def test_missing_value_returns_none(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(ws, deals_mapping, [{"listing_url": "u1"}], key="listing_url")
        assert find_row_by_key(ws, deals_mapping["listing_url"], "nope") is None

    def test_missing_key_column_returns_none(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(ws, deals_mapping, [{"listing_url": "u1"}], key="listing_url")
        assert find_row_by_key(ws, "Колонки-которой-нет", "u1") is None


class TestCmdAppend:
    def test_append_writes_rows(self, make_ws, scl_mapping):
        ws = make_ws()
        result = cmd_append(
            ws,
            scl_mapping,
            [
                {"run_id": "r1", "source_name": "olx_kz", "status": "ok", "listings_found": 5},
                {"run_id": "r1", "source_name": "kaspi", "status": "error", "listings_found": 0},
            ],
        )
        assert result == {"appended": 2}
        records = cmd_read(ws, scl_mapping)
        assert len(records) == 2
        assert records[0]["run_id"] == "r1"
        assert records[0]["listings_found"] == 5
        assert records[1]["status"] == "error"

    def test_append_does_not_dedup(self, make_ws, scl_mapping):
        ws = make_ws()
        cmd_append(ws, scl_mapping, [{"run_id": "r1"}])
        cmd_append(ws, scl_mapping, [{"run_id": "r1"}])
        assert len(cmd_read(ws, scl_mapping)) == 2  # append никогда не дедуплицирует


class TestCmdUpsert:
    def test_insert_sets_first_seen_and_last_checked(self, make_ws, deals_mapping):
        ws = make_ws()
        result = cmd_upsert(
            ws,
            deals_mapping,
            [{"listing_url": "u1", "price_kzt": 1_500_000, "title": "MBP 14"}],
            key="listing_url",
        )
        assert result == {"inserted": 1, "updated": 0}
        rows = cmd_read(ws, deals_mapping)
        assert len(rows) == 1
        assert rows[0]["first_seen_at_almaty"]  # проставлено
        assert rows[0]["last_checked_at"]
        assert rows[0]["price_kzt"] == 1_500_000

    def test_insert_computes_freshness(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(ws, deals_mapping, [{"listing_url": "u1"}], key="listing_url")
        rows = cmd_read(ws, deals_mapping)
        # только что вставлено → почти ноль минут/часов с первой фиксации
        assert int(rows[0]["minutes_since_first_seen"]) in (0, 1)

    def test_first_seen_immutable_across_upserts(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(
            ws, deals_mapping, [{"listing_url": "u1", "price_kzt": 1_500_000}], "listing_url"
        )
        original_fs = cmd_read(ws, deals_mapping)[0]["first_seen_at_almaty"]

        # Второй upsert пытается подсунуть другой first_seen и новую цену.
        result = cmd_upsert(
            ws,
            deals_mapping,
            [
                {
                    "listing_url": "u1",
                    "price_kzt": 1_300_000,
                    "first_seen_at_almaty": "2000-01-01 00:00:00",
                }
            ],
            key="listing_url",
        )
        assert result == {"inserted": 0, "updated": 1}
        rows = cmd_read(ws, deals_mapping)
        assert len(rows) == 1  # дедуп: одна строка, не две
        assert rows[0]["first_seen_at_almaty"] == original_fs  # immutable
        assert rows[0]["first_seen_at_almaty"] != "2000-01-01 00:00:00"
        assert rows[0]["price_kzt"] == 1_300_000  # цена обновилась

    def test_dedup_within_single_call(self, make_ws, deals_mapping):
        ws = make_ws()
        result = cmd_upsert(
            ws,
            deals_mapping,
            [
                {"listing_url": "u1", "price_kzt": 1},
                {"listing_url": "u1", "price_kzt": 2},  # тот же URL в одном прогоне
            ],
            key="listing_url",
        )
        assert result == {"inserted": 1, "updated": 1}
        rows = cmd_read(ws, deals_mapping)
        assert len(rows) == 1
        assert rows[0]["price_kzt"] == 2

    def test_rows_without_key_are_skipped(self, make_ws, deals_mapping):
        ws = make_ws()
        result = cmd_upsert(
            ws,
            deals_mapping,
            [{"price_kzt": 1}, {"listing_url": "", "price_kzt": 2}],
            key="listing_url",
        )
        assert result == {"inserted": 0, "updated": 0}
        assert cmd_read(ws, deals_mapping) == []

    def test_key_not_in_mapping_raises(self, make_ws, deals_mapping):
        ws = make_ws()
        with pytest.raises(ValueError, match="not in column mapping"):
            cmd_upsert(ws, deals_mapping, [{"listing_url": "u1"}], key="nonexistent_key")


class TestCmdMarkUnavailable:
    def test_marks_only_targeted_rows(self, make_ws, deals_mapping):
        ws = make_ws()
        cmd_upsert(
            ws, deals_mapping, [{"listing_url": "u1"}, {"listing_url": "u2"}], key="listing_url"
        )
        result = cmd_mark_unavailable(ws, deals_mapping, [{"listing_url": "u1"}], key="listing_url")
        assert result == {"marked_unavailable": 1}
        by_url = {r["listing_url"]: r for r in cmd_read(ws, deals_mapping)}
        assert by_url["u1"]["availability_status"] == "недоступно"
        assert by_url["u2"]["availability_status"] in ("", None)  # не тронут

    def test_raises_without_availability_column(self, make_ws, scl_mapping):
        ws = make_ws()
        with pytest.raises(ValueError, match="availability_status"):
            cmd_mark_unavailable(ws, scl_mapping, [{"run_id": "r1"}], key="run_id")


class TestCmdRead:
    def test_empty_sheet_returns_empty_list(self, make_ws, deals_mapping):
        assert cmd_read(make_ws(), deals_mapping) == []

    def test_roundtrip_russian_to_english_keys(self, make_ws, scl_mapping):
        ws = make_ws()
        cmd_append(ws, scl_mapping, [{"run_id": "r9", "source_name": "olx_kz"}])
        records = cmd_read(ws, scl_mapping)
        # ключи возвращаются английскими, значения — исходными
        assert records[0]["run_id"] == "r9"
        assert records[0]["source_name"] == "olx_kz"
