/** Native authority at original model preparation, registry and Messages write. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import LlmRuntime,{LlmAdapter,LlmError,createUserMessage,type GenerateOptions,type NativeLlmWritePermit,type StreamChunk} from "@deepseek-ai/dsh-llm";
import {adapter as deepseek,options as deepOptions,sse,textEvents} from "mmx-native-deepseek-helpers";
const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.unstubAllGlobals();vi.restoreAllMocks();});
class Fixture extends LlmAdapter{
  requests:GenerateOptions[]=[];
  override async resolveModel(provider:string,model:string){return{provider,id:model,name:model,defaultMaxTokens:100};}
  async *stream(options:GenerateOptions,native?:NativeLlmWritePermit):AsyncIterable<StreamChunk>{
    native?.assertCurrent();this.requests.push(options);yield{type:"finish",reason:{kind:"stop"}};
  }
}
async function host(native=true){
  const ctx=new Context(),lifetime=new AbortController(),seen:any[]=[];
  const state={current:true};
  const admission:any={signal:lifetime.signal,check:(facts:any)=>{seen.push(facts);return state.current;}};
  if(native)ctx.provide("nativeLlmAdmission",admission);
  cleanup.push(()=>ctx.fiber.dispose());await ctx.plugin(LlmRuntime);
  const adapter=new Fixture(),registration=ctx.llm.registerAdapter(["fixture"],adapter);
  const request=(extra:Partial<GenerateOptions>={}):GenerateOptions=>({provider:"fixture",model:"fixture",
    messages:[createUserMessage({source:{kind:"user"},content:[{type:"text",text:"question"}]})],...extra});
  return{ctx,lifetime,state,admission,adapter,registration,request,seen};
}
async function chunks(stream:AsyncIterable<StreamChunk>){const out:StreamChunk[]=[];for await(const x of stream)out.push(x);return out;}
const failure=(result:StreamChunk[])=>result.find(x=>x.type==="finish") as any;

it.each([false,true])("joins actual request, resolved defaults and registration for prepared=%s",async prepared=>{
  const h=await host(),request=h.request({sessionId:"original-session" as any,purpose:"compaction"});
  const observation=h.ctx.llm.observeRegistration("fixture")!;
  expect(observation.adapterIdentity).toBe(h.adapter);expect(observation.assertCurrent()).toBe(true);
  expect(Object.isFrozen(observation.registrationIdentity)).toBe(true);
  expect(()=>{(observation.registrationIdentity as any).adapter=new Fixture();}).toThrow();
  expect(()=>{(observation.registrationIdentity as any).provider.id="foreign";}).toThrow();
  const call=prepared?await h.ctx.llm.prepareCall(request):undefined;
  const actual=call?{...request,...call.config}:request;
  const result=await chunks(call?call.stream(actual):h.ctx.llm.stream(actual));
  expect(failure(result).reason.kind).toBe("stop");expect(h.adapter.requests).toHaveLength(1);
  expect(h.seen.map(x=>x.phase)).toEqual(["dispatch","write"]);
  for(const facts of h.seen){
    expect(facts.request).toBe(actual);expect(facts.config).toMatchObject({provider:"fixture",model:"fixture",maxTokens:100});
    expect(facts.registrationIdentity).toBe(observation.registrationIdentity);
    expect(facts.ownerIdentity).toBe(observation.ownerIdentity);
    expect(facts.options.sessionId).toBe("original-session");expect(facts.options.purpose).toBe("compaction");
    expect(facts.config).not.toHaveProperty("purpose");expect(facts.config).not.toHaveProperty("sessionId");
  }
  expect(Object.isFrozen(actual)).toBe(true);
});

it("passive registration observation is exact and invalidates on same-adapter replacement",async()=>{
  const h=await host(),seen=h.ctx.llm.observeRegistration("fixture")!;
  expect(h.ctx.llm.observeRegistration("missing")).toBeUndefined();
  h.registration.replace(["fixture"]);
  expect(()=>seen.assertCurrent()).toThrow("registration");
  const next=h.ctx.llm.observeRegistration("fixture")!;
  expect(next.adapterIdentity).toBe(seen.adapterIdentity);expect(next.registrationIdentity).not.toBe(seen.registrationIdentity);
  h.registration();expect(()=>next.assertCurrent()).toThrow("registration");
});

it.each(["withdrawn","callback-replaced","async","registration-reentry"] as const)(
  "native final dispatch refuses %s without entering the adapter",async mode=>{
    const h=await host();
    if(mode==="withdrawn")h.state.current=false;
    if(mode==="callback-replaced")h.admission.check=()=>true;
    if(mode==="registration-reentry"){
      // The captured check's observable state can change its effects without replacing it.
      h.seen.push=(()=>{h.registration.replace(["fixture"]);return 1;}) as any;
    }
    if(mode==="async"){
      h.state.current=Promise.resolve(true) as any;
    }
    const result=await chunks(h.ctx.llm.stream(h.request()));
    expect(failure(result).reason.kind).toBe("error");expect(h.adapter.requests).toEqual([]);
  });

it.each([false,true])("registration replacement after model lookup starts preserves ordinary=%s",async ordinary=>{
  const h=await host(!ordinary),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.adapter.resolveModel.bind(h.adapter);
  vi.spyOn(h.adapter,"resolveModel").mockImplementation(async(p,m)=>{entered.resolve();await release.promise;return original(p,m);});
  const pending=chunks(h.ctx.llm.stream(h.request()));await entered.promise;h.registration.replace(["fixture"]);release.resolve();
  const result=await pending;
  expect(failure(result).reason.kind).toBe(ordinary?"stop":"error");
  expect(h.adapter.requests).toHaveLength(ordinary?1:0);
});

it("awaiting middleware cannot retain withdrawn native authority",async()=>{
  const h=await host(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  h.ctx.on("llm/stream",async function*(options,next){entered.resolve();await release.promise;yield*next();});
  const pending=chunks(h.ctx.llm.stream(h.request()));await entered.promise;h.state.current=false;release.resolve();
  expect(failure(await pending).reason.kind).toBe("error");expect(h.adapter.requests).toEqual([]);
});

it("prepared native header admission uses original registration and rejects unprepared fallback",async()=>{
  const h=await host(),call=await h.ctx.llm.prepareCall(h.request()),signal=new AbortController().signal;
  const context={agent:{},session:{},turn:1,step:1,signal};
  expect(h.ctx.llm.requireNativePreparation(context,call.config,call)).toBe(true);
  expect(h.seen[0].agent).toBe(context.agent);expect(h.seen[0].session).toBe(context.session);
  expect(()=>h.ctx.llm.requireNativePreparation(context,call.config,undefined)).toThrow("prepared registration");
  h.registration.replace(["fixture"]);
  expect(()=>h.ctx.llm.requireNativePreparation(context,call.config,call)).toThrow("registration");
});

it("native attachment refusal retains original content before provider dispatch",async()=>{
  const h=await host();
  const message=createUserMessage({source:{kind:"user"},content:[{type:"file",attachment:{
    id:"fixture-file",filename:"original.txt",mimeType:"text/plain",byteSize:10,
  }} as any]});
  const result=await chunks(h.ctx.llm.stream(h.request({messages:[message]})));
  expect(failure(result).reason.failure.code).toBe("NATIVE_ATTACHMENT_UNSUPPORTED");expect(h.adapter.requests).toEqual([]);
});

async function httpHost(dependencies:Record<string,unknown>={}){
  const h=await host();h.registration();
  const adapter=deepseek({}, {...dependencies,nativeRequired:true});
  const registration=h.ctx.llm.registerAdapter(["deepseek-official"],adapter);
  const fetch=vi.fn<typeof globalThis.fetch>().mockImplementation(async()=>new Response(sse(textEvents)));
  vi.stubGlobal("fetch",fetch);
  return{...h,adapter,registration,fetch,run:()=>chunks(h.ctx.llm.stream(deepOptions()))};
}
it.each(["authentication","extensions"] as const)("withdrawal during %s refuses the Messages write",async phase=>{
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>(),accepted=vi.fn();
  const dependencies=phase==="authentication"?{resolveAuth:async()=>{entered.resolve();await release.promise;return{headers:{"x-test":"inert"}};}}:
    {prepareExtensions:async()=>{entered.resolve();await release.promise;return{fields:{},accept:accepted};}};
  const h=await httpHost(dependencies),pending=h.run();await entered.promise;h.state.current=false;release.resolve();
  expect(failure(await pending).reason.kind).toBe("error");expect(h.fetch).not.toHaveBeenCalled();expect(accepted).not.toHaveBeenCalled();
});
it("synchronous header preparation cannot revoke authority and still write",async()=>{
  let h:Awaited<ReturnType<typeof httpHost>>;
  h=await httpHost({resolveUserId:()=>{h.state.current=false;return"inert";}});
  expect(failure(await h.run()).reason.kind).toBe("error");expect(h.fetch).not.toHaveBeenCalled();
});
it("HTTP acceptance settles captured extensions even after send authority withdraws",async()=>{
  const accepted=vi.fn(),h=await httpHost({prepareExtensions:async()=>({fields:{},accept:accepted})});
  h.fetch.mockImplementation(async()=>{h.state.current=false;return new Response(sse(textEvents));});
  expect(failure(await h.run()).reason.kind).toBe("stop");
  expect(h.fetch).toHaveBeenCalledTimes(1);expect(accepted).toHaveBeenCalledTimes(1);
});
it("a native provider cannot dispatch directly without the original runtime witness",async()=>{
  const auth=vi.fn(),adapter=deepseek({}, {nativeRequired:true,resolveAuth:auth});
  await expect(chunks(adapter.stream(deepOptions()))).rejects.toThrow("original runtime witness");
  expect(auth).not.toHaveBeenCalled();
});

it("a structural native permit cannot authorize a provider request",async()=>{
  const auth=vi.fn(),adapter=deepseek({}, {nativeRequired:true,resolveAuth:auth});
  const fake={signal:new AbortController().signal,assertCurrent:()=>true as const};
  await expect(chunks(adapter.stream(deepOptions(),fake))).rejects.toThrow("original adapter invocation");
  expect(auth).not.toHaveBeenCalled();
});
it("an issued native permit cannot be replayed or paired with different options",async()=>{
  const h=await httpHost(),generate=vi.spyOn(h.adapter as any,"generate");
  expect(failure(await h.run()).reason.kind).toBe("stop");
  const [options,_connection,permit]=generate.mock.calls[0];
  await expect(chunks(h.adapter.stream({...options},permit))).rejects.toThrow("original adapter invocation");
  await expect(chunks(h.adapter.stream(options,permit))).rejects.toThrow("original adapter invocation");
  expect(h.fetch).toHaveBeenCalledTimes(1);
});

it("native lifetime cancellation stays terminal while the Agent signal remains live",async()=>{
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const h=await httpHost({prepareExtensions:async()=>{entered.resolve();await release.promise;return{fields:{},accept:async()=>{}};}});
  const signal=new AbortController().signal;
  const pending=chunks(h.ctx.llm.stream(deepOptions({signal})));
  await entered.promise;h.lifetime.abort();release.resolve();
  const result=await pending;
  expect(signal.aborted).toBe(false);expect(failure(result).reason.kind).toBe("aborted");
  expect(failure(result).reason.failure.code).toBe("ABORTED");expect(h.fetch).not.toHaveBeenCalled();
});
it("passive registration currentness requires the original root runtime",async()=>{
  const h=await host(),observation=h.ctx.llm.observeRegistration("fixture")!;
  const original=h.ctx.get.bind(h.ctx);
  vi.spyOn(h.ctx,"get").mockImplementation(((name:any)=>name==="llm"?undefined:original(name)) as any);
  expect(()=>observation.assertCurrent()).toThrow("runtime changed");
});
