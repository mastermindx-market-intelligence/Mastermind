import { describe, expect, it, onTestFinished, afterAll, vi } from 'vitest'
import { writeFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { Context } from '@deepseek-ai/cordis'
import { Client, InMemoryTransport } from '@modelcontextprotocol/client'
import { McpServer } from '@modelcontextprotocol/server'
import { serveStdio } from '@modelcontextprotocol/server/stdio'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { syncTools, publicToolName } from 'mmx-mcp-tools'
import { startConnection, resolveReconnectPolicy } from 'mmx-mcp-connection'
const { transportFactory } = vi.hoisted(() => ({ transportFactory: vi.fn() }))
vi.mock('mmx-mcp-transport', () => ({ createTransport: transportFactory }))
const observations = []
afterAll(() => {
  const mode = process.env.MMX_MCP_SOURCE ?? 'donor'
  writeFileSync(new URL(`./.cache/mcp-observations-${mode}.json`, import.meta.url),
    JSON.stringify(observations, null, 2) + '\n')
})

async function setup(version = '1') {
  const ctx = new Context()
  const prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const server = new McpServer({ name: 'mmx-read-fixture', version })
  const counts = { read: 0, write: 0 }
  const state = { current: true, allowed: true, gate: undefined, entered: undefined }
  const nonce = randomUUID()
  server.registerTool('read.memo', { inputSchema: z.object({ path: z.literal('memo') }) },
    async () => { counts.read++; state.entered?.(); await state.gate
      return { content: [{ type: 'text', text: nonce }] } })
  server.registerTool('write_memo', { inputSchema: z.object({}),
    annotations: { readOnlyHint: true } }, async () => {
    counts.write++; return { content: [] }
  })
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const serving = serveStdio(() => server, { transport: serverTransport })
  const client = new Client({ name: 'mmx-admission-test', version: '1' })
  await client.connect(clientTransport)
  let registrations = new Map()
  const snapshots = []
  const options = { registrationFailure: 'throw', serverName: 'fixture',
    toolCallTimeoutMs: 1000, isCurrentGeneration: () => state.current,
    admitGeneration(snapshot) {
      snapshots.push(snapshot)
      return snapshot.tools.filter(t => t.name === 'read.memo')
        .map(t => ({ rawName: t.name, allow: () => state.allowed }))
    },
  }
  onTestFinished(async () => {
    for (const dispose of registrations.values()) dispose()
    await client.close(); await serving.close(); await runtime.dispose(); await prompt.dispose()
  })
  return { ctx, client, server, counts, state, nonce, options, snapshots,
    async sync(overrides = {}) {
      registrations = await syncTools(client, ctx, { ...options, ...overrides }, registrations)
      return registrations
    },
    call(rawName = 'read.memo') { return ctx.tools.execute({
      name: publicToolName('fixture', rawName), callId: ToolCallId(randomUUID()),
      arguments: rawName === 'read.memo' ? { path: 'memo' } : {},
      signal: new AbortController().signal,
    }) },
  }
}

describe('MCP generation admission with actual SDK and ToolRuntime', () => {
  it('exposes only admitted tools and returns a real server nonce', async () => {
    const f = await setup(); await f.sync()
    expect(f.ctx.tools.schemas().map(t => t.name)).toEqual([publicToolName('fixture', 'read.memo')])
    const result = await f.call()
    expect(result.isError).toBe(false)
    expect(result.value.content).toEqual([{ type: 'text', text: f.nonce }])
    expect((await f.call('write_memo')).isError).toBe(true)
    expect(f.counts).toEqual({ read: 1, write: 0 })
    observations.push({ journey: 'permitted-real-mcp-call', rawName: 'read.memo',
      publicName: publicToolName('fixture', 'read.memo'), sourceNonce: f.nonce,
      result: result.value, calls: { ...f.counts },
      exposed: f.ctx.tools.schemas().map(t => t.name) })
  })
  it('passes immutable complete schemas and actual server identity to admission', async () => {
    const f = await setup(); await f.sync()
    expect(f.snapshots).toHaveLength(1)
    const s = f.snapshots[0]
    expect(s.serverName).toBe('fixture')
    expect(s.serverInfo).toEqual({ name: 'mmx-read-fixture', version: '1' })
    expect(s.tools).toHaveLength(2)
    expect(Object.isFrozen(s) && Object.isFrozen(s.tools)).toBe(true)
    expect(Object.isFrozen(s.tools[0].inputSchema.properties)).toBe(true)
    expect(s.tools.find(t => t.name === 'write_memo').annotations.readOnlyHint).toBe(true)
  })
  it('refuses revoked permission after an asynchronous wrapper', async () => {
    const f = await setup(); await f.sync()
    const remove = f.ctx.on('tools/execute', async (_exec, next) => {
      await Promise.resolve(); f.state.allowed = false; return next()
    })
    try { expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0) }
    finally { remove() }
  })
  it('refuses a disconnected connection generation before sending', async () => {
    const f = await setup(); await f.sync(); f.state.current = false
    expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
  })
  it('retires the old generation when re-admission refuses schema drift', async () => {
    const f = await setup(); await f.sync()
    await expect(f.sync({ admitGeneration() { throw new Error('SCHEMA_DRIFT') } })).rejects.toThrow('SCHEMA_DRIFT')
    expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
  })
  it('retires the old generation before a failing list request', async () => {
    const f = await setup(); await f.sync()
    f.server.server.setRequestHandler('tools/list', async () => { throw new Error('LIST_FAILED') })
    await expect(f.sync()).rejects.toThrow()
    expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
  })
  it('retires the previous generation while refreshed discovery is pending', async () => {
    const f = await setup(); await f.sync()
    let release, enter
    const held = new Promise(r => { release = r }), entered = new Promise(r => { enter = r })
    f.server.server.setRequestHandler('tools/list', async () => { enter(); await held; return { tools: [] } })
    const pending = f.sync()
    try { await entered; expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0) }
    finally { release(); await pending }
  })
  it('retained old definition cannot send after a successful replacement sync', async () => {
    const f = await setup(); await f.sync()
    const old = f.ctx.tools.get(publicToolName('fixture', 'read.memo'))
    await f.sync()
    await expect(old.execute({ path: 'memo' }, {
      name: old.name, callId: ToolCallId('retained'), signal: new AbortController().signal,
    })).rejects.toThrow('MCP_TOOL_ADMISSION_REFUSED')
    expect(f.counts.read).toBe(0)
  })
  for (const [name, decision] of [
    ['unlisted tool', () => [{ rawName: 'absent', allow: () => true }]],
    ['duplicate selection', () => ['read.memo', 'read.memo'].map(rawName => ({ rawName, allow: () => true }))],
    ['nonfunction guard', () => [{ rawName: 'read.memo', allow: true }]],
    ['async admission', async () => []],
  ]) {
    it(`refuses ${name} without exposure or execution`, async () => {
      const f = await setup()
      await expect(f.sync({ admitGeneration: decision })).rejects.toThrow()
      expect(f.ctx.tools.schemas()).toEqual([]); expect(f.counts).toEqual({ read: 0, write: 0 })
    })
  }
  it('requires live connection binding when admission is enabled', async () => {
    const f = await setup()
    await expect(f.sync({ isCurrentGeneration: undefined })).rejects.toThrow()
    expect(f.ctx.tools.schemas()).toEqual([])
  })
  it('requires a literal true from the final execution guard', async () => {
    const f = await setup()
    await f.sync({ admitGeneration: () => [{ rawName: 'read.memo', allow: async () => true }] })
    expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
  })
  it('keeps a completed old-generation call attributable without resending it', async () => {
    const f = await setup(); await f.sync()
    let release, entered
    const observed = new Promise(r => { entered = r })
    f.state.entered = entered; f.state.gate = new Promise(r => { release = r })
    const calling = f.call()
    try {
      await observed
      await f.sync({ admitGeneration: () => [] })
      release()
      const result = await calling
      expect(result.isError).toBe(false)
      expect(result.value.content).toEqual([{ type: 'text', text: f.nonce }])
      expect(f.counts.read).toBe(1)
      expect(f.ctx.tools.schemas()).toEqual([])
    } finally { release(); await calling }
  })
  it('preserves the unconfigured legacy bridge behavior', async () => {
    const f = await setup(); await f.sync({ admitGeneration: undefined })
    expect(f.ctx.tools.schemas()).toHaveLength(2)
    expect((await f.call()).isError).toBe(false)
    f.server.server.setRequestHandler('tools/list', async () => { throw new Error('LIST_FAILED') })
    await expect(f.sync({ admitGeneration: undefined })).rejects.toThrow()
    expect((await f.call()).isError).toBe(false)
    expect(f.counts.read).toBe(2)
  })
})

