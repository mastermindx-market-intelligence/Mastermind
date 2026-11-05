// @vitest-environment jsdom
// Inert Host/E owner only. This tests ephemeral ownership, no native continuity.
import {act,cleanup,renderHook} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import type {MissionHost} from "../../host";
import type {OwnerContext} from "../../orchestration/operation-controller";
import type {FreshConversationDraftStateProps} from "./useFreshConversationDraftState";
import {useFreshConversationTurnDraftState} from "./useFreshConversationTurnDraftState";
import {decodeFreshConversationWindow} from "../fresh-conversation-reference";
import fixture from "./fixtures/fresh-conversation-recovery-owner.json";
afterEach(()=>{cleanup();delete window.MastermindMissionHost;});
function setup(){
  let epoch=1,generation=4,owner:OwnerContext|null={principalScope:"unit-E-author",generation:"E-1"};
  let workspace:"signed_in"|"signed_out"="signed_in";
  const request=vi.fn(async()=>{throw Error("No transport in draft ownership tests");});
  const host:NonNullable<FreshConversationDraftStateProps["host"]>={invalidationGeneration:()=>generation,
    auth:{getState:()=>({status:workspace,reason:null,acquisition:workspace==="signed_in",content:workspace==="signed_in"}),signIn:async()=>{},signOut:async()=>{},subscribe:()=>()=>{}},freshConversation:{request}};
  window.MastermindMissionHost=host as MissionHost;
  const props:FreshConversationDraftStateProps={host,authRevision:epoch,currentAuthRevision:()=>epoch,getExecutiveOwner:()=>owner};
  return{props,host,request,setEpoch:(n:number)=>{epoch=n;},setGeneration:(n:number)=>{generation=n;},setOwner:(n:OwnerContext|null)=>{owner=n;},setWorkspace:(n:"signed_in"|"signed_out")=>{workspace=n;}};
}
const key={work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key};
const ref={work_ref:fixture.request.work_ref,reference:decodeFreshConversationWindow(fixture.initial_read,fixture.initial_read.reference).reference};
it("preserves exact current-original text across renders/Back without source or URL effects",()=>{
  const h=setup(),{result,rerender}=renderHook(p=>useFreshConversationTurnDraftState(p),{initialProps:h.props});
  const url=window.location.href;act(()=>{expect(result.current.selectOriginal(key)).toBe(true);});
  act(()=>result.current.onMessageChange("  Follow up\n🙂 中文  "));
  const probe=result.current.hasUnsentDraft,invalidator=result.current.invalidateAuth;
  rerender(h.props);act(()=>{expect(result.current.selectOriginal(key)).toBe(true);});
  expect(result.current.message).toBe("  Follow up\n🙂 中文  ");expect(result.current.hasUnsentDraft).toBe(probe);
  expect(result.current.invalidateAuth).toBe(invalidator);expect(result.current.hasUnsentDraft()).toBe(true);
  expect(result.current.selection).toEqual(key);expect(h.request).not.toHaveBeenCalled();expect(window.location.href).toBe(url);
});
it("keeps reference selectors exact, detached, and free of a fabricated legacy key",()=>{
  const h=setup(),{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
  const supplied={work_ref:ref.work_ref,reference:{...ref.reference}};act(()=>{expect(result.current.selectOriginal(supplied)).toBe(true);});
  supplied.reference.root_event_id++;
  expect(result.current.selection).toEqual(ref);expect(result.current.selection).not.toHaveProperty("operation_key");
  act(()=>result.current.onMessageChange("Reference-scoped unsent text"));expect(result.current.message).toBe("Reference-scoped unsent text");
});
it("does not transplant unsent text into another original; stale callbacks cannot write a newly selected slot",()=>{
  const h=setup(),{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
  act(()=>result.current.selectOriginal(key));act(()=>result.current.onMessageChange("Original A"));
  const stale=result.current.onMessageChange;
  act(()=>{expect(result.current.selectOriginal(ref)).toBe(false);});expect(result.current.message).toBe("Original A");
  act(()=>result.current.discard());act(()=>{expect(result.current.selectOriginal(ref)).toBe(true);});
  act(()=>stale("Must not move"));expect(result.current.message).toBe("");expect(result.current.selection).toEqual(ref);
});
it.each(["epoch","generation","owner","method","host"] as const)("masks and refuses late writes on no-render %s drift",kind=>{
  const h=setup(),{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
  act(()=>result.current.selectOriginal(key));act(()=>result.current.onMessageChange("Private old original"));
  const api=result.current,write=api.onMessageChange;
  if(kind==="epoch")h.setEpoch(2);if(kind==="generation")h.setGeneration(5);if(kind==="owner")h.setOwner({principalScope:"other",generation:"E-2"});
  if(kind==="method")Object.assign(h.host.freshConversation!,{request:vi.fn(async()=>{throw Error("new method");})});
  if(kind==="host")window.MastermindMissionHost={} as MissionHost;
  expect(api.message).toBe("");expect(api.selection).toBeNull();expect(api.draftOwner).toBeNull();expect(api.hasUnsentDraft()).toBe(false);
  act(()=>write("Must refuse"));expect(result.current.message).toBe("");expect(h.request).not.toHaveBeenCalled();
});
it("uses independently qualified Executive ownership while Workspace is signed out, without granting an action",()=>{
  const h=setup();h.setWorkspace("signed_out");const{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
  act(()=>{expect(result.current.selectOriginal(ref)).toBe(true);});act(()=>result.current.onMessageChange("Still owned by E"));
  expect(result.current.message).toBe("Still owned by E");expect(result.current.draftOwner?.principalScope).toBe("unit-E-author");expect(h.request).not.toHaveBeenCalled();
});
it("quarantines preserved text without nominal/automatic restore; explicit withdrawal clears",()=>{
  const h=setup(),{result,rerender}=renderHook(p=>useFreshConversationTurnDraftState(p),{initialProps:h.props});
  act(()=>result.current.selectOriginal(key));act(()=>result.current.onMessageChange("Hold without exposing"));
  act(()=>result.current.invalidateAuth(true));expect(result.current.message).toBe("");expect(result.current.draftOwner).toBeNull();
  rerender(h.props);act(()=>{expect(result.current.selectOriginal(key)).toBe(false);});expect(result.current.message).toBe("");
  act(()=>result.current.invalidateAuth(false));act(()=>{expect(result.current.selectOriginal(key)).toBe(true);});expect(result.current.message).toBe("");
});
it("settles only its captured unchanged message from the exact recorded original turn_read, then permits another original",()=>{
 const h=setup(),{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
 act(()=>result.current.selectOriginal(ref));act(()=>result.current.onMessageChange(fixture.turn_request.message));
 let token:object|null=null;act(()=>{token=result.current.captureSubmission(fixture.turn_request.turn_key,fixture.turn_request.message);});
 expect(token).not.toBeNull();expect(result.current.hasUnsentDraft()).toBe(true);
 act(()=>{expect(result.current.settleSubmission(token!,fixture.lost_consume)).toBe(false);
  expect(result.current.settleSubmission(token!,{...fixture.turn_read,data:{...fixture.turn_read.data,turn_key:'mmos-conversation-turn-'+'f'.repeat(40)}})).toBe(false);});expect(result.current.message).toBe(fixture.turn_request.message);
 act(()=>{expect(result.current.settleSubmission(token!,fixture.turn_read)).toBe(true);});
 expect(result.current.message).toBe('');expect(result.current.hasUnsentDraft()).toBe(false);expect(result.current.submittedTurnKey).toBeNull();
 act(()=>{expect(result.current.selectOriginal(key)).toBe(true);});expect(result.current.selection).toEqual(key);
});
it("never settles newer text, another key, or a same-text edit made after capture",()=>{
 const h=setup(),{result}=renderHook(()=>useFreshConversationTurnDraftState(h.props));
 act(()=>result.current.selectOriginal(ref));act(()=>result.current.onMessageChange(fixture.turn_request.message));
 let token:object|null=null;act(()=>{token=result.current.captureSubmission(fixture.turn_request.turn_key,fixture.turn_request.message);});
 expect(result.current.submissionFor('mmos-conversation-turn-'+'f'.repeat(40))).toBeNull();
 act(()=>result.current.onMessageChange('Newer unsent edit'));act(()=>{expect(result.current.settleSubmission(token!,fixture.turn_read)).toBe(false);});
 expect(result.current.message).toBe('Newer unsent edit');
 act(()=>result.current.onMessageChange(fixture.turn_request.message));act(()=>{expect(result.current.settleSubmission(token!,fixture.turn_read)).toBe(false);});
 expect(result.current.message).toBe(fixture.turn_request.message);expect(h.request).not.toHaveBeenCalled();
});
