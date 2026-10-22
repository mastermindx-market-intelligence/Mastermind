"""Self-Directed account fails closed on an invalid book (E13, C1–C6).

A single unreadable or malformed ``account.json`` used to be silently replaced by a fresh
$1M all-cash book — and the next save persisted it, erasing the user's real paper positions.
These tests pin the fail-closed contract: a MISSING file is still a legitimate new book, but
an EXISTING unreadable/unparseable/schema-invalid file is quarantined byte-for-byte beside
the original and every caller refuses. All prices/state are synthetic round numbers (this
repository is public). No network, no real ``data/``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def sd_paths(tmp_path: Path, monkeypatch) -> Path:
    """Redirect every self_directed state file into this test's tmp dir (overrides the
    conftest session root) so no test can reach the real ``data/`` tree."""
    from portfolio import self_directed as sd
    monkeypatch.setattr(sd, "_DATA", tmp_path)
    monkeypatch.setattr(sd, "_ACCOUNT_PATH", tmp_path / "account.json")
    monkeypatch.setattr(sd, "_FILLS_PATH", tmp_path / "fills.jsonl")
    monkeypatch.setattr(sd, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(sd, "_THESES_PATH", tmp_path / "theses.json")
    monkeypatch.setattr(sd, "_NAV_PATH", tmp_path / "nav_history.jsonl")
    monkeypatch.setattr(sd, "_PUBLISHED_PATH", tmp_path / "published" / "latest.json")
    return tmp_path


@pytest.fixture()
def run_events_recorder(monkeypatch) -> list[dict]:
    """Capture control_plane.run_events.append events in a list — never the real ledger."""
    from control_plane import run_events
    events: list[dict] = []
    monkeypatch.setattr(run_events, "append", lambda event, **_kw: events.append(event))
    return events


# ── helpers ───────────────────────────────────────────────────────────────────

def _valid_book_bytes() -> bytes:
    """A small, live-shaped VALID book (round numbers only)."""
    return json.dumps({
        "inception_date": "2026-01-05",
        "starting_nav": 1_000_000.0,
        "cash": 500_000.0,
        "positions": {"AAA": {"shares": 100.0, "avg_cost": 25.0}},
    }, indent=2).encode("utf-8")


INVALID_CASES: dict[str, bytes] = {
    # a) unparseable
    "truncated_json": b'{"cash": 500.0, "positions": {"AAA": {"shares": 1.0',
    "empty_file": b"",
    "non_utf8": b'{"cash": 500.0, "positions": {}, "note": "\xff\xfe"}',
    # b) schema-invalid
    "cash_string": b'{"cash": "500000", "positions": {}}',
    "cash_true": b'{"cash": true, "positions": {}}',
    "cash_nan": b'{"cash": NaN, "positions": {}}',
    "positions_list": b'{"cash": 500.0, "positions": []}',
    "position_missing_avg_cost": b'{"cash": 500.0, "positions": {"AAA": {"shares": 3.0}}}',
    "starting_nav_zero": b'{"starting_nav": 0, "cash": 500.0, "positions": {}}',
}


def _ledger_rows(tmp_path: Path) -> list[dict]:
    p = tmp_path / "account_quarantine.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in
            p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _quarantine_copies(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("account.quarantine.*.json"))


def _deny_read_bytes_for(monkeypatch, target: Path) -> None:
    """Make Path.read_bytes raise PermissionError for ONE path only (root-run CI may ignore
    chmod, so the read itself is patched rather than the file mode)."""
    real_read_bytes = Path.read_bytes

    def _deny(self: Path) -> bytes:
        if self == target:
            raise PermissionError(13, "Permission denied")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _deny)


def _assert_single_detection(tmp_path: Path, run_events: list[dict], payload: bytes) -> None:
    """One byte-identical quarantine copy, one ledger row, one HARD_STOP event."""
    copies = _quarantine_copies(tmp_path)
    assert len(copies) == 1 and copies[0].read_bytes() == payload
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["book"] == "self_directed"
    assert rows[0]["event"] == "account_state_invalid"
    assert rows[0]["status"] == "quarantined"
    assert rows[0]["source_sha256"] == hashlib.sha256(payload).hexdigest()
    assert rows[0]["recoverable"] is True
    hard = [e for e in run_events if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1
    assert hard[0]["kind"] == "account_state_invalid"
    assert hard[0]["job"] == "self_directed"
    assert hard[0]["book"] == "self_directed"
    assert hard[0]["step"] == "load_account"
    assert hard[0]["status"] == "error"
    assert hard[0]["actor"] == "deterministic_engine"
    assert hard[0]["extra"]["quarantine_status"] == "quarantined"
    assert hard[0]["extra"]["recoverable"] is True
    assert hard[0]["extra"]["source_sha256"] == hashlib.sha256(payload).hexdigest()


def _assert_refusal(excinfo, expected_problem: str | None = None) -> None:
    err = excinfo.value
    assert isinstance(err, RuntimeError) and err.__class__.__name__ == "SelfDirectedAccountInvalid"
    assert err.reason_code == "self_directed_account_invalid"
    assert err.problems
    assert err.record is not None
    if expected_problem:
        assert expected_problem in err.problems


# ── 1. the invalid classes fail closed everywhere ─────────────────────────────

@pytest.mark.parametrize("case", sorted(INVALID_CASES))
def test_invalid_book_class_fails_closed_everywhere(
        sd_paths: Path, run_events_recorder: list[dict], case: str) -> None:
    """Unparseable (truncated / empty / non-UTF-8) and schema-invalid books: _load_account,
    book(read_only=True) and place_order (open AND closed) all raise; the original bytes stay
    in place with one identical quarantine copy; one ledger row + one HARD_STOP event; the
    refused order creates neither fills.jsonl nor pending.json."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    payload = INVALID_CASES[case]
    (tmp_path / "account.json").write_bytes(payload)

    with pytest.raises(sd.SelfDirectedAccountInvalid) as e1:
        sd._load_account()
    _assert_refusal(e1, "unparseable" if case in
                    ("truncated_json", "empty_file", "non_utf8") else None)
    if case == "cash_string":
        _assert_refusal(e1, "cash_invalid")
    if case == "cash_true":
        _assert_refusal(e1, "cash_invalid")
    if case == "cash_nan":
        _assert_refusal(e1, "cash_invalid")
    if case == "positions_list":
        _assert_refusal(e1, "positions_invalid")
    if case == "position_missing_avg_cost":
        _assert_refusal(e1, "position_avg_cost_invalid:AAA")
    if case == "starting_nav_zero":
        _assert_refusal(e1, "starting_nav_invalid")

    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.book(prices={}, read_only=True, resolve_missing_prices=False)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=True)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=False)

    assert (tmp_path / "account.json").read_bytes() == payload, \
        "the original invalid file must be untouched, never replaced"
    _assert_single_detection(tmp_path, run_events_recorder, payload)
    assert not (tmp_path / "fills.jsonl").exists()
    assert not (tmp_path / "pending.json").exists()


