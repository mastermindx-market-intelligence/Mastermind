import {spawn} from "node:child_process";
import readline from "node:readline";
import {fileURLToPath} from "node:url";
import {dirname,join} from "node:path";

const child=spawn(process.execPath,[join(dirname(fileURLToPath(import.meta.url)),"bridge.mjs")],{
  env:process.env,stdio:["pipe","pipe","pipe"],detached:true
});
let id=0,stderr="";
const pending=new Map();
child.stderr.on("data",d=>{if(stderr.length<500)stderr+=d.toString()});
readline.createInterface({input:child.stdout}).on("line",line=>{
  let response;
  try{response=JSON.parse(line)}catch{return}
  const p=pending.get(response.id);
  if(!p)return;
  clearTimeout(p.timer);pending.delete(response.id);
  response.error?p.reject(new Error(response.error.message??"MCP_ERROR")):p.resolve(response.result);
});
function ask(method,params={}){
  return new Promise((resolve,reject)=>{
    const n=++id;
    const timer=setTimeout(()=>{pending.delete(n);reject(new Error("MCP_TIMEOUT "+method))},18000);
    pending.set(n,{resolve,reject,timer});
    child.stdin.write(JSON.stringify({jsonrpc:"2.0",id:n,method,params})+"\n");
  });
}
const evidence={};
try {
  const init=await ask("initialize",{protocolVersion:"2025-11-25",
    capabilities:{},clientInfo:{name:"mmx-cuse-smoke",version:"0.1.0"}});
  evidence.initialized=Boolean(init?.protocolVersion);
  child.stdin.write(JSON.stringify({jsonrpc:"2.0",method:"notifications/initialized"})+"\n");
  const inventory=await ask("tools/list",{});
  evidence.tools=(inventory?.tools??[]).map(t=>t.name);
  const apps=await ask("tools/call",{name:"list_apps",arguments:{}});
  evidence.allowed_apps=(apps?.content??[]).filter(x=>x.type==="text").map(x=>x.text);
  try {
    await ask("tools/call",{name:"click",arguments:{app:"com.google.Chrome",element_index:1}});
    evidence.forbidden_click="UNEXPECTED_SUCCESS";
    process.exitCode=2;
  }catch(e){evidence.forbidden_click=e.message}
  if(process.env.MMX_CUSE_SMOKE_APP){
    try {
      const res=await ask("tools/call",{name:"get_app_state",
        arguments:{app:process.env.MMX_CUSE_SMOKE_APP}});
      evidence.app_state={ok:!res?.isError,types:(res?.content??[]).map(c=>c.type),
        error:res?.isError?(res.content??[]).find(c=>c.type==="text")?.text?.slice(0,160):null};
      if(!evidence.app_state.ok || !evidence.app_state.types.includes("image"))process.exitCode=2;
    }catch(e){
      evidence.app_state={error:e.message.slice(0,160)};
      process.exitCode=2;
    }
  }
  console.log(JSON.stringify(evidence,null,2));
}catch(e){
  process.exitCode=1;
  console.log(JSON.stringify({smoke_failed:e.message,stderr:stderr.slice(-180)}));
}finally{
  child.stdin.end();
  try{process.kill(-child.pid,"SIGTERM")}catch{}
  setTimeout(()=>{try{process.kill(-child.pid,"SIGKILL")}catch{}},1000).unref();
}
