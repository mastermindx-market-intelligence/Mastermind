"""Native transport source-policy regression, with no host or provider effects."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "candidate/remote_sub.sh"

class PolicySourceUpload(unittest.TestCase):
    def test_economic_picker_keeps_policy_yaml_file_path(self):
        script = CONTROLLER.read_text()
        declarations = re.findall(r"^\s*POLICY_SOURCE=([^\n]+)$", script, re.M)
        self.assertEqual(len(declarations), 2)
        self.assertTrue(all("orch/fabric/pools.yaml" in x for x in declarations))
        self.assertEqual(script.count("ECONOMIC_POLICY_DIR="), 1)
        self.assertIn('"$ECONOMIC_POLICY_DIR/pick.py" launch-policy', script)
        self.assertNotIn('"$POLICY_SOURCE/pick.py" launch-policy', script)
        self.assertIn('commission_run policy-upload "$SCP_CMD" -q "$POLICY_SOURCE"', script)

    def test_shell_syntax_without_execution(self):
        subprocess.run(["bash", "-n", str(CONTROLLER)], check=True, capture_output=True)
