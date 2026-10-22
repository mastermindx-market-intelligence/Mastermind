import test from 'node:test';
import assert from 'node:assert/strict';
import { ErrorCode } from '@modelcontextprotocol/sdk/types.js';

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

function harness({ remoteSchema = READ_SCHEMA, callImpl = null, extraTools = [] } = {}) {
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
            ...extraTools,
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
  assert.equal(resolved.enabled, true);
  assert.deepEqual(resolveFleetRoutingConfig(resolved), resolved);

  for (const url of [
    'http://mini4.example-tailnet.ts.net/mcp',
    'https://mini4.example-tailnet.ts.net/',
    'https://mini4.example-tailnet.ts.net/other',
    'https://example.com/mcp',
    'https://user:pass@mini4.example-tailnet.ts.net/mcp',
    'https://mini4.example-tailnet.ts.net/mcp?x=1',
    'https://mini4.example-tailnet.ts.net:443/mcp',
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


test('deterministic remote refusal keeps the route but ambiguous failure retires it', async () => {
  let mode = 'deterministic';
  const h = harness({
    callImpl() {
      const error = new Error(mode);
      if (mode === 'deterministic') error.code = ErrorCode.InvalidParams;
      throw error;
    },
  });
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  const expected = new Map([['read_file', READ_SCHEMA]]);
  await router.preflight('mini4', expected);

  await assert.rejects(
    router.call('mini4', { name: 'read_file', arguments: { path: '/tmp/x' } }),
    /deterministic/,
  );
  assert.equal(h.created[0].clientCloses, 0);
  assert.equal(h.created[0].transportCloses, 0);

  mode = 'ambiguous';
  await assert.rejects(
    router.call('mini4', { name: 'read_file', arguments: { path: '/tmp/y' } }),
    /ambiguous/,
  );
  assert.equal(h.created[0].clientCloses, 1);
  assert.equal(h.created[0].transportCloses, 1);

  await assert.rejects(
    router.call('mini4', { name: 'read_file', arguments: { path: '/tmp/z' } }),
    /NOT_BOUND/,
  );

  const rebound = await router.preflight('mini4', expected);
  assert.equal(rebound.state, 'READY');
  assert.equal(h.created.length, 2);
});

test('modern Desktop Commander may omit only get_prompts; missing tool is refused before dispatch', async () => {
  const h = harness();
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  const expected = new Map([
    ['read_file', READ_SCHEMA],
    ['get_prompts', { type: 'object', properties: {} }],
  ]);
  const receipt = await router.preflight('mini4', expected);
  assert.equal(receipt.state, 'READY');
  assert.deepEqual(receipt.toolNames, ['read_file']);
  await assert.rejects(
    router.call('mini4', { name: 'get_prompts', arguments: { action: 'get_prompt', promptId: 'onboarding' } }),
    /FLEET_ROUTE_TOOL_UNAVAILABLE/,
  );
  assert.equal(h.created[0].calls, 0, 'unavailable helper must have zero remote effects');
  await router.call('mini4', { name: 'read_file', arguments: { path: '/etc/os-release' } });
  assert.equal(h.created[0].calls, 1);
  await router.close();
});

test('modern contract does not tolerate another missing core tool', async () => {
  const h = harness();
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  await assert.rejects(
    router.preflight('mini4', new Map([
      ['read_file', READ_SCHEMA],
      ['get_prompts', { type: 'object' }],
      ['write_file', { type: 'object' }],
    ])),
    /FLEET_ROUTE_PREFLIGHT_REFUSED/,
  );
  assert.equal(h.created[0].calls, 0);
  assert.equal(h.created[0].clientCloses, 1);
  await router.close();
});

test('present get_prompts must still match its exact schema', async () => {
  const h = harness();
  const factory = async (...args) => {
    const result = await h.factory(...args);
    const originalList = result.client.listTools;
    result.client.listTools = async () => ({
      tools: [...(await originalList()).tools,
        { name: 'get_prompts', inputSchema: { type: 'array' } }],
    });
    return result;
  };
  const router = createFleetRouter(config(), { clientFactory: factory });
  await assert.rejects(
    router.preflight('mini4', new Map([
      ['read_file', READ_SCHEMA],
      ['get_prompts', { type: 'object', properties: {} }],
    ])),
    /FLEET_ROUTE_PREFLIGHT_REFUSED/,
  );
  assert.equal(h.created[0].calls, 0);
  await router.close();
});

test('gateway-owned output pager remains routable after a modern-host binding', async () => {
  const h = harness();
  const router = createFleetRouter(config(), { clientFactory: h.factory });
  await router.preflight('mini4', new Map([
    ['read_file', READ_SCHEMA],
    ['get_prompts', { type: 'object', properties: {} }],
  ]));
  await router.call('mini4', { name: 'studio_output_page', arguments: { receipt_id: 'test', offset: 0 } });
  assert.equal(h.created[0].calls, 1);
  await router.close();
});


test('known modern integer-only search deltas bind and validate arguments locally before dispatch', async () => {
  const oldSearch = {
    type: 'object', properties: {
      pattern: { type: 'string' },
      maxResults: { type: 'number' },
      contextLines: { type: 'number' },
      timeout_ms: { type: 'number' },
    },
  };
  const modernSearch = structuredClone(oldSearch);
  for (const name of ['maxResults', 'contextLines', 'timeout_ms']) {
    modernSearch.properties[name].type = 'integer';
    modernSearch.properties[name].minimum = 0;
  }
  const oldMore = {
    type: 'object', properties: {
      sessionId: { type: 'string' },
      offset: { type: 'number' },
      length: { type: 'number' },
    },
  };
  const modernMore = structuredClone(oldMore);
  modernMore.properties.offset.type = 'integer';
  modernMore.properties.length.type = 'integer';
  modernMore.properties.length.minimum = 1;
  const h = harness({extraTools: [
    {name:'start_search',inputSchema:modernSearch},
    {name:'get_more_search_results',inputSchema:modernMore},
  ]});
  const router=createFleetRouter(config(),{clientFactory:h.factory});
  const expected=new Map([
    ['read_file',READ_SCHEMA],
    ['get_prompts',{type:'object'}],
    ['start_search',oldSearch],
    ['get_more_search_results',oldMore],
  ]);
  const receipt=await router.preflight('mini4',expected);
  assert.equal(receipt.state,'READY');
  for(const [name,args] of [
    ['start_search',{maxResults:2.5}],
    ['start_search',{maxResults:-1}],
    ['start_search',{contextLines:0.5}],
    ['start_search',{timeout_ms:-2}],
    ['start_search',{timeout_ms:0.2}],
    ['get_more_search_results',{offset:0.75,length:5}],
    ['get_more_search_results',{offset:0,length:0}],
    ['get_more_search_results',{offset:0,length:1.25}],
    ['get_more_search_results',{offset:9007199254740992,length:1}],
    ['start_search',{maxResults:9007199254740992}],
  ]) {
    await assert.rejects(
      router.call('mini4',{name,arguments:args}),
      /FLEET_ROUTE_TOOL_ARGUMENTS_INCOMPATIBLE/,
    );
  }
  assert.equal(h.created[0].calls,0,'invalid requests must never reach remote MCP');
  await router.call('mini4',{
    name:'start_search',
    arguments:{pattern:'abc',maxResults:10,contextLines:0,timeout_ms:2000},
  });
  await router.call('mini4',{
    name:'get_more_search_results',
    arguments:{sessionId:'one',offset:0,length:1},
  });
  assert.equal(h.created[0].calls,2);
  await router.close();
});

test('unknown modern schema difference still fails closed before binding', async () => {
  const oldSchema = {type:'object',properties:{maxResults:{type:'number'},contextLines:{type:'number'},timeout_ms:{type:'number'}}};
  const newSchema=structuredClone(oldSchema);
  for(const field of ['maxResults','contextLines','timeout_ms']){
    newSchema.properties[field].type='integer';newSchema.properties[field].minimum=0;
  }
  newSchema.properties.maxResults.maximum=100;
  const h=harness({extraTools:[{name:'start_search',inputSchema:newSchema}]});
  const router=createFleetRouter(config(),{clientFactory:h.factory});
  await assert.rejects(
    router.preflight('mini4',new Map([['read_file',READ_SCHEMA],['start_search',oldSchema]])),
    /FLEET_ROUTE_PREFLIGHT_REFUSED/,
  );
  assert.equal(h.created[0].calls,0);
  assert.equal(h.created[0].clientCloses,1);
  await router.close();
});
