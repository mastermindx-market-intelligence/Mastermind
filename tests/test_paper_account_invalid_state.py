"""D-ACCT-1 — an EXISTING-but-invalid account.json fails closed; it is never a fresh book.

The defect: ``_load_account_file`` used to return ``_fresh_account()`` for a corrupt or
schema-invalid account.json, so the next ``_save_account()`` silently reset a live paper
book.  The contract under test:

  * missing file -> fresh book (unchanged);
  * existing but unreadable/unparseable/invalid file -> byte-for-byte quarantine copy,
    one ledger row, one HARD_STOP governance event, and an ``AccountStateInvalid`` raise;
  * nothing may overwrite an invalid book, and an invalid in-memory state is not saved;
  * ``account_file_status`` is a read-only landing-gate instrument;
  * every failure inside the quarantine path still fails closed.

Offline/fast: no network, no live data — every book is redirected into tmp dirs and
``control_plane.run_events.append`` is monkeypatched to a recorder.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import bot  # noqa: F401  -> vendor/macro onto sys.path


# ---------------------------------------------------------------------------
# isolation: default (flagship) book via module globals, non-default via registry
# ---------------------------------------------------------------------------

@pytest.fixture()
def flagship_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the DEFAULT book's module-global paths into a fresh tmp dir."""
    from portfolio import paper_account

    monkeypatch.setattr(paper_account, "_DATA", tmp_path)
    monkeypatch.setattr(paper_account, "_ACCOUNT_PATH", tmp_path / "account.json")
    monkeypatch.setattr(paper_account, "_FILLS_PATH", tmp_path / "fills.jsonl")
    monkeypatch.setattr(paper_account, "_NAV_PATH", tmp_path / "nav_history.jsonl")
    return tmp_path


@pytest.fixture()
def autonomous_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    """Redirect the non-default ``autonomous`` book into a fresh tmp dir."""
    from portfolio import registry

    base = tmp_path / "autonomous"
    original_data_dir = registry.data_dir

    def _data_dir(portfolio_id: str | None = None) -> Path:
        if portfolio_id == "autonomous":
            return base
        return original_data_dir(portfolio_id)

    monkeypatch.setattr(registry, "data_dir", _data_dir)
    return "autonomous", base


@pytest.fixture(params=[None, "autonomous"], ids=["flagship", "autonomous"])
def book(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str | None, Path]:
    """The same isolation for BOTH the default book and a non-default id."""
    from portfolio import paper_account, registry

    if request.param is None:
        monkeypatch.setattr(paper_account, "_DATA", tmp_path)
        monkeypatch.setattr(paper_account, "_ACCOUNT_PATH", tmp_path / "account.json")
        monkeypatch.setattr(paper_account, "_FILLS_PATH", tmp_path / "fills.jsonl")
        monkeypatch.setattr(paper_account, "_NAV_PATH", tmp_path / "nav_history.jsonl")
        return None, tmp_path

    base = tmp_path / request.param
    original_data_dir = registry.data_dir

    def _data_dir(portfolio_id: str | None = None) -> Path:
        if portfolio_id == request.param:
            return base
        return original_data_dir(portfolio_id)

    monkeypatch.setattr(registry, "data_dir", _data_dir)
    return request.param, base


