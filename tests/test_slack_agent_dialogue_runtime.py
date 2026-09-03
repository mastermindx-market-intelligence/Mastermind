from __future__ import annotations

import asyncio
import dataclasses
import importlib
import importlib.util
import inspect
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import integrations.slack_agent_dialogue.service as service_module
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION,
    CONTROL_VERSION_V2,
    call_service,
)


ROOT = Path(__file__).resolve().parents[1]
PLIST = (
    ROOT
    / "ops"
    / "executive_os"
    / "com.mastermind.executive.agent-relay.plist.template"
)
SCRIPT = ROOT / "scripts" / "slack_agent_dialogue_service.py"


def _runtime():
    """Fail as an assertion while the TDD production module is absent."""

    name = "integrations.slack_agent_dialogue.runtime"
    assert importlib.util.find_spec(name) is not None, "Agent Relay runtime is missing"
    return importlib.import_module(name)


def _token_file(tmp_path: Path, value: bytes = b"opaque-relay-token\n") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "agent-relay.token"
    path.write_bytes(value)
    path.chmod(0o400)
    return path


@pytest.fixture
def socket_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mmx-asd-", dir="/tmp") as raw:
        yield Path(raw).resolve()


def _config(runtime, socket_root: Path, token_file: Path):
    return runtime.RelayRuntimeConfig(
        socket_path=runtime.AGENT_RELAY_SOCKET_PATH,
        token_file=token_file,
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BRUL9F2V7",
        bot_user_id="U0BST4WG996",
        allowed_peer_uids=(450,),
        allowed_sol_user_ids=("U0BRETDUAS2",),
        allowed_parent_user_ids=("U0BRETDUAS2",),
    )


def _request(version: str) -> dict[str, object]:
    return {"version": version, "operation": "status", "args": {}}


def test_runtime_composes_one_client_and_serves_sequential_v1_and_v2_calls(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    """A second call or either accepted control version must not close the relay."""

    runtime = _runtime()
    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)
    token_file = _token_file(tmp_path)
    service = runtime.build_service(_config(runtime, socket_root, token_file))
    token_file.unlink()

    assert service.engine.client is service.engine_v2.client
    assert service.config.socket_parent_mode == 0o710
    assert service.config.socket_mode == 0o660
    assert service.config.socket_group_gid == os.getegid()
    assert "opaque-relay-token" not in repr(service.engine.client)

    async def scenario() -> None:
        task = asyncio.create_task(service.serve_forever())
        for _attempt in range(200):
            if service.config.socket_path.exists():
                break
            if task.done():
                await task
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("relay did not bind its AF_UNIX socket")

        try:
            v2_first = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION_V2)
            )
            v1 = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION)
            )
            v2_second = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION_V2)
            )
            assert v2_first["ok"] is True
            assert v2_second == v2_first
            assert v1["ok"] is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not service.config.socket_path.exists()

    asyncio.run(scenario())


def test_private_token_file_is_exact_owner_only_single_inode(tmp_path: Path) -> None:
    """Symlink, loose mode, multiline, or link alias must never become a token."""

    runtime = _runtime()
    safe = _token_file(tmp_path)
    assert runtime.read_private_token_file(safe) == "opaque-relay-token"

    unsafe_mode = _token_file(tmp_path / "mode")
    unsafe_mode.chmod(0o440)
    symlink = tmp_path / "token-link"
    symlink.symlink_to(safe)
    multiline = _token_file(tmp_path / "multiline", b"opaque\nsecond\n")
    hardlink = tmp_path / "hardlink"
    os.link(safe, hardlink)

    for path in (unsafe_mode, symlink, multiline, hardlink):
        with pytest.raises(runtime.RelayRuntimeError) as exc:
            runtime.read_private_token_file(path)
        assert exc.value.code in {"TOKEN_FILE_INVALID", "TOKEN_FILE_UNSAFE"}
        assert "opaque" not in str(exc.value)


