#!/usr/bin/env node
/** Build an explicit test artifact; never install or arm an Executive route. */
import {createRequire} from 'node:module'
import {fileURLToPath, pathToFileURL} from 'node:url'
import {dirname, resolve, join, relative} from 'node:path'
import {readFile, writeFile, mkdir, realpath, readdir, copyFile, lstat} from 'node:fs/promises'
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
const buildOptions = {
  cwd: root, config: false, outDir,
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
}
await build({...buildOptions, clean: true, entry: {'native-agent-fixture': 'native-agent-fixture.mjs'}})
await build({...buildOptions, entry: {'native-history-fixture': 'native-history-fixture.mjs'}})
// The unchanged native JSONL owner loads its platform flock addon lazily.
// Copy the donor's verified platform payload into this artifact's own module
// closure; an ambient dependency or a substitute lock cannot qualify recovery.
const nativeName = '@deepseek-ai/node-addon-system-' + process.platform + '-' + process.arch
const nativeRequire = createRequire(join(donor, 'native/system/packages/entry/package.json'))
const nativeManifest = nativeRequire.resolve(nativeName + '/package.json')
const nativeRoot = await realpath(dirname(nativeManifest))
if (!nativeRoot.startsWith(join(donor, 'native/system/packages') + '/')) throw new Error('Native addon source escaped donor')
execFileSync(process.execPath, [join(donor, 'native/system/scripts/verify-launcher-binary.mjs'), nativeRoot], {stdio: 'inherit'})
const nativeMetadata = JSON.parse(await readFile(nativeManifest, 'utf8'))
const prebuilds = JSON.parse(await readFile(join(nativeRoot, 'prebuilds.json'), 'utf8'))
if (nativeMetadata.name !== nativeName || prebuilds.platform !== process.platform + '-' + process.arch) {
  throw new Error('Native platform package identity differs')
}
const nativeOutputs = {}
for (const name of ['package.json', 'prebuilds.json', 'LICENSE', ...prebuilds.binaries.map(row => row.path)]) {
  const source = join(nativeRoot, name)
  if (resolve(source) !== source || !source.startsWith(nativeRoot + '/')
    || !(await lstat(source)).isFile() || await realpath(source) !== source) throw new Error('Native payload path refused')
  const output = 'node_modules/' + nativeName + '/' + name
  const destination = join(outDir, output)
  await mkdir(dirname(destination), {recursive: true})
  await copyFile(source, destination)
  nativeOutputs[output] = sha(await readFile(destination))
  if (nativeOutputs[output] !== sha(await readFile(source))) throw new Error('Native payload copy changed')
}
const files = {}
const sourcePaths = ['native-agent-fixture.mjs', 'native-history-fixture.mjs', 'fixture-persistence.mjs', 'build-native-fixture.mjs', 'source-manifest.json',
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
const outputs = {'../package.json': sha(await readFile(join(outDir, '../package.json'))), ...nativeOutputs}
for (const name of await readdir(outDir)) if (name.endsWith('.mjs')) outputs[name] = sha(await readFile(join(outDir, name)))
const receipt = {schema: 'mastermind.dsh_fullapp_native_fixture.v1',
  donor_sha: manifest.donor_sha, node: process.execPath, node_version: process.version,
  node_sha256: sha(await readFile(process.execPath)), bundle_sha256: sha(await readFile(bundle)),
  sources_sha256: files, output_sha256: outputs,
  native_addon: {name: nativeName, version: nativeMetadata.version, donor_path: relative(donor, nativeRoot),
    verifier: 'native/system/scripts/verify-launcher-binary.mjs'},
  production_armed: false, provider_calls: false}
await writeFile(join(outDir, 'build-manifest.json'), JSON.stringify(receipt, null, 2) + '\n')
console.log('FULLAPP_NATIVE_FIXTURE_BUILT ' + receipt.bundle_sha256)