it('threads admission through the actual connection startup owner', async () => {
  const ctx = new Context()
  const prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const server = new McpServer({ name: 'connection-fixture', version: '1' })
  server.registerTool('read', { inputSchema: z.object({}) }, async () => ({ content: [] }))
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const serving = serveStdio(() => server, { transport: serverTransport })
  transportFactory.mockReturnValue(clientTransport)
  const config = { transport: 'stdio', serverName: 'connection', command: 'in-memory',
    args: [], env: {}, cwd: '', toolCallTimeoutMs: 1000, failOnStartupError: true }
  const admission = vi.fn(() => [])
  const connection = startConnection(ctx, config,
    resolveReconnectPolicy({ enabled: false }, 'test'), admission)
  onTestFinished(async () => {
    await connection.dispose(); await serving.close(); await runtime.dispose(); await prompt.dispose()
  })
  expect(await connection.ready).toEqual({})
  expect(admission).toHaveBeenCalledTimes(1)
  expect(ctx.tools.schemas()).toEqual([])
})

it('rejects a server-identity mismatch before exposing tools', async () => {
  const f = await setup('2')
  await expect(f.sync({ admitGeneration(s) {
    if (s.serverInfo?.version !== '1') throw new Error('SERVER_IDENTITY_MISMATCH')
    return []
  } })).rejects.toThrow('SERVER_IDENTITY_MISMATCH')
  expect(f.ctx.tools.schemas()).toEqual([]); expect(f.counts.read).toBe(0)
})
it('rejects public display names supplied as raw grant identities', async () => {
  const f = await setup()
  await expect(f.sync({ admitGeneration: () => [{
    rawName: publicToolName('fixture', 'read.memo'), allow: () => true,
  }] })).rejects.toThrow('MCP_GENERATION_ADMISSION_INVALID')
  expect(f.ctx.tools.schemas()).toEqual([])
})
it('captures the selected guard instead of a mutable grant-property lookup', async () => {
  const f = await setup(); f.state.allowed = false
  const grant = { rawName: 'read.memo', allow: () => f.state.allowed }
  await f.sync({ admitGeneration: () => [grant] })
  grant.allow = () => true
  expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
})
it('rejects a generation that disconnects while discovery is suspended', async () => {
  const f = await setup(); await f.sync()
  let release, enter
  const held = new Promise(r => { release = r }), entered = new Promise(r => { enter = r })
  const listed = await f.client.listTools(undefined, { cacheMode: 'refresh' })
  f.server.server.setRequestHandler('tools/list', async () => { enter(); await held; return listed })
  const pending = f.sync()
  try { await entered; f.state.current = false }
  finally { release() }
  await expect(pending).rejects.toThrow('MCP_GENERATION_NOT_CURRENT')
  expect(f.ctx.tools.schemas()).toEqual([]); expect(f.counts.read).toBe(0)
})
it('checks currentness again after the admission callback', async () => {
  const f = await setup()
  await expect(f.sync({ admitGeneration: s => {
    f.state.current = false
    return [{ rawName: s.tools[0].name, allow: () => true }]
  } })).rejects.toThrow('MCP_GENERATION_NOT_CURRENT')
  expect(f.ctx.tools.schemas()).toEqual([])
})
it('lets the owner reject changed output schemas from real tools/list', async () => {
  const f = await setup()
  const original = await f.client.listTools(undefined, { cacheMode: 'refresh' })
  const expected = JSON.stringify(original.tools)
  const admission = s => {
    if (JSON.stringify(s.tools) !== expected) throw new Error('FULL_SCHEMA_DRIFT')
    return [{ rawName: 'read.memo', allow: () => true }]
  }
  await f.sync({ admitGeneration: admission })
  const changed = structuredClone(original)
  changed.tools.find(t => t.name === 'read.memo').outputSchema = { type: 'object', properties: { extra: { type: 'string' } } }
  f.server.server.setRequestHandler('tools/list', async () => changed)
  await expect(f.sync({ admitGeneration: admission })).rejects.toThrow('FULL_SCHEMA_DRIFT')
  expect(f.ctx.tools.schemas()).toEqual([]); expect(f.counts.read).toBe(0)
})
it('allows an explicitly empty selection without inventing a required capability', async () => {
  const f = await setup(); await f.sync({ admitGeneration: () => [] })
  expect(f.ctx.tools.schemas()).toEqual([])
  expect((await f.call()).isError).toBe(true); expect(f.counts.read).toBe(0)
})
it('uses the same admission hook on actual SDK tool-list notifications', async () => {
  const ctx = new Context()
  const prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const server = new McpServer({ name: 'notification-fixture', version: '1' })
  let calls = 0, allow = true
  server.registerTool('read', { inputSchema: z.object({}) }, async () => {
    calls++; return { content: [] }
  })
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const serving = serveStdio(() => server, { transport: serverTransport })
  transportFactory.mockReturnValue(clientTransport)
  const admission = vi.fn(s => allow ? s.tools.filter(t => t.name === 'read')
    .map(t => ({ rawName: t.name, allow: () => allow })) : [])
  const config = { transport: 'stdio', serverName: 'notify', command: 'in-memory',
    args: [], env: {}, cwd: '', toolCallTimeoutMs: 1000, failOnStartupError: true }
  const connection = startConnection(ctx, config,
    resolveReconnectPolicy({ enabled: false }, 'test'), admission)
  onTestFinished(async () => {
    await connection.dispose(); await serving.close(); await runtime.dispose(); await prompt.dispose()
  })
  expect(await connection.ready).toEqual({})
  const execute = () => ctx.tools.execute({ name: 'mcp__notify__read', arguments: {},
    callId: ToolCallId(randomUUID()), signal: new AbortController().signal })
  expect((await execute()).isError).toBe(false); expect(calls).toBe(1)
  allow = false
  server.registerTool('extra', { inputSchema: z.object({}) }, async () => ({ content: [] }))
  await vi.waitFor(() => { expect(admission.mock.calls.length).toBeGreaterThanOrEqual(2) })
  expect(ctx.tools.schemas()).toEqual([])
  expect((await execute()).isError).toBe(true); expect(calls).toBe(1)
  observations.push({ journey: 'connection-notification-readmission',
    generationsObserved: admission.mock.calls.length, calls, exposedAfterRevocation: ctx.tools.schemas() })
})
