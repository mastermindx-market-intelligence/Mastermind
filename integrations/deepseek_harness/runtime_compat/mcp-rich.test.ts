import {it, expect, onTestFinished, vi} from 'vitest'
import {Context} from '@deepseek-ai/cordis'
import {InMemoryTransport} from '@modelcontextprotocol/client'
import {McpServer, ProtocolError} from '@modelcontextprotocol/server'
import {serveStdio} from '@modelcontextprotocol/server/stdio'
import {z} from 'zod'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import {ToolCallId} from '@deepseek-ai/dsh-llm'
import {startConnection, resolveReconnectPolicy} from 'mmx-mcp-connection'
const {transportFactory} = vi.hoisted(() => ({transportFactory: vi.fn()}))
vi.mock('mmx-mcp-transport', () => ({createTransport: transportFactory}))

async function setup(kind: 'image' | 'header') {
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime, {strictDispatchBinding: true})
  let calls = 0
  const serving: {close(): Promise<void>}[] = []
  transportFactory.mockImplementation(() => {
    const server = new McpServer({name: 'rich-fixture', version: '1'})
    server.registerTool('read', {inputSchema: z.object({})}, async () => {
      calls++
      return {content: [{type: 'image', mimeType: 'image/png', data: 'AQ=='}]}
    })
    if (kind === 'header') server.server.setRequestHandler('tools/call', async () => {
      calls++
      // Exact HEADER_MISMATCH_ERROR_CODE from the pinned SDK2.2 source.
      throw new ProtocolError(-32020, 'fixture schema generation mismatch')
    })
    const [client, peer] = InMemoryTransport.createLinkedPair()
    serving.push(serveStdio(() => server, {transport: peer}))
    return client
  })
  const connection = startConnection(ctx, {
    transport: 'stdio', serverName: 'rich', command: 'fixture', args: [], env: {}, cwd: '',
    toolCallTimeoutMs: 1000, failOnStartupError: true,
  }, resolveReconnectPolicy({enabled: false}, 'fixture'),
  snapshot => snapshot.tools.map(tool => ({rawName: tool.name, allow: () => true})))
  onTestFinished(async () => {
    await connection.dispose()
    for (const server of serving) await server.close()
    await ctx.fiber.dispose()
  })
  expect(await connection.ready).toEqual({})
  return {ctx, calls: () => calls}
}
it('rejects rich results before attachment or model-route access', async () => {
  const f = await setup('image')
  const get = vi.spyOn(f.ctx, 'get')
  const result = await f.ctx.tools.execute({
    name: 'mcp__rich__read', arguments: {}, callId: ToolCallId('rich-call'),
    signal: new AbortController().signal,
  })
  expect(result.isError).toBe(true)
  expect(JSON.stringify(result)).toContain('MCP_RICH_RESULT_NOT_ADMITTED')
  expect(get.mock.calls.some(([name]) => name === 'attachments' || name === 'llm')).toBe(false)
  expect(f.calls()).toBe(1)
})
it('does not replay a mismatched-header call through the real SDK', async () => {
  const f = await setup('header')
  const result = await f.ctx.tools.execute({
    name: 'mcp__rich__read', arguments: {}, callId: ToolCallId('header-call'),
    signal: new AbortController().signal,
  })
  expect(result.isError).toBe(true)
  expect(f.calls()).toBe(1)
})
