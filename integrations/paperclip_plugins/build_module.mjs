#!/usr/bin/env node
// build_module.mjs — one builder for every Mastermind Paperclip module.
//
// Run from a module directory (or pass the directory as $1):
//   node ../build_module.mjs            # from integrations/paperclip_plugins/<name>/
//
// Produces, from src/manifest.js, src/worker.js and src/ui.jsx:
//   dist/manifest.js  ESM, pure data (no imports)
//   dist/worker.js    ESM, node24, SDK bundled in
//   dist/ui/index.js  ESM, browser, SDK-UI + react external (host import map)
//
// esbuild and the plugin SDK come from the installed Paperclip CLI tree
// (PAPERCLIP_CLI_ROOT, default ~/.paperclip/cli/current). No npm install
// needed inside the module — that is the point: modules build with the same
// SDK version the running shell loads.
import { existsSync } from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { pathToFileURL } from 'node:url'

const moduleDir = path.resolve(process.argv[2] || process.cwd())
const cliRoot = process.env.PAPERCLIP_CLI_ROOT
  || path.join(os.homedir(), '.paperclip', 'cli', 'current')

function findEsbuild() {
  const candidates = [
    path.join(cliRoot, 'node_modules', 'esbuild', 'lib', 'main.js'),
    path.join(cliRoot, 'node_modules', '@paperclipai', 'server', 'node_modules', 'esbuild', 'lib', 'main.js'),
    path.join(cliRoot, 'node_modules', '@paperclipai', 'adapter-utils', 'node_modules', 'esbuild', 'lib', 'main.js'),
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  console.error(`build_module: no esbuild under ${cliRoot}; set PAPERCLIP_CLI_ROOT to the Paperclip CLI root`)
  process.exit(1)
}

const esbuild = await import(pathToFileURL(findEsbuild()))

// Specifiers the host rewrites via its import map at UI load time. They MUST
// stay bare and external in dist/ui/index.js.
const UI_EXTERNAL = [
  '@paperclipai/plugin-sdk/ui',
  '@paperclipai/plugin-sdk/ui/hooks',
  'react',
  'react-dom',
  'react/jsx-runtime',
]

const sdkRoot = path.join(cliRoot, 'node_modules', '@paperclipai', 'plugin-sdk')
// Bundle the exact SDK the installed shell ships, no matter where this module
// directory lives. Worker build only: an esbuild alias matches as a path
// prefix, so applying it to the UI build would also remap the external
// '@paperclipai/plugin-sdk/ui' specifier into dist/index.js/ui.
const alias = {
  '@paperclipai/plugin-sdk': path.join(sdkRoot, 'dist', 'index.js'),
}

const dist = path.join(moduleDir, 'dist')
const common = { bundle: true, format: 'esm', sourcemap: true, minify: false, logLevel: 'info' }

/** @type {import('esbuild').BuildOptions[]} */
const builds = [
  {
    ...common,
    entryPoints: [path.join(moduleDir, 'src', 'manifest.js')],
    outfile: path.join(dist, 'manifest.js'),
    platform: 'node',
    target: 'node24',
  },
  {
    ...common,
    entryPoints: [path.join(moduleDir, 'src', 'worker.js')],
    outfile: path.join(dist, 'worker.js'),
    platform: 'node',
    target: 'node24',
    external: ['react', 'react-dom'],
    alias,
  },
]
const uiEntry = path.join(moduleDir, 'src', 'ui.jsx')
if (existsSync(uiEntry)) {
  builds.push({
    ...common,
    entryPoints: [uiEntry],
    outfile: path.join(dist, 'ui', 'index.js'),
    platform: 'browser',
    target: 'es2022',
    jsx: 'automatic',
    external: UI_EXTERNAL,
  })
}

for (const b of builds) {
  const r = await esbuild.build(b)
  if (r.errors.length > 0) process.exit(1)
}
console.log(`build_module: built ${moduleDir} -> ${dist}`)
