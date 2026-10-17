"""Fail-closed observation proof for avoiding *duplicate* postmerge CI work.

This test suite does not skip, alter, or own protected CI. The pure verifier is
not yet wired into any GitHub Actions step or a release decision.
"""
from __future__ import annotations

import copy

import pytest

from scripts.ci_merge_group_reuse import qualify_merge_group_proof

REPOSITORY = "mastermindx-market-intelligence/Mastermind"
HEAD = "c" * 40
RUN = 38885403814
WORKFLOW = 324108847
JOB_STEPS = {
    "pytest shard 0": [
        "Verify Paper direct pinned MCP SDK",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source", "Validate shell scripts", "Run repository test shard",
    ],
    "pytest shard 1": ["Run repository test shard"],
    "pytest shard 2": ["Run repository test shard"],
    "test": ["Run repository test gate"],
}


def proof_fixture():
    run = {
        "id": RUN, "workflow_id": WORKFLOW, "head_sha": HEAD,
        "head_branch": "gh-readonly-queue/master/pr-1476-fixture",
        "event": "merge_group", "status": "completed", "conclusion": "success",
        "path": ".github/workflows/ci.yml", "run_attempt": 1,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "created_at": "2026-10-16T10:10:00Z",
        "updated_at": "2026-10-16T10:42:10Z",
    }
    jobs = []
    for index, (name, steps) in enumerate(JOB_STEPS.items(), start=1):
        jobs.append({
            "id": index, "name": name, "run_id": RUN,
            "run_attempt": 1, "head_sha": HEAD,
            "status": "completed", "conclusion": "success",
            "started_at": "2026-10-16T10:15:00Z",
            "completed_at": "2026-10-16T10:41:59Z",
            "steps": [
                {"name": step, "status": "completed", "conclusion": "success"}
                for step in steps
            ],
        })
    return run, {"total_count": len(jobs), "jobs": jobs}


def qualified(run, jobs, *, event="push", ref="refs/heads/master", sha=HEAD,
              repo=REPOSITORY, workflow=WORKFLOW, push_at="2026-10-16T10:43:00Z"):
    return qualify_merge_group_proof(
        repository=repo, head_sha=sha, current_event=event, current_ref=ref,
        current_created_at=push_at, expected_workflow_id=workflow,
        workflow_run=run, workflow_jobs=jobs,
    )


def test_a_complete_prior_native_merge_group_proof_is_eligible():
    run, jobs = proof_fixture()
    ok, reason = qualified(run, jobs)
    assert ok and reason == "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN"


@pytest.mark.parametrize("event,ref", [
    ("pull_request", "refs/heads/master"),
    ("merge_group", "refs/heads/master"),
    ("push", "refs/heads/feature"),
    ("workflow_dispatch", "refs/heads/master"),
])
def test_only_master_pushes_are_eligible(event, ref):
    run, jobs = proof_fixture()
    assert not qualified(run, jobs, event=event, ref=ref)[0]


@pytest.mark.parametrize("mutation", [
    "head_mismatch", "event_not_merge_group", "workflow_path", "workflow_identity",
    "run_not_complete", "run_failure", "run_retry", "run_id_missing",
    "wrong_source_repository", "wrong_head_repository", "untrusted_queue_branch",
    "future_run", "corrupt_run_timestamp", "different_candidate_head",
])
def test_run_identity_and_causal_proof_fail_closed(mutation):
    run, jobs = proof_fixture()
    if mutation == "head_mismatch":run["head_sha"] = "d" * 40
    if mutation == "event_not_merge_group":run["event"] = "workflow_dispatch"
    if mutation == "workflow_path":run["path"] = ".github/workflows/unreviewed.yml"
    if mutation == "workflow_identity":run["workflow_id"] += 1
    if mutation == "run_not_complete":run["status"] = "in_progress"
    if mutation == "run_failure":run["conclusion"] = "failure"
    if mutation == "run_retry":run["run_attempt"] = 2
    if mutation == "run_id_missing":run.pop("id")
    if mutation == "wrong_source_repository":run["repository"]["full_name"] = "attacker/project"
    if mutation == "wrong_head_repository":run["head_repository"]["full_name"] = "attacker/project"
    if mutation == "untrusted_queue_branch":run["head_branch"] = "main"
    if mutation == "future_run":run["updated_at"] = "2026-10-16T10:44:01Z"
    if mutation == "corrupt_run_timestamp":run["updated_at"] = "garbage"
    if mutation == "different_candidate_head":
        assert not qualified(run, jobs, sha="e" * 40)[0]
        return
    assert not qualified(run, jobs)[0], mutation


