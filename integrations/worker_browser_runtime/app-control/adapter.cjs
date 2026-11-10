'use strict';

// Fixed adapter over a context already owned by Workbench. No listener, browser
// acquisition, credentials, retries, registry, or caller-supplied JavaScript.
const catalogue = require('../../../app/mastermind_os/src/agent-control/tools.json');
const SCHEMA = 'mastermind.os.app-control.v1';
const READ_TOOLS = new Set(['mastermind_os_inspect', 'mastermind_os_check']);
const APP_TOOLS = new Set(catalogue.map(tool => tool.name));
const MAX_BYTES = 96 * 1024;

function validateOrigin(value) {
  if (typeof value !== 'string') throw new Error('APP_ORIGIN_INVALID');
  const url = new URL(value);
  if (url.origin !== value || url.username || url.password ||
      !(url.protocol === 'https:' || url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
    throw new Error('APP_ORIGIN_INVALID');
  }
  return value;
}
function appUrl(value, origin) {
  try { const url = new URL(value); return url.origin === origin && (url.pathname === '/os' || url.pathname.startsWith('/os/')); }
  catch { return false; }
}
function result(value) {
  const encoded = JSON.stringify(value);
  if (Buffer.byteLength(encoded) > MAX_BYTES) throw new Error('OUTPUT_UNAVAILABLE');
  return { content: [{ type: 'text', text: encoded }], structuredContent: value,
    isError: ['REFUSED', 'EFFECT_UNKNOWN', 'FAIL'].includes(value.status) };
}
function refusal(code) { return result({ schema: SCHEMA, status: 'REFUSED', code }); }

function createAppControlAdapter({ getContext, origin }) {
  validateOrigin(origin);
  if (typeof getContext !== 'function') throw new Error('OWNED_CONTEXT_REQUIRED');
  return Object.freeze({
    // WebMCP has extra annotation names. Project only standard MCP annotations
    // so raw JSON-RPC and SDK-normalized catalogue digests agree.
    tools: () => catalogue.map(tool => ({ ...structuredClone(tool), annotations: { readOnlyHint: tool.annotations.readOnlyHint } })),
    async call(name, args = {}, { signal } = {}) {
      if (!APP_TOOLS.has(name)) return refusal('TOOL_UNAVAILABLE');
      if (signal?.aborted) return refusal('CANCELLED_BEFORE_DISPATCH');
      if (!args || typeof args !== 'object' || Array.isArray(args)) return refusal('INVALID_ARGUMENT');
      try { if (Buffer.byteLength(JSON.stringify(args)) > 32 * 1024) return refusal('INVALID_ARGUMENT'); }
      catch { return refusal('INVALID_ARGUMENT'); }
      let page;
      try {
        const context = await getContext();
        const pages = context.pages().filter(candidate => !candidate.isClosed() && appUrl(candidate.url(), origin));
        if (pages.length !== 1) return refusal(pages.length ? 'APP_PAGE_AMBIGUOUS' : 'APP_PAGE_UNAVAILABLE');
        page = pages[0];
      } catch { return refusal('BROWSER_RESOURCE_UNAVAILABLE'); }
      if (signal?.aborted) return refusal('CANCELLED_BEFORE_DISPATCH');
      try {
        // This literal function is the only evaluation primitive. All arguments
        // are data. The page repeats origin/path/version checks at dispatch time.
        const value = await page.evaluate(async ({ expectedOrigin, schema, tool, input }) => {
          const refused = code => ({ schema, status: 'REFUSED', code });
          if (location.origin !== expectedOrigin || !(location.pathname === '/os' || location.pathname.startsWith('/os/'))) return refused('APP_ORIGIN_CHANGED');
          const api = window.MastermindAppControl;
          if (!api || api.schema !== schema || typeof api.call !== 'function') return refused('APP_CONTROL_UNAVAILABLE');
          return await api.call(tool, input);
        }, { expectedOrigin: origin, schema: SCHEMA, tool: name, input: args });
        if (!appUrl(page.url(), origin) || !value || value.schema !== SCHEMA) throw new Error('APP_RESULT_UNAVAILABLE');
        return result(value);
      } catch {
        // The request may already have reached React or a remote owner. The
        // existing Workbench action_ref remains the only reconciliation carrier.
        return result({ schema: SCHEMA, status: READ_TOOLS.has(name) ? 'REFUSED' : 'EFFECT_UNKNOWN',
          code: READ_TOOLS.has(name) ? 'APP_READ_UNAVAILABLE' : 'INSPECT_ORIGINAL_OWNER_BEFORE_ANY_RETRY' });
      }
    },
  });
}
module.exports = { APP_TOOLS, READ_TOOLS, SCHEMA, createAppControlAdapter, validateOrigin };
