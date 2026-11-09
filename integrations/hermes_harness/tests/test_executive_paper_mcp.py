"""Offline Hermes Executive v3 + Paper MCP source/installer contract tests."""
from __future__ import annotations

from pathlib import Path
import os
import signal
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness import executive_paper_mcp as plugin
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_steward.config_guard import _load_unique_yaml


class ExecutivePaperMcpTests(unittest.TestCase):
    def profile(self, home: Path, role: str):
        from dataclasses import replace
        return replace(
            compose_profile(role, state_dir=home / "state",
                            secrets_file=home / "unread.env"),
            tool_allowlist=frozenset({"clarify"}),
        )

    def test_actual_role_render_has_both_disabled_read_only_servers(self):
        for role in ("mmsecretary", "mmmeta"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                result = plugin.render_disarmed_native_exec_paper(
                    self.profile(Path(tmp), role))
                config = _load_unique_yaml(result.encode("utf-8"))
            self.assertEqual(set(config["mcp_servers"]), {
                "mastermind_steward", *plugin.SERVER_NAMES,
            })
            self.assertEqual(config["toolsets"], ["clarify"])
            for entry in config["mcp_servers"].values():
                self.assertIs(entry["enabled"], False)
                self.assertIs(entry["tools"]["resources"], False)
                self.assertIs(entry["tools"]["prompts"], False)
            self.assertEqual(
                config["mcp_servers"]["mastermind_executive_v3"]["tools"]["include"],
                list(plugin.EXECUTIVE_READ_TOOLS),
            )
            self.assertEqual(
                config["mcp_servers"]["mastermind_paper"]["tools"]["include"],
                list(plugin.PAPER_READ_TOOLS),
            )
            for forbidden in ("submit_ceo_intent", "session_send", "paper_edit",
                              "--allow-write", "127.0.0.1:29979"):
                self.assertNotIn(forbidden, result)

    def test_original_native_model_and_steward_are_preserved(self):
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.profile(Path(tmp), "mmmeta")
            old = _load_unique_yaml(render_disarmed_native_byok(profile).encode())
            new = _load_unique_yaml(
                plugin.render_disarmed_native_exec_paper(profile).encode())
        for key in old:
            if key != "mcp_servers":
                self.assertEqual(old[key], new[key], key)
        self.assertEqual(old["mcp_servers"]["mastermind_steward"],
                         new["mcp_servers"]["mastermind_steward"])

    def test_server_addresses_are_only_existing_owner_env_references(self):
        cfg = plugin.disarmed_server_entries()
        self.assertEqual(
            cfg["mastermind_executive_v3"]["headers"]["Authorization"],
            "Bearer ${MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN}",
        )
        self.assertEqual(cfg["mastermind_executive_v3"]["url"],
                         "${MASTERMIND_EXECUTIVE_V3_MCP_URL}")
        self.assertEqual(cfg["mastermind_paper"]["command"],
                         "${MASTERMIND_PAPER_MCP_PYTHON}")
        self.assertEqual(cfg["mastermind_paper"]["args"],
                         ["${MASTERMIND_PAPER_MCP_SERVER}"])

    def test_executive_tool_names_really_are_read_only_in_current_v3(self):
        from integrations.executive_mcp.web_ceo_v3 import web_ceo_v3_tool_spec
        for name in plugin.EXECUTIVE_READ_TOOLS:
            with self.subTest(tool=name):
                self.assertIs(web_ceo_v3_tool_spec(name).read_only, True)

    def test_pre_enrollment_source_drift_refuses_and_never_mutates_original(self):
        baseline = {
            "toolsets": ["clarify"],
            "agent": {"disabled_toolsets": [
                "terminal", "file", "browser", "delegation", "computer_use",
            ]},
            "mcp_servers": {"mastermind_steward": {"enabled": False}},
        }
        original = baseline["mcp_servers"].copy()
        result = plugin.augment_disarmed_document(baseline)
        self.assertEqual(baseline["mcp_servers"], original)
        self.assertFalse(result["mcp_servers"]["mastermind_paper"]["enabled"])
        mutants = (
            {**baseline, "toolsets": ["clarify", "terminal"]},
            {**baseline, "mcp_servers": {"mastermind_steward": {"enabled": True}}},
            {**baseline, "mcp_servers": {**original, "unreviewed": {"enabled": True}}},
            {**baseline, "agent": {"disabled_toolsets": ["file"]}},
        )
        for mutant in mutants:
            with self.subTest(mutant=repr(mutant)), self.assertRaises(ValueError):
                plugin.augment_disarmed_document(mutant)

    def test_supervisor_catalog_accepts_only_exact_disabled_bytes(self):
        from integrations.hermes_steward.client import ALLOWED_TOOLS
        for role in ("mmsecretary", "mmmeta"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                profile = self.profile(Path(tmp), role)
                rendered = plugin.render_disarmed_native_exec_paper(profile).encode()
                expected = plugin.exact_disarmed_catalog(profile, rendered)
                self.assertEqual(expected, {
                    "mastermind_steward": tuple(ALLOWED_TOOLS),
                    "mastermind_executive_v3": plugin.EXECUTIVE_READ_TOOLS,
                    "mastermind_paper": plugin.PAPER_READ_TOOLS,
                })
                for modified in (
                    rendered + b"\\n",
                    rendered.replace(b"enabled: false", b"enabled: true", 1),
                    rendered.replace(b"paper_read", b"paper_edit", 1),
                    rendered.replace(b"${MASTERMIND_PAPER_MCP_SERVER}", b"/tmp/unsafe.py", 1),
                    rendered[:100],
                    rendered.decode(),
                    b"x" * (64 * 1024 + 1),
                ):
                    with self.subTest(modified_type=type(modified).__name__,
                                      modified_size=len(modified)):
                        self.assertIsNone(plugin.exact_disarmed_catalog(profile, modified))

    def test_duplicate_yaml_rejected_without_installed_effect(self):
        from integrations.hermes_harness import native_byok
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.profile(Path(tmp), "mmmeta")
            with mock.patch.object(
                native_byok, "render_disarmed_native_byok",
                return_value="mcp_servers: {}\nmcp_servers: {}\n",
            ), self.assertRaises(RuntimeRefusal):
                plugin.render_disarmed_native_exec_paper(profile)


class ExecutivePaperInstalledContractTests(unittest.TestCase):
    """Original supervisor/installer, real private files, synthetic credentials.

    The subprocess tests use the existing loopback-only Hermes stand-in.
    They cannot establish a real MCP enrollment or provider authentication.
    """
    def setUp(self):
        import shutil
        from dataclasses import replace
        from integrations.hermes_runtime.tests._support import STUB
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-exec-paper-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = replace(compose_profile(
            "mmsecretary", state_dir=self.root / "state",
            secrets_file=self.root / "secrets.env", hermes_home=self.root / "home",
            gateway_port=0, backend_port=0),
            tool_allowlist=frozenset({"clarify"}), restart_sec=0.01,
            memory_sample_interval_sec=0.02)
        self.stub = self.root / "hermes-stub"
        shutil.copyfile(STUB, self.stub)
        self.stub.chmod(0o700)
        self.native = self.profile.hermes_home / "profiles" / self.profile.role / "config.yaml"
        self.native.parent.mkdir(parents=True)
        self._write_config(plugin.render_disarmed_native_exec_paper(self.profile))

    def _write_config(self, text):
        self.native.write_text(text, encoding="utf-8")
        self.native.chmod(0o600)

    def _runtime(self, *, missing_key=False, key_file=None):
        from integrations.hermes_runtime.secrets import Secrets
        from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
        from integrations.hermes_runtime.supervisor import ServiceRuntime
        from integrations.hermes_runtime.tests._support import CENSUS
        values = {
            "HERMES_NATIVE_EGRESS_ROLE": self.profile.role,
            "HERMES_NATIVE_HTTPS_PROXY": "http://127.0.0.2:18651",
            "ZAI_API_KEY": "synthetic-sibling-provider-key-123456",
            "HERMES_SLACK_BOT_TOKEN": "synthetic-slack-token-123456",
            "MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN": "synthetic-not-enrolled-exec-token",
            "MASTERMIND_PAPER_MCP_PYTHON": "/not-an-enrolled-python",
        }
        if not missing_key:
            values["BYTEPLUS_MODELARK_API_KEY"] = "synthetic-primary-provider-key-123456"
        if key_file is not None:
            from integrations.hermes_models.contract import native_provider
            values[native_provider(self.profile.role, self.profile.native_provider_id).credential_file_env] = str(key_file)
        secrets = Secrets("synthetic-gateway-token-123456", "hermes",
                          "synthetic-dashboard-password-123456", values)
        census = self.root / "census.txt"
        catalog = plugin.exact_disarmed_catalog(self.profile, self.native.read_bytes())
        self.assertIsNotNone(catalog)
        census.write_text(CENSUS.read_text().rstrip() + "\n\nMCP servers:\n" + "".join(
            "  " + name + "  [include only: " + ", ".join(names) + "]\n"
            for name, names in catalog.items()), encoding="utf-8")
        return ServiceRuntime(self.profile, secrets, self.stub,
                              extra_child_env={"HERMES_STUB_TOOLS": str(census),
                                               "HERMES_STUB_COMMIT": PINNED_UPSTREAM_SHA})

    def test_current_install_owner_and_supervisor_agree_for_both_roles(self):
        from dataclasses import replace
        from integrations.hermes_harness.native_byok import expected_native_config
        from integrations.hermes_runtime.supervisor import expected_disabled_mcp
        for role in ("mmsecretary", "mmmeta"):
            profile = replace(self.profile, role=role)
            path = profile.hermes_home / "profiles" / role / "config.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected_native_config(profile), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(expected_disabled_mcp(profile),
                             plugin.exact_disarmed_catalog(profile, path.read_bytes()))

    def test_explicit_evaluation_missing_config_refuses_before_manifest_lookup(self):
        from integrations.hermes_runtime.supervisor import expected_disabled_mcp
        self.native.unlink()
        manifest = self.profile.state_dir / "install-manifest.json"
        exists = Path.exists
        def guarded_exists(path):
            if path == manifest:
                self.fail("explicit evaluation inspected the install manifest")
            return exists(path)
        with mock.patch.object(Path, "exists", guarded_exists):
            with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_MISSING"):
                expected_disabled_mcp(self.profile, evaluation_inputs={})

    def test_disabled_catalog_preserves_only_original_primary_key_and_proxy(self):
        runtime = self._runtime()
        ambient = {"MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN": "ambient-not-a-grant",
                   "MASTERMIND_PAPER_MCP_SERVER": "/ambient/not-authorized.py"}
        with mock.patch.dict(os.environ, ambient):
            env = runtime._model_child_env()
            registry_env = runtime._registry_env()
        self.assertEqual(env["BYTEPLUS_MODELARK_API_KEY"], "synthetic-primary-provider-key-123456")
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.2:18651")
        for name in ("ZAI_API_KEY", "HERMES_GATEWAY_TOKEN", "HERMES_SLACK_BOT_TOKEN",
                     "MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN", "MASTERMIND_PAPER_MCP_SERVER",
                     "MASTERMIND_PAPER_MCP_PYTHON"):
            self.assertNotIn(name, env)
            self.assertNotIn(name, registry_env)
        self.assertNotIn("BYTEPLUS_MODELARK_API_KEY", registry_env)
        runtime._check_registry()

    def test_missing_key_refuses_before_any_child_or_registry_process(self):
        runtime = self._runtime(missing_key=True)
        with mock.patch("subprocess.run") as run, mock.patch("subprocess.Popen") as spawn:
            with self.assertRaisesRegex(RuntimeRefusal, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE"):
                runtime.start()
        run.assert_not_called()
        spawn.assert_not_called()
        self.assertIsNone(runtime.gateway)

    def test_config_drift_during_key_resolution_withholds_environment(self):
        from integrations.hermes_harness import native_model_credential
        runtime = self._runtime()
        resolve = native_model_credential.primary_model_env
        def drift(*args, **kwargs):
            result = resolve(*args, **kwargs)
            self.native.write_bytes(self.native.read_bytes() + b"# drift\n")
            return result
        with mock.patch.object(native_model_credential, "primary_model_env", side_effect=drift):
            with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
                runtime._model_child_env()

    def test_config_permission_revocation_during_key_resolution_withholds_environment(self):
        from integrations.hermes_harness import native_model_credential
        runtime = self._runtime()
        resolve = native_model_credential.primary_model_env
        def revoke(*args, **kwargs):
            result = resolve(*args, **kwargs)
            self.native.chmod(0o644)
            return result
        with mock.patch.object(native_model_credential, "primary_model_env", side_effect=revoke):
            with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_UNSAFE"):
                runtime._model_child_env()

    def test_consumer_mutation_during_key_resolution_withholds_environment(self):
        from integrations.hermes_harness import native_model_credential
        from integrations.hermes_harness.native_byok import expected_native_config
        from integrations.hermes_harness.tests.test_native_executive_consumer import publication_document
        runtime = self._runtime()
        document = publication_document()
        self._write_config(expected_native_config(self.profile, document))
        resolve = native_model_credential.primary_model_env
        def revoke(*args, **kwargs):
            result = resolve(*args, **kwargs)
            document["principal"]["subject_digest"] = "f" * 64
            return result
        with mock.patch.object(runtime, "_consumer_publication", return_value=document):
            with mock.patch.object(native_model_credential, "primary_model_env", side_effect=revoke):
                with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
                    runtime._model_child_env()

    def test_hardlink_symlink_and_enabled_catalog_refuse(self):
        from integrations.hermes_runtime.supervisor import expected_disabled_mcp
        original = self.native.read_bytes()
        alias = self.root / "config-alias"
        os.link(self.native, alias)
        with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_UNSAFE"):
            expected_disabled_mcp(self.profile)
        alias.unlink()
        self.native.rename(alias)
        self.native.symlink_to(alias)
        with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_SYMLINK"):
            expected_disabled_mcp(self.profile)
        self.native.unlink()
        self._write_config(original.decode().replace("enabled: false", "enabled: true", 1))
        with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
            expected_disabled_mcp(self.profile)

    def _wait(self, predicate, timeout=5):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("original local child did not reach expected state")

    def test_start_and_restart_use_same_disabled_catalog_and_never_claim_mcp_connection(self):
        runtime = self._runtime()
        runtime.start()
        self.addCleanup(runtime.stop)
        self._wait(lambda: runtime.child_pid is not None and runtime.health_snapshot()[0] == 200)
        first_pid = runtime.child_pid
        self.assertEqual(set(runtime._expected_disabled_mcp()), {
            "mastermind_steward", "mastermind_executive_v3", "mastermind_paper"})
        os.kill(runtime.child_pid, signal.SIGKILL)
        self._wait(lambda: runtime.child_pid not in (None, first_pid) and runtime.health_snapshot()[0] == 200)
        self.assertGreaterEqual(runtime.restart_count, 1)
        self.assertFalse(runtime.health_snapshot()[1]["provider_authenticated"])
        self.assertFalse(runtime.health_snapshot()[1]["native_model_turn_verified"])

    def test_restart_after_config_tamper_starts_no_replacement(self):
        runtime = self._runtime()
        runtime.start()
        self.addCleanup(runtime.stop)
        self._wait(lambda: runtime.child_pid is not None and runtime.health_snapshot()[0] == 200)
        self._write_config(self.native.read_text().replace("paper_read", "paper_edit", 1))
        os.kill(runtime.child_pid, signal.SIGKILL)
        self._wait(lambda: runtime.failed)
        self.assertEqual(runtime.child_starts, 1)
        self.assertEqual(runtime.refusal_code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_restart_after_primary_key_revocation_starts_no_replacement(self):
        key_file = self.root / "primary-key"
        key_file.write_text("synthetic-file-provider-key-123456", encoding="utf-8")
        key_file.chmod(0o600)
        runtime = self._runtime(key_file=key_file)
        served = self.root / "served-count"
        runtime.extra_child_env["HERMES_STUB_COUNT"] = str(served)
        runtime.start()
        self.addCleanup(runtime.stop)
        self._wait(lambda: runtime.child_pid is not None and runtime.health_snapshot()[0] == 200)
        key_file.unlink()
        os.kill(runtime.child_pid, signal.SIGKILL)
        self._wait(lambda: runtime.failed)
        # child_starts counts attempts before environment qualification. The
        # existing subprocess fixture records actual serve executions.
        self.assertEqual(served.read_text(), "1")
        self.assertIsNone(runtime.child_pid)
        self.assertEqual(runtime.refusal_code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

    def test_legacy_exact_byok_keeps_original_key_without_catalog_upgrade(self):
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        runtime = self._runtime()
        self._write_config(render_disarmed_native_byok(self.profile))
        self.assertEqual(set(runtime._expected_disabled_mcp()), {"mastermind_steward"})
        self.assertIn("BYTEPLUS_MODELARK_API_KEY", runtime._model_child_env())

    def _application_runtime(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from integrations.hermes_application_fabric import publication
        from integrations.hermes_runtime.secrets import Secrets

        self._write_config(plugin.render_disarmed_native_exec_paper(self.profile))
        runtime = self._runtime()
        runtime.profile = replace(
            self.profile, model_provider=publication.PROVIDER,
            model_default="fixture-application-model", native_provider_id=None,
            gateway_backend="native-session-authority",
        )
        document = {
            "schema": publication.SCHEMA, "role": self.profile.role,
            "enrollment_request_id": "fixture-application-enrollment",
            "principal_id": "uid:1001", "macro_root": str(self.root / ("a" * 40)),
            "macro_commit_sha": "a" * 40, "model": "fixture-application-model",
            "max_tokens": 128, "package_sha256": "b" * 64,
        }
        # Held-launch custody is an explicit fixture; configuration and
        # credential selection below use the actual APPLICATION owners.
        runtime._native_launch = SimpleNamespace(
            recipe={"primary_application": document, "vendor_root": str(self.root / "vendor")},
            qualify=lambda *_: None,
        )
        runtime.secrets = Secrets(
            runtime.secrets.token, runtime.secrets.dashboard_username,
            runtime.secrets.dashboard_password,
            {**runtime.secrets.values,
             "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN": "synthetic-application-token-1234567890"},
        )
        self._write_config(publication.expected_native_config(runtime.profile, document))
        return runtime, document

    def test_application_retains_its_own_census_and_only_its_role_credential(self):
        runtime, _ = self._application_runtime()
        self.assertEqual(set(runtime._expected_disabled_mcp()), {"mastermind_steward"})
        with mock.patch(
            "integrations.hermes_runtime.native_gateway_entry.native_git_environment",
            return_value={},
        ):
            env = runtime._model_child_env()
        self.assertEqual(env["HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN"],
                         "synthetic-application-token-1234567890")
        for name in ("BYTEPLUS_MODELARK_API_KEY", "ZAI_API_KEY",
                     "MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN"):
            self.assertNotIn(name, env)

    def test_application_publication_revocation_withholds_prepared_environment(self):
        from integrations.hermes_application_fabric import publication
        for change in ("mutate", "remove"):
            with self.subTest(change=change):
                runtime, document = self._application_runtime()
                before = self.native.read_bytes()
                resolve = publication.primary_child_env
                def revoke(*args, **kwargs):
                    env = resolve(*args, **kwargs)
                    if change == "mutate":
                        document["enrollment_request_id"] = "changed-enrollment"
                    else:
                        runtime._native_launch.recipe.pop("primary_application")
                    return env
                with mock.patch(
                    "integrations.hermes_runtime.native_gateway_entry.native_git_environment",
                    return_value={},
                ), mock.patch.object(publication, "primary_child_env", side_effect=revoke):
                    with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
                        runtime._model_child_env()
                self.assertEqual(self.native.read_bytes(), before)

    def test_selected_child_grant_is_preserved_and_cannot_fall_back(self):
        from dataclasses import replace
        from integrations.hermes_harness.native_byok import expected_native_config
        from integrations.hermes_harness.tests.test_native_executive_consumer import publication_document
        from integrations.hermes_runtime.supervisor import expected_disabled_mcp
        document = publication_document()
        with self.assertRaisesRegex(RuntimeRefusal, "NATIVE_CONSUMER_ROLE_MISMATCH"):
            expected_native_config(replace(self.profile, role="mmmeta"), document)
        config = expected_native_config(self.profile, document)
        self._write_config(config)
        parsed = _load_unique_yaml(config.encode())
        self.assertEqual(parsed["plugins"]["entries"]["native_selected_child_plugin"]["mcp_allowlist"],
                         ["mastermind_coo"])
        self.assertIs(parsed["mcp_servers"]["mastermind_coo"]["enabled"], True)
        self.assertEqual(parsed["mcp_servers"]["mastermind_coo"]["tools"]["include"], [])
        for name in plugin.SERVER_NAMES:
            self.assertIs(parsed["mcp_servers"][name]["enabled"], False)
        self.assertEqual(expected_disabled_mcp(self.profile, document)["mastermind_coo"], ("(none)",))
        with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
            expected_disabled_mcp(self.profile, None)
        self._write_config(expected_native_config(self.profile))
        with self.assertRaisesRegex(RuntimeRefusal, "RUNTIME_NATIVE_CONFIG_DRIFT"):
            expected_disabled_mcp(self.profile, document)


if __name__ == "__main__":
    unittest.main()
