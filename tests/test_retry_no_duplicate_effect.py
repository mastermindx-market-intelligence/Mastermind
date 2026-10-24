"""L-R4 regression fences: an ambiguous retry / re-decide never duplicates a target or a fill.

Four fences (each test's docstring names the change that would break it):

A. provider waterfall — an UNCLASSIFIED provider error must end the rung loop (replaying
   a turn whose typed tools may already have run could submit a second target), while the
   all-cooling marker / a classified auth-quota failure still advances (control).
B. scheduler retry — `_maybe_schedule_brain_retry` schedules nothing without a fresh
   ``brain_pool_exhausted`` marker, and caps at brain.retry_policy.MAX_RETRIES_PER_DAY
   one-shot jobs per job per UTC day with distinct ids.
C. decision rows — a retry for the same asof keeps exactly one row: substantive
   supersedes substantive, a barren re-run never erases a substantive book, and rows for
   other asofs are preserved in order.
D. settlement — repeated closed-session re-decides leave exactly ONE pending target
   (latest-wins) and zero fills; the open settle fills only that target exactly once and
   is idempotent; an earlier queued row is never marked executed with a later target's
   fills.

Paper-only: every test runs against tmp_path via monkeypatch (registry._ROOT), never the
real data/ directory, with no network, no live model, and no bot run.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone

AUTONOMOUS = "autonomous"


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _submission(summary: str, ticker: str, weight: float) -> dict:
    """A minimal accepted structured submission (mastermind.target_book.v2)."""
    return {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker,
            "weight": weight,
            "action": "add",
            "action_effective": "add",
            "rationale": summary,
        }],
        "summary": summary,
    }


def _seed_account() -> None:
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        AUTONOMOUS,
    )


def _fills(pid: str) -> list[dict]:
    from portfolio import paper_account

    return paper_account._load_jsonl(paper_account._paths(pid)["fills"])


def _decision_rows(pid: str) -> list[dict]:
    from portfolio import registry

    path = registry.data_dir(pid) / "decisions.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _receipt_files(pid: str) -> list[str]:
    """Every retained settlement receipt (active outbox + acknowledged archive)."""
    from portfolio import paper_account

    root = paper_account._settlement_receipt_dir(pid)
    if not root.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.json"))


def _run_events_written(tmp_path) -> list[dict]:
    path = tmp_path / "data" / "governance" / "run_events.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# A. waterfall: an unclassified provider error never replays the turn
# ---------------------------------------------------------------------------

def _waterfall(monkeypatch, rungs: list[dict], results: list[dict]):
    """Stub provider_rungs + cli_bridge._reason (classification uses static fakes).

    ``results[i]`` is returned by the i-th provider call; a call past the end of the
    list raises, so an unexpected replay fails loudly instead of silently passing.
    """
    from brain import cli_bridge, provider_waterfall as pw

    class _Auth:
        @staticmethod
        def _oauth_pool_candidates(_lane):
            return []

        @staticmethod
        def _is_auth_error(exc):
            return "401" in str(exc)

        @staticmethod
        def _is_rate_limit_error(exc):
            return "usage limit" in str(exc).lower() or "429" in str(exc)

    class _Pool:
        def is_cooling(self, key_id):
            return False

    monkeypatch.setattr(pw, "_shared_modules", lambda: (_Auth, _Pool()))
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: rungs)
    monkeypatch.setattr(pw, "_note_codex", lambda *_args, **_kwargs: None)
    calls: list[dict] = []

    async def fake_reason(_prompt, **kwargs):
        calls.append({
            "backend": kwargs.get("_backend_override"),
            "slots": kwargs.get("_subscription_slots"),
        })
        return results[len(calls) - 1]

    monkeypatch.setattr(cli_bridge, "_reason", fake_reason)
    return pw, calls


def test_oauth_unclassified_error_stops_the_rung_loop(monkeypatch):
    """A1: the first oauth rung fails with an unclassified error ("Claude Code returned
    an error result: success" — the exact 2026-10 shape) → `_reason` is called exactly
    ONCE and that failure is returned; the second rung is never tried.

    Fails if the oauth advance gate is loosened — e.g. advancing on ANY non-ok result
    instead of only "all pool keys cooling/dead" / a classified auth-quota failure —
    which would replay a possibly half-completed typed-tool turn (a second target)."""
    oauth_3 = {"provider": "oauth", "key_id": "claude_code_oauth_3",
               "env_name": "CLAUDE_CODE_OAUTH_TOKEN_3", "cooling": False}
    oauth_5 = {"provider": "oauth", "key_id": "claude_code_oauth_5",
               "env_name": "CLAUDE_CODE_OAUTH_TOKEN_5", "cooling": False}
    failure = {"ok": False, "text": None, "backend": "cli",
               "error": "Exception('Claude Code returned an error result: success')"}
    pw, calls = _waterfall(monkeypatch, [oauth_3, oauth_5], [failure])

    out = asyncio.run(pw.reason("decide the book", role="pm"))

    assert len(calls) == 1
    assert calls[0]["backend"] == "cli"
    assert calls[0]["slots"] == [{
        "key_id": "claude_code_oauth_3",
        "env_name": "CLAUDE_CODE_OAUTH_TOKEN_3",
        "cooling": False,
    }]
    assert out["ok"] is False
    assert out["error"] == failure["error"]
    assert out["provider"] == "oauth"
    assert out["provider_attempts"] == [
        {"provider": "oauth", "key_id": "claude_code_oauth_3",
         "ok": False, "cooling": False},
    ]


def test_all_cooling_marker_still_advances_to_next_rung(monkeypatch):
    """A2 (control for A1): the first oauth rung failing with "all pool keys
    cooling/dead" IS retried on the second rung, exactly once, and its success wins.

    Fails if the rung loop stops advancing entirely — e.g. the all-cooling marker stops
    matching or the `_failure_kind` classification is dropped from the advance gate."""
    oauth_3 = {"provider": "oauth", "key_id": "claude_code_oauth_3",
               "env_name": "CLAUDE_CODE_OAUTH_TOKEN_3", "cooling": True}
    oauth_5 = {"provider": "oauth", "key_id": "claude_code_oauth_5",
               "env_name": "CLAUDE_CODE_OAUTH_TOKEN_5", "cooling": False}
    failure = {"ok": False, "text": None, "backend": "cli",
               "error": "all pool keys cooling/dead"}
    success = {"ok": True, "text": "second rung book", "backend": "sdk"}
    pw, calls = _waterfall(monkeypatch, [oauth_3, oauth_5], [failure, success])

    out = asyncio.run(pw.reason("decide the book", role="pm"))

    assert len(calls) == 2
    assert [call["slots"][0]["key_id"] for call in calls] == [
        "claude_code_oauth_3", "claude_code_oauth_5",
    ]
    assert out["ok"] is True
    assert out["text"] == "second rung book"
    assert out["provider"] == "oauth"
    assert [attempt["key_id"] for attempt in out["provider_attempts"]] == [
        "claude_code_oauth_3", "claude_code_oauth_5",
    ]


def test_codex_unclassified_error_never_reaches_oauth(monkeypatch):
    """A3: a Codex rung failing with an unclassified error (a tool call already failed
    after a write) returns that failure; no oauth rung is attempted.

    Fails if Codex hands off to Claude on any failure instead of only a classified
    auth/quota exhaustion (`_failure_kind(...) is None` early-return removed)."""
    codex = {"provider": "codex", "key_id": "codex_account",
             "env_name": None, "cooling": False}
    oauth_3 = {"provider": "oauth", "key_id": "claude_code_oauth_3",
               "env_name": "CLAUDE_CODE_OAUTH_TOKEN_3", "cooling": False}
    failure = {"ok": False, "text": None, "backend": "codex",
               "error": "tool call failed after write"}
    pw, calls = _waterfall(monkeypatch, [codex, oauth_3], [failure])

    out = asyncio.run(pw.reason("govern autonomous", role="pm"))

    assert [call["backend"] for call in calls] == ["codex"]
    assert out["ok"] is False
    assert out["error"] == failure["error"]
    assert out["provider"] == "codex"
    assert out["provider_attempts"] == [
        {"provider": "codex", "key_id": "codex_account",
         "ok": False, "cooling": False},
    ]


# ---------------------------------------------------------------------------
# B. scheduler: no retry without the marker, capped one-shot jobs per day
# ---------------------------------------------------------------------------

class _RecordingScheduler:
    def __init__(self):
        self.jobs: list[dict] = []

    def add_job(self, fn, trigger, **kwargs):
        self.jobs.append({"fn": fn, "trigger": trigger, **kwargs})


def _redirect_run_events(tmp_path, monkeypatch) -> None:
    """Point control_plane.run_events at tmp (the ledger default is the live data/ dir)."""
    from control_plane import run_events

    ledger_path = run_events._ledger_path
    monkeypatch.setattr(
        run_events, "_ledger_path", lambda root=None: ledger_path(tmp_path)
    )


def _install_fake_date_trigger(monkeypatch) -> None:
    """`apscheduler` is absent from hermetic environments; `_maybe_schedule_brain_retry`
    imports `apscheduler.triggers.date.DateTrigger` lazily and returns without scheduling
    when it is missing.  Inject the smallest stub chain so the add_job call (the behavior
    under test) is observable.  monkeypatch-only; reverted after each test."""
    apscheduler = types.ModuleType("apscheduler")
    triggers = types.ModuleType("apscheduler.triggers")
    date_module = types.ModuleType("apscheduler.triggers.date")
    date_module.DateTrigger = (
        lambda *args, **kwargs: {"trigger": "date", "args": args, "kwargs": kwargs}
    )
    apscheduler.triggers = triggers
    triggers.date = date_module
    monkeypatch.setitem(sys.modules, "apscheduler", apscheduler)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers", triggers)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.date", date_module)


def test_no_retry_scheduled_without_pool_exhausted_marker(tmp_path, monkeypatch):
    """B1: `_read_pool_exhausted_since` → None (no fresh all-cooling marker this run)
    ⇒ no add_job on a present scheduler and no retry_scheduled event.

    Fails if `_maybe_schedule_brain_retry` schedules a retry on any run end — e.g. the
    marker gate is dropped and decide_retry is fed an assumed all-cooling failure."""
    from app import scheduler

    _redirect_run_events(tmp_path, monkeypatch)
    fake = _RecordingScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", fake)
    monkeypatch.setattr(
        scheduler, "_read_pool_exhausted_since", lambda book, since_ts: None
    )

    since = datetime.now(timezone.utc)
    scheduler._maybe_schedule_brain_retry("autonomous_daily", "autonomous", since)

    assert fake.jobs == []
    events = _run_events_written(tmp_path)
    assert [event for event in events if event.get("step") == "brain_retry"] == []


def test_retry_scheduling_capped_per_day_with_distinct_ids(tmp_path, monkeypatch):
    """B2: with a fresh all-cooling marker, calling `_maybe_schedule_brain_retry`
    repeatedly on the same UTC day schedules at most MAX_RETRIES_PER_DAY one-shot jobs
    (the real decide_retry decides), each with a DISTINCT id and the original job as its
    one-shot target.

    Fails if the per-(job, UTC-day) cap is removed — a third add_job would appear — or
    if retry ids stop being unique (replace_existing would then silently drop a
    legitimately scheduled retry)."""
    from app import scheduler
    from brain.retry_policy import MAX_RETRIES_PER_DAY

    _redirect_run_events(tmp_path, monkeypatch)
    _install_fake_date_trigger(monkeypatch)
    fake = _RecordingScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", fake)
    marker = {
        "kind": "brain_pool_exhausted",
        "book": "autonomous",
        "extra": {"all_cooling": True,
                  "earliest_reset": "2020-01-01T00:00:00+00:00"},
    }
    monkeypatch.setattr(
        scheduler, "_read_pool_exhausted_since", lambda book, since_ts: dict(marker)
    )
    monkeypatch.setattr(scheduler, "_today_iso_utc", lambda: "2026-10-22")
    # Far from the next scheduled run so the guard never rejects the retry slot.
    monkeypatch.setattr(
        scheduler, "_next_scheduled_run",
        lambda job_id: datetime.now(timezone.utc) + timedelta(days=365),
    )
    monkeypatch.setattr(scheduler, "_BRAIN_RETRY_COUNTS", {})

    since = datetime.now(timezone.utc)
    for _ in range(MAX_RETRIES_PER_DAY + 2):
        scheduler._maybe_schedule_brain_retry("autonomous_daily", "autonomous", since)

    assert len(fake.jobs) == MAX_RETRIES_PER_DAY
    ids = [job["id"] for job in fake.jobs]
    assert ids == [
        f"autonomous_daily__brain_retry_2026-10-22_{attempt}"
        for attempt in range(1, MAX_RETRIES_PER_DAY + 1)
    ]
    assert len(set(ids)) == len(ids)
    for job in fake.jobs:
        assert job["fn"] is scheduler._brain_retry_run
        assert job["args"] == ["autonomous_daily"]
        assert job["replace_existing"] is True
        run_date = job["trigger"]["kwargs"]["run_date"]
        assert run_date.tzinfo is not None
        assert run_date > since
    assert scheduler._BRAIN_RETRY_COUNTS[
        ("autonomous_daily", "2026-10-22")
    ] == MAX_RETRIES_PER_DAY
    events = [
        event for event in _run_events_written(tmp_path)
        if event.get("step") == "brain_retry"
    ]
    assert [event.get("status") for event in events] == [
        "retry_scheduled"
    ] * MAX_RETRIES_PER_DAY


# ---------------------------------------------------------------------------
# C. decision rows: a same-asof retry keeps exactly one row
# ---------------------------------------------------------------------------

def _queued_row(asof: str, summary: str, ticker: str, weight: float) -> dict:
    """A production-shaped accepted queued row carrying its full accepted identity."""
    from bot import decision_rows as dr

    submission = _submission(summary, ticker, weight)
    row = {
        "asof": asof,
        "summary": summary,
        "holdings": [{"ticker": ticker, "weight": weight}],
        "executed": [],
        "error": None,
        "target_status": "queued",
        "decision_effective": True,
    }
    row.update(dr.accepted_identity_fields(
        AUTONOMOUS, asof, submission, {ticker: weight}, "queued"
    ))
    assert dr.is_substantive(row)
    return row


def _barren_row(asof: str) -> dict:
    """A rejected re-run stub: nothing accepted, nothing held, not decision-effective."""
    from bot import decision_rows as dr

    row = {
        "asof": asof,
        "summary": None,
        "holdings": [],
        "executed": [],
        "error": None,
        "target_status": "rejected_no_submission",
        "decision_effective": False,
    }
    assert not dr.is_substantive(row)
    return row


def test_same_asof_retry_substantive_supersedes_substantive():
    """C1: a substantive retry for the same asof replaces the earlier row — exactly one
    row survives, the later one.

    Fails if a substantive re-run can no longer supersede (e.g. replace_for_asof starts
    never replacing, so a genuinely better book would be lost)."""
    from bot import decision_rows as dr

    first = _queued_row("2026-08-12", "overnight book", "AAPL", 0.20)
    retry = _queued_row("2026-08-12", "overnight re-decide", "MSFT", 0.10)

    rows = dr.replace_for_asof([first], retry, "2026-08-12")

    assert rows == [retry]
    assert len(rows) == 1


def test_same_asof_retry_barren_never_erases_substantive():
    """C2: a barren retry (rejected_no_submission, decision_effective False, no
    holdings) for the same asof leaves the substantive row intact.

    Fails if the barren-protection is dropped — the 2026-07-24 HK regression where an
    error stub erased that day's accepted book from decisions.jsonl."""
    from bot import decision_rows as dr

    book = _queued_row("2026-08-12", "overnight book", "AAPL", 0.20)
    stub = _barren_row("2026-08-12")

    assert dr.replace_for_asof([book], stub, "2026-08-12") == [book]


def test_same_asof_retry_preserves_other_asofs_in_order():
    """C3: rows for other asofs survive a same-asof retry (in order), and a new asof
    appends without touching them.

    Fails if replace_for_asof drops, rewrites, or reorders rows for other dates (e.g. a
    rewrite filtered to the retry's own date)."""
    from bot import decision_rows as dr

    monday = _queued_row("2026-08-11", "monday book", "AAPL", 0.20)
    tuesday = _queued_row("2026-08-12", "tuesday book", "MSFT", 0.10)
    tuesday_retry = _queued_row("2026-08-12", "tuesday retry", "NVDA", 0.30)
    wednesday = _queued_row("2026-08-13", "wednesday book", "BIIB", 0.15)

    assert dr.replace_for_asof([monday, tuesday], tuesday_retry, "2026-08-12") == [
        monday, tuesday_retry,
    ]
    assert dr.replace_for_asof([monday, tuesday], wednesday, "2026-08-13") == [
        monday, tuesday, wednesday,
    ]


# ---------------------------------------------------------------------------
# D. settlement: re-decides never stack targets or fills
# ---------------------------------------------------------------------------

def _settle_env(monkeypatch, tmp_path):
    """Hermetic autonomous settlement boundary (mirrors
    tests/test_decision_settlement_reconciliation.py's setup).  Returns
    (bot.settle, bot.autonomous module, market-open cell)."""
    from bot import settle
    from portfolio import fx, paper_account, registry

    module = importlib.import_module("bot.autonomous")
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(module, "_warm_live", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(paper_account, "_current_price", lambda symbol: 100.0)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "test_open" for symbol in symbols},
        ),
    )
    market = {"open": False}
    monkeypatch.setattr(settle, "is_open", lambda pid: market["open"])
    return settle, module, market


