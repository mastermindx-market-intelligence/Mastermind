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
import {canonical,nativeConfig,parseExecutionPolicy,createNativeHostBindings} from "../native_worker.mjs";
import {mkdtemp,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";

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
async function host({tool=false,hang=false,beforeNew,onStream}:{tool?:boolean,hang?:boolean,
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
      yield*text("Original native answer");
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
  const a=new TransformStream<Uint8Array,Uint8Array>(),b=new TransformStream<Uint8Array,Uint8Array>();
  await ctx.plugin({name:"native-entry-unit",inject:[...Acp.inject],apply(inner:Context){
    bindings.bindAcpFiber(inner.fiber);
    Acp.apply(inner,{provider:"deepseek-account",model:"deepseek-chat",stream:ndJsonStream(a.writable,b.readable),
      nativePromptAdmission:bindings.nativePromptAdmission,nativeObservation:bindings.nativeObservation,
      nativeModelAdmission:facts=>{seen.assignments++;return bindings.nativeModelAdmission(facts);}});
  }});
  const claims:any[]=[],updates:any[]=[];
  const connection=createClient({name:"native-entry-unit"})
    .onNotification(methods.client.session.update,({params})=>{updates.push(params);})
    .onRequest(methods.client.session.requestPermission,()=>({outcome:{outcome:"cancelled" as const}}))
    .onNotification("_mastermind/native_claim",(x:any)=>x,({params})=>{claims.push(params);})
    .connect(ndJsonStream(b.writable,a.readable));
  const client=connection.agent;
  await client.request(methods.agent.initialize,{protocolVersion:PROTOCOL_VERSION,clientCapabilities:{}});
  if(beforeNew)await beforeNew(client);
  const selected=await client.request(methods.agent.session.new,{cwd:workspace,mcpServers:[]});
  const sessionId=selected.sessionId,agent=ctx.agents.get(SessionId(sessionId))!;
  const observe=()=>client.request("_mastermind/native_observe",{schema:"mastermind.dsh.native_observation_request.v1",sessionId});
  const prompt=(id="original-op",content:any[]=[{type:"text",text:"Original question"}])=>client.request(methods.agent.session.prompt,{
    sessionId,prompt:content,_meta:{mastermindNative:{operationId:id}},
  });
  return{ctx,workspace,generation,account,seen,bindings,sourceFacts,client,sessionId,agent,selected,observe,prompt,claims,updates};
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
