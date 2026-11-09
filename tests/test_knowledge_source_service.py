"""Actual canonical Git-byte compiler→private custody→Events→temporary Git.

The nominal installed facade's private read is connected to the actual fixed
capture engine ONLY by this explicit test fixture. Installed collector issuance,
credential qualification and PR metadata remain separate obligations. No live
Git, provider, credential or grant effect occurs here.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from control_plane.agentos_project_knowledge_recipe import compile_project_knowledge_recipe, restore_project_knowledge_recipe
from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_project_git_publisher import PublisherBinding
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter
from integrations.mastermind_workspace_app.knowledge_publisher_events import KnowledgePublisherEvents
from integrations.mastermind_workspace_app.knowledge_source_service import ProjectKnowledgeSourceOwner
from tests.test_agentos_project_knowledge_recipe import owner_bytes, canonical_workstream
from tests.test_knowledge_publisher_events import granted
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_project_git_publisher import env, isolated_git_env, git, rev_parse, InertPullRequestOwner


def selection(preview):
    return {"schema": "mastermind.workspace_source_operation_lookup.v1", **preview["selection"]}


def inspection(preview):
    images=preview["preview"]["postimages"]
    ws=next(image for image in images if image["path"].startswith("agentos/workstreams/"))
    pref=next((image for image in images if image["path"].startswith("agentos/decisions/")),None)
    return {**preview["selection"],"source_commit":preview["preview"]["source_commit"],
        "base_revision":ws["expected_preimage_sha256"],"request_sha256":preview["request_sha256"],
        "expected_preference_revision":pref["expected_preimage_sha256"] if pref else None}


@pytest.fixture
def owner(env, monkeypatch, tmp_path):
    ws = canonical_workstream()
    for path, text in [("scripts/agentos.py", owner_bytes("scripts/agentos.py")),
                       ("scripts/project_knowledge_recipes.py", owner_bytes("scripts/project_knowledge_recipes.py")),
                       ("agentos/workstreams/WS-ALPHA.md", ws)]:
        target = env.clone / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    git(env.clone, "add", "scripts", "agentos")
    git(env.clone, "commit", "-m", "Actual protected canonical bytes and synthetic project")
    git(env.clone, "push", "origin", "main")
    commit = rev_parse(env.clone, "HEAD")
    calls = []
    def fixture_read(facade, *, mode, request, actor_ref, permission_binding_digest,
                     decision_date, initial_snapshot, source_binding):
        calls.append(mode)
        common = dict(macro_root=facade._macro_root, expected_macro_sha=rev_parse(env.clone, "HEAD"),
                      request=request, actor_ref=actor_ref, permission_binding_digest=permission_binding_digest)
        if mode == "prepare":
            return compile_project_knowledge_recipe(**common, decision_date=decision_date)
        return restore_project_knowledge_recipe(**common, initial_snapshot=initial_snapshot, source_binding=source_binding)
    monkeypatch.setattr(InstalledProjectKnowledgeCompiler, "_read", fixture_read)
    compiler = InstalledProjectKnowledgeCompiler(macro_root=env.clone)
    adapter = ProjectKnowledgeRecipeAdapter(compiler)
    _, bindings, who, contexts = granted("add_project_file", {"work_ref":"WS:ALPHA", "permission_digest":"3"*64})
    bindings["profiles"]["member-0"]["project_preference_set"] = {"work_ref":"WS:ALPHA", "permission_digest":"4"*64}
    runtime, supervisor, execution = empty_owner(tmp_path / "custody")
    events = SourceOperationEvents(runtime.store)
    private = ProjectSourceOriginalInput(supervisor)
    event_adapter = KnowledgePublisherEvents(events=events, contexts=contexts)
    binding = PublisherBinding(worktree=str(env.clone), expected_origin=str(env.origin),
        default_branch="main", publisher_identity="synthetic-fixed-service-identity")
    pr = InertPullRequestOwner(env.origin)
    service = ProjectKnowledgeSourceOwner(events=events, private_inputs=private, permission_factory=contexts,
        adapter=adapter, publisher_events=event_adapter, publisher_binding=binding,
        qualify_publisher=lambda value: value == binding, pr_owner=pr, retained_date=lambda:"2026-11-04")
    request = {"schema":"mastermind.project_file_add_request.v1", "request_id":"mmos-project-file-add-"+"a"*40,
        "work_ref":"WS:ALPHA", "source_commit":commit, "base_revision":hashlib.sha256(ws.encode()).hexdigest(),
        "file":{"display_name":"Notes.md", "media_type":"text/markdown", "content_utf8":"Keep literal 中文\nline two.\n"}}
    return dict(service=service, compiler=compiler, adapter=adapter, request=request, who=who, bindings=bindings,
        runtime=runtime, private=private, events=events, pr=pr, env=env, calls=calls, execution=execution)


@pytest.mark.parametrize("preference", [False, True])
def test_actual_prepare_private_event_then_single_atomic_proposal(owner, preference):
    o=owner; request=copy.deepcopy(o["request"])
    if preference:
        request = {key:value for key,value in request.items() if key not in {"schema","file","request_id"}} | {
            "schema":"mastermind.project_preference_set_request.v1", "request_id":"mmos-project-preference-set-"+"b"*40,
            "expected_preference_revision":None, "value":"A concise 中文 summary.\nKeep this line."}
    preview=o["service"].prepare(request, o["who"]); lookup=selection(preview)
    assert preview["request_sha256"] != preview["recipe_fingerprint_sha256"]
    assert preview["preview"]["state"] == "DRAFT_ONLY" and len(preview["preview"]["postimages"]) == 2
    assert o["pr"].create_calls == 0 and o["runtime"].jobs.list_jobs() == []
    safe = json.dumps([event.to_dict() for event in o["runtime"].store.list_events()])
    assert (request.get("value") or request["file"]["content_utf8"]) not in safe
    result=o["service"].submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=o["who"])
    assert result["receipt"]["kind"] == "PROPOSAL_OBSERVED", result
    assert o["pr"].create_calls == 1
    before=len(o["calls"])
    assert o["service"].submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=o["who"]) == result
    assert len(o["calls"]) == before and o["pr"].create_calls == 1


def test_body_free_reconciliation_uses_original_events_when_compiler_and_private_unavailable(owner, monkeypatch):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    first=service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    assert first["receipt"]["kind"] == "PROPOSAL_OBSERVED", first
    branch=first["receipt"]["proposal"]["head_branch"]
    integrator=o["env"].tmp_path/"integrator"
    git(o["env"].tmp_path,"clone",str(o["env"].origin),str(integrator))
    git(integrator,"fetch","origin",branch); git(integrator,"merge","--no-ff","--no-edit","FETCH_HEAD")
    git(integrator,"push","origin","main")
    monkeypatch.setattr(o["compiler"],"_read",lambda **kw: pytest.fail("compiler read during recovery"))
    monkeypatch.setattr(o["private"],"read",lambda *a,**kw: pytest.fail("private read during recovery"))
    assert service.read_status(inspection(preview),o["who"]) == first
    final=service.reconcile(inspection(preview),o["who"])
    assert final["disposition"] == "accepted" and final["receipt"]["kind"] == "SOURCE_OBSERVED", final
    assert len(final["receipt"]["sources"]) == 2 and o["pr"].create_calls == 1


def test_original_restore_failure_has_actual_same_invocation_no_effect_and_never_retries(owner, monkeypatch):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    monkeypatch.setattr(o["compiler"],"restore",lambda *a,**kw: (_ for _ in ()).throw(ValueError("source unavailable")))
    result=service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    assert result["disposition"] == "refused" and result["reason"] == "NOT_DISPATCHED", result
    assert o["pr"].create_calls == 0
    assert service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"]) == result


def test_same_id_changed_payload_conflicts_before_new_compile(owner):
    o=owner; o["service"].prepare(o["request"],o["who"])
    changed=copy.deepcopy(o["request"]); changed["file"]["content_utf8"]="Changed"
    before=len(o["calls"])
    with pytest.raises(SourceOperationConflict): o["service"].prepare(changed,o["who"])
    assert len(o["calls"]) == before and o["pr"].create_calls == 0


def test_post_invocation_error_remains_unknown_and_no_resubmit(owner):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    o["pr"].create_error=RuntimeError("ambiguous PR response")
    result=service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    assert result["disposition"] == "unknown" and result["receipt"]["kind"] == "PHASE_ATTEMPTED", result
    assert o["pr"].create_calls == 1
    assert service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"]) == result
    assert o["pr"].create_calls == 1


def test_private_peer_carrier_keeps_original_identity_and_withdrawal_blocks_effect(owner):
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.mastermind_workspace_app.source_operation_principal import bind_private_source_principal
    o=owner; service=o["service"]; peer=[True]
    carried=bind_private_source_principal(principal_frame(o["who"]), verified_expires_at=o["who"].expires_at,
        peer_guard=lambda:peer[0])
    preview=service.prepare(o["request"],carried); lookup=selection(preview)
    # Both actual nominal carriers reach precisely the same prepared original.
    assert service.prepare(o["request"],o["who"])["preview_witness"] == preview["preview_witness"]
    peer[0]=False
    with pytest.raises(PermissionError):
        service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=carried)
    assert o["pr"].create_calls == 0
    assert service.read_status(inspection(preview),o["who"])["receipt"]["kind"] == "INTENT"


def test_revocation_during_restore_cannot_append_false_no_effect(owner, monkeypatch):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    def revoke(*a,**kw):
        o["bindings"]["profiles"]["member-0"]["project_file_add"]=None
        raise ValueError("source unavailable after revocation")
    monkeypatch.setattr(o["compiler"],"restore",revoke)
    with pytest.raises(PermissionError):
        service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    assert o["pr"].create_calls == 0
    kinds=[e.payload.get("kind") for e in o["runtime"].store.list_events()]
    assert len(kinds) == 2  # original INTENT and actual PHASE_ATTEMPTED only
    o["bindings"]["profiles"]["member-0"]["project_file_add"]={"work_ref":"WS:ALPHA","permission_digest":"3"*64}
    status=service.read_status(inspection(preview),o["who"])
    assert status["disposition"] == "unknown" and status["receipt"]["kind"] == "PHASE_ATTEMPTED"


def test_changed_distinct_grant_stamp_refuses_original_write(owner):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    o["bindings"]["profiles"]["member-0"]["project_file_add"]["permission_digest"]="8"*64
    # A newly issued distinct grant does not authorize the old original stamp.
    with pytest.raises(PermissionError):
        service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    assert o["pr"].create_calls == 0


def test_body_free_inspection_compares_all_original_safe_fields_even_after_proposal(owner):
    o=owner; service=o["service"]
    preview=service.prepare(o["request"],o["who"]); lookup=selection(preview)
    service.submit(lookup=lookup,preview_witness=preview["preview_witness"],principal=o["who"])
    for key,bad in [("source_commit","f"*40),("base_revision","f"*64),("request_sha256","f"*64)]:
        changed=inspection(preview)|{key:bad}
        with pytest.raises(SourceOperationConflict): service.read_status(changed,o["who"])
        with pytest.raises(SourceOperationConflict): service.reconcile(changed,o["who"])
    assert o["pr"].create_calls == 1
