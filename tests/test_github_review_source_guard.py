"""Authenticated source observations stay outside the Runtime writer lock."""
import asyncio
import dataclasses
import json
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_host_config import ReviewHostSettings
from control_plane.github_review_intent import (
    AutomaticReviewOrigin, IntentSource, PullRequestFacts, RepositoryPolicyAuthority,
    decide_reconciled_review, review_intent_id, review_command_id,
)
from control_plane.github_review_socket_contract import (
    FRAME_SCHEMA, PreparedReviewSourceCheck, REVIEW_SLACK_CHANNEL_ID,
)
from control_plane.github_review_socket_owner import (
    ExecutiveGitHubReviewSocketOwner, GitHubReviewSocketRefused,
)
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_socket_client import ExecutiveReviewSocketClient
from integrations.github_review_source_guard import (
    GitHubReviewSourceBinding, GitHubReviewSourcePreflight, GitHubReviewSourceUnavailable,
)
from integrations.slack_agent_dialogue.engine import SlackMessage
from test_github_review_runtime_adapter import decision

REPO = "example/repo"
SHA = "a" * 40


def settings(**changes):
    values = dict(
        enabled=True, publication_enabled=True, expected_host="review.example.com",
        installation_id=4242, installation_ids=frozenset({4242}),
        repositories=frozenset({REPO}), configured_reviewer="reviewer",
        authorized_actors=frozenset({"alice", "bob"}),
        allow_lifecycle_review=True, allow_repository_policy_review=True,
    )
    values.update(changes)
    return ReviewHostSettings(**values)


def payload(**changes):
    value = {
        "number": 42, "state": "open", "draft": False,
        "head": {"sha": SHA, "repo": {"full_name": REPO}},
        "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
        "title": "Review the source", "body": "Ordinary bounded context",
    }
    value.update(changes)
    return value


def automatic(config=None):
    config = config or settings()
    policy = config.review_policy()
    repository = next(iter(config.repositories))
    intent_id = review_intent_id(repository=repository, pull_number=42, head_sha=SHA)
    return dataclasses.replace(
        decision(), intent_source=IntentSource.PR_LIFECYCLE, actor="automation[bot]",
        repository=repository, intent_id=intent_id, command_id=review_command_id(intent_id),
        policy_authority=RepositoryPolicyAuthority(
            origin=AutomaticReviewOrigin.SIGNED_WEBHOOK,
            installation_id=config.installation_id,
            policy_digest=policy.repository_policy_digest(
                repository=repository, installation_id=config.installation_id,
            ),
        ),
    )


def reconciled(config=None):
    config = config or settings()
    return decide_reconciled_review(
        policy=config.review_policy(), repository=REPO, installation_id=config.installation_id,
        pull_number=42, owner_execution_ref="ROOT-1740:r15",
        pull_request=PullRequestFacts(
            repository=REPO, number=42, state="open", draft=False,
            head_sha=SHA, head_repository=REPO, base_repository=REPO, base_sha="b" * 40,
        ),
    )


def frame(chosen=None):
    return {"schema": FRAME_SCHEMA, "action": "admit_or_join",
            "decision": (chosen or decision()).to_dict(), "objective": "Read-only source review"}


def setup(tmp_path, *, config=None, binding_guard=None, admission_guard=None, **owner_options):
    runtime = Runtime.at(tmp_path)
    config = config or settings()
    state = {"now": 10.0, "inside": False, "calls": [], "local_checks": [],
             "permission": "write", "permission_status": 200, "pr": payload()}

    class Tokens:
        def token_for_installation(self, *, installation_id):
            assert not state["inside"], "credential read inside Runtime write transaction"
            assert installation_id == config.installation_id
            return "synthetic-source-token"

    def transport(request):
        assert not state["inside"], "GitHub HTTP inside Runtime write transaction"
        state["calls"].append(request.url.path)
        if "/collaborators/" in request.url.path:
            login = request.url.path.split("/collaborators/")[1].split("/")[0]
            return httpx.Response(state["permission_status"], json={
                "user": {"login": state.get("returned_login", login)},
                "permission": state["permission"],
            })
        assert request.url.path.endswith("/pulls/42")
        return httpx.Response(state.get("pr_status", 200), json=state["pr"])

    github = GitHubReviewAPI(
        repository=next(iter(config.repositories)), installation_id=config.installation_id,
        token_source=Tokens(), publisher_login="reviewer-bot[bot]", publisher_user_id=9001,
        client=httpx.Client(transport=httpx.MockTransport(transport)), sleep=lambda delay: None,
    )

    def current_binding():
        state["local_checks"].append(state["inside"])
        if binding_guard is not None:
            return binding_guard(state)

    binding = GitHubReviewSourceBinding(
        settings=config, github=github, current_binding_guard=current_binding,
    )
    preflight = GitHubReviewSourcePreflight(bindings=[binding], clock=lambda: state["now"])
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, repositories=config.repositories,
        admission_guard=(lambda: admission_guard(state)) if admission_guard else (lambda: None),
        source_preflight=preflight, automatic_policy=config.review_policy(),
        **owner_options,
    )
    return runtime, owner, preflight, binding, state


