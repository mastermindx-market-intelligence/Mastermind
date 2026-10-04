"""Native Codex stays a gated view of incumbent Runtime/Dialogue owners."""
from __future__ import annotations

import asyncio
import dataclasses
import plistlib
from pathlib import Path

import pytest

from integrations.session_bridge.runtime_owner import (
    RuntimeCodexTargetProjector, RuntimeExecutiveReplyBindingResolver,
)
from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_owner import Reads, projector
from tests.test_workspace_agent_runtime_binding import target


def test_codex_view_preserves_exact_fabric_binding_and_hides_native_handles():
    base, _ = projector()
    view = RuntimeCodexTargetProjector(base, owner_configured=lambda: True)
    fabric = base.list_targets()[0]
    public, = view.project()
    assert public["target_ref"] == fabric.target_ref.replace("fabric_attempt:", "codex:", 1)
    binding = RuntimeExecutiveReplyBindingResolver(view).resolve(public["target_ref"])
    assert dataclasses.replace(binding, target_ref=fabric.target_ref) == fabric.reply_binding()
    assert binding.continuation_operation_key == public["continuation_operation_key"]
    assert binding.continuation_operation_key != fabric.reply_binding().continuation_operation_key
    assert set(public) == {"target_ref", "kind", "generation", "addressable", "continuation_operation_key"}
    assert public["kind"] == "codex"
    assert "provider-session" not in repr(public)


@pytest.mark.parametrize("changes", [
    {"harness_provider": "anthropic-claude"},
    {"harness_owner_seat": "ceo"},
])
def test_codex_view_omits_other_providers_and_seats(changes):
    class Other(Reads):
        def target(self, operation):
            return target(**changes)
    base, _ = projector(Other())
    view = RuntimeCodexTargetProjector(base, owner_configured=lambda: True)
    assert view.project() == []
    ref = base.list_targets()[0].target_ref.replace("fabric_attempt:", "codex:", 1)
    with pytest.raises(BridgeError, match="no longer current"):
        view.resolve(ref)


@pytest.mark.parametrize("state", [None, False, 1, "true"])
def test_codex_gate_is_explicit_boolean_and_fabric_remains_visible(state):
    base, _ = projector()
    view = RuntimeCodexTargetProjector(base, owner_configured=lambda: state)
    assert view.project() == []
    assert len(base.project()) == 1
    with pytest.raises(BridgeError):
        view.resolve("codex:" + "a" * 64)


def test_codex_gate_failure_and_mid_read_revocation_fail_closed():
    base, _ = projector()
    def broken():
        raise OSError("owner unavailable")
    assert RuntimeCodexTargetProjector(base, owner_configured=broken).project() == []
    answers = iter([True, False])
    assert RuntimeCodexTargetProjector(base, owner_configured=lambda: next(answers)).project() == []
    answers = iter([True, False])
    ref = base.list_targets()[0].target_ref.replace("fabric_attempt:", "codex:", 1)
    with pytest.raises(BridgeError):
        RuntimeCodexTargetProjector(base, owner_configured=lambda: next(answers)).resolve(ref)


@pytest.mark.parametrize("change", [
    {"harness_generation_number": 8},
    {"harness_provider": "anthropic-claude"},
    {"harness_owner_seat": "ceo"},
    {"fence_generation": 9},
])
def test_codex_list_then_current_owner_drift_refuses_original_reference(change):
    class Moving(Reads):
        current = {}
        def target(self, operation):
            return target(**self.current)
    reads = Moving()
    base, _ = projector(reads)
    view = RuntimeCodexTargetProjector(base, owner_configured=lambda: True)
    ref = view.project()[0]["target_ref"]
    reads.current = change
    with pytest.raises(BridgeError) as error:
        view.resolve(ref)
    assert error.value.code == "native_target_stale"


@pytest.mark.parametrize("ref", ["codex:latest", "fabric_attempt:" + "a"*64, "codex:" + "A"*64])
def test_codex_resolve_rejects_noncanonical_references(ref):
    base, _ = projector()
    with pytest.raises(BridgeError):
        RuntimeCodexTargetProjector(base, owner_configured=lambda: True).resolve(ref)


def test_a2_public_capability_uses_exact_existing_owner_metadata(monkeypatch):
    from ops.executive_os import a2_agent_relay_enrollment as owner
    sha = "a" * 40
    raw = owner.render_plist(bot_user_id="U0BST4WG996", release_sha=sha, w3c_enabled=True)
    reads = []
    def read(path, **metadata):
        reads.append((path, metadata))
        return raw
    monkeypatch.setattr(owner, "_read_exact", read)
    assert owner.w3c_plist_configured(release_sha=sha) is True
    assert reads == [(owner.PLIST_PATH, {"uid": 0, "gid": 0, "mode": 0o644})]
    assert owner.w3c_plist_configured(release_sha="b" * 40) is False


