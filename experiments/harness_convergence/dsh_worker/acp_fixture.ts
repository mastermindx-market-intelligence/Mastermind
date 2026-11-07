/**
 * N1 provider-free DSH ACP worker fixture.
 *
 * This process exists only to prove the existing Mastermind ACP Worker v1 seam
 * against the pinned DSH ACP server. It owns no company lifecycle, provider
 * credential, route, retry policy, or durable session store.
 */
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime, {
  LlmAdapter,
  ToolCallId,
  type GenerateOptions,
  type LlmResolvedModelInfo,
  type StreamChunk,
} from '@deepseek-ai/dsh-llm'
import SessionStore, {
  SessionLogOffset,
  type SessionEvent,
  type SessionHeader,
  type SessionId,
} from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import SessionPersistence, {
  SessionPersistenceRevision,
  type SessionAccess,
  type SessionHandle,
  type SessionPersistenceCreateOptions,
  type SessionPersistenceListOptions,
  type SessionPersistenceOpenOptions,
  type SessionPersistenceSnapshot,
  type SessionPersistenceStatOptions,
} from '@deepseek-ai/dsh-session-persistence'
import * as AcpPlugin from '@deepseek-ai/dsh-acp'

const PROVIDER = 'fixture'
const MODEL = 'fixture-model'
const BEHAVIOR = process.env.MMX_N1_BEHAVIOR ?? 'ok'
if (!['ok', 'hang', 'invalid-result', 'tool-call'].includes(BEHAVIOR)) {
  throw new Error('N1_BEHAVIOR_REFUSED')
}

type Stored = {
  readonly header: SessionHeader
  readonly inheritedEventCount: SessionLogOffset
  readonly events: SessionEvent[]
  revision: number
  writerOpen: boolean
}

class EphemeralPersistence extends SessionPersistence {
  private readonly rows = new Map<SessionId, Stored>()

  async create(
    header: SessionHeader,
    options: SessionPersistenceCreateOptions = {},
  ): Promise<SessionHandle> {
    options.signal?.throwIfAborted()
    if (this.rows.has(header.id)) throw new Error('N1_SESSION_ALREADY_EXISTS')
    const stored: Stored = {
      header: structuredClone(header),
      inheritedEventCount: options.inheritedEventCount ?? SessionLogOffset(0),
      events: [],
      revision: 0,
      writerOpen: true,
    }
    this.rows.set(header.id, stored)
    return this.handle(stored, 'write')
  }

  async open(
    id: SessionId,
    access: SessionAccess,
    options: SessionPersistenceOpenOptions = {},
  ): Promise<SessionHandle> {
    options.signal?.throwIfAborted()
    const stored = this.rows.get(id)
    if (stored === undefined) throw new Error('N1_SESSION_NOT_FOUND')
    if (access === 'write') throw new Error('N1_RESUME_DISABLED')
    return this.handle(stored, 'read')
  }

  async flush(): Promise<void> {}

  stat(
    id: SessionId,
    options: SessionPersistenceStatOptions = {},
  ): Promise<SessionPersistenceSnapshot | undefined> {
    options.signal?.throwIfAborted()
    const stored = this.rows.get(id)
    return Promise.resolve(stored === undefined ? undefined : this.snapshot(stored))
  }

  list(
    options: SessionPersistenceListOptions = {},
  ): Promise<readonly SessionPersistenceSnapshot[]> {
    options.signal?.throwIfAborted()
    return Promise.resolve([...this.rows.values()].map(row => this.snapshot(row)))
  }

  private snapshot(stored: Stored): SessionPersistenceSnapshot {
    return {
      header: structuredClone(stored.header),
      revision: SessionPersistenceRevision('n1:' + stored.header.id + ':' + stored.revision),
      eventCount: stored.events.length,
    }
  }

