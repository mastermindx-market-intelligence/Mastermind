import test from 'node:test';
import assert from 'node:assert/strict';

import {
  FLEET_BACKEND_TOOL_NAMES,
  createFleetRouter,
  resolveFleetRoutingConfig,
} from './fleet-routing.mjs';

const READ_SCHEMA = {
  type: 'object',
  properties: { path: { type: 'string' } },
  required: ['path'],
  additionalProperties: false,
};

function config(overrides = {}) {
  return {
    enabled: true,
    requestTimeoutMs: 5000,
    routes: [
      { hostRef: 'mini4', url: 'https://mini4.example-tailnet.ts.net/mcp' },
      { hostRef: 'ubuntu1', url: 'https://ubuntu1.example-tailnet.ts.net/mcp' },
    ],
    ...overrides,
  };
}

function harness({ remoteSchema = READ_SCHEMA, callImpl = null } = {}) {
  const created = [];
  const factory = async (route) => {
    const state = {
      route,
      connects: 0,
      lists: 0,
      calls: 0,
      clientCloses: 0,
      transportCloses: 0,
    };
    const transport = {
      async close() { state.transportCloses += 1; },
    };
    const client = {
      async connect(value) {
        assert.equal(value, transport);
        state.connects += 1;
      },
      async listTools() {
        state.lists += 1;
        return {
          tools: [
            { name: 'read_file', inputSchema: remoteSchema },
            { name: 'studio_ping', inputSchema: { type: 'object' } },
          ],
        };
      },
      async callTool(request) {
        state.calls += 1;
        if (callImpl) return callImpl(request, state);
        return { content: [{ type: 'text', text: route.hostRef }], structuredContent: { hostRef: route.hostRef } };
      },
      async close() { state.clientCloses += 1; },
    };
    state.client = client;
    state.transport = transport;
    created.push(state);
    return { client, transport };
  };
  return { created, factory };
}

test('routing config is exact tailnet-only and bounded', () => {
  const resolved = resolveFleetRoutingConfig(config());
  assert.deepEqual(resolved.routes.map((route) => route.hostRef), ['mini4', 'ubuntu1']);
  assert.equal(resolved.routes[0].url, 'https://mini4.example-tailnet.ts.net/mcp');

  for (const url of [
    'http://mini4.example-tailnet.ts.net/mcp',
    'https://mini4.example-tailnet.ts.net/',
    'https://mini4.example-tailnet.ts.net/other',
    'https://example.com/mcp',
    'https://user:pass@mini4.example-tailnet.ts.net/mcp',
    'https://mini4.example-tailnet.ts.net/mcp?x=1',
    'https://mini4.example-tailnet.ts.net:8443/mcp',
  ]) {
    assert.throws(
      () => resolveFleetRoutingConfig(config({ routes: [{ hostRef: 'mini4', url }] })),
      /exact https tailnet MCP URL/,
      url,
    );
  }

  assert.throws(
    () => resolveFleetRoutingConfig(config({
      routes: [
        { hostRef: 'mini4', url: 'https://mini4.example-tailnet.ts.net/mcp' },
        { hostRef: 'mini4', url: 'https://ubuntu1.example-tailnet.ts.net/mcp' },
      ],
    })),
    /unique hostRef/,
  );
  assert.throws(
    () => resolveFleetRoutingConfig(config({ requestTimeoutMs: 0 })),
    /requestTimeoutMs/,
  );
});

test('preflight binds one configured host only after exact tool schema match', async () => {
  const h = harness();
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  const expected = new Map([['read_file', READ_SCHEMA]]);

  const first = await router.preflight('mini4', expected);
  assert.equal(first.state, 'READY');
  assert.equal(first.hostRef, 'mini4');
  assert.deepEqual(first.toolNames, ['read_file']);
  const second = await router.preflight('mini4', expected);
  assert.equal(second, first);
  assert.equal(h.created.length, 1);
  assert.equal(h.created[0].connects, 1);
  assert.equal(h.created[0].lists, 1);

  await assert.rejects(
    router.preflight('not-configured', expected),
    /HOST_NOT_CONFIGURED/,
  );
  await router.close();
  assert.equal(h.created[0].clientCloses, 1);
});

test('contract mismatch refuses before any routed tool call', async () => {
  const h = harness({
    remoteSchema: {
      type: 'object',
      properties: { path: { type: 'number' } },
      required: ['path'],
      additionalProperties: false,
    },
  });
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  await assert.rejects(
    router.preflight('mini4', new Map([['read_file', READ_SCHEMA]])),
    /PREFLIGHT_REFUSED/,
  );
  assert.equal(h.created.length, 1);
  assert.equal(h.created[0].calls, 0);
  assert.equal(h.created[0].clientCloses, 1);
  await assert.rejects(
    router.call('mini4', { name: 'read_file', arguments: { path: '/tmp/x' } }),
    /NOT_BOUND/,
  );
});

test('one routed call means one remote tools/call and unknown tools are refused locally', async () => {
  const h = harness();
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  await router.preflight('mini4', new Map([['read_file', READ_SCHEMA]]));

  const result = await router.call('mini4', {
    name: 'read_file',
    arguments: { path: '/tmp/example' },
  });
  assert.equal(result.structuredContent.hostRef, 'mini4');
  assert.equal(h.created[0].calls, 1);

  await assert.rejects(
    router.call('mini4', { name: 'not_a_tool', arguments: {} }),
    /TOOL_NOT_ALLOWED/,
  );
  assert.equal(h.created[0].calls, 1, 'refused call must not dispatch remotely');
  assert.ok(FLEET_BACKEND_TOOL_NAMES.includes('start_process'));
});
