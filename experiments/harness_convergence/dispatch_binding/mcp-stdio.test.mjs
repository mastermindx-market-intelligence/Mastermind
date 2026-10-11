import { it, expect, vi, onTestFinished, afterAll } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomUUID, createHash } from 'node:crypto'
import { Context } from '@deepseek-ai/cordis'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { startConnection, resolveReconnectPolicy } from 'mmx-mcp-connection'
import { qualifyLoadedDispatchRuntime } from './qualify-loaded-runtime.mjs'

const directory = dirname(fileURLToPath(import.meta.url))
const observations = []
afterAll(() => writeFileSync(resolve(directory, '.cache/stdio-observations.json'),
  JSON.stringify(observations, null, 2) + '\n'))
const hash = text => createHash('sha256').update(text).digest('hex')
function alive(pid) {
  try { process.kill(pid, 0); return true }
  catch (error) { if (error.code === 'ESRCH') return false; throw error }
}
async function setup({ strict = true, mode = 'normal', denied = false } = {}) {
  const root = mkdtempSync(resolve(directory, '.cache/stdio-'))
  const nonce = randomUUID(), home = resolve(root, 'home')
  mkdirSync(home)
  const input = { 'memo.txt': `Research fixture\nneedle ${nonce}\n`,
    'signals.txt': `alpha\nbeta\nneedle ${nonce}\n` }
  writeFileSync(resolve(root, 'fixture.json'), JSON.stringify({ kind: 'mmx-synthetic-stdio-test', nonce }))
  for (const [name, text] of Object.entries(input)) writeFileSync(resolve(root, name), text)
  const events = () => existsSync(resolve(root, 'events.jsonl'))
    ? readFileSync(resolve(root, 'events.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []
  const ctx = new Context(), prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const preflight = await qualifyLoadedDispatchRuntime(ctx, { signal: new AbortController().signal })
  const state = { allowed: !denied }, snapshots = [], workloadEvidence = {}
  const config = { transport: 'stdio', serverName: 'disk', command: process.execPath,
    args: [resolve(directory, 'stdio-fixture-server.mjs'), root, mode], cwd: root,
    env: { HOME: home, PATH: `${dirname(process.execPath)}:/usr/bin:/bin`, TMPDIR: root,
      MMX_EXPLICIT_CONFIG: 'fixture-explicit' }, toolCallTimeoutMs: 3000, failOnStartupError: true }
  const admit = snapshot => {
    snapshots.push(snapshot)
    if (snapshot.serverInfo?.name !== 'mmx-stdio-fixture' || snapshot.serverInfo?.version !== '1') throw new Error('Fixture identity mismatch')
    return snapshot.tools.filter(tool => ['read_file', 'search_files'].includes(tool.name))
      .map(tool => ({ rawName: tool.name, allow: () => state.allowed }))
  }
  const connection = startConnection(ctx, config,
    resolveReconnectPolicy({ enabled: false }, 'fixture'), strict ? admit : undefined)
  let stopped = false
  async function close() {
    if (stopped) return
    await connection.dispose()
    const starts = events().filter(event => event.event === 'start')
    for (const start of starts) await vi.waitFor(() => expect(alive(start.pid)).toBe(false), { timeout: 3000, interval: 10 })
    await runtime.dispose(); await prompt.dispose(); stopped = true
    observations.push({ mode, strict, root, nonce, preflightVerified: preflight.verified,
      events: events(), workloadEvidence, childAbsentAfterDispose: starts.length > 0 && starts.every(start => !alive(start.pid)),
      childCount: starts.length,
      inputsUnchanged: Object.entries(input).every(([name, text]) => readFileSync(resolve(root, name), 'utf8') === text) })
  }
  onTestFinished(async () => { try { await close() } finally { vi.unstubAllEnvs() } })
  return { ctx, connection, events, close, input, nonce, root, home, state, snapshots, workloadEvidence,
    async ready() { expect(await connection.ready).toEqual({}); expect(events()[0].event).toBe('start') },
    call(name, args, signal = new AbortController().signal) {
      return ctx.tools.execute({ name: `mcp__disk__${name}`, arguments: args,
        callId: ToolCallId(randomUUID()), signal })
    } }
}

it('real stdio subprocess reads and searches two synthetic files through admitted tools', async () => {
  const f = await setup(); await f.ready()
  expect(f.ctx.tools.schemas().map(t => t.name).sort()).toEqual(['mcp__disk__read_file', 'mcp__disk__search_files'])
  const read = await f.call('read_file', { file: 'memo.txt' })
  expect(read.isError).toBe(false)
  const value = JSON.parse(read.value.content[0].text)
  expect(value.text).toBe(f.input['memo.txt']); expect(value.sha256).toBe(hash(value.text))
  expect(value.nonce).toBe(f.nonce); expect(value.pid).not.toBe(process.pid)
  f.workloadEvidence.read = value
  const search = await f.call('search_files', { query: f.nonce })
  expect(search.isError).toBe(false)
  f.workloadEvidence.search = JSON.parse(search.value.content[0].text)
  expect(JSON.parse(search.value.content[0].text).matches).toEqual([
    { file: 'memo.txt', line: 2, text: `needle ${f.nonce}` },
    { file: 'signals.txt', line: 3, text: `needle ${f.nonce}` },
  ])
  expect((await f.call('write_file', {})).isError).toBe(true)
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(1)
  expect(f.events().filter(e => e.event === 'search')).toHaveLength(1)
  expect(f.events().some(e => e.event === 'ungranted-write')).toBe(false)
  await f.close()
})

it('host-admitted stdio excludes unapproved ambient configuration', async () => {
  vi.stubEnv('MMX_UNAPPROVED_CONFIG', 'fixture-ambient')
  const f = await setup(); await f.ready()
  expect(f.events()[0].ambient).toBeNull()
  expect(f.events()[0].explicit).toBe('fixture-explicit')
})
it('host-admitted stdio excludes ambient Node startup options', async () => {
  vi.stubEnv('NODE_OPTIONS', '--no-warnings')
  const f = await setup(); await f.ready()
  expect(f.events()[0].nodeOptions).toBeNull()
})
it('explicit private home and cwd reach the actual child', async () => {
  const f = await setup(); await f.ready()
  expect(f.events()[0].home).toBe(f.home); expect(f.events()[0].cwd).toBe(f.root)
})
it('legacy transport retains its existing scrubbed ambient behavior', async () => {
  vi.stubEnv('MMX_UNAPPROVED_CONFIG', 'fixture-ambient')
  const f = await setup({ strict: false }); await f.ready()
  expect(f.events()[0].ambient).toBe('fixture-ambient')
  expect((await f.call('read_file', { file: 'memo.txt' })).isError).toBe(false)
})
it('revoked live grant prevents an actual child request', async () => {
  const f = await setup(); await f.ready()
  const remove = f.ctx.on('tools/execute', async (_exec, next) => {
    await Promise.resolve(); f.state.allowed = false; return next()
  })
  try { expect((await f.call('read_file', { file: 'memo.txt' })).isError).toBe(true) }
  finally { remove() }
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(0)
})
it('instruction and resource channels remain closed over real stdio', async () => {
  const f = await setup(); await f.ready()
  expect(f.connection.instructions()).toBe('')
  await expect(f.connection.resources.request({ method: 'resources/read', uri: 'fixture://secret' },
    { signal: new AbortController().signal })).rejects.toThrow('MCP_RESOURCE_NOT_ADMITTED')
  expect(f.events().some(e => e.event === 'resource-read')).toBe(false)
})
it('startup discovery rejection settles the real child', async () => {
  const f = await setup({ mode: 'reject-list' })
  expect((await f.connection.ready).error).toBeDefined()
  expect(f.ctx.tools.schemas()).toEqual([])
  await f.close()
})
it('lost response never resends the already-read request', async () => {
  const f = await setup({ mode: 'lost-reply' }); await f.ready()
  const startsBefore = f.events().filter(e => e.event === 'start').map(e => e.pid)
  // MCP2 auto negotiation uses a disposable probe before the session process.
  expect(startsBefore).toHaveLength(2)
  expect((await f.call('read_file', { file: 'memo.txt' })).isError).toBe(true)
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(1)
  await f.close()
  expect(f.events().filter(e => e.event === 'start').map(e => e.pid)).toEqual(startsBefore)
})
it('in-flight cancellation reaches the real server and settles without a second call', async () => {
  const f = await setup({ mode: 'wait-cancel' }); await f.ready()
  const controller = new AbortController()
  const pending = f.call('read_file', { file: 'memo.txt' }, controller.signal)
  await vi.waitFor(() => expect(f.events().some(e => e.event === 'read')).toBe(true), { timeout: 2000, interval: 10 })
  controller.abort()
  expect((await pending).isError).toBe(true)
  await vi.waitFor(() => expect(f.events().some(e => e.event === 'cancelled')).toBe(true), { timeout: 2000, interval: 10 })
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(1)
  await f.close()
})
it('the synthetic fixture never reads a caller-selected outside path', async () => {
  const f = await setup(); await f.ready()
  expect((await f.call('read_file', { file: '../outside.txt' })).isError).toBe(true)
  expect(f.events().filter(e => e.event === 'read')).toHaveLength(0)
})
it('SDK negotiation probe is reaped before the useful session is ready', async () => {
  const f = await setup(); await f.ready()
  const starts = f.events().filter(e => e.event === 'start')
  expect(starts).toHaveLength(2)
  expect(starts[0].pid).not.toBe(starts[1].pid)
  expect(alive(starts[0].pid)).toBe(false)
  expect(alive(starts[1].pid)).toBe(true)
  const result = await f.call('read_file', { file: 'memo.txt' })
  expect(JSON.parse(result.value.content[0].text).pid).toBe(starts[1].pid)
  await f.close()
  expect(starts.every(e => !alive(e.pid))).toBe(true)
})
