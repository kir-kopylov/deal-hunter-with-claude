#!/usr/bin/env python3
"""Калькулятor landed cost для международных refurb-предложений → KZT.

Раньше формула жила только копией внутри tests/test_landed_cost.py — тесты
проверяли копию, а не рабочий код. Теперь это единственный источник правды;
тест импортирует calc_landed_cost отсюда.

Использование (CLI):
    python3 landed_cost_calc.py --price 1899 --currency USD \
        --source apple_refurb_us --screen 14
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(Path.home() / ".claude")))
LANDED_COST_YAML = DEAL_HUNTER_HOME / "data" / "landed_cost_table.yaml"


def load_landed_cost_table() -> dict:
    """Прочитать data/landed_cost_table.yaml."""
    with LANDED_COST_YAML.open() as f:
        return yaml.safe_load(f)


def calc_landed_cost(
    item_price: float,
    item_currency: str,
    source: str,
    screen_size: str,
    cfg: dict,
) -> dict:
    """Посчитать полную стоимость доставки товара до KZT.

    Возвращает разбивку: item / shipping / customs / overhead / risk / total (в KZT).
    Бросает KeyError, если валюта/источник/посредник неизвестны.
    """
    fx = cfg["fx_rates_to_kzt"]
    customs = cfg["customs_kz"]
    forwarders = cfg["forwarders"]
    fwd_name = cfg["default_forwarder_by_source"][source]
    fwd = forwarders[fwd_name]
    overhead = cfg["overhead_percent"] / 100.0
    risk = cfg["risk_premium_percent"] / 100.0

    # Доставка посредником: тариф либо за фунт (USD), либо за кг (GBP).
    if "per_lb_usd" in fwd:
        weight = (
            fwd["estimated_weight_lb_macbook_14"]
            if "14" in screen_size
            else fwd["estimated_weight_lb_macbook_16"]
        )
        shipping_usd = fwd["base_fee_usd"] + weight * fwd["per_lb_usd"]
    elif "per_kg_gbp" in fwd:
        weight = (
            fwd["estimated_weight_kg_macbook_14"]
            if "14" in screen_size
            else fwd["estimated_weight_kg_macbook_16"]
        )
        shipping_gbp = fwd["base_fee_gbp"] + weight * fwd["per_kg_gbp"]
        shipping_usd = shipping_gbp * fx["GBP"] / fx["USD"]
    else:
        shipping_usd = 0

    # Таможня (декларируемая стоимость = только товар).
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


def main() -> int:
    p = argparse.ArgumentParser(description="Landed cost calculator (→ KZT)")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--currency", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--screen", default="14", help='Диагональ: "14" или "16"')
    args = p.parse_args()

    cfg = load_landed_cost_table()
    result = calc_landed_cost(args.price, args.currency, args.source, args.screen, cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
