"""Repository policy, bounded backfill and cross-origin canonical admission."""
import asyncio
import dataclasses
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from control_plane import github_review_intent as core
from control_plane import github_review_intent_ingress as ingress
from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission, ReviewAdmissionUnavailable
from control_plane.github_review_socket_contract import FRAME_SCHEMA
from control_plane.github_review_socket_owner import ExecutiveGitHubReviewSocketOwner, GitHubReviewSocketRefused
from integrations.github_review_api import GitHubReviewAPIUnavailable
from integrations.github_review_ingress_asgi import GitHubReviewReceiver
from integrations.github_review_slack_thread import ExecutiveSlackReviewThreads, SlackReviewThreadUnavailable
from integrations.github_review_socket_client import ExecutiveReviewSocketClient
from test_github_review_api import source
from test_github_review_lifecycle import (
    REPO, HEAD, DELIVERY, SECRET, Actors, Pulls, Secrets, admit, facts, payload,
    policy as actor_policy, settings, http,
)
from test_github_review_runtime_adapter import decision as manual_decision


def policy(**kwargs):
    return actor_policy(allow_repository_policy_review=True, **kwargs)


def reconciled(**kwargs):
    values = dict(policy=policy(), repository=REPO, installation_id=4242,
                  pull_number=42, owner_execution_ref="ROOT-1740:cycle-1", pull_request=facts())
    values.update(kwargs)
    return core.decide_reconciled_review(**values)


def automatic():
    return core.decide_review_intent(
        envelope=core.WebhookEnvelope(DELIVERY, "pull_request", "opened", REPO, 4242, 42),
        policy=policy(), pull_request=facts(),
        signal=core.IntentSignal("dependabot[bot]", core.ActorPermissionBasis.REVERIFIED_LIFECYCLE_PERMISSION),
    )


def adapter(tmp_path):
    runtime = Runtime.at(tmp_path)
    return runtime, ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=lambda: None)


@pytest.mark.parametrize("sender", ["dependabot[bot]", "unlisted-human"])
def test_standing_policy_records_sender_without_borrowing_human_authority(tmp_path, sender):
    runtime, fabric = adapter(tmp_path)
    actors, pulls = Actors(), Pulls()
    result = admit(body=payload(sender=sender), selected_policy=policy(), actors=actors, pulls=pulls, fabric=fabric)
    assert result.state is ingress.AdmissionState.ADMITTED
    assert actors.reads == 0 and pulls.reads == 1
    assert result.decision.actor == sender
    authority = result.decision.policy_authority
    assert authority.origin is core.AutomaticReviewOrigin.SIGNED_WEBHOOK
    assert authority.installation_id == 4242
    assert authority.owner_execution_ref is None
    assert authority.policy_digest == policy().repository_policy_digest(repository=REPO, installation_id=4242)
    event = runtime.store.get_event_by_command_id(result.decision.command_id)
    assert event.payload["provenance"]["decision"] == result.decision.to_dict()


def test_payload_cannot_enable_policy_and_manual_bot_still_refused(tmp_path):
    runtime, fabric = adapter(tmp_path)
    value = json.loads(payload(sender="dependabot[bot]"))
    value["allow_repository_policy_review"] = True
    value["policy_authority"] = automatic().policy_authority.to_dict()
    pulls = Pulls()
    result = admit(body=json.dumps(value).encode(), pulls=pulls, fabric=fabric)
    assert result.decision.refusal is core.ReviewIntentRefusal.ACTOR_NOT_AUTHORIZED
    assert pulls.reads == 0
    with pytest.raises(core.ReviewIntentError):
        admit(body=payload("labeled", "dependabot[bot]"), selected_policy=policy(), pulls=pulls, fabric=fabric)
    assert pulls.reads == 0 and runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("value", [1, "true", None])
def test_standing_policy_boolean_is_strict(value):
    with pytest.raises(core.ReviewIntentError):
        actor_policy(allow_repository_policy_review=value)


