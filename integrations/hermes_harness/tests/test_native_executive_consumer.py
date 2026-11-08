"""Focused proof of the native selected-child consumer startup.

Two layers. The *controlled* layer exercises the publication, the owner
slot, the one-RPC transport and the extension proof with disposable files
and a disposable MCP owner; it needs no installed role, no credential and no
network. The *native* layer exercises the real pinned ``PluginContext``,
``PluginManager`` and tool registry, and the real loader's one-argument
``register(ctx)`` call.

A fixture is never presented as an enrollment: the controlled layer proves
the consumer's own contracts, and the native layer proves that the upstream
loader really calls the plugin's ``register(ctx)`` and that the registration
is read back from the actual scoped entry.

The native layer runs only when a checkout of the pinned upstream is
available at ``MASTERMIND_HERMES_VENDOR_ROOT``; without it the native layer
skips with the exact reason and the controlled layer still runs.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_executive_consumer import (
    CONSUMER_MCP_SERVER,
    CONSUMER_PLUGIN_NAME,
    CONSUMER_PLUGIN_SOURCE,
    CONSUMER_SCHEMA,
    ConsumerSlot,
    NativeExecutiveTransport,
    publication_from_document,
    schema_digest,
    tools_schema_digest,
    validate_consumer_publication,
)
from integrations.hermes_harness.native_tool_registration import (
    NATIVE_TOOL_SCHEMA,
    SELECTED_CHILD_SCHEMA,
    NativeDelegateBinding,
    NativeDelegateRegistration,
    NativeDelegateStartup,
    native_delegate_handler,
)
from integrations.hermes_runtime.errors import RuntimeRefusal

VENDOR_ENV = "MASTERMIND_HERMES_VENDOR_ROOT"

COMMAND = "coo-cycle:ROOT1:dispatch:JOB1:attempt:1"
JOB_ID = "JOB1"
WORK_REF = "WS:EXEC1"

OWNER = "a" * 40
OTHER_OWNER = "b" * 40
TARGET_DIGEST = "1" * 64
TOOLS_DIGEST = "2" * 64
PLUGIN_DIGEST = "3" * 64


def publication_document(**overrides) -> dict:
    """One valid publication document; the shared fixture of this increment."""
    document = {
        "schema": CONSUMER_SCHEMA,
        "work_ref": WORK_REF,
        "command": COMMAND,
        "job_id": JOB_ID,
        "target_digest": TARGET_DIGEST,
        "root_job_id": "ROOT1",
        "mission_authority_ref": "mission:exec1",
        "authority_generation_digest": "4" * 64,
        "capability_profile_digest": "5" * 64,
        "principal_binding_digest": "6" * 64,
        "principal": {
            "policy_id": "exec-policy",
            "issuer_digest": "7" * 64,
            "subject_digest": "8" * 64,
            "client_ref": "9" * 64,
            "resource_ref": "https://coo.example/mcp/coo",
            "scopes": ["exec.read", "exec.write"],
        },
        "mcp": {
            "server": CONSUMER_MCP_SERVER,
            "url": "https://coo.example/mcp/coo",
            "client_id": "hermes-executive",
            "scope": "exec.read exec.write",
            "server_name": "mastermind-executive-coo",
            "server_version": "1.0.0",
        },
        "session": {
            "request_id": "enroll-1",
            "principal_id": "uid:1001",
            "role": "mmsecretary",
        },
        "plugin": {
            "name": CONSUMER_PLUGIN_NAME,
            "source": CONSUMER_PLUGIN_SOURCE,
            "digest": PLUGIN_DIGEST,
        },
        "tools_schema_digest": TOOLS_DIGEST,
    }
    document.update(overrides)
    return document


def _publication(**overrides):
    return publication_from_document(validate_consumer_publication(publication_document(**overrides)))


def _envelope(*, command: str = COMMAND, job_id: str = JOB_ID, state: str = "ACTIVE",
              target_digest: str = TARGET_DIGEST, live_submit: bool = True) -> dict:
    body = {
        "schema": SELECTED_CHILD_SCHEMA,
        "state": state,
        "reason": None,
        "command_id": command,
        "job_id": job_id,
        "attempt_id": "attempt-1",
        "attempt_status": "running",
        "job_status": "running",
        "live_submit": live_submit,
        "result_status": None,
        "result_envelope_digest": None,
        "terminal_evidence_digest": None,
        "target_digest": target_digest,
    }
    return body


class _Result:
    """One MCP tool result, shaped like the SDK's own object."""

    def __init__(self, structured=None, text=None, is_error: bool = False):
        self.structuredContent = structured
        self.content = [types.SimpleNamespace(text=text)] if text is not None else []
        self.isError = is_error


class _Session:
    """A disposable MCP session double that records every call."""

    def __init__(self, results=None, error=None):
        self.results = list(results or [])
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments=None, **kwargs):
        self.calls.append((name, dict(arguments or {})))
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return _Result(structured=_envelope())


class _Owner:
    """A disposable MCP owner with the incumbent RPC lock and inflight set."""

    def __init__(self, session):
        self.session = session
        self._rpc_lock = asyncio.Lock()
        self._inflight_tasks: set = set()