@pytest.mark.parametrize("mutation", [
    "truncated", "extra_job", "duplicate_job", "missing_shard_zero", "skipped_shard",
    "failed_required_fanin", "wrong_sha", "wrong_run_id", "wrong_attempt",
    "uncompleted_shard", "missing_paper_gate", "missing_fabric_gate", "missing_shell_gate",
    "missing_compile", "missing_pytest", "missing_fanin", "skipped_fabric_gate",
    "future_job", "unknown_job_id", "invalid_steps",
])
def test_truncated_wrong_or_missing_job_proof_fails_closed(mutation):
    run, jobs = proof_fixture()
    target = jobs["jobs"][0]
    if mutation == "truncated":jobs["jobs"].pop()
    if mutation == "extra_job":
        jobs["jobs"].append(copy.deepcopy(target)); jobs["total_count"] += 1
    if mutation == "duplicate_job":jobs["jobs"][1]["name"] = target["name"]
    if mutation == "missing_shard_zero":target["name"] = "other"
    if mutation == "skipped_shard":target["conclusion"] = "skipped"
    if mutation == "failed_required_fanin":jobs["jobs"][-1]["conclusion"] = "failure"
    if mutation == "wrong_sha":target["head_sha"] = "d" * 40
    if mutation == "wrong_run_id":target["run_id"] += 1
    if mutation == "wrong_attempt":target["run_attempt"] += 1
    if mutation == "uncompleted_shard":target["status"] = "queued"
    if mutation == "missing_paper_gate":target["steps"] = [s for s in target["steps"] if not s["name"].startswith("Verify Paper")]
    if mutation == "missing_fabric_gate":target["steps"] = [s for s in target["steps"] if "Fabric HTTP" not in s["name"]]
    if mutation == "missing_shell_gate":target["steps"] = [s for s in target["steps"] if "shell scripts" not in s["name"]]
    if mutation == "missing_compile":target["steps"] = [s for s in target["steps"] if s["name"]!="Compile source"]
    if mutation == "missing_pytest":target["steps"] = [s for s in target["steps"] if s["name"]!="Run repository test shard"]
    if mutation == "missing_fanin":jobs["jobs"][-1]["steps"] = []
    if mutation == "skipped_fabric_gate":
        next(s for s in target["steps"] if "Fabric HTTP" in s["name"])["conclusion"]="skipped"
    if mutation == "future_job":target["completed_at"] = "2026-10-16T10:44:01Z"
    if mutation == "unknown_job_id":target["id"] = None
    if mutation == "invalid_steps":target["steps"] = "not a list"
    assert not qualified(run, jobs)[0], mutation


def test_unavailable_or_malformed_remote_evidence_does_not_authorize_reuse():
    run, jobs = proof_fixture()
    for artifact in (None, "not-json", [], {}, 1):
        assert not qualified(artifact, jobs)[0]
        assert not qualified(run, artifact)[0]


def test_unknown_or_invalid_expected_workflow_cannot_be_adopted():
    run, jobs = proof_fixture()
    for workflow in (None, -1, 0, True, "324108847", 324108848):
        assert not qualified(run, jobs, workflow=workflow)[0]


def test_boolean_attempts_and_inconsistent_job_clock_are_not_qualified():
    run, jobs = proof_fixture()
    run["run_attempt"] = True
    assert not qualified(run, jobs)[0]
    run, jobs = proof_fixture()
    jobs["jobs"][0]["run_attempt"] = True
    assert not qualified(run, jobs)[0]
    run, jobs = proof_fixture()
    jobs["jobs"][0]["completed_at"] = "2026-10-16T10:42:30Z"
    assert not qualified(run, jobs)[0], "A job cannot complete after the run"


def test_missing_or_naive_created_at_is_refused_before_any_consideration():
    run, jobs = proof_fixture()
    for stamp in (None, "", "2026-10-16T10:43:00", "not-an-iso-date", 0):
        assert not qualified(run, jobs, push_at=stamp)[0]


