"""P1 — поведенческие тесты scripts/tg_notify.sh без сети.

curl подменяется фейковым исполняемым файлом на PATH, который пишет свои
аргументы в файл и печатает управляемый HTTP-код. Так мы проверяем:
маппинг категория→эмодзи, opt-out RUN_SUMMARY, отсутствие кредов, ветки
HTTP!=200 и сбоя curl (контракт «не ронять вызывающего»), усечение до 4000.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tg_notify.sh"

FAKE_CURL = """#!/bin/bash
if [[ -n "${CURL_FAIL:-}" ]]; then
  exit 1
fi
# Аргументы пишем через NUL-разделитель: значение text= само содержит переносы
# строк (заголовок Markdown + \\n + тело), поэтому '\\n' как разделитель не дал бы
# восстановить полный аргумент. NUL в тексте появиться не может.
printf '%s\\0' "$@" >> "$CURL_ARGS_FILE"
echo '{"ok":true}'
echo "${CURL_HTTP_CODE:-200}"
"""


@pytest.fixture
def tg(tmp_path):
    """Готовит изолированный DEAL_HUNTER_HOME + фейковый curl и возвращает runner."""
    home = tmp_path
    (home / "secrets").mkdir()
    (home / "logs").mkdir()
    bindir = home / "bin"
    bindir.mkdir()
    curl = bindir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    args_file = home / "curl_args.txt"
    fail_log = home / "logs" / "tg_failed.log"

    def run(
        category="HOT_DEAL",
        message="hello",
        *,
        write_env=True,
        token="TOKEN",
        chat="CHAT",
        summary=None,
        http_code="200",
        curl_fail=False,
    ):
        if write_env:
            lines = []
            if token is not None:
                lines.append(f"TG_TOKEN={token}")
            if chat is not None:
                lines.append(f"TG_CHAT_ID={chat}")
            if summary is not None:
                lines.append(f"TG_SUMMARY={summary}")
            (home / "secrets" / ".env.deals").write_text("\n".join(lines) + "\n")

        import os

        env = dict(os.environ)
        # Hermetic: не давать унаследованным TG_*-кредам/настройкам протечь в скрипт.
        # tg_notify.sh читает ${TG_TOKEN:-} и т.п. из окружения, а sourcing пустого
        # env-файла их не очищает — иначе missing-creds/opt-out ветки не отработают
        # там, где эти переменные экспортированы (локально или в CI).
        for var in ("TG_TOKEN", "TG_CHAT_ID", "TG_SUMMARY"):
            env.pop(var, None)
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["DEAL_HUNTER_HOME"] = str(home)
        env["CURL_ARGS_FILE"] = str(args_file)
        env["CURL_HTTP_CODE"] = http_code
        if curl_fail:
            env["CURL_FAIL"] = "1"
        return subprocess.run(
            ["bash", str(SCRIPT), category, message],
            capture_output=True,
            text=True,
            env=env,
        )

    run.args_file = args_file
    run.fail_log = fail_log
    return run


def test_usage_error_when_message_missing(tg):
    r = tg(category="HOT_DEAL", message="")
    assert r.returncode == 64


def test_missing_env_file_exits_65(tg):
    r = tg(write_env=False)
    assert r.returncode == 65


def test_run_summary_suppressed_when_opted_out(tg):
    r = tg(category="RUN_SUMMARY", message="daily", summary="0")
    assert r.returncode == 0
    # curl НЕ должен вызываться
    assert not tg.args_file.exists()


def test_run_summary_sent_when_enabled(tg):
    r = tg(category="RUN_SUMMARY", message="daily", summary="1")
    assert r.returncode == 0
    assert tg.args_file.exists()


def test_missing_creds_logs_and_exits_66(tg):
    r = tg(token=None, chat=None)
    assert r.returncode == 66
    assert "MISSING_CREDS" in tg.fail_log.read_text()
    assert not tg.args_file.exists()


def test_happy_path_calls_curl_with_emoji_and_prefix(tg):
    r = tg(category="HOT_DEAL", message="MacBook за полцены")
    assert r.returncode == 0
    args = tg.args_file.read_text()
    assert "🔥" in args
    assert "HOT DEAL" in args
    assert "MacBook за полцены" in args
    assert "chat_id=CHAT" in args


@pytest.mark.parametrize(
    "category,emoji,prefix",
    [
        ("HOT_DEAL", "🔥", "HOT DEAL"),
        ("HELP_NEEDED", "🆘", "HELP NEEDED"),
        ("STALE_QUEUE", "⏰", "STALE QUEUE"),
        ("SOMETHING_NEW", "ℹ️", "SOMETHING_NEW"),  # дефолтная ветка case
    ],
)
def test_category_emoji_mapping(tg, category, emoji, prefix):
    tg(category=category, message="x")
    args = tg.args_file.read_text()
    assert emoji in args
    assert prefix in args


def test_http_non_200_logged_but_exit_0(tg):
    r = tg(http_code="403")
    assert r.returncode == 0  # не ломаем основной пайплайн
    assert "HTTP_403" in tg.fail_log.read_text()


def test_curl_failure_logged_but_exit_0(tg):
    r = tg(curl_fail=True)
    assert r.returncode == 0
    assert "CURL_FAIL" in tg.fail_log.read_text()


def test_message_truncated_to_4000(tg):
    long_msg = "A" * 5000
    tg(category="HOT_DEAL", message=long_msg)
    # Аргументы разделены NUL; восстанавливаем ПОЛНОЕ значение text= вместе со
    # встроенными переносами строк (заголовок + \n + тело), иначе измерили бы
    # только первую физическую строку и пропустили бы отказ усечения.
    parts = tg.args_file.read_text().split("\0")
    text_values = [p[len("text=") :] for p in parts if p.startswith("text=")]
    assert text_values, "no text= arg recorded from curl"
    # tg_notify.sh усекает FULL_MSG до 4000 символов (под лимит Telegram 4096)
    assert len(text_values[0]) <= 4000
    # без усечения тут было бы ~5014 символов — проверяем, что тело реально урезано
    assert len(text_values[0]) < len(long_msg)
