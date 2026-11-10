import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t3_computer_use_setup", SOURCE / "scripts/t3_computer_use_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

LEGACY_BROWSER = b'''const readline = require("node:readline");
function send(object) { process.stdout.write(JSON.stringify(object) + "\\n"); }
readline.createInterface({input: process.stdin}).on("line", line => {
  const m = JSON.parse(line);
  if (m.id === undefined) return;
  if (m.method === "initialize") send({id:m.id,result:{protocolVersion:m.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:"fixture",version:"1"}}});
  else if (m.method === "tools/list") send({id:m.id,result:{tools:[{name:"mmx_browser",inputSchema:{type:"object"}}]}});
  else send({id:m.id,error:{code:-32601,message:"Method not found"}});
});
'''
FIXED_BROWSER = LEGACY_BROWSER.replace(
    b'JSON.stringify(object)', b'JSON.stringify({ ...object, jsonrpc: "2.0" })')


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
        browser.write_bytes(LEGACY_BROWSER)
        self.browser = browser
        self.write_json(browser.with_name("runtime.json"), {"schema": "mastermind.browser.mcp_runtime/v1"})
        node = self.home / ".local/share/mastermind-runtime/node/bin/node"
        node.parent.mkdir(parents=True)
        node.write_text("#!/bin/sh\n")
        node.chmod(0o700)
        cli = self.home / ".local/bin/claude"
        cli.parent.mkdir(parents=True)
        cli.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
path = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".claude.json"
data = json.loads(path.read_text())
servers = data.setdefault("mcpServers", {})
assert sys.argv[1] == "mcp" and sys.argv[3:5] == ["--scope", "user"]
name = sys.argv[5]
if sys.argv[2] == "add-json":
    if name in servers:
        sys.exit(3)
    servers[name] = json.loads(sys.argv[6])
elif sys.argv[2] == "remove":
    del servers[name]
else:
    sys.exit(4)