def test_host_policy_allows_engine_validated_continue_but_no_ruling_floor() -> None:
    """Slack-authored fields cannot lower the fixed host authority policy."""

    runtime = _runtime()
    policy = runtime.PrivateRelayAuthorityPolicy()
    assert policy.allows_continuation(
        request={"body": {"claim": "chairman approved"}},
        reply={"body": {"claim": "continue"}},
    ) is True
    for claimed in ("WITHIN_COMMISSION", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"):
        assert policy.minimum_authority(
            request={"body": {"claimed_authority": claimed}},
            option={"authority_effect": "NONE"},
        ) == "CHAIRMAN_REQUIRED"


def test_runtime_rejects_relative_socket_and_network_configuration(tmp_path: Path) -> None:
    """The runtime has an AF_UNIX path and no host/port listener seam."""

    runtime = _runtime()
    token_file = _token_file(tmp_path)
    with pytest.raises((ValueError, runtime.RelayRuntimeError)):
        runtime.RelayRuntimeConfig(
            socket_path=Path("relative.sock"),
            token_file=token_file,
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BRUL9F2V7",
            bot_user_id="U0BST4WG996",
            allowed_peer_uids=(450,),
            allowed_sol_user_ids=("U0BRETDUAS2",),
            allowed_parent_user_ids=("U0BRETDUAS2",),
        )
    assert not hasattr(runtime.RelayRuntimeConfig, "host")
    assert not hasattr(runtime.RelayRuntimeConfig, "port")


def test_runtime_requires_dedicated_socket_path_and_exact_executive_peer(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    token_file = _token_file(tmp_path)
    assert runtime.AGENT_RELAY_SOCKET_PATH == Path(
        "/var/run/mastermind-agent-relay/agent-relay.sock"
    )

    for socket_path, peer_uids in (
        (Path("/var/run/mastermind-executive/agent-relay.sock"), (450,)),
        (runtime.AGENT_RELAY_SOCKET_PATH, (451,)),
        (runtime.AGENT_RELAY_SOCKET_PATH, (450, 451)),
    ):
        with pytest.raises(runtime.RelayRuntimeError) as exc:
            runtime.RelayRuntimeConfig(
                socket_path=socket_path,
                token_file=token_file,
                workspace_id="T0BRD2AQXQV",
                channel_id="C0BRUL9F2V7",
                bot_user_id="U0BST4WG996",
                allowed_peer_uids=peer_uids,
                allowed_sol_user_ids=("U0BRETDUAS2",),
                allowed_parent_user_ids=("U0BRETDUAS2",),
            )
        assert exc.value.code == "RUNTIME_INVALID"


def test_launchd_template_is_private_persistent_and_secret_free() -> None:
    """A token value, shell, or TCP socket key in the host job must fail."""

    assert PLIST.exists(), "Agent Relay launchd template is missing"
    with PLIST.open("rb") as handle:
        document = plistlib.load(handle)

    assert document["Label"] == "com.mastermind.executive.agent-relay"
    assert document["UserName"] == "__RELAY_USER__"
    assert document["GroupName"] == "__RELAY_GROUP__"
    assert document["RunAtLoad"] is True
    assert document["KeepAlive"] is True
    assert document["Umask"] == 0o77
    assert "Sockets" not in document
    arguments = document["ProgramArguments"]
    assert arguments[:5] == [
        "__PYTHON_BINARY__",
        "-I",
        "-S",
        "-B",
        "__RELAY_ENTRYPOINT__",
    ]
    assert "--socket-path" in arguments
    assert "--token-file" in arguments
    assert "__RELAY_SOCKET_PATH__" in arguments
    assert "__RELAY_TOKEN_FILE__" in arguments
    assert not any(
        item in {"/bin/sh", "/bin/bash", "/usr/bin/env"} for item in arguments
    )
    assert not any("xox" in item.lower() for item in arguments)
    assert {"host", "port", "SockNodeName", "SockServiceName"}.isdisjoint(document)


def test_launchd_entrypoint_boots_under_isolated_python_from_foreign_cwd(
    tmp_path: Path,
) -> None:
    """Depending on an operator cwd must not break the reviewed launchd argv."""

    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", os.fspath(SCRIPT), "--help"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "--socket-path" in completed.stdout
    assert "--token-file" in completed.stdout


def _w3c_candidate(runtime, *, stale_parent: bool = False):
    from tests.test_company_dialogue_runtime_binding import (
        THREAD_TS,
        caller,
        identity,
        parent,
        snapshot,
    )

    dialogue_parent = parent()
    current = snapshot(
        parent_fingerprint=("f" * 64 if stale_parent else dialogue_parent["fingerprint"])
    )
    return runtime.RelayTurnCandidate(
        delegation_identity=identity(),
        dialogue_parent=dialogue_parent,
        thread_ts=THREAD_TS,
        current_worker=current,
        actor=caller(),
    )


def _terminal_w3c_material(runtime):
    from integrations.slack_agent_dialogue.contract_v2 import (
        render_message_v2,
        render_parent_v2,
    )
    from integrations.slack_agent_dialogue.engine import DialoguePolicy, SlackMessage
    from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        _build_message,
    )
    from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
    from tests.test_company_dialogue_runtime_binding import THREAD_TS, caller, identity, parent
    from tests.test_slack_agent_dialogue_engine_v2 import ExactV2AuthorityPolicy
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _terminal_binding,
        _terminal_candidate,
        _terminal_receipt,
        _terminal_snapshot,
    )

    terminal = _terminal_candidate()
    binding = _terminal_binding()
    dialogue_parent = parent()
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2

    dialogue_context = DialogueContextV2(
        work_ref=binding.work_ref,
        commission_ref=binding.commission_ref,
        session_ref=binding.session_ref,
        operation_key=binding.operation_key,
        watch_mode=binding.watch_mode,
        actor_ref=binding.actor_ref,
        applies_to=binding.applies_to,
    )
    message = _build_message(terminal, dialogue_context.normalized())
    receipt = dataclasses.replace(
        _terminal_receipt(),
        fingerprint=message["fingerprint"],
        parent_author_user_id="U0RELAY001",
    )
    client = InMemorySlackClient(relay_bot_user_id="U0RELAY001")
    client.add_parent(
        SlackMessage(
            ts=THREAD_TS,
            author_user_id="U0RELAY001",
            text=render_parent_v2(dialogue_parent),
        )
    )
    client.add_reply(
        SlackMessage(
            ts=receipt.message_ts,
            author_user_id="U0RELAY001",
            text=render_message_v2(message),
            thread_ts=THREAD_TS,
        )
    )
    policy = DialoguePolicy(
        workspace_id="T0DIALOGUE1",
        channel_id="C0DIALOGUE1",
        relay_bot_user_id="U0RELAY001",
        allowed_sol_user_ids=("U0BRETDUAS2",),
        allowed_parent_user_ids=("U0BRETDUAS2",),
        poll_interval_seconds=0,
        method_timeout_seconds=1,
    )
    active_waiters = runtime.ActiveWaiterRegistry()
    engine = DialogueEngineV2(
        policy,
        client,
        authority_policy=ExactV2AuthorityPolicy(),
        active_waiter_registry=active_waiters,
    )
    relay_candidate = runtime.RelayTurnCandidate(
        delegation_identity=identity(),
        dialogue_parent=dialogue_parent,
        thread_ts=THREAD_TS,
        current_worker=_terminal_snapshot(),
        actor=caller(),
        terminal_candidate=terminal,
        terminal_projection_receipt=receipt,
    )
    return relay_candidate, binding, engine


