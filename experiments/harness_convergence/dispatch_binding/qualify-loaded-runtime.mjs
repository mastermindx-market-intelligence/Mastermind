import { randomUUID } from 'node:crypto'
import { ToolCallId } from '@deepseek-ai/dsh-llm'

function refuse(check) {
  const error = new Error(`Loaded DSH dispatch policy failed: ${check}`)
  error.code = 'DSH_DISPATCH_PREFLIGHT_REFUSED'
  error.check = check
  return error
}

/**
 * Probe the supplied, already-created ToolRuntime before workload publication.
 * No direct model call, provider choice, config mutation, process spawn or retry.
 * Call only in the incumbent factory's exclusive, provider-free pre-prompt phase.
 * Existing middleware must be trusted/provider-free; it is never bypassed.
 * This is behavior evidence, not artifact authentication or execution admission.
 * The host retains the outer deadline and must reconcile an unsettled runtime.
 */
export async function qualifyLoadedDispatchRuntime(ctx, { signal } = {}) {
  if (!(signal instanceof AbortSignal)) throw new TypeError('Owner AbortSignal required')
  signal.throwIfAborted()
  const checks = []
  for (const check of ['positive', 'revocation', 'replacement', 'result-owner']) {
    signal.throwIfAborted()
    checks.push(Object.freeze(await probe(ctx, signal, check)))
  }
  signal.throwIfAborted()
  return Object.freeze({ verified: true, checks: Object.freeze(checks) })
}

async function probe(ctx, signal, check) {
  const name = `mmx_dispatch_probe_${randomUUID().replaceAll('-', '')}`
  let bodyCalls = 0, replacementCalls = 0, guardAllowed = false
  let wrapperEntered = false, changed = false, allowed = true
  let unregister
  const cleanup = []
  const tool = label => ({
    name, description: 'Temporary in-memory pre-prompt dispatch probe', parameters: {},
    output: { schema: { type: 'string' }, render: (_, value) => [
      { type: 'text', text: `${label}:${value}` },
    ] },
    async execute() {
      if (label === 'original') bodyCalls++; else replacementCalls++
      if (check === 'result-owner' && label === 'original') {
        await Promise.resolve().then(replace)
      }
      return 'value'
    },
  })
  const original = tool('original'), replacement = tool('replacement')
  function replace() {
    unregister()
    unregister = ctx.tools.register(replacement)
    changed = true
  }
  try {
    unregister = ctx.tools.register(original)
    cleanup.push(() => unregister())
    cleanup.push(ctx.tools.guard(exec => {
      if (exec.name !== name) return undefined
      // Name-only for replacement: the runtime must bind the actual definition.
      const admit = allowed && (check === 'replacement'
        || ctx.tools.get(exec.name, exec.agent) === original)
      if (admit) guardAllowed = true
      return admit ? undefined : 'PREFLIGHT_REVOKED'
    }))
    cleanup.push(ctx.on('tools/execute', async (exec, next) => {
      if (exec.name !== name) return next()
      wrapperEntered = true
      await Promise.resolve().then(() => {
        if (check === 'revocation') { allowed = false; changed = true }
        if (check === 'replacement') replace()
      })
      const result = await next()
      return check === 'result-owner' ? { value: 'rewritten', content: [] } : result
    }))
    const result = await ctx.tools.execute({
      signal, name, callId: ToolCallId(name), arguments: {},
    })
    signal.throwIfAborted()
    if (!guardAllowed || !wrapperEntered || replacementCalls !== 0) throw refuse(check)
    if (check === 'revocation' || check === 'replacement') {
      if (!changed || bodyCalls !== 0 || result.isError !== true) throw refuse(check)
    } else {
      const value = check === 'positive' ? 'value' : 'rewritten'
      if (bodyCalls !== 1 || result.isError === true || result.value !== value
        || JSON.stringify(result.content) !== JSON.stringify([
          { type: 'text', text: `original:${value}` },
        ]) || (check === 'result-owner' && !changed)) throw refuse(check)
    }
    return { name: check, bodyCalls, replacementCalls }
  } finally {
    const errors = []
    for (const remove of cleanup.reverse()) { try { remove() } catch (e) { errors.push(e) } }
    if (errors.length) throw new AggregateError(errors, 'Dispatch probe cleanup failed')
  }
}
