#!/usr/bin/env node
/** Typecheck the actual patched host package and its current company reader. */
import {createRequire} from "node:module";
import {dirname,resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {readFileSync,writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
const here=dirname(fileURLToPath(import.meta.url)),donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw new Error("DSH_SOURCE must name the pinned native donor");
const manifest=JSON.parse(readFileSync(resolve(here,"native-session-source.json"),"utf8"));
for(const [name,digest] of Object.entries(manifest.output_sha256)){
  if(createHash("sha256").update(readFileSync(resolve(here,".cache/native-session",name))).digest("hex")!==digest)
    throw new Error("Prepared native source differs: "+name);
}
const ts=createRequire(resolve(donor,"package.json"))("typescript");
const project=resolve(donor,"packages/api/session-controller");
const raw=ts.readConfigFile(resolve(project,"tsconfig.host.json"),ts.sys.readFile);
if(raw.error)throw new Error("Native host typecheck configuration unavailable");
const parsed=ts.parseJsonConfigFileContent(raw.config,ts.sys,project);
const root=resolve(here,".cache/native-session/packages/api/session-controller/src");
const reader=resolve(here,"../company_plugin/src/company-peer.ts");
const options={...parsed.options,noEmit:true,composite:false,incremental:false,declaration:false,declarationMap:false,
  disableSourceOfProjectReferenceRedirect:true,rootDir:undefined,outDir:undefined,tsBuildInfoFile:undefined,
  typeRoots:[resolve(donor,"node_modules/@types")],
  paths:{...parsed.options.paths,
    "@deepseek-ai/dsh-api-session-controller":[resolve(root,"index.ts")],
    "@deepseek-ai/dsh-api-session-controller/src/*":[resolve(root,"*")],
  }};
const names=parsed.fileNames.map(file=>file.replace(resolve(project,"src"),root));
names.push(reader,resolve(here,"../company_plugin/src/executive-read-port.ts"));
const program=ts.createProgram({rootNames:names,options,projectReferences:parsed.projectReferences});
const diagnostics=[...parsed.errors,...ts.getPreEmitDiagnostics(program)];
const output=ts.formatDiagnosticsWithColorAndContext(diagnostics,{
  getCanonicalFileName:x=>x,getCurrentDirectory:()=>here,getNewLine:()=>"\n",
});
writeFileSync(resolve(here,".cache/native-session/typecheck.log"),output);
console.log("NATIVE_SESSION_TYPECHECK_DIAGNOSTICS "+diagnostics.length);
if(output)console.log(output);
process.exitCode=diagnostics.length?1:0;
