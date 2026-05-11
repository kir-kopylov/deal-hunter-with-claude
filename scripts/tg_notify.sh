#!/bin/bash
# Telegram notify helper. Usage:
#   tg_notify.sh <CATEGORY> "<message>"
# Categories: HOT_DEAL | HELP_NEEDED | RUN_SUMMARY | STALE_QUEUE | YIELD_DROP | DIST_SHIFT
#
# Reads TG_TOKEN, TG_CHAT_ID, TG_SUMMARY from $DEAL_HUNTER_HOME/secrets/.env.deals.
# Logs failures to $DEAL_HUNTER_HOME/logs/tg_failed.log instead of failing the caller.

set -u

DEAL_HUNTER_HOME="${DEAL_HUNTER_HOME:-$HOME/.claude}"

CATEGORY="${1:-}"
MESSAGE="${2:-}"

if [[ -z "$CATEGORY" || -z "$MESSAGE" ]]; then
  echo "Usage: $0 <CATEGORY> \"<message>\"" >&2
  exit 64
fi

ENV_FILE="$DEAL_HUNTER_HOME/secrets/.env.deals"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Copy from .env.deals.template and fill in." >&2
  exit 65
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

LOG_FAIL="$DEAL_HUNTER_HOME/logs/tg_failed.log"
mkdir -p "$(dirname "$LOG_FAIL")"

# Suppress RUN_SUMMARY if user opted out
if [[ "$CATEGORY" == "RUN_SUMMARY" && "${TG_SUMMARY:-1}" != "1" ]]; then
  exit 0
fi

# Pick emoji + sound for category
case "$CATEGORY" in
  HOT_DEAL)     EMOJI="🔥"; SILENT="false"; PREFIX="HOT DEAL" ;;
  HELP_NEEDED)  EMOJI="🆘"; SILENT="false"; PREFIX="HELP NEEDED" ;;
  STALE_QUEUE)  EMOJI="⏰"; SILENT="false"; PREFIX="STALE QUEUE" ;;
  YIELD_DROP)   EMOJI="⚠️"; SILENT="true";  PREFIX="YIELD DROP" ;;
  DIST_SHIFT)   EMOJI="⚠️"; SILENT="true";  PREFIX="DIST SHIFT" ;;
  RUN_SUMMARY)  EMOJI="✅"; SILENT="true";  PREFIX="RUN" ;;
  *)            EMOJI="ℹ️"; SILENT="true";  PREFIX="$CATEGORY" ;;
esac

if [[ -z "${TG_TOKEN:-}" || -z "${TG_CHAT_ID:-}" ]]; then
  echo "$(date -Iseconds) MISSING_CREDS category=$CATEGORY msg=$MESSAGE" >> "$LOG_FAIL"
  exit 66
fi

FULL_MSG="${EMOJI} *${PREFIX}*
${MESSAGE}"

# Truncate to 4000 chars to stay under Telegram's 4096 limit
FULL_MSG="${FULL_MSG:0:4000}"

API_URL="https://api.telegram.org/bot${TG_TOKEN}/sendMessage"

RESP=$(curl -s -m 10 -X POST "$API_URL" \
  --data-urlencode "chat_id=${TG_CHAT_ID}" \
  --data-urlencode "text=${FULL_MSG}" \
  --data-urlencode "parse_mode=Markdown" \
  --data-urlencode "disable_notification=${SILENT}" \
  -w "\n%{http_code}") || {
    echo "$(date -Iseconds) CURL_FAIL category=$CATEGORY msg=$MESSAGE" >> "$LOG_FAIL"
    exit 0  # don't propagate failure to caller
  }

HTTP_CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | sed '$d')

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "$(date -Iseconds) HTTP_${HTTP_CODE} category=$CATEGORY body=$BODY" >> "$LOG_FAIL"
  exit 0  # log and continue, don't break main pipeline
fi

exit 0
