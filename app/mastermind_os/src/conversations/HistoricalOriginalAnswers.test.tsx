// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoricalOriginalAnswers } from "./HistoricalOriginalAnswers";
import type { MountedExecutiveSessionBinding } from "../orchestration/os-executive-session-host";

afterEach(cleanup);
const workRef = "WS:TEST";
const rootJobId = "JOB-TEST";
const operationKey = "session-continue-" + "b".repeat(64);
const targetKey = "fabric_attempt:" + "a".repeat(64);
const readRef = "session-reply-" + "c".repeat(64);
const row = { read_ref: readRef, operation_key: operationKey, target_ref: targetKey,
  request_ref: "session-bridge-continue:" + "b".repeat(64),
  request_event_id: 5, request_revision: "d".repeat(64),
  requested_at: "2026-10-18T00:00:00Z", work_ref: workRef,
  root_job_id: rootJobId, reference_only: true as const };
const page = {schema:"mastermind.os.executive.session_result.v1", operation:"references",
  ok:true, effect:"NONE",operation_key:null,error:null,
  data:{schema:"mastermind.session_reply_references.v1",status:"COMPLETE",references:[row],next_cursor:null,high_water:5}};
function setup() {
  const readRefs = vi.fn(async () => page);
  const qualified = vi.fn(async () => ({
    receipt: { operationKey, targetKey, kind:"message" as const, disposition:"accepted" as const },
    answer: {text:"Recovered historical A.", nextStep:"Continue B separately.",
      readRef, parentConsumed:false as const},
  }));
  const store = {read:vi.fn(),reserve:vi.fn(),clearIfEqual:vi.fn()};
  const binding = {port:{readOriginalReferences:readRefs,readQualifiedAnswer:qualified},
    store} as unknown as MountedExecutiveSessionBinding;
  const props = {binding,selection:{workRef,rootJobId},principalScope:"scope",
    generation:"gen1",authRevision:1,selectionSeq:1,activeReadRef:null};
  return {props,readRefs,qualified,store};
}
describe("historical original answer READ",()=>{
  it("recovers historical A while no pending-B store operation occurs",async()=>{
    const x=setup();
    render(<HistoricalOriginalAnswers {...x.props}/>);
    const button = await screen.findByRole("button",{name:/Open original request/});
    fireEvent.click(button);
    await screen.findByText("Recovered historical A.");
    expect(x.readRefs).toHaveBeenCalledTimes(1);
    expect(x.qualified).toHaveBeenCalledWith(
      {operationKey,targetKey,kind:"message"}, expect.any(AbortSignal));
    expect(x.store.read).not.toHaveBeenCalled();
    expect(x.store.reserve).not.toHaveBeenCalled();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("withholds a foreign readRef even on an accepted native receipt",async()=>{
    const x=setup();
    x.qualified.mockResolvedValueOnce({receipt:{operationKey,targetKey,kind:"message",disposition:"accepted"},
      answer:{text:"FORBIDDEN", nextStep:"x", readRef:"session-reply-"+"e".repeat(64),parentConsumed:false}});
    render(<HistoricalOriginalAnswers {...x.props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    await screen.findByText(/Historical reference or answer unavailable/);
    expect(screen.queryByText("FORBIDDEN")).toBeNull();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("withdraws the old selected answer on auth revision changes",async()=>{
    const x=setup();
    const {rerender}=render(<HistoricalOriginalAnswers {...x.props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    await screen.findByText("Recovered historical A.");
    rerender(<HistoricalOriginalAnswers {...x.props} authRevision={2}/>);
    await waitFor(()=>expect(screen.queryByText("Recovered historical A.")).toBeNull());
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
});
