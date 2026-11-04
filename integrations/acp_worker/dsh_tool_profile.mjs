import { createAdmittedPlugin } from '@deepseek-ai/dsh-mcp-client'
import { compileDshMcpGrant } from './dsh_mcp_grant.mjs'
import { compileDshAttemptOverlay } from './dsh_attempt_overlay.mjs'
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
export function createDshToolProfile(options) {
  return composeDshToolProfile(options)
}

// Private composition hook: a grant-bound host rechecks after asynchronous
// preflight, immediately before the existing plugin can start its transport.
function composeDshToolProfile({ admitGeneration, signal }, assertBeforeTransport) {
  const admitted = createAdmittedPlugin(admitGeneration, signal)
  return Object.freeze({
    ...admitted,
    name: 'mastermind-dsh-tool-profile',
    async apply(ctx, config) {
      signal.throwIfAborted()
      const snapshot = structuredClone(config)
      await qualifyLoadedDispatchRuntime(ctx, { signal })
      signal.throwIfAborted()
      assertBeforeTransport?.(snapshot)
      signal.throwIfAborted()
      await admitted.apply(ctx, snapshot)
    },
  })
}

/**
 * Compose an existing Executive MCP grant projection into the same tool profile.
 * isCurrentBinding must be a trusted host closure proving current DSH/Attempt/
 * artifact/realm eligibility; projecting another surface's grant grants none.
 * Target checks precede preflight or transport creation. The original profile
 * and donor plugin still own activation, namespace, cancellation and disposal.
 */
export function createDshGrantedToolProfile({
  projection, isCurrentBinding, signal, attemptOverlay,
}) {
  const bound = compileDshAttemptOverlay(projection, attemptOverlay)
  // This remains the incumbent host's ONE binding callback, with the exact
  // Attempt claim attached. A stale/widened Attempt cannot borrow this profile
  // by changing the caller's config or by waiting through async preflight.
  const current = bound
    ? (binding, request) => bound.isLive() && isCurrentBinding(binding, Object.freeze({
      ...request, attempt: bound.claim,
    }))
    : isCurrentBinding
  const grant = compileDshMcpGrant(projection, { isCurrentBinding: current, signal })
  const assertBeforeTransport = config => {
    grant.assertConfig(config)
    bound?.assertConfig(config)
  }
  const profile = composeDshToolProfile(
    { admitGeneration: grant.admitGeneration, signal }, assertBeforeTransport,
  )
  return Object.freeze({
    ...profile,
    async apply(ctx, config) {
      signal.throwIfAborted()
      const fixedConfig = structuredClone(config)
      grant.assertConfig(fixedConfig)
      // Only the trusted Python packet's immutable cwd/env may reach the
      // existing DSH MCP transport. Never accept ambient or caller-selected
      // server environment keys, and never alter command, args or tool grant.
      const admittedConfig = bound ? bound.bind(fixedConfig) : fixedConfig
      await profile.apply(ctx, admittedConfig)
    },
  })
}
