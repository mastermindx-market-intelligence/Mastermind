import {defineConfig} from "vitest/config";
import {createRequire} from "node:module";
import {resolve,dirname} from "node:path";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {fileURLToPath,pathToFileURL} from "node:url";
const donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw Error("DSH_SOURCE must name the pinned native donor");
const here=dirname(fileURLToPath(import.meta.url));
const manifest=JSON.parse(readFileSync(resolve(here,"native-host-source.json"),"utf8"));
const preimage=process.env.MMX_NATIVE_HOST_PREIMAGE==="1";
const candidate=preimage?donor:resolve(here,".cache/native-host-"+manifest.patch_sha256);
for(const [name,digest] of Object.entries(preimage?manifest.source_sha256:{...manifest.source_sha256,...manifest.output_sha256})){
  if(createHash("sha256").update(readFileSync(resolve(candidate,name))).digest("hex")!==digest)
    throw Error("Native host source differs: "+name);
}
const donorRequire=createRequire(resolve(donor,"package.json")),ts=donorRequire("typescript");
const parsed=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(parsed.error)throw Error("Native paths unavailable");
const roots=["packages/core/agent/src","packages/core/agent-loop/src","apps/cli/src",
  "packages/typert/protocol/src","packages/api/remote-access/src","packages/api/gateway/src","packages/client/connection/src","packages/llm/llm/src","packages/llm/llm-deepseek/src","packages/credentials/deepseek-account/src","packages/credentials/deepseek-account-platform/src","packages/llm/llm-deepseek-account/src"];
const redirect=(path:string)=>roots.some(root=>path===resolve(donor,root)||path.startsWith(resolve(donor,root)+"/"))
  ?resolve(candidate,path.slice(donor.length+1)):path;
const aliases=Object.entries(parsed.config.compilerOptions.paths).filter(([name])=>!name.includes("*")).map(([name,paths])=>({
  find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:redirect(resolve(donor,(paths as string[])[0])),
}));
const sdkRequire=createRequire(resolve(donor,"packages/acp/acp/package.json"));
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
export default defineConfig({
  resolve:{alias:[
    {find:"@agentclientprotocol/sdk",replacement:sdkRequire.resolve("@agentclientprotocol/sdk")},
    {find:"mmx-original-acp",replacement:resolve(donor,"packages/acp/acp/src/index.ts")},
    {find:"mmx-native-deepseek-helpers",replacement:resolve(donor,"packages/llm/llm-deepseek/tests/helpers.ts")},
    {find:"mmx-native-test-remote",replacement:resolve(donor,"packages/api/session-controller/tests/test-remote.ts")},
    {find:"mmx-native-browser-credentials",replacement:resolve(donor,"packages/api/gateway/tests/browser-credentials.ts")},
    {find:"mmx-profile-boot",replacement:resolve(candidate,"apps/cli/src/profile-boot.ts")},
    ...aliases,
  ]},
  plugins:[{name:"original-host-admission-overlay",enforce:"pre",resolveId(id,importer){
    const path=id.startsWith(".")&&importer?resolve(dirname(importer),id):id.startsWith("/")?id:undefined;
    if(path){const mapped=redirect(path);if(mapped!==path)return mapped;}
  }},shared.standardDecoratorPlugin()],
  test:{environment:"node",include:["native-llm-admission.test.ts",resolve(donor,"packages/llm/llm/tests/service.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/prepared-call.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/extensions.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/files.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/file-store.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/dynamic-config.spec.ts"),resolve(donor,"packages/llm/llm-deepseek/tests/adapter.spec.ts")],maxWorkers:1,fileParallelism:false,
    testTimeout:15000,hookTimeout:15000,execArgv:shared.vitestExecArgv},
});