def test_duplicate_step_identity_is_not_a_success_witness():
    run, jobs = proof_fixture()
    steps = jobs["jobs"][0]["steps"]
    steps.append(copy.deepcopy(next(s for s in steps if s["name"] == "Run repository test shard")))
    assert not qualified(run, jobs)[0]



def _read_fixture(*, invalid: str | None = None):
    run, jobs = proof_fixture()
    now = dict(run)
    now.update(id=500, event="push", head_branch="master",
               created_at="2026-10-16T10:43:00Z", conclusion=None, status="in_progress")
    listing = {"total_count": 2, "workflow_runs": [now, run]}
    paths = {
        f"repos/{REPOSITORY}/actions/runs/500": now,
        f"repos/{REPOSITORY}/actions/runs?head_sha={HEAD}&per_page=100": listing,
        f"repos/{REPOSITORY}/actions/runs/{RUN}": run,
        f"repos/{REPOSITORY}/actions/runs/{RUN}/jobs?per_page=100": jobs,
    }
    calls = []
    def read(path: str):
        calls.append(path)
        if invalid == "read_denied":
            raise PermissionError("synthetic 403")
        if invalid == "not_json":
            return "not-json"
        return copy.deepcopy(paths[path])
    return read, calls, paths


def test_original_read_only_composer_resolves_exact_provider_run():
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    read, calls, paths = _read_fixture()
    result = find_prior_merge_group_proof(
        repository=REPOSITORY, head_sha=HEAD,
        current_event="push", current_ref="refs/heads/master", current_run_id=500,
        expected_workflow_id=WORKFLOW, read=read,
    )
    assert result == (True, "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN")
    assert calls == list(paths)


@pytest.mark.parametrize("event,ref", [( "pull_request", "refs/heads/master"),
    ("merge_group", "refs/heads/master"), ("push", "refs/heads/feature")])
def test_read_only_composer_never_issues_api_reads_outside_master_push(event, ref):
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    read, calls, _paths = _read_fixture()
    assert not find_prior_merge_group_proof(
        repository=REPOSITORY, head_sha=HEAD,current_event=event,
        current_ref=ref,current_run_id=500,expected_workflow_id=WORKFLOW,read=read,
    )[0]
    assert calls == []


@pytest.mark.parametrize("invalid", ["read_denied", "not_json"])
def test_read_only_composer_fails_closed_on_permission_or_transport_errors(invalid):
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    read, calls, _paths = _read_fixture(invalid=invalid)
    assert not find_prior_merge_group_proof(
        repository=REPOSITORY, head_sha=HEAD,current_event="push",
        current_ref="refs/heads/master",current_run_id=500,
        expected_workflow_id=WORKFLOW,read=read,
    )[0]
    assert len(calls) == 1


def test_read_only_composer_rejects_incomplete_run_listing():
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    read, calls, paths = _read_fixture()
    paths[f"repos/{REPOSITORY}/actions/runs?head_sha={HEAD}&per_page=100"]["total_count"] += 1
    assert not find_prior_merge_group_proof(
        repository=REPOSITORY, head_sha=HEAD,current_event="push",
        current_ref="refs/heads/master",current_run_id=500,
        expected_workflow_id=WORKFLOW,read=read,
    )[0]
    assert len(calls) == 2


def test_read_only_composer_requires_unambiguous_same_generation():
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    read, calls, paths = _read_fixture()
    listing = paths[f"repos/{REPOSITORY}/actions/runs?head_sha={HEAD}&per_page=100"]
    listing["workflow_runs"].append(copy.deepcopy(listing["workflow_runs"][1]))
    listing["total_count"] = 3
    assert not find_prior_merge_group_proof(
        repository=REPOSITORY, head_sha=HEAD,current_event="push",
        current_ref="refs/heads/master",current_run_id=500,
        expected_workflow_id=WORKFLOW,read=read,
    )[0]
    assert len(calls) == 2


