import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t3_computer_use_setup", SOURCE / "scripts/t3_computer_use_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.t3 = self.home / ".t3"
        self.settings = self.t3 / "userdata/settings.json"
        self.homes = [self.t3 / "providers" / name for name in ("fabric", "claude", "disabled")]
        instances = {}
        self.originals = {}
        for i, home in enumerate(self.homes):
            home.mkdir(parents=True)
            instances[home.name] = {"driver": "claudeAgent", "enabled": i < 2,
                                    "config": {"homePath": str(home)}}
            original = {"cached": "preserve", "private": "never-print-this-value",
                        "mcpServers": {"existing": {"command": "existing-command", "env": {"SECRET": "not-for-receipts"}}}}
            self.write_json(home / ".claude.json", original)
            self.originals[home] = (home / ".claude.json").read_bytes()
        self.write_json(self.settings, {"providerInstances": instances, "unrelated": 42})
        quiet = self.home / ".cursor/quiet-computer-use/quiet_mcp.py"
        quiet.parent.mkdir(parents=True)
        quiet.write_bytes(b"qualified quiet fixture")
        binary = quiet.parent / "vendor/peekaboo-macos-arm64/peekaboo"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"qualified binary fixture")
        binary.chmod(0o700)
        self.binary = binary
        browser = self.t3 / "mcp/mmx-browser/server.js"
        browser.parent.mkdir(parents=True)
        browser.write_text("// existing browser owner\n")
        self.write_json(browser.with_name("runtime.json"), {"schema": "mastermind.browser.mcp_runtime/v1"})
        node = self.home / ".local/share/mastermind-runtime/node/bin/node"
        node.parent.mkdir(parents=True)
        node.write_text("#!/bin/sh\n")
        node.chmod(0o700)
        self.patches = [patch.object(setup, "QUIET_SHA256", setup.digest(quiet.read_bytes())),
                        patch.object(setup, "PEEKABOO_SHA256", setup.digest(binary.read_bytes()))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
        path.chmod(0o600)

    def plan(self):
        return setup.make_plan(self.t3, SOURCE, self.home)

    def test_install_preserves_configuration_and_discovers_both_skills(self):
        plan = self.plan()
        self.assertEqual(plan["providers"], ["claude", "fabric"])
        receipt = setup.apply_plan(plan, plan["plan_sha256"])
        self.assertEqual(receipt["state"], "INSTALLED_NOT_CONSUMER_PROVEN")
        for home in self.homes[:2]:
            config = json.loads((home / ".claude.json").read_text())
            self.assertEqual(config["cached"], "preserve")
            self.assertEqual(config["mcpServers"]["existing"]["env"]["SECRET"], "not-for-receipts")
            self.assertEqual(config["mcpServers"]["peekaboo"]["args"][0].split("/")[-1], "quiet_mcp.py")
            for skill in setup.SKILLS:
                self.assertEqual((home / "skills" / skill / "SKILL.md").read_bytes(),
                                 (SOURCE / "skills" / skill / "SKILL.md").read_bytes())
        self.assertEqual((self.homes[2] / ".claude.json").read_bytes(), self.originals[self.homes[2]])
        self.assertFalse((self.homes[2] / "skills").exists())
        saved = Path(receipt["receipt"]).read_text()
        self.assertNotIn("never-print-this-value", saved)
        self.assertNotIn("not-for-receipts", saved)
        self.assertEqual(self.plan()["operations"], [])
        self.assertEqual(setup.apply_plan(self.plan(), self.plan()["plan_sha256"])["state"], "ALREADY_INSTALLED")

    def test_stale_preview_and_changed_dependency_make_no_changes(self):
        plan = self.plan()
        d = json.loads(self.settings.read_text())
        d["newer-setting"] = True
        self.write_json(self.settings, d)
        with self.assertRaises(setup.SetupError):
            setup.apply_plan(self.plan(), plan["plan_sha256"])
        with self.assertRaises(setup.SetupError):
            setup.apply_plan(plan, plan["plan_sha256"])
        for home in self.homes:
            self.assertEqual((home / ".claude.json").read_bytes(), self.originals[home])

    def test_config_writer_after_preview_is_preserved(self):
        plan = self.plan()
        config_path = self.homes[0] / ".claude.json"
        self.write_json(config_path, {"newer-writer": True})
        with self.assertRaises(setup.SetupError):
            setup.apply_plan(plan, plan["plan_sha256"])
        self.assertEqual(json.loads(config_path.read_text()), {"newer-writer": True})

    def test_conflicting_mcp_entry_is_not_overwritten(self):
        p = self.homes[0] / ".claude.json"
        self.write_json(p, {"mcpServers": {"peekaboo": {"command": "someone-elses-owner"}}})
        with self.assertRaisesRegex(setup.SetupError, "Conflicting peekaboo"):
            self.plan()
        self.assertIn("someone-elses-owner", p.read_text())

    def test_existing_empty_env_browser_entry_is_preserved(self):
        p = self.homes[0] / ".claude.json"
        config = json.loads(p.read_text())
        existing = {"type": "stdio", "command": str(self.home / ".local/share/mastermind-runtime/node/bin/node"),
                    "args": [str(self.t3 / "mcp/mmx-browser/server.js")], "env": {}}
        config["mcpServers"]["mmx-browser"] = existing
        self.write_json(p, config)
        plan = self.plan()
        setup.apply_plan(plan, plan["plan_sha256"])
        self.assertEqual(json.loads(p.read_text())["mcpServers"]["mmx-browser"], existing)

    def test_rollback_restores_exact_originals(self):
        plan = self.plan()
        result = setup.apply_plan(plan, plan["plan_sha256"])
        setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        for home in self.homes:
            self.assertEqual((home / ".claude.json").read_bytes(), self.originals[home])
        for home in self.homes[:2]:
            for skill in setup.SKILLS:
                self.assertFalse((home / "skills" / skill).is_symlink())

    def test_rollback_does_not_overwrite_later_provider_updates(self):
        plan = self.plan()
        result = setup.apply_plan(plan, plan["plan_sha256"])
        p = self.homes[0] / ".claude.json"
        newer = json.loads(p.read_text())
        newer["new-cache"] = "keep"
        self.write_json(p, newer)
        with self.assertRaisesRegex(setup.SetupError, "Later change preserved"):
            setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        self.assertEqual(json.loads(p.read_text())["new-cache"], "keep")

    def test_binary_integrity_and_duplicate_json_keys(self):
        self.binary.write_bytes(b"changed binary")
        with self.assertRaisesRegex(setup.SetupError, "binary differs"):
            self.plan()
        self.settings.write_text('{"providerInstances":{},"providerInstances":{}}')
        with self.assertRaisesRegex(setup.SetupError, "Duplicate JSON key"):
            self.plan()

    def test_provider_or_skill_escape_is_refused(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.homes[0] / "skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(setup.SetupError, "escapes T3"):
            self.plan()
        self.assertEqual(list(outside.iterdir()), [])

    def test_unsupported_enabled_provider_is_not_silently_claimed(self):
        d = json.loads(self.settings.read_text())
        d["providerInstances"]["codex"] = {"enabled": True, "driver": "codex"}
        self.write_json(self.settings, d)
        with self.assertRaisesRegex(setup.SetupError, "needs its own adapter"):
            self.plan()

    def test_partial_apply_leaves_exact_reconciliation_receipt(self):
        plan = self.plan()
        real_symlink = os.symlink
        def race(target, link, *args, **kwargs):
            Path(link).mkdir()  # a concurrent writer wins exclusive creation
            return real_symlink(target, link, *args, **kwargs)
        with patch.object(os, "symlink", side_effect=race):
            with self.assertRaisesRegex(setup.SetupError, "reconcile exact targets"):
                setup.apply_plan(plan, plan["plan_sha256"])
        receipts = list((self.t3 / "backups/computer-use").glob("install-*/receipt.json"))
        self.assertEqual(len(receipts), 1)
        data = json.loads(receipts[0].read_text())
        self.assertEqual(data["state"], "PARTIAL_RECONCILE_ORIGINAL_TARGETS")
        self.assertTrue(any(op["state"] == "VERIFIED" for op in data["operations"]))
        self.assertEqual(data["operations"][-1]["state"], "PREPARED")


if __name__ == "__main__":
    unittest.main()
