#!/usr/bin/env node
/** Prepare a new disposable web profile for the existing no-credential launcher. */
import {fileURLToPath} from "node:url";
import {dirname,join,resolve} from "node:path";
import {readFile,writeFile,mkdir,realpath} from "node:fs/promises";
import {createHash} from "node:crypto";
const packageDir=dirname(fileURLToPath(import.meta.url));
const supplied=process.argv[2];
if(!supplied || !supplied.startsWith("/") || process.argv.length!==3) throw new Error("Supply one new absolute preview directory.");
const root=resolve(supplied);
if(await realpath(dirname(root))!==dirname(root)) throw new Error("Preview parent must not be symlinked.");
const manifest=JSON.parse(await readFile(join(packageDir,"lib/build-manifest.json"),"utf8"));
const hash=bytes=>createHash("sha256").update(bytes).digest("hex");
if(manifest.schema!=="mastermind.dsh.company_build.v1" || manifest.donor_sha!=="687f282e8625c6b8d11ff58211a90524be2e4317" ||
   hash(await readFile(join(packageDir,"lib/client.js")))!==manifest.client_sha256) throw new Error("Build the company plugin from the pinned donor first.");
for(const [path,digest] of Object.entries(manifest.source_sha256)){
  if(!/^src\/(?:client\/)?[a-z.-]+\.ts$/.test(path) || hash(await readFile(join(packageDir,path)))!==digest) throw new Error("Plugin source changed after build.");
}
// Creation is exclusive: no overwrite or merge with a current user's profile.
await mkdir(root,{mode:0o700});
await mkdir(join(root,"state/profiles/web"),{recursive:true,mode:0o700});
const patch=[{insert:[{id:"mastermind-company",name:join(packageDir,"lib/index.js"),config:{}}]}];
await writeFile(join(root,"state/profiles/web/cordis.patch.yml"),JSON.stringify(patch,null,2)+"\n",{mode:0o600,flag:"wx"});
console.log("DSH_COMPANY_PREVIEW_PREPARED "+root);
