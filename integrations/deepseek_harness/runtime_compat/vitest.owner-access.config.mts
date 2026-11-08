import {defineConfig} from "vitest/config";
import {createRequire} from "node:module";
import {resolve,dirname} from "node:path";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {fileURLToPath,pathToFileURL} from "node:url";
const donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/"))throw Error("DSH_SOURCE must name the pinned native donor");
const here=dirname(fileURLToPath(import.meta.url));
const access=JSON.parse(readFileSync(resolve(here,"native-access-source.json"),"utf8"));
const hostBytes=readFileSync(resolve(here,"native-host-source.json"));
if(createHash("sha256").update(hostBytes).digest("hex")!==access.host_manifest_sha256)
  throw Error("Owner access requires its exact host composition");
const host=JSON.parse(hostBytes.toString()),session=JSON.parse(readFileSync(resolve(here,"native-session-source.json"),"utf8"));
const candidate=resolve(here,".cache/native-access",access.patch_sha256);
const sessionRoot=access.schema!=="mastermind.dsh_native_access_source.v1"?candidate:resolve(here,".cache/native-session");
for(const [root,files] of [
  [candidate,{...host.source_sha256,...host.output_sha256,...access.base_sha256,...access.output_sha256}],
  [sessionRoot,{...session.source_sha256,...session.output_sha256,...(sessionRoot===candidate?access.output_sha256:{})}],
] as const)for(const [name,digest] of Object.entries(files)){
  if(createHash("sha256").update(readFileSync(resolve(root,name))).digest("hex")!==digest)
    throw Error("Native owner access input differs: "+name);
}
const requireDonor=createRequire(resolve(donor,"package.json")),ts=requireDonor("typescript");
const parsed=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(parsed.error)throw Error("Native source paths unavailable");
const roots=["packages/core/agent/src","packages/core/agent-loop/src","apps/cli/src",
  "packages/typert/protocol/src","packages/client/connection/src",
  "packages/api/remote-access/src","packages/api/gateway/src","packages/api/remotes/src",
  ...(["mastermind.dsh_native_access_source.v3","mastermind.dsh_native_access_source.v4"].includes(access.schema)?["packages/client/file-upload/src"]:[]),
  ...(access.schema==="mastermind.dsh_native_access_source.v4"?["packages/client/ui-deliverables/src"]:[])];
const sessionSource=resolve(donor,"packages/api/session-controller/src");
const redirect=(path:string)=>{
  if(path===sessionSource||path.startsWith(sessionSource+"/"))
    return resolve(sessionRoot,"packages/api/session-controller/src")+path.slice(sessionSource.length);
  return roots.some(root=>path===resolve(donor,root)||path.startsWith(resolve(donor,root)+"/"))
    ?resolve(candidate,path.slice(donor.length+1)):path;
};
const aliases=Object.entries(parsed.config.compilerOptions.paths).filter(([name])=>!name.includes("*")).map(([name,paths])=>({
  find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:redirect(resolve(donor,(paths as string[])[0])),
}));
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
const regression=process.env.MMX_NATIVE_ACCESS_REGRESSION==="1";
export default defineConfig({
  resolve:{alias:[
    {find:"mmx-native-test-remote",replacement:resolve(donor,"packages/api/session-controller/tests/test-remote.ts")},
    {find:"mmx-native-present-open",replacement:resolve(candidate,"packages/client/ui-deliverables/src/present-open.ts")},
    {find:"mmx-native-changes-support",replacement:resolve(donor,"packages/deliverables/workspace-changes/tests/support.ts")},
    {find:"mmx-native-browser-credentials",replacement:resolve(donor,"packages/api/gateway/tests/browser-credentials.ts")},
    {find:/^@deepseek-ai\/dsh-api-session-controller\/src\//,replacement:resolve(sessionRoot,"packages/api/session-controller/src")+"/"},
    ...aliases,
  ]},
  plugins:[{name:"native-owner-access-composition",enforce:"pre",resolveId(id,importer){
    const path=id.startsWith(".")&&importer?resolve(dirname(importer),id):id.startsWith("/")?id:undefined;
    if(path){const mapped=redirect(path);if(mapped!==path)return mapped;}
  }},shared.standardDecoratorPlugin()],
  test:{environment:"node",include:process.env.MMX_NATIVE_ACCESS_CHANGES_REGRESSION==="1"?[
    resolve(donor,"packages/client/ui-deliverables/tests/changes-open.host.spec.ts"),
    resolve(donor,"packages/client/ui-deliverables/tests/present-open.host.spec.ts"),
  ]:process.env.MMX_NATIVE_ACCESS_UPLOAD_REGRESSION==="1"?[
    resolve(donor,"packages/client/file-upload/tests/file-upload-http.host.spec.ts"),
    resolve(donor,"packages/client/connection/tests/fetch-routes.host.spec.ts"),
    resolve(donor,"packages/client/connection/tests/http-bridge.host.spec.ts"),
    resolve(donor,"packages/client/connection/tests/binary-rpc.host.spec.ts"),
  ]:process.env.MMX_NATIVE_ACCESS_SEARCH_REGRESSION==="1"?[resolve(donor,"packages/api/session-controller/tests/session-search.host.spec.ts")]:regression?[
    resolve(donor,"packages/api/remote-access/tests/**/*.host.spec.ts"),
    resolve(donor,"packages/api/gateway/tests/gateway*.host.spec.ts"),
  ]:["native-owner-access.test.ts","native-owner-hold.test.ts","native-owner-upload.test.ts","native-owner-changes.test.ts"],
  maxWorkers:1,fileParallelism:false,testTimeout:15000,hookTimeout:15000,execArgv:shared.vitestExecArgv},
});
