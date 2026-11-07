"""Real bounded Runtime rows; synthetic clocks never establish live demand."""
from contextlib import contextmanager
from dataclasses import replace
import json
import sqlite3

import pytest

from control_plane.executive_runtime import JobPayload, Runtime
from scripts import executive_wake_reconcile as cli
from tests.test_capacity_campaign_observation import snapshot
from tests.test_executive_wake_reconcile_observe_cli import image, unchanged_authoritative


@pytest.fixture
def workload(tmp_path):
    tick = [1_780_000_000_000]
    runtime = Runtime.at(tmp_path / "runtime", clock=lambda: tick[0])
    runtime.workers.register_worker("fixture-worker", provider="codex",
        account_label="fixture-account", worker_type="fixture", capabilities=["read"])
    job = runtime.jobs.create_job("TESTDATA acceptance proof, not ordinary demand", review_required=True)
    tick[0] += 2500
    lease = runtime.attempts.claim_job(job.job_id, worker_id="fixture-worker")
    assert lease is not None
    queued = runtime.jobs.create_job("TESTDATA private queued objective")
    return runtime, tick, job, lease, queued


def test_real_cli_retains_recorded_claim_delay_and_counts_without_campaign_claim(
    workload, tmp_path, monkeypatch, capsys,
):
    runtime, tick, job, lease, queued = workload
    monkeypatch.setattr(cli, "collect_source_snapshot", lambda *a, **kw: snapshot())
    directory = tmp_path / "evidence"
    directory.mkdir(mode=0o700)
    receipt = directory / "point.json"
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        before = image(runtime.store.root)
        events = tuple(keeper.execute("SELECT * FROM events ORDER BY event_id"))
        assert cli.main(["--root", str(runtime.store.root), "--observe-only",
                         "--observation-receipt", str(receipt)]) == 0
        point = json.loads(capsys.readouterr().out)["capacity_observation"]
        observed = point["runtime_workload"]
        assert observed["jobs_by_status"] == {"QUEUED": 1, "RUNNING": 1}
        assert observed["attempts_by_status"] == {"CLAIMED": 1}
        assert observed["review_required_jobs_by_status"] == {"RUNNING": 1}
        summary = observed["recorded_creation_to_first_claim_ms"]
        assert (summary["completed"], summary["unfinished"], summary["p95"]) == (1, 1, 2000)
        # Actual fixture claim is +2500ms; canonical readback is whole seconds.
        assert observed["recorded_timestamp_resolution_ms"] == 1000
        assert observed["campaign_qualified"] is observed["ordinary_busy_classification_claimed"] is False
        assert "INCLUDES_PROOF" in observed["population_scope"]
        assert "NOT_MODEL" in observed["clock_scope"]
        assert "private queued objective" not in json.dumps(observed)
        assert point["unavailable_metrics"]["actual_cash_usd_per_accepted_outcome"]["value"] is None
        assert point["unavailable_metrics"]["seven_day_installed_coverage"]["value"] is None
        assert cli.main(["--summarize-observations", str(receipt), "--json"]) == 0
        closed = json.loads(capsys.readouterr().out)
        assert closed["observations"][0]["runtime_workload"] == observed
        assert closed["campaign_qualified"] is closed["installed_coverage_claimed"] is False
        unchanged_authoritative(runtime.store.root, before)
        assert tuple(keeper.execute("SELECT * FROM events ORDER BY event_id")) == events
    finally:
        keeper.close()


def _observe(runtime, **bounds):
    from control_plane.capacity_runtime_observation import observe_runtime_workload
    return observe_runtime_workload(runtime, **bounds)


def _retry(runtime, tick, job):
    tick[0] += 500
    runtime.jobs.fail_job(job.job_id, JobPayload(errors=["TESTDATA failure"]))
    runtime.jobs.requeue_job(job.job_id)
    tick[0] += 4000
    assert runtime.attempts.claim_job(job.job_id, worker_id="fixture-worker") is not None


def test_first_claim_stays_original_across_retry_and_is_not_execution_time(workload):
    runtime, tick, job, lease, queued = workload
    _retry(runtime, tick, job)
    report = _observe(Runtime.at(runtime.store.root, create=False))
    assert report["state"] == "OBSERVED"
    assert report["attempts_by_status"] == {"CLAIMED": 1, "FAILED": 1}
    completed = next(row for row in report["first_claims"] if row["job_id"] == job.job_id)
    assert completed["attempt_id"] == lease.attempt.attempt_id
    assert completed["value"] == 2000
    assert report["recorded_creation_to_first_claim_ms"]["completed"] == 1


