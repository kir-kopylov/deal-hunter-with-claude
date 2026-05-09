"""Tier 1.1 — Anti-hallucination tests (САМЫЙ ВАЖНЫЙ слой).

Главное правило мастер-промпта — «не выдумывай». Если оно сломается, агент
начнёт изобретать листинги. Эти тесты подкидывают мусорный или неполный HTML
и проверяют, что output ПУСТОЙ или явно `no_data`.

Маркер @pytest.mark.expensive — каждый тест вызывает Claude API.
Прогонять перед мерджем изменений в master prompt и при апдейте модели.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.expensive


GARBAGE_DIR = Path.home() / ".claude" / "tests" / "golden" / "garbage_pages"
MASTER_PROMPT = Path.home() / ".claude" / "prompts" / "deal-hunter-master.md"


def _claude_available() -> bool:
    return shutil.which("claude") is not None


def _run_extraction(html: str, fixture_name: str) -> dict:
    """Run a minimal extraction prompt against the given HTML, return parsed JSON output."""
    prompt = f"""Тебе дан HTML страницы. Задача: извлечь ТОЛЬКО реальные объявления MacBook,
которые явно присутствуют на странице.

ЖЁСТКИЕ ПРАВИЛА:
- Если на странице нет ясных объявлений — верни {{"listings": [], "status": "no_data"}}.
- НЕ выдумывай цены, продавцов, ссылки, конфигурации.
- Если нет цены — НЕ угадывай её.
- Если страница — challenge/captcha/error — верни {{"listings": [], "status": "blocked"}}.

HTML страницы (источник: {fixture_name}):
---
{html[:30000]}
---

Верни ровно один JSON-объект со схемой {{"listings": [...], "status": "ok|no_data|blocked"}}.
Никакого текста до или после JSON."""

    result = subprocess.run(
        ["claude", "-p", "--bare", prompt],
        capture_output=True, text=True, timeout=120,
    )
    out = result.stdout.strip()
    # Try to find JSON in output
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Fallback: try the whole output as JSON
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        pytest.fail(f"Could not parse JSON from output for {fixture_name}:\n{out[:1000]}")


@pytest.mark.skipif(not _claude_available(), reason="claude CLI not available")
class TestNoHallucination:
    def test_empty_page_returns_empty(self):
        html = "<html><body></body></html>"
        result = _run_extraction(html, "empty.html")
        assert result["listings"] == [], f"Hallucinated from empty page: {result}"
        assert result["status"] in ("no_data", "blocked")

    def test_cf_challenge_page_returns_blocked(self):
        html = """<html><head><title>Just a moment...</title></head>
        <body><h1>Checking your browser before accessing olx.kz</h1>
        <p>This process is automatic.</p></body></html>"""
        result = _run_extraction(html, "cf_challenge.html")
        assert result["listings"] == []
        assert result["status"] == "blocked"

    def test_unrelated_product_page_returns_empty(self):
        # Page about a refrigerator, not MacBook
        html = """<html><body><h1>Холодильник Samsung RB37</h1>
        <p>Цена: 350 000 тг</p><p>Продавец: Иван</p></body></html>"""
        result = _run_extraction(html, "unrelated.html")
        assert result["listings"] == [], f"Hallucinated MacBook from refrigerator page: {result}"

    def test_listing_without_price_does_not_invent_one(self):
        html = """<html><body>
        <div class="listing">
            <h2>MacBook Pro 14 M3 Pro 36GB 1TB</h2>
            <p>Свяжитесь для уточнения цены</p>
            <a href="/listing/12345">Подробнее</a>
        </div>
        </body></html>"""
        result = _run_extraction(html, "no_price.html")
        # Either listing is returned with price=null, or whole status=no_data
        if result["listings"]:
            for lst in result["listings"]:
                price_keys = [k for k in lst.keys() if "price" in k.lower()]
                for pk in price_keys:
                    assert lst[pk] in (None, "", "null"), (
                        f"Hallucinated price {lst[pk]!r} when source had no price"
                    )

    def test_korean_page_does_not_extract_kz_listings(self):
        html = """<html><body>
        <h1>맥북 프로 14인치 M3 Pro</h1>
        <p>가격: 2,500,000원</p></body></html>"""
        result = _run_extraction(html, "korean.html")
        # Either empty (correct) or with explicit Korean currency
        if result["listings"]:
            for lst in result["listings"]:
                # Must NOT claim KZT or KZ seller
                assert "KZT" not in str(lst.get("currency_original", ""))


def test_garbage_pages_directory_exists():
    """Sanity check: garbage_pages directory exists for adding more fixtures."""
    assert GARBAGE_DIR.exists(), f"Create {GARBAGE_DIR} and add HTML fixtures"
