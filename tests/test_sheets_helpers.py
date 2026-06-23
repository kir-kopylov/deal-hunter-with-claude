"""P0 — тесты для чистых помощников sheets_write.

Покрываем функции, которые не требуют ни сети, ни gspread:
- english_to_russian_row: маппинг английских ключей в строку для Sheet
- load_column_mapping: чтение data/sheet_columns_ru.yaml + use_mapping_from
- now_almaty_iso: формат метки времени
"""

from __future__ import annotations

import re

import pytest
from sheets_write import (
    english_to_russian_row,
    load_column_mapping,
    now_almaty_iso,
)

pytestmark = pytest.mark.unit


class TestNowAlmatyIso:
    def test_format(self):
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", now_almaty_iso())


class TestLoadColumnMapping:
    def test_loads_deals_mapping(self):
        mapping = load_column_mapping("Deals")
        assert mapping["listing_url"] == "Ссылка на объявление"
        assert mapping["first_seen_at_almaty"] == "Впервые замечено (Алматы)"

    def test_hot_deals_resolves_via_use_mapping_from(self):
        # Hot_Deals: { use_mapping_from: Deals } → должен вернуть маппинг Deals.
        hot = load_column_mapping("Hot_Deals")
        deals = load_column_mapping("Deals")
        assert hot == deals
        assert "use_mapping_from" not in hot

    def test_unknown_tab_raises(self):
        with pytest.raises(ValueError, match="not in"):
            load_column_mapping("NoSuchTab")


class TestEnglishToRussianRow:
    def setup_method(self):
        self.mapping = {
            "listing_url": "Ссылка",
            "price_kzt": "Цена",
            "main_pros": "Плюсы",
        }
        self.headers = ["Ссылка", "Цена", "Плюсы"]

    def test_basic_mapping_in_header_order(self):
        row = {"price_kzt": 100, "listing_url": "http://x"}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result == ["http://x", 100, ""]

    def test_unknown_keys_dropped_silently(self):
        row = {"listing_url": "http://x", "totally_unknown": "ignored"}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result == ["http://x", "", ""]
        assert "ignored" not in result

    def test_none_becomes_empty_string(self):
        row = {"listing_url": None, "price_kzt": 0}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result[0] == ""  # None → ""
        assert result[1] == 0  # 0 сохраняется как есть, не превращается в ""

    def test_list_value_serialized_to_json(self):
        row = {"main_pros": ["лёгкий", "тихий"]}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result[2] == '["лёгкий", "тихий"]'  # ensure_ascii=False → кириллица читаемая

    def test_dict_value_serialized_to_json(self):
        row = {"main_pros": {"battery": "ok"}}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result[2] == '{"battery": "ok"}'

    def test_missing_header_filled_with_empty(self):
        row = {"listing_url": "http://x"}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result == ["http://x", "", ""]

    def test_header_order_independent_of_dict_order(self):
        # Порядок ключей во входном dict не влияет — порядок задаётся headers.
        row = {"main_pros": "p", "price_kzt": 5, "listing_url": "u"}
        result = english_to_russian_row(row, self.mapping, self.headers)
        assert result == ["u", 5, "p"]