def trace_transaction(runtime, state, monkeypatch, *, age=0):
    original = runtime.store.transaction
    @contextmanager
    def transaction():
        with original() as conn:
            state["now"] += age
            state["inside"] = True
            try:
                yield conn
            finally:
                state["inside"] = False
    monkeypatch.setattr(runtime.store, "transaction", transaction)


def test_source_reads_once_and_commit_checks_never_use_http(tmp_path, monkeypatch):
    runtime, owner, _, _, state = setup(tmp_path)
    trace_transaction(runtime, state, monkeypatch)
    receipt = owner.handle_frame(frame())
    assert receipt["state"] == "ADMITTED"
    assert len(state["calls"]) == 2
    assert state["local_checks"].count(True) >= 2
    assert len(runtime.jobs.list_jobs()) == 1
    assert owner.handle_frame(frame())["state"] == "ALREADY_ADMITTED"
    assert len(state["calls"]) == 4
    assert len(runtime.jobs.list_jobs()) == 1


def test_prepared_observation_expires_after_writer_lock_is_acquired(tmp_path, monkeypatch):
    runtime, owner, _, _, state = setup(tmp_path)
    trace_transaction(runtime, state, monkeypatch, age=3.0)
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert len(state["calls"]) == 2
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.get_event_by_command_id(decision().command_id) is None


@pytest.mark.parametrize("which", ["binding", "arm"])
@pytest.mark.parametrize("commit_check", [1, 2])
def test_revocation_at_either_commit_fence_rolls_back(tmp_path, monkeypatch, which, commit_check):
    count = [0]
    def revoke(state):
        if state["inside"]:
            count[0] += 1
            if count[0] == commit_check:
                raise ValueError("revoked")
    options = {"binding_guard" if which == "binding" else "admission_guard": revoke}
    runtime, owner, _, _, state = setup(tmp_path, **options)
    trace_transaction(runtime, state, monkeypatch)
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert count[0] == commit_check
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.get_event_by_command_id(decision().command_id) is None


@pytest.mark.parametrize("change", [
    {"actor": "bob"}, {"delivery_command_id": "gh-review-delivery:" + "f" * 32},
    {"intent_source": IntentSource.COMMAND_COMMENT},
])
def test_prepared_check_is_bound_to_the_whole_decision(tmp_path, change):
    runtime, owner, preflight, _, state = setup(tmp_path)
    prepared = preflight(decision())
    owner._source_preflight = lambda chosen: prepared
    with pytest.raises(GitHubReviewSocketRefused, match="SOURCE_NOT_VERIFIED"):
        owner.handle_frame(frame(dataclasses.replace(decision(), **change)))
    assert runtime.jobs.list_jobs() == []
    assert len(state["calls"]) == 2


@pytest.mark.parametrize("permission,status,login", [
    ("read", 200, None), ("none", 200, None), ("write", 404, None),
    ("write", 401, None), ("write", 429, None), ("write", 503, None),
    ("unknown", 200, None), ("write", 200, "mallory"),
])
def test_current_permission_failure_has_no_pr_read_or_admission(tmp_path, permission, status, login):
    runtime, owner, _, _, state = setup(tmp_path)
    state["permission"], state["permission_status"] = permission, status
    if login:
        state["returned_login"] = login
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert all("/collaborators/" in path for path in state["calls"])
    assert len(state["calls"]) == (2 if status == 503 else 1)
    assert runtime.jobs.list_jobs() == []