class _McpLoop:
    """A disposable MCP loop on its own thread, like the upstream one."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()


class PublicationTests(unittest.TestCase):
    def test_the_publication_is_a_closed_document(self) -> None:
        document = publication_document()
        self.assertEqual(validate_consumer_publication(document), document)
        for mutation in (
            {"extra": "member"},
            {"schema": "mastermind.hermes_native_executive_consumer/v2"},
        ):
            broken = dict(document)
            broken.update(mutation)
            with self.assertRaises(RuntimeRefusal):
                validate_consumer_publication(broken)
        missing = dict(document)
        missing.pop("target_digest")
        with self.assertRaises(RuntimeRefusal):
            validate_consumer_publication(missing)

    def test_the_publication_carries_no_credential(self) -> None:
        for member in ("bearer", "token", "client_secret", "authorization"):
            broken = publication_document()
            broken[member] = "secret"
            with self.assertRaises(RuntimeRefusal):
                validate_consumer_publication(broken)

    def test_the_command_must_name_the_frozen_job(self) -> None:
        with self.assertRaises(RuntimeRefusal):
            validate_consumer_publication(publication_document(job_id="OTHER"))

    def test_a_bundled_plugin_source_is_refused(self) -> None:
        with self.assertRaises(RuntimeRefusal):
            validate_consumer_publication(publication_document(plugin={
                "name": CONSUMER_PLUGIN_NAME, "source": "bundled", "digest": PLUGIN_DIGEST}))

    def test_remote_http_lookalikes_and_non_mcp_routes_refuse(self) -> None:
        for url in ("http://127.0.0.1evil.example/mcp", "http://127.0.0.1@evil.example/mcp",
                    "https://coo.example/other", "https://coo.example/mcp?token=public",
                    "https://coo.example/mcp#fragment"):
            document = publication_document()
            document["mcp"]["url"] = url
            with self.assertRaises(RuntimeRefusal):
                validate_consumer_publication(document)
        document = publication_document()
        document["mcp"]["url"] = "http://127.0.0.1:4010/mcp"
        self.assertEqual(validate_consumer_publication(document), document)

    def test_the_tools_schema_digest_covers_every_tool(self) -> None:
        first = types.SimpleNamespace(name="mmx_delegate", description="a",
                                       inputSchema={"type": "object"})
        second = types.SimpleNamespace(name="executive_mandate", description="b",
                                        inputSchema={"type": "object"})
        forward = tools_schema_digest([first, second])
        backward = tools_schema_digest([second, first])
        self.assertEqual(forward, backward)
        changed = tools_schema_digest([
            types.SimpleNamespace(name="mmx_delegate", description="a",
                                  inputSchema={"type": "object", "extra": 1}),
            second])
        self.assertNotEqual(forward, changed)


class _Transport:
    """A disposable transport double with the two closed entries."""

    def __init__(self, envelope=None):
        self.envelope = envelope if envelope is not None else _envelope()
        self.calls: list[tuple[str, str]] = []

    def submit_selected_child(self, command_id: str):
        self.calls.append(("submit", command_id))
        return self.envelope

    def selected_child_status(self, command_id: str):
        self.calls.append(("status", command_id))
        return self.envelope


class SlotTests(unittest.TestCase):
    def _slot(self, **overrides) -> ConsumerSlot:
        publication = _publication()
        binding = NativeDelegateBinding(
            transport=_Transport(),
            currentness_guard=lambda: True,
            profile_id=overrides.get("profile_id", "mmsecretary"),
            session_id="session-1",
            command=publication.command,
            job_id=publication.job_id,
        )
        return ConsumerSlot(
            owner=overrides.get("owner", OWNER),
            profile_id=overrides.get("profile_id", "mmsecretary"),
            source=overrides.get("source", CONSUMER_PLUGIN_SOURCE),
            plugin_id=overrides.get("plugin_id", CONSUMER_PLUGIN_NAME),
            publication=publication,
            startup=NativeDelegateStartup(binding=binding),
        )

    def test_an_unbound_slot_has_no_registration_or_load_attempt(self) -> None:
        slot = ConsumerSlot(owner=OWNER, profile_id="mmsecretary", source=CONSUMER_PLUGIN_SOURCE,
                            plugin_id=CONSUMER_PLUGIN_NAME, publication=_publication(),
                            startup=NativeDelegateStartup())
        self.assertIsNone(slot.startup.binding)
        self.assertIsNone(slot.registration)
        self.assertFalse(slot.load_attempted)
        with self.assertRaises(RuntimeRefusal):
            slot.bind_startup(NativeDelegateStartup())

    def test_the_slot_is_installed_once_and_never_retargeted(self) -> None:
        class _Manager:
            scope_key = "/profile"

        manager = _Manager()
        slot = self._slot()
        self.assertIs(consumer.install_consumer_slot(manager, slot), slot)
        self.assertIs(consumer.install_consumer_slot(manager, slot), slot)
        foreign = self._slot(owner=OTHER_OWNER)
        with self.assertRaises(RuntimeRefusal):
            consumer.install_consumer_slot(manager, foreign)

    def test_a_second_different_registration_is_refused(self) -> None:
        slot = self._slot()
        consumer.install_consumer_slot(types.SimpleNamespace(scope_key="/profile"), slot)
        registration = NativeDelegateRegistration(
            name="mmx_delegate", toolset="mmx_delegate", scope="/profile",
            profile_id="mmsecretary", session_id="session-1", command=COMMAND,
            job_id=JOB_ID, handler=lambda *a, **k: "", check_fn=lambda: True,
            handle=object(), entry=object())
        slot.publish_registration(registration)
        other = NativeDelegateRegistration(
            name="mmx_delegate", toolset="mmx_delegate", scope="/other",
            profile_id="mmsecretary", session_id="session-1", command=COMMAND,
            job_id=JOB_ID, handler=lambda *a, **k: "", check_fn=lambda: True,
            handle=object(), entry=object())
        with self.assertRaises(RuntimeRefusal):
            slot.publish_registration(other)
        self.assertIs(slot.registration, registration)


class TransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = _McpLoop()
        self.addCleanup(self.loop.close)

    def _transport(self, session=None, owner=None, *, current=True, trust=None,
                   publication=None):
        session = session if session is not None else _Session()
        owner = owner if owner is not None else _Owner(session)
        publication = publication if publication is not None else _publication()
        transport = NativeExecutiveTransport(
            publication=publication, server=owner, session=session,
            loop=self.loop.loop, timeout=5.0,
            currentness=(lambda: current), trust_gate=trust)
        return transport, session, owner

    def test_one_status_call_sends_exactly_one_request(self) -> None:
        transport, session, _ = self._transport()
        envelope = transport.selected_child_status(COMMAND)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][0], "mmx_delegate")
        self.assertEqual(session.calls[0][1], {"action": "selected_child_status",
                                               "command": COMMAND})
        self.assertEqual(envelope["command_id"], COMMAND)
        self.assertEqual(envelope["target_digest"], TARGET_DIGEST)

    def test_a_pre_send_refusal_is_a_proved_no_effect(self) -> None:
        transport, session, _ = self._transport(current=False)
        envelope = transport.selected_child_status(COMMAND)
        self.assertEqual(session.calls, [])
        self.assertEqual(envelope["state"], "REFUSED")
        self.assertEqual(envelope["live_submit"], False)
        self.assertEqual(envelope["command_id"], COMMAND)

    def test_the_trust_gate_refuses_before_any_transport_work(self) -> None:
        transport, session, _ = self._transport(trust=lambda: "gated")
        envelope = transport.selected_child_status(COMMAND)
        self.assertEqual(session.calls, [])
        self.assertEqual(envelope["state"], "REFUSED")

    def test_a_foreign_command_never_reaches_the_transport(self) -> None:
        transport, session, _ = self._transport()
        envelope = transport.selected_child_status("coo-cycle:ROOT1:dispatch:JOB2:attempt:1")
        self.assertEqual(session.calls, [])
        self.assertEqual(envelope["state"], "REFUSED")

    def test_a_lost_response_keeps_the_original_command(self) -> None:
        session = _Session(error=RuntimeError("connection lost"))
        transport, _, _ = self._transport(session=session)
        with self.assertRaises(Exception):
            transport.submit_selected_child(COMMAND)
        self.assertEqual(len(session.calls), 1)

    def test_a_wrong_target_digest_is_never_projected(self) -> None:
        session = _Session(results=[_Result(structured=_envelope(target_digest="f" * 64))])
        transport, _, _ = self._transport(session=session)
        with self.assertRaises(Exception):
            transport.selected_child_status(COMMAND)

    def test_an_is_error_result_is_not_proof(self) -> None:
        session = _Session(results=[_Result(structured=_envelope(), is_error=True)])
        transport, _, _ = self._transport(session=session)
        with self.assertRaises(Exception):
            transport.selected_child_status(COMMAND)

    def test_a_text_only_result_is_unwrapped(self) -> None:
        session = _Session(results=[_Result(text=json.dumps(_envelope()))])
        transport, _, _ = self._transport(session=session)
        envelope = transport.selected_child_status(COMMAND)
        self.assertEqual(envelope["command_id"], COMMAND)

    def test_the_c28_adapter_maps_a_submit_failure_to_effect_unknown(self) -> None:
        session = _Session(error=RuntimeError("connection lost"))
        transport, _, _ = self._transport(session=session)
        publication = _publication()
        binding = NativeDelegateBinding(
            transport=transport, currentness_guard=lambda: True,
            profile_id="mmsecretary", session_id="session-1",
            command=publication.command, job_id=publication.job_id)
        handler = native_delegate_handler(binding)
        body = json.loads(handler({"action": "selected_child_submit", "command": COMMAND},
                                  session_id="session-1"))
        self.assertEqual(body["state"], "EFFECT_UNKNOWN")
        self.assertEqual(body["command_id"], COMMAND)
        self.assertIsNone(body["live_submit"])
        self.assertEqual(len(session.calls), 1)

    def test_the_c28_adapter_maps_a_status_failure_to_unavailable(self) -> None:
        session = _Session(error=RuntimeError("connection lost"))
        transport, _, _ = self._transport(session=session)
        publication = _publication()
        binding = NativeDelegateBinding(
            transport=transport, currentness_guard=lambda: True,
            profile_id="mmsecretary", session_id="session-1",
            command=publication.command, job_id=publication.job_id)
        handler = native_delegate_handler(binding)
        body = json.loads(handler({"action": "selected_child_status", "command": COMMAND},
                                  session_id="session-1"))
        self.assertEqual(body["state"], "UNAVAILABLE")
        self.assertEqual(body["command_id"], COMMAND)

    def test_a_replaced_session_is_never_called(self) -> None:
        session = _Session()
        owner = _Owner(session)
        transport, _, _ = self._transport(session=session, owner=owner)
        owner.session = _Session()
        with self.assertRaises(Exception):
            transport.selected_child_status(COMMAND)


class ConfigTests(unittest.TestCase):
    def test_the_consumer_entry_has_an_empty_filter_and_no_credential(self) -> None:
        from integrations.hermes_harness.native_mcp import (
            render_consumer_mcp_server,
            render_consumer_plugin_config,
        )

        publication = _publication()
        server = render_consumer_mcp_server(publication)
        self.assertEqual(server["tools"]["include"], [])
        self.assertFalse(server["tools"]["resources"])
        self.assertFalse(server["tools"]["prompts"])
        self.assertEqual(server["auth"], "oauth")
        self.assertEqual(server["oauth"]["client_id"], "hermes-executive")
        self.assertNotIn("client_secret", server["oauth"])
        self.assertNotIn("headers", server)
        plugins = render_consumer_plugin_config(publication)
        self.assertEqual(plugins["enabled"], [CONSUMER_PLUGIN_NAME])
        self.assertEqual(plugins["entries"][CONSUMER_PLUGIN_NAME]["mcp_allowlist"],
                         [CONSUMER_MCP_SERVER])

    def test_the_consumer_config_matches_the_approved_facts(self) -> None:
        publication = _publication()
        config = {"url": publication.mcp.url, "auth": "oauth",
                  "oauth": {"client_id": publication.mcp.client_id,
                            "scope": publication.mcp.scope}}
        self.assertTrue(publication.mcp.matches_config(config))
        self.assertFalse(publication.mcp.matches_config(
            {"url": publication.mcp.url, "auth": "oauth",
             "oauth": {"client_id": "other", "scope": publication.mcp.scope}}))
        self.assertFalse(publication.mcp.matches_config({"url": publication.mcp.url}))


class ExtensionProofTests(unittest.TestCase):
    def test_a_missing_extension_keeps_the_hold(self) -> None:
        from integrations.hermes_runtime.registry import (
            assert_extension_proof_exact,
            inspect_extension_proof,
        )

        verdict = inspect_extension_proof(
            {"tool": "mmx_delegate", "present": False, "scope": "/profile"},
            expected_tool="mmx_delegate")
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertFalse(verdict["installed"])
        with self.assertRaises(RuntimeRefusal) as caught:
            assert_extension_proof_exact(
                {"tool": "mmx_delegate", "present": False, "scope": "/profile"},
                expected_tool="mmx_delegate")
        self.assertEqual(caught.exception.code, "NATIVE_EXTENSION_NOT_INSTALLED")

    def test_a_proved_entry_passes(self) -> None:
        from integrations.hermes_runtime.registry import assert_extension_proof_exact

        observed = {
            "tool": "mmx_delegate", "present": True, "scope": "/profile",
            "schema_sha256": schema_digest(NATIVE_TOOL_SCHEMA),
        }
        verdict = assert_extension_proof_exact(
            observed, expected_tool="mmx_delegate",
            expected_schema_sha256=schema_digest(NATIVE_TOOL_SCHEMA),
            expected_scope="/profile")
        self.assertTrue(verdict["installed"])

    def test_a_stale_schema_keeps_the_hold(self) -> None:
        from integrations.hermes_runtime.registry import inspect_extension_proof

        verdict = inspect_extension_proof(
            {"tool": "mmx_delegate", "present": True, "scope": "/profile",
             "schema_sha256": "f" * 64},
            expected_tool="mmx_delegate", expected_schema_sha256="e" * 64)
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertIn("EXTENSION_SCHEMA_MISMATCH", verdict["issues"])


def _installation(*, consumer=None, role: str = "mmsecretary") -> dict:
    """One hermes runtime installation document with an optional consumer."""
    native = {
        "schema": "mastermind.hermes_native_gateway_installation/v2",
        "python": {"path": "/usr/bin/python3.12", "real_path": "/usr/bin/python3.12",
                   "sha256": "e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f"},
        "startup": {
            "profile": "cpython-3.12-linux-root-prefix-nosite.v1", "prefix": "/usr",
            "exec_prefix": "/usr", "base_prefix": "/usr", "base_exec_prefix": "/usr"},
        "vendor_root": "/opt/hermes/vendor",
        "import_roots": ["/opt/hermes/vendor"],
        "dependency_inventory": {"path": "/opt/hermes/inventory.json",
                                 "sha256": "a" * 64, "size": 4096},
        "session_enrollment": {
            "schema": "mastermind.hermes_secretary_session_enrollment/v1",
            "request_id": "enroll-1"},
    }
    if consumer is not None:
        native["schema"] = "mastermind.hermes_native_gateway_installation/v3"
        native["executive_consumer"] = consumer
    roles = [
        {"role": "mmmeta", "uid": 993, "gid": 980,
         "state_dir": "/home/mmmeta/.local/state/hermes-runtime-mmmeta",
         "restart_sec": 2, "start_limit_burst": 5, "start_limit_interval_sec": 60},
        {"role": "mmsecretary", "uid": 994, "gid": 981,
         "state_dir": "/home/mmsecretary/.local/state/hermes-runtime-mmsecretary",
         "restart_sec": 2, "start_limit_burst": 5, "start_limit_interval_sec": 60},
    ]
    for row in roles:
        if row["role"] == role:
            row["native_gateway"] = json.loads(json.dumps(native))
    return {
        "schema": "mastermind.hermes_runtime_installation/v1",
        "bootstrap_python": native["python"],
        "launch_python": native["python"],
        "startup": native["startup"],
        "roles": roles,
    }


class InstallationTests(unittest.TestCase):
    def test_the_v3_member_carries_the_consumer(self) -> None:
        from ops.executive_os.release_manifest import validate_hermes_runtime_installation

        document = _installation(consumer=publication_document())
        validated = validate_hermes_runtime_installation(document)
        secretary = next(row for row in validated["roles"] if row["role"] == "mmsecretary")
        self.assertIn("executive_consumer", secretary["native_gateway"])
        self.assertEqual(secretary["native_gateway"]["executive_consumer"],
                         publication_document())

    def test_the_absent_member_leaves_the_older_installations_unchanged(self) -> None:
        from ops.executive_os.release_manifest import validate_hermes_runtime_installation

        validated = validate_hermes_runtime_installation(_installation())
        secretary = next(row for row in validated["roles"] if row["role"] == "mmsecretary")
        self.assertNotIn("executive_consumer", secretary["native_gateway"])
        self.assertEqual(secretary["native_gateway"]["schema"],
                         "mastermind.hermes_native_gateway_installation/v2")

    def test_the_consumer_requires_the_secretary_role(self) -> None:
        from ops.executive_os.release_manifest import (
            ReleaseManifestError,
            validate_hermes_runtime_installation,
        )

        with self.assertRaises(ReleaseManifestError):
            validate_hermes_runtime_installation(
                _installation(consumer=publication_document(), role="mmmeta"))

    def test_a_malformed_consumer_member_is_refused(self) -> None:
        from ops.executive_os.release_manifest import (
            ReleaseManifestError,
            validate_hermes_runtime_installation,
        )

        broken = publication_document()
        broken["extra"] = "member"
        with self.assertRaises(ReleaseManifestError):
            validate_hermes_runtime_installation(_installation(consumer=broken))

    def test_plugin_code_stays_outside_the_role_owned_home(self) -> None:
        from integrations.hermes_harness.native_executive_consumer import (
            plugin_package_digest,
        )
        from integrations.hermes_runtime.install import _install_consumer_plugin

        source = (Path(__file__).resolve().parents[1] / CONSUMER_PLUGIN_NAME)
        digest = plugin_package_digest(source)
        document = publication_document()
        document["plugin"] = dict(document["plugin"], digest=digest)
        with tempfile.TemporaryDirectory() as name:
            role_dir = Path(name) / "profiles" / "mmsecretary"
            role_dir.mkdir(parents=True)
            installed = _install_consumer_plugin(role_dir, document)
            self.assertEqual(installed, digest)
            target = role_dir / "plugins" / CONSUMER_PLUGIN_NAME
            self.assertFalse(target.exists())
            target.mkdir(parents=True)
            with self.assertRaises(RuntimeRefusal):
                _install_consumer_plugin(role_dir, document)

    def test_an_unsealed_plugin_source_is_refused(self) -> None:
        from integrations.hermes_runtime.install import _install_consumer_plugin

        document = publication_document()
        with tempfile.TemporaryDirectory() as name:
            role_dir = Path(name) / "profiles" / "mmsecretary"
            role_dir.mkdir(parents=True)
            with self.assertRaises(RuntimeRefusal) as caught:
                _install_consumer_plugin(role_dir, document)
            self.assertEqual(caught.exception.code,
                             "NATIVE_CONSUMER_PLUGIN_SOURCE_MISMATCH")


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


class NativePluginLoaderTests(unittest.TestCase):
    """The real pinned loader, the real ``register(ctx)`` and the real registry."""

    @classmethod
    def setUpClass(cls) -> None:
        root = _vendor_root()
        if root is None:
            raise unittest.SkipTest(
                f"{VENDOR_ENV} does not name a checkout of the pinned upstream")
        cls.vendor = root
        cls.upstream = _Upstream(root)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self._native_managers = {}
        self.home = self.root / "profiles" / "mmsecretary"
        self.home.mkdir(parents=True, exist_ok=True)
        environment = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.home)

        def restore() -> None:
            if environment is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = environment

        self.addCleanup(restore)
        from integrations.hermes_runtime import native_session_control

        self.control = native_session_control
        native_session_control.install_runtime_owner(OWNER)

    def _manager(self, name: str):
        """One manager for one named profile under the same Hermes root."""
        scope = self.root / "profiles" / name
        scope.mkdir(parents=True, exist_ok=True)
        os.environ["HERMES_HOME"] = str(scope)
        manager = self.upstream.PluginManager(scope_key=str(scope))
        self._native_managers[name] = manager
        return manager, str(scope)

    def _grant_mcp(self):
        """Grant the plugin its one server, as the installed config would.

        The grant is read by the upstream owner from the profile config. In
        this environment the YAML library is an import-only shim, so the
        config cannot be parsed; the grant itself is stubbed at the upstream
        owner and the default-deny refusal is proved separately.
        """
        from unittest import mock

        return mock.patch.object(
            self.upstream.PluginContext, "_mcp_allowlist",
            staticmethod(lambda plugin_id: [CONSUMER_MCP_SERVER]))

    def _manifest(self, path: Path, source: str = CONSUMER_PLUGIN_SOURCE):
        return self.upstream.PluginManifest(
            name=CONSUMER_PLUGIN_NAME, version="1", source=source, path=str(path),
            provides_tools=["mmx_delegate"], key=CONSUMER_PLUGIN_NAME)

    def _plugin_dir(self, name: str) -> Path:
        """The real plugin package, installed as the loader will find it."""
        import shutil

        source = (Path(__file__).resolve().parents[1] / CONSUMER_PLUGIN_NAME)
        target = self.root / "plugins" / name / CONSUMER_PLUGIN_NAME
        target.mkdir(parents=True, exist_ok=True)
        for member in ("plugin.yaml", "__init__.py"):
            shutil.copyfile(source / member, target / member)
        manager = self._native_managers.get(name)
        slot = getattr(manager, consumer.CONSUMER_SLOT_ATTRIBUTE, None)
        if isinstance(slot, ConsumerSlot):
            slot.package_path = str(target)
            slot.package_check = lambda: consumer.plugin_package_digest(target) == slot.publication.plugin.digest
        return target

    def _slot(self, profile_id: str = "mmsecretary", owner: str = OWNER) -> ConsumerSlot:
        source = Path(__file__).resolve().parents[1] / CONSUMER_PLUGIN_NAME
        publication = _publication(plugin={"name": CONSUMER_PLUGIN_NAME,
            "source": CONSUMER_PLUGIN_SOURCE, "digest": consumer.plugin_package_digest(source)})
        binding = NativeDelegateBinding(
            transport=_Transport(), currentness_guard=lambda: True,
            profile_id=profile_id, session_id="session-1",
            command=publication.command, job_id=publication.job_id)
        return ConsumerSlot(owner=owner, profile_id=profile_id,
                            source=CONSUMER_PLUGIN_SOURCE, plugin_id=CONSUMER_PLUGIN_NAME,
                            publication=publication,
                            startup=NativeDelegateStartup(binding=binding))

    def test_the_vendor_is_the_pinned_upstream(self) -> None:
        from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA

        try:
            head = subprocess.run(
                ["git", "-C", str(self.vendor), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is unavailable; the upstream pin cannot be attested here")
        if head.returncode:
            self.skipTest("the vendor root is not a git checkout")
        self.assertEqual(head.stdout.strip(), PINNED_UPSTREAM_SHA)

    def test_an_unbound_discovery_exposes_no_tool(self) -> None:
        manager, scope = self._manager("unbound")
        ctx = self.upstream.PluginContext(self._manifest(self.home), manager)
        with self.assertRaises(Exception):
            consumer.read_consumer_slot(
                ctx, owner=OWNER, source=CONSUMER_PLUGIN_SOURCE,
                plugin_id=CONSUMER_PLUGIN_NAME)
        self.assertIsNone(self.upstream.registry.snapshot_registration(
            "mmx_delegate", scope=scope))

    def test_the_real_loader_calls_register_with_one_argument(self) -> None:
        manager, scope = self._manager("loaded")
        consumer.install_consumer_slot(manager, self._slot(profile_id="loaded"))
        path = self._plugin_dir("loaded")
        manifest = self._manifest(path)
        with self._grant_mcp():
            # The real loader calls ``register(ctx)`` with one argument only.
            manager._load_plugin(manifest)
        entry = self.upstream.registry.snapshot_registration("mmx_delegate", scope=scope)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.toolset, "mmx_delegate")
        self.assertEqual(entry.schema, NATIVE_TOOL_SCHEMA)
        self.assertIsNotNone(entry.check_fn)
        loaded = manager._plugins.get(CONSUMER_PLUGIN_NAME)
        self.assertTrue(loaded.enabled)
        self.assertEqual(loaded.error, None)

    def test_the_plugin_refuses_without_the_mcp_grant(self) -> None:
        manager, scope = self._manager("ungranted")
        consumer.install_consumer_slot(manager, self._slot(profile_id="ungranted"))
        path = self._plugin_dir("ungranted")
        manager._load_plugin(self._manifest(path))
        self.assertIsNone(self.upstream.registry.snapshot_registration(
            "mmx_delegate", scope=scope))
        loaded = manager._plugins.get(CONSUMER_PLUGIN_NAME)
        self.assertFalse(loaded.enabled)
        self.assertIsNotNone(loaded.error)

    def test_a_foreign_profile_cannot_read_the_slot(self) -> None:
        manager, _ = self._manager("foreign")
        consumer.install_consumer_slot(manager, self._slot(profile_id="mmsecretary"))
        ctx = self.upstream.PluginContext(self._manifest(self.home), manager)
        with self.assertRaises(Exception) as caught:
            consumer.read_consumer_slot(
                ctx, owner=OWNER, source=CONSUMER_PLUGIN_SOURCE,
                plugin_id=CONSUMER_PLUGIN_NAME)
        self.assertEqual(getattr(caught.exception, "code", None), "NATIVE_PROFILE_MISMATCH")

    def test_a_foreign_owner_cannot_read_the_slot(self) -> None:
        manager, _ = self._manager("foreign-owner")
        consumer.install_consumer_slot(manager, self._slot(owner=OWNER))
        ctx = self.upstream.PluginContext(self._manifest(self.home), manager)
        with self.assertRaises(Exception) as caught:
            consumer.read_consumer_slot(
                ctx, owner=OTHER_OWNER, source=CONSUMER_PLUGIN_SOURCE,
                plugin_id=CONSUMER_PLUGIN_NAME)
        self.assertEqual(getattr(caught.exception, "code", None),
                         "NATIVE_CONSUMER_SLOT_FOREIGN")

    def test_a_bundled_manifest_cannot_read_the_slot(self) -> None:
        manager, _ = self._manager("bundled")
        consumer.install_consumer_slot(manager, self._slot())
        ctx = self.upstream.PluginContext(
            self._manifest(self.home, source="bundled"), manager)
        with self.assertRaises(Exception) as caught:
            consumer.read_consumer_slot(
                ctx, owner=OWNER, source=CONSUMER_PLUGIN_SOURCE,
                plugin_id=CONSUMER_PLUGIN_NAME)
        self.assertEqual(getattr(caught.exception, "code", None),
                         "NATIVE_CONSUMER_PLUGIN_SOURCE_MISMATCH")

    def test_two_profiles_keep_two_separate_registrations(self) -> None:
        first, first_scope = self._manager("profile-a")
        consumer.install_consumer_slot(first, self._slot(profile_id="profile-a"))
        with self._grant_mcp():
            first._load_plugin(self._manifest(self._plugin_dir("profile-a")))
        second, second_scope = self._manager("profile-b")
        consumer.install_consumer_slot(second, self._slot(profile_id="profile-b"))
        with self._grant_mcp():
            second._load_plugin(self._manifest(self._plugin_dir("profile-b")))
        one = self.upstream.registry.snapshot_registration("mmx_delegate", scope=first_scope)
        two = self.upstream.registry.snapshot_registration("mmx_delegate", scope=second_scope)
        self.assertIsNotNone(one)
        self.assertIsNotNone(two)
        self.assertIsNot(one.handler, two.handler)

    def test_the_unload_releases_the_owner_lease(self) -> None:
        manager, scope = self._manager("unload")
        consumer.install_consumer_slot(manager, self._slot(profile_id="unload"))
        with self._grant_mcp():
            manager._load_plugin(self._manifest(self._plugin_dir("unload")))
        self.assertIsNotNone(self.upstream.registry.snapshot_registration(
            "mmx_delegate", scope=scope))
        manager.unload()
        self.assertIsNone(self.upstream.registry.snapshot_registration(
            "mmx_delegate", scope=scope))

    def test_the_empty_include_filter_denies_every_tool(self) -> None:
        from tools.mcp_tool_registration import _make_tool_filter

        should_register = _make_tool_filter(
            CONSUMER_MCP_SERVER, {"tools": {"include": []}})
        self.assertFalse(should_register("mmx_delegate"))
        self.assertFalse(should_register("executive_mandate"))
        # An absent filter is not an empty one: it registers everything.
        permissive = _make_tool_filter(CONSUMER_MCP_SERVER, {"tools": {}})
        self.assertTrue(permissive("mmx_delegate"))

    def test_the_runtime_owner_is_bound_exactly_once(self) -> None:
        self.assertEqual(self.control.current_runtime_owner(), OWNER)
        with self.assertRaises(RuntimeRefusal):
            self.control.install_runtime_owner(OTHER_OWNER)
        self.assertEqual(self.control.current_runtime_owner(), OWNER)


if __name__ == "__main__":
    unittest.main()

# C46 controlled integration regressions. These fixtures do not claim an
# installed enrollment, root-owned source custody, or a provider turn.
def test_native_tools_digest_matches_the_capability_owner():
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    first = types.SimpleNamespace(
        name="mmx_delegate", description="old prose", inputSchema={"type": "object"},
        outputSchema={"type": "object"}, annotations={"readOnlyHint": False})
    expected = observed_mcp_tool_schema_digest({"tools": {"mmx_delegate": {
        "name": first.name, "inputSchema": first.inputSchema,
        "outputSchema": first.outputSchema, "annotations": first.annotations}}})
    assert tools_schema_digest([first]) == expected
    first.description = "new prose"
    assert tools_schema_digest([first]) == expected
    first.annotations = {"readOnlyHint": True}
    assert tools_schema_digest([first]) != expected


def test_native_transport_accepts_closed_digest_free_local_uncertainty():
    loop = _McpLoop()
    try:
        for action, state, reason in (
            ("selected_child_submit", "EFFECT_UNKNOWN", "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN"),
            ("selected_child_status", "UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE")):
            local = {"schema": SELECTED_CHILD_SCHEMA, "state": state, "reason": reason,
                     "command_id": COMMAND, "job_id": None, "attempt_id": None,
                     "attempt_status": None, "job_status": None, "live_submit": None}
            session = _Session(results=[_Result(structured=local)])
            transport = NativeExecutiveTransport(
                publication=_publication(), server=_Owner(session), session=session,
                loop=loop.loop, currentness=lambda: True)
            result = transport._call(action, COMMAND)
            assert result == local
            assert "target_digest" not in result
            assert len(session.calls) == 1
    finally:
        loop.close()


def test_native_transport_rejects_contradictory_control_effect_evidence():
    import pytest
    loop = _McpLoop()
    try:
        for state, attempt, live in (
                ("ACTIVE", None, False), ("NOT_CLAIMED", None, True),
                ("EFFECT_UNKNOWN", None, False), ("ACTIVE", "attempt-1", None)):
            body = _envelope(state=state, live_submit=live)
            body["attempt_id"] = attempt
            if attempt is None:
                body["attempt_status"] = body["job_status"] = None
            session = _Session(results=[_Result(structured=body)])
            transport = NativeExecutiveTransport(
                publication=_publication(), server=_Owner(session), session=session,
                loop=loop.loop, currentness=lambda: True)
            with pytest.raises(consumer._ConsumerUncertain):
                transport.submit_selected_child(COMMAND)
            assert len(session.calls) == 1
    finally:
        loop.close()


def test_native_rpc_rechecks_the_session_after_waiting_for_its_lock():
    import concurrent.futures
    import pytest
    loop = _McpLoop()
    try:
        session = _Session()
        owner = _Owner(session)
        held = threading.Event()
        release = asyncio.Event()
        async def hold():
            async with owner._rpc_lock:
                held.set()
                await release.wait()
        holder = asyncio.run_coroutine_threadsafe(hold(), loop.loop)
        assert held.wait(2)
        before_queue = threading.Event()
        def current():
            before_queue.set()
            return True
        transport = NativeExecutiveTransport(
            publication=_publication(), server=owner, session=session,
            loop=loop.loop, currentness=current, timeout=3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(transport.submit_selected_child, COMMAND)
            assert before_queue.wait(2)
            owner.session = _Session()
            loop.loop.call_soon_threadsafe(release.set)
            holder.result(timeout=2)
            with pytest.raises(consumer._ConsumerUncertain):
                result.result(timeout=3)
        assert session.calls == []
        assert owner.session.calls == []
    finally:
        loop.close()


def test_native_rpc_late_revocation_returns_original_uncertainty():
    loop = _McpLoop()
    try:
        for action, state in (("selected_child_submit", "EFFECT_UNKNOWN"),
                              ("selected_child_status", "UNAVAILABLE")):
            live = {"current": True}
            class LateSession(_Session):
                async def call_tool(self, name, arguments=None, **kwargs):
                    result = await super().call_tool(name, arguments, **kwargs)
                    live["current"] = False
                    return result
            session = LateSession()
            transport = NativeExecutiveTransport(
                publication=_publication(), server=_Owner(session), session=session,
                loop=loop.loop, currentness=lambda: live["current"])
            binding = NativeDelegateBinding(
                transport=transport, currentness_guard=lambda: True,
                profile_id="mmsecretary", session_id="session-1", command=COMMAND, job_id=JOB_ID)
            result = json.loads(native_delegate_handler(binding)(
                {"action": action, "command": COMMAND}, session_id="session-1"))
            assert result["state"] == state
            assert result["command_id"] == COMMAND and result["job_id"] == JOB_ID
            assert result["live_submit"] is None
            assert len(session.calls) == 1
    finally:
        loop.close()


def test_captured_mcp_guard_rejects_registry_config_and_handshake_replacement(monkeypatch):
    loop = _McpLoop()
    try:
        document = publication_document()
        tool = types.SimpleNamespace(name="mmx_delegate", inputSchema={"type": "object"},
                                     outputSchema=None, annotations=None)
        document["tools_schema_digest"] = tools_schema_digest([tool])
        publication = publication_from_document(document)
        session = _Session()
        owner = _Owner(session)
        owner._tools = [tool]
        owner._config = {"url": publication.mcp.url, "auth": "oauth",
                         "oauth": {"client_id": publication.mcp.client_id, "scope": publication.mcp.scope}}
        owner.initialize_result = types.SimpleNamespace(serverInfo=types.SimpleNamespace(
            name=publication.mcp.server_name, version=publication.mcp.server_version))
        core = types.ModuleType("tools.mcp_tool")
        core._lock = threading.RLock()
        core._servers = {"profile::coo": owner}
        package = types.ModuleType("tools")
        package.mcp_tool = core
        loops = types.ModuleType("tools.mcp_tool_loop")
        loops._running_loop = lambda: loop.loop
        scopes = types.ModuleType("tools.mcp_tool_scope")
        scopes._resolve_server_key = lambda _name: "profile::coo"
        for name, module in {"tools": package, "tools.mcp_tool": core,
                             "tools.mcp_tool_loop": loops, "tools.mcp_tool_scope": scopes}.items():
            monkeypatch.setitem(sys.modules, name, module)
        captured = consumer.capture_native_mcp_owner(publication, include_guard=True)
        assert captured[:3] == (owner, session, loop.loop)
        guard = captured[3]
        assert guard() is True
        core._servers["profile::coo"] = _Owner(session)
        assert guard() is False
        core._servers["profile::coo"] = owner
        owner._config["url"] = "https://foreign.example/mcp"
        assert guard() is False
        owner._config["url"] = publication.mcp.url
        owner.initialize_result.serverInfo.version = "foreign"
        assert guard() is False
        owner.initialize_result.serverInfo.version = publication.mcp.server_version
        tool.annotations = {"readOnlyHint": True}
        assert guard() is False
    finally:
        loop.close()


def test_registration_uncertainty_retains_original_context_and_does_not_reload(monkeypatch):
    from integrations.hermes_harness import native_selected_child_plugin as plugin
    from integrations.hermes_harness.native_tool_registration import NativeToolRegistrationError
    publication = _publication()
    manifest = types.SimpleNamespace(name=CONSUMER_PLUGIN_NAME, source=CONSUMER_PLUGIN_SOURCE,
                                     path="/held/package")
    manager = types.SimpleNamespace(scope_key="/profile", _plugins={})
    context = types.SimpleNamespace(
        _manager=manager, manifest=manifest, profile_name="mmsecretary",
        plugin_id=CONSUMER_PLUGIN_NAME, _mcp_allowlist=lambda _name: [CONSUMER_MCP_SERVER])
    binding = NativeDelegateBinding(
        transport=_Transport(), currentness_guard=lambda: True, profile_id="mmsecretary",
        session_id="session-1", command=COMMAND, job_id=JOB_ID)
    counts = {"qualify": 0, "load": 0, "register": 0}
    def qualify(**_kwargs):
        counts["qualify"] += 1
        return binding
    def uncertain(ctx, startup):
        counts["register"] += 1
        raise NativeToolRegistrationError("NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN",
                                          context=ctx, binding=startup.binding,
                                          scope=manager.scope_key)
    def load(manifest):
        counts["load"] += 1
        try:
            plugin.register(context)
        except Exception as error:
            manager._plugins[CONSUMER_PLUGIN_NAME] = types.SimpleNamespace(
                enabled=False, error=str(error), manifest=manifest)
    manager._load_plugin = load
    monkeypatch.setattr(consumer, "qualify_executive_consumer", qualify)
    monkeypatch.setattr(plugin, "current_runtime_owner", lambda: OWNER)
    monkeypatch.setattr(plugin, "register_native_delegate_tools", uncertain)
    arguments = dict(manager=manager, publication=publication, owner=OWNER, profile_id="mmsecretary",
                     session_id="session-1", instance_id="instance-1", authority_epoch=1,
                     route="route-1", server=None, session=None, loop=None,
                     session_guard=lambda: True, manifest=manifest, package_check=lambda: True)
    slot = consumer.install_native_consumer(**arguments)
    assert slot is getattr(manager, consumer.CONSUMER_SLOT_ATTRIBUTE)
    assert slot.load_outcome == "EFFECT_UNKNOWN"
    assert slot.registration_context is context and slot.registration_binding is binding
    assert slot.registration_error.original_context is context
    assert slot.registration_error.original_binding is binding
    assert slot.registration_error.original_scope == "/profile"
    assert consumer.install_native_consumer(**arguments) is slot
    assert counts == {"qualify": 1, "load": 1, "register": 1}
    import pytest
    with pytest.raises(RuntimeRefusal):
        consumer.install_native_consumer(**dict(arguments, publication=_publication(target_digest="f" * 64)))
    assert counts["load"] == 1


def test_v3_consumer_joins_enrollment_request_and_actual_role():
    import pytest
    from ops.executive_os.release_manifest import ReleaseManifestError, validate_hermes_runtime_installation
    for key, value in (("request_id", "foreign-request"), ("role", "mmmeta")):
        document = publication_document()
        document["session"][key] = value
        with pytest.raises(ReleaseManifestError):
            validate_hermes_runtime_installation(_installation(consumer=document))


def test_provider_import_boundary_excludes_foreign_code_and_preserves_native_rows(tmp_path, monkeypatch):
    import pytest
    from integrations.hermes_runtime import native_gateway_entry as gateway
    vendor = tmp_path / "vendor"
    package = vendor / "providers"
    bundled = vendor / "plugins/model-providers"
    builtin = bundled / "builtin"
    package.mkdir(parents=True)
    builtin.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    foreign = tmp_path / "role/plugins/foreign"
    foreign.mkdir(parents=True)
    providers = types.ModuleType("providers")
    providers.__file__ = str(package / "__init__.py")
    providers.__path__ = [str(package)]
    providers._BUNDLED_PLUGINS_DIR = bundled
    providers._discovered = providers._discovering = False
    for name in ("_REGISTRY", "_ALIASES", "_SOURCES", "_HOME_LAYERS"):
        setattr(providers, name, {})
    original_registry = providers._REGISTRY
    calls = []
    providers._import_plugin_dir = lambda path, source, **kw: calls.append((path, source, kw))
    providers._discover_entry_point_providers = lambda: calls.append("entry-point-import")
    monkeypatch.setitem(sys.modules, "providers", providers)
    launch = types.SimpleNamespace(recipe={"executive_consumer": publication_document()},
                                   check=lambda: None)
    gateway._bind_consumer_provider_imports(launch, vendor)
    assert providers._import_plugin_dir(foreign, "user", home_key=str(tmp_path / "role")) is None
    assert providers._discover_entry_point_providers() is None
    assert calls == []
    with pytest.raises(RuntimeRefusal):
        providers._import_plugin_dir(foreign, "bundled")
    alias = bundled / "alias"
    alias.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(RuntimeRefusal):
        providers._import_plugin_dir(alias, "bundled")
    providers._import_plugin_dir(builtin, "bundled")
    assert calls == [(builtin, "bundled", {"home_key": ""})]
    assert providers._REGISTRY is original_registry
    assert providers._discovered is False
    with pytest.raises(RuntimeRefusal):
        gateway._bind_consumer_provider_imports(launch, vendor)

def test_serving_proof_cannot_borrow_a_foreign_same_schema_registration(tmp_path, monkeypatch):
    import pytest
    from integrations.hermes_runtime import native_session_control as control
    publication = _publication()
    home = tmp_path / "role"
    manager = types.SimpleNamespace(scope_key=str(home), _plugins={})
    server = _Owner(_Session())
    guard = consumer.NativeConsumerCurrentness(
        publication=publication, session_id="session-1", instance_id="instance-1",
        authority_epoch=1, server=server, session=server.session, guard=lambda: True)
    binding = NativeDelegateBinding(
        transport=_Transport(), currentness_guard=guard, profile_id="mmsecretary",
        session_id="session-1", command=COMMAND, job_id=JOB_ID)
    slot = consumer.install_consumer_slot(manager, ConsumerSlot(
        owner=OWNER, profile_id="mmsecretary", source=CONSUMER_PLUGIN_SOURCE,
        plugin_id=CONSUMER_PLUGIN_NAME, publication=publication,
        startup=NativeDelegateStartup(binding=binding)))
    handler = native_delegate_handler(binding)
    check = lambda: True
    entry = types.SimpleNamespace(handler=handler, check_fn=check,
                                  toolset="mmx_delegate", schema=NATIVE_TOOL_SCHEMA)
    registration = NativeDelegateRegistration(
        name="mmx_delegate", toolset="mmx_delegate", scope=str(home),
        profile_id="mmsecretary", session_id="session-1", command=COMMAND, job_id=JOB_ID,
        handler=handler, check_fn=check, handle=object(), entry=entry)
    slot.publish_registration(registration)
    slot.registration_context = types.SimpleNamespace(_manager=manager)
    slot.load_outcome = "REGISTERED"
    loaded = types.SimpleNamespace(enabled=True, error=None)
    slot.loader_record = loaded
    manager._plugins[CONSUMER_PLUGIN_NAME] = loaded
    live = {"entry": entry}
    plugin_module = types.ModuleType("hermes_cli.plugins")
    plugin_module.get_plugin_manager = lambda: manager
    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = types.SimpleNamespace(
        snapshot_registration=lambda _name, scope: live["entry"] if scope == str(home) else None)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugin_module)
    monkeypatch.setitem(sys.modules, "tools.registry", registry_module)
    monkeypatch.setattr(control, "current_runtime_owner", lambda: OWNER)
    runner = types.SimpleNamespace(_draining=False, session_runtime_descriptor={
        "state": "ready", "instance_id": "instance-1", "authority_epoch": 1})
    proof = control._consumer_extension(runner, home)
    assert proof["session_id"] == "session-1" and proof["target_digest"] == TARGET_DIGEST
    assert proof["implementation_sha"] == OWNER and proof["scope"] == str(home)
    live["entry"] = types.SimpleNamespace(
        handler=lambda *_args, **_kwargs: "", check_fn=check,
        toolset="mmx_delegate", schema=NATIVE_TOOL_SCHEMA)
    with pytest.raises(RuntimeRefusal):
        control._consumer_extension(runner, home)
    live["entry"] = entry
    manager._plugins[CONSUMER_PLUGIN_NAME] = types.SimpleNamespace(enabled=True, error=None)
    with pytest.raises(RuntimeRefusal):
        control._consumer_extension(runner, home)


def test_enrollment_qualification_keeps_original_worker_after_observer_cancellation(tmp_path, monkeypatch):
    import contextvars
    import pytest
    from integrations.hermes_runtime import native_gateway_entry as gateway
    from integrations.hermes_runtime import native_session_control as control
    from integrations.hermes_harness import native_selected_child_plugin as plugin
    held = Path(consumer.__file__).parent / CONSUMER_PLUGIN_NAME
    class HeldOwner:
        root = tmp_path / OWNER
        def directory(self, relative):
            return self.root / relative
        def source(self, relative):
            return (held / Path(relative).name).read_bytes()
        def check(self):
            return None
    owner = HeldOwner()
    document = publication_document()
    document["plugin"]["digest"] = consumer.held_plugin_package_digest(owner)
    publication = publication_from_document(document)
    role_home = tmp_path / "role"
    launch = types.SimpleNamespace(owner=owner, recipe={"executive_consumer": document},
                                   check=lambda: None)
    active_profile = contextvars.ContextVar("c46_fixture_profile", default="foreign")
    active_profile.set("mmsecretary")
    manager = types.SimpleNamespace(scope_key=str(role_home), _plugins={})
    foreign_manager = types.SimpleNamespace(scope_key="/foreign")
    counts = {"qualify": 0, "load": 0, "register": 0}
    contexts = []
    class Manifest:
        def __init__(self, **values):
            self.__dict__.update(values)
    def original_load(manifest):
        counts["load"] += 1
        context = types.SimpleNamespace(
            _manager=manager, manifest=manifest, profile_name="mmsecretary",
            plugin_id=CONSUMER_PLUGIN_NAME, _mcp_allowlist=lambda _name: [CONSUMER_MCP_SERVER])
        contexts.append(context)
        plugin.register(context)
        manager._plugins[CONSUMER_PLUGIN_NAME] = types.SimpleNamespace(
            enabled=True, error=None, manifest=manifest)
    manager._load_plugin = original_load
    modules = {
        "hermes_cli.plugins": {"get_plugin_manager": lambda: manager
                              if active_profile.get() == "mmsecretary" else foreign_manager},
        "hermes_cli.profiles": {"get_active_profile_name": lambda: active_profile.get()},
        "hermes_cli.plugins_manifest": {"PluginManifest": Manifest},
    }
    for name, values in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    native_ready = types.SimpleNamespace(publish_gateway_runtime_ready=lambda _runner: "native-ready")
    monkeypatch.setattr(gateway, "_vendor_module", lambda name, _root: native_ready
                        if name == "gateway.run_runtime" else pytest.fail("unexpected native import"))
    # This test owns cancellation/qualification, with an explicit loader edge.
    # Actual pinned general-loader import custody is covered by the native
    # Agent OS lifecycle tests, including policy namespace and isolation.
    monkeypatch.setattr(gateway, "_install_held_consumer_import", lambda *_: lambda candidate: None)
    monkeypatch.setattr(control, "current_runtime_owner", lambda: OWNER)
    monkeypatch.setattr(plugin, "current_runtime_owner", lambda: OWNER)
    target = {"profile_id": str(role_home), "principal_id": publication.session.principal_id,
              "session_id": "session-1", "instance_id": "instance-1", "authority_epoch": 1,
              "revision": 0, "execution_generation": 0}
    observed = {"status": "ABSENT", "target": None, "route": None}
    def read_original_enrollment(*_args, role):
        assert role == publication.session.role == "mmsecretary"
        return dict(observed)
    monkeypatch.setattr(control, "read_enrolled_session", read_original_enrollment)
    entered, release = threading.Event(), threading.Event()
    loop = _McpLoop()
    server = _Owner(_Session())
    monkeypatch.setattr(consumer, "capture_native_mcp_owner",
                        lambda *_args, **_kwargs: (server, server.session, loop.loop, lambda: True))
    def qualify(**kwargs):
        counts["qualify"] += 1
        guard = consumer.NativeConsumerCurrentness(
            publication=publication, session_id=target["session_id"],
            instance_id=target["instance_id"], authority_epoch=target["authority_epoch"],
            server=server, session=server.session, guard=kwargs["currentness"])
        assert guard() is True
        entered.set()
        assert release.wait(5)
        assert guard() is True
        return NativeDelegateBinding(
            transport=_Transport(), currentness_guard=guard, profile_id="mmsecretary",
            session_id="session-1", command=COMMAND, job_id=JOB_ID)
    monkeypatch.setattr(consumer, "qualify_executive_consumer", qualify)
    def register(context, startup):
        counts["register"] += 1
        binding = startup.binding
        return NativeDelegateRegistration(
            name="mmx_delegate", toolset="mmx_delegate", scope=str(role_home),
            profile_id=binding.profile_id, session_id=binding.session_id,
            command=binding.command, job_id=binding.job_id,
            handler=native_delegate_handler(binding), check_fn=binding.currentness_guard,
            handle=object(), entry=object())
    monkeypatch.setattr(plugin, "register_native_delegate_tools", register)
    runner = types.SimpleNamespace(_draining=False, session_runtime_descriptor={
        "state": "ready", "instance_id": "instance-1", "authority_epoch": 1})
    async def scenario():
        transition = gateway._install_consumer_seam(launch, tmp_path / "vendor", role_home)
        slot = getattr(manager, consumer.CONSUMER_SLOT_ATTRIBUTE)
        assert native_ready.publish_gateway_runtime_ready(runner) == "native-ready"
        assert slot.startup.binding is None and slot.qualification_task is None
        candidate = Manifest(name=CONSUMER_PLUGIN_NAME, key=CONSUMER_PLUGIN_NAME,
                             source=CONSUMER_PLUGIN_SOURCE, path=slot.package_path)
        assert manager._load_plugin(candidate) is None
        candidate.path = str(role_home / "plugins" / CONSUMER_PLUGIN_NAME)
        with pytest.raises(RuntimeRefusal):
            manager._load_plugin(candidate)
        assert counts == {"qualify": 0, "load": 0, "register": 0}
        observed.update(status="ENROLLED", target=target, route="route-1")
        transition(runner)
        original_observer = slot.qualification_task
        assert await asyncio.to_thread(entered.wait, 3)
        original_worker = slot.qualification_worker
        assert original_worker is not None and not original_worker.done()
        original_observer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await original_observer
        # The outer observer's cancellation cannot admit a replacement while
        # the original native registration worker still owns the outcome.
        transition(runner)
        assert slot.qualification_worker is original_worker
        assert slot.qualification_task is original_observer
        assert counts == {"qualify": 1, "load": 0, "register": 0}
        active_profile.set("foreign")
        release.set()
        assert await asyncio.wait_for(asyncio.shield(original_worker), timeout=4) is slot
        await asyncio.sleep(0)
        assert slot.load_outcome == slot.qualification_outcome == "REGISTERED"
        assert slot.registration_context is contexts[0] and slot.registration is not None
        assert counts == {"qualify": 1, "load": 1, "register": 1}
        transition(runner)
        assert counts == {"qualify": 1, "load": 1, "register": 1}
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        loop.close()
