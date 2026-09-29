"""Installed host composition with real registry/parser and disposable sources."""
from __future__ import annotations
import copy
import dataclasses
import json
from pathlib import Path
import sys
import pytest

from control_plane.coo_principal_host import CooHostProvider, FACT_SCHEMA, validate_missions
from ops.executive_os.coo_principal_host import CooInstalledSource
from control_plane.coo_principal_envelope import PrincipalAdmissionContext, derive_principal_envelope
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.executive_mcp.coo import COO_SERVER_NAME, COO_SERVER_VERSION, COO_TOOL_SPECS
from integrations.mastermind_executive_app.coo_binding import _digest
sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_coo_install_binding as install
    import test_coo_principal_mandate as mandate
finally:
    sys.path.pop(0)
ROOT = Path(__file__).resolve().parents[1]


def registry_file(tmp_path):
    raw = json.loads((ROOT / "config/executive_agent_capabilities.json").read_text())
    template = copy.deepcopy(raw["mcp_servers"]["openai-developer-docs-v1"])
    specs = {s.name: {"name": s.name, "inputSchema": s.input_schema,
                     "annotations": s.annotations} for s in COO_TOOL_SPECS}
    template.update(config_name="mastermindExecutive", url="https://mcp.mastermind-x.com/mcp/coo",
        auth_status="oAuth", server_identity=COO_SERVER_NAME, server_version=COO_SERVER_VERSION,
        enabled_tools=sorted(specs), tool_schema_digest=observed_mcp_tool_schema_digest({"tools": specs}))
    raw["mcp_servers"]["executive-coo-test"] = template
    profile = copy.deepcopy(raw["profiles"]["operator.appserver.readonly.v1"])
    profile["mcp_servers"] = ["executive-coo-test"]
    raw["profiles"]["coo.test.v1"] = profile
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(raw))
    return path


