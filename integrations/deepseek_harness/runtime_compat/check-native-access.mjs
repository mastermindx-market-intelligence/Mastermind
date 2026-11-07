#!/usr/bin/env node
/** Strict native typecheck for the composed host, access and Session owners. */
import {createRequire} from "node:module";
import {dirname,resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {readFileSync,writeFileSync,existsSync} from "node:fs";
import {createHash} from "node:crypto";
const here=dirname(fileURLToPath(import.meta.url)),donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw Error("DSH_SOURCE must name the pinned native donor");
const access=JSON.parse(readFileSync(resolve(here,"native-access-source.json"),"utf8"));
const hostBytes=readFileSync(resolve(here,"native-host-source.json"));
if(createHash("sha256").update(hostBytes).digest("hex")!==access.host_manifest_sha256)
  throw Error("Native access host composition differs");
const host=JSON.parse(hostBytes.toString()),session=JSON.parse(readFileSync(resolve(here,"native-session-source.json"),"utf8"));
const candidate=resolve(here,".cache/native-access",access.patch_sha256);
const sessionRoot=access.schema!=="mastermind.dsh_native_access_source.v1"?candidate:resolve(here,".cache/native-session");
for(const [root,files] of [
  [candidate,{...host.source_sha256,...host.output_sha256,...access.base_sha256,...access.output_sha256}],
  [sessionRoot,{...session.source_sha256,...session.output_sha256,...(sessionRoot===candidate?access.output_sha256:{})}],
])for(const [name,digest] of Object.entries(files)){
  if(createHash("sha256").update(readFileSync(resolve(root,name))).digest("hex")!==digest)
    throw Error("Native source differs: "+name);
}
const ts=createRequire(resolve(donor,"package.json"))("typescript");
const packages=["packages/core/agent","packages/core/agent-loop","apps/cli","packages/typert/protocol",
  "packages/client/connection","packages/api/remote-access","packages/api/gateway","packages/api/remotes",
  "packages/api/session-controller",...(["mastermind.dsh_native_access_source.v3","mastermind.dsh_native_access_source.v4"].includes(access.schema)?["packages/client/file-upload"]:[]),
  ...(access.schema==="mastermind.dsh_native_access_source.v4"?["packages/client/ui-deliverables"]:[])];
const configs=packages.map(name=>{
  const root=resolve(donor,name),config=existsSync(resolve(root,"tsconfig.host.json"))?"tsconfig.host.json":"tsconfig.json";
  const raw=ts.readConfigFile(resolve(root,config),ts.sys.readFile);
  if(raw.error)throw Error("Native type configuration unavailable");
  return ts.parseJsonConfigFileContent(raw.config,ts.sys,root);
});
const redirect=path=>{
  const relative=path.slice(donor.length+1),sessionPath="packages/api/session-controller/src";
  if(relative===sessionPath||relative.startsWith(sessionPath+"/"))return resolve(sessionRoot,relative);
  if(packages.some(pkg=>path===resolve(donor,pkg,"src")||path.startsWith(resolve(donor,pkg,"src")+"/")))
    return resolve(candidate,relative);
  // Unmodified dependencies retain the declarations produced by their own native
  // project settings; patched packages share one source/module identity.
  const source=path.match(/^(.*)\/src(?:\/(.*))?$/);
  if(source){
    const tail=source[2]??"index.ts";
    const declaration=resolve(source[1],"lib/types",tail.replace(/\.tsx?$/,".d.ts"));
    if(existsSync(declaration))return declaration;
  }
  return path;
};
const options={...configs[0].options,noEmit:true,composite:false,incremental:false,declaration:false,declarationMap:false,
  disableSourceOfProjectReferenceRedirect:true,rootDir:undefined,outDir:undefined,tsBuildInfoFile:undefined,
  typeRoots:[resolve(donor,"node_modules/@types")],
  paths:Object.fromEntries(Object.entries(configs[0].options.paths).map(([name,values])=>[
    name,values.map(value=>redirect(resolve(donor,value))),
  ]))};
const names=configs.flatMap(config=>config.fileNames.map(redirect));
// Resolve one source graph: references to original donor declaration outputs would
// otherwise give the patched protocol and its augmentations two module identities.
const program=ts.createProgram({rootNames:names,options});
const diagnostics=[...configs.flatMap(x=>x.errors),...ts.getPreEmitDiagnostics(program)];
const output=ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:x=>x,getCurrentDirectory:()=>here,getNewLine:()=>"\n"});
writeFileSync(resolve(candidate,"typecheck.log"),output);
console.log("NATIVE_ACCESS_TYPECHECK_DIAGNOSTICS "+diagnostics.length);if(output)console.log(output);
process.exitCode=diagnostics.length?1:0;
