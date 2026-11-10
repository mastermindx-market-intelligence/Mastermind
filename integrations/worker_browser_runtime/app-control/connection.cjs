'use strict';

require('./runtime.cjs').assertRuntime();

const { createConnection } = require('@playwright/mcp');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { InMemoryTransport } = require('@modelcontextprotocol/sdk/inMemory.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const { APP_TOOLS, createAppControlAdapter } = require('./adapter.cjs');

// Match the original Workbench grant. Unsafe evaluation, code, installation,
// credential tools never enter this profile's model catalogue.
const NATIVE_TOOLS = new Set(['browser_click', 'browser_close', 'browser_console_messages',
  'browser_fill_form', 'browser_hover', 'browser_navigate', 'browser_network_requests',
  'browser_press_key', 'browser_select_option', 'browser_snapshot', 'browser_tabs',
  'browser_take_screenshot', 'browser_type', 'browser_wait_for']);

/** Compose the native SDK and app handlers in the SAME owner-supplied context. */
async function createAppControlConnection({ getContext, origin, outputDir }) {
  const adapter = createAppControlAdapter({ getContext, origin });
  // With contextGetter, isolated=false means "borrow exactly this context".
  // Actual isolated/persistent browser creation remains with the existing child.
  const native = await createConnection({ browser: { isolated: false }, outputDir }, getContext);
  const upstream = new Client({ name: 'mastermind-owned-browser-adapter', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await native.connect(serverTransport);
  await upstream.connect(clientTransport);
  const discovered = await upstream.listTools();
  const nativeCatalogue = discovered.tools.filter(tool => NATIVE_TOOLS.has(tool.name));
  if (nativeCatalogue.length !== NATIVE_TOOLS.size) {
    await upstream.close();
    throw new Error('PINNED_NATIVE_CATALOGUE_DRIFT');
  }
  const server = new Server({ name: 'mastermind-owned-browser-app-profile', version: '1.0.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [...nativeCatalogue, ...adapter.tools()] }));
  server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
    const { name, arguments: args = {} } = request.params;
    if (APP_TOOLS.has(name)) return adapter.call(name, args, { signal: extra.signal });
    if (!NATIVE_TOOLS.has(name)) return { content: [{ type: 'text', text: '{"code":"TOOL_NOT_GRANTED"}' }], isError: true };
    const response = await upstream.callTool({ name, arguments: args }, undefined, { signal: extra.signal });
    // MCP omits isError on ordinary success; the existing Workbench effect
    // owner deliberately requires explicit false before recording APPLIED.
    return { ...response, isError: response.isError ?? false };
  });
  server.onclose = () => { void upstream.close(); };
  return server;
}
module.exports = { NATIVE_TOOLS, createAppControlConnection };
