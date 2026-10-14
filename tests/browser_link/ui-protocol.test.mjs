import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePopupMessage } from '../../integrations/mastermind_browser_link/extension/ui-protocol.mjs';

const id = 'a'.repeat(32);
const popup = `chrome-extension://${id}/popup.html`;
const sender = { id, url: popup };

test('only the exact extension popup may establish local sharing', () => {
  assert.equal(validatePopupMessage({ kind: 'share_current' }, sender, id, popup).kind, 'share_current');
  for (const foreign of [
    { id, url: 'https://example.test/' },
    { id: 'b'.repeat(32), url: popup },
    { id, url: popup + '?spoof=1' },
  ]) {
    assert.throws(
      () => validatePopupMessage({ kind: 'share_current' }, foreign, id, popup),
      { code: 'UI_SENDER_REFUSED' },
    );
  }
});

test('popup cannot choose an arbitrary share target or submit native commands', () => {
  for (const message of [
    { kind: 'share_current', tab_id: 42 },
    { kind: 'click' },
    { kind: 'status', actor: 'admin' },
    { kind: 'revoke', tab_id: -1 },
  ]) {
    assert.throws(
      () => validatePopupMessage(message, sender, id, popup),
      { code: 'INVALID_COMMAND' },
    );
  }
});