@pytest.mark.parametrize("endpoint", [
    "https://api.github.com/repos/org/repo/actions/runs/1",
    "repos/org/repo/issues/1",
    "repos/org/repo/actions/runs/1/rerun",
    "repos/org/repo/actions/runs/1/jobs?per_page=100&other=value",
    "repos/org/repo/actions/runs?head_sha=bad&per_page=100",
])
def test_existing_gh_transport_rejects_nonallowed_urls_before_argv(endpoint):
    from scripts.ci_merge_group_reuse import read_json_via_existing_gh
    called = []
    def fake_process(*args, **kwargs):
        called.append(args)
        raise AssertionError("invalid endpoint must not spawn GH")
    with pytest.raises(ValueError, match="ENDPOINT_NOT_ALLOWED"):
        read_json_via_existing_gh(endpoint, run=fake_process, executable="/usr/bin/gh")
    assert called == []


def test_existing_gh_transport_has_only_one_bounded_get_no_retry():
    import subprocess
    from scripts.ci_merge_group_reuse import read_json_via_existing_gh
    called = []
    def fake_process(args, **kwargs):
        called.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout='{"hello":"world"}', stderr="ignored diagnostic")
    value = read_json_via_existing_gh(
        f"repos/{REPOSITORY}/actions/runs/{RUN}",
        run=fake_process, executable="/approved/gh",
    )
    assert value == {"hello": "world"}
    assert len(called) == 1
    args, kwargs = called[0]
    assert args[0] == "/approved/gh"
    assert args[1] == "api"
    assert "--method" in args and args[args.index("--method") + 1] == "GET"
    assert "--paginate" not in args
    assert kwargs["timeout"] <= 15


def test_existing_gh_transport_fails_closed_without_exposing_raw_provider_error():
    import subprocess
    from scripts.ci_merge_group_reuse import read_json_via_existing_gh
    def fake_process(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="PRIVATE: gh HTTP 403")
    with pytest.raises(ValueError) as error:
        read_json_via_existing_gh(
            f"repos/{REPOSITORY}/actions/runs/{RUN}",
            run=fake_process, executable="/approved/gh",
        )
    assert "PRIVATE" not in str(error.value)


def test_existing_gh_transport_rejects_nonjson_and_oversized_output():
    import subprocess
    from scripts.ci_merge_group_reuse import read_json_via_existing_gh
    for body in ("not-json", "x" * (2_000_000 + 1)):
        def fake_process(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=body, stderr="")
        with pytest.raises(ValueError):
            read_json_via_existing_gh(
                f"repos/{REPOSITORY}/actions/runs/{RUN}",
                run=fake_process, executable="/approved/gh",
            )


def push_environment():
    return {
        "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/master",
        "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_SHA": HEAD,
        "GITHUB_RUN_ID": "500", "GITHUB_WORKFLOW": "CI",
        "GH_TOKEN": "SYNTHETIC_TEST_ONLY",
    }


def test_ci_caller_env_is_opt_in_and_keeps_same_origin_identity(monkeypatch):
    from scripts import ci_merge_group_reuse as reuse
    monkeypatch.setattr(reuse, '_checkout_identity_proven', lambda expected: expected == HEAD)
    from scripts.ci_merge_group_reuse import possible_same_sha_reuse_for_ci_runner
    read, calls, paths = _read_fixture()
    assert possible_same_sha_reuse_for_ci_runner(environ=push_environment(), read=read) == (
        True, "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN"
    )
    assert calls == list(paths)


@pytest.mark.parametrize(("field", "replacement"), [
    ("GITHUB_EVENT_NAME", "merge_group"),
    ("GITHUB_REF", "refs/heads/feature"),
    ("GITHUB_REPOSITORY", "other/repo"),
    ("GITHUB_SHA", "z" * 40),
    ("GITHUB_RUN_ID", "not-a-run"),
    ("GITHUB_WORKFLOW", "Unreviewed workflow"),
    ("GH_TOKEN", ""),
])
def test_ci_caller_falls_back_to_full_tests_without_trusted_host_context(field, replacement):
    from scripts.ci_merge_group_reuse import possible_same_sha_reuse_for_ci_runner
    read, calls, _paths = _read_fixture()
    env = push_environment(); env[field] = replacement
    assert not possible_same_sha_reuse_for_ci_runner(environ=env, read=read)[0]
    assert calls == []


