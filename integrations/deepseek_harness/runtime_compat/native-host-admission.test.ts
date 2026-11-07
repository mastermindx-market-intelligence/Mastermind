import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import AgentLoop from "@deepseek-ai/dsh-agent-loop";
import {mountAgentLoopTestDependencies} from "@deepseek-ai/dsh-agent-loop-testkit";
import {LlmAdapter,createUserMessage,type GenerateOptions,type StreamChunk} from "@deepseek-ai/dsh-llm";
import type {Agent,AgentInputAttempt,AgentInputCapability,InboxTarget} from "@deepseek-ai/dsh-agent";
import {Session,SessionId} from "@deepseek-ai/dsh-session";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import {createSessionTestController} from "mmx-native-test-remote";
import * as AcpPlugin from "mmx-original-acp";
import {client as createAcpClient,methods,ndJsonStream,PROTOCOL_VERSION} from "@agentclientprotocol/sdk";
import {mkdtemp,rm,readFile,readdir} from "node:fs/promises";
import {join} from "node:path";
import {tmpdir} from "node:os";

const cleanup:(()=>Promise<void>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const outcome=<T,>(promise:Promise<T>)=>promise.then(value=>({value}),error=>({error}));
async function reached(entered:Promise<void>,pending:Promise<unknown>){
  await Promise.race([entered,pending.then(()=>{throw Error("Native operation missed the delayed boundary");})]);
}
async function harness({ordinary=false,configured=[],invalidAdmission,isolate=false,input}:{ordinary?:boolean,configured?:any[],invalidAdmission?:(...args:any[])=>unknown,isolate?:boolean,input?:AgentInputCapability}={}){
  const root=await mkdtemp(join(tmpdir(),"mmx-native-host-admission-"));
  cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  const generation=new AbortController();
  let owner:Context["fiber"]|undefined,operation:"create"|"resume"="create",selected:SessionId|undefined,current=true;
  const checks: {fiber:Context["fiber"],operation:string,id:SessionId}[]=[];
  const requirement={admit(caller:Context,action:"create"|"resume",id:SessionId){
    checks.push({fiber:caller.fiber,operation:action,id});
    if(!current||caller.fiber!==owner||action!==operation||(selected!==undefined&&id!==selected))
      throw Error("Original operation does not admit this native caller");
    selected=id;
    return{signal:generation.signal,...input===undefined?{}:{input},assertCurrent(){
      if(!current||caller.fiber!==owner||id!==selected)throw Error("Original operation retired");
      return true as const;
    }};
  }};
  if(!ordinary)ctx.provide("agentLifecycleAdmission",invalidAdmission?{admit:invalidAdmission} as any:requirement);
  await ctx.plugin(TypertRegistry);
  await mountAgentLoopTestDependencies(ctx);
  await ctx.plugin(JsonlPersistence,{root,compression:"none"});
  let modelCalls=0;
  class FixtureAdapter extends LlmAdapter{
    providerInfo(provider:string){return{id:provider,name:"Fixture"};}
    async listModels(provider:string){return[{provider,id:"fixture",name:"Fixture",inputModalities:["text"] as const}];}
    async resolveModel(provider:string,model:string){return{provider,id:model,name:"Fixture",inputModalities:["text"] as const};}
    async *stream(options:GenerateOptions):AsyncIterable<StreamChunk>{
      options.signal?.throwIfAborted();modelCalls++;
      yield{type:"block-start",index:0,blockType:"text"};
      yield{type:"text-delta",index:0,text:"Same native session"};
      yield{type:"block-end",index:0,block:{type:"text",text:"Same native session"}};
      yield{type:"finish",reason:{kind:"stop"}};
    }
  }
  ctx.llm.registerAdapter(["fixture"],new FixtureAdapter());
  const prepare=vi.spyOn(ctx.sessions,"prepare"),create=vi.spyOn(ctx.sessionPersistence,"create"),open=vi.spyOn(ctx.sessionPersistence,"open");
  const failures:unknown[]=[];ctx.on("agent-loop/config-start-failed",({error})=>{failures.push(error);});
  const loopOwner=isolate?ctx.isolate("agentLifecycleAdmission"):ctx;
  const loopFiber=await loopOwner.plugin(AgentLoop,{agents:configured});
  let caller!:Context;
  await ctx.plugin({name:"original-operation-owner",inject:["agents","agentLoop"],apply(inner:Context){caller=inner;}});
  const controller=createSessionTestController(ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:root});
  return{ctx,root,caller,controller,loopFiber,requirement,generation,prepare,create,open,failures,checks,
    allow(fiber=caller.fiber,action:"create"|"resume"="create",id?:SessionId){owner=fiber;operation=action;selected=id;},
    retire(){current=false;},
    selected:()=>selected,modelCalls:()=>modelCalls};
}
async function seed(h:Awaited<ReturnType<typeof harness>>,id:SessionId){
  const session=Session.create(id);
  session.append("turn/start",{turn:1});
  session.append("step/start",{turn:1,step:1});
  const writer=await h.ctx.sessionPersistence.create({...session.header,cwd:h.root});
  try{await writer.append(session.snapshotEvents());await writer.flush();}finally{await writer.close();}
  return session.snapshotEvents();
}
async function readNativeFiles(root:string){
  const entries:Record<string,string>={};
  async function visit(dir:string){for(const name of await readdir(dir,{withFileTypes:true})){
    const file=join(dir,name.name);if(name.isDirectory())await visit(file);else if(name.isFile())entries[file.slice(root.length)]=(await readFile(file)).toString("base64");
  }}
  await visit(root);return entries;
}

