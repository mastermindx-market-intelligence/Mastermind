#!/usr/bin/env node
/** Original ACP TypeScript project with only the exact compatibility source replaced. */
import {createRequire} from "node:module";
import {dirname,resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {readFileSync,writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
const here=dirname(fileURLToPath(import.meta.url)),donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw Error("DSH_SOURCE must name the pinned native donor");
const manifest=JSON.parse(readFileSync(resolve(here,"native-acp-source.json"),"utf8"));
const candidate=resolve(here,".cache/native-acp-"+manifest.patch_sha256);
for(const [name,digest] of Object.entries({...manifest.source_sha256,...manifest.output_sha256})){
  if(createHash("sha256").update(readFileSync(resolve(candidate,name))).digest("hex")!==digest)
    throw Error("Native ACP source differs: "+name);
}
const ts=createRequire(resolve(donor,"package.json"))("typescript"),project=resolve(donor,"packages/acp/acp");
const raw=ts.readConfigFile(resolve(project,"tsconfig.json"),ts.sys.readFile);
if(raw.error)throw Error("Native ACP configuration unavailable");
const parsed=ts.parseJsonConfigFileContent(raw.config,ts.sys,project);
const root=resolve(candidate,"packages/acp/acp/src");
const options={...parsed.options,noEmit:true,composite:false,incremental:false,declaration:false,declarationMap:false,
  disableSourceOfProjectReferenceRedirect:true,rootDir:undefined,outDir:undefined,tsBuildInfoFile:undefined,
  typeRoots:[resolve(donor,"node_modules/@types")],
  paths:{...parsed.options.paths,"@deepseek-ai/dsh-acp":[resolve(root,"index.ts")],
    "@deepseek-ai/dsh-acp/src/*":[resolve(root,"*")]}};
const names=parsed.fileNames.map(file=>file.replace(resolve(project,"src"),root));
const program=ts.createProgram({rootNames:names,options,projectReferences:parsed.projectReferences});
const diagnostics=[...parsed.errors,...ts.getPreEmitDiagnostics(program)];
const output=ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:x=>x,getCurrentDirectory:()=>here,getNewLine:()=>"\n"});
writeFileSync(resolve(candidate,"typecheck.log"),output);
console.log("NATIVE_ACP_TYPECHECK_DIAGNOSTICS "+diagnostics.length);if(output)console.log(output);
process.exitCode=diagnostics.length?1:0;
