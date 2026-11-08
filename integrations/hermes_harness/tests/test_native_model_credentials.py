"""Model-scoped credential transport tests: pure source, no Hermes start.

Fake fixture secrets only. No live model/provider request or host credential accessed.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.native_byok import render_disarmed_native_byok
from integrations.hermes_harness.native_model_credential import primary_model_env
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.memory import HighWaterLog
from integrations.hermes_runtime.secrets import Secrets, load_secrets
from integrations.hermes_runtime.supervisor import ServiceRuntime
from integrations.hermes_runtime.tests._support import STUB, TOKEN

FAKE_BYTEPLUS = "test-provider-key-local-fixture-not-live-123456"
FAKE_ZAI = "test-zai-key-local-fixture-not-live-123456"


class NativeCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="mmx-native-key-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.secret = self.root / "private.env"
        self.state = self.root / "state"
        self.home = self.root / "hermes-home"
        self.home.mkdir(mode=0o700)

    def _fixture_extras(self, lines: str) -> str:
        choices = {
            "BYTEPLUS_MODELARK_API_KEY": (FAKE_BYTEPLUS,),
            "ZAI_API_KEY": (FAKE_ZAI,),
            "HERMES_NATIVE_EGRESS_ROLE": ("mmsecretary", "mmmeta"),
            "HERMES_SLACK_BOT_TOKEN": (TOKEN, FAKE_BYTEPLUS, FAKE_ZAI,
                "distinct-dashboard-only-fixture-123456", "slack-token-fake-not-live",
                "synthetic-slack-bearer-123456"),
            "HERMES_SLACK_BOT_USER_ID": ("UPROJECTBOT001",),
            "BYTEPLUS_MODELARK_API_KEY_FILE": (str(self.root / "model-key"),
                str(self.root / "model-key-reused-as-slack-token")),
        }
        canonical = []
        for line in lines.splitlines():
            name, sep, value = line.partition("=")
            if sep != "=" or name not in choices or value not in choices[name]:
                raise ValueError("not a closed synthetic credential fixture")
            # Rebuild from the finite fixture catalog, never caller bytes.
            canonical.append(name + "=" + next(item for item in choices[name] if item == value) + "\n")
        return "".join(canonical)

    def _runtime(self, role="mmsecretary", extras="", dashboard_case="distinct", include_proxy=True):
        if role not in {"mmsecretary", "mmmeta"}:
            raise ValueError("not a synthetic role")
        examples = {
            "distinct": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=distinct-dashboard-only-fixture-123456\n",
            "missing": "",
            "model_alias": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + FAKE_BYTEPLUS + "\n",
        }
        if dashboard_case not in examples:
            raise ValueError("not a synthetic dashboard scenario")
        if type(include_proxy) is not bool:
            raise ValueError("invalid synthetic proxy selection")
        egress = (
            f"HERMES_NATIVE_EGRESS_ROLE={role}\n"
            f"HERMES_NATIVE_HTTPS_PROXY=http://{'127.0.0.2' if role == 'mmsecretary' else '127.0.0.3'}:{18651 if role == 'mmsecretary' else 18652}\n"
            if include_proxy else ""
        )
        content = "HERMES_GATEWAY_TOKEN=" + TOKEN + "\n" + examples[dashboard_case] + egress + self._fixture_extras(extras)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.secret, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
        profile = replace(
            compose_profile(role, state_dir=self.state, secrets_file=self.secret,
                            hermes_home=self.home, gateway_port=0, backend_port=0),
            tool_allowlist=frozenset({"clarify"}),
        )
        cfg = self.home / "profiles" / role / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(render_disarmed_native_byok(profile), encoding="utf-8")
        cfg.chmod(0o600)
        return ServiceRuntime(profile, load_secrets(self.secret), STUB)

    def test_fixture_rejects_arbitrary_values_before_file_creation(self) -> None:
        for kw in ({"extras": "BYTEPLUS_MODELARK_API_KEY=not-in-fixture-catalog\n"},
                   {"dashboard_case": "not-in-fixture-catalog"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self._runtime(**kw)
            self.assertFalse(self.secret.exists())

    def test_secretary_only_primary_key_and_no_parent_bearer(self) -> None:
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
            "HERMES_SLACK_BOT_TOKEN=slack-token-fake-not-live\n"
            "HERMES_SLACK_BOT_USER_ID=UPROJECTBOT001\n"
        ))
        census = rt._env()
        self.assertNotIn("BYTEPLUS_MODELARK_API_KEY", census)
        self.assertNotIn("ZAI_API_KEY", census)
        native = rt._model_child_env()
        self.assertEqual(native["BYTEPLUS_MODELARK_API_KEY"], FAKE_BYTEPLUS)
        self.assertNotIn("ZAI_API_KEY", native)
        self.assertNotIn("HERMES_GATEWAY_TOKEN", native)
        self.assertNotIn("HERMES_SLACK_BOT_TOKEN", native)
        self.assertNotIn(TOKEN, native.values())
        self.assertNotIn(FAKE_ZAI, native.values())
        self.assertEqual(native["HERMES_SLACK_BOT_USER_ID"], "UPROJECTBOT001")
        self.assertEqual(native["HTTPS_PROXY"], "http://127.0.0.2:18651")
        self.assertNotIn("HTTP_PROXY", native)
        self.assertNotIn("ALL_PROXY", native)
        self.assertNotIn("HERMES_NATIVE_HTTPS_PROXY", native)

    def test_meta_ceo_key_is_disjoint_from_secretary(self) -> None:
        rt = self._runtime(role="mmmeta", extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
        ))
        native = rt._model_child_env()
        self.assertEqual(native["ZAI_API_KEY"], FAKE_ZAI)
        self.assertNotIn("BYTEPLUS_MODELARK_API_KEY", native)

    def test_missing_or_bad_file_pointer_fails_closed(self) -> None:
        rt = self._runtime()
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

        file = self.root / "model-key"
        file.write_text(FAKE_BYTEPLUS + "\n", encoding="utf-8")
        file.chmod(0o600)
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY_FILE=" + str(file) + "\n")
        self.assertEqual(rt._model_child_env()["BYTEPLUS_MODELARK_API_KEY"], FAKE_BYTEPLUS)
        file.chmod(0o644)
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

    def test_missing_role_private_proxy_refuses_even_if_shell_has_proxy(self) -> None:
        rt = self._runtime(extras='BYTEPLUS_MODELARK_API_KEY=' + FAKE_BYTEPLUS + '\nHERMES_NATIVE_EGRESS_ROLE=mmsecretary\n', include_proxy=False)
        with mock.patch.dict(os.environ, {'HTTPS_PROXY': 'http://127.0.0.2:18651'}):
            with self.assertRaises(RuntimeRefusal) as exc:
                rt._model_child_env()
        self.assertEqual(exc.exception.code, 'NATIVE_EGRESS_PROXY_NOT_ENROLLED')

    def test_shell_only_key_cannot_bypass_role_private_secret_file(self) -> None:
        # A systemd unit must not depend on the installing operator's shell.
        rt = self._runtime()
        from unittest import mock
        with mock.patch.dict(os.environ, {
            "BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS,
            "BYTEPLUS_MODELARK_API_KEY_FILE": "/tmp/not-authorized.key",
        }):
            with self.assertRaises(RuntimeRefusal) as exc:
                rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

    def test_mcp_enabled_or_config_drift_blocks_key_material(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        cfg = rt.profile.hermes_home / "profiles" / rt.profile.role / "config.yaml"
        cfg.write_text(cfg.read_text().replace("enabled: false", "enabled: true"))
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_gateway_token_must_not_be_reused_as_dashboard_password(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="missing",
        )
        self.assertEqual(rt.secrets.dashboard_password, rt.secrets.token)
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")

    def test_model_key_must_not_be_reused_as_gateway_or_dashboard_key(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="model_alias",
        )
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_slack_bot_auth_must_not_alias_gateway_or_dashboard(self) -> None:
        for label, slack_token in (
            ("gateway", TOKEN),
            ("dashboard", "distinct-dashboard-only-fixture-123456"),
        ):
            with self.subTest(alias=label):
                rt = self._runtime(extras=(
                    "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
                    "HERMES_SLACK_BOT_TOKEN=" + slack_token + "\n"
                ))
                with self.assertRaises(RuntimeRefusal) as exc:
                    rt._model_child_env()
                self.assertEqual(exc.exception.code, "NATIVE_SLACK_BOT_AUTH_ALIAS_REFUSED")

    def test_the_consumer_client_ref_cannot_borrow_the_model_identity(self) -> None:
        """The Executive connection keeps its own OAuth client reference.

        It never borrows the model's provider, its credential name or its
        served model: the two identities stay disjoint.
        """
        from integrations.hermes_models.contract import native_provider
        from integrations.hermes_harness.tests.test_native_executive_consumer import (
            publication_document,
        )

        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        spec = native_provider(rt.profile.role, rt.profile.native_provider_id)
        for label, borrowed in (
            ("credential_env", spec.credential_env),
            ("provider_id", spec.provider_id),
            ("hermes_name", spec.hermes_name),
            ("served_model", spec.served_model),
        ):
            with self.subTest(alias=label):
                document = publication_document()
                document["mcp"] = dict(document["mcp"], client_id=borrowed)
                with self.assertRaises(RuntimeRefusal) as exc:
                    primary_model_env(rt.profile, rt.secrets.values, document)
                self.assertEqual(exc.exception.code,
                                 "NATIVE_CONSUMER_MODEL_CREDENTIAL_ALIAS_REFUSED")

    def test_no_consumer_keeps_the_model_credential_unchanged(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        env = primary_model_env(rt.profile, rt.secrets.values)
        self.assertEqual(env, {"BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS})

    def test_model_key_must_not_alias_slack_bot_token_for_either_role(self) -> None:
        for role, env_name, value in (
            ("mmsecretary", "BYTEPLUS_MODELARK_API_KEY", FAKE_BYTEPLUS),
            ("mmmeta", "ZAI_API_KEY", FAKE_ZAI),
        ):
            with self.subTest(role=role):
                rt = self._runtime(role=role, extras=(
                    env_name + "=" + value + "\n"
                    "HERMES_SLACK_BOT_TOKEN=" + value + "\n"
                ))
                with self.assertRaises(RuntimeRefusal) as exc:
                    rt._model_child_env()
                self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_file_pointer_key_must_not_alias_slack_bot_token(self) -> None:
        key_file = self.root / "model-key-reused-as-slack-token"
        key_file.write_text(FAKE_BYTEPLUS + "\n", encoding="utf-8")
        key_file.chmod(0o600)
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY_FILE=" + str(key_file) + "\n"
            "HERMES_SLACK_BOT_TOKEN=" + FAKE_BYTEPLUS + "\n"
        ))
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_byok_alias_refusal_happens_before_any_hermes_subprocess(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="missing",
        )
        with mock.patch(
            "integrations.hermes_runtime.supervisor.subprocess.run",
            side_effect=AssertionError("credential reached tools-list census"),
        ) as census:
            with self.assertRaises(RuntimeRefusal) as refused:
                rt.start()
        self.assertEqual(refused.exception.code, "NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")
        census.assert_not_called()
        self.assertIsNone(rt.gateway)
        self.assertIsNone(rt._thread)
        self.assertEqual(rt.child_starts, 0)

    def test_tool_census_env_contains_no_privileged_bearer(self) -> None:
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
            "HERMES_SLACK_BOT_TOKEN=synthetic-slack-bearer-123456\n"
        ))
        env = rt._registry_env()
        self.assertEqual(set(env), {"PATH", "HOME", "HERMES_HOME", "LANG"})
        self.assertNotIn(FAKE_BYTEPLUS, env.values())
        self.assertNotIn(FAKE_ZAI, env.values())
        self.assertNotIn(TOKEN, env.values())
        self.assertNotIn(rt.secrets.dashboard_password, env.values())

    def test_unexpected_supervisor_thread_error_becomes_terminal_failure(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        with mock.patch.object(rt, "_loop", side_effect=OSError("sensitive synthetic fixture")):
            rt._loop_guarded()
        code, health = rt.health_snapshot()
        self.assertEqual(code, 503)
        self.assertEqual(health["status"], "failed")
        self.assertTrue(rt.failed)
        self.assertEqual(rt.refusal_code, "RUNTIME_SUPERVISOR_EXCEPTION")
        self.assertNotIn("sensitive", repr((health, rt.refusal_code)))
        self.assertIsNone(rt.child_pid)

    def test_subprocess_spawn_failure_marks_supervisor_failed(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        rt.memory = HighWaterLog(self.state / "memory" / "high-water.log")
        # No actual spawn or port bind: test the exact supervised failure path.
        with mock.patch(
            "integrations.hermes_runtime.supervisor.reserve_loopback_port", return_value=19997,
        ), mock.patch(
            "integrations.hermes_runtime.supervisor.build_serve_argv",
            return_value=["/tmp/synthetic-never-executed"],
        ), mock.patch(
            "integrations.hermes_runtime.supervisor.subprocess.Popen",
            side_effect=OSError("synthetic spawn failure"),
        ):
            rt._loop_guarded()
        code, health = rt.health_snapshot()
        self.assertEqual(code, 503)
        self.assertEqual(health["status"], "failed")
        self.assertEqual(rt.refusal_code, "RUNTIME_SUPERVISOR_EXCEPTION")
        self.assertEqual(rt.child_starts, 1)
        self.assertIsNone(rt.child_pid)

    def test_uninstalled_shadow_profile_cannot_request_key(self) -> None:
        p = compose_profile("mmsecretary", state_dir=self.state, secrets_file=self.secret)
        with self.assertRaises(RuntimeRefusal) as exc:
            primary_model_env(p, {"BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS})
        self.assertEqual(exc.exception.code, "NATIVE_EXTENSION_NOT_INSTALLED")


# Pinned child-side source qualification. Environment, provider/profile hooks,
# primary-client setup and service/host edges are explicit synthetic fixtures.
# The actual resolver, secret-selection, request-cache, SDK and HTTPX bodies run.
import ast
import contextlib
from contextvars import ContextVar
import copy
import hashlib
import inspect
import json
import logging
import sys
import threading
from types import MethodType, SimpleNamespace

import httpx
import pytest

from integrations.hermes_runtime import native_eval_inputs as eval_inputs
from integrations.hermes_runtime import native_eval_publication as eval_publication
from integrations.hermes_runtime import native_request_observation as request_observation
from integrations.hermes_runtime import native_session_control as native_control
from integrations.hermes_runtime import native_transport_observation as transport_observation
from integrations.hermes_runtime.tests.test_native_eval_inputs import (
    lifecycle, history_lifecycle, engine, native, decoded_fixture, actual_result,
    current_result, signed, rsa_key, joined, owner, env, isolated_git_env, identity,
    native_trial, execute_trial, fresh_run_id, success,
)
from integrations.hermes_runtime.tests.test_native_request_observation import module

_AUTH_FIXTURES = Path(__file__).parent / "fixtures/native_credential_observation"
_AUTH_MANIFEST = json.loads((_AUTH_FIXTURES / "provenance.json").read_text())
FAKE_OTHER = "synthetic-other-static-provider-key-not-live-123456"


def _node_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    return set()


def _credential_source(n, monkeypatch, path, names, *, values=None, methods=None):
    manifest, root = _AUTH_MANIFEST, _AUTH_FIXTURES
    if path not in manifest["files"]:
        root = Path(__file__).parents[2] / "hermes_runtime/tests/fixtures/native_eval_inputs"
        manifest = json.loads((root / "provenance.json").read_text())
    item = manifest["files"][path]
    raw = (root / item["fixture"]).read_bytes()
    assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["git_blob"]
    target = n.vendor / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(0o644)
    name = path.removesuffix(".py").replace("/", ".")
    existing = sys.modules.get(name)
    preserved = {} if existing is None else {k: v for k, v in vars(existing).items() if not k.startswith("__")}
    selected = [node for node in ast.parse(raw).body if _node_names(node) & set(names)]
    assert set().union(*map(_node_names, selected)) == set(names)
    if methods is not None:
        for node in selected:
            if isinstance(node, ast.ClassDef):
                node.body = [child for child in node.body if _node_names(child) & methods]
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    code = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    result = module(monkeypatch, name, __file__=str(target), **{**preserved, **(values or {})})
    parent, _, leaf = name.rpartition(".")
    if parent in sys.modules:
        monkeypatch.setattr(sys.modules[parent], leaf, result, raising=False)
    exec(compile(code, str(target), "exec"), vars(result))
    return result


@pytest.fixture
def credential_path(history_lifecycle, engine, monkeypatch, request):
    from integrations.hermes_harness import native_model_credential as credential_owner
    from integrations.hermes_harness.native_byok import _expected_providers
    from integrations.hermes_models.contract import native_provider
    import openai

    l, n = history_lifecycle, history_lifecycle.native
    # The incumbent source fixture normally uses the secretary role. This
    # declared role edge selects mmmeta before creating any admission/witness.
    n.binding.role = "mmmeta"
    spec = native_provider("mmmeta", "zai.glm-5.3")
    chain = SimpleNamespace(lifecycle=l, engine=engine, native=n, spec=spec, mode="direct",
        pool=None, clients=[], sends=[], resolver_calls=0, creations=0, guards=[],
        before_send=None, before_builder=None, sdk_failure=None, retry_witnesses=[],
        environ={spec.credential_env: FAKE_ZAI})
    # Select this public mechanism class before the incumbent ArtifactStore
    # freezes/digests the configuration. READ_ONLY is a different class and
    # cannot be inferred from presentation of a key.
    from integrations.hermes_runtime.tests import test_native_eval_inputs as input_fixture
    original_documents = input_fixture.documents
    chain.auth_class = "API_KEY"
    def documents(*args, **kwargs):
        scenario, config, text, files, context = original_documents(*args, **kwargs)
        fields = copy.deepcopy({k: v for k, v in config.items()
                                if k not in {"schema", "configuration_digest"}})
        fields["execution"]["auth_realm_class"] = chain.auth_class
        return scenario, eval_inputs.contracts.build_configuration(fields), text, files, context
    monkeypatch.setattr(input_fixture, "documents", documents)
    chain.config = {"model": {"provider": spec.hermes_name, "default": spec.served_model,
                             "base_url": spec.base_url},
                    "providers": {spec.hermes_name: copy.deepcopy(_expected_providers()[spec.hermes_name])}}
    log = logging.getLogger("synthetic-native-credential-source")
    secrets = _credential_source(n, monkeypatch, "agent/secret_scope.py",
        {"_environ_or", "get_secret", "get_secret_str"}, values={
            "os": SimpleNamespace(environ=chain.environ), "_is_global_env": lambda _: False,
            "_SECRET_SCOPE": ContextVar("synthetic_secret_scope", default=None),
            "_LAUNCH_BODY_SCOPE": ContextVar("synthetic_launch_scope", default=None),
            "is_multiplex_active": lambda: False, "serves_routed_profile": lambda: False,
            "UnscopedSecretError": RuntimeError})
    chain.secrets = secrets
    core = _credential_source(n, monkeypatch, "hermes_cli/runtime_provider.py",
        {"_runtime", "frozen_runtime_config"}, values={
            "copy": copy, "contextmanager": contextlib.contextmanager, "is_actual_route": lambda *_: False,
            "_FROZEN_RUNTIME_CONFIG": ContextVar("synthetic_frozen_config", default=None),
            "_config_mod": SimpleNamespace(DEFAULT_CONFIG={}, _deep_merge=lambda a, b: {**a, **b})})
    core._resolves_to_custom = lambda _: False
    core.has_usable_secret = lambda value: type(value) is str and bool(value) and value != "no-key-required"
    core._get_model_config = lambda: chain.config["model"]
    core._detect_api_mode_for_url = lambda _: "chat_completions"
    core._parse_api_mode = lambda value: value
    core.load_config = lambda: core._FROZEN_RUNTIME_CONFIG.get() or chain.config
    core._try_resolve_from_custom_pool = lambda *a, **kw: chain.pool
    core._host_gated_env_key_candidates = lambda *a, **kw: ()
    core.get_compatible_custom_providers = lambda _: []
    core.resolve_runtime_provider = lambda **kw: (_ for _ in ()).throw(AssertionError("unexpected fallback"))
    core.resolve_runtime_with_fallback = core.resolve_runtime_provider
    monkeypatch.setattr(sys.modules["hermes_cli.config"], "is_provider_enabled",
                        lambda entry: entry.get("enabled", True) is not False, raising=False)
    custom = _credential_source(n, monkeypatch, "hermes_cli/runtime_provider_custom.py",
        {"_rp", "_clean", "_entry_url", "_match_new_style_provider", "_select_named_custom_provider",
         "_get_named_custom_provider", "_key_env_secret", "_entry_credential",
         "_custom_runtime", "_resolve_named_custom_runtime", "_lift_common_custom_fields"},
        values={"logger": log, "get_secret_str": secrets.get_secret_str,
            "_normalize_custom_provider_name": lambda name: name.strip().lower(),
            "_shadowed_by_builtin": lambda _: False,
            "custom_provider_aliases": lambda display, key: {display.strip().lower(), key.strip().lower()},
            "_LLAMACPP_ALIASES": set(), "_lift_extra_headers": lambda *_: None,
            "_lift_model_capabilities": lambda *_: None, "_apply_custom_provider_extras": lambda *_: None,
            "_opencode_family_for_custom": lambda *_: None,
            "entry_declares_credential": lambda entry: bool(entry.get("key_env") or entry.get("api_key")
                                                           or entry.get("key_cmd"))})
    core._get_named_custom_provider = custom._get_named_custom_provider
    core._resolve_named_custom_runtime = custom._resolve_named_custom_runtime
    worker = _credential_source(n, monkeypatch, "gateway/session_worker_construct.py",
        {"route_runtime"}, values={"json": json})
    chain.core, chain.custom, chain.worker = core, custom, worker

    methods = {"_request_slot", "_checkout_request_slot", "_store_request_slot", "_release_request_slot",
               "_create_request_openai_client", "_close_request_openai_client",
               "_is_openai_client_closed", "_REQUEST_CLIENT_REUSE_REASONS"}
    clients = _credential_source(n, monkeypatch, "agent/client_lifecycle.py",
        {"ClientLifecycleMixin", "_reset_slot", "_OPENAI_SLOT"}, methods=methods,
        values={"base_url_host_matches": lambda *_: False, "logger": log})
    chain.clients_module = clients
    module(monkeypatch, "agent.auxiliary_client", _to_openai_base_url=lambda value: value,
           _validate_base_url=lambda _: None, _validate_proxy_env_urls=lambda: None,
           _GEMINI_NATIVE_PROVIDER_NAMES=())
    module(monkeypatch, "agent.ssl_verify", resolve_httpx_verify=lambda **kw: True)
    module(monkeypatch, "providers", get_provider_profile=lambda _: None)
    module(monkeypatch, "agent.codex_headers", apply_required_codex_headers=lambda *a, **kw: None)
    module(monkeypatch, "agent.served_model", install_served_model_capture=lambda *a: None)
    def build_sdk(**kwargs):
        chain.creations += 1
        if chain.sdk_failure is not None:
            raise chain.sdk_failure
        if chain.mode in {"retry_restore", "retry_pressure"}:
            # Explicit synthetic SDK-retry edge. Native source normally chooses
            # zero SDK retries; production policy is not changed by this probe.
            kwargs["max_retries"] = 2
        value = openai.OpenAI(**kwargs)
        if chain.mode == "returned_client_changed":
            value.api_key = FAKE_OTHER
        chain.clients.append(value)
        return value
    boot = module(monkeypatch, "agent.process_bootstrap", OpenAI=build_sdk)
    monkeypatch.setattr(sys.modules["agent"], "process_bootstrap", boot, raising=False)
    helpers = _credential_source(n, monkeypatch, "agent/agent_runtime_helpers.py",
        {"create_openai_client"}, values={"_provider_supplied_client": lambda *_: None,
            "_ensure_copilot_headers": lambda *_: None, "_ra": lambda: SimpleNamespace(logger=log)})
    chain.helpers = helpers
    profile = replace(compose_profile("mmmeta", state_dir=n.vendor / "fixture-state",
                      secrets_file=n.vendor / "not-read.env", hermes_home=n.home.parent.parent),
                      tool_allowlist=frozenset({"clarify"}))
    construction = getattr(request, "param", "ordinary")
    chain.construction = construction
    if construction == "source_hash_drift":
        target = n.vendor / "agent/secret_scope.py"
        target.write_bytes(target.read_bytes() + b"\n# changed source fixture\n")
    elif construction in {"core_alias_race", "custom_alias_race"}:
        prepare = credential_owner.prepare_native_credential_observation
        target = core if construction == "core_alias_race" else custom
        def prepare_with_race(*args, **kwargs):
            result = prepare(*args, **kwargs)
            original = target._resolve_named_custom_runtime
            def retained_owner(*args, **kwargs):
                return original(*args, **kwargs)
            chain.retained_owner, chain.race_target = retained_owner, target
            target._resolve_named_custom_runtime = retained_owner
            return result
        monkeypatch.setattr(credential_owner, "prepare_native_credential_observation", prepare_with_race)
    n.binding.transport_installation.bind_credentials(n.vendor, profile)
    installed = n.binding.transport_installation.credential_installation
    assert type(installed) is credential_owner.NativeCredentialObservation
    assert installed.current() is (construction == "ordinary")
    chain.installed = installed

    def resolve(turn):
        chain.resolver_calls += 1
        if chain.mode == "no_current_read":
            return copy.deepcopy(chain.prior_route)
        context = None
        if chain.mode == "scoped_override":
            context = secrets._SECRET_SCOPE.set(SimpleNamespace(mapping={spec.credential_env: FAKE_ZAI}))
        elif chain.mode == "empty_scope":
            context = secrets._SECRET_SCOPE.set(SimpleNamespace(mapping={}))
        if chain.mode == "inline_key":
            chain.config["providers"][spec.hermes_name]["api_key"] = FAKE_ZAI
        explicit = FAKE_ZAI if chain.mode == "explicit_key" else ""
        try:
            runtime, fallback = worker.route_runtime(SimpleNamespace(request_json="{}"),
                chain.config, spec.served_model, explicit)
        finally:
            if context is not None:
                secrets._SECRET_SCOPE.reset(context)
        assert fallback is None
        if chain.mode == "route_changed":
            runtime = {**runtime, "api_key": FAKE_OTHER}
        chain.prior_route = {"model": spec.served_model, "runtime": runtime}
        return copy.deepcopy(chain.prior_route)
    chain.resolve = resolve

    def handler(request):
        chain.sends.append(json.loads(request.content))
        current = transport_observation._dispatch_context.get()
        if current is not None and current.credential is not None:
            chain.retry_witnesses.append(current.credential)
        if chain.before_send is not None:
            chain.before_send(request)
        if chain.mode in {"retry_restore", "retry_pressure"} and len(chain.sends) <= 2:
            chain.clients[-1].api_key = FAKE_OTHER if len(chain.sends) == 1 else FAKE_ZAI
            return httpx.Response(500, headers={"retry-after-ms": "1"},
                                  json={"error": {"message": "synthetic retry"}})
        return httpx.Response(200, json=success("glm-5.3"))
    chain.handler = handler

    def prepare_agent(out):
        agent = out["agent"]
        klass = clients.ClientLifecycleMixin
        if not hasattr(agent, "_client_kwargs"):
            agent._client_kwargs = {"api_key": agent.api_key, "base_url": agent.base_url}
            lock = threading.RLock()
            agent._openai_client_lock = lambda: lock
            agent._ensure_primary_openai_client = lambda **kw: object()
            agent._client_log_context = lambda: "synthetic"
            agent._build_keepalive_http_client = lambda *a, **kw: httpx.Client(
                transport=httpx.MockTransport(lambda request: chain.handler(request)))
            agent._close_openai_client = lambda client, **kw: client.close()
            for name in methods - {"_REQUEST_CLIENT_REUSE_REASONS", "_is_openai_client_closed"}:
                setattr(agent, name, MethodType(getattr(klass, name), agent))
            agent._is_openai_client_closed = klass._is_openai_client_closed
            agent._REQUEST_CLIENT_REUSE_REASONS = klass._REQUEST_CLIENT_REUSE_REASONS
            agent._create_openai_client = MethodType(helpers.create_openai_client, agent)
        chain.guards.append(out["scope"].transport.credential_scope)
        if chain.mode == "client_kwargs_changed":
            agent._client_kwargs = {**agent._client_kwargs, "api_key": FAKE_OTHER}
        if chain.mode == "header_override":
            agent._client_kwargs = {**agent._client_kwargs, "default_headers": {"Authorization": "Bearer " + FAKE_OTHER}}
        if chain.before_builder is not None:
            chain.before_builder(out)
    chain.prepare_agent = prepare_agent

    def run(tmp_path, *, trial=None, cached=None, admission="eval-admission", generation=3,
            request_id="r"):
        t = trial or native_trial(l, tmp_path)
        if trial is not None:
            t.specification["run_id"] = fresh_run_id()
        def downstream(out):
            engine.invoke(out["agent"], out["kwargs"], None, request_id=request_id,
                          native_client_lifecycle=True, threaded=False)
        out = execute_trial(l, t, native_context=True, route_factory=resolve,
            before_builder=prepare_agent, after_request=downstream, cached=cached,
            admission=admission, generation=generation, api_request_id=request_id)
        receipt = {"admission_id": admission, "ref": {"profile_id": t.owner.profile_id, "session_id": t.session},
            "sequence": 1, "status": "terminal", "outcome": "completed",
            "authority_epoch": 2, "execution_generation": generation}
        projected = native_control._project_original_result(receipt, out["marker"], out["saved"], role="mmmeta")
        assert "request_observation" in projected and "evaluation_inputs" in projected
        def build(value=None):
            return eval_publication._build_run(out["marker"], receipt, projected if value is None else value,
                finalizer_ref=t.owner.producer["runner_code_ref"], now="2026-11-08T00:00:00Z",
                missing_reason="NOT_OBSERVED")
        return SimpleNamespace(out=out, trial=t, projected=projected, build=build)
    chain.run = run
    yield chain
    for client in chain.clients:
        client.close()


def test_original_direct_credential_reaches_new_sdk_request_and_eval(credential_path, tmp_path):
    chain = credential_path
    w = chain.run(tmp_path)
    runtime = w.projected["request_observation"]["transport"]
    assert len(runtime["attempts"]) == len(chain.sends) == 1
    assert runtime["dispatches"][0]["auth_client_check"] == "matched"
    assert runtime["attempts"][0]["auth_mechanism"] == "API_KEY"
    assert transport_observation.validate_document(runtime) == runtime
    run = w.build()
    assert run["execution"]["auth_realm_class"] == "API_KEY", {
        "selected": w.out["marker"]["configuration"]["execution"]["auth_realm_class"],
        "unavailable": run["observation_availability"]["unavailable"],
        "errors": w.projected["request_observation"]["errors"],
        "transport_errors": runtime["errors"],
        "metadata_overflow": w.projected["request_observation"]["metadata_overflow"],
        "input_errors": w.projected["evaluation_inputs"]["errors"],
        "assembly_count": len(w.projected["evaluation_inputs"]["assemblies"]),
        "observed_count": len(w.projected["request_observation"]["observations"]),
    }
    assert run["execution"]["provider"] == "custom"
    assert run["validity"]["status"] != "VALID"
    assert run["effect"]["state"] == "EFFECT_UNKNOWN" and run["cleanup"]["status"] == "UNPROVEN"
    raw = json.dumps(w.projected)
    assert all(value not in raw for value in (FAKE_ZAI, FAKE_OTHER, "Bearer ", "ZAI_API_KEY", "Authorization"))
    guard = chain.guards[0]
    assert guard._key is None and guard._capture is None and guard._pending_route is None


def test_current_resolution_qualifies_original_warm_client_without_old_witness(credential_path, tmp_path):
    chain = credential_path
    first = chain.run(tmp_path)
    assert first.build()["execution"]["auth_realm_class"] == "API_KEY"
    second = chain.run(tmp_path, trial=first.trial, cached=first.out["agent"],
                       admission="warm-eval", generation=4)
    assert second.out["reused"] is True and second.out["agent"] is first.out["agent"]
    assert second.build()["execution"]["auth_realm_class"] == "API_KEY"
    assert chain.creations == 1 and chain.resolver_calls == 2 and len(chain.sends) == 2
    assert chain.guards[0] is not chain.guards[1]
    assert all(guard._key is None for guard in chain.guards)


@pytest.mark.parametrize("mode,expected", [
    ("empty_scope", "API_KEY"),
    ("scoped_override", "unavailable"),
    ("explicit_key", "unavailable"),
    ("inline_key", "unavailable"),
    ("route_changed", "conflicting"),
    ("client_kwargs_changed", "conflicting"),
    ("returned_client_changed", "conflicting"),
    ("header_override", "conflicting"),
])
def test_original_selection_and_actual_client_changes_do_not_invent_authentication(
        credential_path, tmp_path, mode, expected):
    chain = credential_path
    chain.mode = mode
    w = chain.run(tmp_path)
    transport = w.projected["request_observation"]["transport"]
    assert len(chain.sends) == len(transport["attempts"]) == 1
    assert transport["attempts"][0]["auth_mechanism"] == expected
    run = w.build()
    assert run["execution"]["auth_realm_class"] == ("API_KEY" if expected == "API_KEY" else None)
    if expected == "conflicting":
        missing = {row["path"]: row["reason"] for row in run["observation_availability"]["unavailable"]}
        assert missing["execution.auth_realm_class"] == "OBSERVATION_CONFLICT"
    assert all(value not in json.dumps(w.projected) for value in (FAKE_ZAI, FAKE_OTHER, "Bearer ", "ZAI_API_KEY"))
    assert all(guard._key is None and guard._pending_route is None for guard in chain.guards)


def test_presented_api_key_cannot_attest_a_different_selected_realm_class(credential_path, tmp_path):
    chain = credential_path
    chain.auth_class = "READ_ONLY"
    w = chain.run(tmp_path)
    assert w.projected["request_observation"]["transport"]["attempts"][0]["auth_mechanism"] == "API_KEY"
    run = w.build()
    assert run["execution"]["auth_realm_class"] is None
    missing = {row["path"]: row["reason"] for row in run["observation_availability"]["unavailable"]}
    assert missing["execution.auth_realm_class"] == "OBSERVATION_CONFLICT"


def test_warm_client_cannot_reuse_an_earlier_admissions_credential_witness(credential_path, tmp_path):
    chain = credential_path
    first = chain.run(tmp_path)
    assert first.build()["execution"]["auth_realm_class"] == "API_KEY"
    chain.mode = "no_current_read"
    second = chain.run(tmp_path, trial=first.trial, cached=first.out["agent"],
                       admission="warm-without-read", generation=4)
    assert second.out["reused"] is True and chain.creations == 1
    assert len(chain.sends) == 2
    observed = second.projected["request_observation"]["transport"]
    assert observed["dispatches"][0]["auth_client_check"] == "unavailable"
    assert observed["attempts"][0]["auth_mechanism"] == "unavailable"
    assert second.build()["execution"]["auth_realm_class"] is None
    assert chain.guards[0] is not chain.guards[1]
    assert all(guard._key is None for guard in chain.guards)


def test_original_shared_client_outside_dispatch_preserves_its_factory(credential_path, tmp_path):
    chain = credential_path
    shared = []
    def primary(out):
        # Actual original execution scope is active, but no transport dispatch
        # exists yet. This unrelated primary client is not an auth witness.
        assert request_observation._current.get() is out["scope"]
        assert transport_observation._dispatch_context.get() is None
        shared.append(chain.helpers.create_openai_client(out["agent"],
            {"api_key": FAKE_OTHER, "base_url": chain.spec.base_url},
            reason="synthetic-primary", shared=True))
    chain.before_builder = primary
    w = chain.run(tmp_path)
    assert chain.creations == 2 and shared[0] is chain.clients[0]
    assert len(chain.sends) == 1 and w.build()["execution"]["auth_realm_class"] == "API_KEY"


@pytest.mark.parametrize("credential_path", [
    "core_alias_race", "custom_alias_race", "source_hash_drift",
], indirect=True)
def test_changed_source_or_intervening_original_owner_is_retained(credential_path, tmp_path):
    chain = credential_path
    assert chain.installed.current() is False
    if hasattr(chain, "retained_owner"):
        assert chain.race_target._resolve_named_custom_runtime is chain.retained_owner
    w = chain.run(tmp_path)
    assert len(chain.sends) == 1
    assert w.build()["execution"]["auth_realm_class"] is None
    assert w.projected["request_observation"]["transport"]["attempts"][0]["auth_mechanism"] == "unavailable"
    assert chain.guards == [None]


@pytest.mark.parametrize("callback", ["bind", "mechanism", "client_status", "close", "scope_close"])
def test_optional_observation_callback_fault_cannot_replace_original_success(
        credential_path, tmp_path, monkeypatch, callback):
    from integrations.hermes_harness import native_model_credential as credential_owner
    chain = credential_path
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic observation callback failure")
    cls = credential_owner._CredentialScope if callback == "scope_close" else credential_owner._CredentialDispatch
    monkeypatch.setattr(cls, "close" if callback == "scope_close" else callback, broken)
    # A failing ordinary invalidation callback is not allowed to escape either.
    monkeypatch.setattr(credential_owner._CredentialDispatch, "fail", broken)
    w = chain.run(tmp_path)
    assert w.out["response"] == "component result" and len(chain.sends) == 1
    transport = w.projected["request_observation"]["transport"]
    assert "transport_observation_failed" in transport["errors"]
    assert w.build()["execution"]["auth_realm_class"] is None
    assert all(guard._key is None for guard in chain.guards)


def test_original_sdk_factory_exception_is_preserved_and_private_state_is_released(
        credential_path, tmp_path):
    chain = credential_path
    original = RuntimeError("synthetic original SDK creation failure")
    chain.sdk_failure = original
    with pytest.raises(RuntimeError) as caught:
        chain.run(tmp_path)
    assert caught.value is original and chain.creations == 1 and chain.sends == []
    assert all(guard._key is None and guard._pending_route is None for guard in chain.guards)


def test_cleanup_fault_preserves_the_original_transport_exception(
        credential_path, tmp_path, monkeypatch):
    import openai
    from integrations.hermes_harness import native_model_credential as credential_owner
    chain = credential_path
    original = httpx.ConnectError("synthetic original transport failure")
    def fail_send(request):
        raise original
    def fail_close(self):
        raise RuntimeError("synthetic observation cleanup failure")
    chain.before_send = fail_send
    monkeypatch.setattr(credential_owner._CredentialDispatch, "close", fail_close)
    with pytest.raises(openai.APIConnectionError) as caught:
        chain.run(tmp_path)
    assert caught.value.__cause__ is original
    assert len(chain.sends) == 1 and all(guard._key is None for guard in chain.guards)


def test_each_actual_sdk_retry_keeps_authentication_conflict_sticky(credential_path, tmp_path):
    chain = credential_path
    chain.mode = "retry_restore"
    w = chain.run(tmp_path)
    assert len(chain.sends) == 3 and chain.creations == 1
    assert chain.clients[0].api_key == FAKE_ZAI
    assert chain.retry_witnesses and all(witness._state == "conflicting" for witness in chain.retry_witnesses)
    observed = w.projected["request_observation"]["transport"]
    assert observed["attempts"][0]["auth_mechanism"] == "API_KEY"
    assert all(row["auth_mechanism"] == "conflicting" for row in observed["attempts"][1:])
    assert observed["dispatches"][0]["auth_client_check"] == "conflicting"
    assert w.build()["execution"]["auth_realm_class"] is None


@pytest.mark.parametrize("change", ["overflow", "missing_assembly", "missing_attempt", "different_request"])
def test_auth_scalar_requires_the_existing_complete_original_join(credential_path, tmp_path, change):
    chain = credential_path
    w = chain.run(tmp_path)
    value = copy.deepcopy(w.projected)
    if change == "overflow":
        value["request_observation"]["transport"]["overflow"] = True
    elif change == "missing_assembly":
        value["evaluation_inputs"]["assemblies"] = []
    elif change == "missing_attempt":
        value["request_observation"]["transport"]["attempts"] = []
    else:
        value["evaluation_inputs"]["assemblies"][0]["api_request_id"] = "different-original-request"
    assert w.build(value)["execution"]["auth_realm_class"] is None


if __name__ == "__main__":
    unittest.main()
