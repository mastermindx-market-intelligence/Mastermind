/** Original donor services and JSONL/zstd persistence; no provider or installed authority. */
import {afterEach, expect, it, vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import SessionStore, {Session, SessionId} from "@deepseek-ai/dsh-session";
import AgentRegistry from "@deepseek-ai/dsh-agent";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import * as Connection from "@deepseek-ai/dsh-client-connection";
import {createUserMessage, createMessage} from "@deepseek-ai/dsh-llm";
import {mkdtemp, readdir, readFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";
import type {PeerScope} from "@deepseek-ai/dsh-typert-protocol";
import {createSessionTestController} from "mmx-native-test-remote";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {createCompanySessionReadBridge, type CompanySessionReadBinding} from "./src/company-peer";

const cleanup:(()=>Promise<void>)[]=[];
afterEach(async()=>{
  while(cleanup.length)await cleanup.pop()!();
  vi.restoreAllMocks();
});
async function disk(root:string):Promise<Record<string,string>>{
  const files:Record<string,string>={};
  async function walk(path:string){
    for(const entry of await readdir(path,{withFileTypes:true})){
      const child=join(path,entry.name);
      if(entry.isDirectory())await walk(child);
      else if(entry.isFile())files[child.slice(root.length+1)]=createHash("sha256").update(await readFile(child)).digest("hex");
    }
  }
  await walk(root);return files;
}
async function harness(){
  const root=await mkdtemp(join(tmpdir(),"mmx-company-native-read-"));
  cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  await ctx.plugin(SessionStore);await ctx.plugin(AgentRegistry);await ctx.plugin(TypertRegistry);
  await ctx.plugin(JsonlPersistence,{root});
  const id=SessionId("company-bound-original"),foreign=SessionId("other-company-original");
  for(const sessionId of [id,foreign]){
    const seed=Session.create(sessionId);
    seed.append("turn/start",{turn:1});
    seed.append("step/start",{turn:1,step:1});
    seed.append("user/message",createUserMessage({
      content:[{type:"text",text:sessionId===id?"Original question — 原始问题":"Private foreign question"}],
      source:{kind:"user"},
    }),{surfaceOp:"append"});
    seed.append("assistant/message",{
      turn:1,step:1,message:createMessage({role:"assistant",
        content:[{type:"text",text:"Native answer retained — 原样保留"}],
        source:{kind:"model",provider:"fixture",model:"fixture"}}),
      stream:[{type:"text-chunks",time0:1,index:0,dt:[1,1],texts:["Native answer"," retained"," — 原样保留"]}],
    },{surfaceOp:"append"});
    seed.append("step/end",{turn:1,step:1});
    seed.append("turn/end",{turn:1,reason:{kind:"completed"}});
    const handle=await ctx.sessionPersistence.create({...seed.header,cwd:"/fixture/company-workspace"});
    try{await handle.append(seed.snapshotEvents());await handle.flush();}finally{await handle.close();}
  }
  createSessionTestController(ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:"/fixture"});
  provideBrowserCredentials(ctx);await ctx.plugin(Connection);await ctx.plugin(TypertGatewayService);
  const peers:PeerScope[]=[];
  const originalCreate=ctx.connection.createPeer.bind(ctx.connection);
  vi.spyOn(ctx.connection,"createPeer").mockImplementation(options=>{
    const peer=originalCreate(options);peers.push(peer);return peer;
  });
  const bridge=createCompanySessionReadBridge(ctx);
  let current=true;
  const generation=new AbortController();
  const binding:CompanySessionReadBinding={principalScope:"fixture-company-principal",
    authorizationGeneration:"fixture-auth-1",workRef:"WS:company-native-read",sessionId:id,
    signal:generation.signal,requireCurrent:()=>{if(!current)throw Error("fixture authority retired");}};
  const reader=bridge.open(binding);
  return {ctx,root,id,foreign,peers,bridge,binding,reader,generation,setCurrent:(next:boolean)=>{current=next;}};
}

it("recovers unchanged cold native history without acquiring a writer or creating an Agent",async()=>{
  const h=await harness();
  const held=await h.ctx.sessionPersistence.open(h.id,"write");
  cleanup.push(()=>held.close());
  const before=await disk(h.root);
  const create=vi.spyOn(h.ctx.agents,"create"),resume=vi.spyOn(h.ctx.agents,"resume");
  const open=vi.spyOn(h.ctx.sessionPersistence,"open");
  const first=await h.reader.snapshotPage(),second=await h.reader.snapshotPage();
  expect(first).toEqual(second);
  expect(first.projections).toMatchObject({kind:"sequenced"});
  expect(JSON.stringify(first.page)).toContain("Native answer retained");
  expect(JSON.stringify(first.page)).toContain("原始问题");
  expect(first.page?.records.map(row=>row.event.seq)).toEqual([0,1,2,3,4,5]);
  expect(open.mock.calls.every(call=>call[0]===h.id&&call[1]==="read")).toBe(true);
  expect(create).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();
  expect(h.ctx.sessions.get(h.id)).toBeUndefined();expect(h.ctx.agents.get(h.id)).toBeUndefined();
  expect(await disk(h.root)).toEqual(before);
});

it("denies foreign resources and every native write before the original storage or command owner runs",async()=>{
  const h=await harness(),peer=h.peers[0]!;
  const open=vi.spyOn(h.ctx.sessionPersistence,"open");
  await expect(h.ctx.typertGateway.invoke({namespace:"session",method:"projections",
    args:{request:{sessionId:h.foreign}},peer})).rejects.toMatchObject({code:"remote-access/denied"});
  expect(open).not.toHaveBeenCalled();
  for(const [method,request] of [
    ["cancel",{sessionId:h.id}],
    ["prompt",{sessionId:h.id,requestId:"withheld-prompt",mode:"queue",content:[{type:"text",text:"must not run"}]}],
  ] as const){
    await expect(h.ctx.typertGateway.invoke({namespace:"session",method,args:{request},peer}))
      .rejects.toMatchObject({code:"remote-access/denied"});
  }
  await expect(h.ctx.typertGateway.wireStream.open("session/follow",
    {args:{request:{address:{kind:"session",sessionId:h.id}}}},
    {[Symbol.asyncIterator]:async function*(){}},peer,new AbortController().signal))
    .rejects.toMatchObject({code:"remote-access/denied"});
  expect(open).not.toHaveBeenCalled();expect(h.ctx.agents.get(h.id)).toBeUndefined();
  expect(Object.keys(h.reader).sort()).toEqual(["dispose","page","projections","snapshotPage"]);
  expect(()=>h.reader.page({throughSeq:1,address:{kind:"session",sessionId:h.foreign}} as never))
    .toThrow("Fixed native history page fields");
});

it("withholds an actual native result when current authority changes during its await",async()=>{
  const h=await harness(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.typertGateway.invoke.bind(h.ctx.typertGateway);
  vi.spyOn(h.ctx.typertGateway,"invoke").mockImplementation(async request=>{
    const value=await original(request);
    entered.resolve();await release.promise;return value;
  });
  const pending=h.reader.projections().then(value=>({value}),error=>({error}));
  await Promise.race([entered.promise,pending.then(()=>{throw Error("Native read did not reach the delayed boundary");})]);
  h.setCurrent(false);release.resolve();
  const outcome=await pending;
  expect(outcome).toHaveProperty("error");
  expect("error" in outcome && outcome.error.message).toContain("no longer current");
  expect(h.peers[0]?.signal.aborted).toBe(true);
  // Once this exact reader observes retirement, returning to principal A cannot revive it.
  h.setCurrent(true);await expect(h.reader.projections()).rejects.toThrow("no longer current");
});

it("ends only the retired generation; another current reader uses the same original session",async()=>{
  const h=await harness();
  const nextGeneration=new AbortController();
  const next=h.bridge.open({...h.binding,authorizationGeneration:"fixture-auth-2",signal:nextGeneration.signal});
  h.generation.abort();
  await expect(h.reader.projections()).rejects.toThrow("no longer current");
  expect(h.peers[0]?.signal.aborted).toBe(true);expect(h.peers[1]?.signal.aborted).toBe(false);
  const recovered=await next.snapshotPage();
  expect(recovered.projections).toMatchObject({kind:"sequenced"});
  expect(h.ctx.agents.get(h.id)).toBeUndefined();
  await next.dispose();await next.dispose();
  await expect(next.projections()).rejects.toThrow("no longer current");
});

it("joins caller cancellation without retiring a still-current authorization generation",async()=>{
  const h=await harness(),cancelled=new AbortController();
  cancelled.abort();
  await expect(h.reader.projections(cancelled.signal)).rejects.toThrow();
  expect(h.peers[0]?.signal.aborted).toBe(false);
  expect(await h.reader.projections()).toMatchObject({kind:"sequenced"});
});

it("refuses promise-valued guards and mutation of captured session/generation identity",async()=>{
  const h=await harness();
  expect(()=>h.bridge.open({...h.binding,workRef:{toString:()=>"WS:coerced"} as never}))
    .toThrow("Trusted current company session read binding required");
  expect(()=>h.bridge.open({...h.binding,requireCurrent:(async()=>{}) as never}))
    .toThrow("no longer current");
  const mutable={...h.binding};
  const reader=h.bridge.open(mutable);
  mutable.sessionId=h.foreign;
  await expect(reader.projections()).rejects.toThrow("no longer current");
  mutable.sessionId=h.id;
  await expect(reader.projections()).rejects.toThrow("no longer current");
});
