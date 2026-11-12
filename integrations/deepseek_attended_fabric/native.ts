/** Native Cordis/Tools registration, scoped to the actual authenticated Agent. */
import type { Agent } from '@deepseek-ai/dsh-agent'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import { createHandler, parameters, TOOL } from './core.ts'
import type { FabricHost } from './core.ts'

/**
 * Called by the incumbent authenticated native host after its Agent and Tools
 * service exist. There is deliberately no cordis.yml/config grant or global
 * registration fallback. Disposal withdraws this tool; it does not cancel jobs.
 */
export function installFabricTool(agent: Agent, host: FabricHost<Agent>): () => void {
  if (!agent?.ctx || scopeOf(agent.ctx) !== agent)
    throw new Error('FABRIC_EXACT_NATIVE_AGENT_SCOPE_REQUIRED')
  let mounted = true
  const handler = createHandler(agent, host, () => mounted)
  const tool: ToolDefinition = {
    name: TOOL,
    description: 'Submit or observe one separately admitted company Fabric job for this native session. '
      + 'Keep the same task_key after interruption. Fabric owns host, account, model, budget and lifecycle. '
      + 'This tool does not cancel remote work or accept results. A controller receipt is not worker execution.',
    parameters,
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    isConcurrencySafe: () => false,
    execute: (args, exec) => handler(args, exec.agent, exec.signal),
  }
  return agent.ctx.effect(() => {
    const unregister = agent.ctx.tools.register(tool)
    return () => {
      mounted = false
      unregister()
    }
  })
}
