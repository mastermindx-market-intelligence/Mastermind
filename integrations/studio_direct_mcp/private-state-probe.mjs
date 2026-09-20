import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
const target=process.argv[2] || '/Users/chriswong/.local/share/studio-direct-mcp/private/chatgpt1/private-tunnel-gateway.mjs';
const live=target.startsWith('http://127.0.0.1:');
const expectShared=process.argv.includes('--expect-shared');
const gw=live ? {url:target,close:async()=>{}} : await (await import(pathToFileURL(target))).startPrivateGateway({accountLabel:'continuity-probe',port:0,command:process.execPath,args:['/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js'],requestTimeoutMs:10000});
const clients=[],transports=[];const receipt={scope:live?'installed-live-loopback-real-Desktop-Commander':'isolated-loopback-real-Desktop-Commander',nativeChatGPT:false,at:new Date().toISOString()};
try {
 for(let i=0;i<2;i++) {const c=new Client({name:'cross-session-probe',version:'1'});const t=new StreamableHTTPClientTransport(new URL(gw.url));clients.push(c);transports.push(t);await c.connect(t);}
 receipt.gateway=await clients[0].callTool({name:'studio_ping',arguments:{}});
 const start=await clients[0].callTool({name:'start_process',arguments:{command:"/usr/bin/printf 'STUDIO_DIRECT_STATE_PROBE\\n'",timeout_ms:1000}});
 const output=start.content.filter(c=>c.type==='text').map(c=>c.text).join('\n');
 const pid=Number(output.match(/PID:?\s*(\d+)/i)?.[1]);
 if(!pid) throw new Error('Probe did not return its process PID');
 receipt.pid=pid;receipt.startError=!!start.isError;
 const next=await clients[1].callTool({name:'read_process_output',arguments:{pid,timeout_ms:1000}});
 receipt.nextSessionResult=next;
 receipt.sameSessionResult=await clients[0].callTool({name:'read_process_output',arguments:{pid,timeout_ms:1000}});
 if(expectShared) {
  assert.ok(!next.isError, 'Process handle must work from a different MCP session');
  assert.ok(next.content.some(c=>c.text?.includes('STUDIO_DIRECT_STATE_PROBE')));
  await transports[0].terminateSession();
  const afterDelete=await clients[1].callTool({name:'read_process_output',arguments:{pid,timeout_ms:1000}});
  assert.ok(!afterDelete.isError, 'Deleting the creator session must preserve the process handle');
  receipt.creatorDeletedHandlePreserved=true;
  for(let i=0;i<12;i++) {
   const c=new Client({name:'native-churn-probe',version:'1'});
   const t=new StreamableHTTPClientTransport(new URL(gw.url));
   clients.push(c);transports.push(t);await c.connect(t);
   const result=await c.callTool({name:'read_process_output',arguments:{pid,timeout_ms:1000}});
   assert.ok(!result.isError, 'Handle must survive capacity reclamation');
   await new Promise(resolve=>setTimeout(resolve,80));
  }
  receipt.churnSessions=12;
  receipt.status='PASS';
 }
} catch(e) {receipt.error=e.message;process.exitCode=1;}
finally {for(const t of transports)try{await t.terminateSession();}catch{}for(const c of clients)await c.close();await gw.close();console.log(JSON.stringify(receipt,null,2));}
