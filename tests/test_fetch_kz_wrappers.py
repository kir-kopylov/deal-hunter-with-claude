"""P2 — тонкие обёртки fetch_kz.parse_*_listings(page).

Проверяем, что обёртки корректно делегируют чистым парсерам, не поднимая
браузер: подсовываем FakePage с .content()/.url.
"""

from __future__ import annotations

import sys

import pytest
from fetch_kz import fetch_with_playwright, parse_kaspi_listings, parse_olx_listings

pytestmark = pytest.mark.unit


class FakePage:
    def __init__(self, html: str, url: str):
        self._html = html
        self.url = url

    def content(self) -> str:
        return self._html


def test_parse_olx_listings_delegates_to_pure_parser():
    page = FakePage(
        '<div data-cy="l-card"><a href="/d/x-1.html">t</a><h6>Title</h6></div>',
        "https://www.olx.kz/list/q-macbook",
    )
    out = parse_olx_listings(page)
    assert len(out) == 1
    assert out[0]["url"] == "https://www.olx.kz/d/x-1.html"
    assert out[0]["title"] == "Title"


def test_parse_kaspi_listings_delegates_to_pure_parser():
    page = FakePage(
        '<div data-card><a href="/shop/p/item-1/">x</a>'
        "<div data-card-name>Имя</div><span data-card-price>10 ₸</span></div>",
        "https://kaspi.kz/shop/search",
    )
    out = parse_kaspi_listings(page)
    assert len(out) == 1
    assert out[0]["url"] == "https://kaspi.kz/shop/p/item-1/"
    assert out[0]["price_text"] == "10 ₸"


def test_missing_dependency_reports_module_name(monkeypatch):
    # Делаем playwright неимпортируемым → fetch не должен падать, а вернуть
    # needs_human с ТОЧНЫМ именем модуля (а не общим 'playwright_not_installed').
    monkeypatch.setitem(sys.modules, "playwright", None)
    result = fetch_with_playwright("https://olx.kz/list/q-macbook", "olx_kz", timeout_s=5)
    assert result["status"] == "needs_human"
    # reason называет отсутствующий модуль (playwright[.sync_api]), не общий ярлык.
    assert result["reason"].startswith("dependency_missing:")
    assert "playwright" in result["reason"]
    assert result["url"] == "https://olx.kz/list/q-macbook"
