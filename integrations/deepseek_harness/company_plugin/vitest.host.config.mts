import {defineConfig} from "vitest/config";
import {createRequire} from "node:module";
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {execFileSync} from "node:child_process";
const donor=process.env.DSH_SOURCE;
if(!donor||!donor.startsWith("/")||
  execFileSync("git",["-C",donor,"rev-parse","HEAD"],{encoding:"utf8"}).trim()!=="687f282e8625c6b8d11ff58211a90524be2e4317"||
  execFileSync("git",["-C",donor,"status","--porcelain"],{encoding:"utf8"}).trim())
  throw new Error("Exact clean native donor required");
const requireDonor=createRequire(resolve(donor,"package.json"));
const ts=requireDonor("typescript");
const parsed=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(parsed.error)throw new Error("Native TypeScript source map unavailable");
const aliases=Object.entries(parsed.config.compilerOptions.paths)
  .filter(([name])=>!name.includes("*")).map(([name,values])=>({
    find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:resolve(donor,(values as string[])[0]),
  }));
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
export default defineConfig({
  resolve:{alias:[
    {find:"mmx-pinned-native-history",replacement:resolve(donor,"packages/api/session-controller/src/history.ts")},
    {find:"mmx-native-test-remote",replacement:resolve(donor,"packages/api/session-controller/tests/test-remote.ts")},
    {find:"mmx-native-browser-credentials",replacement:resolve(donor,"packages/api/gateway/tests/browser-credentials.ts")},
    ...aliases,
  ]},
  plugins:[shared.standardDecoratorPlugin()],
  test:{environment:"node",include:["native.host.test.ts","native.executive.test.ts","native.executive.fixture.test.ts","native.closed-history.test.ts"],maxWorkers:1,fileParallelism:false,
    testTimeout:15000,hookTimeout:15000,execArgv:shared.vitestExecArgv},
});
