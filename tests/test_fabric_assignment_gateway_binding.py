"""Coordinator integration falsifiers; inert receipts, no enrolled realm proof."""
import asyncio
import copy
import stat

import pytest

from control_plane import broker_assignment_seal as seals
from ops.executive_os import remote_assignment_control as control
from tests import test_remote_assignment_control as roots
from tests import test_remote_gateway_fabric_target as gateway_fixture
from tests import test_fabric_assignment_transport as assignment
from tests import test_executive_fabric_bridge_broker as bridge_fixture


def test_fabric_seal_requires_control_binding_before_forwarding(tmp_path):
    with pytest.raises(ValueError, match="Control binding"):
        gateway_fixture._config(tmp_path, broker_target="attended-fabric",
            expected_broker_peer_uid=1001, allowed_operations={"assignment-seal"})


def _fabric_fixture(tmp_path, monkeypatch):
    binding, paths, snapshot, request, calls, raw_broker = roots.fixture(tmp_path)
    roots.mock_principal(monkeypatch, binding)
    ref = bridge_fixture.start_result(bridge_fixture.start_payload())["process_ref"]
    ref["run_id"] = request["attempt_id"]
    ref["effective_uid"] = ref["real_uid"] = binding.worker_uid
    ref["effective_gid"] = ref["real_gid"] = binding.worker_gid
    snapshot["process_ref"] = copy.deepcopy(ref)
    request["broker_request"] = {
        "binding": {"root_id": "original-root", "job_id": request["job_id"],
            "attempt_id": request["attempt_id"], "effective_grant_digest": "a" * 64,
            "commission_sha256": "b" * 64},
        "physical_binding_sha256": "c" * 64, "run_id": request["attempt_id"],
        "worker_id": request["worker_id"], "process_ref": ref}
    common = {"adapter_id": "attended-fabric",
        "binding": copy.deepcopy(request["broker_request"]["binding"]),
        "physical_binding_sha256": "c" * 64}
    seen = []
    async def broker(op, payload):
        seen.append((op, copy.deepcopy(payload)))
        original = request["broker_request"]
        assert all(payload[key] == original[key] for key in original)
        result = await raw_broker(op, {key: payload[key] for key in
            (("run_id",) if op.endswith("prepare") else ("run_id", "snapshot_sha256", "seal"))})
        return {**common, **(result if op.endswith("prepare") else {"observation": result})}
    return binding, paths, snapshot, request, common, seen, broker


@pytest.mark.parametrize("damage", ["root", "route", "grant", "process", "snapshot_digest"])
def test_fabric_foreign_prepare_refuses_before_control_chmod(tmp_path, monkeypatch, damage):
    binding, paths, snapshot, request, common, seen, original = _fabric_fixture(tmp_path, monkeypatch)
    async def broker(op, payload):
        result = await original(op, payload)
        if op.endswith("prepare"):
            if damage == "root":
                result["binding"] = {**result["binding"], "root_id": "other-root"}
            elif damage == "route": result["physical_binding_sha256"] = "d" * 64
            elif damage == "grant":
                result["snapshot"]["effective_grant_digest"] = "e" * 64
                result["snapshot_sha256"] = seals.digest(result["snapshot"])
            elif damage == "process":
                result["snapshot"]["process_ref"]["pid"] += 1
                result["snapshot_sha256"] = seals.digest(result["snapshot"])
            else: result["snapshot_sha256"] = "f" * 64
        return result
    with pytest.raises(control.RemoteAssignmentError):
        asyncio.run(control.seal_original_assignment(binding, request, broker, fabric_target=True))
    assert [op for op, _ in seen] == ["assignment-seal-prepare"]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o770 for path in paths.values())


def test_fabric_control_codec_preserves_full_binding_and_never_finalizes(tmp_path, monkeypatch):
    binding, paths, _, request, common, seen, broker = _fabric_fixture(tmp_path, monkeypatch)
    result = asyncio.run(control.seal_original_assignment(binding, request, broker, fabric_target=True))
    assert {key: result[key] for key in common} == common
    assert result["observation"]["snapshot"]["process_ref"] == request["broker_request"]["process_ref"]
    assert [op for op, _ in seen] == ["assignment-seal-prepare", "assignment-seal-commit"]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in paths.values())


class PreparedBackend(assignment.Backend):
    async def execute(self, op, payload):
        if op not in {"assignment-seal-prepare", "assignment-seal-commit"}:
            return await super().execute(op, payload)
        self.calls.append((op, copy.deepcopy(payload)))
        common = {"adapter_id": "attended-fabric", "binding": payload["binding"],
            "physical_binding_sha256": payload["physical_binding_sha256"]}
        if op.endswith("prepare"):
            return {**common, "snapshot": copy.deepcopy(self.value["snapshot"]),
                "snapshot_sha256": self.value["snapshot_sha256"]}
        return {**common, "observation": copy.deepcopy(self.value)}


def test_bridge_prepare_commit_uses_original_terminal_preflight(tmp_path, monkeypatch):
    backend = PreparedBackend()
    broker = bridge_fixture.broker(tmp_path, monkeypatch, backend)
    payload = assignment.payload(backend.value)
    result = bridge_fixture.execute(broker, bridge_fixture.envelope("assignment-seal-prepare", payload))
    assert result["result"]["snapshot"] == backend.value["snapshot"]
    result = bridge_fixture.execute(broker, bridge_fixture.envelope("assignment-seal-commit", {
        **payload, "snapshot_sha256": backend.value["snapshot_sha256"],
        "seal": backend.value["control_seal"]}))
    assert result["result"]["observation"] == backend.value
    assert [op for op, _ in backend.calls] == ["status", "assignment-seal-prepare", "status", "assignment-seal-commit"]


def test_bridge_commit_refuses_substituted_seal_return(tmp_path, monkeypatch):
    backend = PreparedBackend()
    supplied = copy.deepcopy(backend.value["control_seal"])
    supplied["sealed_at"] = "2026-10-12T01:00:00Z"
    with pytest.raises(bridge_fixture.api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        bridge_fixture.execute(bridge_fixture.broker(tmp_path, monkeypatch, backend),
            bridge_fixture.envelope("assignment-seal-commit", {
                **assignment.payload(backend.value), "snapshot_sha256": backend.value["snapshot_sha256"],
                "seal": supplied}))