def test_unreadable_book_fails_closed_with_a_failed_quarantine_record(
        sd_paths: Path, run_events_recorder: list[dict], monkeypatch) -> None:
    """c) unreadable: the read itself fails. No copy is possible, so the record status is
    `quarantine_failed`; the original stays; each detection is audited (C3's no-row-on-recheck
    guarantee is bytes-keyed — a failed quarantine has no bytes to dedupe on — so unlike the
    byte-backed classes every failed detection appends its own row + event)."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    account_path = tmp_path / "account.json"
    payload = _valid_book_bytes()
    account_path.write_bytes(payload)
    _deny_read_bytes_for(monkeypatch, account_path)

    with pytest.raises(sd.SelfDirectedAccountInvalid) as e1:
        sd._load_account()
    assert e1.value.problems == ["unreadable:PermissionError"]
    assert e1.value.record["status"] == "quarantine_failed"
    assert e1.value.record["quarantine_file"] is None

    # the FIRST detection: exactly one ledger row + one HARD_STOP event
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["book"] == "self_directed"
    assert rows[0]["status"] == "quarantine_failed"
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1
    assert hard[0]["extra"]["quarantine_status"] == "quarantine_failed"
    assert hard[0]["extra"]["quarantine_file"] is None

    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.book(prices={}, read_only=True, resolve_missing_prices=False)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=True)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=False)

    assert _quarantine_copies(tmp_path) == [], "no copy can exist for an unreadable file"
    # every detection, repeats included, is audited and carries the same shape
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 4
    assert all(r["book"] == "self_directed" and r["status"] == "quarantine_failed"
               for r in rows)
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 4
    assert all(e["kind"] == "account_state_invalid" and e["book"] == "self_directed"
               for e in hard)
    # status stays a read-only probe on an unreadable file: INVALID, never raising
    status = sd.account_file_status()
    assert status["status"] == "INVALID"
    assert status["problems"] == ["unreadable:PermissionError"]
    assert not (tmp_path / "fills.jsonl").exists()
    assert not (tmp_path / "pending.json").exists()


# ── 2. a legitimate new book ──────────────────────────────────────────────────

def test_missing_file_is_a_legitimate_new_book(
        sd_paths: Path, run_events_recorder: list[dict]) -> None:
    """No account file at all is the normal first run: a fresh book, nothing written,
    nothing quarantined. A market-open buy with an injected price then fills and creates
    account.json."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    assert not (tmp_path / "account.json").exists()

    state = sd._load_account()
    assert state["cash"] == 1_000_000.0
    assert state["positions"] == {}

    assert not (tmp_path / "account.json").exists(), "loading a new book must write nothing"
    assert _quarantine_copies(tmp_path) == []
    assert not (tmp_path / "account_quarantine.jsonl").exists()
    assert run_events_recorder == []

    r = sd.place_order("AAA", "buy", 10, price=25.0, market_open=True)
    assert r["ok"] is True and r["status"] == "filled"
    assert r["cash_after"] == 999_750.0
    assert (tmp_path / "account.json").exists()
    saved = json.loads((tmp_path / "account.json").read_text(encoding="utf-8"))
    assert saved["positions"]["AAA"] == {"shares": 10.0, "avg_cost": 25.0}
    assert run_events_recorder == []


