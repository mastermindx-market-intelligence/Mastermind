// @vitest-environment jsdom
// Injected, source-only transport/store tests; no live authentication or SEND.
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { createOsExecutiveSessionHost } from './orchestration/os-executive-session-host';
import type { ExecutiveSessionTransport } from './orchestration/executive-session-command-port';
import type { OperationPointer, PendingPointerStore } from './orchestration/operation-controller';
import type { AuthState } from './host';

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn().mockResolvedValue({ state: 'BUILT_NOT_PROVEN' }) }));
const SCOPE = 'c'.repeat(64), REF = `fabric_attempt:${'a'.repeat(64)}`, KEY = `session-continue-${'b'.repeat(64)}`;
const pointer: OperationPointer = { operationKey: KEY, kind: 'message', targetKey: REF };
// Original historical request A is distinct from the still-pending command B.
const HIST_OP_A = 'session-continue-' + 'c'.repeat(64);
const HIST_DIGEST_A = '47fc2dc67be106469d55109fd1d116d32185022daa6103e087a22ba245ec7e69';
const HIST_READ_A = 'session-reply-' + HIST_DIGEST_A;
const HIST_REQUEST_A = 'session-bridge-continue:' + HIST_DIGEST_A;
const HIST_ROW_A = {
  read_ref: HIST_READ_A, operation_key: HIST_OP_A, request_ref: HIST_REQUEST_A,
  request_event_id: 5, request_revision: 'd'.repeat(64),
  requested_at: '2026-10-18T00:00:00Z', work_ref: 'WS:ALPHA',
  root_job_id: 'JOB-1', target_ref: REF, reference_only: true as const,
};

