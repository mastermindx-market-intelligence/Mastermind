import { describe, expect, it, vi } from "vitest";
import { createNativeExecutiveTransport } from "./native-executive-transport";
import { decodeSessionContext } from "./orchestration/executive-session-command-port";
import { createOsExecutiveSessionHost } from "./orchestration/os-executive-session-host";
import type { PendingPointerStore } from "./orchestration/operation-controller";
const deferred = () => { let resolve!: (x: unknown) => void; let reject!: (x: unknown) => void;
  const promise = new Promise<unknown>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
async function fixture() {
  let notify = (_raw: unknown) => {};
  const invoke = vi.fn(async (command: string, _args?: Record<string, unknown>): Promise<unknown> =>
    command === "executive_auth_status" ? { generation: 3, available: true } : { ok: true });
  const created = await createNativeExecutiveTransport(invoke as never, async (event, callback) => {
    expect(event).toBe("mastermind-executive-auth-state"); notify = (raw) => callback({ payload: raw }); return () => {};
  });
  await created.ready;
  return { ...created, invoke, notify: (raw: unknown) => notify(raw) };
}
describe("native fixed Executive bridge", () => {
  it("maps only fixed commands/arguments without passing a bearer or resource", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    await f.transport.context(signal);
    await f.transport.submit({ goal: "fixture" }, signal);
    await f.transport.status({ intent_id: "auto-original" }, signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"], ["executive_context", undefined],
      ["executive_submit", { arguments: { goal: "fixture" } }],
      ["executive_status", { intentId: "auto-original" }],
    ]);
  });
  it.each(["context", "submit", "status"] as const)("sign-out settles a stalled %s locally and discards its late reply without retry", async (method) => {
    const f = await fixture(), late = deferred(), signal = new AbortController().signal;
    f.invoke.mockReturnValueOnce(late.promise);
    const pending = method === "context" ? f.transport.context(signal) : method === "submit"
      ? f.transport.submit({ operation_key: "original" }, signal) : f.transport.status({ intent_id: "auto-original" }, signal);
    const held = expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.invalidate(); await held; late.resolve({ ok: true, foreign: true }); await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
    expect(f.transport.available()).toBe(false);
    f.notify({ generation: 3, available: true }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 4, available: true }); expect(f.transport.available()).toBe(true);
  });
  it("rejects malformed/regressing status, propagates private generations, and never exposes token fields", async () => {
    const f = await fixture(), first = f.transport.authGeneration();
    f.notify({ generation: 4, available: true });
    expect(f.transport.authGeneration()).toBeGreaterThan(first);
    f.notify({ generation: 3, available: false }); expect(f.transport.available()).toBe(true);
    f.notify({ generation: 4, available: true, token: "private" }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 4, available: true }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 5, available: true }); expect(f.transport.available()).toBe(true);
  });
  it("maps fixed historical READ and the distinct closed native session SEND", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-1" };
    await f.sessionTransport.context(selection, signal);
    await f.sessionTransport.reply({ operation_key: "session-continue-"+"a".repeat(64) }, signal);
    await f.sessionTransport.references!({
      work_ref: selection.workRef, root_job_id: selection.rootJobId, cursor: "YWJjZA==",
    }, signal);
    await f.sessionTransport.send({
      target_ref: "fabric_attempt:"+"b".repeat(64),
      operation_key: "session-continue-"+"a".repeat(64),
      instruction: "Explicit native continuation", stop_condition: "Return once",
    },signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"],
      ["executive_session_context", {selection:{work_ref:"WS:ALPHA",root_job_id:"JOB-1"}}],
      ["executive_session_reply",{operationKey:"session-continue-"+"a".repeat(64)}],
      ["executive_session_references",{selection:{work_ref:"WS:ALPHA",root_job_id:"JOB-1"},
        pageSize:16,cursor:"YWJjZA=="}],
      ["executive_session_send",{arguments:{target_ref:"fabric_attempt:"+"b".repeat(64),operation_key:"session-continue-"+"a".repeat(64),instruction:"Explicit native continuation",stop_condition:"Return once"}}],
    ]);
    expect(f.invoke.mock.calls.map(([cmd])=>cmd)).not.toContain("executive_submit");
    expect(f.invoke.mock.calls.filter(([cmd])=>cmd==="executive_session_send")).toHaveLength(1);
  });
  it("rejects malformed native historical READ inputs before invoking any command", async () => {
    const f=await fixture(), signal=new AbortController().signal;
    await expect(f.sessionTransport.context({workRef:"WS:BAD?",rootJobId:"JOB-1"},signal))
      .rejects.toThrow("SESSION_SELECTION_INVALID");
    await expect(f.sessionTransport.reply({operation_key:"session-continue-"+"A".repeat(64)},signal))
      .rejects.toThrow("SESSION_OPERATION_INVALID");
    await expect(f.sessionTransport.references!({
      work_ref:"WS:ALPHA",root_job_id:"JOB-1",cursor:"bad/cursor",
    },signal)).rejects.toThrow("SESSION_REFERENCES_INVALID");
    await expect(f.sessionTransport.references!({
      work_ref:"WS:ALPHA",root_job_id:"JOB-1",page_size:33,
    },signal)).rejects.toThrow("SESSION_REFERENCES_INVALID");
    expect(f.invoke.mock.calls.map(([command])=>command)).toEqual(["executive_auth_status"]);
  });
  it("preserves a validated backend capability without inventing one or changing its original owner",async()=>{
    const f=await fixture(),signal=new AbortController().signal;
    const selection={workRef:"WS:ALPHA",rootJobId:"JOB-1"};
    const raw={schema:"mastermind.os.executive.session_result.v1",
      operation:"context",ok:true,effect:"NONE",operation_key:null,error:null,
      data:{schema:"mastermind.os.executive.session_context.v1",
        principal_scope:"c".repeat(64),verified_expiry:2000000000,
        selection:{work_ref:selection.workRef,root_job_id:selection.rootJobId},
        selection_state:"RESOLVED",target:{
          target_ref:"fabric_attempt:"+"a".repeat(64),
          generation:"a".repeat(24),addressable:true,kind:"fabric_attempt",
          continuation_operation_key:"session-continue-"+"b".repeat(64),
          work_ref:selection.workRef,root_job_id:selection.rootJobId,
        },capabilities:{send:true,reply_read:true,stop:false},
      }};
    f.invoke.mockResolvedValueOnce(raw);
    const output=await f.sessionTransport.context(selection,signal);
    expect(decodeSessionContext(output,selection)?.capabilities).toEqual({
      send:true,reply_read:true,stop:false,
    });
    expect((output as typeof raw).data.principal_scope).toBe(raw.data.principal_scope);
    expect(raw.data.capabilities.send).toBe(true); // no server payload mutation
    expect(f.invoke.mock.calls.map(([cmd])=>cmd)).toEqual([
      "executive_auth_status","executive_session_context",
    ]);
  });
  it("mounts native historical READ under the real Session host with B pending and no SEND",async()=>{
    const f=await fixture();
    const selection={workRef:"WS:ALPHA",rootJobId:"JOB-1"};
    const bPointer={operationKey:"session-continue-"+"d".repeat(64),
      kind:"message" as const,targetKey:"fabric_attempt:"+"a".repeat(64)};
    const store:PendingPointerStore={
      read:vi.fn(async()=>bPointer),reserve:vi.fn(async()=>({reserved:false,pointer:bPointer})),
      clearIfEqual:vi.fn(async()=>false),
    };
    const context={
      schema:"mastermind.os.executive.session_result.v1",operation:"context",
      ok:true,effect:"NONE",operation_key:null,error:null,
      data:{schema:"mastermind.os.executive.session_context.v1",
        principal_scope:"c".repeat(64),verified_expiry:4102444800,
        selection:{work_ref:selection.workRef,root_job_id:selection.rootJobId},
        selection_state:"RESOLVED",
        target:{target_ref:bPointer.targetKey,generation:"a".repeat(24),
          addressable:true,kind:"fabric_attempt",
          continuation_operation_key:bPointer.operationKey,
          work_ref:selection.workRef,root_job_id:selection.rootJobId},
        capabilities:{send:false,reply_read:true,stop:false},
      },
    };
    const aPointer={operationKey:"session-continue-"+"b".repeat(64),
      kind:"message" as const,targetKey:bPointer.targetKey};
    const digestA="1e2af7babc8b2c2d41e9d42df56a01b295802954493db2fc132c3456ac969a0e";
    const originalReply={
      schema:"mastermind.os.executive.session_result.v1",
      operation:"reply",ok:true,effect:"CONTINUATION_COMMITTED",
      operation_key:aPointer.operationKey,error:null,
      data:{schema:"mastermind.native_reply_read.v1",
        read_ref:"session-reply-"+digestA,
        request_ref:"session-bridge-continue:"+digestA,
        in_reply_to:"asd-dot-continue-c81bfcc7ccadd7372a1b0d05bb610f9d147b43b9",
        message_key:"asd-native-reply-4310b611582e4d2fa8f7053ea19490441b3e3db1",
        fingerprint:"f".repeat(64),text:"Historical native A recovered",
        next_step:"B remains pending",primary_ts:"1728620000.000001",
        reply_committed:true,parent_consumed:false,operation_key:aPointer.operationKey,
      },
    };
    const references={schema:"mastermind.os.executive.session_result.v1",
      operation:"references",ok:true,effect:"NONE",operation_key:null,error:null,
      data:{schema:"mastermind.session_reply_references.v1",status:"COMPLETE",
        high_water:5,references:[],next_cursor:null}};
    f.invoke.mockImplementation(async (cmd)=>{
      if(cmd==="executive_session_context")return context;
      if(cmd==="executive_session_references")return references;
      if(cmd==="executive_session_reply")return originalReply;
      throw new Error("unexpected native command");
    });
    const host=createOsExecutiveSessionHost(f.sessionTransport,store);
    try {
      await host.refresh(selection);
      expect(host.binding.port.currentTargetRef()).toBeNull();
      expect(host.binding.port.context()?.principalScope).toBe("c".repeat(64));
      const signal=new AbortController().signal;
      await expect(host.binding.port.readOriginalReferences!(selection,signal))
        .resolves.toEqual(references);
      const history=await host.binding.port.readQualifiedAnswer!(aPointer,signal);
      expect(history.receipt.disposition).toBe("accepted");
      expect(history.answer).toEqual({
        text:"Historical native A recovered",nextStep:"B remains pending",
        readRef:"session-reply-"+digestA,parentConsumed:false,
      });
      expect(host.binding.port.currentTargetRef()).toBeNull();
      expect(store.reserve).not.toHaveBeenCalled();
      expect(store.clearIfEqual).not.toHaveBeenCalled();
      expect(await store.read("c".repeat(64))).toEqual(bPointer);
      expect(f.invoke.mock.calls.map(([cmd])=>cmd)).toEqual([
        "executive_auth_status","executive_session_context",
        "executive_session_references","executive_session_reply",
      ]);
    } finally { host.dispose(); }
  });
  it("stale native historical READ is withheld after auth epoch changes",async()=>{
    const f=await fixture(), late=deferred(),signal=new AbortController().signal;
    f.invoke.mockReturnValueOnce(late.promise);
    const pending=f.sessionTransport.references!({
      work_ref:"WS:ALPHA",root_job_id:"JOB-1",
    },signal);
    const held=expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.invalidate(); await held;
    late.resolve({private:"old scope"});
    await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
    expect(f.sessionTransport.available()).toBe(false);
  });

  it("projects four-item same-project history through one distinct fixed native command",async()=>{
    const f=await fixture(), signal=new AbortController().signal;
    f.invoke.mockResolvedValueOnce({reference_only:true});
    await expect(f.sessionTransport.projectReferences!({work_ref:"WS:ALPHA",page_size:4,cursor:"YQ=="},signal))
      .resolves.toEqual({reference_only:true});
    expect(f.invoke).toHaveBeenLastCalledWith("executive_project_session_references",{workRef:"WS:ALPHA",cursor:"YQ=="});
    f.invoke.mockClear();
    for(const args of [{work_ref:"WS:ALPHA",page_size:16},{work_ref:"WS:ALPHA",page_size:4,root_job_id:"JOB-1"},
      {work_ref:"WS:ALPHA\n",page_size:4},{work_ref:"WS:ALPHA",page_size:4,cursor:"bad/.."}]) {
      await expect(f.sessionTransport.projectReferences!(args as never,signal)).rejects.toThrow("SESSION_REFERENCES_INVALID");
    }
    expect(f.invoke).not.toHaveBeenCalled();
    const late=deferred(); f.invoke.mockReturnValueOnce(late.promise);
    const pending=f.sessionTransport.projectReferences!({work_ref:"WS:ALPHA",page_size:4},signal);
    const held=expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.invalidate(); await held; late.resolve({private:"old"});
  });
  it("an initially missing command leaves Executive unavailable", async () => {
    const invoke = vi.fn(async () => { throw new Error("native missing"); });
    const f = await createNativeExecutiveTransport(invoke as never, async () => () => {});
    expect(f.transport.available()).toBe(false);
    await expect(f.transport.context(new AbortController().signal)).rejects.toThrow("EXECUTIVE_UNAVAILABLE");
    expect(invoke).toHaveBeenCalledTimes(1);
  });
  it("reports the observed auth outcome as closed diagnostics without any additional native call", async () => {
    const f = await fixture();
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: true, phase: "ready", contextReadReason: "UNKNOWN" });
    const before = f.invoke.mock.calls.length;
    for (let round = 0; round < 3; round++) expect(f.transport.diagnostics?.().phase).toBe("ready");
    expect(f.invoke.mock.calls.length).toBe(before);
    expect(f.invoke.mock.calls.map(([command]) => command)).toEqual(["executive_auth_status"]);
    f.notify({ generation: 4, available: false });
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: false, phase: "auth_unavailable", contextReadReason: "UNKNOWN" });
    expect(f.invoke.mock.calls.length).toBe(before);
  });
  it("records invalid_response for malformed auth status and never echoes the private payload", async () => {
    const f = await fixture();
    f.notify({ generation: 4, available: true, token: "private" });
    expect(f.transport.available()).toBe(false);
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "invalid_response", contextReadReason: "UNKNOWN" });
    f.notify({ generation: 4, available: true });
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: true, phase: "ready", contextReadReason: "UNKNOWN" });
  });
  it("resets diagnostics on local sign-out and stale replies cannot resurrect an older phase", async () => {
    const f = await fixture();
    expect(f.transport.diagnostics?.().phase).toBe("ready");
    f.invalidate();
    expect(f.transport.available()).toBe(false);
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "not_requested", contextReadReason: "UNKNOWN" });
    f.notify({ generation: 3, available: true }); // regressing generation stays ignored
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "not_requested", contextReadReason: "UNKNOWN" });
    f.notify({ generation: 4, available: false });
    expect(f.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: false, phase: "auth_unavailable", contextReadReason: "UNKNOWN" });
    expect(f.transport.available()).toBe(false);
  });
  it("a pending initial status that loses the epoch race leaves the reset diagnostics untouched", async () => {
    const late = deferred();
    let notify = (_raw: unknown) => {};
    const invoke = vi.fn(async (command: string): Promise<unknown> =>
      command === "executive_auth_status" ? late.promise : { ok: true });
    const created = await createNativeExecutiveTransport(invoke as never, async (event, callback) => {
      expect(event).toBe("mastermind-executive-auth-state"); notify = (raw) => callback({ payload: raw }); return () => {};
    });
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "pending", contextReadReason: "UNKNOWN" });
    created.invalidate();
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "not_requested", contextReadReason: "UNKNOWN" });
    late.resolve({ generation: 7, available: true });
    await created.ready;
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "not_requested", contextReadReason: "UNKNOWN" });
    expect(created.transport.available()).toBe(false);
    notify({ generation: 7, available: true });
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: true, phase: "ready", contextReadReason: "UNKNOWN" });
    expect(invoke).toHaveBeenCalledTimes(1);
  });
  it("records transport_failure when the auth listener cannot be established, with no status request", async () => {
    const invoke = vi.fn(async (): Promise<unknown> => ({ generation: 3, available: true }));
    const created = await createNativeExecutiveTransport(invoke as never, async () => {
      throw new Error("listener refused");
    });
    await created.ready;
    expect(created.transport.available()).toBe(false);
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "transport_failure", contextReadReason: "UNKNOWN" });
    expect(invoke).not.toHaveBeenCalled();
  });
  it("records transport_failure with unknown auth when the initial status command is missing", async () => {
    const invoke = vi.fn(async () => { throw new Error("native missing"); });
    const created = await createNativeExecutiveTransport(invoke as never, async () => () => {});
    await created.ready;
    expect(created.transport.available()).toBe(false);
    expect(created.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: null, phase: "transport_failure", contextReadReason: "UNKNOWN" });
    expect(invoke).toHaveBeenCalledTimes(1);
  });
});

