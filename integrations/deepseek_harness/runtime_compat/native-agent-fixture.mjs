/** Real full-app donor + native ACP + workspace MCP; deterministic test model only. */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime, { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import EphemeralPersistence from './fixture-persistence.mjs'
import * as JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import * as Acp from '@deepseek-ai/dsh-acp'
import { createNativeDshAgentAdmission } from '../../acp_worker/dsh_native_agent.mjs'

const sha = bytes => createHash('sha256').update(bytes).digest('hex')
const input = process.env.MMX_FULLAPP_FIXTURE_INPUT
assert.ok(input?.startsWith('/'))
const descriptor = Number(process.env.MMX_ACP_ATTEST_FD)
delete process.env.MMX_ACP_ATTEST_FD
const projectionBytes = readFileSync(input + '/projection.json')
const projection = JSON.parse(projectionBytes)
const config = JSON.parse(readFileSync(input + '/config.json'))
const expectedTools = JSON.parse(readFileSync(input + '/tools.json'))
const mode = process.env.MMX_FULLAPP_FIXTURE_MODE ?? 'ok'
assert.ok(['ok', 'revoked', 'owner-revoked', 'hang', 'wrong-tool-contract', 'durable', 'abort-before-ready'].includes(mode))
const state = { ready: false, allowed: true, attempt: undefined, calls: 0 }
const owner = new AbortController()

function actualResult(options, id) {
  const message = options.messages.findLast(row => row.role === 'tool' && row.toolCallId === id)
  assert.ok(message, 'native loop did not commit the actual tool result')
  if (message.isError) return { error: true }
  let value = JSON.parse(message.content.filter(row => row.type === 'text').map(row => row.text).join(''))
  if (value.content) value = JSON.parse(value.content[0].text)
  assert.equal(value.schema, 'mastermind.acp_workspace_read_result.v1')
  return value
}
class FixtureAdapter extends LlmAdapter {
  providerInfo(provider) { assert.equal(provider, 'fixture'); return {id: provider, name: 'Fixture'} }
  async listModels(provider) {
    return provider === 'fixture' ? [{provider, id: 'fixture-model', name: 'Fixture', inputModalities: ['text']}] : []
  }
  async resolveModel(provider, model) {
    assert.equal(provider, 'fixture'); assert.equal(model, 'fixture-model')
    return {provider, id: model, name: model, inputModalities: ['text'], context: {contextWindow: 16384}}
  }
  async *stream(options) {
    assert.ok(state.ready, 'provider began before actual MCP discovery and parent ACK')
    options.signal?.throwIfAborted()
    state.calls++
    process.stderr.write('FULLAPP_MODEL_CALL ' + state.calls + '\n')
    if (state.calls === 2 && mode === 'hang') {
      await new Promise((_resolve, reject) => {
        if (options.signal?.aborted) return reject(new Error('cancelled'))
        options.signal?.addEventListener('abort', () => reject(new Error('cancelled')), {once: true})
      })
    }
    let rawName, args
    if (state.calls === 1) {
      rawName = 'read_file'; args = {relative_path: 'memo.txt'}
    } else if (state.calls === 2) {
      const read = actualResult(options, 'native-read')
      assert.equal(read.ok, true)
      const query = read.data.content.split('\n')[0]
      assert.ok(query.length > 0)
      if (mode === 'revoked') state.allowed = false
      if (mode === 'owner-revoked') owner.abort('original owner revoked')
      rawName = 'search_text'; args = {relative_path: 'memo.txt', query}
    }
    if (rawName) {
      const id = ToolCallId(state.calls === 1 ? 'native-read' : 'native-search')
      const name = 'mcp__mastermindAcpWorkspaceRead__' + rawName
      const argumentsText = JSON.stringify(args)
      yield {type: 'block-start', index: 0, blockType: 'tool-call'}
      yield {type: 'tool-call-delta', index: 0, id, name, argumentsDelta: argumentsText}
      yield {type: 'block-end', index: 0, block: {type: 'tool-call', id, name, arguments: argumentsText}}
      yield {type: 'usage', usage: {inputTokens: 1, outputTokens: 1}}
      yield {type: 'finish', reason: {kind: 'tool-calls'}}
      return
    }
    if (mode === 'owner-revoked') {
      assert.ok(!state.agent.ctx.tools.schemas(state.agent).some(tool => tool.name === 'inherited_sentinel'),
        'revoked MCP fiber exposed an inherited tool')
      const refused = await state.agent.ctx.tools.execute({name: 'inherited_sentinel', arguments: {},
        callId: 'inherited-sentinel', signal: new AbortController().signal, agent: state.agent})
      assert.equal(refused.isError, true, 'revoked Agent executed an inherited tool')
    }
    const read = actualResult(options, 'native-read')
    const search = actualResult(options, 'native-search')
    const failed = read.error === true || search.error === true
    const env = state.attempt.env
    const text = JSON.stringify({
      schema_version: 'mastermind.executive_worker_result/v1',
      job_id: env.MMX_ACP_JOB_ID, run_id: env.MMX_ACP_RUN_ID, worker_id: env.MMX_ACP_WORKER_ID,
      status: failed ? 'FAILED' : 'COMPLETED',
      summary: JSON.stringify({read, search, model_calls: state.calls}),
      completed_steps: ['Read admitted memo bytes', ...failed ? [] : ['Searched the observed first line']],
      current_state: failed ? 'revoked dispatch refused' : 'native read/search completed',
      artifacts: [], next_actions: [], errors: failed ? ['Attempt no longer current'] : [], validations: [],
    })
    yield {type: 'block-start', index: 0, blockType: 'text'}
    if (mode === 'durable') process.stderr.write('FULLAPP_MODEL_OUTPUT_SHA256 ' + sha(text) + '\n')
    const deltas = mode === 'durable' ? [text.slice(0, 17), text.slice(17, 43), text.slice(43)] : [text]
    for (const delta of deltas) yield {type: 'text-delta', index: 0, text: delta}
    yield {type: 'block-end', index: 0, block: {type: 'text', text}}
    yield {type: 'usage', usage: {inputTokens: 1, outputTokens: text.length}}
    yield {type: 'finish', reason: {kind: 'stop'}}
  }
}
const ctx = new Context()
try {
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime, {strictDispatchBinding: true})
  ctx.tools.register({name: 'inherited_sentinel', description: 'Must remain hidden from admitted Agent',
    parameters: {}, output: {schema: {type: 'string'}, render: (_exec, value) => [{type: 'text', text: value}]},
    async execute() { process.stderr.write('INHERITED_SENTINEL_EXECUTED\n'); return 'forbidden' }})
  await ctx.plugin(AgentRegistry)
  if (mode === 'durable') await ctx.plugin(JsonlPersistence, {root: input + '/sessions'})
  else await ctx.plugin(EphemeralPersistence)
  await ctx.plugin(AgentLoop, {agents: []})
  ctx.llm.registerAdapter(['fixture'], new FixtureAdapter())
  if (mode === 'wrong-tool-contract') expectedTools[0].contract_sha256 = 'f'.repeat(64)
  await ctx.plugin(createNativeDshAgentAdmission({
    fd: descriptor, signal: owner.signal,
    projectionDigest: sha(projectionBytes),
    artifactDigest: sha(readFileSync(new URL(import.meta.url))),
    projection, config, expectedTools: [...expectedTools].reverse(),
    isCurrentBinding(binding, request) {
      const current = state.allowed && JSON.stringify(binding.source) === JSON.stringify(projection.source)
        && request.attempt?.env.MMX_ACP_JOB_ID === 'fullapp-job'
      if (current && mode === 'abort-before-ready' && request.phase === 'discovery')
        queueMicrotask(() => owner.abort('fixture abort after native discovery'))
      return current
    },
    onAdmitted({agent, attemptOverlay}) {
      state.agent = agent; state.attempt = attemptOverlay; state.ready = true
      process.stderr.write('FULLAPP_NATIVE_SESSION ' + JSON.stringify({session_id: agent.session.id}) + '\n')
    },
  }))
  await ctx.plugin(Acp, {provider: 'fixture', model: 'fixture-model'})
  await new Promise((resolve, reject) => {
    process.stdin.once('end', resolve); process.stdin.once('error', reject); process.stdin.resume()
  })
} finally {
  state.allowed = false
  owner.abort('fixture shutdown')
  await ctx.fiber.dispose()
}
