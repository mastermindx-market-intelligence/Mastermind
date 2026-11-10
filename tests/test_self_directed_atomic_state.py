"""Atomic replacement for Self-Directed state read concurrently by unlocked dashboard consumers."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from portfolio import self_directed as SD

pytestmark = pytest.mark.strict_book_dirs


@pytest.fixture()
def sandbox(tmp_path, monkeypatch, event_records):
    data = tmp_path / "self_directed"
    data.mkdir()
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
    old = json.dumps({
        "account": {"cash": 321.0, "positions": {}},
        "pending": [{"order_id": "old"}],
        "theses": {"AAPL": {"note": "old"}},
    }[kind])
    target.write_text(old)
    attempted = []

    def fail_replace(src, dst):
        attempted.append(Path(dst))
        _raise_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        if kind == "account":
            SD._save_account({"cash": 1.0, "positions": {}})
        elif kind == "pending":
            SD._save_pending([{"order_id": "new"}])
        else:
            SD._save_theses({"AAPL": {"note": "new"}})

    assert target.read_text() == old
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []

    assert attempted == [target]


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
    original_replace = os.replace
    attempted = []

    def fail_target(src, dst):
        if Path(dst) == SD._NAV_PATH:
            attempted.append(Path(dst))
            _raise_replace(src, dst)
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_target)

    with pytest.raises(OSError, match="replace unavailable"):
        SD.mark(prices={"AAPL": 160.0, "SPY": 510.0}, asof="2026-09-16")

    assert SD._NAV_PATH.read_text() == old

    assert attempted == [SD._NAV_PATH]


def test_publication_keeps_prior_complete_file_when_replace_fails(sandbox, monkeypatch):
    SD._save_account({
        "inception_date": "2026-09-01", "starting_nav": 1_000_000.0, "cash": 900_000.0,
        "positions": {"AAPL": {"shares": 1_000.0, "avg_cost": 100.0}},
    })
    SD._PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = '{"schema":"portfolio.v1","as_of":"2026-09-15","nav":1040000}'
    SD._PUBLISHED_PATH.write_text(old)
    original_replace = os.replace
    attempted = []

    def fail_target(src, dst):
        if Path(dst) == SD._PUBLISHED_PATH:
            attempted.append(Path(dst))
            _raise_replace(src, dst)
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_target)

    with pytest.raises(OSError, match="replace unavailable"):
        SD.publish(prices={"AAPL": 160.0}, asof="2026-09-16")

    assert SD._PUBLISHED_PATH.read_text() == old

    assert attempted == [SD._PUBLISHED_PATH]


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


import stat


@pytest.fixture()
def event_records(monkeypatch):
    from control_plane import run_events

    records = []
    monkeypatch.setattr(run_events, "append", lambda event: records.append(event))
    return records


def _valid_account():
    return {
        "inception_date": "2026-09-01", "starting_nav": 1_000_000.0, "cash": 900_000.0,
        "spy_shares": 2_000.0, "spy_inception_price": 500.0,
        "positions": {"AAPL": {
            "shares": 1_000.0, "avg_cost": 100.0,
            "current_price": 150.0, "current_price_asof": "2026-09-17",
        }},
    }


def _target(kind):
    if kind in ("nav", "publication"):
        SD._ACCOUNT_PATH.write_text(json.dumps(_valid_account()))
    if kind == "publication":
        SD._PUBLISHED_PATH.parent.mkdir(parents=True)
    return {
        "account": SD._ACCOUNT_PATH, "pending": SD._PENDING_PATH,
        "theses": SD._THESES_PATH, "nav": SD._NAV_PATH, "publication": SD._PUBLISHED_PATH,
    }[kind]


def _old_payload(kind):
    values = {
        "account": {"cash": 321.0, "positions": {}},
        "pending": [{"order_id": "old"}],
        "theses": {"AAPL": {"note": "old"}},
        "nav": {"date": "2026-09-15", "nav": 1_040_000.0},
        "publication": {"schema": "portfolio.v1", "as_of": "2026-09-15", "nav": 1_040_000},
    }
    return (json.dumps(values[kind]) + ("\n" if kind == "nav" else "")).encode()


def _invoke_writer(kind):
    if kind == "account":
        return SD._save_account({"cash": 777.0, "positions": {}})
    if kind == "pending":
        return SD._save_pending([{"order_id": "new", "ticker": "AAPL"}])
    if kind == "theses":
        return SD._save_theses({"AAPL": {"note": "研究 — conviction"}})
    if kind == "nav":
        return SD.mark(prices={"AAPL": 160.0, "SPY": 510.0}, asof="2026-09-16")
    return SD.publish(prices={"AAPL": 160.0}, asof="2026-09-16")


def _assert_payload(kind, payload):
    if kind == "nav":
        rows = [json.loads(line) for line in payload.decode().splitlines()]
        assert rows[-1]["date"] == "2026-09-16"
        assert rows[-1]["nav"] == 1_060_000.0
        return
    value = json.loads(payload)
    if kind == "account":
        assert value["cash"] == 777.0
    elif kind == "pending":
        assert value == [{"order_id": "new", "ticker": "AAPL"}]
    elif kind == "theses":
        assert value == {"AAPL": {"note": "研究 — conviction"}}
        assert "研究".encode() in payload
    else:
        assert value["schema"] == "portfolio.v1"
        assert value["nav"] == 1_060_000.0


@pytest.mark.parametrize("kind", ["account", "pending", "theses", "nav", "publication"])
@pytest.mark.parametrize("mode", [0o600, 0o640])
def test_existing_artifact_permissions_survive_atomic_replacement(sandbox, kind, mode):
    target = _target(kind)
    target.write_bytes(_old_payload(kind))
    target.chmod(mode)
    _invoke_writer(kind)
    assert stat.S_IMODE(target.stat().st_mode) == mode
    _assert_payload(kind, target.read_bytes())
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.parametrize("kind", ["account", "pending", "theses", "nav", "publication"])
def test_fresh_files_keep_existing_umask_behavior(sandbox, kind):
    target = _target(kind)
    previous = os.umask(0o027)
    try:
        _invoke_writer(kind)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    _assert_payload(kind, target.read_bytes())


@pytest.mark.parametrize("kind", ["account", "pending", "theses", "nav", "publication"])
def test_readers_see_old_complete_file_until_synced_replacement(sandbox, monkeypatch, kind):
    target = _target(kind)
    old = _old_payload(kind)
    target.write_bytes(old)
    real_replace = os.replace
    real_fsync = os.fsync
    synced = set()
    observed = []

    def fsync(fd):
        info = os.fstat(fd)
        result = real_fsync(fd)
        if stat.S_ISREG(info.st_mode):
            synced.add(info.st_ino)
        return result

    def replace(src, dst):
        source, destination = Path(src), Path(dst)
        if destination == target:
            assert source.parent == target.parent
            assert target.read_bytes() == old
            assert source.stat().st_ino in synced
            _assert_payload(kind, source.read_bytes())
            observed.append((target.read_bytes(), source.read_bytes()))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    _invoke_writer(kind)
    assert len(observed) == 1
    assert observed[0][0] == old
    assert observed[0][1] == target.read_bytes()
    _assert_payload(kind, target.read_bytes())


@pytest.mark.parametrize("failure", ["write", "flush", "file_fsync", "mode"])
def test_pre_replace_failures_preserve_target_and_remove_temporary_file(sandbox, monkeypatch, failure):
    target = SD._DATA / "private-state.json"
    old = b'{"complete":"old"}'
    target.write_bytes(old)
    target.chmod(0o600)
    original_open = Path.open

    class FaultyFile:
        def __init__(self, actual):
            self.actual = actual

        def __enter__(self):
            self.actual.__enter__()
            return self

        def __exit__(self, *args):
            return self.actual.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.actual, name)

        def write(self, payload):
            if failure == "write":
                self.actual.write(payload[:3])
                self.actual.flush()
                raise OSError("private write failure")
            return self.actual.write(payload)

        def flush(self):
            if failure == "flush":
                raise OSError("private flush failure")
            return self.actual.flush()

    def open_file(self, *args, **kwargs):
        actual = original_open(self, *args, **kwargs)
        if self.parent == target.parent and self.name.startswith(f".{target.name}."):
            return FaultyFile(actual)
        return actual

    monkeypatch.setattr(Path, "open", open_file)
    if failure == "file_fsync":
        monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("private fsync failure")))
    if failure == "mode":
        monkeypatch.setattr(os, "fchmod", lambda *args: (_ for _ in ()).throw(OSError("private mode failure")))
    with pytest.raises(OSError, match="private"):
        SD._atomic_write_bytes(target, b'{"complete":"new"}')
    assert target.read_bytes() == old
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_directory_fsync_fallback_preserves_successful_replace(sandbox, monkeypatch):
    target = SD._DATA / "private-state.json"
    target.write_bytes(b'{"old":true}')
    real_fsync = os.fsync
    seen = []

    def fsync(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        seen.append("directory" if directory else "file")
        if directory:
            raise OSError("directory sync unavailable")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    SD._atomic_write_bytes(target, b'{"new":true}')
    assert target.read_bytes() == b'{"new":true}'
    assert seen == ["file", "directory"]
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_unknown_existing_mode_refuses_before_creating_a_temporary_file(sandbox, monkeypatch):
    target = SD._DATA / "private-state.json"
    old = b'{"old":true}'
    target.write_bytes(old)
    original = Path.stat

    def stat_file(self, *args, **kwargs):
        if self == target:
            raise PermissionError("mode unavailable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_file)
    with pytest.raises(PermissionError, match="mode unavailable"):
        SD._atomic_write_bytes(target, b'{"new":true}')
    assert target.read_bytes() == old
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_directory_target_remains_untouched_after_replace_refusal(sandbox):
    target = SD._DATA / "directory-target"
    target.mkdir()
    marker = target / "keep"
    marker.write_text("old")
    with pytest.raises(OSError):
        SD._atomic_write_bytes(target, b"new")
    assert target.is_dir()
    assert marker.read_text() == "old"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.parametrize("kind", ["account", "pending", "theses"])
def test_missing_book_directory_still_refuses_without_recreation(sandbox, kind):
    SD._DATA.rmdir()
    with pytest.raises(SD.SelfDirectedAccountInvalid) as caught:
        _invoke_writer(kind)
    assert "data_dir_missing" in caught.value.problems
    assert not SD._DATA.exists()
    assert list(sandbox.rglob("*.tmp")) == []


def test_missing_publication_directory_retains_none_refusal(sandbox):
    SD._ACCOUNT_PATH.write_text(json.dumps(_valid_account()))
    before = SD._ACCOUNT_PATH.read_bytes()
    assert SD.publish(prices={"AAPL": 160.0}, asof="2026-09-16") is None
    assert not SD._PUBLISHED_PATH.parent.exists()
    assert SD._ACCOUNT_PATH.read_bytes() == before


def test_existing_invalid_account_is_preserved_and_quarantine_copy_remains_exact(sandbox, event_records):
    original = b"\xff private invalid account bytes"
    SD._ACCOUNT_PATH.write_bytes(original)
    with pytest.raises(SD.SelfDirectedAccountInvalid) as first:
        SD._load_account()
    assert first.value.problems
    assert first.value.record["status"] == "quarantined"
    with pytest.raises(SD.SelfDirectedAccountInvalid) as second:
        SD._load_account()
    assert second.value.record["status"] == "already_quarantined"
    copies = list(SD._DATA.glob("account.quarantine.*.json"))
    assert len(copies) == 1
    assert copies[0].read_bytes() == original
    assert SD._ACCOUNT_PATH.read_bytes() == original
    assert len(event_records) == 1
    assert event_records[0]["kind"] == "account_state_invalid"
    assert list(SD._DATA.glob(".*.tmp")) == []


def test_nav_atomic_replacement_remains_idempotent_by_date(sandbox):
    SD._ACCOUNT_PATH.write_text(json.dumps(_valid_account()))
    SD._NAV_PATH.write_bytes(_old_payload("nav"))
    SD._NAV_PATH.chmod(0o640)
    SD.mark(prices={"AAPL": 160.0, "SPY": 510.0}, asof="2026-09-16")
    SD.mark(prices={"AAPL": 170.0, "SPY": 510.0}, asof="2026-09-16")
    rows = [json.loads(line) for line in SD._NAV_PATH.read_text().splitlines()]
    assert [row["date"] for row in rows] == ["2026-09-15", "2026-09-16"]
    assert rows[-1]["nav"] == 1_070_000.0
    assert stat.S_IMODE(SD._NAV_PATH.stat().st_mode) == 0o640
    assert list(SD._DATA.glob(".*.tmp")) == []
