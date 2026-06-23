"""P1 — валидация preconditions у shell-энтрипоинтов.

Покрываем дешёвые, но ценные ветки fail-fast: usage/exit-коды и копирование
approve.sh. Полный happy-path run-deals/help-deals не гоняем (требует claude CLI).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, *args, home: Path, stdin: str | None = None):
    env = dict(os.environ)
    env["DEAL_HUNTER_HOME"] = str(home)
    env.pop("PYTHON_VENV", None)  # не активировать venv в тестах
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
    )


# --- approve.sh -----------------------------------------------------------------


def test_approve_usage_error(tmp_path):
    r = _run("approve.sh", home=tmp_path)
    assert r.returncode == 64


def test_approve_missing_received_exits_65(tmp_path):
    r = _run("approve.sh", "olx_kz/normal", home=tmp_path)
    assert r.returncode == 65


def test_approve_copies_received_to_approved(tmp_path):
    fixtures = tmp_path / "tests" / "fixtures" / "olx_kz"
    fixtures.mkdir(parents=True)
    received = fixtures / "normal.received.json"
    received.write_text('{"listings": []}')
    approved = fixtures / "normal.approved.json"

    r = _run("approve.sh", "olx_kz/normal", home=tmp_path)
    assert r.returncode == 0, r.stderr
    assert approved.exists()
    assert approved.read_text() == '{"listings": []}'


# --- run-deals.sh ---------------------------------------------------------------


def test_run_deals_usage_without_group(tmp_path):
    r = _run("run-deals.sh", home=tmp_path)
    assert r.returncode == 64


def test_run_deals_missing_env_file_exits_65(tmp_path):
    r = _run("run-deals.sh", "A1", home=tmp_path)
    assert r.returncode == 65


def test_run_deals_missing_master_prompt_exits_66(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / ".env.deals").write_text("# empty\n")
    r = _run("run-deals.sh", "A1", home=tmp_path)
    assert r.returncode == 66


# --- help-deals.sh --------------------------------------------------------------


def test_help_deals_missing_env_exits_65(tmp_path):
    r = _run("help-deals.sh", home=tmp_path)
    assert r.returncode == 65


def test_help_deals_cancel_on_no(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / ".env.deals").write_text("# empty\n")
    # отвечаем "n" на "Готов? [y/N]" → отмена, exit 0, claude не запускается
    r = _run("help-deals.sh", home=tmp_path, stdin="n\n")
    assert r.returncode == 0
    assert "Cancelled" in r.stdout
