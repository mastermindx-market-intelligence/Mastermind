import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import PublishedTools from '@deepseek-ai/dsh-tools'
import PatchedTools from './.cache/donor/index.ts'
import PristineTools from './.cache/pristine/index.ts'

async function withRuntime(factory, config, run) {
  const ctx = new Context()
  const prompt = await ctx.plugin(SystemPrompt)
  const tools = await ctx.plugin(factory, config)
  try { return await run(ctx) }
  finally { await tools.dispose(); await prompt.dispose() }
}
async function qualify(ctx, signal = new AbortController().signal) {
  const { qualifyLoadedDispatchRuntime } = await import('./qualify-loaded-runtime.mjs')
  return qualifyLoadedDispatchRuntime(ctx, { signal })
}
const strict = { strictDispatchBinding: true }

test('actual patched and enabled runtime qualifies before any model call', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const before = ctx.tools.schemas()
    const receipt = await qualify(ctx)
    assert.equal(receipt.verified, true)
    assert.deepEqual(receipt.checks.map(x => x.name), [
      'positive', 'revocation', 'replacement', 'result-owner',
    ])
    assert.deepEqual(receipt.checks.map(x => x.bodyCalls), [1, 0, 0, 1])
    assert.ok(Object.isFrozen(receipt) && Object.isFrozen(receipt.checks))
    assert.deepEqual(ctx.tools.schemas(), before, 'probe tools must be removed')
  })
})
for (const [name, factory, config] of [
  ['published ignores requested option', PublishedTools, strict],
  ['pristine ignores requested option', PristineTools, strict],
  ['patched default remains disabled', PatchedTools, {}],
  ['patched explicitly disabled', PatchedTools, { strictDispatchBinding: false }],
]) {
  test(name, async () => withRuntime(factory, config, async ctx => {
    const before = ctx.tools.schemas()
    await assert.rejects(qualify(ctx), error =>
      error.code === 'DSH_DISPATCH_PREFLIGHT_REFUSED' && error.check === 'revocation')
    assert.deepEqual(ctx.tools.schemas(), before)
  }))
}

test('denying everything cannot fake qualification', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const remove = ctx.tools.guard(() => 'fixture-all-denied')
    try { await assert.rejects(qualify(ctx), e => e.check === 'positive') }
    finally { remove() }
    assert.equal((await qualify(ctx)).verified, true)
  })
})
test('unrelated tool definitions and callbacks survive the preflight', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    let calls = 0
    const retained = { name: 'retained_read', description: 'retained', parameters: {},
      output: { schema: { type: 'null' }, render: () => [] },
      async execute() { calls++; return null },
    }
    const remove = ctx.tools.register(retained)
    try {
      const before = ctx.tools.schemas()
      assert.equal((await qualify(ctx)).verified, true)
      assert.equal(calls, 0)
      assert.equal(ctx.tools.get(retained.name), retained)
      assert.deepEqual(ctx.tools.schemas(), before)
    } finally { remove() }
  })
})
test('preflight can run twice without leaked guards or wrappers', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    assert.equal((await qualify(ctx)).verified, true)
    assert.equal((await qualify(ctx)).verified, true)
    assert.deepEqual(ctx.tools.schemas(), [])
  })
})
test('throwing existing middleware refuses and leaves no probe tools', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const remove = ctx.on('tools/execute', async () => { throw new Error('fixture') })
    try { await assert.rejects(qualify(ctx), e => e.check === 'positive') }
    finally { remove() }
    assert.deepEqual(ctx.tools.schemas(), [])
    assert.equal((await qualify(ctx)).verified, true)
  })
})

test('already-aborted owner signal prevents all probe registration', async () => {
  const controller = new AbortController(); controller.abort()
  let touched = false
  const ctx = { get tools() { touched = true; throw new Error('must not inspect') } }
  await assert.rejects(qualify(ctx, controller.signal), e => e.name === 'AbortError')
  assert.equal(touched, false)
})
test('owner cancellation during middleware prevents qualification', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const controller = new AbortController()
    const remove = ctx.on('tools/execute', async (_exec, next) => {
      controller.abort(); return next()
    })
    try { await assert.rejects(qualify(ctx, controller.signal), e =>
      e.name === 'AbortError' || e.code === 'DSH_DISPATCH_PREFLIGHT_REFUSED') }
    finally { remove() }
    assert.deepEqual(ctx.tools.schemas(), [])
  })
})
test('missing deadline signal fails closed before touching runtime', async () => {
  const { qualifyLoadedDispatchRuntime } = await import('./qualify-loaded-runtime.mjs')
  await assert.rejects(qualifyLoadedDispatchRuntime({}, {}), TypeError)
})

for (const [variant, expectedCheck] of [
  ['guard', 'revocation'], ['definition', 'replacement'], ['result', 'result-owner'],
]) {
  test(`partial patch without ${variant} enforcement is refused`, async () => {
    const { default: BrokenTools } = await import(`./.cache/preflight-defects/${variant}/index.ts`)
    await withRuntime(BrokenTools, strict, async ctx => {
      const before = ctx.tools.schemas()
      await assert.rejects(qualify(ctx), error =>
        error.code === 'DSH_DISPATCH_PREFLIGHT_REFUSED' && error.check === expectedCheck)
      assert.deepEqual(ctx.tools.schemas(), before)
    })
  })
}

test('cancellation does not abandon an unsettled tool pipeline', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const controller = new AbortController()
    let enter, release
    const entered = new Promise(resolve => { enter = resolve })
    const held = new Promise(resolve => { release = resolve })
    const remove = ctx.on('tools/execute', async (_exec, next) => {
      enter(); await held; return next()
    })
    let settled = false
    const running = qualify(ctx, controller.signal).finally(() => { settled = true })
    running.catch(() => {}) // Observe the original promise after the deliberate hold.
    try {
      await entered
      controller.abort()
      await new Promise(resolve => setImmediate(resolve))
      assert.equal(settled, false, 'cancellation is not proof of pipeline cleanup')
      release()
      await assert.rejects(running, e => e.name === 'AbortError')
      assert.deepEqual(ctx.tools.schemas(), [])
    } finally { release(); remove() }
  })
})
test('cleanup failure blocks qualification after draining all own disposers', async () => {
  await withRuntime(PatchedTools, strict, async ctx => {
    const tools = ctx.tools
    const observedContext = { on: ctx.on.bind(ctx), tools: {
      register(definition) {
        const remove = tools.register(definition)
        return () => { remove(); throw new Error('fixture cleanup error') }
      },
      get: tools.get.bind(tools), guard: tools.guard.bind(tools),
      execute: tools.execute.bind(tools),
    } }
    await assert.rejects(qualify(observedContext), AggregateError)
    assert.deepEqual(ctx.tools.schemas(), [])
    assert.equal((await qualify(ctx)).verified, true)
  })
})
