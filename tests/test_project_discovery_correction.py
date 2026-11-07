"""Actual Macro Git capture -> existing private input/Events -> fixed publisher.

Temporary Git and explicit facade/credential/PR fixture boundaries are used.
No production permission, installed enrollment, account or host proof is claimed.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from common import workspace_discovery_correction_contract as contract
from common.workspace_source_operation_wire import validate_knowledge_lookup, validate_operation_request
from control_plane.agentos_project_knowledge_recipe import compile_project_knowledge_recipe, restore_project_knowledge_recipe
from control_plane.canonical_data_publication import capture_source_publication
from control_plane.ceo_boot_packet import bounded_subprocess_runner
from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_project_git_publisher import PublisherBinding, FixedProjectGitPublisher
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter
from integrations.mastermind_workspace_app.knowledge_publisher_events import KnowledgePublisherEvents, KnowledgeOperationConflict
from integrations.mastermind_workspace_app.knowledge_source_service import ProjectKnowledgeSourceOwner
from integrations.mastermind_workspace_app.project_authoring_grant import SCHEMA_V6
from integrations.mastermind_workspace_app.source_operation_http import _preview
from tests.discovery_correction_test_support import source_bytes
from tests.test_agentos_project_knowledge_recipe import canonical_workstream
from tests.test_knowledge_publisher_events import granted
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_project_git_publisher import env, isolated_git_env, git, rev_parse, InertPullRequestOwner


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def selection(preview):
    return {"schema": "mastermind.workspace_source_operation_lookup.v1", **preview["selection"]}


def old_note():
    return ("---\nschema: agentos.discovery.v1\nkey: ORIGINAL-FINDING\n"
        "claim: The original measured result.\nfalsifier: pytest tests/finding.py changes the result\n"
        "so_what: Use the measured path.\nkind: runtime\nverified_at: '2026-10-01'\n"
        "verified_by: pytest tests/finding.py\nscope: [WS:ALPHA]\nconfidence: probable\n"
        "---\n\nPreserve original evidence. 中文\n")


@pytest.fixture
def correction_owner(env, monkeypatch, tmp_path):
    ws=canonical_workstream().replace("- DEC:EARLIER-CALL\n", "[]\n")
    # Keep a genuine empty YAML list on the original decisions key.
    ws=ws.replace("decisions:\n[]\n", "decisions: []\n")
    old=old_note()
    for path,text in [("scripts/agentos.py",source_bytes("scripts/agentos.py")),
                      ("scripts/project_knowledge_recipes.py",source_bytes("scripts/project_knowledge_recipes.py")),
                      ("agentos/workstreams/WS-ALPHA.md",ws),
                      ("agentos/discoveries/DSC-ORIGINAL-FINDING.md",old)]:
        target=env.clone/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    git(env.clone,"add","scripts","agentos");git(env.clone,"commit","-m","Actual correction source and synthetic records")
    git(env.clone,"push","origin","main")
    commit=rev_parse(env.clone,"HEAD");calls=[];reads=[]
    def runner(argv,**kwargs):
        reads.append(tuple(argv))
        return bounded_subprocess_runner(argv,**kwargs)
    def fixture_read(facade,*,mode,request,actor_ref,permission_binding_digest,decision_date,initial_snapshot,source_binding):
        calls.append(mode)
        common=dict(macro_root=facade._macro_root,expected_macro_sha=rev_parse(env.clone,"HEAD"),
            request=request,actor_ref=actor_ref,permission_binding_digest=permission_binding_digest,runner=runner)
        if mode=="prepare":return compile_project_knowledge_recipe(**common,decision_date=decision_date)
        return restore_project_knowledge_recipe(**common,initial_snapshot=initial_snapshot,source_binding=source_binding)
    monkeypatch.setattr(InstalledProjectKnowledgeCompiler,"_read",fixture_read)
    compiler=InstalledProjectKnowledgeCompiler(macro_root=env.clone)
    adapter=ProjectKnowledgeRecipeAdapter(compiler)
    _,bindings,who,contexts=granted("add_project_file",{"work_ref":"WS:ALPHA","permission_digest":"3"*64})
    bindings["schema"]=SCHEMA_V6
    for slot in bindings["profiles"].values():
        slot.update(project_plan_proposal_publish=None,project_canonical_data_read=None,project_discovery_correct=None)
    bindings["profiles"]["member-0"]["project_discovery_correct"]={"work_ref":"WS:ALPHA","permission_digest":"5"*64}
    runtime,supervisor,execution=empty_owner(tmp_path/"custody")
    events=SourceOperationEvents(runtime.store);private=ProjectSourceOriginalInput(supervisor)
    event_adapter=KnowledgePublisherEvents(events=events,contexts=contexts)
    binding=PublisherBinding(worktree=str(env.clone),expected_origin=str(env.origin),default_branch="main",publisher_identity="synthetic-fixed-service-identity")
    pr=InertPullRequestOwner(env.origin)
    service=ProjectKnowledgeSourceOwner(events=events,private_inputs=private,permission_factory=contexts,adapter=adapter,
        publisher_events=event_adapter,publisher_binding=binding,qualify_publisher=lambda value:value==binding,
        pr_owner=pr,retained_date=lambda:"2026-11-07")
    request={"schema":contract.REQUEST_SCHEMA,"request_id":contract.REQUEST_PREFIX+"a"*40,"work_ref":"WS:ALPHA",
        "source_commit":commit,"base_revision":sha(ws),"discovery_ref":"DSC:ORIGINAL-FINDING",
        "expected_discovery_revision":sha(old),"correction_reason":"A retained observation contradicts the prior measured result.",
        "replacement":{"claim":"The corrected measured result.","falsifier":"pytest tests/new_finding.py disproves it",
            "so_what":"Use the corrected measured path.","kind":"runtime","confidence":"probable",
            "verified_at":"2026-11-05","verified_by":"pytest tests/new_finding.py","expires":None,
            "body_utf8":"\nNew evidence. 中文\n","evidence":["tests/new_finding.py:12"]}}
    return dict(service=service,compiler=compiler,adapter=adapter,request=request,who=who,bindings=bindings,
        contexts=contexts,runtime=runtime,private=private,events=events,pr=pr,env=env,calls=calls,reads=reads,old=old,ws=ws,execution=execution)


def test_actual_capture_three_image_publication_and_exact_preview(correction_owner):
    o=correction_owner;preview=o["service"].prepare(o["request"],o["who"])
    scope=preview["owner_context"]["principal_scope"]
    assert _preview(preview,{"action":contract.ACTION,"request":o["request"]},scope)==preview
    assert len(preview["preview"]["postimages"])==3 and o["pr"].create_calls==0
    assert preview["preview"]["change"]["replacement"]["verified_at"]=="2026-11-05"
    assert any("--batch" in argv for argv in o["reads"])
    safe=json.dumps([event.to_dict() for event in o["runtime"].store.list_events()])
    assert o["request"]["correction_reason"] not in safe and o["request"]["replacement"]["body_utf8"] not in safe
    selected=selection(preview)
    result=o["service"].submit(lookup=selected,preview_witness=preview["preview_witness"],principal=o["who"])
    assert result["receipt"]["kind"]=="PROPOSAL_OBSERVED",result
    assert o["pr"].create_calls==1
    before=len(o["calls"])
    assert o["service"].submit(lookup=selected,preview_witness=preview["preview_witness"],principal=o["who"])==result
    assert len(o["calls"])==before and o["pr"].create_calls==1


@pytest.mark.parametrize("changed",["discovery_ref","expected_discovery_revision","base_revision","source_commit","work_ref","replacement"])
def test_same_id_changed_original_conflicts_before_second_capture(correction_owner,changed):
    o=correction_owner;o["service"].prepare(o["request"],o["who"]);before=list(o["calls"])
    request=copy.deepcopy(o["request"])
    if changed=="discovery_ref":request[changed]="DSC:OTHER-FINDING"
    elif changed=="work_ref":request[changed]="WS:OTHER"
    elif changed=="replacement":request[changed]["claim"]="A changed claim under the same original ID."
    else:request[changed]="f"*len(request[changed])
    with pytest.raises((SourceOperationConflict,PermissionError)):o["service"].prepare(request,o["who"])
    assert o["calls"]==before and o["pr"].create_calls==0


def test_restore_after_data_advance_uses_original_bodies_closure_date_and_code(correction_owner):
    o=correction_owner;preview=o["service"].prepare(o["request"],o["who"])
    path=o["env"].clone/"agentos/discoveries/DSC-ORIGINAL-FINDING.md"
    path.write_text("TODAYS CHANGED BODY MUST NOT BECOME THE ORIGINAL\n")
    git(o["env"].clone,"add",str(path));git(o["env"].clone,"commit","-m","Changed later DATA")
    o["reads"].clear()
    restored=o["service"].prepare(o["request"],o["who"])
    assert restored==preview
    assert not any("--batch" in argv or any(str(item).startswith("agentos/") for item in argv) for argv in o["reads"])
    assert o["pr"].create_calls==0


def test_body_free_reconciliation_three_sources_one_commit_and_current_data_selection(correction_owner,monkeypatch):
    o=correction_owner;service=o["service"];request=o["request"]
    preview=service.prepare(request,o["who"]);selected=selection(preview)
    first=service.submit(lookup=selected,preview_witness=preview["preview_witness"],principal=o["who"])
    assert first["receipt"]["kind"]=="PROPOSAL_OBSERVED",first
    integrator=o["env"].tmp_path/"integrator"
    git(o["env"].tmp_path,"clone",str(o["env"].origin),str(integrator))
    git(integrator,"fetch","origin",first["receipt"]["proposal"]["head_branch"])
    git(integrator,"merge","--no-ff","--no-edit","FETCH_HEAD");git(integrator,"push","origin","main")
    monkeypatch.setattr(o["compiler"],"_read",lambda **kw:pytest.fail("compiler during original reconciliation"))
    monkeypatch.setattr(o["private"],"read",lambda *a,**kw:pytest.fail("private body during original reconciliation"))
    lookup=contract.request_lookup(request)
    assert service.read_status(lookup,o["who"])==first
    final=service.reconcile(lookup,o["who"])
    assert final["disposition"]=="accepted" and final["receipt"]["kind"]=="SOURCE_OBSERVED",final
    assert len(final["receipt"]["sources"])==3
    assert len({item["commit"] for item in final["receipt"]["sources"]})==1
    permission=o["contexts"].bind(o["who"],action=contract.ACTION,work_ref="WS:ALPHA")
    proof=capture_source_publication(o["events"],selected,permission.principal_scope,guard=permission.check)
    assert proof.check(permission.principal_scope)["sources"]==final["receipt"]["sources"]
    assert selected in o["events"].publication_candidates("WS:ALPHA",permission.principal_scope,guard=permission.check)["lookups"]
    assert o["pr"].create_calls==1


def test_recorded_frontend_correction_owner_journey(correction_owner):
    """Export actual owner/Git DTOs; native auth and installed CODE stay explicit UI seams."""
    import os
    from control_plane.agentos_project_knowledge import read_project_knowledge_catalogue, read_project_knowledge_source
    o=correction_owner;service=o["service"];request=o["request"];root=o["env"].clone
    def read(root):
        commit=rev_parse(root,"HEAD")
        catalogue=read_project_knowledge_catalogue(macro_root=root,expected_macro_sha=commit,work_ref="WS:ALPHA")
        assert catalogue["availability"]=="AVAILABLE",catalogue
        sources={}
        for row in catalogue["project"]["records"]:
            if row["kind"]=="DISCOVERY":
                body=read_project_knowledge_source(macro_root=root,expected_macro_sha=commit,work_ref="WS:ALPHA",
                    source_ref=row["source_ref"],expected_revision=row["revision"])
                assert body["availability"]=="AVAILABLE",body
                sources[row["source_ref"]]=body
        return catalogue,sources
    before,before_sources=read(root)
    original=next(value for value in before_sources.values() if value["source"]["path"]=="agentos/discoveries/DSC-ORIGINAL-FINDING.md")
    assert original["document"]["content_utf8"]==o["old"]
    permission=o["contexts"].bind(o["who"],action=contract.ACTION,work_ref=request["work_ref"])
    context=permission.public_context()
    preview=service.prepare(request,o["who"])
    selected=selection(preview);lookup=contract.request_lookup(request)
    prepared_status=service.read_status(lookup,o["who"])
    proposal=service.submit(lookup=selected,preview_witness=preview["preview_witness"],principal=o["who"])
    assert proposal["receipt"]["kind"]=="PROPOSAL_OBSERVED"
    landed=o["env"].tmp_path/"frontend-integrator"
    git(o["env"].tmp_path,"clone",str(o["env"].origin),str(landed))
    git(landed,"fetch","origin",proposal["receipt"]["proposal"]["head_branch"])
    git(landed,"merge","--no-ff","--no-edit","FETCH_HEAD");git(landed,"push","origin","main")
    final=service.reconcile(lookup,o["who"])
    assert final["disposition"]=="accepted" and len(final["receipt"]["sources"])==3
    after,after_sources=read(landed)
    assert len(after_sources)==2
    old_after=next(value for value in after_sources.values() if value["source"]["path"]==original["source"]["path"])
    assert "Preserve original evidence. 中文" in old_after["document"]["content_utf8"]
    assert "superseded_by:" in old_after["document"]["content_utf8"]
    assert any("The corrected measured result." in value["document"]["content_utf8"] for value in after_sources.values())
    output=os.environ.get("MM_DISCOVERY_CORRECTION_OWNER_OUTPUT")
    if output:
        Path(output).write_text(json.dumps({"schema":"mastermind.discovery_correction_owner_fixture.v1",
            "scope":"ACTUAL_OWNER_AND_TEMP_GIT_NATIVE_AUTH_AND_INSTALLED_CODE_ARE_EXPLICIT_UI_SEAMS",
            "compiler_source":"b4b08673508bb0aafe2aa729666f1aefab23911c",
            "request":request,"lookup":lookup,"context":context,"preview":preview,
            "prepared_status":prepared_status,"proposal_status":proposal,"source_status":final,
            "before_catalogue":before,"before_sources":before_sources,"original_source":original,
            "after_catalogue":after,"after_sources":after_sources},ensure_ascii=False,indent=2)+"\n")


@pytest.mark.parametrize("mutation",["partial","duplicate","mixed_commit"])
def test_three_image_source_proof_refuses_partial_duplicate_or_mixed_evidence(correction_owner,mutation):
    o=correction_owner;preview=o["service"].prepare(o["request"],o["who"])
    planned={"postimages":preview["preview"]["postimages"]}
    sources=[{"repository":"macro","commit":"d"*40,"path":p["path"],"content_sha256":p["content_sha256"]} for p in planned["postimages"]]
    if mutation=="partial":sources.pop()
    elif mutation=="duplicate":sources[-1]=sources[0]
    else:sources[-1]["commit"]="e"*40
    with pytest.raises(KnowledgeOperationConflict):KnowledgePublisherEvents._source_proof(planned,{"sources":sources})


def test_post_invocation_exception_stays_unknown_and_is_never_dispatched_again(correction_owner,monkeypatch):
    o=correction_owner;preview=o["service"].prepare(o["request"],o["who"]);calls=[]
    def unknown(*args,**kwargs):calls.append(True);raise OSError("fixture: uncertain after invocation")
    monkeypatch.setattr(FixedProjectGitPublisher,"publish_knowledge",unknown)
    args=dict(lookup=selection(preview),preview_witness=preview["preview_witness"],principal=o["who"])
    first=o["service"].submit(**args)
    assert first["disposition"]=="unknown" and first["receipt"]["kind"]=="PHASE_ATTEMPTED"
    assert o["service"].submit(**args)==first and calls==[True]


def test_distinct_grant_withdrawal_blocks_action_and_original_inspection(correction_owner):
    o=correction_owner;o["service"].prepare(o["request"],o["who"])
    o["bindings"]["profiles"]["member-0"]["project_discovery_correct"]=None
    with pytest.raises(PermissionError):o["service"].read_status(contract.request_lookup(o["request"]),o["who"])
    with pytest.raises(PermissionError):o["service"].prepare(o["request"],o["who"])
    assert o["pr"].create_calls==0


def test_closed_correction_lookup_preserves_separate_preference_shape(correction_owner):
    request=correction_owner["request"];lookup=contract.request_lookup(request)
    assert validate_knowledge_lookup(lookup)==lookup
    assert validate_operation_request("prepare",{"action":contract.ACTION,"request":request})["request"]==request
    with pytest.raises(ValueError):validate_knowledge_lookup({**lookup,"expected_preference_revision":None})
    with pytest.raises(ValueError):validate_operation_request("prepare",{"action":contract.ACTION,"request":{**request,"actor_ref":"caller"}})


@pytest.mark.parametrize("attack",["foreign_ref","directory_symlink","duplicate_yaml","fourth_image"])
def test_capture_refuses_incomplete_or_ambiguous_reference_universe(correction_owner,attack):
    o=correction_owner;root=o["env"].clone
    if attack=="foreign_ref":
        path=root/"agentos/workstreams/WS-OTHER.md";path.write_text(o["ws"].replace("key: ALPHA","key: OTHER")+"\n")
        text=path.read_text().replace("artifacts:","discoveries: [DSC:ORIGINAL-FINDING]\nartifacts:");path.write_text(text)
    elif attack=="directory_symlink":
        target=root/"foreign-records";target.mkdir();(target/"foreign.md").write_text("---\nworkstream: WS:OTHER\ndiscoveries: [DSC:ORIGINAL-FINDING]\n---\n")
        (root/"agentos/handoffs").symlink_to("../foreign-records",target_is_directory=True)
    elif attack=="duplicate_yaml":
        path=root/"agentos/discoveries/DSC-ORIGINAL-FINDING.md";path.write_text(o["old"].replace("scope: [WS:ALPHA]","scope: [WS:OTHER]\nscope: [WS:ALPHA]"))
    else:
        path=root/"scripts/project_knowledge_recipes.py";path.write_text(path.read_text()+"\n_original_correction = build_project_discovery_correct\ndef build_project_discovery_correct(*args, **kwargs):\n result = _original_correction(*args, **kwargs)\n result['postimages'].append(dict(result['postimages'][0], path='unrelated.md'))\n return result\n")
    git(root,"add",".");git(root,"commit","-m","Synthetic hostile source boundary")
    request=copy.deepcopy(o["request"]);request["source_commit"]=rev_parse(root,"HEAD")
    if attack=="duplicate_yaml":request["expected_discovery_revision"]=sha((root/"agentos/discoveries/DSC-ORIGINAL-FINDING.md").read_text())
    with pytest.raises(ValueError):o["service"].prepare(request,o["who"])
    assert o["pr"].create_calls==0
