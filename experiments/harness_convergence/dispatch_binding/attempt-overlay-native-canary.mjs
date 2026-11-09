// Exact pinned DSH AgentLoop/ToolRuntime + MCP SDK, provider-free, synthetic.
// No Executive Attempt is issued and no installed ACP descriptor is armed.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'
import { setTimeout as sleep } from 'node:timers/promises'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'

const here = dirname(fileURLToPath(import.meta.url)), cache = resolve(here, '.cache')
const hash = data => createHash('sha256').update(data).digest('hex')
const build = JSON.parse(readFileSync(resolve(cache, 'profile-build-result.json'), 'utf8'))
assert.equal(hash(readFileSync(resolve(cache, build.artifact))), build.artifact_sha256)
const built = await import(pathToFileURL(resolve(cache, build.artifact)).href)
const scenario = process.argv[2] ?? 'normal'
assert.ok(['normal', 'host-revoked', 'foreign-env', 'pre-aborted'].includes(scenario))
const root = mkdtempSync(resolve(cache, 'attempt-bound-'))
const home = resolve(root, 'home'); mkdirSync(home)
const nonce = randomUUID()
const input = { 'memo.txt': 'attempt read\nneedle ' + nonce + '\n',
  'signals.txt': 'needle ' + nonce + '\n' }
