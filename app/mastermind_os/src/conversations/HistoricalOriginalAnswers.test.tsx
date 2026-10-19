// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  const readRefs = vi.fn(async (_selection?: unknown, _signal?: AbortSignal,
                                   _cursor?: string): Promise<unknown> => page);
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

describe("history security and pagination fences",()=>{
  it("never publishes a delayed historical read after A-B-A auth/selection",async()=>{
    const x=setup();
    let finish!: (value: Awaited<ReturnType<typeof x.qualified>>) => void;
    x.qualified.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const {rerender}=render(<HistoricalOriginalAnswers {...x.props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    expect(x.qualified).toHaveBeenCalledTimes(1);
    rerender(<HistoricalOriginalAnswers {...x.props}
      selection={{workRef,rootJobId:"JOB-OTHER"}} selectionSeq={2}/>);
    expect(screen.queryByText("Recovered historical A.")).toBeNull();
    rerender(<HistoricalOriginalAnswers {...x.props} selectionSeq={3} authRevision={2}/>);
    expect(screen.queryByText("Recovered historical A.")).toBeNull();
    await act(async()=>{finish({
      receipt:{operationKey,targetKey,kind:"message",disposition:"accepted"},
      answer:{text:"STALE A MUST NOT SHOW", nextStep:"Forbidden",readRef,parentConsumed:false},
    });});
    expect(screen.queryByText("STALE A MUST NOT SHOW")).toBeNull();
    expect(x.store.reserve).not.toHaveBeenCalled();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("automatically traverses empty PARTIAL pages before displaying actual references",async()=>{
    const x=setup();
    x.readRefs.mockResolvedValueOnce({...page,data:{...page.data,status:"PARTIAL",
      references:[],next_cursor:"YWJjZA=="}}).mockResolvedValueOnce(page);
    render(<HistoricalOriginalAnswers {...x.props}/>);
    expect(await screen.findByRole("button",{name:/Open original request/})).toBeTruthy();
    expect(x.readRefs).toHaveBeenCalledTimes(2);
    expect(x.readRefs.mock.calls[1][2]).toBe("YWJjZA==");
    expect(x.qualified).not.toHaveBeenCalled();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("caps sparse scanning to four read-only pages per user action",async()=>{
    const x=setup();
    const cursors = ["YQ==","Yg==","Yw==","ZA==","ZQ==","Zg==","Zw==","aA=="];
    let n=0;
    x.readRefs.mockImplementation(async()=>({...page,data:{...page.data,
      status:"PARTIAL",references:[],next_cursor:cursors[n++]}}));
    render(<HistoricalOriginalAnswers {...x.props}/>);
    fireEvent.click(await screen.findByRole("button",{name:"More original requests"}));
    await waitFor(()=>expect(x.readRefs).toHaveBeenCalledTimes(8));
    expect(screen.getByRole("button",{name:"More original requests"})).toBeTruthy();
    expect(x.qualified).not.toHaveBeenCalled();
    expect(x.store.reserve).not.toHaveBeenCalled();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("refuses a repeated cursor instead of looping forever",async()=>{
    const x=setup();
    x.readRefs.mockResolvedValue({...page,data:{...page.data,
      status:"PARTIAL",references:[],next_cursor:"YQ==" }});
    render(<HistoricalOriginalAnswers {...x.props}/>);
    await screen.findByText(/Historical reference or answer unavailable/);
    expect(x.readRefs).toHaveBeenCalledTimes(2);
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("rejects a changed high water across cursor pages",async()=>{
    const x=setup();
    x.readRefs.mockResolvedValueOnce({...page,data:{...page.data,
      status:"PARTIAL",references:[],next_cursor:"YQ=="}})
      .mockResolvedValueOnce({...page,data:{...page.data,high_water:6}});
    render(<HistoricalOriginalAnswers {...x.props}/>);
    await screen.findByText(/Historical reference or answer unavailable/);
    expect(screen.queryByRole("button",{name:/Open original request/})).toBeNull();
    expect(x.readRefs).toHaveBeenCalledTimes(2);
  });
  it("stops automatic sparse traversal when the auth generation changes mid-page",async()=>{
    const x=setup();
    let finish!: (raw:unknown) => void;
    x.readRefs.mockResolvedValueOnce({...page,data:{...page.data,
      status:"PARTIAL",references:[],next_cursor:"YQ=="}})
      .mockImplementationOnce(()=>new Promise<unknown>(resolve=>{finish=resolve;}))
      .mockResolvedValueOnce({...page,data:{...page.data,references:[]}});
    const {rerender}=render(<HistoricalOriginalAnswers {...x.props}/>);
    await waitFor(()=>expect(x.readRefs).toHaveBeenCalledTimes(2));
    rerender(<HistoricalOriginalAnswers {...x.props} authRevision={2}/>);
    await waitFor(()=>expect(x.readRefs).toHaveBeenCalledTimes(3));
    await act(async()=>finish(page));
    expect(screen.queryByRole("button",{name:/Open original request/})).toBeNull();
    expect(x.qualified).not.toHaveBeenCalled();
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("rejects foreign and extended backend metadata before exposing a reference",async()=>{
    const x=setup();
    x.readRefs.mockResolvedValueOnce({...page,data:{...page.data,
      references:[{...row, private_original_body:"DO NOT DISPLAY"}]}});
    render(<HistoricalOriginalAnswers {...x.props}/>);
    await screen.findByText(/Historical reference or answer unavailable/);
    expect(screen.queryByText("DO NOT DISPLAY")).toBeNull();
    expect(screen.queryByRole("button",{name:/Open original request/})).toBeNull();
    expect(x.qualified).not.toHaveBeenCalled();
  });
  it("shows one answer if the active answer card already owns the same read ref",async()=>{
    const x=setup();
    const {rerender}=render(<HistoricalOriginalAnswers {...x.props}/>);
    fireEvent.click(await screen.findByRole("button",{name:/Open original request/}));
    await screen.findByText("Recovered historical A.");
    rerender(<HistoricalOriginalAnswers {...x.props} activeReadRef={readRef}/>);
    expect(screen.queryByText("Recovered historical A.")).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button",{name:/Open original request/}).disabled).toBe(true);
    expect(x.store.clearIfEqual).not.toHaveBeenCalled();
  });
});
