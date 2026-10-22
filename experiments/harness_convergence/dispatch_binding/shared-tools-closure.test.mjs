import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime, { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId, SessionLogOffset } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import ExternalAgentLoop from '@deepseek-ai/dsh-agent-loop'
import SessionPersistence, { SessionPersistenceRevision } from '@deepseek-ai/dsh-session-persistence'

const here = new URL('.', import.meta.url)
const cache = new URL('./.cache/', here)
const build = JSON.parse(readFileSync(new URL('./profile-build-result.json', cache), 'utf8'))
const profile = await import(new URL(build.artifact, cache))

class EphemeralPersistence extends SessionPersistence {
  rows = new Map()

  async create(header, options = {}) {
    options.signal?.throwIfAborted()
    if (this.rows.has(header.id)) throw new Error('SESSION_ALREADY_EXISTS')
    const stored = {
      header: structuredClone(header),
      inheritedEventCount: options.inheritedEventCount ?? SessionLogOffset(0),
      events: [], revision: 0, writerOpen: true,
    }
    this.rows.set(header.id, stored)
    return this.handle(stored, 'write')
  }

  async open(id, access, options = {}) {
    options.signal?.throwIfAborted()
    const stored = this.rows.get(id)
    if (stored === undefined) throw new Error('SESSION_NOT_FOUND')
    if (access === 'write') throw new Error('RESUME_DISABLED')
    return this.handle(stored, 'read')
  }

  async flush() {}

  stat(id, options = {}) {
    options.signal?.throwIfAborted()
    const stored = this.rows.get(id)
    return Promise.resolve(stored === undefined ? undefined : this.snapshot(stored))
  }

  list(options = {}) {
    options.signal?.throwIfAborted()
    return Promise.resolve([...this.rows.values()].map(row => this.snapshot(row)))
  }

  snapshot(stored) {
    return {
      header: structuredClone(stored.header),
      revision: SessionPersistenceRevision(`shared:${stored.header.id}:${stored.revision}`),
      eventCount: stored.events.length,
    }
  }

  handle(stored, access) {
    let closed = false
    let floor = 0
    const ensure = () => { if (closed) throw new Error('SESSION_HANDLE_CLOSED') }
    const handle = {
      id: stored.header.id,
      header: stored.header,
      inheritedEventCount: stored.inheritedEventCount,
      access,
      async read(offset = 0, length = Number.MAX_SAFE_INTEGER) {
        ensure()
        const start = Math.max(floor, offset)
        const events = stored.events.slice(start, start + length).map(event => structuredClone(event))
        floor = Math.max(floor, start + events.length)
        return { eventState: 'detached', events }
      },
      async append(events) {
        ensure()
        if (access !== 'write' || !stored.writerOpen) throw new Error('SESSION_READ_ONLY')
        for (const [index, event] of events.entries()) {
          if (event.seq !== stored.events.length + index) throw new Error('SESSION_NONCONTIGUOUS')
        }
        stored.events.push(...events.map(event => structuredClone(event)))
        stored.revision += 1
      },
      async flush() { ensure(); if (access !== 'write') throw new Error('SESSION_READ_ONLY') },
      async close() {
        if (closed) return
        closed = true
        if (access === 'write') stored.writerOpen = false
      },
      async [Symbol.asyncDispose]() { await handle.close() },
    }
    return handle
  }
}

function toolResult(messages, id) {
  return messages.findLast(row => row.role === 'tool' && row.toolCallId === id)
}

class FixtureAdapter extends LlmAdapter {
  calls = 0
  providerInfo(provider) { return { id: provider, name: 'Fixture' } }
  async listModels(provider) {
    return provider === 'fixture'
      ? [{ provider, id: 'fixture-model', name: 'Fixture', inputModalities: ['text'] }]
      : []
  }
  async resolveModel(provider, model) {
    return { provider, id: model, name: model, inputModalities: ['text'], context: { contextWindow: 8192 } }
  }
  async *stream(options) {
    this.calls += 1
    if (this.calls === 1) {
      const id = ToolCallId('shared-scheduler-call')
      const argumentsText = '{}'
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'tool-call-delta', index: 0, id, name: 'shared_scheduler_probe', argumentsDelta: argumentsText }
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'shared_scheduler_probe', arguments: argumentsText } }
      yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1 } }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
      return
    }
    const committed = toolResult(options.messages, 'shared-scheduler-call')
    assert.ok(committed, 'scheduled tool result was not committed')
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text: 'done' }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'done' } }
    yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

test('profile ToolRuntime and exported AgentLoop share one scheduled-tool owner', { timeout: 15_000 }, async () => {
  assert.equal(typeof profile.ToolRuntime, 'function')
  const AgentLoop = profile.AgentLoop ?? ExternalAgentLoop
  const ctx = new Context()
  let bodyCalls = 0
  const adapter = new FixtureAdapter()
  let handle
  try {
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(SessionStore)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(profile.ToolRuntime, { strictDispatchBinding: true })
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(EphemeralPersistence)
    await ctx.plugin(AgentLoop, { agents: [] })
    ctx.llm.registerAdapter(['fixture'], adapter)
    handle = await ctx.agents.create({
      sessionId: SessionId('shared-tools-closure'),
      agentOptions: { provider: 'fixture', model: 'fixture-model' },
      setup: async agentCtx => {
        agentCtx.tools.register({
          name: 'shared_scheduler_probe',
          description: 'Prove one physical tool scheduler is used by AgentLoop and ToolRuntime',
          parameters: {},
          output: {
            schema: { type: 'string' },
            render: (_args, value) => [{ type: 'text', text: value }],
          },
          async execute() { bodyCalls += 1; return 'scheduled' },
        })
      },
    })
    handle.agent.followup({ content: [{ type: 'text', text: 'run the probe' }], source: { kind: 'user' } })
    await handle.agent.whenIdle()
    assert.equal(bodyCalls, 1, 'the actual scheduled tool body must execute exactly once')
    assert.equal(adapter.calls, 2, 'the model must observe the committed tool result before finishing')
  } finally {
    if (handle) await handle.dispose()
    await ctx.fiber.dispose()
  }
})
