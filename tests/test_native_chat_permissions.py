"""Fail closed when a future native command or capability bypasses chat isolation."""
import json
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).parents[1] / "app/mastermind_os/src-tauri"


class NativeChatPermissionInventory(unittest.TestCase):
    def test_every_registered_command_is_permission_controlled(self):
        source = (ROOT / "src/main.rs").read_text().split("tauri::generate_handler![", 1)[1].split("])", 1)[0]
        actual = {row.strip().rstrip(",").split("::")[-1] for row in source.splitlines() if row.strip()}
        declared = re.findall(r'"([a-z][a-z0-9_]+)"', (ROOT / "application_commands.rs").read_text())
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(actual, set(declared))
        permissions = tomllib.loads((ROOT / "permissions/local-main-application.toml").read_text())
        self.assertEqual(set(permissions["permission"][0]["commands"]["allow"]), actual)

    def test_only_local_main_is_granted_native_privileges(self):
        config = json.loads((ROOT / "tauri.conf.json").read_text())
        self.assertEqual(config["app"]["security"]["capabilities"], ["main"])
        capability = json.loads((ROOT / "capabilities/main.json").read_text())
        self.assertNotIn("windows", capability)
        self.assertNotIn("remote", capability)
        self.assertEqual(capability["webviews"], ["main"])
        self.assertTrue(capability["local"])
        self.assertEqual(set(capability["permissions"]), {"local-main-application", "core:event:allow-listen", "core:event:allow-unlisten"})


if __name__ == "__main__": unittest.main()