it("refuses an unadmitted caller before original Session preparation or persistence",async()=>{
  const h=await harness(),id=SessionId("unadmitted-native-session");
  const result=await outcome(h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}));
  expect({refused:"error" in result,nativePreparations:h.prepare.mock.calls.length,nativeWriters:h.create.mock.calls.length})
    .toEqual({refused:true,nativePreparations:0,nativeWriters:0});
  expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.modelCalls()).toBe(0);
});
it("closes declarative startup at the same original factory boundary",async()=>{
  const h=await harness({configured:[{id:"unauthorized-startup",provider:"fixture",model:"fixture"}]});
  await vi.waitFor(()=>expect(h.failures.length).toBe(1));
  expect(h.prepare).not.toHaveBeenCalled();expect(h.create).not.toHaveBeenCalled();
  expect(h.modelCalls()).toBe(0);
});
it("keeps ordinary attended creation unchanged when no launch requirement exists",async()=>{
  const h=await harness({ordinary:true}),id=SessionId("ordinary-native-session");
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}});
  expect(h.ctx.agents.get(id)).toBe(handle.agent);
  expect(h.ctx.sessions.get(id)).toBe(handle.agent.session);
  await handle.dispose();
});
it("admits the actual caller fiber through Cordis shadows and rejects a web caller",async()=>{
  const h=await harness(),id=SessionId("exact-original-caller");h.allow(h.caller.fiber,"create",id);
  await expect(h.ctx.agents.create({sessionId:id,meta:{cwd:h.root}})).rejects.toThrow("does not admit");
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}});
  expect(h.checks.at(-1)?.fiber).toBe(h.caller.fiber);
  expect(h.ctx.agents.get(id)).toBe(handle.agent);
  expect(h.create).toHaveBeenCalledTimes(1);await handle.dispose();
});
it("keeps the captured host requirement after its mutable slot is replaced",async()=>{
  const h=await harness(),id=SessionId("captured-launch-requirement");
  h.requirement.admit=(()=>({signal:new AbortController().signal,assertCurrent:()=>true})) as any;
  await expect(h.caller.agents.create({sessionId:id})).rejects.toThrow("does not admit");
  expect(h.create).not.toHaveBeenCalled();
});
it("refuses cold recovery before acquiring the original native writer",async()=>{
  const h=await harness(),id=SessionId("unadmitted-cold-session");await seed(h,id);
  h.create.mockClear();h.open.mockClear();const before=await readNativeFiles(h.root);
  await expect(h.caller.agents.resume({resumeSessionId:id})).rejects.toThrow("does not admit");
  expect(h.open).not.toHaveBeenCalled();expect(await readNativeFiles(h.root)).toEqual(before);
});
it("rechecks original authority after native read and before semantic crash repair",async()=>{
  const h=await harness(),id=SessionId("retired-during-cold-read");await seed(h,id);
  const before=await readNativeFiles(h.root);h.allow(h.caller.fiber,"resume",id);
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  h.open.mockRestore();
  const open=h.ctx.sessionPersistence.open.bind(h.ctx.sessionPersistence);
  vi.spyOn(h.ctx.sessionPersistence,"open").mockImplementation(async(...args)=>{
    const handle=await open(...args),read=handle.read.bind(handle);
    vi.spyOn(handle,"read").mockImplementation(async(...readArgs)=>{const result=await read(...readArgs);entered.resolve();await release.promise;return result;});
    return handle;
  });
  const pending=outcome(h.caller.agents.resume({resumeSessionId:id}));
  await reached(entered.promise,pending);h.retire();release.resolve();
  expect(await pending).toHaveProperty("error");expect(await readNativeFiles(h.root)).toEqual(before);
  expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.ctx.sessions.get(id)).toBeUndefined();
  const writer=await open(id,"write");await writer.close();expect(h.modelCalls()).toBe(0);
});
it("rolls back a generation retired during unpublished setup through the same native owner",async()=>{
  const h=await harness(),id=SessionId("retired-during-native-setup");h.allow(h.caller.fiber,"create",id);
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>(),commit=vi.fn();
  const pending=outcome(h.caller.agents.create({sessionId:id,meta:{cwd:h.root},setup:async()=>{
    entered.resolve();await release.promise;return{commit};
  }}));
  await reached(entered.promise,pending);h.generation.abort(Error("Original generation retired"));release.resolve();
  expect(await pending).toHaveProperty("error");expect(commit).not.toHaveBeenCalled();
  expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.ctx.sessions.get(id)).toBeUndefined();
  expect(await h.ctx.sessionPersistence.stat(id)).toBeUndefined();expect(h.modelCalls()).toBe(0);
});
it("uses one original Agent and Session for stock ACP and native web observation",async()=>{
  const h=await harness(),toClient=new TransformStream<Uint8Array,Uint8Array>(),toAgent=new TransformStream<Uint8Array,Uint8Array>();
  const updates:any[]=[];
  const clientApp=createAcpClient({name:"native-host-qualification"})
    .onNotification(methods.client.session.update,({params})=>{updates.push(params);})
    .onRequest(methods.client.session.requestPermission,()=>({outcome:{outcome:"cancelled" as const}}));
  const fiber=await h.ctx.plugin({name:"original-acp-composition",inject:[...AcpPlugin.inject],apply(ctx:Context){
    h.allow(ctx.fiber);
    AcpPlugin.apply(ctx,{provider:"fixture",model:"fixture",stream:ndJsonStream(toClient.writable,toAgent.readable)});
  }});
  const connection=clientApp.connect(ndJsonStream(toAgent.writable,toClient.readable)),client=connection.agent;
  await client.request(methods.agent.initialize,{protocolVersion:PROTOCOL_VERSION,clientCapabilities:{}});
  const {sessionId}=await client.request(methods.agent.session.new,{cwd:h.root,mcpServers:[]});
  const id=SessionId(sessionId),agent=h.ctx.agents.get(id)!;
  expect(h.selected()).toBe(id);expect(h.checks.at(-1)?.fiber).toBe(fiber);
  expect(agent.session).toBe(h.ctx.sessions.get(id));expect(h.create).toHaveBeenCalledTimes(1);expect(h.modelCalls()).toBe(0);
  const nativeAgents=(h.controller as any).agents;
  const resolved=await nativeAgents.resolveAgent(id);
  expect(resolved.agent).toBe(agent);
  expect(h.open).not.toHaveBeenCalled();
  await expect(client.request(methods.agent.session.new,{cwd:h.root,mcpServers:[]})).rejects.toThrow();
  expect(h.create).toHaveBeenCalledTimes(1);
  await client.request(methods.agent.session.close,{sessionId});
  expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.ctx.sessions.get(id)).toBeUndefined();
  const writer=await h.ctx.sessionPersistence.open(id,"write");await writer.close();
  expect(updates).toEqual([]);expect(h.modelCalls()).toBe(0);
});

