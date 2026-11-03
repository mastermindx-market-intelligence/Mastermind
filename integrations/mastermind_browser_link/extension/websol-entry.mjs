import { startBrowserLink } from './background-core.mjs';

// Reuse the installed immutable profile identity; storage UUIDs do not bind
// same-extension-ID profiles to the correct native host.
const instanceId = globalThis.MMX_WEB_SOL_INSTANCE?.instanceId;
if (typeof instanceId === 'string' && /^[0-9a-f]{64}$/.test(instanceId)) {
  startBrowserLink({ popupPath: 'browser-link/popup.html', showBadge: false,
    instanceRef: instanceId, nativeHost: `com.mastermind.browser_link.${instanceId.slice(0, 24)}` });
}