# ── 3. idempotent re-detection ────────────────────────────────────────────────

def test_redetection_is_idempotent_and_new_bytes_get_their_own_copy(
        sd_paths: Path, run_events_recorder: list[dict]) -> None:
    """Loading the same invalid bytes 3 times: every call raises, but the copy, the ledger
    row and the event happen once. Different invalid bytes get a second copy + row."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    payload1 = INVALID_CASES["truncated_json"]
    (tmp_path / "account.json").write_bytes(payload1)

    for _ in range(3):
        with pytest.raises(sd.SelfDirectedAccountInvalid):
            sd._load_account()

    copies = _quarantine_copies(tmp_path)
    assert len(copies) == 1 and copies[0].read_bytes() == payload1
    assert len(_ledger_rows(tmp_path)) == 1
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 1

    payload2 = INVALID_CASES["cash_string"]
    assert payload2 != payload1
    (tmp_path / "account.json").write_bytes(payload2)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd._load_account()

    copies = _quarantine_copies(tmp_path)
    assert len(copies) == 2
    assert sorted(c.read_bytes() for c in copies) == sorted([payload1, payload2])
    assert len(_ledger_rows(tmp_path)) == 2
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 2


# ── 4. mutation-style: no fresh-book fallback anywhere ────────────────────────

def test_invalid_book_is_never_overwritten_and_the_fresh_branch_is_unreachable(
        sd_paths: Path, run_events_recorder: list[dict], monkeypatch) -> None:
    """With `_fresh_account` replaced by a tripwire, every invalid-file path still fails
    closed: the fresh branch is unreachable on an existing invalid file, account.json is
    byte-identical afterwards, and mark() writes no NAV row."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    payload = INVALID_CASES["positions_list"]
    (tmp_path / "account.json").write_bytes(payload)

    def _tripwire() -> dict:
        raise AssertionError("fresh-book fallback reached")

    monkeypatch.setattr(sd, "_fresh_account", _tripwire)
    assert sd._fresh_account is _tripwire, "the tripwire must be armed"

    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd._load_account()
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.book(prices={}, read_only=True, resolve_missing_prices=False)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 5, price=10.0, market_open=True)
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 5, price=10.0, market_open=False)

    assert sd.mark(prices={"AAA": 12.0}) is None
    assert sd.publish(prices={"AAA": 12.0}) is None
    assert not (tmp_path / "nav_history.jsonl").exists()

    good_state = {"inception_date": "2026-01-05", "starting_nav": 1_000_000.0,
                  "cash": 900_000.0, "positions": {"BBB": {"shares": 2.0, "avg_cost": 50.0}}}
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd._save_account(good_state)

    assert (tmp_path / "account.json").read_bytes() == payload, \
        "account.json must be byte-identical after every refused path"
    fresh_book_bytes = json.dumps(
        {"inception_date": "2026-01-01", "starting_nav": 1_000_000.0,
         "cash": 1_000_000.0, "positions": {}}, indent=2, default=str).encode("utf-8")
    assert (tmp_path / "account.json").read_bytes() != fresh_book_bytes, \
        "the surviving book must never be a fresh $1M book"
    assert not (tmp_path / "fills.jsonl").exists()
    assert not (tmp_path / "pending.json").exists()


# ── 5. _save_account refuses ──────────────────────────────────────────────────

