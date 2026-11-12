import { definePlugin, runWorker } from '@paperclipai/plugin-sdk';
import manifest, { tools } from './manifest.mjs';
import { Store } from './store.mjs';
import { NativePort } from './native.mjs';
import { Teamlink } from './core.mjs';
import { validate, validateConfig } from './validation.mjs';
import { Realtime } from './realtime.mjs';

let context, configuration = {}, active = 0, lastJob = null, managedSkill = null, realtime = null;
let transition = null, closing = false;
const idleWaiters = new Set();
const methods = { teamlink_inventory: 'inventory', teamlink_inspect: 'inspect', teamlink_bind: 'bind', teamlink_send: 'send',
  teamlink_status: 'status', teamlink_ack: 'ack', teamlink_context: 'context' };
const service = (config = configuration) => new Teamlink(context, new Store(context.db), new NativePort(config), config);

async function admitted(work) {
  // A host config RPC is asynchronous. Fence admission before its first await,
  // and keep every admitted handler on one immutable configuration generation.
  while (transition) await transition;
  if (closing) throw new Error('TEAMLINK_SHUTTING_DOWN');
  const runtime = { config: configuration, service: service(), realtime };
  active++;
  try { return await work(runtime); }
  finally {
    active--;
    if (!active) { for (const resolve of idleWaiters) resolve(); idleWaiters.clear(); }
  }
}

async function perform(declaration, params, actor) {
  try {
    return await admitted(async ({ service: owned, realtime: live }) => {
      validate(declaration.parametersSchema, params);
      const execute = () => owned[methods[declaration.name]](params, actor);
      const value = params.issueId && live ? await live.exclusive(params.issueId, execute) : await execute();
      if (declaration.name === 'teamlink_bind' && live) {
        // A refresh failure cannot erase a committed binding's receipt.
        try { await live.refresh(); } catch { live.errors.inventory = 'REALTIME_INVENTORY_UNAVAILABLE'; }
      }
      if (params.issueId) live?.nudge(params.issueId);
      return { content: JSON.stringify(value), data: value };
    });
  } catch (error) {
    return { error: /^[A-Z0-9_]+$/.test(error.message) ? error.message : 'TEAMLINK_OPERATION_UNAVAILABLE' };
  }
}

const plugin = definePlugin({
  async setup(ctx) {
    // The host delivers each persisted company config through configChanged
    // after initialization, including on restart. An unscoped setup-time
    // config.get is intentionally denied by Paperclip's company boundary.
    context = ctx; configuration = {};
    for (const declaration of tools) {
      ctx.tools.register(declaration.name, declaration, (params, run) => perform(declaration, params, {
        kind: 'agent', companyId: run.companyId, agentId: run.agentId, runId: run.runId,
      }));
      ctx.actions.register(declaration.name, (params, host) => {
        // The native action route injects its authorized company scope into
        // params. Validate that scope, then remove only that host-added field;
        // agent tool input still follows the strict declared parameter schema.
        if (params.companyId !== undefined && params.companyId !== host.companyId) return { error: 'COMPANY_SCOPE_MISMATCH' };
        const { companyId: _companyScope, ...input } = params;
        return perform(declaration, input, {
          kind: host.actor.type === 'user' ? 'board' : host.actor.type,
          companyId: host.companyId, userId: host.actor.userId, agentId: host.actor.agentId, runId: host.actor.runId,
        });
      });
    }
    ctx.events.on('issue.comment.created', async event => {
      await admitted(async ({ config, service: owned, realtime: live }) => {
        if (!config.enabled) return;
        const execute = () => owned.commentEvent(event);
        if (live && event.entityId) await live.exclusive(event.entityId, execute); else await execute();
        if (event.entityId) live?.nudge(event.entityId);
      });
    });
    ctx.jobs.register('reconcile', async () => {
      try {
        await admitted(async ({ config, service: owned, realtime: live }) => {
          if (!config.enabled) return;
          if (live) {
            try { await live.refresh(); }
            catch { live.errors.inventory = 'REALTIME_INVENTORY_UNAVAILABLE'; }
          }
          await owned.tick(live ? (issue, work) => live.exclusive(issue, work) : undefined);
          lastJob = { status: 'completed', at: new Date().toISOString() };
        });
      }
      catch { lastJob = { status: 'observation_unavailable', at: new Date().toISOString() }; }
    });
  },
  async onConfigChanged(next, scope) {
    // This installation is intentionally single-company. A second company cannot
    // replace its global connection or supply actor identity through tool input.
    if (scope?.companyId && next.companyId !== scope.companyId) throw new Error('COMPANY_SCOPE_MISMATCH');
    validate(manifest.instanceConfigSchema, next);
    if (closing) throw new Error('TEAMLINK_SHUTTING_DOWN');
    if (transition || active || realtime?.inflight.size || realtime?.refreshing || realtime?.connecting) throw new Error('TEAMLINK_OPERATION_IN_PROGRESS');
    if (configuration.companyId && next.companyId !== configuration.companyId) throw new Error('SINGLE_COMPANY_ONLY');
    let release;
    transition = new Promise(resolve => { release = resolve; });
    const previous = realtime; previous?.pause();
    try {
      const snapshot = structuredClone(next);
      const candidate = next.enabled && next.realtime !== false ? new Realtime(snapshot, new Store(context.db), service(snapshot)) : null;
      let skill = managedSkill;
      if (next.enabled) {
        const resolved = await context.skills.managed.reconcile('teamlink', next.companyId);
        if (!resolved.skill?.key) throw new Error('TEAMLINK_SKILL_UNAVAILABLE');
        skill = { key: resolved.skill.key, id: resolved.skill.id, status: resolved.status };
      }
      if (closing) throw new Error('TEAMLINK_SHUTTING_DOWN');
      await previous?.stop();
      if (closing) throw new Error('TEAMLINK_SHUTTING_DOWN');
      configuration = snapshot; realtime = candidate; managedSkill = skill;
      if (candidate) {
        try { await candidate.refresh(); }
        catch { candidate.errors.inventory = 'REALTIME_INVENTORY_UNAVAILABLE'; }
      }
    } finally {
      if (!closing && realtime === previous) previous?.resume();
      transition = null; release();
    }
  },
  async onValidateConfig(config) { return validateConfig(manifest.instanceConfigSchema, config); },
  async onHealth() {
    const live = realtime?.health() || null;
    return { status: configuration.enabled ? (closing || transition || lastJob?.status === 'observation_unavailable' || live && (!live.connected || live.error) ? 'degraded' : 'ok') : 'degraded',
      message: configuration.enabled ? 'Native Paperclip transport configured; see observations for source freshness.' : 'Teamlink disabled until configured.',
      details: { enabled: configuration.enabled === true, companyId: configuration.companyId || null,
        environmentId: configuration.environmentId || null, managedSkill, active, transitioning: Boolean(transition), closing, lastJob, realtime: live } };
  },
  async onShutdown() {
    closing = true;
    if (transition) await transition;
    const drained = active ? new Promise(resolve => idleWaiters.add(resolve)) : Promise.resolve();
    await Promise.all([realtime?.stop(), drained]); realtime = null;
  },
  // Native subscriptions are owned and drained here. Never claim quiescence
  // while an enabled event listener can schedule work. Cron remains recovery.
  async onIdleDrain() { return active || transition || realtime && !realtime.closed ? 'present' : 'none'; },
});

export default plugin;
runWorker(plugin, import.meta.url);

