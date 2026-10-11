"""Host installation tests: explicit opt-in, unchanged legacy configuration."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("workspace_private_service", Path(__file__).with_name("private_service.py"))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class RepositoryWorkspaceInstallTests(unittest.TestCase):
    def configuration(self, enabled=False):
        return service._build_config("test-account", "127.0.0.1", 45025,
            Path("/owned/node"), Path("/owned/backend"), Path("/owned/state"), Path("/owned/home"),
            repository_workspaces=enabled)

    def test_default_profile_does_not_gain_repository_tools(self):
        self.assertNotIn("repositoryWorkspaces", self.configuration())

    def test_explicit_profile_enables_closed_repo_choices_not_model_paths(self):
        value = self.configuration(True)
        self.assertEqual(value["repositoryWorkspaces"], {
            "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]})
        self.assertEqual(value["gitPublish"]["sourceRepository"], "/owned/home/Documents/GitHub/Mastermind")
        with self.assertRaises((ValueError, SystemExit)):
            self.configuration("true")

    def test_source_manifest_includes_consumer_and_preserves_legacy_generations(self):
        self.assertIn("workspace-access.mjs", service.STAGE_FILES)
        prior = frozenset(service.LEGACY_STAGE_FILES_V6) - {"workspace-access.mjs"}
        self.assertIn(prior, service.KNOWN_MANIFEST_FILESETS)
        self.assertIn(prior - {"fleet-status.mjs"}, service.KNOWN_MANIFEST_FILESETS)

    def test_stage_and_upgrade_accept_explicit_opt_in_without_provider_selection(self):
        for command in ["stage", "upgrade"]:
            parsed = service.build_parser().parse_args([command, "--account", "test-account", "--port", "45025",
                "--source", "/owned/source", "--node", "/owned/node", "--backend", "/owned/backend",
                "--enable-repository-workspaces"])
            self.assertIs(parsed.enable_repository_workspaces, True)

    def test_verified_previous_setting_is_retained_without_a_new_opt_in(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"repositoryWorkspaces": {
                "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}}))
            prior = {"configHash": service._sha256_file(config)}
            result = service._repository_workspace_setting(SimpleNamespace(), {"config": config}, prior)
            self.assertIs(result, True)
            config.write_text("{}")
            with self.assertRaises(SystemExit):
                service._repository_workspace_setting(SimpleNamespace(), {"config": config}, prior)


class RepositoryWorkspaceLifecycleTests(unittest.TestCase):
    def test_actual_stage_restage_and_upgrade_preserve_opt_in(self):
        import tempfile
        from unittest import mock
        import private_service_test as fixtures
        native = fixtures.svc
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / "home"
            home.mkdir()
            source = fixtures._make_source(root)
            node = fixtures._make_node(root)
            backend = fixtures._make_backend(root)
            paper_sha = fixtures._seed_paper_runtime(home)
            args = fixtures._stage_args(source, node, backend)
            args.enable_repository_workspaces = True
            with mock.patch.dict("os.environ", {"HOME": str(home)}), \
                 mock.patch.object(native, "PAPER_BRIDGE_SHA256", paper_sha), \
                 mock.patch.object(native, "_run", fixtures.CmdRecorder()):
                fixtures._capture_stdout(lambda: native.cmd_stage(args))
                paths = native._build_runtime_roots("test-account")
                fixtures._seed_node_modules(paths)
                enabled = {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
                self.assertEqual(json.loads(paths["config"].read_text())["repositoryWorkspaces"], enabled)
                args.enable_repository_workspaces = False
                fixtures._capture_stdout(lambda: native.cmd_stage(args))
                self.assertEqual(json.loads(paths["config"].read_text())["repositoryWorkspaces"], enabled)
                upgraded = fixtures._make_upgrade_source(root)
                fixtures._capture_stdout(lambda: native.cmd_upgrade(fixtures._stage_args(upgraded, node, backend)))
                self.assertEqual(json.loads(paths["config"].read_text())["repositoryWorkspaces"], enabled)
                manifest = json.loads(paths["manifest"].read_text())
                self.assertEqual(manifest["configHash"], native._sha256_file(paths["config"]))
                self.assertIn("workspace-access.mjs", manifest["files"])

    def test_retained_enabled_field_is_exact_boolean_not_integer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"repositoryWorkspaces": {
                "enabled": 1, "allowedRepositories": ["mastermind", "macro", "terminal"]}}))
            prior = {"configHash": service._sha256_file(config)}
            with self.assertRaises(SystemExit):
                service._repository_workspace_setting(SimpleNamespace(), {"config": config}, prior)


if __name__ == "__main__":
    unittest.main()
