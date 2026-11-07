import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
const mode = process.env.MMX_DSH_GRANT_SOURCE ?? 'runtime'
if (!['runtime', 'mutant'].includes(mode)) throw new Error('Unknown test source')
const url = new URL(mode === 'mutant' ? './.cache/grant-mutant.mjs'
  : '../../../integrations/acp_worker/dsh_mcp_grant.mjs', import.meta.url)
async function api() {
  assert.ok(existsSync(url), 'Runtime grant projection bridge is missing')
  return import(url.href)
}
function fixture() {
  const projection = { schema: 'mastermind.dsh_mcp_tool_projection.v1', production_armed: false,
    source: { profile_id: 'fixture', profile_digest: 'a'.repeat(64), grant_digest: 'b'.repeat(64),
      tool_schema_digest: 'c'.repeat(64), capability_id: 'fixture.read',
      execution_surface: 'codex-app-server', auth_realm: 'dedicated-worker-account', auth_status: 'unsupported' },
    target: { serverName: 'fixture', transport: 'stdio', command: '/fixture/node', args: ['/fixture/server.mjs'] },
    serverInfo: { name: 'fixture-server', version: '1' }, required: true, approvalMode: 'approve',
    tools: [{ name: 'read_file', inputSchema: { type: 'object', properties: { file: { type: 'string' } } },
      outputSchema: null, annotations: { readOnlyHint: true }, execution: null }] }
  const snapshot = { serverName: 'fixture', serverInfo: structuredClone(projection.serverInfo),
    tools: [structuredClone(projection.tools[0]), { name: 'write_file', inputSchema: { type: 'object' } }] }
  const controller = new AbortController()
  const calls = [], state = { allowed: true }
  const options = { signal: controller.signal, isCurrentBinding(binding, request) {
    calls.push({ binding, request }); return state.allowed
  } }
  const config = { ...structuredClone(projection.target), env: { HOME: '/fixture/home' },
    cwd: '/fixture', failOnStartupError: true, reconnect: { enabled: false } }
  return { projection, snapshot, controller, options, config, calls, state }
}

test('matches exact source grant and filters ungranted tools', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  const grant = compileDshMcpGrant(f.projection, f.options)
  grant.assertConfig(f.config)
  const rows = grant.admitGeneration(f.snapshot)
  assert.deepEqual(rows.map(x => x.rawName), ['read_file'])
  assert.equal(rows[0].allow({ signal: f.controller.signal }), true)
  assert.deepEqual(f.calls.map(x => x.request.phase), ['startup', 'discovery', 'dispatch'])
  assert.equal(f.calls[2].request.rawName, 'read_file')
  assert.equal(f.calls[0].binding.source.profile_digest, f.projection.source.profile_digest)
  assert.ok(Object.isFrozen(f.calls[0].binding.source))
})

for (const [label, change] of [
  ['input schema', f => { f.snapshot.tools[0].inputSchema.properties.file.type = 'number' }],
  ['output schema', f => { f.snapshot.tools[0].outputSchema = { type: 'string' } }],
  ['annotations', f => { f.snapshot.tools[0].annotations.readOnlyHint = false }],
  ['execution policy', f => { f.snapshot.tools[0].execution = { taskSupport: 'required' } }],
  ['server identity', f => { f.snapshot.serverInfo.name = 'different' }],
  ['server version', f => { f.snapshot.serverInfo.version = '2' }],
  ['namespace', f => { f.snapshot.serverName = 'other' }],
  ['missing required tool', f => { f.snapshot.tools.shift() }],
  ['duplicate catalog tool', f => { f.snapshot.tools.push(f.snapshot.tools[0]) }],
]) test(`refuses changed ${label}`, async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  const grant = compileDshMcpGrant(f.projection, f.options); change(f)
  assert.throws(() => grant.admitGeneration(f.snapshot), { code: 'DSH_MCP_GRANT_REFUSED' })
})

