/**
 * Uses the real adopted Cordis, AgentLoop, AgentRegistry, Session and Tools.
 * Provider tokens and Fabric responses are deterministic fixtures, not live
 * remote execution, installed enrollment or production acceptance evidence.
 */
import { expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime, { createUserMessage, ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { MockAdapter, textResponse, toolCallResponse } from 'mmx-native-mock-adapter'
import { installFabricTool } from './native.ts'
import { TOOL } from './core.ts'
import { fixture, submitArgs } from './test-fixture.ts'

async function mount(adapter: InstanceType<typeof MockAdapter>) {
  const ctx = new Context()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, { personaPrefix: 'Native Fabric integration fixture.' })
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], adapter)
  return ctx
}
function idle(ctx: Context, parent: Agent) {
  return new Promise<void>(resolve => {
    const dispose = ctx.on('agent/status', ({ agent, status }) => {
      if (agent === parent && status === 'idle') { dispose(); resolve() }
    })
  })
}
function run(ctx: Context, agent: Agent, signal = new AbortController().signal) {
  return ctx.tools.execute({
    callId: ToolCallId('native-invoke'), name: TOOL,
    arguments: { action: 'status', task_key: submitArgs.task_key }, agent, signal,
  })
}

it('drives the actual native parent loop through submit, verified result and retained native history', async () => {
  const adapter = new MockAdapter([
    toolCallResponse('delegate-1', TOOL, submitArgs),
    toolCallResponse('result-1', TOOL, { action: 'result', task_key: submitArgs.task_key }),
    textResponse('I consumed the verified company-job result.'),
  ])
  const ctx = await mount(adapter)
  let f!: ReturnType<typeof fixture<Agent>>
  try {
    const parent = await ctx.agents.create({
      sessionId: SessionId('native-fabric-parent'), agentOptions: { provider: 'mock', model: 'mock' },
      setup: (_ctx, agent) => {
        f = fixture(agent)
        let submitted = false
        vi.mocked(f.host.authorizeNewRun).mockResolvedValueOnce(true).mockResolvedValue(false)
        vi.mocked(f.host.callTool).mockImplementation(async name => {
          if (name === 'fabric_status') return f.status(submitted ? 'TERMINAL' : 'NOT_FOUND')
          if (name === 'fabric_request') { submitted = true; return f.receipt() }
          return f.result()
        })
        installFabricTool(agent, f.host)
      },
    })
    const other = await ctx.agents.create({
      sessionId: SessionId('unrelated-native-agent'), agentOptions: { provider: 'mock', model: 'mock' },
    })
    expect(ctx.tools.schemas(parent.agent).some(t => t.name === TOOL)).toBe(true)
    expect(ctx.tools.schemas(other.agent).some(t => t.name === TOOL)).toBe(false)
    const done = idle(ctx, parent.agent)
    parent.agent.followup(createUserMessage({
      content: [{ type: 'text', text: 'Use the delegated company-job fixture.' }],
      source: { kind: 'user' },
    }))
    await done
    expect(adapter.requests).toHaveLength(3)
    expect(JSON.stringify(adapter.requests.at(-1))).toContain(f.responseText)
    const history = JSON.stringify(parent.agent.session.snapshotEvents())
    expect(history).toContain(f.runId)
    expect(history).toContain('result_transfer_verified')
    expect(history).toContain(f.responseText)
    expect(JSON.stringify(other.agent.session.snapshotEvents())).not.toContain(f.responseText)
    expect(vi.mocked(f.host.callTool).mock.calls.map(([name]) => name))
      .toEqual(['fabric_status', 'fabric_request', 'fabric_status', 'fabric_result', 'fabric_status'])
    expect(f.host.authorizeSession).toHaveBeenCalledWith(parent.agent)
    await parent.dispose()
    expect(ctx.tools.schemas(parent.agent).some(t => t.name === TOOL)).toBe(false)
    expect(ctx.agents.get(parent.agent.id)).toBeUndefined()
    await other.dispose()
  } finally { await ctx.fiber.dispose() }
})

