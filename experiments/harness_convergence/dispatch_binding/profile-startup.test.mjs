import { it, expect, vi, onTestFinished, afterAll } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import * as McpPlugin from '@deepseek-ai/dsh-mcp-client'

const directory = dirname(fileURLToPath(import.meta.url))
const observations = []
// Fulfillment is projected, never pretty-print a live Cordis proxy on refusal failure.
const activation = fiber => Promise.resolve(fiber).then(() => 'ACTIVATED')
afterAll(() => writeFileSync(resolve(directory, '.cache/profile-observations.json'),
  JSON.stringify(observations, null, 2) + '\n'))
function alive(pid) {
  try { process.kill(pid, 0); return true }
  catch (e) { if (e.code === 'ESRCH') return false; throw e }
}
function descriptor(admit, signal) {
  expect(typeof McpPlugin.createAdmittedPlugin).toBe('function')
  return McpPlugin.createAdmittedPlugin(admit, signal)
}
async function host({ mode = 'normal', strict = true } = {}) {
  const root = mkdtempSync(resolve(directory, '.cache/profile-'))
  const nonce = randomUUID(), home = resolve(root, 'home'); mkdirSync(home)
  const inputs = { 'memo.txt': `profile\nneedle ${nonce}\n`,
    'signals.txt': `alpha\nneedle ${nonce}\n` }
  writeFileSync(resolve(root, 'fixture.json'), JSON.stringify({ kind: 'mmx-synthetic-stdio-test', nonce }))
  for (const [file, text] of Object.entries(inputs)) writeFileSync(resolve(root, file), text)
  const events = () => existsSync(resolve(root, 'events.jsonl'))
    ? readFileSync(resolve(root, 'events.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []
  const ctx = new Context(), prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: strict })
  const controller = new AbortController(), fibers = [], state = { allowed: true }, calls = [], workload = {}
  const config = { transport: 'stdio', serverName: 'profile', command: process.execPath,
    args: [resolve(directory, 'stdio-fixture-server.mjs'), root, mode], cwd: root,
    env: { HOME: home, PATH: `${dirname(process.execPath)}:/usr/bin:/bin`, TMPDIR: root },
    toolCallTimeoutMs: 1500, failOnStartupError: true, reconnect: { enabled: false } }
  const admit = snapshot => {
    calls.push(snapshot)
    if (snapshot.serverInfo?.name !== 'mmx-stdio-fixture') throw new Error('wrong server')
    return snapshot.tools.filter(t => ['read_file', 'search_files'].includes(t.name))
      .map(t => ({ rawName: t.name, allow: () => state.allowed }))
  }
  async function settled() {
    for (const start of events().filter(e => e.event === 'start')) {
      await vi.waitFor(() => expect(alive(start.pid)).toBe(false), { timeout: 3000, interval: 10 })
    }
  }
  onTestFinished(async () => {
    controller.abort()
    for (const fiber of fibers.toReversed()) await fiber.dispose()
    await runtime.dispose(); await prompt.dispose(); await settled()
    const starts = events().filter(e => e.event === 'start')
    observations.push({ mode, nonce, events: events(), workload,
      pids: starts.map(e => e.pid), childrenAbsent: starts.every(e => !alive(e.pid)),
      inputsUnchanged: Object.entries(inputs).every(([f, text]) => readFileSync(resolve(root, f), 'utf8') === text) })
  })
  return { ctx, config, admit, controller, state, calls, root, nonce, inputs, events, settled, workload,
    load(plugin, overrides = {}) {
      const fiber = ctx.plugin(plugin, { ...config, ...overrides }); fibers.push(fiber)
      return fiber
    },
    call(file = 'memo.txt') { return ctx.tools.execute({ name: 'mcp__profile__read_file',
      arguments: { file }, callId: randomUUID(), signal: new AbortController().signal }) },
  }
}
it('public admitted plugin activates the real read path with only selected tools', async () => {
  const f = await host()
  const fiber = f.load(descriptor(f.admit, f.controller.signal)); await fiber
  expect(f.calls).toHaveLength(1)
  expect(f.ctx.tools.schemas().map(t => t.name).sort()).toEqual([
    'mcp__profile__read_file', 'mcp__profile__search_files'])
  const value = JSON.parse((await f.call()).value.content[0].text)
  expect(value.nonce).toBe(f.nonce); expect(value.text).toBe(f.inputs['memo.txt'])
  await fiber.dispose(); await f.settled(); expect(f.ctx.tools.schemas()).toEqual([])
})
for (const [title, overrides] of [
  ['permissive startup', { failOnStartupError: false }],
  ['implicit reconnect', { reconnect: undefined }],
  ['enabled reconnect', { reconnect: { enabled: true } }],
]) {
  it(`admitted plugin refuses ${title} before process creation`, async () => {
    const f = await host()
    await expect(activation(f.load(descriptor(f.admit, f.controller.signal), overrides)))
      .rejects.toThrow('MCP_ADMITTED_STARTUP_POLICY_REFUSED')
    expect(f.events()).toEqual([])
  })
}
it('public admitted factory rejects missing host permission or cancellation binding', () => {
  expect(typeof McpPlugin.createAdmittedPlugin).toBe('function')
  expect(() => McpPlugin.createAdmittedPlugin(null, new AbortController().signal)).toThrow(TypeError)
  expect(() => McpPlugin.createAdmittedPlugin(() => [], undefined)).toThrow(TypeError)
})
it('pre-aborted admitted startup creates no process', async () => {
  const f = await host(); f.controller.abort()
  await expect(activation(f.load(descriptor(f.admit, f.controller.signal)))).rejects.toThrow()
  expect(f.events()).toEqual([])
})
it('public admitted startup failure rolls back tools and settles all child processes', async () => {
  const f = await host({ mode: 'reject-list' })
  await expect(activation(f.load(descriptor(f.admit, f.controller.signal))))
    .rejects.toThrow('initial connection or tool synchronization failed')
  expect(f.ctx.tools.schemas()).toEqual([]); await f.settled()
  expect(f.events().filter(e => e.event === 'start').length).toBeGreaterThan(0)
})
it('public admitted plugin shares namespace ownership with the original plugin', async () => {
  const f = await host()
  const first = f.load(descriptor(f.admit, f.controller.signal)); await first
  const starts = f.events().filter(e => e.event === 'start').length
  await expect(activation(f.load(McpPlugin))).rejects.toThrow('already in use')
  expect(f.events().filter(e => e.event === 'start')).toHaveLength(starts)
  expect((await f.call()).isError).toBe(false)
})
it('plugin disposal releases the original namespace for another admitted instance', async () => {
  const f = await host()
  const first = f.load(descriptor(f.admit, f.controller.signal)); await first
  await first.dispose(); await f.settled()
  const second = f.load(descriptor(f.admit, f.controller.signal)); await second
  expect((await f.call()).isError).toBe(false)
})
it('owner abort uses existing plugin teardown and removes admitted tools', async () => {
  const f = await host(), fiber = f.load(descriptor(f.admit, f.controller.signal)); await fiber
  f.controller.abort()
  await vi.waitFor(() => expect(f.ctx.tools.schemas()).toEqual([]), { timeout: 3000, interval: 10 })
  await fiber.dispose(); await f.settled()
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(0)
})