it("settles a repeated native status without changing the existing auth generation", async () => {
  const status = { generation: 4, available: true };
  const invoke = vi.fn(async () => status);
  const native = await createNativeExecutiveTransport(invoke as never, async (_event, listener) => {
    listener({ payload: status }); // existing event arrives before the initial status reply
    return () => {};
  });
  await native.ready;
  expect(native.transport.diagnostics?.()).toEqual({ kind: "native", authAvailable: true, phase: "ready", contextReadReason: "UNKNOWN" });
  expect(native.transport.authGeneration()).toBe(1);
  expect(invoke).toHaveBeenCalledExactlyOnceWith("executive_auth_status");
});


it("retains only the context READ refusal code and preserves every public rejection", async () => {
  const f = await fixture(), signal = new AbortController().signal;
  f.invoke.mockRejectedValueOnce("ACCESS_REFUSED");
  await expect(f.transport.context(signal)).rejects.toThrow("EXECUTIVE_TRANSPORT_UNAVAILABLE");
  expect(f.transport.diagnostics?.().contextReadReason).toBe("ACCESS_REFUSED");
  const calls = f.invoke.mock.calls.length;
  f.transport.diagnostics?.(); f.transport.diagnostics?.();
  expect(f.invoke).toHaveBeenCalledTimes(calls);
  f.invoke.mockRejectedValueOnce("AUTHENTICATION_REQUIRED");
  await expect(f.transport.submit({ goal: "fixture" }, signal)).rejects.toThrow("EXECUTIVE_TRANSPORT_UNAVAILABLE");
  expect(f.transport.diagnostics?.().contextReadReason).toBe("ACCESS_REFUSED"); // mutation is not observed
  f.invoke.mockRejectedValueOnce(new Error("PRIVATE account credential"));
  await expect(f.transport.context(signal)).rejects.toThrow("EXECUTIVE_TRANSPORT_UNAVAILABLE");
  expect(f.transport.diagnostics?.().contextReadReason).toBe("UNKNOWN");
  f.invoke.mockResolvedValueOnce({ ok: true });
  await f.transport.context(signal);
  expect(f.transport.diagnostics?.().contextReadReason).toBe("NONE");
});