def test_removed_actor_refuses_before_any_credential_read(tmp_path):
    runtime, owner, _, _, state = setup(tmp_path, config=settings(authorized_actors=frozenset({"bob"})))
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert state["calls"] == [] and runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("source,allowed", [
    (IntentSource.INTENT_LABEL, True), (IntentSource.COMMAND_COMMENT, True),
    (IntentSource.REVIEW_REQUESTED, False), (IntentSource.PR_LIFECYCLE, False),
])
def test_manual_draft_exception_does_not_enable_automatic_drafts(tmp_path, source, allowed):
    runtime, owner, _, _, state = setup(tmp_path)
    state["pr"]["draft"] = True
    chosen = dataclasses.replace(decision(), intent_source=source)
    if allowed:
        assert owner.handle_frame(frame(chosen))["state"] == "ADMITTED"
    else:
        with pytest.raises(GitHubReviewSocketRefused):
            owner.handle_frame(frame(chosen))
        assert runtime.jobs.list_jobs() == []


def test_actor_lifecycle_requires_current_flag_without_upgrading_to_standing_policy(tmp_path):
    runtime, owner, _, _, state = setup(tmp_path, config=settings(allow_lifecycle_review=False))
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame(dataclasses.replace(decision(), intent_source=IntentSource.PR_LIFECYCLE)))
    assert state["calls"] == [] and runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("make", [automatic, reconciled])
def test_standing_authority_never_impersonates_a_human_permission(tmp_path, make):
    runtime, owner, _, _, state = setup(tmp_path, reconciliation_guard=lambda ref: None)
    chosen = make()
    assert owner.handle_frame(frame(chosen))["state"] == "ADMITTED"
    assert state["calls"] == [f"/repos/{REPO}/pulls/42"]
    saved = runtime.store.get_event_by_command_id(chosen.command_id).payload["provenance"]["decision"]
    assert saved["actor"] == chosen.actor
    assert saved["policy_authority"] == chosen.policy_authority.to_dict()


@pytest.mark.parametrize("which", ["installation", "digest", "disabled", "reconciliation"])
def test_invalid_standing_authority_refuses_before_any_read(tmp_path, which):
    runtime, owner, _, _, state = setup(tmp_path)
    chosen = automatic()
    if which == "installation":
        chosen = dataclasses.replace(chosen, policy_authority=dataclasses.replace(chosen.policy_authority, installation_id=4243))
    elif which == "digest":
        chosen = dataclasses.replace(chosen, policy_authority=dataclasses.replace(chosen.policy_authority, policy_digest="f" * 64))
    elif which == "disabled":
        owner._automatic_policy = settings(allow_repository_policy_review=False).review_policy()
    else:
        chosen = reconciled()
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame(chosen))
    assert state["calls"] == [] and runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("changed", [
    {"number": 43}, {"state": "closed"}, {"draft": "false"},
    {"head": {"sha": "c" * 40, "repo": {"full_name": REPO}}},
    {"head": {"sha": SHA, "repo": {"full_name": "outsider/fork"}}},
    {"base": {"sha": "b" * 40, "repo": {"full_name": "other/repo"}}},
])
def test_current_pr_identity_and_state_must_still_match(tmp_path, changed):
    runtime, owner, _, _, state = setup(tmp_path)
    state["pr"] = payload(**changed)
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert runtime.jobs.list_jobs() == []


def test_factory_rejects_ambiguous_or_mismatched_host_bindings(tmp_path):
    _, _, _, binding, _ = setup(tmp_path)
    with pytest.raises(GitHubReviewSourceUnavailable, match="AMBIGUOUS"):
        GitHubReviewSourcePreflight(bindings=[binding, binding])
    with pytest.raises(GitHubReviewSourceUnavailable, match="BINDING_INVALID"):
        dataclasses.replace(binding, settings=settings(installation_id=4243, installation_ids=frozenset({4243})))
    with pytest.raises(GitHubReviewSourceUnavailable, match="BINDING_INVALID"):
        dataclasses.replace(binding, settings=settings(repositories=frozenset({"other/repo"})))


def test_broad_owner_policy_does_not_authorize_an_unbound_repository_install_pair(tmp_path):
    runtime, owner, _, _, state = setup(tmp_path)
    owner._automatic_policy = dataclasses.replace(
        settings().review_policy(), installation_ids=frozenset({4242, 4243}),
    )
    other = settings(installation_id=4243, installation_ids=frozenset({4243}))
    with pytest.raises(GitHubReviewSocketRefused, match="SOURCE_NOT_VERIFIED"):
        owner.handle_frame(frame(automatic(other)))
    assert state["calls"] == [] and runtime.jobs.list_jobs() == []


