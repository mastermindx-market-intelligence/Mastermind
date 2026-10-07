import { test, after } from 'node:test'
import { writeFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { Context } from '@deepseek-ai/cordis'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
const sources = new Map([
  ['npm', '@deepseek-ai/dsh-tools'], ['1', './.cache/donor/index.ts'],
  ['pristine', './.cache/pristine/index.ts'], ['mutant', './.cache/mutant/index.ts'],
])
const selected = sources.get(process.env.MMX_DSH_SOURCE ?? 'npm')
if (!selected) throw new Error('Unknown donor test source')
const { default: ToolRuntime, TOOL_RUNTIME_SCHEDULER } = await import(selected)
const observations = {}
after(() => {
  const source = process.env.MMX_DSH_SOURCE ?? 'npm'
  // Test evidence only; leaf tool bodies remain entirely in-memory.
  writeFileSync(new URL(`./.cache/observations-${source}.json`, import.meta.url),
    JSON.stringify(observations, null, 2) + '\n')
})

// Real Cordis + real donor ToolRuntime. Only the leaf tool bodies are inert.
async function exercise(scenario, config = { strictDispatchBinding: true }) {
  const ctx = new Context()
  const promptFiber = await ctx.plugin(SystemPrompt)
  const toolFiber = await ctx.plugin(ToolRuntime, config)
  const trace = []
  const counts = { approved: 0, replacement: 0 }
  let allowed = scenario !== 'denied-before'
  let unregister
  const name = 'mcp__fixture__read'
  const definition = (label) => ({
    name, description: 'Bounded in-memory read', parameters: {},
    output: { schema: { type: 'string' }, render: (_, value) => [
      { type: 'text', text: `${label}:${value}` },
    ] },
    async execute() {
      counts[label]++
      trace.push(`${label}-body`)
      if (scenario.includes('during-body') && label === 'approved') {
        await Promise.resolve().then(() => {
          if (scenario.startsWith('remove')) { unregister(); trace.push('removed') }
          else if (scenario.startsWith('revoke')) { allowed = false; trace.push('revoked') }
          else replace()
        })
      }
      return 'original'
    },
  })
  const approved = definition('approved')
  const replacement = definition('replacement')
  function replace() {
    unregister()
    unregister = ctx.tools.register(replacement)
    trace.push('replaced')
  }
  unregister = ctx.tools.register(approved)
  const removeGuard = ctx.tools.guard(exec => {
    const admit = allowed && (scenario.endsWith('name-only')
      || ctx.tools.get(exec.name, exec.agent) === approved)
    trace.push(admit ? 'guard-allow' : 'guard-deny')
    if (scenario === 'guard-throws'
      || (scenario === 'guard-throws-late' && trace.includes('wrapper-enter'))) {
      throw new Error('guard unavailable')
    }
    return admit ? undefined : 'MASTERMIND_BINDING_REFUSED'
  })
  const controller = new AbortController()
  const removeWrapper = ctx.on('tools/execute', async (_exec, next) => {
    trace.push('wrapper-enter')
    await Promise.resolve().then(() => {
      if (scenario.startsWith('replace-before-body')) replace()
      if (scenario === 'revoke-before-body') { allowed = false; trace.push('revoked') }
      if (scenario === 'remove-before-body') { unregister(); trace.push('removed') }
      if (scenario === 'cancel-before-body') controller.abort()
    })
    const result = await next()
    if (scenario === 'replace-during-body-wrapper-value') {
      return { value: 'wrapped', content: [] }
    }
    return result
  })
  const removePost = ctx.on('tools/post-execute', async (_exec, _result, next) => {
    if (scenario.endsWith('during-body-post-value')) {
      return { kind: 'accept', value: 'rewritten' }
    }
    return next()
  })
  try {
    const input = {
      signal: controller.signal, callId: ToolCallId('dispatch-binding-probe'),
      name, arguments: {},
    }
    let result
    if (scenario === 'queued-revocation') {
      const scheduler = ctx.tools[TOOL_RUNTIME_SCHEDULER]
      const prepared = await scheduler.prepare(input)
      assert.equal(prepared.kind, 'dispatch')
      allowed = false
      trace.push('queued-grant-revoked')
      const dispatched = await scheduler.dispatch(prepared.exec)
      result = dispatched.kind === 'post-result'
        ? await scheduler.finalize(prepared.exec, dispatched.result)
        : scheduler.finish(prepared.exec, dispatched.result)
    } else {
      result = await ctx.tools.execute(input)
    }
    return { result, trace, counts }
  } finally {
    controller.abort()
    removePost(); removeWrapper(); removeGuard(); unregister()
    await toolFiber.dispose()
    await promptFiber.dispose()
  }
}

for (const scenario of ['stable', 'denied-before', 'replace-before-body',
  'revoke-before-body', 'remove-before-body', 'cancel-before-body', 'guard-throws',
  'replace-during-body', 'replace-during-body-post-value',
  'replace-during-body-wrapper-value', 'replace-before-body-name-only',
  'guard-throws-late', 'queued-revocation', 'remove-during-body-post-value',
  'revoke-during-body-post-value']) {
  test(scenario, async t => {
    const observed = await exercise(scenario)
    observations[scenario] = observed
    t.diagnostic(JSON.stringify(observed))
    assert.equal(observed.counts.replacement, 0, 'a replacement body must never run')
    if (scenario === 'stable' || scenario.includes('during-body')) {
      assert.equal(observed.counts.approved, 1)
      assert.notEqual(observed.result.isError, true)
      const value = scenario.endsWith('post-value') ? 'rewritten'
        : scenario.endsWith('wrapper-value') ? 'wrapped' : 'original'
      assert.equal(observed.result.value, value)
      assert.deepEqual(observed.result.content, [{ type: 'text', text: `approved:${value}` }],
        'result conversion must stay with the definition whose body ran')
    } else {
      assert.equal(observed.counts.approved, 0, 'no body after pre-dispatch denial')
      assert.equal(observed.result.isError, true)
      if (scenario === 'denied-before' || scenario === 'guard-throws') {
        assert.ok(!observed.trace.includes('wrapper-enter'))
      }
      if (scenario === 'replace-before-body' || scenario === 'revoke-before-body') {
        assert.ok(observed.trace.includes('guard-allow'))
        assert.ok(observed.trace.includes('wrapper-enter'))
      }
    }
  })
}

// Compatibility: the new policy is opt-in, not a hidden default migration.
for (const config of [{}, { strictDispatchBinding: false }]) {
  test(`legacy behavior retained: ${JSON.stringify(config)}`, async () => {
    const stable = await exercise('stable', config)
    assert.equal(stable.trace.filter(value => value === 'guard-allow').length, 1)
    const replaced = await exercise('replace-before-body', config)
    assert.equal(replaced.counts.replacement, 1)
    const revoked = await exercise('revoke-before-body', config)
    assert.equal(revoked.counts.approved, 1)
    for (const scenario of ['replace-during-body-post-value', 'replace-during-body-wrapper-value']) {
      const observed = await exercise(scenario, config)
      assert.equal(observed.counts.replacement, 0)
      assert.match(observed.result.content[0].text, /^replacement:/)
    }
  })
}

test('strict binding rejects own-scope shadowing during the wrapper', async () => {
  const { createScope } = await import('@deepseek-ai/dsh-scope')
  const ctx = new Context()
  const promptFiber = await ctx.plugin(SystemPrompt)
  const toolFiber = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const key = { id: 'scoped-fixture' }
  let scope
  const scopeFiber = await ctx.plugin(Object.assign(inner => {
    scope = createScope(inner, key)
  }, { inject: ['tools', 'systemPrompt'] }))
  let bodies = 0
  const definition = {
    name: 'scoped_read', description: 'Read fixture', parameters: {},
    output: { schema: { type: 'null' }, render: () => [] },
    async execute() { bodies++; return null },
  }
  const removeOriginal = ctx.tools.register(definition)
  let removeShadow = () => {}
  const removeWrapper = ctx.on('tools/execute', async (_exec, next) => {
    await Promise.resolve().then(() => {
      removeShadow = scope.ctx.tools.register({ ...definition })
    })
    return next()
  })
  try {
    const result = await ctx.tools.execute({
      signal: new AbortController().signal, callId: ToolCallId('scoped'),
      agent: key, name: definition.name, arguments: {},
    })
    assert.equal(bodies, 0)
    assert.equal(result.isError, true)
    assert.match(result.error.message, /TOOL_DISPATCH_BINDING_CHANGED/)
  } finally {
    removeWrapper(); removeShadow(); removeOriginal()
    await scopeFiber.dispose(); await toolFiber.dispose(); await promptFiber.dispose()
  }
})

test('strict cancellation drains an already-started body without replay', async () => {
  const ctx = new Context()
  const promptFiber = await ctx.plugin(SystemPrompt)
  const toolFiber = await ctx.plugin(ToolRuntime, { strictDispatchBinding: true })
  const controller = new AbortController()
  let bodies = 0
  let settled = false
  const unregister = ctx.tools.register({
    name: 'draining_read', description: 'In-memory pending read', parameters: {},
    output: { schema: { type: 'null' }, render: () => [] },
    async execute() {
      bodies++
      await Promise.resolve().then(() => controller.abort())
      settled = true
      return null
    },
  })
  try {
    const result = await ctx.tools.execute({
      signal: controller.signal, callId: ToolCallId('drained'),
      name: 'draining_read', arguments: {},
    })
    assert.equal(bodies, 1)
    assert.equal(settled, true)
    assert.equal(result.isError, true)
    assert.equal(result.error.info.code, 'ABORTED')
  } finally {
    unregister(); await toolFiber.dispose(); await promptFiber.dispose()
  }
})
