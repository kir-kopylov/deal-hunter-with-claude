#!/bin/bash
# Approve a parser fixture: copy <fixture>.received.json to <fixture>.approved.json
#
# Usage:  bash $DEAL_HUNTER_HOME/scripts/approve.sh olx_kz/normal_listing
#
set -euo pipefail

DEAL_HUNTER_HOME="${DEAL_HUNTER_HOME:-$HOME/.claude}"

FIXTURE="${1:-}"
if [[ -z "$FIXTURE" ]]; then
  echo "Usage: $0 <source>/<scenario>" >&2
  echo "Example: $0 olx_kz/normal_listing" >&2
  exit 64
fi

DIR="$DEAL_HUNTER_HOME/tests/fixtures/$FIXTURE"
RECEIVED="${DIR}.received.json"
APPROVED="${DIR}.approved.json"

if [[ ! -f "$RECEIVED" ]]; then
  echo "ERROR: $RECEIVED not found. Run pytest first to generate it." >&2
  exit 65
fi

if [[ -f "$APPROVED" ]]; then
  echo "Diff between current and proposed approval:"
  diff -u "$APPROVED" "$RECEIVED" || true
  read -r -p "Approve this change? [y/N] " ans
  if [[ "${ans,,}" != "y" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

cp "$RECEIVED" "$APPROVED"
echo "Approved: $APPROVED"
