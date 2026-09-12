import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

/** A bounded, read-only request through the already-running inner MCP client. */
export async function probeInner(client, sentinelPath, sentinel, timeoutMs = 8000) {
  const controller = new AbortController();
  let timer;
  try {
    const result = await Promise.race([
      client.callTool({name:'read_file', arguments:{path:sentinelPath,offset:0,length:3},
        _meta:{remote:true,local_transport_health:true}}, undefined,
        {signal:controller.signal,timeout:timeoutMs,maxTotalTimeout:timeoutMs,resetTimeoutOnProgress:false}),
      new Promise((_,reject) => {timer=setTimeout(() => {
        reject(new Error('probe_timeout')); controller.abort();
      },timeoutMs);}),
    ]);
    if (result?.isError || !Array.isArray(result?.content) ||
        !result.content.some(c => c.type==='text' && typeof c.text==='string' && c.text.split(/\r?\n/).includes(sentinel))) {
      throw new Error('probe_invalid');
    }
  } finally { clearTimeout(timer); }
}

/** Health policy only: never resubmits a remote request or starts a shell. */
export class Watchdog {
  constructor({probe,trip,report=()=>{},maxFailures=3}) {
    this.probe=probe; this.trip=trip; this.report=report; this.maxFailures=maxFailures;
    this.failures=0; this.busy=false; this.stopped=false;
  }
  stop(){this.stopped=true;}
  fail(code){if(this.stopped)return;this.stopped=true;this.trip(code);}
  closed(){this.fail('inner_transport_closed');}
  async tick(){
    if(this.busy||this.stopped)return;
    this.busy=true;
    try{await this.probe();if(!this.stopped){this.failures=0;this.report(true,0);}}
    catch{if(!this.stopped){this.failures++;this.report(false,this.failures);
      if(this.failures>=this.maxFailures)this.fail('inner_probe_failed');}}
    finally{this.busy=false;}
  }
}

/** A small service crash budget, not a user-command retry queue. */
export function restartPolicy(starts, now = new Date().getTime()) {
  const recent=(Array.isArray(starts)?starts:[]).filter(t=>Number.isFinite(t)&&t>now-600000&&t<=now);
  const exponent=Math.min(Math.max(recent.length-1,0),5);
  return {allowed:true,delayMs:recent.length?Math.min(300000,10000*2**exponent):0,starts:[...recent.slice(-5),now]};
}

export function atomicJson(file, value) {
  const tmp=`${file}.${process.pid}.${randomUUID()}.tmp`;
  let fd;
  try{
    fd=fs.openSync(tmp,'wx',0o600);fs.writeFileSync(fd,JSON.stringify(value,null,2)+'\n');
    fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;fs.renameSync(tmp,file);
  }finally{if(fd!==undefined)fs.closeSync(fd);try{fs.unlinkSync(tmp);}catch(e){if(e.code!=='ENOENT')throw e;}}
}

/** Deliberate field allowlist: never accepts raw tool data, error text or tokens. */
export function eventLogger(dir, generation, {maxBytes=1048576,backups=4}={}) {
  fs.mkdirSync(dir,{recursive:true,mode:0o700});
  const file=path.join(dir,'events.jsonl');
  const fields=new Set(['mcpPid','exitCode','activeCount','failures','delayMs','durationMs','pid','attempts']);
  return (event,values={})=>{
    if(!/^[a-z_]{1,64}$/.test(event))throw Error('invalid_event_code');
    const record={at:new Date().toISOString(),event,generation,pid:process.pid};
    for(const [k,v] of Object.entries(values))if(fields.has(k)&&Number.isFinite(v))record[k]=v;
    const line=JSON.stringify(record)+'\n';
    let size=0;try{size=fs.statSync(file).size;}catch(e){if(e.code!=='ENOENT')throw e;}
    if(size+Buffer.byteLength(line)>maxBytes){
      for(let i=backups;i>=1;i--){const src=i===1?file:`${file}.${i-1}`,dst=`${file}.${i}`;
        try{fs.renameSync(src,dst);}catch(e){if(e.code!=='ENOENT')throw e;}}
    }
    fs.appendFileSync(file,line,{mode:0o600});
  };
}
