"""Tier 1.4 — Day-in-the-life e2e симуляция.

Прогоняет несколько последовательных запусков с in-memory Sheet (FakeWorksheet),
проверяя межзапусковую логику уровня sheets_write: дедуп, first_seen preservation,
обновление цены in-place, пометку пропавших как unavailable (без удаления).

Инварианты, которые принадлежат агенту/мастер-промпту (Price_History-диффы,
cross-source dedup, дедуп Pending_Help_Queue), помечены как scoped skip — их
правильнее проверять на integration-уровне, а не в записи в Sheet.
"""

from __future__ import annotations

import pytest
from sheets_write import cmd_mark_unavailable, cmd_read, cmd_upsert, load_column_mapping

pytestmark = pytest.mark.unit


@pytest.fixture
def deals():
    return load_column_mapping("Deals")


class TestDayInTheLife:
    def test_invariant_dedup_within_run(self, make_ws, deals):
        """Один и тот же listing_url дважды в одном run → одна строка, не две."""
        ws = make_ws()
        cmd_upsert(
            ws,
            deals,
            [
                {"listing_url": "https://olx.kz/a/1", "price_kzt": 100},
                {"listing_url": "https://olx.kz/a/1", "price_kzt": 100},
            ],
            key="listing_url",
        )
        assert len(cmd_read(ws, deals)) == 1

    def test_invariant_first_seen_preserved_across_runs(self, make_ws, deals):
        """Run #1 вставляет listing с first_seen. Run #2 встречает тот же URL —
        first_seen остаётся прежним (sheets_write игнорирует входной first_seen)."""
        ws = make_ws()
        cmd_upsert(ws, deals, [{"listing_url": "u1", "price_kzt": 1_500_000}], key="listing_url")
        first_seen_run1 = cmd_read(ws, deals)[0]["first_seen_at_almaty"]

        # Run #2: тот же URL, агент по ошибке прислал бы другой first_seen.
        cmd_upsert(
            ws,
            deals,
            [{"listing_url": "u1", "first_seen_at_almaty": "1999-01-01 00:00:00"}],
            key="listing_url",
        )
        assert cmd_read(ws, deals)[0]["first_seen_at_almaty"] == first_seen_run1

    def test_invariant_price_updates_in_place_across_runs(self, make_ws, deals):
        """Run #1: цена 1_500_000. Run #2: 1_300_000. Строка одна, цена обновлена.
        (Запись диффа в Price_History — задача агента, см. skip ниже.)"""
        ws = make_ws()
        cmd_upsert(ws, deals, [{"listing_url": "u1", "price_kzt": 1_500_000}], key="listing_url")
        cmd_upsert(ws, deals, [{"listing_url": "u1", "price_kzt": 1_300_000}], key="listing_url")
        rows = cmd_read(ws, deals)
        assert len(rows) == 1
        assert rows[0]["price_kzt"] == 1_300_000

    def test_invariant_pruned_listings_marked_unavailable(self, make_ws, deals):
        """Run #1: 5 listings. Run #2: 3 в выдаче, 2 пропали → 2 помечены
        'недоступно', НЕ удалены (всего по-прежнему 5 строк)."""
        ws = make_ws()
        urls = [f"u{i}" for i in range(1, 6)]
        cmd_upsert(
            ws, deals, [{"listing_url": u, "price_kzt": 100} for u in urls], key="listing_url"
        )

        # Run #2: вернулись u1..u3, пропали u4,u5.
        cmd_upsert(ws, deals, [{"listing_url": u} for u in urls[:3]], key="listing_url")
        cmd_mark_unavailable(ws, deals, [{"listing_url": u} for u in urls[3:]], key="listing_url")

        by_url = {r["listing_url"]: r for r in cmd_read(ws, deals)}
        assert len(by_url) == 5  # ничего не удалено
        assert by_url["u4"]["availability_status"] == "недоступно"
        assert by_url["u5"]["availability_status"] == "недоступно"
        assert by_url["u1"]["availability_status"] in ("", None)

    def test_full_day_three_runs(self, make_ws, deals):
        """Связный сценарий дня: 3 запуска подряд на одном Sheet."""
        ws = make_ws()
        # 09:00 — нашли 4 объявления.
        cmd_upsert(
            ws,
            deals,
            [{"listing_url": f"u{i}", "price_kzt": 1_000_000 + i} for i in range(4)],
            key="listing_url",
        )
        fs = {r["listing_url"]: r["first_seen_at_almaty"] for r in cmd_read(ws, deals)}

        # 14:00 — u0 подешевел, u3 пропал.
        cmd_upsert(ws, deals, [{"listing_url": "u0", "price_kzt": 900_000}], key="listing_url")
        cmd_mark_unavailable(ws, deals, [{"listing_url": "u3"}], key="listing_url")

        # 20:00 — u3 вернулся в выдачу (снова upsert).
        cmd_upsert(ws, deals, [{"listing_url": "u3", "price_kzt": 1_003}], key="listing_url")

        rows = {r["listing_url"]: r for r in cmd_read(ws, deals)}
        assert len(rows) == 4  # дедуп держится весь день
        assert rows["u0"]["price_kzt"] == 900_000
        # first_seen у всех неизменны с 09:00
        for url, original in fs.items():
            assert rows[url]["first_seen_at_almaty"] == original

    # --- Инварианты уровня агента/промпта (не sheets_write) ---

    def test_invariant_price_history_diff_is_agent_level(self, make_ws):
        """Запись диффа цены в Price_History считает агент/мастер-промпт, не
        sheets_write — проверяется на integration-уровне."""
        pytest.skip("Price_History diff — orchestration layer, не sheets_write")

    def test_invariant_cross_source_dedup(self, make_ws):
        """A1 (OLX) и A2 (Kaspi Shop) видят один и тот же телефон-продавца с
        одинаковыми model+ram+ssd ±5% по цене → один лот. Это Tier 2 (агент)."""
        pytest.skip("cross-source dedup — Tier 2, логика агента, не sheets_write")

    def test_invariant_help_queue_dedup(self, make_ws):
        """Дедуп Pending_Help_Queue по target_url+query+24ч — логика агента при
        формировании задач, не примитив записи sheets_write."""
        pytest.skip("help-queue dedup — orchestration layer, не sheets_write")
