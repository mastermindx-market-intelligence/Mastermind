import { definePlugin, runWorker } from '@paperclipai/plugin-sdk';
import manifest, { tools } from './manifest.mjs';
import { Store } from './store.mjs';
import { NativePort } from './native.mjs';
import { Teamlink } from './core.mjs';
import { validate, validateConfig } from './validation.mjs';

let context, configuration = {}, active = 0, lastJob = null, managedSkill = null;
const methods = { teamlink_inventory: 'inventory', teamlink_inspect: 'inspect', teamlink_bind: 'bind', teamlink_send: 'send',
  teamlink_status: 'status', teamlink_ack: 'ack', teamlink_context: 'context' };
const service = () => new Teamlink(context, new Store(context.db), new NativePort(configuration), configuration);

async function perform(declaration, params, actor) {
  active++;
  try {
    validate(declaration.parametersSchema, params);
    const value = await service()[methods[declaration.name]](params, actor);
    return { content: JSON.stringify(value), data: value };
  } catch (error) {
    return { error: /^[A-Z0-9_]+$/.test(error.message) ? error.message : 'TEAMLINK_OPERATION_UNAVAILABLE' };
  } finally { active--; }
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
      ctx.actions.register(declaration.name, (params, host) => perform(declaration, params, {
        kind: host.actor.type === 'user' ? 'board' : host.actor.type,
        companyId: host.companyId, userId: host.actor.userId, agentId: host.actor.agentId, runId: host.actor.runId,
      }));
    }
    ctx.events.on('issue.comment.created', async event => {
      if (!configuration.enabled) return;
      active++;
      try { await service().commentEvent(event); }
      finally { active--; }
    });
    ctx.jobs.register('reconcile', async () => {
      if (!configuration.enabled) return;
      active++;
      try { await service().tick(); lastJob = { status: 'completed', at: new Date().toISOString() }; }
      catch { lastJob = { status: 'observation_unavailable', at: new Date().toISOString() }; }
      finally { active--; }
    });
  },
  async onConfigChanged(next, scope) {
    // This installation is intentionally single-company. A second company cannot
    // replace its global connection or supply actor identity through tool input.
    if (scope?.companyId && next.companyId !== scope.companyId) throw new Error('COMPANY_SCOPE_MISMATCH');
    if (active) throw new Error('TEAMLINK_OPERATION_IN_PROGRESS');
    if (configuration.companyId && next.companyId !== configuration.companyId) throw new Error('SINGLE_COMPANY_ONLY');
    if (next.enabled) {
      const resolved = await context.skills.managed.reconcile('teamlink', next.companyId);
      if (!resolved.skill?.key) throw new Error('TEAMLINK_SKILL_UNAVAILABLE');
      managedSkill = { key: resolved.skill.key, id: resolved.skill.id, status: resolved.status };
    }
    configuration = next;
  },
  async onValidateConfig(config) { return validateConfig(manifest.instanceConfigSchema, config); },
  async onHealth() {
    return { status: configuration.enabled ? (lastJob?.status === 'observation_unavailable' ? 'degraded' : 'ok') : 'degraded',
      message: configuration.enabled ? 'Native Paperclip transport configured; see observations for source freshness.' : 'Teamlink disabled until configured.',
      details: { enabled: configuration.enabled === true, companyId: configuration.companyId || null,
        environmentId: configuration.environmentId || null, managedSkill, active, lastJob } };
  },
  // No timers, daemon, detached promises, sockets or retained agent credentials.
  // Native Paperclip scheduled jobs are the durable recovery owner.
  async onIdleDrain() { return active ? 'present' : 'none'; },
});

export default plugin;
runWorker(plugin, import.meta.url);
