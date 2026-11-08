/** Original in-process entry consumers, with inert account/model fixtures only. */
import {afterEach,expect,it,vi} from "vitest";
import {Context,Service,symbols} from "@deepseek-ai/cordis";
import {client as createClient,methods,ndJsonStream,PROTOCOL_VERSION} from "@agentclientprotocol/sdk";
import {LlmAdapter,createUserMessage,ToolCallId,isAgentLoopRequest,type GenerateOptions,type StreamChunk,type NativeLlmWritePermit} from "@deepseek-ai/dsh-llm";
import AgentLoop from "@deepseek-ai/dsh-agent-loop";
import {mountAgentLoopTestDependencies} from "@deepseek-ai/dsh-agent-loop-testkit";
import * as Persistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TokenMeter from "@deepseek-ai/dsh-token-meter";
import {SessionId} from "@deepseek-ai/dsh-session";
import SandboxPolicy from "@deepseek-ai/dsh-sandbox-policy";
import Approval from "@deepseek-ai/dsh-user-approval";
import Skills from "@deepseek-ai/dsh-skill";
import * as Acp from "mmx-native-acp";
import {canonical,nativeConfig,parseExecutionPolicy,createNativeHostBindings,createNativeReadAdmission,createNativeReadOutputGuard} from "../native_worker.mjs";
import {mkdtemp,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";
import {Duplex,PassThrough,Readable,Writable} from "node:stream";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import TypertGateway from "@deepseek-ai/dsh-api-gateway";
import * as Connection from "@deepseek-ai/dsh-client-connection";
import {createSessionTestController} from "mmx-native-test-remote";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {createCompanySessionReadBridge} from "../company_plugin/lib/company-peer.js";
import {executeExecutiveNativeRead,inject as readInject} from "../company_plugin/lib/executive-read-port.js";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const hash=(x:any)=>createHash("sha256").update(canonical(x)).digest("hex");
const requirements=()=>{
  const config=nativeConfig();return{schema:"mastermind.dsh.native_execution_policy.v1",
    profile_id:"operator.dsh.native-conversation.v1",profile_digest:"a".repeat(64),policy_digest:"b".repeat(64),
    expected_config_digest:hash(config),config,model:{provider:"deepseek-account",model:"deepseek-chat"}};
};
it("consumes only the exact canonical requirement envelope",()=>{
  const raw=canonical(requirements()),parsed=parseExecutionPolicy(raw);
  expect(parsed.config).toEqual(nativeConfig());expect(Object.isFrozen(parsed.model)).toBe(true);
  for(const changed of [
    raw+" ",raw.replace('"schema":','"schema":"duplicate","schema":'),
    canonical({...requirements(),worker_id:"echo-is-not-an-observation"}),
    canonical({...requirements(),model:{provider:"other",model:"deepseek-chat"}}),
    canonical({...requirements(),expected_config_digest:"c".repeat(64)}),
    canonical({...requirements(),config:{...nativeConfig(),network_policy:"enabled"}}),
  ])expect(()=>parseExecutionPolicy(changed)).toThrow();
});
const text=(value:string):StreamChunk[]=>[
  {type:"block-start",index:0,blockType:"text"},{type:"text-delta",index:0,text:value},
  {type:"block-end",index:0,block:{type:"text",text:value}},{type:"finish",reason:{kind:"stop"}},
];
async function host({tool=false,hang=false,read=false,beforeNew,onStream}:{tool?:boolean,hang?:boolean,read?:boolean,
  beforeNew?:(client:any)=>Promise<void>,onStream?:(ctx:Context,options:GenerateOptions)=>Promise<void>}={}){
  const ctx=new Context(),workspace=await mkdtemp(join(tmpdir(),"mmx native entry "));
  const generation=new AbortController(),account={current:true,cache:0,userId:null as string|null},seen:{requests:GenerateOptions[],writes:number,assignments:number,tools:number}=
    {requests:[],writes:0,assignments:0,tools:0};
  cleanup.push(async()=>{await ctx.fiber.dispose();await rm(workspace,{recursive:true,force:true});});
  const sourceFacts=async()=>({
    process:{pid:1,uid:1,gid:1,exec_path:"/fixture/node",node_version:"v26.5.0",binary_sha256:"a".repeat(64)},
    source:{entry_path:"/fixture/native_worker.mjs",entry_sha256:"b".repeat(64)},
    workspace:{workspace_path:workspace,device:1,inode:1,uid:1,gid:1},
  });
  const bindings=createNativeHostBindings({root:ctx,generation,policy:parseExecutionPolicy(canonical(requirements())),
    workspace,symbols,isAgentLoopRequest,sourceFacts});
  await mountAgentLoopTestDependencies(ctx,{systemPrompt:{personaPrefix:""}});
  await ctx.plugin(Persistence,{root:workspace,compression:"none"});await ctx.plugin(TokenMeter);
  await ctx.plugin(SandboxPolicy,{mode:"workspace-write",workspaceRoot:workspace});
  await ctx.plugin(Approval,{policy:"ask"});await ctx.plugin(Skills);
  class InertAccount extends Service{
    constructor(inner:Context){super(inner,"deepseekAccount");}
    async getLocalInferenceSnapshot(){
      const cache=account.cache,userId=account.userId;
      return Object.freeze({inferenceOrigin:"https://api.deepseek.com",userId,
        isCurrent:()=>account.current&&account.cache===cache&&account.userId===userId,
        isInferenceCurrent:()=>account.current});
    }
  }
  await ctx.plugin(InertAccount);
  class Inert extends LlmAdapter{
    providerInfo(){return{id:"deepseek-account",name:"Inert native test model"};}
    async listModels(){return[{provider:"deepseek-account",id:"deepseek-chat",name:"Inert",inputModalities:["text"] as const}];}
    async resolveModel(){return{provider:"deepseek-account",id:"deepseek-chat",name:"Inert",inputModalities:["text"] as const,context:{contextWindow:1024}};}
    async *stream(options:GenerateOptions,permit?:NativeLlmWritePermit):AsyncIterable<StreamChunk>{
      permit?.assertCurrent();seen.writes++;seen.requests.push(options);
      await onStream?.(ctx,options);
      if(hang){
        yield{type:"block-start",index:0,blockType:"text"};
        await new Promise<void>((_resolve,reject)=>{
          if(options.signal?.aborted){reject(Error("cancelled"));return;}
          options.signal?.addEventListener("abort",()=>reject(Error("cancelled")),{once:true});
        });return;
      }
      if(tool&&seen.requests.length===1){
        yield{type:"block-start",index:0,blockType:"tool-call"};
        yield{type:"block-end",index:0,block:{type:"tool-call",id:ToolCallId("original-read"),name:"read",arguments:"{}"}};
        yield{type:"finish",reason:{kind:"tool-calls"}};return;
      }
      yield*text(read?"Native answer "+seen.writes:"Original native answer");
    }
  }
  ctx.llm.registerAdapter(["deepseek-account"],new Inert());
  for(const name of ["read","glob","grep"])ctx.tools.register({
    name,description:"Inert owned "+name,parameters:{type:"object",properties:{}},
    output:{schema:{type:"string"},render:(_args,value)=>[{type:"text",text:value as string}]},
    execute:async()=>{seen.tools++;return"original read data";},
  });
  await ctx.plugin(AgentLoop,{agents:[]});
  bindings.bindServices({requireLoaderCurrent:()=>true,toolModules:()=>true});
  if(read){
    await ctx.plugin(TypertRegistry);
    const controllerDependencies = ["agentDefaultModel","attachments","fileUploads","fs","llm","remoteAccess",
      "sessionProjections","sessionQuery","workspaceRegistry"].filter(name=>ctx.get(name)!==undefined);
    await ctx.plugin({inject:["sessions","agents","sessionPersistence","typert",...controllerDependencies],apply(inner:Context){
      createSessionTestController(inner,{defaultModelSelection:()=>({provider:"deepseek-account",model:"deepseek-chat"}),cwd:workspace});
    }});
    provideBrowserCredentials(ctx);await ctx.plugin(Connection);await ctx.plugin(TypertGateway);
  }
  const a=new TransformStream<Uint8Array,Uint8Array>(),b=new TransformStream<Uint8Array,Uint8Array>();
  const toHost=new PassThrough(),fromHost=new PassThrough();
  const port=Duplex.from({readable:toHost,writable:fromHost}),peer=Duplex.from({readable:fromHost,writable:toHost});
  port.on("error",()=>{});peer.on("error",()=>{});
  cleanup.push(async()=>{port.destroy();peer.destroy();});
  const output=read?createNativeReadOutputGuard(port):undefined;
  const hostStream=read?output!.wrap(ndJsonStream(Writable.toWeb(port),Readable.toWeb(port))):ndJsonStream(a.writable,b.readable);
  const clientStream=read?ndJsonStream(Writable.toWeb(peer),Readable.toWeb(peer)):ndJsonStream(b.writable,a.readable);
  await ctx.plugin({name:"native-entry-unit",inject:[...Acp.inject,...(read?readInject:[])],apply(inner:Context){
    bindings.bindAcpFiber(inner.fiber);
    const nativeReadAdmission=read?createNativeReadAdmission({bindings,generation,
      bridge:createCompanySessionReadBridge(inner),executeRead:executeExecutiveNativeRead,output,packageSha256:"3".repeat(64)}):undefined;
    Acp.apply(inner,{provider:"deepseek-account",model:"deepseek-chat",stream:hostStream,
      ...(nativeReadAdmission?{nativeReadAdmission}:{}),
      nativePromptAdmission:bindings.nativePromptAdmission,nativeObservation:bindings.nativeObservation,
      nativeModelAdmission:facts=>{seen.assignments++;return bindings.nativeModelAdmission(facts);}});
  }});
  const claims:any[]=[],updates:any[]=[];
  const connection=createClient({name:"native-entry-unit"})
    .onNotification(methods.client.session.update,({params})=>{updates.push(params);})
    .onRequest(methods.client.session.requestPermission,()=>({outcome:{outcome:"cancelled" as const}}))
    .onNotification("_mastermind/native_claim",(x:any)=>x,({params})=>{claims.push(params);})
    .connect(clientStream);
  const client=connection.agent;
  const initialized:any=await client.request(methods.agent.initialize,{protocolVersion:PROTOCOL_VERSION,clientCapabilities:{}});
  if(beforeNew)await beforeNew(client);
  const selected=await client.request(methods.agent.session.new,{cwd:workspace,mcpServers:[]});
  const sessionId=selected.sessionId,agent=ctx.agents.get(SessionId(sessionId))!;
  const observe=()=>client.request("_mastermind/native_observe",{schema:"mastermind.dsh.native_observation_request.v1",sessionId});
  const prompt=(id="original-op",content:any[]=[{type:"text",text:"Original question"}])=>client.request(methods.agent.session.prompt,{
    sessionId,prompt:content,_meta:{mastermindNative:{operationId:id}},
  });
  return{ctx,workspace,generation,account,seen,bindings,sourceFacts,client,sessionId,agent,selected,initialized,observe,prompt,claims,updates};
}
it("joins the original zero-setter startup, observed account and original answer",async()=>{
  const h=await host();
  expect(h.selected.configOptions?.some((x:any)=>x.currentValue==='["deepseek-account","deepseek-chat"]')).toBe(true);
  const observation:any=await h.observe();
  expect(observation.schema).toBe("mastermind.dsh.native_owner_observation.v1");
  expect(observation.facts.agent_id).toBe(h.sessionId);
  expect(observation.facts.account).toEqual({inference_origin:"https://api.deepseek.com",user_id:null});
  expect(observation.facts.capabilities.map((x:any)=>x.name)).toEqual(["read","glob","grep","mastermind-company"]);
  expect(h.seen.assignments).toBe(0);
  const terminal=await h.prompt();
  expect(terminal.stopReason).toBe("end_turn");expect(h.seen.writes).toBe(1);expect(h.claims).toHaveLength(1);
  expect(h.ctx.sessions.get(SessionId(h.sessionId))).toBe(h.agent.session);
  expect(h.updates.filter(x=>x.update.sessionUpdate==="agent_message_chunk").map(x=>x.update.content.text).join(""))
    .toBe("Original native answer");
  await expect(h.client.request(methods.agent.session.new,{cwd:h.workspace,mcpServers:[]})).rejects.toThrow();
});
it("keeps one operation through actual tool dispatch and the next native model step",async()=>{
  const h=await host({tool:true});await h.observe();await h.prompt();
  expect(h.seen.tools).toBe(1);expect(h.seen.writes).toBe(2);expect(h.claims).toHaveLength(1);
  expect(h.seen.requests[1].messages.some((x:any)=>x.role==="tool"||x.content?.some((b:any)=>b.type==="tool-result"))).toBe(true);
  expect(h.updates.some(x=>x.update.sessionUpdate==="tool_call_update"&&x.update.status==="completed")).toBe(true);
});
it("pre-enqueue content refusal leaves the same original owner available",async()=>{
  const h=await host();await h.observe();
  await expect(h.prompt("bad-content",[{type:"image",data:"AA==",mimeType:"image/png"}])).rejects.toThrow();
  expect(h.seen.writes).toBe(0);
  await expect(h.prompt("valid-content")).resolves.toMatchObject({stopReason:"end_turn"});
  expect(h.seen.writes).toBe(1);
});
it("requires the observed eligible account before Send and retires it on logout",async()=>{
  const h=await host();
  await expect(h.prompt("before-observation")).rejects.toThrow();
  await h.observe();h.account.current=false;
  await expect(h.prompt("after-account-retirement")).rejects.toThrow();
  expect(h.seen.writes).toBe(0);expect(h.claims).toEqual([]);
});
it("refuses public inbox injection and another model assignment after observation",async()=>{
  const h=await host();await h.observe();
  expect(()=>h.agent.inbox.append("next-turn",createUserMessage({source:{kind:"user"},content:[{type:"text",text:"unowned"}]}))).toThrow();
  await expect(h.client.request(methods.agent.session.setConfigOption,{
    sessionId:h.sessionId,configId:"model",value:'["deepseek-account","deepseek-chat"]',
  })).rejects.toThrow();
  expect(h.seen.writes).toBe(0);await expect(h.prompt()).resolves.toMatchObject({stopReason:"end_turn"});
});
it("refuses MCP startup before the sole original association is consumed",async()=>{
  const h=await host({beforeNew:async client=>{
    await expect(client.request(methods.agent.session.new,{cwd:process.cwd(),
      mcpServers:[{name:"foreign",command:"false",args:[],env:[]}]})).rejects.toThrow("MCP");
  }});
  await h.observe();expect(h.seen.writes).toBe(0);
});
it("receipt-first Stop settles the retained original prompt",async()=>{
  const h=await host({hang:true});await h.observe();
  const pending=h.prompt();await vi.waitFor(()=>expect(h.claims).toHaveLength(1));
  const claim=h.claims[0];
  await expect(h.client.request("_mastermind/native_cancel",claim)).resolves.toMatchObject({status:"requested"});
  await expect(pending).resolves.toMatchObject({stopReason:"cancelled"});
  expect(h.seen.writes).toBe(1);expect(h.ctx.agents.get(SessionId(h.sessionId))).toBe(h.agent);
});

it("an ordinary cached-profile refresh preserves the original grant and same Session",async()=>{
  const h=await host();await h.observe();
  h.account.cache++;h.account.userId="original-account";
  await expect(h.prompt("same-grant")).resolves.toMatchObject({stopReason:"end_turn"});
  const next:any=await h.observe();
  expect(next.facts.account.user_id).toBe("original-account");expect(h.seen.writes).toBe(1);
  expect(h.ctx.agents.get(SessionId(h.sessionId))).toBe(h.agent);
  h.account.current=false;
  await expect(h.observe()).rejects.toThrow();
  await expect(h.prompt("retired-grant")).rejects.toThrow();expect(h.seen.writes).toBe(1);
});
it("the live original step does not authorize unrecorded public tool calls",async()=>{
  const denied:any[]=[];
  const h=await host({onStream:async(ctx,options)=>{
    const agent=ctx.agents.get(SessionId(String(options.sessionId)))!;
    for(const signal of [new AbortController().signal,options.signal!]){
      denied.push(await ctx.tools.execute({agent,signal,callId:ToolCallId("unrecorded"),
        name:"read",arguments:{}}));
    }
  }});
  await h.observe();await h.prompt();
  expect(denied).toHaveLength(2);expect(denied.every(result=>result.isError)).toBe(true);
  expect(h.seen.tools).toBe(0);expect(h.seen.writes).toBe(1);
});
it("native wrappers cannot repeat an original tool body with the same execution token",async()=>{
  const h=await host({tool:true});await h.observe();
  const results:any[]=[];
  h.ctx.on("tools/execute",async(_exec,next)=>{
    const first=await next();results.push(await next());return first;
  });
  await h.prompt();
  expect(h.seen.tools).toBe(1);expect(results).toHaveLength(1);expect(results[0].isError).toBe(true);
  expect(h.seen.writes).toBe(2);
});

it("reads the original claimed answer through the same ACP, Gateway and Session after a later turn and logout",async()=>{
  const h=await host({read:true});await h.observe();
  expect(h.initialized._meta.mastermindNative.schema).toBe("mastermind.dsh.native_prompt_extension.v3");
  const first:any=await h.prompt("first");
  await h.prompt("second");
  const terminal=first._meta.mastermindNative;
  const association={schema:"mastermind.dsh.native_read_association.v1",work_ref:"WS:Original-native",
    root_job_id:"JOB-001",native_session_id:h.sessionId,owner_principal_scope:"1".repeat(64),
    composition_sha256:"2".repeat(64),native_package_sha256:"3".repeat(64),
    donor_sha:"687f282e8625c6b8d11ff58211a90524be2e4317"};
  const request={schema:"mastermind.dsh.native_read.v1",request_id:"4".repeat(64),
    association_sha256:hash(association),principal:{principal_scope:"1".repeat(64),
      issued_at:Math.floor(Date.now()/1000)-1,expires_at:Math.floor(Date.now()/1000)+120},
    read:{kind:"result",claim:terminal.claim,terminal,offset_bytes:0,expected_sha256:null}};
  const envelope={schema:"mastermind.dsh.native_acp_read.v1",sessionId:h.sessionId,association,request};
  const before=h.agent.session.seq;
  h.account.current=false;
  const value:any=await h.client.request("_mastermind/native_read",envelope);
  expect(value.status).toBe("READ");expect(value.data.claim).toEqual(terminal.claim);
  expect(value.data.state).toBe("CONTENT");
  const records=Buffer.from(value.data.content.data,"base64").toString();
  expect(records).toContain("Native answer 1");expect(records).not.toContain("Native answer 2");
  expect(h.agent.session.seq).toBe(before);expect(h.ctx.agents.get(SessionId(h.sessionId))).toBe(h.agent);
  expect(h.seen.writes).toBe(2);
  await expect(h.prompt("signed-out-send")).rejects.toThrow();
  await expect(h.client.request("_mastermind/native_read",{
    ...envelope,association:{...association,native_package_sha256:"9".repeat(64)},
  })).rejects.toThrow();
  const again:any=await h.client.request("_mastermind/native_read",envelope);
  expect(again.data).toEqual(value.data);expect(h.agent.session.seq).toBe(before);
});

it.each(["expiry","source","shutdown"] as const)("withholds %s after original SDK serialization but before physical response write",async fault=>{
  const socket=new PassThrough(),writes:Buffer[]=[];
  socket.on("data",chunk=>writes.push(Buffer.from(chunk)));
  const output=createNativeReadOutputGuard(socket);
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  let current=true,finished=0;
  const response=Object.freeze({schema:"mastermind.dsh.native_read_result.v1",request_id:"a".repeat(64),
    association_sha256:"b".repeat(64),status:"READ",data:{original:"must remain private"}});
  const unavailable=Object.freeze({...response,status:"UNAVAILABLE",data:null});
  output.register({requestId:7,response,unavailable,requireCurrent(){if(!current)throw Error("retired");},finish(){finished++;}});
  const stream=output.wrap(ndJsonStream(new WritableStream({async write(chunk){
    entered.resolve();await release.promise;socket.write(chunk);
  }}),new ReadableStream()));
  const writer=stream.writable.getWriter(),pending=writer.write({jsonrpc:"2.0",id:7,result:response});
  await entered.promise;
  if(fault==="shutdown")output.dispose();else current=false;
  release.resolve();await pending;
  expect(writes).toHaveLength(1);
  expect(JSON.parse(writes[0].toString())).toEqual({jsonrpc:"2.0",id:7,result:unavailable});
  expect(finished).toBe(1);
  await writer.close();await stream.readable.cancel();socket.destroy();
});
