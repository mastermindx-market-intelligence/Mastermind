import {defineConfig} from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";
import {pathToFileURL} from "node:url";
import {resolve} from "node:path";
import {createRequire} from "node:module";
const donor=process.env.DSH_SOURCE;
if(!donor)throw new Error("DSH_SOURCE must name the accepted donor checkout");
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
const donorRequire=createRequire(resolve(donor,"packages/test-support/client-runtime/package.json"));
export default defineConfig({
  resolve:{alias:[
    {find:new RegExp("^@deepseek-ai/dsh-client-store$"),replacement:resolve(donor,"packages/client/store/src/index.ts")},
    {find:new RegExp("^@deepseek-ai/dsh-client-test-runtime$"),replacement:resolve(donor,"packages/test-support/client-runtime/src/index.ts")},
    {find:/^react$/,replacement:donorRequire.resolve("react")},
    {find:/^react-dom$/,replacement:donorRequire.resolve("react-dom")},
    {find:new RegExp("^react-dom/client$"),replacement:donorRequire.resolve("react-dom/client")},
  ]},
  plugins:[tsconfigPaths({projects:[resolve(donor,"tsconfig.base.json")]}),shared.standardDecoratorPlugin()],
  test:{environment:"jsdom",include:["native.client.test.ts"],testTimeout:30000,hookTimeout:30000,
    maxWorkers:1,execArgv:shared.vitestExecArgv},
});
