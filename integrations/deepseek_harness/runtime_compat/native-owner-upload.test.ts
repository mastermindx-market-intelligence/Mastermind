/** Original native upload, Gateway, Agent and Session owners; bounded storage fixture. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import RemoteAccessService,{type RemoteAccessBinding} from "@deepseek-ai/dsh-api-remote-access";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import {apply as applyConnection,inject as connectionInject} from "@deepseek-ai/dsh-client-connection";
import FileUploads from "@deepseek-ai/dsh-client-file-upload";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {mountAgentLoopTestDependencies,mountAgentLoopTestHarness} from "@deepseek-ai/dsh-agent-loop-testkit";
import {LlmAdapter} from "@deepseek-ai/dsh-llm";
import {SessionId} from "@deepseek-ai/dsh-session";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import {createSessionTestController} from "mmx-native-test-remote";
import {mkdtemp,rm} from "node:fs/promises";
import {join} from "node:path";
import {tmpdir} from "node:os";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
async function fixture(){
  const root=await mkdtemp(join(tmpdir(),"mmx-native-upload-"));cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());ctx.provide("remoteAccessOwnerRestricted",true);
  await ctx.plugin(TypertRegistry);await ctx.plugin(RemoteAccessService);await ctx.plugin(TypertGatewayService);
  provideBrowserCredentials(ctx);await ctx.plugin({inject:[...connectionInject],apply:applyConnection});
  await mountAgentLoopTestDependencies(ctx);await ctx.plugin(JsonlPersistence,{root});
  class FixtureAdapter extends LlmAdapter{
    providerInfo(provider:string){return{id:provider,name:"Upload fixture"};}
    async listModels(provider:string){return[{provider,id:"fixture",name:"Fixture",inputModalities:["text"]}];}
    async resolveModel(provider:string,model:string){return{provider,id:model,name:"Fixture",inputModalities:["text"]};}
    async *stream(){yield{type:"finish",reason:{kind:"stop"}};}
  }
  ctx.llm.registerAdapter(["fixture"],new FixtureAdapter());
  const loop=await mountAgentLoopTestHarness(ctx);
  const stored:Uint8Array[][]=[];
  const gate={hold:false,entered:Promise.withResolvers<void>(),release:Promise.withResolvers<void>()};
  const save=async(bytes:Uint8Array[],name?:string)=>{
    stored.push(bytes);if(gate.hold){gate.entered.resolve();await gate.release.promise;}
    return{attachmentId:"fixture-file-"+stored.length,name:name??"upload.bin",bytes:bytes.reduce((n,b)=>n+b.length,0)};
  };
  const storage={
    imageLimits:{maxImageBytes:1024,maxImagesPerMessage:2,maxMessageImageBytes:2048,maxImagePixels:100,maxImageDimension:10,mediaTypes:["image/png"]},
    admitPromptContent:vi.fn(async(parts:any[])=>parts),
    saveFileStream:vi.fn(async(request:any)=>{const bytes:Uint8Array[]=[];for await(const part of request.data)bytes.push(part);return save(bytes,request.name);}),
    admitEncodedFile:vi.fn(async(request:any)=>save([new Uint8Array(Buffer.from(request.data,"base64"))],request.name)),
    isAttachmentError:()=>false,
  };
  expect(ctx.get("attachments")).toBeUndefined();ctx.provide("attachments",storage as never);
  if(ctx.get("commands")===undefined)ctx.provide("commands",{registerFileReceiptResolver:()=>()=>{}} as never);
  const uploads=new FileUploads(ctx);
  const register=uploads.registerAgentResolver.bind(uploads);let registration:any;
  vi.spyOn(uploads,"registerAgentResolver").mockImplementation((resolve,access)=>{
    const dispose=register(resolve,access);registration={resolve,access,dispose};return dispose;
  });
  createSessionTestController(ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:root});
  const live=await loop.create(SessionId("upload-live"),{provider:"fixture",model:"fixture"},{cwd:root});
  const state={current:true,allowed:true,denyEncoded:false},abort=new AbortController();
  const bindings=():RemoteAccessBinding[]=>state.allowed?[{resource:{kind:"session",id:live.id},
    role:{name:"native-upload",resource:"session",actions:["fileUploads/upload","session/prompt"]},
    condition:({args})=>state.denyEncoded&&(args?.request as {data?:string}|undefined)?.data==="AQID"
      ?{kind:"deny",reason:"encoded-data-withdrawn"}:{kind:"allow"}}]:[];
  ctx.remoteAccess.registerOwnerRestriction({signal:abort.signal,requireCurrent:()=>{if(!state.current)throw Error("retired");},policy:{bindings}});
  const peer=ctx.connection.browserPeer,fetch=ctx.connection.createSharedFetchHandler("/api").fetch;
  const upload=(body:BodyInit=new Blob([Uint8Array.of(1,2,3)]),sessionId:string=live.id)=>fetch(new Request(
    "http://native/api/session/uploadFileBinary?sessionId="+encodeURIComponent(sessionId)+"&name=original.bin",
    {method:"POST",headers:{"content-type":"application/octet-stream"},body,duplex:"half"} as RequestInit),peer);
  const invoke=(method:string,request:any)=>ctx.typertGateway.invoke({namespace:"session",method,args:{request},peer});
  const renew=()=>{registration.dispose();const stop=register(registration.resolve,registration.access);cleanup.push(async()=>stop());};
  const staged=()=>((uploads as any).stagedFiles.get(live.session)?.size??0) as number;
  return{ctx,live,uploads,storage,stored,gate,state,abort,peer,fetch,upload,invoke,renew,staged};
}

it("stores a permitted binary upload and consumes its exact Session receipt through the original prompt",async()=>{
  const h=await fixture(),response=await h.upload(),body=await response.json();
  expect(response.status).toBe(200);expect(body.ok).toBe(true);expect(h.stored).toEqual([[Uint8Array.of(1,2,3)]]);
  expect(h.uploads.resolve(h.live,body.value.receiptId)).toEqual(body.value.file);
  const followup=vi.spyOn(h.live,"followup");
  await expect(h.invoke("prompt",{sessionId:h.live.id,requestId:"native-upload-prompt",mode:"queue",
    content:[{type:"file",receiptId:body.value.receiptId}]})).resolves.toEqual({accepted:true});
  expect(followup).toHaveBeenCalledOnce();
  expect(followup.mock.calls[0]![0].content).toContainEqual({type:"file",attachment:body.value.file});
  expect(followup.mock.calls[0]![0].source).toMatchObject({kind:"user",rpcId:"native-upload-prompt"});
});
it("refuses a foreign upload before Agent activation or storage",async()=>{
  const h=await fixture(),resume=vi.spyOn(h.ctx.agents,"resume");
  expect((await h.upload(undefined,"foreign")).status).toBe(403);
  expect(resume).not.toHaveBeenCalled();expect(h.storage.saveFileStream).not.toHaveBeenCalled();expect(h.staged()).toBe(0);
});
it("keeps a scoped cold upload out of the original Agent resolver",async()=>{
  const h=await fixture(),resume=vi.spyOn(h.ctx.agents,"resume");
  const get=h.ctx.agents.get.bind(h.ctx.agents);
  vi.spyOn(h.ctx.agents,"get").mockImplementation(id=>id===h.live.id?undefined:get(id));
  const response=await h.upload();expect(await response.json()).toMatchObject({ok:false,error:{code:"session/not-found"}});
  expect(resume).not.toHaveBeenCalled();expect(h.storage.saveFileStream).not.toHaveBeenCalled();
});
it.each(["signal","resolver","peer"] as const)("cancels the original stalled byte reader when its %s retires",async(retire)=>{
  const h=await fixture(),cancel=vi.fn();
  const body=new ReadableStream<Uint8Array>({cancel});
  const pending=h.upload(body);
  await vi.waitFor(()=>expect(h.storage.saveFileStream).toHaveBeenCalledOnce());
  if(retire==="signal")h.abort.abort(Error("retired"));
  else if(retire==="resolver")h.renew();
  else await h.peer.dispose();
  expect((await pending).status).toBe(403);expect(cancel).toHaveBeenCalledOnce();
  expect(h.stored).toEqual([]);expect(h.staged()).toBe(0);expect(h.ctx.agents.get(h.live.id)).toBe(h.live);
});
it.each(["guard","bindings","resolver"] as const)("withholds a binary receipt after storage on %s retirement without removing the native Agent",async(retire)=>{
  const h=await fixture();h.gate.hold=true;const pending=h.upload();await h.gate.entered.promise;
  if(retire==="guard")h.state.current=false;else if(retire==="bindings")h.state.allowed=false;else h.renew();
  h.gate.release.resolve();expect((await pending).status).toBe(403);
  expect(h.stored).toHaveLength(1);expect(h.staged()).toBe(0);expect(h.ctx.agents.get(h.live.id)).toBe(h.live);
});
it.each(["bindings","data"] as const)("keeps the encoded native fallback in the same access and receipt boundary on %s retirement",async(retire)=>{
  const h=await fixture();h.gate.hold=true;
  const pending=h.ctx.typertGateway.invoke({namespace:"fileUploads",method:"upload",
    args:{agentId:h.live.id,request:{data:"AQID",name:"encoded.bin"}},peer:h.peer});
  const observed=pending.then(value=>({value}),error=>({error}));
  await Promise.race([h.gate.entered.promise,observed.then(()=>{throw Error("encoded upload never reached storage");})]);
  if(retire==="bindings")h.state.allowed=false;else h.state.denyEncoded=true;
  h.gate.release.resolve();expect(await observed).toHaveProperty("error");
  expect(h.stored).toHaveLength(1);expect(h.staged()).toBe(0);
});
it("does not accept a decorated Promise as a synchronous native route allowance",async()=>{
  const h=await fixture(),called=vi.fn(async()=>new Response("unexpected"));
  const source=Object.assign(Promise.resolve(),{signal:new AbortController().signal,requireCurrent:()=>{}});
  const dispose=h.ctx.connection.fetch.register({path:"/api/fixture-upload",methods:["POST"],requestBody:"streaming",
    ownerAccess:()=>source,fetch:called});
  expect((await h.fetch(new Request("http://native/api/fixture-upload",{method:"POST"}),h.peer)).status).toBe(403);
  expect(called).not.toHaveBeenCalled();await dispose();
});
it("retires the exact original Fetch route even when its caller later changes the route object",async()=>{
  const h=await fixture(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const route={path:"/api/original-upload",methods:["POST"] as const,requestBody:"streaming" as const,
    ownerAccess:()=>({signal:new AbortController().signal,requireCurrent:()=>{}}),
    fetch:async()=>{entered.resolve();await release.promise;return new Response("late");}};
  const dispose=h.ctx.connection.fetch.register(route);
  const pending=h.fetch(new Request("http://native/api/original-upload",{method:"POST"}),h.peer);
  await entered.promise;route.path="/api/changed-upload";await dispose();release.resolve();
  expect((await pending).status).toBe(403);
  expect((await h.fetch(new Request("http://native/api/original-upload",{method:"POST"}),h.peer)).status).toBe(404);
});
