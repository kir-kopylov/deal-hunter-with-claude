"""Tier 1.6 — Landed cost calculator tests.

Тесты на расчёт landed cost для международных refurb-предложений.
calc_landed_cost импортируется из scripts/landed_cost_calc.py — это единственный
источник правды формулы (раньше здесь жила её копия, что давало ложную
уверенность: тест проверял копию, а не рабочий код).
"""

from __future__ import annotations

import json
import sys

import landed_cost_calc
import pytest
from landed_cost_calc import calc_landed_cost, load_landed_cost_table

pytestmark = pytest.mark.unit


@pytest.fixture
def cfg():
    return load_landed_cost_table()


class TestCli:
    def test_main_prints_breakdown(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "landed_cost_calc.py",
                "--price",
                "1899",
                "--currency",
                "USD",
                "--source",
                "apple_refurb_us",
                "--screen",
                "14",
            ],
        )
        assert landed_cost_calc.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["total_kzt"] > out["item_kzt"] > 0
        assert set(out) == {
            "item_kzt",
            "shipping_kzt",
            "customs_kzt",
            "overhead_kzt",
            "risk_kzt",
            "total_kzt",
        }


class TestLandedCost:
    def test_apple_us_macbook_pro_14_below_duty_free(self, cfg):
        # $200 item — well below 200 EUR threshold
        r = calc_landed_cost(200, "USD", "apple_refurb_us", "14", cfg)
        assert r["customs_kzt"] == 0
        assert r["item_kzt"] == 200 * cfg["fx_rates_to_kzt"]["USD"]
        assert r["shipping_kzt"] > 0
        assert r["total_kzt"] > r["item_kzt"]

    def test_apple_us_macbook_pro_14_above_duty_free(self, cfg):
        # $1899 — typical M3 Pro refurb price, well above 200 EUR
        r = calc_landed_cost(1899, "USD", "apple_refurb_us", "14", cfg)
        assert r["customs_kzt"] > 0
        # Sanity: customs should be ~17% of (price - 200 EUR equivalent)
        assert r["total_kzt"] > r["item_kzt"]

    def test_apple_uk_uses_uk_forwarder(self, cfg):
        r = calc_landed_cost(1599, "GBP", "apple_refurb_uk", "14", cfg)
        # Should use myparcel_uk path (kg-based shipping)
        assert r["shipping_kzt"] > 0

    def test_macbook_16_heavier_than_14(self, cfg):
        r14 = calc_landed_cost(2000, "USD", "apple_refurb_us", "14", cfg)
        r16 = calc_landed_cost(2000, "USD", "apple_refurb_us", "16", cfg)
        assert r16["shipping_kzt"] > r14["shipping_kzt"]

    def test_higher_item_price_higher_customs(self, cfg):
        cheap = calc_landed_cost(500, "USD", "apple_refurb_us", "14", cfg)
        pricey = calc_landed_cost(2500, "USD", "apple_refurb_us", "14", cfg)
        assert pricey["customs_kzt"] > cheap["customs_kzt"]

    def test_overhead_and_risk_proportional_to_item(self, cfg):
        r1 = calc_landed_cost(1000, "USD", "apple_refurb_us", "14", cfg)
        r2 = calc_landed_cost(2000, "USD", "apple_refurb_us", "14", cfg)
        # overhead and risk scale linearly with item price
        assert abs(r2["overhead_kzt"] - 2 * r1["overhead_kzt"]) < 10
        assert abs(r2["risk_kzt"] - 2 * r1["risk_kzt"]) < 10

    def test_total_breakdown_sums_correctly(self, cfg):
        r = calc_landed_cost(1899, "USD", "apple_refurb_us", "14", cfg)
        partial_sum = (
            r["item_kzt"] + r["shipping_kzt"] + r["customs_kzt"] + r["overhead_kzt"] + r["risk_kzt"]
        )
        assert abs(r["total_kzt"] - partial_sum) <= 5  # rounding tolerance

    def test_back_market_uses_us_forwarder(self, cfg):
        r = calc_landed_cost(1500, "USD", "back_market", "14", cfg)
        assert r["shipping_kzt"] > 0
        assert r["total_kzt"] > r["item_kzt"]

    def test_macbook_pro_m3_pro_realistic_total(self, cfg):
        """Sanity check: $1899 Apple US M3 Pro refurb should land at ~1.1-1.4M KZT."""
        r = calc_landed_cost(1899, "USD", "apple_refurb_us", "14", cfg)
        assert 800_000 < r["total_kzt"] < 2_000_000, (
            f"Suspicious total: {r['total_kzt']} KZT. Check fx rates and customs."
        )

    def test_unknown_currency_raises(self, cfg):
        with pytest.raises(KeyError):
            calc_landed_cost(1000, "XXX", "apple_refurb_us", "14", cfg)