it.each([
  ["missing signal",()=>({assertCurrent:()=>true})],
  ["false current",()=>({signal:new AbortController().signal,assertCurrent:()=>false})],
  ["asynchronous permit",()=>Promise.resolve({signal:new AbortController().signal,assertCurrent:()=>true})],
  ["rejected asynchronous permit",()=>Promise.reject(Error("No asynchronous grant"))],
  ["asynchronous current",()=>({signal:new AbortController().signal,assertCurrent:()=>Promise.resolve(true)})],
  ["rejected asynchronous current",()=>({signal:new AbortController().signal,assertCurrent:()=>Promise.reject(Error("No async current"))})],
] as const)("refuses %s without a writer or unhandled authority task",async(_name,invalidAdmission)=>{
  const h=await harness({invalidAdmission}),id=SessionId("invalid-authority");
  const result=await outcome(h.caller.agents.create({sessionId:id}));
  expect("error" in result).toBe(true);expect(h.prepare).not.toHaveBeenCalled();expect(h.create).not.toHaveBeenCalled();
});
it("resumes the exact cold identity under the admitted original caller",async()=>{
  const h=await harness(),id=SessionId("admitted-cold-session");await seed(h,id);h.allow(h.caller.fiber,"resume",id);
  const handle=await h.caller.agents.resume({resumeSessionId:id});
  expect(handle.agent.session.id).toBe(id);expect(h.ctx.agents.get(id)).toBe(handle.agent);
  expect(h.ctx.sessions.get(id)).toBe(handle.agent.session);expect(h.modelCalls()).toBe(0);
  await handle.dispose();const writer=await h.ctx.sessionPersistence.open(id,"write");await writer.close();
});

