import {defineConfig} from "vitest/config";
import {createRequire} from "node:module";
import {resolve,dirname} from "node:path";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {fileURLToPath,pathToFileURL} from "node:url";
const donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw new Error("DSH_SOURCE must name the pinned native donor");
const here=dirname(fileURLToPath(import.meta.url));
const manifest=JSON.parse(readFileSync(resolve(here,"native-session-source.json"),"utf8"));
const original=resolve(donor,"packages/api/session-controller/src");
const preimage=process.env.MMX_NATIVE_SESSION_PREIMAGE==="1";
const candidate=preimage?original:resolve(here,".cache/native-session/packages/api/session-controller/src");
for(const [name,digest] of Object.entries(preimage?manifest.source_sha256:manifest.output_sha256)){
  const file=resolve(preimage?donor:resolve(here,".cache/native-session"),name);
  if(createHash("sha256").update(readFileSync(file)).digest("hex")!==digest)
    throw new Error("Native session test input differs: "+name);
}
const requireDonor=createRequire(resolve(donor,"package.json")),ts=requireDonor("typescript");
const parsed=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(parsed.error)throw new Error("Native source paths unavailable");
const aliases=Object.entries(parsed.config.compilerOptions.paths).filter(([name])=>!name.includes("*")).map(([name,paths])=>({
  find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:name==="@deepseek-ai/dsh-api-session-controller"?resolve(candidate,"index.ts"):resolve(donor,(paths as string[])[0]),
}));
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
export default defineConfig({
  resolve:{alias:[
    {find:"mmx-native-test-remote",replacement:resolve(donor,"packages/api/session-controller/tests/test-remote.ts")},
    {find:/^@deepseek-ai\/dsh-api-session-controller\/src\//,replacement:candidate+"/"},
    ...aliases,
  ]},
  plugins:[{name:"original-native-session-overlay",enforce:"pre",resolveId(id,importer){
    const path=id.startsWith(".")&&importer?resolve(dirname(importer),id):id.startsWith("/")?id:undefined;
    if(path&&(path===original||path.startsWith(original+"/")))return candidate+path.slice(original.length);
  }},shared.standardDecoratorPlugin()],
  test:{environment:"node",include:["native-session-generation.test.ts"],maxWorkers:1,fileParallelism:false,
    testTimeout:15000,hookTimeout:15000,execArgv:shared.vitestExecArgv},
});
