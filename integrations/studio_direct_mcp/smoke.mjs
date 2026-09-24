#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';

async function main() {
  const argv=process.argv.slice(2), opts={samples:3};
  for(let i=0;i<argv.length;i++) {
    const a=argv[i];
    if(a==='--noop') opts.noop=true;
    else if(['--url','--token-file','--stdio','--samples'].includes(a)) opts[a.slice(2)]=argv[++i];
    else throw Error('Usage: smoke.mjs (--url BASE --token-file FILE | --stdio CONFIG) [--noop] [--samples N]');
  }
  const samples=Number(opts.samples);
  if(!Number.isInteger(samples)||samples<1||samples>10) throw Error('samples must be 1..10');
  const report={at:new Date().toISOString(),mode:opts.stdio?'stdio':'https',steps:[]};
  let token='',transport,client;
  const clean=s=>token?String(s).split(token).join('[redacted]'):String(s);
  async function measure(step,fn) {
    const started=performance.now();
    try {
      const result=await fn();
      if(result?.isError) throw Error(result.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n')||'MCP tool error');
      report.steps.push({step,ok:true,ms:Number((performance.now()-started).toFixed(3))});
      return result;
    } catch(e) {
      report.steps.push({step,ok:false,ms:Number((performance.now()-started).toFixed(3)),error:clean(e.message)});
      throw e;
    }
  }
  try {
    if(opts.stdio) {
      const cfg=JSON.parse(await readFile(opts.stdio,'utf8'));
      transport=new StdioClientTransport({command:cfg.command,args:cfg.args,cwd:cfg.cwd,env:cfg.childEnv||{},stderr:'pipe'});
    } else {
      if(!opts.url||!opts['token-file']) throw Error('url and token-file are required');
      token=(await readFile(opts['token-file'],'utf8')).trim();
      if(!token||/\s/.test(token)) throw Error('Invalid token file');
      const u=new URL(opts.url); u.pathname='/mcp';
      transport=new StreamableHTTPClientTransport(u,{requestInit:{headers:{Authorization:`Bearer ${token}`}}});
      report.endpoint=u.href;
    }
    client=new Client({name:'studio-direct-acceptance',version:'0.1.0'});
    await measure('initialize',()=>client.connect(transport));
    transport.stderr?.on('data',()=>{});
    const listed=await measure('tools/list',()=>client.listTools());
    report.toolCount=listed.tools.length;
    for(let i=0;i<samples;i++) {
      const ping=await measure('ping',()=>listed.tools.some(t=>t.name==='studio_ping')?client.callTool({name:'studio_ping',arguments:{}}):client.ping());
      if(i===0&&ping?.content) report.identity=ping.content.filter(x=>x.type==='text').map(x=>x.text).join('');
      await measure('read_file',()=>client.callTool({name:'read_file',arguments:{path:'/System/Library/CoreServices/SystemVersion.plist',offset:0,length:8}}));
    }
    if(opts.noop) {
      const marker=`STUDIO_DIRECT_ACCEPTANCE_${Date.now()}_${process.pid}`;
      const result=await measure('start_process',()=>client.callTool({name:'start_process',arguments:{command:`printf '%s\\n' '${marker}'; /usr/bin/true`,timeout_ms:1000,verbose_timing:true}},undefined,{timeout:15000}));
      const text=result.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n')||'';
      if(!text.includes(marker)) throw Error('Remote execution marker missing');
      report.remoteCommandMarker=marker;
    }
    report.ok=true;
  } catch(e) {
    report.ok=false;report.error=clean(e.message);process.exitCode=1;
  } finally {
    if(transport instanceof StreamableHTTPClientTransport) await transport.terminateSession().catch(()=>{});
    await client?.close().catch(()=>{});
    await transport?.close().catch(()=>{});
  }
  console.log(JSON.stringify(report,null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
