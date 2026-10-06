import test from 'node:test';
import assert from 'node:assert/strict';
import { validateCommand, BrowserLinkError, MAX_FRAME_BYTES } from '../../integrations/mastermind_browser_link/extension/protocol.mjs';
const now = 1_000_000;
const valid = () => ({ schema: 'mastermind.browser_link.command.v1', request_id: 'request-1', connection_generation: 'connection-1', tab_id: 0, consent_id: 'consent-1', document_revision: 0, expires_at_ms: now + 1000, command: 'snapshot', args: {} });
const bad = (value, code = 'INVALID_COMMAND') => assert.throws(() => validateCommand(value, now), e => e instanceof BrowserLinkError && e.code === code);

test('exact valid read is normalized and frozen', () => { const x = validateCommand(valid(), now); assert.equal(x.command, 'snapshot'); assert.equal(Object.isFrozen(x.args), true); });
test('extra caller-controlled identity, method and endpoint fields are denied', () => { for (const key of ['actor', 'cdp_method', 'socket', '__proto__']) bad({ ...valid(), [key]: 'attacker' }); });
test('missing required fields are denied', () => { for (const field of Object.keys(valid())) { const x = valid(); delete x[field]; bad(x); } });
test('non-object, arrays and cyclic payloads are bounded refusals', () => { for (const x of [null, [], 2, 'text']) bad(x); const x = valid(); x.args.x = x; bad(x); });
test('non-finite and boolean numeric identities are refused', () => { for (const value of [true, -1, NaN, Infinity, 1.1, Number.MAX_SAFE_INTEGER + 1]) bad({ ...valid(), tab_id: value }); });
test('unknown actions and raw evaluate are not representable', () => { for (const command of ['evaluate', 'get_cookies', 'Browser.getVersion', 'shell']) bad({ ...valid(), command }); });
test('read tools cannot carry a writer grant', () => bad({ ...valid(), writer: { holder_ref: 'a', fence: 1 } }));
test('mutations require an exact writer envelope', () => { const x = { ...valid(), command: 'click', args: { element_ref: 'e-1' } }; bad(x); bad({ ...x, writer: { holder_ref: 'a', fence: 1, admin: true } }); });
test('expired and overlong lifetimes are refused', () => { bad({ ...valid(), expires_at_ms: now }, 'EXPIRED'); bad({ ...valid(), expires_at_ms: now + 30001 }, 'INVALID_COMMAND'); });
test('output-independent input frame cap is enforced before parsing action', () => { assert.equal(MAX_FRAME_BYTES, 65536); bad({ ...valid(), args: { text: 'x'.repeat(70000) } }, 'FRAME_TOO_LARGE'); });
test('navigate cannot target privileged protocols or URL credentials', () => { for (const url of ['file:///etc/passwd','chrome://settings','javascript:alert(1)','https://u:p@example.test/','data:text/html,x']) bad({ ...valid(), command: 'navigate', args: { url }, writer: { holder_ref: 'a', fence: 1 } }); });
test('scroll magnitudes and text lengths are bounded', () => { bad({ ...valid(), command: 'scroll', args: { delta_x: 0, delta_y: 2001 }, writer: { holder_ref: 'a', fence: 1 } }); bad({ ...valid(), command: 'type', args: { element_ref: 'e', text: 'a'.repeat(16385) }, writer: { holder_ref: 'a', fence: 1 } }); });