@pytest.mark.parametrize("make", [manual_decision, automatic, reconciled])
def test_canonical_decision_roundtrip_is_exact(make):
    chosen = make()
    assert core.ReviewIntentDecision.from_admitted_dict(chosen.to_dict()) == chosen
    if chosen.intent_source is core.IntentSource.OPEN_PR_RECONCILIATION:
        assert chosen.actor is None and chosen.delivery_command_id is None


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(actor="pretend-human"),
    lambda r: r.update(delivery_command_id="gh-review-delivery:" + "1" * 32),
    lambda r: r.update(extra="field"),
    lambda r: r["policy_authority"].update(installation_id=True),
    lambda r: r["policy_authority"].update(owner_execution_ref="https://untrusted.example"),
    lambda r: r.update(schema=core.SCHEMA),
])
def test_reconciliation_codec_refuses_forged_or_mixed_origins(mutate):
    raw = reconciled().to_dict()
    mutate(raw)
    with pytest.raises(core.ReviewIntentError):
        core.ReviewIntentDecision.from_admitted_dict(raw)


@pytest.mark.parametrize("current,reason", [
    (facts(state="closed"), "PULL_REQUEST_NOT_OPEN"),
    (facts(draft=True), "PULL_REQUEST_DRAFT"),
    (facts(head_repository="attacker/fork"), "HEAD_REPOSITORY_MISMATCH"),
    (facts(number=43), "PULL_NUMBER_MISMATCH"),
    (facts(body=core.UNTRUSTED_BLOCK_CLOSE), "UNTRUSTED_CONTENT_DETECTED"),
])
def test_backfill_retains_existing_source_fences(current, reason):
    assert reconciled(pull_request=current).refusal.value == reason


def test_cross_origin_join_preserves_first_receipt_and_strict_replay(tmp_path):
    runtime, fabric = adapter(tmp_path)
    original = manual_decision()
    first = fabric.admit_or_join_review_intent(decision=original, objective="  Original task  ")
    assert first.created
    for later in (automatic(), reconciled(), dataclasses.replace(original, actor="bob")):
        joined = fabric.admit_or_join_review_intent(decision=later, objective="Later request text")
        assert not joined.created and joined.job_id == first.job_id
        assert joined.decision == original
    with pytest.raises(ReviewAdmissionUnavailable, match="PAYLOAD_CONFLICT"):
        fabric.admit_or_join_review_intent(decision=original, objective="Changed exact submission")
    event = runtime.store.get_event_by_command_id(original.command_id)
    assert event.payload["provenance"]["objective_sha256"] == hashlib.sha256(b"Original task").hexdigest()
    assert len(runtime.jobs.list_jobs()) == 1
    assert fabric.read_admitted_job(command_id=original.command_id).decision == original


@pytest.mark.parametrize("first_action,second_action", [("labeled", "opened"), ("opened", "labeled")])
def test_sequential_webhooks_return_canonical_winner_without_second_notice(tmp_path, first_action, second_action):
    runtime, fabric = adapter(tmp_path)
    first = admit(body=payload(first_action), selected_policy=policy(), fabric=fabric)
    second = admit(body=payload(second_action), selected_policy=policy(), fabric=fabric)
    assert first.state is ingress.AdmissionState.ADMITTED
    assert second.state is ingress.AdmissionState.ALREADY_ADMITTED
    assert second.decision == first.decision and second.job_id == first.job_id
    assert len(runtime.jobs.list_jobs()) == 1


def test_policy_revision_joins_same_head_but_new_head_creates_new_identity(tmp_path):
    runtime, fabric = adapter(tmp_path)
    first = fabric.admit_or_join_review_intent(decision=reconciled(), objective="Original")
    changed_policy = dataclasses.replace(policy(), minimum_permission="maintain")
    changed = reconciled(policy=changed_policy, owner_execution_ref="ROOT-1740:cycle-2")
    assert changed.policy_authority.policy_digest != first.decision.policy_authority.policy_digest
    joined = fabric.admit_or_join_review_intent(decision=changed, objective="Changed policy")
    assert not joined.created and joined.decision == first.decision
    new_head = reconciled(pull_request=facts(head_sha="c" * 40), owner_execution_ref="ROOT-1740:cycle-2")
    latest = fabric.admit_or_join_review_intent(decision=new_head, objective="New head")
    assert latest.created and latest.job_id != first.job_id
    assert len(runtime.jobs.list_jobs()) == 2


