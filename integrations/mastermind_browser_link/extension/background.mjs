import { ChromePort } from './chrome-port.mjs';
import { SharedTabController } from './controller.mjs';
import { BrowserLinkError, COMMAND_SCHEMA, boundedJSON, httpURL } from './protocol.mjs';
import { validatePopupMessage } from './ui-protocol.mjs';

const NATIVE_HOST = 'com.mastermind.browser_link';
let nativePort = null, controller = null, adapter = null, ready = false, disconnecting = false, connecting = false;
const popupURL = chrome.runtime.getURL('popup.html');
function send(port, data) {
  boundedJSON(data);
  // Never retry a command/result if this port has gone away. The owner must
  // reconcile the original operation rather than infer absence of an effect.
  port.postMessage(data);
}
function inventory() {
  if (ready && nativePort && controller) send(nativePort, { schema: 'mastermind.browser_link.inventory.v1',
    connection_generation: controller.connectionGeneration, shared_tabs: controller.inventory() });
}
function badge() { chrome.action.setBadgeText({ text: !ready ? 'OFF' : controller?.inventory().length ? 'ON' : '' }).catch(() => {}); }
async function connect() {
  if (nativePort || disconnecting || connecting) return;
  connecting = true;
  try {
  // Discovery correlation only. This value never restores consent or authority.
  const key = 'browserLinkInstanceRef';
  let instanceRef = (await chrome.storage.local.get(key))[key];
  if (typeof instanceRef !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(instanceRef)) {
    instanceRef = crypto.randomUUID();
    await chrome.storage.local.set({ [key]: instanceRef });
  }
  const generation = crypto.randomUUID();
  const nextAdapter = new ChromePort({ chrome });
  const nextController = new SharedTabController({ adapter: nextAdapter, connectionGeneration: generation });
  const port = chrome.runtime.connectNative(NATIVE_HOST);
  nativePort = port; controller = nextController; adapter = nextAdapter; ready = false;
  port.onDisconnect.addListener(() => {
    // Reading lastError consumes Chrome's connection error without leaking its
    // possibly machine-specific text into MCP output or persistent logs.
    void chrome.runtime.lastError;
    if (nativePort !== port) return;
    const ids = nextController.inventory().map(tab => tab.tab_id);
    nextController.disconnect(); nativePort = null; ready = false; disconnecting = true; badge();
    Promise.allSettled(ids.map(id => nextAdapter.detach(id))).finally(() => { disconnecting = false; });
  });
  port.onMessage.addListener(message => {
    if (nativePort !== port) return;
    try {
      boundedJSON(message);
      if (message?.schema === 'mastermind.browser_link.ready.v1' && Object.keys(message).sort().join(',') === 'connection_generation,schema' && message.connection_generation === generation) {
        ready = true; inventory(); badge(); return;
      }
      if (!ready || message?.schema !== COMMAND_SCHEMA) { port.disconnect(); return; }
      nextController.execute(message).then(result => {
        if (nativePort === port) { send(port, result); inventory(); badge(); }
      }).catch(() => { if (nativePort === port) port.disconnect(); });
    } catch { port.disconnect(); }
  });
  send(port, { schema: 'mastermind.browser_link.hello.v1', protocol_version: 1,
    extension_id: chrome.runtime.id, instance_ref: instanceRef, connection_generation: generation });
  badge();
  } finally { connecting = false; }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  (async () => {
    const request = validatePopupMessage(message, sender, chrome.runtime.id, popupURL);
    if (request.kind === 'status') return { connected: ready, shared_tabs: controller?.inventory() ?? [],
      deployment: 'candidate; remote access still requires existing-owner admission' };
    if (!ready || !controller) throw new BrowserLinkError('LINK_NOT_READY');
    if (request.kind === 'share_current') {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tab || !Number.isSafeInteger(tab.id)) throw new BrowserLinkError('TARGET_UNAVAILABLE');
      controller.share(tab.id, httpURL(tab.url).origin); inventory(); badge();
      return { shared: true, tab_id: tab.id };
    }
    controller.revoke(request.tab_id); inventory(); badge();
    await adapter.detach(request.tab_id);
    return { revoked: true, tab_id: request.tab_id };
  })().then(respond, error => respond({ error: error instanceof BrowserLinkError ? error.code : 'UI_ACTION_REFUSED' }));
  return true;
});

chrome.tabs.onRemoved.addListener(tabId => { controller?.revoke(tabId); adapter?.detached(tabId); inventory(); badge(); });
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (!change.url || !controller) return;
  const shared = controller.inventory().find(tab => tab.tab_id === tabId);
  if (!shared) return;
  try { if (httpURL(change.url).origin !== shared.origin) { controller.revoke(tabId); adapter.detach(tabId); } else controller.invalidate(tabId); }
  catch { controller.revoke(tabId); adapter.detach(tabId); }
  inventory(); badge();
});
chrome.debugger.onDetach.addListener(source => {
  if (!Number.isSafeInteger(source.tabId)) return;
  adapter?.detached(source.tabId); controller?.revoke(source.tabId); inventory(); badge();
});
chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!Number.isSafeInteger(source.tabId)) return;
  if (method === 'Page.frameNavigated' && params.frame?.parentId) return;
  if (['Page.frameNavigated', 'Page.navigatedWithinDocument', 'DOM.documentUpdated', 'DOM.childNodeRemoved', 'DOM.attributeModified', 'DOM.characterDataModified'].includes(method)) {
    controller?.invalidate(source.tabId);
  }
});
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'browser-link-reconnect') connect().catch(() => {}); });
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('browser-link-reconnect', { periodInMinutes: 1 }); });
chrome.runtime.onStartup.addListener(() => connect().catch(() => {}));
connect().catch(() => { ready = false; badge(); });
