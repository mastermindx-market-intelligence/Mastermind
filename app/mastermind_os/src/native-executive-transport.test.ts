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
  it("maps only fixed historical READ commands and never invokes a native session SEND", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-1" };
    await f.sessionTransport.context(selection, signal);
    await f.sessionTransport.reply({ operation_key: "session-continue-"+"a".repeat(64) }, signal);
    await f.sessionTransport.references!({
      work_ref: selection.workRef, root_job_id: selection.rootJobId, cursor: "YWJjZA==",
    }, signal);
    await expect(f.sessionTransport.send({
      target_ref: "fabric_attempt:"+"b".repeat(64),
      operation_key: "session-continue-"+"a".repeat(64),
      instruction: "no native SEND", stop_condition: "never",
    },signal)).rejects.toThrow("NATIVE_SESSION_READ_ONLY");
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"],
      ["executive_session_context", {selection:{work_ref:"WS:ALPHA",root_job_id:"JOB-1"}}],
      ["executive_session_reply",{operationKey:"session-continue-"+"a".repeat(64)}],
      ["executive_session_references",{selection:{work_ref:"WS:ALPHA",root_job_id:"JOB-1"},
        pageSize:16,cursor:"YWJjZA=="}],
    ]);
    expect(f.invoke.mock.calls.map(([cmd])=>cmd)).not.toContain("executive_submit");
    expect(f.invoke.mock.calls.map(([cmd])=>cmd)).not.toContain("executive_session_send");
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
  it("reduces a validated native context to READ-only while preserving its original owner",async()=>{
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
      send:false,reply_read:true,stop:false,
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
        capabilities:{send:true,reply_read:true,stop:false},
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
      await expect(f.sessionTransport.send({
        target_ref:bPointer.targetKey,
        operation_key:bPointer.operationKey,
        instruction:"do not send",stop_condition:"do not send",
      },signal)).rejects.toThrow("NATIVE_SESSION_READ_ONLY");
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
  it("an initially missing command leaves Executive unavailable", async () => {
    const invoke = vi.fn(async () => { throw new Error("native missing"); });
    const f = await createNativeExecutiveTransport(invoke as never, async () => () => {});
    expect(f.transport.available()).toBe(false);
    await expect(f.transport.context(new AbortController().signal)).rejects.toThrow("EXECUTIVE_UNAVAILABLE");
    expect(invoke).toHaveBeenCalledTimes(1);
  });
});
