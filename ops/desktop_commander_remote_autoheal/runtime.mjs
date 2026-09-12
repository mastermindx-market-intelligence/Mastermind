/** Pinned vendor launcher + inner-transport health. Never replays user work. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {spawn,spawnSync} from 'node:child_process';
import {probeInner,Watchdog,restartPolicy,atomicJson,eventLogger} from './monitor.mjs';
import {saveSession,childMatches,processInfo,verifyManifest,fatalAuth,safeCall} from './safety.mjs';

// Vendor console lines contain full tool arguments/results. Do not persist them.
for(const method of ['log','info','warn','error','debug','trace','dir'])console[method]=()=>{};
process.umask(0o077);
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const root=config.root, generation=randomUUID();
const log=eventLogger(path.join(root,'logs'),generation);
const statusPath=path.join(root,'status.json'),holdPath=path.join(root,'HOLD.json');
const state={generation,pid:process.pid,phase:'starting',deviceId:config.deviceId,
 version:config.vendorVersion,nodeVersion:process.version,startedAt:new Date().toISOString(),
 innerLastOkAt:null,remoteReachable:false,activeCalls:[],mcp:null};
let device,watchdog,interval,startupTimer,finishing=false;
const active=new Map();
// Diagnostic evidence only; never replay or infer no effect from a lost result.
const mergeUncertainCalls=(...groups)=>{
 const calls=new Map();
 for(const group of groups){
  if(!Array.isArray(group))continue;
  for(const call of group){
   const safe=safeCall({id:call?.id,tool_name:call?.tool});
   if(safe)calls.set(safe.id+':'+safe.tool,safe);
  }
 }
 return [...calls.values()];
};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const readJson=(file,fallback)=>{try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}};
const commandIsIncumbentBridge=command=>
 /(?:^|\s)(?:node\s+)?\S*\/node_modules\/\.bin\/desktop-commander\s+remote(?:\s|$)/.test(command)||
 /(?:^|\s)desktop-commander\s+remote(?:\s|$)/.test(command);
function incumbentBridgeRows(){
 const ps=spawnSync('/bin/ps',['-axo','uid=,pid=,args='],{encoding:'utf8',timeout:3000});
 if(ps.error||ps.status!==0)throw Error('process_observation_unavailable');
 return ps.stdout.split('\n').filter(line=>{
  const m=line.trim().match(/^(\d+)\s+(\d+)\s+(.*)$/);
  return m&&Number(m[1])===config.uid&&Number(m[2])!==process.pid&&commandIsIncumbentBridge(m[3]);
 });
}
async function waitForIncumbentBridgeClear(){
 let announced=false;
 for(;;){
  let rows;
  try{rows=incumbentBridgeRows();}
  catch{hold('process_observation_unavailable');process.exit(0);return false;}
  if(!rows.length){
   if(announced){state.phase='starting';delete state.reason;delete state.incumbentCount;publish();log('incumbent_bridge_cleared');}
   return true;
  }
  state.phase='waiting_for_incumbent';state.reason='unmanaged_bridge_present';state.incumbentCount=rows.length;publish();
  if(!announced){log('waiting_for_incumbent_bridge',{count:rows.length});announced=true;}
  await sleep(5000);
  if(finishing)return false;
 }
}
const publish=()=>{state.activeCalls=[...active.values()].filter(Boolean);atomicJson(statusPath,state);};
const hold=code=>{state.phase='held';state.reason=code;atomicJson(holdPath,{at:new Date().toISOString(),code,generation});log(code);};
async function bounded(promise,ms){let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('bounded_timeout')),ms);})]);}finally{clearTimeout(timer);}}

async function finish(code,exitCode){
 if(finishing)return;finishing=true;
 clearInterval(interval);clearTimeout(startupTimer);watchdog?.stop();
 const fuse=setTimeout(()=>process.exit(exitCode),20000);
 // Capture before drain removes calls whose producer may already have acted.
 if(exitCode)state.uncertainCalls=mergeUncertainCalls(state.uncertainCalls,[...active.values()]);
 state.phase=exitCode?'recovering':'stopped';state.reason=code;state.remoteReachable=false;publish();
 log(code,{activeCount:active.size,mcpPid:state.mcp?.pid});
 // Stop accepting new work before draining already-received calls.
 try{device?.remoteChannel.stopHeartbeat();await bounded(device?.remoteChannel.unsubscribe()??Promise.resolve(),3000);}catch{}
 const end=performance.now()+10000;
 while(active.size&&performance.now()<end)await sleep(100);
 state.uncertainCalls=mergeUncertainCalls(state.uncertainCalls,[...active.values()]);publish();
 if(state.uncertainCalls.length)log('inflight_reconciliation_required',{activeCount:state.uncertainCalls.length});
 try{if(device)await bounded(device.shutdown(),4000);}catch{}
 clearTimeout(fuse);process.exit(exitCode);
}
const recover=code=>{void finish(code,75).catch(()=>process.exit(75));};
process.on('SIGTERM',()=>recover('signal_sigterm'));
process.on('SIGINT',()=>recover('signal_sigint'));
process.on('uncaughtException',()=>recover('uncaught_exception'));
process.on('unhandledRejection',()=>recover('unhandled_rejection'));
process.on('exit',code=>{try{state.phase=fs.existsSync(holdPath)?'held':(code?'exited_unhealthy':'stopped');state.exitCode=code;state.remoteReachable=false;publish();log('process_exit',{exitCode:code});}catch{}});

async function startup(){
 const previous=readJson(statusPath,null);
 if(previous?.mcp){state.mcp=previous.mcp;state.previousPid=previous.pid;}
 if(fs.existsSync(holdPath)){state.phase='held';state.reason=readJson(holdPath,{}).code;publish();process.exit(0);}
 if(process.version!==config.nodeVersion){hold('node_version_changed');process.exit(0);}
 try{verifyManifest(root,readJson(path.join(root,'release-manifest.json'),{}));}
 catch{hold('release_integrity_failed');process.exit(0);}
 state.priorUncertainCalls=mergeUncertainCalls(previous?.priorUncertainCalls,previous?.uncertainCalls,previous?.activeCalls);
 // Hard parent crashes may leave the local MCP orphaned. Never kill its commands.
 if(previous?.mcp&&!processInfo(previous.previousPid??previous.pid)){
  const actual=processInfo(previous.mcp.pid);
  if(actual){
   if(!childMatches(previous.mcp,actual,config.uid,config.node,config.vendorEntry)){
    hold('orphan_identity_unresolved');process.exit(0);
   }
   process.kill(actual.pid,'SIGTERM');await sleep(2200);
   const remaining=processInfo(actual.pid);
   if(remaining&&childMatches(previous.mcp,remaining,config.uid,config.node,config.vendorEntry)){
    process.kill(actual.pid,'SIGKILL');await sleep(300);
   }
   if(processInfo(actual.pid)){hold('orphan_cleanup_unresolved');process.exit(0);}
   log('owned_mcp_orphan_reaped',{mcpPid:actual.pid});
  }
 }
 // Do not start beside a Terminal-launched bridge sharing device.json.
 if(previous?.mcp&&processInfo(previous.mcp.pid)&&processInfo(previous.previousPid??previous.pid)){
  hold('previous_generation_identity_unresolved');process.exit(0);
 }
 if(config.waitForIncumbent!==false&&!(await waitForIncumbentBridgeClear()))return;
 const budgetFile=path.join(root,'restart-budget.json');
 const policy=restartPolicy(readJson(budgetFile,{starts:[]}).starts);
 if(!policy.allowed){hold('restart_budget_exhausted');process.exit(0);}
 atomicJson(budgetFile,{starts:policy.starts});publish();log('generation_start',{delayMs:policy.delayMs});
 if(policy.delayMs)await sleep(policy.delayMs);
 if(finishing)return;
 const {MCPDevice}=await import(pathToFileURL(config.vendorDevice).href);
 class GuardedDevice extends MCPDevice{
  setupShutdownHandlers(){} // One shutdown owner: this launchd wrapper.
  async loadPersistedConfig(){
   const session=await super.loadPersistedConfig();
   if(this.deviceId!==config.deviceId||!session?.refresh_token){hold('auth_required');throw Error('auth_required');}
   this.remoteChannel.client.auth.onAuthStateChange((event,newSession)=>{
    if(event==='TOKEN_REFRESHED'&&newSession?.access_token){
     try{saveSession(this.configPath,this.deviceId,newSession);log('session_rotation_persisted');}
     catch{hold('session_persistence_failed');void finish('session_persistence_failed',0);}
    }
   });
   return session;
  }
  async savePersistedConfig(){
   const current=await this.remoteChannel.getSession();
   saveSession(this.configPath,this.deviceId,current.data.session);
  }
  async handleNewToolCall(payload){
   const call=payload.new,id=call.id;
   if(active.has(id)||this.seenCallIds.has(id))return;
   if(finishing){
    this.rememberCallId(id);
    try{if(await this.remoteChannel.markCallExecuting(id)){
      await this.remoteChannel.updateCallResult(id,'failed',null,'Bridge recovering; no new execution in this generation. Reconcile before any retry.');
      await this.remoteChannel.notifyResult(id);
    }}catch{}
    return;
   }
   if(call.tool_name==='shutdown'){watchdog?.stop();clearInterval(interval);}
   active.set(id,safeCall(call));publish();
   try{return await super.handleNewToolCall(payload);}
   finally{active.delete(id);publish();}
  }
 }
 device=new GuardedDevice({persistSession:true});
 // Throw before the vendor can fall back to opening a browser to pair a new session.
 const setSession=device.remoteChannel.setSession.bind(device.remoteChannel);
 device.remoteChannel.setSession=async session=>{
  try{const result=await setSession(session);if(result?.error)throw result.error;return result;}
  catch(error){if(fatalAuth(error))hold('auth_required');throw error;}
 };
 const init=device.desktop.initialize.bind(device.desktop);
 device.desktop.initialize=async()=>{
  await init();
  delete state.previousPid;state.mcp=processInfo(device.desktop.mcpTransport.pid);
  if(!state.mcp)throw Error('mcp_identity_unavailable');
  const previousClose=device.desktop.mcpClient.onclose;
  device.desktop.mcpClient.onclose=()=>{try{previousClose?.();}finally{if(!finishing&&!device.isShuttingDown)watchdog?.closed();}};
  publish();log('inner_connected',{mcpPid:state.mcp.pid});
 };
 watchdog=new Watchdog({
  probe:()=>probeInner(device.desktop.mcpClient,config.sentinelPath,config.sentinel,8000),
  trip:recover,
  report:(ok,failures)=>{
   state.remoteReachable=!!device.remoteChannel.isReachable()&&!!device.remoteChannel.presenceTracked&&
    (device.remoteChannel.lastHeartbeatOkAt==null||performance.now()-device.remoteChannel.lastHeartbeatOkAt<75000);
   if(ok)state.innerLastOkAt=new Date().toISOString();
   state.phase=ok?(state.remoteReachable?'healthy':'remote_reconnecting'):'inner_degraded';
   publish();log(ok?'probe_pass':'probe_fail',{failures,mcpPid:state.mcp?.pid});
  }
 });
 // Same no-sleep behavior as the vendor's existing `remote` CLI; no power settings changed.
 const caffeine=spawn('/usr/bin/caffeinate',['-w',String(process.pid)],{stdio:'ignore'});
 caffeine.on('error',()=>log('keepawake_unavailable'));
 startupTimer=setTimeout(()=>recover('startup_timeout'),120000);
 await device.start();clearTimeout(startupTimer);
 if(finishing)return;
 await watchdog.tick();
 interval=setInterval(()=>{
  if(device.remoteChannel.sessionLost){hold('auth_required');void finish('auth_required',0);return;}
  void watchdog.tick();
 },20000);
}
startup().catch(()=>recover('startup_failure'));
