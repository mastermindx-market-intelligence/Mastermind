"""The native consumer uses real H5 observation/wait code, not an LLM poll loop."""
from __future__ import annotations

import copy
import importlib

import pytest

from integrations.github_ci_candidate_reader import GitHubCandidateReader
from tests.test_github_ci_candidate_reader import APP, CHECKS_PATH, HEAD, REPO, fixture_api


def cli():
    return importlib.import_module("scripts.github_ci_candidate")


def test_completed_candidate_returns_once_without_sleeping():
    api = fixture_api()
    reader = GitHubCandidateReader(read=lambda path: copy.deepcopy(api[path]), clock=lambda: 1800000000)
    slept = []
    result = cli().observe_candidate(reader=reader, repository=REPO, pull_request_number=1500, expected_head_sha=HEAD, max_samples=5, interval_seconds=60, wait=slept.append)
    assert result["observation"]["state"] == "GREEN"
    assert result["material_return"] is True
    assert result["sample_count"] == 1
    assert result["release_authorized"] is False
    assert result["wake_delivered"] is False
    assert slept == []


def test_pending_progress_is_suppressed_until_existing_waiter_returns_material():
    api = fixture_api()
    api[CHECKS_PATH]["check_runs"][0].update(status="queued", conclusion=None)
    reader = GitHubCandidateReader(read=lambda path: copy.deepcopy(api[path]), clock=lambda: 1800000000)
    waits = []
    def wait(seconds):
        waits.append(seconds)
        api[CHECKS_PATH]["check_runs"][0].update(status="completed", conclusion="success")
    result = cli().observe_candidate(reader=reader, repository=REPO, pull_request_number=1500, expected_head_sha=HEAD, max_samples=3, interval_seconds=60, wait=wait)
    assert result["observation"]["state"] == "GREEN"
    assert result["material_return"] is True
    assert result["sample_count"] == 2
    assert waits == [60]
    assert result["decision"]["candidate_state"] == "GREEN"


def test_exhausted_wait_is_not_completion_or_delivered_wake():
    api = fixture_api()
    api[CHECKS_PATH]["check_runs"][0].update(status="in_progress", conclusion=None)
    reader = GitHubCandidateReader(read=lambda path: copy.deepcopy(api[path]), clock=lambda: 1800000000)
    slept = []
    result = cli().observe_candidate(reader=reader, repository=REPO, pull_request_number=1500, expected_head_sha=HEAD, max_samples=2, interval_seconds=60, wait=slept.append)
    assert result["observation"]["state"] == "PENDING"
    assert result["material_return"] is False
    assert result["wake_delivered"] is False
    assert result["release_authorized"] is False
    assert slept == [60, 60]


@pytest.mark.parametrize("count", [-1, 121, True])
def test_invalid_wait_budget_fails_before_read(count):
    class Reader:
        def sample(self, **kwargs):
            pytest.fail("no network read permitted for invalid arguments")
    with pytest.raises(ValueError):
        cli().observe_candidate(reader=Reader(), repository=REPO, pull_request_number=1500, expected_head_sha=HEAD, max_samples=count, interval_seconds=60)


@pytest.mark.parametrize("endpoint", ["https://example.com", "repos/owner/repo/issues", "repos/owner/repo/pulls/1?access_token=x", "repos/owner/repo/actions/runs/1/rerun", "-X POST"])
def test_cli_transport_has_only_closed_get_endpoints(endpoint):
    with pytest.raises(ValueError):
        cli().GitHubCLIReader().read(endpoint)


@pytest.mark.parametrize("state,code", [("GREEN", 0), ("FAILED", 1), ("UNKNOWN", 2), ("STALE", 3), ("PENDING", 4)])
def test_exit_codes_do_not_turn_pending_or_stale_into_success(state, code):
    assert cli().exit_code(state) == code


def test_fresh_baseline_is_not_immediately_read_again_before_cadence():
    api = fixture_api()
    api[CHECKS_PATH]["check_runs"][0].update(status="queued", conclusion=None)
    reader = GitHubCandidateReader(read=lambda path: copy.deepcopy(api[path]), clock=lambda: 1800000000)
    calls = []
    class TracedReader:
        def sample(self, **kwargs):
            calls.append("sample")
            if len(calls) > 1:
                assert calls[-2] == "wait", "fresh baseline triggered redundant API sampling"
            return reader.sample(**kwargs)
    def wait(seconds):
        calls.append("wait")
        api[CHECKS_PATH]["check_runs"][0].update(status="completed", conclusion="success")
    result = cli().observe_candidate(reader=TracedReader(), repository=REPO, pull_request_number=1500, expected_head_sha=HEAD, max_samples=2, interval_seconds=60, wait=wait)
    assert calls == ["sample", "wait", "sample"]
    assert result["sample_count"] == 2