it("does not lose the root launch requirement under a child isolation label",async()=>{
  const h=await harness({isolate:true}),id=SessionId("isolated-policy-is-not-a-grant");
  const result=await outcome(h.caller.agents.create({sessionId:id}));
  expect("error" in result).toBe(true);expect(h.prepare).not.toHaveBeenCalled();expect(h.create).not.toHaveBeenCalled();
});
it("rechecks retirement caused synchronously by the original authority callback",async()=>{
  const generation=new AbortController();
  const h=await harness({invalidAdmission:()=>({signal:generation.signal,assertCurrent(){generation.abort(Error("retired in check"));return true;}})});
  const result=await outcome(h.caller.agents.create({sessionId:SessionId("retired-inside-check")}));
  expect("error" in result).toBe(true);expect(h.prepare).not.toHaveBeenCalled();expect(h.create).not.toHaveBeenCalled();
});


/** Inert original-operation fixture: no serializable value can mint its input grant. */
function inputOwner(){
  let live=true,grant:{agent:Agent,message:ReturnType<typeof createUserMessage>,target:InboxTarget,wakeup:boolean}|undefined;
  let consumed=0,hook:((attempt:AgentInputAttempt)=>void)|undefined;
  const attempts:AgentInputAttempt[]=[];
  const capability:AgentInputCapability={
    assertCurrent(){if(!live)throw Error("Input generation retired");return true;},
    consume(attempt){
      attempts.push(attempt);
      const owned=grant;
      if(owned===undefined||attempt.agent!==owned.agent||attempt.session!==owned.agent.session
          ||attempt.sessionSeq!==owned.agent.session.seq||attempt.removedCount!==0
          ||attempt.inserted.length!==1||attempt.inserted[0]!==owned.message
          ||attempt.send?.message!==owned.message||attempt.send.requestedTarget!==owned.target
          ||attempt.send.wakeup!==owned.wakeup||attempt.target!==owned.target
          ||attempt.start!==(owned.target==="next-turn"?owned.agent.inbox.nextTurn:owned.agent.inbox.nextStep).length)
        throw Error("No exact original input grant");
      grant=undefined;consumed++;
      expect(Object.isFrozen(attempt)).toBe(true);expect(Object.isFrozen(attempt.inserted)).toBe(true);
      expect(Object.isFrozen(owned.message)).toBe(true);
      hook?.(attempt);
      return true;
    },
  };
  return{capability,attempts,consumed:()=>consumed,
    allow(agent:Agent,message:ReturnType<typeof createUserMessage>,target:InboxTarget="next-turn",wakeup=true){
      if(grant!==undefined)throw Error("Original input already reserved");grant={agent,message,target,wakeup};
    },
    retire(){live=false;},onConsume(callback:(attempt:AgentInputAttempt)=>void){hook=callback;},
  };
}
const inputMessage=()=>createUserMessage({content:[{type:"text",text:"Original admitted input"}],source:{kind:"user"}});

