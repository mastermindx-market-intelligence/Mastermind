"""Focused tests for the native selected-child plugin adapter.

Two layers.

*Controlled adapter tests* cover the closed request shape, the caller-lineage
fence, the refusal/uncertainty split and the binding isolation. They need no
upstream runtime and call no provider, credential, listener or service.

*Native API tests* exercise the real pinned ``PluginContext`` and
``ToolRegistry``. They run only when a checkout of the pinned upstream is
available at ``MASTERMIND_HERMES_VENDOR_ROOT``; otherwise they skip with the
exact reason. Nothing here installs a package, and no upstream proof is
fabricated: the upstream code under test is the pinned code.

The pinned upstream imports ``ruamel.yaml``, which is absent from this
environment and cannot be installed. The test therefore installs an
import-only shim for that library. The shim's ``YAML`` raises if anything
actually parses YAML, so the native path under test provably never touches a
YAML parser.
"""
from __future__ import annotations

from dataclasses import replace
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from integrations.hermes_harness import native_tool_registration as adapter
from integrations.hermes_harness.native_tool_registration import (
    NATIVE_TOOL_SCHEMA,
    NativeDelegateBinding,
    NativeDelegateStartup,
    NativeToolRegistrationError,
    SELECTED_CHILD_SCHEMA,
    SELECTED_CHILD_STATES,
    SUPPORTED_LOADING_MODE,
    TOOL_NAME,
    TOOLSET_NAME,
    native_delegate_check_fn,
    native_delegate_handler,
    register_native_delegate_tools,
)

ROOT = Path(__file__).resolve().parents[3]
VENDOR_ENV = "MASTERMIND_HERMES_VENDOR_ROOT"

COMMAND = "coo-cycle:JOB-ROOT-001:dispatch:JOB-CHILD-002:attempt:1"
OTHER_COMMAND = "coo-cycle:JOB-ROOT-001:dispatch:JOB-CHILD-009:attempt:1"
JOB_ID = "JOB-CHILD-002"


class _RecordingTransport:
    """One host-owned transport double: it records every call it receives."""

    def __init__(self, envelope=None, error=None):
        self.envelope = envelope
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def submit_selected_child(self, command_id: str):
        self.calls.append(("submit", command_id))
        if self.error is not None:
            raise self.error
        return self.envelope

    def selected_child_status(self, command_id: str):
        self.calls.append(("status", command_id))
        if self.error is not None:
            raise self.error
        return self.envelope


def _envelope(*, command: str = COMMAND, job_id: str = JOB_ID, state: str = "ACTIVE",
              attempt_id: str | None = "ATT-001", live_submit: bool | None = True,
              **extra) -> dict:
    body = {
        "schema": SELECTED_CHILD_SCHEMA,
        "state": state,
        "reason": None,
        "command_id": command,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "attempt_status": "CLAIMED",
        "job_status": "RUNNING",
        "live_submit": live_submit,
    }
    body.update(extra)
    return body


def _binding(transport=None, *, current: bool = True, session_id: str = "sess-1",
             task_id: str | None = None, session_key: str | None = None,
             command: str = COMMAND, job_id: str = JOB_ID,
             profile_id: str = "default") -> NativeDelegateBinding:
    return NativeDelegateBinding(
        transport=transport if transport is not None else _RecordingTransport(),
        currentness_guard=lambda: current,
        profile_id=profile_id,
        session_id=session_id,
        command=command,
        job_id=job_id,
        session_key=session_key,
        task_id=task_id,
    )


def _dispatch(handler, arguments, *, session_id="sess-1", task_id=None):
    return json.loads(handler(arguments, session_id=session_id, task_id=task_id))


