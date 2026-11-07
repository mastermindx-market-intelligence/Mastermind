// @vitest-environment jsdom
//
// PlanAdoptionReview consumer tests over the ACTUAL OperationController.
//
// The controller under test is the real class from
// ../orchestration/operation-controller. The injected FiniteCommandPort and
// PendingPointerStore are inert, atomic, in-memory test doubles: they record
// calls, script receipts and hold pointers, and they have no timers, no
// network, no persistence and no live effects of their own. The producer port
// behavior and the controller are never mocked — only their inputs and outputs
// are scripted here.
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { OperationController } from "../orchestration/operation-controller";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "../orchestration/operation-controller";
import { PlanAdoptionReview } from "./PlanAdoptionReview";
import type { PlanAdoptionBinding, PlanAdoptionPrepared } from "./PlanAdoptionReview";
import type { PlanAdoptionRequest } from "./plan-adoption-request";

afterEach(() => cleanup());

// ── Inert typed port ─────────────────────────────────────────────────────────

/** Records calls and scripts receipts. No timers, no transport, no effects. */
class ScriptedPort implements FiniteCommandPort {
  readonly prepares: CommandIntent[] = [];
  readonly submits: Array<{ pointer: OperationPointer; intent: CommandIntent; signal: AbortSignal }> = [];
  readonly reads: Array<{ pointer: OperationPointer; signal: AbortSignal }> = [];
  readonly advances: Array<{pointer:OperationPointer;digest:string}> = [];
  advanceImpl: (pointer:OperationPointer,digest:string)=>Promise<EffectReceipt> = async pointer => receiptFor(pointer,"unknown");
  contextValue: OwnerContext | null = { principalScope: "principal-scope-a", generation: "gen-1" };
  submitImpl: (pointer: OperationPointer, intent: CommandIntent) => Promise<EffectReceipt> = async () => {
    throw new Error("NO_SCRIPTED_RECEIPT");
  };
  readImpl: (pointer: OperationPointer) => Promise<EffectReceipt> = async () => {
    throw new Error("NO_SCRIPTED_RECEIPT");
  };

  context(): OwnerContext | null {
    return this.contextValue;
  }

  prepare(intent: CommandIntent): OperationPointer {
    this.prepares.push(intent);
    return { operationKey: String((intent.payload.request as PlanAdoptionRequest).request_id), kind: intent.kind, targetKey: intent.targetKey };
  }

  submit(pointer: OperationPointer, intent: CommandIntent, signal: AbortSignal): Promise<EffectReceipt> {
    this.submits.push({ pointer, intent, signal });
    return this.submitImpl(pointer, intent);
  }

  advanceOperation(pointer:OperationPointer,digest:string,_signal:AbortSignal):Promise<EffectReceipt> {
    this.advances.push({pointer,digest}); return this.advanceImpl(pointer,digest);
  }

  readOperation(pointer: OperationPointer, signal: AbortSignal): Promise<EffectReceipt> {
    this.reads.push({ pointer, signal });
    return this.readImpl(pointer);
  }
}

// ── Inert atomic in-memory pointer store ─────────────────────────────────────

/**
 * Faithful inert PendingPointerStore: reserve never overwrites and returns the
 * existing pointer back, clearIfEqual deletes only the exact pointer, and
 * every answer is a plain value or promise — never an effect.
 */
class MemoryPointerStore implements PendingPointerStore {
  reserveCalls = 0;
  clearCalls = 0;
  readonly #pointers = new Map<string, OperationPointer>();

  read(principalScope: string): OperationPointer | null {
    return this.#pointers.get(principalScope) ?? null;
  }

  reserve(
    principalScope: string,
    pointer: OperationPointer,
  ): { readonly reserved: true } | { readonly reserved: false; readonly pointer: OperationPointer } {
    this.reserveCalls += 1;
    const existing = this.#pointers.get(principalScope);
    if (existing) return { reserved: false, pointer: existing };
    this.#pointers.set(principalScope, { ...pointer });
    return { reserved: true };
  }

