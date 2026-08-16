"""The daily loop + scheduler wiring."""
from pathlib import Path

import bot  # noqa: F401

# ── W8 legacy-contract pin (2026-07-19): this file exercises pre-W8 build/book mechanics; the v2
# gates are covered by tests/test_flagship_v2_replay.py + tests/test_entry_context_engines.py.
import pytest as _pytest_w8


@_pytest_w8.fixture(autouse=True)
def _w8_legacy_env(monkeypatch):
    monkeypatch.setenv("MASTERMIND_ENTRY_GATE", "0")
    monkeypatch.setenv("MASTERMIND_PROPHET_FEED", "0")
    monkeypatch.setenv("MASTERMIND_ROTATION_IN", "off")
    monkeypatch.setenv("MASTERMIND_NW_DECISION", "off")
    try:
        from portfolio import prophet_feed as _pf
        _pf._reset_cache()
    except Exception:
        pass
    yield
    try:
        from portfolio import prophet_feed as _pf
        _pf._reset_cache()
    except Exception:
        pass


_DB = Path(__file__).resolve().parent.parent / "data" / "bot.db"
_SCHED = Path(__file__).resolve().parent.parent / "data" / "scheduler.sqlite"


def _clean():
    for p in (_DB, _SCHED):
        if p.exists():
            p.unlink()


def test_daily_loop_archived_is_noop():
    """Production Flagship is archived: run_daily must no-op before book work."""
    _clean()
    from bot import daily
    from portfolio import registry
    assert registry.is_archived("flagship")
    out = daily.run_daily(armed=False)
    assert out["archived"] is True
    assert out["book"]["ran"] is False
    assert out["skipped"] == "portfolio_archived"
    _clean()


@_pytest_w8.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "vendor" / "macro" / "data" / "regime" / "latest.json").exists(),
    reason="vendored regime latest.json absent — hosted CI sparse checkout",
)
def test_daily_loop_deterministic(monkeypatch):
    _clean()
    from portfolio import registry
    monkeypatch.setitem(registry._BY_ID["flagship"], "active", True)
    from bot import daily
    out = daily.run_daily(armed=False)            # offline: book only, no Claude bridge
    assert out["book"]["ran"] is True
    assert out["book"]["sleeves"]["cash"] >= 0.05
    # armed steps are skipped without armed=True
    assert "research" not in out
    # 0d perception organs run UNCONDITIONALLY and fail-soft — they must record a status into
    # `out` without ever breaking the daily flow, even absent vendor data (no exception, no error key
    # required, but the key is always present).
    assert "universe_triage" in out
    assert "divergence_clue" in out
    _clean()


def test_scheduler_registers_successor_us_job_only():
    _clean()
    from app import scheduler
    s = scheduler.start()
    if s is None:                                  # apscheduler not installed -> graceful no-op
        return
    ids = {j.id for j in s.get_jobs()}
    assert "autonomous_daily" in ids
    assert not ({"daily_loop", "heavyweight_daily", "etf_daily"} & ids)
    s.shutdown(wait=False)
    _clean()
