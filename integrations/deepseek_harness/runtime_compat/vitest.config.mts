import {defineConfig} from "vitest/config";
import {createRequire} from "node:module";
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";
const donor=process.env.DSH_SOURCE;
if(!donor)throw new Error("DSH_SOURCE must be the accepted full-app donor");
const donorRequire=createRequire(resolve(donor,"package.json"));
const sdkRequire=createRequire(resolve(donor,"packages/mcp/mcp-client/package.json"));
const ts=donorRequire("typescript");
const parsed=ts.readConfigFile(resolve(donor,"tsconfig.base.json"),ts.sys.readFile);
if(parsed.error)throw new Error("Unable to read donor TypeScript configuration");
const paths=parsed.config.compilerOptions.paths;
const aliases=Object.entries(paths).filter(([name])=>!name.includes("*")).map(([name,values])=>({
 find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:resolve(donor,(values as string[])[0]),
}));
const local=(path:string)=>resolve(process.cwd(),path);
const mcp=(file:string)=>local(".cache/patched/packages/mcp/mcp-client/src/"+file);
const shared=await import(pathToFileURL(resolve(donor,"vitest.shared.ts")).href);
export default defineConfig({
 resolve:{alias:[
  {find:/^@deepseek-ai\/dsh-tools$/,replacement:local(".cache/patched/packages/core/tools/src/index.ts")},
  {find:/^@deepseek-ai\/dsh-mcp-client$/,replacement:mcp("index.ts")},
  {find:"mmx-mcp-tools",replacement:mcp("tools.ts")},
  {find:"mmx-mcp-connection",replacement:mcp("connection.ts")},
  {find:"mmx-mcp-transport",replacement:mcp("transport.ts")},
  {find:"mmx-worker-profile",replacement:local("../../acp_worker/dsh_tool_profile.mjs")},
  ...["@modelcontextprotocol/client","@modelcontextprotocol/client/stdio",
    "@modelcontextprotocol/server","@modelcontextprotocol/server/stdio","zod"].map(name=>({
      find:new RegExp("^"+RegExp.escape(name)+"$"),replacement:sdkRequire.resolve(name),
    })),
  ...aliases,
 ]},
 plugins:[shared.standardDecoratorPlugin()],
 test:{environment:"node",include:["dispatch.test.ts","mcp.test.ts","mcp-context.test.ts","mcp-rich.test.ts"],maxWorkers:1,fileParallelism:false,
  testTimeout:15000,hookTimeout:15000,execArgv:shared.vitestExecArgv},
});
