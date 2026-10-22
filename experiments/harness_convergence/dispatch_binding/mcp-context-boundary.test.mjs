import { it, expect, onTestFinished, vi } from 'vitest'
import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { Context } from '@deepseek-ai/cordis'
import { InMemoryTransport } from '@modelcontextprotocol/client'
import { McpServer } from '@modelcontextprotocol/server'
import { serveStdio } from '@modelcontextprotocol/server/stdio'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { startConnection, resolveReconnectPolicy } from 'mmx-mcp-connection'
const { transportFactory } = vi.hoisted(() => ({ transportFactory: vi.fn() }))
vi.mock('mmx-mcp-transport', () => ({ createTransport: transportFactory }))

async function setup(governed = true, select = s => s.tools.map(t => ({ rawName: t.name, allow: () => true }))) {
  const ctx = new Context()
  const prompt = await ctx.plugin(SystemPrompt)
  const runtime = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const counts = { list: 0, read: 0, templates: 0, tool: 0 }
  const server = new McpServer({ name: 'context-fixture', version: '1' }, {
    instructions: 'Fixture instructions that require separate context admission.',
  })
  server.registerTool('read', { inputSchema: z.object({}) }, async () => {
    counts.tool++; return { content: [{ type: 'text', text: 'permitted-tool' }] }
  })
  server.registerResource('memo', 'memo://value', {}, async () => {
    counts.read++; return { contents: [{ uri: 'memo://value', text: 'resource-content' }] }
  })
  server.server.setRequestHandler('resources/list', async () => {
    counts.list++; return { resources: [{ name: 'memo', uri: 'memo://value' }] }
  })
  server.server.setRequestHandler('resources/templates/list', async () => {
    counts.templates++; return { resourceTemplates: [] }
  })
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const serving = serveStdio(() => server, { transport: serverTransport })
  transportFactory.mockReturnValue(clientTransport)
  const config = { transport: 'stdio', serverName: 'context', command: 'in-memory',
    args: [], env: {}, cwd: '', toolCallTimeoutMs: 1000, failOnStartupError: true }
  const connection = startConnection(ctx, config,
    resolveReconnectPolicy({ enabled: false }, 'test'), governed ? select : undefined)
  onTestFinished(async () => {
    await connection.dispose(); await serving.close(); await runtime.dispose(); await prompt.dispose()
  })
  expect(await connection.ready).toEqual({})
  return { ctx, connection, counts, exec: { signal: new AbortController().signal } }
}

it('tool admission does not publish server instructions', async () => {
  const f = await setup()
  expect(f.connection.instructions()).toBe('')
})
for (const request of [
  { method: 'resources/list' }, { method: 'resources/templates/list' },
  { method: 'resources/read', uri: 'memo://value' },
]) {
  it(`tool admission does not authorize ${request.method}`, async () => {
    const f = await setup()
    await expect(f.connection.resources.request(request, f.exec)).rejects.toThrow('MCP_RESOURCE_NOT_ADMITTED')
    expect(f.counts).toEqual({ list: 0, read: 0, templates: 0, tool: 0 })
  })
}
it('tool-only context restriction preserves a permitted real tool call', async () => {
  const f = await setup()
  const result = await f.ctx.tools.execute({ name: 'mcp__context__read', arguments: {},
    callId: ToolCallId(randomUUID()), signal: f.exec.signal })
  expect(result.isError).toBe(false)
  expect(result.value.content).toEqual([{ type: 'text', text: 'permitted-tool' }])
  expect(f.counts).toEqual({ list: 0, read: 0, templates: 0, tool: 1 })
})
it('empty admitted tool set does not expose other context channels', async () => {
  const f = await setup(true, () => [])
  expect(f.ctx.tools.schemas()).toEqual([])
  expect(f.connection.instructions()).toBe('')
  await expect(f.connection.resources.request({ method: 'resources/list' }, f.exec))
    .rejects.toThrow('MCP_RESOURCE_NOT_ADMITTED')
  expect(f.counts.list).toBe(0)
})
it('legacy context publication and resource requests stay unchanged', async () => {
  const f = await setup(false)
  expect(f.connection.instructions()).toContain('Fixture instructions')
  const listed = await f.connection.resources.request({ method: 'resources/list' }, f.exec)
  expect(listed.resources).toHaveLength(1)
  const read = await f.connection.resources.request({ method: 'resources/read', uri: 'memo://value' }, f.exec)
  expect(read.contents[0].text).toBe('resource-content')
  const templates = await f.connection.resources.request({ method: 'resources/templates/list' }, f.exec)
  expect(templates.resourceTemplates).toEqual([])
  expect(f.counts).toEqual({ list: 1, read: 1, templates: 1, tool: 0 })
})
