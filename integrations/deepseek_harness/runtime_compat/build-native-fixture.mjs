#!/usr/bin/env node
/** Build an explicit test artifact; never install or arm an Executive route. */
import {createRequire} from 'node:module'
import {fileURLToPath, pathToFileURL} from 'node:url'
import {dirname, resolve, join} from 'node:path'
import {readFile, writeFile, mkdir, realpath, readdir} from 'node:fs/promises'
import {execFileSync} from 'node:child_process'
import {createHash} from 'node:crypto'
const root = dirname(fileURLToPath(import.meta.url))
const donor = await realpath(process.argv[2] ?? '')
const manifest = JSON.parse(await readFile(join(root, 'source-manifest.json'), 'utf8'))
if (process.argv.length !== 3 || donor !== resolve(process.argv[2])
  || execFileSync('git', ['-C', donor, 'rev-parse', 'HEAD'], {encoding: 'utf8'}).trim() !== manifest.donor_sha
  || execFileSync('git', ['-C', donor, 'status', '--porcelain'], {encoding: 'utf8'}).trim()) {
  throw new Error('Exact clean full-app donor required')
}
const sha = value => createHash('sha256').update(value).digest('hex')
for (const [file, digest] of Object.entries(manifest.source_sha256)) {
  if (sha(await readFile(join(donor, file))) !== digest) throw new Error('Donor source drift: ' + file)
}
if (sha(await readFile(join(donor, 'pnpm-lock.yaml'))) !== manifest.donor_lock_sha256) throw new Error('Donor lock drift')
for (const patch of manifest.patches) {
  if (sha(await readFile(join(root, patch.file))) !== patch.sha256) throw new Error('Patch drift: ' + patch.file)
}
for (const patch of manifest.patches) for (const [file, digest] of Object.entries(patch.outputs)) {
  if (sha(await readFile(join(root, '.cache/patched', file))) !== digest) throw new Error('Patched source drift: ' + file)
}
const donorRequire = createRequire(join(donor, 'package.json'))
const ts = donorRequire('typescript')
const parsed = ts.readConfigFile(join(donor, 'tsconfig.base.json'), ts.sys.readFile)
if (parsed.error) throw new Error('Donor TypeScript configuration unavailable')
const alias = Object.fromEntries(Object.entries(parsed.config.compilerOptions.paths)
  .filter(([key]) => !key.includes('*')).map(([key, values]) => [key, resolve(donor, values[0])]))
alias['@deepseek-ai/dsh-tools'] = join(root, '.cache/patched/packages/core/tools/src/index.ts')
alias['@deepseek-ai/dsh-mcp-client'] = join(root, '.cache/patched/packages/mcp/mcp-client/src/index.ts')
const sdk = createRequire(join(donor, 'packages/mcp/mcp-client/package.json'))
for (const name of ['@modelcontextprotocol/client', '@modelcontextprotocol/client/stdio']) alias[name] = sdk.resolve(name)
const {build} = await import(pathToFileURL(donorRequire.resolve('tsdown')).href)
const shared = await import(pathToFileURL(join(donor, 'vitest.shared.ts')).href)
const decorators = shared.standardDecoratorPlugin()
const outDir = join(root, '.cache/build')
await mkdir(outDir, {recursive: true})
await build({
  cwd: root, config: false, entry: {'native-agent-fixture': 'native-agent-fixture.mjs'}, outDir,
  format: 'esm', platform: 'node', target: 'es2024', dts: false, clean: false, sourcemap: false,
  alias, deps: {alwaysBundle: () => true, onlyBundle: false},
  plugins: [{name: 'one-native-tools-runtime', resolveId: {order: 'pre', handler(id) {
    for (const [name, relative] of [['@deepseek-ai/dsh-tools', 'packages/core/tools/src'],
      ['@deepseek-ai/dsh-mcp-client', 'packages/mcp/mcp-client/src']]) {
      if (id === name) return join(root, '.cache/patched', relative, 'index.ts')
      const original = join(donor, relative)
      if (id === original || id.startsWith(original + '/')) return join(root, '.cache/patched', relative, id.slice(original.length) || 'index.ts')
    }
  }}}, {name: decorators.name, transform: {order: 'pre', handler: decorators.transform}}],
  outExtensions: () => ({js: '.mjs'}),
  banner: {js: "import {createRequire as __mmxCreateRequire} from 'node:module';const require=__mmxCreateRequire(import.meta.url);"},
})
const files = {}
const sourcePaths = ['native-agent-fixture.mjs', 'fixture-persistence.mjs', 'build-native-fixture.mjs', 'source-manifest.json',
  '../../acp_worker/dsh_native_agent.mjs', '../../acp_worker/dsh_native_attempt.mjs',
  '../../acp_worker/dsh_tool_profile.mjs', '../../acp_worker/dsh_dispatch_preflight.mjs',
  '../../acp_worker/dsh_attempt_overlay.mjs', '../../acp_worker/dsh_mcp_grant.mjs']
for (const file of sourcePaths) files[file] = sha(await readFile(join(root, file)))
const bundle = join(outDir, 'native-agent-fixture.mjs')
const bundleText = await readFile(bundle, 'utf8')
if ([...bundleText.matchAll(/Symbol\(["']@deepseek-ai\/dsh-tools\.scheduler["']\)/g)].length !== 1) {
  throw new Error('Native Agent and admitted tools must share exactly one scheduler identity')
}
// Native llm attribution reads this exact package metadata relative to its bundle.
await writeFile(join(outDir, '../package.json'), await readFile(join(donor, 'packages/llm/llm/package.json')))
const outputs = {'../package.json': sha(await readFile(join(outDir, '../package.json')))}
for (const name of await readdir(outDir)) if (name.endsWith('.mjs')) outputs[name] = sha(await readFile(join(outDir, name)))
const receipt = {schema: 'mastermind.dsh_fullapp_native_fixture.v1',
  donor_sha: manifest.donor_sha, node: process.execPath, node_version: process.version,
  node_sha256: sha(await readFile(process.execPath)), bundle_sha256: sha(await readFile(bundle)),
  sources_sha256: files, output_sha256: outputs, production_armed: false, provider_calls: false}
await writeFile(join(outDir, 'build-manifest.json'), JSON.stringify(receipt, null, 2) + '\n')
console.log('FULLAPP_NATIVE_FIXTURE_BUILT ' + receipt.bundle_sha256)