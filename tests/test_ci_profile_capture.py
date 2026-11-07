"""The existing offline profiler's read-only Actions consumer, not a release gate."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from scripts import ci_profile_capture as capture

REPO = "mastermindx-market-intelligence/Mastermind"
SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[1]


def run_payload():
    return {
        "id": 701, "run_attempt": 2, "name": "CI", "head_sha": SHA,
        "head_branch": "feature/test", "event": "pull_request",
        "path": ".github/workflows/ci.yml", "status": "completed",
        "conclusion": "failure", "created_at": "2026-11-04T10:00:00Z",
        "repository": {"full_name": REPO},
    }


def job_payload(job_id=1):
    return {
        "id": job_id, "run_id": 701, "run_attempt": 2, "head_sha": SHA,
        "name": f"pytest shard {job_id}", "status": "completed",
        "conclusion": "success", "started_at": "2026-11-04T10:00:10Z",
        "completed_at": "2026-11-04T10:03:10Z",
        "steps": [{"number": 1, "name": "Run repository test shard",
                   "status": "completed", "conclusion": "success",
                   "started_at": "2026-11-04T10:00:40Z",
                   "completed_at": "2026-11-04T10:03:00Z"}],
    }


def api_fixture(jobs=None, run=None, transform=None):
    rows = jobs if jobs is not None else [job_payload()]
    run = run if run is not None else run_payload()
    calls = []

    def read(path):
        calls.append(path)
        prefix = f"repos/{REPO}/actions/runs/701/attempts/2"
        if path == prefix:
            return copy.deepcopy(run)
        assert path.startswith(prefix + "/jobs?per_page=100&page=")
        page = int(path.rsplit("=", 1)[1])
        result = {"total_count": len(rows), "jobs": copy.deepcopy(rows[(page-1)*100:page*100])}
        return transform(page, result) if transform else result

    return read, calls


def test_completed_attempt_capture_is_paginated_and_preserves_native_bytes():
    jobs = [job_payload(i) for i in range(1, 102)]
    read, calls = api_fixture(jobs)
    snapshot = capture.capture_attempt(REPO, 701, 2, read_json=read)
    assert len(calls) == 3
    assert snapshot["run"] == run_payload()
    assert snapshot["jobs"] == {"total_count": 101, "jobs": jobs}
    assert "observed_at" in snapshot
    assert all("/attempts/2" in path for path in calls)
    profile = capture.build_profile(snapshot)
    assert profile["complete_jobs"] is True
    assert profile["identity"]["run_attempt"] == 2


@pytest.mark.parametrize("repo", ["../repo", "org/..", "org/repo/extra", "org/repo?x=1", "org/repo#x", "https://evil/x", "org/rep\no", ""])
def test_invalid_repository_refused_before_network(repo):
    with pytest.raises(capture.CaptureError):
        capture.capture_attempt(repo, 701, 2, read_json=lambda _: pytest.fail("network"))


@pytest.mark.parametrize("run_id,attempt", [(True, 2), (701, False), (0, 2), (701, 0), (-1, 2), (701, "2")])
def test_invalid_numeric_identity_refused_before_network(run_id, attempt):
    with pytest.raises(capture.CaptureError):
        capture.capture_attempt(REPO, run_id, attempt, read_json=lambda _: pytest.fail("network"))


@pytest.mark.parametrize("field,value", [
    ("id", 702), ("run_attempt", 3), ("status", "in_progress"),
    ("name", "untrusted"), ("path", ".github/workflows/other.yml"),
    ("repository", {"full_name": "other/repo"}), ("head_sha", "not-a-sha"),
])
def test_wrong_run_or_workflow_is_not_profiled(field, value):
    run = run_payload()
    run[field] = value
    read, _ = api_fixture(run=run)
    with pytest.raises((capture.CaptureError, capture.ProfileError)):
        capture.capture_attempt(REPO, 701, 2, read_json=read)


@pytest.mark.parametrize("kind", ["count_drift", "empty_page", "duplicate", "oversized_count", "bad_shape", "short_page"])
def test_incomplete_or_inconsistent_pagination_refuses(kind):
    jobs = [job_payload(i) for i in range(1, 102)]
    def transform(page, result):
        if kind == "oversized_count": result["total_count"] = capture.MAX_JOBS + 1
        if kind == "bad_shape": result["jobs"] = {}
        if kind == "short_page" and page == 1: result["jobs"] = result["jobs"][:2]
        if page == 2:
            if kind == "count_drift": result["total_count"] += 1
            if kind == "empty_page": result["jobs"] = []
            if kind == "duplicate": result["jobs"] = [job_payload(1)]
        return result
    read, _ = api_fixture(jobs, transform=transform)
    with pytest.raises((capture.CaptureError, capture.ProfileError)):
        capture.capture_attempt(REPO, 701, 2, read_json=read)


def test_missing_native_job_attempt_is_not_fabricated():
    job = job_payload()
    del job["run_attempt"]
    read, _ = api_fixture([job])
    snapshot = capture.capture_attempt(REPO, 701, 2, read_json=read)
    assert "run_attempt" not in snapshot["jobs"]["jobs"][0]
    assert capture.build_profile(snapshot)["identity_verified"] is False


def test_mixed_attempts_and_duplicate_jobs_are_rejected_by_existing_owner():
    job = job_payload()
    job["run_attempt"] = 1
    read, _ = api_fixture([job])
    with pytest.raises(capture.ProfileError):
        capture.capture_attempt(REPO, 701, 2, read_json=read)


def test_report_escapes_untrusted_names_and_does_not_claim_delivery_or_queue():
    job = job_payload()
    job["name"] = "<img src=x> | @everyone\n[steal](https://bad)"
    job["conclusion"] = "failure"
    read, _ = api_fixture([job])
    text = capture.render_summary(capture.build_profile(capture.capture_attempt(REPO, 701, 2, read_json=read)))
    assert "<img" not in text
    assert "@everyone" not in text
    assert "[steal](" not in text
    assert "Not a merge, deployment, or acceptance verdict" in text
    assert "not runner queue time" in text
    assert "failure" in text
    assert "3.17" in text  # 190 seconds from creation to actual last job end.


def test_zero_jobs_stay_an_evidence_gap():
    read, _ = api_fixture([])
    profile = capture.build_profile(capture.capture_attempt(REPO, 701, 2, read_json=read))
    assert profile["complete_jobs"] is False
    assert "Evidence gaps" in capture.render_summary(profile)


def test_network_reader_uses_fixed_https_get_and_no_secret_output():
    requests = []
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return Response(b'{"ok": true}')
    read = capture.github_reader("secret-value", opener=Opener())
    assert read("repos/org/repo/actions/runs/1/attempts/1") == {"ok": True}
    request, timeout = requests[0]
    assert request.full_url.startswith("https://api.github.com/repos/")
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer secret-value"
    assert 0 < timeout <= 30
    with pytest.raises(capture.CaptureError): read("https://evil.example/steal")


@pytest.mark.parametrize("error", [HTTPError("https://x", 403, "secret-value", {}, None), URLError("secret-value")])
def test_network_errors_are_sanitized_and_never_retried(error):
    calls = []
    class Opener:
        def open(self, *args, **kwargs):
            calls.append(1)
            raise error
    with pytest.raises(capture.CaptureError) as exc:
        capture.github_reader("secret-value", opener=Opener())("repos/org/repo/actions/runs/1/attempts/1")
    assert "secret-value" not in str(exc.value)
    assert len(calls) == 1


def test_redirects_are_not_followed():
    assert capture.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil") is None


def test_output_files_are_the_original_snapshot_and_existing_profile(tmp_path):
    read, _ = api_fixture()
    snapshot = capture.capture_attempt(REPO, 701, 2, read_json=read)
    capture.write_report(snapshot, tmp_path / "report")
    assert sorted(p.name for p in (tmp_path / "report").iterdir()) == ["profile.json", "snapshot.json", "summary.md"]
    assert json.loads((tmp_path / "report/snapshot.json").read_text()) == snapshot
    assert json.loads((tmp_path / "report/profile.json").read_text())["schema"] == "ci-run-profile/1"
    with pytest.raises(FileExistsError): capture.write_report(snapshot, tmp_path / "report")


def test_actions_consumer_is_read_only_nonblocking_and_never_executes_pr_source():
    import yaml
    from scripts.ci_pytest import _WorkflowYAMLLoader
    data = yaml.load((ROOT / ".github/workflows/ci-profile.yml").read_text(), Loader=_WorkflowYAMLLoader)
    assert data["on"]["workflow_run"] == {"workflows": ["CI"], "types": ["completed"]}
    assert data["permissions"] == {"contents": "read", "actions": "read"}
    assert data["concurrency"]["cancel-in-progress"] is False
    job = data["jobs"]["profile"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["if"] == "github.event_name == 'workflow_run' || github.ref == 'refs/heads/master'"
    assert "permissions" not in job  # no broader per-job override
    import re
    assert all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"])
               for step in job["steps"] if "uses" in step)
    assert 1 <= job["timeout-minutes"] <= 10
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    text = (ROOT / ".github/workflows/ci-profile.yml").read_text()
    for forbidden in ("pull_request_target", "head_sha }}", "download-artifact", "pull-requests: write", "contents: write", "workflow_dispatch --", "gh pr merge"):
        assert forbidden not in text
    assert "ci-profile" not in (ROOT / ".github/workflows/ci.yml").read_text()


def test_native_attempt_jobs_url_is_accepted_without_rewriting_evidence():
    run = run_payload()
    run["jobs_url"] = f"https://api.github.com/repos/{REPO}/actions/runs/701/attempts/2/jobs"
    read, _ = api_fixture(run=run)
    snapshot = capture.capture_attempt(REPO, 701, 2, read_json=read)
    assert snapshot["run"]["jobs_url"] == run["jobs_url"]
    assert capture.build_profile(snapshot)["source_urls"]["jobs_api_url"] == run["jobs_url"]


@pytest.mark.parametrize("suffix", ["/attempts/1/jobs", "/attempts/3/jobs", "/attempts/2/jobs?x=1", "/attempts/2/jobs/", "/attempts/02/jobs"])
def test_attempt_url_must_bind_the_exact_native_attempt(suffix):
    run = run_payload()
    run["jobs_url"] = f"https://api.github.com/repos/{REPO}/actions/runs/701{suffix}"
    read, _ = api_fixture(run=run)
    with pytest.raises(capture.ProfileError):
        capture.capture_attempt(REPO, 701, 2, read_json=read)


def test_short_failed_job_is_visible_even_when_not_in_slowest_fifteen():
    jobs = [job_payload(i) for i in range(1, 18)]
    jobs[-1].update(name="important-short-failure", conclusion="failure",
                    completed_at="2026-11-04T10:00:11Z", steps=[])
    read, _ = api_fixture(jobs)
    text = capture.render_summary(capture.build_profile(capture.capture_attempt(REPO, 701, 2, read_json=read)))
    assert "important-short-failure" not in text.split("## Failed or incomplete jobs")[0]
    assert "important-short-failure" in text.split("## Failed or incomplete jobs")[1]


@pytest.mark.parametrize("payload", [b'[]', b'{invalid', b'\xff', b'x' * (capture.MAX_INPUT_BYTES + 1)])
def test_reader_rejects_malformed_or_oversized_metadata(payload):
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def open(self, *args, **kwargs): return Response(payload)
    with pytest.raises(capture.CaptureError):
        capture.github_reader("test", opener=Opener())("repos/org/repo/actions/runs/1/attempts/1")