path.write_text(json.dumps(data, indent=2) + "\\n")
''')
        cli.chmod(0o700)
        self.patches = [patch.object(setup, "QUIET_SHA256", setup.digest(quiet.read_bytes())),
                        patch.object(setup, "PEEKABOO_SHA256", setup.digest(binary.read_bytes())),
                        patch.object(setup, "BROWSER_SERVER_ORIGINAL_SHA256", setup.digest(LEGACY_BROWSER)),
                        patch.object(setup, "BROWSER_SERVER_FIXED_SHA256", setup.digest(FIXED_BROWSER))]
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
        self.assertEqual(self.browser.read_bytes(), FIXED_BROWSER)
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
        self.assertEqual(self.browser.read_bytes(), LEGACY_BROWSER)
        for home in self.homes:
            self.assertEqual(json.loads((home / ".claude.json").read_text()), json.loads(self.originals[home]))
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
        setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        self.assertEqual(json.loads(p.read_text())["new-cache"], "keep")

    def test_owner_api_preserves_writer_between_precheck_and_mutation(self):
        plan = self.plan()
        real_command = setup.run_mcp_command
        def writer_then_owner(op, remove=False):
            p = Path(op["path"])
            data = json.loads(p.read_text())
            data["concurrent-sdk-cache"] = "preserved"
            self.write_json(p, data)
            return real_command(op, remove)
        with patch.object(setup, "run_mcp_command", side_effect=writer_then_owner):
            result = setup.apply_plan(plan, plan["plan_sha256"])
            setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        for home in self.homes[:2]:
            self.assertEqual(json.loads((home / ".claude.json").read_text())["concurrent-sdk-cache"], "preserved")

    def test_rollback_preserves_changed_mcp_entry(self):
        plan = self.plan()
        result = setup.apply_plan(plan, plan["plan_sha256"])
        p = self.homes[0] / ".claude.json"
        data = json.loads(p.read_text())
        data["mcpServers"]["peekaboo"] = {"command": "new-owner"}
        self.write_json(p, data)
        with self.assertRaisesRegex(setup.SetupError, "Later change preserved"):
            setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        self.assertEqual(json.loads(p.read_text())["mcpServers"]["peekaboo"], {"command": "new-owner"})

    def test_interrupted_rollback_reconciles_completed_effect_without_replay(self):
        plan = self.plan()
        result = setup.apply_plan(plan, plan["plan_sha256"])
        receipt_path = Path(result["receipt"])
        real_restore = setup.restore_operation
        first_path = None
        def interrupted(op):
            nonlocal first_path
            first_path = op["path"]
            real_restore(op)
            raise KeyboardInterrupt("after effect, before readback")
        with patch.object(setup, "restore_operation", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                setup.rollback(receipt_path, result["receipt_sha256"])
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["state"], "ROLLING_BACK")
        self.assertEqual(receipt["operations"][-1]["rollback_state"], "PREPARED")
        with patch.object(setup, "restore_operation", wraps=real_restore) as restore:
            setup.rollback(receipt_path, setup.digest(receipt_path.read_bytes()))
            self.assertNotIn(first_path, [call.args[0]["path"] for call in restore.call_args_list])
        self.assertEqual(json.loads(receipt_path.read_text())["state"], "ROLLED_BACK")

    def test_failed_owner_command_is_not_replayed_or_replaced_with_file_write(self):
        plan = self.plan()
        with patch.object(setup, "run_mcp_command", side_effect=setup.SetupError("owner refused")) as command:
            with self.assertRaisesRegex(setup.SetupError, "reconcile exact targets"):
                setup.apply_plan(plan, plan["plan_sha256"])
            self.assertEqual(command.call_count, 1)
        for home in self.homes:
            self.assertEqual((home / ".claude.json").read_bytes(), self.originals[home])

    def test_binary_integrity_and_duplicate_json_keys(self):
        self.binary.write_bytes(b"changed binary")
        with self.assertRaisesRegex(setup.SetupError, "binary differs"):
            self.plan()
        self.settings.write_text('{"providerInstances":{},"providerInstances":{}}')
        with self.assertRaisesRegex(setup.SetupError, "Duplicate JSON key"):
            self.plan()

    def test_browser_protocol_repair_preserves_unknown_and_newer_writers(self):
        self.browser.write_bytes(LEGACY_BROWSER + b"// newer owner\n")
        with self.assertRaisesRegex(setup.SetupError, "browser adapter differs"):
            self.plan()
        self.browser.write_bytes(LEGACY_BROWSER)
        plan = self.plan()
        self.browser.write_bytes(LEGACY_BROWSER + b"// concurrent owner\n")
        with self.assertRaisesRegex(setup.SetupError, "Dependency changed"):
            setup.apply_plan(plan, plan["plan_sha256"])
        self.assertTrue(self.browser.read_bytes().endswith(b"// concurrent owner\n"))

    def test_browser_protocol_repair_initialization_catalog_and_errors(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the MCP wire contract")
        requests = [
            {"jsonrpc": "2.0", "id": "init", "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "unknown"},
        ]
        wire = "".join(json.dumps(m) + "\n" for m in requests)
        def exchange():
            output = subprocess.run([node, str(self.browser)], input=wire, text=True,
                                    capture_output=True, check=True, timeout=10)
            return [json.loads(line) for line in output.stdout.splitlines()]
        self.assertTrue(all("jsonrpc" not in m for m in exchange()))
        plan = self.plan()
        setup.apply_plan(plan, plan["plan_sha256"])
        messages = exchange()
        self.assertEqual([m["id"] for m in messages], ["init", 2, 3])
        self.assertTrue(all(m.get("jsonrpc") == "2.0" for m in messages))
        self.assertTrue(all(("result" in m) != ("error" in m) for m in messages))
        self.assertEqual(messages[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(messages[1]["result"]["tools"][0]["name"], "mmx_browser")
        self.assertEqual(messages[2]["error"]["code"], -32601)

    def test_browser_skill_distribution_needs_no_mac_binary_or_mcp_configuration(self):
        shutil.rmtree(self.home / ".cursor")
        shutil.rmtree(self.t3 / "mcp")
        shutil.rmtree(self.home / ".local")
        for home in self.homes:
            (home / ".claude.json").unlink()
        plan = setup.make_plan(self.t3, SOURCE, self.home, browser_skills_only=True)
        self.assertEqual(plan["components"], ["browser-skills"])
        result = setup.apply_plan(plan, plan["plan_sha256"])
        for home in self.homes[:2]:
            self.assertTrue((home / "skills/mastermind-browser-use/SKILL.md").is_file())
            self.assertFalse((home / "skills/mastermind-computer-use").exists())
            self.assertFalse((home / ".claude.json").exists())
        self.assertFalse((self.homes[2] / "skills").exists())
        setup.rollback(Path(result["receipt"]), result["receipt_sha256"])
        self.assertFalse((self.t3 / "skills/mastermind-browser-use/SKILL.md").exists())

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
