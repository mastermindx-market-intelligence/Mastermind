"""Real nine-job regression and adversarial auxiliary-proof cases.

The fixture projects values captured from GitHub; the API reader is replaced,
not the public verifier. These checks do not qualify a live protected push.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from scripts import ci_postmerge_proof as proof

FIXTURE = Path(__file__).with_name("fixtures") / "ci_postmerge_full_nine_jobs.json"
# Real capture of the scoped four-job shape that certified #2365's tree
# (group 42606700720 for master 9e6659c4a4; the same shape as 42592403849):
# PR fast checks succeeded, the pytest shard matrix was skipped as one
# unexpanded job, and no shard executed — while master's full pytest failed
# the frozen identity-review pins. The proof must refuse this group.
SCOPED_FIXTURE = Path(__file__).with_name("fixtures") / "ci_postmerge_scoped_group.json"


def test_proof_inventory_matches_the_actual_workflow():
    """A workflow change must update the closed proof contract atomically."""
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
    jobs = yaml.safe_load(workflow.read_text())["jobs"]
    # Expand only the current, explicitly qualified matrix; no generic workflow
    # interpreter or permissive support for future qualification lanes.
    assert set(jobs) == {"pr_scope", "pr_fast", "pytest_shards", "test"}
    matrix = jobs["pytest_shards"]["strategy"]["matrix"]
    assert matrix == {"index": [0, 1, 2, 3, 4, 5]}
    assert jobs["pytest_shards"]["name"] == "pytest shard ${{ matrix.index }}"
    names = [f"pytest shard {index}" for index in matrix["index"]]
    for key in ("pr_scope", "pr_fast", "test"):
        assert "strategy" not in jobs[key]
        names.append(jobs[key]["name"])
    assert len(names) == len(set(names))
    assert set(names) == proof._JOB_NAMES
    assert set(names) == {job["name"] for job in subject()["jobs"]["jobs"]}


def subject():
    return json.loads(FIXTURE.read_text())


def scoped_subject():
    return json.loads(SCOPED_FIXTURE.read_text())


def evaluate(data):
    current = data["current"]
    sha = current["head_sha"]
    repo = current["repository"]["full_name"]
    prefix = "/repos/" + repo
    group = data["listing"]["workflow_runs"][0]
    env = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/master",
        "GITHUB_REPOSITORY": repo,
        "GITHUB_SHA": sha,
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_RUN_ID": str(current["id"]),
        "GITHUB_RUN_ATTEMPT": "1",
        "GH_TOKEN": "offline-placeholder-not-a-credential",
    }
    reads = []
    current_reads = 0

    def read(path):
        nonlocal current_reads
        reads.append(path)
        if path == f"{prefix}/actions/runs/{current['id']}":
            current_reads += 1
            return deepcopy(data["current"] if current_reads == 1 else data["current_recheck"])
        if path == f"{prefix}/actions/workflows/ci.yml/runs?event=merge_group&head_sha={sha}&per_page=100":
            return deepcopy(data["listing"])
        if path == f"{prefix}/actions/runs/{group['id']}/attempts/1/jobs?per_page=100":
            return deepcopy(data["jobs"])
        if path == f"{prefix}/actions/runs/{group['id']}":
            return deepcopy(data["recheck"])
        raise AssertionError("unexpected endpoint: " + path)

    return proof.find_reusable_run(env, read_json=read), reads


def auxiliary(data, name="PR fast checks"):
    return next(job for job in data["jobs"]["jobs"] if job["name"] == name)


def test_captured_full_nine_job_run_qualifies():
    data = subject()
    result, reads = evaluate(data)
    assert result == 42548210214
    assert len(reads) == 5


@pytest.mark.parametrize("name", [f"pytest shard {i}" for i in range(6)] + ["test", "PR test scope", "PR fast checks"])
def test_every_job_is_required_even_when_total_count_matches_the_missing_inventory(name):
    data = subject()
    data["jobs"]["jobs"] = [job for job in data["jobs"]["jobs"] if job["name"] != name]
    data["jobs"]["total_count"] = len(data["jobs"]["jobs"])
    assert evaluate(data)[0] is None


@pytest.mark.parametrize("name", ["PR test scope", "PR fast checks"])
@pytest.mark.parametrize("field,value", [
    ("head_sha", "f" * 40),
    ("run_id", 1),
    ("run_attempt", 2),
    ("workflow_name", "Untrusted"),
    ("check_run_url", "https://foreign.invalid/check"),
    ("status", "in_progress"),
    ("name", "unrecognized extra job"),
])
def test_auxiliary_jobs_keep_all_identity_and_completion_fences(name, field, value):
    data = subject()
    auxiliary(data, name)[field] = value
    assert evaluate(data)[0] is None


@pytest.mark.parametrize("name,conclusion", [
    ("PR test scope", "skipped"),
    ("PR test scope", "failure"),
    ("PR test scope", "neutral"),
    ("PR fast checks", "success"),
    ("PR fast checks", "failure"),
    ("PR fast checks", "neutral"),
    ("PR fast checks", None),
])
def test_each_auxiliary_has_only_one_permitted_conclusion(name, conclusion):
    data = subject()
    auxiliary(data, name)["conclusion"] = conclusion
    assert evaluate(data)[0] is None


@pytest.mark.parametrize("mode", ["missing", "skipped", "failed", "duplicate"])
def test_scope_requires_its_actual_unique_successful_classifier_step(mode):
    data = subject()
    steps = auxiliary(data, "PR test scope")["steps"]
    step = next(s for s in steps if s["name"] == "Classify integrated source diff using protected base code")
    if mode == "missing":
        steps.remove(step)
    elif mode == "duplicate":
        steps.append(deepcopy(step))
    else:
        step["conclusion"] = "skipped" if mode == "skipped" else "failure"
    assert evaluate(data)[0] is None


@pytest.mark.parametrize("mode", ["inverted", "missing"])
def test_nonexecuted_auxiliary_timestamps_are_not_an_execution_interval(mode):
    data = subject()
    job = auxiliary(data)
    if mode == "inverted":
        job["started_at"], job["completed_at"] = "2026-11-09T01:57:58Z", "2026-11-09T01:57:52Z"
    else:
        job.pop("started_at")
        job.pop("completed_at")
    assert evaluate(data)[0] == 42548210214


@pytest.mark.parametrize("field,value", [
    ("steps", [{"name": "unexpected execution", "status": "completed", "conclusion": "success"}]),
    ("steps", None),
    ("runner_id", 1),
    ("runner_name", "unexpected-runner"),
    ("runner_group_id", 1),
    ("runner_group_name", "unexpected-group"),
])
def test_nonexecuted_auxiliary_rejects_execution_evidence(field, value):
    data = subject()
    auxiliary(data)[field] = value
    assert evaluate(data)[0] is None


@pytest.mark.parametrize("name", ["PR test scope", "PR fast checks"])
def test_duplicate_auxiliary_identity_rejects_even_with_valid_names(name):
    data = subject()
    job = auxiliary(data, name)
    # Pick a different job to avoid accidentally assigning its own id.
    other = next(j for j in data["jobs"]["jobs"] if j["name"] != name)
    job["id"] = other["id"]
    job["check_run_url"] = other["check_run_url"]
    assert evaluate(data)[0] is None


def test_extra_job_with_matching_count_is_not_accepted_as_future_schema():
    data = subject()
    extra = deepcopy(auxiliary(data))
    extra["id"] += 1
    extra["name"] = "Future qualification lane"
    extra["check_run_url"] = extra["check_run_url"].rsplit("/", 1)[0] + "/" + str(extra["id"])
    data["jobs"]["jobs"].append(extra)
    data["jobs"]["total_count"] += 1
    assert evaluate(data)[0] is None


def test_real_successful_shard_timestamp_anomaly_still_rejects():
    data = subject()
    job = auxiliary(data, "pytest shard 1")
    job["completed_at"] = "2026-11-09T01:57:00Z"
    assert evaluate(data)[0] is None


def test_real_failed_aggregate_still_rejects():
    data = subject()
    auxiliary(data, "test")["conclusion"] = "failure"
    assert evaluate(data)[0] is None


def test_captured_scoped_merge_group_never_qualifies():
    """A green scoped group executed no shard; it can never prove full CI."""
    result, reads = evaluate(scoped_subject())
    assert result is None
    # Rejection happens at the job-inventory read itself: the push identity,
    # actor, single-group listing and group source fences all passed on the
    # real captured values, and only the four-job scoped shape refused reuse.
    assert len(reads) == 3
    assert reads[-1].endswith("/jobs?per_page=100")


def test_scoped_capture_documents_the_unexecuted_shard_evidence():
    data = scoped_subject()
    conclusions = {job["name"]: job["conclusion"] for job in data["jobs"]["jobs"]}
    assert conclusions == {
        "PR test scope": "success",
        "PR fast checks": "success",
        'pytest shard ${{ matrix.index }}': "skipped",
        "test": "success",
    }
    skipped = next(job for job in data["jobs"]["jobs"]
                   if "matrix.index" in job["name"])
    assert skipped["steps"] == []
    # The unexpanded template name can never be part of the proof inventory:
    # accepting it would certify a group that executed zero pytest shards.
    assert 'pytest shard ${{ matrix.index }}' not in proof._JOB_NAMES
    for index in range(6):
        assert f"pytest shard {index}" in proof._JOB_NAMES