def test_redecides_keep_one_target_and_settle_fills_it_once(tmp_path, monkeypatch):
    """D1–D3: two closed-session re-decides of the SAME book/asof leave exactly one
    pending target (the second decision) and zero fills; the open settle then fills only
    that target, and a repeated settle_open the same day adds nothing.

    Fails if a re-decide stacks a second pending target (the queue became an append
    list, or save stopped being latest-wins), if settlement fills the superseded AAPL
    intent, or if settle_open re-executes on a same-day retry (extra fills/receipt)."""
    settle, module, market = _settle_env(monkeypatch, tmp_path)
    _seed_account()

    first_submission = _submission("overnight book", "AAPL", 0.20)
    module._append_decision_log(
        "2026-08-12", first_submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    first = settle.execute_or_queue(
        AUTONOMOUS, {"AAPL": 0.20}, {"AAPL": 100.0}, "2026-08-12",
        market_open=False, decision_snapshot=first_submission,
    )
    assert first["queued"] is True
    assert first["executed"] == []

    second_submission = _submission("overnight re-decide", "MSFT", 0.10)
    module._append_decision_log(
        "2026-08-12", second_submission, [], [], {},
        target_status="queued", effective_target={"MSFT": 0.10},
    )
    second = settle.execute_or_queue(
        AUTONOMOUS, {"MSFT": 0.10}, {"MSFT": 100.0}, "2026-08-12",
        market_open=False, decision_snapshot=second_submission,
    )
    assert second["queued"] is True
    assert second["executed"] == []

    # D1: exactly one pending target, equal to the SECOND decision; zero fills so far.
    from portfolio import paper_account

    pending = paper_account.load_pending_target(AUTONOMOUS)
    assert pending["target"] == {"MSFT": 0.10}
    assert pending["asof"] == "2026-08-12"
    assert pending["decision_snapshot"]["accepted_asof"] == "2026-08-12"
    assert paper_account.pending_target_file_exists(AUTONOMOUS) is True
    assert _fills(AUTONOMOUS) == []

    # D2: the open settle fills only the surviving MSFT intent; AAPL never fills.
    market["open"] = True
    result = settle.settle_open(AUTONOMOUS, "2026-08-13")
    assert result["ok"] is True, result
    assert result["receipt_acknowledged"] is True
    assert result["decision_reconciliation"]["reconciled"] is True
    fills = _fills(AUTONOMOUS)
    assert {fill["ticker"] for fill in fills} == {"MSFT"}
    assert all(fill["ticker"] != "AAPL" for fill in fills)
    rows = _decision_rows(AUTONOMOUS)
    assert len(rows) == 1
    assert rows[0]["asof"] == "2026-08-12"
    assert rows[0]["target_status"] == "executed"
    assert [fill["ticker"] for fill in rows[0]["executed"]] == ["MSFT"]
    positions = paper_account._load_account(AUTONOMOUS)["positions"]
    assert set(positions) == {"MSFT"}
    assert paper_account.pending_settlement_receipts(AUTONOMOUS) == []

    # D3: calling settle_open again the same day is idempotent — no additional fills,
    # no second receipt, no ledger or account change.
    fills_before = fills
    receipts_before = _receipt_files(AUTONOMOUS)
    again = settle.settle_open(AUTONOMOUS, "2026-08-13")
    assert len(_fills(AUTONOMOUS)) == len(fills_before)
    assert {fill["ticker"] for fill in _fills(AUTONOMOUS)} == {"MSFT"}
    assert _receipt_files(AUTONOMOUS) == receipts_before
    assert _decision_rows(AUTONOMOUS) == rows
    assert paper_account.pending_settlement_receipts(AUTONOMOUS) == []
    assert paper_account.pending_target_file_exists(AUTONOMOUS) is False
    positions_again = paper_account._load_account(AUTONOMOUS)["positions"]
    assert {t: lot["shares"] for t, lot in positions_again.items()} == {
        t: lot["shares"] for t, lot in positions.items()
    }


def test_overnight_redecide_leaves_earlier_queued_row_unattributed(tmp_path, monkeypatch):
    """D4: two re-decides on DIFFERENT asofs (2026-08-12, then the overnight 2026-08-13
    run), settled 2026-08-14.  The receipt binds the 2026-08-13 accepted identity, so
    the 2026-08-13 row is executed with MSFT fills and the earlier 2026-08-12 queued row
    must NOT be marked executed with them — no misattribution.

    Fails if reconciliation matches a row by book or date-proximity instead of the exact
    (accepted_asof, decision_id, submission_sha256, target_sha256) identity: the earlier
    row would then be marked executed as the source of the later target's fills."""
    settle, module, market = _settle_env(monkeypatch, tmp_path)
    _seed_account()

    earlier_submission = _submission("tuesday book", "AAPL", 0.20)
    module._append_decision_log(
        "2026-08-12", earlier_submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    first = settle.execute_or_queue(
        AUTONOMOUS, {"AAPL": 0.20}, {"AAPL": 100.0}, "2026-08-12",
        market_open=False, decision_snapshot=earlier_submission,
    )
    assert first["queued"] is True

    later_submission = _submission("overnight re-decide", "MSFT", 0.10)
    module._append_decision_log(
        "2026-08-13", later_submission, [], [], {},
        target_status="queued", effective_target={"MSFT": 0.10},
    )
    second = settle.execute_or_queue(
        AUTONOMOUS, {"MSFT": 0.10}, {"MSFT": 100.0}, "2026-08-13",
        market_open=False, decision_snapshot=later_submission,
    )
    assert second["queued"] is True

    market["open"] = True
    result = settle.settle_open(AUTONOMOUS, "2026-08-14")
    assert result["ok"] is True, result
    assert result["decision_reconciliation"]["reconciled"] is True

    rows = {row["asof"]: row for row in _decision_rows(AUTONOMOUS)}
    assert set(rows) == {"2026-08-12", "2026-08-13"}
    executed_row = rows["2026-08-13"]
    assert executed_row["target_status"] == "executed"
    assert [fill["ticker"] for fill in executed_row["executed"]] == ["MSFT"]

    # The earlier queued row is left EXACTLY as it was: still "queued" (superseded
    # intents are never rewritten into executed by a later target's settlement).
    earlier = rows["2026-08-12"]
    assert earlier["target_status"] == "queued"
    assert earlier["executed"] == []
    assert "settlement_transaction_id" not in earlier
    assert earlier.get("settled_asof") is None
    assert {fill["ticker"] for fill in _fills(AUTONOMOUS)} == {"MSFT"}
