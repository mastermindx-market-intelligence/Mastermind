"""Atomic replacement for Self-Directed state read concurrently by unlocked dashboard consumers."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from portfolio import self_directed as SD


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "self_directed"
    monkeypatch.setattr(SD, "_DATA", data)
    monkeypatch.setattr(SD, "_ACCOUNT_PATH", data / "account.json")
    monkeypatch.setattr(SD, "_FILLS_PATH", data / "fills.jsonl")
    monkeypatch.setattr(SD, "_PENDING_PATH", data / "pending.json")
    monkeypatch.setattr(SD, "_THESES_PATH", data / "theses.json")
    monkeypatch.setattr(SD, "_NAV_PATH", data / "nav_history.jsonl")
    monkeypatch.setattr(SD, "_PUBLISHED_PATH", tmp_path / "published" / "latest.json")
    monkeypatch.setattr(SD, "_today", lambda: "2026-09-16")
    yield tmp_path


def _raise_replace(*_args, **_kwargs):
    raise OSError("replace unavailable")


@pytest.mark.parametrize("kind", ["account", "pending", "theses"])
def test_json_state_keeps_old_complete_file_when_replace_fails(sandbox, monkeypatch, kind):
    target = {
        "account": SD._ACCOUNT_PATH,
        "pending": SD._PENDING_PATH,
        "theses": SD._THESES_PATH,
    }[kind]
    target.parent.mkdir(parents=True, exist_ok=True)
    old = '{"sentinel":"old-complete-state"}'
    target.write_text(old)
    monkeypatch.setattr(os, "replace", _raise_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        if kind == "account":
            SD._save_account({"cash": 1.0, "positions": {}})
        elif kind == "pending":
            SD._save_pending([{"order_id": "new"}])
        else:
            SD._save_theses({"AAPL": {"note": "new"}})

    assert target.read_text() == old
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_nav_history_keeps_prior_complete_file_when_replace_fails(sandbox, monkeypatch):
    SD._save_account({
        "inception_date": "2026-09-01", "starting_nav": 1_000_000.0, "cash": 900_000.0,
        "spy_shares": 2_000.0, "spy_inception_price": 500.0,
        "positions": {"AAPL": {
            "shares": 1_000.0, "avg_cost": 100.0,
            "current_price": 150.0, "current_price_asof": "2026-09-17",
        }},
    })
    SD._NAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = json.dumps({"date": "2026-09-15", "nav": 1_040_000.0}) + "\n"
    SD._NAV_PATH.write_text(old)
    monkeypatch.setattr(os, "replace", _raise_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        SD.mark(prices={"AAPL": 160.0, "SPY": 510.0}, asof="2026-09-16")

    assert SD._NAV_PATH.read_text() == old


def test_publication_keeps_prior_complete_file_when_replace_fails(sandbox, monkeypatch):
    SD._save_account({
        "inception_date": "2026-09-01", "starting_nav": 1_000_000.0, "cash": 900_000.0,
        "positions": {"AAPL": {"shares": 1_000.0, "avg_cost": 100.0}},
    })
    SD._PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = '{"schema":"portfolio.v1","as_of":"2026-09-15","nav":1040000}'
    SD._PUBLISHED_PATH.write_text(old)
    monkeypatch.setattr(os, "replace", _raise_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        SD.publish(prices={"AAPL": 160.0}, asof="2026-09-16")

    assert SD._PUBLISHED_PATH.read_text() == old


def test_replacement_temp_is_same_directory_and_disappears_after_success(sandbox, monkeypatch):
    real_replace = os.replace
    seen = []

    def _record(src, dst):
        seen.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _record)
    SD._save_account({"cash": 123.0, "positions": {}})

    assert len(seen) == 1
    src, dst = seen[0]
    assert dst == SD._ACCOUNT_PATH
    assert src.parent == dst.parent
    assert src.name.startswith(f".{dst.name}.") and src.name.endswith(".tmp")
    assert not src.exists()
    assert json.loads(dst.read_text())["cash"] == 123.0
