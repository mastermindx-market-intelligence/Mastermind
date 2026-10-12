"""A missing Runtime command may recover an existing result, never launch."""
import copy

import pytest

from test_executive_fabric_bridge_broker import (
    Backend, api, broker, envelope, execute, start_payload, start_result,
)
from test_fabric_control_start import request


@pytest.mark.parametrize("strip_expired_command", [False, True])
def test_stripping_command_cannot_turn_status_into_fresh_start(
        tmp_path, monkeypatch, strip_expired_command):
    value = request()
    owner = Backend()
    service = broker(tmp_path, monkeypatch, owner)
    if strip_expired_command:
        value["payload"]["control_start"]["lease_expires_at"] = "2000-01-01T00:00:00Z"
        with pytest.raises(api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
            execute(service, value)
        assert owner.calls == []
    del value["payload"]["control_start"]
    with pytest.raises(api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        execute(service, value)
    assert [operation for operation, _ in owner.calls] == ["status"]
    assert owner.retained is None


@pytest.mark.parametrize("state", ["NO_RETAINED_START", "NOT_FOUND", "EFFECT_UNKNOWN"])
def test_no_unsealed_observation_selects_a_modifying_operation(tmp_path, monkeypatch, state):
    owner = Backend()
    owner.start_state = state
    with pytest.raises(api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), envelope())
    assert [operation for operation, _ in owner.calls] == ["status"]


def test_exact_unsealed_existing_result_is_read_only_recovery(tmp_path, monkeypatch):
    owner = Backend()
    owner.retained = start_result(start_payload())
    expected = copy.deepcopy(owner.retained)
    assert execute(broker(tmp_path, monkeypatch, owner), envelope())["result"] == expected
    assert [operation for operation, _ in owner.calls] == ["status"]


def test_owned_authority_refusal_never_falls_back_to_generic_start(tmp_path, monkeypatch):
    class RefusingOwner(Backend):
        attempted = 0

        async def start_owned(self, payload, *, authority):
            self.attempted += 1
            # An owner can discover expiry at its actual effect boundary.
            authority.require(payload, now=authority.expires_at)

    owner = RefusingOwner()
    with pytest.raises(api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), request())
    assert owner.attempted == 1
    assert [operation for operation, _ in owner.calls] == ["status"]
    assert owner.retained is None


@pytest.mark.parametrize("field", ["binding", "physical_binding_sha256"])
def test_changed_retained_identity_does_not_create_a_fresh_start(tmp_path, monkeypatch, field):
    owner = Backend()
    owner.retained = start_result(start_payload())
    if field == "binding":
        owner.retained[field]["root_id"] = "different-root"
    else:
        owner.retained[field] = "8" * 64
    with pytest.raises(api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), envelope())
    assert [operation for operation, _ in owner.calls] == ["status"]
