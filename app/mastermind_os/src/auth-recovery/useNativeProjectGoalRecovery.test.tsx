// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { createNativeClient, bindMissionHost } from "../host";
import { useProjectJourneyState } from "../projects/useProjectJourneyState";
import { useNativeProjectGoalRecovery } from "./useNativeProjectGoalRecovery";
import { NativeDraftRecoveryNotice } from "./NativeDraftRecoveryNotice";
import { render, screen } from "@testing-library/react";
import { projectGoalDraftScope } from "./project-goal-scope";
import { createNativeDraftRecoveryOwner } from "./native-draft-owner";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { IDBFactory } from "fake-indexeddb";
import nativeSequence from "./fixtures/native-draft-owner-sequence.json";
const signed = {status:"signed_in",reason:null,acquisition:true,content:false};
// Positive sequence is actual6324 native Inner/Token + real serde output,
// using the signed READ-owner fixture. Altered frames below are negatives.
const metadata = (phase="QUALIFIED", cause="OWNER_QUALIFIED", extra={}) => ({...nativeSequence.qualified,phase,cause,principal_scope:phase==="QUALIFIED"?nativeSequence.qualified.principal_scope:null,valid_until_ms:phase==="QUALIFIED"?nativeSequence.qualified.valid_until_ms:null,...extra});
afterEach(()=>{ cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); });
async function setup() {
  vi.spyOn(Date,"now").mockReturnValue(nativeSequence.now_ms);
  history.replaceState(null,"","/os/?new_project=1");
  let frame:unknown=metadata(), status:unknown=signed, revision=1;
  const listeners = new Map<string,(value:{payload:unknown})=>void>();
  const invoke=vi.fn(async (command:string) => command==="read_native_draft_continuity"?frame:
    command==="executive_auth_status"?{generation:0,available:false}:status);
  const raw=await createNativeClient(invoke as never,async (event,handler)=>{listeners.set(event,handler);return()=>{};});
  const host=bindMissionHost(raw);window.MastermindMissionHost=host;
  const view=renderHook(()=>{
    const journey=useProjectJourneyState({host,authRevision:revision,currentAuthRevision:()=>revision});
    const recovery=useNativeProjectGoalRecovery({native:true,owner:host.nativeDraftRecovery,journey,authGeneration:revision});
    return {journey,recovery};
  });
  const notify=async (value:unknown, continuity:unknown)=>{
    status=value;frame=continuity;
    act(()=>{listeners.get("mastermind-auth-state")!({payload:value});view.result.current.recovery.onAuthChange((value as typeof signed).reason==="USER_SIGNED_OUT");revision++;view.rerender();});
  };
  return {...view,host,raw,invoke,notify,set:(value:unknown)=>frame=value};
}
it("actual native host facet and incumbent draft slot quarantine then explicitly restore exact original text",async()=>{
  const h=await setup();
  await act(async()=>h.result.current.recovery.beforeEdit());
  act(()=>h.result.current.journey.onGoalChange("Private goal\n  preserve whitespace\n"));
  await h.notify(nativeSequence.expired_auth,nativeSequence.expired);
  expect(h.result.current.journey.goal).toBe("");expect(h.result.current.recovery.quarantine).toBe(true);
  expect(h.result.current.journey.returnToRetainedGoal()).toBe(false);
  await h.notify({status:"signing_in",reason:null,acquisition:false,content:false},metadata("REAUTHENTICATING","REAUTHENTICATION"));
  await h.notify(signed,metadata());
  expect(h.result.current.journey.goal).toBe("");expect(h.result.current.recovery.quarantine).toBe(true);
  await act(async()=>expect(await h.result.current.recovery.recover()).toBe(true));
  expect(h.result.current.journey.goal).toBe("Private goal\n  preserve whitespace\n");expect(h.result.current.recovery.quarantine).toBe(false);
  expect(h.invoke.mock.calls.filter(([c])=>c==="read_native_draft_continuity")).toHaveLength(2);
  expect(h.invoke.mock.calls.every(([c])=>["auth_status","executive_auth_status","read_native_draft_continuity"].includes(c))).toBe(true);
});
it.each(["logout","different","unproven"])("%s cannot expose or restore an expired private draft",async kind=>{
  const h=await setup();await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("Hidden original"));
  await h.notify(nativeSequence.expired_auth,nativeSequence.expired);
  await h.notify(kind==="logout"?{status:"signed_out",reason:"USER_SIGNED_OUT",acquisition:false,content:false}:signed,
    kind==="different"?nativeSequence.different:metadata("UNQUALIFIED","OWNER_UNQUALIFIED"));
  await act(async()=>expect(await h.result.current.recovery.recover()).toBe(false));
  expect(h.result.current.journey.goal).toBe("");
  if(kind!=="unproven")expect(h.result.current.journey.retainedGoal).toBeNull();
  else expect(h.result.current.recovery.quarantine).toBe(true);
});
it("explicit logout clears the facet immediately even if native logout fails",async()=>{
  const h=await setup();await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("private"));
  h.invoke.mockImplementationOnce(async()=>{throw new Error("KEYCHAIN_UNAVAILABLE");});
  const unsubscribe=h.host.auth!.subscribe(()=>h.result.current.recovery.onAuthChange());
  await act(async()=>{await expect(h.raw.signOut()).rejects.toThrow("KEYCHAIN_UNAVAILABLE");});
  expect(h.result.current.journey.goal).toBe("");expect(h.result.current.journey.retainedGoal).toBeNull();unsubscribe();
});
it("unbound previous identity clears on withdrawal without touching the original pointer",async()=>{
  const h=await setup();h.set(metadata("UNQUALIFIED","OWNER_UNQUALIFIED"));await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("unbound private"));
  const href=location.href;const original={operationKey:"mmos-launch-"+"1".repeat(40),kind:"launch" as const,targetKey:"WS:Original.Work-1"};
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  await store.reserve("d".repeat(64),original);
  await h.notify({status:"signed_out",reason:null,acquisition:false,content:false},metadata("UNQUALIFIED","OWNER_UNQUALIFIED"));
  expect(h.result.current.recovery.quarantine).toBe(false);expect(h.result.current.recovery.canRecover).toBe(false);
  expect(h.result.current.journey.retainedGoal).toBeNull();
  act(()=>h.result.current.recovery.discard());expect(h.result.current.journey.retainedGoal).toBeNull();expect(location.href).toBe(href);expect(await createIndexedDbPendingPointerStore(factory).read("d".repeat(64))).toEqual(original);
});
it("public owner-shaped callbacks and a foreign original scope cannot authorize incumbent draft restore",async()=>{
  const h=await setup();await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("original"));
  await h.notify(nativeSequence.expired_auth,nativeSequence.expired);await h.notify(signed,metadata());
  const forged={scopeKey:"project-goal.v1:blank",principalScope:"b".repeat(64),ownerInstance:"a".repeat(32),privacyEpoch:1};
  expect(h.result.current.journey.returnToNativeRetainedGoal(forged,{canReturn:()=>true} as never)).toBe(false);
  const foreign=createNativeDraftRecoveryOwner({inspect:async()=>metadata(),sourceGeneration:()=>0,signedIn:()=>true});const origin=await foreign.capture("foreign");expect(await foreign.check(origin!)).toBe("RETURNABLE");
  expect(h.result.current.journey.returnToNativeRetainedGoal(origin!,foreign)).toBe(false);expect(h.result.current.journey.goal).toBe("");
});
it("closed original goal scope does not acquire authority from malformed selection",()=>{
  expect(projectGoalDraftScope(null)).toBe("project-goal.v1:blank");
  expect(projectGoalDraftScope({createRequestId:"forged",workRef:null,planningOperationKey:null,jobId:null})).toBeNull();
  expect(projectGoalDraftScope({get createRequestId():string{throw Error("must not read");},workRef:null,planningOperationKey:null,jobId:null})).toBeNull();
});
it("unauthenticated notice renders generic bilingual recovery cue and no private body",()=>{
  const recover=vi.fn(),discard=vi.fn();const h=render(<NativeDraftRecoveryNotice locale="en" checking={false} canRecover={false} onRecover={recover} onDiscard={discard}/>);
  expect(screen.getByText("Your unsent work is kept in this window. Sign in to recover it.")).toBeTruthy();expect(screen.queryByText("Hidden original")).toBeNull();
  expect((screen.getByRole("button",{name:"Recover unsent work"}) as HTMLButtonElement).disabled).toBe(true);
  h.rerender(<NativeDraftRecoveryNotice locale="zh-CN" checking={false} canRecover={false} onRecover={recover} onDiscard={discard}/>);
  expect(screen.getByText("未发送的内容保留在此窗口中。登录后可恢复。")).toBeTruthy();
});

