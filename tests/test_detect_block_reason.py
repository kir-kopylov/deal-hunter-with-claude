"""P0 — тесты для fetch_kz.detect_block_reason.

detect_block_reason — защитный шлюз от анти-бот блокировок: по HTML/заголовку/URL
решает, заблокирована ли страница, и какой именно причиной. Это чистая функция
(нет браузера, нет сети), но до сих пор у неё было ноль тестов. Здесь фиксируем
её фактическое поведение, включая неочевидный приоритет операторов or/and.
"""

from __future__ import annotations

import pytest
from fetch_kz import detect_block_reason

pytestmark = pytest.mark.unit


class TestCloudflareChallenge:
    def test_cf_challenge_marker(self):
        html = '<html><body><div class="cf-challenge">...</div></body></html>'
        assert detect_block_reason(html, "Just a moment", "https://olx.kz/") == "cf_challenge"

    def test_checking_your_browser_phrase(self):
        html = "<h1>Checking your browser before accessing olx.kz</h1>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "cf_challenge"

    def test_cloudflare_plus_challenge(self):
        html = "<p>Powered by Cloudflare</p><p>Please complete the challenge</p>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "cf_challenge"

    def test_cloudflare_alone_is_not_block(self):
        # Тонкость приоритета: `A or B or C and D` == `A or B or (C and D)`,
        # поэтому одного слова "cloudflare" без "challenge" НЕ хватает.
        # Фиксируем именно текущее поведение.
        html = "<p>This site is protected by Cloudflare CDN.</p>"
        assert detect_block_reason(html, "", "https://olx.kz/listing/1") is None


class TestCaptcha:
    @pytest.mark.parametrize(
        "marker",
        ["please solve the captcha", "вы не робот", "i'm not a robot"],
    )
    def test_captcha_markers(self, marker):
        html = f"<html><body>{marker}</body></html>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "captcha"


class TestAccessDenied:
    @pytest.mark.parametrize(
        "marker",
        ["доступ запрещён", "Access Denied", "403 Forbidden"],
    )
    def test_access_denied_markers(self, marker):
        html = f"<html><body>{marker}</body></html>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "access_denied"


class TestLoginRequired:
    @pytest.mark.parametrize(
        "marker",
        ["необходимо войти", "Please log in to continue"],
    )
    def test_login_required_markers(self, marker):
        html = f"<html><body>{marker}</body></html>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "login_required"


class TestEmptyDom:
    def test_small_search_page_is_empty_dom(self):
        html = "<html><body>пусто</body></html>"  # < 5000 байт
        assert detect_block_reason(html, "", "https://olx.kz/list/q-macbook") == "empty_dom"

    def test_small_q_dash_page_is_empty_dom(self):
        html = "<html><body>x</body></html>"
        assert detect_block_reason(html, "", "https://olx.kz/d/q-macbook-pro/") == "empty_dom"

    def test_large_search_page_is_ok(self):
        html = "<html><body>" + ("<div>card</div>" * 1000) + "</body></html>"
        assert len(html) >= 5000
        assert detect_block_reason(html, "", "https://olx.kz/list/q-macbook") is None

    def test_small_non_search_page_is_ok(self):
        # Маленькая страница НЕ на /search и НЕ /q- не считается empty_dom.
        html = "<html><body>тонкая карточка товара</body></html>"
        assert detect_block_reason(html, "", "https://olx.kz/obyavlenie/123") is None

    def test_search_keyword_path_triggers(self):
        html = "<html></html>"
        assert (
            detect_block_reason(html, "", "https://kaspi.kz/shop/search?q=macbook") == "empty_dom"
        )


class TestCleanPage:
    def test_normal_listing_page_returns_none(self):
        html = "<html><body>" + ("<div class='l-card'>MacBook Pro 14</div>" * 50) + "</body></html>"
        assert detect_block_reason(html, "MacBook — OLX.kz", "https://olx.kz/list/") is None


class TestPriorityAndCaseInsensitivity:
    def test_case_insensitive(self):
        html = "<H1>CHECKING YOUR BROWSER</H1>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "cf_challenge"

    def test_cf_wins_over_captcha_when_both_present(self):
        # cf_challenge проверяется раньше captcha — фиксируем порядок приоритета.
        html = "<p>Checking your browser</p><p>please complete the captcha</p>"
        assert detect_block_reason(html, "", "https://olx.kz/") == "cf_challenge"

    def test_block_reason_wins_over_empty_dom(self):
        # Маленькая /search-страница, но с captcha → отдаём captcha, не empty_dom,
        # потому что captcha проверяется раньше эвристики размера.
        html = "<p>вы не робот</p>"
        assert len(html) < 5000
        assert detect_block_reason(html, "", "https://olx.kz/list/q-macbook") == "captcha"
