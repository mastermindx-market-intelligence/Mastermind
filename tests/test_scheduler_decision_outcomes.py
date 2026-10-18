"""Missing PM decisions must reach the existing durable scheduler-health consumer."""
import copy
import importlib
import json

import pytest

BOOKS = [("autonomous", "_autonomous_job", "run_autonomous"),
         ("china", "_china_job", "run_china"), ("hk", "_hk_job", "run_hk")]

FIRST_RUNS = [(book, "maybe_first_" + book + "_run", runner)
              for book, _wrapper, runner in BOOKS]
INVOCATIONS = BOOKS + FIRST_RUNS


@pytest.fixture
def isolated_scheduler(tmp_path, monkeypatch):
    from app import scheduler
    from control_plane import locks, run_events
    ledger_path, locks_dir = run_events._ledger_path, locks._locks_dir
    monkeypatch.setattr(run_events, "_ledger_path", lambda root=None: ledger_path(tmp_path))
    monkeypatch.setattr(locks, "_locks_dir", lambda root=None: locks_dir(tmp_path))
    monkeypatch.setattr(scheduler, "_scheduler", None)
    calls = {"runner": [], "evaluation": [], "retry": []}
    monkeypatch.setattr(scheduler, "_post_mark_forward_evaluation",
                        lambda *args, **kwargs: calls["evaluation"].append(args))
    monkeypatch.setattr(scheduler, "_maybe_schedule_brain_retry",
                        lambda *args: calls["retry"].append(args))
    return scheduler, ledger_path(tmp_path), calls


def _prepare_first(book, isolated_scheduler, monkeypatch, *, available=True):
    """Capture thread scheduling; run its real target only when the test asks."""
    import threading
    from brain import cli_bridge
    from portfolio import registry

    scheduler, ledger, calls = isolated_scheduler
    # Import the book before substituting Thread; no real runner is invoked.
    importlib.import_module("bot." + book)
    monkeypatch.setenv(book.upper() + "_FIRST_RUN", "1")
    monkeypatch.setattr(registry, "data_dir",
                        lambda key: ledger.parent.parent / "portfolios" / key)
    calls["availability"] = []

    def fixture_available():
        calls["availability"].append(book)
        return available

    monkeypatch.setattr(cli_bridge, "available", fixture_available)
    threads = []

    class DeferredThread:
        def __init__(self, *, target, name, daemon):
            assert name == book + "-first-run"
            assert daemon is True
            self.target = target

        def start(self):
            threads.append(self)

    monkeypatch.setattr(threading, "Thread", DeferredThread)
    return threads


def _invoke(book, wrapper, runner, result, isolated_scheduler, monkeypatch):
    scheduler, ledger, calls = isolated_scheduler
    module = importlib.import_module("bot." + book)
    returned = copy.deepcopy(result)

    def fake_runner():
        calls["runner"].append(book)
        return returned

    monkeypatch.setattr(module, runner, fake_runner)
    first_run = wrapper.startswith("maybe_first_")
    if first_run:
        threads = _prepare_first(book, isolated_scheduler, monkeypatch)
        assert getattr(scheduler, wrapper)() is True
        assert len(threads) == 1
        assert not ledger.exists()  # outer True is only thread-scheduling evidence
        assert calls["runner"] == calls["evaluation"] == calls["retry"] == []
        threads[0].target()
    else:
        getattr(scheduler, wrapper)()
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    started = [event for event in events if event["kind"] == "run_started"]
    finished = [event for event in events if event["kind"] == "run_finished"]
    assert len(started) == len(finished) == 1
    assert started[0]["extra"]["run_id"] == finished[0]["extra"]["run_id"]
    assert started[0]["book"] == finished[0]["book"] == book
    trigger = "first_run" if first_run else "cron"
    assert started[0]["extra"]["trigger"] == finished[0]["extra"]["trigger"] == trigger
    assert calls["runner"] == [book]  # no replay or replacement provider call
    assert len(calls["evaluation"]) == 1
    assert len(calls["retry"]) == (0 if first_run else 1)
    assert returned == result
    health = next(row for row in scheduler.scheduler_health()
                  if row["id"] == book + "_daily")
    assert health["last_status"] == finished[0]["status"]
    assert health["last_reason"] == finished[0]["extra"].get("reason")
    assert health["last_target_status"] == finished[0]["extra"].get("target_status")
    projected = json.dumps({"events": events, "health": health})
    assert "fixture-only private diagnostic" not in projected
    assert "SYNTHETIC_PRIVATE_PROVIDER_FAILURE" not in projected
    return finished[0], events

