"""Real principal, retained Runtime and CCR joins; inert paid wire transport.

Native status/artifact/ledger behavior has its own real-reader tests. Here the
last transport is deliberately inert so no test contacts an installed broker.
"""
import asyncio
import copy
import dataclasses
import hashlib
import json

import pytest

from common import executive_workspace_fabric_contract as wire
from common import executive_workspace_contract as workspace
from control_plane import executive_paid_fabric_composition as composition
from control_plane import workspace_fabric_read as reader
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.workspace_read_service import WorkspaceReadService
from scripts import chairman_control_room as ccr
from tests import test_workspace_paid_fabric_runtime as runtime_fixture
from tests.test_workspace_paid_fabric_runtime import paid
from tests.test_workspace_read_service import cache_fixture
from tests.test_mission_workspace import _owner_observation_inputs
from tests.test_executive_coo_host import setup as actual_coo_fixture


def status(run, root, parent=None):
    return {"schema": wire.STATUS_SCHEMA, "run_id": run, "root_id": root,
        "parent_run_id": parent or root, "state": "TERMINAL", "rc": 0, "signal": "ok",
        "result_available": True, "result_bytes": 7, "accepted": False,
        "accepted_by": None, "acceptance_state": "NOT_ACCEPTED", "acceptance_reason": "NO_OUTCOME"}