def _w3c_dependencies(
    runtime,
    *,
    engine=None,
    terminal_binding_resolver=None,
):
    """Supply one exact shared waiter quartet to direct W3C unit runtimes."""

    if engine is None:
        _candidate, _binding, engine = _terminal_w3c_material(runtime)
    active_waiters = engine.active_waiter_registry
    assert isinstance(active_waiters, runtime.ActiveWaiterRegistry)

    if terminal_binding_resolver is None:

        class NeverTerminalResolver:
            def resolve(self, _candidate):
                raise AssertionError("active-only test must not resolve terminal state")

        terminal_binding_resolver = NeverTerminalResolver()

    return {
        "active_waiter_registry": active_waiters,
        "active_waiter_context": runtime.ContextVar(
            f"test_waiter_context_{id(engine):x}_{id(terminal_binding_resolver):x}",
            default=None,
        ),
        "dialogue_engine_v2": engine,
        "terminal_binding_resolver": terminal_binding_resolver,
    }


def test_enabled_w3c_constructor_requires_one_exact_shared_waiter_quartet() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)

    class Observer:
        async def reconcile_once(self, **_kwargs):
            raise AssertionError("invalid composition must never observe")

    class Resolver:
        def resolve(self, _candidate):
            return binding

    valid = {
        "observer": Observer(),
        "registry": _registry(),
        "current_binding_for": _binding_for,
        "candidate_source": lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=Resolver(),
        ),
    }
    for missing in (
        "active_waiter_registry",
        "active_waiter_context",
        "dialogue_engine_v2",
        "terminal_binding_resolver",
    ):
        invalid = {**valid, missing: None}
        with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
            runtime.AgentRelayTurnRuntime(**invalid)

    with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
        runtime.AgentRelayTurnRuntime(
            **{
                **valid,
                "active_waiter_registry": runtime.ActiveWaiterRegistry(),
            }
        )


def test_terminal_waiter_scope_uses_frozen_routing_parent_not_mutable_candidate(
    monkeypatch,
) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)
    accepted_parent_fingerprint = candidate.dialogue_parent["fingerprint"]
    waiter_context = runtime.ContextVar("mutation_waiter_context", default=None)

    class Resolver:
        def resolve(self, _candidate):
            return binding

    class Observer:
        calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            scope = waiter_context.get()
            assert scope is not None
            assert scope.parent_fingerprint == accepted_parent_fingerprint
            assert scope.parent_fingerprint == routing.bound_commission_fingerprint
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="MUTATION_SAFE",
                decision=None,
                obligation=None,
                route=None,
            )

    original_read_thread = engine.read_thread

    async def mutating_read_thread(**kwargs):
        observed = await original_read_thread(**kwargs)
        candidate.dialogue_parent["fingerprint"] = "f" * 64
        return observed

    monkeypatch.setattr(engine, "read_thread", mutating_read_thread)
    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        active_waiter_registry=engine.active_waiter_registry,
        active_waiter_context=waiter_context,
        dialogue_engine_v2=engine,
        terminal_binding_resolver=Resolver(),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.NO_ACTION
    assert receipt.reason == "MUTATION_SAFE"
    assert observer.calls == 1