it.each(["send","followup","steer","inject","append","prepend","splice"] as const)(
  "refuses native %s without an original input grant at the durable Inbox",async(method)=>{
    const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-input-"+method);
    h.allow(h.caller.fiber,"create",id);
    const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent;
    const before=agent.session.snapshotEvents(),message=inputMessage();
    expect(()=>{
      switch(method){
        case"send":agent.send(message,"next-turn",true);break;
        case"followup":agent.followup(message);break;
        case"steer":agent.steer(message);break;
        case"inject":agent.inject(message);break;
        case"append":agent.inbox.append("next-turn",message);break;
        case"prepend":agent.inbox.prepend("next-turn",message);break;
        case"splice":agent.inbox.splice("next-turn",Infinity,0,[message]);break;
      }
    }).toThrow("No exact original input grant");
    expect(agent.session.snapshotEvents()).toEqual(before);expect(agent.inbox.hasPending).toBe(false);
    expect(h.modelCalls()).toBe(0);expect(owner.consumed()).toBe(0);await handle.dispose();
  },
);
it("allows only the exact private send path to consume an input once",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("one-native-input");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root},agentOptions:{provider:"fixture",model:"fixture"}});
  const agent=handle.agent,message=inputMessage();owner.allow(agent,message);
  expect(()=>agent.inbox.append("next-turn",message)).toThrow("No exact original input grant");
  expect(owner.attempts.at(-1)?.send).toBeUndefined();expect(owner.consumed()).toBe(0);
  agent.followup(message);
  await vi.waitFor(()=>{expect(h.modelCalls()).toBe(1);expect(agent.status).toBe("idle");});
  expect(owner.consumed()).toBe(1);
  expect(()=>agent.followup(message)).toThrow("No exact original input grant");
  expect(agent.session.snapshotEvents().filter(event=>event.type==="user/message")).toHaveLength(1);
  expect(h.modelCalls()).toBe(1);await handle.dispose();
});
it("does not let public replace or forged source labels reuse a consumed insertion",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-replace-fence");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent,message=inputMessage();
  owner.allow(agent,message,"next-step",false);agent.inject(message);
  const before=agent.session.snapshotEvents();
  expect(()=>agent.inbox.replace(message.id,inputMessage())).toThrow("No exact original input grant");
  expect(agent.session.snapshotEvents()).toEqual(before);expect(agent.inbox.nextStep[0].id).toBe(message.id);
  expect(owner.consumed()).toBe(1);expect(h.modelCalls()).toBe(0);
  agent.inbox.remove(message.id);expect(agent.inbox.hasPending).toBe(false);await handle.dispose();
});
it("prevents reentrant admission from borrowing the original private insertion",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-input-reentry");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent,message=inputMessage();
  owner.allow(agent,message,"next-step",false);
  owner.onConsume(()=>{
    expect(()=>agent.inject(message)).toThrow("native input admission is reentrant");
    expect(()=>agent.inbox.append("next-step",message)).toThrow("native input admission is reentrant");
  });
  agent.inject(message);
  expect(owner.consumed()).toBe(1);expect(agent.inbox.nextStep.map(x=>x.id)).toEqual([message.id]);
  expect(h.modelCalls()).toBe(0);await handle.dispose();
});
it.each(["lifetime","generation","session"] as const)("rechecks %s after consuming the exact input",async(drift)=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-input-drift-"+drift);
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent,message=inputMessage();
  owner.allow(agent,message,"next-step",false);
  owner.onConsume(()=>{
    if(drift==="lifetime")owner.retire();
    if(drift==="generation")h.generation.abort(Error("Generation retired inside input consume"));
    if(drift==="session")agent.session.append("agent/inbox/spliced",{target:"next-step",start:0,inserted:[]});
  });
  expect(()=>agent.inject(message)).toThrow();
  expect(owner.consumed()).toBe(1);expect(agent.inbox.hasPending).toBe(false);
  expect(agent.session.snapshotEvents().filter(event=>event.type==="agent/inbox/spliced"&&event.data.inserted.length>0)).toEqual([]);
  expect(h.modelCalls()).toBe(0);await handle.dispose();
});
it("retains captured input methods after the mutable permit is replaced",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("captured-native-input");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}});
  owner.capability.consume=()=>true;
  expect(()=>handle.agent.inject(inputMessage())).toThrow("No exact original input grant");
  expect(h.modelCalls()).toBe(0);await handle.dispose();
});
it.each(["next-turn","next-step"] as const)("refuses native cold pending %s before crash repair",async(target)=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-pending-"+target);
  const session=Session.create(id);
  session.append("agent/inbox/spliced",{target,start:0,inserted:[inputMessage()]});
  session.append("turn/start",{turn:1});session.append("step/start",{turn:1,step:1});
  const writer=await h.ctx.sessionPersistence.create({...session.header,cwd:h.root});
  try{await writer.append(session.snapshotEvents());await writer.flush();}finally{await writer.close();}
  const before=await readNativeFiles(h.root);h.allow(h.caller.fiber,"resume",id);
  await expect(h.caller.agents.resume({resumeSessionId:id})).rejects.toThrow("cannot adopt pending input");
  expect(await readNativeFiles(h.root)).toEqual(before);expect(h.ctx.agents.get(id)).toBeUndefined();
  expect(h.ctx.sessions.get(id)).toBeUndefined();expect(h.modelCalls()).toBe(0);
});
it("refuses seeded native input before taking a fresh writer",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-seed-pending");
  const session=Session.create(id);session.append("agent/inbox/spliced",{target:"next-step",start:0,inserted:[inputMessage()]});
  h.allow(h.caller.fiber,"create",id);
  await expect(h.caller.agents.create({sessionId:id,seed:session.snapshotEvents()})).rejects.toThrow("cannot adopt pending input");
  expect(h.create).not.toHaveBeenCalled();expect(h.modelCalls()).toBe(0);
});
it("refuses pending input added by unpublished setup before source publication",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-setup-pending");
  h.allow(h.caller.fiber,"create",id);
  await expect(h.caller.agents.create({sessionId:id,setup:(_ctx,agent)=>{
    agent.session.append("agent/inbox/spliced",{target:"next-step",start:0,inserted:[inputMessage()]});
  }})).rejects.toThrow("cannot adopt pending input");
  expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.ctx.sessions.get(id)).toBeUndefined();
  expect(await h.ctx.sessionPersistence.stat(id)).toBeUndefined();expect(h.modelCalls()).toBe(0);
});