def test_ci_caller_falls_back_to_full_tests_on_provider_failure(monkeypatch):
    from scripts import ci_merge_group_reuse as reuse
    monkeypatch.setattr(reuse, '_checkout_identity_proven', lambda expected: expected == HEAD)
    from scripts.ci_merge_group_reuse import possible_same_sha_reuse_for_ci_runner
    read, calls, _paths = _read_fixture(invalid="read_denied")
    assert not possible_same_sha_reuse_for_ci_runner(environ=push_environment(), read=read)[0]
    assert len(calls) == 1


@pytest.mark.parametrize("repo", ["../..", "./owner", "owner/..", "owner/.", ".hidden/repo"])
def test_repository_path_components_cannot_escape_or_stealth_retarget(repo):
    from scripts.ci_merge_group_reuse import find_prior_merge_group_proof
    run, jobs = proof_fixture()
    assert not qualified(run, jobs, repo=repo)[0]
    calls = []
    def read(endpoint):
        calls.append(endpoint)
        raise AssertionError("invalid repository must not reach provider")
    assert not find_prior_merge_group_proof(
        repository=repo,head_sha=HEAD,current_event="push",
        current_ref="refs/heads/master",current_run_id=500,
        expected_workflow_id=WORKFLOW,read=read,
    )[0]
    assert calls == []


@pytest.mark.parametrize("endpoint", [
    "repos/../repo/actions/runs/123",
    "repos/org/../actions/runs/123",
    "repos/.hidden/repo/actions/runs/123",
])
def test_endpoint_components_refuse_traversal_or_stealth_owners(endpoint):
    from scripts.ci_merge_group_reuse import read_json_via_existing_gh
    with pytest.raises(ValueError, match="ENDPOINT_NOT_ALLOWED"):
        read_json_via_existing_gh(
            endpoint,
            run=lambda *args, **kwargs: pytest.fail("no provider request"),
            executable="/approved/gh",
        )


def _stub_parallel_shard(monkeypatch, tmp_path):
    from scripts import ci_parallel_shard as runner
    from scripts import ci_merge_group_reuse as reuse
    included = tuple(f"tests/test_fake_{index}.py" for index in range(12))
    monkeypatch.setattr(runner, "validate_parallel_workflow", lambda *_a: None)
    monkeypatch.setattr(runner.ci_pytest, "resolve_gate", lambda root: {
        "included": included,
        "plan": {"discovered": len(included), "excluded": 0, "running": len(included)},
    })
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("stub not a release workflow")
    return runner, reuse, included


def test_canonical_runner_reuses_exact_qualified_push_proof_without_pytest(monkeypatch, tmp_path):
    from scripts import ci_merge_group_reuse as reuse
    runner, _, included = _stub_parallel_shard(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    seen=[]
    monkeypatch.setattr(reuse, "possible_same_sha_reuse_for_ci_runner", lambda: (True, "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN"))
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kw: pytest.fail("previous exact proof must prevent a duplicate pytest subprocess"))
    assert runner.main(["--jobs", "3", "--index", "1", "--root", str(tmp_path)]) == 0


