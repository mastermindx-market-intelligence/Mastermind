"""Real a5/e4, captured Git records, Runtime Events and private artifact owner.

Only external identity/grant fixtures, local bare remote and inert PR owner are
used. No installed service, credential, provider or real publication is invoked.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zlib
import base64

import pytest

from control_plane.project_plan_adoption_operation import PlanAdoptionRecipeAdapter
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationEvents
from control_plane.workspace_project_git_publisher import PublisherBinding
from integrations.mastermind_workspace_app.project_plan_adoption_service import ProjectPlanAdoptionSourceOwner
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from tests.test_agentos_plan_continuity_capture import repository, read
from tests.test_plan_adoption_read_roundtrip import compiler
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_plan_adoption_git_publisher import old, isolated_git_env


@pytest.fixture
def joined(repository, tmp_path, request):
    repo, work = repository, "WS:PLAN-TEST"
    code, owner = compiler(), repository["owner"]
    source_fixture = json.loads((Path(__file__).parent / "fixtures/agentos-plan-adoption-compiler-a5cb.json").read_bytes())
    code_raw = zlib.decompress(base64.b64decode(source_fixture["zlib_base64"], validate=True))
    repo["write"]("scripts/agentos_plan_adoption.py", code_raw)
    proposed = dict(repo["ws"], objective="Adopt this exact reviewed plan.")
    candidate = (repo["git"]("show", "HEAD:agentos/workstreams/WS-PLAN-TEST.md") if getattr(request, "param", False)
                 else owner._yaml_frontmatter(proposed).encode() + b"\nReal candidate body\r\n")
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    header = dict(repo["header"], candidate_sha256=candidate_sha)
    repo["write"]("planning/proposal.md", owner._yaml_frontmatter(header).encode() + candidate)
    head = repo["commit"]()
    repo["git"]("branch", "-M", "main")
    origin, clone = tmp_path / "origin.git", tmp_path / "publisher-clone"
    old.git(tmp_path, "init", "--bare", str(origin))
    repo["git"]("remote", "add", "origin", str(origin))
    repo["git"]("push", "-u", "origin", "main")
    old.git(tmp_path, "clone", str(origin), str(clone))
    rid = "mmos-project-adopt-" + "9" * 40
    candidate_path = "planning/proposal.candidate-" + candidate_sha[:20] + ".md"
    decision_path = "agentos/decisions/DEC-PLAN-ADOPTION-" + "9" * 40 + ".md"
    def captured(path, at):
        raw = repo["git"]("show", at + ":" + path)
        return {"source": {"repository": code.MACRO, "path": path, "commit": at,
            "content_sha256": hashlib.sha256(raw).hexdigest()}, "raw_bytes": raw}
    request = {"schema": "agentos.plan_adoption_request.v1", "request_id": rid, "work_ref": work,
        "expected_commit": head, "expected_adoption": "DEC:PLAN-FIRST",
        "proposal_source": captured("planning/proposal.md", head)["source"],
        "base_source": repo["baseline"]["source"], "candidate_sha256": candidate_sha}
    binding = {name: captured(path, head)["source"] for name, path in {
        "compiler": "scripts/agentos_plan_adoption.py", "owner": "scripts/agentos.py",
        "contract": "scripts/agentos_project_plan_contract.py"}.items()}
    adapter = PlanAdoptionRecipeAdapter(compiler=code, owner=owner, source_binding=binding)
    state = SimpleNamespace(qualified=True, unavailable=False, captures=0, actor_calls=0)
    def capture_snapshot(original, who, phase):
        state.captures += 1
        if state.unavailable: raise ValueError("synthetic source unavailable")
        at = repo["git"]("rev-parse", "HEAD").decode().strip()
        if phase == "CANDIDATE" and at != original["expected_commit"]:
            raise ValueError("synthetic stale source")
        value = {"schema": "agentos.plan_adoption_snapshot.v1", "repository": code.MACRO, "commit": at,
            "workstream": captured("agentos/workstreams/WS-PLAN-TEST.md", at),
            "decisions": [captured("agentos/decisions/DEC-PLAN-FIRST.md", at)],
            "proposal": captured("planning/proposal.md", at), "base": repo["baseline"],
            "candidate_target": {"path": candidate_path, "state": "ABSENT"},
            "decision_target": {"path": decision_path, "state": "ABSENT"}}
        if phase == "ADOPTION":
            value["candidate_target"] = {"path": candidate_path, "state": "CAPTURED", "capture": captured(candidate_path, at)}
        return value
    def actor_for(who, original, snapshot):
        state.actor_calls += 1
        return {"principal_id": who.subject_digest, "decided_by": "fixture-member",
            "decided_at": "2026-11-04", "decision_rationale": "Adopt the exact explicitly reviewed proposal."}
    policy, bindings = project_bindings()
    bindings["profiles"]["member-0"]["plan_adoption"] = {"work_ref": work, "permission_digest": "8" * 64}
    who = verified(policy, principal(bindings))
    permissions = WorkspaceSourceOperationContextFactory(policy=policy, load_bindings=lambda: bindings, now=lambda: 2)
    runtime, supervisor, native = empty_owner(tmp_path / "private")
    events, private = SourceOperationEvents(runtime.store), ProjectSourceOriginalInput(supervisor)
    pr = old.InertPullRequestOwner(origin)
    publisher_binding = PublisherBinding(worktree=str(clone), expected_origin=str(origin),
        default_branch="main", publisher_identity=old.PUBLISHER_IDENTITY)
    def service():
        return ProjectPlanAdoptionSourceOwner(events=events, private_inputs=private, permission_factory=permissions,
            adapter=adapter, capture_snapshot=capture_snapshot, actor_for=actor_for,
            qualify_recipe=lambda *args: state.qualified, publisher_binding=publisher_binding,
            qualify_publisher=old.qualify_publisher, pr_owner=pr)
    source = service()
    lookup = {"schema": "mastermind.workspace_source_operation_lookup.v1", "action": "ADOPT_PLAN",
              "request_id": rid, "work_ref": work}
    def merge(status):
        branch = status["receipt"]["proposal"]["head_branch"]
        repo["git"]("fetch", "origin", branch)
        repo["git"]("merge", "--ff-only", "FETCH_HEAD")
        repo["git"]("push", "origin", "main")
        repo["head"] = repo["git"]("rev-parse", "HEAD").decode().strip()
    def prepare_submit():
        preview = source.prepare(request, who)
        return preview, source.submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=who)
    return SimpleNamespace(**locals())


def advance_request(f, ready):
    return {"schema": "mastermind.workspace_source_operation_advance.v1", "action": "ADOPT_PLAN",
        "request_id": f.rid, "work_ref": f.work, **ready["advance"]}


def test_real_compiler_private_events_git_two_phases_then_actual_current_plan_read(joined):
    f = joined
    preview, pending = f.prepare_submit()
    assert preview["request_sha256"] != preview["recipe_fingerprint_sha256"]
    assert pending["disposition"] == "unknown" and pending["receipt"]["kind"] == "PROPOSAL_OBSERVED"
    assert f.pr.create_calls == 1 and f.runtime.jobs.list_jobs() == []
    baseline = f.repo["git"]("show", "HEAD:agentos/workstreams/WS-PLAN-TEST.md")
    assert baseline != f.candidate
    f.merge(pending)
    before_get = len(f.runtime.store.list_events())
    assert f.source.read_status(f.lookup, f.who)["reason"] != "READY_FOR_ADVANCE"
    assert len(f.runtime.store.list_events()) == before_get
    ready = f.source.reconcile(f.lookup, f.who)
    assert ready["reason"] == "READY_FOR_ADVANCE" and ready["disposition"] == "unknown"
    assert f.repo["git"]("show", "HEAD:agentos/workstreams/WS-PLAN-TEST.md") == baseline
    # Re-enter the original owner; actor/date/private material do not refresh.
    source = f.service()
    phase2 = source.advance(advance_request(f, ready), f.who)
    assert phase2["phase"] == "ADOPTION" and phase2["disposition"] == "unknown"
    assert f.state.actor_calls == 1 and f.pr.create_calls == 2
    f.merge(phase2)
    f.state.unavailable = True
    final = source.reconcile(f.lookup, f.who)
    assert final["disposition"] == "accepted" and len(final["receipt"]["sources"]) == 3
    assert f.state.actor_calls == 1 and f.runtime.jobs.list_jobs() == [] and f.native.spec is None
    assert "raw_bytes" not in json.dumps(final) and "decision_rationale" not in json.dumps(final)
    actual, _ = read(f.repo)
    assert actual["continuity"]["adoption"]["state"] == "AVAILABLE", actual
    assert actual["continuity"]["adoption"]["decision_ref"] == "DEC:PLAN-ADOPTION-" + "9" * 40
    assert actual["continuity"]["proposals"]["items"][0]["adoption_relation"] == "CURRENT_DECISION_REFERENCES_PROPOSAL"
    assert actual["continuity"]["proposals"]["items"][0]["comparison_basis"] == "RECORDED_PREDECESSOR"


def test_later_reserved_boundary_denial_keeps_original_candidate_and_zero_new_attempt(joined):
    f = joined
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    before = len(f.runtime.store.list_events())
    f.state.qualified = False
    with pytest.raises(PermissionError, match="RECIPE_UNQUALIFIED"):
        f.source.advance(advance_request(f, ready), f.who)
    assert len(f.runtime.store.list_events()) == before and f.pr.create_calls == 1
    assert f.source.read_status(f.lookup, f.who) == ready


def test_duplicate_advance_and_current_source_loss_never_repeat_publication(joined):
    f = joined
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    first = f.source.advance(advance_request(f, ready), f.who)
    count, captures = len(f.runtime.store.list_events()), f.state.captures
    f.state.unavailable = True
    assert f.source.advance(advance_request(f, ready), f.who) == first
    assert len(f.runtime.store.list_events()) == count and f.state.captures == captures
    assert f.pr.create_calls == 2 and f.source.read_status(f.lookup, f.who) == first
    assert f.source.reconcile(f.lookup, f.who)["phase"] == "ADOPTION"
    assert f.state.captures == captures and f.pr.create_calls == 2


def test_grant_loss_between_ready_and_advance_does_not_borrow_read_or_create(joined):
    f = joined
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    count = len(f.runtime.store.list_events())
    f.bindings["profiles"]["member-0"]["plan_adoption"] = None
    with pytest.raises(PermissionError): f.source.advance(advance_request(f, ready), f.who)
    with pytest.raises(PermissionError): f.source.read_status(f.lookup, f.who)
    assert len(f.runtime.store.list_events()) == count and f.pr.create_calls == 1


def test_existing_intent_prepare_recovers_frozen_preview_without_actor_or_source_refresh(joined):
    f = joined
    first = f.source.prepare(f.request, f.who)
    count, captures = len(f.runtime.store.list_events()), f.state.captures
    f.state.unavailable = True
    assert f.source.prepare(f.request, f.who) == first
    assert len(f.runtime.store.list_events()) == count and f.state.captures == captures and f.state.actor_calls == 1
    changed = deepcopy(f.request); changed["candidate_sha256"] = "f" * 64
    with pytest.raises(Exception): f.source.prepare(changed, f.who)
    assert len(f.runtime.store.list_events()) == count and f.state.captures == captures


def test_stale_proposal_after_candidate_settlement_never_claims_adoption(joined):
    f = joined
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    count = len(f.runtime.store.list_events())
    raw = f.repo["git"]("show", "HEAD:planning/proposal.md")
    f.repo["write"]("planning/proposal.md", raw + b"\nchanged proposal\n")
    f.repo["commit"](); f.repo["git"]("push", "origin", "main")
    with pytest.raises(Exception): f.source.advance(advance_request(f, ready), f.who)
    assert len(f.runtime.store.list_events()) == count and f.pr.create_calls == 1
    assert f.source.read_status(f.lookup, f.who) == ready


def test_malformed_request_never_reaches_source_or_actor_callback(joined):
    f = joined
    with pytest.raises(Exception): f.source.prepare({**f.request, "actor": "caller"}, f.who)
    assert f.state.captures == 0 and f.state.actor_calls == 0
    assert f.runtime.store.list_events() == [] and f.runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("joined", [True], indirect=True)
def test_real_compiler_omitted_unchanged_ws_still_requires_full_logical_readback(joined):
    f = joined
    _, pending = f.prepare_submit(); f.merge(pending)
    ready = f.source.reconcile(f.lookup, f.who)
    phase2 = f.source.advance(advance_request(f, ready), f.who)
    permission = f.source._permission(f.who, f.lookup)
    binding = f.events.publication_binding(f.lookup, permission.principal_scope, phase="ADOPTION", guard=permission.check)
    assert len(binding["postimages"]) == 3
    ws = next(i for i in binding["postimages"] if i["path"].startswith("agentos/workstreams/"))
    assert ws["content_sha256"] == ws["expected_preimage_sha256"] == f.candidate_sha
    f.merge(phase2)
    final = f.source.reconcile(f.lookup, f.who)
    assert final["disposition"] == "accepted" and len(final["receipt"]["sources"]) == 3


def test_source_callback_failure_is_closed_and_creates_no_intent(joined):
    f = joined
    f.source._capture = lambda *args: (_ for _ in ()).throw(ValueError("PRIVATE_SOURCE_CANARY"))
    with pytest.raises(ValueError, match="^SOURCE_OPERATION_SOURCE_UNAVAILABLE$"):
        f.source.prepare(f.request, f.who)
    assert f.runtime.store.list_events() == [] and f.pr.create_calls == 0


@pytest.mark.parametrize("later", [False, True])
def test_boundary_qualification_loss_after_claim_cannot_start_a_publication(joined, monkeypatch, later):
    f = joined
    preview = f.source.prepare(f.request, f.who)
    ready = None
    if later:
        pending = f.source.submit(lookup=f.lookup, preview_witness=preview["preview_witness"], principal=f.who)
        f.merge(pending); ready = f.source.reconcile(f.lookup, f.who)
    before, creates = old.snapshot(f.clone), f.pr.create_calls
    actual = f.source._publisher
    def after_claim(*args, **kwargs):
        publisher = actual(*args, **kwargs)
        f.state.qualified = False
        return publisher
    monkeypatch.setattr(f.source, "_publisher", after_claim)
    if later:
        result = f.source.advance(advance_request(f, ready), f.who)
        assert result["disposition"] == "unknown" and result["phase"] == "ADOPTION"
    else:
        result = f.source.submit(lookup=f.lookup, preview_witness=preview["preview_witness"], principal=f.who)
        assert result["disposition"] == "refused" and result["reason"] == "NOT_DISPATCHED"
    assert f.pr.create_calls == creates and old.snapshot(f.clone) == before
