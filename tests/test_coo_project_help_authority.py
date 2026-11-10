"""Current project DATA and original Executive root through actual read owners.

The existing fixture creates local Git publications and a real Runtime root.
Its credential/PR, source-seal and native-execution seams remain explicitly
inert. Plan v2 is acquired by the real installed collector and fixed child;
Mission v3 uses its real bounded Runtime/discovery acquisition. No live host,
OAuth enrollment, provider, native session, network service or activation is
claimed. This file does not replace an owner response with a constructed DTO.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import coo_project_help_contract as wire
from common.workspace_project_plan_contract import BODY_SCHEMA_V2
from control_plane.coo_principal_host import CooHostProvider
from control_plane.coo_project_help_read import capture_project_help_authority
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_PROJECT_HELP_PROFILE_ID as PROFILE,
)
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA, COO_SCOPES, _digest, principal_frame,
)
from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
from integrations.session_bridge.installed import (
    build_runtime_session_bridge, principal_frame as session_frame,
)
from integrations.session_bridge.project_task_context import (
    SCHEMA as PLAN_SCHEMA, contract_digest, load_context, parse_plan,
)
from tests import test_executive_coo_host as host_tests
from tests.test_fabric_result_projection import _release
from tests.test_installed_source_git_identity import identity
from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_project_discovery_installed_plan import (
    full_joined, actual_child, discovery_service,
)
from tests.test_project_planning_factory import invocation
from tests.test_workspace_project_git_publisher import git

ROOT = Path(__file__).resolve().parents[1]


def _source_plan(work_ref):
    value = {
        "schema": PLAN_SCHEMA, "workstream": work_ref,
        "objective": "Keep the original project and ask its currently authorized owners for help.",
        "requirements": [{"id": "R1", "text": "Use current source and original root evidence."}],
        "allowed_paths": [], "non_goals": ["No execution or new authority from a context read."],
        "tasks": [{"id": "T1", "title": "Observe original project help", "requirement_ids": ["R1"],
            "depends_on": [], "acceptance": [{"id": "A1", "text": "Original owner scope stays current."}],
            "state": "pending", "evidence": []}],
    }
    raw = ("# Original project help plan\n\n```mastermind-plan\n"
           + json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n```\n").encode()
    assert parse_plan(raw) == value
    return raw, contract_digest(value)


def _adopt_actual_source_plan(j):
    """Two real commits make the typed decision refer to immutable plan bytes."""
    from scripts import agentos  # Captured actual Macro owner from the fixture.
    work = j["args"]["work_ref"]
    relative = "docs/plans/eg2-project-help.md"
    raw, contract = _source_plan(work)
    path = j["integrator"] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    git(j["integrator"], "add", relative)
    git(j["integrator"], "commit", "-m", "Fixture original source plan")
    source = {"repository": "mastermindx-market-intelligence/macro", "path": relative,
        "commit": git(j["integrator"], "rev-parse", "HEAD").strip(),
        "content_sha256": hashlib.sha256(raw).hexdigest()}
    decision = {
        "key": "EG2-HELP", "question": "Which exact project plan governs this fixture?",
        "answer": "The original source bytes.", "rationale": "An explicit test adoption.",
        "alternatives": [{"option": "Infer", "why_not": "The original source is available."}],
        "evidence": ["Fixture source readback"], "affects": [work], "confidence": "high",
        "reversibility": "easy", "decided_by": "fixture-owner", "decided_at": "2026-11-10",
        "project_plan_adoption": {"schema": "agentos.project_plan_adoption.v1", "work_ref": work,
            "adopted_source": source, "predecessor": None, "proposal_source": None,
            "display_revision": None},
    }
    relative_decision = "agentos/decisions/DEC-EG2-HELP.md"
    decision_path = j["integrator"] / relative_decision
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(agentos._yaml_frontmatter(decision) + "\nOriginal fixture adoption.\n")
    git(j["integrator"], "add", relative_decision)
    git(j["integrator"], "commit", "-m", "Fixture explicit original plan adoption")
    git(j["integrator"], "push", "origin", "main")
    j["current"] = git(j["integrator"], "rev-parse", "HEAD").strip()
    return {"schema": wire.PLAN_SCHEMA, "work_ref": work, "source": source,
            "contract_sha256": contract}, raw


def _frame(f):
    _, fact, authority = f.provider.source.for_principal(principal_frame(f.principal), f.work)
    return {"schema": wire.FRAME_SCHEMA, "principal": principal_frame(f.principal),
        "session_principal": session_frame(f.principal), "workspace_principal": workspace_frame(f.j["workspace"]),
        "principal_context": {"work_ref": f.work, "principal_binding_digest": fact.principal_binding_digest,
            "mission_authority_ref": authority.mission_authority_ref,
            "authority_generation_digest": authority.authority_generation_digest},
        "capability_profile_digest": authority.capability_profile_digest}


@pytest.fixture
def qualified_help(full_joined, monkeypatch, tmp_path):
    j = full_joined
    j["full_c"] = True
    _, children = actual_child(j, monkeypatch)
    admitted = asyncio.run(invocation(j["factory"], j["args"],
        lambda: j["factory"].submit(**j["args"])))
    selected_plan, raw_plan = _adopt_actual_source_plan(j)
    original, caches, lease = discovery_service(j, monkeypatch)
    try:
        workspace = WorkspaceReadService(cache=original.cache, runtime=original.runtime,
            authorize=original.authorize, armed={}, runtime_identity={},
            bounded_runtime=original._bounded_runtime, project_discovery=original._project_discovery,
            canonical_project_data=j["data"].installed_binding())
        work = j["args"]["work_ref"]
        # This current project is absent from the installed C catalogue. Its
        # actual published DATA owner, not a synthetic responsibility row,
        # must qualify the exact original Runtime root.
        assert not any(row.get("work_ref") == work for row in caches[0].state_cache["doc"]["work"])
        plan = workspace._read_project_plan({"work_ref": work}, workspace_frame(j["workspace"]))
        assert plan["schema"] == BODY_SCHEMA_V2 and plan["availability"] == "AVAILABLE", plan
        assert plan["continuity"]["adoption"]["state"] == "AVAILABLE", plan["continuity"]
        assert plan["continuity"]["adoption"]["adoption"]["adopted_source"] == selected_plan["source"]
        assert plan["continuity"]["adoption"]["content"].encode() == raw_plan
        assert children  # Real fixed isolated Plan/discovery child was reached.

        host_dir = tmp_path / "help-coo-source"
        host_dir.mkdir()
        source_host, coo, _, policy_path = host_tests.setup(host_dir)
        raw = json.loads(policy_path.read_bytes())
        assert raw["profiles"][PROFILE]["enabled"] is False
        raw["profiles"][PROFILE]["enabled"] = True  # Explicit disposable grant.
        policy_path.write_text(json.dumps(raw))
        registry = ExecutionCapabilityRegistry.load(policy_path, source_root=ROOT)
        policy = dataclasses.replace(j["factory"].policies.read,
            policy_id="project-help-coo", required_scopes=COO_SCOPES)
        principal = dataclasses.replace(j["workspace"], policy_id=policy.policy_id,
            resource=policy.resource, scopes=policy.required_scopes)
        binding = {"schema": BINDING_SCHEMA, "enabled": True,
            "binding": {**principal_frame(principal), "permission_digest": "d" * 64}}
        coo.update(policy=json.loads(json.dumps(dataclasses.asdict(policy))), binding=binding)
        scope = {"schema": wire.SCOPE_SCHEMA, "root_job_id": admitted["job_id"], "source_plan": selected_plan}
        coo["missions"][0].update(work_ref=work, principal_binding_digest=_digest(binding["binding"]),
            capability_profile_id=PROFILE, capability_profile_digest=registry.profiles[PROFILE].profile_digest,
            authority_version=4, principal_actions=[wire.ACTION], project_help=scope)
        provider = CooHostProvider(source_host.source, workspace)
        f = SimpleNamespace(j=j, work=work, root=admitted["job_id"], coo=coo, policy_path=policy_path,
            provider=provider, workspace=workspace, principal=principal, scope=scope,
            source_plan=selected_plan, raw_plan=raw_plan, children=children, caches=caches)
        f.frame = _frame(f)
        yield f
    finally:
        _release(*lease)


def test_actual_installed_plan_and_mission_qualify_original_help_scope_without_writes(qualified_help, tmp_path):
    f = qualified_help
    events = [item.to_dict() for item in f.j["runtime"].events.list_events()]
    captured = capture_project_help_authority(f.provider, f.frame)
    assert captured.scope == f.scope
    assert captured.principal_context == f.frame["principal_context"]
    assert {key: captured.mission_read[key] for key in (
        "qualification", "mission_read_state", "transport", "execution_authorized")} == {
        "qualification": "CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH", "mission_read_state": "PARTIAL",
        "transport": {"dispatch_state": "UNKNOWN", "reason": "dispatch_evidence_not_supplied",
            "actionable": False, "historical": True}, "execution_authorized": False}
    assert len(captured.mission_read["root_origin_sha256"]) == 64
    assert "boot_packet: unavailable" in captured.mission_read["diagnostics"]
    assert any("durable orchestration root provenance not projected" in item
        for item in captured.mission_read["diagnostics"])
    # The ordinary memory grant owner_root=None is not an Executive root;
    # this scope comes from the explicit v4 row and actual Mission v3 read.
    assert captured.source_row["project_help"]["root_job_id"] == f.root
    context = load_context(workspace_root=f.j["integrator"], relative_path=f.source_plan["source"]["path"],
        workstream=f.work, expected_sha256=f.source_plan["source"]["content_sha256"])
    assert wire.context_matches_source_plan(context, f.source_plan)
    result = asyncio.run(f.provider.read_project_help(f.frame))
    assert result["scope"] == f.scope
    assert result["observation"]["mission"] == captured.mission_read
    assert result["targets"] == wire.unavailable_targets("SESSION_BRIDGE_NOT_COMPOSED")
    assert result["execution_authority"] is False and result["native_origin_attested"] is False
    # The actual installed read adapter can be present without inventing an
    # active child. The real target owner observes the admitted, queued root.
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "never-opened.sock")
    connected = asyncio.run(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
    assert connected["targets"]["state"] == "AVAILABLE"
    assert connected["targets"]["items"] == []
    assert [item.to_dict() for item in f.j["runtime"].events.list_events()] == events


def test_foreign_or_stale_principal_cannot_borrow_help_enrollment(qualified_help):
    f = qualified_help
    for path, value in [
        (("principal_context", "principal_binding_digest"), "f" * 64),
        (("principal_context", "authority_generation_digest"), "f" * 64),
        (("principal_context", "work_ref"), "WS:FOREIGN-HELP"),
        (("workspace_principal", "subject_digest"), "f" * 64),
        (("session_principal", "subject_digest"), "f" * 64),
    ]:
        frame = copy.deepcopy(f.frame)
        frame[path[0]][path[1]] = value
        with pytest.raises((ValueError, LookupError)):
            capture_project_help_authority(f.provider, frame)
    row = f.coo["missions"][0]
    row["enabled"] = False
    with pytest.raises(ValueError):
        capture_project_help_authority(f.provider, f.frame)
    row["enabled"] = True
    assert capture_project_help_authority(f.provider, f.frame).scope == f.scope


def test_actual_current_data_mission_receipt_keeps_its_closed_owner_joins(qualified_help):
    from control_plane.coo_principal_mandate import _mission_state
    from common.project_discovery_observation_contract import validate_coherence
    f = qualified_help
    acquired = f.workspace._read_mission_v3({"principal": workspace_frame(f.j["workspace"]),
        "selection": {"work_ref": f.work, "root_job_id": f.root}})
    assert acquired["ok"] is True
    assert "help_read_qualification" not in acquired
    original = acquired["result"]
    receipt = original["source"]["owner_observation"]
    assert receipt["schema"] == "mastermind.workspace_source_observation.v2"
    assert receipt["project_data"]["source"]["commit"] == f.j["current"]
    assert validate_coherence(receipt, work_ref=f.work, root_job_id=f.root) == receipt
    qualified = _mission_state(original, expected_work_ref=f.work)
    # A current DATA card has no invented transport proof. The general
    # mandate correctly remains unqualified for new effects; help uses its
    # separate private READ qualification from the same actual owner inputs.
    assert qualified.qualified is False
    assert qualified.reason_codes == ("mission_read_state_not_current",)
    assert original["read_state"]["state"] == "PARTIAL"
    assert original["transport"]["dispatch_state"] == "UNKNOWN"
    assert original["transport"]["historical"] is True
    # These are adversarial mutations of an actual acquired receipt. None is
    # returned by a substituted owner or used to assert source authority.
    for change in ("foreign_root", "runtime_drift", "control_drift", "foreign_data",
            "foreign_code", "foreign_creation", "unknown_data_field"):
        candidate = copy.deepcopy(original)
        row = candidate["source"]["owner_observation"]
        if change == "foreign_root":
            row["selection"]["root_job_id"] = "JOB-999999"
        elif change == "runtime_drift":
            row["runtime"]["after"] += 1
        elif change == "control_drift":
            row["control_room"]["publication_after"] += 1
        elif change == "foreign_data":
            row["project_data"]["source"]["commit"] = "f" * 40
        elif change == "foreign_code":
            row["project_data"]["code_source"]["commit"] = "f" * 40
        elif change == "foreign_creation":
            row["project_data"]["creation_publication"]["selection"]["work_ref"] = "WS:FOREIGN-HELP"
        else:
            row["project_data"]["caller_authority"] = True
        with pytest.raises((ValueError, KeyError, TypeError)):
            validate_coherence(row, work_ref=f.work, root_job_id=f.root)


def test_actual_read_qualification_refuses_stale_card_and_other_partial_causes(qualified_help, monkeypatch):
    from control_plane import workspace_project_discovery_read as owner
    f = qualified_help
    qualify = owner._project_help_qualification
    observations = []

    def inspect_actual_inputs(project, mission, selected, *, roots, creation):
        result = qualify(project, mission, selected, roots=roots, creation=creation)
        assert result["selection"] == {"work_ref": f.work, "root_job_id": f.root}
        observations.append(result)
        # The normal read continues with the original owner result. Changed
        # copies below are fed only into refusal checks for this pure helper.
        for change in ("stale_card", "duplicate_card", "foreign_card_root", "historical",
                "other_partial", "degraded_missingness", "foreign_root", "missing_origin",
                "foreign_origin", "foreign_root_row", "foreign_creation"):
            changed_project, changed_mission = copy.deepcopy(project), copy.deepcopy(mission)
            changed_roots, changed_creation = copy.deepcopy(roots), copy.deepcopy(creation)
            if change == "stale_card":
                changed_project["source_validity"]["cards"][0]["components"]["card"]["remaining_ms"] = 0
            elif change == "duplicate_card":
                rows = changed_project["control_room"]["autonomy"]["responsibilities"]
                rows.append(copy.deepcopy(rows[0]))
            elif change == "foreign_card_root":
                changed_project["source_validity"]["cards"][0]["root_job_id"] = "JOB-999999"
            elif change == "historical":
                changed_mission["read_state"]["state"] = "HISTORICAL"
            elif change == "other_partial":
                changed_mission["transport"]["reason"] = "no_exact_join_match"
            elif change == "degraded_missingness":
                changed_mission["missingness"].append({"missingness_class": "DEGRADED",
                    "target_field": "execution", "producer_owner": "executive_os", "reason": "fixture degraded owner"})
            elif change == "foreign_root":
                changed_mission["mission"]["root_job_candidates"] = [f.root, "JOB-999999"]
            elif change == "missing_origin":
                changed_roots["origins"] = []
            elif change == "foreign_origin":
                changed_roots["origins"][0]["work_ref"] = "WS:FOREIGN-HELP"
            elif change == "foreign_root_row":
                changed_roots["rows"][0]["root_job_id"] = "JOB-999999"
            else:
                changed_creation["selection"]["work_ref"] = "WS:FOREIGN-HELP"
            with pytest.raises((ValueError, KeyError, TypeError)):
                qualify(changed_project, changed_mission, selected,
                    roots=changed_roots, creation=changed_creation)
        return result

    monkeypatch.setattr(owner, "_project_help_qualification", inspect_actual_inputs)
    result = asyncio.run(f.provider.read_project_help(f.frame))
    assert len(observations) == 2
    assert result["observation"]["mission"]["mission_read_state"] == "PARTIAL"
    assert result["execution_authority"] is False


def test_newly_enrolled_foreign_root_or_adoption_never_retargets_the_read(qualified_help):
    f = qualified_help
    row = f.coo["missions"][0]
    original = copy.deepcopy(row["project_help"])
    for change in ("root", "source_commit", "source_hash", "source_path", "contract"):
        row["project_help"] = copy.deepcopy(original)
        if change == "root":
            row["project_help"]["root_job_id"] = "JOB-999999"
        elif change == "contract":
            row["project_help"]["source_plan"]["contract_sha256"] = "f" * 64
        else:
            key = {"source_commit": "commit", "source_hash": "content_sha256", "source_path": "path"}[change]
            row["project_help"]["source_plan"]["source"][key] = (
                "docs/plans/foreign.md" if key == "path" else "f" * (40 if key == "commit" else 64))
        current = _frame(f)  # Even a current explicit row must match real owners.
        with pytest.raises((ValueError, LookupError)):
            capture_project_help_authority(f.provider, current)
    row["project_help"] = original
    assert capture_project_help_authority(f.provider, f.frame).scope == f.scope


def test_actual_plan_read_cannot_release_after_original_mission_revocation(qualified_help, monkeypatch):
    f = qualified_help
    # Plan now shares Mission's actual DATA acquisition. Revoke at the same
    # physical Plan child boundary, without replacing its output or owner.
    collector = f.j["collector"]
    original = collector._runner
    reads = []

    def revoked_after_real_read(argv, **kwargs):
        result = original(argv, **kwargs)
        if any(str(item).endswith("/scripts/agentos_project_plan_entry.py") for item in argv):
            reads.append(list(argv))
            f.coo["missions"][0]["enabled"] = False
        return result

    monkeypatch.setattr(collector, "_runner", revoked_after_real_read)
    with pytest.raises(ValueError):
        capture_project_help_authority(f.provider, f.frame)
    assert len(reads) == 1


def test_actual_workspace_grant_revocation_prevents_plan_and_runtime_read(qualified_help, monkeypatch):
    f = qualified_help
    document = f.j["document"]
    document["profiles"][document["primary_profile"]]["enabled"] = False
    monkeypatch.setattr(f.workspace, "_read_mission_v3", lambda *_a, **_k: pytest.fail("revoked principal reached Runtime"))
    monkeypatch.setattr(f.workspace, "_read_project_plan", lambda *_a, **_k: pytest.fail("revoked principal reached plan"))
    with pytest.raises(ValueError):
        capture_project_help_authority(f.provider, f.frame)


def test_actual_source_plan_parser_refuses_wrong_scope_before_help_delivery(qualified_help):
    f = qualified_help
    context = load_context(workspace_root=f.j["integrator"], relative_path=f.source_plan["source"]["path"],
        workstream=f.work, expected_sha256=f.source_plan["source"]["content_sha256"])
    for field, value in (("workstream", "WS:FOREIGN-HELP"), ("source_path", "docs/plans/foreign.md"),
            ("source_sha256", "f" * 64), ("contract_sha256", "f" * 64)):
        changed = copy.deepcopy(context)
        changed[field] = value
        with pytest.raises(ValueError):
            wire.context_matches_source_plan(changed, f.source_plan)
    path = f.j["integrator"] / f.source_plan["source"]["path"]
    path.write_bytes(f.raw_plan + b"\nUnadopted progress edit.\n")
    with pytest.raises(ValueError):
        load_context(workspace_root=f.j["integrator"], relative_path=f.source_plan["source"]["path"],
            workstream=f.work, expected_sha256=f.source_plan["source"]["content_sha256"])
