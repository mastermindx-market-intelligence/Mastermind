import { build, version } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const staticAssets = {
  'browser-link-bootstrap.js': 'extension/websol-bootstrap.js',
  'browser-link/popup.html': 'extension/popup.html',
  'browser-link/popup.css': 'extension/popup.css',
  'browser-link/popup.mjs': 'extension/popup.mjs',
};

// Pure build result by default. This bundles our own modules, never Web Sol's
// version-sensitive classic worker, instance config, or native host.
export async function buildWebSolLink() {
  if (version !== '0.28.2') throw new Error('Browser Link build dependency drift');
  const result = await build({
    absWorkingDir: here,
    entryPoints: ['extension/websol-entry.mjs'],
    outfile: 'dist/browser-link/worker.bundle.js',
    bundle: true, format: 'iife', platform: 'browser', target: 'chrome116',
    charset: 'ascii', legalComments: 'inline', minify: false,
    sourcemap: false, metafile: true, write: false, logLevel: 'silent',
  });
  if (result.outputFiles.length !== 1 || Object.values(result.metafile.outputs).some(row => row.imports.length)) {
    throw new Error('Browser Link build must be a self-contained classic worker');
  }
  const assets = {'browser-link/worker.bundle.js': Buffer.from(result.outputFiles[0].contents)};
  for (const [name, source] of Object.entries(staticAssets)) assets[name] = await readFile(resolve(here, source));
  const sources = [...new Set([...Object.keys(result.metafile.inputs), ...Object.values(staticAssets), 'build.mjs', 'package.json', 'package-lock.json'])].sort();
  const sourceDigests = {};
  for (const source of sources) sourceDigests[source] = digest(await readFile(resolve(here, source)));
  return {
    assets,
    receipt: {
      schema: 'mastermind.browser_link_build.v1',
      compiler: 'esbuild', compiler_version: version,
      source_digests: sourceDigests,
      asset_digests: Object.fromEntries(Object.entries(assets).sort().map(([name, bytes]) => [name, digest(bytes)])),
      is_installation: false,
    },
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 2) throw new Error('Build has no deployment or installation flags');
  const {assets,receipt} = await buildWebSolLink();
  for (const [name, bytes] of Object.entries(assets)) {
    const destination = resolve(here, 'dist', name);
    await mkdir(dirname(destination), {recursive:true});
    await writeFile(destination, bytes);
  }
  await writeFile(resolve(here,'dist/build-info.json'), JSON.stringify(receipt,null,2)+'\n');
  process.stdout.write(JSON.stringify({schema:receipt.schema,assets:Object.keys(assets).length,is_installation:false})+'\n');
}
