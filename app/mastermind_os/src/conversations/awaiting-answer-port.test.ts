import { describe, expect, it, vi } from "vitest";
import { OperationController, type CommandIntent, type EffectReceipt, type FiniteCommandPort,
  type OperationPointer, type PendingPointerStore } from "../orchestration/operation-controller";
import { createAwaitingAnswerPort, type QualifiedAnswerRead } from "./awaiting-answer-port";

const POINTER: OperationPointer = Object.freeze({ operationKey: "session-continue-" + "b".repeat(64), kind: "message", targetKey: "fabric_attempt:" + "a".repeat(64) });
const INTENT: CommandIntent = { kind: "message", targetKey: POINTER.targetKey, payload: { instruction: "a private instruction" } };
const receipt = (patch: Partial<EffectReceipt> = {}): EffectReceipt => ({ ...POINTER, disposition: "accepted", ...patch });
const ANSWER = Object.freeze({ text: "Qualified bounded reply", parent_consumed: false });
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; };
function fixture() {
  let generation = "1", current = true, saved: OperationPointer | null = null;
  const port: FiniteCommandPort = {
    context: () => ({ principalScope: "scope", generation }),
    prepare: vi.fn(() => POINTER),
    submit: vi.fn(async () => receipt()),
    readOperation: vi.fn(async () => receipt()),
  };
  const store: PendingPointerStore = {
    read: vi.fn(() => saved),
    reserve: vi.fn((_scope, pointer) => {
      if (saved) return { reserved: false as const, pointer: saved };
      saved = pointer; return { reserved: true as const };
    }),
    clearIfEqual: vi.fn((_scope, pointer) => {
      if (!saved || saved.operationKey !== pointer.operationKey || saved.kind !== pointer.kind || saved.targetKey !== pointer.targetKey) return false;
      saved = null; return true;
    }),
  };
  const readAnswer = vi.fn(async (_pointer: OperationPointer, _signal: AbortSignal): Promise<QualifiedAnswerRead<typeof ANSWER>> => ({ receipt: receipt(), answer: ANSWER }));
  const onAdmission = vi.fn(), onAnswer = vi.fn(
    (_pointer: OperationPointer, _answer: typeof ANSWER): boolean | Promise<boolean> => true,
  );
  const wrapped = createAwaitingAnswerPort({ port, readAnswer, isCurrent: p => current && p.targetKey === POINTER.targetKey, onAdmission, onAnswer });
  const controller = new OperationController(wrapped, store);
  return { controller, wrapped, port, store, readAnswer, onAdmission, onAnswer, saved: () => saved,
    changeOwner: () => { generation = "2"; }, changeTarget: () => { current = false; } };
}