test('exact target must match before startup', async () => {
  const { compileDshMcpGrant } = await api()
  for (const changes of [{ command: '/other/node' }, { args: [] }, { serverName: 'other' },
                         { transport: 'streamable-http', url: 'https://other.invalid/' }]) {
    const f = fixture(), grant = compileDshMcpGrant(f.projection, f.options)
    assert.throws(() => grant.assertConfig({ ...f.config, ...changes }), { code: 'DSH_MCP_GRANT_REFUSED' })
  }
})
test('host revocation and both cancellation signals refuse dispatch', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  const rows = compileDshMcpGrant(f.projection, f.options).admitGeneration(f.snapshot)
  f.state.allowed = false
  assert.equal(rows[0].allow({ signal: f.controller.signal }), false)
  f.state.allowed = true
  const other = new AbortController(); other.abort()
  assert.equal(rows[0].allow({ signal: other.signal }), false)
  f.controller.abort()
  assert.equal(rows[0].allow({ signal: new AbortController().signal }), false)
})
test('truthy and asynchronous host decisions cannot authorize anything', async () => {
  const { compileDshMcpGrant } = await api()
  for (const decision of [1, {}, Promise.resolve(true), false, undefined]) {
    const f = fixture(); f.options.isCurrentBinding = () => decision
    const grant = compileDshMcpGrant(f.projection, f.options)
    assert.throws(() => grant.admitGeneration(f.snapshot), { code: 'DSH_MCP_GRANT_REFUSED' })
  }
})

test('projection mutation cannot widen already compiled permission', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  const grant = compileDshMcpGrant(f.projection, f.options)
  f.projection.tools[0].inputSchema.type = 'null'; f.projection.target.command = '/other/node'
  f.options.isCurrentBinding = () => true; f.state.allowed = false
  assert.throws(() => grant.admitGeneration(f.snapshot), { code: 'DSH_MCP_GRANT_REFUSED' })
  f.state.allowed = true
  grant.assertConfig(f.config)
  assert.equal(grant.admitGeneration(f.snapshot)[0].allow({ signal: f.controller.signal }), true)
})
test('prose changes do not change schema permission', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  f.snapshot.tools[0].description = 'new prose'; f.snapshot.tools[0].title = 'new label'
  assert.equal(compileDshMcpGrant(f.projection, f.options).admitGeneration(f.snapshot).length, 1)
})
test('missing host binding and malformed projection refuse before use', async () => {
  const { compileDshMcpGrant } = await api()
  const f = fixture()
  for (const options of [{}, { signal: f.controller.signal }, { isCurrentBinding: () => true }])
    assert.throws(() => compileDshMcpGrant(f.projection, options), { code: 'DSH_MCP_GRANT_REFUSED' })
  for (const changes of [{ production_armed: true }, { required: false }, { approvalMode: 'prompt' },
                         { tools: [] }, { schema: 'unknown' }])
    assert.throws(() => compileDshMcpGrant({ ...f.projection, ...changes }, f.options),
      { code: 'DSH_MCP_GRANT_REFUSED' })
})
test('foreign projection identity cannot satisfy a bound host', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  f.options.isCurrentBinding = binding => binding.source.profile_digest === 'd'.repeat(64)
  assert.throws(() => compileDshMcpGrant(f.projection, f.options).assertConfig(f.config),
    { code: 'DSH_MCP_GRANT_REFUSED' })
})
test('HTTPS target is compared exactly, not just by hostname', async () => {
  const f = fixture(), { compileDshMcpGrant } = await api()
  f.projection.target = { serverName: 'fixture', transport: 'streamable-http', url: 'https://example.test/mcp' }
  const grant = compileDshMcpGrant(f.projection, f.options)
  grant.assertConfig(f.projection.target)
  assert.throws(() => grant.assertConfig({ ...f.projection.target, url: 'https://example.test/other' }),
    { code: 'DSH_MCP_GRANT_REFUSED' })
})
