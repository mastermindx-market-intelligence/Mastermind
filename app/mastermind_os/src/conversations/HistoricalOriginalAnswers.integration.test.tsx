// @vitest-environment jsdom
// Source-level real binding + real durable IndexedDB pointer integration.
// Wire results use an in-memory verified-producer fixture, NOT installed OAuth.
import { IDBFactory } from "fake-indexeddb";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { HistoricalOriginalAnswers } from "./HistoricalOriginalAnswers";
import { createOsExecutiveSessionHost } from "../orchestration/os-executive-session-host";
import { createIndexedDbSessionPendingPointerStore } from "../orchestration/indexeddb-session-pending-pointer-store";
import type { ExecutiveSessionTransport } from "../orchestration/executive-session-command-port";
import secretaryFixture from "../fixtures/native-hermes-session-send-producer.json";
import metaFixture from "../fixtures/native-hermes-meta-session-send-producer.json";

const WS = "WS:ALPHA", ROOT = "JOB-1", SCOPE = "c".repeat(64);
const TARGET = "fabric_attempt:"+"a".repeat(64);
const OP_A = "session-continue-"+"b".repeat(64);
const OP_B = "session-continue-"+"e".repeat(64);
// Exact Runtime _request_key: SHA-256 of canonical
// {"operation_key": OP_A, "schema":"mastermind.session_bridge.continue_request.v1"}.
const REQUEST_KEY_A = "1e2af7babc8b2c2d41e9d42df56a01b295802954493db2fc132c3456ac969a0e";
const READ_A = "session-reply-"+REQUEST_KEY_A;
const REQUEST_REF_A = "session-bridge-continue:"+REQUEST_KEY_A;
const DOT_A = "asd-dot-continue-c81bfcc7ccadd7372a1b0d05bb610f9d147b43b9";
const NATIVE_A = "asd-native-reply-4310b611582e4d2fa8f7053ea19490441b3e3db1";
const selection = {workRef:WS,rootJobId:ROOT};
const row = {
  read_ref: READ_A, operation_key: OP_A, request_ref:REQUEST_REF_A,
  request_event_id:5, request_revision:"d".repeat(64),
  requested_at:"2026-10-18T00:00:00Z",work_ref:WS,root_job_id:ROOT,
  target_ref:TARGET,reference_only:true,
};
const envelope = (operation:string, data:unknown, effect="NONE")=>({
  schema:"mastermind.os.executive.session_result.v1",
  operation,ok:true,effect,operation_key:effect==="NONE"?null:OP_A,
  data,error:null,
});
const nativeData = {
  schema:"mastermind.native_reply_read.v1",
  read_ref:READ_A,request_ref:REQUEST_REF_A,in_reply_to:DOT_A,
  message_key:NATIVE_A,fingerprint:"f".repeat(64),text:"Historical A is committed.",
  next_step:"B remains pending.",primary_ts:"1728620000.000001",
  reply_committed:true,parent_consumed:false,operation_key:OP_A,
};
const context = envelope("context",{
  schema:"mastermind.os.executive.session_context.v1",
  principal_scope:SCOPE,verified_expiry:4102444800,
  selection:{work_ref:WS,root_job_id:ROOT},selection_state:"RESOLVED",
  target:{target_ref:TARGET,generation:"a".repeat(24),addressable:true,
    kind:"fabric_attempt",continuation_operation_key:OP_B,work_ref:WS,root_job_id:ROOT},
  capabilities:{send:true,reply_read:true,stop:false},
});
const references=envelope("references",{
  schema:"mastermind.session_reply_references.v1",status:"COMPLETE",
  references:[row],next_cursor:null,high_water:5,
});
const native=envelope("reply",nativeData,"CONTINUATION_COMMITTED");

afterEach(()=>{
  cleanup();
  vi.unstubAllGlobals();
});

