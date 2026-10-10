import { isDeepStrictEqual } from 'node:util'

function refused() {
  const error = new Error('DSH MCP grant binding refused')
  error.code = 'DSH_MCP_GRANT_REFUSED'
  return error
}
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const toolName = value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/.test(value)
function freeze(value) {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child)
    Object.freeze(value)
  }
  return value
}
function jsonCopy(value) {
  let nodes = 0
  function check(item, depth = 0) {
    if (++nodes > 16384 || depth > 40) throw refused()
    if (item === null || typeof item === 'boolean' || typeof item === 'string') return
    if (typeof item === 'number') {
      if (!Number.isFinite(item) || (Number.isInteger(item) && !Number.isSafeInteger(item))) throw refused()
      return
    }
    if (!Array.isArray(item) && (!record(item) || Object.getPrototypeOf(item) !== Object.prototype)) throw refused()
    for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(item))) {
      if (!('value' in descriptor)) throw refused()
      check(descriptor.value, depth + 1)
    }
  }
  check(value)
  const text = JSON.stringify(value)
  if (Buffer.byteLength(text) > 262144) throw refused()
  return JSON.parse(text)
}
function contract(tool) {
  if (!record(tool) || !toolName(tool.name) || !record(tool.inputSchema)) throw refused()
  for (const key of ['outputSchema', 'annotations', 'execution'])
    if (tool[key] != null && !record(tool[key])) throw refused()
  return { name: tool.name, inputSchema: tool.inputSchema, outputSchema: tool.outputSchema ?? null,
    annotations: tool.annotations ?? null, execution: tool.execution ?? null }
}

/**
 * Consume a trusted Python policy projection without recreating its digest law.
 * The projection is NOT DSH entitlement. isCurrentBinding is supplied by the
 * incumbent host and must attest the actual DSH Attempt/artifact/resource realm;
 * it is not a JSON flag, persisted lease, model callback, or policy database.
 */
export function compileDshMcpGrant(projection, { isCurrentBinding, signal } = {}) {
  if (typeof isCurrentBinding !== 'function' || !(signal instanceof AbortSignal)) throw refused()
  const value = jsonCopy(projection), target = value.target, source = value.source
  if (value.schema !== 'mastermind.dsh_mcp_tool_projection.v1' || value.production_armed !== false
    || value.required !== true || value.approvalMode !== 'approve' || !record(source)
    || !record(target) || !record(value.serverInfo) || !Array.isArray(value.tools)
    || value.tools.length < 1 || value.tools.length > 256) throw refused()
  for (const key of ['profile_digest', 'grant_digest', 'tool_schema_digest'])
    if (typeof source[key] !== 'string' || !/^[a-f0-9]{64}$/.test(source[key])) throw refused()
  for (const key of ['profile_id', 'execution_surface', 'auth_realm', 'capability_id', 'auth_status'])
    if (typeof source[key] !== 'string' || !source[key] || source[key].length > 128) throw refused()
  for (const key of ['name', 'version'])
    if (typeof value.serverInfo[key] !== 'string' || !value.serverInfo[key]) throw refused()
  if (typeof target.serverName !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(target.serverName)) throw refused()
  if (target.transport === 'stdio') {
    if (typeof target.command !== 'string' || !target.command.startsWith('/') || target.command.includes('\0')
      || !Array.isArray(target.args) || target.args.some(x => typeof x !== 'string' || x.includes('\0'))
      || Object.keys(target).sort().join(',') !== 'args,command,serverName,transport') throw refused()
  } else if (target.transport === 'streamable-http') {
    let endpoint
    try { endpoint = new URL(target.url) } catch { throw refused() }
    if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
      || Object.keys(target).sort().join(',') !== 'serverName,transport,url') throw refused()
  } else throw refused()
  const expected = new Map()
  for (const tool of value.tools) {
    const row = contract(tool)
    if (expected.has(row.name)) throw refused()
    expected.set(row.name, freeze(row))
  }
  const binding = freeze({ source, target, serverInfo: value.serverInfo })
  function live(phase, rawName, execution) {
    if (signal.aborted || (phase === 'dispatch' && (!(execution?.signal instanceof AbortSignal) || execution.signal.aborted))) return false
    try { return isCurrentBinding(binding, Object.freeze({ phase, rawName, execution })) === true }
    catch { return false }
  }
  return Object.freeze({
    assertConfig(config) {
      if (!record(config)) throw refused()
      const actual = { serverName: config.serverName, transport: config.transport }
      if (config.transport === 'stdio') { actual.command = config.command; actual.args = config.args }
      else actual.url = config.url
      if (!isDeepStrictEqual(actual, target) || !live('startup')) throw refused()
    },
    admitGeneration(snapshot) {
      if (!record(snapshot) || snapshot.serverName !== target.serverName
        || snapshot.serverInfo?.name !== binding.serverInfo.name
        || snapshot.serverInfo?.version !== binding.serverInfo.version
        || !Array.isArray(snapshot.tools) || snapshot.tools.length > 256) throw refused()
      const observed = new Map()
      for (const tool of snapshot.tools) {
        const row = contract(tool)
        if (observed.has(row.name)) throw refused()
        observed.set(row.name, row)
      }
      for (const [name, row] of expected)
        if (!isDeepStrictEqual(row, observed.get(name))) throw refused()
      if (!live('discovery')) throw refused()
      return [...expected.keys()].map(rawName => Object.freeze({ rawName,
        allow: execution => live('dispatch', rawName, execution) }))
    },
  })
}
