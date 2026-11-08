/** Signal propagation through the original command, resume, inbox and history owners. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import {mountAgentLoopTestDependencies,mountAgentLoopTestHarness} from "@deepseek-ai/dsh-agent-loop-testkit";
import {LlmAdapter,createMessage,createUserMessage} from "@deepseek-ai/dsh-llm";
import {Session,SessionId} from "@deepseek-ai/dsh-session";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import {Peer} from "@deepseek-ai/dsh-client-connection";
import {createSessionTestController} from "mmx-native-test-remote";
import {ApiSessionAgentController} from "@deepseek-ai/dsh-api-session-controller/src/agent.ts";
import {mkdtemp,rm} from "node:fs/promises";
import {join} from "node:path";
import {tmpdir} from "node:os";

const cleanup:(()=>Promise<void>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const outcome=<T,>(promise:Promise<T>)=>promise.then(value=>({value}),error=>({error}));
async function enteredOrFailed(entered:Promise<void>,pending:Promise<unknown>){
  await Promise.race([entered,pending.then(()=>{throw Error("Native operation did not reach the delayed boundary");})]);
}
async function harness(){
  const root=await mkdtemp(join(tmpdir(),"mmx-native-command-generation-"));
  cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  await ctx.plugin(TypertRegistry);await mountAgentLoopTestDependencies(ctx);
  await ctx.plugin(JsonlPersistence,{root});
  let calls=0;
  class FixtureAdapter extends LlmAdapter{
    providerInfo(provider:string){return{id:provider,name:"Fixture"};}
    async listModels(provider:string){return[{provider,id:"fixture",name:"Fixture",inputModalities:["text"]}];}
    async resolveModel(provider:string,model:string){return{provider,id:model,name:"Fixture",inputModalities:["text"]};}
    async *stream(options:any){
      options.signal?.throwIfAborted();calls++;
      yield{type:"block-start",index:0,blockType:"text"};
      yield{type:"text-delta",index:0,text:"Native fixture response"};
      yield{type:"block-end",index:0,block:{type:"text",text:"Native fixture response"}};
      yield{type:"usage",usage:{inputTokens:1,outputTokens:1}};
      yield{type:"finish",reason:{kind:"stop"}};
    }
  }
  ctx.llm.registerAdapter(["fixture"],new FixtureAdapter());
  const loop=await mountAgentLoopTestHarness(ctx);
  const controller=createSessionTestController(ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:root});
  await ctx.plugin(TypertGatewayService);
  const peer=new Peer(ctx,{principal:{kind:"owner"},interactions:"none"});
  const live=await loop.create(SessionId("native-command-live"),{provider:"fixture",model:"fixture"},{cwd:root});
  const cold=SessionId("native-command-cold");
  const seed=Session.create(cold);
  seed.append("turn/start",{turn:1});seed.append("step/start",{turn:1,step:1});
  seed.append("user/message",createUserMessage({content:[{type:"text",text:"Original question"}],source:{kind:"user"}}),{surfaceOp:"append"});
  seed.append("assistant/message",{turn:1,step:1,message:createMessage({role:"assistant",content:[{type:"text",text:"Original answer"}],
    source:{kind:"model",provider:"fixture",model:"fixture"}}),stream:[]},{surfaceOp:"append"});
  seed.append("step/end",{turn:1,step:1});seed.append("turn/end",{turn:1,reason:{kind:"completed"}});
  const handle=await ctx.sessionPersistence.create({...seed.header,cwd:root});
  try{await handle.append(seed.snapshotEvents());await handle.flush();}finally{await handle.close();}
  const agents=(controller as unknown as {agents:ApiSessionAgentController}).agents;
  const request={sessionId:live.id,requestId:"native-original-prompt",mode:"queue",content:[{type:"text",text:"One original native message"}]} as any;
  return{ctx,root,live,cold,agents,controller,peer,request,calls:()=>calls};
}

it("refuses a prompt revoked during attachment admission before the original inbox write",async()=>{
  const h=await harness(),abort=new AbortController();
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.attachments.admitPromptContent.bind(h.ctx.attachments);
  vi.spyOn(h.ctx.attachments,"admitPromptContent").mockImplementation(async content=>{
    entered.resolve();await release.promise;return original(content);
  });
  const before=h.live.session.snapshotEvents();
  const pending=outcome(h.controller.prompt(h.request,abort.signal));
  await enteredOrFailed(entered.promise,pending);abort.abort(Error("original generation retired"));release.resolve();
  expect(await pending).toHaveProperty("error");
  expect(h.live.session.snapshotEvents()).toEqual(before);
  expect(h.calls()).toBe(0);
});

it("preserves native requestId deduplication and the original prompt source",async()=>{
  const h=await harness(),signal=new AbortController().signal;
  const followup=vi.spyOn(h.live,"followup");
  await expect(h.controller.prompt(h.request,signal)).resolves.toEqual({accepted:true});
  await expect(h.controller.prompt(h.request,signal)).resolves.toEqual({accepted:true});
  expect(followup).toHaveBeenCalledTimes(1);
  const sent=followup.mock.calls[0]![0];
  expect(sent.source).toMatchObject({kind:"user",rpcId:h.request.requestId});
  expect(sent.content).toEqual(h.request.content);
});

it("refuses a cancelled Gateway Stop before the original synchronous Agent cancel",async()=>{
  const h=await harness(),abort=new AbortController(),cancel=vi.spyOn(h.live,"cancel");
  const pending=outcome(h.ctx.typertGateway.invoke({namespace:"session",method:"cancel",args:{request:{sessionId:h.live.id}},peer:h.peer,signal:abort.signal}));
  abort.abort(Error("original generation retired"));
  expect(await pending).toHaveProperty("error");
  expect(cancel).not.toHaveBeenCalled();
});

it("preserves native Stop acknowledgement and keepInbox semantics",async()=>{
  const h=await harness(),cancel=vi.spyOn(h.live,"cancel");
  await expect(h.ctx.typertGateway.invoke({namespace:"session",method:"cancel",args:{request:{sessionId:h.live.id}},
    peer:h.peer,signal:new AbortController().signal})).resolves.toEqual({accepted:true});
  expect(cancel).toHaveBeenCalledExactlyOnceWith({kind:"user"},{keepInbox:true});
});

it("does not begin a cold writer after revocation during original preset composition",async()=>{
  const h=await harness(),abort=new AbortController(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.agents.composeAgent.bind(h.agents);
  vi.spyOn(h.agents,"composeAgent").mockImplementation(async(...args)=>{
    const result=await original(...args);entered.resolve();await release.promise;return result;
  });
  const resume=vi.spyOn(h.ctx.agents,"resume");
  const pending=outcome(h.agents.resolveAgent(h.cold,abort.signal));
  await enteredOrFailed(entered.promise,pending);abort.abort(Error("original generation retired"));release.resolve();
  expect(await pending).toHaveProperty("error");
  expect(resume).not.toHaveBeenCalled();expect(h.ctx.agents.get(h.cold)).toBeUndefined();expect(h.calls()).toBe(0);
});

it("passes creation cancellation into the original native factory and leaves no new writer published",async()=>{
  const h=await harness(),abort=new AbortController(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.agents.composeAgent.bind(h.agents);
  vi.spyOn(h.agents,"composeAgent").mockImplementation(async(...args)=>{
    const composition=await original(...args);
    return{...composition,setup:async(...setupArgs:any[])=>{
      const prepared=await composition.setup?.(...setupArgs);
      entered.resolve();await release.promise;return prepared;
    }};
  });
  const resume=vi.spyOn(h.ctx.agents,"resume");
  const pending=outcome(h.agents.resolveAgent(h.cold,abort.signal));
  await enteredOrFailed(entered.promise,pending);abort.abort(Error("original generation retired"));release.resolve();
  expect(await pending).toHaveProperty("error");
  expect(resume).toHaveBeenCalledTimes(1);expect(resume.mock.calls[0]![0].signal).toBe(abort.signal);
  expect(h.ctx.agents.get(h.cold)).toBeUndefined();expect(h.ctx.sessions.get(h.cold)).toBeUndefined();expect(h.calls()).toBe(0);
  const writer=await h.ctx.sessionPersistence.open(h.cold,"write");await writer.close();
});

it("a cancelled joining waiter cannot cancel or adopt the original initiator's shared resume",async()=>{
  const h=await harness(),firstSignal=new AbortController(),waiterSignal=new AbortController();
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.agents.composeAgent.bind(h.agents);
  vi.spyOn(h.agents,"composeAgent").mockImplementation(async(...args)=>{
    const composition=await original(...args);entered.resolve();await release.promise;return composition;
  });
  const resume=vi.spyOn(h.ctx.agents,"resume");
  const first=outcome(h.agents.resolveAgent(h.cold,firstSignal.signal));await enteredOrFailed(entered.promise,first);
  const joining=outcome(h.agents.resolveAgent(h.cold,waiterSignal.signal));
  waiterSignal.abort(Error("joining generation retired"));release.resolve();
  const completed=await first;expect(completed).toHaveProperty("value.agent");
  expect(await joining).toHaveProperty("error");
  expect(resume).toHaveBeenCalledTimes(1);expect(firstSignal.signal.aborted).toBe(false);
  expect(h.ctx.agents.get(h.cold)).toBe((completed as any).value.agent);
});

it("a retired follow opening never promotes its cold observation after the next pull",async()=>{
  const h=await harness(),abort=new AbortController(),promote=vi.spyOn(h.agents,"resolveObservedAgent");
  const iterator=h.controller.follow({address:{kind:"session",sessionId:h.cold}},abort.signal)[Symbol.asyncIterator]();
  const opening=await iterator.next();expect(opening).toMatchObject({done:false,value:{type:"snapshot"}});
  expect(promote).not.toHaveBeenCalled();
  abort.abort(Error("original generation retired"));
  const ended=await outcome(iterator.next());expect(ended).toHaveProperty("error");
  await iterator.return?.();
  expect(promote).not.toHaveBeenCalled();expect(h.ctx.agents.get(h.cold)).toBeUndefined();expect(h.calls()).toBe(0);
});
