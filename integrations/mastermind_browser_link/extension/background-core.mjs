import { ChromePort } from './chrome-port.mjs';
import { SharedTabController } from './controller.mjs';
import { BrowserLinkError, COMMAND_SCHEMA, boundedJSON, httpURL } from './protocol.mjs';
import { validatePopupMessage } from './ui-protocol.mjs';

const NATIVE_HOST = 'com.mastermind.browser_link';
const RECONNECT_ALARM = 'browser-link-reconnect';
const HANDSHAKE_TIMEOUT_MS = 5000;

// Each extension profile owns one connection. Embedders retain their own worker,
// popup, native messaging protocol, and toolbar badge.
export function startBrowserLink({ chrome = globalThis.chrome, popupPath = 'popup.html', showBadge = true,
  nativeHost = NATIVE_HOST, instanceRef: fixedInstanceRef = null } = {}) {
  if (fixedInstanceRef !== null && (typeof fixedInstanceRef !== 'string' || !/^[0-9a-f]{64}$/.test(fixedInstanceRef))) throw new TypeError('Invalid fixed profile identity');
  if (nativeHost !== NATIVE_HOST && (typeof fixedInstanceRef !== 'string' || !/^[0-9a-f]{64}$/.test(fixedInstanceRef) ||
      nativeHost !== `${NATIVE_HOST}.${fixedInstanceRef.slice(0, 24)}`)) throw new TypeError('Invalid profile-bound native host');
  let nativePort = null, controller = null, adapter = null, ready = false;
  let disconnecting = false, connecting = false, closeConnection = null;
  const popupURL = chrome.runtime.getURL(popupPath);
  function send(port, data) {
    boundedJSON(data);
    // Never replay commands or results. The durable owner reconciles effects.
    port.postMessage(data);
  }
  function inventory(requestId = null) {
    if (!ready || !nativePort || !controller) return;
    try {
      send(nativePort, { schema: 'mastermind.browser_link.inventory.v2',
        connection_generation: controller.connectionGeneration, shared_tabs: controller.inventory(),
        ...(requestId === null ? {} : { request_id: requestId }) });
    } catch { closeConnection?.(); }
  }
  function badge() {
    if (showBadge) chrome.action.setBadgeText({ text: !ready ? 'OFF' : controller?.inventory().length ? 'ON' : '' }).catch(() => {});
  }
  async function connect() {
    if (nativePort || disconnecting || connecting) return;
    connecting = true;
    try {
      // Discovery correlation only: never credentials, consent, or authority.
      const key = 'browserLinkInstanceRef';
      let instanceRef = fixedInstanceRef ?? (await chrome.storage.local.get(key))[key];
      if (typeof instanceRef !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(instanceRef)) {
        instanceRef = crypto.randomUUID();
        await chrome.storage.local.set({ [key]: instanceRef });
      }
      const generation = crypto.randomUUID();
      const nextAdapter = new ChromePort({ chrome });
      const nextController = new SharedTabController({ adapter: nextAdapter, connectionGeneration: generation });
      const port = chrome.runtime.connectNative(nativeHost);
      let handshakeTimer = null;
      nativePort = port; controller = nextController; adapter = nextAdapter; ready = false;
      function cleanup() {
        clearTimeout(handshakeTimer); handshakeTimer = null;
        if (nativePort !== port) return;
        const ids = nextController.inventory().map(tab => tab.tab_id);
        nextController.disconnect();
        nativePort = null; controller = null; adapter = null; closeConnection = null;
        ready = false; disconnecting = true; badge();
        Promise.allSettled(ids.map(id => nextAdapter.detach(id))).finally(() => { disconnecting = false; });
      }
      function close() {
        // Locally initiated disconnects need cleanup too: Chrome need not fire
        // this end's onDisconnect event when it calls Port.disconnect().
        cleanup();
        try { port.disconnect(); } catch {}
      }
      closeConnection = close;
      port.onDisconnect.addListener(() => {
        void chrome.runtime.lastError; // consume machine-specific error without logging it
        cleanup();
      });
      port.onMessage.addListener(message => {
        if (nativePort !== port) return;
        try {
          boundedJSON(message);
          if (message?.schema === 'mastermind.browser_link.ready.v2' &&
              Object.keys(message).sort().join(',') === 'connection_generation,schema' &&
              message.connection_generation === generation) {
            clearTimeout(handshakeTimer); handshakeTimer = null;
            ready = true; inventory(); badge(); return;
          }
          if (ready && message?.schema === 'mastermind.browser_link.observe.v2' &&
              Object.keys(message).sort().join(',') === 'connection_generation,request_id,schema' &&
              message.connection_generation === generation && typeof message.request_id === 'string' &&
              /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(message.request_id)) {
            inventory(message.request_id); return;
          }
          if (!ready || message?.schema !== COMMAND_SCHEMA) { close(); return; }
          nextController.execute(message).then(result => {
            if (nativePort === port) { send(port, result); inventory(); badge(); }
          }).catch(() => { if (nativePort === port) close(); });
        } catch { close(); }
      });
      handshakeTimer = setTimeout(() => { if (nativePort === port && !ready) close(); }, HANDSHAKE_TIMEOUT_MS);
      try {
        send(port, { schema: 'mastermind.browser_link.hello.v2', protocol_version: 2,
          extension_id: chrome.runtime.id, instance_ref: instanceRef, connection_generation: generation });
      } catch (error) { close(); throw error; }
      badge();
    } finally { connecting = false; }
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    // A composed Web Sol worker also receives content-script/census messages.
    // Leave those to its existing listener instead of racing to respond.
    if (sender?.id !== chrome.runtime.id || sender?.url !== popupURL) return false;
    (async () => {
      const request = validatePopupMessage(message, sender, chrome.runtime.id, popupURL);
      if (request.kind === 'status') return { connected: ready, shared_tabs: controller?.inventory() ?? [],
        deployment: 'candidate; remote access still requires existing-owner admission' };
      if (!ready || !controller) throw new BrowserLinkError('LINK_NOT_READY');
      if (request.kind === 'share_current') {
        const requestedController = controller, requestedPort = nativePort;
        const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        if (!ready || controller !== requestedController || nativePort !== requestedPort) throw new BrowserLinkError('LINK_NOT_READY');
        if (!tab || !Number.isSafeInteger(tab.id)) throw new BrowserLinkError('TARGET_UNAVAILABLE');
        if (tab.status === 'loading' || (typeof tab.pendingUrl === 'string' && tab.pendingUrl)) throw new BrowserLinkError('TARGET_NAVIGATING');
        controller.share(tab.id, httpURL(tab.url).origin, request.allow_create ?? false); inventory(); badge();
        return { shared: true, tab_id: tab.id };
      }
      const currentAdapter = adapter;
      controller.revoke(request.tab_id); inventory(); badge();
      await currentAdapter.detach(request.tab_id);
      return { revoked: true, tab_id: request.tab_id };
    })().then(respond, error => respond({ error: error instanceof BrowserLinkError ? error.code : 'UI_ACTION_REFUSED' }));
    return true;
  });

  chrome.tabs.onRemoved.addListener(tabId => { controller?.revoke(tabId); adapter?.detached(tabId); inventory(); badge(); });
  chrome.tabs.onReplaced?.addListener((_addedTabId, removedTabId) => {
    controller?.revoke(removedTabId); adapter?.detached(removedTabId); inventory(); badge();
  });
  chrome.tabs.onUpdated.addListener((tabId, change) => {
    if (!controller) return;
    const shared = controller.inventory().find(tab => tab.tab_id === tabId);
    if (!shared) return;
    if (change.url) {
      try {
        if (httpURL(change.url).origin !== shared.origin) { controller.revoke(tabId); void adapter.detach(tabId); }
        else controller.invalidate(tabId);
      } catch { controller.revoke(tabId); void adapter.detach(tabId); }
    }
    if (change.status === 'loading' || change.status === 'complete') {
      controller.navigation(tabId, change.status === 'loading');
    }
    inventory(); badge();
  });
  chrome.debugger.onDetach.addListener(source => {
    if (!Number.isSafeInteger(source.tabId)) return;
    adapter?.detached(source.tabId); controller?.revoke(source.tabId); inventory(); badge();
  });
  chrome.debugger.onEvent.addListener((source, method, params) => {
    if (!Number.isSafeInteger(source.tabId)) return;
    if (!controller?.inventory().some(tab => tab.tab_id === source.tabId)) return;
    if (method === 'Page.frameNavigated' && params.frame?.parentId) return;
    if (['Page.frameNavigated', 'Page.navigatedWithinDocument', 'DOM.documentUpdated'].includes(method)) {
      controller?.invalidate(source.tabId); inventory();
    }
    // Element identity is checked again at the actuator. Ordinary live DOM
    // changes do not turn every tab reference into a different document.
  });
  async function ensureReconnectAlarm() {
    const alarm = await chrome.alarms.get(RECONNECT_ALARM);
    if (!alarm || alarm.periodInMinutes !== 1) await chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 1 });
  }
  function startup() {
    ensureReconnectAlarm().catch(() => {});
    connect().catch(() => { ready = false; badge(); });
  }
  chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === RECONNECT_ALARM) connect().catch(() => {}); });
  chrome.runtime.onInstalled.addListener(startup);
  chrome.runtime.onStartup.addListener(startup);
  startup();
}
