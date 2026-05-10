#!/usr/bin/env python3
"""Playwright-обёртка для KZ маркетплейсов с anti-bot (OLX.kz, Kaspi).

Использование:
    python3 fetch_kz.py "<url>" [--source olx_kz|kaspi_objavleniya] [--timeout 30]

Output (stdout, JSON):
- Успех: {"status":"ok","url":"...","listings":[{...}, ...]}
- Блокировка: {"status":"needs_human","reason":"cf_challenge|empty_dom|timeout","url":"...","screenshot":"..."}

Никогда не падает с exception — все ошибки маппятся в needs_human-ответ
(агент превратит это в Pending_Help_Queue + TG алерт).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(Path.home() / ".claude")))
SCREENSHOT_DIR = DEAL_HUNTER_HOME / "logs" / "fetch_kz_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def detect_block_reason(html: str, title: str, url: str) -> str | None:
    """Heuristics for detecting anti-bot blocks. Returns reason str or None if page looks ok."""
    lower = html.lower()
    if "cf-challenge" in lower or "checking your browser" in lower or "cloudflare" in lower and "challenge" in lower:
        return "cf_challenge"
    if "captcha" in lower or "вы не робот" in lower or "i'm not a robot" in lower:
        return "captcha"
    if "доступ запрещён" in lower or "access denied" in lower or "403 forbidden" in lower:
        return "access_denied"
    if "необходимо войти" in lower or "please log in" in lower:
        return "login_required"
    # Heuristic: if page is suspiciously small AND URL is a search results page
    if "/search" in url or "/q-" in url:
        if len(html) < 5000:
            return "empty_dom"
    return None


def parse_olx_listings(page) -> list[dict]:
    """Extract listing cards from olx.kz search results.
    NOTE: this is a placeholder selector — DOM may need adjustment after first real run.
    Approval-style fixture tests should pin this down."""
    return page.evaluate("""
        () => {
            const cards = document.querySelectorAll('[data-cy="l-card"], div.css-1apmciz, div.css-19ucd76');
            return Array.from(cards).map(c => {
                const linkEl = c.querySelector('a');
                const titleEl = c.querySelector('h6, h4, [data-cy="ad-card-title"]');
                const priceEl = c.querySelector('[data-testid="ad-price"], p[data-testid="ad-price"]');
                const locEl = c.querySelector('[data-testid="location-date"]');
                return {
                    url: linkEl ? new URL(linkEl.getAttribute('href'), location.origin).href : null,
                    title: titleEl ? titleEl.textContent.trim() : null,
                    price_text: priceEl ? priceEl.textContent.trim() : null,
                    location_date_text: locEl ? locEl.textContent.trim() : null,
                };
            }).filter(x => x.url);
        }
    """)


def parse_kaspi_listings(page) -> list[dict]:
    """Extract listing cards from kaspi.kz search results.
    NOTE: placeholder — needs fixture-based refinement."""
    return page.evaluate("""
        () => {
            const cards = document.querySelectorAll('div.item-card, div[data-card]');
            return Array.from(cards).map(c => {
                const linkEl = c.querySelector('a.item-card__name-link, a[href*="/p/"]');
                const titleEl = c.querySelector('.item-card__name, [data-card-name]');
                const priceEl = c.querySelector('.item-card__prices-price, [data-card-price]');
                return {
                    url: linkEl ? new URL(linkEl.getAttribute('href'), location.origin).href : null,
                    title: titleEl ? titleEl.textContent.trim() : null,
                    price_text: priceEl ? priceEl.textContent.trim() : null,
                };
            }).filter(x => x.url);
        }
    """)


PARSERS = {
    "olx_kz": parse_olx_listings,
    "kaspi_objavleniya": parse_kaspi_listings,
}


def fetch_with_playwright(url: str, source: str | None, timeout_s: int) -> dict:
    """Main fetch function. Catches all exceptions, returns dict with status."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    try:
        from playwright_stealth import stealth_sync
        has_stealth = True
    except ImportError:
        has_stealth = False

    ts = int(time.time())
    screenshot_path = SCREENSHOT_DIR / f"{source or 'unknown'}_{ts}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
                locale="ru-RU",
                timezone_id="Asia/Almaty",
            )
            page = context.new_page()
            if has_stealth:
                stealth_sync(page)

            # Random pre-navigation delay
            time.sleep(random.uniform(1.5, 3.5))

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            except PWTimeout:
                page.screenshot(path=str(screenshot_path))
                browser.close()
                return {
                    "status": "needs_human",
                    "reason": "timeout",
                    "url": url,
                    "screenshot": str(screenshot_path),
                }

            # Wait a bit for JS to settle
            time.sleep(random.uniform(2.0, 4.0))

            html = page.content()
            title = page.title()

            block_reason = detect_block_reason(html, title, url)
            if block_reason:
                page.screenshot(path=str(screenshot_path))
                browser.close()
                return {
                    "status": "needs_human",
                    "reason": block_reason,
                    "url": url,
                    "screenshot": str(screenshot_path),
                    "page_title": title,
                }

            parser = PARSERS.get(source)
            if parser is None:
                # Unknown source — return raw HTML chunk so master prompt can parse via LLM
                browser.close()
                return {
                    "status": "ok",
                    "url": url,
                    "raw_html_excerpt": html[:50000],
                    "note": "no_parser_for_source_returning_raw_html",
                }

            listings = parser(page)
            browser.close()

            # Suspicion check: search-page returning 0 listings is suspicious
            is_search_page = "/search" in url or "/q-" in url
            if is_search_page and len(listings) == 0:
                page.screenshot(path=str(screenshot_path))
                return {
                    "status": "needs_human",
                    "reason": "suspicious_low_yield",
                    "url": url,
                    "screenshot": str(screenshot_path),
                    "page_title": title,
                }

            return {
                "status": "ok",
                "url": url,
                "listings_count": len(listings),
                "listings": listings,
            }

    except ImportError as e:
        return {
            "status": "needs_human",
            "reason": "playwright_not_installed",
            "url": url,
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "needs_human",
            "reason": f"unexpected_error: {type(e).__name__}",
            "url": url,
            "error": str(e),
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--source", help="olx_kz | kaspi_objavleniya | ...")
    p.add_argument("--timeout", type=int, default=30)
    args = p.parse_args()

    if not args.source:
        host = urlparse(args.url).hostname or ""
        if "olx.kz" in host:
            args.source = "olx_kz"
        elif "kaspi.kz" in host:
            args.source = "kaspi_objavleniya"

    result = fetch_with_playwright(args.url, args.source, args.timeout)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 0  # always exit 0; status is in payload


if __name__ == "__main__":
    sys.exit(main())
