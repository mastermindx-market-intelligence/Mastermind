// Build qualification for the source candidate; never installs/activates an OS profile.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, existsSync, mkdtempSync, readdirSync } from 'node:fs'
import { dirname, resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { build } from 'vite'

const here = dirname(fileURLToPath(import.meta.url)), cache = resolve(here, '.cache')
const hash = data => createHash('sha256').update(data).digest('hex')
const core = JSON.parse(readFileSync(resolve(here, 'donor-manifest.json'), 'utf8'))
const mcp = JSON.parse(readFileSync(resolve(here, 'mcp-manifest.json'), 'utf8'))
const agentLoop = JSON.parse(readFileSync(resolve(here, 'agent-loop-manifest.json'), 'utf8'))
const lock = JSON.parse(readFileSync(resolve(here, 'package-lock.json'), 'utf8'))
const installedAgentLoop = JSON.parse(readFileSync(
  resolve(here, 'node_modules/@deepseek-ai/dsh-agent-loop/package.json'), 'utf8',
))
const lockedAgentLoop = lock.packages['node_modules/@deepseek-ai/dsh-agent-loop']
assert.equal(installedAgentLoop.name, agentLoop.package)
assert.equal(installedAgentLoop.version, agentLoop.version)
assert.deepEqual(
  { version: lockedAgentLoop?.version, resolved: lockedAgentLoop?.resolved, integrity: lockedAgentLoop?.integrity },
  { version: agentLoop.version, resolved: agentLoop.resolved, integrity: agentLoop.integrity },
)
const inputs = {}
function record(path, expected) {
  const actual = hash(readFileSync(path))
  if (expected !== undefined) assert.equal(actual, expected, `Changed build input: ${path}`)
  inputs[relative(here, path)] = actual
}
for (const file of core.files.filter(f => f.kind === 'source')) {
  record(resolve(cache, 'donor', file.name), file.name === 'index.ts' ? core.patched_index_sha256 : file.sha256)
}
for (const file of mcp.files.filter(f => f.folder === 'mcp-pristine')) {
  record(resolve(cache, 'mcp-donor', file.name), mcp.patched_source_sha256[file.name] ?? file.sha256)
}
for (const [file, expected] of Object.entries(agentLoop.files)) {
  record(resolve(here, 'node_modules/@deepseek-ai/dsh-agent-loop', file), expected)
}
record(resolve(here, 'agent-loop-manifest.json'))
for (const file of ['dsh_tool_profile.mjs', 'dsh_dispatch_preflight.mjs', 'dsh_mcp_grant.mjs']) {
  record(resolve(here, '../../../integrations/acp_worker', file))
}
record(resolve(here, 'package-lock.json'), core.npm_lock_sha256)
record(fileURLToPath(import.meta.url))
const source = "export { createDshToolProfile, createDshGrantedToolProfile } from 'mmx-worker-profile'\nexport { default as ToolRuntime } from '@deepseek-ai/dsh-tools'\nexport { default as AgentLoop } from '@deepseek-ai/dsh-agent-loop'\n"
const entry = resolve(cache, `profile-entry-${hash(source)}.mjs`)
if (existsSync(entry)) assert.equal(readFileSync(entry, 'utf8'), source)
else writeFileSync(entry, source, { flag: 'wx' })
const out = mkdtempSync(resolve(cache, 'profile-build-'))
await build({
  configFile: false, root: here, envDir: false, publicDir: false, logLevel: 'silent',
  resolve: { alias: [
    { find: 'mmx-worker-profile', replacement: resolve(here, '../../../integrations/acp_worker/dsh_tool_profile.mjs') },
    { find: '@deepseek-ai/dsh-tools', replacement: resolve(cache, 'donor/index.ts') },
    { find: '@deepseek-ai/dsh-mcp-client', replacement: resolve(cache, 'mcp-donor/index.ts') },
  ] },
  ssr: { noExternal: ['@deepseek-ai/dsh-tools', '@deepseek-ai/dsh-mcp-client', '@deepseek-ai/dsh-agent-loop'] },
  build: { ssr: entry, target: 'node22', outDir: out, emptyOutDir: false,
    sourcemap: false, minify: false, copyPublicDir: false,
    rolldownOptions: { output: { format: 'es', entryFileNames: 'index.mjs' } } },
})
const files = Object.fromEntries(readdirSync(out).filter(name => name.endsWith('.mjs'))
  .sort().map(name => [name, hash(readFileSync(resolve(out, name)))]))
assert.ok(files['index.mjs'])
for (const name of Object.keys(files)) {
  const code = readFileSync(resolve(out, name), 'utf8')
  assert.equal(/from\s*['"](?:mmx-worker-profile|@deepseek-ai\/dsh-(?:tools|mcp-client|agent-loop))['"]/.test(code), false,
    'The profile, patched tools/MCP client, and selected AgentLoop must share one bundled dependency closure')
}
const result = { kind: 'TEST_LOCAL_PROFILE_BUILD', artifact: relative(cache, resolve(out, 'index.mjs')),
  artifact_sha256: files['index.mjs'], files, input_sha256: inputs,
  lock_sha256: core.npm_lock_sha256, mcp_patch_sha256: mcp.patch_sha256,
  agent_loop: { package: agentLoop.package, version: agentLoop.version,
    integrity: agentLoop.integrity, manifest_sha256: hash(readFileSync(resolve(here, 'agent-loop-manifest.json'))) },
  compiler: JSON.parse(readFileSync(resolve(here, 'node_modules/vite/package.json'), 'utf8')).version,
  installed: false, model_requests: 0 }
writeFileSync(resolve(cache, 'profile-build-result.json'), JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify({ success: true, artifact: result.artifact, artifact_sha256: result.artifact_sha256 }))
