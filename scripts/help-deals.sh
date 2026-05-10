#!/bin/bash
# Assisted-mode entrypoint. Run when you receive a HELP_NEEDED Telegram alert.
#
# Opens an INTERACTIVE Claude Code session with the master prompt scoped to:
# "read Pending_Help_Queue, close all WAITING_FOR_HUMAN tasks via claude-in-chrome MCP,
#  pause for human at each anti-bot barrier, then continue to extract listings."
#
# Usage:
#   bash $DEAL_HUNTER_HOME/scripts/help-deals.sh
#
# Requires:
#   - Chrome extension "Claude in Chrome" installed and connected.
#   - claude-in-chrome MCP tools available in this Claude Code installation.

set -uo pipefail

DEAL_HUNTER_HOME="${DEAL_HUNTER_HOME:-$HOME/.claude}"

ENV_FILE="$DEAL_HUNTER_HOME/secrets/.env.deals"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 65
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

if [[ -n "${PYTHON_VENV:-}" && -d "$PYTHON_VENV" ]]; then
  # shellcheck disable=SC1091
  . "$PYTHON_VENV/bin/activate"
fi

# Pre-check: claude-in-chrome MCP available?
# (manual check — we can't introspect MCP from here without claude itself)
echo
echo "===================================================================="
echo " Assisted Mode — закрытие очереди Pending_Help_Queue вручную "
echo "===================================================================="
echo
echo "Перед запуском убедись:"
echo "  1. Chrome extension 'Claude in Chrome' установлен и активен"
echo "  2. Chrome открыт"
echo "  3. У тебя ~5-15 минут чтобы пройти capth/cf-challenges по очереди"
echo
read -r -p "Готов? [y/N] " ans
if [[ "${ans,,}" != "y" ]]; then
  echo "Cancelled."
  exit 0
fi

export DEAL_HUNTER_HOME
MASTER_PROMPT="$DEAL_HUNTER_HOME/prompts/deal-hunter-master.md"

ASSISTED_PROMPT="SOURCE_GROUP=assisted
RUN_ID=assisted-$(date +%Y%m%d-%H%M%S)
DEAL_HUNTER_HOME=$DEAL_HUNTER_HOME

Ты в ASSISTED MODE. Задача:

1. Прочитай лист Pending_Help_Queue:
   python3 \$DEAL_HUNTER_HOME/scripts/sheets_write.py --tab Pending_Help_Queue --read

2. Для каждой задачи со status=WAITING_FOR_HUMAN:
   a. Обнови её на status=IN_PROGRESS, assigned_at=now() через sheets_write.py upsert
   b. Используй mcp__Claude_in_Chrome__navigate чтобы открыть target_url в реальном Chrome
   c. Подожди немного, затем mcp__Claude_in_Chrome__get_page_text или screenshot
   d. Если видишь cf-challenge/captcha/login-form — НЕ пытайся их обойти. Скажи мне:
      'Пройди вручную в окне Chrome: <что именно нужно>. Скажи 'готово' когда закончишь.'
      Дождись моего подтверждения, ТОЛЬКО ТОГДА продолжай.
   e. После прохождения барьера — извлеки листинги со страницы (используй get_page_text + парсинг)
   f. Запиши результаты в лист Deals (через sheets_write.py upsert)
   g. Обнови задачу на status=DONE, closed_at=now(), result_summary='<короткий итог>'
   h. Шли tg_notify.sh RUN_SUMMARY с результатом по этой задаче

3. После всей очереди — итоговый tg_notify.sh с числом закрытых задач.

Соблюдай мастер-промпт ниже (особенно правило 'не выдумывай'):

---

$(cat "$MASTER_PROMPT")"

# Open interactive Claude Code with the assisted prompt pre-loaded
# Note: we don't use --bare here because we NEED claude-in-chrome MCP
exec claude "$ASSISTED_PROMPT"
