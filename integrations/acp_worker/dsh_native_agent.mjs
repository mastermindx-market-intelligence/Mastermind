import { isDeepStrictEqual } from 'node:util'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import { acceptNativeDshAttempt } from './dsh_native_attempt.mjs'
import { createDshGrantedToolProfile } from './dsh_tool_profile.mjs'

const refused = () => new Error('DSH_NATIVE_AGENT_ADMISSION_REFUSED')

/**
 * Join the incumbent native channel to ONE already-created DSH Agent.
 * Native readiness v3 observes that exact Session before the original ACK.
 * This programmatic host plugin creates no Agent, prompt, provider, process,
 * session identity, retry, or result owner. Stock ACP still owns prompt/cancel.
 *
 * The installed host supplies the already-attested projection, tool identities,
 * artifact digests and current-binding closure. A web/plugin config cannot grant
 * these capabilities. The accepted owner ACK precedes agent/created completion.
 */
export function createNativeDshAgentAdmission({
  fd, signal, projectionDigest, artifactDigest, projection, config,
  expectedTools, isCurrentBinding, onAdmitted,
}) {
  if (!Number.isInteger(fd) || fd < 3 || !(signal instanceof AbortSignal)
    || typeof isCurrentBinding !== 'function'
    || !Array.isArray(expectedTools) || expectedTools.length < 1
    || (onAdmitted !== undefined && typeof onAdmitted !== 'function')) throw refused()
  const fixedProjection = structuredClone(projection)
  const fixedConfig = structuredClone(config)
  const tools = structuredClone(expectedTools)
  if (tools.length > 16 || tools.some(row =>
    !row || Object.keys(row).sort().join(',') !== 'contract_sha256,name'
    || typeof row.name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(row.name)
    || typeof row.contract_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.contract_sha256))) throw refused()
  const orderedTools = rows => [...rows].sort((a, b) => a.name.localeCompare(b.name))
  const names = new Set(tools.map(row => row.name))
  if (names.size !== tools.length) throw refused()
  let consumed = false
  return Object.freeze({
    name: 'mastermind-native-agent-admission',
    inject: ['agents', 'tools'],
    apply(ctx) {
      const lifetime = new AbortController()
      ctx.effect(() => () => lifetime.abort('native admission plugin disposed'))
      ctx.on('agent/created', async ({ agent, source, signal: creating }) => {
        signal.throwIfAborted()
        if (consumed || source !== 'startup' || scopeOf(agent.ctx) !== agent) throw refused()
        consumed = true
        const active = AbortSignal.any([signal, lifetime.signal, ...creating ? [creating] : []])
        let live = true
        const stopObserving = ctx.on('agent/disposed', ({ agent: removed }) => {
          if (removed === agent) { live = false; stopObserving() }
        })
        // These restrictions belong to the Agent, not to the removable MCP
        // fiber. Revocation must never reveal inherited tools on a live Agent.
        agent.ctx.tools.presentAs('native')
        agent.ctx.tools.restrict({ allow: [] })
        const nativeSession = agent.session
        const nativeSessionId = nativeSession.id
        let discoveryEvidence
        const observeNativeSession = () => {
          if (!live || active.aborted || !discoveryEvidence
            || discoveryEvidence.signal.aborted || scopeOf(agent.ctx) !== agent
            || ctx.agents.get(agent.id) !== agent || agent.session !== nativeSession
            || nativeSession.id !== nativeSessionId
            || isCurrentBinding(discoveryEvidence.binding, discoveryEvidence.request) !== true)
            throw refused()
          return nativeSessionId
        }
        let activation
        try {
          const accepted = await acceptNativeDshAttempt({
            fd, signal: active, projectionDigest, artifactDigest,
            nativeSessionRequired: true, observeNativeSession,
            async activate(overlay, observedTools, activationSignal) {
              if (agent.session.header.cwd !== overlay.cwd
                || !isDeepStrictEqual(orderedTools(observedTools), orderedTools(tools))) throw refused()
              let discovery = false
              const current = (binding, request) => {
                const valid = live && !activationSignal.aborted
                  && ctx.agents.get(agent.id) === agent
                  && isCurrentBinding(binding, request) === true
                if (valid && request.phase === 'discovery') {
                  discovery = true
                  discoveryEvidence = { binding, request, signal: activationSignal }
                }
                return valid
              }
              const granted = createDshGrantedToolProfile({
                projection: fixedProjection, isCurrentBinding: current,
                signal: activationSignal, attemptOverlay: overlay, agent,
              })
              const mounted = await agent.ctx.plugin({
                ...granted,
                async apply(inner, options) {
                  // Preflight and MCP registration use the existing Agent
                  // scope; the deny-inherited boundary outlives this fiber.
                  await granted.apply(inner, options)
                  if (!discovery || !live || activationSignal.aborted) throw refused()
                  const exposed = inner.tools.schemas(agent).map(row => row.name).sort()
                  if (!isDeepStrictEqual(exposed, [...names].sort())) throw refused()
                  agent.ctx.tools.guard(execution => live && !activationSignal.aborted
                    && execution.agent === agent && names.has(execution.name)
                    ? undefined : 'DSH_NATIVE_AGENT_TOOL_NOT_ADMITTED')
                },
              }, fixedConfig)
              return { ready: true, dispose: () => mounted.dispose() }
            },
          })
          activation = accepted.activation
          if (accepted.nativeSessionId !== observeNativeSession()) throw refused()
          // Synchronous host observation after the real ACK; no admission or
          // result is inferred from an allocation, callback or UI handshake.
          onAdmitted?.({ agent, attemptOverlay: accepted.attemptOverlay })
        } catch (error) {
          live = false
          stopObserving()
          await activation?.dispose?.()
          throw error
        }
        // The existing Agent scope owns the mounted MCP fiber until disposal.
      })
    },
  })
}
