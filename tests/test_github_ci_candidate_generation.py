"""Adverse real-API generation cases; no live workflow is mutated."""
from __future__ import annotations

import copy

import pytest

from control_plane.github_release_assessment import CandidateCIState
from integrations.github_ci_candidate_reader import CandidateReadError, GitHubCandidateReader
from tests.test_github_ci_candidate_reader import (
    CHECKS_PATH, HEAD, PREFIX, REPO, WORKFLOW_PATH, fixture_api,
)

JOBS_PATH = f"{WORKFLOW_PATH}/attempts/2/jobs?per_page=100&page=1"


def api_with_jobs():
    api = fixture_api()
    api[JOBS_PATH] = {"total_count": 1, "jobs": [{
        "id": 901, "run_id": 900, "run_attempt": 2, "head_sha": HEAD,
        "check_run_url": f"https://api.github.com/{PREFIX}/check-runs/901",
    }]}
    return api


def observed(api, change=None):
    counts = {}
    def read(path):
        counts[path] = counts.get(path, 0) + 1
        row = copy.deepcopy(api[path])
        if change is not None:
            change(path, counts[path], row)
        return row
    reader = GitHubCandidateReader(read=read, clock=lambda: 1800000000)
    return reader.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_old_success_does_not_qualify_a_new_attempt_without_that_check():
    api = api_with_jobs()
    api[JOBS_PATH] = {"total_count": 0, "jobs": []}
    with pytest.raises(CandidateReadError, match="current workflow attempt"):
        observed(api)


@pytest.mark.parametrize("field,value", [
    ("run_id", 999), ("run_attempt", 1), ("head_sha", "e" * 40),
    ("check_run_url", "https://api.github.com/repos/foreign/repo/check-runs/901"),
    ("run_attempt", True),
])
def test_job_membership_cannot_be_borrowed_from_another_identity(field, value):
    api = api_with_jobs()
    api[JOBS_PATH]["jobs"][0][field] = value
    with pytest.raises(CandidateReadError, match="job|attempt"):
        observed(api)


def test_workflow_rerun_during_read_refuses_the_old_success():
    def change(path, count, row):
        if path == WORKFLOW_PATH and count > 1:
            row["run_attempt"] = 3
    with pytest.raises(CandidateReadError, match="generation changed"):
        observed(api_with_jobs(), change)


@pytest.mark.parametrize("status", ["waiting", "pending", "requested"])
def test_github_actions_waiting_states_are_pending_not_transport_failure(status):
    api = api_with_jobs()
    api[CHECKS_PATH]["check_runs"][0].update(status=status, conclusion=None)
    assert observed(api).state is CandidateCIState.PENDING


def test_current_attempt_job_membership_allows_success():
    assert observed(api_with_jobs()).state is CandidateCIState.GREEN


def test_job_pagination_is_complete_and_bounded():
    api = api_with_jobs()
    wanted = api[JOBS_PATH]["jobs"][0]
    api[JOBS_PATH] = {"total_count": 101, "jobs": [
        {**wanted, "id": 2000 + i, "check_run_url": f"https://api.github.com/{PREFIX}/check-runs/{2000 + i}"}
        for i in range(100)
    ]}
    api[f"{WORKFLOW_PATH}/attempts/2/jobs?per_page=100&page=2"] = {"total_count": 101, "jobs": [wanted]}
    assert observed(api).state is CandidateCIState.GREEN


def test_job_pagination_count_change_is_not_accepted():
    api = api_with_jobs()
    wanted = api[JOBS_PATH]["jobs"][0]
    api[JOBS_PATH] = {"total_count": 101, "jobs": [
        {**wanted, "id": 2000 + i, "check_run_url": f"https://api.github.com/{PREFIX}/check-runs/{2000 + i}"}
        for i in range(100)
    ]}
    api[f"{WORKFLOW_PATH}/attempts/2/jobs?per_page=100&page=2"] = {"total_count": 102, "jobs": [wanted]}
    with pytest.raises(CandidateReadError, match="job coverage"):
        observed(api)