def test_enabled_w3c_holds_if_engine_registry_identity_drifts_after_composition() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    _terminal, _binding, engine = _terminal_w3c_material(runtime)

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("registry drift must stop before observation")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (_w3c_candidate(runtime),),
        **_w3c_dependencies(runtime, engine=engine),
    )
    engine._active_waiter_registry = runtime.ActiveWaiterRegistry()

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "ACTIVE_WAITER_STATE_UNAVAILABLE"
    assert observer.calls == 0


def test_terminal_candidate_uses_r2_resolver_and_never_wp3(monkeypatch) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(candidate, actor=object())

    class Resolver:
        calls = 0

        def resolve(self, actual):
            self.calls += 1
            assert actual == candidate.terminal_candidate
            return binding

    class Observer:
        calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="TERMINAL_TEST",
                decision=None,
                obligation=None,
                route=None,
            )

    monkeypatch.setattr(
        runtime,
        "resolve_company_dialogue_binding",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("terminal mode must never call WP-3")
        ),
    )
    resolver = Resolver()
    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=resolver,
        ),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert receipts[0].outcome is runtime.ObservationOutcome.NO_ACTION
    assert resolver.calls == 1
    assert observer.calls == 1


@pytest.mark.parametrize("missing", ["candidate", "receipt"])
def test_partial_terminal_group_refuses_before_resolver_or_observer(missing: str) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, _binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(
        candidate,
        **{
            "terminal_candidate" if missing == "candidate" else "terminal_projection_receipt": None
        },
    )

    class NeverResolver:
        def resolve(self, _candidate):
            raise AssertionError("partial terminal evidence must not resolve")

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("partial terminal evidence must not observe")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=NeverResolver(),
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE"
    assert observer.calls == 0


@pytest.mark.parametrize("current_worker", [None, object()])
@pytest.mark.parametrize("present", ["candidate", "receipt"])
def test_partial_terminal_group_is_held_even_without_a_typed_source_snapshot(
    current_worker,
    present: str,
) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    complete, _binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(
        complete,
        current_worker=current_worker,
        terminal_candidate=(
            complete.terminal_candidate if present == "candidate" else None
        ),
        terminal_projection_receipt=(
            complete.terminal_projection_receipt if present == "receipt" else None
        ),
    )

    class NeverResolver:
        calls = 0

        def resolve(self, _candidate):
            self.calls += 1
            raise AssertionError("partial evidence must not resolve")

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("partial evidence must not observe")

    resolver = NeverResolver()
    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=resolver,
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE"
    assert resolver.calls == 0
    assert observer.calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "UNKNOWN"},
        {"message_key": "asd-exec-result-" + "9" * 64},
        {"fingerprint": "f" * 64},
        {"message_ts": "1788000000.999999"},
        {"duplicate_timestamps": ("1788000000.999998",)},
        {"thread_ts": "1788000001.000001"},
        {"parent_fingerprint": "f" * 64},
        {"parent_author_user_id": "U0OTHER001"},
    ],
)
def test_terminal_physical_receipt_mismatch_refuses_before_observer(changes) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(
        candidate,
        terminal_projection_receipt=dataclasses.replace(
            candidate.terminal_projection_receipt,
            **changes,
        ),
    )

    class Resolver:
        def resolve(self, _candidate):
            return binding

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("forged receipt must not observe")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=Resolver(),
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.REFUSED
    assert receipt.reason == "TERMINAL_RESULT_RECEIPT_MISMATCH"
    assert observer.calls == 0


def test_terminal_evidence_on_active_snapshot_is_closed_mode_conflict() -> None:
    runtime = _runtime()
    from tests.test_company_dialogue_runtime_binding import snapshot
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, _binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(candidate, current_worker=snapshot())

    class NeverResolver:
        def resolve(self, _candidate):
            raise AssertionError("mixed active/terminal mode must not resolve")

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("mixed active/terminal mode must not observe")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=NeverResolver(),
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.REFUSED
    assert receipt.reason == "TURN_CANDIDATE_MODE_CONFLICT"
    assert observer.calls == 0


