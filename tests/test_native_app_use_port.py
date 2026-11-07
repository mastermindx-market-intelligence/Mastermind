"""Adversarial native action tests using the real Workbench artifact store."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import dataclasses
import os

import pytest

from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding, adopt_artifact_store,
)
from integrations.workbench_action_mcp.contracts import ActionCaller, ActionScope, ProjectActionBinding
from integrations.workbench_app_use.contracts import (
    AppUseRefused, NativeAppGrant, NativeDispatchUnknown, NativeRefCodec, NativeTarget, MAX_OBSERVATION_AGE_MS,
)
from integrations.workbench_app_use.native_port import NativeAppPort

TARGET = NativeTarget("com.mastermind.probe", 120, "179387650000000012", 7)
COMMAND = {"action": "click_element", "arguments": {"element_id": "element-1"}}


class Provider:
    session_ref = "c" * 64
    carrier = "peekaboo-local"
    qualified_actions = frozenset({"click_element", "type_text", "press_key"})
    def __init__(self):
        self.calls = 0
        self.reads = 0
        self.target_valid = True
        self.error = None
    def validate_session(self):
        pass
    def permissions(self):
        return {"observation_ready": True}
    def applications(self):
        return {"applications": [
            {**{k: v for k, v in TARGET.wire().items() if k != "window_id"}, "name": "Probe"},
            {"bundle_id": "com.private.other", "pid": 900,
             "process_start_identity_decimal": "1", "name": "Private"}],
            "inventory_complete": True}
    def windows(self, **application):
        return {"windows": [{"target": TARGET.wire(), "title": "Same title"}]}
    def validate_target(self, target):
        if not self.target_valid or target != TARGET:
            raise AppUseRefused("NATIVE_PROCESS_CHANGED")
    def observe(self, target):
        self.validate_target(target)
        self.reads += 1
        return {"snapshot_id": "snapshot-1", "content": {"ui_elements": [
            {"id": "element-1", "role": "AXButton", "title": "Probe"}]}}
    def dispatch(self, target, snapshot, command):
        self.calls += 1
        if self.error:
            raise self.error
        return {"native_acknowledged": True, "carrier": self.carrier,
                "native_result_sha256": "d" * 64, "business_outcome_verified": False}


@pytest.fixture
def setup(tmp_path):
    root, artifacts = tmp_path / "root", tmp_path / "artifacts"
    root.mkdir(mode=0o700); artifacts.mkdir(mode=0o700)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    store_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    root_stat = os.fstat(root_fd)
    clock = [100000]
    caller = ActionCaller("a" * 64, "client:1", "native:test", ("workbench.action",), 100000)
    scope = ActionScope(root_fd, root_stat.st_dev, root_stat.st_ino,
        "context:1", "responsibility:1", "operation:1", "owner:1", "generation:1",
        ("probe.txt",), 900000)
    binding = ProjectActionBinding(caller, "project:1", scope)
    grant = NativeAppGrant("mcp:" + "b" * 64, "f" * 64, "boot:1", "c" * 64,
        scope.generation, (TARGET.bundle_id,), ("click_element", "type_text", "press_key"), 900000, (TARGET,))
    state = {"live": True, "binding": binding, "grant": grant, "lock_hook": lambda: None}
    @contextmanager
    def lock():
        state["lock_hook"]()
        yield
    provider = Provider()
    port = NativeAppPort(
        resolve_binding=lambda c, p: state["binding"] if state["live"] else None,
        resolve_recovery_binding=lambda c, p: state["binding"],
        resolve_grant=lambda b: state["grant"], clock_ms=lambda: clock[0],
        action_token_key=b"k" * 32, artifact_store=adopt_artifact_store(store_fd),
        host_binding=ActionHostBinding("f" * 64, "boot:1"), provider=provider,
        desktop_lock=lock)
    yield port, provider, caller, state, clock, artifacts
    os.close(root_fd); os.close(store_fd)


def prepare(setup, value=COMMAND):
    port, _, caller, _, _, _ = setup
    observation = port.observe(caller, project_ref="project:1", target=TARGET.wire())
    return port.prepare(caller, project_ref="project:1",
        observation_ref=observation["observation_ref"], native_command=value)["action_ref"]


def run(setup, ref):
    return setup[0].run(setup[2], project_ref="project:1", action_ref=ref)


def test_inventory_is_grant_scoped(setup):
    value = setup[0].inventory(setup[2], project_ref="project:1")
    assert [app["bundle_id"] for app in value["applications"]] == [TARGET.bundle_id]
    assert not value["physical_input_exclusion_proven"]


def test_duplicate_delivery_executes_once_and_is_not_business_acceptance(setup):
    ref = prepare(setup)
    first = run(setup, ref)
    second = run(setup, ref)
    assert first == second
    assert first["effect_state"] == "APPLIED"
    assert first["business_outcome_verified"] is False
    assert first["replay_permitted"] is False
    assert setup[1].calls == 1


def test_ambiguous_reply_is_never_replayed(setup):
    ref = prepare(setup)
    setup[1].error = NativeDispatchUnknown("reply lost after click")
    first = run(setup, ref)
    setup[1].error = None
    second = run(setup, ref)
    assert first == second
    assert second["effect_state"] == "EFFECT_UNKNOWN"
    assert setup[1].calls == 1


def test_expired_snapshot_cannot_dispatch_but_can_reconcile(setup):
    ref = prepare(setup)
    setup[4][0] += MAX_OBSERVATION_AGE_MS + 1000
    with pytest.raises(AppUseRefused, match="STALE"):
        run(setup, ref)
    assert setup[1].calls == 0
    result = setup[0].reconcile(setup[2], project_ref="project:1", action_ref=ref)
    assert result["effect_state"] == "EFFECT_UNKNOWN"
    assert result["evidence_status"] == "absent"
    assert result["replay_permitted"] is False


def test_completed_receipt_survives_observation_expiry_and_native_revocation(setup):
    ref = prepare(setup)
    result = run(setup, ref)
    setup[4][0] += MAX_OBSERVATION_AGE_MS + 1000
    setup[3]["live"] = False
    assert run(setup, ref) == result
    assert setup[1].calls == 1


@pytest.mark.parametrize("changed", ["process", "authority", "session", "scope"])
def test_exact_binding_change_blocks_dispatch(setup, changed):
    ref = prepare(setup)
    if changed == "process":
        setup[1].target_valid = False
    elif changed == "session":
        setup[1].session_ref = "e" * 64
    elif changed == "scope":
        binding = setup[3]["binding"]
        setup[3]["binding"] = dataclasses.replace(binding,
            scope=dataclasses.replace(binding.scope, generation="generation:2"))
    else:
        setup[3]["grant"] = dataclasses.replace(setup[3]["grant"], actions=())
    with pytest.raises(AppUseRefused):
        run(setup, ref)
    assert setup[1].calls == 0


def test_revocation_while_waiting_for_desktop_is_checked(setup):
    ref = prepare(setup)
    setup[3]["lock_hook"] = lambda: setup[3].update(live=False)
    with pytest.raises(AppUseRefused, match="ADMISSION"):
        run(setup, ref)
    assert setup[1].calls == 0


def test_expiry_during_target_validation_blocks_dispatch(setup):
    ref = prepare(setup)
    original = setup[1].validate_target
    def expire(target):
        original(target)
        setup[4][0] += MAX_OBSERVATION_AGE_MS + 1000
    setup[1].validate_target = expire
    with pytest.raises(AppUseRefused, match="STALE"):
        run(setup, ref)
    assert setup[1].calls == 0


def test_predispatch_refusal_is_recorded_and_not_retried(setup):
    ref = prepare(setup)
    setup[1].error = AppUseRefused("binary changed before spawn")
    first = run(setup, ref)
    setup[1].error = None
    assert first["effect_state"] == "NOT_APPLIED"
    assert run(setup, ref) == first
    assert setup[1].calls == 1


def test_result_write_failure_leaves_original_pending_claim(setup, monkeypatch):
    import integrations.workbench_app_use.native_port as module
    from integrations.workbench_action_mcp.action_artifacts import ActionArtifactUncertain
    ref = prepare(setup)
    def fail(*args, **kwargs):
        raise ActionArtifactUncertain("durability unconfirmed")
    monkeypatch.setattr(module, "finalize_action", fail)
    assert run(setup, ref)["effect_state"] == "EFFECT_UNKNOWN"
    assert run(setup, ref)["effect_state"] == "EFFECT_UNKNOWN"
    assert setup[1].calls == 1


@pytest.mark.parametrize("text", ["hello\nsubmit", "x\tsecret", "x\r", "\x00"])
def test_text_cannot_smuggle_keypresses(setup, text):
    with pytest.raises(AppUseRefused, match="PLAIN_TEXT"):
        prepare(setup, {"action": "type_text", "arguments": {"text": text}})
    assert setup[1].calls == 0


def test_cross_purpose_or_tampered_token_refuses(setup):
    ref = prepare(setup)
    corrupt = ("A" if ref[0] != "A" else "B") + ref[1:]
    with pytest.raises(AppUseRefused):
        run(setup, corrupt)
    with pytest.raises(AppUseRefused, match="PURPOSE"):
        NativeRefCodec(b"k" * 32).decode(ref, kind="observation", now_ms=setup[4][0])


def test_paper_and_native_use_the_same_existing_mutex(setup, tmp_path):
    from integrations.paper_desktop.bridge import desktop_lock, Refusal
    lock_root = tmp_path / "paper-lock"
    setup[0]._lock = lambda: desktop_lock(lock_root, wait_seconds=0)
    ref = prepare(setup)
    with desktop_lock(lock_root, wait_seconds=0):
        with pytest.raises(Refusal, match="DESKTOP_BUSY"):
            run(setup, ref)
    assert setup[1].calls == 0


def test_decimal_process_identity_is_never_reduced_to_float(setup):
    value = setup[0].observe(setup[2], project_ref="project:1", target=TARGET.wire())
    assert value["target"]["process_start_identity_decimal"] == "179387650000000012"


def test_application_read_grant_does_not_authorize_another_window(setup):
    # Same application/process, but the owner granted a different window.
    setup[3]["grant"] = dataclasses.replace(setup[3]["grant"],
        targets=(dataclasses.replace(TARGET, window_id=8),))
    with pytest.raises(AppUseRefused, match="WINDOW_NOT_GRANTED"):
        prepare(setup)
    assert setup[1].calls == 0