class BindingContractTests(unittest.TestCase):
    def test_binding_rejects_a_command_for_another_job(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            _binding(job_id="JOB-CHILD-009")
        self.assertEqual(caught.exception.code, "NATIVE_COMMAND_JOB_MISMATCH")

    def test_binding_rejects_a_malformed_command(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            _binding(command="coo-cycle:root:dispatch:child")
        self.assertEqual(caught.exception.code, "NATIVE_COMMAND_INVALID")

    def test_binding_rejects_a_transport_without_the_two_entries(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            NativeDelegateBinding(
                transport=object(),
                currentness_guard=lambda: True,
                profile_id="default",
                session_id="sess-1",
                command=COMMAND,
                job_id=JOB_ID,
            )
        self.assertEqual(caught.exception.code, "NATIVE_TRANSPORT_INVALID")

    def test_binding_rejects_a_missing_currentness_guard(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            NativeDelegateBinding(
                transport=_RecordingTransport(),
                currentness_guard=None,
                profile_id="default",
                session_id="sess-1",
                command=COMMAND,
                job_id=JOB_ID,
            )
        self.assertEqual(caught.exception.code, "NATIVE_CURRENTNESS_GUARD_INVALID")

    def test_binding_rejects_async_function_and_async_callable_guards(self) -> None:
        async def guard():
            return True

        class AsyncGuard:
            async def __call__(self):
                return True

        for candidate in (guard, AsyncGuard()):
            with self.subTest(candidate=type(candidate).__name__):
                with self.assertRaises(NativeToolRegistrationError) as caught:
                    replace(_binding(), currentness_guard=candidate)
                self.assertEqual(caught.exception.code, "NATIVE_CURRENTNESS_GUARD_INVALID")

    def test_module_holds_no_process_global_binding(self) -> None:
        # A module-level binding would let a later install retarget a live
        # handler. The handler must hold the binding it was registered with.
        for name, value in vars(adapter).items():
            self.assertNotIsInstance(value, NativeDelegateBinding, name)
        self.assertFalse(
            [name for name, value in vars(adapter).items()
             if isinstance(value, (list, dict, set)) and value
             and any(isinstance(item, NativeDelegateBinding) for item in value)],
        )


class RequestShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = _RecordingTransport(_envelope())
        self.binding = _binding(self.transport)
        self.handler = native_delegate_handler(self.binding)

    def test_closed_actions_reach_the_transport_once(self) -> None:
        body = _dispatch(self.handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "ACTIVE")
        self.assertEqual(body["live_submit"], True)
        self.assertEqual(body["command_id"], COMMAND)
        self.assertEqual(body["job_id"], JOB_ID)
        self.assertEqual(self.transport.calls, [("submit", COMMAND)])

    def test_status_action_reads_the_same_original_command(self) -> None:
        self.transport.envelope = _envelope(state="NOT_CLAIMED", attempt_id=None, live_submit=False)
        body = _dispatch(self.handler, {"action": "selected_child_status", "command": COMMAND})
        self.assertEqual(body["state"], "NOT_CLAIMED")
        self.assertEqual(body["live_submit"], False)
        self.assertEqual(self.transport.calls, [("status", COMMAND)])

    def test_legacy_actions_refuse_without_a_call(self) -> None:
        for action in ("submit", "status", "cancel", "review", "consume", "delegate_task"):
            body = _dispatch(self.handler, {"action": action, "command": COMMAND})
            self.assertEqual(body["state"], "REFUSED", action)
            self.assertEqual(body["reason"], "UNKNOWN_ACTION", action)
        self.assertEqual(self.transport.calls, [])

    def test_unknown_and_model_authority_fields_refuse_without_a_call(self) -> None:
        for field, value in (
            ("idempotency_key", "model-chosen-key"),
            ("root_id", "JOB-ROOT-001"),
            ("parent_id", "JOB-ROOT-001"),
            ("job_id", JOB_ID),
            ("attempt_id", "ATT-001"),
            ("authority", "model-asserted"),
            ("reviewer_id", "model-asserted"),
            ("idempotency_key2", "x"),
        ):
            body = _dispatch(self.handler, {
                "action": "selected_child_submit", "command": COMMAND, field: value})
            self.assertEqual(body["state"], "REFUSED", field)
            self.assertEqual(body["reason"], "UNKNOWN_FIELD", field)
        self.assertEqual(self.transport.calls, [])

    def test_malformed_action_types_refuse_without_a_call(self) -> None:
        for action in ([], {}, 5, None, True, ("selected_child_submit",), b"submit"):
            body = _dispatch(self.handler, {"action": action, "command": COMMAND})
            self.assertEqual(body["state"], "REFUSED", repr(action))
            self.assertEqual(body["reason"], "UNKNOWN_ACTION", repr(action))
        self.assertEqual(self.transport.calls, [])

    def test_malformed_arguments_refuse_without_a_call(self) -> None:
        for arguments in (None, [], "submit", 5, {"action": "selected_child_submit"}):
            body = _dispatch(self.handler, arguments)
            self.assertEqual(body["state"], "REFUSED", repr(arguments))
        self.assertEqual(self.transport.calls, [])

    def test_a_malformed_command_refuses_without_a_call(self) -> None:
        body = _dispatch(self.handler, {"action": "selected_child_submit", "command": "JOB-CHILD-002"})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "COMMAND_INVALID")
        self.assertEqual(self.transport.calls, [])

    def test_a_foreign_command_refuses_without_a_call(self) -> None:
        body = _dispatch(self.handler, {
            "action": "selected_child_submit", "command": OTHER_COMMAND})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_COMMAND_MISMATCH")
        self.assertEqual(self.transport.calls, [])


class CallerLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = _RecordingTransport(_envelope())
        self.binding = _binding(self.transport)
        self.handler = native_delegate_handler(self.binding)

    def test_a_missing_native_session_refuses_without_a_call(self) -> None:
        body = _dispatch(self.handler, {"action": "selected_child_submit", "command": COMMAND},
                         session_id=None)
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_MISSING")
        self.assertEqual(self.transport.calls, [])

    def test_a_foreign_native_session_refuses_without_a_call(self) -> None:
        body = _dispatch(self.handler, {"action": "selected_child_submit", "command": COMMAND},
                         session_id="sess-other")
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_MISMATCH")
        self.assertEqual(self.transport.calls, [])

    def test_a_task_mismatch_refuses_without_a_call(self) -> None:
        binding = _binding(self.transport, task_id="task-1")
        handler = native_delegate_handler(binding)
        body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND},
                         task_id="task-2")
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_TASK_MISMATCH")
        self.assertEqual(self.transport.calls, [])

    def test_a_foreign_route_key_refuses_without_a_call(self) -> None:
        binding = _binding(self.transport, session_key="route-1")
        handler = native_delegate_handler(binding)
        with mock.patch.object(adapter, "_bound_session_key", return_value="route-2"):
            body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_KEY_MISMATCH")
        self.assertEqual(self.transport.calls, [])

    def test_an_unprovable_route_key_refuses_without_a_call(self) -> None:
        binding = _binding(self.transport, session_key="route-1")
        handler = native_delegate_handler(binding)
        with mock.patch.object(adapter, "_bound_session_key", return_value=None):
            body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_KEY_UNAVAILABLE")
        self.assertEqual(self.transport.calls, [])

    def test_a_stale_binding_refuses_without_a_call(self) -> None:
        state = {"current": True}
        binding = NativeDelegateBinding(
            transport=self.transport,
            currentness_guard=lambda: state["current"],
            profile_id="default",
            session_id="sess-1",
            command=COMMAND,
            job_id=JOB_ID,
        )
        handler = native_delegate_handler(binding)
        probe = native_delegate_check_fn(binding)
        self.assertTrue(probe())
        state["current"] = False
        body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_BINDING_STALE")
        self.assertEqual(self.transport.calls, [])

    def test_truthy_non_boolean_and_awaitable_guard_results_cannot_authorize(self) -> None:
        class Awaitable:
            def __await__(self):
                raise AssertionError("a synchronous qualification must not await")

        for value in (1, "current", [True], object(), Awaitable()):
            binding = replace(self.binding, currentness_guard=lambda: value)
            self.assertFalse(native_delegate_check_fn(binding)())
            for action in ("selected_child_submit", "selected_child_status"):
                body = _dispatch(native_delegate_handler(binding),
                    {"action": action, "command": COMMAND})
                self.assertEqual(body["state"], "REFUSED")
                self.assertEqual(body["reason"], "NATIVE_BINDING_STALE")
        self.assertEqual(self.transport.calls, [])

    def test_sync_guard_returning_a_coroutine_is_closed_and_cannot_send(self) -> None:
        created = []

        async def deferred_guard():
            self.fail("the deferred guard must never be awaited")

        def guard():
            value = deferred_guard()
            created.append(value)
            return value

        binding = replace(self.binding, currentness_guard=guard)
        self.assertFalse(native_delegate_check_fn(binding)())
        for action in ("selected_child_submit", "selected_child_status"):
            body = _dispatch(native_delegate_handler(binding),
                {"action": action, "command": COMMAND})
            self.assertEqual(body["state"], "REFUSED")
            self.assertEqual(body["reason"], "NATIVE_BINDING_STALE")
        self.assertEqual(self.transport.calls, [])
        self.assertTrue(created)
        self.assertTrue(all(value.cr_frame is None for value in created))

    def test_discovery_never_authorizes_a_foreign_caller(self) -> None:
        probe = native_delegate_check_fn(self.binding)
        self.assertTrue(probe())
        body = _dispatch(self.handler, {"action": "selected_child_submit", "command": COMMAND},
                         session_id="sess-other")
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_MISMATCH")
        self.assertEqual(self.transport.calls, [])

    def test_a_raising_currentness_guard_refuses_without_a_call(self) -> None:
        def guard():
            raise RuntimeError("private detail")
        binding = NativeDelegateBinding(
            transport=self.transport,
            currentness_guard=guard,
            profile_id="default",
            session_id="sess-1",
            command=COMMAND,
            job_id=JOB_ID,
        )
        handler = native_delegate_handler(binding)
        body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_BINDING_STALE")
        self.assertNotIn("private detail", json.dumps(body))
        self.assertEqual(self.transport.calls, [])


class UncertaintyTests(unittest.TestCase):
    def test_a_submit_exception_keeps_the_original_command_and_unknown_effect(self) -> None:
        transport = _RecordingTransport(error=RuntimeError("private transport detail"))
        handler = native_delegate_handler(_binding(transport))
        body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(body["state"], "EFFECT_UNKNOWN")
        self.assertEqual(body["command_id"], COMMAND)
        self.assertEqual(body["job_id"], JOB_ID)
        self.assertIsNone(body["live_submit"])
        self.assertEqual(transport.calls, [("submit", COMMAND)])

    def test_a_malformed_envelope_keeps_the_original_command_and_unknown_effect(self) -> None:
        for envelope in (
            _envelope(command=OTHER_COMMAND),
            _envelope(job_id="JOB-CHILD-009"),
            _envelope(state="NOT_A_STATE"),
            {"schema": SELECTED_CHILD_SCHEMA, "state": "ACTIVE"},
            "not json",
            ["not", "an", "envelope"],
            _envelope(live_submit=False),
        ):
            transport = _RecordingTransport(envelope)
            handler = native_delegate_handler(_binding(transport))
            body = _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
            self.assertEqual(body["state"], "EFFECT_UNKNOWN", repr(envelope))
            self.assertEqual(body["command_id"], COMMAND)
            self.assertIsNone(body["live_submit"])
            self.assertEqual(transport.calls, [("submit", COMMAND)])

    def test_a_status_exception_is_unavailable_rather_than_a_no_effect(self) -> None:
        transport = _RecordingTransport(error=RuntimeError("private transport detail"))
        handler = native_delegate_handler(_binding(transport))
        body = _dispatch(handler, {"action": "selected_child_status", "command": COMMAND})
        self.assertEqual(body["state"], "UNAVAILABLE")
        self.assertEqual(body["command_id"], COMMAND)
        self.assertIsNone(body["live_submit"])
        self.assertEqual(transport.calls, [("status", COMMAND)])

    def test_a_status_never_resubmits(self) -> None:
        transport = _RecordingTransport(_envelope())
        handler = native_delegate_handler(_binding(transport))
        _dispatch(handler, {"action": "selected_child_status", "command": COMMAND})
        self.assertEqual([name for name, _ in transport.calls], ["status"])

    def test_one_dispatch_calls_the_transport_exactly_once(self) -> None:
        transport = _RecordingTransport(error=RuntimeError("boom"))
        handler = native_delegate_handler(_binding(transport))
        for _ in range(3):
            _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND})
        self.assertEqual(len(transport.calls), 3)

    def test_a_refusal_never_reaches_the_transport(self) -> None:
        transport = _RecordingTransport(_envelope())
        handler = native_delegate_handler(_binding(transport))
        _dispatch(handler, {"action": "cancel", "command": COMMAND})
        _dispatch(handler, {"action": "selected_child_submit", "command": OTHER_COMMAND})
        _dispatch(handler, {"action": "selected_child_submit", "command": COMMAND},
                  session_id=None)
        self.assertEqual(transport.calls, [])