it('enforces native scope visibility and removes the exact scoped registration on disposal', async () => {
  const ctx = await mount(new MockAdapter([]))
  try {
    const a = await ctx.agents.create({ sessionId: SessionId('scope-owner') })
    const b = await ctx.agents.create({ sessionId: SessionId('scope-stranger') })
    const f = fixture(a.agent)
    const dispose = installFabricTool(a.agent, f.host)
    expect(ctx.tools.schemas().some(t => t.name === TOOL)).toBe(false)
    const foreign = await run(ctx, b.agent)
    expect(foreign.isError).toBe(true)
    expect(f.host.callTool).not.toHaveBeenCalled()
    const own = await run(ctx, a.agent)
    expect(own.isError).toBe(false)
    if (!own.isError) expect(own.value).toMatchObject({ state: 'TERMINAL', worker_started: false })
    dispose()
    expect((await run(ctx, a.agent)).isError).toBe(true)
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  } finally { await ctx.fiber.dispose() }
})

it('withdraws in-flight result access on native plugin disposal without cancelling a company job', async () => {
  const ctx = await mount(new MockAdapter([]))
  const entered = Promise.withResolvers<void>(), pending = Promise.withResolvers<unknown>()
  try {
    const a = await ctx.agents.create({ sessionId: SessionId('scope-dispose-during-read') })
    const f = fixture(a.agent)
    vi.mocked(f.host.callTool).mockImplementation(async () => {
      entered.resolve()
      return pending.promise
    })
    const dispose = installFabricTool(a.agent, f.host)
    const reading = run(ctx, a.agent)
    await entered.promise
    dispose()
    pending.resolve(f.status())
    const result = await reading
    expect(result.isError).toBe(false)
    if (!result.isError) expect(result.value).toMatchObject({
      reason: 'NATIVE_RESPONSE_WITHHELD', remote_cancellation_requested: false,
    })
    expect(f.host.callTool).toHaveBeenCalledTimes(1)
  } finally {
    pending.resolve({})
    await ctx.fiber.dispose()
  }
})

it('rejects a global/forged context instead of registering a global tool', async () => {
  const ctx = await mount(new MockAdapter([]))
  try {
    const forged = { id: 'forged', ctx } as unknown as Agent
    expect(() => installFabricTool(forged, fixture(forged).host))
      .toThrow('FABRIC_EXACT_NATIVE_AGENT_SCOPE_REQUIRED')
    expect(ctx.tools.schemas().some(t => t.name === TOOL)).toBe(false)
  } finally { await ctx.fiber.dispose() }
})

it('recovers an interrupted native tool call on the same Fabric run without another submission', async () => {
  const ctx = await mount(new MockAdapter([]))
  const entered = Promise.withResolvers<void>(), pending = Promise.withResolvers<unknown>()
  try {
    const a = await ctx.agents.create({ sessionId: SessionId('native-interrupted-submit') })
    const f = fixture(a.agent), abort = new AbortController()
    let submitted = false
    vi.mocked(f.host.authorizeNewRun).mockResolvedValueOnce(true).mockResolvedValue(false)
    vi.mocked(f.host.callTool).mockImplementation(async name => {
      if (name === 'fabric_status') return f.status(submitted ? 'TERMINAL' : 'NOT_FOUND')
      if (name === 'fabric_request') {
        submitted = true
        entered.resolve()
        return pending.promise
      }
      return f.result()
    })
    installFabricTool(a.agent, f.host)
    const sending = ctx.tools.execute({
      callId: ToolCallId('interrupted-send'), name: TOOL, arguments: submitArgs,
      agent: a.agent, signal: abort.signal,
    })
    await entered.promise
    abort.abort()
    pending.resolve(f.receipt())
    expect((await sending).isError).toBe(true)
    const recovered = await run(ctx, a.agent)
    expect(recovered.isError).toBe(false)
    if (!recovered.isError) expect(recovered.value).toMatchObject({ state: 'TERMINAL', run_id: f.runId })
    expect(vi.mocked(f.host.callTool).mock.calls.filter(([name]) => name === 'fabric_request')).toHaveLength(1)
  } finally {
    pending.resolve({})
    await ctx.fiber.dispose()
  }
})
