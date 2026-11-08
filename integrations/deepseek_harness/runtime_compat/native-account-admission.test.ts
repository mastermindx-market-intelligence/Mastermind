/** Native account witnesses retain original credential and HTTP settlement owners. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import {mkdtemp,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import AuthorizationService from "@deepseek-ai/dsh-authorization";
import {LocalCredentialProvider} from "@deepseek-ai/dsh-credentials-local";
import {credentialKey} from "@deepseek-ai/dsh-credentials";
import {PlatformAccount} from "@deepseek-ai/dsh-deepseek-account-platform";
import LlmRuntime,{LlmError,createUserMessage,type StreamChunk} from "@deepseek-ai/dsh-llm";
import {DeepSeekLlmApiExtensionRegistry} from "@deepseek-ai/dsh-deepseek-llm-api-extensions";
import * as AccountProvider from "@deepseek-ai/dsh-llm-deepseek-account";
import {AccountModelCatalog} from "mmx-native-account-catalog";
import {requestModelListing,parseModelListing} from "mmx-native-account-listing";
import {sse,textEvents} from "mmx-native-deepseek-helpers";

const KEY=credentialKey("deepseek-account-platform","default");
const INFERENCE="https://api.deepseek.com",PLATFORM="https://platform.deepseek.com";
const META={version:"1.2.3",locale:"en",timezoneOffsetSeconds:0};
const FLASH={id:"deepseek-flash",name:"DeepSeek Flash",context_window:1000000,max_output_tokens:1000,
  input_modalities:["text"],output_modalities:["text"],api_capabilities:{anthropic_messages:{}}};
const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.unstubAllGlobals();vi.restoreAllMocks();});
const flush=()=>new Promise<void>(resolve=>setImmediate(resolve));
async function fixture(config:Record<string,unknown>={}){
  const home=await mkdtemp(join(tmpdir(),"mmx-native-account-"));
  cleanup.push(()=>rm(home,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  await ctx.plugin(LocalCredentialProvider,{path:join(home,"credentials.yaml"),watch:false});
  await ctx.plugin(AuthorizationService);
  const fiber=ctx.plugin(PlatformAccount,{logoutMaxRetries:0,...config});await fiber;
  const account=ctx.deepseekAccount as PlatformAccount;
  const fetch=vi.fn<typeof globalThis.fetch>().mockImplementation(async()=>Response.json({code:0,data:{biz_code:0,biz_data:null}}));
  vi.stubGlobal("fetch",fetch);
  const write=async(token="fixture-secret",issuer=PLATFORM)=>ctx.credentials.modifyRecord(KEY,()=>Promise.resolve({
    kind:"grant" as const,payload:{version:1,issuer,token},
  }));
  return{ctx,account,fiber,fetch,write};
}
it("passive account observation reads only the original grant and never publishes a token",async()=>{
  const h=await fixture();await h.write();
  const reads=vi.spyOn(h.ctx.credentials,"readRecord"),writes=vi.spyOn(h.ctx.credentials,"modifyRecord");
  const profile=vi.spyOn(h.account,"getProfile"),device=vi.spyOn(h.account,"getDeviceIdentity");
  const snapshot=await h.account.getLocalInferenceSnapshot();
  expect(snapshot).toMatchObject({inferenceOrigin:INFERENCE,userId:null});
  expect(Object.keys(snapshot!).sort()).toEqual(["inferenceOrigin","isCurrent","userId"]);
  expect(Object.isFrozen(snapshot)).toBe(true);expect(snapshot!.isCurrent()).toBe(true);
  expect(JSON.stringify(snapshot)).not.toContain("fixture-secret");
  expect(reads).toHaveBeenCalledExactlyOnceWith(KEY);expect(writes).not.toHaveBeenCalled();
  expect(profile).not.toHaveBeenCalled();expect(device).not.toHaveBeenCalled();expect(h.fetch).not.toHaveBeenCalled();
});
it("a missing grant supplies neither native HTTP authority nor an account identity",async()=>{
  const h=await fixture();
  expect(await h.account.resolveInferenceCredential(INFERENCE)).toBeUndefined();
  expect(await h.account.getLocalInferenceSnapshot()).toBeNull();expect(h.fetch).not.toHaveBeenCalled();
});
it.each(["https://elsewhere.invalid/messages","https://name:secret@api.deepseek.com/messages","http://api.deepseek.com/messages"])(
  "refuses native authentication for destination %s without reading the credential",async url=>{
    const h=await fixture();await h.write();const reads=vi.spyOn(h.ctx.credentials,"readRecord");
    expect(await h.account.resolveInferenceCredential(url)).toBeUndefined();expect(reads).not.toHaveBeenCalled();
  });
it("retains legacy inference eligibility while native capture additionally requires the exact issuer",async()=>{
  const h=await fixture();await h.write("dsh_mock_inert");
  expect(await h.account.resolveToken(INFERENCE)).toBeUndefined();
  expect(await h.account.resolveInferenceCredential(INFERENCE)).toBeUndefined();
  await h.write("inert","http://localhost:1");
  expect(await h.account.resolveToken(INFERENCE)).toBeUndefined();
  await expect(h.account.resolveInferenceCredential(INFERENCE)).rejects.toThrow();
  await h.write("inert","https://other-platform.invalid");
  expect(await h.account.resolveToken(INFERENCE)).toBe("inert");
  await expect(h.account.resolveInferenceCredential(INFERENCE)).rejects.toThrow();
  expect(h.fetch).not.toHaveBeenCalled();
});
it("private deployments retain the original matching issuer and inference origin rules",async()=>{
  const origin="https://private-platform.invalid",inference="https://private-inference.invalid";
  const h=await fixture({platformOrigin:origin,inferenceOrigin:inference});
  await h.write("inert",origin);
  expect(await h.account.resolveToken(inference)).toBe("inert");
  const witness=await h.account.resolveInferenceCredential(inference);expect(witness!.assertCurrent()).toBe(true);
  expect(await h.account.resolveInferenceCredential(INFERENCE)).toBeUndefined();
  await h.write("inert",PLATFORM);expect(await h.account.resolveToken(inference)).toBeUndefined();
});
it("grant replacement invalidates retained authority and passive identity synchronously",async()=>{
  const h=await fixture();await h.write();
  const witness=(await h.account.resolveInferenceCredential(INFERENCE))!,snapshot=(await h.account.getLocalInferenceSnapshot())!;
  expect(witness.assertCurrent()).toBe(true);expect(Object.isFrozen(witness)).toBe(true);
  await h.write("replacement-secret");
  expect(witness.signal.aborted).toBe(true);expect(()=>witness.assertCurrent()).toThrow();expect(snapshot.isCurrent()).toBe(false);
  const reads=vi.spyOn(h.ctx.credentials,"readRecord");expect(()=>witness.assertCurrent()).toThrow();expect(reads).not.toHaveBeenCalled();
  expect((await h.account.resolveInferenceCredential(INFERENCE))!.token).toBe("replacement-secret");
});
it.each([1,2])("withdrawal in nested local-read microtasks cannot publish a current witness (depth %s)",async depth=>{
  const h=await fixture();await h.write();
  const original=h.ctx.credentials.readRecord.bind(h.ctx.credentials);
  vi.spyOn(h.ctx.credentials,"readRecord").mockImplementationOnce(async key=>{
    const value=await original(key);
    const withdraw=(remaining:number)=>queueMicrotask(()=>remaining?withdraw(remaining-1):h.ctx.emit("credentials/record-updated",KEY));
    withdraw(depth);return value;
  });
  const witness=await h.account.resolveInferenceCredential(INFERENCE);
  await flush();
  if(witness!==undefined)expect(()=>witness.assertCurrent()).toThrow();
  expect(h.fetch).not.toHaveBeenCalled();
});
it("profile identity refresh invalidates only its passive snapshot, not the same grant's HTTP lifetime",async()=>{
  const h=await fixture();await h.write();
  const witness=(await h.account.resolveInferenceCredential(INFERENCE))!,cold=(await h.account.getLocalInferenceSnapshot())!;
  h.fetch.mockResolvedValueOnce(Response.json({code:0,data:{biz_code:0,biz_data:{
    id:"observed-user",email:"m***@example.invalid",id_profile:{name:"Inert Account",picture:null},
  }}}));
  await h.account.getProfile(META);
  expect(cold.isCurrent()).toBe(false);expect(witness.signal.aborted).toBe(false);expect(witness.assertCurrent()).toBe(true);
  const warm=(await h.account.getLocalInferenceSnapshot())!;
  expect(warm.userId).toBe("observed-user");expect(warm.isCurrent()).toBe(true);expect(h.fetch).toHaveBeenCalledTimes(1);
});
it("beginning sign-out refuses new and retained native authority before its storage await completes",async()=>{
  const h=await fixture();await h.write();const witness=(await h.account.resolveInferenceCredential(INFERENCE))!;
  const entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.credentials.readRecord.bind(h.ctx.credentials);
  vi.spyOn(h.ctx.credentials,"readRecord").mockImplementationOnce(async key=>{entered.resolve();await release.promise;return original(key);});
  const pending=h.account.signOut(META);await entered.promise;
  expect(witness.signal.aborted).toBe(false);expect(()=>witness.assertCurrent()).toThrow();
  expect(await h.account.resolveInferenceCredential(INFERENCE)).toBeUndefined();
  release.resolve();await pending;expect(witness.signal.aborted).toBe(true);
});
it("disposing the original account invalidates both witnesses without a network request",async()=>{
  const h=await fixture();await h.write();
  const witness=(await h.account.resolveInferenceCredential(INFERENCE))!,snapshot=(await h.account.getLocalInferenceSnapshot())!;
  await h.fiber.dispose();expect(witness.signal.aborted).toBe(true);expect(()=>witness.assertCurrent()).toThrow();
  expect(snapshot.isCurrent()).toBe(false);expect(h.fetch).not.toHaveBeenCalled();
});
async function collect(stream:AsyncIterable<StreamChunk>){const result:StreamChunk[]=[];for await(const chunk of stream)result.push(chunk);return result;}
const finish=(values:StreamChunk[])=>values.find(x=>x.type==="finish") as any;
async function provider(){
  const h=await fixture();await h.write();
  const lifetime=new AbortController(),admission={signal:lifetime.signal,check:()=>true as const};
  h.ctx.provide("nativeLlmAdmission",admission);await h.ctx.plugin(LlmRuntime);
  await h.ctx.plugin(DeepSeekLlmApiExtensionRegistry);await h.ctx.plugin(AccountProvider);
  h.fetch.mockImplementation(async input=>{
    const url=String(input);
    if(url.endsWith("/models"))return Response.json({data:[FLASH]});
    if(url.endsWith("/messages"))return new Response(sse(textEvents));
    throw new Error("Unexpected fixture HTTP destination");
  });
  const request=()=>({provider:"deepseek-account",model:"deepseek-flash",
    messages:[createUserMessage({source:{kind:"user"},content:[{type:"text",text:"fixture question"}]})]});
  return{...h,lifetime,admission,run:()=>collect(h.ctx.llm.stream(request())),
    messages:()=>h.fetch.mock.calls.filter(([url])=>String(url).endsWith("/messages"))};
}
it("the original account provider resolves its listing and sends through the original native runtime",async()=>{
  const h=await provider();expect(finish(await h.run()).reason.kind).toBe("stop");
  expect(h.messages()).toHaveLength(1);
  expect((h.messages()[0][1]!.headers as Record<string,string>)["x-dsh-auth-token"]).toBe("fixture-secret");
  expect(h.fetch.mock.calls.map(([url])=>new URL(String(url)).pathname)).toEqual(["/models","/anthropic/v1/messages"]);
});
it.each(["account","generation"] as const)("withdrawal of %s while extensions prepare remains terminal and performs no Messages write",async kind=>{
  const h=await provider(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const accepted=vi.fn();
  h.ctx.deepseekLlmApiExtensions.register("fixture_native" as never,{prepare:async()=>{entered.resolve();await release.promise;return{value:"inert",accept:accepted};}} as any);
  const pending=h.run();await entered.promise;
  if(kind==="account")await h.write("replacement-secret");else h.lifetime.abort();
  release.resolve();const result=finish(await pending);
  expect(result.reason.kind).toBe("aborted");expect(result.reason.failure.code).toBe("ABORTED");
  expect(h.messages()).toHaveLength(0);expect(accepted).not.toHaveBeenCalled();
});
it("HTTP success settles the captured extension after its original account grant is replaced",async()=>{
  const h=await provider(),accepted=vi.fn();
  h.ctx.deepseekLlmApiExtensions.register("fixture_native" as never,{prepare:()=>({value:"inert",accept:accepted})} as any);
  h.fetch.mockImplementation(async input=>{
    if(String(input).endsWith("/models"))return Response.json({data:[FLASH]});
    await h.write("replacement-secret");return new Response(sse(textEvents));
  });
  await h.run();expect(h.messages()).toHaveLength(1);expect(accepted).toHaveBeenCalledTimes(1);
});
it("a 401 settles with the captured original account even when the account service is replaced after dispatch",async()=>{
  const h=await provider(),oldReject=vi.spyOn(h.account,"rejectToken");let newReject:ReturnType<typeof vi.spyOn>|undefined;
  h.fetch.mockImplementation(async input=>{
    if(String(input).endsWith("/models"))return Response.json({data:[FLASH]});
    await h.fiber.dispose();await h.ctx.plugin(PlatformAccount,{logoutMaxRetries:0});
    newReject=vi.spyOn(h.ctx.deepseekAccount,"rejectToken");
    return Response.json({error:{message:"inert rejected token",type:"authentication_error"}},{status:401});
  });
  const result=finish(await h.run());
  expect(result.reason.failure.code).toBe("ACCOUNT_TOKEN_INVALID");
  expect(oldReject).toHaveBeenCalledExactlyOnceWith("fixture-secret");expect(newReject).not.toHaveBeenCalled();
  expect((await h.ctx.credentials.readRecord(KEY))!.payload).toMatchObject({token:"fixture-secret"});
});
it.each(["missing","async","reentrant"] as const)("native catalog refuses a %s credential witness before HTTP without legacy fallback",async mode=>{
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());
  const lifetime=new AbortController(),admission={signal:lifetime.signal,check:()=>true as const};
  ctx.provide("nativeLlmAdmission",admission);await ctx.plugin(LlmRuntime);
  const legacy=vi.fn().mockResolvedValue("must-not-use"),signal=new AbortController().signal;
  const owner:any={resolveToken:legacy};
  if(mode!=="missing")owner.resolveInferenceCredential=async()=>({token:"inert",signal,assertCurrent:()=>{
    if(mode==="async")return Promise.resolve(true);
    admission.check=()=>true;return true;
  }});
  ctx.provide("deepseekAccount",owner);await ctx.plugin(AccountProvider);
  const fetch=vi.fn();vi.stubGlobal("fetch",fetch);
  await expect(ctx.llm.listModels("deepseek-account")).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  expect(legacy).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();
});
const modelListing=()=>parseModelListing({data:[FLASH]});
function catalogFixture(fresh=false){
  let current=true;
  const controller=new AbortController(),loaded=Promise.withResolvers<any>(),entered=Promise.withResolvers<void>();
  const credential={token:"inert",signal:controller.signal,assertCurrent:()=>{controller.signal.throwIfAborted();if(!current)throw new LlmError("retired","NATIVE_AUTHORITY");return true as const;}};
  const info=vi.fn(),warn=vi.fn(),now=vi.fn(()=>0),load=vi.fn(async()=>{entered.resolve();return loaded.promise;});
  const catalog=new AccountModelCatalog({settings:()=>({url:INFERENCE+"/models",maxAgeMs:1000,timeoutMs:10000}),
    token:async()=>fresh?{...credential}:credential,load,now,info,warn});
  cleanup.push(async()=>catalog.dispose());
  return{catalog,credential,controller,loaded,entered,load,info,warn,now,retire:()=>{current=false;}};
}
it("native catalog preserves one original in-flight load across concurrent views",async()=>{
  const h=catalogFixture(),first=h.catalog.view(),second=h.catalog.view();await h.entered.promise;
  expect(h.load).toHaveBeenCalledTimes(1);h.loaded.resolve(modelListing());
  await expect(first).resolves.toMatchObject({signedIn:true});await expect(second).resolves.toMatchObject({signedIn:true});
  expect(h.info).toHaveBeenCalledTimes(1);expect(h.load.mock.calls[0][3]).toBe(h.credential);
});
it("withdrawn catalog authority cannot publish a late successful listing",async()=>{
  const h=catalogFixture(),pending=h.catalog.view();const rejected=expect(pending).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  await h.entered.promise;h.retire();h.loaded.resolve(modelListing());await rejected;
  expect(h.catalog.current().listing).toBeUndefined();expect(h.info).not.toHaveBeenCalled();expect(h.warn).not.toHaveBeenCalled();
});
it("withdrawn catalog authority cannot publish fallback state or failure diagnostics",async()=>{
  const h=catalogFixture(),pending=h.catalog.view();const rejected=expect(pending).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  await h.entered.promise;h.retire();h.loaded.reject(new Error("inert late failure"));await rejected;
  expect(h.catalog.current().listing).toBeUndefined();expect(h.warn).not.toHaveBeenCalled();
});
it("listing checks retained authority after synchronous header preparation and before fetch",async()=>{
  const h=catalogFixture(),fetch=vi.fn();vi.stubGlobal("fetch",fetch);
  const headers={get "x-dsh-auth-token"(){h.retire();return"inert";}};
  await expect(requestModelListing(INFERENCE+"/models",headers,new AbortController().signal,h.credential))
    .rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  expect(fetch).not.toHaveBeenCalled();
});
it("native catalog cancellation reaches the original shared load",async()=>{
  const h=catalogFixture(),pending=h.catalog.view(),rejected=expect(pending).rejects.toThrow();
  await h.entered.promise;const signal=h.load.mock.calls[0][2] as AbortSignal;
  h.controller.abort();expect(signal.aborted).toBe(true);h.loaded.reject(signal.reason);await rejected;
  expect(h.info).not.toHaveBeenCalled();expect(h.warn).not.toHaveBeenCalled();
});

it("native catalog keeps a valid retained scope across freshly wrapped witnesses for the same grant",async()=>{
  const h=catalogFixture(true),first=h.catalog.view();await h.entered.promise;h.loaded.resolve(modelListing());await first;
  await expect(h.catalog.view()).resolves.toMatchObject({signedIn:true});
  expect(h.load).toHaveBeenCalledTimes(1);
});
it("the same token in a replacement credential lifetime cannot reuse the previous native listing",async()=>{
  const first=new AbortController(),second=new AbortController();let controller=first,loads=0;
  const held=Promise.withResolvers<any>(),entered=Promise.withResolvers<void>();
  const token=async()=>{const captured=controller;return{token:"same-token",signal:captured.signal,assertCurrent:()=>{captured.signal.throwIfAborted();return true as const;}};};
  const catalog=new AccountModelCatalog({settings:()=>({url:INFERENCE+"/models",maxAgeMs:10000,timeoutMs:10000}),
    token,load:async()=>{loads++;if(loads===1)return modelListing();entered.resolve();return held.promise;},
    now:()=>0,info:()=>{},warn:()=>{}});
  cleanup.push(async()=>catalog.dispose());
  await catalog.view();expect(catalog.current().listing).toBeDefined();
  first.abort();expect(catalog.current()).toEqual({signedIn:false,listing:undefined});controller=second;
  const pending=catalog.view();await entered.promise;expect(loads).toBe(2);expect(catalog.current().listing).toBeUndefined();
  held.resolve(modelListing());await expect(pending).resolves.toMatchObject({signedIn:true,listing:modelListing()});
});
it("catalog witness reentry cannot publish after disposal",async()=>{
  const h=catalogFixture(),pending=h.catalog.view(),rejected=expect(pending).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  await h.entered.promise;
  vi.spyOn(h.credential,"assertCurrent").mockImplementation(()=>{h.catalog.dispose();return true;});
  h.loaded.resolve(modelListing());await rejected;
  expect(h.catalog.current()).toEqual({signedIn:false,listing:undefined});expect(h.info).not.toHaveBeenCalled();
});
it.each([false,true])("catalog clock callback disposal cannot publish success=%s or subsequent state",async success=>{
  const h=catalogFixture(),pending=h.catalog.view(),rejected=expect(pending).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  await h.entered.promise;h.now.mockImplementation(()=>{h.catalog.dispose();return 0;});
  if(success)h.loaded.resolve(modelListing());else h.loaded.reject(new Error("inert failure"));
  await rejected;expect(h.catalog.current().listing).toBeUndefined();
  expect(h.info).not.toHaveBeenCalled();expect(h.warn).not.toHaveBeenCalled();
});
it("native withdrawal before the deferred listing load makes no HTTP call",async()=>{
  const h=catalogFixture();let checks=0;const original=h.credential.assertCurrent;
  vi.spyOn(h.credential,"assertCurrent").mockImplementation(()=>{
    const result=original();if(++checks===2)queueMicrotask(()=>h.retire());return result;
  });
  await expect(h.catalog.view()).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});
  expect(h.load).not.toHaveBeenCalled();
});

it.each([false,true])("late previous-lifetime success=%s cannot replace the same-token successor's in-flight catalog",async success=>{
  const first=new AbortController(),second=new AbortController();let controller=first;
  const loads:any[]=[];
  const catalog=new AccountModelCatalog({settings:()=>({url:INFERENCE+"/models",maxAgeMs:10000,timeoutMs:10000}),
    token:async()=>{const captured=controller;return{token:"same-token",signal:captured.signal,assertCurrent:()=>{captured.signal.throwIfAborted();return true as const;}};},
    load:async()=>{const result=Promise.withResolvers<any>();loads.push(result);return result.promise;},
    now:()=>0,info:()=>{},warn:()=>{}});
  cleanup.push(async()=>catalog.dispose());
  const old=catalog.view(),oldRejected=expect(old).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});await flush();
  first.abort();controller=second;const next=catalog.view();await flush();expect(loads).toHaveLength(2);
  if(success)loads[0].resolve(modelListing());else loads[0].reject(new Error("retired owner failure"));
  await oldRejected;expect(catalog.current().listing).toBeUndefined();
  const same=catalog.view();await flush();expect(loads).toHaveLength(2);
  loads[1].resolve(modelListing());await next;await same;expect(catalog.current().listing).toEqual(modelListing());
});
it("a native TTL clock callback cannot start a new load after disposing the catalog",async()=>{
  const h=catalogFixture(),first=h.catalog.view();await h.entered.promise;h.loaded.resolve(modelListing());await first;
  h.now.mockImplementation(()=>{h.catalog.dispose();return 10000;});
  await expect(h.catalog.view()).rejects.toMatchObject({code:"NATIVE_AUTHORITY"});expect(h.load).toHaveBeenCalledTimes(1);
});