def test_save_refuses_an_invalid_in_memory_state_without_touching_disk(
        sd_paths: Path, run_events_recorder: list[dict]) -> None:
    """An invalid in-memory state is refused BEFORE anything is written: the on-disk file is
    untouched and nothing is quarantined (the disk file is still valid)."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    payload = _valid_book_bytes()
    (tmp_path / "account.json").write_bytes(payload)

    with pytest.raises(sd.SelfDirectedAccountInvalid) as err:
        sd._save_account({"cash": "lots", "positions": {}})
    assert err.value.problems == ["cash_invalid"]
    assert err.value.record is None

    assert (tmp_path / "account.json").read_bytes() == payload
    assert _quarantine_copies(tmp_path) == []
    assert not (tmp_path / "account_quarantine.jsonl").exists()
    assert run_events_recorder == []


def test_save_refuses_to_overwrite_an_existing_invalid_file(
        sd_paths: Path, run_events_recorder: list[dict]) -> None:
    """Nothing may overwrite an INVALID book on disk: it is quarantined and the save raises."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    bad_payload = INVALID_CASES["cash_string"]
    (tmp_path / "account.json").write_bytes(bad_payload)
    good_state = {"inception_date": "2026-01-05", "starting_nav": 1_000_000.0,
                  "cash": 900_000.0, "positions": {"AAA": {"shares": 5.0, "avg_cost": 10.0}}}

    with pytest.raises(sd.SelfDirectedAccountInvalid) as err:
        sd._save_account(good_state)
    assert err.value.problems == ["cash_invalid"]

    assert (tmp_path / "account.json").read_bytes() == bad_payload
    _assert_single_detection(tmp_path, run_events_recorder, bad_payload)


# ── 6. account_file_status — read-only probe ──────────────────────────────────

