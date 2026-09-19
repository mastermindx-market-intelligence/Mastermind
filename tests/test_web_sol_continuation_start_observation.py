from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "integrations/chairman_surfaces/web_sol_extension/continuation_core.js"

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
  const source = fs.readFileSync(process.argv[1], 'utf8');
  const scenario = process.argv[2];
  const context = vm.createContext({
    Promise, Set, Object, Array, String, Number, RegExp,
    setTimeout: (callback, _delay) => { callback(); return 0; },
    clearTimeout: () => {},
  });
  vm.runInContext(source, context, {filename: 'continuation_core.js'});

  const conversation = 'a'.repeat(64);
  const request = {
    schema: 'mastermind.web_sol_surface_action.v1',
    binding_id: '11111111-1111-4111-8111-111111111111',
    conversation_fingerprint: conversation,
    binding_fingerprint: 'b'.repeat(64),
    action: 'SUBMIT_CONTINUATION',
    operation_key: `start-observation-${scenario}`,
    issued_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 30000).toISOString(),
    nonce: `continuation-nonce-${scenario}-00000001`,
    turn_id: `ohf-turn-r3-${scenario}-0001`,
    directive_digest: 'cde0de54629786dcd6c0ee3b169558cf050de48b828a4da15cbd2d881c66afd9',
    session_alias: 'EXECUTIVE-CEO-A',
    runtime_binding_id: 'bind-wsx-' + 'c'.repeat(48),
    runtime_binding_generation: 1,
    runtime_binding_fingerprint: 'd'.repeat(64),
  };
  let probes = 0;
  let sends = 0;
  const observed = (state) => ({
    conversation_fingerprint: conversation,
    observation: {
      target_present: true,
      exact_conversation_loaded: true,
      auth_required: false,
      composer_available: true,
      generation_state: state,
    },
  });
  const ops = {
    resolveExactTarget: () => ({status: null, tabId: 7}),
    requestWindowStatus: () => null,
    unknownObservation: () => observed('unknown').observation,
    freshProbe: async () => {
      probes += 1;
      const state = scenario === 'delayed-active' && probes >= 3 ? 'active' : 'idle';
      return observed(state);
    },
    sendMessage: async (_tabId, message) => {
      sends += 1;
      return {
        schema: 'mastermind.web_sol_continuation_submit_result.v1',
        conversation_fingerprint: conversation,
        turn_id: message.turn_id,
        directive_digest: message.directive_digest,
        session_alias: message.session_alias,
        runtime_binding_id: message.runtime_binding_id,
        runtime_binding_generation: message.runtime_binding_generation,
        runtime_binding_fingerprint: message.runtime_binding_fingerprint,
        effect: 'SUBMIT_TRIGGERED',
      };
    },
  };

  const result = await context.MMXWebSolContinuation.handle(request, ops);
  assert.equal(sends, 1, 'observation must never resubmit the continuation');
  if (scenario === 'delayed-active') {
    assert.equal(result.status, 'CONTINUATION_STARTED');
    assert.equal(probes, 3, 'START should be accepted on a later fresh probe');
  } else if (scenario === 'never-active') {
    assert.equal(result.status, 'CONTINUATION_SUBMIT_EFFECT_UNKNOWN');
    assert.equal(probes, 11, 'observation must remain bounded after one pre-submit probe');
  } else {
    throw new Error(`unknown scenario ${scenario}`);
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
"""


@pytest.mark.parametrize("scenario", ["delayed-active", "never-active"])
def test_post_submit_start_observation_is_bounded_and_never_resends(scenario: str) -> None:
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(
        [node, "-e", HARNESS, str(CORE), scenario],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