def test_reconciliation_authority_revoked_before_commit_creates_nothing(tmp_path):
    runtime = Runtime.at(tmp_path)
    calls = []
    def guard():
        calls.append(True)
        if len(calls) > 1:
            raise PermissionError("revoked")
    fabric = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=guard)
    with pytest.raises(ReviewAdmissionUnavailable, match="REFUSED"):
        fabric.admit_or_join_review_intent(decision=reconciled(), objective="Review")
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.get_event_by_command_id(reconciled().command_id) is None


@pytest.mark.parametrize("make", [automatic, reconciled])
def test_automatic_return_uses_original_provenance_and_publishes_only_comment(tmp_path, make):
    from integrations.github_review_return import GitHubReviewReturn, ReviewReturnSourceMode
    from test_github_review_publish_workflow import git_api

    runtime = Runtime.at(tmp_path)
    fabric = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=lambda: None,
        constraints={"eligible_quota_classes": ["glm-native"]})
    chosen = make()
    receipt = fabric.admit_or_join_review_intent(decision=chosen, objective="Independent review")
    runtime.workers.register_worker("reviewer-01", provider="glm", account_label="reviewer",
        worker_type="mock", capabilities=["code"], quota_classes={"glm-native": ["code"]})
    runtime.jobs.assign_job(receipt.job_id, "reviewer-01")
    runtime.jobs.complete_job(receipt.job_id, JobPayload(summary="No blockers found.", verdict="approve"))
    github, history = git_api()
    handler = GitHubReviewReturn.for_authorized_source(runtime=runtime, github=github,
        publication_guard=lambda: None, source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY)
    losing_origin = reconciled() if make is automatic else automatic()
    with pytest.raises(ingress.ReviewVerificationRefused, match="SOURCE_IDENTITY_MISMATCH"):
        handler.deliver(decision=losing_origin, job_id=receipt.job_id)
    assert history["posts"] == []
    result = handler.deliver(decision=chosen, job_id=receipt.job_id)
    assert result.publication.state is ingress.PublishState.PUBLISHED
    assert [p["event"] for p in history["posts"]] == ["COMMENT"]
    again = handler.deliver(decision=chosen, job_id=receipt.job_id)
    assert again.publication.state is ingress.PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


def test_three_concurrent_origins_commit_one_job_and_propagate_the_winner(tmp_path):
    runtimes = [Runtime.at(tmp_path) for _ in range(3)]
    barrier = threading.Barrier(3)

    class RacingAdmission(ExecutiveReviewJobAdmission):
        def _create(self, **kwargs):
            barrier.wait(timeout=10)
            return super()._create(**kwargs)

    ports = [RacingAdmission(runtime=r, admission_guard=lambda: None) for r in runtimes]
    choices = [manual_decision(), automatic(), reconciled()]
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = [executor.submit(p.admit_or_join_review_intent, decision=d, objective=f"Origin {i}")
                   for i, (p, d) in enumerate(zip(ports, choices))]
        receipts = [f.result(timeout=20) for f in pending]
    assert sum(r.created for r in receipts) == 1
    winner = next(r for r in receipts if r.created)
    assert all(r.job_id == winner.job_id and r.decision == winner.decision for r in receipts)
    assert len(runtimes[0].jobs.list_jobs()) == 1
    events = runtimes[0].store.list_events(command_id_prefix="gh-review-intent:")
    assert len(events) == 1 and events[0].payload["provenance"]["decision"] == winner.decision.to_dict()


def test_legacy_receipt_exists_but_is_not_fabricated_or_redispatched(tmp_path):
    runtime, fabric = adapter(tmp_path)
    chosen = manual_decision()
    provenance = {"schema": "mastermind.github_review_runtime_admission.v1"}
    for name in ("repository", "pull_number", "frozen_head_sha", "actor", "intent_id", "command_id"):
        provenance[name] = getattr(chosen, name)
    job = runtime.jobs.create_job("Legacy review", command_id=chosen.command_id, provenance=provenance,
                                  requested_authorities=["READ"], allowed_write_paths=[])
    with pytest.raises(ingress.ExistingReviewDecisionUnavailable, match="LEGACY_DECISION_UNAVAILABLE"):
        fabric.admit_or_join_review_intent(decision=reconciled(), objective="Backfill")
    assert chosen.command_id in fabric.admitted_command_ids()
    assert [j.job_id for j in runtime.jobs.list_jobs()] == [job.job_id]


