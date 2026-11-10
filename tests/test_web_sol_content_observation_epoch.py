"""Read the real repository content.js in a Node VM; no Chrome/provider operation.

Drop-in unittest/pytest regression for the asynchronous observation coherence repair.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/chairman_surfaces/web_sol_extension/content.js"
HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const crypto = require('node:crypto');
(async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const location = {origin:'https://chatgpt.com', pathname:'/c/synthetic-before'};
  const document = {visibilityState:'visible', readyState:'complete',
    querySelector:selector => selector === '#prompt-textarea' ? {} : null};
  const context = vm.createContext({TextEncoder, Uint8Array, location, document,
    crypto:{subtle:{digest:async (...args) => {await gate;return crypto.webcrypto.subtle.digest(...args);}}},
    chrome:{runtime:{onMessage:{addListener:() => {}},sendMessage:() => {}}}});
  vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
  const fp = crypto.createHash('sha256').update('https://chatgpt.com/c/synthetic-before').digest('hex');
  const result = vm.runInContext(`buildProbe('${fp}')`, context);
  const scenario = process.argv[2];
  if (scenario === 'navigation') location.pathname = '/c/synthetic-after';
  if (scenario === 'visibility') document.visibilityState = 'hidden';
  if (scenario === 'ready') document.readyState = 'loading';
  release();
  if (scenario === 'navigation') {
    await assert.rejects(result, /OBSERVATION_INVALIDATED/);
  } else {
    const probe = await result;
    assert.equal(probe.observation.exact_conversation_loaded, true);
    assert.equal(probe.observation.visibility, 'visible');
    assert.equal(probe.observation.document_ready_state, 'complete');
    assert.equal(probe.observation.schema, 'mastermind.web_sol_surface_probe.v1');
    assert.equal(Object.keys(probe.observation).length, 10);
  }
})().catch(error => {console.error(error.message);process.exitCode=1;});
"""


class WebSolContentObservationEpochTests(unittest.TestCase):
    def run_scenario(self, scenario: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required; do not skip this gate")
        self.assertTrue(SOURCE.is_file(), "Real repository source must exist")
        result = subprocess.run(
            [node, "-e", HARNESS, str(SOURCE), scenario],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_navigation_during_hash_refuses_previous_conversation(self):
        self.run_scenario("navigation")

    def test_visibility_is_captured_at_same_observation_instant(self):
        self.run_scenario("visibility")

    def test_ready_state_is_captured_at_same_observation_instant(self):
        self.run_scenario("ready")

    def test_unchanged_conversation_preserves_v1_contract(self):
        self.run_scenario("unchanged")


if __name__ == "__main__":
    unittest.main()
