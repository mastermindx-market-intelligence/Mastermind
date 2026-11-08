#!/usr/bin/env node
/** Exact original native Agent and AgentLoop projects with captured host source. */

import {createRequire} from "node:module";
import {readFileSync,existsSync} from "node:fs";
import {resolve,dirname} from "node:path";
import {fileURLToPath} from "node:url";
import {createHash} from "node:crypto";
const donor=process.env.DSH_SOURCE,here=dirname(fileURLToPath(import.meta.url));
if(!donor||!donor.startsWith("/"))throw Error("DSH_SOURCE must name the pinned native donor");
const manifest=JSON.parse(readFileSync(resolve(here,"native-host-source.json"),"utf8"));
const candidate=resolve(here,".cache/native-host-"+manifest.patch_sha256);
for(const [name,digest] of Object.entries({...manifest.source_sha256,...manifest.output_sha256})){
 if(createHash("sha256").update(readFileSync(resolve(candidate,name))).digest("hex")!==digest)throw Error("Host source changed: "+name);
}
const ts=createRequire(resolve(donor,"package.json"))("typescript");
const base=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(base.error)throw Error("Original source path configuration unavailable");
const patched=["packages/core/agent","packages/core/agent-loop","packages/llm/llm","packages/llm/llm-deepseek","packages/credentials/deepseek-account","packages/credentials/deepseek-account-platform","packages/llm/llm-deepseek-account"];
const projectCache=new Map();
function declarationPath(value){
 value=value.replace(/^\.\//,"");
 const match=/\/src(?:\/|$)/.exec(value);
 if(!match)return resolve(donor,value);
 const marker=match.index,relative=value.slice(0,marker),suffix=value.slice(marker+4).replace(/^\//,"")||"index.ts";
 if(relative.includes("*"))return resolve(donor,value);
 if(patched.includes(relative))return resolve(candidate,value);
 let parsed=projectCache.get(relative);
 if(!parsed){
  const project=resolve(donor,relative),file=ts.readConfigFile(resolve(project,"tsconfig.json"),ts.sys.readFile);
  if(file.error)throw Error("Original dependency project unavailable: "+relative);
  parsed=ts.parseJsonConfigFileContent(file.config,ts.sys,project);projectCache.set(relative,parsed);
 }
 const directory=parsed.options.declarationDir??parsed.options.outDir??resolve(donor,relative,"lib/types");
 const output=resolve(directory,suffix.replace(/\.tsx?$/,".d.ts"));
 return output.includes("*")||existsSync(output)?output:resolve(donor,value);
}
const sourcePaths=Object.fromEntries(Object.entries(base.config.compilerOptions.paths).map(([key,values])=>[key,values.map(declarationPath)]));
let total=0;
for(const name of ["packages/core/agent","packages/core/agent-loop","packages/llm/llm","packages/llm/llm-deepseek","packages/credentials/deepseek-account","packages/credentials/deepseek-account-platform","packages/llm/llm-deepseek-account"]){
 const project=resolve(donor,name),raw=ts.readConfigFile(resolve(project,"tsconfig.json"),ts.sys.readFile);
 if(raw.error)throw Error("Host TypeScript project unavailable");
 const parsed=ts.parseJsonConfigFileContent(raw.config,ts.sys,project);
 const root=resolve(candidate,name,"src");
 const options={...parsed.options,noEmit:true,composite:false,incremental:false,declaration:false,declarationMap:false,
 disableSourceOfProjectReferenceRedirect:true,rootDir:undefined,outDir:undefined,tsBuildInfoFile:undefined,
 typeRoots:[resolve(donor,"node_modules/@types")],
 paths:sourcePaths};
 const names=parsed.fileNames.map(file=>file.replace(resolve(project,"src"),root));
 const host=ts.createCompilerHost(options);
 host.resolveModuleNames=(modules,containingFile)=>modules.map(module=>{
  const found=ts.resolveModuleName(module,containingFile,options,host).resolvedModule;
  if(!found)return found;
  for(const dependency of patched){
   const prefix=resolve(donor,dependency,"lib/types")+"/";
   if(found.resolvedFileName.startsWith(prefix)){
    const source=resolve(candidate,dependency,"src",found.resolvedFileName.slice(prefix.length).replace(/\.d\.ts$/,".ts"));
    if(!existsSync(source))throw Error("Patched declaration has no exact source: "+source);
    return {...found,resolvedFileName:source,extension:ts.Extension.Ts};
   }
  }
  return found;
 });
 const program=ts.createProgram({rootNames:names,options,host});
 const diagnostics=[...parsed.errors,...ts.getPreEmitDiagnostics(program)];total+=diagnostics.length;
 console.log("PROJECT "+name+" DIAGNOSTICS "+diagnostics.length);
 console.log(ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:x=>x,getCurrentDirectory:()=>here,getNewLine:()=>"\n"}));
}
process.exitCode=total?1:0;
