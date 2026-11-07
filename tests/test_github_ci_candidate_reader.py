"""Real GitHub response shapes into the existing exact-candidate classifier."""
from __future__ import annotations

import copy
import importlib

import pytest

from control_plane.github_release_assessment import CandidateCIState

REPO = "mastermindx-market-intelligence/Mastermind"
HEAD = "a" * 40
BASE = "b" * 40
APP = 15368
PREFIX = f"repos/{REPO}"
PR_PATH = f"{PREFIX}/pulls/1500"
BRANCH_PATH = f"{PREFIX}/branches/master"
RULES_PATH = f"{PREFIX}/rules/branches/master?per_page=100&page=1"
CHECKS_PATH = f"{PREFIX}/commits/{HEAD}/check-runs?filter=latest&per_page=100&page=1"
WORKFLOW_PATH = f"{PREFIX}/actions/runs/900"


def fixture_api():
    repository = {"id": 1317762013, "full_name": REPO}
    return {
        PR_PATH: {"number": 1500, "state": "open", "head": {"ref": "sol/web-throughput", "sha": HEAD, "repo": repository}, "base": {"ref": "master", "sha": BASE, "repo": repository}},
        BRANCH_PATH: {"name": "master", "protected": True, "protection": {"required_status_checks": {"strict": True, "contexts": ["test"], "checks": [{"context": "test", "app_id": APP}]}}},
        RULES_PATH: [],
        CHECKS_PATH: {"total_count": 1, "check_runs": [{"id": 901, "name": "test", "head_sha": HEAD, "status": "completed", "conclusion": "success", "app": {"id": APP}, "check_suite": {"id": 800}, "details_url": f"https://github.com/{REPO}/actions/runs/900/job/901"}]},
        WORKFLOW_PATH: {"id": 900, "head_sha": HEAD, "check_suite_id": 800, "run_attempt": 2},
        f"{WORKFLOW_PATH}/attempts/2/jobs?per_page=100&page=1": {"total_count": 1, "jobs": [{"id": 901, "run_id": 900, "run_attempt": 2, "head_sha": HEAD, "check_run_url": f"https://api.github.com/{PREFIX}/check-runs/901"}]},
    }


def reader(api):
    module = importlib.import_module("integrations.github_ci_candidate_reader")
    calls = []
    def read(endpoint):
        calls.append(endpoint)
        value = api[endpoint]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)
    return module.GitHubCandidateReader(read=read, clock=lambda: 1800000000), calls


def test_owner_native_snapshot_reaches_existing_green_classifier():
    subject, calls = reader(fixture_api())
    result = subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert result.state is CandidateCIState.GREEN
    assert result.latest_checks[0].workflow_run_id == 900
    assert result.latest_checks[0].attempt == 2
    assert result.latest_checks[0].check_run_id == 901
    assert calls.count(PR_PATH) == 2
    assert all(ref.owner.value == "github" for ref in result.source_refs)
    assert all(len(ref.content_sha256) == 64 for ref in result.source_refs)


@pytest.mark.parametrize("status,conclusion,expected", [("queued", None, CandidateCIState.PENDING), ("in_progress", None, CandidateCIState.PENDING), ("completed", "failure", CandidateCIState.FAILED), ("completed", "skipped", CandidateCIState.FAILED)])
def test_native_check_states_are_not_reinterpreted(status, conclusion, expected):
    api = fixture_api()
    api[CHECKS_PATH]["check_runs"][0].update(status=status, conclusion=conclusion)
    subject, _ = reader(api)
    assert subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD).state is expected


def test_missing_required_check_is_pending_not_green():
    api = fixture_api()
    api[CHECKS_PATH] = {"total_count": 0, "check_runs": []}
    subject, _ = reader(api)
    assert subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD).state is CandidateCIState.PENDING


def test_ruleset_additional_check_is_not_omitted():
    api = fixture_api()
    api[RULES_PATH] = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "security", "integration_id": APP}]}}]
    subject, _ = reader(api)
    result = subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert result.state is CandidateCIState.PENDING
    assert {row.context for row in result.required_checks} == {"test", "security"}


