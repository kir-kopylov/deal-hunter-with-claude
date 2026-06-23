"""Tier 1.2 — Parser tests в approval-стиле.

Сравнивает output парсеров с .approved.json. При расхождении — показывает diff и
просит запустить scripts/approve.sh для одобрения изменения.

Использование:
    pytest tests/test_parsers.py                     # обычный прогон
    bash scripts/approve.sh olx_kz/normal            # одобрить изменение фикстуры

Парсеры — чистые функции parsers.parse_html (BeautifulSoup, без браузера); те же
функции использует fetch_kz.py в проде, поэтому approval-фикстуры пиннят реальную
логику разбора DOM, а не каркас.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from parsers import parse_html

pytestmark = pytest.mark.unit


FIXTURES = (
    Path(os.environ.get("DEAL_HUNTER_HOME", str(Path.home() / ".claude"))) / "tests" / "fixtures"
)


def _list_fixtures() -> list[tuple[str, Path]]:
    """Find all .html fixtures grouped by source."""
    out = []
    if not FIXTURES.exists():
        return out
    for source_dir in FIXTURES.iterdir():
        if not source_dir.is_dir():
            continue
        for html_file in source_dir.glob("*.html"):
            out.append((f"{source_dir.name}/{html_file.stem}", html_file))
    return out


def parse_html_to_listings(source: str, html: str) -> dict:
    """HTML→listings через рабочий парсер parsers.parse_html (без браузера)."""
    return {"source": source, "listings": parse_html(source, html)}


@pytest.mark.parametrize(
    "fixture_id,html_path", _list_fixtures(), ids=lambda x: x if isinstance(x, str) else ""
)
def test_parser_matches_approved(fixture_id: str, html_path: Path):
    """Compare parser output to last approved version."""
    source, _ = fixture_id.split("/", 1)
    html = html_path.read_text()
    received = parse_html_to_listings(source, html)

    received_path = html_path.with_suffix(".received.json")
    approved_path = html_path.with_suffix(".approved.json")

    received_path.write_text(json.dumps(received, ensure_ascii=False, indent=2, sort_keys=True))

    if not approved_path.exists():
        pytest.fail(
            f"No approved.json for {fixture_id}. "
            f"Review {received_path} and copy to {approved_path} if correct, "
            f"or run: bash $DEAL_HUNTER_HOME/scripts/approve.sh {fixture_id}"
        )

    expected = json.loads(approved_path.read_text())
    if received != expected:
        pytest.fail(
            f"Parser output for {fixture_id} differs from approved.\n"
            f"Diff: see {received_path} vs {approved_path}\n"
            f"If change is intentional: bash $DEAL_HUNTER_HOME/scripts/approve.sh {fixture_id}"
        )


def test_at_least_one_fixture_per_critical_source():
    """Reminder: each source MUST have at least 1 fixture for parser to be tested."""
    critical = ["olx_kz", "kaspi_objavleniya"]
    fixtures = _list_fixtures()
    sources_with_fixtures = {fid.split("/")[0] for fid, _ in fixtures}
    missing = [s for s in critical if s not in sources_with_fixtures]
    if missing:
        pytest.skip(
            f"No fixtures yet for: {missing}. "
            f"Save real HTML to $DEAL_HUNTER_HOME/tests/fixtures/<source>/<scenario>.html "
            f"and run pytest again to bootstrap approved.json."
        )


class TestParserEdgeCases:
    def test_empty_html_returns_empty(self):
        assert parse_html("olx_kz", "<html></html>") == []
        assert parse_html("kaspi_objavleniya", "") == []

    def test_unknown_source_returns_empty(self):
        assert parse_html("totally_unknown", "<div data-cy='l-card'><a href='/x'></a></div>") == []

    def test_olx_card_without_link_is_dropped(self):
        html = '<div data-cy="l-card"><h6>Без ссылки</h6></div>'
        assert parse_html("olx_kz", html) == []

    def test_kaspi_card_without_link_is_dropped(self):
        html = "<div data-card><div data-card-name>Без ссылки</div></div>"
        assert parse_html("kaspi_objavleniya", html) == []

    def test_olx_relative_href_absolutized_against_origin(self):
        # location.origin-семантика: путь base_url игнорируется, берётся scheme+host.
        html = '<div data-cy="l-card"><a href="/d/x-1.html">t</a></div>'
        out = parse_html("olx_kz", html, base_url="https://www.olx.kz/list/q-macbook")
        assert out[0]["url"] == "https://www.olx.kz/d/x-1.html"

    def test_kaspi_matches_via_data_card_attributes(self):
        html = (
            '<div data-card><a href="/shop/p/item-1/">x</a>'
            "<div data-card-name>Имя</div><span data-card-price>10 ₸</span></div>"
        )
        out = parse_html("kaspi_objavleniya", html)
        assert len(out) == 1
        assert out[0]["title"] == "Имя"
        assert out[0]["price_text"] == "10 ₸"
        assert out[0]["url"].endswith("/shop/p/item-1/")

    def test_missing_price_yields_none_not_crash(self):
        html = '<div data-cy="l-card"><a href="/d/x-1.html">t</a><h6>Title</h6></div>'
        out = parse_html("olx_kz", html)
        assert out[0]["price_text"] is None
        assert out[0]["title"] == "Title"
