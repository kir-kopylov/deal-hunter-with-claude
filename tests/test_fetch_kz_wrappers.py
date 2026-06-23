"""P2 — тонкие обёртки fetch_kz.parse_*_listings(page).

Проверяем, что обёртки корректно делегируют чистым парсерам, не поднимая
браузер: подсовываем FakePage с .content()/.url.
"""

from __future__ import annotations

import pytest
from fetch_kz import parse_kaspi_listings, parse_olx_listings

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