def test_exact_policy_map_supports_heterogeneous_repositories_on_one_owner(tmp_path):
    runtime, _, _, first, state1 = setup(tmp_path / "first")
    config2 = settings(repositories=frozenset({"example/second"}), configured_reviewer="other-reviewer")
    _, _, _, second, state2 = setup(tmp_path / "second", config=config2)
    state2["pr"]["head"]["repo"]["full_name"] = "example/second"
    state2["pr"]["base"]["repo"]["full_name"] = "example/second"
    preflight = GitHubReviewSourcePreflight(bindings=[first, second], clock=lambda: 10.0)
    policies = dict(preflight.automatic_policies)
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, repositories=frozenset({REPO, "example/second"}),
        admission_guard=lambda: None, source_preflight=preflight, automatic_policies=policies,
    )
    policies.clear()  # the owner retained its own immutable map
    a = owner.handle_frame(frame(automatic(first.settings)))
    b = owner.handle_frame(frame(automatic(second.settings)))
    assert a["job_id"] != b["job_id"]
    assert len(runtime.jobs.list_jobs()) == 2
    assert state1["calls"] == [f"/repos/{REPO}/pulls/42"]
    assert state2["calls"] == ["/repos/example/second/pulls/42"]


def test_exact_policy_map_has_no_fallback_to_an_unconfigured_pair(tmp_path):
    runtime, _, preflight, binding, state = setup(tmp_path)
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, repositories=frozenset({REPO}), admission_guard=lambda: None,
        source_preflight=preflight, automatic_policies=preflight.automatic_policies,
    )
    other = settings(installation_id=4243, installation_ids=frozenset({4243}))
    with pytest.raises(GitHubReviewSocketRefused, match="POLICY_NOT_ENROLLED"):
        owner.handle_frame(frame(automatic(other)))
    assert state["calls"] == [] and runtime.jobs.list_jobs() == []
    common = dict(runtime=runtime, repositories=frozenset({REPO}),
                  admission_guard=lambda: None, source_preflight=preflight)
    with pytest.raises(ValueError, match="ambiguous"):
        ExecutiveGitHubReviewSocketOwner(
            **common, automatic_policy=settings().review_policy(), automatic_policies=preflight.automatic_policies,
        )
    with pytest.raises(ValueError, match="exact source pair"):
        ExecutiveGitHubReviewSocketOwner(
            **common, automatic_policies={(4243, REPO): settings().review_policy()},
        )


def test_empty_policy_map_keeps_manual_source_and_refuses_automatic(tmp_path):
    config = settings(allow_lifecycle_review=False, allow_repository_policy_review=False)
    runtime, _, preflight, _, state = setup(tmp_path, config=config)
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, repositories=frozenset({REPO}), admission_guard=lambda: None,
        source_preflight=preflight, automatic_policies=preflight.automatic_policies,
    )
    assert owner.handle_frame(frame())["state"] == "ADMITTED"
    state["calls"].clear()
    with pytest.raises(GitHubReviewSocketRefused, match="POLICY_NOT_ENROLLED"):
        owner.handle_frame(frame(automatic()))
    assert state["calls"] == []


@pytest.mark.parametrize("commit_check", [1, 2])
def test_exact_policy_revocation_at_either_commit_check_rolls_back(tmp_path, monkeypatch, commit_check):
    runtime, _, preflight, _, state = setup(tmp_path)
    count = [0]
    def arm():
        if state["inside"]:
            count[0] += 1
            if count[0] == commit_check:
                owner._automatic_policies = {}
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, repositories=frozenset({REPO}), admission_guard=arm,
        source_preflight=preflight, automatic_policies=preflight.automatic_policies,
    )
    trace_transaction(runtime, state, monkeypatch)
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame(automatic()))
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.get_event_by_command_id(automatic().command_id) is None