def test_canonical_reader_refuses_one_event_containing_another_jobs_decision(tmp_path):
    runtime, fabric = adapter(tmp_path)
    first = fabric.admit_or_join_review_intent(decision=manual_decision(), objective="First")
    other = reconciled(pull_request=facts(head_sha="c" * 40))
    provenance = {"schema": "mastermind.github_review_runtime_admission.v1",
                  "decision": first.decision.to_dict(),
                  "objective_sha256": hashlib.sha256(b"Other").hexdigest()}
    for name in ("repository", "pull_number", "frozen_head_sha", "actor", "intent_id", "command_id"):
        provenance[name] = getattr(other, name)
    runtime.jobs.create_job("Other", command_id=other.command_id, provenance=provenance,
                            requested_authorities=["READ"], allowed_write_paths=[])
    assert fabric.read_admitted_job(command_id=other.command_id) is None
    with pytest.raises(ReviewAdmissionUnavailable, match="IDENTITY_CONFLICT"):
        fabric.read_existing_review(decision=other)


class Pages:
    def __init__(self, pages, current=None):
        self.pages = pages
        self.current = current or {}
        self.calls = []

    def list_open_pull_request_numbers(self, *, repository, page, per_page):
        self.calls.append(("list", repository, page, per_page))
        result = self.pages[page]
        if isinstance(result, Exception):
            raise result
        return result

    def read_pull_request(self, *, repository, pull_number):
        self.calls.append(("read", repository, pull_number))
        return self.current.get(pull_number, facts(number=pull_number))


def scan(pulls, fabric, **kwargs):
    values = dict(policy=policy(), repository=REPO, installation_id=4242,
                  owner_execution_ref="ROOT-1740:cycle-1", authorize=lambda ref: None,
                  pull_requests=pulls, fabric=fabric, per_page=2)
    values.update(kwargs)
    return ingress.reconcile_open_pull_requests(**values)


def test_bounded_scan_rereads_each_pr_and_joins_existing_heads(tmp_path):
    runtime, fabric = adapter(tmp_path)
    first = fabric.admit_or_join_review_intent(decision=manual_decision(), objective="Manual")
    pulls = Pages({1: ingress.OpenPullRequestPage((42, 43), True),
                   2: ingress.OpenPullRequestPage((44,), False)},
                  {43: facts(number=43, state="closed")})
    result = scan(pulls, fabric)
    assert result.complete and result.pages_read == 2 and result.next_page is None
    assert [o.state for o in result.outcomes] == [ingress.AdmissionState.ALREADY_ADMITTED,
                                               ingress.AdmissionState.REFUSED, ingress.AdmissionState.ADMITTED]
    assert result.outcomes[0].decision == first.decision
    assert result.outcomes[1].decision.refusal is core.ReviewIntentRefusal.PULL_REQUEST_NOT_OPEN
    assert len(runtime.jobs.list_jobs()) == 2
    assert [c[-1] for c in pulls.calls if c[0] == "read"] == [42, 43, 44]


def test_legacy_existing_pr_does_not_block_later_new_pr_in_scan(tmp_path):
    runtime, fabric = adapter(tmp_path)
    chosen = manual_decision()
    provenance = {"schema": "mastermind.github_review_runtime_admission.v1"}
    for name in ("repository", "pull_number", "frozen_head_sha", "actor", "intent_id", "command_id"):
        provenance[name] = getattr(chosen, name)
    legacy = runtime.jobs.create_job("Legacy", command_id=chosen.command_id, provenance=provenance,
                                     requested_authorities=["READ"], allowed_write_paths=[])
    pulls = Pages({1: ingress.OpenPullRequestPage((42, 43), False)})
    result = scan(pulls, fabric)
    assert result.complete and result.interruption is None
    assert result.outcomes[0].job_id == legacy.job_id
    assert result.outcomes[0].state is ingress.AdmissionState.ALREADY_ADMITTED
    assert result.outcomes[0].decision.refusal is core.ReviewIntentRefusal.ADMITTED_DECISION_UNAVAILABLE
    assert result.outcomes[0].decision.actor is None and result.outcomes[0].decision.delivery_command_id is None
    assert result.outcomes[1].state is ingress.AdmissionState.ADMITTED
    assert len(runtime.jobs.list_jobs()) == 2


