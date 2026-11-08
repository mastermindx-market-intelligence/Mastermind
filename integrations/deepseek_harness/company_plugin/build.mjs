#!/usr/bin/env node
/**
 * Build with the accepted donor's existing toolchain, without editing its tree.
 * Usage: node build.mjs /absolute/path/to/the/pinned/deepseek-harness
 */
import {createRequire} from "node:module";
import {fileURLToPath,pathToFileURL} from "node:url";
import {dirname,join,resolve} from "node:path";
import {readFile,writeFile,mkdir,realpath,rm} from "node:fs/promises";
import {execFileSync} from "node:child_process";
import {createHash} from "node:crypto";
const DONOR="687f282e8625c6b8d11ff58211a90524be2e4317";
const packageDir=dirname(fileURLToPath(import.meta.url));
const supplied=process.argv[2];
if (!supplied || !supplied.startsWith("/") || process.argv.length!==3) throw new Error("Supply one absolute pinned donor checkout.");
const donor=await realpath(supplied);
if (donor!==resolve(supplied) || execFileSync("git",["-C",donor,"rev-parse","HEAD"],{encoding:"utf8"}).trim()!==DONOR)
  throw new Error("Donor revision or path does not match the approved source.");
if (execFileSync("git",["-C",donor,"status","--porcelain"],{encoding:"utf8"}).trim())
  throw new Error("The donor checkout must be clean.");
const requireDonor=createRequire(join(donor,"package.json"));
const {build}=await import(pathToFileURL(requireDonor.resolve("tsdown")).href);
const ts=requireDonor("typescript");
const outDir=join(packageDir,"lib");
await mkdir(outDir,{recursive:true});
await build({
  cwd:packageDir,config:false,entry:{client:"src/client/index.ts"},outDir,
  format:"cjs",platform:"browser",target:"es2022",dts:false,clean:false,sourcemap:false,
  external:["react","@deepseek-ai/dsh-client-store"],outExtensions:()=>({js:".cjs"}),
});
const emitted=await readFile(join(outDir,"client.cjs"),"utf8");
const bundled='window.__ModuleLoader__.load({id:"@mastermind/dsh-company",factory:(require)=>{\nconst module={exports:{}};const exports=module.exports;\n'+emitted+'\nreturn module.exports;\n}});\n';
await writeFile(join(outDir,"client.js"),bundled);
await rm(join(outDir,"client.cjs"));
await writeFile(join(outDir,"index.js"),"// Client-only company presentation; no host execution capability.\nexport function apply() {}\n");
const sha=bytes=>createHash("sha256").update(bytes).digest("hex");
await build({
  cwd:packageDir,config:false,entry:{"company-peer":"src/company-peer.ts","executive-read-port":"src/executive-read-port.ts"},outDir,
  format:"esm",platform:"node",target:"es2024",dts:false,clean:false,sourcemap:false,
  // Reuse the original native Cordis scope implementation at runtime.
  external:[/^@deepseek-ai\//],
  alias:{"mmx-pinned-native-history":join(donor,"packages/api/session-controller/src/history.ts")},
  // The donor uses TypeScript's standard-decorator transform. Rolldown's
  // syntax lowering alone preserves @Remote, which Node cannot execute.
  plugins:[{name:"mastermind-company-standard-decorators",transform:{order:"pre",handler(code,id){
    if(id.split("?",1)[0]!==join(packageDir,"src/closed-native-history.ts"))return;
    const result=ts.transpileModule(code,{fileName:id,compilerOptions:{
      target:ts.ScriptTarget.ES2024,module:ts.ModuleKind.ESNext,sourceMap:false,
    }});
    return {code:result.outputText,map:null};
  }}}],
  outExtensions:()=>({js:".js"}),
});
// Do not publish a build record for host JavaScript the selected Node cannot parse.
for(const name of ["company-peer.js","executive-read-port.js"])
  execFileSync(process.execPath,["--check",join(outDir,name)],{stdio:"pipe"});
const host=await readFile(join(outDir,"company-peer.js"));
const port=await readFile(join(outDir,"executive-read-port.js"));
const sources=["protocol.ts","index.ts","company-peer.ts","executive-read-port.ts","native-result-content.ts","closed-native-history.ts","client/connection.ts","client/index.ts","client/styles.ts"];
const sourceDigests={};
for(const path of sources)sourceDigests["src/"+path]=sha(await readFile(join(packageDir,"src",path)));
const manifest={
  schema:"mastermind.dsh.company_build.v1",donor_sha:DONOR,plugin:"@mastermind/dsh-company",
  source_sha256:sourceDigests,client_sha256:sha(bundled),
  host_exports:{"./company-peer":{file:"company-peer.js",sha256:sha(host)},
    "./executive-read-port":{file:"executive-read-port.js",sha256:sha(port)}},
  capabilities:["company_project_presentation","company_project_navigation"],
  provider_admission:false,
};
await writeFile(join(outDir,"build-manifest.json"),JSON.stringify(manifest,null,2)+"\n");
console.log("DSH_COMPANY_PLUGIN_BUILT "+manifest.client_sha256);