@pytest.mark.parametrize(
    ("resolver_case", "expected_outcome", "expected_reason"),
    [
        (
            "missing",
            "RECONCILIATION_INCOMPLETE",
            "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
        ),
        (
            "failing",
            "RECONCILIATION_INCOMPLETE",
            "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
        ),
        (
            "wrong_type",
            "REFUSED",
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
    ],
)
def test_terminal_resolver_missing_failing_or_wrong_type_has_zero_observer_effect(
    resolver_case: str,
    expected_outcome: str,
    expected_reason: str,
) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, _binding, engine = _terminal_w3c_material(runtime)

    class Resolver:
        def resolve(self, _candidate):
            if resolver_case == "failing":
                raise RuntimeError("private runtime failure")
            return object()

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unresolved terminal input must not observe")

    observer = Observer()
    dependencies = _w3c_dependencies(
        runtime,
        engine=engine,
        terminal_binding_resolver=Resolver(),
    )
    if resolver_case == "missing":
        dependencies["terminal_binding_resolver"] = None
        with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
            runtime.AgentRelayTurnRuntime(
                observer=observer,
                registry=_registry(),
                current_binding_for=_binding_for,
                candidate_source=lambda: (candidate,),
                **dependencies,
            )
        assert observer.calls == 0
        return

    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **dependencies,
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome.value == expected_outcome
    assert receipt.reason == expected_reason
    assert observer.calls == 0
    assert "private runtime failure" not in repr(receipt)


@pytest.mark.parametrize("physical_state", ["missing", "duplicate"])
def test_terminal_physical_result_missing_or_duplicate_has_zero_observer_effect(
    physical_state: str,
) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)
    messages = engine.client.thread_messages[candidate.thread_ts]
    if physical_state == "missing":
        messages.clear()
    else:
        messages.append(dataclasses.replace(messages[0], ts="1788000000.123458"))

    class Resolver:
        def resolve(self, _candidate):
            return binding

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unproven physical result must not observe")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=Resolver(),
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.REFUSED
    assert receipt.reason == "TERMINAL_RESULT_RECEIPT_MISMATCH"
    assert observer.calls == 0


@pytest.mark.parametrize("outage", ["parent_read", "thread_read"])
def test_terminal_physical_read_outage_is_incomplete_not_receipt_refusal(
    monkeypatch,
    outage: str,
) -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, binding, engine = _terminal_w3c_material(runtime)

    async def unavailable(**_kwargs):
        raise RuntimeError("private transport outage")

    monkeypatch.setattr(
        engine.client,
        "fetch_channel_history" if outage == "parent_read" else "fetch_thread",
        unavailable,
    )

    class Resolver:
        def resolve(self, _candidate):
            return binding

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unavailable physical proof must not observe")

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=Resolver(),
        ),
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE"
    assert observer.calls == 0
    assert engine.client.post_call_count == 0


def test_turn_runtime_derives_trusted_routing_before_observer_io() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    class Observer:
        def __init__(self):
            self.calls = []

        async def reconcile_once(self, *, context, routing):
            self.calls.append((context, routing))
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="TEST",
                decision=None,
                obligation=None,
                route=None,
            )

    observer = Observer()

    class NeverTerminalResolver:
        def resolve(self, _candidate):
            raise AssertionError("active mode must never call the terminal resolver")

    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (_w3c_candidate(runtime),),
        poll_interval_seconds=1.0,
        **_w3c_dependencies(
            runtime,
            terminal_binding_resolver=NeverTerminalResolver(),
        ),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert [receipt.outcome for receipt in receipts] == [
        runtime.ObservationOutcome.NO_ACTION
    ]
    assert len(observer.calls) == 1
    context, routing = observer.calls[0]
    assert context.operation_key == _w3c_candidate(runtime).dialogue_parent["operation_key"]
    assert routing.ceo_target_bound is True
    assert routing.coo_target_bound is True
    assert routing.routing_workstream is None


def test_turn_runtime_refuses_stale_current_worker_before_observer_or_target_io() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import _registry

    class Observer:
        calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            raise AssertionError("observer must not run for stale current-worker facts")

    binding_calls: list[str] = []
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=Observer(),
        registry=_registry(),
        current_binding_for=lambda seat: binding_calls.append(seat),
        candidate_source=lambda: (
            _w3c_candidate(runtime, stale_parent=True),
        ),
        poll_interval_seconds=1.0,
        **_w3c_dependencies(runtime),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.REFUSED
    assert receipts[0].reason.startswith("CURRENT_WORKER_REFUSED:")
    assert turn_runtime.observer.calls == 0
    assert binding_calls == []


