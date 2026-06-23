"""P2 — fetch_kz.fetch_with_playwright branch coverage без реального браузера.

Подменяем playwright.sync_api на фейковый модуль (FakeP/FakeBrowser/FakePage),
чтобы прогнать все ветки fetch_with_playwright: timeout, anti-bot block,
suspicious_low_yield, ok-с-парсером, ok-raw-html (нет парсера), unexpected_error.
Также покрываем main() — авто-детект source по hostname.
"""

from __future__ import annotations

import sys
import types

import fetch_kz
import pytest

pytestmark = pytest.mark.unit


class FakePWTimeout(Exception):
    """Стенд-ин для playwright.sync_api.TimeoutError."""


class FakePage:
    def __init__(self, html="", title="", url="", goto_exc=None, content_exc=None):
        self._html = html
        self._title = title
        self.url = url
        self._goto_exc = goto_exc
        self._content_exc = content_exc
        self.screenshots: list[str] = []

    def goto(self, url, wait_until=None, timeout=None):
        if self._goto_exc is not None:
            raise self._goto_exc

    def content(self):
        if self._content_exc is not None:
            raise self._content_exc
        return self._html

    def title(self):
        return self._title

    def screenshot(self, path=None):
        self.screenshots.append(path)


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


class _Chromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self, **kwargs):
        return self._browser


class _FakeP:
    def __init__(self, browser):
        self.chromium = _Chromium(browser)


class _CM:
    def __init__(self, p):
        self._p = p

    def __enter__(self):
        return self._p

    def __exit__(self, *exc):
        return False


@pytest.fixture
def install_fake_playwright(monkeypatch):
    """Возвращает функцию install(page) -> browser, регистрирующую фейковый playwright."""

    # Никаких реальных задержек и stealth — детерминизм и скорость.
    monkeypatch.setattr(fetch_kz.time, "sleep", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "playwright_stealth", None)

    def install(page: FakePage) -> FakeBrowser:
        browser = FakeBrowser(page)
        fake_mod = types.ModuleType("playwright.sync_api")
        fake_mod.sync_playwright = lambda: _CM(_FakeP(browser))
        fake_mod.TimeoutError = FakePWTimeout
        monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)
        return browser

    return install


# --- большой HTML, чтобы обойти empty_dom-эвристику (len(html) < 5000) на search-страницах
_BIG = "<!--" + "x" * 6000 + "-->"


def test_timeout_branch(install_fake_playwright):
    page = FakePage(url="https://olx.kz/list/q-macbook", goto_exc=FakePWTimeout("nav timeout"))
    browser = install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://olx.kz/list/q-macbook", "olx_kz", 5)
    assert r["status"] == "needs_human"
    assert r["reason"] == "timeout"
    assert page.screenshots  # скриншот сделан
    assert browser.closed


def test_block_reason_branch(install_fake_playwright):
    page = FakePage(
        html="<html><body>Please solve the captcha</body></html>",
        title="blocked",
        url="https://olx.kz/d/obyavlenie/x.html",
    )
    install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://olx.kz/d/obyavlenie/x.html", "olx_kz", 5)
    assert r["status"] == "needs_human"
    assert r["reason"] == "captcha"
    assert r["page_title"] == "blocked"


def test_suspicious_low_yield_branch(install_fake_playwright):
    # search-страница (q-), валидная по размеру, но парсер находит 0 листингов
    page = FakePage(html=_BIG, title="ok", url="https://olx.kz/list/q-macbook")
    install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://olx.kz/list/q-macbook", "olx_kz", 5)
    assert r["status"] == "needs_human"
    assert r["reason"] == "suspicious_low_yield"


def test_ok_with_parser(install_fake_playwright):
    html = _BIG + '<div data-cy="l-card"><a href="/d/x-1.html">t</a><h6>MacBook Pro</h6></div>'
    page = FakePage(html=html, title="ok", url="https://www.olx.kz/list/q-macbook")
    browser = install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://www.olx.kz/list/q-macbook", "olx_kz", 5)
    assert r["status"] == "ok"
    assert r["listings_count"] == 1
    assert r["listings"][0]["url"] == "https://www.olx.kz/d/x-1.html"
    assert browser.closed


def test_ok_raw_html_when_no_parser(install_fake_playwright):
    # source=None → парсера нет → возвращаем raw_html_excerpt (не search-страница)
    page = FakePage(html="<html>some content</html>", title="t", url="https://example.com/p/1")
    install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://example.com/p/1", None, 5)
    assert r["status"] == "ok"
    assert r["note"] == "no_parser_for_source_returning_raw_html"
    assert "raw_html_excerpt" in r


def test_unexpected_error_branch(install_fake_playwright):
    # page.content() бросает RuntimeError → ловится общим except → unexpected_error
    page = FakePage(url="https://olx.kz/d/x.html", content_exc=RuntimeError("boom"))
    install_fake_playwright(page)
    r = fetch_kz.fetch_with_playwright("https://olx.kz/d/x.html", "olx_kz", 5)
    assert r["status"] == "needs_human"
    assert r["reason"] == "unexpected_error: RuntimeError"
    assert r["error"] == "boom"


# --- main(): авто-детект source по hostname --------------------------------------


@pytest.mark.parametrize(
    "url,expected_source",
    [
        ("https://www.olx.kz/list/q-macbook", "olx_kz"),
        ("https://kaspi.kz/shop/search", "kaspi_objavleniya"),
        ("https://example.com/p/1", None),
    ],
)
def test_main_autodetects_source(monkeypatch, capsys, url, expected_source):
    captured = {}

    def fake_fetch(u, source, timeout):
        captured["source"] = source
        return {"status": "ok", "url": u}

    monkeypatch.setattr(fetch_kz, "fetch_with_playwright", fake_fetch)
    monkeypatch.setattr(sys, "argv", ["fetch_kz.py", url])
    rc = fetch_kz.main()
    assert rc == 0
    assert captured["source"] == expected_source
    out = capsys.readouterr().out
    assert '"status": "ok"' in out or '"status":"ok"' in out


def test_main_explicit_source_overrides_autodetect(monkeypatch, capsys):
    captured = {}

    def fake_fetch(u, source, timeout):
        captured["source"] = source
        return {"status": "ok", "url": u}

    monkeypatch.setattr(fetch_kz, "fetch_with_playwright", fake_fetch)
    # hostname олх, но явный --source kaspi_objavleniya должен победить
    monkeypatch.setattr(
        sys, "argv", ["fetch_kz.py", "https://olx.kz/x", "--source", "kaspi_objavleniya"]
    )
    assert fetch_kz.main() == 0
    assert captured["source"] == "kaspi_objavleniya"