class BindingIsolationTests(unittest.TestCase):
    def test_two_bindings_never_exchange_commands_or_transports(self) -> None:
        first_transport = _RecordingTransport(_envelope())
        second_transport = _RecordingTransport(_envelope(command=OTHER_COMMAND, job_id="JOB-CHILD-009"))
        first = native_delegate_handler(_binding(first_transport, session_id="sess-1"))
        second = native_delegate_handler(_binding(
            second_transport, session_id="sess-2", command=OTHER_COMMAND, job_id="JOB-CHILD-009"))

        first_body = _dispatch(first, {"action": "selected_child_submit", "command": COMMAND},
                               session_id="sess-1")
        second_body = _dispatch(second, {"action": "selected_child_submit", "command": OTHER_COMMAND},
                                session_id="sess-2")
        self.assertEqual(first_body["command_id"], COMMAND)
        self.assertEqual(second_body["command_id"], OTHER_COMMAND)
        self.assertEqual(first_transport.calls, [("submit", COMMAND)])
        self.assertEqual(second_transport.calls, [("submit", OTHER_COMMAND)])

    def test_a_handler_keeps_its_binding_after_another_one_is_built(self) -> None:
        first_transport = _RecordingTransport(_envelope())
        first = native_delegate_handler(_binding(first_transport, session_id="sess-1"))
        second_transport = _RecordingTransport(_envelope(command=OTHER_COMMAND, job_id="JOB-CHILD-009"))
        native_delegate_handler(_binding(
            second_transport, session_id="sess-2", command=OTHER_COMMAND, job_id="JOB-CHILD-009"))
        body = _dispatch(first, {"action": "selected_child_submit", "command": COMMAND},
                         session_id="sess-1")
        self.assertEqual(body["command_id"], COMMAND)
        self.assertEqual(first_transport.calls, [("submit", COMMAND)])
        self.assertEqual(second_transport.calls, [])