def test_real_job_and_attempt_limits_report_partial_without_unbounded_fallback(workload, monkeypatch):
    runtime, tick, job, lease, queued = workload
    _retry(runtime, tick, job)
    original = Runtime.bounded_acquisition
    calls = []
    class PageOwner:
        def __init__(self, owner): self.owner = owner
        def list_jobs(self, **kwargs):
            calls.append(("jobs", kwargs.copy()))
            return self.owner.list_jobs(**kwargs)
        def list_attempts(self, **kwargs):
            calls.append(("attempts", kwargs.copy()))
            return self.owner.list_attempts(**kwargs)
    @contextmanager
    def bounded(self):
        with original(self) as owner:
            yield PageOwner(owner)
    monkeypatch.setattr(Runtime, "bounded_acquisition", bounded)
    monkeypatch.setattr(runtime.jobs, "list_jobs", lambda: pytest.fail("unbounded Jobs"))
    monkeypatch.setattr(runtime.attempts, "list_attempts", lambda *a: pytest.fail("unbounded Attempts"))
    report = _observe(runtime, max_jobs=1, max_attempts=1)
    assert report["state"] == "PARTIAL"
    assert report["coverage"]["jobs_truncated"] is True
    assert report["coverage"]["selected_pages_complete"] is False
    assert len(calls) == 2 and calls[0] == ("jobs", {"limit": 1})
    assert calls[1][1]["limit"] == 1 and len(calls[1][1]["job_ids"]) == 1
    assert report["campaign_qualified"] is False
    calls.clear()
    report = _observe(runtime, max_attempts=1)
    assert report["coverage"]["attempts_truncated"] is True
    assert report["coverage"]["attempts_observed"] == 1
    assert report["recorded_creation_to_first_claim_ms"]["p95"] == 2000
    assert report["degraded"] == ["ATTEMPT_PAGE_INCOMPLETE"]
    assert len(calls) == 2


def test_empty_snapshot_has_no_zero_latency_or_ordinary_demand(tmp_path):
    runtime = Runtime.at(tmp_path)
    report = _observe(Runtime.at(tmp_path, create=False))
    assert report["state"] == "EMPTY"
    assert report["jobs_by_status"] == report["attempts_by_status"] == {}
    assert report["recorded_creation_to_first_claim_ms"]["population"] == 0
    assert report["recorded_creation_to_first_claim_ms"]["p95"] is None
    assert report["first_claims"] == []
    assert report["ordinary_busy_classification_claimed"] is False
    assert report["campaign_qualified"] is report["installed_coverage_claimed"] is False


def test_existing_review_slot_is_counted_as_runtime_backlog_only(tmp_path):
    from tests.test_executive_wake_persist import _completed_review_child
    runtime = Runtime.at(tmp_path)
    parent, child = _completed_review_child(runtime)
    runtime.jobs.create_job("TESTDATA review slot", parent_job_id=parent.job_id,
                            reviews_job_id=child.job_id)
    report = _observe(Runtime.at(tmp_path, create=False))
    assert report["review_jobs_by_status"] == {"QUEUED": 1}
    assert report["review_required_jobs_by_status"] == {"COMPLETED": 1}
    assert report["coverage"]["complete_company_demand_census"] is False
    assert report["campaign_qualified"] is False


def _changed_attempt_page(runtime, monkeypatch, change):
    original = Runtime.bounded_acquisition
    class PageOwner:
        def __init__(self, owner): self.owner = owner
        def list_jobs(self, **kwargs): return self.owner.list_jobs(**kwargs)
        def list_attempts(self, **kwargs):
            page = self.owner.list_attempts(**kwargs)
            return replace(page, items=change(page.items))
    @contextmanager
    def bounded(self):
        with original(self) as owner:
            yield PageOwner(owner)
    monkeypatch.setattr(Runtime, "bounded_acquisition", bounded)


@pytest.mark.parametrize("stamp", [None, "", "not-a-date", "2026-01-01T00:00:00",
    "2026-01-01T00:00:00+02:00", "2000-01-01T00:00:00Z"])
def test_bad_or_regressed_recorded_clock_never_becomes_zero_sample(workload, monkeypatch, stamp):
    runtime, *_ = workload
    _changed_attempt_page(runtime, monkeypatch,
        lambda rows: (replace(rows[0], started_at=stamp),))
    report = _observe(runtime)
    assert report["state"] == "PARTIAL"
    assert report["recorded_creation_to_first_claim_ms"]["completed"] == 0
    assert report["recorded_creation_to_first_claim_ms"]["p95"] is None
    assert report["recorded_creation_to_first_claim_ms"]["unavailable"] == 1


