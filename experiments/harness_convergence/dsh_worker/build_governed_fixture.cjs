/** Build only an explicitly provisioned, provider-free dependency supply.
 * Usage: node build_governed_fixture.cjs /absolute/supply /absolute/esbuild
 * No install, network request, provider call or source-carrier modification.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const {createHash} = require('node:crypto')
const [root, esbuildPath] = process.argv.slice(2)
assert.ok(path.isAbsolute(root) && path.isAbsolute(esbuildPath))
const esbuild = require(esbuildPath)
const sha = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const profile = path.join(root,'profile1060.mjs')
assert.equal(sha(profile),'c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c')
for (const name of ['governed_acp_fixture.mjs','scoped_profile.test.mjs']) {
  esbuild.buildSync({entryPoints:[path.join(__dirname,name)],
    outfile:path.join(root,'runtime/build',name),bundle:true,platform:'node',format:'esm',target:'node22',
    tsconfig:path.join(root,'donor/tsconfig.base.json'),
    alias:{'@mmx/dsh-grant-profile':profile},
    nodePaths:[path.join(root,'node_modules'),path.join(root,'donor/node_modules/.pnpm/node_modules')],
    banner:{js:"import { createRequire as __mmxCreateRequire } from 'node:module'; const require = __mmxCreateRequire(import.meta.url);"}})
}
const manifestPath=path.join(root,'supply-manifest.json')
const manifest=JSON.parse(fs.readFileSync(manifestPath))
for (const name of ['governed_acp_fixture.mjs','scoped_profile.test.mjs']) {
  const relative='runtime/build/'+name
  manifest.files[relative]=sha(path.join(root,relative))
}
manifest.fixture_sources=Object.fromEntries(['governed_acp_fixture.mjs','scoped_profile.mjs',
  'scoped_profile.test.mjs','build_governed_fixture.cjs'].map(name=>[name,sha(path.join(__dirname,name))]))
fs.writeFileSync(manifestPath,JSON.stringify(manifest,null,2)+'\n')