it("opens historical A with the mounted native qualifier, without consuming durable pending B, including after remount",async()=>{
  // Native test-only WebCrypto, not an application dependency.
  const nodeCrypto = await import("node:crypto" as string);
  vi.stubGlobal("crypto",nodeCrypto.webcrypto);
  const idb = new IDBFactory();
  const store = createIndexedDbSessionPendingPointerStore(idb);
  const pendingB = {operationKey:OP_B,targetKey:TARGET,kind:"message" as const};
  expect((await store.reserve(SCOPE,pendingB)).reserved).toBe(true);
  const transport:ExecutiveSessionTransport = {
    authGeneration:()=>1,available:()=>true,subscribe:()=>()=>{},
    context:vi.fn(async()=>context),
    references:vi.fn(async()=>references),
    reply:vi.fn(async()=>native),
    send:vi.fn(async()=>{throw new Error("NO SEND ALLOWED IN HISTORICAL READ");}),
  };
  const host = createOsExecutiveSessionHost(transport,store);
  try {
    await host.ready;
    await host.refresh(selection);
    const owner = host.binding.port.context();
    expect(owner?.principalScope).toBe(SCOPE);
    const props = {binding:host.binding,selection,principalScope:owner!.principalScope,
      generation:owner!.generation,selectionSeq:1,authRevision:1,activeReadRef:null};
    const first = render(<HistoricalOriginalAnswers {...props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    await screen.findByText("Historical A is committed.");
    expect(await store.read(SCOPE)).toEqual(pendingB);
    first.unmount();
    // New component lifetime, same durable scope and original request evidence.
    const afterReload = createIndexedDbSessionPendingPointerStore(idb);
    expect(await afterReload.read(SCOPE)).toEqual(pendingB);
    render(<HistoricalOriginalAnswers {...props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    await screen.findByText("Historical A is committed.");
    expect(await afterReload.read(SCOPE)).toEqual(pendingB);
    expect(transport.send).not.toHaveBeenCalled();
    expect(transport.reply).toHaveBeenCalledTimes(2);
    expect(transport.references).toHaveBeenCalledTimes(2);
    expect(transport.reply).toHaveBeenCalledWith(
      {operation_key:OP_A},expect.any(AbortSignal));
  } finally { host.dispose(); }
});

it("opens a mixed Fabric/Secretary/Meta page without clearing the retained Secretary operation", async () => {
  const nodeCrypto = await import("node:crypto" as string);
  vi.stubGlobal("crypto", nodeCrypto.webcrypto);
  const selected = {workRef: metaFixture.selection.work_ref,
    rootJobId: metaFixture.selection.root_job_id, targetKind: "hermes_meta" as const};
  const scope = metaFixture.context.data.principal_scope;
  const idb = new IDBFactory(), store = createIndexedDbSessionPendingPointerStore(idb);
  const pendingB = {kind: "message" as const,
    operationKey: secretaryFixture.arguments.operation_key,
    targetKey: secretaryFixture.arguments.target_ref};
  expect((await store.reserve(scope, pendingB)).reserved).toBe(true);
  const nativeRows = [secretaryFixture, metaFixture].map((source, index) => ({
    read_ref: source.reply.data.read_ref, operation_key: source.reply.data.operation_key,
    request_ref: source.reply.data.request_ref, request_revision: source.reply.data.request_revision,
    target_ref: source.reply.data.target_ref, request_event_id: 4 - index,
    requested_at: "2026-10-18T00:00:00Z", work_ref: selected.workRef,
    root_job_id: selected.rootJobId, reference_only: true,
  }));
  const rows = [{...row, work_ref: selected.workRef, root_job_id: selected.rootJobId}, ...nativeRows];
  const replies = new Map<string, unknown>([
    [OP_A, native], [secretaryFixture.arguments.operation_key, secretaryFixture.reply],
    [metaFixture.arguments.operation_key, metaFixture.reply],
  ]);
  const transport: ExecutiveSessionTransport = {
    authGeneration: () => 1, available: () => true, subscribe: () => () => {},
    context: vi.fn(async () => metaFixture.context),
    references: vi.fn(async () => envelope("references", {
      schema: "mastermind.session_reply_references.v1", status: "COMPLETE",
      references: rows, next_cursor: null, high_water: 5,
    })),
    reply: vi.fn(async ({operation_key}) => replies.get(operation_key)),
    send: vi.fn(async () => {throw Error("HISTORY MUST NOT SEND");}),
  };
  const host = createOsExecutiveSessionHost(transport, store);
  try {
    await host.ready; await host.refresh(selected);
    const owner = host.binding.port.context()!;
    const props = {binding: host.binding, selection: selected,
      principalScope: owner.principalScope, generation: owner.generation,
      selectionSeq: 1, authRevision: 1, activeReadRef: null};
    const first = render(<HistoricalOriginalAnswers {...props}/>);
    await screen.findAllByRole("button", {name: /Open original request/});
    const answers = [nativeData.text, secretaryFixture.reply.data.answer, metaFixture.reply.data.answer];
    for (let index = 0; index < rows.length; index++) {
      fireEvent.click(screen.getAllByRole("button", {name: /Open original request/})[index]);
      await screen.findByText(answers[index]);
      expect(await store.read(scope)).toEqual(pendingB);
    }
    first.unmount();
    const reloaded = createIndexedDbSessionPendingPointerStore(idb);
    render(<HistoricalOriginalAnswers {...props}/>);
    fireEvent.click((await screen.findAllByRole("button", {name: /Open original request/}))[2]);
    await screen.findByText(metaFixture.reply.data.answer);
    expect(await reloaded.read(scope)).toEqual(pendingB);
    expect(transport.send).not.toHaveBeenCalled();
    expect(transport.reply).toHaveBeenCalledTimes(4);
    expect(transport.reply).toHaveBeenLastCalledWith(
      {operation_key: metaFixture.arguments.operation_key}, expect.any(AbortSignal));
  } finally {host.dispose();}
});
