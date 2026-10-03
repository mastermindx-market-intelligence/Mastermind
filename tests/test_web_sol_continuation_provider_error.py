from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.chairman_surfaces import web_sol_protocol as protocol
from tests.test_web_sol_continuation_submit import receipt, request


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
    operation_key: `provider-error-${scenario}`,
    issued_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 30000).toISOString(),
    nonce: `provider-error-nonce-${scenario}-00000001`,
    turn_id: `provider-error-turn-${scenario}-0001`,
    directive_digest: '55cca851529f53f89ade6a2abb43880513fcd189dfcda50237ec1369640a06c5',
    session_alias: 'EXECUTIVE-CEO-A',
    runtime_binding_id: 'bind-wsx-' + 'c'.repeat(48),
    runtime_binding_generation: 1,
    runtime_binding_fingerprint: 'd'.repeat(64),
    wake_obligation_ids: ['WAKE-' + 'a'.repeat(32)],
    wake_obligation_digest: '277016348d4e5720093a82a9c63a128cca067db825cf7d5ffbed5c59c3d5d314',
  };
  let probes = 0;
  let sends = 0;
  const observed = (state, providerError) => ({
    conversation_fingerprint: conversation,
    observation: {
      target_present: true,
      exact_conversation_loaded: true,
      auth_required: false,
      provider_error_present: providerError,
      composer_available: true,
      generation_state: state,
    },
  });
  const ops = {
    resolveExactTarget: () => ({status: null, tabId: 7}),
    requestWindowStatus: () => null,
    unknownObservation: () => observed('unknown', null).observation,
    freshProbe: async () => {
      probes += 1;
      if (scenario === 'pre-submit') return observed('idle', true);
      if (probes === 1) return observed('idle', false);
      return observed('active', true);
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
        wake_obligation_ids: message.wake_obligation_ids,
        wake_obligation_digest: message.wake_obligation_digest,
        effect: 'SUBMIT_TRIGGERED',
      };
    },
  };

  const result = await context.MMXWebSolContinuation.handle(request, ops);
  if (scenario === 'pre-submit') {
    assert.equal(result.status, 'CONTINUATION_NOT_SUBMITTED');
    assert.equal(sends, 0, 'a known provider error must refuse before any effect');
  } else if (scenario === 'post-submit') {
    assert.equal(result.status, 'CONTINUATION_SUBMIT_EFFECT_UNKNOWN');
    assert.equal(sends, 1, 'post-submit observation must never cause replay');
  } else {
    throw new Error(`unknown scenario ${scenario}`);
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
"""


@pytest.mark.parametrize("scenario", ["pre-submit", "post-submit"])
def test_provider_error_cannot_submit_or_become_generation_start(scenario: str) -> None:
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


def test_started_receipt_rejects_provider_error_observation() -> None:
    action = request()
    started = receipt(action, "CONTINUATION_STARTED", generation_state="active")
    started["observation"]["provider_error_present"] = True
    with pytest.raises(protocol.WebSolProtocolError, match="provider_error_present"):
        protocol.validate_receipt(started)
