"""Drive the pack_server.mjs node:test suite from pytest (TSHc F12/F24/F25).

The node suite builds a fake source tree (fake package manager, fake yaml,
canned .ts modules) and a fake HOME, then drives pack_server.mjs as a real
child process, so containment, publication order, leftover cleanup, the
packing lock and failure-log naming are exercised end to end. A node >= 23 is
required because pack_server.mjs imports .ts modules natively; without one the
test skips rather than fails.
"""
import os
import re
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(REPO, "tools", "mmos_team_server", "pack_server.test.mjs")
CANDIDATE_NODES = [
    "/opt/homebrew/bin/node",
    os.path.expanduser(
        "~/.mastermind/mmos_dev/tsh/team-root/runtime/node-v24.22.2-darwin-arm64/bin/node"
    ),
]


def _suitable_node():
    for candidate in CANDIDATE_NODES:
        if not (os.path.isfile(candidate) and os.access(candidate, os.X_OK)):
            continue
        try:
            version = subprocess.run(
                [candidate, "--version"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            continue
        match = re.match(r"v(\d+)\.", version.stdout or "")
        if match and int(match.group(1)) >= 23:
            return candidate
    return None


class PackServerNodeSuite(unittest.TestCase):
    def test_pack_server_node_suite(self):
        node = _suitable_node()
        if node is None:
            self.skipTest("no node >= 23 available (pack_server.mjs imports .ts natively)")
        proc = subprocess.run(
            [node, "--test", SUITE],
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        tail = "\n".join(combined.strip().splitlines()[-10:])
        if proc.returncode == 77 or "SKIP:" in combined:
            self.skipTest(f"node suite skipped: {tail}")
        self.assertEqual(
            proc.returncode, 0, f"node suite failed (exit {proc.returncode}):\n{tail}"
        )


if __name__ == "__main__":
    unittest.main()
