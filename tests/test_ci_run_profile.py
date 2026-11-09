"""Focused offline tests for scripts/ci_run_profile.py (#917/#1957 P3.O3).

Covers only the two added files: build_profile identity validation,
completeness, elapsed/union/compute arithmetic, exact shard-step matching,
fail-closed evidence handling, and the frozen CLI (file/stdin input, 8 MiB
bound, error exits). No CI workflow, shard selection or policy file is touched.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.ci_run_profile import (  # noqa: E402
    MAX_INPUT_BYTES,
    SHARD_STEP_NAME,
    ProfileError,
    build_profile,
    load_snapshot,
    main,
)

_SHA = "7f1242bfa90f0f0448e66e400e054bd5aa5fa15a"
_REPO = "mastermindx-market-intelligence/Mastermind"
_RUN_ID = 2661552489
_GH = f"https://github.com/{_REPO}"
_API = f"https://api.github.com/repos/{_REPO}"


def _t(seconds: int) -> str:
    """UTC 'Z' ISO8601 stamp at 2026-11-02T10:00:00Z plus ``seconds``."""
    return f"2026-11-02T10:{seconds // 60:02d}:{seconds % 60:02d}Z"


def _step(number, name, start, end):
    return {
        "number": number,
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "started_at": start,
        "completed_at": end,
    }


def _run(overrides=None):
    run = {
        "id": _RUN_ID,
        "name": "CI",
        "head_branch": "feat/ci-run-profile",
        "head_sha": _SHA,
        "run_number": 4182,
        "run_attempt": 3,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 11849612,
        "path": ".github/workflows/ci.yml",
        "created_at": _t(0),
        "updated_at": _t(1200),  # far past the real completion; must never be used
        "url": f"{_API}/actions/runs/{_RUN_ID}",
        "html_url": f"{_GH}/actions/runs/{_RUN_ID}",
        "jobs_url": f"{_API}/actions/runs/{_RUN_ID}/jobs",
        "repository": {"id": 1069423077, "full_name": _REPO, "html_url": _GH},
    }
    run.update(overrides or {})
    return run


def _job(job_id, name, start, end, *, status="completed", conclusion="success",
         shard=None, attempt=3):
    steps = [_step(1, "Set up job", _t(start), _t(start + 5))]
    if shard is not None:
        steps.append(_step(2, "Check out repository", _t(start + 5), _t(shard[0])))
        steps.append(_step(3, SHARD_STEP_NAME, _t(shard[0]), _t(shard[1])))
        steps.append(_step(4, "Upload test timings", _t(shard[1]), _t(shard[1] + 2)))
    else:
        steps.append(_step(2, "Finish notes", _t(start + 5), _t(end)))
    return {
        "id": job_id,
        "run_id": _RUN_ID,
        "head_sha": _SHA,
        "run_attempt": attempt,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": None if start is None else _t(start),
        "completed_at": None if end is None else _t(end),
        "runner_name": "ubuntu-latest",
        "html_url": f"{_GH}/actions/runs/{_RUN_ID}/job/{job_id}",
        "steps": steps,
    }


def _snapshot(**overrides):
    """Realistic-shaped synthetic capture: seven jobs including a test fan-in."""
    jobs = [
        _job(900101, "lint", 5, 120),
        _job(900102, "build", 5, 240),
        _job(900103, "test-shard-0", 250, 720, shard=(255, 715)),
        _job(900104, "test-shard-1", 250, 600, shard=(255, 595)),
        _job(900105, "test-shard-2", 252, 570, shard=(256, 565)),
        _job(900106, "integration", 725, 900),  # fan-in after the shards
        _job(900107, "deploy", 905, 990),
    ]
    snapshot = {"run": _run(overrides.pop("run", {})), "jobs": {"total_count": 7, "jobs": jobs}}
    snapshot.update(overrides)
    return snapshot


def _patch_job(snapshot, job_id, **fields):
    for job in snapshot["jobs"]["jobs"]:
        if job["id"] == job_id:
            job.update(fields)
            return snapshot
    raise AssertionError(f"no job {job_id}")


# --- determinism, identity, attempts -------------------------------------------------


def test_profile_is_deterministic_and_json_safe():
    first = json.dumps(build_profile(_snapshot()))
    second = json.dumps(build_profile(_snapshot()))
    assert first == second
    assert json.loads(first)


def test_identity_source_urls_and_attempts_preserved():
    profile = build_profile(_snapshot())
    identity = profile["identity"]
    assert identity["run_id"] == _RUN_ID
    assert identity["head_sha"] == _SHA
    assert identity["run_attempt"] == 3
    assert identity["repository_full_name"] == _REPO
    assert identity["workflow_path"] == ".github/workflows/ci.yml"
    assert profile["identity_verified"] is True
    assert profile["attempts"] == {
        "run_attempt": 3,
        "distinct_job_attempts": ["3"],
        "all_jobs_match_run_attempt": True,
    }
    urls = profile["source_urls"]
    assert urls["run_html_url"].endswith(f"/actions/runs/{_RUN_ID}")
    assert urls["jobs_api_url"].endswith("/jobs")
    assert sorted(urls["job_html_urls"]) == sorted(str(i) for i in range(900101, 900108))
    assert profile["reported"] == {"status": "completed", "conclusion": "success"}


def test_missing_repository_identity_is_gap_not_verified():
    profile = build_profile(_snapshot(run={"repository": None}))
    assert profile["identity_verified"] is False
    assert profile["identity"]["repository_full_name"] is None
    assert any("repository identity unverified" in gap for gap in profile["evidence_gaps"])


def test_missing_run_id_rejected():
    with pytest.raises(ProfileError, match="run identity"):
        build_profile(_snapshot(run={"id": None}))


@pytest.mark.parametrize(
    "field,value",
    [("run_id", 999), ("head_sha", "0" * 40), ("run_attempt", 2)],
)
def test_mismatched_job_evidence_rejected(field, value):
    snapshot = _snapshot()
    _patch_job(snapshot, 900103, **{field: value})
    with pytest.raises(ProfileError, match=f"match workflow run {field}"):
        build_profile(snapshot)


def test_mixed_head_sha_evidence_between_jobs_rejected():
    snapshot = _snapshot(run={"head_sha": None})
    _patch_job(snapshot, 900104, head_sha="a" * 40)  # siblings still carry _SHA
    with pytest.raises(ProfileError, match="mixed head_sha evidence"):
        build_profile(snapshot)


def test_duplicate_job_ids_rejected():
    snapshot = _snapshot()
    snapshot["jobs"]["jobs"][4]["id"] = 900103  # test-shard-2 reuses shard-0's id
    with pytest.raises(ProfileError, match="duplicate job id"):
        build_profile(snapshot)


def test_structural_shapes_fail_closed():
    bad = [
        [],
        {"jobs": {"total_count": 0, "jobs": []}},
        {"run": {"id": 1}},
        {"run": {"id": 1}, "jobs": {"total_count": "7", "jobs": []}},
        {"run": {"id": 1}, "jobs": {"total_count": 1, "jobs": {}}},
    ]
    for snapshot in bad:
        with pytest.raises(ProfileError):
            build_profile(snapshot)


# --- arithmetic: parallel vs serial, completion, offsets -----------------------------


def test_parallel_overlapping_jobs_sum_exceeds_union():
    profile = build_profile(_snapshot())
    assert profile["complete_jobs"] is True
    assert profile["compute_time_seconds"] == 1748.0
    assert profile["concurrent_wall_time_seconds"] == 965.0
    assert profile["compute_time_seconds"] > profile["concurrent_wall_time_seconds"]
    assert profile["workflow_elapsed_seconds"] == 990.0
    assert profile["tail_seconds_after_created_at"] == 990.0
    assert profile["last_job_finished"] == {
        "job_id": 900107,
        "name": "deploy",
        "completed_at": _t(990),
    }
    offsets = {row["name"]: row["start_offset_seconds_from_created_at"] for row in profile["jobs"]}
    assert offsets == {
        "lint": 5.0,
        "build": 5.0,
        "test-shard-0": 250.0,
        "test-shard-1": 250.0,
        "test-shard-2": 252.0,
        "integration": 725.0,
        "deploy": 905.0,
    }


def test_serial_jobs_union_equals_sum():
    snapshot = {
        "run": _run(),
        "jobs": {
            "total_count": 3,
            "jobs": [_job(1, "a", 0, 100), _job(2, "b", 100, 200), _job(3, "c", 200, 300)],
        },
    }
    profile = build_profile(snapshot)
    assert profile["complete_jobs"] is True
    assert profile["compute_time_seconds"] == 300.0
    assert profile["concurrent_wall_time_seconds"] == 300.0
    assert profile["workflow_elapsed_seconds"] == 300.0


def test_completion_uses_max_completed_at_never_updated_at():
    profile = build_profile(_snapshot(run={"updated_at": "2026-11-02T23:59:59Z"}))
    assert profile["workflow_elapsed_seconds"] == 990.0
    assert profile["workflow_elapsed_basis"] == (
        "run.created_at -> max(job.completed_at); run.updated_at deliberately not used"
    )
    assert profile["last_job_finished"]["completed_at"] == _t(990)


def test_total_count_page_mismatch_never_completes():
    snapshot = _snapshot()
    snapshot["jobs"]["jobs"].pop()  # deploy missing from the capture
    profile = build_profile(snapshot)
    assert profile["complete_jobs"] is False
    assert profile["progress"]["page_complete"] is False
    assert profile["progress"]["jobs_captured"] == 6
    assert profile["workflow_elapsed_seconds"] is None
    assert any("total_count=7" in gap and "6 job objects" in gap for gap in profile["evidence_gaps"])
    assert profile["reported"]["status"] == "completed"  # run itself stays visible


def test_pending_run_stays_visible_with_observed_age():
    snapshot = _snapshot(run={"status": "in_progress", "conclusion": None}, observed_at=_t(1000))
    _patch_job(snapshot, 900107, status="in_progress", conclusion=None, completed_at=None)
    profile = build_profile(snapshot)
    assert profile["complete_jobs"] is False
    assert profile["reported"] == {"status": "in_progress", "conclusion": None}
    assert profile["observed"] == {"observed_at": _t(1000), "run_age_seconds": 1000.0}
    deploy = next(row for row in profile["jobs"] if row["job_id"] == 900107)
    assert deploy["running_seconds"] is None
    assert deploy["age_at_observed_at_seconds"] == 95.0  # observed 1000 - started 905
    assert profile["progress"]["unfinished_jobs"] == [
        {"job_id": 900107, "name": "deploy", "status": "in_progress"}
    ]
    assert any("not terminal" in gap for gap in profile["evidence_gaps"])
    assert profile["workflow_elapsed_seconds"] is None
    assert profile["compute_time_seconds"] == 1663.0  # 1748 minus deploy's unknown 85


def test_missing_started_at_keeps_job_visible_unknown():
    snapshot = _snapshot()
    _patch_job(snapshot, 900106, started_at=None)
    profile = build_profile(snapshot)
    integration = next(row for row in profile["jobs"] if row["job_id"] == 900106)
    assert integration["start_offset_seconds_from_created_at"] is None
    assert integration["running_seconds"] is None
    assert profile["compute_time_seconds"] == 1573.0
    assert profile["concurrent_wall_time_seconds"] == 790.0
    assert any("no started_at" in gap for gap in profile["evidence_gaps"])


def test_completed_job_missing_completed_at_never_counts_complete():
    snapshot = _snapshot()
    _patch_job(snapshot, 900106, completed_at=None)
    profile = build_profile(snapshot)
    assert profile["complete_jobs"] is False
    assert profile["workflow_elapsed_seconds"] is None
    assert profile["compute_time_seconds"] == 1573.0
    assert profile["progress"]["jobs_missing_completed_at"] == [
        {"job_id": 900106, "name": "integration"}
    ]


def test_missing_created_at_withholds_offsets_and_elapsed():
    profile = build_profile(_snapshot(run={"created_at": None}))
    assert all(row["start_offset_seconds_from_created_at"] is None for row in profile["jobs"])
    assert profile["workflow_elapsed_seconds"] is None
    assert profile["tail_seconds_after_created_at"] is None
    assert profile["compute_time_seconds"] == 1748.0  # durations do not need created_at
    assert any("created_at" in gap for gap in profile["evidence_gaps"])


def test_observed_absent_is_null_not_zero():
    profile = build_profile(_snapshot())
    assert profile["observed"] == {"observed_at": None, "run_age_seconds": None}
    assert all(row["age_at_observed_at_seconds"] is None for row in profile["jobs"])


# --- timestamp validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "bad,match",
    [
        ("2026-11-02T10:00:00", "no UTC offset"),  # naive
        ("not-a-timestamp", "invalid ISO8601"),
        ("2026-11-02T10:00:00+99:00", "invalid ISO8601"),  # impossible offset
        (12345, "ISO8601 string"),
    ],
)
def test_invalid_timestamps_rejected(bad, match):
    with pytest.raises(ProfileError, match=match):
        build_profile(_snapshot(run={"created_at": bad}))


def test_inverted_job_duration_rejected():
    snapshot = _snapshot()
    _patch_job(snapshot, 900103, completed_at=_t(240))  # before started 250
    with pytest.raises(ProfileError, match="inverted duration"):
        build_profile(snapshot)


def test_job_starting_before_created_at_rejected():
    with pytest.raises(ProfileError, match="inverted start offset"):
        build_profile(_snapshot(run={"created_at": _t(300)}))


def test_observed_at_before_created_at_rejected():
    with pytest.raises(ProfileError, match="inverted observation window"):
        build_profile(_snapshot(run={"status": "in_progress"}, observed_at="2026-11-02T09:59:00Z"))


def test_aware_non_utc_offset_converted_not_rejected():
    snapshot = _snapshot()
    _patch_job(
        snapshot,
        900107,
        started_at="2026-11-02T11:15:05+01:00",  # same instant as _t(905)
        completed_at="2026-11-02T11:16:30+01:00",  # same instant as _t(990)
    )
    profile = build_profile(snapshot)
    deploy = next(row for row in profile["jobs"] if row["job_id"] == 900107)
    assert deploy["start_offset_seconds_from_created_at"] == 905.0
    assert deploy["running_seconds"] == 85.0  # identical to the Z-stamped original


# --- shard-step matching ---------------------------------------------------------------


def test_shard_rows_and_stats_exact():
    profile = build_profile(_snapshot())
    shards = profile["test_shards"]
    assert shards["matched_step_name"] == "Run repository test shard"
    assert [row["job_name"] for row in shards["rows"]] == [
        "test-shard-0",
        "test-shard-1",
        "test-shard-2",
    ]
    assert [row["seconds"] for row in shards["rows"]] == [460.0, 340.0, 309.0]
    assert shards["stats"] == {
        "count": 3,
        "timed_count": 3,
        "min_seconds": 309.0,
        "max_seconds": 460.0,
        "sum_seconds": 1109.0,
        "mean_seconds": 369.666667,
    }
    assert shards["theoretical_perfectly_balanced_lower_bound_seconds"] == 369.666667
    assert "no achieved savings" in shards["lower_bound_note"]
    assert shards["rows"][0]["seconds"] != 470.0  # step time, not whole-job time


def test_exact_step_name_matching_only():
    snapshot = _snapshot()
    _patch_job(
        snapshot,
        900103,
        steps=[
            _step(3, "Run repository test shards", _t(255), _t(715)),  # plural: no match
            _step(4, "run repository test shard", _t(255), _t(715)),  # case: no match
        ],
    )
    profile = build_profile(snapshot)
    assert [row["job_id"] for row in profile["test_shards"]["rows"]] == [900104, 900105]
    assert profile["test_shards"]["stats"]["count"] == 2
    assert all("no steps matched" not in gap for gap in profile["evidence_gaps"])


def test_shard_step_missing_times_reported_unknown():
    snapshot = _snapshot()
    _patch_job(snapshot, 900103, steps=[_step(3, SHARD_STEP_NAME, _t(255), None)])
    profile = build_profile(snapshot)
    assert profile["test_shards"]["rows"][0]["seconds"] is None
    assert profile["test_shards"]["stats"]["sum_seconds"] == 649.0  # 340 + 309 only
    assert profile["test_shards"]["stats"]["timed_count"] == 2
    assert any("shard step" in gap for gap in profile["evidence_gaps"])


def test_no_matching_steps_reports_gap():
    snapshot = _snapshot()
    for job in snapshot["jobs"]["jobs"]:
        job["steps"] = []
    profile = build_profile(snapshot)
    assert profile["test_shards"]["rows"] == []
    assert profile["test_shards"]["stats"] is None
    assert profile["test_shards"]["theoretical_perfectly_balanced_lower_bound_seconds"] is None
    assert any("no steps matched" in gap for gap in profile["evidence_gaps"])


# --- CLI: frozen python -m interface, bounded input, error handling --------------------


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "scripts.ci_run_profile", *args],
        input=stdin,
        capture_output=True,
        cwd=str(_ROOT),
        timeout=120,
    )


def test_cli_file_and_stdin_roundtrip(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    from_file = _run_cli([str(path)])
    assert from_file.returncode == 0, from_file.stderr.decode()
    from_stdin = _run_cli(["-"], stdin=json.dumps(_snapshot()).encode())
    assert from_stdin.returncode == 0, from_stdin.stderr.decode()
    assert json.loads(from_file.stdout)["compute_time_seconds"] == 1748.0
    assert from_file.stdout == from_stdin.stdout  # byte-identical deterministic output


def test_cli_errors_fail_closed(tmp_path):
    assert _run_cli(["--help"]).returncode == 0
    empty = _run_cli([])
    assert empty.returncode == 2 and b"usage:" in empty.stderr

    missing = _run_cli([str(tmp_path / "absent.json")])
    assert missing.returncode == 2
    assert b"cannot read input" in missing.stderr

    bad_json = _run_cli(["-"], stdin=b"{not json")
    assert bad_json.returncode == 2
    assert b"not valid JSON" in bad_json.stderr

    not_object = _run_cli(["-"], stdin=b"[1, 2, 3]")
    assert not_object.returncode == 2
    assert b"JSON object" in not_object.stderr

    snapshot = _snapshot()
    snapshot["jobs"]["jobs"][2]["run_id"] = 1  # contradicts the run object
    mismatched = _run_cli(["-"], stdin=json.dumps(snapshot).encode())
    assert mismatched.returncode == 2
    assert b"run_id" in mismatched.stderr


def test_cli_bounded_input_rejects_oversize(tmp_path):
    payload = b'{"pad":"' + b"a" * MAX_INPUT_BYTES + b'"}'
    assert len(payload) > MAX_INPUT_BYTES
    path = tmp_path / "big.json"
    path.write_bytes(payload)
    result = _run_cli([str(path)])
    assert result.returncode == 2
    assert b"bounded read limit" in result.stderr
    assert result.stdout == b""


def test_load_snapshot_8mib_boundary():
    exactly = b"{}".ljust(MAX_INPUT_BYTES, b" ")  # trailing whitespace is valid JSON
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snap.bin"
        path.write_bytes(exactly)
        assert load_snapshot(str(path)) == {}
        path.write_bytes(exactly + b" ")
        with pytest.raises(ProfileError, match="bounded read limit"):
            load_snapshot(str(path))


# --- declared boundaries ----------------------------------------------------------------


def test_limitations_and_claim_boundaries_declared():
    profile = build_profile(_snapshot())
    joined = " ".join(profile["limitations"])
    assert "queued_at" in joined  # runner queue time openly not observable
    assert "dependencies" in joined  # no critical path inferred
    claims = profile["claim_boundaries"]
    assert claims["billing_estimate"] is None
    assert claims["achieved_elapsed_reduction_percent"] is None
    assert claims["delivery_or_acceptance_verdict"] is None


# Parent acceptance regressions: these failed on the returned worker artifact.
@pytest.mark.parametrize("field", ["run_id", "head_sha", "run_attempt"])
def test_missing_job_identity_never_verifies_or_completes(field):
    snapshot = _snapshot()
    snapshot["jobs"]["jobs"][0].pop(field)
    profile = build_profile(snapshot)
    assert profile["identity_verified"] is False
    assert profile["complete_jobs"] is False
    assert profile["workflow_elapsed_seconds"] is None
    assert any("job identity unverified" in g for g in profile["evidence_gaps"])


@pytest.mark.parametrize("status", ["queued", "completed"])
def test_zero_jobs_does_not_prove_completion(status):
    snapshot = _snapshot(run={"status": status})
    snapshot["jobs"] = {"total_count": 0, "jobs": []}
    profile = build_profile(snapshot)
    assert profile["complete_jobs"] is False
    assert profile["identity_verified"] is False
    assert profile["workflow_elapsed_seconds"] is None


def test_nonterminal_run_does_not_complete_from_current_job_page():
    profile = build_profile(_snapshot(run={"status": "in_progress", "conclusion": None}))
    assert profile["complete_jobs"] is False
    assert profile["workflow_elapsed_seconds"] is None
    assert profile["test_shards"]["theoretical_perfectly_balanced_lower_bound_seconds"] is None


@pytest.mark.parametrize("field,value", [("id", "123"), ("id", 0), ("run_attempt", True), ("head_sha", [])])
def test_malformed_run_identity_is_bounded_profile_error(field, value):
    with pytest.raises(ProfileError, match="identity"):
        build_profile(_snapshot(run={field: value}))


@pytest.mark.parametrize("field,value", [("id", []), ("run_id", True), ("head_sha", []), ("run_attempt", True)])
def test_malformed_job_identity_is_bounded_profile_error(field, value):
    snapshot = _snapshot()
    snapshot["jobs"]["jobs"][0][field] = value
    with pytest.raises(ProfileError, match="identity"):
        build_profile(snapshot)


@pytest.mark.parametrize("tamper", ["repository", "job_url", "job_run_url"])
def test_cross_repository_or_run_urls_are_rejected(tamper):
    snapshot = _snapshot()
    if tamper == "repository":
        snapshot["run"]["repository"]["full_name"] = "another/repository"
    elif tamper == "job_url":
        snapshot["jobs"]["jobs"][0]["html_url"] = "https://github.com/another/repository/actions/runs/1/job/2"
    else:
        snapshot["jobs"]["jobs"][0]["run_url"] = f"{_API}/actions/runs/999"
    with pytest.raises(ProfileError, match="URL contradicts"):
        build_profile(snapshot)


@pytest.mark.parametrize("count", [-1, 6])
def test_contradictory_total_count_is_rejected(count):
    snapshot = _snapshot()
    snapshot["jobs"]["total_count"] = count
    with pytest.raises(ProfileError, match="total_count contradicts"):
        build_profile(snapshot)


def test_observation_before_a_job_timestamp_is_rejected():
    with pytest.raises(ProfileError, match="follows observed_at"):
        build_profile(_snapshot(observed_at=_t(500)))


def test_shard_timing_outside_job_interval_is_rejected():
    snapshot = _snapshot()
    _patch_job(snapshot, 900103, steps=[_step(3, SHARD_STEP_NAME, _t(240), _t(715))])
    with pytest.raises(ProfileError, match="outside the job interval"):
        build_profile(snapshot)


def test_partial_shard_timings_do_not_create_a_balancing_bound():
    snapshot = _snapshot()
    _patch_job(snapshot, 900103, steps=[_step(3, SHARD_STEP_NAME, _t(255), None)])
    profile = build_profile(snapshot)
    assert profile["test_shards"]["theoretical_perfectly_balanced_lower_bound_seconds"] is None


def test_skipped_shard_is_not_an_executed_zero_duration_shard():
    snapshot = _snapshot()
    step = _step(3, SHARD_STEP_NAME, _t(255), _t(255))
    step["conclusion"] = "skipped"
    _patch_job(snapshot, 900103, steps=[step])
    profile = build_profile(snapshot)
    assert profile["test_shards"]["rows"][0]["seconds"] is None
    assert profile["test_shards"]["theoretical_perfectly_balanced_lower_bound_seconds"] is None


def test_partial_compute_is_explicitly_labeled():
    snapshot = _snapshot()
    _patch_job(snapshot, 900106, started_at=None)
    profile = build_profile(snapshot)
    assert profile["compute_time_complete"] is False
    assert "partial" in profile["compute_time_basis"]


def test_cli_malformed_identity_reports_bounded_error_without_traceback():
    snapshot = _snapshot()
    snapshot["jobs"]["jobs"][0]["head_sha"] = []
    result = _run_cli(["-"], stdin=json.dumps(snapshot).encode())
    assert result.returncode == 2
    assert b"Traceback" not in result.stderr
    assert len(result.stderr) < 600
    assert result.stdout == b""