describe("native Secretary selection beside qualified Fabric SEND", () => {
  it.each([false, true])("preserves the qualified Secretary SEND capability %s on the same native route", async (send) => {
    const f = await fixture(), signal = new AbortController().signal;
    const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-1", targetKind: "hermes_secretary" as const };
    const target = "hermes_secretary:" + "a".repeat(64);
    const key = "session-continue-416b8fb98b2d93a068cd6dbd4ff5516c0a75961314334810df3f5b86cf754137";
    const raw = { schema: "mastermind.os.executive.session_result.v1",
      operation: "context", ok: true, effect: "NONE", operation_key: null, error: null,
      data: { schema: "mastermind.os.executive.session_context.v1",
        principal_scope: "c".repeat(64), verified_expiry: 4102444800,
        selection: { work_ref: selection.workRef, root_job_id: selection.rootJobId,
          target_kind: selection.targetKind },
        selection_state: "RESOLVED", target: { target_ref: target, generation: "a".repeat(24),
          addressable: true, kind: "hermes_secretary", continuation_operation_key: key,
          work_ref: selection.workRef, root_job_id: selection.rootJobId },
        capabilities: { send, reply_read: true, stop: false } } };
    f.invoke.mockResolvedValueOnce(raw);
    const result = await f.sessionTransport.context(selection, signal);
    expect(decodeSessionContext(result, selection)?.capabilities)
      .toEqual({ send, reply_read: true, stop: false });
    expect(raw.data.capabilities.send).toBe(send);
    const arguments_ = { target_ref: target, operation_key: key,
      instruction: "One native question", stop_condition: "Return once" };
    if (send) await f.sessionTransport.send(arguments_, signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"],
      ["executive_session_context", { selection: raw.data.selection }],
      ...(send ? [["executive_session_send", { arguments: arguments_ }]] : []),
    ]);
  });
});

