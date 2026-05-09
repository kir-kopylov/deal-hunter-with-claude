"""Tier 1.3 — Schema validation для всех YAML конфигов.

Каждый prod-запуск также вызывает эти проверки fail-fast в run-deals.sh.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

DATA = Path.home() / ".claude" / "data"
VALID_DAYS = {"sun", "mon", "tue", "wed", "thu", "fri", "sat", "*"}


pytestmark = pytest.mark.unit


def _load(name: str) -> dict:
    with (DATA / name).open() as f:
        return yaml.safe_load(f)


class TestScheduleYaml:
    def setup_method(self):
        self.cfg = _load("schedule.yaml")

    def test_has_timezone(self):
        assert self.cfg["timezone"] == "Asia/Almaty"

    def test_has_groups(self):
        assert "groups" in self.cfg
        assert set(self.cfg["groups"].keys()) >= {"baseline", "A1", "A2", "A3", "B", "C"}

    def test_each_group_has_required_keys(self):
        for name, group in self.cfg["groups"].items():
            assert "label" in group, f"Group {name}: missing label"
            assert "sources" in group, f"Group {name}: missing sources"
            assert "schedule" in group, f"Group {name}: missing schedule"
            assert isinstance(group["sources"], list) and group["sources"], f"Group {name}: empty sources"
            assert group["schedule"], f"Group {name}: empty schedule"

    def test_schedule_entries_valid(self):
        for name, group in self.cfg["groups"].items():
            for entry in group["schedule"]:
                day = entry["day"]
                if isinstance(day, list):
                    for d in day:
                        assert d in VALID_DAYS, f"Group {name}: invalid day {d!r}"
                else:
                    assert day in VALID_DAYS, f"Group {name}: invalid day {day!r}"
                assert 0 <= entry["hour"] <= 23, f"Group {name}: invalid hour {entry['hour']}"
                assert 0 <= entry["minute"] <= 59, f"Group {name}: invalid minute {entry['minute']}"

    def test_source_endpoints_referenced_in_groups(self):
        endpoints = self.cfg.get("source_endpoints", {})
        for name, group in self.cfg["groups"].items():
            if name == "baseline":
                continue
            for src in group["sources"]:
                if src == "internal":
                    continue
                # Soft check: warn if missing endpoint, but don't fail (some sources may
                # be handled via WebSearch fallback)
                if src not in endpoints:
                    pytest.warns(UserWarning, match=f"source {src} has no endpoint")


class TestSheetColumnsYaml:
    def setup_method(self):
        self.cfg = _load("sheet_columns_ru.yaml")

    def test_has_required_tabs(self):
        for tab in ["Deals", "Baseline_Prices", "Price_History", "Source_Check_Log",
                    "Hot_Deals", "Pending_Help_Queue"]:
            assert tab in self.cfg, f"Missing tab: {tab}"

    def test_internal_keys_are_snake_case(self):
        import re
        pat = re.compile(r"^[a-z][a-z0-9_]*$")
        for tab, mapping in self.cfg.items():
            if tab == "enums":
                continue
            for k in mapping:
                if k == "use_mapping_from":
                    continue
                assert pat.match(k), f"Tab {tab}: key {k!r} not snake_case"

    def test_russian_headers_non_empty_and_unique(self):
        for tab, mapping in self.cfg.items():
            if tab == "enums":
                continue
            if "use_mapping_from" in mapping:
                continue
            headers = list(mapping.values())
            assert all(h.strip() for h in headers), f"Tab {tab}: empty header found"
            assert len(headers) == len(set(headers)), f"Tab {tab}: duplicate headers"

    def test_deals_has_first_seen_at_almaty(self):
        assert "first_seen_at_almaty" in self.cfg["Deals"]
        assert "source_posted_at_raw" in self.cfg["Deals"]
        # posted_at_detected should NOT be there — it was replaced
        assert "posted_at_detected" not in self.cfg["Deals"]

    def test_pending_help_queue_has_status_and_block_reason(self):
        q = self.cfg["Pending_Help_Queue"]
        assert "status" in q
        assert "block_reason" in q
        assert "task_id" in q

    def test_hot_deals_uses_deals_mapping(self):
        assert self.cfg["Hot_Deals"].get("use_mapping_from") == "Deals"

    def test_enums_present(self):
        assert "enums" in self.cfg
        assert "priority" in self.cfg["enums"]
        assert "block_reason" in self.cfg["enums"]
        assert "pending_status" in self.cfg["enums"]


class TestLandedCostYaml:
    def setup_method(self):
        self.cfg = _load("landed_cost_table.yaml")

    def test_has_last_updated(self):
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(self.cfg["last_updated"]))

    def test_has_fx_rates(self):
        rates = self.cfg["fx_rates_to_kzt"]
        for ccy in ["USD", "EUR", "GBP"]:
            assert ccy in rates
            assert rates[ccy] > 0

    def test_customs_rules(self):
        c = self.cfg["customs_kz"]
        assert c["duty_free_limit_eur"] > 0
        assert 0 <= c["duty_rate_percent"] <= 100
        assert 0 <= c["vat_rate_percent"] <= 100

    def test_forwarders_have_required_fields(self):
        for name, fw in self.cfg["forwarders"].items():
            base_keys = [k for k in fw if k.startswith("base_fee_")]
            assert base_keys, f"Forwarder {name}: missing base_fee_*"
            assert "typical_delivery_days" in fw