def test_scan_bound_and_partial_failure_are_explicit_without_losing_admissions(tmp_path):
    runtime, fabric = adapter(tmp_path)
    pulls = Pages({1: ingress.OpenPullRequestPage((42, 43), True), 2: RuntimeError("private transport detail")})
    first = scan(pulls, fabric, max_pages=1)
    assert not first.complete and first.next_page == 2 and first.interruption is None
    assert len(runtime.jobs.list_jobs()) == 2
    second = scan(pulls, fabric, start_page=2, owner_execution_ref="ROOT-1740:cycle-2")
    assert not second.complete and second.interruption == "REVIEW_RECONCILIATION_LIST_UNAVAILABLE"
    assert "private transport" not in json.dumps(second.to_dict())
    assert len(runtime.jobs.list_jobs()) == 2


def test_disabled_or_unarmed_backfill_earns_no_reads(tmp_path):
    runtime, fabric = adapter(tmp_path)
    pulls = Pages({})
    with pytest.raises(ingress.ReviewIngressUnavailable, match="DISABLED"):
        scan(pulls, fabric, policy=actor_policy())
    with pytest.raises(ingress.ReviewIngressUnavailable, match="UNARMED"):
        scan(pulls, fabric, authorize=lambda ref: False)
    assert pulls.calls == [] and runtime.jobs.list_jobs() == []


def test_receiver_exposes_backfill_only_to_bound_internal_owner(tmp_path):
    runtime, fabric = adapter(tmp_path)
    pulls = Pages({1: ingress.OpenPullRequestPage((42,), False)})
    receiver = GitHubReviewReceiver(settings=settings(allow_repository_policy_review=True),
        secret_source=Secrets(), pull_requests=pulls, actors=Actors(), fabric=fabric)
    with pytest.raises(ingress.ReviewIngressUnavailable, match="OWNER_UNARMED"):
        receiver.reconcile_open_pull_requests(owner_execution_ref="ROOT-1740:cycle-1")
    assert pulls.calls == []
    receiver = GitHubReviewReceiver(settings=settings(allow_repository_policy_review=True),
        secret_source=Secrets(), pull_requests=pulls, actors=Actors(), fabric=fabric,
        reconciliation_guard=lambda ref: None if ref == "ROOT-1740:cycle-1" else False)
    assert receiver.reconcile_open_pull_requests(owner_execution_ref="ROOT-1740:cycle-1").complete


def test_receiver_cannot_attribute_reads_to_another_allowlisted_installation(tmp_path):
    runtime, fabric = adapter(tmp_path)
    pulls, actors = Pulls(), Actors()
    selected = settings(allow_repository_policy_review=True,
                        installation_ids=frozenset({4242, 4243}))
    receiver = GitHubReviewReceiver(settings=selected, secret_source=Secrets(),
        pull_requests=pulls, actors=actors, fabric=fabric)
    status, response = http(receiver, payload(sender="dependabot[bot]", installation=4243))
    assert status == 200
    assert response["reason"] == "INSTALLATION_NOT_ALLOWLISTED"
    assert pulls.reads == actors.reads == 0
    assert runtime.jobs.list_jobs() == []
    assert selected.review_policy().installation_ids == frozenset({4242})


