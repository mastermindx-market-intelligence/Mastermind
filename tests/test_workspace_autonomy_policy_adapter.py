"""Real temporary Runtime/CCR owners; no installed host or provider effects."""
import asyncio
from dataclasses import replace

import pytest

from common import workspace_autonomy_read_contract as wire
from control_plane import executive_coo_policy as policy_owner
from control_plane import workspace_autonomy_policy_adapter as adapter
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.workspace_autonomy_policy_adapter import read_autonomy_policy
from tests.test_workspace_admitted_plan_read import owner_fixture, request, service


def authorizer():
    state = {"allowed": True, "digest": "a" * 64}
    def authorize(_):
        return state["allowed"]
    authorize.binding_digest = lambda _: state["digest"]
    return authorize, state


def frame(owner):
    value = request(owner)
    value.update(schema=wire.FRAME_SCHEMA, operation="autonomy")
    return value


def test_real_selected_admission_reuses_one_closed_runtime_acquisition(tmp_path):
    with owner_fixture(tmp_path) as owner:
        authorize, _ = authorizer()
        existing = service(owner, authorize)
        before = owner["namespace"].entries
        result = asyncio.run(read_autonomy_policy(existing, frame(owner)))
        assert result["ok"] and result["result"]["availability"] == "AVAILABLE"
        assert result["result"]["selection"] == owner["selection"]
        assert result["result"]["policy"]["scope"] == "ADMITTED_ROOT"
        assert result["result"]["policy"]["limits"] == CooCyclePolicy.load().to_dict()
        assert owner["namespace"].entries == before + 1 == owner["namespace"].exits


def test_denial_and_foreign_root_prevent_runtime_access(tmp_path):
    with owner_fixture(tmp_path) as owner:
        authorize, state = authorizer()
        existing = service(owner, authorize)
        before = owner["namespace"].entries
        state["allowed"] = False
        assert asyncio.run(read_autonomy_policy(existing, frame(owner)))["status"] == 403
        state["allowed"] = True
        value = frame(owner)
        value["selection"]["root_job_id"] = "JOB-999999"
        assert asyncio.run(read_autonomy_policy(existing, value))["status"] == 404
        assert owner["namespace"].entries == before


@pytest.mark.parametrize("change", ["revoked", "permission_digest", "authorizer_replaced"])
def test_policy_read_cannot_outlive_the_original_permission(tmp_path, monkeypatch, change):
    with owner_fixture(tmp_path) as owner:
        authorize, state = authorizer()
        existing = service(owner, authorize)
        original = CooCyclePolicy.for_digest
        def read(digest):
            policy = original(digest)
            if change == "revoked": state["allowed"] = False
            elif change == "permission_digest": state["digest"] = "b" * 64
            else: existing.authorize = authorizer()[0]
            return policy
        monkeypatch.setattr(CooCyclePolicy, "for_digest", read)
        result = asyncio.run(read_autonomy_policy(existing, frame(owner)))
        assert result["ok"] is False and result["status"] == 403


def test_source_publication_change_discards_policy(tmp_path):
    with owner_fixture(tmp_path) as owner:
        authorize, _ = authorizer()
        existing = service(owner, authorize)
        original = existing.cache.snapshot
        calls = [0]
        def sample():
            value = original()
            calls[0] += 1
            return replace(value, publication=value.publication + 1) if calls[0] == 4 else value
        existing.cache.snapshot = sample
        result = asyncio.run(read_autonomy_policy(existing, frame(owner)))
        assert result["result"]["availability"] == "UNAVAILABLE"
        assert result["result"]["reason_codes"] == ["SOURCE_CHANGED"]


def test_policy_source_move_and_private_failures_are_closed(tmp_path, monkeypatch):
    with owner_fixture(tmp_path) as owner:
        authorize, _ = authorizer()
        existing = service(owner, authorize)
        # Move the actual policy source across composition, independently of
        # how many earlier admission reads resolve this same policy owner.
        path = tmp_path / "policy-source.yml"
        path.write_bytes(policy_owner._POLICY_PATH.read_bytes())
        monkeypatch.setattr(policy_owner, "_POLICY_PATH", path)
        original = adapter.compose_autonomy_policy_read
        observed = []
        def changed(body, policy):
            result = original(body, policy)
            observed.append(policy)
            path.write_bytes(path.read_bytes() + b"\n")
            return result
        monkeypatch.setattr(adapter, "compose_autonomy_policy_read", changed)
        assert asyncio.run(read_autonomy_policy(existing, frame(owner)))["result"]["reason_codes"] == ["SOURCE_CHANGED"]
        assert len(observed) == 1
        after = CooCyclePolicy.load()
        assert after.policy_sha256 == observed[0].policy_sha256
        assert after.source_sha256 != observed[0].source_sha256
        def fail(_): raise RuntimeError("private host path must never be released")
        monkeypatch.setattr(CooCyclePolicy, "for_digest", fail)
        result = asyncio.run(read_autonomy_policy(existing, frame(owner)))
        assert result["result"]["reason_codes"] == ["SOURCE_UNAVAILABLE"]
        assert "private host" not in str(result)
