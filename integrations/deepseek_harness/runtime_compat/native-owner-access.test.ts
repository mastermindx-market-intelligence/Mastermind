/** Real native owners and transports; deterministic model only, no provider traffic. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import RemoteAccessService,{type RemoteAccessAction,type RemoteAccessBinding,type OwnerAccessSource} from "@deepseek-ai/dsh-api-remote-access";
import TypertGatewayService,{type TypertRemoteEventDispatch} from "@deepseek-ai/dsh-api-gateway";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import {Remote,TypertRemoteService} from "@deepseek-ai/dsh-typert-protocol";
import {apply as applyConnection,inject as connectionInject} from "@deepseek-ai/dsh-client-connection";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {mountAgentLoopTestDependencies,mountAgentLoopTestHarness} from "@deepseek-ai/dsh-agent-loop-testkit";
import {LlmAdapter,createMessage,createUserMessage} from "@deepseek-ai/dsh-llm";
import {Session,SessionId} from "@deepseek-ai/dsh-session";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import {createSessionTestController} from "mmx-native-test-remote";
import {mkdtemp,rm} from "node:fs/promises";
import {join} from "node:path";
import {tmpdir} from "node:os";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const outcome=<T,>(p:Promise<T>)=>p.then(value=>({value}),error=>({error}));
const actions:readonly RemoteAccessAction[]=[
  "ownerFixture/read","ownerFixture/slow","ownerFixture/watch",
  "session/page","session/projections","session/prompt","session/cancel","session/list","session/follow",
  "event:fixture/notice","event:fixture/ask",
];
function bindings(ids:readonly string[]):RemoteAccessBinding[]{
  return ids.map(id=>({resource:{kind:"session",id},role:{name:"original-associated-session",resource:"session",actions}}));
}
class OwnerFixture extends TypertRemoteService{
  calls=0;entered=Promise.withResolvers<void>();release=Promise.withResolvers<void>();
  constructor(ctx:Context){super(ctx,"ownerFixture");}
  @Remote({resources:{session:request=>request.sessionId}})
  read(request:{readonly sessionId:string}):string{void request;this.calls++;return this.ctx.invocation!.peer.principal.kind;}
  @Remote({resources:{session:request=>request.sessionId}})
  async slow(request:{readonly sessionId:string}):Promise<string>{
    void request;this.calls++;this.entered.resolve();await this.release.promise;return "withheld late result";
  }
  @Remote({mode:"stream",resources:{session:request=>request.sessionId}})
  async *watch(request:{readonly sessionId:string},signal:AbortSignal):AsyncIterable<string>{
    void request;void signal;this.calls++;yield "opening";this.entered.resolve();await this.release.promise;yield "withheld late frame";
  }
}
async function host(ids:readonly string[]=["associated"],restricted=true){
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  if(restricted)ctx.provide("remoteAccessOwnerRestricted",true);
  await ctx.plugin(TypertRegistry);await ctx.plugin(RemoteAccessService);await ctx.plugin(TypertGatewayService);
  provideBrowserCredentials(ctx);await ctx.plugin({inject:[...connectionInject],apply:applyConnection});
  await ctx.plugin(OwnerFixture);
  const state={current:true,held:bindings(ids)},abort=new AbortController();
  const source:OwnerAccessSource={signal:abort.signal,requireCurrent:()=>{if(!state.current)throw Error("association retired");},
    policy:{bindings:()=>state.held}};
  const dispose=restricted?ctx.remoteAccess.registerOwnerRestriction(source):()=>{};
  const peer=ctx.connection.browserPeer,fixture=ctx.get("ownerFixture") as OwnerFixture;
  const call=(method:string,id="associated")=>ctx.typertGateway.invoke({
    namespace:"ownerFixture",method,args:{request:{sessionId:id}},peer,
  });
  return{ctx,peer,fixture,state,abort,source,dispose,call};
}
function eventSource(h:Awaited<ReturnType<typeof host>>){
  const queue:TypertRemoteEventDispatch[]=[];let wake:(()=>void)|undefined;
  h.ctx.effect(()=>h.ctx.typertGateway.registerRemoteEvents(async function*(signal){
    while(!signal.aborted){
      while(queue.length&&!signal.aborted)yield queue.shift()!;
      if(signal.aborted)break;
      await new Promise<void>(resolve=>{wake=resolve;signal.addEventListener("abort",resolve,{once:true});});
    }
  },{home:"/native-fixture"}));
  return(dispatch:TypertRemoteEventDispatch)=>{queue.push(dispatch);wake?.();};
}
async function events(h:Awaited<ReturnType<typeof host>>){
  const abort=new AbortController();cleanup.push(async()=>{abort.abort();});
  const iterator=(await h.ctx.typertGateway.wireStream.open("$events",{args:{}},(async function*(){})(),h.peer,abort.signal))[Symbol.asyncIterator]();
  const ready=await iterator.next();expect(ready).toMatchObject({done:false,value:{type:"ready"}});
  return{iterator,abort,clientId:(ready.value as any).clientId};
}
function ask(h:Awaited<ReturnType<typeof host>>,resources:unknown=[{kind:"session",id:"associated"}]){
  const subject={},resolve=vi.fn(),reject=vi.fn();
  return{event:"fixture/ask",request:{agent:subject,question:"native waterfall"},context:{
    value:h.ctx,subject,agentId:"associated",...(resources===undefined?{}:{resources}),
  },resolve,reject} as any;
}
async function result(h:Awaited<ReturnType<typeof host>>,clientId:string,eventId:string){
  const response=await h.ctx.connection.createSharedFetchHandler("/api").fetch(new Request("http://native/api/$events/result",{
    method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
      type:"client-request",rpcId:"original-event-result",method:"$events/result",
      payload:{args:{clientId,eventId,outcome:{kind:"result",value:"late answer"}}},
    }),
  }),h.peer);
  return response.json();
}

it("permits only the associated native resource before receiver lookup and retains the real owner",async()=>{
  const h=await host(),receiver=vi.spyOn(h.ctx.typertGateway as any,"resolveReceiverContext");
  await expect(h.call("read","foreign")).rejects.toMatchObject({code:"remote-access/denied"});
  expect(receiver).not.toHaveBeenCalled();expect(h.fixture.calls).toBe(0);
  await expect(h.call("read")).resolves.toBe("owner");expect(h.fixture.calls).toBe(1);
  expect(h.ctx.remoteAccess.snapshotFor({kind:"owner"})).toMatchObject({type:"baseline",owner:false,
    grants:[{resource:{kind:"session",id:"associated"}}]});
});
it("keeps startup restriction after source unload and forbids late adoption of an unrestricted host",async()=>{
  const h=await host(),scope=h.ctx.remoteAccess.captureOwnerRestriction()!;
  h.dispose();expect(scope.signal.aborted).toBe(true);
  await expect(h.call("read")).rejects.toMatchObject({code:"remote-access/denied"});
  expect(h.ctx.remoteAccess.snapshotFor({kind:"owner"})).toEqual({type:"baseline",owner:false,grants:[]});
  const ordinary=await host([],false);
  expect(()=>ordinary.ctx.remoteAccess.registerOwnerRestriction(h.source)).toThrow("required before native startup");
  await expect(ordinary.call("read","foreign")).resolves.toBe("owner");
});
it.each(["guard","bindings","policy"] as const)("never revives an old generation after %s changes and returns",async(field)=>{
  const h=await host(),scope=h.ctx.remoteAccess.captureOwnerRestriction()!;
  if(field==="guard"){
    h.state.current=false;expect(()=>scope.requireCurrent()).toThrow();h.state.current=true;
  }else if(field==="bindings"){
    const original=h.source.policy.bindings;(h.source.policy as any).bindings=()=>[];
    expect(()=>scope.requireCurrent()).toThrow();(h.source.policy as any).bindings=original;
  }else{
    const original=h.source.policy;(h.source as any).policy={bindings:()=>h.state.held};
    expect(()=>scope.requireCurrent()).toThrow();(h.source as any).policy=original;
  }
  expect(scope.signal.aborted).toBe(true);await expect(h.call("read")).rejects.toMatchObject({code:"remote-access/denied"});
});
it("refuses an async currentness guard without exposing grants or dispatch",async()=>{
  const h=await host();h.dispose();
  expect(()=>h.ctx.remoteAccess.registerOwnerRestriction({...h.source,requireCurrent:async()=>{}} as any)).toThrow("unavailable");
  await expect(h.call("read")).rejects.toMatchObject({code:"remote-access/denied"});expect(h.fixture.calls).toBe(0);
});
it.each([async()=>({kind:"allow"}),()=>({kind:"unexpected"}),()=>null])("refuses malformed policy decisions before dispatch",async condition=>{
  const h=await host();h.state.held=[{...h.state.held[0]!,condition} as any];
  await expect(h.call("read")).rejects.toMatchObject({code:"remote-access/denied"});
  expect(h.fixture.calls).toBe(0);
  expect(h.ctx.remoteAccess.snapshotFor({kind:"owner"})).toEqual({type:"baseline",owner:false,grants:[]});
});
it("withholds a unary result when the source retires during the original method",async()=>{
  const h=await host(),pending=outcome(h.call("slow"));
  await h.fixture.entered.promise;h.state.current=false;h.fixture.release.resolve();
  expect(await pending).toHaveProperty("error");expect(h.fixture.calls).toBe(1);
});
it("withholds a delayed stream frame and retires the original stream generation",async()=>{
  const h=await host(),source=await h.ctx.typertGateway.stream({
    namespace:"ownerFixture",method:"watch",args:{request:{sessionId:"associated"}},peer:h.peer,
  }),iterator=source[Symbol.asyncIterator]();
  expect(await iterator.next()).toEqual({done:false,value:"opening"});
  const pending=outcome(iterator.next());await h.fixture.entered.promise;
  h.state.current=false;h.fixture.release.resolve();expect(await pending).toHaveProperty("error");await iterator.return?.();
});
it("drops a queued broadcast and stops advertising a live client when its source retires",async()=>{
  const h=await host(),push=eventSource(h),e=await events(h);
  const decide=vi.spyOn(h.ctx.remoteAccess,"decide");
  push({event:"fixture/notice",args:["associated"],resources:{session:id=>id}});
  await vi.waitFor(()=>expect(decide).toHaveBeenCalled());
  h.state.current=false;expect(h.ctx.typertGateway.hasLiveClient()).toBe(false);
  expect(await e.iterator.next()).toMatchObject({done:true});
});
it("settles the original queued waterfall exactly once on source retirement",async()=>{
  const h=await host(),push=eventSource(h),e=await events(h),dispatch=ask(h);
  const decide=vi.spyOn(h.ctx.remoteAccess,"decide");push(dispatch);
  await vi.waitFor(()=>expect(decide).toHaveBeenCalled());
  h.abort.abort(Error("original association closed"));
  await vi.waitFor(()=>expect(dispatch.reject).toHaveBeenCalledTimes(1));
  expect(dispatch.resolve).not.toHaveBeenCalled();expect(await e.iterator.next()).toMatchObject({done:true});
});
it("rejects a late waterfall answer through the actual Connection and preserves original cancellation delivery",async()=>{
  const h=await host(),push=eventSource(h),e=await events(h),dispatch=ask(h);push(dispatch);
  const frame=await e.iterator.next();expect(frame).toMatchObject({value:{type:"waterfall"}});
  h.state.held=[];
  expect(await result(h,e.clientId,(frame.value as any).eventId)).toMatchObject({result:{ok:false,error:{code:"remote-access/denied"}}});
  expect(dispatch.resolve).not.toHaveBeenCalled();expect(dispatch.reject).toHaveBeenCalledTimes(1);
  expect(await e.iterator.next()).toMatchObject({value:{type:"cancel",eventId:(frame.value as any).eventId}});
  expect(await result(h,e.clientId,(frame.value as any).eventId)).toMatchObject({result:{ok:true}});
});
it.each([
  {name:"missing",resources:undefined},{name:"null",resources:null},{name:"empty",resources:[]},
  {name:"global",resources:[{kind:"global"}]},{name:"foreign",resources:[{kind:"session",id:"foreign"}]},
])("refuses $name waterfall resources",async({resources})=>{
  const h=await host(),push=eventSource(h),e=await events(h),dispatch=ask(h,resources);
  if(resources===undefined)delete dispatch.context.resources;
  push(dispatch);
  await vi.waitFor(()=>expect(dispatch.reject).toHaveBeenCalledTimes(1));expect(dispatch.resolve).not.toHaveBeenCalled();
  e.abort.abort();expect(await e.iterator.next()).toMatchObject({done:true});
});
it("retains the original raw file route hold even after scoped chat admission",async()=>{
  const h=await host(),fetch=vi.fn(async()=>new Response("private file"));
  h.ctx.connection.fetch.register({path:"/api/file",methods:["GET"],requestBody:"buffered",fetch});
  const response=await h.ctx.connection.createSharedFetchHandler("/api").fetch(new Request("http://native/api/file"),h.peer);
  expect(response.status).toBe(403);expect(fetch).not.toHaveBeenCalled();
});

async function native(){
  const root=await mkdtemp(join(tmpdir(),"mmx-owner-access-native-"));cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const h=await host(["owner-native-live","owner-native-cold"]);
  await mountAgentLoopTestDependencies(h.ctx);await h.ctx.plugin(JsonlPersistence,{root});
  let calls=0;
  class FixtureAdapter extends LlmAdapter{
    providerInfo(provider:string){return{id:provider,name:"Native fixture"};}
    async listModels(provider:string){return[{provider,id:"fixture",name:"Fixture",inputModalities:["text"]}];}
    async resolveModel(provider:string,model:string){return{provider,id:model,name:"Fixture",inputModalities:["text"]};}
    async *stream(options:any){
      options.signal?.throwIfAborted();calls++;
      yield{type:"block-start",index:0,blockType:"text"};yield{type:"text-delta",index:0,text:"Native response"};
      yield{type:"block-end",index:0,block:{type:"text",text:"Native response"}};
      yield{type:"usage",usage:{inputTokens:1,outputTokens:1}};yield{type:"finish",reason:{kind:"stop"}};
    }
  }
  h.ctx.llm.registerAdapter(["fixture"],new FixtureAdapter());
  const loop=await mountAgentLoopTestHarness(h.ctx);
  const controller=createSessionTestController(h.ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:root});
  const live=await loop.create(SessionId("owner-native-live"),{provider:"fixture",model:"fixture"},{cwd:root});
  const cold=SessionId("owner-native-cold"),seed=Session.create(cold);
  seed.append("turn/start",{turn:1});seed.append("step/start",{turn:1,step:1});
  seed.append("user/message",createUserMessage({content:[{type:"text",text:"Original question"}],source:{kind:"user"}}),{surfaceOp:"append"});
  seed.append("assistant/message",{turn:1,step:1,message:createMessage({role:"assistant",content:[{type:"text",text:"Original answer"}],
    source:{kind:"model",provider:"fixture",model:"fixture"}}),stream:[]},{surfaceOp:"append"});
  seed.append("step/end",{turn:1,step:1});seed.append("turn/end",{turn:1,reason:{kind:"completed"}});
  const handle=await h.ctx.sessionPersistence.create({...seed.header,cwd:root});
  try{await handle.append(seed.snapshotEvents());await handle.flush();}finally{await handle.close();}
  const request={sessionId:live.id,requestId:"native-associated-original",mode:"queue",content:[{type:"text",text:"Native associated prompt"}]};
  const invoke=(method:string,request:unknown)=>h.ctx.typertGateway.invoke({namespace:"session",method,args:{request},peer:h.peer});
  return{...h,root,live,cold,controller,request,invoke,calls:()=>calls};
}
it("reads the associated original JSONL and refuses a foreign read before persistence access",async()=>{
  const h=await native(),open=vi.spyOn(h.ctx.sessionPersistence,"open");
  await expect(h.invoke("page",{address:{kind:"session",sessionId:"foreign"},throughSeq:5,maxMessages:20})).rejects.toMatchObject({code:"remote-access/denied"});
  expect(open).not.toHaveBeenCalled();
  const page=await h.invoke("page",{address:{kind:"session",sessionId:h.cold},throughSeq:5,maxMessages:20});
  expect(JSON.stringify(page)).toContain("Original answer");expect(h.ctx.agents.get(h.cold)).toBeUndefined();expect(h.calls()).toBe(0);
});
it.each(["signal","guard","bindings","replacement"] as const)("retires a prompt through %s during attachment admission before the original native inbox write",async(retirement)=>{
  const h=await native(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const admit=h.ctx.attachments.admitPromptContent.bind(h.ctx.attachments);
  vi.spyOn(h.ctx.attachments,"admitPromptContent").mockImplementation(async content=>{entered.resolve();await release.promise;return admit(content);});
  const before=h.live.session.snapshotEvents(),pending=outcome(h.invoke("prompt",h.request));
  await Promise.race([entered.promise,pending.then(()=>{throw Error("native prompt did not reach attachment admission");})]);
  if(retirement==="signal")h.abort.abort(Error("association retired"));
  else if(retirement==="guard")h.state.current=false;
  else if(retirement==="bindings")h.state.held=[];
  else {h.dispose();h.ctx.remoteAccess.registerOwnerRestriction({...h.source,signal:new AbortController().signal});}
  release.resolve();
  expect(await pending).toHaveProperty("error");expect(h.live.session.snapshotEvents()).toEqual(before);expect(h.calls()).toBe(0);
});
it("keeps the original prompt provenance, request deduplication and native Stop semantics",async()=>{
  const h=await native(),followup=vi.spyOn(h.live,"followup"),cancel=vi.spyOn(h.live,"cancel");
  await expect(h.invoke("prompt",h.request)).resolves.toEqual({accepted:true});
  await expect(h.invoke("prompt",h.request)).resolves.toEqual({accepted:true});
  expect(followup).toHaveBeenCalledTimes(1);
  expect(followup.mock.calls[0]![0].source).toMatchObject({kind:"user",rpcId:h.request.requestId});
  await expect(h.invoke("cancel",{sessionId:"foreign"})).rejects.toMatchObject({code:"remote-access/denied"});expect(cancel).not.toHaveBeenCalled();
  await expect(h.invoke("cancel",{sessionId:h.live.id})).resolves.toEqual({accepted:true});
  expect(cancel).toHaveBeenCalledExactlyOnceWith({kind:"user"},{keepInbox:true});
});


function searchHit(h:Awaited<ReturnType<typeof native>>,id:string,index=0){
  return{header:{...h.live.session.header,id:SessionId(id),cwd:h.root},live:false,persisted:true,
    bestMatch:{sessionId:SessionId(id),seq:index,type:"user/message",time:100+index,surface:"current",snippet:"permitted match "+id}};
}
function searchFixture(h:Awaited<ReturnType<typeof native>>,allowed:readonly string[],pages:{items:ReturnType<typeof searchHit>[];nextCursor?:string}[]){
  h.state.held=[...bindings(allowed).map(binding=>({...binding,role:{...binding.role,actions:[...binding.role.actions,"session/search"]}})) as RemoteAccessBinding[],
    {resource:{kind:"global"},role:{name:"search-invocation",resource:"global",actions:["session/search"]}}];
  const rows=[...new Map(pages.flatMap(page=>page.items).map(item=>[item.header.id,{header:item.header,live:false,persisted:true}])).values()];
  vi.spyOn(h.ctx.sessionQuery,"listSessions").mockResolvedValue(rows as any);
  let index=0;
  const search=vi.spyOn(h.ctx.sessionQuery,"searchSessions").mockImplementation(async request=>{
    expect(request).not.toHaveProperty("sessionFilters");
    return pages[index++] as any;
  });
  const resume=vi.spyOn(h.ctx.agents,"resume");
  return{search,resume};
}
it("searches past an unauthorized first page without spending the permitted result limit",async()=>{
  const h=await native(),hidden=Array.from({length:20},(_,i)=>searchHit(h,"foreign-"+i));
  const {search,resume}=searchFixture(h,["shared-late"],[
    {items:hidden,nextCursor:"native-search-next"},{items:[searchHit(h,"shared-late")]},
  ]);
  await expect(h.invoke("search",{query:"match"})).resolves.toEqual({
    items:[{sessionId:"shared-late",snippet:"permitted match shared-late"}],hasMore:false,
  });
  expect(search).toHaveBeenCalledTimes(2);expect(resume).not.toHaveBeenCalled();expect(h.calls()).toBe(0);
});
it.each([{extraAllowed:false},{extraAllowed:true}])("computes search hasMore from permitted lookahead ($extraAllowed)",async({extraAllowed})=>{
  const h=await native(),ids=Array.from({length:20},(_,i)=>"shared-"+i);
  const extras=extraAllowed?[searchHit(h,"shared-extra")]:Array.from({length:20},(_,i)=>searchHit(h,"foreign-extra-"+i));
  const {search,resume}=searchFixture(h,extraAllowed?[...ids,"shared-extra"]:ids,[
    {items:ids.map(id=>searchHit(h,id)),nextCursor:"native-search-extra"},{items:extras},
  ]);
  const value=await h.invoke("search",{query:"match"}) as any;
  expect(value.items.map((item:any)=>item.sessionId)).toEqual(ids);expect(value.hasMore).toBe(extraAllowed);
  expect(search).toHaveBeenCalledTimes(2);expect(resume).not.toHaveBeenCalled();expect(h.calls()).toBe(0);
});
it("does not query content when no listed Session is permitted",async()=>{
  const h=await native(),{search,resume}=searchFixture(h,[],[{items:[searchHit(h,"foreign-only")]}]);
  await expect(h.invoke("search",{query:"match"})).resolves.toEqual({items:[],hasMore:false});
  expect(search).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();expect(h.calls()).toBe(0);
});
it("withholds search results when the original source retires during a page read",async()=>{
  const h=await native(),page={items:[searchHit(h,"shared-delayed")]};
  const {search,resume}=searchFixture(h,["shared-delayed"],[page]);
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  search.mockImplementation(async()=>{entered.resolve();await release.promise;return page as any;});
  const pending=outcome(h.invoke("search",{query:"match"}));await entered.promise;
  h.abort.abort(Error("original search generation retired"));release.resolve();
  expect(await pending).toHaveProperty("error");expect(resume).not.toHaveBeenCalled();expect(h.calls()).toBe(0);
});

it("never adopts a replacement owner source between event opening and its first pull",async()=>{
  const h=await host();eventSource(h);
  const abort=new AbortController();cleanup.push(async()=>{abort.abort();});
  const source=await h.ctx.typertGateway.wireStream.open("$events",{args:{}},(async function*(){})(),h.peer,abort.signal);
  h.dispose();h.ctx.remoteAccess.registerOwnerRestriction({...h.source,signal:new AbortController().signal});
  const iterator=source[Symbol.asyncIterator]();
  expect(await outcome(iterator.next())).toHaveProperty("error");
  expect((h.ctx.typertGateway as any).remoteEventClients.size).toBe(0);
  expect(h.ctx.typertGateway.hasLiveClient()).toBe(false);
});

it("reclaims a revoked search slot before counting the next page and its permitted lookahead",async()=>{
  const h=await native(),ids=Array.from({length:22},(_,i)=>"shared-changing-"+i);
  const pages=[{items:ids.slice(0,20).map(id=>searchHit(h,id)),nextCursor:"native-changing-next"},
    {items:ids.slice(20).map(id=>searchHit(h,id))}];
  const {search,resume}=searchFixture(h,ids,pages);
  search.mockImplementationOnce(async()=>pages[0] as any).mockImplementationOnce(async()=>{
    h.state.held=h.state.held.filter(binding=>binding.resource.kind!=="session"||binding.resource.id!==ids[0]);
    return pages[1] as any;
  });
  const value=await h.invoke("search",{query:"match"}) as any;
  expect(value.items.map((item:any)=>item.sessionId)).toEqual(ids.slice(1,21));
  expect(value.hasMore).toBe(true);expect(search).toHaveBeenCalledTimes(2);
  expect(resume).not.toHaveBeenCalled();expect(h.calls()).toBe(0);
});