@pytest.mark.parametrize("book,wrapper,runner", INVOCATIONS)
@pytest.mark.parametrize("result,reason", [
    ({"target_status": "rejected_no_submission", "decided": False,
      "decision_effective": False, "brain": {"ok": False}}, "missing_submission"),
    (None, "invalid_result"),
    ({}, "invalid_result"),
    ({"target_status": "executed", "decision_effective": False}, "inconsistent_result"),
    ({"target_status": "queued", "decision_effective": True,
      "publish_error": "fixture-only private diagnostic"}, "projection_failed"),
    ({"target_status": "rejected_execution_error", "decided": False,
      "decision_effective": False}, "rejected_execution_error"),
])
def test_semantic_failures_are_not_recorded_as_success(
        book, wrapper, runner, result, reason, isolated_scheduler, monkeypatch):
    finished, _events = _invoke(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch
    )
    assert finished["status"] == "error"
    assert finished["severity"] == "FREEZE"
    assert finished["extra"]["reason"] == reason
    assert "error" not in finished["extra"]


@pytest.mark.parametrize("book,wrapper,runner", INVOCATIONS)
@pytest.mark.parametrize("result", [
    {"target_status": "queued", "decided": True, "decision_effective": True},
    {"target_status": "executed", "decided": True, "decision_effective": True,
     "executed": []},
    {"target_status": "queued", "decided": True, "decision_effective": True,
     "brain": {"ok": False, "error": "SYNTHETIC_PRIVATE_PROVIDER_FAILURE"}},
])
def test_accepted_decisions_remain_successful(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch):
    finished, _events = _invoke(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch
    )
    assert finished["status"] == "ok"
    assert finished.get("severity") is None
    assert finished["extra"].get("reason") is None
    assert finished["extra"]["target_status"] == result["target_status"]

@pytest.mark.parametrize("book,wrapper,runner", INVOCATIONS)
@pytest.mark.parametrize("result,reason", [
    ({"skipped": "legacy_etf_migration_pending", "decided": False},
     "legacy_etf_migration_pending"),
    ({"target_status": "rejected_no_submission", "decided": False,
      "decision_effective": False, "cost_capped": True,
      "brain": {"ok": False, "skipped": True}}, "cost_capped"),
])
def test_explicit_inert_runs_are_visible_skips(
        book, wrapper, runner, result, reason, isolated_scheduler, monkeypatch):
    finished, _events = _invoke(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch
    )
    assert finished["status"] == "skip"
    assert finished["severity"] == "ADVISORY_ONLY"
    assert finished["extra"]["reason"] == reason


def test_scheduler_health_projects_safe_reason(isolated_scheduler, monkeypatch):
    scheduler, _ledger, _calls = isolated_scheduler
    result = {"target_status": "rejected_no_submission", "decided": False,
              "decision_effective": False, "brain": {"ok": False}}
    _invoke("autonomous", "_autonomous_job", "run_autonomous", result,
            isolated_scheduler, monkeypatch)
    health = next(row for row in scheduler.scheduler_health()
                  if row["id"] == "autonomous_daily")
    assert health["last_reason"] == "missing_submission"


