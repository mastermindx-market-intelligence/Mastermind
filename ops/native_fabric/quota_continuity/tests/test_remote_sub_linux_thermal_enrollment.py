"""Source-only regression of the incumbent host-registry gate in remote_sub.sh.

Tests run the actual inline registry validator against local, inert JSON files.
They never call remote_sub.sh, SSH, a provider, or the Fabric lease broker.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "candidate" / "remote_sub.sh"


def registry_validator_source() -> str:
    text = LAUNCHER.read_text(encoding="utf-8")
    owner = text.index("load_host_registry() {")
    start = text.index("import json, sys\nfrom pathlib import Path\n", owner)
    end = text.index("\n' \"$HOSTS_SOURCE\" \"$HOST_ARG\"", start)
    return text[start:end]


class NativeLauncherThermalPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.registry = Path(temp.name) / "hosts.json"
        self.entry = {
            "ssh_alias": "ubuntu0",
            "cores": 8,
            "max_active": 4,
            "load_gate": 4,
            "roles": ["lanes"],
            "allowed_modes": ["glm"],
            "platform": "linux",
            "require_thermal": True,
            "cpu_tctl_limit_c": 80,
        }

    def validate(self, entry: dict) -> subprocess.CompletedProcess[str]:
        self.registry.write_text(json.dumps({"ubuntu0": entry}), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-I", "-S", "-c", registry_validator_source(),
             str(self.registry), "ubuntu0", "glm", str(ROOT / "candidate")],
            text=True, capture_output=True, timeout=5, check=False,
        )

    def test_enrolled_linux_worker_preserves_physical_limit(self):
        result = self.validate(dict(self.entry))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[5], "80")

    def test_linux_missing_or_false_enrollment_rejected(self):
        for variant in ("missing", "false", "malformed"):
            with self.subTest(variant=variant):
                entry = dict(self.entry)
                if variant == "missing":
                    entry.pop("require_thermal")
                elif variant == "false":
                    entry["require_thermal"] = False
                else:
                    entry["require_thermal"] = "true"
                result = self.validate(entry)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, "")

    def test_unknown_platform_refused(self):
        for variant in ("missing", "freebsd"):
            with self.subTest(variant=variant):
                entry = dict(self.entry)
                if variant == "missing":
                    entry.pop("platform")
                else:
                    entry["platform"] = variant
                self.assertEqual(self.validate(entry).returncode, 3)

    def test_darwin_without_linux_guard_retains_separate_path(self):
        entry = dict(self.entry, platform="darwin")
        entry.pop("require_thermal")
        entry.pop("cpu_tctl_limit_c")
        result = self.validate(entry)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[5], "0")

    def test_ill_formed_thermal_limit_is_not_admitted(self):
        for limit in (49, 101, "80", True):
            with self.subTest(limit=limit):
                entry = dict(self.entry, cpu_tctl_limit_c=limit)
                self.assertEqual(self.validate(entry).returncode, 3)


if __name__ == "__main__":
    unittest.main()
