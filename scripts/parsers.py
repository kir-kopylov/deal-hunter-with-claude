"""Чистые парсеры HTML→листинги для KZ-маркетплейсов (без браузера).

Раньше разбор DOM жил внутри fetch_kz.py как JS в page.evaluate() — его нельзя
было протестировать без живого браузера. Здесь те же CSS-селекторы реализованы
на BeautifulSoup, принимают HTML строкой и потому покрываются обычными unit-тестами
(approval-стиль в tests/test_parsers.py). fetch_kz.py делегирует разбор сюда.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def _text(el) -> str | None:
    """textContent.trim()-аналог: собрать текст и схлопнуть пробелы. None если пусто."""
    if el is None:
        return None
    txt = " ".join(el.get_text().split())
    return txt or None


def _origin(base_url: str) -> str:
    """scheme://netloc из URL — как location.origin в браузере."""
    p = urlparse(base_url)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return base_url


def _abs_url(el, origin: str) -> str | None:
    if el is None:
        return None
    href = el.get("href")
    if not href:
        return None
    return urljoin(origin + "/", href)


def parse_olx_html(html: str, base_url: str) -> list[dict]:
    """Карточки объявлений из выдачи olx.kz."""
    soup = BeautifulSoup(html, "html.parser")
    origin = _origin(base_url)
    out: list[dict] = []
    for card in soup.select('[data-cy="l-card"], div.css-1apmciz, div.css-19ucd76'):
        link = card.select_one("a")
        url = _abs_url(link, origin)
        if not url:
            continue  # без ссылки карточка бесполезна — пропускаем
        out.append(
            {
                "url": url,
                "title": _text(card.select_one('h6, h4, [data-cy="ad-card-title"]')),
                "price_text": _text(card.select_one('[data-testid="ad-price"]')),
                "location_date_text": _text(card.select_one('[data-testid="location-date"]')),
            }
        )
    return out


def parse_kaspi_html(html: str, base_url: str) -> list[dict]:
    """Карточки объявлений из выдачи kaspi.kz."""
    soup = BeautifulSoup(html, "html.parser")
    origin = _origin(base_url)
    out: list[dict] = []
    for card in soup.select("div.item-card, div[data-card]"):
        link = card.select_one('a.item-card__name-link, a[href*="/p/"]')
        url = _abs_url(link, origin)
        if not url:
            continue
        out.append(
            {
                "url": url,
                "title": _text(card.select_one(".item-card__name, [data-card-name]")),
                "price_text": _text(card.select_one(".item-card__prices-price, [data-card-price]")),
            }
        )
    return out


# Базовые URL по источнику (для построения абсолютных ссылок в тестах/фикстурах).
BASE_URLS = {
    "olx_kz": "https://www.olx.kz",
    "kaspi_objavleniya": "https://kaspi.kz",
}

SOURCE_PARSERS = {
    "olx_kz": parse_olx_html,
    "kaspi_objavleniya": parse_kaspi_html,
}


def parse_html(source: str, html: str, base_url: str | None = None) -> list[dict]:
    """Диспетчер: source → нужный парсер. Неизвестный source → пустой список."""
    fn = SOURCE_PARSERS.get(source)
    if fn is None:
        return []
    return fn(html, base_url or BASE_URLS.get(source, ""))