@pytest.mark.parametrize("book,wrapper,runner", FIRST_RUNS)
@pytest.mark.parametrize("gate", ["disabled", "nav_exists", "unavailable"])
def test_first_run_gates_schedule_no_thread_or_job(
        book, wrapper, runner, gate, isolated_scheduler, monkeypatch):
    scheduler, ledger, calls = isolated_scheduler
    threads = _prepare_first(book, isolated_scheduler, monkeypatch,
                             available=gate != "unavailable")
    module = importlib.import_module("bot." + book)

    def forbidden_runner():
        pytest.fail("A first-run gate must not reach the book runner")

    monkeypatch.setattr(module, runner, forbidden_runner)
    if gate == "disabled":
        monkeypatch.setenv(book.upper() + "_FIRST_RUN", "0")
    elif gate == "nav_exists":
        from portfolio import registry
        nav = registry.data_dir(book) / "nav_history.jsonl"
        nav.parent.mkdir(parents=True)
        nav.write_text('{"fixture":"existing NAV history"}\n')

    assert getattr(scheduler, wrapper)() is False
    assert threads == []
    assert not ledger.exists()
    assert calls["runner"] == calls["evaluation"] == calls["retry"] == []
    assert calls["availability"] == ([book] if gate == "unavailable" else [])


@pytest.mark.parametrize("book,wrapper,runner", FIRST_RUNS)
def test_first_run_held_lock_stays_an_inert_skip(
        book, wrapper, runner, isolated_scheduler, monkeypatch):
    from control_plane import locks
    scheduler, ledger, calls = isolated_scheduler
    threads = _prepare_first(book, isolated_scheduler, monkeypatch)
    module = importlib.import_module("bot." + book)

    def forbidden_runner():
        pytest.fail("Lock refusal must not reach the book runner")

    monkeypatch.setattr(module, runner, forbidden_runner)
    held = locks.acquire("book:" + book)
    assert held is not None
    try:
        assert getattr(scheduler, wrapper)() is True
        assert len(threads) == 1 and not ledger.exists()
        threads[0].target()
    finally:
        held.release()
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    started = [e for e in events if e["kind"] == "run_started"]
    finished = [e for e in events if e["kind"] == "run_finished"]
    assert len(started) == len(finished) == 1
    assert started[0]["extra"]["run_id"] == finished[0]["extra"]["run_id"]
    assert finished[0]["status"] == "skip"
    assert finished[0]["severity"] == "ADVISORY_ONLY"
    assert finished[0]["extra"]["trigger"] == "first_run"
    assert len([e for e in events if e["kind"] == "run_skipped"]) == 1
    assert calls["runner"] == calls["evaluation"] == calls["retry"] == []


@pytest.mark.parametrize("book,wrapper,runner", FIRST_RUNS)
@pytest.mark.parametrize("failure_at", ["runner", "post_mark"])
def test_first_run_ordinary_exception_does_not_replay(
        book, wrapper, runner, failure_at, isolated_scheduler, monkeypatch):
    scheduler, ledger, calls = isolated_scheduler
    threads = _prepare_first(book, isolated_scheduler, monkeypatch)
    module = importlib.import_module("bot." + book)
    result = {"target_status": "queued", "decision_effective": True}

    def fake_runner():
        calls["runner"].append(book)
        if failure_at == "runner":
            raise RuntimeError("synthetic runner failure")
        return result

    def fake_post_mark(*args):
        calls["evaluation"].append(args)
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(module, runner, fake_runner)
    if failure_at == "post_mark":
        monkeypatch.setattr(scheduler, "_post_mark_forward_evaluation", fake_post_mark)
    assert getattr(scheduler, wrapper)() is True
    assert len(threads) == 1 and not ledger.exists()
    threads[0].target()
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    finished = [e for e in events if e["kind"] == "run_finished"]
    assert len(finished) == 1 and finished[0]["status"] == "error"
    assert finished[0]["extra"]["trigger"] == "first_run"
    assert calls["runner"] == [book]
    assert len(calls["evaluation"]) == (1 if failure_at == "post_mark" else 0)
    assert calls["retry"] == []
    assert result == {"target_status": "queued", "decision_effective": True}