@pytest.mark.parametrize("change", [
    lambda rows: (),
    lambda rows: (replace(rows[0], attempt_number=2),),
    lambda rows: (rows[0], rows[0]),
    lambda rows: (replace(rows[0], job_id="JOB-NOT-SELECTED"),),
])
def test_missing_duplicate_or_wrong_attempt_binding_never_counts_accepted_timing(workload, monkeypatch, change):
    runtime, *_ = workload
    _changed_attempt_page(runtime, monkeypatch, change)
    report = _observe(runtime)
    assert report["state"] in {"PARTIAL", "UNAVAILABLE"}
    summary = report["recorded_creation_to_first_claim_ms"]
    assert summary is None or summary["completed"] == 0
    assert report["campaign_qualified"] is False


def test_one_snapshot_does_not_mix_a_concurrent_retry_into_older_job(workload, monkeypatch):
    runtime, tick, job, lease, queued = workload
    original = Runtime.bounded_acquisition
    class PageOwner:
        def __init__(self, owner): self.owner = owner
        def list_jobs(self, **kwargs):
            page = self.owner.list_jobs(**kwargs)
            # Actual distinct writer connection during the retained WAL read.
            _retry(runtime, tick, job)
            return page
        def list_attempts(self, **kwargs): return self.owner.list_attempts(**kwargs)
    @contextmanager
    def bounded(self):
        with original(self) as owner:
            yield PageOwner(owner)
    monkeypatch.setattr(Runtime, "bounded_acquisition", bounded)
    report = _observe(runtime)
    assert report["state"] == "OBSERVED" and report["coverage"]["attempts_observed"] == 1
    assert report["attempts_by_status"] == {"CLAIMED": 1}
    monkeypatch.setattr(Runtime, "bounded_acquisition", original)
    after = _observe(runtime)
    assert after["coverage"]["attempts_observed"] == 2
    assert after["snapshot_digest"] != report["snapshot_digest"]


def test_acquisition_failure_is_retained_rc2_without_partial_rows_or_private_error(
    workload, tmp_path, monkeypatch, capsys,
):
    runtime, *_ = workload
    monkeypatch.setattr(cli, "collect_source_snapshot", lambda *a, **kw: snapshot())
    def unavailable(*a, **kw):
        raise ValueError("TESTDATA private source diagnostic")
    monkeypatch.setattr(Runtime, "bounded_acquisition", unavailable)
    assert cli.main(["--root", str(runtime.store.root), "--observe-only", "--json"]) == 2
    raw = capsys.readouterr().out
    point = json.loads(raw)["capacity_observation"]
    assert point["point_status"] == "PARTIAL"
    assert point["runtime_workload"]["state"] == "UNAVAILABLE"
    assert point["runtime_workload"]["jobs_by_status"] is None
    assert "private source diagnostic" not in raw


@pytest.mark.parametrize("bounds", [dict(max_jobs=0), dict(max_jobs=True),
    dict(max_jobs=129), dict(max_attempts=0), dict(max_attempts=513)])
def test_callers_cannot_expand_fixed_acquisition_bounds(workload, bounds):
    runtime, *_ = workload
    with pytest.raises(ValueError, match="INVALID_RUNTIME_OBSERVATION_BOUND"):
        _observe(runtime, **bounds)


def test_attempt_number_cannot_exceed_its_recorded_job_count(workload, monkeypatch):
    runtime, tick, job, lease, queued = workload
    _retry(runtime, tick, job)
    original = _observe(runtime)
    assert original['state'] == 'OBSERVED'
    assert original['coverage']['attempts_observed'] == 2
    assert original['recorded_creation_to_first_claim_ms']['completed'] == 1
    _changed_attempt_page(runtime, monkeypatch, lambda rows: tuple(
        replace(row, attempt_number=3) if row.attempt_number == 2 else row for row in rows))
    report = _observe(runtime)
    assert report['state'] == 'UNAVAILABLE'
    assert report['degraded'] == ['RUNTIME_WORKLOAD_ACQUISITION_UNAVAILABLE']
    assert report['coverage'] is report['snapshot_digest'] is None
    assert report['recorded_creation_to_first_claim_ms'] is None
    assert report['first_claims'] == []