@pytest.mark.parametrize("fault", [
    "missing", "metadata", "not_w3c", "wrong_socket", "duplicate_bot", "extra_argument", "malformed",
])
def test_a2_public_capability_refuses_changed_or_unreadable_artifact(monkeypatch, fault):
    from ops.executive_os import a2_agent_relay_enrollment as owner
    sha = "a" * 40
    raw = owner.render_plist(bot_user_id="U0BST4WG996", release_sha=sha, w3c_enabled=fault != "not_w3c")
    doc = plistlib.loads(raw)
    args = doc["ProgramArguments"]
    if fault == "wrong_socket":
        args[args.index("--socket-path") + 1] = "/tmp/other.sock"
    if fault == "duplicate_bot":
        args.extend(["--bot-user-id", "U0BST4WG996"])
    if fault == "extra_argument":
        args.append("--unreviewed")
    raw = plistlib.dumps(doc, fmt=plistlib.FMT_XML, sort_keys=False)
    if fault == "malformed":
        raw = b"not a plist"
    def read(*a, **k):
        if fault in {"missing", "metadata"}:
            raise owner.A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")
        return raw
    monkeypatch.setattr(owner, "_read_exact", read)
    assert owner.w3c_plist_configured(release_sha=sha) is False


@pytest.mark.parametrize("revoke_on_read", [False, True])
def test_installed_codex_send_uses_same_dialogue_writer_without_provider_attention(tmp_path, monkeypatch, revoke_on_read):
    from types import SimpleNamespace
    from integrations.session_bridge import runtime_return
    monkeypatch.setattr(runtime_return, "time", SimpleNamespace(time=lambda: 1791000100))
    from tests.test_company_consultation_target_resolution import _seed
    from tests.test_session_bridge_installed import principal_frame
    from integrations.session_bridge import dialogue_reply, installed
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector

    seed = _seed(tmp_path, monkeypatch, physical=True, root_source=True)
    base = RuntimeFabricTargetProjector(seed.runtime)
    view = RuntimeCodexTargetProjector(base, owner_configured=lambda: True)
    public = view.project()[0]
    binding = view.resolve(public["target_ref"]).reply_binding()
    worker_result = build_message_v2({
        "schema": MESSAGE_SCHEMA_V2, "message_key": binding.reply_to_message_key,
        "message_type": "RESULT", "work_ref": binding.work_ref,
        "commission_ref": dict(binding.commission_ref), "session_ref": binding.session_ref,
        "actor_ref": dict(binding.current_writer), "reply_to_message_key": None,
        "applies_to": dict(binding.applies_to), "summary": "Bounded fixture result",
        "body": {"status": "PASS", "result": "Fixture only"},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-09-30T19:00:00Z",
    })
    calls, committed = [], []
    async def relay(path, request):
        calls.append(request)
        if request["operation"] == "read_thread":
            if revoke_on_read:
                gate[0] = False
            messages = [{"message": worker_result, "primary_ts": "1787896129.000001", "duplicate_timestamps": []}]
            messages.extend({"message": msg, "primary_ts": "1787896130.000001", "duplicate_timestamps": []}
                            for msg in committed)
            return {"ok": True, "result": {"thread_ts": binding.thread_ts, "messages": messages,
                    "historical_messages": [], "ineligible_count": 0, "mutated_count": 0}}
        assert request["operation"] == "send_message"
        message = request["args"]["message"]
        committed.append(message)
        return {"ok": True, "result": {"action": "POSTED", "message_key": message["message_key"],
                "fingerprint": message["fingerprint"]}}
    writer_type = dialogue_reply.AgentDialogueContinueWriter
    monkeypatch.setattr(dialogue_reply, "AgentDialogueContinueWriter",
                        lambda resolver, **kwargs: writer_type(resolver, service_call=relay, **kwargs))
    returns_type = runtime_return.RuntimeSessionReturn
    monkeypatch.setattr(runtime_return, "RuntimeSessionReturn",
                        lambda *args, **kwargs: returns_type(*args, service_call=relay, **kwargs))
    gate = [True]
    owner = installed.build_runtime_session_bridge(
        seed.runtime, dialogue_socket_path=Path("/tmp/fixture-relay.sock"),
        codex_owner_configured=lambda: gate[0])
    async def call(tool, args):
        return await owner.handle_frame({"schema": installed.PRIVATE_SCHEMA, "tool": tool,
                "principal": principal_frame(), "arguments": args})
    async def run():
        result = await call("session_targets", {"kind": "codex"})
        assert len(result["data"]) == 2
        args = {"target_ref": public["target_ref"], "operation_key": public["continuation_operation_key"],
                "instruction": "Inspect one bounded finding.", "stop_condition": "Return the finding."}
        result = await call("session_send", args)
        if revoke_on_read:
            assert result["error"]["code"] == "binding_unavailable"
            assert [call["operation"] for call in calls] == ["read_thread"]
            assert committed == []
            return
        assert result["ok"] is True, result
        assert result["data"]["carrier"]["reply_committed"] is True
        assert result["data"]["read_ref"].startswith("session-reply-")
        assert result["data"]["attention"] == {"state": "UNAVAILABLE"}
        assert committed[0]["message_type"] == "CONTINUE"
        assert committed[0]["reply_to_message_key"] == binding.reply_to_message_key
        result = await call("session_send", args)
        assert result["ok"] is True, result
        assert result["data"]["carrier"]["action"] == "DUPLICATE"
        assert len(committed) == 1
        before = len(calls)
        gate[0] = False
        assert (await call("session_targets", {"kind": "codex"}))["data"] == []
        result = await call("session_send", args)
        # An exact committed retry is a read, even after owner disarm. It
        # cannot revive the target, submit another CONTINUE or repeat attention.
        assert result["ok"] is True, result
        assert result["data"]["carrier"]["action"] == "DUPLICATE"
        assert result["data"]["attention"] == {"state": "EFFECT_UNKNOWN"}
        assert len(calls) == before + 1
        assert len(committed) == 1
    asyncio.run(run())