writeFileSync(resolve(root, 'fixture.json'), JSON.stringify({ kind: 'mmx-synthetic-stdio-test', nonce }))
for (const [name, value] of Object.entries(input)) writeFileSync(resolve(root, name), value)
const events = () => existsSync(resolve(root, 'events.jsonl'))
  ? readFileSync(resolve(root, 'events.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []
const config = { serverName: 'mastermindAcpWorkspaceRead', transport: 'stdio',
  command: process.execPath, args: [resolve(here, 'stdio-fixture-server.mjs'), root, 'normal'],
  failOnStartupError: true, reconnect: { enabled: false }, toolCallTimeoutMs: 1800 }
const ownerEnv = { MMX_ACP_WORKSPACE_PATH: root, MMX_ACP_WORKSPACE_BASE_SHA: 'a'.repeat(40),
  MMX_ACP_RUN_ID: 'test-run', MMX_ACP_JOB_ID: 'test-job', MMX_ACP_WORKER_ID: 'test-worker',
  MMX_ACP_DEADLINE_MS: String(Date.now() + 45000) }
const attemptOverlay = { cwd: root, env: ownerEnv }
const ctx = new Context(), prompt = await ctx.plugin(SystemPrompt)
const runtime = await ctx.plugin(built.ToolRuntime, { strictDispatchBinding: true })
const cap = new AbortController(), owner = new AbortController()
let capture, admitted, catalog, phases = [], completed, rejected
let allowed = true
const source = { profile_id: 'worker.acp.providerfree.readonly.v1',
  profile_digest: 'a'.repeat(64), grant_digest: 'b'.repeat(64), tool_schema_digest: 'c'.repeat(64),
  capability_id: 'mastermind-acp-workspace-read-v1',
  execution_surface: 'acp-agent', auth_realm: 'dedicated-worker-no-auth', auth_status: 'unsupported' }
const allowedNames = new Set(['read_file', 'search_files'])
const clean = { ...config, cwd: root, env: { HOME: home,
  PATH: `${dirname(process.execPath)}:/usr/bin:/bin`, TMPDIR: root } }
function isAlive(pid) {
  try { process.kill(pid, 0); return true }
  catch (error) { if (error.code === 'ESRCH') return false; throw error }
}
try {
  // Real discovery captures actual server/tool schema, without admitting tools.
  capture = ctx.plugin(built.createDshToolProfile({
    signal: cap.signal, admitGeneration(value) { catalog = value; return [] },
  }), clean)
  await capture
  await capture.dispose(); cap.abort()
  assert.ok(catalog?.serverInfo?.name)
  const projection = {
    schema: 'mastermind.dsh_mcp_tool_projection.v1', production_armed: false,
    source, target: {
      serverName: config.serverName, transport: config.transport,
      command: config.command, args: config.args,
    },
    serverInfo: structuredClone(catalog.serverInfo),
    required: true, approvalMode: 'approve',
    tools: structuredClone(catalog.tools.filter(item => allowedNames.has(item.name))),
  }
  assert.equal(projection.tools.length, 2)
  if (scenario === 'pre-aborted') owner.abort()
  const plugin = built.createDshGrantedToolProfile({
    projection, signal: owner.signal, attemptOverlay,
    isCurrentBinding(binding, request) {
      phases.push(request.phase)
      return allowed && binding.source.profile_id === source.profile_id
        && binding.source.profile_digest === source.profile_digest
        && request.attempt?.schema === 'mastermind.dsh_acp_attempt_binding.v1'
        && request.attempt.cwd === root
        && request.attempt.env.MMX_ACP_JOB_ID === 'test-job'
        && request.attempt.env.MMX_ACP_RUN_ID === 'test-run'
        && request.attempt.env.MMX_ACP_WORKER_ID === 'test-worker'
    },
  })
  const suppliedConfig = scenario === 'foreign-env'
    ? { ...config, env: { OPENAI_API_KEY: 'forbidden' } } : config
  try {
    admitted = ctx.plugin(plugin, suppliedConfig)
    await admitted
    completed = true
  } catch (error) {
    rejected = { name: error.name, code: error.code ?? null, message: error.message }
  }
  const starts = events().filter(x => x.event === 'start')
  if (starts.length !== (['normal', 'host-revoked'].includes(scenario) ? 4 : 2))
    console.error(JSON.stringify({ scenario, completed, rejected, phases,
      starts: starts.length, events: events().map(x => x.event) }))
  assert.equal(starts.length, ['normal', 'host-revoked'].includes(scenario) ? 4 : 2,
    'Denied startup cannot create an additional MCP child')
  if (['normal', 'host-revoked'].includes(scenario)) {
    assert.equal(completed, true, JSON.stringify(rejected))
    for (const start of starts.slice(2)) {
      assert.equal(start.cwd, root)
      assert.equal(start.home, root)
      assert.equal(start.tmpdir, root)
      assert.equal(start.ambient, null)
      assert.equal(start.nodeOptions, null)
      assert.deepEqual(start.attempt, ownerEnv)
    }
    assert.deepEqual(ctx.tools.schemas().map(t => t.name).sort(),
      ['mcp__mastermindAcpWorkspaceRead__read_file', 'mcp__mastermindAcpWorkspaceRead__search_files'])
    const call = (name, args) => ctx.tools.execute({
      name: `mcp__mastermindAcpWorkspaceRead__${name}`, arguments: args,
      callId: randomUUID(), signal: owner.signal,
    })
    const read = await call('read_file', { file: 'memo.txt' })
    assert.equal(read.isError, false)
    assert.equal(JSON.parse(read.value.content[0].text).text, input['memo.txt'])
    if (scenario === 'host-revoked') allowed = false
    const search = await call('search_files', { query: nonce })
    assert.equal(search.isError, scenario === 'host-revoked')
    assert.equal((await call('write_file', {})).isError, true)
    assert.equal(events().filter(x => x.event === 'read').length, 1)
    assert.equal(events().filter(x => x.event === 'search').length,
      scenario === 'normal' ? 1 : 0)
    assert.ok(phases.includes('discovery') && phases.includes('dispatch'))
  } else {
    assert.equal(completed, undefined)
    assert.ok(rejected)
    if (scenario === 'foreign-env') {
      assert.equal(rejected.code, 'DSH_ACP_ATTEMPT_OVERLAY_REFUSED')
      assert.ok(phases.includes('startup'))
    } else if (scenario === 'pre-aborted') {
      assert.equal(rejected.name, 'AbortError')
      assert.equal(phases.length, 0)
    }
    assert.equal(events().filter(x => x.event === 'read').length, 0)
  }
} finally {
  owner.abort(); cap.abort()
  await admitted?.dispose(); await capture?.dispose()
  await runtime.dispose(); await prompt.dispose()
}
for (const start of events().filter(event => event.event === 'start')) {
  const until = Date.now() + 3000
  while (isAlive(start.pid) && Date.now() < until) await sleep(10)
  assert.equal(isAlive(start.pid), false)
}
assert.ok(Object.entries(input).every(([name, value]) => readFileSync(resolve(root, name), 'utf8') === value))
const result = { success: true, scenario, artifact_sha256: build.artifact_sha256,
  source: 'synthetic ACP Attempt, real pinned DSH plugin, real MCP child, no Executive admission',
  phases, events: events().map(x => ({ event: x.event, attempt: x.attempt, cwd: x.cwd, pid: x.pid })),
  admitted: !!completed, rejected, children_absent: true, input_unchanged: true,
  read_calls: events().filter(x => x.event === 'read').length,
  search_calls: events().filter(x => x.event === 'search').length, model_requests: 0 }
writeFileSync(resolve(cache, `attempt-overlay-${scenario}.json`), JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify({ success: true, scenario, read_calls: result.read_calls,
  search_calls: result.search_calls, children_absent: true }))
