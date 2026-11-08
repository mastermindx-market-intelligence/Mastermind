import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import RemoteAccessService from "@deepseek-ai/dsh-api-remote-access";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import {Remote,TypertRemoteService,type PrincipalMap} from "@deepseek-ai/dsh-typert-protocol";
import {apply as applyConnection,inject as connectionInject} from "@deepseek-ai/dsh-client-connection";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";

declare module "@deepseek-ai/dsh-typert-protocol"{
  interface PrincipalMap{"host-read-fixture":{readonly kind:"host-read-fixture"}}
}
const roots:Context[]=[];
afterEach(async()=>{vi.restoreAllMocks();while(roots.length)await roots.pop()!.fiber.dispose();});
class HostFixture extends TypertRemoteService{
  calls=0;
  constructor(ctx:Context){super(ctx,"hostFixture");}
  @Remote read():string{this.calls++;return this.ctx.invocation?.peer.principal.kind??"internal";}
  @Remote mutate():string{this.calls++;return "native write";}
}
async function host({restricted=true,isolate=false}:{restricted?:boolean,isolate?:boolean}={}){
  const root=new Context();roots.push(root);
  if(restricted)root.provide("remoteAccessOwnerRestricted",true);
  const ctx=isolate?root.isolate("remoteAccessOwnerRestricted"):root;
  await ctx.plugin(TypertRegistry);
  const accessFiber=await ctx.plugin(RemoteAccessService);
  await ctx.plugin(TypertGatewayService);
  provideBrowserCredentials(ctx);
  await ctx.plugin({inject:[...connectionInject],apply:applyConnection});
  await ctx.plugin(HostFixture);
  const owner=ctx.connection.browserPeer;
  return{root,ctx,owner,accessFiber,fixture:ctx.get("hostFixture") as HostFixture};
}
function call(h:Awaited<ReturnType<typeof host>>,method:string,peer=h.owner){
  return h.ctx.typertGateway.invoke({peer,namespace:"hostFixture",method,args:{}});
}
it("holds every stock-owner command before dispatch, including calls with no resources",async()=>{
  const h=await host();
  const resolve=vi.spyOn(h.ctx.typertGateway as any,"resolveReceiverContext");
  const result=await call(h,"mutate").then(()=>({allowed:true}),error=>({allowed:false,code:error.code}));
  expect(result).toEqual({allowed:false,code:"remote-access/denied"});
  expect(h.fixture.calls).toBe(0);expect(resolve).not.toHaveBeenCalled();
  expect(h.ctx.remoteAccess.decide({principal:{kind:"owner"},action:"hostFixture/mutate",resources:[]})).toMatchObject({kind:"deny"});
});
it("advertises no stock-owner grants in baseline, list filtering, or access follow",async()=>{
  const h=await host(),abort=new AbortController();
  expect(h.ctx.remoteAccess.snapshotFor({kind:"owner"})).toEqual({type:"baseline",owner:false,grants:[]});
  const invocation={peer:h.owner,request:{namespace:"hostFixture",method:"read",args:{}}};
  expect(h.ctx.extend({invocation} as any).remoteAccess.allows({kind:"global"})).toBe(false);
  const source=await h.ctx.typertGateway.stream({peer:h.owner,namespace:"remoteAccess",method:"follow",args:{},signal:abort.signal});
  const iterator=source[Symbol.asyncIterator]();
  expect((await iterator.next()).value).toEqual({type:"baseline",owner:false,grants:[]});
  abort.abort();await iterator.return?.();
});
it("does not inherit privilege through a child isolation label or service remount",async()=>{
  const h=await host({isolate:true});
  expect(h.ctx.get("remoteAccessOwnerRestricted")).toBeUndefined();
  expect(h.ctx.remoteAccess.ownerRestricted).toBe(true);
  await expect(call(h,"mutate")).rejects.toMatchObject({code:"remote-access/denied"});
  await h.accessFiber.dispose();await h.ctx.plugin(RemoteAccessService);
  await vi.waitFor(()=>expect(h.ctx.get("typertGateway")).toBeDefined());
  expect(h.ctx.remoteAccess.ownerRestricted).toBe(true);
  await expect(call(h,"mutate")).rejects.toMatchObject({code:"remote-access/denied"});
});
it("preserves the existing non-owner read policy without inheriting owner writes",async()=>{
  const h=await host(),peer=h.ctx.connection.createPeer({principal:{kind:"host-read-fixture"}});
  const dispose=h.ctx.remoteAccess.registerPolicy("host-read-fixture",{bindings:()=>[{
    role:{name:"existing-fixture-read",resource:"global",actions:["hostFixture/read"]},resource:{kind:"global"},
  }]});
  await expect(call(h,"read",peer)).resolves.toBe("host-read-fixture");
  await expect(call(h,"mutate",peer)).rejects.toMatchObject({code:"remote-access/denied"});
  dispose();await expect(call(h,"read",peer)).rejects.toMatchObject({code:"remote-access/denied"});
  await expect(call(h,"read")).rejects.toMatchObject({code:"remote-access/denied"});
});
it("refuses stock-owner event subscription and event answers before event ownership",async()=>{
  const h=await host();
  await expect(h.ctx.typertGateway.wireStream.open("$events",{args:{}},(async function*(){})(),h.owner,new AbortController().signal))
    .rejects.toMatchObject({code:"remote-access/denied",details:{reason:"owner-restricted"}});
  const response=await h.ctx.connection.createSharedFetchHandler("/api").fetch(new Request("http://127.0.0.1/api/$events/result",{
    method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
      type:"client-request",rpcId:"held-event-answer",method:"$events/result",
      payload:{args:{clientId:"none",eventId:"none",outcome:{kind:"next"}}},
    }),
  }),h.owner);
  expect(await response.json()).toMatchObject({result:{ok:false,error:{code:"remote-access/denied",details:{reason:"owner-restricted"}}}});
});
it.each([
  ["/api/session/uploadFileBinary","POST","streaming"],
  ["/api/file","GET","buffered"],
  ["/api/changes.summary","GET","buffered"],
  ["/api/changes.diff","GET","buffered"],
  ["/api/changes.open","POST","buffered"],
  ["/api/present.open","POST","buffered"],
  ["/api/present.host","GET","buffered"],
] as const)("holds exact raw route %s before its callback",async(path,method,requestBody)=>{
  const h=await host(),fetch=vi.fn(async()=>new Response("native effect"));
  h.ctx.connection.fetch.register({path,methods:[method],requestBody,fetch});
  const response=await h.ctx.connection.createSharedFetchHandler("/api").fetch(new Request("http://127.0.0.1"+path,{method}),h.owner);
  expect(response.status).toBe(403);expect(fetch).not.toHaveBeenCalled();
});
it("keeps ordinary attended owner calls and raw routes available",async()=>{
  const h=await host({restricted:false});await expect(call(h,"mutate")).resolves.toBe("native write");
  const fetch=vi.fn(async()=>new Response("original native route"));
  h.ctx.connection.fetch.register({path:"/api/file",methods:["GET"],requestBody:"buffered",fetch});
  const response=await h.ctx.connection.createSharedFetchHandler("/api").fetch(new Request("http://127.0.0.1/api/file"),h.owner);
  expect(response.status).toBe(200);expect(fetch).toHaveBeenCalledTimes(1);
  expect(h.ctx.remoteAccess.snapshotFor({kind:"owner"})).toEqual({type:"baseline",owner:true});
});
it("keeps exact origin and native cookie authentication ahead of the company hold",async()=>{
  const h=await host(),target=new URL(h.ctx.connection.authenticatedUrl("http://127.0.0.1:4180"));
  let cookie:string|undefined;
  h.ctx.connection.authorizeIndex({method:"GET",url:target.pathname+target.search,headers:{host:target.host}},{
    writeHead(_status:number,headers:any){cookie=headers?.["set-cookie"]?.split(";",1)[0];},end(){},
  });
  expect(typeof cookie).toBe("string");
  const request={method:"POST",headers:{host:target.host,origin:target.origin,cookie:cookie!}};
  expect(h.ctx.connection.admit(request)).toHaveProperty("peer");
  expect(h.ctx.connection.admit({...request,headers:{...request.headers,origin:"http://127.0.0.1.evil:4180"}})).toEqual({rejection:403});
  expect(h.ctx.connection.admit({...request,headers:{host:target.host,origin:target.origin}})).toEqual({rejection:401});
});
it.each([false,"true",1,null])("refuses malformed launch restriction %s",async(value)=>{
  const root=new Context();roots.push(root);root.provide("remoteAccessOwnerRestricted",value as any);
  await expect(root.plugin(RemoteAccessService)).rejects.toThrow("invalid host owner access restriction");
});