def test_account_file_status_reads_without_writing(sd_paths: Path,
                                                   run_events_recorder: list[dict]) -> None:
    """MISSING / VALID / INVALID classification; every probe call leaves the tmp tree (paths
    and bytes) exactly as it found it and emits no run event, proving the probe never writes."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths

    def tree() -> dict[str, bytes | None]:
        return {p.relative_to(tmp_path).as_posix(): (p.read_bytes() if p.is_file() else None)
                for p in tmp_path.rglob("*")}

    def probe(**kwargs) -> dict:
        before = tree()
        result = sd.account_file_status(**kwargs)
        assert tree() == before, "account_file_status must never write anything"
        return result

    missing = probe()
    assert missing == {"status": "MISSING", "path": str(tmp_path / "account.json"),
                       "sha256": None, "size": None, "problems": []}

    payload = _valid_book_bytes()
    (tmp_path / "account.json").write_bytes(payload)
    valid = probe()
    assert valid["status"] == "VALID"
    assert valid["problems"] == []
    assert valid["sha256"] == hashlib.sha256(payload).hexdigest()
    assert valid["size"] == len(payload)

    bad_payload = INVALID_CASES["cash_string"]
    (tmp_path / "account.json").write_bytes(bad_payload)
    invalid = probe()
    assert invalid["status"] == "INVALID"
    assert invalid["problems"] == ["cash_invalid"]
    assert invalid["sha256"] == hashlib.sha256(bad_payload).hexdigest()

    # the probe overrode path must work too, without touching the default one
    other = tmp_path / "elsewhere.json"
    other.write_bytes(bad_payload)
    assert probe(path=other)["status"] == "INVALID"
    assert probe()["status"] == "INVALID"

    assert _quarantine_copies(tmp_path) == []
    assert _ledger_rows(tmp_path) == []
    assert run_events_recorder == []


# ── 7. a valid live-shaped file survives a mark/save round trip ───────────────

def test_valid_live_shaped_file_round_trips(sd_paths: Path) -> None:
    """Extra mark/benchmark keys are allowed everywhere; a legacy file may omit starting_nav
    and inception_date; a mark + save keeps the file VALID."""
    from portfolio import self_directed as sd
    tmp_path = sd_paths
    live = {
        "inception_date": "2026-01-05",
        "starting_nav": 1_000_000.0,
        "cash": 500_000.0,
        "positions": {
            "AAA": {"shares": 1000.0, "avg_cost": 25.0, "current_price": 27.5,
                    "current_price_source": "portfolio_mark",
                    "current_price_asof": "2026-06-01"},
        },
        "spy_shares": 2000.0,
        "spy_inception_price": 500.0,
    }
    payload = json.dumps(live, indent=2).encode("utf-8")
    (tmp_path / "account.json").write_bytes(payload)

    state = sd._load_account()
    assert state["cash"] == 500_000.0
    assert state["positions"]["AAA"]["shares"] == 1000.0
    assert state["spy_shares"] == 2000.0
    assert sd.account_file_status()["status"] == "VALID"

    row = sd.mark(prices={"AAA": 30.0, "SPY": 500.0}, asof="2026-06-02")
    assert row is not None and row["nav"] == 530_000.0        # 500k cash + 1000 * 30
    assert row["spy_nav"] == 1_000_000.0

    assert sd.account_file_status()["status"] == "VALID", "a mark/save round trip stays VALID"
    reloaded = sd._load_account()
    assert reloaded["positions"]["AAA"]["current_price"] == 30.0
    assert reloaded["positions"]["AAA"]["current_price_asof"] == "2026-06-02"
    b = sd.book(prices={"AAA": 30.0, "SPY": 500.0}, read_only=True,
                resolve_missing_prices=False)
    assert b["nav"] == 530_000.0

    # a legacy file: starting_nav and inception_date both ABSENT are allowed
    legacy_payload = json.dumps({"cash": 1_000_000.0, "positions": {}}, indent=2).encode("utf-8")
    (tmp_path / "account.json").write_bytes(legacy_payload)
    legacy = sd._load_account()
    assert legacy["starting_nav"] == 1_000_000.0
    assert legacy["inception_date"]
    assert sd.account_file_status()["status"] == "VALID"
    assert _quarantine_copies(tmp_path) == []


# ── 8. the dashboard routes surface the typed reason ──────────────────────────

def test_web_book_route_reports_the_typed_invalid_account(
        sd_paths: Path, monkeypatch) -> None:
    from app import web
    from portfolio import self_directed
    tmp_path = sd_paths
    (tmp_path / "account.json").write_bytes(INVALID_CASES["cash_string"])
    monkeypatch.setattr(web, "_live_prices", lambda tickers, **_kw: {})
    monkeypatch.setattr(self_directed, "_market_status",
                        lambda: {"is_open": False, "session": "closed", "next_open": None})

    response = web.api_self_directed()
    assert response.status_code == 200
    raw = response.body if isinstance(response.body, bytes) else response.body.encode()
    data = json.loads(raw)
    assert data["status"] == "unavailable"
    assert data["reason_code"] == "self_directed_account_invalid"
    assert data["problems"] == ["cash_invalid"]
    assert isinstance(data["quarantine_file"], str) and data["quarantine_file"]
    assert data["quarantine_file"].startswith("account.quarantine.")
    assert data["nav"] is None
    assert b"1000000" not in raw, "no fabricated funded book may appear on the wire"


def test_web_history_route_reports_the_typed_invalid_account(
        sd_paths: Path, monkeypatch) -> None:
    from app import web
    from portfolio import self_directed
    tmp_path = sd_paths
    (tmp_path / "account.json").write_bytes(INVALID_CASES["cash_string"])
    (tmp_path / "pending.json").write_text(json.dumps([
        {"order_id": "AAA-1", "ticker": "AAA", "side": "buy", "shares": 1.0,
         "placed_at": "2026-06-01T14:30:00+00:00", "status": "pending"},
    ]), encoding="utf-8")
    monkeypatch.setattr(web, "_live_prices", lambda tickers, **_kw: {})
    monkeypatch.setattr(self_directed, "_market_open", lambda now=None: True)

    response = web.api_self_directed_history()
    assert response.status_code == 200
    data = json.loads(response.body)
    assert data["status"] == "unavailable"
    assert data["reason_code"] == "self_directed_account_invalid"
    assert data["problems"] == ["cash_invalid"]
    assert data["history"] == []
    assert data["pending"] == []


def test_web_order_route_reports_the_typed_invalid_account(
        sd_paths: Path, monkeypatch) -> None:
    from app import web
    from portfolio import self_directed
    tmp_path = sd_paths
    payload = INVALID_CASES["cash_string"]
    (tmp_path / "account.json").write_bytes(payload)
    monkeypatch.setattr(web, "_live_prices", lambda tickers, **_kw: {})
    monkeypatch.setattr(self_directed, "_market_open", lambda now=None: False)

    response = web.api_self_directed_order(web._OrderReq(ticker="AAA", side="buy", shares=1))
    assert response.status_code == 500
    data = json.loads(response.body)
    assert data["ok"] is False
    assert data["reason_code"] == "self_directed_account_invalid"
    assert data["problems"] == ["cash_invalid"]
    assert data["error"]

    assert (tmp_path / "account.json").read_bytes() == payload, "the order must not touch disk"
    assert not (tmp_path / "pending.json").exists()
    assert not (tmp_path / "fills.jsonl").exists()


# ===========================================================================
# W3-E14 — book paths fail closed; load/save never create a book directory.
# Everything below exercises the PRODUCTION behaviour: the conftest book-dir
# bootstrap shim is OFF for tests marked ``strict_book_dirs``.
# ===========================================================================

import errno
import os

_BOOKS = "books"

_VALID_STATE: dict = {"inception_date": "2026-01-05", "starting_nav": 1_000_000.0,
                      "cash": 900_000.0, "positions": {"BBB": {"shares": 2.0, "avg_cost": 50.0}}}

_STAT_FAILURE_CASES: dict[str, OSError] = {
    "eacces": PermissionError(errno.EACCES, "Permission denied"),
    "enotdir": NotADirectoryError(errno.ENOTDIR, "Not a directory"),
    "eloop": OSError(errno.ELOOP, "Too many levels of symbolic links"),
}


@pytest.fixture()
def strict_sd(tmp_path: Path, monkeypatch) -> Path:
    """A REAL books/self_directed + books/published tree (production behaviour — the
    conftest bootstrap shim is OFF under ``strict_book_dirs``), with every module path
    re-pointed into it."""
    from portfolio import self_directed as sd

    books = tmp_path / _BOOKS
    base = books / "self_directed"
    published = books / "published"
    base.mkdir(parents=True, exist_ok=True)
    published.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sd, "_DATA", base)
    monkeypatch.setattr(sd, "_ACCOUNT_PATH", base / "account.json")
    monkeypatch.setattr(sd, "_FILLS_PATH", base / "fills.jsonl")
    monkeypatch.setattr(sd, "_PENDING_PATH", base / "pending.json")
    monkeypatch.setattr(sd, "_THESES_PATH", base / "theses.json")
    monkeypatch.setattr(sd, "_NAV_PATH", base / "nav_history.jsonl")
    monkeypatch.setattr(sd, "_PUBLISHED_PATH", published / "latest.json")
    return base


def _tree(root: Path) -> dict[str, object]:
    """Snapshot every path under root: file bytes, ("link", target) for a symlink, "dir"."""
    out: dict[str, object] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dp = Path(dirpath)
        for name in dirnames + filenames:
            p = dp / name
            rel = p.relative_to(root).as_posix()
            if os.path.islink(p):
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = "dir"
            else:
                out[rel] = p.read_bytes()
    return out


def _deny_stat_for(monkeypatch, target: Path, exc: OSError) -> None:
    """Patch os.stat AND os.lstat so either raises ``exc`` for exactly one path and calls
    through for every other path."""
    target_str = os.fsdecode(os.fspath(target))
    real_stat = os.stat
    real_lstat = os.lstat

    def _deny_stat(path, *args, **kwargs):
        if os.fsdecode(os.fspath(path)) == target_str:
            raise exc
        return real_stat(path, *args, **kwargs)

    def _deny_lstat(path, *args, **kwargs):
        if os.fsdecode(os.fspath(path)) == target_str:
            raise exc
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", _deny_stat)
    monkeypatch.setattr(os, "lstat", _deny_lstat)


def _fresh_tripwire(*_args, **_kwargs):
    raise AssertionError("fresh-book fallback reached")


def _write_tripwire(*_args, **_kwargs):
    raise AssertionError("write reached")


def _assert_path_invalid(excinfo, problem: str) -> None:
    err = excinfo.value
    assert isinstance(err, RuntimeError) and err.__class__.__name__ == "SelfDirectedAccountInvalid"
    assert err.problems == [problem]
    assert err.record is not None
    assert err.record["status"] == "path_invalid"
    assert err.record["quarantine_file"] is None
    assert err.record["source_sha256"] is None
    assert err.record["recoverable"] is True


# ── B1. book dir renamed (unmount simulation) ─────────────────────────────────

@pytest.mark.strict_book_dirs
def test_renamed_book_dir_fails_closed_everywhere_and_creates_nothing(
        strict_sd: Path, run_events_recorder: list[dict], monkeypatch, tmp_path: Path) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    (base / "account.json").write_bytes(_valid_book_bytes())
    base.rename(base.with_name(base.name + ".unmounted"))
    books_root = tmp_path / _BOOKS
    snapshot = _tree(books_root)
    fresh = sd._fresh_account()
    monkeypatch.setattr(sd, "_fresh_account", _fresh_tripwire)
    monkeypatch.setattr(sd, "_atomic_write_bytes", _write_tripwire)

    calls = [
        lambda: sd._load_account(),
        lambda: sd.book(prices={}, read_only=True, resolve_missing_prices=False),
        lambda: sd.place_order("AAA", "buy", 1, price=10.0, market_open=True),
        lambda: sd.place_order("AAA", "buy", 1, price=10.0, market_open=False),
        lambda: sd._save_account(dict(fresh)),
        lambda: sd._save_pending([]),
        lambda: sd._append_fill({"ticker": "AAA"}),
        lambda: sd._save_theses({}),
    ]
    for call in calls:
        with pytest.raises(sd.SelfDirectedAccountInvalid) as excinfo:
            call()
        _assert_path_invalid(excinfo, "data_dir_missing")

    status = sd.account_file_status()
    assert status == {"status": "INVALID", "problems": ["data_dir_missing"],
                      "sha256": None, "size": None, "path": str(base / "account.json")}
    assert sd.mark(prices={"AAA": 12.0}) is None
    assert sd.publish(prices={"AAA": 12.0}) is None

    assert not base.exists()
    assert not (books_root / "published" / "latest.json").exists()
    assert _tree(books_root) == snapshot
    assert run_events_recorder, "the path-invalid raise must emit its HARD_STOP event"
    for event in run_events_recorder:
        assert event["kind"] == "account_state_invalid"
        assert event["severity"] == "HARD_STOP"
        assert event["job"] == "self_directed"
        assert event["book"] == "self_directed"
        assert event["extra"]["quarantine_status"] == "path_invalid"


# ── B2. dangling symlink ──────────────────────────────────────────────────────

@pytest.mark.strict_book_dirs
def test_dangling_symlink_fails_closed_and_writes_nothing(
        strict_sd: Path, run_events_recorder: list[dict], monkeypatch) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    account_path = base / "account.json"
    try:
        os.symlink("missing-target.json", account_path)
    except OSError as exc:  # pragma: no cover — filesystems without symlink support
        pytest.skip(f"symlinks unavailable: {exc!r}")
    snapshot = _tree(base)
    fresh = sd._fresh_account()
    monkeypatch.setattr(sd, "_fresh_account", _fresh_tripwire)
    monkeypatch.setattr(sd, "_atomic_write_bytes", _write_tripwire)

    with pytest.raises(sd.SelfDirectedAccountInvalid) as first:
        sd._load_account()
    _assert_path_invalid(first, "dangling_symlink")
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1
    assert hard[0]["job"] == "self_directed"
    assert hard[0]["book"] == "self_directed"
    assert hard[0]["step"] == "load_account"
    assert hard[0]["extra"]["quarantine_status"] == "path_invalid"

    with pytest.raises(sd.SelfDirectedAccountInvalid) as book_exc:
        sd.book(prices={}, read_only=True, resolve_missing_prices=False)
    _assert_path_invalid(book_exc, "dangling_symlink")
    with pytest.raises(sd.SelfDirectedAccountInvalid) as order_exc:
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=True)
    _assert_path_invalid(order_exc, "dangling_symlink")
    with pytest.raises(sd.SelfDirectedAccountInvalid) as save_exc:
        sd._save_account(dict(fresh))
    _assert_path_invalid(save_exc, "dangling_symlink")

    status = sd.account_file_status()
    assert status["status"] == "INVALID"
    assert status["problems"] == ["dangling_symlink"]

    assert os.readlink(account_path) == "missing-target.json"
    assert not (base / "missing-target.json").exists()
    assert not (base / "account_quarantine.jsonl").exists()
    assert not list(base.glob("account.quarantine.*.json"))
    assert _tree(base) == snapshot


# ── B3. absent file in an existing dir is a new book ──────────────────────────

@pytest.mark.strict_book_dirs
def test_absent_file_in_existing_dir_is_a_new_book(
        strict_sd: Path, run_events_recorder: list[dict]) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    snapshot = _tree(base)
    state = sd._load_account()
    assert state == sd._fresh_account()
    status = sd.account_file_status()
    assert status == {"status": "MISSING", "path": str(base / "account.json"),
                      "sha256": None, "size": None, "problems": []}
    assert run_events_recorder == []
    assert _tree(base) == snapshot

    sd._save_account(sd._fresh_account())
    assert (base / "account.json").is_file()


# ── B4. a stat failure on the file is INVALID (quarantine path) ───────────────

@pytest.mark.strict_book_dirs
@pytest.mark.parametrize("case_id", sorted(_STAT_FAILURE_CASES))
def test_stat_failure_on_account_file_fails_closed(
        strict_sd: Path, run_events_recorder: list[dict], monkeypatch, case_id: str) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    account_path = base / "account.json"
    original = _valid_book_bytes()
    account_path.write_bytes(original)
    exc = _STAT_FAILURE_CASES[case_id]
    expected = f"unreadable:{type(exc).__name__}"
    _deny_stat_for(monkeypatch, account_path, exc)
    fresh = sd._fresh_account()
    monkeypatch.setattr(sd, "_fresh_account", _fresh_tripwire)

    with pytest.raises(sd.SelfDirectedAccountInvalid) as first:
        sd._load_account()
    assert first.value.record["status"] == "quarantine_failed"
    assert first.value.record["problems"] == [expected]
    rows = _ledger_rows(base)
    assert len(rows) == 1
    assert rows[0]["book"] == "self_directed"
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1

    status = sd.account_file_status()
    assert status["status"] == "INVALID"
    assert status["problems"] == [expected]
    assert len(_ledger_rows(base)) == 1
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 1

    with pytest.raises(sd.SelfDirectedAccountInvalid) as book_exc:
        sd.book(prices={}, read_only=True, resolve_missing_prices=False)
    assert book_exc.value.record["status"] == "quarantine_failed"
    assert book_exc.value.record["problems"] == [expected]
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd._save_account(dict(fresh))
    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd.place_order("AAA", "buy", 1, price=10.0, market_open=True)
    assert not (base / "fills.jsonl").exists()
    assert not (base / "pending.json").exists()
    assert sd.mark(prices={"AAA": 12.0}) is None
    assert not (base / "nav_history.jsonl").exists()

    with open(account_path, "rb") as fh:  # os.stat is patched; read without it
        assert fh.read() == original


# ── B5. a REAL ELOOP (no monkeypatch) ─────────────────────────────────────────

@pytest.mark.strict_book_dirs
def test_real_eloop_self_symlink_fails_closed(
        strict_sd: Path, run_events_recorder: list[dict]) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    account_path = base / "account.json"
    account_path.write_bytes(_valid_book_bytes())
    account_path.unlink()
    os.symlink("account.json", account_path)
    fresh = sd._fresh_account()

    with pytest.raises(sd.SelfDirectedAccountInvalid) as excinfo:
        sd._load_account()
    assert excinfo.value.record["problems"] == ["unreadable:OSError"]

    status = sd.account_file_status()
    assert status["status"] == "INVALID"
    assert status["problems"] == ["unreadable:OSError"]

    with pytest.raises(sd.SelfDirectedAccountInvalid):
        sd._save_account(dict(fresh))
    assert os.readlink(account_path) == "account.json"
    assert run_events_recorder, "the unreadable ELOOP must be audited"


# ── B6. read race: vanish and phantom ─────────────────────────────────────────

@pytest.mark.strict_book_dirs
def test_read_race_vanish_returns_a_new_book_without_auditing(
        strict_sd: Path, run_events_recorder: list[dict], monkeypatch) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    account_path = base / "account.json"
    account_path.write_bytes(_valid_book_bytes())
    real_read_bytes = Path.read_bytes

    def vanishing_read(self):
        if self == account_path:
            account_path.unlink()
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", vanishing_read)
    state = sd._load_account()
    assert state == sd._fresh_account()
    assert _ledger_rows(base) == []
    assert run_events_recorder == []


@pytest.mark.strict_book_dirs
def test_read_race_phantom_fails_closed(
        strict_sd: Path, run_events_recorder: list[dict], monkeypatch) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    account_path = base / "account.json"
    account_path.write_bytes(_valid_book_bytes())
    real_read_bytes = Path.read_bytes

    def phantom_read(self):
        if self == account_path:
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", phantom_read)
    with pytest.raises(sd.SelfDirectedAccountInvalid) as excinfo:
        sd._load_account()
    assert excinfo.value.record["problems"] == ["unreadable:FileNotFoundError"]
    assert excinfo.value.record["status"] == "quarantine_failed"
    assert len(_ledger_rows(base)) == 1
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 1


# ── B7. publish never creates its directory ───────────────────────────────────

@pytest.mark.strict_book_dirs
def test_publish_never_creates_its_directory(
        strict_sd: Path, run_events_recorder: list[dict]) -> None:
    from portfolio import self_directed as sd

    base = strict_sd
    (base / "account.json").write_bytes(_valid_book_bytes())
    published = base.parent / "published"
    published.rmdir()

    assert sd.publish(prices={"AAA": 12.0}) is None
    assert not published.exists()