def setup(tmp_path):
    path = registry_file(tmp_path)
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    coo = install.coo_block()
    coo["missions"] = [dict(enabled=True, work_ref="WS:EXECUTIVE-CAPACITY-FABRIC",
        principal_binding_digest=_digest(coo["binding"]["binding"]),
        mission_authority_ref="authority:coo-test", outcome_ref="outcome:coo-test",
        proof_contract_ref="proof:coo-test", capability_profile_id="coo.test.v1",
        capability_profile_digest=registry.profiles["coo.test.v1"].profile_digest,
        execution_profiles=["research_only"], allowed_write_paths=[])]
    source = CooInstalledSource(lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    workspace = WorkspaceReadService(cache=None, runtime=None, authorize=None, armed={}, runtime_identity={})
    host = CooHostProvider(source, workspace)
    principal = {k: v for k, v in coo["binding"]["binding"].items() if k != "permission_digest"}
    return host, coo, principal, path


def test_real_registry_and_install_binding_produce_exact_authority(tmp_path):
    host, coo, principal, _ = setup(tmp_path)
    frame = dict(schema=FACT_SCHEMA, operation="authority", work_ref=coo["missions"][0]["work_ref"], principal=principal)
    first = host.facts(frame)
    assert first["release_class"] == "RESERVED_RELEASE"
    assert first["source_grant_digest"] is None and first["economic_envelope_digest"] is None
    coo["missions"][0]["enabled"] = False
    assert host.facts(frame) == first  # disarming new effects cannot rewrite accepted identity


def envelope_for(host, tmp_path):
    row, fact, authority = host.source.snapshot("WS:EXECUTIVE-CAPACITY-FABRIC")
    context = PrincipalAdmissionContext(row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    value = derive_principal_envelope(dict(operation_key="coo-host-test", objective="Inspect the current mission.",
        department="executive-infrastructure", priority=5, execution_profile="research_only",
        workstream=row["work_ref"]), context=context, workspace_root=str(tmp_path / "workspaces"),
        grounding=dict(mastermind_sha="a" * 40, macro_sha="b" * 40, boot_packet_schema="mastermind.ceo_boot_packet.v1"))
    return value["envelope"]


def test_final_guard_uses_real_mandate_reducer_and_current_mission(tmp_path, monkeypatch):
    host, coo, _, _ = setup(tmp_path)
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", lambda work_ref: mandate.mission_doc())
    envelope = envelope_for(host, tmp_path)
    assert host.guard(envelope) is None
    coo["missions"][0]["enabled"] = False
    with pytest.raises(ValueError): host.guard(envelope)


@pytest.mark.parametrize("fault", ["binding", "mission", "profile", "schema", "revoked", "principal"])
def test_host_facts_refuse_unenrolled_or_changed_sources(tmp_path, fault):
    host, coo, principal, path = setup(tmp_path)
    row = coo["missions"][0]
    frame = dict(schema=FACT_SCHEMA, operation="authority", work_ref=row["work_ref"], principal=principal)
    if fault == "binding": row["principal_binding_digest"] = "f" * 64
    if fault == "mission": coo["missions"] = []
    if fault == "profile": row["capability_profile_digest"] = "f" * 64
    if fault == "schema":
        raw = json.loads(path.read_text()); raw["mcp_servers"]["executive-coo-test"]["tool_schema_digest"] = "f" * 64
        path.write_text(json.dumps(raw))
    if fault == "revoked": coo["binding"] = install.coo_binding(enabled=False)
    if fault == "principal": frame["principal"]["client_ref"] = "f" * 64
    with pytest.raises(ValueError): host.facts(frame)


@pytest.mark.parametrize("fault", ["disabled", "identity", "profile", "path", "stale"])
def test_new_job_guard_refuses_outside_exact_current_grant(tmp_path, monkeypatch, fault):
    host, coo, _, _ = setup(tmp_path); envelope = envelope_for(host, tmp_path)
    document = mandate.mission_doc()
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", lambda work_ref: document)
    if fault == "disabled": coo["missions"][0]["enabled"] = False
    if fault == "identity": envelope["authority_generation_digest"] = "f" * 64
    if fault == "profile": envelope["execution_contract"]["requested_authorities"] = ["READ", "RUN_TESTS", "WRITE_BRANCH"]
    if fault == "path": envelope["execution_contract"]["allowed_write_paths"] = ["outside/path"]
    if fault == "stale": document["read_state"]["state"] = "HISTORICAL"
    with pytest.raises(ValueError): host.guard(envelope)


@pytest.mark.parametrize("fault", ["duplicate", "extra", "boolean", "wildcard", "profile", "empty"])
def test_mission_rows_are_closed_and_non_widening(tmp_path, fault):
    _, coo, _, _ = setup(tmp_path); rows = coo["missions"]
    if fault == "duplicate": rows.append(copy.deepcopy(rows[0]))
    if fault == "extra": rows[0]["authority_level"] = "A7"
    if fault == "boolean": rows[0]["enabled"] = 1
    if fault == "wildcard": rows[0].update(execution_profiles=["bounded_code_change"], allowed_write_paths=["tests/*"])
    if fault == "profile": rows[0]["execution_profiles"] = ["admin"]
    if fault == "empty": rows[0]["execution_profiles"] = []
    with pytest.raises(ValueError): validate_missions(rows)


def test_installed_mission_disarm_is_dynamic_but_scope_is_immutable(tmp_path, monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    _, coo, _, _ = setup(tmp_path); raw = install.base_document()
    raw.update(coo=coo, executive_mcp_profile=WEB_CEO_V2_PROFILE)
    source = tmp_path / raw["release_sha"]; source.mkdir()
    path = tmp_path / "executive-mcp.json"; path.write_text(json.dumps(raw))
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(entry.os, "geteuid", lambda: 451)
    loader = entry.current_projection_loader(path, source, raw, "coo", None, expected_uid=451)
    changed = copy.deepcopy(raw); changed["coo"]["missions"][0]["enabled"] = False
    path.write_text(json.dumps(changed)); assert loader()["missions"][0]["enabled"] is False
    changed["coo"]["missions"][0]["outcome_ref"] = "outcome:changed"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError): loader()


from tests import test_workspace_result_service as real_workspace
result_owner = real_workspace.result_owner


def test_work_ref_selection_uses_actual_workspace_and_runtime_owners(tmp_path, result_owner):
    host, coo, principal, _ = setup(tmp_path)
    selected = result_owner["selection"]
    coo["missions"][0]["work_ref"] = selected["work_ref"]
    host = CooHostProvider(host.source, real_workspace.service(result_owner))
    before = result_owner["namespace"].entries
    result = host.facts(dict(schema=FACT_SCHEMA, operation="mission", work_ref=selected["work_ref"], principal=principal))
    assert result["read_state"]["state"] == "CURRENT"
    assert result["source"]["owner_observation"]["selection"]["root_job_id"] == selected["root_job_id"]
    assert result["source"]["owner_observation"]["runtime"]["state"] == "SAME"
    assert result_owner["namespace"].entries == before + 1 == result_owner["namespace"].exits


def test_ambiguous_responsibility_is_refused_before_runtime_read(tmp_path, result_owner):
    host, coo, _, _ = setup(tmp_path)
    workspace = real_workspace.service(result_owner)
    owner = result_owner["owners"][0]
    row = owner.state_cache["doc"]["autonomy"]["responsibilities"][0]
    owner.state_cache["doc"]["autonomy"]["responsibilities"].append(copy.deepcopy(row))
    before = result_owner["namespace"].entries
    with pytest.raises((ValueError, LookupError)):
        workspace.read_mission_for_work_ref(result_owner["selection"]["work_ref"])
    assert result_owner["namespace"].entries == before


def test_disabled_mission_cannot_report_ready_but_identity_remains_readable(tmp_path, monkeypatch):
    host, coo, principal, _ = setup(tmp_path)
    coo["missions"][0]["enabled"] = False
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", lambda _: pytest.fail("disabled mission acquired"))
    frame = dict(schema=FACT_SCHEMA, operation="authority", work_ref=coo["missions"][0]["work_ref"], principal=principal)
    assert host.facts(frame)["work_ref"] == frame["work_ref"]
    with pytest.raises(ValueError): host.facts(dict(frame, operation="mission"))


def test_changed_delegation_during_mission_read_refuses_result(tmp_path, monkeypatch):
    host, coo, principal, _ = setup(tmp_path)
    def moved(_):
        coo["missions"][0]["enabled"] = False
        return mandate.mission_doc()
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", moved)
    with pytest.raises(ValueError):
        host.facts(dict(schema=FACT_SCHEMA, operation="mission", work_ref=coo["missions"][0]["work_ref"], principal=principal))


@pytest.mark.parametrize("value", [1, None, "true"])
def test_control_arming_is_not_inferred_from_truthiness(value):
    from ops.executive_os.coo_principal_host import validate_control_coo
    assert validate_control_coo({}) is False
    with pytest.raises(ValueError): validate_control_coo({"coo_principal_armed": value})


def test_guard_rereads_delegation_after_workspace_acquisition(tmp_path, monkeypatch):
    host, coo, _, _ = setup(tmp_path)
    envelope = envelope_for(host, tmp_path)
    def moved(_):
        coo["missions"][0]["enabled"] = False
        return mandate.mission_doc()
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", moved)
    with pytest.raises(ValueError): host.guard(envelope)
