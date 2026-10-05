import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { ErrorCode } from '@modelcontextprotocol/sdk/types.js';

const HOST_REF = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const MAX_ROUTES = 32;
const MIN_TIMEOUT_MS = 1000;
const MAX_TIMEOUT_MS = 300000;

export const FLEET_BACKEND_TOOL_NAMES = Object.freeze([
  'get_config',
  'set_config_value',
  'read_file',
  'read_multiple_files',
  'write_file',
  'write_pdf',
  'create_directory',
  'list_directory',
  'move_file',
  'start_search',
  'get_more_search_results',
  'stop_search',
  'list_searches',
  'get_file_info',
  'edit_block',
  'start_process',
  'read_process_output',
  'interact_with_process',
  'force_terminate',
  'list_sessions',
  'list_processes',
  'kill_process',
  'get_usage_stats',
  'get_recent_tool_calls',
  'give_feedback_to_desktop_commander',
  'get_prompts',
]);

const FLEET_BACKEND_TOOL_SET = new Set(FLEET_BACKEND_TOOL_NAMES);

export const STUDIO_SELECT_HOST_TOOL = Object.freeze({
  name: 'studio_select_host',
  title: 'Select Studio Fleet Host',
  description:
    'Bind this MCP session once to one operator-configured fleet host before using Desktop Commander tools. ' +
    'The selection is preflighted against the remote Studio tool contract. It does not start work, move an ' +
    'existing process, retry an effect, or change Fleet/Capacity placement. A session cannot switch hosts after ' +
    'selection or after a Desktop Commander tool has been dispatched.',
  inputSchema: {
    type: 'object',
    properties: {
      hostRef: {
        type: 'string',
        minLength: 1,
        maxLength: 64,
        pattern: '^[a-z0-9][a-z0-9._-]{0,63}$',
      },
    },
    required: ['hostRef'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Select Studio Fleet Host',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true },
});

function stable(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
  const keys = Object.keys(value).sort();
  return '{' + keys.map((key) => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}';
}

function parseRouteUrl(raw) {
  if (typeof raw !== 'string' || raw.length < 1 || raw.length > 2048) {
    throw new TypeError('fleet route url must be an exact https tailnet MCP URL');
  }
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new TypeError('fleet route url must be an exact https tailnet MCP URL');
  }
  const authority = raw.match(/^https:\/\/([^/?#]+)/)?.[1] ?? '';
  if (
    url.protocol !== 'https:' ||
    !url.hostname.endsWith('.ts.net') ||
    url.hostname.length <= '.ts.net'.length ||
    authority.includes(':') ||
    url.pathname !== '/mcp' ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new TypeError('fleet route url must be an exact https tailnet MCP URL');
  }
  return url.toString();
}

export function resolveFleetRoutingConfig(raw) {
  if (raw == null || raw === false || raw?.enabled === false) return null;
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    throw new TypeError('config.fleetRouting must be an object when enabled');
  }
  const allowed = new Set(['enabled', 'routes', 'requestTimeoutMs']);
  for (const key of Object.keys(raw)) {
    if (!allowed.has(key)) throw new TypeError(`config.fleetRouting contains unknown key: ${key}`);
  }
  if (raw.enabled !== true) throw new TypeError('config.fleetRouting.enabled must be true');
  if (!Array.isArray(raw.routes) || raw.routes.length < 1 || raw.routes.length > MAX_ROUTES) {
    throw new TypeError(`config.fleetRouting.routes must contain 1..${MAX_ROUTES} routes`);
  }
  const routes = [];
  const hostRefs = new Set();
  const urls = new Set();
  for (const item of raw.routes) {
    if (!item || typeof item !== 'object' || Array.isArray(item) ||
        Object.keys(item).some((key) => !['hostRef', 'url'].includes(key))) {
      throw new TypeError('fleet route must contain only hostRef and url');
    }
    if (typeof item.hostRef !== 'string' || !HOST_REF.test(item.hostRef)) {
      throw new TypeError('fleet route hostRef is invalid');
    }
    const url = parseRouteUrl(item.url);
    if (hostRefs.has(item.hostRef) || urls.has(url)) {
      throw new TypeError('fleet routes must have unique hostRef and url values');
    }
    hostRefs.add(item.hostRef);
    urls.add(url);
    routes.push(Object.freeze({ hostRef: item.hostRef, url }));
  }
  const timeout = Number(raw.requestTimeoutMs);
  if (!Number.isInteger(timeout) || timeout < MIN_TIMEOUT_MS || timeout > MAX_TIMEOUT_MS) {
    throw new TypeError(
      `config.fleetRouting.requestTimeoutMs must be an integer from ${MIN_TIMEOUT_MS} to ${MAX_TIMEOUT_MS}`,
    );
  }
  return Object.freeze({
    enabled: true,
    requestTimeoutMs: timeout,
    routes: Object.freeze(routes.sort((a, b) => a.hostRef.localeCompare(b.hostRef))),
  });
}

function contractMap(tools) {
  if (!Array.isArray(tools)) throw new Error('FLEET_ROUTE_CATALOG_INVALID');
  const result = new Map();
  for (const tool of tools) {
    if (!tool || typeof tool !== 'object' || typeof tool.name !== 'string') continue;
    if (!FLEET_BACKEND_TOOL_SET.has(tool.name)) continue;
    if (result.has(tool.name)) throw new Error('FLEET_ROUTE_CATALOG_INVALID');
    result.set(tool.name, stable(tool.inputSchema ?? null));
  }
  return result;
}

function expectedContractMap(tools) {
  const source = tools instanceof Map ? [...tools.entries()] : [];
  const result = new Map();
  for (const [name, schema] of source) {
    if (!FLEET_BACKEND_TOOL_SET.has(name)) continue;
    result.set(name, typeof schema === 'string' ? schema : stable(schema ?? null));
  }
  return result;
}

function validateContract(remoteTools, expectedTools) {
  const remote = contractMap(remoteTools);
  const expected = expectedContractMap(expectedTools);
  if (expected.size === 0) throw new Error('FLEET_ROUTE_LOCAL_CONTRACT_UNAVAILABLE');
  for (const [name, schema] of expected) {
    if (remote.get(name) !== schema) throw new Error('FLEET_ROUTE_CONTRACT_MISMATCH');
  }
  return Object.freeze([...remote.keys()].sort());
}

function defaultClientFactory(route) {
  const client = new Client({ name: 'mastermind-studio-fleet-router', version: '1' });
  const transport = new StreamableHTTPClientTransport(new URL(route.url));
  return { client, transport };
}

export function createFleetRouter(rawConfig, deps = {}) {
  const cfg = resolveFleetRoutingConfig(rawConfig);
  if (!cfg) return null;
  const makeClient = deps.clientFactory ?? defaultClientFactory;
  if (typeof makeClient !== 'function') throw new TypeError('fleet router clientFactory is invalid');
  const routeByRef = new Map(cfg.routes.map((route) => [route.hostRef, route]));
  const live = new Map();
  let closed = false;

  async function drop(hostRef) {
    const state = live.get(hostRef);
    live.delete(hostRef);
    if (!state) return;
    try { await state.client?.close?.(); } catch { /* bounded cleanup */ }
    try { await state.transport?.close?.(); } catch { /* bounded cleanup */ }
  }

  async function preflight(hostRef, expectedTools, { signal } = {}) {
    if (closed) throw new Error('FLEET_ROUTE_CLOSED');
    if (typeof hostRef !== 'string' || !HOST_REF.test(hostRef)) {
      throw new Error('FLEET_ROUTE_HOST_REF_INVALID');
    }
    const route = routeByRef.get(hostRef);
    if (!route) throw new Error('FLEET_ROUTE_HOST_NOT_CONFIGURED');
    const existing = live.get(hostRef);
    if (existing?.ready === true) return existing.receipt;
    if (existing?.connectPromise) return existing.connectPromise;

    const state = existing ?? { route, ready: false, client: null, transport: null, receipt: null };
    live.set(hostRef, state);
    state.connectPromise = (async () => {
      let created;
      try {
        created = await makeClient(route);
        if (!created?.client || !created?.transport) throw new Error('FLEET_ROUTE_CLIENT_INVALID');
        state.client = created.client;
        state.transport = created.transport;
        await state.client.connect(state.transport);
        const listed = await state.client.listTools(
          {},
          { timeout: cfg.requestTimeoutMs, signal },
        );
        const toolNames = validateContract(listed?.tools, expectedTools);
        state.receipt = Object.freeze({
          schema: 'mastermind.studio_fleet_route_binding.v1',
          hostRef,
          url: route.url,
          toolCount: toolNames.length,
          toolNames,
          state: 'READY',
        });
        state.ready = true;
        return state.receipt;
      } catch (error) {
        await drop(hostRef);
        const wrapped = new Error('FLEET_ROUTE_PREFLIGHT_REFUSED');
        wrapped.cause = error;
        throw wrapped;
      } finally {
        if (live.get(hostRef) === state) state.connectPromise = null;
      }
    })();
    return state.connectPromise;
  }

  async function call(hostRef, request, options = {}) {
    if (closed) throw new Error('FLEET_ROUTE_CLOSED');
    const state = live.get(hostRef);
    if (!state?.ready || !state.client) throw new Error('FLEET_ROUTE_NOT_BOUND');
    const name = request?.name;
    if (!FLEET_BACKEND_TOOL_SET.has(name) && name !== 'studio_output_page') {
      throw new Error('FLEET_ROUTE_TOOL_NOT_ALLOWED');
    }
    // Exactly one remote tools/call. No retry/replay exists in this adapter.
    try {
      return await state.client.callTool(
        request,
        undefined,
        { timeout: cfg.requestTimeoutMs, signal: options.signal },
      );
    } catch (error) {
      const deterministic = [
        ErrorCode.InvalidParams,
        ErrorCode.MethodNotFound,
        ErrorCode.InvalidRequest,
      ].includes(error?.code);
      if (!deterministic) {
        // The route session may now be tainted or disconnected. Retire it rather
        // than silently reusing it; a later frontend session must explicitly
        // preflight a fresh remote MCP session on the same configured host.
        await drop(hostRef);
      }
      throw error;
    }
  }

  return Object.freeze({
    routes: cfg.routes,
    has(hostRef) { return routeByRef.has(hostRef); },
    preflight,
    call,
    async close() {
      if (closed) return;
      closed = true;
      for (const hostRef of [...live.keys()]) await drop(hostRef);
    },
  });
}

export function fleetRouteToolResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
    ...(isError ? { isError: true } : {}),
  };
}