const deferred = <T,>() => { let resolve!: (v:T)=>void; const promise = new Promise<T>(r=>{resolve=r;}); return {promise,resolve}; };
let dispose: (()=>void) | undefined;
function fixture(retained: OperationPointer | null = null, target = true, content = false, history = false) {
  let saved = retained, hasTarget = target, gen = 1;
  let auth: AuthState = { status: 'signed_in', reason: null, acquisition: false, content };
  const authListeners = new Set<(a:AuthState)=>void>();
  const listeners = new Set<()=>void>();
  const store: PendingPointerStore = {
    read: vi.fn(() => saved),
    reserve: vi.fn((_s, p) => { if(saved) return {reserved:false as const,pointer:saved}; saved=p; return {reserved:true as const}; }),
    clearIfEqual: vi.fn((_s,p)=>{ if(saved?.operationKey!==p.operationKey) return false; saved=null; return true; }),
  };
  const transport: ExecutiveSessionTransport = {
    available: () => auth.status === 'signed_in', authGeneration: () => gen,
    subscribe: fn => { listeners.add(fn); return ()=>{listeners.delete(fn);}; },
    context: vi.fn(async (selection) => ({ schema:'mastermind.os.executive.session_result.v1', operation:'context', ok:true, effect:'NONE', operation_key:null, error:null,
      data:{ schema:'mastermind.os.executive.session_context.v1', principal_scope:SCOPE, verified_expiry:Math.floor(Date.now()/1000)+3600,
        selection:{work_ref:selection.workRef, root_job_id:selection.rootJobId}, selection_state:hasTarget?'RESOLVED':'UNAVAILABLE',
        target:hasTarget?{target_ref:REF,generation:'a'.repeat(24),addressable:true,kind:'fabric_attempt',continuation_operation_key:KEY,work_ref:selection.workRef,root_job_id:selection.rootJobId}:null,
        capabilities:{send:hasTarget,reply_read:true,stop:false} } })),
    send: vi.fn(async () => { expect(saved).toEqual(pointer); throw new Error('lost private response'); }),
    reply: vi.fn(async () => { throw new Error('reply unavailable'); }),
    ...(history ? { references: vi.fn(async () => ({
      schema: 'mastermind.os.executive.session_result.v1', operation: 'references',
      ok: true, effect: 'NONE', operation_key: null, error: null,
      data: { schema: 'mastermind.session_reply_references.v1',
        status: 'COMPLETE', references: [HIST_ROW_A],
        high_water: 5, next_cursor: null },
    })) } : {}),
  };
  const host = createOsExecutiveSessionHost(transport,store); dispose=host.dispose;
  const readCurrentWindow=vi.fn(async()=>{throw new Error('fixture window unavailable')});
  window.MastermindMissionHost = {
    readCurrentWindow,
    sessionCommandBinding:host.binding, session:{refresh:s=>host.refresh(s as Parameters<typeof host.refresh>[0]),setStopCondition:host.setStopCondition},
    auth:{ getState:()=>auth,subscribe:fn=>{authListeners.add(fn);return ()=>{authListeners.delete(fn);};}, signIn:async()=>{},signOut:async()=>{} },
  };
  return { host, store, transport, readCurrentWindow, saved:()=>saved, loseTarget:()=>{hasTarget=false;},
    notifyAuth:()=>{ gen++; for(const fn of listeners)fn(); for(const fn of authListeners)fn(auth); },
  };
}
beforeEach(()=>{ history.replaceState(null,'','/os/?work_ref=WS%3AALPHA&root_job_id=JOB-1'); delete window.MastermindMissionHost; });
afterEach(()=>{cleanup();dispose?.();dispose=undefined;delete window.MastermindMissionHost;vi.restoreAllMocks();});
async function panel() { fireEvent.click(screen.getByRole('button',{name:'Conversations'})); return screen.findByLabelText('Session continuation'); }
async function enter() { await waitFor(()=>expect((screen.getByRole('button',{name:'Send'}) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.change(screen.getByLabelText('What would you like done?'),{target:{value:'Continue this selected slice'}});
  fireEvent.change(screen.getByLabelText('How will we know it is done?'),{target:{value:'Owner confirms the slice'}});
  await waitFor(()=>expect((screen.getByRole('button',{name:'Send'}) as HTMLButtonElement).disabled).toBe(false));
}
describe('App selected-session composition',()=>{
  it('does not qualify context during an uncommitted render',()=>{
    const f=fixture();renderToString(<App/>);
    expect(f.transport.context).not.toHaveBeenCalled();
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it('captures the required synchronous provider once and reserves before SEND without Launch',async()=>{
    const f=fixture();render(<App/>);await panel();await enter();
    const provider=vi.spyOn(window.MastermindMissionHost!.session!,'setStopCondition');
    const intent=vi.spyOn(f.host.binding,'makeMessageIntent');
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(f.transport.send).toHaveBeenCalledTimes(1));
    expect(intent).toHaveBeenCalledTimes(1);expect(provider).toHaveBeenCalledTimes(1);
    expect(f.transport.send).toHaveBeenCalledWith({target_ref:REF,instruction:'Continue this selected slice',stop_condition:'Owner confirms the slice',operation_key:KEY},expect.any(AbortSignal));
    await screen.findByRole('button',{name:'Check status'});
    expect(f.saved()).toEqual(pointer);expect(screen.queryByLabelText('Goal')).toBeNull();
  });
  it('reopens the original pointer with no target, status only, and retains an unavailable reply',async()=>{
    const f=fixture(pointer,false);render(<App/>);await panel();
    fireEvent.click(await screen.findByRole('button',{name:'Check status'}));
    await waitFor(()=>expect(f.transport.reply).toHaveBeenCalledTimes(1));
    expect(f.transport.reply).toHaveBeenCalledWith({operation_key:KEY},expect.any(AbortSignal));
    expect(f.transport.send).not.toHaveBeenCalled();expect(f.store.reserve).not.toHaveBeenCalled();expect(f.saved()).toEqual(pointer);
    expect(screen.queryByLabelText('What would you like done?')).toBeNull();
  });
  it("commits one qualified original reply into the real Conversations view before pointer clearance", async () => {
    const f = fixture(pointer, false, true);
    const read = vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockResolvedValue({
      receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "The bounded original finding is confirmed.",
        nextStep: "Review original evidence", readRef: "read-ref-1", parentConsumed: false },
    });
    // The pointer cannot clear merely because the underlying read returns:
    // React must have actually committed the qualified view first.
    const originalClear = vi.mocked(f.store.clearIfEqual).getMockImplementation()!;
    vi.mocked(f.store.clearIfEqual).mockImplementation((scope, p) => {
      expect(screen.getByRole("region", { name: "Qualified original answer" })).toBeTruthy();
      expect(screen.getByText("The bounded original finding is confirmed.")).toBeTruthy();
      expect(p).toEqual(pointer);
      return originalClear(scope, p);
    });
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(f.store.clearIfEqual).toHaveBeenCalledTimes(1));
    const answer = screen.getByRole("region", { name: "Qualified original answer" });
    expect(answer.closest(".conversation-window")).not.toBeNull();
    expect(answer.textContent).toContain("Original-parent acceptance is not established");
    expect(read).toHaveBeenCalledWith(pointer, expect.any(AbortSignal));
    expect(f.transport.send).not.toHaveBeenCalled();
    expect(f.transport.reply).not.toHaveBeenCalled();
    expect(f.saved()).toBeNull();
  });
  it("keeps a locally accepted original answer across non-security navigation", async () => {
    const f = fixture(pointer, false, true);
    const read = vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockResolvedValue({
      receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "A qualified answer remains in this Office session.",
        nextStep: "Review", readRef: "read-ref-1", parentConsumed: false },
    });
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(f.saved()).toBeNull());
    expect(screen.getAllByRole("region", { name: "Qualified original answer" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.queryByText("A qualified answer remains in this Office session.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText("A qualified answer remains in this Office session.")).toBeTruthy();
    expect(screen.getAllByRole("region", { name: "Qualified original answer" })).toHaveLength(1);
    expect(read).toHaveBeenCalledTimes(1);
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it("renders an idempotent original reply after failed compare-clear without a second SEND", async () => {
    const f = fixture(pointer, false, true);
    const read = vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockResolvedValue({
      receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "This original answer must not appear twice.",
        nextStep: "Inspect owner proof", readRef: "read-ref-1", parentConsumed: false },
    });
    vi.mocked(f.store.clearIfEqual).mockReturnValue(false);
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(f.store.clearIfEqual).toHaveBeenCalledTimes(1));
    expect(screen.getAllByRole("region", { name: "Qualified original answer" })).toHaveLength(1);
    expect(f.saved()).toEqual(pointer);
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(screen.getAllByRole("region", { name: "Qualified original answer" })).toHaveLength(1);
    expect(f.saved()).toEqual(pointer);
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it("withholds a delayed qualified reply when authentication generation changes", async () => {
    const f = fixture(pointer, false, true);
    const late = deferred<{
      receipt: { operationKey: string; kind: "message"; targetKey: string; disposition: "accepted"; reason: "ACCEPTED" };
      answer: { text: string; nextStep: string; readRef: string; parentConsumed: false };
    }>();
    const read = vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockReturnValue(late.promise);
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    await act(async () => f.notifyAuth());
    await act(async () => late.resolve({
      receipt: { operationKey: KEY, kind: "message", targetKey: REF,
        disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "No stale answer may leak.", nextStep: "none", readRef: "read-ref-1", parentConsumed: false },
    }));
    expect(screen.queryByRole("region", { name: "Qualified original answer" })).toBeNull();
    expect(screen.queryByText("No stale answer may leak.")).toBeNull();
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    expect(f.saved()).toEqual(pointer);
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it("does not display a late original answer after navigation away, retaining its key for explicit recovery", async () => {
    const f = fixture(pointer, false, true);
    const late = deferred<Awaited<ReturnType<NonNullable<typeof f.host.binding.port.readQualifiedAnswer>>>>();
    const read = vi.spyOn(f.host.binding.port, "readQualifiedAnswer")
      .mockReturnValueOnce(late.promise)
      .mockResolvedValue({
        receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
        answer: { text: "Reopened only under original authority.",
          nextStep: "Verify", readRef: "read-ref-1", parentConsumed: false },
      });
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    await act(async () => late.resolve({
      receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "Must not publish a late old-view answer.",
        nextStep: "none", readRef: "read-ref-1", parentConsumed: false },
    }));
    expect(screen.queryByText("Must not publish a late old-view answer.")).toBeNull();
    expect(f.saved()).toEqual(pointer);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Reopened only under original authority.")).toBeTruthy();
    await waitFor(() => expect(f.saved()).toBeNull());
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it("hides the qualified local answer immediately when the original auth owner changes", async () => {
    const f = fixture(pointer, false, true);
    vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockResolvedValue({
      receipt: { ...pointer, disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "Only current authorized source may see me.",
        nextStep: "Review", readRef: "read-ref-1", parentConsumed: false },
    });
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(f.saved()).toBeNull());
    expect(screen.getByText("Only current authorized source may see me.")).toBeTruthy();
    await act(async () => f.notifyAuth());
    expect(screen.queryByText("Only current authorized source may see me.")).toBeNull();
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it("does not clear or display a malformed/foreign original answer", async () => {
    const f = fixture(pointer, false, true);
    vi.spyOn(f.host.binding.port, "readQualifiedAnswer").mockResolvedValue({
      receipt: { ...pointer, operationKey: "foreign-key", disposition: "accepted", reason: "ACCEPTED" },
      answer: { text: "Foreign content", nextStep: "none", readRef: "read-ref-foreign", parentConsumed: false },
    });
    render(<App />); await panel();
    fireEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(f.host.binding.port.readQualifiedAnswer).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("region", { name: "Qualified original answer" })).toBeNull();
    expect(f.saved()).toEqual(pointer);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it('holds SEND on unreadable pointer storage instead of inferring absence',async()=>{
    const f=fixture(); vi.mocked(f.store.read).mockRejectedValue(new Error('private store failure'));render(<App/>);await panel();
    await screen.findByRole('button',{name:'Check status'});
    expect(screen.queryByText('private store failure')).toBeNull();
    fireEvent.change(screen.getByLabelText('What would you like done?'),{target:{value:'Continue'}});
    fireEvent.change(screen.getByLabelText('How will we know it is done?'),{target:{value:'done'}});
    expect((screen.getByRole('button',{name:'Send'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Check status'}));
    await waitFor(()=>expect(f.store.read).toHaveBeenCalledTimes(2));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Check status'})).toBeTruthy());
    expect(screen.getByText('POINTER_READ_UNAVAILABLE')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Send'}) as HTMLButtonElement).disabled).toBe(true);
    expect(f.transport.send).not.toHaveBeenCalled();
  });
  it('shows a safe local reservation refusal and retains the typed draft with zero SEND',async()=>{
    const f=fixture();vi.mocked(f.store.reserve).mockRejectedValue(new Error('private write failure'));
    render(<App/>);await panel();await enter();
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toBe('STORE_WRITE_FAILED');
    expect(screen.queryByText('private write failure')).toBeNull();
    expect((screen.getByLabelText('What would you like done?') as HTMLTextAreaElement).value).toBe('Continue this selected slice');
    expect(f.transport.send).not.toHaveBeenCalled();expect(f.saved()).toBeNull();
  });
  it('requalifies an expired unchanged selection before original-key status recovery',async()=>{
    let expire:(()=>void)|undefined;
    const timeout=globalThis.setTimeout;
    vi.spyOn(globalThis,'setTimeout').mockImplementation(((handler:TimerHandler,delay?:number,...args:unknown[])=>{
      if(typeof handler==='function' && delay && delay>300000) expire=handler as ()=>void;
      return timeout(handler,delay,...args);
    }) as typeof setTimeout);
    const f=fixture(pointer,false);render(<App/>);await panel();
    await screen.findByRole('button',{name:'Check status'});
    expect(expire).toBeTypeOf('function');
    const reads=vi.mocked(f.transport.context).mock.calls.length;
    await act(async()=>expire!());
    fireEvent.click(await screen.findByRole('button',{name:'Refresh session capability'}));
    await screen.findByRole('button',{name:'Check status'});
    expect(f.transport.context).toHaveBeenCalledTimes(reads+1);
    fireEvent.click(screen.getByRole('button',{name:'Check status'}));
    await waitFor(()=>expect(f.transport.reply).toHaveBeenCalledTimes(1));
    expect(f.transport.reply).toHaveBeenCalledWith({operation_key:KEY},expect.any(AbortSignal));
    expect(f.transport.send).not.toHaveBeenCalled();expect(f.saved()).toEqual(pointer);
  });
  it('fences same-value history events and A-B-A before a delayed reservation commits',async()=>{
    const f=fixture(); const reserve=deferred<{reserved:true}>();
    const commit=vi.mocked(f.store.reserve).getMockImplementation()!;
    vi.mocked(f.store.reserve).mockImplementation(async (scope,pointer)=>{await reserve.promise; return commit(scope,pointer);});
    render(<App/>);await panel();await enter();fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(f.store.reserve).toHaveBeenCalledTimes(1));
    const before=vi.mocked(f.transport.context).mock.calls.length;
    await act(async()=>{ window.dispatchEvent(new PopStateEvent('popstate')); history.replaceState(null,'','/os/?work_ref=WS%3AOTHER&root_job_id=JOB-1'); window.dispatchEvent(new PopStateEvent('popstate')); history.replaceState(null,'','/os/?work_ref=WS%3AALPHA&root_job_id=JOB-1'); window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(vi.mocked(f.transport.context).mock.calls.length).toBe(before+3);
    await act(async()=>{reserve.resolve({reserved:true});await reserve.promise;});
    expect(f.transport.send).not.toHaveBeenCalled();
    expect(f.saved()).toEqual(pointer);
    expect(screen.queryByText(/Continuation committed/)).toBeNull();
  });
  it('ignores delayed store discovery after an identical-state authentication generation changes',async()=>{
    const f=fixture();const read=deferred<OperationPointer|null>();vi.mocked(f.store.read).mockReturnValueOnce(read.promise);
    render(<App/>);await panel();await waitFor(()=>expect(f.store.read).toHaveBeenCalledTimes(1));
    await act(async()=>f.notifyAuth());
    await act(async()=>{read.resolve(pointer);await read.promise;});
    expect(screen.queryByText(KEY)).toBeNull();expect(f.transport.reply).not.toHaveBeenCalled();expect(f.transport.send).not.toHaveBeenCalled();
  });
  it('reopens historical A inside actual Conversations after a reload while pending B remains untouched', async () => {
    const f=fixture(pointer,false,true,true);
    const qualified=vi.spyOn(f.host.binding.port,'readQualifiedAnswer').mockImplementation(async (candidate)=>{
      expect(candidate.operationKey).toBe(HIST_OP_A);
      expect(candidate.targetKey).toBe(REF);
      return {receipt:{...candidate,disposition:'accepted',reason:'ACCEPTED'},
        answer:{text:'Historical A recovered on the real Conversations screen.',
          nextStep:'B stays pending.',readRef:HIST_READ_A,parentConsumed:false}};
    });
    const first=render(<App/>); await panel();
    fireEvent.click(await screen.findByRole('button',{name:/Open original request/}));
    const original=await screen.findByText('Historical A recovered on the real Conversations screen.');
    expect(original.closest('.conversation-window')).not.toBeNull();
    expect(f.saved()).toEqual(pointer); // B survives A's unrelated READ.
    expect(f.transport.send).not.toHaveBeenCalled();
    expect(f.store.reserve).not.toHaveBeenCalled();
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    first.unmount();

    // App component remount mimics the user-facing reload composition. The
    // separately tested IndexedDB test covers durable persistence across
    // actual pending-store reopen, which this UI fixture intentionally mocks.
    render(<App/>); await panel();
    fireEvent.click(await screen.findByRole('button',{name:/Open original request/}));
    expect(await screen.findByText('Historical A recovered on the real Conversations screen.')).toBeTruthy();
    expect(f.saved()).toEqual(pointer);
    expect(f.transport.send).not.toHaveBeenCalled();
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    expect(qualified).toHaveBeenCalledTimes(2);
    expect(qualified.mock.calls.every(([candidate])=>candidate.operationKey===HIST_OP_A)).toBe(true);
  });

  it('places one actual Session inside Conversations and preserves its explicit pair across passive read and presentation changes',async()=>{
    const f=fixture(null,true,true); const view=render(<App/>); await panel(); await enter();
    const instruction=screen.getByLabelText('What would you like done?') as HTMLTextAreaElement;
    const condition=screen.getByLabelText('How will we know it is done?') as HTMLTextAreaElement;
    expect(screen.getAllByLabelText('Session continuation')).toHaveLength(1);
    expect(instruction.closest('.conversation-window')).not.toBeNull();
    expect(screen.getByRole('button',{name:'Unsent notes'}).getAttribute('aria-expanded')).toBe('false');
    instruction.focus();
    view.rerender(<App locale="zh-CN" theme="light"/>);
    expect(screen.getByLabelText('你希望完成什么？')).toBe(instruction);
    expect(screen.getByLabelText('达到什么条件才算完成？')).toBe(condition);
    expect(instruction.value).toBe('Continue this selected slice');
    expect(condition.value).toBe('Owner confirms the slice');
    expect(document.activeElement).toBe(instruction);
    // The passive observation body may re-key; the independent Session owner has not changed.
    const observedReads=f.readCurrentWindow.mock.calls.length;
    fireEvent.click(screen.getByRole('button',{name:'Refresh observed window'}));
    await waitFor(()=>expect(f.readCurrentWindow).toHaveBeenCalledTimes(observedReads+1));
    view.rerender(<App/>);
    expect(screen.getByLabelText('What would you like done?')).toBe(instruction);
    expect(f.transport.send).not.toHaveBeenCalled();
    const before=vi.mocked(f.transport.context).mock.calls.length;
    await act(async()=>window.dispatchEvent(new PopStateEvent('popstate')));
    await waitFor(()=>expect(f.transport.context).toHaveBeenCalledTimes(before+1));
    await panel(); // Selection navigation returns the shell to its canonical default view.
    await waitFor(()=>expect(screen.getByLabelText('What would you like done?')).not.toBe(instruction));
    expect((screen.getByLabelText('What would you like done?') as HTMLTextAreaElement).value).toBe('');
    expect(f.transport.send).not.toHaveBeenCalled();
  });

});
