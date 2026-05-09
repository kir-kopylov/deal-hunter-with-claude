"""Tier 1.2 — Parser tests в approval-стиле.

Сравнивает output парсеров с .approved.json. При расхождении — показывает diff и
просит запустить scripts/approve.sh для одобрения изменения.

Использование:
    pytest tests/test_parsers.py                     # обычный прогон
    bash scripts/approve.sh olx_kz/normal            # одобрить изменение фикстуры

NB: реальные парсеры сейчас в fetch_kz.py и используют live browser. Чтобы тесты
работали без браузера, нужно вынести логику парсинга DOM в отдельные функции,
которые принимают HTML строкой. Это TODO; пока тесты — каркас.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


FIXTURES = Path.home() / ".claude" / "tests" / "fixtures"


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
    """Pure-function HTML→listings parser. TODO: extract from fetch_kz.py.
    Currently a stub that returns empty for any input."""
    # When implemented, this will use BeautifulSoup or similar (no real browser).
    return {"source": source, "listings": [], "_stub": True}


@pytest.mark.parametrize("fixture_id,html_path", _list_fixtures(), ids=lambda x: x if isinstance(x, str) else "")
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
            f"or run: bash ~/.claude/scripts/approve.sh {fixture_id}"
        )

    expected = json.loads(approved_path.read_text())
    if received != expected:
        pytest.fail(
            f"Parser output for {fixture_id} differs from approved.\n"
            f"Diff: see {received_path} vs {approved_path}\n"
            f"If change is intentional: bash ~/.claude/scripts/approve.sh {fixture_id}"
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
            f"Save real HTML to ~/.claude/tests/fixtures/<source>/<scenario>.html "
            f"and run pytest again to bootstrap approved.json."
        )