@pytest.fixture(autouse=True)
def run_events_recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture every governance event instead of writing the real ledger.

    Autouse: ANY quarantine in this module must never reach the real
    ``data/governance/run_events.jsonl``, even in tests that don't assert on events.
    """
    from control_plane import run_events

    seen: list[dict] = []
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: seen.append(event))
    return seen


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _live_book() -> dict[str, Any]:
    """A synthetic but LIVE-book-shaped state: every real metadata key present."""
    return {
        "inception_date": "2026-06-20",
        "starting_nav": 1_000_000.0,
        "cash": 412_500.75,
        "positions": {
            "AAPL": {
                "shares": 1200.5,
                "avg_cost": 187.25,
                "current_price": 203.125,
                "current_price_asof": "2026-10-21",
                "current_price_source": "yahoo_cache",
                "current_price_time_kind": "close",
            },
        },
        "spy_shares": 2000.0,
        "spy_inception_price": 500.0,
        "benchmark_symbol": "SPY",
        "cash_yield_through": "2026-10-21",
        "last_paper_transaction_id": "a" * 64,
    }


def _write_book(base: Path, payload: bytes) -> bytes:
    base.mkdir(parents=True, exist_ok=True)
    (base / "account.json").write_bytes(payload)
    return payload


def _invalid_bytes() -> bytes:
    return b'{"cash": "x", "starting_nav": 1.0, "positions": {}}'


def _quarantine_copies(base: Path) -> list[Path]:
    return sorted(base.glob("account.quarantine.*.json"))


def _quarantine_rows(base: Path) -> list[dict]:
    ledger = base / "account_quarantine.jsonl"
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# 1. missing file -> fresh book, nothing quarantined
# ---------------------------------------------------------------------------

def test_missing_file_is_still_a_new_book_and_quarantines_nothing(
    flagship_book: Path, run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    state = paper_account._load_account()
    assert state == paper_account._fresh_account()
    assert paper_account.account_file_status()["status"] == "MISSING"
    assert _quarantine_copies(flagship_book) == []
    assert not (flagship_book / "account_quarantine.jsonl").exists()
    assert run_events_recorder == []


# ---------------------------------------------------------------------------
# 2. a valid live-shaped book loads unchanged, with no quarantine artifacts
# ---------------------------------------------------------------------------

def test_valid_live_book_loads_unchanged_without_quarantine(
    flagship_book: Path, run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    book = _live_book()
    raw = _write_book(flagship_book, json.dumps(book, indent=2).encode("utf-8"))

    loaded = paper_account._load_account_file()
    assert loaded == book
    assert paper_account.validate_account_state(loaded) == []
    assert _quarantine_copies(flagship_book) == []
    assert _quarantine_rows(flagship_book) == []
    assert run_events_recorder == []
    assert (flagship_book / "account.json").read_bytes() == raw


# ---------------------------------------------------------------------------
# 3. parametrized invalid inputs fail closed, on both books
# ---------------------------------------------------------------------------

def _invalid_cases() -> list[tuple[str, bytes, Any, str]]:
    """(case_id, raw bytes, parsed-state-or-None, the one expected problem code)."""
    nan = float("nan")
    cases: list[tuple[str, bytes, Any, str]] = [
        ("garbage_bytes", b"\x00\x01not-json{{{\x9c", None, "unparseable"),
        ("empty_file", b"", None, "unparseable"),
        ("top_level_list", json.dumps([]).encode("utf-8"), [], "not_an_object"),
        ("cash_string",
         json.dumps({"cash": "x", "starting_nav": 1e6, "positions": {}}).encode("utf-8"),
         {"cash": "x", "starting_nav": 1e6, "positions": {}}, "cash_invalid"),
        # the literal NaN that json.dumps produces for a non-finite float
        ("cash_nan",
         json.dumps({"cash": nan, "starting_nav": 1e6, "positions": {}}).encode("utf-8"),
         {"cash": nan, "starting_nav": 1e6, "positions": {}}, "cash_invalid"),
        ("cash_bool",
         json.dumps({"cash": True, "starting_nav": 1e6, "positions": {}}).encode("utf-8"),
         {"cash": True, "starting_nav": 1e6, "positions": {}}, "cash_invalid"),
        ("positions_list",
         json.dumps({"cash": 1.0, "starting_nav": 1e6, "positions": []}).encode("utf-8"),
         {"cash": 1.0, "starting_nav": 1e6, "positions": []}, "positions_invalid"),
        ("starting_nav_zero",
         json.dumps({"cash": 1.0, "starting_nav": 0, "positions": {}}).encode("utf-8"),
         {"cash": 1.0, "starting_nav": 0, "positions": {}}, "starting_nav_invalid"),
        ("starting_nav_missing",
         json.dumps({"cash": 1.0, "positions": {}}).encode("utf-8"),
         {"cash": 1.0, "positions": {}}, "starting_nav_invalid"),
        ("position_shares_nan",
         json.dumps({"cash": 1.0, "starting_nav": 1e6,
                     "positions": {"AAA": {"shares": nan, "avg_cost": 5.0}}}).encode("utf-8"),
         {"cash": 1.0, "starting_nav": 1e6,
          "positions": {"AAA": {"shares": nan, "avg_cost": 5.0}}}, "position_shares_invalid:AAA"),
        ("position_avg_cost_missing",
         json.dumps({"cash": 1.0, "starting_nav": 1e6,
                     "positions": {"AAA": {"shares": 3.0}}}).encode("utf-8"),
         {"cash": 1.0, "starting_nav": 1e6,
          "positions": {"AAA": {"shares": 3.0}}}, "position_avg_cost_invalid:AAA"),
        ("position_string_value",
         json.dumps({"cash": 1.0, "starting_nav": 1e6,
                     "positions": {"AAA": "junk"}}).encode("utf-8"),
         {"cash": 1.0, "starting_nav": 1e6,
          "positions": {"AAA": "junk"}}, "position_not_object:AAA"),
    ]
    return cases


@pytest.mark.parametrize(
    "payload,state,expected_code",
    [case[1:] for case in _invalid_cases()],
    ids=[case[0] for case in _invalid_cases()],
)
def test_invalid_existing_file_fails_closed_and_quarantines(
    book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    payload: bytes,
    state: Any,
    expected_code: str,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = book
    original = _write_book(base, payload)
    original_sha = _sha256(original)

    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account(portfolio_id)

    problems = excinfo.value.record["problems"]
    assert expected_code in problems
    if state is not None:
        assert paper_account.validate_account_state(state) == sorted(problems)
    else:
        assert problems == [expected_code]
    assert f"account state invalid for {portfolio_id or 'flagship'}" in str(excinfo.value)

    # the original bytes are unchanged; the copy is byte-for-byte identical
    assert (base / "account.json").read_bytes() == original
    copies = _quarantine_copies(base)
    assert [copy.name for copy in copies] == [
        f"account.quarantine.{original_sha[:16]}.json"
    ]
    assert copies[0].read_bytes() == original

    # exactly one ledger row and exactly one HARD_STOP governance event
    rows = _quarantine_rows(base)
    assert len(rows) == 1
    assert rows[0]["event"] == "account_state_invalid"
    assert rows[0]["status"] == "quarantined"
    assert rows[0]["recoverable"] is True
    assert rows[0]["source_sha256"] == original_sha
    assert len(run_events_recorder) == 1
    event = run_events_recorder[0]
    assert event["kind"] == "account_state_invalid"
    assert event["severity"] == "HARD_STOP"
    assert event["book"] == (portfolio_id or "flagship")
    assert event["extra"]["problems"] == problems


# ---------------------------------------------------------------------------
# 4. repeats stay failed-closed; a different invalid content gets its own artifacts
# ---------------------------------------------------------------------------

def test_repeated_invalid_loads_are_idempotent_until_content_changes(
    flagship_book: Path, run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    first = _write_book(flagship_book, _invalid_bytes())
    first_sha16 = _sha256(first)[:16]
    for _ in range(3):
        with pytest.raises(paper_account.AccountStateInvalid):
            paper_account._load_account()
    assert [copy.name for copy in _quarantine_copies(flagship_book)] == [
        f"account.quarantine.{first_sha16}.json"
    ]
    assert len(_quarantine_rows(flagship_book)) == 1
    assert len(run_events_recorder) == 1
    assert (flagship_book / "account.json").read_bytes() == first

    second = b'{"cash": "y", "starting_nav": 1.0, "positions": {}}'
    (flagship_book / "account.json").write_bytes(second)
    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account._load_account()
    assert len(_quarantine_copies(flagship_book)) == 2
    assert len(_quarantine_rows(flagship_book)) == 2
    assert len(run_events_recorder) == 2


# ---------------------------------------------------------------------------
# 5. mark() fails closed without writing a nav row
# ---------------------------------------------------------------------------

def test_mark_on_invalid_account_raises_and_writes_nothing(
    flagship_book: Path, run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    original = _write_book(flagship_book, _invalid_bytes())
    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account.mark({"SPY": 500.0}, "2026-01-02")
    assert not (flagship_book / "nav_history.jsonl").exists()
    assert (flagship_book / "account.json").read_bytes() == original


def test_mark_on_invalid_non_default_account_raises_and_writes_nothing(
    autonomous_book: tuple[str, Path],
) -> None:
    from portfolio import paper_account

    portfolio_id, base = autonomous_book
    original = _write_book(base, _invalid_bytes())
    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account.mark({"SPY": 500.0}, "2026-01-02", portfolio_id=portfolio_id)
    assert not (base / "nav_history.jsonl").exists()
    assert (base / "account.json").read_bytes() == original


# ---------------------------------------------------------------------------
# 6. accrue_cash_yield keeps its never-raise contract
# ---------------------------------------------------------------------------

def test_accrue_cash_yield_does_not_raise_and_does_not_save(
    flagship_book: Path,
) -> None:
    from portfolio import paper_account

    original = _write_book(flagship_book, _invalid_bytes())
    result = paper_account.accrue_cash_yield("2026-01-02")  # documented best-effort fallback
    assert isinstance(result, float)
    assert (flagship_book / "account.json").read_bytes() == original


# ---------------------------------------------------------------------------
# 7. the buy/fill path fails closed with no fill row and no save
# ---------------------------------------------------------------------------

def test_execute_fill_on_invalid_account_raises_without_fill_or_save(
    flagship_book: Path,
) -> None:
    from portfolio import paper_account

    original = _write_book(flagship_book, _invalid_bytes())
    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account.execute_fill("AAA", "buy", shares=10.0, price=50.0, asof="2026-01-02")
    assert not (flagship_book / "fills.jsonl").exists()
    assert (flagship_book / "account.json").read_bytes() == original


# ---------------------------------------------------------------------------
# 8/9. _save_account refuses both directions
# ---------------------------------------------------------------------------

def test_save_account_refuses_to_overwrite_an_invalid_file(
    autonomous_book: tuple[str, Path],
) -> None:
    from portfolio import paper_account

    portfolio_id, base = autonomous_book
    original = _write_book(base, _invalid_bytes())
    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account._save_account(paper_account._fresh_account(), portfolio_id)
    assert (base / "account.json").read_bytes() == original
    # the invalid on-disk book was still quarantined before the raise
    assert len(_quarantine_copies(base)) == 1
    assert len(_quarantine_rows(base)) == 1


def test_save_account_refuses_an_invalid_in_memory_state_over_a_valid_file(
    flagship_book: Path,
) -> None:
    from portfolio import paper_account

    raw = _write_book(flagship_book, json.dumps(_live_book(), indent=2).encode("utf-8"))
    bad_state = paper_account._fresh_account()
    bad_state["positions"] = {"AAA": {"shares": "x", "avg_cost": 1.0}}

    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account._save_account(bad_state)

    assert (flagship_book / "account.json").read_bytes() == raw
    # nothing on disk was invalid, so nothing is quarantined
    assert _quarantine_copies(flagship_book) == []
    assert _quarantine_rows(flagship_book) == []


# ---------------------------------------------------------------------------
# 10. strict replay keeps both legacy message strings and the exception family
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,legacy_message",
    [
        (b"{not-json", "account cannot be read during transaction recovery"),
        (b'{"cash": "x"}', "account schema is invalid during transaction recovery"),
    ],
    ids=["unparseable", "schema_invalid"],
)
def test_strict_load_raises_account_state_invalid_with_legacy_messages(
    flagship_book: Path, payload: bytes, legacy_message: str,
) -> None:
    from portfolio import paper_account

    _write_book(flagship_book, payload)
    with pytest.raises(paper_account.PaperTransactionConflict) as excinfo:
        paper_account._load_account_file(strict=True)
    assert isinstance(excinfo.value, paper_account.AccountStateInvalid)
    assert legacy_message in str(excinfo.value)


# ---------------------------------------------------------------------------
# 11. a failing governance sink never softens the raise
# ---------------------------------------------------------------------------

def test_run_event_failure_does_not_soften_the_raise(
    flagship_book: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane import run_events
    from portfolio import paper_account

    original = _write_book(flagship_book, _invalid_bytes())

    def boom(event: dict, **kwargs: Any) -> None:
        raise RuntimeError("event sink down")

    monkeypatch.setattr(run_events, "append", boom)
    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account()
    assert "event sink down" in excinfo.value.record["event_log_error"]
    # the copy still exists, the original is untouched, and no fresh book was saved
    assert _quarantine_copies(flagship_book)[0].read_bytes() == original
    assert (flagship_book / "account.json").read_bytes() == original
    assert len(_quarantine_rows(flagship_book)) == 1


# ---------------------------------------------------------------------------
# 12. a failed quarantine copy still fails closed and keeps the original
# ---------------------------------------------------------------------------

def test_quarantine_copy_failure_keeps_the_raise_and_the_original(
    flagship_book: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio import paper_account

    original = _write_book(flagship_book, _invalid_bytes())
    real_atomic_write = paper_account._atomic_write_bytes

    def failing_atomic_write(path: Path, payload: bytes) -> None:
        if path.name.startswith("account.quarantine."):
            raise OSError("quarantine disk full")
        real_atomic_write(path, payload)

    monkeypatch.setattr(paper_account, "_atomic_write_bytes", failing_atomic_write)
    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account()
    assert excinfo.value.record["status"] == "quarantine_failed"
    assert "quarantine disk full" in excinfo.value.record["quarantine_error"]
    assert excinfo.value.record["recoverable"] is True
    assert _quarantine_copies(flagship_book) == []
    assert (flagship_book / "account.json").read_bytes() == original


# ---------------------------------------------------------------------------
# 13. account_file_status: the read-only landing gate
# ---------------------------------------------------------------------------

def test_account_file_status_classifies_missing_valid_invalid_without_writing(
    flagship_book: Path,
) -> None:
    from portfolio import paper_account

    missing = paper_account.account_file_status()
    assert missing["status"] == "MISSING"
    assert missing["sha256"] is None and missing["size"] is None
    assert missing["problems"] == []
    assert missing["path"] == str(flagship_book / "account.json")

    valid_raw = _write_book(flagship_book, json.dumps(_live_book(), indent=2).encode("utf-8"))
    listing_before = sorted(path.name for path in flagship_book.iterdir())

    valid = paper_account.account_file_status()
    assert valid["status"] == "VALID"
    assert valid["problems"] == []
    assert valid["sha256"] == _sha256(valid_raw)
    assert valid["size"] == len(valid_raw)
    assert valid["path"] == str(flagship_book / "account.json")

    invalid_raw = b'{"cash": "x", "starting_nav": 1.0, "positions": {}}'
    (flagship_book / "account.json").write_bytes(invalid_raw)
    invalid = paper_account.account_file_status()
    assert invalid["status"] == "INVALID"
    assert invalid["problems"] == ["cash_invalid"]
    assert invalid["sha256"] == _sha256(invalid_raw)
    assert invalid["size"] == len(invalid_raw)

    # never writes anything — not even for an INVALID file
    listing_after = sorted(path.name for path in flagship_book.iterdir())
    assert listing_after == listing_before
    assert (flagship_book / "account.json").read_bytes() == invalid_raw


def test_account_file_status_honors_explicit_path_override(
    flagship_book: Path,
) -> None:
    from portfolio import paper_account

    other = flagship_book / "elsewhere"
    other.mkdir()
    raw = _write_book(other, json.dumps({"cash": 10.0, "starting_nav": 100.0,
                                         "positions": {}}).encode("utf-8"))
    status = paper_account.account_file_status("autonomous", path=other / "account.json")
    assert status["status"] == "VALID"
    assert status["path"] == str(other / "account.json")
    assert status["sha256"] == _sha256(raw)

    absent = paper_account.account_file_status(path=other / "nope.json")
    assert absent["status"] == "MISSING"


# ---------------------------------------------------------------------------
# 14. the P&L-wiping cost-basis reset is gone entirely
# ---------------------------------------------------------------------------

def test_reset_cost_basis_entry_point_is_removed() -> None:
    from portfolio import paper_account

    assert not hasattr(paper_account, "reset_cost_basis_to_market")
    assert "reset_cost_basis_to_market" not in inspect.getsource(paper_account)


# ===========================================================================
# W3-E14 — book paths fail closed; load/save never create a book directory.
# Everything below exercises the PRODUCTION behaviour: the conftest book-dir
# bootstrap shim is OFF for tests marked ``strict_book_dirs``.
# ===========================================================================

import ast
import errno
import os
import shutil
import tempfile
import uuid
from typing import Callable

_BOOKS = "books"


@pytest.fixture(params=[None, "autonomous"], ids=["flagship", "autonomous"])
def strict_book(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str | None, Path]:
    """The ``book`` fixture's isolation, plus an EXISTING book dir, for the strict
    (shim-free) E14 fail-closed tests."""
    from portfolio import paper_account, registry

    base = tmp_path / _BOOKS / (request.param or "flagship")
    base.mkdir(parents=True, exist_ok=True)
    if request.param is None:
        monkeypatch.setattr(paper_account, "_DATA", base)
        monkeypatch.setattr(paper_account, "_ACCOUNT_PATH", base / "account.json")
        monkeypatch.setattr(paper_account, "_FILLS_PATH", base / "fills.jsonl")
        monkeypatch.setattr(paper_account, "_NAV_PATH", base / "nav_history.jsonl")
        return None, base
    original_data_dir = registry.data_dir

    def _data_dir(portfolio_id: str | None = None) -> Path:
        if portfolio_id == request.param:
            return base
        return original_data_dir(portfolio_id)

    monkeypatch.setattr(registry, "data_dir", _data_dir)
    return request.param, base


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


def _deny_stat_for(monkeypatch: pytest.MonkeyPatch, target: Path, exc: OSError) -> None:
    """Patch os.stat AND os.lstat so either raises ``exc`` for exactly one path and calls
    through for every other path."""
    target_str = os.fsdecode(os.fspath(target))
    real_stat = os.stat
    real_lstat = os.lstat

    def _deny_stat(path: object, *args: object, **kwargs: object) -> object:
        if os.fsdecode(os.fspath(path)) == target_str:
            raise exc
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def _deny_lstat(path: object, *args: object, **kwargs: object) -> object:
        if os.fsdecode(os.fspath(path)) == target_str:
            raise exc
        return real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", _deny_stat)
    monkeypatch.setattr(os, "lstat", _deny_lstat)


def _fresh_tripwire(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("fresh-book fallback reached")


def _write_tripwire(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("write reached")


def _arm(monkeypatch: pytest.MonkeyPatch, module: object,
         names: tuple[str, ...]) -> None:
    for name in names:
        monkeypatch.setattr(module, name, _fresh_tripwire if name == "_fresh_account"
                            else _write_tripwire)


def _assert_path_invalid(
    excinfo: pytest.ExceptionInfo,
    problem: str,
) -> None:
    record = excinfo.value.record
    assert record is not None
    assert record["problems"] == [problem]
    assert record["status"] == "path_invalid"
    assert record["quarantine_file"] is None
    assert record["source_sha256"] is None
    assert record["recoverable"] is True


_STAT_FAILURE_CASES: dict[str, OSError] = {
    "eacces": PermissionError(errno.EACCES, "Permission denied"),
    "enotdir": NotADirectoryError(errno.ENOTDIR, "Not a directory"),
    "eloop": OSError(errno.ELOOP, "Too many levels of symbolic links"),
}


# ---------------------------------------------------------------------------
# A1. book dir renamed (unmount simulation) — nothing is created or written
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_renamed_book_dir_fails_closed_everywhere_and_creates_nothing(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    _write_book(base, json.dumps(_live_book(), indent=2).encode("utf-8"))
    (base / ".paper_transaction.lock").write_bytes(b"")
    base.rename(base.with_name(base.name + ".unmounted"))
    books_root = tmp_path / _BOOKS
    snapshot = _tree(books_root)
    fresh = paper_account._fresh_account()
    _arm(monkeypatch, paper_account, ("_fresh_account", "_atomic_write_bytes", "_append_jsonl"))

    loaders: list[Callable[[], object]] = [
        lambda: paper_account._load_account_file(portfolio_id),
        lambda: paper_account._load_account(portfolio_id),
        lambda: paper_account._save_account(fresh, portfolio_id),
        lambda: paper_account._save_pending([], portfolio_id),
    ]
    for call in loaders:
        with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
            call()
        _assert_path_invalid(excinfo, "data_dir_missing")
    with pytest.raises(paper_account.AccountStateInvalid) as lock_excinfo:
        with paper_account._paper_transaction_lock(portfolio_id):
            pass
    _assert_path_invalid(lock_excinfo, "data_dir_missing")

    status = paper_account.account_file_status(portfolio_id)
    assert status == {"status": "INVALID", "problems": ["data_dir_missing"],
                      "sha256": None, "size": None,
                      "path": str(base / "account.json")}

    assert not base.exists()
    assert _tree(books_root) == snapshot
    assert run_events_recorder, "the path-invalid raise must emit its HARD_STOP event"
    for event in run_events_recorder:
        assert event["kind"] == "account_state_invalid"
        assert event["severity"] == "HARD_STOP"
        assert event["extra"]["quarantine_status"] == "path_invalid"


# ---------------------------------------------------------------------------
# A2. dangling symlink — invalid, never a new book, and nothing is written
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_dangling_symlink_fails_closed_and_writes_nothing(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    account_path = base / "account.json"
    try:
        os.symlink("missing-target.json", account_path)
    except OSError as exc:  # pragma: no cover — filesystems without symlink support
        pytest.skip(f"symlinks unavailable: {exc!r}")
    (base / ".paper_transaction.lock").write_bytes(b"")
    snapshot = _tree(base)
    fresh = paper_account._fresh_account()
    _arm(monkeypatch, paper_account, ("_fresh_account", "_atomic_write_bytes", "_append_jsonl"))

    with pytest.raises(paper_account.AccountStateInvalid) as first:
        paper_account._load_account_file(portfolio_id)
    _assert_path_invalid(first, "dangling_symlink")
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1
    assert hard[0]["step"] == "load_account"
    assert hard[0]["extra"]["quarantine_status"] == "path_invalid"

    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account(portfolio_id)
    _assert_path_invalid(excinfo, "dangling_symlink")
    with pytest.raises(paper_account.AccountStateInvalid) as save_excinfo:
        paper_account._save_account(fresh, portfolio_id)
    _assert_path_invalid(save_excinfo, "dangling_symlink")

    status = paper_account.account_file_status(portfolio_id)
    assert status["status"] == "INVALID"
    assert status["problems"] == ["dangling_symlink"]

    assert os.readlink(account_path) == "missing-target.json"
    assert not (base / "missing-target.json").exists()
    assert not (base / "account_quarantine.jsonl").exists()
    assert not list(base.glob("account.quarantine.*.json"))
    assert _tree(base) == snapshot


# ---------------------------------------------------------------------------
# A3. absent file in an existing dir is still a legitimate new book
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_absent_file_in_existing_dir_is_a_new_book(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    snapshot = _tree(base)

    state = paper_account._load_account_file(portfolio_id)
    assert state == paper_account._fresh_account()
    status = paper_account.account_file_status(portfolio_id)
    assert status == {"status": "MISSING", "path": str(base / "account.json"),
                      "sha256": None, "size": None, "problems": []}
    assert run_events_recorder == []
    assert _tree(base) == snapshot

    paper_account._save_account(paper_account._fresh_account(), portfolio_id)
    assert (base / "account.json").is_file()


# ---------------------------------------------------------------------------
# A4. a stat failure on the file is INVALID (quarantine path), parametrized
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
@pytest.mark.parametrize("case_id", sorted(_STAT_FAILURE_CASES))
def test_stat_failure_on_account_file_fails_closed(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    account_path = base / "account.json"
    original = _write_book(base, json.dumps(_live_book(), indent=2).encode("utf-8"))
    exc = _STAT_FAILURE_CASES[case_id]
    expected = f"unreadable:{type(exc).__name__}"
    _deny_stat_for(monkeypatch, account_path, exc)
    fresh = paper_account._fresh_account()
    monkeypatch.setattr(paper_account, "_fresh_account", _fresh_tripwire)

    with pytest.raises(paper_account.AccountStateInvalid) as first:
        paper_account._load_account_file(portfolio_id)
    assert first.value.record["status"] == "quarantine_failed"
    assert first.value.record["problems"] == [expected]
    rows = _quarantine_rows(base)
    assert len(rows) == 1
    assert rows[0]["status"] == "quarantine_failed"
    hard = [e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]
    assert len(hard) == 1

    status = paper_account.account_file_status(portfolio_id)
    assert status["status"] == "INVALID"
    assert status["problems"] == [expected]
    assert len(_quarantine_rows(base)) == 1
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 1

    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account._save_account(fresh, portfolio_id)

    with open(account_path, "rb") as fh:  # os.stat is patched; read without it
        assert fh.read() == original


# ---------------------------------------------------------------------------
# A5. a REAL ELOOP (no monkeypatch) — a self-referential symlink is invalid
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_real_eloop_self_symlink_fails_closed(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    account_path = base / "account.json"
    _write_book(base, json.dumps(_live_book(), indent=2).encode("utf-8"))
    account_path.unlink()
    os.symlink("account.json", account_path)
    fresh = paper_account._fresh_account()

    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account_file(portfolio_id)
    assert excinfo.value.record["problems"] == ["unreadable:OSError"]

    status = paper_account.account_file_status(portfolio_id)
    assert status["status"] == "INVALID"
    assert status["problems"] == ["unreadable:OSError"]

    with pytest.raises(paper_account.AccountStateInvalid):
        paper_account._save_account(fresh, portfolio_id)
    assert os.readlink(account_path) == "account.json"
    assert run_events_recorder, "the unreadable ELOOP must be audited"


# ---------------------------------------------------------------------------
# A6. read race: the file vanishes between the stat and the read
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_read_race_vanish_returns_a_new_book_without_auditing(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    account_path = base / "account.json"
    _write_book(base, json.dumps(_live_book(), indent=2).encode("utf-8"))
    real_read_bytes = Path.read_bytes

    def vanishing_read(self: Path) -> bytes:
        if self == account_path:
            account_path.unlink()
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", vanishing_read)
    state = paper_account._load_account_file(portfolio_id)
    assert state == paper_account._fresh_account()
    assert _quarantine_rows(base) == []
    assert run_events_recorder == []


@pytest.mark.strict_book_dirs
def test_read_race_phantom_fails_closed(
    strict_book: tuple[str | None, Path],
    run_events_recorder: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio import paper_account

    portfolio_id, base = strict_book
    account_path = base / "account.json"
    _write_book(base, json.dumps(_live_book(), indent=2).encode("utf-8"))
    real_read_bytes = Path.read_bytes

    def phantom_read(self: Path) -> bytes:
        if self == account_path:
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", phantom_read)
    with pytest.raises(paper_account.AccountStateInvalid) as excinfo:
        paper_account._load_account_file(portfolio_id)
    assert excinfo.value.record["problems"] == ["unreadable:FileNotFoundError"]
    assert excinfo.value.record["status"] == "quarantine_failed"
    assert len(_quarantine_rows(base)) == 1
    assert len([e for e in run_events_recorder if e.get("severity") == "HARD_STOP"]) == 1


# ---------------------------------------------------------------------------
# A7. the low-level writers never create directories
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_low_level_writers_never_create_directories(
    strict_book: tuple[str | None, Path],
) -> None:
    from portfolio import paper_account

    _portfolio_id, base = strict_book
    base.rename(base.with_name(base.name + ".away"))

    with pytest.raises(OSError):
        paper_account._atomic_write_bytes(base / "x.json", b"{}")
    with pytest.raises(OSError):
        paper_account._append_jsonl(base / "fills.jsonl", {"a": 1})
    with pytest.raises(OSError):
        paper_account._ensure_book_subdir(base / "settlement_receipts")
    assert not base.exists()

    base.mkdir()
    paper_account._ensure_book_subdir(base / "settlement_receipts")
    assert (base / "settlement_receipts").is_dir()
    assert sorted(p.name for p in base.iterdir()) == ["settlement_receipts"]


# ---------------------------------------------------------------------------
# A8. _check_book_dir classifies without ever creating
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_check_book_dir_classifies_without_creating(tmp_path: Path) -> None:
    from portfolio import paper_account

    missing = tmp_path / "nope"
    problem, exc = paper_account._check_book_dir(missing)
    assert problem == "data_dir_missing"
    assert isinstance(exc, FileNotFoundError)
    assert not missing.exists()

    regular = tmp_path / "regular.txt"
    regular.write_bytes(b"x")
    assert paper_account._check_book_dir(regular) == ("data_dir_not_directory", None)
    assert regular.read_bytes() == b"x"

    existing = tmp_path / "dir"
    existing.mkdir()
    assert paper_account._check_book_dir(existing) == (None, None)


# ---------------------------------------------------------------------------
# S1. the explicit bootstrap is unreachable from production code
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_bootstrap_book_dir_is_unreachable_from_production_code() -> None:
    root = Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    for folder in ("app", "bot", "brain", "portfolio", "loop", "control_plane", "scripts"):
        base_dir = root / folder
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "bootstrap_book_dir":
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} Name")
                elif isinstance(node, ast.Attribute) and node.attr == "bootstrap_book_dir":
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} Attribute")
                elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                      and node.value == "bootstrap_book_dir"):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} Constant")
    assert offenders == []


# ---------------------------------------------------------------------------
# S2. no mkdir anywhere outside the explicit bootstrap helpers
# ---------------------------------------------------------------------------

@pytest.mark.strict_book_dirs
def test_no_mkdir_outside_the_explicit_bootstrap_helpers() -> None:
    root = Path(__file__).resolve().parent.parent
    allowed = {
        "portfolio/paper_account.py": {"bootstrap_book_dir", "_ensure_book_subdir"},
        "portfolio/self_directed.py": {"bootstrap_book_dir"},
    }
    violations: list[str] = []
    for rel, allowed_fns in allowed.items():
        path = root / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        stack: list[str] = []

        class _Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                stack.append(node.name)
                self.generic_visit(node)
                stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in {"mkdir", "makedirs"}:
                    if not stack or stack[-1] not in allowed_fns:
                        violations.append(f"{rel}:{node.lineno} inside {stack or '<module>'}")
                self.generic_visit(node)

        _Visitor().visit(tree)
    assert violations == []


# ---------------------------------------------------------------------------
# S3. the conftest shim never applies OUTSIDE the session basetemp (NOT strict)
# ---------------------------------------------------------------------------

def test_shim_leaves_dirs_outside_basetemp_missing(tmp_path: Path) -> None:
    from portfolio import paper_account

    outside = Path(tempfile.gettempdir()) / f"e14-shim-{uuid.uuid4().hex}" / "book"
    try:
        assert paper_account._check_book_dir(outside)[0] == "data_dir_missing"
        assert not outside.exists()
    finally:
        shutil.rmtree(outside.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# S4. the conftest shim bootstraps missing book dirs under basetemp (NOT strict)
# ---------------------------------------------------------------------------

def test_shim_bootstraps_missing_book_dirs_under_basetemp(tmp_path: Path) -> None:
    from portfolio import paper_account

    target = tmp_path / "auto"
    assert paper_account._check_book_dir(target) == (None, None)
    assert target.is_dir()