it("explicit selection gesture rebinds metadata to actual incumbent goal scope before expiry",async()=>{
  const h=await setup();await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("same original unsent goal"));
  const selected={createRequestId:"mmos-project-create-"+"e".repeat(40),workRef:null,planningOperationKey:null,jobId:null};
  await act(async()=>{h.result.current.journey.onSelection(selected);await h.result.current.recovery.beforeEdit();});
  await h.notify(nativeSequence.expired_auth,nativeSequence.expired);await h.notify(signed,nativeSequence.same);
  await act(async()=>expect(await h.result.current.recovery.recover()).toBe(true));
  expect(h.result.current.journey.goal).toBe("same original unsent goal");expect(h.result.current.journey.selection).toEqual(selected);
  expect(h.invoke.mock.calls.filter(([c])=>c==="read_native_draft_continuity")).toHaveLength(3);
});

it("a genuinely issued different native Host facet cannot restore this Host's same-scope retained text",async()=>{
  const h=await setup();await act(async()=>h.result.current.recovery.beforeEdit());act(()=>h.result.current.journey.onGoalChange("private exact Host"));
  await h.notify(nativeSequence.expired_auth,nativeSequence.expired);await h.notify(signed,nativeSequence.same);
  const otherRaw=await createNativeClient((async(command:string)=>command==="read_native_draft_continuity"?nativeSequence.same:command==="executive_auth_status"?{generation:0,available:false}:signed) as never,async()=>()=>{});
  const otherHost=bindMissionHost(otherRaw);expect(otherHost.nativeDraftRecovery).not.toBe(h.host.nativeDraftRecovery);
  const origin=await otherHost.nativeDraftRecovery!.capture("project-goal.v1:blank");expect(origin).not.toBeNull();
  expect(await otherHost.nativeDraftRecovery!.check(origin!)).toBe("RETURNABLE");
  expect(h.result.current.journey.returnToNativeRetainedGoal(origin!,otherHost.nativeDraftRecovery!)).toBe(false);
  expect(h.result.current.journey.goal).toBe("");expect(h.result.current.recovery.quarantine).toBe(true);
  await act(async()=>expect(await h.result.current.recovery.recover()).toBe(true));
  expect(h.result.current.journey.goal).toBe("private exact Host");
});