@pytest.mark.parametrize("bridge_armed,relay_w3c", [(False, False), (False, True), (True, False), (True, True)])
def test_actual_factory_requires_both_owners_and_a_serving_listener(
    tmp_path, short_socket_root, monkeypatch, bridge_armed, relay_w3c
):
    import json
    from tests.test_company_consultation_target_resolution import _seed
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_session_bridge_installed import principal_frame
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from integrations.session_bridge.installed import PRIVATE_SCHEMA
    from ops.executive_os import a2_agent_relay_enrollment as enrollment

    _seed(tmp_path, monkeypatch, physical=True, root_source=True)

    async def run():
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                                   profile=WEB_CEO_SESSIONS_PROFILE) as (service, raw, _):
            await service.start()
            # Only capability setup is a fixture. Target discovery and private
            # ingress use the actual service, Runtime and owned binding source.
            from scripts import executive_os_phase1c as cli
            from control_plane.wake_ledger import WakeRetryPolicy
            # Exercise the actual on-disk normalization seam, mocking only the
            # root-owned file read/current UID for this unprivileged fixture.
            import os
            document = json.loads(json.dumps(raw, default=os.fspath))
            document.update({
                "dialogue_observation_socket_path": "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
                "dialogue_observation_launchd_socket_name": "DialogueObservation",
                "dialogue_observation_peer_uid": 457,
                "dialogue_bridge_armed": bridge_armed,
                "dialogue_wake_retry_policy": {
                    "max_delivery_attempts": 1, "retry_cooldown_s": 15, "accepted_ttl_s": 300,
                    "target_unavailable_backoff_s": 60, "reenable_on_binding_rotation": True,
                    "armed": bridge_armed,
                },
            })
            with monkeypatch.context() as loading:
                loading.setattr(cli, "_private_json", lambda *a, **k: document)
                loading.setattr(cli.os, "geteuid", lambda: document["control_uid"])
                loaded = cli.load_control_config(tmp_path / "control-fixture.json")
            assert isinstance(loaded["dialogue_wake_retry_policy"], WakeRetryPolicy)
            raw["dialogue_bridge_armed"] = loaded["dialogue_bridge_armed"]
            raw["dialogue_wake_retry_policy"] = loaded["dialogue_wake_retry_policy"]
            plist = enrollment.render_plist(bot_user_id="U0BST4WG996",
                    release_sha=raw["proof_base_sha"], w3c_enabled=relay_w3c)
            monkeypatch.setattr(enrollment, "_read_exact", lambda *a, **k: plist)
            listener = await asyncio.start_unix_server(
                lambda reader, writer: writer.close(), path=short_socket_root / "obs.sock")
            service._dialogue_observation_server = listener

            async def targets(kind):
                response = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]),
                    (json.dumps({"schema": PRIVATE_SCHEMA, "tool": "session_targets",
                                "principal": principal_frame(), "arguments": {"kind": kind}}) + "\n").encode())
                assert response["result"]["ok"] is True, response
                return response["result"]["data"]

            try:
                assert len(await targets("fabric_attempt")) == 2
                assert len(await targets("codex")) == (2 if bridge_armed and relay_w3c else 0)
                listener.close()
                await listener.wait_closed()
                assert await targets("codex") == []
                assert len(await targets("fabric_attempt")) == 2
            finally:
                listener.close()
                await listener.wait_closed()
                service._dialogue_observation_server = None
    asyncio.run(run())
