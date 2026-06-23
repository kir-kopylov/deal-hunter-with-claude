"""P2 — пути устойчивости sheets_write: stash при сбое Sheets + main() CLI.

Когда Google Sheets недоступен, sheets_write не должен терять данные: строки
пишутся в state/stash.jsonl, а процесс возвращает ненулевой код. Плюс покрываем
диспетчер main() (append/read, успех и ошибка) через monkeypatch get_worksheet.
"""

from __future__ import annotations

import json
import sys

import pytest
import sheets_write
from sheets_write import cmd_append, cmd_upsert, load_column_mapping

pytestmark = pytest.mark.unit


class TestStashRows:
    def test_appends_jsonl_and_creates_parent(self, monkeypatch, tmp_path):
        stash = tmp_path / "state" / "stash.jsonl"  # родитель ещё не существует
        monkeypatch.setattr(sheets_write, "STASH_FILE", stash)

        sheets_write.stash_rows("Deals", "append", [{"a": 1}, {"b": 2}], "boom")
        sheets_write.stash_rows("Deals", "upsert", [{"c": 3}], "boom2")

        lines = stash.read_text().splitlines()
        assert len(lines) == 3
        recs = [json.loads(line) for line in lines]
        assert recs[0]["row"] == {"a": 1}
        assert recs[0]["reason"] == "boom"
        assert recs[0]["mode"] == "append"
        assert recs[2]["mode"] == "upsert"
        assert all("stashed_at_almaty" in r for r in recs)
        assert all(r["tab"] == "Deals" for r in recs)


class TestMainStashFallback:
    def _argv(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["sheets_write.py", *args])

    def test_append_failure_stashes_and_returns_2(self, monkeypatch, tmp_path, capsys):
        stash = tmp_path / "stash.jsonl"
        monkeypatch.setattr(sheets_write, "STASH_FILE", stash)
        monkeypatch.delenv("SHEET_ID", raising=False)  # get_worksheet упадёт
        self._argv(
            monkeypatch,
            "--tab",
            "Deals",
            "--mode",
            "append",
            "--rows",
            '[{"listing_url":"u1"}]',
        )

        rc = sheets_write.main()
        assert rc == 2

        recs = [json.loads(line) for line in stash.read_text().splitlines()]
        assert len(recs) == 1
        assert recs[0]["row"] == {"listing_url": "u1"}

        err = json.loads(capsys.readouterr().err)
        assert err["ok"] is False
        assert err["stashed_count"] == 1
        assert err["stash_file"] == str(stash)

    def test_rows_file_failure_stashes(self, monkeypatch, tmp_path):
        rows_file = tmp_path / "rows.json"
        rows_file.write_text('[{"listing_url":"u1"},{"listing_url":"u2"}]')
        stash = tmp_path / "stash.jsonl"
        monkeypatch.setattr(sheets_write, "STASH_FILE", stash)
        monkeypatch.delenv("SHEET_ID", raising=False)
        self._argv(monkeypatch, "--tab", "Deals", "--mode", "append", "--rows-file", str(rows_file))

        assert sheets_write.main() == 2
        assert len(stash.read_text().splitlines()) == 2

    def test_read_failure_returns_1(self, monkeypatch, capsys):
        monkeypatch.delenv("SHEET_ID", raising=False)
        self._argv(monkeypatch, "--tab", "Deals", "--read")

        assert sheets_write.main() == 1
        err = json.loads(capsys.readouterr().err)
        assert "error" in err

    def test_missing_rows_and_read_is_argparse_error(self, monkeypatch):
        self._argv(monkeypatch, "--tab", "Deals", "--mode", "append")
        with pytest.raises(SystemExit):
            sheets_write.main()

    def test_no_mode_and_no_read_is_argparse_error(self, monkeypatch):
        # Ни --read, ни --mode → main() должен ругнуться (p.error → SystemExit).
        self._argv(monkeypatch, "--tab", "Deals", "--rows", "[]")
        with pytest.raises(SystemExit):
            sheets_write.main()


class TestMainSuccessPaths:
    """Успешные ветки main() через monkeypatch get_worksheet → FakeWorksheet."""

    def test_append_success_returns_0(self, monkeypatch, make_ws, capsys):
        ws = make_ws()
        monkeypatch.setattr(sheets_write, "get_worksheet", lambda tab: ws)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sheets_write.py",
                "--tab",
                "Source_Check_Log",
                "--mode",
                "append",
                "--rows",
                '[{"run_id":"r1"}]',
            ],
        )
        assert sheets_write.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        assert out["appended"] == 1

    def test_upsert_success_returns_0(self, monkeypatch, make_ws, capsys):
        ws = make_ws()
        monkeypatch.setattr(sheets_write, "get_worksheet", lambda tab: ws)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sheets_write.py",
                "--tab",
                "Deals",
                "--mode",
                "upsert",
                "--key",
                "listing_url",
                "--rows",
                '[{"listing_url":"u1","price_kzt":100}]',
            ],
        )
        assert sheets_write.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out == {"ok": True, "inserted": 1, "updated": 0}

    def test_mark_unavailable_success_returns_0(self, monkeypatch, make_ws, capsys):
        ws = make_ws()
        cmd_upsert(ws, load_column_mapping("Deals"), [{"listing_url": "u1"}], key="listing_url")
        monkeypatch.setattr(sheets_write, "get_worksheet", lambda tab: ws)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sheets_write.py",
                "--tab",
                "Deals",
                "--mode",
                "mark_unavailable",
                "--key",
                "listing_url",
                "--rows",
                '[{"listing_url":"u1"}]',
            ],
        )
        assert sheets_write.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["marked_unavailable"] == 1

    def test_read_success_returns_0(self, monkeypatch, make_ws, capsys):
        ws = make_ws()
        cmd_append(ws, load_column_mapping("Source_Check_Log"), [{"run_id": "r1"}])
        monkeypatch.setattr(sheets_write, "get_worksheet", lambda tab: ws)
        monkeypatch.setattr(sys, "argv", ["sheets_write.py", "--tab", "Source_Check_Log", "--read"])

        assert sheets_write.main() == 0
        data = json.loads(capsys.readouterr().out)
        assert data[0]["run_id"] == "r1"

    def test_single_dict_rows_wrapped_in_list(self, monkeypatch, make_ws, capsys):
        # --rows c одиночным объектом (не массивом) должен обернуться в список.
        ws = make_ws()
        monkeypatch.setattr(sheets_write, "get_worksheet", lambda tab: ws)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sheets_write.py",
                "--tab",
                "Source_Check_Log",
                "--mode",
                "append",
                "--rows",
                '{"run_id":"solo"}',
            ],
        )
        assert sheets_write.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["appended"] == 1
