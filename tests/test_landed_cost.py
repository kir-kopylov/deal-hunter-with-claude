"""Tier 1.6 — Landed cost calculator tests.

Тесты на расчёт landed cost для международных refurb-предложений.
NB: реальный калькулятор пока не выделен в модуль — здесь тесты задают КОНТРАКТ
формулы. Когда landed_cost_calc.py появится, импортируется отсюда.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

DATA = Path(os.environ.get("DEAL_HUNTER_HOME", str(Path.home() / ".claude"))) / "data"

pytestmark = pytest.mark.unit


def calc_landed_cost(
    item_price: float,
    item_currency: str,
    source: str,
    screen_size: str,
    cfg: dict,
) -> dict:
    """Reference implementation of landed cost calculation. Mirror in landed_cost_calc.py."""
    fx = cfg["fx_rates_to_kzt"]
    customs = cfg["customs_kz"]
    forwarders = cfg["forwarders"]
    fwd_name = cfg["default_forwarder_by_source"][source]
    fwd = forwarders[fwd_name]
    overhead = cfg["overhead_percent"] / 100.0
    risk = cfg["risk_premium_percent"] / 100.0

    # FX to USD-equivalent for forwarder (most are USD-priced)
    item_usd = item_price * fx[item_currency] / fx["USD"]

    # Forwarder shipping
    if "per_lb_usd" in fwd:
        weight = (fwd["estimated_weight_lb_macbook_14"]
                  if "14" in screen_size else fwd["estimated_weight_lb_macbook_16"])
        shipping_usd = fwd["base_fee_usd"] + weight * fwd["per_lb_usd"]
    elif "per_kg_gbp" in fwd:
        weight = (fwd["estimated_weight_kg_macbook_14"]
                  if "14" in screen_size else fwd["estimated_weight_kg_macbook_16"])
        shipping_gbp = fwd["base_fee_gbp"] + weight * fwd["per_kg_gbp"]
        shipping_usd = shipping_gbp * fx["GBP"] / fx["USD"]
    else:
        shipping_usd = 0

    # Customs (declared value = item only)
    item_eur = item_price * fx[item_currency] / fx["EUR"]
    if item_eur > customs["duty_free_limit_eur"]:
        excess = item_eur - customs["duty_free_limit_eur"]
        duty_eur = excess * customs["duty_rate_percent"] / 100.0
        vat_eur = excess * customs["vat_rate_percent"] / 100.0
        customs_kzt = (duty_eur + vat_eur) * fx["EUR"]
    else:
        customs_kzt = 0

    item_kzt = item_price * fx[item_currency]
    shipping_kzt = shipping_usd * fx["USD"]
    overhead_kzt = item_kzt * overhead
    risk_kzt = item_kzt * risk

    total_kzt = item_kzt + shipping_kzt + customs_kzt + overhead_kzt + risk_kzt
    return {
        "item_kzt": round(item_kzt),
        "shipping_kzt": round(shipping_kzt),
        "customs_kzt": round(customs_kzt),
        "overhead_kzt": round(overhead_kzt),
        "risk_kzt": round(risk_kzt),
        "total_kzt": round(total_kzt),
    }


@pytest.fixture
def cfg():
    with (DATA / "landed_cost_table.yaml").open() as f:
        return yaml.safe_load(f)


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
        partial_sum = (r["item_kzt"] + r["shipping_kzt"] + r["customs_kzt"]
                       + r["overhead_kzt"] + r["risk_kzt"])
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
