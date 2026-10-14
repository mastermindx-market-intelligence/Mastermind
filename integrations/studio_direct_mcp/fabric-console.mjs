#!/usr/bin/env node
// Attended acceptance client. One SDK connection, one response per input line.
// This starts no watcher, retries no request, and never accepts a worker on its own.
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {readFile} from 'node:fs/promises';
import {FABRIC_TOOLS} from './fabric-backend.mjs';
const client=new Client({name:'mastermind-fabric-attended-acceptance',version:'0.1.0'},{capabilities:{}});
const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('./fabric-backend.mjs',import.meta.url))],env:{...process.env},stderr:'pipe'});
transport.stderr?.on('data',()=>{});
await client.connect(transport);
console.log(JSON.stringify({event:'READY',tools:(await client.listTools()).tools.map(t=>t.name)}));
const lines=createInterface({input:process.stdin,terminal:false});
for await (const line of lines){
 if(!line.trim()) continue;
 if(line==='CLOSE'){await client.close();break;}
 let req;
 try{
  req=JSON.parse(line);
  if(!FABRIC_TOOLS.some(t=>t.name===req.name)) throw new Error('UNKNOWN_TOOL');
  if(req.packet_file){
   if(req.name!=='fabric_request' || typeof req.packet_file!=='string') throw new Error('INVALID_PACKET_FILE');
   req.arguments.work_packet=await readFile(req.packet_file,'utf8');
   delete req.packet_file;
  }
  const result=await client.callTool(req,undefined,{timeout:30000});
  console.log(JSON.stringify({event:'RESULT',name:req.name,result}));
 }catch(e){console.log(JSON.stringify({event:'CLIENT_ERROR',name:req?.name??null,error:e.code??e.name??'ERROR',effect_unknown:req?.name==='fabric_request'||req?.name==='fabric_accept',retry_allowed:false}));}
}
await client.close();
