"""Fail-closed native merge-group reuse: no unproven master push may omit pytest."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import ci_postmerge_proof as proof


_SHA = "2d7284af863e4435e83e176498feb62041716753"
_RUN_ID = 38967208427
_REPO = "mastermindx-market-intelligence/Mastermind"
_PREFIX = f"/repos/{_REPO}"


def _env() -> dict[str, str]:
    return {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/master",
        "GITHUB_REPOSITORY": _REPO,
        "GITHUB_SHA": _SHA,
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_RUN_ID": "39999999999",
        "GITHUB_RUN_ATTEMPT": "1",
        "GH_TOKEN": "test-token-never-log",
    }


def _run() -> dict:
    return {
        "id": _RUN_ID,
        "run_attempt": 1,
        "workflow_id": 324108847,
        "event": "merge_group",
        "head_sha": _SHA,
        "path": ".github/workflows/ci.yml",
        "head_branch": "gh-readonly-queue/master/pr-1476-proven",
        "created_at": "2026-10-16T21:07:58Z",
        "updated_at": "2026-10-16T21:36:05Z",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": _REPO},
        "head_repository": {"full_name": _REPO},
    }


def _push() -> dict:
    return {
        "id": 39999999999,
        "run_attempt": 1,
        "workflow_id": 324108847,
        "event": "push",
        "head_sha": _SHA,
        "head_branch": "master",
        "path": ".github/workflows/ci.yml",
        "status": "in_progress",
        "conclusion": None,
        "created_at": "2026-10-16T21:36:27Z",
        "actor": {"login": "github-merge-queue[bot]", "type": "Bot"},
        "triggering_actor": {"login": "github-merge-queue[bot]", "type": "Bot"},
        "repository": {"full_name": _REPO},
        "head_repository": {"full_name": _REPO},
    }


def _steps(index: int) -> list[dict]:
    names = (
        ["Verify Paper direct pinned MCP SDK",
         "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
         "Compile source", "Validate shell scripts", "Run repository test shard"]
        if index == 0 else
        ["Run repository test gate"] if index == 3 else
        ["Run repository test shard"]
    )
    return [{"name": name, "status": "completed", "conclusion": "success"} for name in names]


def _jobs() -> dict:
    names = ["pytest shard 0", "pytest shard 1", "pytest shard 2", "test"]
    return {
        "total_count": 4,
        "jobs": [
            {
                "id": 117196531521 + index,
                "name": name,
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-16T21:08:01Z",
                "completed_at": "2026-10-16T21:35:00Z",
                "head_sha": _SHA,
                "run_id": _RUN_ID,
                "run_attempt": 1,
                "workflow_name": "CI",
                "steps": _steps(index),
                "check_run_url": f"https://api.github.com{_PREFIX}/check-runs/{117196531521 + index}",
            }
            for index, name in enumerate(names)
        ],
    }


def _subject() -> dict[str, dict]:
    return {
        "listing": {"total_count": 1, "workflow_runs": [_run()]},
        "jobs": _jobs(),
        "recheck": _run(),
        "current": _push(),
        "current_recheck": _push(),
    }


def _read(subject: dict, touched: list[str] | None = None):
    current_reads = 0

    def fetch(path: str):
        nonlocal current_reads
        if touched is not None:
            touched.append(path)
        if path == f"{_PREFIX}/actions/runs/39999999999":
            current_reads += 1
            key = "current" if current_reads == 1 else "current_recheck"
            return deepcopy(subject[key])
        if path == (
            f"{_PREFIX}/actions/workflows/ci.yml/runs"
            f"?event=merge_group&head_sha={_SHA}&per_page=100"
        ):
            return deepcopy(subject["listing"])
        if path == f"{_PREFIX}/actions/runs/{_RUN_ID}/attempts/1/jobs?per_page=100":
            return deepcopy(subject["jobs"])
        if path == f"{_PREFIX}/actions/runs/{_RUN_ID}":
            return deepcopy(subject["recheck"])
        raise AssertionError("unexpected endpoint")

    return fetch


def test_exact_same_sha_successful_merge_group_reuses_only_complete_four_jobs():
    touched: list[str] = []
    assert proof.find_reusable_run(_env(), read_json=_read(_subject(), touched)) == _RUN_ID
    assert len(touched) == 5
    assert all(path.startswith(_PREFIX + "/actions/") for path in touched)


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_EVENT_NAME", "merge_group"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_REPOSITORY", "other/repo"),
        ("GITHUB_SHA", "bad"),
        ("GITHUB_API_URL", "https://malicious.example"),
        ("GITHUB_RUN_ID", ""),
        ("GITHUB_RUN_ATTEMPT", "0"),
        ("GH_TOKEN", ""),
    ],
)
def test_unproven_source_never_queries_api(key: str, replacement: str):
    env = _env()
    env[key] = replacement
    touched: list[str] = []
    assert proof.find_reusable_run(env, read_json=_read(_subject(), touched)) is None
    assert touched == []


@pytest.mark.parametrize(
    ("target", "path", "value"),
    [
        ("current", ("head_branch",), "other"),
        ("current", ("event",), "pull_request"),
        ("current", ("head_sha",), "f" * 40),
        ("current", ("run_attempt",), 2),
        ("current", ("status",), "queued"),
        ("current_recheck", ("run_attempt",), 2),
        ("current_recheck", ("head_sha",), "f" * 40),
        ("current_recheck", ("actor", "login"), "mastermindxryan"),
        ("current_recheck", ("triggering_actor", "type"), "User"),
        ("listing", ("total_count",), 0),
        ("listing", ("total_count",), 2),
        ("listing", ("workflow_runs", 0, "event"), "push"),
        ("listing", ("workflow_runs", 0, "status"), "in_progress"),
        ("listing", ("workflow_runs", 0, "conclusion"), "failure"),
        ("listing", ("workflow_runs", 0, "path"), ".github/workflows/other.yml"),
        ("listing", ("workflow_runs", 0, "repository", "full_name"), "other/repo"),
        ("listing", ("workflow_runs", 0, "head_repository", "full_name"), "other/repo"),
        ("listing", ("workflow_runs", 0, "head_sha"), "f" * 40),
        ("listing", ("workflow_runs", 0, "head_branch"), "other"),
        ("listing", ("workflow_runs", 0, "workflow_id"), 123456),
        ("listing", ("workflow_runs", 0, "updated_at"), "2026-10-16T22:36:05Z"),
        ("listing", ("workflow_runs", 0, "run_attempt"), 0),
        ("listing", ("workflow_runs", 0, "run_attempt"), 2),
        ("jobs", ("jobs", 0, "started_at"), "2026-10-16T21:40:00Z"),
        ("jobs", ("jobs", 2, "completed_at"), "2026-10-16T21:00:00Z"),
        ("jobs", ("total_count",), 3),
        ("jobs", ("jobs", 0, "status"), "skipped"),
        ("jobs", ("jobs", 0, "conclusion"), "skipped"),
        ("jobs", ("jobs", 0, "conclusion"), "neutral"),
        ("jobs", ("jobs", 0, "conclusion"), "failure"),
        ("jobs", ("jobs", 1, "name"), "pytest shard 0"),
        ("jobs", ("jobs", 2, "run_attempt"), 2),
        ("jobs", ("jobs", 2, "head_sha"), "f" * 40),
        ("jobs", ("jobs", 0, "run_id"), 5),
        ("jobs", ("jobs", 0, "check_run_url"), "https://example.com/false"),
        ("jobs", ("jobs", 0, "workflow_name"), "Unknown"),
        ("jobs", ("jobs", 0, "steps", 0, "conclusion"), "skipped"),
        ("jobs", ("jobs", 0, "steps", 4, "conclusion"), "skipped"),
        ("jobs", ("jobs", 1, "steps", 0, "conclusion"), "skipped"),
        ("jobs", ("jobs", 2, "steps", 0, "name"), "echo bypass"),
        ("jobs", ("jobs", 3, "steps", 0, "conclusion"), "skipped"),
        ("jobs", ("jobs", 3, "steps"), []),
        ("recheck", ("run_attempt",), 2),
        ("recheck", ("conclusion",), "failure"),
        ("recheck", ("head_sha",), "f" * 40),
    ],
)
def test_false_green_and_stale_run_evidence_always_falls_back(
    target: str, path: tuple, value: object
):
    sample = _subject()
    element = sample[target]
    for key in path[:-1]:
        element = element[key]
    element[path[-1]] = value
    assert proof.find_reusable_run(_env(), read_json=_read(sample)) is None


def test_other_valid_commit_must_use_its_own_exact_sha():
    env = _env()
    env["GITHUB_SHA"] = "1" * 40
    touched: list[str] = []

    def no_matching_group(path: str):
        touched.append(path)
        if path == f"{_PREFIX}/actions/runs/39999999999":
            record = _push()
            record["head_sha"] = "1" * 40
            return record
        return {"total_count": 0, "workflow_runs": []}

    assert proof.find_reusable_run(env, read_json=no_matching_group) is None
    assert len(touched) == 2
    assert "head_sha=" + "1" * 40 in touched[1]


@pytest.mark.parametrize(
    ("actor_field", "replacement"),
    [
        ("actor", {"login": "mastermindxryan", "type": "User"}),
        ("triggering_actor", {"login": "mastermindxryan", "type": "User"}),
        ("actor", {"login": "github-merge-queue[bot]", "type": "User"}),
        ("triggering_actor", {"login": "github-merge-queue[bot]", "type": "User"}),
        ("actor", None),
        ("triggering_actor", None),
    ],
)
def test_direct_or_unverified_push_actor_cannot_reuse(
    actor_field: str, replacement: object,
):
    sample = _subject()
    sample["current"][actor_field] = replacement
    sample["current_recheck"][actor_field] = replacement
    assert proof.find_reusable_run(_env(), read_json=_read(sample)) is None


def test_second_matching_run_is_ambiguous_and_cannot_reuse():
    sample = _subject()
    sample["listing"]["workflow_runs"].append(_run())
    sample["listing"]["total_count"] = 2
    assert proof.find_reusable_run(_env(), read_json=_read(sample)) is None


def test_missing_job_and_job_duplication_cannot_reuse():
    sample = _subject()
    sample["jobs"]["jobs"][3] = deepcopy(sample["jobs"]["jobs"][0])
    assert proof.find_reusable_run(_env(), read_json=_read(sample)) is None


def test_auth_denial_and_api_failure_fall_back_to_full_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    output = tmp_path / "output"
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def denied(*args, **kwargs):
        raise PermissionError("Actions read denied")

    monkeypatch.setattr(proof, "_github_read", denied)
    assert proof.main() == 0
    assert output.read_text() == "reuse=false\n"
    assert "test-token-never-log" not in output.read_text()


def test_invalid_or_absent_output_path_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert proof.main() != 0


@pytest.mark.parametrize("failed_stage", [None, 0, 1, 2])
def test_checkout_proof_checks_head_worktree_and_index(
    failed_stage: int | None, monkeypatch: pytest.MonkeyPatch
):
    from types import SimpleNamespace

    commands: list[tuple[str, ...]] = []

    def fake_run(argv, **kwargs):
        commands.append(tuple(argv))
        fail = failed_stage == len(commands) - 1
        return SimpleNamespace(
            returncode=1 if fail else 0,
            stdout=_SHA if argv[1] == "rev-parse" else "",
        )

    monkeypatch.setattr(proof.subprocess, "run", fake_run)
    assert proof._checkout_identity_proven(_SHA) is (failed_stage is None)
    assert commands[0] == ("git", "rev-parse", "--verify", "HEAD")
    if failed_stage is None:
        assert commands[1] == ("git", "diff", "--quiet", "--")
        assert commands[2] == ("git", "diff", "--cached", "--quiet", "--")


def test_wrong_local_head_cannot_reuse_even_when_git_is_clean(
    monkeypatch: pytest.MonkeyPatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        proof.subprocess, "run",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=("f" * 40) if argv[1] == "rev-parse" else "",
        ),
    )
    assert proof._checkout_identity_proven(_SHA) is False


def test_live_proof_with_changed_checkout_falls_back_to_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    output = tmp_path / "output"
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(proof, "_checkout_identity_proven", lambda sha: False)
    monkeypatch.setattr(proof, "_github_read", lambda path, token: _read(_subject())(path))
    assert proof.main() == 0
    assert output.read_text() == "reuse=false\n"


def test_verified_output_requires_exact_five_api_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    output = tmp_path / "output"
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(proof, "_checkout_identity_proven", lambda sha: True)
    monkeypatch.setattr(proof, "_github_read", lambda path, token: _read(_subject())(path))
    assert proof.main() == 0
    assert output.read_text() == "reuse=true\n"
