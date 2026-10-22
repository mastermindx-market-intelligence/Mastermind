#!/usr/bin/env node
// Read-only SDK -> Fabric facade -> maintained Desktop Commander -> adapter proof.
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {fileURLToPath} from 'node:url';
import {FABRIC_TOOLS} from './fabric-backend.mjs';
import assert from 'node:assert/strict';
const [run_id,root_id]=process.argv.slice(2);
if(!run_id || !root_id) throw new Error('usage: node fabric-preflight.mjs RUN_ID ROOT_ID');
const client=new Client({name:'mastermind-fabric-preflight',version:'0.1.0'},{capabilities:{}});
const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('./fabric-backend.mjs',import.meta.url))],env:{...process.env},stderr:'pipe'});
let stderrBytes=0;
transport.stderr?.on('data',b=>{stderrBytes+=b.length;});
const value=r=>r.structuredContent??JSON.parse(r.content[0].text);
try{
 await client.connect(transport);
 const catalog=await client.listTools();
 assert.deepEqual(catalog.tools.map(t=>t.name).sort(),FABRIC_TOOLS.map(t=>t.name).sort());
 const capabilities=value(await client.callTool({name:'fabric_capabilities',arguments:{}}));
 assert.equal(capabilities.adapter_available,true);
 const status=value(await client.callTool({name:'fabric_status',arguments:{run_id,root_id}}));
 assert.equal(status.status?.run_id,run_id);
 assert.equal(status.retry_allowed,false);
 console.log(JSON.stringify({schema:'mastermind.fabric_mcp_preflight.v1',ok:true,tools:catalog.tools.map(t=>t.name),adapter_available:capabilities.adapter_available,run_id,state:status.status.state,worker_dispatched:false,native_chatgpt_proven:false,stderr_bytes:stderrBytes}));
}finally{await client.close();}