  clearIfEqual(principalScope: string, pointer: OperationPointer): boolean {
    this.clearCalls += 1;
    const existing = this.#pointers.get(principalScope);
    if (
      !existing ||
      existing.operationKey !== pointer.operationKey ||
      existing.kind !== pointer.kind ||
      existing.targetKey !== pointer.targetKey
    ) {
      return false;
    }
    this.#pointers.delete(principalScope);
    return true;
  }

  peek(principalScope: string): OperationPointer | null {
    return this.#pointers.get(principalScope) ?? null;
  }
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

/** The exact prepared request fixture (canonical compiler capture shape). */
function requestFixture(): PlanAdoptionRequest {
  return {
    schema: "agentos.plan_adoption_request.v1",
    request_id: "mmos-project-adopt-1111111111111111111111111111111111111111",
    work_ref: "WS:PLAN-TEST",
    expected_commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    expected_adoption: "DEC:PLAN-FIRST",
    proposal_source: {
      repository: "mastermindx-market-intelligence/macro",
      path: "planning/proposal.md",
      commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      content_sha256: "b69ebf6fd58208ecd77df079c9aba30095f096bf2d7138ba339d484493a2a872",
    },
    base_source: {
      repository: "mastermindx-market-intelligence/macro",
      path: "planning/base.md",
      commit: "cccccccccccccccccccccccccccccccccccccccc",
      content_sha256: "ed3b8e42d76ccbf1ef084870250ecd744db8e64e42746e0412f25bb87ef76130",
    },
    candidate_sha256: "5ff031df7d920e7267181542f54013a09bd04c545a90ae84514237b1d96f0a09",
  };
}

function receiptFor(pointer: OperationPointer, disposition: EffectReceipt["disposition"]): EffectReceipt {
  return { operationKey: pointer.operationKey, kind: pointer.kind, targetKey: pointer.targetKey, disposition };
}

// ── Harness ──────────────────────────────────────────────────────────────────

interface Harness {
  view: RenderResult;
  controller: OperationController;
  port: ScriptedPort;
  store: MemoryPointerStore;
  prepared: PlanAdoptionPrepared;
  binding: PlanAdoptionBinding;
  request: PlanAdoptionRequest;
  setCurrent(value: boolean): void;
  setCanAdopt(value: boolean): void;
  setCanInspect(value: boolean): void;
  setGeneration(value: string): void;
  setContext(value: OwnerContext | null): void;
  rerender(): void;
}

const PREVIEW_TEXT = "supplied-comparison-content";

function mountHarness(options?: {
  locale?: "en" | "zh-CN";
  prepared?: boolean;
  controller?: OperationController;
  store?: MemoryPointerStore;
}): Harness {
  const port = new ScriptedPort();
  const store = options?.store ?? new MemoryPointerStore();
  const controller = options?.controller ?? new OperationController(port, store);
  const request = requestFixture();
  let current = true;
  let canAdopt = true;
  let canInspect = true;
  const withPrepared = options?.prepared !== false;
  const prepared: PlanAdoptionPrepared = {
    request,
    preview: <div>{PREVIEW_TEXT}</div>,
    isCurrent: () => current,
  };
  const binding: PlanAdoptionBinding = {
    controller,
    context: () => port.contextValue,
    canAdopt: () => canAdopt,
    canInspect: () => canInspect,
  };
  const element = () => (
    // A fresh element per render: an identical element object would let React
    // bail out of re-rendering entirely.
    <PlanAdoptionReview workRef="WS:PLAN-TEST" prepared={withPrepared ? prepared : undefined} binding={binding} locale={options?.locale} />
  );
  const view = render(element());
  return {
    view,
    controller,
    port,
    store,
    prepared,
    binding,
    request,
    setCurrent: (value) => {
      current = value;
    },
    setCanAdopt: (value) => {
      canAdopt = value;
    },
    setCanInspect: (value) => {
      canInspect = value;
    },
    setGeneration: (value) => {
      port.contextValue = { principalScope: "principal-scope-a", generation: value };
    },
    setContext: (value) => {
      port.contextValue = value;
    },
    rerender: () => {
      view.rerender(element());
    },
  };
}

function openReview(): void {
  fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("PlanAdoptionReview", () => {
  it("opens and closes the local review with zero operation calls", async () => {
    const h = mountHarness();
    expect(h.port.submits).toHaveLength(0);
    expect(h.port.reads).toHaveLength(0);
    expect(h.port.prepares).toHaveLength(0);
    expect(h.store.reserveCalls).toBe(0);
    expect(h.store.clearCalls).toBe(0);

    openReview();
    expect(await screen.findByText(PREVIEW_TEXT)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Adopt this plan" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Close review" }));
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    // Reviewing and closing are pure UI changes: no begin, no recover, no
    // store reservation, no pointer clear.
    expect(h.port.submits).toHaveLength(0);
    expect(h.port.reads).toHaveLength(0);
    expect(h.port.prepares).toHaveLength(0);
    expect(h.store.reserveCalls).toBe(0);
    expect(h.store.clearCalls).toBe(0);
  });

  it("submits exactly once on explicit adopt with the same detached request", async () => {
    const h = mountHarness();
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    await waitFor(() => expect(h.port.submits).toHaveLength(1));

    const call = h.port.submits[0];
    expect(call.intent.kind).toBe("project_adopt");
    expect(call.intent.targetKey).toBe("WS:PLAN-TEST");
    expect(call.intent.payload.action).toBe("ADOPT_PLAN");
    const sent = call.intent.payload.request as PlanAdoptionRequest;
    expect(sent).not.toBe(h.request);
    expect(sent.request_id).toBe("mmos-project-adopt-1111111111111111111111111111111111111111");
    expect(sent).toEqual(requestFixture());
    expect(call.pointer.operationKey).toBe(sent.request_id);

    // A click while the first explicit attempt is still awaiting must not
    // create a second submission.
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(h.port.submits).toHaveLength(1);

    // Later mutation of the prepared prop cannot affect the submitted intent.
    (h.prepared.request as { expected_commit: string }).expected_commit = "mutated-after-render";
    expect((call.intent.payload.request as PlanAdoptionRequest).expected_commit).toBe(
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    );
    expect(h.port.submits).toHaveLength(1);
    // The intent went through the controller's real begin path exactly once.
    expect(h.port.prepares).toHaveLength(1);
    expect(h.store.reserveCalls).toBe(1);
  });

  it("fails closed on a dynamic denial even without a rerender", async () => {
    const h = mountHarness();
    openReview();
    h.setCanAdopt(false);
    // No rerender happened: the click handler still rechecks the live
    // predicate and refuses to submit.
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(h.port.submits).toHaveLength(0);
    expect(h.store.reserveCalls).toBe(0);

    h.rerender();
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
    expect(h.port.submits).toHaveLength(0);
    expect(screen.getByText(/Adoption is not currently permitted/i)).toBeTruthy();
  });

  it("treats a throwing adopt permission as no permission", async () => {
    const h = mountHarness();
    openReview();
    const strictBinding: PlanAdoptionBinding = {
      controller: h.controller,
      context: () => h.port.contextValue,
      canAdopt: () => {
        throw new Error("permission lookup exploded");
      },
      canInspect: () => true,
    };
    h.view.rerender(<PlanAdoptionReview workRef="WS:PLAN-TEST" prepared={h.prepared} binding={strictBinding} />);
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
    expect(h.port.submits).toHaveLength(0);
    expect(h.store.reserveCalls).toBe(0);
  });

  it("masks a changed request, a moved generation and a lost context", async () => {
    const h = mountHarness();
    openReview();
    expect(await screen.findByText(PREVIEW_TEXT)).toBeTruthy();

    // The parent supplies a different prepared request: the frozen identity no
    // longer matches, so the preview closes immediately and no submit path
    // remains.
    const other = requestFixture();
    (other as { expected_commit: string }).expected_commit = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    h.view.rerender(<PlanAdoptionReview workRef="WS:PLAN-TEST" prepared={{ ...h.prepared, request: other }} binding={h.binding} />);
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    expect(screen.getByText(/no longer matches the current request/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
    expect(h.port.submits).toHaveLength(0);

    // Returning to the prior request requires a fresh explicit review.
    h.view.rerender(<PlanAdoptionReview workRef="WS:PLAN-TEST" prepared={h.prepared} binding={h.binding} />);
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    openReview();
    expect(await screen.findByText(PREVIEW_TEXT)).toBeTruthy();

    // Authentication epoch moves before the click: no rerender, no submit.
    h.setGeneration("gen-2");
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(h.port.submits).toHaveLength(0);
    h.rerender();
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    expect(screen.getByText(/no longer matches the current request/i)).toBeTruthy();

    // A completely absent context is unavailable, not a grant.
    h.setContext(null);
    h.rerender();
    expect(screen.getByText(/Plan adoption is unavailable/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
    expect(h.port.submits).toHaveLength(0);
  });

  it("settles an unknown outcome only through explicit recover, with zero extra submits", async () => {
    const h = mountHarness();
    h.port.submitImpl = async (pointer) => receiptFor(pointer, "unknown");
    h.port.readImpl = async (pointer) => receiptFor(pointer, "unknown");
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(await screen.findByText(/not known yet/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    await waitFor(() => expect(h.port.reads).toHaveLength(1));
    expect(await screen.findByText(/not known yet/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    await waitFor(() => expect(h.port.reads).toHaveLength(2));
    expect(screen.getByText(/not known yet/i)).toBeTruthy();
    // Observation only: recover never re-submits the adoption.
    expect(h.port.submits).toHaveLength(1);
  });

  it("closing while pending never cancels the operation", async () => {
    const h = mountHarness();
    let release!: (value: EffectReceipt) => void;
    h.port.submitImpl = async (pointer) =>
      new Promise<EffectReceipt>((resolve) => {
        release = (value) => resolve(value);
        void pointer;
      });
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    await waitFor(() => expect(h.port.submits).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Close review" }));
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    // Closing the review is UI only: the in-flight effect keeps its signal and
    // the durable hint stays reserved.
    expect(h.port.submits[0].signal.aborted).toBe(false);
    expect(h.store.peek("principal-scope-a")).not.toBeNull();

    release(receiptFor(h.port.submits[0].pointer, "accepted"));
    expect(await screen.findByText(/Publication of the original adoption is confirmed/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(1);
    expect(h.store.peek("principal-scope-a")).toBeNull();
  });

  it("reports publication without replacing the supplied baseline", async () => {
    const h = mountHarness();
    h.port.submitImpl = async (pointer) => receiptFor(pointer, "accepted");
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(await screen.findByText(/Refresh the plan to read its recorded adoption decision/i)).toBeTruthy();
    // The presenter never claims the supplied compare content became current,
    // and only the controller's own terminal clear touched the store.
    expect(screen.queryByText(/is now current/i)).toBeNull();
    expect(h.store.clearCalls).toBe(1);

    // The supplied preview slot stays exactly as provided, and the settled
    // plan cannot be adopted again from this review.
    expect(screen.getByText(PREVIEW_TEXT)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Adopt this plan" })).toHaveProperty("disabled", true);
    expect(h.port.submits).toHaveLength(1);
  });

  it("hides a late response after an authentication change", async () => {
    const h = mountHarness();
    let release!: (value: EffectReceipt) => void;
    h.port.submitImpl = async (pointer) =>
      new Promise<EffectReceipt>((resolve) => {
        release = (value) => resolve(value);
        void pointer;
      });
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    await waitFor(() => expect(h.port.submits).toHaveLength(1));

    // The auth epoch moves while the receipt is in flight; the response
    // belongs to a session this surface no longer shows.
    h.setGeneration("gen-2");
    await act(async () => {
      release(receiptFor(h.port.submits[0].pointer, "accepted"));
    });
    h.rerender();
    expect(screen.queryByText(/Submitting this adoption/i)).toBeNull();
    expect(screen.queryByText(/Publication of the original adoption/i)).toBeNull();
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
    // The operation was never claimed cancelled: the durable hint stays in its
    // original scope and an explicit check stays available under the new epoch.
    expect(h.store.peek("principal-scope-a")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Check original operation" })).toHaveProperty("disabled", false);
    expect(h.port.submits).toHaveLength(1);
  });

  it("publishes nothing after unmount and never claims cancellation", async () => {
    const h = mountHarness();
    let release!: (value: EffectReceipt) => void;
    h.port.submitImpl = async (pointer) =>
      new Promise<EffectReceipt>((resolve) => {
        release = (value) => resolve(value);
        void pointer;
      });
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    await waitFor(() => expect(h.port.submits).toHaveLength(1));
    h.view.unmount();

    await act(async () => {
      release(receiptFor(h.port.submits[0].pointer, "accepted"));
    });
    // Unmount prevented local publication; it claimed no cancellation — the
    // real effect settled through the controller regardless, and the submit
    // signal was never aborted by this surface.
    expect(h.port.submits[0].signal.aborted).toBe(false);
    expect(h.store.peek("principal-scope-a")).toBeNull();

    // A reopened surface inherits nothing from the unmounted instance: no
    // getState on mount, so nothing is published without an awaited call.
    mountHarness({ controller: h.controller, store: h.store });
    expect(screen.queryByText(/Publication of the original adoption/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Check original operation" })).toBeTruthy();
  });

  it("never claims a different work or kind as this plan's result", async () => {
    const h = mountHarness();
    h.store.reserve("principal-scope-a", {
      operationKey: "op-foreign-private",
      kind: "message",
      targetKey: "WS:OTHER-PLAN",
    });
    h.port.readImpl = async (pointer) => receiptFor(pointer, "accepted");

    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    expect(await screen.findByText(/has settled/i)).toBeTruthy();
    expect(screen.getByText(/no matching plan-adoption receipt/i)).toBeTruthy();
    expect(screen.queryByText(/Publication of the original adoption/i)).toBeNull();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("op-foreign-private");
    expect(text).not.toContain("WS:OTHER-PLAN");
    expect(h.port.submits).toHaveLength(0);
    h.view.unmount();

    // A still-unresolved foreign pointer holds this surface: no new adoption
    // may start, and its identity stays private. A fresh controller runs over
    // the same durable store.
    const second = mountHarness({ store: h.store });
    second.store.reserve("principal-scope-a", {
      operationKey: "op-foreign-private-2",
      kind: "stop",
      targetKey: "WS:OTHER-PLAN",
    });
    second.port.readImpl = async (pointer) => receiptFor(pointer, "unknown");
    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    expect(await screen.findByText(/not this plan's adoption is still being resolved/i)).toBeTruthy();
    openReview();
    expect(screen.getByRole("button", { name: "Adopt this plan" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(second.port.submits).toHaveLength(0);
    const text2 = document.body.textContent ?? "";
    expect(text2).not.toContain("op-foreign-private-2");
    expect(text2).not.toContain("WS:OTHER-PLAN");
  });

  it("mounts with zero calls and offers an explicit check on reopening", async () => {
    const h = mountHarness();
    expect(h.port.reads).toHaveLength(0);
    expect(h.port.submits).toHaveLength(0);
    expect(h.store.reserveCalls).toBe(0);
    const check = screen.getByRole("button", { name: "Check original operation" });
    expect(check).toHaveProperty("disabled", false);
    fireEvent.click(check);
    // The store was empty, so recover found no pointer at all: the truthful
    // answer is "nothing recorded", no submit was invented and no port call
    // was needed to say so.
    expect(await screen.findByText(/No pending adoption was found on this device/i)).toBeTruthy();
    expect(h.port.reads).toHaveLength(0);
    expect(h.port.submits).toHaveLength(0);
    h.view.unmount();

    const denied = mountHarness();
    denied.setCanInspect(false);
    denied.rerender();
    expect(screen.getByRole("button", { name: "Check original operation" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    expect(denied.port.reads).toHaveLength(0);
  });

  it("offers the explicit check even without a prepared payload", async () => {
    const h = mountHarness({ prepared: false });
    expect(screen.getByText(/No prepared comparison was supplied/i)).toBeTruthy();
    // No prepared payload means no review and no submit path; the truthful
    // buttons stay disabled rather than pretending a grant.
    expect(screen.getByRole("button", { name: "Review plan" })).toHaveProperty("disabled", true);
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();

    // A recorded pointer for the same scope resolves through recover; without
    // a prepared plan it is never claimed as this plan's result.
    h.store.reserve("principal-scope-a", {
      operationKey: "mmos-project-adopt-" + "2".repeat(40),
      kind: "project_adopt",
      targetKey: "WS:PLAN-TEST",
    });
    h.port.readImpl = async (pointer) => receiptFor(pointer, "unknown");
    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    await waitFor(() => expect(h.port.reads).toHaveLength(1));
    expect(await screen.findByText(/not known yet/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(0);
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("mmos-project-adopt-" + "2".repeat(40));
  });

  it("routes an existing same-work pointer to checking without a second submit", async () => {
    const h = mountHarness();
    h.store.reserve("principal-scope-a", {
      operationKey: "mmos-project-adopt-" + "3".repeat(40),
      kind: "project_adopt",
      targetKey: "WS:PLAN-TEST",
    });
    h.port.readImpl = async (pointer) => receiptFor(pointer, "unknown");
    openReview();
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(await screen.findByText(/original adoption is pending/i)).toBeTruthy();
    // The real controller refused to submit over the pending pointer.
    expect(h.port.submits).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Check original operation" }));
    await waitFor(() => expect(h.port.reads).toHaveLength(1));
    expect(await screen.findByText(/not known yet/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(0);
  });

  it("fails closed without an owner context or with a malformed one", () => {
    const h = mountHarness();
    h.setContext(null);
    h.rerender();
    expect(screen.getByText(/Plan adoption is unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Check original operation" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Review plan" })).toHaveProperty("disabled", true);

    h.setContext({ principalScope: "principal-scope-a", generation: "" });
    h.rerender();
    expect(screen.getByText(/Plan adoption is unavailable/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(0);
    expect(h.port.reads).toHaveLength(0);
  });

  it("renders the whole surface in zh-CN on request", async () => {
    const h = mountHarness({ locale: "zh-CN" });
    expect(screen.getByRole("button", { name: "审查计划" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "检查原始操作" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Review plan" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "审查计划" }));
    expect(await screen.findByText(PREVIEW_TEXT)).toBeTruthy();
    expect(screen.getByRole("button", { name: "采纳此计划" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "关闭审查" })).toBeTruthy();
    expect(screen.getByText("规划来源")).toBeTruthy();
    expect(screen.getByText("计划目标")).toBeTruthy();

    h.port.submitImpl = async (pointer) => receiptFor(pointer, "refused");
    fireEvent.click(screen.getByRole("button", { name: "采纳此计划" }));
    expect(await screen.findByText(/此采纳请求已被拒绝/)).toBeTruthy();
    expect(h.port.submits).toHaveLength(1);
    expect(h.port.submits[0].intent.kind).toBe("project_adopt");
    expect(h.port.submits[0].intent.targetKey).toBe("WS:PLAN-TEST");
    expect(h.port.submits[0].intent.payload.action).toBe("ADOPT_PLAN");
  });

  it("keeps raw identifiers behind the closed disclosure only", () => {
    const h = mountHarness();
    openReview();
    const facts = document.querySelector("dl.mm-plan-adoption__facts");
    expect(facts).toBeTruthy();
    const factsText = facts!.textContent ?? "";
    expect(factsText).toContain("WS:PLAN-TEST");
    expect(factsText).toContain("DEC:PLAN-FIRST");
    expect(factsText).not.toContain("mmos-project-adopt-");
    expect(factsText).not.toContain("5ff031df7d920e7267181542f54013a09bd04c545a90ae84514237b1d96f0a09");
    const details = document.querySelector("details.mm-plan-adoption__ids") as HTMLDetailsElement | null;
    expect(details).toBeTruthy();
    // Closed by default; the identifiers live only inside it.
    expect(details!.open).toBe(false);
    expect((details!.textContent ?? "")).toContain(
      "mmos-project-adopt-1111111111111111111111111111111111111111",
    );
    expect((details!.textContent ?? "")).toContain("5ff031df7d920e7267181542f54013a09bd04c545a90ae84514237b1d96f0a09");
    expect(h.port.submits).toHaveLength(0);
  });
});

describe("adoption consumer source/phase integration", () => {
  it("masks every prepared source fact when context is revoked", () => {
    const h = mountHarness(); openReview();
    expect(document.body.textContent).toContain(h.request.proposal_source.path);
    h.setContext(null); h.rerender();
    expect(document.body.textContent).not.toContain(h.request.proposal_source.path);
    expect(document.body.textContent).not.toContain(h.request.expected_adoption);
    expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
  });
  it("requires inspection permission at the adopt click even without rerender", () => {
    const h = mountHarness(); openReview(); h.setCanInspect(false);
    fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(h.port.submits).toHaveLength(0);
    h.rerender(); expect(screen.queryByText(PREVIEW_TEXT)).toBeNull();
  });
  it("does not turn an exception after submission into a no-dispatch claim", async () => {
    const h = mountHarness();
    h.port.submitImpl = async pointer => {
      h.port.context = () => { throw new Error("synthetic private context error"); };
      return receiptFor(pointer, "accepted");
    };
    openReview(); fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
    expect(await screen.findByText(/outcome is not known yet/i)).toBeTruthy();
    expect(h.port.submits).toHaveLength(1);
    expect(h.store.peek("principal-scope-a")).not.toBeNull();
    expect(document.body.textContent).not.toContain("not submitted");
    expect(document.body.textContent).not.toContain("synthetic private");
    expect(screen.getByRole("button", { name: "Adopt this plan" })).toHaveProperty("disabled", true);
  });
  it("reopens and advances the SAME settled-phase operation without a prepared payload", async () => {
    const h = mountHarness({prepared:false});
    const pointer:OperationPointer = {kind:"project_adopt",targetKey:"WS:PLAN-TEST",operationKey:"mmos-project-adopt-"+"4".repeat(40)};
    h.store.reserve("principal-scope-a",pointer);
    const digest = "e".repeat(64);
    h.port.readImpl = async p => ({...receiptFor(p,"unknown"),reason:"READY_FOR_ADVANCE",advance:{phase_receipt_digest:digest}});
    h.port.advanceImpl = async p => receiptFor(p,"refused");
    fireEvent.click(screen.getByRole("button", {name:"Check original operation"}));
    const advance = await screen.findByRole("button", {name:"Continue original adoption"});
    expect(h.port.advances).toHaveLength(0);
    fireEvent.click(advance);
    await waitFor(()=>expect(h.port.advances).toHaveLength(1));
    expect(h.port.advances[0]).toEqual({pointer,digest});
    expect(h.port.reads).toHaveLength(2);
    expect(h.port.submits).toHaveLength(0);
    expect(h.port.prepares).toHaveLength(0);
    expect(h.store.peek("principal-scope-a")).toEqual(pointer);
    expect(h.store.clearCalls).toBe(0);
    expect(await screen.findByText(/outcome is not known yet/i)).toBeTruthy();
  });
  it("does not enable advance for an unobserved unknown phase", async () => {
    const h=mountHarness({prepared:false});
    h.store.reserve("principal-scope-a",{kind:"project_adopt",targetKey:"WS:PLAN-TEST",operationKey:"mmos-project-adopt-"+"5".repeat(40)});
    h.port.readImpl=async p=>receiptFor(p,"unknown");
    fireEvent.click(screen.getByRole("button",{name:"Check original operation"}));
    expect(await screen.findByText(/outcome is not known yet/i)).toBeTruthy();
    expect(screen.queryByRole("button",{name:"Continue original adoption"})).toBeNull();
    expect(h.port.advances).toHaveLength(0);
  });
  it("a missing local hint after unknown does not permit a replacement submit", async () => {
    const h=mountHarness();openReview();
    fireEvent.click(screen.getByRole("button",{name:"Adopt this plan"}));
    expect(await screen.findByText(/outcome is not known yet/i)).toBeTruthy();
    const pointer=h.store.peek("principal-scope-a")!;
    h.store.clearIfEqual("principal-scope-a",pointer); // external local hint loss only, no source outcome
    fireEvent.click(screen.getByRole("button",{name:"Check original operation"}));
    await waitFor(()=>expect(screen.getByRole("button",{name:"Check original operation"})).toHaveProperty("disabled",false));
    expect(screen.getByRole("button",{name:"Adopt this plan"})).toHaveProperty("disabled",true);
    expect(document.body.textContent).not.toContain("No operation was started");
    expect(h.port.submits).toHaveLength(1);
  });
});