def test_turn_runtime_factory_reuses_the_existing_relay_slack_client(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    from control_plane.executive_runtime import Runtime
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        RuntimeTerminalReturnBindingResolver,
    )
    from tests.test_executive_wake_persisted_dispatch import _POLICY
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    token_file = _token_file(tmp_path)
    service = runtime.build_service(_config(runtime, socket_root, token_file))
    turn_runtime = runtime.build_turn_runtime(
        service,
        registry=_registry(),
        repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger")),
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=_binding_for,
        retry_policy=_POLICY,
        observation_client=runtime.ExecutiveDialogueObservationClient(
            runtime.EXECUTIVE_OBSERVATION_SOCKET_PATH
        ),
        terminal_binding_resolver=RuntimeTerminalReturnBindingResolver(lambda: None),
    )

    assert turn_runtime.observer.client is service.engine.client
    assert turn_runtime.observer.client is service.engine_v2.client
    assert turn_runtime.observer.policy is service.engine.policy
    assert service.engine_v2.active_waiter_registry is not None
    assert (
        turn_runtime.active_waiter_registry
        is service.engine_v2.active_waiter_registry
    )
    assert (
        inspect.signature(runtime.run_relay)
        .parameters["turn_runtime_factory"]
        .default
        is None
    )


def test_real_observation_source_discovers_parents_through_shared_v2_engine() -> None:
    runtime = _runtime()
    from integrations.slack_agent_dialogue.executive_observation_client import (
        ResolvedDialogueObservation,
    )

    candidate, _binding, engine = _terminal_w3c_material(runtime)
    active = _w3c_candidate(runtime)

    class ObservationClient:
        calls: list[tuple[dict, str]] = []

        async def resolve(self, *, parent, thread_ts):
            self.calls.append((dict(parent), thread_ts))
            return ResolvedDialogueObservation(
                state="RESOLVED",
                mode="ACTIVE_CURRENT_WORKER",
                dialogue_parent=dict(parent),
                thread_ts=thread_ts,
                delegation_identity=active.delegation_identity,
                current_worker=active.current_worker,
                actor=active.actor,
            )

    client = ObservationClient()

    async def collect():
        source = runtime.build_executive_observation_candidate_source(
            engine,
            client,
            maximum=4,
        )
        iterator = await source()
        return tuple([item async for item in iterator])

    observed = asyncio.run(collect())

    assert len(observed) == 1
    assert observed[0].current_worker == active.current_worker
    assert observed[0].actor == active.actor
    assert observed[0].dialogue_parent == candidate.dialogue_parent
    assert client.calls == [(candidate.dialogue_parent, candidate.thread_ts)]
    assert engine.client.channel_history_call_count == 1


