/** Same native Agent/Session, original ACP SDK decoder, and original persistence. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import {client as createClient,methods,ndJsonStream,PROTOCOL_VERSION,type SendRequestOptions} from "@agentclientprotocol/sdk";
import {LlmAdapter,createUserMessage,ToolCallId,type GenerateOptions,type StreamChunk} from "@deepseek-ai/dsh-llm";
import AgentLoop from "@deepseek-ai/dsh-agent-loop";
import {defineContentToolFixture} from "@deepseek-ai/dsh-tools";
import type {AgentInputCapability} from "@deepseek-ai/dsh-agent";
import {mountAgentLoopTestDependencies} from "@deepseek-ai/dsh-agent-loop-testkit";
import * as Persistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TokenMeter from "@deepseek-ai/dsh-token-meter";
import {SessionId} from "@deepseek-ai/dsh-session";
import * as Acp from "mmx-native-acp";
import {AcpSession} from "mmx-native-acp-session";
import {mkdtemp,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const text=(value:string):StreamChunk[]=>[
  {type:"block-start",index:0,blockType:"text"},
  {type:"text-delta",index:0,text:value},
  {type:"block-end",index:0,block:{type:"text",text:value}},
  {type:"finish",reason:{kind:"stop"}},
];
class FixtureAdapter extends LlmAdapter{
  requests:GenerateOptions[]=[];
  constructor(readonly script:(StreamChunk[]|"hang")[]){super();}
  providerInfo(){return{id:"fixture",name:"Fixture"};}
  async listModels(){return[{provider:"fixture",id:"fixture",name:"Fixture",inputModalities:["text"] as const}];}
  async resolveModel(){return{provider:"fixture",id:"fixture",name:"Fixture",inputModalities:["text"] as const,context:{contextWindow:1024}};}
  async *stream(options:GenerateOptions):AsyncIterable<StreamChunk>{
    this.requests.push(options);
    const next=this.script.shift();
    if(next===undefined)throw Error("native ACP fixture script exhausted");
    if(next==="hang"){
      yield{type:"block-start",index:0,blockType:"text"};
      await new Promise<void>((_resolve,reject)=>{
        if(options.signal?.aborted){reject(Error("fixture aborted"));return;}
        options.signal?.addEventListener("abort",()=>reject(Error("fixture aborted")),{once:true});
      });
    }else for(const chunk of next){options.signal?.throwIfAborted();yield chunk;}
  }
}
async function host(script:(StreamChunk[]|"hang")[],opted=true,guard?:(facts:any)=>boolean,observer?:(facts:any,signal:AbortSignal)=>any,nativeInput?:AgentInputCapability){
  const ctx=new Context(),root=await mkdtemp(join(tmpdir(),"mmx-native-acp-"));
  cleanup.push(async()=>{await ctx.fiber.dispose();await rm(root,{recursive:true,force:true});});
  let nativeOwner:Context["fiber"]|undefined,selectedId:SessionId|undefined;
  const nativeGeneration=new AbortController();
  if(nativeInput!==undefined)ctx.provide("agentLifecycleAdmission",{admit(caller,operation,id){
    if(caller.fiber!==nativeOwner||operation!=="create"||selectedId!==undefined)
      throw Error("Not the original ACP lifecycle owner");
    selectedId=id;
    return{signal:nativeGeneration.signal,input:nativeInput,assertCurrent(){
      if(caller.fiber!==nativeOwner||id!==selectedId)throw Error("Native lifecycle changed");
      return true;
    }};
  }});
  await mountAgentLoopTestDependencies(ctx,{systemPrompt:{personaPrefix:""}});
  await ctx.plugin(Persistence,{root,compression:"none"});
  await ctx.plugin(TokenMeter);await ctx.plugin(AgentLoop,{agents:[]});
  const adapter=new FixtureAdapter(script);ctx.llm.registerAdapter(["fixture"],adapter);
  const a=new TransformStream<Uint8Array,Uint8Array>(),b=new TransformStream<Uint8Array,Uint8Array>();
  const claims:any[]=[],updates:any[]=[];
  const config:any={provider:"fixture",model:"fixture",stream:ndJsonStream(a.writable,b.readable)};
  if(opted)config.nativePromptAdmission=guard??(()=>true);
  if(observer!==undefined)config.nativeObservation=observer;
  await ctx.plugin({name:"native-acp-fixture",inject:[...Acp.inject],apply(inner:Context){nativeOwner=inner.fiber;Acp.apply(inner,config);}});
  const app=createClient({name:"original-native-acp-client"})
    .onNotification(methods.client.session.update,({params})=>{updates.push(params);})
    .onRequest(methods.client.session.requestPermission,()=>({outcome:{outcome:"cancelled" as const}}))
    .onNotification("_mastermind/native_claim",(value:any)=>value,({params})=>{claims.push(params);});
  const connection=app.connect(ndJsonStream(b.writable,a.readable)),client=connection.agent;
  const initialized=await client.request(methods.agent.initialize,{protocolVersion:PROTOCOL_VERSION,clientCapabilities:{}});
  const selected=await client.request(methods.agent.session.new,{cwd:process.cwd(),mcpServers:[]});
  const sessionId=selected.sessionId,agent=ctx.agents.get(SessionId(sessionId))!;
  expect(agent).toBeDefined();expect(agent.session).toBe(ctx.sessions.get(SessionId(sessionId)));
  const prompt=(operationId:string,options?:SendRequestOptions)=>client.request(methods.agent.session.prompt,{
    sessionId,prompt:[{type:"text" as const,text:"original question"}],_meta:{mastermindNative:{operationId}},
  },options);
  const cancel=(claim:any)=>client.request("_mastermind/native_cancel",claim);
  const claimed=async(count=1)=>{await vi.waitFor(()=>expect(claims.length).toBe(count));return claims[count-1];};
  return{ctx,root,config,adapter,client,connection,initialized,sessionId,agent,claims,updates,prompt,cancel,claimed};
}

it("observes one actual first inbox claim and flushes the original native result",async()=>{
  const h=await host([text("original answer")]);
  expect(h.initialized._meta).toMatchObject({mastermindNative:{schema:"mastermind.dsh.native_prompt_extension.v1"}});
  const flush=vi.spyOn(h.ctx.sessions,"flush");
  const result=await h.prompt("operation-one"),claim=await h.claimed();
  const user=h.agent.session.snapshotEvents().find(event=>event.type==="user/message")!;
  expect(claim).toEqual({schema:"mastermind.dsh.native_prompt_claim.v1",operationId:"operation-one",
    requestId:expect.any(Number),sessionId:h.sessionId,messageId:(user.data as any).id,
    nativeTurn:expect.any(Number),throughSeq:expect.any(Number)});
  expect(claim.throughSeq).toBeLessThan(h.agent.session.seq);
  expect(result).toMatchObject({stopReason:"end_turn",_meta:{mastermindNative:{
    schema:"mastermind.dsh.native_prompt_terminal.v1",operationId:"operation-one",claim,
    observedLastTurn:claim.nativeTurn,observedTurnCount:1,throughSeq:expect.any(Number),
  }}});
  expect(flush).toHaveBeenCalledWith(h.agent.session);
  expect((result._meta as any).mastermindNative.throughSeq).toBe(h.agent.session.seq-1);
  expect(h.updates.filter(x=>x.update.sessionUpdate==="agent_message_chunk").map(x=>x.update.content.text).join("")).toBe("original answer");
  expect(h.adapter.requests).toHaveLength(1);
});

it("requests one exact Stop while collection remains owned and keeps ACK separate from terminal",async()=>{
  const h=await host(["hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.sessions.flush.bind(h.ctx.sessions);
  vi.spyOn(h.ctx.sessions,"flush").mockImplementation(async(...args)=>{entered.resolve();await release.promise;await original(...args);});
  const pending=h.prompt("exact-stop");
  const claim=await h.claimed();
  await expect(h.cancel(claim)).resolves.toEqual({status:"requested"});
  await entered.promise;
  await expect(h.cancel(claim)).resolves.toEqual({status:"already_requested"});
  expect(nativeCancel).toHaveBeenCalledTimes(1);
  let settled=false;void pending.then(()=>{settled=true;});
  await Promise.resolve();expect(settled).toBe(false);
  release.resolve();
  await expect(pending).resolves.toMatchObject({stopReason:"cancelled",_meta:{mastermindNative:{claim}}});
  await expect(h.cancel(claim)).resolves.toEqual({status:"not_current"});
  expect(nativeCancel).toHaveBeenCalledTimes(1);
});

it("refuses every foreign claim field before native cancellation",async()=>{
  const h=await host(["hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const pending=h.prompt("exact-original"),claim=await h.claimed();
  for(const changed of [
    {operationId:"other"},{requestId:typeof claim.requestId==="number"?claim.requestId+1:"other"},
    {sessionId:"foreign"},{messageId:"foreign"},{nativeTurn:claim.nativeTurn+1},{throughSeq:claim.throughSeq+1},
  ])await expect(h.cancel({...claim,...changed})).resolves.toEqual({status:"not_current"});
  await expect(h.cancel({...claim,extra:true})).rejects.toThrow();
  expect(nativeCancel).not.toHaveBeenCalled();
  await h.cancel(claim);await pending;
});

it("a closed first turn cannot be cancelled while original persistence is pending",async()=>{
  const h=await host([text("complete")]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.sessions.flush.bind(h.ctx.sessions);
  vi.spyOn(h.ctx.sessions,"flush").mockImplementation(async(...args)=>{entered.resolve();await release.promise;await original(...args);});
  const pending=h.prompt("closed-first"),claim=await h.claimed();
  await entered.promise;
  await expect(h.cancel(claim)).resolves.toEqual({status:"native_turn_closed_or_superseded"});
  expect(nativeCancel).not.toHaveBeenCalled();
  release.resolve();await pending;
});

it("a later autonomous native turn is not owned by a pending earlier ACP prompt",async()=>{
  const h=await host([text("first"),"hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.sessions.flush.bind(h.ctx.sessions);
  vi.spyOn(h.ctx.sessions,"flush").mockImplementation(async(...args)=>{entered.resolve();await release.promise;await original(...args);});
  const pending=h.prompt("first-root"),claim=await h.claimed();
  await entered.promise;
  h.agent.followup(createUserMessage({content:[{type:"text",text:"independent later work"}],source:{kind:"user"}}));
  await vi.waitFor(()=>expect(h.adapter.requests).toHaveLength(2));
  await expect(h.cancel(claim)).resolves.toEqual({status:"native_turn_closed_or_superseded"});
  expect(nativeCancel).not.toHaveBeenCalled();
  h.agent.cancel({kind:"user"}); // explicit original-owner fixture cleanup only
  release.resolve();
  const result=await pending;
  expect((result._meta as any).mastermindNative).toMatchObject({claim,observedTurnCount:2});
});

it("an old tuple cannot cancel the next ACP prompt",async()=>{
  const h=await host([text("first"),"hang"]);
  await h.prompt("first");const old=await h.claimed();
  const nativeCancel=vi.spyOn(h.agent,"cancel"),next=h.prompt("second"),current=await h.claimed(2);
  await expect(h.cancel(old)).resolves.toEqual({status:"not_current"});
  expect(nativeCancel).not.toHaveBeenCalled();
  await expect(h.cancel(current)).resolves.toEqual({status:"requested"});
  await next;expect(nativeCancel).toHaveBeenCalledTimes(1);
});

it("checks runtime authority again after prompt admission and before native enqueue",async()=>{
  let admissions=0;
  const h=await host([text("must never run")],true,facts=>facts.action!=="admit"||++admissions<2);
  const followup=vi.spyOn(h.agent,"followup");
  await expect(h.prompt("retired-before-enqueue")).rejects.toThrow();
  expect(admissions).toBe(2);expect(followup).not.toHaveBeenCalled();
  expect(h.adapter.requests).toHaveLength(0);expect(h.claims).toEqual([]);
});

it("rejects runtime check replacement without borrowing its new grant",async()=>{
  let h:Awaited<ReturnType<typeof host>>;
  h=await host([text("must never run")],true,()=>{h.config.nativePromptAdmission=()=>true;return true;});
  await expect(h.prompt("replaced-check")).rejects.toThrow();
  expect(h.adapter.requests).toHaveLength(0);expect(h.claims).toEqual([]);
});

it("does not turn a native flush failure into a successful terminal result or retry",async()=>{
  const h=await host([text("committed first")]);
  const flush=vi.spyOn(h.ctx.sessions,"flush").mockRejectedValue(Error("original flush failed"));
  await expect(h.prompt("flush-failure")).rejects.toThrow("prompt settlement failed");
  expect(h.adapter.requests).toHaveLength(1);
  flush.mockRestore();
});

it("requires closed correlation metadata for opted-in prompts",async()=>{
  const h=await host([text("must never run")]);
  for(const meta of [undefined,{}, {mastermindNative:{operationId:"op",extra:true}}, {mastermindNative:{operationId:""}}]){
    await expect(h.client.request(methods.agent.session.prompt,{
      sessionId:h.sessionId,prompt:[{type:"text",text:"no valid correlation"}],...(meta===undefined?{}:{_meta:meta}),
    })).rejects.toThrow();
  }
  expect(h.adapter.requests).toHaveLength(0);
});

it("a late SDK request abort cannot cancel a successor native turn",async()=>{
  const h=await host([text("first"),"hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>(),abort=new AbortController();
  const original=h.ctx.sessions.flush.bind(h.ctx.sessions);
  vi.spyOn(h.ctx.sessions,"flush").mockImplementation(async(...args)=>{entered.resolve();await release.promise;await original(...args);});
  const pending=h.prompt("transport-waiter",{cancellationSignal:abort.signal});
  const observed=pending.then(value=>({value}),error=>({error}));
  try{
    const claim=await h.claimed();await entered.promise;
    h.agent.followup(createUserMessage({content:[{type:"text",text:"later autonomous work"}],source:{kind:"user"}}));
    await vi.waitFor(()=>expect(h.adapter.requests).toHaveLength(2));
    abort.abort();
    // The maintained SDK sends cancellation but retains the original response
    // promise. The next ordered request observes that notification's delivery.
    await expect(h.cancel(claim)).resolves.toEqual({status:"native_turn_closed_or_superseded"});
    expect(nativeCancel).not.toHaveBeenCalled();
  }finally{
    h.agent.cancel({kind:"user"});release.resolve();
    await h.agent.whenIdle();await observed;
  }
});

it("preserves default standard prompt, cancellation and notification behavior",async()=>{
  const h=await host([text("ordinary"),"hang"],false);
  expect(h.initialized._meta).toBeUndefined();
  const ordinary=()=>h.client.request(methods.agent.session.prompt,{sessionId:h.sessionId,prompt:[{type:"text",text:"ordinary"}]});
  await expect(ordinary()).resolves.toEqual({stopReason:"end_turn"});
  const pending=ordinary();await vi.waitFor(()=>expect(h.adapter.requests).toHaveLength(2));
  await h.client.notify(methods.agent.session.cancel,{sessionId:h.sessionId});
  await expect(pending).resolves.toEqual({stopReason:"cancelled"});
  expect(h.claims).toEqual([]);
  await expect(h.cancel({})).rejects.toThrow();
});


it("a trusted callback abort cannot enqueue after the original admission signal retires",async()=>{
  const h=await host([text("must never run")],false),controller=new AbortController();
  const record=await AcpSession.create(h.ctx,{
    sessionId:SessionId("callback-abort-native-session"),cwd:process.cwd(),mcpServers:[],
    agentOptions:{},fallbackSelection:{provider:"fixture",model:"fixture"},
    signal:new AbortController().signal,notify:async()=>{},
  });
  const followup=vi.spyOn(record.agent,"followup");let admissions=0;
  try{
    await expect(record.prompt({sessionId:record.agent.session.id,prompt:[{type:"text",text:"must not enqueue"}]},
      false,controller.signal,{
        operationId:"callback-abort",requestId:"actual-direct-native-request",
        requireCurrent(action:any){if(action==="admit"&&++admissions===2)controller.abort();},
        notifyClaim:async()=>{},
      })).resolves.toMatchObject({stopReason:"cancelled"});
    expect(admissions).toBe(2);expect(followup).not.toHaveBeenCalled();
    expect(h.adapter.requests).toHaveLength(0);
  }finally{await record.close("original direct fixture cleanup");}
});

it("a retired guard at the actual first claim reaches no model work",async()=>{
  let current=true;
  const h=await host([text("must never run")],true,facts=>{
    if(facts.action==="claim")current=false;
    return current;
  });
  await expect(h.prompt("retired-at-claim")).rejects.toThrow();
  expect(h.claims).toEqual([]);expect(h.adapter.requests).toHaveLength(0);
});

it("opted-in uncorrelated standard cancellation cannot act on the native Agent",async()=>{
  const h=await host(["hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const pending=h.prompt("correlated-only"),claim=await h.claimed();
  await h.client.notify(methods.agent.session.cancel,{sessionId:h.sessionId});
  await expect(h.cancel({...claim,messageId:"foreign"})).resolves.toEqual({status:"not_current"});
  expect(nativeCancel).not.toHaveBeenCalled();
  await h.cancel(claim);await pending;
});


it("exact current-turn Stop preserves unrelated pending native inbox work",async()=>{
  const h=await host(["hang"]),nativeCancel=vi.spyOn(h.agent,"cancel");
  const pending=h.prompt("current-turn-only"),claim=await h.claimed();
  await vi.waitFor(()=>expect(h.adapter.requests).toHaveLength(1));
  const later=createUserMessage({content:[{type:"text",text:"preserved native next turn"}],source:{kind:"user"}});
  h.agent.followup(later);
  expect(h.agent.inbox.nextTurn.map((item:any)=>item.id)).toContain(later.id);
  await expect(h.cancel(claim)).resolves.toEqual({status:"requested"});
  await expect(pending).resolves.toMatchObject({stopReason:"cancelled"});
  expect(h.agent.inbox.nextTurn.map((item:any)=>item.id)).toContain(later.id);
  expect(nativeCancel).toHaveBeenCalledExactlyOnceWith({kind:"user"},{keepInbox:true});
  expect(h.adapter.requests).toHaveLength(1);
});


const observedWire=()=>({
  served_model:null,harness_version:null,harness_binary_digest:null,capabilities:[],
  effective_skills:[],effective_mcp:[],effective_plugins_or_apps:[],
  sandbox_state:null,approval_state:null,network_state:null,effective_config_digest:null,
  auth:{worker_id:"fixture-worker",provider:"acp",auth_class:null,plan_type:null,
    nonsecret_provider_account_id:null,identity_confidence:"UNKNOWN",attestation_status:"fixture-only"},
  workspace:null,supports_subagent_capability_ceiling:"UNKNOWN",unknown_fields:[],
});
const observationRequest=(sessionId:string)=>({schema:"mastermind.dsh.native_observation_request.v1",sessionId});

it("advertises exact v2 only with an original passive observer and preserves null facts",async()=>{
  const seen:any[]=[];
  const h=await host([],true,undefined,(facts,signal)=>{
    seen.push({facts,signal});return observedWire();
  });
  expect(h.initialized._meta).toEqual({mastermindNative:{
    schema:"mastermind.dsh.native_prompt_extension.v2",
    claimMethod:"_mastermind/native_claim",cancelMethod:"_mastermind/native_cancel",
    observeMethod:"_mastermind/native_observe",
  }});
  const flush=vi.spyOn(h.ctx.sessions,"flush"),cancel=vi.spyOn(h.agent,"cancel");
  const response=await h.client.request("_mastermind/native_observe",observationRequest(h.sessionId));
  expect(response).toEqual({schema:"mastermind.dsh.native_observation.v1",sessionId:h.sessionId,attestation:observedWire()});
  expect(seen).toHaveLength(1);expect(seen[0].facts.agent).toBe(h.agent);
  expect(h.ctx.agents).not.toBe(h.ctx.agents);expect(h.ctx.sessions).not.toBe(h.ctx.sessions);
  expect(seen[0].facts.selection).toEqual({provider:"fixture",model:"fixture"});
  expect(Object.isFrozen(seen[0].facts)).toBe(true);expect(Object.isFrozen(seen[0].facts.selection)).toBe(true);
  expect(h.adapter.requests).toHaveLength(0);expect(h.claims).toHaveLength(0);
  expect(cancel).not.toHaveBeenCalled();expect(flush).not.toHaveBeenCalled();
});

it("keeps the exact v1 advertisement and no observation method for admission-only hosts",async()=>{
  const h=await host([]);
  expect(h.initialized._meta).toEqual({mastermindNative:{
    schema:"mastermind.dsh.native_prompt_extension.v1",
    claimMethod:"_mastermind/native_claim",cancelMethod:"_mastermind/native_cancel",
  }});
  await expect(h.client.request("_mastermind/native_observe",observationRequest(h.sessionId))).rejects.toThrow();
  expect(h.adapter.requests).toHaveLength(0);
});

it("refuses observation composition without original admission",async()=>{
  await expect(host([],false,undefined,()=>observedWire())).rejects.toThrow();
});

it.each(["extra","schema","session","missing"])("rejects a %s observation request without calling the observer",async(change)=>{
  const observer=vi.fn(()=>observedWire()),h=await host([],true,undefined,observer);
  const request:any=observationRequest(h.sessionId);
  if(change==="extra")request.authority=true;
  else if(change==="schema")request.schema="other";
  else if(change==="session")request.sessionId="unknown-session";
  else delete request.schema;
  await expect(h.client.request("_mastermind/native_observe",request)).rejects.toThrow();
  expect(observer).not.toHaveBeenCalled();expect(h.adapter.requests).toHaveLength(0);
});

it.each(["callback","admission","agent","session","selection","selection-value","watermark","close"])(
  "rejects %s replacement during passive observation",async(change)=>{
    const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
    let record:any;
    const original=AcpSession.prototype.observationSnapshot;
    const snapshot=vi.spyOn(AcpSession.prototype,"observationSnapshot");
    // The spy wraps the original implementation and exposes only the existing record.
    snapshot.mockImplementation(function(this:any){record=this;return original.apply(this);});
    const h=await host([],true,undefined,async()=>{entered.resolve();await release.promise;return observedWire();});
    const waiting=h.client.request("_mastermind/native_observe",observationRequest(h.sessionId))
      .then(value=>({ok:true,value}),error=>({ok:false,error}));
    await Promise.race([entered.promise,waiting.then(()=>{throw Error("observer did not reach its await");})]);
    let restore=()=>{};
    if(change==="callback")h.config.nativeObservation=()=>observedWire();
    else if(change==="admission")h.config.nativePromptAdmission=()=>true;
    else if(change==="agent"){
      const get=h.ctx.agents.get.bind(h.ctx.agents),spy=vi.spyOn(h.ctx.agents,"get");
      spy.mockImplementation((id:any)=>id===h.agent.id?({} as any):get(id));restore=()=>spy.mockRestore();
    }else if(change==="session"){
      const get=h.ctx.sessions.get.bind(h.ctx.sessions),spy=vi.spyOn(h.ctx.sessions,"get");
      spy.mockImplementation((id:any)=>id===h.agent.session.id?({} as any):get(id));restore=()=>spy.mockRestore();
    }else if(change==="selection"){
      record.modelControl.selection.current={...record.modelControl.snapshot()};
    }else if(change==="selection-value"){
      record.modelControl.selection.current.model="changed";
    }else if(change==="watermark"){
      const session=h.agent.session as any,seq=session.seq,descriptor=Object.getOwnPropertyDescriptor(session,"seq");
      Object.defineProperty(session,"seq",{configurable:true,get:()=>seq+1});
      restore=()=>{if(descriptor)Object.defineProperty(session,"seq",descriptor);else delete session.seq;};
    }else{
      await h.client.request(methods.agent.session.close,{sessionId:h.sessionId});
    }
    release.resolve();
    try{expect(await waiting).toMatchObject({ok:false});expect(h.adapter.requests).toHaveLength(0);expect(h.claims).toHaveLength(0);}
    finally{restore();snapshot.mockRestore();}
  },
);

it("refuses a busy observation without cancelling or advancing the native turn",async()=>{
  const observer=vi.fn(()=>observedWire()),h=await host(["hang"],true,undefined,observer);
  const pending=h.prompt("observed-busy"),claim=await h.claimed();
  const cancel=vi.spyOn(h.agent,"cancel");
  await expect(h.client.request("_mastermind/native_observe",observationRequest(h.sessionId))).rejects.toThrow();
  expect(observer).not.toHaveBeenCalled();expect(cancel).not.toHaveBeenCalled();
  expect(h.adapter.requests).toHaveLength(1);
  await h.cancel(claim);await pending;
});

it.each(["extra","missing-null","oversized","accessor","sparse","custom-serializer","secret"])(
  "rejects %s observation output without executing data accessors",async(change)=>{
    const output:any=observedWire(),executed=vi.fn();
    if(change==="extra")output.extra=true;
    else if(change==="missing-null")delete output.workspace;
    else if(change==="oversized")output.unknown_fields=["x".repeat(32*1024)];
    else if(change==="accessor")Object.defineProperty(output,"served_model",{enumerable:true,get(){executed();return null;}});
    else if(change==="sparse")output.effective_skills=new Array(1);
    else if(change==="custom-serializer")output.toJSON=()=>{executed();return observedWire();};
    else output.auth.auth_class="auth.json";
    const observer=vi.fn(()=>output),h=await host([],true,undefined,observer);
    await expect(h.client.request("_mastermind/native_observe",observationRequest(h.sessionId))).rejects.toThrow();
    expect(observer).toHaveBeenCalledTimes(1);expect(executed).not.toHaveBeenCalled();expect(h.adapter.requests).toHaveLength(0);
  },
);

it("keeps native selection and a returned observation detached from observer mutation",async()=>{
  const output=observedWire();let facts:any;
  const h=await host([],true,undefined,(value)=>{facts=value;return output;});
  const response:any=await h.client.request("_mastermind/native_observe",observationRequest(h.sessionId));
  expect(()=>{facts.selection.model="changed";}).toThrow();
  output.auth.worker_id="changed";
  expect(response.attestation.auth.worker_id).toBe("fixture-worker");
  const next:any=await h.client.request("_mastermind/native_observe",observationRequest(h.sessionId));
  expect(facts.selection.model).toBe("fixture");expect(next.attestation.auth.worker_id).toBe("changed");
});


it("cancels only the observation waiter and retains its idle native owner",async()=>{
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  let calls=0,originalSignal:AbortSignal|undefined;
  const h=await host([],true,undefined,async(_facts,signal)=>{
    calls++;originalSignal=signal;
    if(calls===1){entered.resolve();await release.promise;}
    return observedWire();
  });
  const cancel=vi.spyOn(h.agent,"cancel"),abort=new AbortController();
  const waiting=h.client.request("_mastermind/native_observe",observationRequest(h.sessionId),{cancellationSignal:abort.signal})
    .then(value=>({ok:true,value}),error=>({ok:false,error}));
  await Promise.race([entered.promise,waiting.then(()=>{throw Error("observer did not reach its await");})]);
  let settled=false;void waiting.then(()=>{settled=true;});
  abort.abort();
  await vi.waitFor(()=>expect(originalSignal?.aborted).toBe(true));
  expect(settled).toBe(false); // original SDK cancellation waits for the peer response
  release.resolve();expect(await waiting).toMatchObject({ok:false});
  const response:any=await h.client.request("_mastermind/native_observe",observationRequest(h.sessionId));
  expect(response.sessionId).toBe(h.sessionId);expect(h.ctx.agents.get(h.agent.id)).toBe(h.agent);
  expect(cancel).not.toHaveBeenCalled();expect(h.adapter.requests).toHaveLength(0);expect(h.claims).toHaveLength(0);
});


/** Private fixture operation slot, consumed only by the original Inbox writer. */
async function inputHost(script:(StreamChunk[]|"hang")[],onEnqueue?:(facts:any,owner:any)=>boolean){
  let current=true;
  let candidate:any;
  const enqueues:any[]=[],retirements:any[]=[],consumed:any[]=[];
  const capability:AgentInputCapability={
    assertCurrent(){if(!current)throw Error("Original input owner retired");return true;},
    consume(attempt){
      const owned=candidate;
      if(owned===undefined||owned.consumed||owned.retired||attempt.agent!==owned.facts.agent
          ||attempt.session!==owned.session||attempt.sessionSeq!==owned.seq
          ||attempt.target!=="next-turn"||attempt.start!==0||attempt.removedCount!==0
          ||attempt.inserted.length!==1||attempt.inserted[0]!==owned.facts.message
          ||attempt.send?.message!==owned.facts.message||attempt.send.requestedTarget!=="next-turn"
          ||attempt.send.wakeup!==true||attempt.agent.inbox.hasPending)
        throw Error("No original ACP enqueue candidate");
      owned.consumed=true;consumed.push(owned);
      return true;
    },
  };
  const owner:any={enqueues,retirements,consumed,capability,candidate:()=>candidate,retire(){current=false;}};
  const guard=(facts:any)=>{
    if(facts.action==="retire"){
      retirements.push(facts);
      if(candidate!==undefined&&candidate.facts.agent===facts.agent&&candidate.session===facts.agent.session
          &&candidate.facts.operationId===facts.operationId&&candidate.facts.requestId===facts.requestId
          &&candidate.facts.message===facts.message)candidate.retired=true;
      return true;
    }
    if(!current)return false;
    if(facts.action==="enqueue"){
      if(candidate!==undefined&&!candidate.retired)throw Error("Original candidate still owned");
      candidate={facts,session:facts.agent.session,seq:facts.agent.session.seq,consumed:false,retired:false};
      enqueues.push(facts);
      return onEnqueue?.(facts,owner)??true;
    }
    return true;
  };
  const h=await host(script,true,guard,undefined,capability);
  return{...h,owner,originalGuard:guard};
}
it("joins real ACP enqueue to the original native Inbox once",async()=>{
  const h=await inputHost([text("admitted native answer")],facts=>{
    expect(Object.isFrozen(facts.message)).toBe(true);
    expect(()=>facts.agent.inbox.append("next-turn",facts.message)).toThrow("No original ACP enqueue candidate");
    return true;
  });
  expect(()=>h.agent.followup(createUserMessage({content:[{type:"text",text:"outside ACP"}],source:{kind:"user"}})))
    .toThrow("No original ACP enqueue candidate");
  const result=await h.prompt("joined-original-enqueue");
  expect(result.stopReason).toBe("end_turn");
  expect(h.owner.enqueues).toHaveLength(1);expect(h.owner.consumed).toHaveLength(1);
  expect(h.owner.retirements).toHaveLength(1);expect(h.owner.candidate().consumed).toBe(true);
  const facts=h.owner.enqueues[0],claim=h.claims[0];
  expect(facts.agent).toBe(h.agent);expect(facts.message.id).toBe(claim.messageId);
  expect(facts.requestId).toBe(claim.requestId);expect(facts.operationId).toBe(claim.operationId);
  expect(()=>h.agent.followup(facts.message)).toThrow("No original ACP enqueue candidate");
  expect(h.adapter.requests).toHaveLength(1);
});
it.each(["false","throw","retire-generation","replace-callback"] as const)(
  "retires the exact unused enqueue after %s without clearing or replaying another operation",async(failure)=>{
    let h:any;
    h=await inputHost([text("later original operation")],(facts,owner)=>{
      if(facts.operationId!=="failed-enqueue")return true;
      if(failure==="throw")throw Error("original enqueue authority failure");
      if(failure==="retire-generation")owner.retire();
      if(failure==="replace-callback")h.config.nativePromptAdmission=vi.fn(()=>true);
      return false;
    });
    await expect(h.prompt("failed-enqueue")).rejects.toThrow();
    expect(h.owner.enqueues).toHaveLength(1);expect(h.owner.retirements).toHaveLength(1);
    expect(h.owner.candidate()).toMatchObject({consumed:false,retired:true});
    expect(h.owner.retirements[0].message).toBe(h.owner.enqueues[0].message);
    expect(h.agent.inbox.hasPending).toBe(false);expect(h.adapter.requests).toHaveLength(0);
    if(failure==="replace-callback")expect(h.config.nativePromptAdmission).not.toHaveBeenCalled();
    if(failure==="false"||failure==="throw"){
      await h.prompt("next-original-enqueue");
      expect(h.owner.consumed).toHaveLength(1);expect(h.adapter.requests).toHaveLength(1);
      expect(h.owner.consumed[0].facts.operationId).toBe("next-original-enqueue");
    }
  },
);
it("does not retire an earlier prompt when a concurrent prompt is refused before enqueue",async()=>{
  const h=await inputHost(["hang"]);
  const pending=h.prompt("still-original").then(value=>({value}),error=>({error}));
  const claim=await h.claimed();
  await expect(h.prompt("unadmitted-concurrent")).rejects.toThrow("already in flight");
  expect(h.owner.retirements).toEqual([]);expect(h.owner.enqueues).toHaveLength(1);
  expect(h.owner.candidate().facts.operationId).toBe("still-original");
  await h.cancel(claim);expect(await pending).toHaveProperty("value");
  expect(h.owner.retirements.map((x:any)=>x.operationId)).toEqual(["still-original"]);
  expect(h.owner.consumed).toHaveLength(1);
});
it("contains accidental asynchronous enqueue and retirement callbacks",async()=>{
  const actions:string[]=[];
  const h=await host([text("must not run")],true,((facts:any)=>{
    actions.push(facts.action);
    if(facts.action==="enqueue"||facts.action==="retire")return Promise.reject(Error("No asynchronous authority"));
    return true;
  }) as any);
  await expect(h.prompt("async-enqueue-refused")).rejects.toThrow("authority is not current");
  await Promise.resolve();
  expect(actions.filter(x=>x==="admit")).toHaveLength(2);
  expect(actions.slice(-2)).toEqual(["enqueue","retire"]);expect(h.adapter.requests).toHaveLength(0);
});
it("preserves original internal tool contexts without granting public inject",async()=>{
  const toolResponse:StreamChunk[]=[
    {type:"block-start",index:0,blockType:"tool-call"},
    {type:"block-end",index:0,block:{type:"tool-call",id:ToolCallId("native-c1"),name:"native_context",arguments:'{"id":"one"}'}},
    {type:"block-start",index:1,blockType:"tool-call"},
    {type:"block-end",index:1,block:{type:"tool-call",id:ToolCallId("native-c2"),name:"native_context",arguments:'{"id":"two"}'}},
    {type:"finish",reason:{kind:"tool-calls"}},
  ];
  const h=await inputHost([toolResponse,text("original contexts joined")]);
  h.ctx.tools.register(defineContentToolFixture({name:"native_context",description:"Inert context fixture",
    parameters:{id:{type:"string",required:true}},isConcurrencySafe:()=>true,
    execute:async(args)=>[{type:"text",text:"result-"+args.id}]}));
  h.ctx.on("tools/post-execute",async(exec,_result)=>{
    const message=createUserMessage({content:[{type:"text",text:"context-"+exec.callId}],source:{kind:"user"}});
    expect(()=>h.agent.inject(message)).toThrow("No original ACP enqueue candidate");
    return{kind:"accept",additionalContexts:[message]};
  });
  const result=await h.prompt("internal-contexts-same-operation");
  expect(result.stopReason).toBe("end_turn");expect(h.adapter.requests).toHaveLength(2);
  expect(h.owner.consumed).toHaveLength(1);
  const events=h.agent.session.snapshotEvents();
  const contexts=events.filter(e=>e.type==="user/message"&&(e.data.content[0] as any)?.text?.startsWith("context-"));
  expect(contexts.map(e=>(e.data as any).content[0].text)).toEqual(["context-native-c1","context-native-c2"]);
  expect(events.findLastIndex(e=>e.type==="tool/result")).toBeLessThan(events.indexOf(contexts[0]));
});