def test_concurrent_preflights_retain_their_own_complete_decisions(tmp_path):
    _, _, preflight, binding, state = setup(tmp_path)
    original = binding.github.read_pull_request
    barrier = Barrier(2)
    def simultaneous(**kwargs):
        barrier.wait(timeout=5)
        return original(**kwargs)
    binding.github.read_pull_request = simultaneous
    choices = [decision(), dataclasses.replace(decision(), actor="bob")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        checks = list(pool.map(preflight, choices))
    assert len(state["calls"]) == 4
    for index, check in enumerate(checks):
        check.verify(choices[index])
        with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
            check.verify(choices[1 - index])


@pytest.mark.parametrize("now", [9.0, 13.0, float("nan"), float("inf"), True])
def test_prepared_freshness_rejects_clock_drift_or_expiry(tmp_path, now):
    _, _, preflight, _, state = setup(tmp_path)
    prepared = preflight(decision())
    state["now"] = now
    with pytest.raises(ValueError, match="EXPIRED"):
        prepared.verify(decision())


@pytest.mark.parametrize("mutate", ["installation", "repository"])
def test_reader_binding_drift_invalidates_prepared_check(tmp_path, mutate):
    runtime, owner, preflight, binding, _ = setup(tmp_path)
    prepared = preflight(decision())
    if mutate == "installation":
        binding.github._installation_id = 4243
    else:
        binding.github._repository = "other/repo"
    owner._source_preflight = lambda chosen: prepared
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert runtime.jobs.list_jobs() == []


def test_network_delay_does_not_renew_observation_lifetime(tmp_path):
    runtime, owner, _, binding, state = setup(tmp_path)
    original = binding.github.read_current_permission
    def delayed(**kwargs):
        value = original(**kwargs)
        state["now"] += 3
        return value
    binding.github.read_current_permission = delayed
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(frame())
    assert len(state["calls"]) == 1 and runtime.jobs.list_jobs() == []


def test_new_and_legacy_guard_paths_are_mutually_exclusive(tmp_path):
    runtime, _, preflight, _, _ = setup(tmp_path)
    common = dict(runtime=runtime, admission_guard=lambda: None, repositories=frozenset({REPO}))
    with pytest.raises(TypeError):
        ExecutiveGitHubReviewSocketOwner(**common)
    with pytest.raises(TypeError):
        ExecutiveGitHubReviewSocketOwner(**common, source_guard=lambda chosen: None, source_preflight=preflight)
    calls = []
    owner = ExecutiveGitHubReviewSocketOwner(**common, source_guard=lambda chosen: calls.append(chosen))
    assert owner.handle_frame(frame())["state"] == "ADMITTED"
    assert len(calls) == 4


def test_parent_reservation_and_capture_stay_guarded_on_prepared_path(tmp_path):
    reserved, recorded = [], []
    runtime, owner, _, _, state = setup(
        tmp_path, relay_bot_user_id="U0BT71H4FQE",
        parent_reserver=lambda **kw: reserved.append(kw) is None,
        parent_recorder=lambda **kw: recorded.append(kw),
        parent_body_renderer=lambda **kw: "Original parent",
        parent_message_reader=lambda chosen, job, ts: SlackMessage(
            ts=ts, author_user_id="U0BT71H4FQE", text="Original parent"),
    )
    receipt = owner.handle_frame(frame())
    parent = {"schema": FRAME_SCHEMA, "action": "reserve_parent", "decision": decision().to_dict(),
              "job_id": receipt["job_id"], "channel_id": REVIEW_SLACK_CHANNEL_ID}
    assert owner.handle_frame(parent)["state"] == "PARENT_SEND_RESERVED"
    assert len(reserved) == 1
    parent.update(action="record_parent", thread_ts="1792699000.000001", author_user_id="U0BT71H4FQE")
    assert owner.handle_frame(parent)["state"] == "PARENT_RECORDED"
    assert len(recorded) == 1 and len(state["calls"]) == 6
    state["permission"] = "none"
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(parent)
    assert len(recorded) == 1


def test_prepared_source_runs_over_real_socket_without_worker_start(tmp_path):
    async def exercise():
        runtime, owner, _, _, state = setup(tmp_path / "runtime")
        socket_path = str(tmp_path / "source.sock")
        async def handle(reader, writer):
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=3)
                result = await asyncio.to_thread(owner.handle_frame, json.loads(raw))
                reply = {"ok": True, "result": result}
            except Exception:
                reply = {"ok": False, "error": {"code": "refused"}}
            writer.write(json.dumps(reply).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, path=socket_path)
        try:
            client = ExecutiveReviewSocketClient(socket_path=socket_path)
            receipt = await asyncio.to_thread(
                client.admit_or_join_review_intent, decision=decision(), objective="Read-only source review",
            )
            assert receipt.created is True
            assert len(runtime.jobs.list_jobs()) == 1
            assert runtime.jobs.get_job(receipt.job_id).attempt_count == 0
            assert len(state["calls"]) == 2
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(exercise())