  private handle(stored: Stored, access: SessionAccess): SessionHandle {
    let closed = false
    let floor = 0
    const ensure = () => {
      if (closed) throw new Error('N1_SESSION_HANDLE_CLOSED')
    }
    const handle: SessionHandle = {
      id: stored.header.id,
      header: stored.header,
      inheritedEventCount: stored.inheritedEventCount,
      access,
      async read(offset = 0, length = Number.MAX_SAFE_INTEGER) {
        ensure()
        const start = Math.max(floor, offset)
        const events = stored.events
          .slice(start, start + length)
          .map(event => structuredClone(event))
        floor = Math.max(floor, start + events.length)
        return { eventState: 'detached' as const, events }
      },
      async append(events: readonly SessionEvent[]) {
        ensure()
        if (access !== 'write' || !stored.writerOpen) throw new Error('N1_SESSION_READ_ONLY')
        for (const [index, event] of events.entries()) {
          if (event.seq !== stored.events.length + index) throw new Error('N1_SESSION_NONCONTIGUOUS')
        }
        stored.events.push(...events.map(event => structuredClone(event)))
        stored.revision += 1
      },
      async flush() {
        ensure()
        if (access !== 'write') throw new Error('N1_SESSION_READ_ONLY')
      },
      async close() {
        if (closed) return
        closed = true
        if (access === 'write') stored.writerOpen = false
      },
      async [Symbol.asyncDispose]() {
        await handle.close()
      },
    }
    return handle
  }
}

class FixtureAdapter extends LlmAdapter {
  calls = 0

  override providerInfo(provider: string) {
    if (provider !== PROVIDER) throw new Error('N1_PROVIDER_MISMATCH')
    return { id: PROVIDER, name: 'N1 fixture provider' }
  }

  override listModels(provider: string) {
    return Promise.resolve(provider === PROVIDER
      ? [{ provider: PROVIDER, id: MODEL, name: 'N1 fixture model', inputModalities: ['text'] as const }]
      : [])
  }

  override resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
    if (provider !== PROVIDER || model !== MODEL) throw new Error('N1_MODEL_MISMATCH')
    return Promise.resolve({
      provider,
      id: model,
      name: model,
      inputModalities: ['text'],
      context: { contextWindow: 4096 },
    })
  }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    if (options.provider !== PROVIDER || options.model !== MODEL) throw new Error('N1_MODEL_MISMATCH')
    this.calls += 1
    if (BEHAVIOR !== 'tool-call' && this.calls !== 1) throw new Error('N1_MULTIPLE_MODEL_CALLS')
    if (BEHAVIOR === 'hang') {
      process.stderr.write('N1_PROMPT_IN_FLIGHT\n')
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'text-delta', index: 0, text: 'partial' }
      await new Promise<void>((_resolve, reject) => {
        if (options.signal?.aborted) {
          reject(new Error('N1_ABORTED'))
          return
        }
        options.signal?.addEventListener('abort', () => reject(new Error('N1_ABORTED')), { once: true })
      })
      return
    }
    if (BEHAVIOR === 'tool-call' && this.calls === 1) {
      const id = ToolCallId('n1-tool-call')
      const args = '{}'
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'tool-call-delta', index: 0, id, name: 'n1_fixture_read', argumentsDelta: args }
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'n1_fixture_read', arguments: args } }
      yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1 } }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
      return
    }
    const value = BEHAVIOR === 'invalid-result'
      ? { answer: 7, fixture_model_calls: this.calls }
      : { answer: 'n1-dsh-acp', fixture_model_calls: this.calls }
    const text = JSON.stringify(value)
    yield { type: 'block-start', index: 0, blockType: 'text' }
    for (const char of text) yield { type: 'text-delta', index: 0, text: char }
    yield { type: 'block-end', index: 0, block: { type: 'text', text } }
    yield { type: 'usage', usage: { inputTokens: 1, outputTokens: text.length } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

async function main(): Promise<void> {
  const ctx = new Context()
  const fixture = new FixtureAdapter()
  try {
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(SessionStore)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)
    if (BEHAVIOR === 'tool-call') {
      ctx.tools.register({
        name: 'n1_fixture_read',
        description: 'In-memory N1 negative-control read tool.',
        parameters: { type: 'object', additionalProperties: false },
        execute: async () => 'n1-tool-result',
        output: {
          schema: { type: 'string' },
          render: (_args: unknown, value: unknown) => [{ type: 'text' as const, text: String(value) }],
        },
      })
    }
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(EphemeralPersistence)
    await ctx.plugin(AgentLoop, { agents: [] })
    ctx.llm.registerAdapter([PROVIDER], fixture)
    await ctx.plugin({
      name: 'n1-dsh-acp',
      inject: [...AcpPlugin.inject],
      apply(inner: Context) {
        AcpPlugin.apply(inner, { provider: PROVIDER, model: MODEL })
      },
    })
    await new Promise<void>((resolve, reject) => {
      process.stdin.once('end', resolve)
      process.stdin.once('error', reject)
      process.stdin.resume()
    })
  } finally {
    await ctx.fiber.dispose()
  }
}

main().catch(() => {
  process.stderr.write('N1_DSH_ACP_FIXTURE_FAILED\n')
  process.exitCode = 70
})