describe("Office two-phase answer durability over the existing controller", () => {
  it("retains accepted SEND and blocks a second submission until the answer", async () => {
    const f = fixture();
    expect((await f.controller.begin(INTENT)).status).toBe("unknown");
    expect(f.onAdmission).toHaveBeenCalledWith(POINTER);
    expect(f.saved()).toEqual(POINTER);
    await f.controller.begin(INTENT);
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    expect(f.readAnswer).not.toHaveBeenCalled();
  });
  it("reads the original answer exactly once and clears only its hint", async () => {
    const f = fixture(); await f.controller.begin(INTENT);
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.readAnswer).toHaveBeenCalledWith(POINTER, expect.any(AbortSignal));
    expect(f.onAnswer).toHaveBeenCalledWith(POINTER, ANSWER);
    expect(f.readAnswer).toHaveBeenCalledTimes(1);
    expect(f.port.readOperation).not.toHaveBeenCalled();
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.saved()).toBeNull();
    expect(ANSWER.parent_consumed).toBe(false);
  });
  it("reopens the existing hint after response loss without another SEND", async () => {
    const f = fixture(); vi.mocked(f.port.submit).mockRejectedValue(new Error("private transport secret"));
    await f.controller.begin(INTENT);
    const reopened = new OperationController(f.wrapped, f.store);
    expect((await reopened.recover()).status).toBe("accepted");
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.readAnswer).toHaveBeenCalledTimes(1);
    expect(f.saved()).toBeNull();
    expect(JSON.stringify(reopened.getState())).not.toContain("private transport secret");
  });
  it("settles a proven pre-effect refusal without inventing an answer", async () => {
    const f = fixture(); vi.mocked(f.port.submit).mockResolvedValue(receipt({ disposition: "refused", reason: "private refusal" }));
    const state = await f.controller.begin(INTENT);
    expect(state.status).toBe("refused"); expect(state.reason).toBe("REFUSED");
    expect(f.saved()).toBeNull(); expect(f.onAdmission).not.toHaveBeenCalled(); expect(f.onAnswer).not.toHaveBeenCalled();
  });
  it.each(["null", "refused", "foreign key", "foreign target", "extra receipt field"])("retains pending request on %s answer", async name => {
    const f = fixture(); await f.controller.begin(INTENT);
    let observed: QualifiedAnswerRead<typeof ANSWER> = { receipt: receipt(), answer: ANSWER };
    if (name === "null") observed = { ...observed, answer: null };
    if (name === "refused") observed = { ...observed, receipt: receipt({ disposition: "refused" }) };
    if (name === "foreign key") observed = { ...observed, receipt: receipt({ operationKey: "other-operation" }) };
    if (name === "foreign target") observed = { ...observed, receipt: receipt({ targetKey: "other-target" }) };
    if (name === "extra receipt field") observed = { ...observed, receipt: { ...receipt(), text: "unqualified prose" } as EffectReceipt };
    f.readAnswer.mockResolvedValue(observed);
    expect((await f.controller.recover()).status).toBe("unknown");
    expect(f.saved()).toEqual(POINTER); expect(f.onAnswer).not.toHaveBeenCalled();
    expect(f.store.clearIfEqual).not.toHaveBeenCalled(); expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
  it("repeated reply loss never resubmits", async () => {
    const f = fixture(); await f.controller.begin(INTENT); f.readAnswer.mockRejectedValue(new Error("private answer secret"));
    await f.controller.recover(); await f.controller.recover();
    expect(f.readAnswer).toHaveBeenCalledTimes(2); expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.saved()).toEqual(POINTER); expect(f.onAnswer).not.toHaveBeenCalled();
    expect(JSON.stringify(f.controller.getState())).not.toContain("private answer secret");
  });
  it.each(["owner", "target"])("withholds delayed private answer after %s invalidation", async boundary => {
    const f = fixture(); await f.controller.begin(INTENT);
    const answer = deferred<QualifiedAnswerRead<typeof ANSWER>>(); f.readAnswer.mockReturnValue(answer.promise);
    const recovering = f.controller.recover();
    // Recovery first reads the incumbent atomic pointer before invoking the reader.
    await vi.waitFor(() => expect(f.readAnswer).toHaveBeenCalledTimes(1));
    if (boundary === "owner") f.changeOwner(); else f.changeTarget();
    answer.resolve({ receipt: receipt(), answer: ANSWER }); await recovering;
    expect(f.onAnswer).not.toHaveBeenCalled(); expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("does not publish admission after owner drift during SEND", async () => {
    const f = fixture(); const send = deferred<EffectReceipt>(); vi.mocked(f.port.submit).mockReturnValue(send.promise);
    const begin = f.controller.begin(INTENT); await vi.waitFor(() => expect(f.port.submit).toHaveBeenCalledTimes(1));
    f.changeOwner(); send.resolve(receipt()); await begin;
    expect(f.onAdmission).not.toHaveBeenCalled(); expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("refuses an aborted answer read before transport", async () => {
    const f = fixture(); const abort = new AbortController(); abort.abort();
    expect((await f.wrapped.readOperation(POINTER, abort.signal)).disposition).toBe("unknown");
    expect(f.readAnswer).not.toHaveBeenCalled(); expect(f.onAnswer).not.toHaveBeenCalled();
  });
  it.each(["false", "throw"])("holds the hint when local answer publication returns %s", async outcome => {
    const f = fixture(); await f.controller.begin(INTENT);
    if (outcome === "false") f.onAnswer.mockReturnValue(false); else f.onAnswer.mockImplementation(() => { throw new Error("private local error"); });
    expect((await f.controller.recover()).status).toBe("unknown"); expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("retains the hint when atomic clear fails after a qualified local read", async () => {
    const f = fixture(); await f.controller.begin(INTENT); vi.mocked(f.store.clearIfEqual).mockReturnValue(false);
    expect((await f.controller.recover()).status).toBe("unknown");
    expect(f.onAnswer).toHaveBeenCalledTimes(1); expect(f.saved()).toEqual(POINTER);
    expect(ANSWER.parent_consumed).toBe(false);
  });
  it("uses historical original key even after the owner advances its next key", async () => {
    const f = fixture(); await f.controller.begin(INTENT);
    vi.mocked(f.port.prepare).mockReturnValue({ ...POINTER, operationKey: "session-continue-" + "d".repeat(64) });
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.readAnswer.mock.calls[0][0].operationKey).toBe(POINTER.operationKey);
    expect(f.port.prepare).toHaveBeenCalledTimes(1); expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
});

describe("rendered answer acknowledgement", () => {
  it("retains the original pointer until the current view confirms its commit", async () => {
    const f = fixture(); await f.controller.begin(INTENT);
    const ack = deferred<boolean>();
    f.onAnswer.mockReturnValue(ack.promise);
    const recovering = f.controller.recover();
    await vi.waitFor(() => expect(f.onAnswer).toHaveBeenCalledTimes(1));
    expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    ack.resolve(true);
    expect((await recovering).status).toBe("accepted");
    expect(f.saved()).toBeNull();
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
  it("keeps its original pointer if a view unmounts before its async ack", async () => {
    const f = fixture(); await f.controller.begin(INTENT);
    const ack = deferred<boolean>();
    f.onAnswer.mockReturnValue(ack.promise);
    const recovering = f.controller.recover();
    await vi.waitFor(() => expect(f.onAnswer).toHaveBeenCalledTimes(1));
    ack.resolve(false);
    expect((await recovering).status).toBe("unknown");
    expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
  it("refuses pointer clearance when owner changes during the committed-view acknowledgement", async () => {
    const f = fixture(); await f.controller.begin(INTENT);
    const ack = deferred<boolean>();
    f.onAnswer.mockReturnValue(ack.promise);
    const recovering = f.controller.recover();
    await vi.waitFor(() => expect(f.onAnswer).toHaveBeenCalledTimes(1));
    f.changeOwner(); ack.resolve(true);
    // OperationController deliberately invalidates to IDLE on a changed
    // owner; the load-bearing invariant is zero stale acceptance/clear.
    expect((await recovering).status).not.toBe("accepted");
    expect(f.saved()).toEqual(POINTER);
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
  });
});
