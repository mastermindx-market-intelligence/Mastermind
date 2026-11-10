// Paperclip module worker. The host forks the BUILT dist/worker.js and calls
// setup(ctx). The file MUST end with `runWorker(plugin, import.meta.url)` —
// without it the worker process exits immediately after load
// ("Worker initialize failed: Worker process exited (code=0)").
//
// Company-scoped host reads (ctx.agents.list, ...) require a company context:
// they work inside a host-issued invocation (data handler called from a
// company-scoped UI, or a tool executed in a run). A bare HTTP bridge call
// must carry companyId at the request top level, not only inside params.
import { definePlugin, runWorker } from '@paperclipai/plugin-sdk'

let pluginCtx = null

async function readSnapshot(ctx, companyId) {
  const out = {
    companyId,
    generatedAt: new Date().toISOString(),
    counts: { REPLACE_ME: null },
    sources: {},
  }
  if (!companyId) {
    out.sources.agents = { ok: false, error: 'no company id in context' }
    return out
  }
  try {
    const agents = await ctx.agents.list({ companyId, limit: 1000 })
    out.sources.agents = { ok: true, read: agents.length }
    out.counts.REPLACE_ME = agents.length // replace with the real derivation
  } catch (err) {
    out.sources.agents = { ok: false, error: String((err && err.message) || err) }
  }
  return out
}

const plugin = definePlugin({
  async setup(ctx) {
    pluginCtx = ctx
    ctx.logger.info('REPLACE-ME: setup')

    // UI data: register one key per widget/page. Return honest data — a
    // source that could not be read yields null and a named error, never a
    // guessed value.
    ctx.data.register('REPLACE-ME', async (params) => {
      const companyId = String(params.companyId || '')
      return readSnapshot(ctx, companyId)
    })

    // Agent tool: same truth in string form.
    ctx.tools.register(
      'REPLACE-ME-report',
      {
        displayName: 'REPLACE ME report',
        description: 'Reports its counts with the source each came from and any source that could not be read.',
        parametersSchema: {
          type: 'object',
          properties: {
            companyId: { type: 'string', description: 'Company to report on; defaults to the run company.' },
          },
          additionalProperties: false,
        },
      },
      async (params, runCtx) => {
        const snapshot = await readSnapshot(ctx, params.companyId || runCtx.companyId)
        return { content: JSON.stringify(snapshot, null, 2), data: snapshot }
      },
    )
  },

  // onHealth receives NO arguments in this SDK — capture ctx in setup.
  async onHealth() {
    if (!pluginCtx) return { status: 'degraded', message: 'setup has not run' }
    return { status: 'ok', message: 'REPLACE ME: define a real check (last read, last sync, queue depth).' }
  },
})

export default plugin
runWorker(plugin, import.meta.url)
