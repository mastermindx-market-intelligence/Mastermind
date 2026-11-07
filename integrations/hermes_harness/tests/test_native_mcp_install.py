"""Real installer-level tests for the disabled native Hermes MCP configuration.

No network connection, model key, MCP bearer token, systemd start, or Slack.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness import native_mcp
from integrations.hermes_harness.cli import _install
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests._support import write_secrets
from integrations.hermes_steward.client import ALLOWED_TOOLS
from integrations.hermes_steward.config_guard import _load_unique_yaml

ROOT = Path(__file__).resolve().parents[3]
STUB = ROOT / "integrations" / "hermes_runtime" / "tests" / "fixtures" / "hermes_stub.py"


class NativeStewardConfigTests(unittest.TestCase):
    def _profile(self, root: Path):
        return compose_profile(
            "mmsecretary",
            state_dir=root / "state",
            secrets_file=root / "secrets.env",
        )

    def test_native_steward_present_but_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as path:
            text = native_mcp.render_disarmed_native_config(self._profile(Path(path)))
        parsed = _load_unique_yaml(text.encode("utf-8"))
        self.assertEqual(parsed["toolsets"], ["clarify"])
        self.assertIn("delegation", parsed["agent"]["disabled_toolsets"])
        self.assertEqual(set(parsed["mcp_servers"]), {"mastermind_steward"})
        entry = parsed["mcp_servers"]["mastermind_steward"]
        self.assertIs(entry["enabled"], False)
        self.assertEqual(entry["url"], "${MASTERMIND_STEWARD_MCP_URL}")
        self.assertEqual(
            entry["headers"],
            {"Authorization": "Bearer ${MASTERMIND_STEWARD_ACCESS_TOKEN}"},
        )
        self.assertEqual(entry["tools"]["include"], list(ALLOWED_TOOLS))
        self.assertIs(entry["tools"]["resources"], False)
        self.assertIs(entry["tools"]["prompts"], False)
        self.assertEqual(text.count("mcp_servers:"), 1)
        self.assertNotIn("xoxb-", text)
        self.assertNotIn("sk-", text)

    def test_meta_ceo_has_same_six_reads_and_no_write_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            p = compose_profile("mmmeta", state_dir=root / "state", secrets_file=root / "secrets.env")
            text = native_mcp.render_disarmed_native_config(p)
        parsed = _load_unique_yaml(text.encode("utf-8"))
        self.assertEqual(parsed["mcp_servers"]["mastermind_steward"]["tools"]["include"], list(ALLOWED_TOOLS))
        self.assertIs(parsed["mcp_servers"]["mastermind_steward"]["enabled"], False)
        self.assertEqual(set(parsed["mcp_servers"]), {"mastermind_steward"})
        self.assertNotIn("mmx_delegate", text)
        self.assertIn("delegation", parsed["agent"]["disabled_toolsets"])

    def test_source_drift_extra_tool_or_missing_source_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = native_mcp._SOURCE.read_text(encoding="utf-8")
            forged = root / "unsafe.yaml"
            self.assertIn("        - resolve_surface", source)
            forged.write_text(
                source.replace(
                    "        - resolve_surface",
                    "        - resolve_surface\n        - write_company_state",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(native_mcp, "_SOURCE", forged):
                with self.assertRaises(RuntimeRefusal) as exc:
                    native_mcp.render_disarmed_native_config(self._profile(root))
                self.assertEqual(exc.exception.code, "NATIVE_MCP_SOURCE_UNQUALIFIED")
            with mock.patch.object(native_mcp, "_SOURCE", root / "missing.yaml"):
                with self.assertRaises(RuntimeRefusal) as exc:
                    native_mcp.render_disarmed_native_config(self._profile(root))
                self.assertEqual(exc.exception.code, "NATIVE_MCP_SOURCE_UNAVAILABLE")

    def test_harness_install_writes_actual_disarmed_native_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            unit_dir = root / "config" / "systemd" / "user"
            upstream = root / "upstream"
            upstream.mkdir()
            (upstream / "PINNED_FIXTURE_ONLY").write_text("fixture\n", encoding="utf-8")
            secrets = root / "secrets.env"
            write_secrets(secrets)
            # Each installer test owns its executable fixture; do not depend
            # on another suite chmod-ing the tracked, non-executable source.
            stub = root / "hermes-stub"
            shutil.copyfile(STUB, stub)
            stub.chmod(0o700)
            payload = _install(
                argparse.Namespace(
                    role="mmsecretary",
                    state=state,
                    systemd_user_dir=unit_dir,
                    secrets_file=secrets,
                    hermes_bin=stub,
                    upstream_source=upstream,
                    fetch=False,
                )
            )
            self.assertEqual(payload["status"], "INSTALLED")
            self.assertEqual(payload["native_steward_mcp"], "CONFIGURED_DISABLED")
            self.assertEqual(payload["native_model_profile"], "CONFIGURED_KEY_NAMES_ONLY")
            self.assertIs(payload["provider_called"], False)
            self.assertIs(payload["extensions_registered"], False)
            from integrations.hermes_runtime.profile import load_profile
            real_profile = load_profile(state / "current" / "profile.yaml")
            self.assertEqual(real_profile.tool_allowlist, frozenset({"clarify"}))
            self.assertEqual(real_profile.extension_allowlist, frozenset())
            self.assertIs(payload["native_steward_connected"], False)
            self.assertEqual(payload["native_executive_v3_mcp"], "CONFIGURED_DISABLED")
            self.assertEqual(payload["native_paper_mcp"], "CONFIGURED_DISABLED")
            self.assertIs(payload["native_executive_v3_connected"], False)
            self.assertIs(payload["native_paper_connected"], False)
            self.assertIs(payload["upstream_attested"], False)
            native = state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "config.yaml"
            self.assertTrue(native.is_file())
            self.assertEqual(stat.S_IMODE(native.stat().st_mode), 0o600)
            parsed = _load_unique_yaml(native.read_bytes())
            from integrations.hermes_harness.executive_paper_mcp import exact_disarmed_catalog
            from integrations.hermes_runtime.supervisor import expected_disabled_mcp
            catalog = exact_disarmed_catalog(real_profile, native.read_bytes())
            self.assertIsNotNone(catalog)
            self.assertEqual(expected_disabled_mcp(real_profile), catalog)
            self.assertEqual(set(parsed["mcp_servers"]), {
                "mastermind_steward", "mastermind_executive_v3", "mastermind_paper",
            })
            self.assertIs(parsed["mcp_servers"]["mastermind_steward"]["enabled"], False)
            self.assertEqual(parsed["model"]["provider"], "byteplus-modelark")
            self.assertEqual(parsed["model"]["default"], "glm-5-3-flash-260828")
            self.assertEqual(parsed["model"]["key_env"], "BYTEPLUS_MODELARK_API_KEY")
            self.assertNotIn("auxiliary", parsed)
            self.assertNotIn("fallback_model", parsed)
            self.assertIs(parsed["providers"]["cursor-pool"]["enabled"], False)
            self.assertEqual(
                parsed["mcp_servers"]["mastermind_steward"]["tools"]["include"],
                list(ALLOWED_TOOLS),
            )
            manifest = json.loads((state / "install-manifest.json").read_text(encoding="utf-8"))
            unit = Path(manifest["unit_path"])
            self.assertEqual(stat.S_IMODE(unit.stat().st_mode), 0o600)
            policy = state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "SOUL.md"
            self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o600)
            receipt = json.loads((state / "current" / "install-receipt.json").read_text(encoding="utf-8"))
            import hashlib
            self.assertEqual(receipt["hermes_config_sha256"], hashlib.sha256(native.read_bytes()).hexdigest())
            self.assertFalse(manifest.get("production_armed", False))
            self.assertTrue(secrets.is_file())
            self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o600)

    def test_catalog_upgrade_and_rollback_restore_exact_legacy_configuration(self) -> None:
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        from integrations.hermes_harness.stack import write_composed_profile
        from integrations.hermes_runtime.install import install, rollback
        from integrations.hermes_runtime.profile import load_profile
        from integrations.hermes_runtime.supervisor import expected_disabled_mcp
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state, secrets, source = root / "state", root / "secrets.env", root / "upstream"
            source.mkdir()
            (source / "FIXTURE_ONLY").write_text("not an attested vendor checkout\n")
            write_secrets(secrets)
            stub = root / "hermes-stub"
            shutil.copyfile(STUB, stub)
            stub.chmod(0o700)
            profile_path = root / "profile.yaml"
            write_composed_profile("mmsecretary", state_dir=state, secrets_file=secrets,
                                   dest=profile_path, installed_native_only=True)
            unit_dir = root / "systemd" / "user"
            first = install(profile_path=profile_path, state_dir=state, systemd_user_dir=unit_dir,
                            secrets_file=secrets, hermes_bin=stub, upstream_source=source,
                            hermes_config_renderer=render_disarmed_native_byok)
            native = state / "current/hermes-home/profiles/mmsecretary/config.yaml"
            before = native.read_bytes()
            upgraded = _install(argparse.Namespace(
                role="mmsecretary", state=state, systemd_user_dir=unit_dir,
                secrets_file=secrets, hermes_bin=stub, upstream_source=source, fetch=False))
            self.assertNotEqual(upgraded["release"], first["release"])
            self.assertNotEqual(native.read_bytes(), before)
            current = load_profile(state / "current/profile.yaml")
            self.assertEqual(set(expected_disabled_mcp(current)), {
                "mastermind_steward", "mastermind_executive_v3", "mastermind_paper"})
            rolled = rollback(state)
            self.assertEqual(rolled["release"], first["release"])
            self.assertEqual(native.read_bytes(), before)
            restored = load_profile(state / "current/profile.yaml")
            self.assertEqual(expected_disabled_mcp(restored), {
                "mastermind_steward": tuple(ALLOWED_TOOLS)})
            self.assertEqual(stat.S_IMODE(native.stat().st_mode), 0o600)

    def test_native_rollback_refuses_changed_source_recipe_before_switch(self) -> None:
        from integrations.hermes_runtime.install import rollback
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            launcher = state / "original-hermes"
            launcher.write_text("fixture\n")
            receipt = {"native_gateway": {"fixture_generation": "old"},
                       "native_adapter_sha256": "a" * 64,
                       "native_launcher_sha256": "b" * 64,
                       "profile_sha256": "c" * 64,
                       "hermes_config_sha256": "e" * 64}
            for generation in ("1", "2"):
                release = state / "releases" / generation
                (release / "bin").mkdir(parents=True)
                (release / "bin/hermes").symlink_to(launcher)
                candidate = dict(receipt)
                (release / "install-receipt.json").write_text(json.dumps(candidate))
            (state / "current").symlink_to("releases/2")
            for field in ("native_adapter_sha256", "hermes_config_sha256"):
                candidate = dict(receipt, **{field: "d" * 64})
                (state / "releases/2/install-receipt.json").write_text(json.dumps(candidate))
                with self.subTest(field=field), self.assertRaisesRegex(
                        RuntimeRefusal, "NATIVE_ROLLBACK_REQUIRES_MATCHING_RELEASE_RECIPE"):
                    rollback(state)
                self.assertEqual(os.readlink(state / "current"), "releases/2")
            for missing_digest in (None, "", "x" * 64):
                candidate = dict(receipt, hermes_config_sha256=missing_digest)
                for generation in ("1", "2"):
                    (state / "releases" / generation / "install-receipt.json").write_text(json.dumps(candidate))
                with self.subTest(digest=missing_digest), self.assertRaisesRegex(
                        RuntimeRefusal, "NATIVE_ROLLBACK_REQUIRES_MATCHING_RELEASE_RECIPE"):
                    rollback(state)
                self.assertEqual(os.readlink(state / "current"), "releases/2")
            # An unchanged complete native recipe remains eligible.
            (state / "releases/1/install-receipt.json").write_text(json.dumps(receipt))
            (state / "releases/2/install-receipt.json").write_text(json.dumps(receipt))
            (state / "install-manifest.json").write_text(json.dumps({"current_release": "2"}))
            self.assertEqual(rollback(state)["release"], "1")

    def test_catalog_import_is_in_original_release_paths_without_checkout_fallback(self) -> None:
        import ast
        import subprocess
        import sys
        import textwrap
        module = ast.parse((ROOT / "scripts/enroll_linux_secondary_worker.py").read_text())
        release_paths = next(ast.literal_eval(node.value) for node in module.body
                             if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == "RELEASE_PATHS"
                                     for target in node.targets))
        with tempfile.TemporaryDirectory() as raw:
            staged = Path(raw) / "release"
            for name in ("control_plane", "common", "integrations/__init__.py",
                         "integrations/hermes_runtime",
                         "integrations/hermes_harness", "integrations/hermes_models",
                         "integrations/hermes_steward", "integrations/hermes_qualification",
                         "integrations/business_mcp_auth/__init__.py",
                         "integrations/business_mcp_auth/claims.py",
                         "integrations/business_mcp_auth/contracts.py",
                         "integrations/mastermind_secretary_mcp/__init__.py",
                         "integrations/mastermind_secretary_mcp/schemas.py"):
                self.assertIn(name, release_paths)
                if (ROOT / name).is_dir():
                    shutil.copytree(ROOT / name, staged / name,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    (staged / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, staged / name)
            helper = staged / "integrations/hermes_harness/executive_paper_mcp.py"
            self.assertEqual(helper.read_bytes(),
                             (ROOT / "integrations/hermes_harness/executive_paper_mcp.py").read_bytes())
            script = textwrap.dedent('''
                import json, sys
                from pathlib import Path
                root = Path(sys.argv[1])
                sys.path.insert(0, str(root))
                from integrations.hermes_runtime.profile import load_profile
                from integrations.hermes_harness.native_byok import expected_native_config
                from integrations.hermes_steward.config_guard import _load_unique_yaml
                result = {}
                for role in ("mmsecretary", "mmmeta"):
                    profile = load_profile(root / "integrations/hermes_runtime/profiles" / (role + ".yaml"),
                                           state_dir=root.parent / role, secrets_file=root.parent / "unused.env")
                    result[role] = sorted(_load_unique_yaml(expected_native_config(profile).encode())["mcp_servers"])
                print(json.dumps(result))
            ''')
            command = [sys.executable, "-I", "-B", "-c", script, str(staged)]
            result = subprocess.run(command, cwd=raw, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {role: [
                "mastermind_executive_v3", "mastermind_paper", "mastermind_steward"]
                for role in ("mmsecretary", "mmmeta")})
            helper.unlink()
            refused = subprocess.run(command, cwd=raw, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("executive_paper_mcp", refused.stderr)


if __name__ == "__main__":
    unittest.main()
