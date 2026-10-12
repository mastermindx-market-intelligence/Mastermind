/** Experimental compatibility adapter for the unchanged #1060 profile.
 *
 * Its preflight registers scoped probes but omits the agent at execute. DSH
 * 4878 intentionally does not infer it. Bind that call to the actual unpublished
 * ACP agent; retain the original plugin fiber, checks, grant and MCP lifecycle.
 * No root/global mount, fallback, synthetic preflight result or new authority.
 */
import { scopeOf } from '@deepseek-ai/dsh-scope'

export function bindProfileToAgent(profile, agentCtx) {
  const agent = scopeOf(agentCtx)
  if (agent === undefined) throw new Error('DSH_PROFILE_AGENT_SCOPE_REQUIRED')
  let used = false
  return Object.freeze({...profile, async apply(ctx, config) {
    if (used || scopeOf(ctx) !== agent) throw new Error('DSH_PROFILE_SCOPE_CHANGED_OR_REUSED')
    used = true
    const rawTools = ctx.tools
    const tools = new Proxy(rawTools, {get(target, key) {
      if (key === 'execute') return input => {
        if (input === null || typeof input !== 'object' || Array.isArray(input)) {
          throw new TypeError('DSH_PROFILE_EXECUTION_INPUT_REQUIRED')
        }
        if (input.agent !== undefined && input.agent !== agent) {
          throw new Error('DSH_PROFILE_CROSS_AGENT_EXECUTION')
        }
        return target.execute({...input, agent})
      }
      const value = Reflect.get(target, key, target)
      return typeof value === 'function' ? value.bind(target) : value
    }})
    const scoped = new Proxy(ctx, {get(target, key) {
      if (key === 'tools') return tools
      const value = Reflect.get(target, key, target)
      return typeof value === 'function' ? value.bind(target) : value
    }})
    // This callback itself is run by agentCtx.plugin; ownership/disposal and
    // registrations remain on that original Cordis context and fiber.
    await profile.apply(scoped, config)
  }})
}
