#!/usr/bin/env node
/** Exact original native Agent and AgentLoop projects with captured host source. */

import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
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
let total=0;
for(const name of ["packages/core/agent","packages/core/agent-loop"]){
 const project=resolve(donor,name),raw=ts.readConfigFile(resolve(project,"tsconfig.json"),ts.sys.readFile);
 if(raw.error)throw Error("Host TypeScript project unavailable");
 const parsed=ts.parseJsonConfigFileContent(raw.config,ts.sys,project);
 const root=resolve(candidate,name,"src");
 const options={...parsed.options,noEmit:true,composite:false,incremental:false,declaration:false,declarationMap:false,
 disableSourceOfProjectReferenceRedirect:true,rootDir:undefined,outDir:undefined,tsBuildInfoFile:undefined,
 typeRoots:[resolve(donor,"node_modules/@types")],
 paths:{...parsed.options.paths,
 "@deepseek-ai/dsh-agent":[resolve(candidate,"packages/core/agent/src/index.ts")],
 "@deepseek-ai/dsh-agent/src/*":[resolve(candidate,"packages/core/agent/src/*")],
 "@deepseek-ai/dsh-agent-loop":[resolve(candidate,"packages/core/agent-loop/src/index.ts")],
 "@deepseek-ai/dsh-agent-loop/src/*":[resolve(candidate,"packages/core/agent-loop/src/*")]}};
 const names=parsed.fileNames.map(file=>file.replace(resolve(project,"src"),root));
 const program=ts.createProgram({rootNames:names,options,projectReferences:parsed.projectReferences});
 const diagnostics=[...parsed.errors,...ts.getPreEmitDiagnostics(program)];total+=diagnostics.length;
 console.log("PROJECT "+name+" DIAGNOSTICS "+diagnostics.length);
 console.log(ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:x=>x,getCurrentDirectory:()=>here,getNewLine:()=>"\n"}));
}
process.exitCode=total?1:0;