def test_duplicate_latest_context_refuses_instead_of_guessing_generation():
    api = fixture_api()
    another = copy.deepcopy(api[CHECKS_PATH]["check_runs"][0])
    another.update(id=902, conclusion="failure")
    api[CHECKS_PATH] = {"total_count": 2, "check_runs": [api[CHECKS_PATH]["check_runs"][0], another]}
    subject, _ = reader(api)
    with pytest.raises(ValueError, match="ambiguous"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_declared_total_cannot_exceed_collected_rows():
    api = fixture_api()
    api[CHECKS_PATH]["total_count"] = 2
    subject, _ = reader(api)
    with pytest.raises(ValueError, match="coverage"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_cross_repository_workflow_url_is_not_followed():
    api = fixture_api()
    api[CHECKS_PATH]["check_runs"][0]["details_url"] = "https://github.com/other/project/actions/runs/900/job/901"
    subject, calls = reader(api)
    with pytest.raises(ValueError, match="workflow"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert WORKFLOW_PATH not in calls


def test_permission_failure_propagates_without_alternate_read():
    api = fixture_api()
    api[RULES_PATH] = PermissionError("denied")
    subject, calls = reader(api)
    with pytest.raises(PermissionError):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert calls.count(RULES_PATH) == 1
    assert CHECKS_PATH not in calls


@pytest.mark.parametrize("repository", ["../other", "https://example.com", "-x/y", "owner/repo?token=x"])
def test_invalid_repository_is_rejected_before_transport(repository):
    subject, calls = reader(fixture_api())
    with pytest.raises(ValueError):
        subject.sample(repository=repository, pull_request_number=1500, expected_head_sha=HEAD)
    assert calls == []


def changing_reader(api, endpoint, change):
    module = importlib.import_module("integrations.github_ci_candidate_reader")
    count = 0
    def read(path):
        nonlocal count
        value = copy.deepcopy(api[path])
        if path == endpoint:
            count += 1
            if count > 1:
                change(value)
        return value
    return module.GitHubCandidateReader(read=read, clock=lambda: 1800000000)


def test_unrelated_base_movement_does_not_restart_candidate_validation():
    subject = changing_reader(fixture_api(), PR_PATH, lambda doc: doc["base"].update(sha="c" * 40))
    assert subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD).state is CandidateCIState.GREEN


def test_candidate_movement_during_collection_refuses():
    subject = changing_reader(fixture_api(), PR_PATH, lambda doc: doc["head"].update(sha="c" * 40))
    with pytest.raises(ValueError, match="candidate changed"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_policy_change_during_collection_refuses():
    def changed(doc):
        doc["protection"]["required_status_checks"]["strict"] = False
    subject = changing_reader(fixture_api(), BRANCH_PATH, changed)
    with pytest.raises(ValueError, match="policy changed"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_old_expected_head_produces_stale_not_success():
    subject, _ = reader(fixture_api())
    assert subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha="d" * 40).state is CandidateCIState.STALE


def test_ruleset_permission_error_never_means_no_required_checks():
    api = fixture_api()
    api[RULES_PATH] = PermissionError("forbidden")
    subject, _ = reader(api)
    with pytest.raises(PermissionError):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


@pytest.mark.parametrize("field,value", [("id", 999), ("head_sha", "e" * 40), ("check_suite_id", 799), ("run_attempt", True)])
def test_workflow_generation_is_verified(field, value):
    api = fixture_api()
    api[WORKFLOW_PATH][field] = value
    subject, _ = reader(api)
    with pytest.raises(ValueError, match="workflow"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


@pytest.mark.parametrize("producer", [None, -1, 42, True])
def test_unqualified_required_producer_is_explicitly_unsupported(producer):
    api = fixture_api()
    api[BRANCH_PATH]["protection"]["required_status_checks"]["checks"][0]["app_id"] = producer
    subject, calls = reader(api)
    with pytest.raises(ValueError, match="producer"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert CHECKS_PATH not in calls


def test_complete_check_pagination_uses_all_pages():
    api = fixture_api()
    wanted = api[CHECKS_PATH]["check_runs"][0]
    unrelated = [{**copy.deepcopy(wanted), "id": 1000 + i, "name": f"unrelated-{i}"} for i in range(100)]
    api[CHECKS_PATH] = {"total_count": 101, "check_runs": unrelated}
    api[CHECKS_PATH.replace("page=1", "page=2")] = {"total_count": 101, "check_runs": [wanted]}
    subject, calls = reader(api)
    assert subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD).state is CandidateCIState.GREEN
    assert any(path.endswith("page=2") for path in calls)


def test_checks_changed_during_pagination_refuses():
    api = fixture_api()
    wanted = api[CHECKS_PATH]["check_runs"][0]
    api[CHECKS_PATH] = {"total_count": 101, "check_runs": [{**copy.deepcopy(wanted), "id": 1000 + i, "name": f"other-{i}"} for i in range(100)]}
    api[CHECKS_PATH.replace("page=1", "page=2")] = {"total_count": 102, "check_runs": [wanted]}
    subject, _ = reader(api)
    with pytest.raises(ValueError, match="coverage changed"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)


def test_cross_repository_candidate_is_not_adopted():
    api = fixture_api()
    api[PR_PATH]["head"]["repo"] = {"id": 99, "full_name": "other/fork"}
    subject, calls = reader(api)
    with pytest.raises(ValueError, match="cross-repository"):
        subject.sample(repository=REPO, pull_request_number=1500, expected_head_sha=HEAD)
    assert calls == [PR_PATH]
