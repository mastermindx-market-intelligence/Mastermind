import { createAdmittedPlugin } from '@deepseek-ai/dsh-mcp-client'
import { qualifyLoadedDispatchRuntime } from './dsh_dispatch_preflight.mjs'

/**
 * Tool-profile composition for the existing DSH/ACP host bootstrap.
 *
 * Load with ctx.plugin(createDshToolProfile({ admitGeneration, signal }), config)
 * in the host's exclusive provider-free phase BEFORE publishing ACP/model work.
 * The host supplies already-admitted immutable artifact/endpoint/profile policy;
 * this factory does not authenticate it or grant execution authority.
 *
 * The donor plugin owns namespace reservation, readiness, startup rollback and
 * connection disposal. This module adds no worker/process/result lifecycle.
 * Config is snapshotted before the preflight can suspend; the donor validates
 * strict startup, disables implicit reconnect and freezes its private copy.
 * Stock donor packages lack createAdmittedPlugin and must fail loading, not fall
 * back to their unrestricted plugin. The existing package owner must install
 * the exact patched artifact; this source file performs no installation.
 */
export function createDshToolProfile({ admitGeneration, signal }) {
  const admitted = createAdmittedPlugin(admitGeneration, signal)
  return Object.freeze({
    ...admitted,
    name: 'mastermind-dsh-tool-profile',
    async apply(ctx, config) {
      signal.throwIfAborted()
      const snapshot = structuredClone(config)
      await qualifyLoadedDispatchRuntime(ctx, { signal })
      signal.throwIfAborted()
      await admitted.apply(ctx, snapshot)
    },
  })
}