class StartupSeamTests(unittest.TestCase):
    def test_an_unbound_startup_refuses(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            register_native_delegate_tools(object(), NativeDelegateStartup())
        self.assertEqual(caught.exception.code, "NATIVE_TOOL_STARTUP_UNBOUND")

    def test_a_missing_startup_refuses(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            register_native_delegate_tools(object(), None)
        self.assertEqual(caught.exception.code, "NATIVE_TOOL_STARTUP_UNBOUND")

    def test_a_context_without_the_owner_api_refuses(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            adapter.register_native_delegate_tool(object(), _binding(_RecordingTransport()))
        self.assertEqual(caught.exception.code, "NATIVE_PLUGIN_CONTEXT_INVALID")

    def test_a_non_binding_refuses(self) -> None:
        with self.assertRaises(NativeToolRegistrationError) as caught:
            adapter.register_native_delegate_tool(object(), {"command": COMMAND})
        self.assertEqual(caught.exception.code, "NATIVE_BINDING_INVALID")


class ContractDriftTests(unittest.TestCase):
    def test_the_state_set_matches_the_accepted_contract(self) -> None:
        from integrations.hermes_delegate import executive

        self.assertEqual(SELECTED_CHILD_SCHEMA, executive.SELECTED_CHILD_SCHEMA)
        selection = executive.ExecutiveChildSelection(
            root_job_id="JOB-ROOT-001",
            parent_job_id="JOB-ROOT-001",
            job_id=JOB_ID,
            plan_attempt_id="PLAN-ATTEMPT-001",
            plan_digest="d" * 64,
            plan_step_id="PLAN-STEP-001",
            repair_round=0,
            expected_current_attempt_id=None,
        )
        child = executive.ExecutiveSelectedChild(selection=selection, attempt_ordinal=1)
        for state in SELECTED_CHILD_STATES:
            attempt = None if state in {"NOT_CLAIMED", "EFFECT_UNKNOWN", "REFUSED", "UNAVAILABLE"} else "ATT-001"
            body = {
                "state": state,
                "command_id": child.command_id,
                "job_id": JOB_ID,
                "attempt_id": attempt,
            }
            projected = executive._envelope(body, child)
            self.assertEqual(projected["state"], state)
            expected_live = True if attempt is not None else (
                None if state in {"EFFECT_UNKNOWN", "UNAVAILABLE"} else False)
            self.assertEqual(projected["live_submit"], expected_live)
        self.assertNotIn("NOT_A_STATE", SELECTED_CHILD_STATES)


# --- native upstream API -----------------------------------------------------

def _install_ruamel_import_shim() -> None:
    """Satisfy the missing ``ruamel.yaml`` import only.

    The upstream ``hermes_cli`` package imports a YAML library at module
    import time. That library is absent here and cannot be installed, so the
    import is satisfied by a shim whose ``YAML`` raises if anything actually
    parses YAML. The native path under test therefore provably never touches a
    YAML parser.
    """
    try:
        import ruamel.yaml  # noqa: F401
        return
    except Exception:
        pass
    ruamel = types.ModuleType("ruamel")
    yaml_module = types.ModuleType("ruamel.yaml")
    error_module = types.ModuleType("ruamel.yaml.error")
    resolver_module = types.ModuleType("ruamel.yaml.resolver")

    class _YAML:
        def __init__(self, *args, **kwargs):
            raise AssertionError("the native path under test must not parse YAML")

    class _YAMLError(Exception):
        pass

    class _VersionedResolver:
        pass

    yaml_module.YAML = _YAML
    yaml_module.YAMLError = _YAMLError
    error_module.YAMLError = _YAMLError
    resolver_module.VersionedResolver = _VersionedResolver
    yaml_module.error = error_module
    yaml_module.resolver = resolver_module
    ruamel.yaml = yaml_module
    sys.modules.setdefault("ruamel", ruamel)
    sys.modules.setdefault("ruamel.yaml", yaml_module)
    sys.modules.setdefault("ruamel.yaml.error", error_module)
    sys.modules.setdefault("ruamel.yaml.resolver", resolver_module)


class _Upstream:
    """The pinned upstream modules the native tests exercise."""

    def __init__(self, root: Path):
        self.root = root
        if str(root) not in sys.path:
            sys.path.append(str(root))
        _install_ruamel_import_shim()
        from hermes_cli.plugins import PluginContext, PluginManager
        from hermes_cli.plugins_manifest import PluginManifest
        from tools.registry import registry

        self.PluginContext = PluginContext
        self.PluginManager = PluginManager
        self.PluginManifest = PluginManifest
        self.registry = registry


def _vendor_root() -> Path | None:
    raw = os.environ.get(VENDOR_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw).resolve()
    if not (root / "hermes_cli" / "plugins.py").is_file():
        return None
    return root


class NativePluginApiTests(unittest.TestCase):
    """The real pinned ``PluginContext`` and ``ToolRegistry``."""

    @classmethod
    def setUpClass(cls) -> None:
        root = _vendor_root()
        if root is None:
            raise unittest.SkipTest(
                f"{VENDOR_ENV} does not name a checkout of the pinned upstream")
        cls.root = root
        cls.upstream = _Upstream(root)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        environment = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)

    def _manager(self, name: str):
        scope = self.home / name
        scope.mkdir(parents=True, exist_ok=True)
        return self.upstream.PluginManager(scope_key=str(scope)), str(scope)

    def _manager_in_home(self, name: str):
        """A manager whose profile scope is also the active Hermes home.

        The owner's discovery reads the active profile's scope, so this is the
        shape the installed tool is actually discoverable in.
        """
        scope = self.home / name
        scope.mkdir(parents=True, exist_ok=True)
        os.environ["HERMES_HOME"] = str(scope)
        return self.upstream.PluginManager(scope_key=str(scope)), str(scope)

    def _ctx(self, manager):
        manifest = self.upstream.PluginManifest(
            name="mastermind-native-delegate",
            version="1",
            source="project",
            path=str(self.home),
            provides_tools=[TOOL_NAME],
            key="mastermind-native-delegate",
        )
        return self.upstream.PluginContext(manifest, manager)

    def test_the_vendor_is_the_pinned_upstream(self) -> None:
        from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA

        try:
            head = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is unavailable; the upstream pin cannot be attested here")
        if head.returncode:
            self.skipTest("the vendor root is not a git checkout")
        self.assertEqual(head.stdout.strip(), PINNED_UPSTREAM_SHA)

    def test_registration_reads_back_through_the_owner_api(self) -> None:
        manager, scope = self._manager("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        binding = _binding(transport)
        registration = adapter.register_native_delegate_tool(ctx, binding)

        entry = self.upstream.registry.snapshot_registration(TOOL_NAME, scope=scope)
        self.assertIsNotNone(entry)
        self.assertIs(entry.handler, registration.handler)
        self.assertIs(entry.check_fn, registration.check_fn)
        self.assertEqual(entry.toolset, TOOLSET_NAME)
        self.assertEqual(entry.schema, NATIVE_TOOL_SCHEMA)
        self.assertEqual(entry.name, TOOL_NAME)
        self.assertEqual(registration.scope, scope)

    def test_absence_registration_and_readback_share_the_native_transaction(self) -> None:
        from registration_lifecycle import replacement_coordinator

        manager, _ = self._manager("transaction-profile")
        ctx = self._ctx(manager)
        original_transaction = replacement_coordinator.transaction
        original_snapshot = self.upstream.registry.snapshot_registration
        depth, snapshots = [0], []

        @contextlib.contextmanager
        def transaction():
            with original_transaction():
                depth[0] += 1
                try:
                    yield
                finally:
                    depth[0] -= 1

        def snapshot(*args, **kwargs):
            snapshots.append(depth[0])
            return original_snapshot(*args, **kwargs)

        with mock.patch.object(replacement_coordinator, "transaction", side_effect=transaction), \
             mock.patch.object(self.upstream.registry, "snapshot_registration", side_effect=snapshot):
            registration = adapter.register_native_delegate_tool(ctx, _binding())
        self.addCleanup(registration.handle.dispose)
        self.assertGreaterEqual(len(snapshots), 3)
        self.assertTrue(all(value > 0 for value in snapshots))
        self.assertEqual(depth[0], 0)

    def test_readback_failure_disposes_only_the_captured_native_lease(self) -> None:
        for failure in ("exception", "mismatch"):
            manager, scope = self._manager("readback-" + failure)
            ctx = self._ctx(manager)
            register, snapshot = ctx.register_tool, self.upstream.registry.snapshot_registration
            registered, failed = [False], [False]

            def register_once(**kwargs):
                handle = register(**kwargs)
                self.addCleanup(handle.dispose)
                registered[0] = True
                return handle

            def readback(*args, **kwargs):
                if registered[0] and not failed[0]:
                    failed[0] = True
                    if failure == "exception":
                        raise OSError("readback unavailable")
                    return None
                return snapshot(*args, **kwargs)

            with mock.patch.object(ctx, "register_tool", side_effect=register_once), \
                 mock.patch.object(self.upstream.registry, "snapshot_registration", side_effect=readback):
                with self.assertRaises(NativeToolRegistrationError) as caught:
                    adapter.register_native_delegate_tool(ctx, _binding())
            expected = ("NATIVE_TOOL_READBACK_FAILED" if failure == "exception"
                        else "NATIVE_TOOL_READBACK_MISMATCH")
            self.assertEqual(caught.exception.code, expected)
            self.assertIsNone(snapshot(TOOL_NAME, scope=scope))

    def test_owner_exception_after_write_retains_original_registration_uncertainty(self) -> None:
        manager, scope = self._manager("uncertain-registration")
        ctx = self._ctx(manager)
        binding = _binding()
        register = ctx.register_tool
        handles = []

        def write_then_raise(**kwargs):
            handle = register(**kwargs)
            handles.append(handle)
            self.addCleanup(handle.dispose)
            raise OSError("owner could not return its lease")

        with mock.patch.object(ctx, "register_tool", side_effect=write_then_raise) as call:
            with self.assertRaises(NativeToolRegistrationError) as caught:
                adapter.register_native_delegate_tool(ctx, binding)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(caught.exception.code, "NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN")
        self.assertIs(caught.exception.original_context, ctx)
        self.assertIs(caught.exception.original_binding, binding)
        self.assertEqual(caught.exception.original_scope, scope)
        self.assertEqual(caught.exception.original_tool_name, TOOL_NAME)
        self.assertIsNone(caught.exception.original_handle)
        self.assertEqual(len(handles), 1)
        self.assertIsNotNone(self.upstream.registry.snapshot_registration(TOOL_NAME, scope=scope))

    def test_a_collision_refuses_and_never_reports_registered(self) -> None:
        manager, scope = self._manager("profile-a")
        ctx = self._ctx(manager)
        first = adapter.register_native_delegate_tool(ctx, _binding(_RecordingTransport()))
        with self.assertRaises(NativeToolRegistrationError) as caught:
            adapter.register_native_delegate_tool(ctx, _binding(_RecordingTransport()))
        self.assertEqual(caught.exception.code, "NATIVE_TOOL_COLLISION")
        entry = self.upstream.registry.snapshot_registration(TOOL_NAME, scope=scope)
        self.assertIs(entry.handler, first.handler)

    def test_the_owner_unload_removes_the_entry(self) -> None:
        manager, scope = self._manager("profile-a")
        ctx = self._ctx(manager)
        registration = adapter.register_native_delegate_tool(ctx, _binding(_RecordingTransport()))
        self.assertIsNotNone(self.upstream.registry.snapshot_registration(TOOL_NAME, scope=scope))
        registration.handle.dispose()
        self.assertIsNone(self.upstream.registry.snapshot_registration(TOOL_NAME, scope=scope))

    def test_a_foreign_profile_refuses(self) -> None:
        manager, _ = self._manager("profile-a")
        ctx = self._ctx(manager)
        with self.assertRaises(NativeToolRegistrationError) as caught:
            adapter.register_native_delegate_tool(ctx, _binding(profile_id="not-this-profile"))
        self.assertEqual(caught.exception.code, "NATIVE_PROFILE_MISMATCH")

    def test_two_profiles_do_not_exchange_handlers(self) -> None:
        first_manager, first_scope = self._manager("profile-a")
        second_manager, second_scope = self._manager("profile-b")
        first_transport = _RecordingTransport(_envelope())
        second_transport = _RecordingTransport(_envelope(command=OTHER_COMMAND, job_id="JOB-CHILD-009"))
        first = adapter.register_native_delegate_tool(
            self._ctx(first_manager), _binding(first_transport, session_id="sess-1"))
        second = adapter.register_native_delegate_tool(
            self._ctx(second_manager),
            _binding(second_transport, session_id="sess-2", command=OTHER_COMMAND, job_id="JOB-CHILD-009"))

        first_entry = self.upstream.registry.snapshot_registration(TOOL_NAME, scope=first_scope)
        second_entry = self.upstream.registry.snapshot_registration(TOOL_NAME, scope=second_scope)
        self.assertIsNot(first_entry, second_entry)
        self.assertIs(first_entry.handler, first.handler)
        self.assertIs(second_entry.handler, second.handler)

        body = json.loads(self.upstream.registry.dispatch(
            TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
            scope=first_scope, session_id="sess-1"))
        self.assertEqual(body["command_id"], COMMAND)
        self.assertEqual(first_transport.calls, [("submit", COMMAND)])
        self.assertEqual(second_transport.calls, [])

    def test_the_real_dispatch_refuses_a_foreign_caller(self) -> None:
        manager, scope = self._manager("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        adapter.register_native_delegate_tool(ctx, _binding(transport))
        body = json.loads(self.upstream.registry.dispatch(
            TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
            scope=scope, session_id="sess-other"))
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_MISMATCH")
        self.assertEqual(transport.calls, [])

    def test_the_real_dispatch_serves_the_bound_command(self) -> None:
        manager, scope = self._manager("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        adapter.register_native_delegate_tool(ctx, _binding(transport))
        body = json.loads(self.upstream.registry.dispatch(
            TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
            scope=scope, session_id="sess-1"))
        self.assertEqual(body["state"], "ACTIVE")
        self.assertEqual(body["live_submit"], True)
        self.assertEqual(transport.calls, [("submit", COMMAND)])

    def test_the_supported_loading_mode_is_the_in_process_one(self) -> None:
        self.assertEqual(SUPPORTED_LOADING_MODE, "in_process")

    def test_a_raising_owner_registration_preserves_uncertainty(self) -> None:
        manager, _ = self._manager("profile-a")
        ctx = self._ctx(manager)

        def boom(**kwargs):
            raise RuntimeError("the owner refused this registration")

        ctx.register_tool = boom
        with self.assertRaises(NativeToolRegistrationError) as caught:
            adapter.register_native_delegate_tool(ctx, _binding(_RecordingTransport()))
        self.assertEqual(caught.exception.code, "NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN")

    def test_the_real_discovery_serves_the_tool_only_while_the_binding_is_current(self) -> None:
        manager, scope = self._manager_in_home("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        state = {"current": True}
        binding = NativeDelegateBinding(
            transport=transport,
            currentness_guard=lambda: state["current"],
            profile_id="default",
            session_id="sess-1",
            command=COMMAND,
            job_id=JOB_ID,
        )
        adapter.register_native_delegate_tool(ctx, binding)

        definitions = self.upstream.registry.get_definitions({TOOL_NAME}, quiet=True)
        self.assertEqual([item["function"]["name"] for item in definitions], [TOOL_NAME])
        self.assertEqual(
            definitions[0]["function"]["parameters"]["properties"]["action"]["enum"],
            ["selected_child_status", "selected_child_submit"])

        state["current"] = False
        # The owner caches availability probes; invalidate so the stale verdict
        # is observed rather than the cached one.
        from tools.registry import invalidate_check_fn_cache
        invalidate_check_fn_cache()
        self.assertEqual(self.upstream.registry.get_definitions({TOOL_NAME}, quiet=True), [])

        # Discovery never authorizes: the stale binding still refuses at the
        # dispatch boundary, which re-checks the binding itself.
        body = json.loads(self.upstream.registry.dispatch(
            TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
            scope=scope, session_id="sess-1"))
        self.assertEqual(body["state"], "REFUSED")
        self.assertEqual(body["reason"], "NATIVE_BINDING_STALE")
        self.assertEqual(transport.calls, [])

    def test_the_installed_entry_is_reachable_from_its_own_profile_scope(self) -> None:
        manager, scope = self._manager_in_home("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        adapter.register_native_delegate_tool(ctx, _binding(transport))
        body = json.loads(self.upstream.registry.dispatch(
            TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
            session_id="sess-1"))
        self.assertEqual(body["state"], "ACTIVE")
        self.assertEqual(transport.calls, [("submit", COMMAND)])

    def test_the_real_route_key_bounds_the_caller(self) -> None:
        from gateway.session_context import scoped_session_key

        manager, scope = self._manager_in_home("profile-a")
        ctx = self._ctx(manager)
        transport = _RecordingTransport(_envelope())
        adapter.register_native_delegate_tool(
            ctx, _binding(transport, session_key="route-1"))
        with scoped_session_key("route-1"):
            body = json.loads(self.upstream.registry.dispatch(
                TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
                scope=scope, session_id="sess-1"))
            self.assertEqual(body["state"], "ACTIVE")
            self.assertEqual(transport.calls, [("submit", COMMAND)])
        with scoped_session_key("route-2"):
            body = json.loads(self.upstream.registry.dispatch(
                TOOL_NAME, {"action": "selected_child_submit", "command": COMMAND},
                scope=scope, session_id="sess-1"))
            self.assertEqual(body["state"], "REFUSED")
            self.assertEqual(body["reason"], "NATIVE_CALLER_SESSION_KEY_MISMATCH")
            self.assertEqual(transport.calls, [("submit", COMMAND)])


if __name__ == "__main__":
    unittest.main()