describe("native project execution bridge", () => {
  const original = {operation_key: "mmos-project-execute-" + "a".repeat(40), work_ref: "WS:EXAMPLE"};
  const context = {record_source: {repository: "mastermindx-market-intelligence/macro", commit: "b".repeat(40),
    path: "agentos/workstreams/WS-EXAMPLE.md", content_sha256: "c".repeat(64)}, adoption: null, adoption_decision_source: null};
  const requests = {
    preview: {...original, operation_key: "mmos-project-preview-" + "d".repeat(40), expected_context: context},
    submit: {...original, expected_context: context, context_sha256: "e".repeat(64),
      execution_binding_sha256: "f".repeat(64), execution_profile: "research_only",
      objective: "Finish the project", handoff_text: "Original private handoff", continuation_mode: "DURABLE"},
    status: original,
  };
  it.each(["preview", "submit", "status"] as const)("invokes only the fixed %s command with the original closed arguments", async operation => {
    const f = await fixture();
    await f.transport.projectExecution!.request(operation, requests[operation], new AbortController().signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"],
      ["executive_project_execution", {operation, arguments: requests[operation]}],
    ]);
  });
  it("refuses route, source and root injection before invoking native code", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    expect(() => f.transport.projectExecution!.request("../submit" as never, original, signal)).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(() => f.transport.projectExecution!.request("status", {...original, root_job_id: "JOB-forged"}, signal)).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(() => f.transport.projectExecution!.request("submit", {...requests.submit,
      expected_context: {...context, record_source: {...context.record_source, path: "agentos/workstreams/WS-OTHER.md"}}}, signal))
      .toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(f.invoke.mock.calls).toEqual([["executive_auth_status"]]);
  });
  it.each(["preview", "submit", "status"] as const)("settles pending %s on auth replacement and never replays its late reply", async operation => {
    const f = await fixture(), late = deferred();
    f.invoke.mockReturnValueOnce(late.promise);
    const request = f.transport.projectExecution!.request(operation, requests[operation], new AbortController().signal);
    const rejected = expect(request).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.notify({generation: 4, available: true});
    await rejected;
    late.resolve({ok: true, data: {root_job_id: "untrusted-late"}});
    await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
  });
  it("counts handoff UTF8 bytes and rejects over-budget input before native dispatch", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    await f.transport.projectExecution!.request("submit", {...requests.submit, handoff_text: "界".repeat(10922)}, signal);
    expect(() => f.transport.projectExecution!.request("submit", {...requests.submit, handoff_text: "界".repeat(10923)}, signal))
      .toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(f.invoke).toHaveBeenCalledTimes(2);
  });
});
