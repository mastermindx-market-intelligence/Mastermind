// Mastermind Core — worker. `definePlugin` default export; the host forks
// this file (dist/worker.js) and calls setup(ctx).
//
// Module rules (lane L9 ledger amendment, verbatim in README.md):
// this module displays and joins; it never admits, schedules, retries or
// accepts work; counts that could not be read are reported as unread, never
// guessed as zero.
import { definePlugin, runWorker } from '@paperclipai/plugin-sdk'

// Heartbeat runs every 30s server-side; four missed beats = unreachable.
const REACHABLE_WINDOW_MS = 2 * 60 * 1000

const STATE_KEY = 'roster-truth/last'

function isoAgo(ms) {
  return new Date(Date.now() - ms).toISOString()
}

/**
 * Read the roster truth for one company. Every count names the source it
 * came from; a source that could not be read yields `null` counts and an
 * error string, never a zero.
 */
async function readRosterTruth(ctx, companyId) {
  const out = {
    companyId,
    generatedAt: new Date().toISOString(),
    moduleRevision: 'r2-reload-proof',
    counts: {
      configuredRoles: null,
      enrolledAgents: null,
      reachableAgents: null,
      agentsWithActiveWork: null,
    },
    sources: {},
  }

  if (!companyId) {
    out.sources.agents = { ok: false, error: 'no company id in context' }
    return out
  }

  // Source: the company's agents (one list read feeds three counts).
  let agents = null
  try {
    agents = await ctx.agents.list({ companyId, limit: 1000 })
    out.sources.agents = { ok: true, read: agents.length }
  } catch (err) {
    out.sources.agents = { ok: false, error: String((err && err.message) || err) }
    return out
  }

  out.counts.enrolledAgents = agents.length

  const roles = new Set()
  for (const a of agents) {
    if (a && typeof a.role === 'string' && a.role) roles.add(a.role)
  }
  out.counts.configuredRoles = roles.size
  out.roles = [...roles].sort()

  // Active work = the agent row itself says it is running/active right now.
  out.counts.agentsWithActiveWork = agents.filter(
    (a) => a && (a.status === 'running' || a.status === 'active'),
  ).length

  // Reachable = a heartbeat inside the window. Same read, different field,
  // named as its own source because it can lag or be absent independently.
  const cutoff = isoAgo(REACHABLE_WINDOW_MS)
  let reachable = 0
  let neverHeartbeated = 0
  for (const a of agents) {
    const at = a && a.lastHeartbeatAt
    if (!at) {
      neverHeartbeated += 1
      continue
    }
    if (new Date(at).getTime() >= new Date(cutoff).getTime()) reachable += 1
  }
  out.counts.reachableAgents = reachable
  out.sources['agents.lastHeartbeatAt'] = {
    ok: true,
    windowMs: REACHABLE_WINDOW_MS,
    neverHeartbeated,
  }

  return out
}

async function persistLastSnapshot(ctx, snapshot) {
  try {
    await ctx.state.set(
      { scopeKind: 'instance', stateKey: STATE_KEY },
      snapshot,
    )
  } catch (err) {
    // State is a convenience for the health check, never a data source of
    // truth: a failed write must not fail the read.
    ctx.logger.warn('roster-truth: could not persist snapshot', {
      error: String((err && err.message) || err),
    })
  }
}

// onHealth() receives no arguments in this SDK; capture the context setup()
// was given so the health check can read the last snapshot.
let pluginCtx = null

const plugin = definePlugin({
  async setup(ctx) {
    pluginCtx = ctx
    ctx.logger.info('mastermind-core: setup', { plugin: 'mastermind.core' })

    // Dashboard widget / page / sidebar all read the same key.
    ctx.data.register('roster-truth', async (params) => {
      const companyId = String(params.companyId || '')
      const snapshot = await readRosterTruth(ctx, companyId)
      await persistLastSnapshot(ctx, snapshot)
      // One metric per read: build 2026.1106.0 persists metrics.write rows to
      // plugin_logs (queryable via /api/plugins/:id/logs) while ctx.logger
      // lines only reach the server log.
      try {
        await ctx.metrics.write('roster.read', 1, { companyId: companyId || 'none' })
      } catch (err) {
        ctx.logger.warn('roster-truth: metric write failed', {
          error: String((err && err.message) || err),
        })
      }
      return snapshot
    })

    // Agent tool: same truth, string form for the agent.
    ctx.tools.register(
      'roster-report',
      {
        displayName: 'Roster report',
        description:
          'Reports the four roster-truth counts with the source each came from and any source that could not be read.',
        parametersSchema: {
          type: 'object',
          properties: {
            companyId: { type: 'string', description: 'Company to report on; defaults to the run company.' },
          },
          additionalProperties: false,
        },
      },
      async (params, runCtx) => {
        const companyId =
          (params && typeof params.companyId === 'string' && params.companyId) ||
          runCtx.companyId
        const snapshot = await readRosterTruth(ctx, companyId)
        await persistLastSnapshot(ctx, snapshot)
        return {
          content: JSON.stringify(snapshot, null, 2),
          data: snapshot,
        }
      },
    )
  },

  async onHealth() {
    // Health = the last roster read's source status, honestly. No snapshot
    // yet means we have not observed anything: degraded, not ok.
    let last = null
    if (pluginCtx) {
      try {
        last = await pluginCtx.state.get({
          scopeKind: 'instance',
          stateKey: STATE_KEY,
        })
      } catch {
        last = null
      }
    }
    const agentsSource = last && last.sources ? last.sources.agents : null
    if (agentsSource && agentsSource.ok) {
      return {
        status: 'ok',
        message: `last roster read ok (${last.generatedAt}); enrolled ${last.counts.enrolledAgents ?? '?'}`,
        details: { lastReadAt: last.generatedAt, sources: last.sources },
      }
    }
    return {
      status: 'degraded',
      message: agentsSource
        ? `last roster read failed to read agents: ${agentsSource.error}`
        : 'no roster read has completed yet',
      details: { lastReadAt: last ? last.generatedAt : null },
    }
  },
})

export default plugin
// Required: without this the worker process exits immediately after load
// ("Worker initialize failed: Worker process exited (code=0)").
runWorker(plugin, import.meta.url)
