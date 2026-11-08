#!/usr/bin/env node
/** Launch the staged native app with its existing persistent auth/session owners. */
import {readFile, readlink, lstat, realpath} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {createReadStream} from 'node:fs'
import {dirname, join, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawn} from 'node:child_process'
const root = dirname(fileURLToPath(import.meta.url))
const hash = async path => {
  const h = createHash('sha256')
  for await (const block of createReadStream(path)) h.update(block)
  return h.digest('hex')
}
const config = JSON.parse(await readFile(join(root, 'app.json'), 'utf8'))
const closure = JSON.parse(await readFile(join(root, 'package-manifest.json'), 'utf8'))
if (process.argv.length > 3 || (process.argv[2] !== undefined && process.argv[2] !== '--check-only')
  || config.schema !== 'mastermind.dsh_attended_package.v1'
  || closure.schema !== 'mastermind.dsh_attended_package_closure.v1'
  || config.donor_sha !== '687f282e8625c6b8d11ff58211a90524be2e4317'
  || config.release !== root || await realpath(root) !== root
  || config.execution !== 'native-attended' || config.company_worker_admission !== false
  || config.node !== process.execPath || await hash(config.node) !== config.node_sha256) throw new Error('Native app package identity refused')
const fullCheck = process.argv[2] === '--check-only'
// Full closure verification belongs to staging/qualification. Routine native
// launches check their immutable controls and entry artifacts without reading
// every development dependency before showing the user's chat.
const entryFiles = new Set(['app.json', 'launch_attended.mjs', 'company.patch.yml',
  'app/apps/cli/lib/bin.js', 'app/apps/web/dist/index.html'])
for (const required of entryFiles) if (!(required in closure.files)) throw new Error('Native entry missing')
for (const [relative, expected] of Object.entries(closure.files)) {
  if (!fullCheck && !entryFiles.has(relative) && !relative.startsWith('company_plugin/')) continue
  if (relative.startsWith('/') || relative.split('/').includes('..')) throw new Error('Package path refused')
  const path = join(root, relative), info = await lstat(path)
  if ('symlink' in expected) {
    if (!info.isSymbolicLink() || await readlink(path) !== expected.symlink
      || !(await realpath(path)).startsWith(root + '/')) throw new Error('Package link refused')
  } else if (!info.isFile() || info.isSymbolicLink() || await hash(path) !== expected.sha256) {
    throw new Error('Native app package changed: ' + relative)
  }
}
const state = config.state
if (typeof state !== 'string' || resolve(state) !== state || await realpath(state) !== state
  || state === root || state.startsWith(root + '/') || (await lstat(state)).mode & 0o077) throw new Error('Private native app state refused')
for (const name of ['home', 'state', 'workspace', 'logs']) {
  const path = join(state, name)
  if (await realpath(path) !== path || !(await lstat(path)).isDirectory()) throw new Error('Native state directory refused')
}
if (await hash(join(root, 'company.patch.yml')) !== config.company_patch_sha256) throw new Error('Company app overlay changed')
if (process.argv[2] === '--check-only') {
  console.log(JSON.stringify({schema: 'mastermind.dsh_attended_package_check.v1', files: Object.keys(closure.files).length,
    donor_sha: config.donor_sha, installed: false, provider_calls: 0}))
} else {
  // The native credential service, not ambient model keys, owns provider setup.
  // The launch URL is private output: launchd sends it only to the 0700 state logs.
  const url = new URL(config.public_url)
  const child = spawn(config.node, [join(root, 'app/apps/cli/lib/bin.js'), 'web',
    '--patch', join(root, 'company.patch.yml'), '--host', '127.0.0.1', '--port', String(config.port),
    '--public-url', url.href, '--trusted-host', url.host, '--no-open'], {
    cwd: join(state, 'workspace'), stdio: 'inherit',
    env: {HOME: join(state, 'home'), DSH_HOME: join(state, 'state'),
      PATH: dirname(config.node) + ':/usr/bin:/bin', LANG: 'en_US.UTF-8'},
  })
  // Forward desktop lifecycle signals to the same native child; never respawn.
  const interrupt = () => child.kill('SIGINT')
  const terminate = () => child.kill('SIGTERM')
  process.on('SIGINT', interrupt); process.on('SIGTERM', terminate)
  child.on('error', () => { process.exitCode = 1 })
  child.on('exit', (code, signal) => {
    process.off('SIGINT', interrupt); process.off('SIGTERM', terminate)
    process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 143)
  })
}