def test_api_pagination_is_repository_scoped_and_never_follows_link_headers():
    requests = []
    def wire(request):
        requests.append(request)
        return httpx.Response(200, json=[{"number": 42}],
                              headers={"Link": '<https://attacker.example/steal>; rel="next"'})
    api, tokens = source(wire)
    page = api.list_open_pull_request_numbers(repository=REPO, page=1, per_page=2)
    assert page == ingress.OpenPullRequestPage((42,), False)
    assert len(requests) == tokens.calls == 1
    assert requests[0].url.host == "api.github.com"
    assert dict(requests[0].url.params) == {"state": "open", "sort": "created", "direction": "asc", "per_page": "2", "page": "1"}
    with pytest.raises(GitHubReviewAPIUnavailable, match="OUT_OF_SCOPE"):
        api.list_open_pull_request_numbers(repository="other/repo", page=1, per_page=2)
    assert tokens.calls == 1


def test_socket_requires_independent_host_policy_and_reconciliation_owner(tmp_path):
    runtime = Runtime.at(tmp_path)
    def owner(**kwargs):
        return ExecutiveGitHubReviewSocketOwner(runtime=runtime, admission_guard=lambda: None,
            source_guard=lambda chosen: None, repositories=frozenset({REPO}), **kwargs)
    def frame(chosen):
        return {"schema": FRAME_SCHEMA, "action": "admit_or_join", "decision": chosen.to_dict(), "objective": "Review"}
    with pytest.raises(GitHubReviewSocketRefused, match="POLICY_NOT_ENROLLED"):
        owner().handle_frame(frame(automatic()))
    with pytest.raises(GitHubReviewSocketRefused, match="OWNER_UNARMED"):
        owner(automatic_policy=policy()).handle_frame(frame(reconciled()))
    forged = dataclasses.replace(automatic(), policy_authority=dataclasses.replace(automatic().policy_authority, policy_digest="0" * 64))
    with pytest.raises(GitHubReviewSocketRefused, match="POLICY_NOT_ENROLLED"):
        owner(automatic_policy=policy()).handle_frame(frame(forged))
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("body", ["Short context", "Long context " * 800, "検証🙂" * 900])
def test_real_socket_returns_original_decision_across_automatic_and_reconciled_origins(tmp_path, body):
    async def exercise():
        runtime = Runtime.at(tmp_path / "runtime")
        owner = ExecutiveGitHubReviewSocketOwner(runtime=runtime, admission_guard=lambda: None,
            source_guard=lambda chosen: None, repositories=frozenset({REPO}),
            automatic_policy=policy(), reconciliation_guard=lambda ref: None)
        path = str(tmp_path / "review.sock")
        async def handle(reader, writer):
            try:
                result = owner.handle_frame(json.loads(await reader.readline()))
                response = {"ok": True, "result": result}
            except Exception:
                response = {"ok": False}
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, path=path)
        try:
            client = ExecutiveReviewSocketClient(socket_path=path)
            current = facts(body=body)
            first = await asyncio.to_thread(ingress.admit_decided_review, decision=automatic(), pull_request=current, fabric=client)
            joined = await asyncio.to_thread(ingress.admit_decided_review, decision=reconciled(), pull_request=current, fabric=client)
            assert first.state is ingress.AdmissionState.ADMITTED and joined.state is ingress.AdmissionState.ALREADY_ADMITTED
            assert joined.decision == first.decision and joined.job_id == first.job_id
            assert len(runtime.jobs.list_jobs()) == 1
            objective = runtime.jobs.get_job(first.job_id).objective
            assert "Retrieve the complete diff" in objective
            assert "Excerpts are not coverage evidence" in objective
            assert len(json.dumps(objective, ensure_ascii=True).encode("ascii")) <= 3000
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(exercise())


def test_later_trigger_cannot_reattribute_the_slack_parent(tmp_path):
    runtime, fabric = adapter(tmp_path)
    receipt = fabric.admit_or_join_review_intent(decision=automatic(), objective="Original")
    threads = ExecutiveSlackReviewThreads(runtime=runtime)
    with pytest.raises(SlackReviewThreadUnavailable, match="SOURCE_IDENTITY_MISMATCH"):
        threads.reserve_parent_send(decision=reconciled(), job_id=receipt.job_id)
    assert threads.reserve_parent_send(decision=receipt.decision, job_id=receipt.job_id)
    assert not threads.reserve_parent_send(decision=receipt.decision, job_id=receipt.job_id)
