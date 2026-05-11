#!/usr/bin/env python3
"""Универсальный интерфейс к Google Sheets для MacBook Deal Hunter.

Использование:
    # запись массива объявлений в Deals (upsert по listing_url)
    python3 sheets_write.py --tab Deals --mode upsert --key listing_url --rows '[...]'

    # append без дедупликации
    python3 sheets_write.py --tab Source_Check_Log --mode append --rows '[...]'

    # пометить пропавшие листинги unavailable
    python3 sheets_write.py --tab Deals --mode mark_unavailable --key listing_url --rows '[{"listing_url":"..."}]'

    # прочитать лист (вернёт JSON)
    python3 sheets_write.py --tab Pending_Help_Queue --read

Особенности:
- Английские ключи в input → русские заголовки в Sheet (через $DEAL_HUNTER_HOME/data/sheet_columns_ru.yaml)
- При первой записи listing_url проставляет first_seen_at_almaty (immutable при последующих upsert)
- Пересчитывает minutes_since_first_seen / hours_since_first_seen при каждом upsert
- При недоступности Sheets API — записывает в $DEAL_HUNTER_HOME/state/stash.jsonl, возвращает ненулевой exit
- Schema validation: будущая интеграция через jsonschema (placeholder)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

HOME = Path.home()
DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(HOME / ".claude")))
COLUMNS_YAML = DEAL_HUNTER_HOME / "data" / "sheet_columns_ru.yaml"
STASH_FILE = DEAL_HUNTER_HOME / "state" / "stash.jsonl"
ALMATY_TZ = timezone(timedelta(hours=5))  # UTC+5 без DST


def now_almaty_iso() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y-%m-%d %H:%M:%S")


def load_column_mapping(tab: str) -> dict[str, str]:
    """Returns {english_key: russian_header} for a given tab."""
    with COLUMNS_YAML.open() as f:
        cfg = yaml.safe_load(f)
    if tab not in cfg:
        raise ValueError(f"Tab {tab!r} not in {COLUMNS_YAML}")
    mapping = cfg[tab]
    if "use_mapping_from" in mapping:
        return cfg[mapping["use_mapping_from"]]
    return mapping


def get_worksheet(tab: str):
    """Authorize gspread and return worksheet. Raises on connectivity failure."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = os.environ.get("SHEETS_SA_JSON", str(DEAL_HUNTER_HOME / "secrets" / "sheets-sa.json"))
    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        raise RuntimeError("SHEET_ID env var not set (expected from .env.deals)")

    creds = Credentials.from_service_account_file(
        sa_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    return sh.worksheet(tab)


def stash_rows(tab: str, mode: str, rows: list[dict], reason: str) -> None:
    """Persist rows locally when Sheets API fails."""
    STASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STASH_FILE.open("a") as f:
        for row in rows:
            f.write(
                json.dumps(
                    {
                        "tab": tab,
                        "mode": mode,
                        "row": row,
                        "reason": reason,
                        "stashed_at_almaty": now_almaty_iso(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def english_to_russian_row(row_en: dict, mapping: dict[str, str], headers: list[str]) -> list:
    """Convert {english_key: value} → row in order of `headers` (russian header strings)."""
    en_to_ru = mapping
    ru_to_value = {}
    for k, v in row_en.items():
        if k not in en_to_ru:
            continue  # silently drop unknown keys (allows graceful schema evolution)
        ru = en_to_ru[k]
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        ru_to_value[ru] = "" if v is None else v
    return [ru_to_value.get(h, "") for h in headers]


def ensure_headers(ws, mapping: dict[str, str]) -> list[str]:
    """Ensure header row matches mapping; if sheet is empty, write headers."""
    expected = [mapping[k] for k in mapping if k != "use_mapping_from"]
    current = ws.row_values(1)
    if not current:
        ws.update("A1", [expected], value_input_option="USER_ENTERED")
        return expected
    # If new keys added to YAML, append to header row
    missing = [h for h in expected if h not in current]
    if missing:
        new_headers = current + missing
        ws.update("A1", [new_headers], value_input_option="USER_ENTERED")
        return new_headers
    return current


def find_row_by_key(ws, key_col_name_ru: str, key_value: str) -> int | None:
    """Return 1-indexed row number for a row where key_col_name_ru == key_value, or None."""
    headers = ws.row_values(1)
    if key_col_name_ru not in headers:
        return None
    col_idx = headers.index(key_col_name_ru) + 1  # 1-indexed
    col_values = ws.col_values(col_idx)
    for i, v in enumerate(col_values[1:], start=2):  # skip header row
        if v == key_value:
            return i
    return None


def cmd_append(ws, mapping: dict[str, str], rows: list[dict]) -> dict:
    headers = ensure_headers(ws, mapping)
    sheet_rows = [english_to_russian_row(r, mapping, headers) for r in rows]
    if sheet_rows:
        ws.append_rows(sheet_rows, value_input_option="USER_ENTERED")
    return {"appended": len(sheet_rows)}


def cmd_upsert(ws, mapping: dict[str, str], rows: list[dict], key: str) -> dict:
    """Upsert by english key. For new rows: set first_seen_at_almaty.
    For existing rows: preserve first_seen_at_almaty, recompute hours_since."""
    if key not in mapping:
        raise ValueError(f"Key {key!r} not in column mapping for this tab")
    key_col_ru = mapping[key]
    headers = ensure_headers(ws, mapping)

    inserted = updated = 0
    now_iso = now_almaty_iso()

    for row in rows:
        key_value = row.get(key)
        if not key_value:
            continue
        existing_row_num = find_row_by_key(ws, key_col_ru, str(key_value))
        if existing_row_num is None:
            # New listing — set first_seen_at_almaty if applicable
            if "first_seen_at_almaty" in mapping and "first_seen_at_almaty" not in row:
                row["first_seen_at_almaty"] = now_iso
            row["last_checked_at"] = now_iso
            row = _recompute_freshness(row)
            ws.append_row(
                english_to_russian_row(row, mapping, headers),
                value_input_option="USER_ENTERED",
            )
            inserted += 1
        else:
            # Existing — preserve first_seen_at_almaty from sheet
            existing_values = ws.row_values(existing_row_num)
            existing_dict = dict(zip(headers, existing_values, strict=False))
            preserved = {}
            if "first_seen_at_almaty" in mapping:
                fsa_ru = mapping["first_seen_at_almaty"]
                if existing_dict.get(fsa_ru):
                    preserved["first_seen_at_almaty"] = existing_dict[fsa_ru]
                else:
                    preserved["first_seen_at_almaty"] = now_iso
            merged = {**row, **preserved, "last_checked_at": now_iso}
            merged = _recompute_freshness(merged)
            ws.update(
                f"A{existing_row_num}",
                [english_to_russian_row(merged, mapping, headers)],
                value_input_option="USER_ENTERED",
            )
            updated += 1
    return {"inserted": inserted, "updated": updated}


def _recompute_freshness(row: dict) -> dict:
    """Compute minutes_since_first_seen and hours_since_first_seen from first_seen_at_almaty."""
    fsa = row.get("first_seen_at_almaty")
    if not fsa:
        return row
    try:
        fsa_dt = datetime.strptime(fsa, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ALMATY_TZ)
        now = datetime.now(ALMATY_TZ)
        delta = now - fsa_dt
        row["minutes_since_first_seen"] = int(delta.total_seconds() // 60)
        row["hours_since_first_seen"] = round(delta.total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        pass
    return row


def cmd_mark_unavailable(ws, mapping: dict[str, str], rows: list[dict], key: str) -> dict:
    """Mark rows as availability_status=unavailable by key."""
    if "availability_status" not in mapping:
        raise ValueError("Tab has no availability_status column")
    key_col_ru = mapping[key]
    avail_col_ru = mapping["availability_status"]
    headers = ws.row_values(1)
    avail_idx = headers.index(avail_col_ru) + 1

    marked = 0
    for row in rows:
        key_value = row.get(key)
        if not key_value:
            continue
        rn = find_row_by_key(ws, key_col_ru, str(key_value))
        if rn:
            ws.update_cell(rn, avail_idx, "недоступно")
            marked += 1
    return {"marked_unavailable": marked}


def cmd_read(ws, mapping: dict[str, str]) -> list[dict]:
    """Read all rows, convert russian headers back to english keys."""
    ru_to_en = {v: k for k, v in mapping.items() if k != "use_mapping_from"}
    records = ws.get_all_records()
    out = []
    for rec in records:
        out.append({ru_to_en.get(k, k): v for k, v in rec.items()})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Google Sheets writer for deal hunter")
    p.add_argument("--tab", required=True)
    p.add_argument("--mode", choices=["append", "upsert", "mark_unavailable"])
    p.add_argument("--read", action="store_true")
    p.add_argument("--key", default="listing_url")
    p.add_argument("--rows", help="JSON array of row dicts (english keys)")
    p.add_argument("--rows-file", help="Path to JSON file with array of row dicts")
    args = p.parse_args()

    mapping = load_column_mapping(args.tab)

    if args.read:
        try:
            ws = get_worksheet(args.tab)
            data = cmd_read(ws, mapping)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            return 1

    if not args.mode:
        p.error("--mode is required when not using --read")

    if args.rows_file:
        with open(args.rows_file) as f:
            rows = json.load(f)
    elif args.rows:
        rows = json.loads(args.rows)
    else:
        p.error("--rows or --rows-file is required")

    if not isinstance(rows, list):
        rows = [rows]

    try:
        ws = get_worksheet(args.tab)
        if args.mode == "append":
            result = cmd_append(ws, mapping, rows)
        elif args.mode == "upsert":
            result = cmd_upsert(ws, mapping, rows, args.key)
        elif args.mode == "mark_unavailable":
            result = cmd_mark_unavailable(ws, mapping, rows, args.key)
        else:
            raise ValueError(f"Unknown mode {args.mode}")
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except Exception as e:
        stash_rows(args.tab, args.mode, rows, str(e))
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(e),
                    "stashed_count": len(rows),
                    "stash_file": str(STASH_FILE),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