@pytest.fixture
def owner(tmp_path, monkeypatch, paid):
    (tmp_path / "coo").mkdir()
    coo, mutable, principal, _ = actual_coo_fixture(tmp_path / "coo")
    mutable["missions"][0]["work_ref"] = "WS:PAID-UNIT"
    row, fact, authority = coo.source.snapshot("WS:PAID-UNIT")
    context = PrincipalAdmissionContext(row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    monkeypatch.setattr(runtime_fixture, "CONTEXT", context)
    state = paid()
    principal = {**principal, "policy_id": "browser-paid-test",
                 "resource": workspace.RESOURCE, "scopes": [workspace.SCOPE]}
    owners, clock, cache = cache_fixture(tmp_path)
    doc = _owner_observation_inputs()["control_room"]
    doc = json.loads(json.dumps(doc).replace("JOB-1", state["root"].job_id)
        .replace("WS:ONE", context.work_ref).replace("2026-09-20", "2026-09-21"))
    doc["generated_at"] = owners[0].state_cache["doc"]["generated_at"]
    doc["autonomy"]["generated_at"] = doc["generated_at"]
    doc["autonomy"]["schema"] = "mastermind.autonomy_control_room.v1"
    current = doc["autonomy"]["responsibilities"][0]
    current["freshness"] = "current"
    current["validity"] = owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["validity"]
    owners[0].state_cache["doc"] = doc
    owners[0].state_cache.pop("source_validity_bounds", None)
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    permission = ["f" * 64]
    def authorize(value):
        return value == principal
    authorize.binding_digest = lambda value: permission[0] if authorize(value) else None
    service = WorkspaceReadService(cache=cache, runtime=state["runtime"], authorize=authorize,
        armed={}, runtime_identity={"db_present": True}, bounded_runtime=lambda runtime: state["reader"])
    raw = workspace.canonical({"schema_version": composition.PAID_BINDINGS_SCHEMA,
        "bindings": [{"physical_binding": state["payload"]["paid_physical_binding"],
                      "source_config": state["payload"]["paid_source_config"],
                      "quota_class": state["payload"]["paid_quota_class"]}]})
    source_path = tmp_path / "paid-bindings.json"
    source_path.write_bytes(raw)
    source_path.chmod(0o400)
    source_generation = ["fixture-root-sealed-generation"]
    # Platform custody seam only: the actual data parser, immutable binding
    # digest and repeated current-source comparisons are unmodified.
    def pinned(path, expected):
        assert path == source_path and hashlib.sha256(source_path.read_bytes()).hexdigest() == expected
        return source_path.read_bytes(), tuple(source_generation)
    monkeypatch.setattr(composition, "_read_pinned", pinned)
    source = composition.PaidBindingSource.from_path(source_path, hashlib.sha256(raw).hexdigest())
    calls = []
    effects = []
    class Client:
        async def request(self, operation, payload, **kwargs):
            assert operation == "native-fabric-status"
            assert payload["binding"] == state["payload"]["binding"]
            assert payload["physical_binding_sha256"] == state["payload"]["physical_binding_sha256"]
            assert payload["process_ref_sha256"] == workspace.digest(state["ref"].to_dict())
            from control_plane.executive_fabric_bridge_broker import start_request_sha256
            assert payload["start_request_sha256"] == start_request_sha256(state["payload"])
            calls.append(copy.deepcopy(payload))
            for effect in effects:
                effect()
            return {"adapter_id": "canonical-paid-fabric", "binding": payload["binding"],
                "physical_binding_sha256": payload["physical_binding_sha256"],
                "request_sha256": payload["start_request_sha256"],
                "process_ref_sha256": payload["process_ref_sha256"],
                "status": {**status(payload["run_id"], payload["binding"]["root_id"]),
                           "result": "PRIVATE", "session_home_reference": {"home_path": "/private"}}}
    monkeypatch.setattr("control_plane.executive_fabric_adapter._fixed_client", lambda physical: Client())
    request = {"schema": wire.FRAME_SCHEMA, "operation": wire.CATALOG_OPERATION,
               "selection": None, "principal": principal}
    return locals()


def run(owner, **overrides):
    return asyncio.run(reader.handle_fabric_frame(owner["service"], owner["request"] | overrides,
        owner["coo"].source, owner["source"]))


def selection(owner):
    return {"root_id": owner["state"]["root"].job_id, "run_id": owner["state"]["running"].attempt_id}


def test_real_principal_runtime_original_join_to_metadata_subset(owner):
    result = run(owner)
    assert result["ok"] is True, result
    body = wire.validate_catalog(result["result"])
    assert body["availability"] == "PARTIAL"
    assert body["coverage"] == {"returned_count": 1, "candidate_count": None,
        "omitted_count": None, "scan_complete": False, "status_complete": True}
    assert body["source"]["scope"] == "EXACT_RUN_SET"
    assert body["reason_codes"] == ["ROWS_OMITTED"]
    item = body["items"][0]
    assert item["status"]["acceptance_state"] == "NOT_ACCEPTED"
    assert item["status"]["accepted"] is False
    assert "PRIVATE" not in json.dumps(result) and "/private" not in json.dumps(result)
    assert len(owner["calls"]) == 1
    assert owner["state"]["namespace"].entries == owner["state"]["namespace"].exits == 2


def test_exact_status_selects_original_and_preserves_nonacceptance(owner):
    result = run(owner, operation=wire.STATUS_OPERATION, selection=selection(owner))
    assert result == {"ok": True, "result": status(selection(owner)["run_id"], selection(owner)["root_id"])}
    assert len(owner["calls"]) == 1


@pytest.mark.parametrize("case", ["foreign_principal", "disabled", "no_permission_witness", "other_root", "other_attempt", "label_only"])
def test_no_entitlement_or_original_attempt_means_zero_native_reads(owner, case):
    overrides = {}
    if case == "foreign_principal":
        overrides["principal"] = owner["principal"] | {"subject_digest": "d" * 64}
    elif case == "disabled":
        owner["mutable"]["missions"][0]["enabled"] = False
    elif case == "no_permission_witness":
        owner["permission"][0] = None
    elif case == "label_only":
        owner["mutable"]["missions"][0]["outcome_ref"] = "changed-authority"
    else:
        selected = selection(owner)
        selected["root_id" if case == "other_root" else "run_id"] = "JOB-999" if case == "other_root" else "ATT-" + "f" * 32
        overrides.update(operation=wire.STATUS_OPERATION, selection=selected)
    result = run(owner, **overrides)
    assert result["ok"] is False and result["status"] in (403, 503)
    assert owner["calls"] == []


@pytest.mark.parametrize("case", ["permission", "disabled", "generation", "physical_source", "runtime", "publication", "owner", "authorizer"])
def test_late_rotation_discards_native_response(owner, case):
    def effect():
        if case == "permission":
            owner["permission"][0] = "e" * 64
        elif case == "disabled":
            owner["mutable"]["missions"][0]["enabled"] = False
        elif case == "generation":
            owner["mutable"]["missions"][0]["outcome_ref"] = "changed-authority"
        elif case == "physical_source":
            owner["source_generation"][0] = "successor"
        elif case == "runtime":
            state = owner["state"]
            state["runtime"].attempts.adopt_attempt(state["running"].attempt_id,
                expected_fence_generation=state["running"].fence_generation, lease_owner="late-owner")
        elif case == "publication":
            owner["owners"][0].state_published_seq += 1
        elif case == "owner":
            new, _, _ = cache_fixture(owner["tmp_path"])
            owner["owners"][0] = new[0]
        else:
            previous = owner["service"].authorize
            def replacement(principal):
                return previous(principal)
            replacement.binding_digest = previous.binding_digest
            owner["service"].authorize = replacement
    owner["effects"].append(effect)
    result = run(owner)
    assert len(owner["calls"]) == 1
    assert result["ok"] is False and result["status"] in (403, 503)
    assert "items" not in json.dumps(result)


def test_bad_retained_paid_identity_does_not_reach_native_owner(owner):
    state = owner["state"]
    with state["runtime"].store.transaction() as connection:
        connection.execute("UPDATE attempts SET launch_metadata_json='{}' WHERE attempt_id=?",
            (state["running"].attempt_id,))
    assert run(owner) == workspace.error("source_unavailable", 503)
    assert owner["calls"] == []


def test_current_physical_binding_cannot_substitute_same_labels(owner):
    source = owner["source"]
    physical = source.bindings[0]
    changed = dataclasses.replace(physical, qualification={**physical.qualification, "boot_id": "another-instance"})
    object.__setattr__(source, "bindings", (changed,))
    assert run(owner) == workspace.error("source_unavailable", 503)
    assert owner["calls"] == []


def _replace_runtime(owner, state):
    old_root = owner["state"]["root"].job_id
    owner["state"] = state
    owner["service"].runtime = state["runtime"]
    owner["service"]._bounded_runtime = lambda runtime: state["reader"]
    original = owner["owners"][0]
    doc = json.loads(json.dumps(original.state_cache["doc"]).replace(old_root, state["root"].job_id))
    original.state_cache["doc"] = doc
    with original.state_lock:
        ccr._publish_source_validity(original, doc, tuple(owner["clock"]), tuple(owner["clock"]))


def test_proved_ordinary_ceo_root_is_omitted_without_native_authority(owner, monkeypatch):
    from control_plane.ceo_intent import submit_intent
    monkeypatch.setattr(runtime_fixture.paid_fixtures, "submit_intent", submit_intent)
    _replace_runtime(owner, owner["paid"]())
    result = run(owner)
    assert result["ok"] is True, result
    catalog = wire.validate_catalog(result["result"])
    assert catalog["items"] == [] and catalog["availability"] == "PARTIAL"
    assert catalog["coverage"]["candidate_count"] is None
    assert catalog["coverage"]["omitted_count"] is None
    assert catalog["coverage"]["scan_complete"] is False
    assert catalog["reason_codes"] == ["ROWS_OMITTED"]
    assert owner["calls"] == []
    assert run(owner, operation=wire.STATUS_OPERATION, selection=selection(owner)) == workspace.error("access_denied", 403)
    assert owner["calls"] == []


def test_unlaunched_principal_claim_is_partial_without_guessed_native_run(owner):
    _replace_runtime(owner, owner["paid"](claimed_only=True))
    result = run(owner)
    assert result["ok"] is True, result
    assert result["result"]["items"] == []
    assert result["result"]["availability"] == "PARTIAL"
    assert result["result"]["coverage"]["candidate_count"] is None
    assert owner["calls"] == []


@pytest.mark.parametrize("extra", [{"root": "/private"}, {"source": "M2"}, {"selection": {"root_id": "JOB-1"}}])
def test_caller_cannot_supply_root_path_or_binding_authority(owner, extra):
    result = run(owner, **extra)
    assert result == workspace.error("invalid_input", 400)
    assert owner["calls"] == []
