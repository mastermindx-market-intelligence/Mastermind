const byId = id => document.getElementById(id);
const share = byId('share-current');
const list = byId('shared-tabs');
const notice = byId('notice');
let pending = false;
let refreshSequence = 0;
let connected = false;

const messages = {
  LINK_NOT_READY: 'The browser is not connected yet.',
  TARGET_UNAVAILABLE: 'Open a website tab, then try sharing it.',
  INVALID_COMMAND: 'Only http and https website tabs can be shared.',
  SHARE_LIMIT: 'Stop sharing a tab before adding another.',
};
const states = { shared: 'Shared', busy: 'Agent working', effect_unresolved: 'Needs review' };

async function request(message) {
  let timer;
  try {
    return await Promise.race([
      chrome.runtime.sendMessage(message),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('STATUS_UNAVAILABLE')), 3000); }),
    ]);
  } finally { clearTimeout(timer); }
}
function setPending(value) {
  pending = value;
  share.disabled = pending || !connected;
  for (const button of list.querySelectorAll('button')) button.disabled = pending;
}
function showStatus(value) {
  if (typeof value?.connected !== 'boolean' || !Array.isArray(value.shared_tabs)) throw new Error('STATUS_UNAVAILABLE');
  connected = value.connected;
  byId('connection-dot').classList.toggle('connected', connected);
  byId('connection-label').textContent = connected ? 'Connected to Mastermind' : 'Not connected';
  byId('connection-detail').textContent = connected
    ? 'Choose tabs to make available to your agents.'
    : 'The host connector must be running on this device. No tabs are shared.';
  list.replaceChildren();
  for (const tab of value.shared_tabs) {
    if (!Number.isSafeInteger(tab.tab_id) || typeof tab.origin !== 'string' || !Object.hasOwn(states, tab.state)) continue;
    const row = document.createElement('li');
    const info = document.createElement('div');
    info.className = 'tab-info';
    const origin = document.createElement('div');
    origin.className = 'tab-origin';
    origin.textContent = tab.origin;
    const state = document.createElement('div');
    state.className = 'tab-state';
    state.textContent = states[tab.state];
    info.append(origin, state);
    const stop = document.createElement('button');
    stop.type = 'button';
    stop.className = 'stop';
    stop.textContent = 'Stop sharing';
    stop.setAttribute('aria-label', 'Stop sharing ' + tab.origin);
    stop.addEventListener('click', () => change({ kind: 'revoke', tab_id: tab.tab_id }));
    row.append(info, stop);
    list.append(row);
  }
  byId('shared-count').textContent = String(list.children.length);
  byId('empty-state').hidden = list.children.length !== 0;
  setPending(pending);
}
async function refresh() {
  const sequence = ++refreshSequence;
  try {
    const value = await request({ kind: 'status' });
    if (sequence !== refreshSequence) return;
    if (value?.error) throw new Error(value.error);
    showStatus(value);
  } catch {
    if (sequence !== refreshSequence) return;
    connected = false;
    setPending(pending);
    byId('connection-dot').classList.remove('connected');
    byId('connection-label').textContent = 'Status unavailable';
    byId('connection-detail').textContent = 'Reopen this popup to check the connection and shared tabs.';
  }
}
async function change(message) {
  if (pending) return;
  setPending(true);
  notice.textContent = '';
  try {
    const result = await request(message);
    if (result?.error) throw new Error(result.error);
    if (message.kind === 'share_current' ? result?.shared !== true : result?.revoked !== true) throw new Error('STATUS_UNAVAILABLE');
  } catch (error) {
    notice.textContent = messages[error.message] ?? 'Could not confirm the change. Check the sharing list before trying again.';
  } finally {
    await refresh();
    setPending(false);
  }
}
share.addEventListener('click', () => change({ kind: 'share_current' }));
await refresh();
const polling = setInterval(() => { if (!pending) void refresh(); }, 1500);
addEventListener('pagehide', () => clearInterval(polling), { once: true });