it.each(["BOUND","UNBOUND"])("withdraws %s private text before an unavailable replacement native facet can enter UNBOUND fallback",async mode=>{
  const h=await setup();if(mode==="UNBOUND")h.set(nativeSequence.expired);
  await act(async()=>h.result.current.recovery.beforeEdit());
  act(()=>h.result.current.journey.onGoalChange("Private original facet text"));
  const staleFocus=h.result.current.recovery.beforeEdit;
  const otherRaw=await createNativeClient((async(command:string)=>command==="read_native_draft_continuity"?nativeSequence.expired:command==="executive_auth_status"?{generation:0,available:false}:signed) as never,async()=>()=>{});
  const otherHost=bindMissionHost(otherRaw);expect(otherHost.nativeDraftRecovery).not.toBe(h.host.nativeDraftRecovery);
  // Actual different issuer, same Host object and native/auth epoch. This is
  // adversarial mutation of the readonly surface, not a forged owner DTO.
  Reflect.set(h.host,"nativeDraftRecovery",otherHost.nativeDraftRecovery);h.rerender();
  expect(h.result.current.recovery.quarantine).toBe(true);
  expect(h.result.current.recovery.canEdit).toBe(false);
  await act(async()=>staleFocus());
  expect(h.result.current.journey.goal).toBe("");
  expect(h.result.current.journey.retainedGoal).toBeNull();
  expect(h.result.current.recovery.canRecover).toBe(false);
});