def test_ephemeral_executive_listener_to_relay_source_vertical(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    import control_plane.executive_service as executive_service_module
    from control_plane.executive_dialogue_observation import (
        ActiveObservationFacts,
        DialogueObservationFacts,
        PublicRuntimeBindingFacts,
    )
    from control_plane.executive_service import ExecutiveControlService
    from tests.test_executive_service import _FakeSupervisor, _config

    active = _w3c_candidate(runtime)
    current = active.current_worker
    assert current is not None
    _terminal, _binding, engine = _terminal_w3c_material(runtime)
    observation_path = socket_root / "observation" / "dialogue-observation.sock"
    monkeypatch.setattr(
        executive_service_module,
        "_peer_uid",
        lambda _connection: 457,
    )

    def facts(_runtime, parent):
        assert parent == active.dialogue_parent
        return DialogueObservationFacts(
            active=(
                ActiveObservationFacts(
                    root_job_id=current.root_job_id,
                    job_id=current.job_id,
                    attempt_id=current.attempt_id,
                    worker_id=current.worker_id,
                    attempt_status=current.attempt_status.value,
                    worker_status=current.worker_status.value,
                    execution_profile_id=current.execution_profile_id,
                    execution_profile_digest=current.execution_profile_digest,
                    capability_policy_digest=current.capability_policy_digest,
                    runtime_binding=PublicRuntimeBindingFacts(
                        session_alias=current.runtime_binding.session_alias,
                        binding_id=current.runtime_binding.binding_id,
                        binding_generation=(
                            current.runtime_binding.binding_generation
                        ),
                        reasoning_surface=str(
                            current.runtime_binding.reasoning_surface
                        ),
                    ),
                    parent_fingerprint=parent["fingerprint"],
                    company_dialogue_server_identity=(
                        current.company_dialogue_server_identity
                    ),
                    company_dialogue_server_version=(
                        current.company_dialogue_server_version
                    ),
                    company_dialogue_tool_schema_digest=(
                        current.company_dialogue_tool_schema_digest
                    ),
                    company_dialogue_attested=True,
                ),
            )
        )

    executive = ExecutiveControlService(
        _config(tmp_path, socket_root=socket_root / "operator"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        dialogue_observation_socket_path=observation_path,
        dialogue_observation_peer_uid=457,
        dialogue_observation_group_gid=os.getegid(),
        dialogue_observation_facts_provider=facts,
    )

    async def scenario():
        await executive.start()
        try:
            assert executive.runtime is not None
            before = (
                len(executive.runtime.jobs.list_jobs()),
                len(executive.runtime.attempts.list_attempts()),
                len(executive.runtime.workers.list_workers()),
                len(executive.runtime.events.list_events()),
            )
            source = runtime.build_executive_observation_candidate_source(
                engine,
                runtime.ExecutiveDialogueObservationClient(
                    observation_path,
                    timeout_seconds=1,
                ),
                maximum=4,
            )
            iterator = await source()
            observed = tuple([item async for item in iterator])
            after = (
                len(executive.runtime.jobs.list_jobs()),
                len(executive.runtime.attempts.list_attempts()),
                len(executive.runtime.workers.list_workers()),
                len(executive.runtime.events.list_events()),
            )
            assert len(observed) == 1
            projected = observed[0].current_worker
            assert projected is not None
            assert dataclasses.replace(
                projected,
                runtime_binding=current.runtime_binding,
            ) == current
            assert projected.runtime_binding.native_handle is None
            assert projected.runtime_binding.account_label is None
            assert observed[0].actor is not None
            assert observed[0].actor.runtime_binding == projected.runtime_binding
            assert after == before
            assert engine.client.post_call_count == 0
        finally:
            await executive.close()

    asyncio.run(scenario())


def test_build_turn_runtime_selects_real_observation_source_when_enabled(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    from control_plane.executive_runtime import Runtime
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        RuntimeTerminalReturnBindingResolver,
    )
    from tests.test_executive_wake_persisted_dispatch import _POLICY
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    service = runtime.build_service(
        _config(runtime, socket_root, _token_file(tmp_path / "relay-token"))
    )
    calls = []

    async def empty_source():
        return runtime._FrozenCandidateIterator(())

    def compose(engine, client, *, maximum):
        calls.append((engine, client, maximum))
        return empty_source

    client = runtime.ExecutiveDialogueObservationClient(
        runtime.EXECUTIVE_OBSERVATION_SOCKET_PATH
    )
    monkeypatch.setattr(
        runtime,
        "build_executive_observation_candidate_source",
        compose,
    )
    turn_runtime = runtime.build_turn_runtime(
        service,
        registry=_registry(),
        repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger")),
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=_binding_for,
        retry_policy=_POLICY,
        observation_client=client,
        terminal_binding_resolver=RuntimeTerminalReturnBindingResolver(lambda: None),
    )

    assert asyncio.run(turn_runtime.reconcile_once()) == ()
    assert calls == [
        (service.engine_v2, client, runtime.DEFAULT_MAX_TURN_CANDIDATES_PER_PASS)
    ]


def test_build_turn_runtime_refuses_parallel_candidate_authority_seams(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    from control_plane.executive_runtime import Runtime
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        RuntimeTerminalReturnBindingResolver,
    )
    from tests.test_executive_wake_persisted_dispatch import _POLICY
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    service = runtime.build_service(
        _config(runtime, socket_root, _token_file(tmp_path / "relay-token"))
    )

    with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
        runtime.build_turn_runtime(
            service,
            registry=_registry(),
            repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger")),
            dispatchers=WakeDispatcherRegistry(),
            current_binding_for=_binding_for,
            retry_policy=_POLICY,
            candidate_source=lambda: (),
            observation_client=runtime.ExecutiveDialogueObservationClient(
                runtime.EXECUTIVE_OBSERVATION_SOCKET_PATH
            ),
            terminal_binding_resolver=RuntimeTerminalReturnBindingResolver(lambda: None),
        )

    with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
        runtime.build_turn_runtime(
            service,
            registry=_registry(),
            repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger-2")),
            dispatchers=WakeDispatcherRegistry(),
            current_binding_for=_binding_for,
            retry_policy=_POLICY,
            observation_client=runtime.ExecutiveDialogueObservationClient(
                "/tmp/not-the-dedicated-executive-observation.sock"
            ),
            terminal_binding_resolver=RuntimeTerminalReturnBindingResolver(lambda: None),
        )


def test_slow_observation_collection_leaves_relay_v1_and_v2_responsive(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    from integrations.slack_agent_dialogue.contract_v2 import render_parent_v2
    from integrations.slack_agent_dialogue.engine import HistoryPage, SlackMessage

    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    monkeypatch.setattr(service_module, "_peer_uid", lambda _connection: 450)
    service = runtime.build_service(
        _config(runtime, socket_root, _token_file(tmp_path / "relay-token"))
    )
    dialogue_parent = _w3c_candidate(runtime).dialogue_parent

    async def parent_history(**_kwargs):
        return HistoryPage(
            messages=(
                SlackMessage(
                    ts="1787961600.000001",
                    author_user_id=service.engine.policy.relay_bot_user_id,
                    text=render_parent_v2(dialogue_parent),
                ),
            ),
            complete=True,
            mutation_evidence_complete=True,
        )

    monkeypatch.setattr(
        service.engine_v2.client,
        "fetch_channel_history",
        parent_history,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowObservationClient:
        async def resolve(self, **_kwargs):
            entered.set()
            await release.wait()
            raise runtime.ExecutiveObservationClientError("UNAVAILABLE_ZERO_EFFECT")

    async def collect():
        source = runtime.build_executive_observation_candidate_source(
            service.engine_v2,
            SlowObservationClient(),
            maximum=4,
        )
        iterator = await source()
        return tuple([item async for item in iterator])

    async def scenario() -> None:
        await service.start()
        collection = asyncio.create_task(collect())
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            for version in (CONTROL_VERSION, CONTROL_VERSION_V2):
                response = await asyncio.wait_for(
                    call_service(service.config.socket_path, _request(version)),
                    timeout=0.2,
                )
                assert response["ok"] is True
            release.set()
            assert await asyncio.wait_for(collection, timeout=1) == ()
        finally:
            release.set()
            await asyncio.gather(collection, return_exceptions=True)
            await service.close()

    asyncio.run(scenario())


def test_terminal_observation_candidate_uses_executive_revalidated_binding() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    candidate, _binding, engine = _terminal_w3c_material(runtime)
    candidate = dataclasses.replace(
        candidate,
        current_worker=None,
        actor=None,
    )

    class NeverLocalResolver:
        def resolve(self, _candidate):
            raise AssertionError("Executive-revalidated binding must be consumed directly")

    class Observer:
        calls = 0

        async def reconcile_once(self, **_kwargs):
            self.calls += 1
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="EXECUTIVE_OBSERVATION_TERMINAL",
                decision=None,
                obligation=None,
                route=None,
            )

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (candidate,),
        **_w3c_dependencies(
            runtime,
            engine=engine,
            terminal_binding_resolver=NeverLocalResolver(),
        ),
        _executive_observation_source=True,
    )

    receipt = asyncio.run(turn_runtime.reconcile_once())[0]

    assert receipt.outcome is runtime.ObservationOutcome.NO_ACTION
    assert receipt.reason == "EXECUTIVE_OBSERVATION_TERMINAL"
    assert observer.calls == 1


@pytest.mark.parametrize("missing", ["registry", "resolver"])
def test_turn_runtime_composition_refuses_missing_trusted_owner(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
    missing: str,
) -> None:
    runtime = _runtime()
    from control_plane.executive_runtime import Runtime
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        RuntimeTerminalReturnBindingResolver,
    )
    from tests.test_executive_wake_persisted_dispatch import _POLICY
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    monkeypatch.setattr(
        runtime,
        "AGENT_RELAY_SOCKET_PATH",
        socket_root / "agent-relay.sock",
    )
    service = runtime.build_service(
        _config(runtime, socket_root, _token_file(tmp_path / "owner-token"))
    )
    if missing == "registry":
        service.engine_v2._active_waiter_registry = None
    resolver = (
        object()
        if missing == "resolver"
        else RuntimeTerminalReturnBindingResolver(lambda: None)
    )

    with pytest.raises(runtime.RelayRuntimeError, match="RUNTIME_INVALID"):
        runtime.build_turn_runtime(
            service,
            registry=_registry(),
            repository=WakeLedgerRepository(Runtime.at(tmp_path / "owner-ledger")),
            dispatchers=WakeDispatcherRegistry(),
            current_binding_for=_binding_for,
            retry_policy=_POLICY,
            observation_client=runtime.ExecutiveDialogueObservationClient(
                runtime.EXECUTIVE_OBSERVATION_SOCKET_PATH
            ),
            terminal_binding_resolver=resolver,
        )


def test_run_relay_keeps_af_unix_service_available_while_turn_loop_runs(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)
    token_file = _token_file(tmp_path)
    config = _config(runtime, socket_root, token_file)
    service = runtime.build_service(config)
    monkeypatch.setattr(runtime, "build_service", lambda _config: service)

    class Loop:
        def __init__(self):
            self.started = asyncio.Event()

        async def serve_forever(self):
            self.started.set()
            await asyncio.Future()

    loop = Loop()

    async def scenario() -> None:
        task = asyncio.create_task(
            runtime.run_relay(
                config,
                turn_runtime_factory=lambda actual: (
                    loop
                    if actual is service
                    else (_ for _ in ()).throw(
                        AssertionError("factory received a different service")
                    )
                ),
            )
        )
        for _attempt in range(200):
            if service.config.socket_path.exists() and loop.started.is_set():
                break
            if task.done():
                await task
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("service and turn loop did not start together")

        try:
            response = await call_service(
                service.config.socket_path,
                _request(CONTROL_VERSION_V2),
            )
            assert response["ok"] is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not service.config.socket_path.exists()

    asyncio.run(scenario())
