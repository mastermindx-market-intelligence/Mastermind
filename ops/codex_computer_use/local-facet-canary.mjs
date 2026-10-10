#!/usr/bin/env node
/**
 * Local-only protocol integration canary.
 *
 * Pure remote-facet -> owner-fixture callbacks -> signed local Computer Use MCP
 * bridge -> real macOS app. This deliberately supplies NO transport, OAuth,
 * remote authorization or fleet placement. Not a production admission adapter.
 */
import {spawn} from "node:child_process";
import readline from "node:readline";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {createComputerUseFacet} from "./remote-facet.mjs";

const dir=dirname(fileURLToPath(import.meta.url));
const target=process.env.MMX_CUSE_INTEGRATION_APP;
if(target!=="com.apple.calculator"){
  console.error("REFUSED: set MMX_CUSE_INTEGRATION_APP=com.apple.calculator for an already consented pilot");
  process.exit(2);
}
const child=spawn(process.execPath,[join(dir,"bridge.mjs")],{
  stdio:["pipe","pipe","pipe"],detached:true,env:process.env,
});
let nextId=0;
const pending=new Map();
let stderr="";
child.stderr.on("data",data=>{
  if(stderr.length<400)stderr+=String(data);
});
const request=(method,params={})=>new Promise((resolve,reject)=>{
  if(child.exitCode!==null)return reject(new Error("UPSTREAM_EXITED"));
  const id=++nextId;
  const timer=setTimeout(()=>{
    pending.delete(id);
    reject(new Error("UPSTREAM_TIMEOUT "+method));
  },16000);
  pending.set(id,{resolve,reject,timer});
  child.stdin.write(JSON.stringify({jsonrpc:"2.0",id,method,params})+"\n");
});
readline.createInterface({input:child.stdout}).on("line",line=>{
  let message;
  try{message=JSON.parse(line)}catch{return}
  const promise=pending.get(message.id);
  if(!promise)return;
  clearTimeout(promise.timer);
  pending.delete(message.id);
  message.error?
    promise.reject(new Error(String(message.error.message??"MCP_ERROR"))):
    promise.resolve(message.result);
});
const EXACT={
  principalRef:"local-fixture-principal",
  bindingRef:"local-fixture-host-binding",
  operationRef:"local-fixture-read-only",
};
const ctx=Object.freeze({principalRef:EXACT.principalRef,bindingRef:EXACT.bindingRef});
let dispatched=0;
const facet=createComputerUseFacet({
  authorize:async(context,{mode,app})=>{
    if(context!==ctx || mode!=="read" || (app!==null && app!==target))return null;
    return {allowed:true,canRead:true,canWrite:false,...EXACT};
  },
  dispatch:async requestArgs=>{
    if(requestArgs.context!==ctx || requestArgs.principalRef!==EXACT.principalRef ||
      requestArgs.bindingRef!==EXACT.bindingRef ||
      requestArgs.operationRef!==EXACT.operationRef ||
      !["get_app_state","list_apps"].includes(requestArgs.toolName))throw new Error("FIXTURE_BOUNDARY_REFUSED");
    dispatched++;
    return request("tools/call",{name:requestArgs.toolName,arguments:requestArgs.arguments});
  },
});
try{
  const initialized=await request("initialize",{
    protocolVersion:"2025-11-25",
    capabilities:{},
    clientInfo:{name:"mmx-cuse-local-facet-canary",version:"0.1.0"},
  });
  if(!initialized?.protocolVersion)throw new Error("MCP_INITIALIZE_FAILED");
  child.stdin.write(JSON.stringify({jsonrpc:"2.0",method:"notifications/initialized"})+"\n");
  const localCatalog=await request("tools/list");
  if(!(localCatalog?.tools??[]).some(x=>x.name==="get_app_state"))throw new Error("NO_CONSENTED_APP_READ");
  const list=await facet.listTools(ctx);
  if(list.tools.length!==2 || list.tools.some(x=>x.name==="cuse_click"))throw new Error("FACET_CATALOG_UNSAFE");
  const observed=await facet.callTool({name:"cuse_get_app_state",arguments:{app:target}},ctx);
  const content=observed?.content??[];
  const types=content.map(x=>x.type);
  if(observed.isError || !types.includes("text") || !types.includes("image"))
    throw new Error("NO_NATIVE_SCREENSHOT");
  let denied=false;
  try{
    await facet.callTool({name:"cuse_click",arguments:{app:target,element_index:"9"}},ctx);
  }catch(e){denied=String(e.message).includes("owner denied");}
  if(!denied || dispatched!==1)throw new Error("WRITE_WAS_NOT_DENIED");
  console.log(JSON.stringify({
    phase:"LOCAL_ONLY",mcpInitialized:true,
    facetTools:list.tools.map(x=>x.name),
    imageBlocks:content.filter(x=>x.type==="image").length,
    accessibilityBlocks:content.filter(x=>x.type==="text").length,
    forbiddenActionRefused:true,dispatchCalls:dispatched,
    remoteWebConnected:false,remoteOwnerAuthenticated:false,
  },null,2));
}catch(e){
  console.error("LOCAL_FACET_CANARY_FAILED "+String(e.message).slice(0,200));
  process.exitCode=1;
}finally{
  child.stdin.end();
  try{process.kill(-child.pid,"SIGTERM")}catch{}
  setTimeout(()=>{try{process.kill(-child.pid,"SIGKILL")}catch{}},1200).unref();
}
