"""Owner coverage must disclose its denominator and failed inputs before cognition."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest
from brain import nw_reflection as N
from brain import neural_web_context as C
from brain import ledger as L

NOW = "2026-09-24T08:00:00Z"
SHA = "a" * 40


@pytest.fixture
def owner(monkeypatch, tmp_path):
    monkeypatch.setattr(N, "_ROOT", tmp_path)
    ledger = tmp_path / "data/brain/theses.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('\n'.join(json.dumps(row) for row in [
        {"subject": "AAA", "status": "open"},
        {"subject": "BBB", "status": "open"},
    ]))
    monkeypatch.setattr(L, "_LEDGER", ledger)
    outcomes = ledger.with_name("outcome_ledger.jsonl")
    outcomes.write_text('\n'.join(json.dumps(row) for row in [
        {"subject": "AAA"}, {"subject": "CCC"}, {"subject": "CCC"}]))
    monkeypatch.setattr(C, "context", lambda: {"candidate_context": {"AAA": {}, "BBB": {}}})
    return tmp_path


def test_owner_declares_distinct_subjects_not_row_sum(owner):
    result = N.coverage()
    assert result["open_theses_n"] == 2
    assert result["resolved_recent_n"] == 3
    assert result["subjects_n"] == 3
    assert result["with_context_row_n"] == 2
    assert result["coverage_rate"] == 0.667
    assert result["inputs_complete"] is True
    assert result["sample_scope"] == "open_theses_and_last_200_outcome_rows"
    assert result["input_status"] == {"context": "COMPLETE", "theses": "COMPLETE", "outcomes": "COMPLETE"}


@pytest.mark.parametrize("relative", ["theses.jsonl", "outcome_ledger.jsonl"])
def test_missing_owner_input_is_not_empty_complete_population(owner, relative):
    (owner / "data/brain" / relative).unlink()
    result = N.coverage()
    assert result["inputs_complete"] is False
    assert "MISSING" in result["input_status"].values()


@pytest.mark.parametrize("bad", ['{broken', '[]', '{"subject": null}'])
def test_malformed_outcome_does_not_silently_certify_scope(owner, bad):
    p = owner / "data/brain/outcome_ledger.jsonl"
    p.write_text(p.read_text() + "\n" + bad)
    result = N.coverage()
    assert result["inputs_complete"] is False
    assert result["input_status"]["outcomes"] == "MALFORMED"


def test_empty_existing_inputs_are_complete_but_have_no_demand(owner):
    for name in ("theses.jsonl", "outcome_ledger.jsonl"):
        (owner / "data/brain" / name).write_text("")
    result = N.coverage()
    assert result["inputs_complete"] is True
    assert result["subjects_n"] == 0
    assert result["coverage_rate"] is None


def test_unavailable_context_is_not_a_proven_coverage_gap(owner, monkeypatch):
    monkeypatch.setattr(C, "context", lambda: {})
    result = N.coverage()
    assert result["inputs_complete"] is False
    assert result["input_status"]["context"] == "UNAVAILABLE"


def test_recent_scope_is_bounded_without_counting_duplicate_subjects(owner):
    p = owner / "data/brain/outcome_ledger.jsonl"
    p.write_text('\n'.join(json.dumps({"subject": "OLD" if i == 0 else "CCC"}) for i in range(201)))
    result = N.coverage()
    assert result["resolved_recent_n"] == 200
    assert result["subjects_n"] == 3
    assert result["inputs_complete"] is True


def test_no_private_subjects_in_owner_diagnostics(owner):
    value = N.coverage()
    assert not any(subject in json.dumps(value) for subject in ["AAA", "BBB", "CCC"])


@pytest.fixture
def snapshot(owner):
    return {"schema": "nw_reflection.v1", "asof": "2026-09-24",
            "generated_at": "2026-09-24T07:00:00Z", "coverage": N.coverage(),
            "nudges": []}


def report(snapshot, now=NOW):
    from brain.improvement_discovery_nw import evaluate_owner_snapshot
    return evaluate_owner_snapshot(snapshot, source_revision=SHA,
        contract_sha256="sha256:" + "b" * 64, observed_at=now)


def test_owner_snapshot_reaches_evidenced_demand_gap_and_competing_options(snapshot):
    r = report(snapshot)
    assert r["opportunities"][0]["diagnosis"] == "EVIDENCED_GAP"
    assert r["owner_coverage"]["subjects_n"] == 3
    assert r["owner_coverage"]["uncovered_subjects_n"] == 1
    assert {x["kind"] for x in r["hypotheses"]} == {"REUSE_OR_CONNECT", "BOUNDED_RESEARCH", "HOLD_OR_NARROW"}
    assert r["selection"] is None
    assert r["independent_discovery_proven"] is False
    assert r["execution_authority_granted"] is False
    assert r["jobs_created"] == 0


def test_partial_population_does_not_become_build_recommendation(snapshot):
    snapshot["coverage"]["inputs_complete"] = False
    snapshot["coverage"]["input_status"]["theses"] = "MISSING"
    r = report(snapshot)
    assert r["opportunities"][0]["diagnosis"] == "UNVERIFIED_GAP"
    assert {h["kind"] for h in r["hypotheses"]} == {"VERIFY_EVIDENCE", "HOLD"}


def test_legacy_denominator_remains_unknown(snapshot):
    for key in ("subjects_n", "sample_scope", "inputs_complete", "input_status"):
        snapshot["coverage"].pop(key)
    r = report(snapshot)
    assert r["opportunities"][0]["diagnosis"] == "UNASSESSED"
    assert r["owner_coverage"]["subjects_n"] is None


def test_old_owner_report_not_relabelled_current(snapshot):
    snapshot.update(asof="2026-07-21", generated_at="2026-07-21T07:00:00Z")
    r = report(snapshot)
    assert r["opportunities"][0]["diagnosis"] == "HELD_SOURCE"
    assert r["hypotheses"] == []
    assert "STALE" in r["opportunities"][0]["source_problems"]


@pytest.mark.parametrize("change", [
    {"subjects_n": True}, {"subjects_n": -1}, {"subjects_n": 1},
    {"coverage_rate": 1.0}, {"coverage_rate": float("nan")},
    {"inputs_complete": "true"}, {"sample_scope": "whole_market"},
    {"input_status": {"context": "COMPLETE", "theses": "MISSING", "outcomes": "COMPLETE"}},
])
def test_inconsistent_owner_metadata_is_refused(snapshot, change):
    snapshot["coverage"].update(change)
    with pytest.raises(ValueError):
        report(snapshot)


def test_future_owner_report_is_refused(snapshot):
    snapshot["generated_at"] = "2026-09-25T07:00:00Z"
    with pytest.raises(ValueError):
        report(snapshot)


def test_no_demand_is_not_a_failing_capability(snapshot):
    snapshot["coverage"].update(open_theses_n=0, resolved_recent_n=0,
        subjects_n=0, with_context_row_n=0, coverage_rate=None)
    r = report(snapshot)
    assert r["opportunities"][0]["diagnosis"] == "UNASSESSED"
    assert all(h["kind"] not in {"REUSE_OR_CONNECT", "BOUNDED_RESEARCH"} for h in r["hypotheses"])


def test_same_asof_correction_replaces_evidence_not_opportunity_identity(snapshot):
    old = report(snapshot)
    snapshot["coverage"].update(with_context_row_n=3, context_rows_n=3, coverage_rate=1.0)
    snapshot["generated_at"] = "2026-09-24T07:30:00Z"
    corrected = report(snapshot)
    assert corrected["opportunities"][0]["id"] == old["opportunities"][0]["id"]
    assert corrected["digest"] != old["digest"]
    assert corrected["opportunities"][0]["diagnosis"] == "SATISFIED"
    assert corrected["hypotheses"] == []


def test_source_prose_is_not_copied_into_public_projection(snapshot):
    from brain.improvement_discovery import agenda_projection
    snapshot["private_note"] = "PRIVATE_OWNER_NOTE"
    r = report(snapshot)
    assert "PRIVATE_OWNER_NOTE" not in json.dumps(r)
    p = agenda_projection(r)
    assert "hypotheses" not in p and "sources" not in p
    assert "PRIVATE_OWNER_NOTE" not in json.dumps(p)


def test_real_agenda_default_consumes_owner_without_new_scheduler(snapshot, monkeypatch, tmp_path):
    from brain import improvement_agenda as A
    from brain import improvement_discovery_nw as O
    monkeypatch.setattr(N, "latest", lambda: deepcopy(snapshot))
    monkeypatch.setattr(O, "_source_identity", lambda root: (SHA, "sha256:" + "b" * 64))
    monkeypatch.setattr(O, "_now", lambda: NOW)
    monkeypatch.setattr(A, "_ROOT", tmp_path)
    monkeypatch.setattr(A, "_OUT", tmp_path / "agenda")
    monkeypatch.setattr(A, "_VALIDATION_DIR", tmp_path / "validation")
    for name in ("_from_calibration", "_from_journal", "_from_shadow", "_from_benchmark",
                 "_from_book_lifecycle", "_from_validation", "_from_cost_guard",
                 "_from_deploy_lag", "_from_model_drift", "_from_nw_reflection",
                 "_from_experiment_registry", "_from_accruing_experiments", "_from_experiment_tristate"):
        monkeypatch.setattr(A, name, lambda *args: [])
    monkeypatch.setattr(A, "_load_agentos_readiness", lambda: ({}, {"available": False,
        "degraded": ["isolated"], "schema": None}, "macro_unavailable"))
    result = A.build(date(2026, 9, 24), cio_rep={})
    assert result["n_items"] == 0
    assert result["discovery"]["diagnosis_counts"] == {"EVIDENCED_GAP": 1}
    assert A.write(date(2026, 9, 24), prebuilt=result)["ok"] is True
    assert A.latest()["discovery"] == result["discovery"]
    assert "hypotheses" not in json.dumps(A.latest())


def test_automatic_read_refuses_snapshot_after_requested_asof(snapshot, monkeypatch, tmp_path):
    from brain import improvement_discovery_nw as O
    monkeypatch.setattr(N, "latest", lambda: snapshot)
    monkeypatch.setattr(O, "_source_identity", lambda root: (SHA, "sha256:" + "b" * 64))
    monkeypatch.setattr(O, "_now", lambda: NOW)
    r = O.latest_agenda_projection(root=tmp_path, asof=date(2026, 9, 23))
    assert r["state"] == "UNAVAILABLE"
    assert r["reason_code"] == "POST_ASOF_OWNER_SNAPSHOT"


@pytest.mark.parametrize("filename", ["theses.jsonl", "outcome_ledger.jsonl"])
def test_input_changed_during_read_is_not_complete(owner, monkeypatch, filename):
    target = owner / "data/brain" / filename
    original = Path.read_text
    def read_and_replace(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path == target:
            path.write_text(text + '\n' + json.dumps({"subject": "LATER"}))
        return text
    monkeypatch.setattr(Path, "read_text", read_and_replace)
    result = N.coverage()
    assert result["inputs_complete"] is False
    assert "CHANGED_DURING_READ" in result["input_status"].values()


def test_owner_cli_prints_internal_hypotheses_not_a_selected_job(snapshot, tmp_path):
    import hashlib
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "report.json"
    source.write_text(json.dumps(snapshot))
    digest = "sha256:" + hashlib.sha256((root / "brain/nw_reflection.py").read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, str(root / "scripts/improvement_discovery.py"),
        str(source), "--now", NOW, "--input-kind", "nw-reflection", "--source-revision", SHA,
        "--contract-sha256", digest, "--format", "markdown"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "Competing hypotheses for Chairman Cognition" in result.stdout
    assert "REUSE_OR_CONNECT" in result.stdout
    assert "not selected work" in result.stdout


def test_readonly_source_binding_rejects_dirty_contract(tmp_path):
    import subprocess
    from brain.improvement_discovery_nw import _source_identity
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True)
    path = tmp_path / "brain/nw_reflection.py"; path.parent.mkdir(); path.write_text("# fixed contract\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "brain/nw_reflection.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "fixture"], check=True)
    revision, digest = _source_identity(tmp_path)
    assert len(revision) == 40 and digest.startswith("sha256:")
    path.write_text("# changed contract\n")
    with pytest.raises(ValueError, match="source_revision_unavailable"):
        _source_identity(tmp_path)


def test_existing_nudge_is_navigation_not_runtime_or_work_acceptance(snapshot):
    snapshot["coverage"].update(with_context_row_n=1, coverage_rate=0.333)
    snapshot["nudges"] = [{"code": "coverage_below_half", "kind": "coverage_gap", "severity": "medium"}]
    r = report(snapshot)
    assert r["existing_agenda_identity_hints"] == ["nw:coverage_below_half"]
    assert r["opportunities"][0]["existing_work"] == []
    assert r["jobs_created"] == 0


def test_projection_read_never_runs_or_persists_the_domain_owner(snapshot, monkeypatch, tmp_path):
    from brain import improvement_discovery_nw as O
    monkeypatch.setattr(N, "latest", lambda: snapshot)
    monkeypatch.setattr(O, "_source_identity", lambda root: (SHA, "sha256:" + "b" * 64))
    monkeypatch.setattr(O, "_now", lambda: NOW)
    def forbidden(*args, **kwargs):
        raise AssertionError("read must not mutate nudge state or trigger another owner cycle")
    monkeypatch.setattr(N, "build", forbidden)
    monkeypatch.setattr(N, "persist", forbidden)
    monkeypatch.setattr(N, "coverage", forbidden)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    r = O.latest_agenda_projection(root=tmp_path, asof=date(2026, 9, 24))
    assert r["state"] == "AVAILABLE"
    assert r["diagnosis_counts"] == {"EVIDENCED_GAP": 1}
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
