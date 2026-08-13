"""Fail-closed cutover tests for queued US Brain v1 targets."""
from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_books(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    return tmp_path


def _legacy_autonomous_target(asof: str = "2026-08-07") -> dict:
    return {
        "target": {"SPY": 0.35, "QQQ": 0.25},
        "asof": asof,
        "queued_at": "2026-08-08T01:00:00+00:00",
    }


class _FakeScheduler:
    """Minimal APScheduler seam for proving paused-start cutover ordering."""

    def __init__(self, *args, **kwargs):
        self.jobs: dict[str, SimpleNamespace] = {}
        self.events: list[str] = []
        self.paused = False
        self.resumed = False
        self.stopped = False

    def add_job(self, *args, **kwargs):
        job_id = kwargs["id"]
        self.jobs[job_id] = SimpleNamespace(id=job_id)

    def start(self, paused=False):
        self.paused = bool(paused)
        self.events.append("start_paused" if paused else "start_running")

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def resume(self):
        self.events.append("resume")
        self.paused = False
        self.resumed = True

    def shutdown(self, wait=False):
        self.events.append("shutdown")
        self.stopped = True

    def get_jobs(self):
        return list(self.jobs.values())


def test_new_autonomous_queue_has_explicit_v2_contract(isolated_books):
    from portfolio import paper_account

    paper_account.save_pending_target(
        {"AAPL": 0.15, "NVDA": 0.10},
        "2026-08-08",
        portfolio_id="autonomous",
    )

    queued = paper_account.load_pending_target("autonomous")
    assert queued is not None
    assert queued["schema_version"] == paper_account.PENDING_TARGET_SCHEMA_V2
    assert queued["engine_version"] == paper_account.US_BRAIN_ENGINE_V2
    assert queued["portfolio_id"] == "autonomous"


def test_startup_preflight_proactively_quarantines_legacy_target(isolated_books, monkeypatch):
    from app import scheduler
    from control_plane import run_events
    from portfolio import registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_autonomous_target()
    (book_dir / "pending_target.json").write_text(json.dumps(legacy))
    events: list[dict] = []
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: events.append(event))

    result = scheduler._startup_us_brain_cutover_preflight()

    assert result["safe_to_resume"] is True
    assert result["outcome"] == "quarantined"
    quarantined = list(book_dir.glob("pending_target.quarantine.*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text()) == legacy
    assert events[-1]["kind"] == "pending_target_cutover_preflight"
    assert events[-1]["step"] == "before_scheduler_resume"


def test_scheduler_stays_paused_until_cutover_preflight_completes(monkeypatch):
    from apscheduler.schedulers import background
    from apscheduler.triggers import cron

    from app import scheduler

    holder: dict[str, _FakeScheduler] = {}

    def make_scheduler(*args, **kwargs):
        fake = _FakeScheduler(*args, **kwargs)
        holder["scheduler"] = fake
        return fake

    def preflight():
        fake = holder["scheduler"]
        assert fake.paused is True
        assert fake.resumed is False
        fake.events.append("preflight")
        return {"safe_to_resume": True, "outcome": "quarantined"}

    monkeypatch.setattr(background, "BackgroundScheduler", make_scheduler)
    monkeypatch.setattr(cron, "CronTrigger", lambda *args, **kwargs: (args, kwargs))
    monkeypatch.setattr(scheduler, "_startup_us_brain_cutover_preflight", preflight)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setenv("MASTERMIND_JOBSTORE", "memory")
    monkeypatch.setenv("MASTERMIND_VPS_AUTHORITATIVE", "1")

    fake = scheduler.start()

    assert fake is holder["scheduler"]
    assert fake.events[:3] == ["start_paused", "preflight", "resume"]
    assert fake.resumed is True
    scheduler._scheduler = None


def test_scheduler_never_resumes_when_cutover_quarantine_fails(monkeypatch):
    from apscheduler.schedulers import background
    from apscheduler.triggers import cron

    from app import scheduler

    holder: dict[str, _FakeScheduler] = {}

    def make_scheduler(*args, **kwargs):
        fake = _FakeScheduler(*args, **kwargs)
        holder["scheduler"] = fake
        return fake

    monkeypatch.setattr(background, "BackgroundScheduler", make_scheduler)
    monkeypatch.setattr(cron, "CronTrigger", lambda *args, **kwargs: (args, kwargs))
    monkeypatch.setattr(
        scheduler,
        "_startup_us_brain_cutover_preflight",
        lambda: {"safe_to_resume": False, "outcome": "quarantine_failed"},
    )
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setenv("MASTERMIND_JOBSTORE", "memory")
    monkeypatch.setenv("MASTERMIND_VPS_AUTHORITATIVE", "1")

    with pytest.raises(RuntimeError, match="scheduler held"):
        scheduler.start()

    fake = holder["scheduler"]
    assert fake.events == ["start_paused", "shutdown"]
    assert fake.resumed is False
    scheduler._scheduler = None


def test_settle_open_quarantines_unversioned_us_v1_before_prices_or_rebalance(
    isolated_books, monkeypatch
):
    from bot import settle
    from control_plane import run_events
    from portfolio import paper_account, registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_autonomous_target()
    pending_path = book_dir / "pending_target.json"
    pending_path.write_text(json.dumps(legacy))

    paper_account._save_account(
        {
            "inception_date": "2026-01-01",
            "starting_nav": 1_000_000.0,
            "cash": 900_000.0,
            "positions": {"AAPL": {"shares": 500.0, "avg_cost": 200.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    account_before = (book_dir / "account.json").read_bytes()
    events: list[dict] = []
    rebalance_calls: list[dict] = []
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: events.append(event))
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prices read before quarantine")),
    )
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda *args, **kwargs: rebalance_calls.append({"args": args, "kwargs": kwargs}),
    )

    result = settle.settle_open("autonomous", asof="2026-08-10")

    assert result["ok"] is False
    assert result["skipped"] == "pending_target_quarantined"
    assert result["quarantined"] is True
    assert result["quarantine"]["status"] == "quarantined"
    assert result["quarantine"]["recoverable"] is True
    assert result["quarantine"]["reason"] == "missing_or_incompatible_schema_version"
    assert rebalance_calls == []
    assert (book_dir / "account.json").read_bytes() == account_before
    assert not pending_path.exists()

    quarantined = list(book_dir.glob("pending_target.quarantine.*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text()) == legacy
    audit_rows = [json.loads(line) for line in (book_dir / "pending_target_quarantine.jsonl")
                  .read_text().splitlines()]
    assert audit_rows[-1]["quarantine_file"] == quarantined[0].name
    assert audit_rows[-1]["target_symbols"] == ["QQQ", "SPY"]
    assert any(event.get("kind") == "pending_target_quarantined" for event in events)


def test_execute_or_queue_cannot_rebalance_after_legacy_target_quarantine(
    isolated_books, monkeypatch
):
    from bot import settle
    from control_plane import run_events
    from portfolio import paper_account, registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "pending_target.json").write_text(json.dumps(_legacy_autonomous_target()))
    rebalance_calls: list[dict] = []
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: None)
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda *args, **kwargs: rebalance_calls.append({"args": args, "kwargs": kwargs}),
    )

    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": 0.15},
        {"AAPL": 200.0},
        "2026-08-10",
        market_open=True,
    )

    assert result["skipped"] == "pending_target_quarantined"
    assert result["executed"] == []
    assert rebalance_calls == []


def test_malformed_autonomous_queue_is_quarantined_not_misreported_as_empty(
    isolated_books, monkeypatch
):
    from bot import settle
    from control_plane import run_events
    from portfolio import paper_account, registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "pending_target.json").write_text("{not-json")
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: None)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rebalance called")),
    )

    result = settle.settle_open("autonomous", asof="2026-08-10")

    assert result["skipped"] == "pending_target_quarantined"
    assert result["quarantine"]["reason"] == "malformed_payload"
    quarantined = list(book_dir.glob("pending_target.quarantine.*.json"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text() == "{not-json"


def test_forced_derisk_quarantines_legacy_target_before_tripwire_or_rewrite(
    isolated_books, monkeypatch
):
    from bot import derisk
    from control_plane import run_events
    from portfolio import paper_account, registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_autonomous_target()
    (book_dir / "pending_target.json").write_text(json.dumps(legacy))
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: None)
    monkeypatch.setattr(
        derisk,
        "tripwire",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tripwire called")),
    )
    monkeypatch.setattr(
        paper_account,
        "save_pending_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target rewritten")),
    )
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rebalance called")),
    )

    result = derisk.derisk_brain("autonomous", "2026-08-10", force=True)

    assert result["skipped"] == "pending_target_quarantined"
    assert result["quarantined"] is True
    quarantined = list(book_dir.glob("pending_target.quarantine.*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text()) == legacy


def test_derisk_rewrite_holds_one_book_lock_across_read_compute_and_save(
    isolated_books, monkeypatch
):
    """A fresh PM queue cannot replace the inspected target mid de-risk rewrite."""
    from bot import derisk
    from portfolio import fragility_chain, paper_account

    depth = {"value": 0}
    events: list[tuple[str, int]] = []

    @contextmanager
    def tracked_lock(portfolio_id=None):
        depth["value"] += 1
        events.append(("lock_enter", depth["value"]))
        try:
            yield
        finally:
            events.append(("lock_exit", depth["value"]))
            depth["value"] -= 1

    def preflight(portfolio_id=None):
        events.append(("preflight", depth["value"]))
        return {
            "ok": True,
            "pending": {"target": {"AAPL": 0.80}, "asof": "2026-08-12"},
        }

    def save(target, asof, portfolio_id=None, **kwargs):
        events.append(("save", depth["value"]))

    monkeypatch.setattr(paper_account, "_paper_transaction_lock", tracked_lock)
    monkeypatch.setattr(paper_account, "preflight_pending_target", preflight)
    monkeypatch.setattr(paper_account, "save_pending_target", save)
    monkeypatch.setattr(
        derisk,
        "tripwire",
        lambda *args, **kwargs: {
            "trigger": True,
            "severity": 2,
            "reasons": ["confirmed_test_unwind"],
            "state": "risk_off",
            "risk_state": {"gross_cap": 0.55, "allow_adds": True},
        },
    )
    monkeypatch.setattr(
        fragility_chain,
        "assess_book",
        lambda *args, **kwargs: {"blocked_chains": []},
    )
    monkeypatch.setattr(derisk, "_write_artifact", lambda *args, **kwargs: None)

    result = derisk.derisk_brain("autonomous", "2026-08-12", force=True)

    assert result["action"] == "revised_pending_target"
    assert ("preflight", 1) in events
    assert ("save", 1) in events
    assert events[0] == ("lock_enter", 1)
    assert events[-1] == ("lock_exit", 1)


def test_pending_preflight_holds_book_lock_across_recovery_reads_and_classification(
    isolated_books, monkeypatch
):
    """A concurrent valid replacement cannot be quarantined from a stale preflight read."""
    from portfolio import paper_account

    depth = {"value": 0}
    observations: list[tuple[str, int]] = []

    @contextmanager
    def tracked_lock(portfolio_id=None):
        depth["value"] += 1
        try:
            yield
        finally:
            depth["value"] -= 1

    monkeypatch.setattr(paper_account, "_paper_transaction_lock", tracked_lock)
    monkeypatch.setattr(
        paper_account,
        "recover_paper_transaction",
        lambda portfolio_id=None: observations.append(("recover", depth["value"])),
    )
    monkeypatch.setattr(
        paper_account,
        "_read_pending_target_payload",
        lambda portfolio_id=None: observations.append(("raw", depth["value"])) or None,
    )
    monkeypatch.setattr(
        paper_account,
        "load_pending_target",
        lambda portfolio_id=None: observations.append(("validated", depth["value"])) or None,
    )
    monkeypatch.setattr(
        paper_account,
        "pending_target_file_exists",
        lambda portfolio_id=None: observations.append(("exists", depth["value"])) or False,
    )

    result = paper_account.preflight_pending_target("autonomous")

    assert result == {"ok": True, "pending": None}
    assert observations == [
        ("recover", 1),
        ("raw", 1),
        ("validated", 1),
        ("exists", 1),
    ]


def test_forced_overnight_watch_quarantines_before_tape_derisk_or_runner(
    isolated_books, monkeypatch
):
    from bot import derisk, settle
    from bot import overnight as watch_loop
    from control_plane import run_events
    from data_layer import overnight as tape
    from portfolio import paper_account, registry

    book_dir = registry.data_dir("autonomous")
    book_dir.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_autonomous_target()
    (book_dir / "pending_target.json").write_text(json.dumps(legacy))
    monkeypatch.setattr(run_events, "append", lambda event, **kwargs: None)
    monkeypatch.setattr(settle, "is_open", lambda pid: False)
    monkeypatch.setattr(
        tape,
        "tape",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tape read")),
    )
    monkeypatch.setattr(
        tape,
        "is_material",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tripwire called")),
    )
    monkeypatch.setattr(
        derisk,
        "derisk_brain",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("derisk called")),
    )
    monkeypatch.setattr(
        paper_account,
        "save_pending_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target rewritten")),
    )
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rebalance called")),
    )
    monkeypatch.setattr(
        watch_loop.importlib,
        "import_module",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("runner loaded")),
    )

    result = watch_loop.watch("autonomous", "2026-08-10", force=True)

    assert result["skipped"] == "pending_target_quarantined"
    assert result["quarantined"] is True
    quarantined = list(book_dir.glob("pending_target.quarantine.*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text()) == legacy


def test_valid_us_v2_target_settles_normally(isolated_books, monkeypatch):
    from portfolio import paper_account

    paper_account.save_pending_target({"AAPL": 0.15}, "2026-08-08", portfolio_id="autonomous")
    calls: list[tuple[dict, dict, str, str | None]] = []
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda target, prices, asof, portfolio_id=None, **kwargs: calls.append(
            (target, prices, asof, portfolio_id)
        ),
    )

    settled = paper_account.settle_target(
        {"AAPL": 201.0, "SPY": 500.0},
        "2026-08-10",
        portfolio_id="autonomous",
    )

    assert settled == {"AAPL": 0.15}
    assert calls == [(
        {"AAPL": 0.15},
        {"AAPL": 201.0, "SPY": 500.0},
        "2026-08-10",
        "autonomous",
    )]
    assert paper_account.load_pending_target("autonomous") is None


@pytest.mark.parametrize("portfolio_id", ["china", "hk"])
def test_unversioned_regional_pending_targets_remain_compatible(
    isolated_books, monkeypatch, portfolio_id
):
    from portfolio import paper_account

    ticker = "600519.SS" if portfolio_id == "china" else "0700.HK"
    paper_account.save_pending_target({ticker: 0.20}, "2026-08-08", portfolio_id=portfolio_id)
    queued = paper_account.load_pending_target(portfolio_id)
    assert queued is not None
    assert "schema_version" not in queued
    assert "engine_version" not in queued
    calls: list[dict] = []
    monkeypatch.setattr(
        paper_account,
        "rebalance",
        lambda target, prices, asof, portfolio_id=None, **kwargs: calls.append(target),
    )

    benchmark = "000300.SS" if portfolio_id == "china" else "^HSI"
    settled = paper_account.settle_target(
        {ticker: 100.0, benchmark: 500.0},
        "2026-08-10",
        portfolio_id=portfolio_id,
    )

    assert settled == {ticker: 0.20}
    assert calls == [{ticker: 0.20}]
    assert paper_account.load_pending_target(portfolio_id) is None