it("rejects changing accessors before they can become native input facts",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-input-accessor");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent,message=structuredClone(inputMessage());
  const getter=vi.fn(()=>"mutable getter");
  Object.defineProperty(message.content[0],"text",{enumerable:true,get:getter});
  owner.allow(agent,message,"next-step",false);
  const before=agent.session.snapshotEvents();
  expect(()=>agent.inject(message)).toThrow("native input cannot contain accessors");
  expect(getter).not.toHaveBeenCalled();expect(owner.consumed()).toBe(0);
  expect(agent.session.snapshotEvents()).toEqual(before);expect(h.modelCalls()).toBe(0);await handle.dispose();
});
it("keeps removal and cancellation available from an original insertion observer",async()=>{
  const owner=inputOwner(),h=await harness({input:owner.capability}),id=SessionId("native-input-remove-reentry");
  h.allow(h.caller.fiber,"create",id);
  const handle=await h.caller.agents.create({sessionId:id,meta:{cwd:h.root}}),agent=handle.agent,message=inputMessage();
  owner.allow(agent,message,"next-step",false);
  h.ctx.on("agent/inbox/inserted",({agent:seen})=>{if(seen===agent)agent.cancel({kind:"user"});});
  agent.inject(message);
  expect(owner.consumed()).toBe(1);expect(agent.inbox.hasPending).toBe(false);expect(h.modelCalls()).toBe(0);
  await handle.dispose();
});

it("folds pending input after the last authority callback before publication",async()=>{
  let unpublished:Agent|undefined,checks=0;
  const input:AgentInputCapability={
    assertCurrent(){
      if(unpublished!==undefined&&++checks===2)
        unpublished.session.append("agent/inbox/spliced",{target:"next-step",start:0,inserted:[inputMessage()]});
      return true;
    },
    consume(){throw Error("No external input grant");},
  };
  const h=await harness({input}),id=SessionId("native-post-fold-callback");
  h.allow(h.caller.fiber,"create",id);
  await expect(h.caller.agents.create({sessionId:id,setup:(_ctx,agent)=>{unpublished=agent;}}))
    .rejects.toThrow("cannot adopt pending input");
  expect(checks).toBe(2);expect(h.ctx.agents.get(id)).toBeUndefined();expect(h.ctx.sessions.get(id)).toBeUndefined();
  expect(await h.ctx.sessionPersistence.stat(id)).toBeUndefined();expect(h.modelCalls()).toBe(0);
});
