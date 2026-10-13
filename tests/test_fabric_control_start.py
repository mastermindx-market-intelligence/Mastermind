"""Real Runtime pin plus inert bridge/owner reservation; no external effects."""
import asyncio
import copy
import dataclasses
import json
import os

import pytest

from control_plane import fabric_control_start as command
from control_plane.executive_worker_broker import PeerCredentials
from integrations.session_bridge.bound_launch_capture import fabric_launch_reservation as reservation
from test_executive_fabric_adapter import _fixture
from test_executive_fabric_bridge_broker import Backend, broker, envelope, execute, start_result


def request():
    value = envelope()
    payload = value["payload"]
    payload["control_start"] = dict(
        schema_version=command.SCHEMA, attempt_id=payload["binding"]["attempt_id"],
        fence_generation=1, pin_version=2, pin_identity_sha256=command.launch_identity(payload),
        lease_expires_at="2099-01-01T00:00:00Z")
    return value


class OriginalOwner(Backend):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.spawns = 0
        self.start_state = "NO_RETAINED_START"

    async def start_owned(self, payload, *, authority):
        authority.require(payload)
        fields = {**payload["binding"],
                  "effective_grant_sha256": payload["binding"]["effective_grant_digest"],
                  "physical_binding_sha256": payload["physical_binding_sha256"],
                  "start_request_sha256": payload["start_request_sha256"]}
        del fields["effective_grant_digest"]
        # This is the actual O_EXCL reservation helper in an inert private dir,
        # not an in-memory 'already started' flag or a new authority database.
        reservation.reserve_bound_log(self.root / (fields["attempt_id"] + ".log"), fields,
                                      run_id=fields["attempt_id"], root_id=fields["root_id"])
        self.spawns += 1
        return start_result(payload)


def test_fresh_control_command_uses_positive_pin_not_status_absence(tmp_path, monkeypatch):
    owner = OriginalOwner(tmp_path)
    original_fstat = os.fstat
    service = broker(tmp_path, monkeypatch, owner)
    # The config fixture's root-owner shim ends at config loading. Reservation
    # exercises real local file metadata, not the reduced config-stat fixture.
    monkeypatch.setattr(os, "fstat", original_fstat)
    assert execute(service, request())["ok"] is True
    assert [op for op, _ in owner.calls] == ["status"] and owner.spawns == 1
    with pytest.raises(Exception, match="EFFECT_UNKNOWN"):
        execute(service, request())
    assert owner.spawns == 1


@pytest.mark.parametrize("damage", [
    lambda p: p["binding"].update(root_id="foreign-root"),
    lambda p: p.update(physical_binding_sha256="8" * 64),
    lambda p: p["control_start"].update(attempt_id="foreign-attempt"),
    lambda p: p["control_start"].update(fence_generation=True),
    lambda p: p["control_start"].update(pin_version=0),
    lambda p: p["control_start"].update(lease_expires_at="2000-01-01T00:00:00Z"),
    lambda p: p["control_start"].update(lease_token="forbidden-opaque-token"),
])
def test_changed_or_expired_owner_command_never_reaches_reservation(tmp_path, monkeypatch, damage):
    owner = OriginalOwner(tmp_path)
    service = broker(tmp_path, monkeypatch, owner)
    value = request(); damage(value["payload"])
    with pytest.raises(Exception):
        execute(service, value)
    assert owner.spawns == 0 and owner.calls == []
    assert not (tmp_path / "attempt-1.log").exists()


def test_json_command_alone_is_not_internal_authority():
    payload = request()["payload"]
    with pytest.raises(command.ControlStartRefused):
        command.authorize_control_command(payload, peer=PeerCredentials(uid=501, gid=501))
    authorized = command.authorize_control_command(payload, peer=PeerCredentials(uid=450, gid=450))
    with pytest.raises(command.ControlStartRefused):
        dataclasses.replace(authorized, _peer_verified=None).require(payload)
    with pytest.raises(command.ControlStartRefused):
        authorized.require(payload, now=authorized.expires_at)
    altered = copy.deepcopy(payload); altered["launch_spec"]["prompt"] = "other task"
    with pytest.raises(command.ControlStartRefused):
        authorized.require(altered)


def test_owner_without_concrete_start_cannot_fall_back_to_status_or_generic_execute(tmp_path, monkeypatch):
    owner = Backend()
    owner.start_owned = None
    with pytest.raises(Exception, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), request())
    assert owner.calls == []


def test_real_runtime_pin_is_projected_once_without_private_lease_token(tmp_path, monkeypatch):
    class Capture:
        def __init__(self): self.payloads = []
        async def request(self, operation, payload, **kwargs):
            self.payloads.append(copy.deepcopy(payload))
            raise ConnectionResetError("inert lost reply")
    client = Capture()
    runtime, _, lease, adapter, spec, _ = _fixture(tmp_path, monkeypatch, client)
    with pytest.raises(ConnectionResetError):
        asyncio.run(adapter.start(spec, lease=lease))
    assert len(client.payloads) == 1
    sent = client.payloads[0]
    pin = runtime.attempts.get_attempt(spec.run_id)
    assert sent["control_start"] == command.command_from_validated_pin(pin, sent)
    assert lease.lease_token not in json.dumps(sent)
    with pytest.raises(Exception):
        asyncio.run(adapter.start(spec, lease=dataclasses.replace(lease, attempt=pin)))
    assert len(client.payloads) == 1


def test_recovery_status_cannot_carry_a_fresh_command(tmp_path, monkeypatch):
    payload = request()["payload"]
    value = envelope("status", dict(binding=payload["binding"], run_id="attempt-1",
                                    control_start=payload["control_start"]))
    owner = OriginalOwner(tmp_path)
    with pytest.raises(Exception):
        execute(broker(tmp_path, monkeypatch, owner), value)
    assert owner.calls == [] and owner.spawns == 0


def test_no_retained_start_observation_does_not_authorize_legacy_start(tmp_path, monkeypatch):
    owner = OriginalOwner(tmp_path)
    with pytest.raises(Exception, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), envelope())
    assert owner.spawns == 0
    assert [op for op, _ in owner.calls] == ["status"]


def test_actual_unknown_effect_blocks_even_a_fresh_control_command(tmp_path, monkeypatch):
    owner = OriginalOwner(tmp_path)
    owner.start_state = "EFFECT_UNKNOWN"
    with pytest.raises(Exception, match="EFFECT_UNKNOWN"):
        execute(broker(tmp_path, monkeypatch, owner), request())
    assert owner.spawns == 0
    assert [op for op, _ in owner.calls] == ["status"]