@pytest.mark.parametrize("qualified,raises", [(False, False), (False, True)])
def test_canonical_runner_executes_full_suite_for_missing_or_error_proof(monkeypatch, tmp_path, qualified, raises):
    import subprocess
    from scripts import ci_merge_group_reuse as reuse
    runner, _, included = _stub_parallel_shard(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    def outcome():
        if raises:
            raise PermissionError("provider-denied")
        return qualified, "PROVIDER_EVIDENCE_UNAVAILABLE"
    monkeypatch.setattr(reuse, "possible_same_sha_reuse_for_ci_runner", outcome)
    seen=[]
    def fake_pytest(args, **kwargs):
        seen.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(runner.subprocess, "run", fake_pytest)
    assert runner.main(["--jobs", "3", "--index", "2", "--root", str(tmp_path)]) == 0
    assert seen == [(runner.ci_pytest.pytest_argv(runner.ci_pytest.partition_modules(included,jobs=3)[2], progress=True), {"cwd":tmp_path.resolve(),"check":False})]


def test_canonical_runner_does_not_probe_during_merge_group_or_plan_only(monkeypatch, tmp_path):
    from scripts import ci_merge_group_reuse as reuse
    runner, _, included = _stub_parallel_shard(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setattr(reuse, "possible_same_sha_reuse_for_ci_runner", lambda: pytest.fail("merge_group should never inspect prior proof"))
    import subprocess
    seen=[]
    def run(args, **kwargs):
        seen.append(args)
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(runner.subprocess, "run",run)
    assert runner.main(["--jobs","3","--index","0","--root",str(tmp_path)]) == 0
    assert len(seen)==1
    monkeypatch.setenv("GITHUB_EVENT_NAME","push")
    assert runner.main(["--jobs","3","--index","0","--root",str(tmp_path),"--plan-only"]) == 0
    assert len(seen)==1


def test_real_workflow_grants_narrow_actions_read_and_only_push_step_receives_token():
    from pathlib import Path
    import yaml
    from scripts import ci_pytest
    root = Path(__file__).resolve().parents[1]
    source = (root / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    workflow = yaml.load(source, Loader=ci_pytest._WorkflowYAMLLoader)
    assert workflow['permissions'] == {'contents': 'read'}
    assert set(workflow['jobs']) == {'pytest_shards', 'test'}
    shard = workflow['jobs']['pytest_shards']
    assert shard['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert workflow['jobs']['test'].get('permissions') is None
    steps = [step for step in shard['steps'] if step.get('name') == 'Run repository test shard']
    assert len(steps) == 1
    step = steps[0]
    assert step['run'] == 'python -m scripts.ci_parallel_shard --jobs 3 --index ${{ matrix.index }}'
    assert step.get('env') == {'GH_TOKEN': "${{ github.event_name == 'push' && github.token || '' }}"}
    assert shard['strategy']['matrix']['index'] == [0,1,2]
    assert workflow['jobs']['test']['name'] == 'test'
    assert workflow['jobs']['test']['needs'] == ['pytest_shards']


@pytest.mark.parametrize(("before", "after"), [
    ("      actions: read", "      actions: write"),
    ("      actions: read", "      actions: none"),
    ("      contents: read\n      actions: read", "      actions: read"),
    ("github.event_name == 'push' && github.token || ''", "github.token"),
    ("github.event_name == 'push' && github.token || ''", "github.event_name == 'pull_request' && github.token || ''"),
])
def test_workflow_privileges_cannot_mutate_without_detection(before, after):
    """Bound the exact source-level grant to push-only read-only provenance."""
    from pathlib import Path
    import yaml
    from scripts import ci_pytest
    root = Path(__file__).resolve().parents[1]
    text = (root / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert before in text
    mutant = text.replace(before, after, 1)
    doc = yaml.load(mutant, Loader=ci_pytest._WorkflowYAMLLoader)
    shards = doc['jobs']['pytest_shards']
    step = next(s for s in shards['steps'] if s.get('name') == 'Run repository test shard')
    is_exact = (
        doc['permissions'] == {'contents': 'read'}
        and shards.get('permissions') == {'contents': 'read','actions': 'read'}
        and step.get('env') == {'GH_TOKEN': "${{ github.event_name == 'push' && github.token || '' }}"}
    )
    assert not is_exact


def test_checkout_attestation_rejects_stale_head_and_modified_tracked_inputs(tmp_path):
    import subprocess
    from scripts.ci_merge_group_reuse import _checkout_identity_proven
    repo = tmp_path / 'source'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,check=True).stdout.strip()
    git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    file = repo/'scripts'/'runner.py';file.parent.mkdir();file.write_text('accepted = True\n')
    git('add','scripts/runner.py');git('commit','-qm','fixture')
    head=git('rev-parse','HEAD')
    assert _checkout_identity_proven(head,root=repo)
    assert not _checkout_identity_proven('f'*40,root=repo)
    file.write_text('accepted = False\n')
    assert not _checkout_identity_proven(head,root=repo)
    git('add','scripts/runner.py')
    assert not _checkout_identity_proven(head,root=repo)


def test_proof_reader_is_never_called_for_unqualified_actual_checkout(monkeypatch):
    from scripts import ci_merge_group_reuse as reuse
    read, calls, _paths = _read_fixture()
    monkeypatch.setattr(reuse,'_checkout_identity_proven',lambda expected:False)
    assert not reuse.possible_same_sha_reuse_for_ci_runner(environ=push_environment(),read=read)[0]
    assert calls == []
