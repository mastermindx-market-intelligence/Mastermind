"""Missing PM decisions must reach the existing durable scheduler-health consumer."""
import copy
import importlib
import json

import pytest

BOOKS = [("autonomous", "_autonomous_job", "run_autonomous"),
         ("china", "_china_job", "run_china"), ("hk", "_hk_job", "run_hk")]


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


def _invoke(book, wrapper, runner, result, isolated_scheduler, monkeypatch):
    scheduler, ledger, calls = isolated_scheduler
    module = importlib.import_module("bot." + book)

    def fake_runner():
        calls["runner"].append(book)
        return copy.deepcopy(result)

    monkeypatch.setattr(module, runner, fake_runner)
    getattr(scheduler, wrapper)()
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    finished = [event for event in events if event["kind"] == "run_finished"]
    assert len(finished) == 1
    assert calls["runner"] == [book]  # no replay or replacement provider call
    assert len(calls["evaluation"]) == len(calls["retry"]) == 1
    health = next(row for row in scheduler.scheduler_health()
                  if row["id"] == book + "_daily")
    assert health["last_status"] == finished[0]["status"]
    return finished[0], events


@pytest.mark.parametrize("book,wrapper,runner", BOOKS)
@pytest.mark.parametrize("result,reason", [
    ({"target_status": "rejected_no_submission", "decided": False,
      "decision_effective": False, "brain": {"ok": False}}, "missing_submission"),
    (None, "invalid_result"),
    ({}, "invalid_result"),
    ({"target_status": "executed", "decision_effective": False}, "inconsistent_result"),
    ({"target_status": "queued", "decision_effective": True,
      "publish_error": "fixture-only private diagnostic"}, "projection_failed"),
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


@pytest.mark.parametrize("book,wrapper,runner", BOOKS)
@pytest.mark.parametrize("result", [
    {"target_status": "queued", "decided": True, "decision_effective": True},
    {"target_status": "executed", "decided": True, "decision_effective": True,
     "executed": []},
])
def test_accepted_decisions_remain_successful(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch):
    finished, _events = _invoke(
        book, wrapper, runner, result, isolated_scheduler, monkeypatch
    )
    assert finished["status"] == "ok"
    assert finished.get("severity") is None
    assert finished["extra"].get("reason") is None

@pytest.mark.parametrize("book,wrapper,runner", BOOKS)
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
