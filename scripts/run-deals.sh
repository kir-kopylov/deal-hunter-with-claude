#!/bin/bash
# Auto-mode entrypoint for MacBook Deal Hunter.
# Called by launchd or manually:
#   bash ~/.claude/scripts/run-deals.sh A1
#
# Reads SOURCE_GROUP from $1 or env. Loads .env.deals secrets.
# Activates Python venv. Runs claude -p --bare in headless mode with the master prompt.

set -uo pipefail

GROUP="${1:-${SOURCE_GROUP:-}}"
if [[ -z "$GROUP" ]]; then
  echo "Usage: $0 <GROUP>   where GROUP is one of: baseline A1 A2 A3 B C" >&2
  exit 64
fi

ENV_FILE="$HOME/.claude/secrets/.env.deals"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 65
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

# Activate Python venv if specified
if [[ -n "${PYTHON_VENV:-}" && -d "$PYTHON_VENV" ]]; then
  # shellcheck disable=SC1091
  . "$PYTHON_VENV/bin/activate"
fi

export SOURCE_GROUP="$GROUP"
RUN_ID="${GROUP}-$(date +%Y%m%d-%H%M%S)-$RANDOM"
TS=$(date +%Y%m%d-%H%M%S)
LOG="$HOME/.claude/logs/deals-${GROUP}-${TS}.log"
mkdir -p "$(dirname "$LOG")"

MASTER_PROMPT="$HOME/.claude/prompts/deal-hunter-master.md"
if [[ ! -f "$MASTER_PROMPT" ]]; then
  echo "ERROR: master prompt not found at $MASTER_PROMPT" >&2
  exit 66
fi

# Fail-fast schema validation
python3 -c "
import yaml, sys
for path in [
    '$HOME/.claude/data/schedule.yaml',
    '$HOME/.claude/data/sheet_columns_ru.yaml',
    '$HOME/.claude/data/landed_cost_table.yaml',
]:
    try:
        with open(path) as f: yaml.safe_load(f)
    except Exception as e:
        print(f'YAML INVALID: {path}: {e}', file=sys.stderr)
        sys.exit(1)
" || {
  bash "$HOME/.claude/scripts/tg_notify.sh" HELP_NEEDED "YAML config invalid before run-deals.sh start. Group=$GROUP. Check logs."
  exit 67
}

# Compose the per-run prompt: master + group-specific instruction
RUN_PROMPT="SOURCE_GROUP=$GROUP
RUN_ID=$RUN_ID

Прочитай мастер-промпт ниже целиком. Выполни workflow для группы $GROUP.

---

$(cat "$MASTER_PROMPT")"

# Allowed tools — pre-approved so headless mode doesn't prompt
ALLOWED_TOOLS="Bash(python3 *) Bash(bash *) Bash(curl *) Bash(osascript *) WebFetch WebSearch Read Grep Glob"

echo "[$(date -Iseconds)] starting run_id=$RUN_ID group=$GROUP" | tee -a "$LOG"

# Use claude in headless mode. --bare skips MCP auto-discovery for speed/stability.
# If you want full MCP set (for assisted mode), use help-deals.sh instead.
claude -p --bare --allowedTools "$ALLOWED_TOOLS" "$RUN_PROMPT" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

echo "[$(date -Iseconds)] finished run_id=$RUN_ID rc=$RC" | tee -a "$LOG"

if [[ "$RC" -ne 0 ]]; then
  bash "$HOME/.claude/scripts/tg_notify.sh" HELP_NEEDED "run-deals.sh group=$GROUP exited rc=$RC. Log: $LOG"
fi

exit "$RC"