async function workerProfile(f) {
  const { createDshToolProfile } = await import('mmx-worker-profile')
  return createDshToolProfile({ admitGeneration: f.admit, signal: f.controller.signal })
}
it('Mastermind runtime profile performs preflight then activates the actual read process', async () => {
  const f = await host(); const fiber = f.load(await workerProfile(f)); await fiber
  const read = await f.call(); expect(read.isError).toBe(false)
  const value = JSON.parse(read.value.content[0].text)
  expect(value.nonce).toBe(f.nonce); expect(value.text).toBe(f.inputs['memo.txt'])
  f.workload.read = value
  const search = await f.ctx.tools.execute({ name: 'mcp__profile__search_files',
    arguments: { query: f.nonce }, callId: randomUUID(), signal: new AbortController().signal })
  expect(search.isError).toBe(false); f.workload.search = JSON.parse(search.value.content[0].text)
  expect(f.workload.search.matches).toEqual([
    { file: 'memo.txt', line: 2, text: `needle ${f.nonce}` },
    { file: 'signals.txt', line: 2, text: `needle ${f.nonce}` }])
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(1)
  expect(f.ctx.tools.schemas().map(t => t.name).sort()).toEqual([
    'mcp__profile__read_file', 'mcp__profile__search_files'])
  await fiber.dispose(); await f.settled()
})
it('Mastermind runtime profile rejects disabled dispatch enforcement before spawning', async () => {
  const f = await host({ strict: false })
  await expect(activation(f.load(await workerProfile(f)))).rejects.toMatchObject({
    code: 'DSH_DISPATCH_PREFLIGHT_REFUSED', check: 'revocation' })
  expect(f.events()).toEqual([]); expect(f.ctx.tools.schemas()).toEqual([])
})
it('Mastermind runtime profile rejects deny-all false readiness before spawning', async () => {
  const f = await host(), remove = f.ctx.tools.guard(() => 'fixture denied')
  try {
    await expect(activation(f.load(await workerProfile(f)))).rejects.toMatchObject({
      code: 'DSH_DISPATCH_PREFLIGHT_REFUSED', check: 'positive' })
    expect(f.events()).toEqual([]); expect(f.ctx.tools.schemas()).toEqual([])
  } finally { remove() }
})
it('Mastermind runtime profile cancellation during preflight never starts a process', async () => {
  const f = await host()
  const remove = f.ctx.on('tools/execute', async (_exec, next) => { f.controller.abort(); return next() })
  try {
    await expect(activation(f.load(await workerProfile(f)))).rejects.toMatchObject({ name: 'AbortError' })
    expect(f.events()).toEqual([]); expect(f.ctx.tools.schemas()).toEqual([])
  } finally { remove() }
})
it('Mastermind runtime profile snapshots startup config before asynchronous preflight', async () => {
  const f = await host(); f.config.env.MMX_EXPLICIT_CONFIG = 'approved'
  const profile = await workerProfile(f)
  let passedConfig
  const observedProfile = { ...profile, async apply(ctx, config) {
    passedConfig = config; await profile.apply(ctx, config)
  } }
  const remove = f.ctx.on('tools/execute', async (_exec, next) => {
    // Mutate the actual object passed to apply, not Cordis' already-copied input.
    passedConfig.env.MMX_EXPLICIT_CONFIG = 'changed-after-preparation'; return next()
  })
  try {
    const fiber = f.load(observedProfile); await fiber
    expect(passedConfig.env.MMX_EXPLICIT_CONFIG).toBe('changed-after-preparation')
    expect(f.events().filter(e => e.event === 'start').map(e => e.explicit)).toEqual(['approved', 'approved'])
    expect((await f.call()).isError).toBe(false)
  } finally { remove() }
})
it('legacy experiment import resolves the same runtime preflight implementation', async () => {
  const old = await import('./qualify-loaded-runtime.mjs')
  const current = await import('../../../integrations/acp_worker/dsh_dispatch_preflight.mjs')
  expect(old.qualifyLoadedDispatchRuntime).toBe(current.qualifyLoadedDispatchRuntime)
})
it('owner abort during real discovery prevents activation and settles startup processes', async () => {
  const f = await host({ mode: 'hold-list' })
  const fiber = f.load(await workerProfile(f)), running = activation(fiber)
  running.catch(() => {})
  await vi.waitFor(() => expect(f.events().some(e => e.event === 'discovery-entered')).toBe(true), { timeout: 2500, interval: 10 })
  f.controller.abort()
  await expect(running).rejects.toMatchObject({ name: 'AbortError' })
  await fiber.dispose(); await f.settled(); expect(f.ctx.tools.schemas()).toEqual([])
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(0)
})
it('owner abort during an actual profile tool call settles without replay', async () => {
  const f = await host({ mode: 'wait-cancel' }), fiber = f.load(await workerProfile(f)); await fiber
  const running = f.call()
  await vi.waitFor(() => expect(f.events().some(e => e.event === 'read')).toBe(true), { timeout: 2500, interval: 10 })
  const starts = f.events().filter(e => e.event === 'start').map(e => e.pid)
  f.controller.abort()
  expect((await running).isError).toBe(true)
  await fiber.dispose(); await f.settled()
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(1)
  expect(f.events().filter(e => e.event === 'start').map(e => e.pid)).toEqual(starts)
})
it('admission refusal rolls back namespace so a later explicit instance can activate', async () => {
  const f = await host()
  const rejected = f.load(descriptor(() => { throw new Error('fixture policy refused') }, f.controller.signal))
  await expect(activation(rejected)).rejects.toThrow('initial connection or tool synchronization failed')
  await rejected.dispose(); await f.settled()
  const next = f.load(await workerProfile(f)); await next
  expect((await f.call()).isError).toBe(false)
})
