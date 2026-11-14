"""Regression coverage for Self-Directed failures inside the daily mark scheduler sweep.

The scheduler is the owner of run-health projection.  Self-Directed may refuse a mark when the
canonical price layer cannot truthfully value every held line; that refusal must remain per-book
best-effort, but it must never disappear behind a bare ``except: pass``.
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.strict_book_dirs


def _isolate_self_directed_sweep(monkeypatch):
    from app import scheduler
    from control_plane import locks
    from portfolio import marks, registry, self_directed

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(locks, "acquire_or_log", lambda *args, **kwargs: _Lock())

    events: list[tuple[str, str, str, str, str]] = []
    ledger_ends: list[tuple[str, str | None]] = []

    monkeypatch.setattr(scheduler, "_MARK_BOOK_IDS", [])
    monkeypatch.setattr(scheduler, "_today_iso", lambda: "2026-09-16")
    monkeypatch.setattr(scheduler, "_is_trading_date", lambda venue, asof: True)
    monkeypatch.setattr(scheduler, "_build_benchmark_ledger", lambda asof, union: None)
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *args, **kwargs: "handle")
    monkeypatch.setattr(
        scheduler,
        "_ledger_end",
        lambda handle, status, severity=None, extra=None: ledger_ends.append((status, severity)),
    )
    monkeypatch.setattr(
        scheduler,
        "_step_failed_event",
        lambda job, book, step, exc, severity="ADVISORY_ONLY": events.append(
            (job, book, step, type(exc).__name__, severity)
        ),
    )
    monkeypatch.setattr(registry, "active_ids", lambda include_self_directed=False: [])
    monkeypatch.setattr(marks, "prices_for", lambda symbols, asof, **kwargs: {})
    monkeypatch.setattr(marks, "mark_one", lambda ticker, asof: 123.0)
    monkeypatch.setattr(
        self_directed,
        "_load_account",
        lambda: {"positions": {"AAPL": {"shares": 2.0, "avg_cost": 100.0}}},
    )
    return scheduler, self_directed, events, ledger_ends


def test_daily_mark_projects_self_directed_mark_refusal_as_freeze(monkeypatch) -> None:
    scheduler, self_directed, events, ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    published = []

    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))

    def _refuse_mark(**kwargs):
        raise self_directed.SelfDirectedMarkUnavailable("AAPL unavailable")

    monkeypatch.setattr(self_directed, "mark", _refuse_mark)
    monkeypatch.setattr(self_directed, "publish", lambda **kwargs: published.append(kwargs))

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "mark:self_directed", "SelfDirectedMarkUnavailable", "FREEZE")
    ]
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None
    assert published == [], "publication must not run after the truthful mark refused"
    assert ledger_ends == [("ok", None)], "one bad book remains best-effort for the sweep"


def test_daily_mark_projects_self_directed_publish_failure_as_freeze(monkeypatch) -> None:
    scheduler, self_directed, events, _ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))
    monkeypatch.setattr(self_directed, "mark", lambda **kwargs: {"nav": 1_000_000.0})

    def _fail_publish(**kwargs):
        raise OSError("publication unavailable")

    monkeypatch.setattr(self_directed, "publish", _fail_publish)

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "publish:self_directed", "OSError", "FREEZE")
    ]
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None


def test_daily_mark_projects_self_directed_setup_failure_as_freeze(monkeypatch) -> None:
    scheduler, self_directed, events, _ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))

    def _fail_load():
        raise ValueError("bad account state")

    monkeypatch.setattr(self_directed, "_load_account", _fail_load)

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "self_directed_setup", "ValueError", "FREEZE")
    ]
    assert resolver_calls == []


def test_daily_mark_projects_resolver_cleanup_failure_as_freeze(monkeypatch) -> None:
    scheduler, self_directed, events, _ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []

    def _resolver(fn):
        resolver_calls.append(fn)
        if fn is None:
            raise RuntimeError("cleanup failed")

    monkeypatch.setattr(self_directed, "set_price_resolver", _resolver)
    monkeypatch.setattr(self_directed, "mark", lambda **kwargs: {"nav": 1_000_000.0})
    monkeypatch.setattr(self_directed, "publish", lambda **kwargs: {"nav": 1_000_000.0})

    scheduler._daily_mark_job()

    assert events == [
        (
            "daily_mark",
            "self_directed",
            "self_directed_resolver_cleanup",
            "RuntimeError",
            "FREEZE",
        )
    ]
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None


def test_daily_mark_success_stays_quiet_and_cleans_resolver(monkeypatch) -> None:
    scheduler, self_directed, events, _ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    calls = []
    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))
    monkeypatch.setattr(self_directed, "mark", lambda **kwargs: calls.append(("mark", kwargs)) or {"nav": 1_000_000.0})
    monkeypatch.setattr(self_directed, "publish", lambda **kwargs: calls.append(("publish", kwargs)) or {"nav": 1_000_000.0})

    scheduler._daily_mark_job()

    assert events == []
    assert [name for name, _ in calls] == ["mark", "publish"]
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None


def test_daily_mark_projects_none_mark_as_freeze_without_publication(monkeypatch):
    scheduler, self_directed, events, ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    published = []
    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))
    monkeypatch.setattr(self_directed, "mark", lambda **kwargs: None)
    monkeypatch.setattr(self_directed, "publish", lambda **kwargs: published.append(kwargs))

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "mark:self_directed", "SelfDirectedMarkUnavailable", "FREEZE")
    ]
    assert published == []
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None
    assert ledger_ends == [("ok", None)]


def test_daily_mark_projects_none_publication_as_freeze(monkeypatch):
    scheduler, self_directed, events, ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    resolver_calls = []
    monkeypatch.setattr(self_directed, "set_price_resolver", lambda fn: resolver_calls.append(fn))
    monkeypatch.setattr(self_directed, "mark", lambda **kwargs: {"nav": 1_000_000.0})
    monkeypatch.setattr(self_directed, "publish", lambda **kwargs: None)

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "publish:self_directed", "SelfDirectedMarkUnavailable", "FREEZE")
    ]
    assert len(resolver_calls) == 2 and callable(resolver_calls[0]) and resolver_calls[1] is None
    assert ledger_ends == [("ok", None)]


def test_real_daily_mark_refusal_preserves_account_and_last_publication(tmp_path, monkeypatch):
    from portfolio import marks, self_directed as SD

    real_load = SD._load_account
    scheduler, self_directed, events, ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    monkeypatch.setattr(SD, "_load_account", real_load)
    data = tmp_path / "self_directed"
    for name, value in {
        "_DATA": data,
        "_ACCOUNT_PATH": data / "account.json",
        "_FILLS_PATH": data / "fills.jsonl",
        "_PENDING_PATH": data / "pending.json",
        "_THESES_PATH": data / "theses.json",
        "_NAV_PATH": data / "nav_history.jsonl",
        "_PUBLISHED_PATH": tmp_path / "published" / "latest.json",
    }.items():
        monkeypatch.setattr(SD, name, value)
    SD.bootstrap_book_dir()
    SD.set_price_resolver(None)
    SD._save_account({
        "inception_date": "2026-05-01",
        "starting_nav": 1_000_000.0,
        "cash": 999_800.0,
        "positions": {"AAPL": {"shares": 2.0, "avg_cost": 100.0}},
    })
    prior = {"schema": "portfolio.v1", "portfolio_id": "self_directed", "as_of": "2026-09-15", "nav": 999_987.0}
    SD._PUBLISHED_PATH.write_text(json.dumps(prior))
    account_bytes = SD._ACCOUNT_PATH.read_bytes()
    publication_bytes = SD._PUBLISHED_PATH.read_bytes()
    monkeypatch.setattr(marks, "mark_one", lambda ticker, asof: None)

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "mark:self_directed", "SelfDirectedMarkUnavailable", "FREEZE")
    ]
    assert SD._ACCOUNT_PATH.read_bytes() == account_bytes
    assert SD._PUBLISHED_PATH.read_bytes() == publication_bytes
    assert not SD._NAV_PATH.exists()
    assert SD._price_resolver is None
    assert ledger_ends == [("ok", None)]


def test_daily_mark_skips_self_directed_when_book_lock_is_held(monkeypatch) -> None:
    scheduler, self_directed, events, ledger_ends = _isolate_self_directed_sweep(monkeypatch)
    from control_plane import locks

    monkeypatch.setattr(locks, "acquire_or_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        self_directed,
        "mark",
        lambda **kwargs: pytest.fail("mark must not run without book:self_directed lock"),
    )
    monkeypatch.setattr(
        self_directed,
        "publish",
        lambda **kwargs: pytest.fail("publish must not run without book:self_directed lock"),
    )

    scheduler._daily_mark_job()

    assert events == [
        ("daily_mark", "self_directed", "lock_held:self_directed", "RuntimeError", "ADVISORY_ONLY")
    ]
    assert ledger_ends == [("ok", None)]
