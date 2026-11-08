import recovery from "./conversations/new-conversation/fixtures/fresh-conversation-recovery-owner.json";
import {expect,it,vi} from "vitest";
import {bindMissionHost,createNativeClient} from "./host";
import fixture from "./conversations/new-conversation/fixtures/fresh-conversation-owner.json";
import {decodeFreshConversationResult} from "./conversations/new-conversation/fresh-conversation";

// Only native invoke/listen is inert. The real client, Host, closed request
// validator and auth-generation cancellation run against source-issued DATA.
async function setup(held=false){
 const events=new Map<string,(event:{payload:unknown})=>void>();
 let finish!:(value:unknown)=>void;
 const pending=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
  if(command==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:false};
  if(command==="executive_auth_status")return {generation:1,available:true};
  if(command!=="executive_fresh_conversation")throw Error("Unlisted inert native edge");
  if(held)return pending;
  if(args?.operation==="consume_status")return structuredClone(recovery.consume_status);
  if(args?.operation==="turn_preview")return structuredClone(recovery.turn_preview);
  return args?.operation==="status" ? {...fixture.create,operation:"status"} : fixture[args?.operation as "preview"|"create"|"read"];
 });
 const raw=await createNativeClient(invoke as never,async(name,listener)=>{events.set(name,listener);return()=>{};});
 let acquisition=true;const state=raw.getState();raw.getState=()=>({...state,acquisition});
 const host=bindMissionHost(raw);
 return {raw,host,invoke,events,finish,revokeWorkspace:()=>{acquisition=false;}};
}
it("carries genuine original preview/create/read DATA through fixed native and Host methods without constructor effects",async()=>{
 const e=await setup(),signal=new AbortController().signal;
 expect(e.invoke.mock.calls.filter(([c])=>c==="executive_fresh_conversation")).toHaveLength(0);
 for(const operation of ["preview","create","read"] as const){
  const request=operation==="create"?fixture.create_request:operation==="preview"?fixture.request:
   {work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key};
  const raw=await e.host.freshConversation!.request(operation,request,signal);
  expect(decodeFreshConversationResult(raw,operation,fixture.request)?.ok).toBe(true);
  expect(e.invoke.mock.calls.at(-1)).toEqual(["executive_fresh_conversation",{operation,arguments:request}]);
 }
});
it("rejects extra fields and accessors before invoking a native command",async()=>{
 const e=await setup(),getter=vi.fn(()=>fixture.request.message),signal=new AbortController().signal;
 for(const input of [{...fixture.request,extra:true},Object.defineProperty({...fixture.request},"message",{get:getter}),
  {...fixture.request,operation_key:"../foreign"}])
  await expect(e.host.freshConversation!.request("preview",input,signal)).rejects.toThrow("FRESH_CONVERSATION_REQUEST_INVALID");
 expect(getter).not.toHaveBeenCalled();expect(e.invoke.mock.calls.filter(([c])=>c==="executive_fresh_conversation")).toHaveLength(0);
});
it("keeps original Executive recovery independent while live Workspace loss refuses a fresh preview",async()=>{
 const e=await setup(),signal=new AbortController().signal;e.revokeWorkspace();
 await expect(e.host.freshConversation!.request("preview",fixture.request,signal)).rejects.toThrow("FRESH_CONVERSATION_UNAVAILABLE");
 await e.host.freshConversation!.request("read",{work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key},signal);
 expect(e.invoke.mock.calls.filter(([c])=>c==="executive_fresh_conversation")).toHaveLength(1);
});
it("withholds a late original result after actual Executive epoch loss with no retry",async()=>{
 const e=await setup(true),signal=new AbortController().signal;
 const pending=e.host.freshConversation!.request("read",{work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key},signal);
 const rejected=expect(pending).rejects.toThrow();
 e.events.get("mastermind-executive-auth-state")!({payload:{generation:2,available:false}});
 e.finish(fixture.read);await rejected;
 expect(e.invoke.mock.calls.filter(([c])=>c==="executive_fresh_conversation")).toHaveLength(1);
});

it("keeps lost-Keep status Executive-only while new turn preflight requires live Workspace",async()=>{
 const e=await setup(),signal=new AbortController().signal;
 const {preview_digest,...request}=recovery.turn_request;
 await e.host.freshConversation!.request("turn_preview",request,signal);
 expect(e.invoke.mock.calls.at(-1)).toEqual(["executive_fresh_conversation",{operation:"turn_preview",arguments:request}]);
 e.revokeWorkspace();
 await expect(e.host.freshConversation!.request("turn_preview",request,signal)).rejects.toThrow("FRESH_CONVERSATION_UNAVAILABLE");
 await expect(e.host.freshConversation!.request("consume_status",recovery.consume_request,signal)).resolves.toEqual(recovery.consume_status);
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_fresh_conversation")).toHaveLength(2);
});

it("carries native-v2 through the same host and native command, preserving Workspace and auth withdrawal",async()=>{
 const e=await setup(),signal=new AbortController().signal;
 const selected={work_ref:fixture.request.work_ref,operation_key:"mmos-native-create-"+"a".repeat(40)};
 const stop={...selected,stop_key:"original-stop",turn_id:"original-native-turn",binding_digest:"b".repeat(64)};
 const preview={...selected,message:"x".repeat(131072)};
 await e.host.freshConversation!.request("preview",preview,signal,"native-v2");
 expect(e.invoke.mock.calls.at(-1)).toEqual(["executive_fresh_conversation",{operation:"preview",arguments:preview,contract:"native-v2"}]);
 await e.host.freshConversation!.request("stop",stop,signal,"native-v2");
 e.revokeWorkspace();
 await expect(e.host.freshConversation!.request("stop",stop,signal,"native-v2")).rejects.toThrow();
 await e.host.freshConversation!.request("stop_status",{...selected,stop_key:stop.stop_key},signal,"native-v2");
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_fresh_conversation")).toHaveLength(3);
 const held=await setup(true);
 const pending=held.host.freshConversation!.request("turn_status",{...selected,turn_key:"original-turn"},signal,"native-v2");
 const rejected=expect(pending).rejects.toThrow();
 held.events.get("mastermind-executive-auth-state")!({payload:{generation:2,available:false}});
 held.finish({unknown:true});await rejected;
 expect(held.invoke.mock.calls.filter(([name])=>name==="executive_fresh_conversation")).toHaveLength(1);
});
