// @vitest-environment jsdom
/**
 * React Testing Library integration tests for useFreshConversationJourney.
 *
 * Real imports only: the genuine hook, the genuine createFreshConversationBinding
 * over the incumbent OperationController, and an atomic in-memory
 * PendingPointerStore double. The consumer-controlled harness owns the
 * separate first-message draft; principal/host/availability values are named
 * synthetic identities. No App, host, native, network or provider effects.
 *
 * P16.T1.S34.S1 - tests only; implementation repair belongs to the parent.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import {
  useFreshConversationJourney,
  type FreshConversationJourneyProps,
} from "./useFreshConversationJourney";
import {
  createFreshConversationBinding,
  type ConversationCreateRequest,
  type ConversationPreviewRequest,
  type ConversationRequestSelection,
  type FreshConversationBinding,
} from "./fresh-conversation-command-binding";
import type {
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "../../orchestration/operation-controller";
import ownerFixtureJson from "./fixtures/fresh-conversation-owner.json";

/** Genuine imported fixture; typed at the single seam the tests consume. */
interface FreshOwnerFixture {
  readonly request: {
    readonly work_ref: string;
    readonly operation_key: string;
    readonly message: string;
  };
  readonly create_request: {
    readonly work_ref: string;
    readonly operation_key: string;
    readonly message: string;
    readonly preview_digest: string;
  };
  readonly preview: unknown;
  readonly create: unknown;
  readonly read: unknown;
}
const FIXTURE = ownerFixtureJson as unknown as FreshOwnerFixture;

const WORK_REF = "WS:ONE";
const PROJECT_TITLE = "One";
const MESSAGE = "  新对话\nRead source.  ";
const OWNER_SCOPE = "746ea62009ffa72215a1792dff1053e74f985463ecc1fbfe69a0744e3cf6e7c4";
const ORIGINAL_KEY = "mmos-conversation-create-0102030405060708090a0b0c0d0e0f1011121314";
const PREVIEW_DIGEST = "c0f93f2ce3a9800224631acd9a8fe0db1e1588c31ea26bea2222d83cdccdfa6d";

const ORIGINAL_POINTER: OperationPointer = {
  operationKey: ORIGINAL_KEY,
  kind: "conversation_create",
  targetKey: WORK_REF,
};
const FOREIGN_POINTER: OperationPointer = {
  operationKey: "mmos-launch-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  kind: "launch",
  targetKey: WORK_REF,
};

/** Deterministic 20-byte stream 01..14 reproduces the fixture canonical key. */
let mintCalls = 0;
function installDeterministicCrypto(): void {
  const stub = {
    getRandomValues: (target: Uint8Array): Uint8Array => {
      mintCalls += 1;
      if (target.length !== 20) throw new Error("synthetic crypto: expected 20-byte mint");
      for (let i = 0; i < target.length; i++) target[i] = i + 1;
      return target;
    },
  };
  vi.stubGlobal("crypto", stub);
}

interface PointerOp {
  readonly op: "read" | "reserve" | "clearIfEqual";
  readonly scope: string;
  readonly pointer: OperationPointer | null;
}

/** Atomic in-memory PendingPointerStore double: never overwrites a reservation. */
class MemoryPointerStore implements PendingPointerStore {
  readonly pointers = new Map<string, OperationPointer>();
  readonly ops: PointerOp[] = [];

  read(principalScope: string): Promise<OperationPointer | null> {
    this.ops.push({ op: "read", scope: principalScope, pointer: null });
    return Promise.resolve(this.pointers.get(principalScope) ?? null);
  }

  reserve(
    principalScope: string,
    pointer: OperationPointer,
  ): Promise<{ readonly reserved: true } | { readonly reserved: false; readonly pointer: OperationPointer }> {
    this.ops.push({ op: "reserve", scope: principalScope, pointer });
    const existing = this.pointers.get(principalScope);
    if (existing) return Promise.resolve({ reserved: false, pointer: existing });
    this.pointers.set(principalScope, pointer);
    return Promise.resolve({ reserved: true });
  }

  clearIfEqual(principalScope: string, pointer: OperationPointer): Promise<boolean> {
    this.ops.push({ op: "clearIfEqual", scope: principalScope, pointer });
    const existing = this.pointers.get(principalScope);
    const equal =
      existing !== undefined &&
      existing.operationKey === pointer.operationKey &&
      existing.kind === pointer.kind &&
      existing.targetKey === pointer.targetKey;
    if (!equal) return Promise.resolve(false);
    this.pointers.delete(principalScope);
    return Promise.resolve(true);
  }

  writes(): PointerOp[] {
    return this.ops.filter((entry) => entry.op !== "read");
  }
}

interface HeldCall<Args> {
  readonly args: Args;
  readonly signal: AbortSignal;
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
}

/** Transport double: every call is held on a deferred the test resolves. */
class TransportDouble {
  readonly preview: HeldCall<ConversationPreviewRequest>[] = [];
  readonly create: HeldCall<ConversationCreateRequest>[] = [];
  readonly status: HeldCall<ConversationRequestSelection>[] = [];
  readonly read: HeldCall<ConversationRequestSelection>[] = [];

  private hold<Args>(sink: HeldCall<Args>[], args: Args, signal: AbortSignal): Promise<unknown> {
    let resolve!: (value: unknown) => void;
    let reject!: (reason?: unknown) => void;
    const settled = new Promise<unknown>((done, failed) => {
      resolve = done;
      reject = failed;
    });
    void settled.catch(() => {});
    sink.push({ args, signal, resolve, reject });
    return settled;
  }

  doPreview(request: ConversationPreviewRequest, signal: AbortSignal): Promise<unknown> {
    return this.hold(this.preview, request, signal);
  }
  doCreate(request: ConversationCreateRequest, signal: AbortSignal): Promise<unknown> {
    return this.hold(this.create, request, signal);
  }
  doStatus(request: ConversationRequestSelection, signal: AbortSignal): Promise<unknown> {
    return this.hold(this.status, request, signal);
  }
  doRead(request: ConversationRequestSelection, signal: AbortSignal): Promise<unknown> {
    return this.hold(this.read, request, signal);
  }
}

/** TEST-AUTHORED synthetic status frame — exact five-field envelope, ABSENT hold. */
const SYNTHETIC_ABSENT_STATUS = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "status",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_data.v1",
    operation_key: ORIGINAL_KEY,
    work_ref: WORK_REF,
    state: "ABSENT",
    effect: "NONE",
    parent_consumed: false,
    preview: null,
    locator: null,
    session: null,
    result: null,
    can_send: false,
  },
  error: null,
};

/** TEST-AUTHORED synthetic read frame — exact envelope, ABSENT (no response yet). */
const SYNTHETIC_ABSENT_READ = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "read",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_data.v1",
    operation_key: ORIGINAL_KEY,
    work_ref: WORK_REF,
    state: "ABSENT",
    effect: "NONE",
    parent_consumed: false,
    preview: null,
    locator: null,
    session: null,
    result: null,
    can_send: false,
  },
  error: null,
};

/** TEST-AUTHORED synthetic producer-error status frame — refusal stays a hold. */
const SYNTHETIC_REFUSED_STATUS = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "status",
  ok: false,
  data: null,
  error: {
    code: "conversation_unavailable",
    message: "SYNTHETIC TEST REFUSAL FRAME authored by this test file; not a producer receipt.",
  },
};

interface Rig {
  readonly binding: FreshConversationBinding;
  readonly store: MemoryPointerStore;
  readonly transport: TransportDouble;
  readonly owner: { current: OwnerContext };
  readonly select: ReturnType<typeof vi.fn<(selection: ConversationRequestSelection) => void>>;
  readonly back: ReturnType<typeof vi.fn<() => void>>;
}

function makeRig(): Rig {
  const owner: { current: OwnerContext } = {
    current: { principalScope: OWNER_SCOPE, generation: "synthetic-gen-1" },
  };
  const transport = new TransportDouble();
  const store = new MemoryPointerStore();
  const binding = createFreshConversationBinding({
    owner: () => owner.current,
    canPreviewCreate: () => true,
    transport: {
      preview: (request: ConversationPreviewRequest, signal: AbortSignal) => transport.doPreview(request, signal),
      create: (request: ConversationCreateRequest, signal: AbortSignal) => transport.doCreate(request, signal),
      status: (request: ConversationRequestSelection, signal: AbortSignal) => transport.doStatus(request, signal),
      read: (request: ConversationRequestSelection, signal: AbortSignal) => transport.doRead(request, signal),
    },
    store,
  });
  return {
    binding,
    store,
    transport,
    owner,
    select: vi.fn((_selection: ConversationRequestSelection) => {}),
    back: vi.fn(() => {}),
  };
}

type JourneyApi = ReturnType<typeof useFreshConversationJourney>;

interface Harness {
  update(patch: Partial<FreshConversationJourneyProps>): void;
  api(): JourneyApi;
  setDraft(workRef: string | null, message: string): void;
  unmount(): void;
}

/** Consumer-controlled mount: the harness, not the hook, owns the draft. */
function mountJourney(
  rig: Rig,
  overrides: Partial<FreshConversationJourneyProps> = {},
): Harness {
  let current: FreshConversationJourneyProps = {
    locale: "en",
    active: true,
    binding: rig.binding,
    authGeneration: 1,
    host: { synthetic: "journey-host" },
    projects: [{ workRef: WORK_REF, title: PROJECT_TITLE }],
    projectsState: "available",
    isProjectCurrent: (ref: string) => ref === WORK_REF,
    workRef: null,
    message: "",
    draftOwner: { ...rig.owner.current },
    onWorkRefChange: (value: string | null) => {
      harness.update({ workRef: value });
    },
    onMessageChange: (value: string) => {
      harness.update({ message: value });
    },
    onOriginalKeySelected: (selection: ConversationRequestSelection) => {
      rig.select(selection);
    },
    onBack: () => {
      rig.back();
    },
    ...overrides,
  };
  let setPropsState!: (next: FreshConversationJourneyProps) => void;
  let captured: JourneyApi | null = null;
  let mounted = true;
  let unmountView: () => void = () => {};

  function App() {
    const [props, setProps] = useState(current);
    setPropsState = setProps;
    current = props;
    const api = useFreshConversationJourney(props);
    captured = api;
    return api.panel;
  }

  const harness: Harness = {
    update(patch) {
      current = { ...current, ...patch };
      if (mounted) setPropsState(current);
    },
    api() {
      if (captured === null) throw new Error("journey api not captured yet");
      return captured;
    },
    setDraft(workRef, message) {
      harness.update({ workRef, message });
    },
    unmount() {
      mounted = false;
      unmountView();
    },
  };
  const view = render(<App />);
  unmountView = view.unmount;
  return harness;
}

/** Fill a valid draft (project chosen + exact fixture first message). */
async function chooseProjectAndMessage(harness: Harness): Promise<void> {
  fireEvent.change(screen.getByLabelText("Project"), { target: { value: WORK_REF } });
  fireEvent.change(screen.getByLabelText("First message"), { target: { value: MESSAGE } });
  await waitFor(() => expect(reviewButton().disabled).toBe(false));
}

function reviewButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Review conversation" }) as HTMLButtonElement;
}

function activeElement(): Element | null {
  return document.activeElement;
}

function expectActiveHeading(text: string, within: string): void {
  const active = activeElement();
  expect(active?.tagName).toBe("H1");
  expect(active?.textContent).toBe(text);
  expect(active?.closest(within)).not.toBeNull();
}

beforeEach(() => {
  mintCalls = 0;
  installDeterministicCrypto();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("new conversation journey over the incumbent controller", () => {
  it("draft guard: an absent project choice and an invalid first message disable Review", async () => {
    const rig = makeRig();
    mountJourney(rig);
    await waitFor(() => expect(screen.getByText("New conversation")).toBeTruthy());
    expect(reviewButton().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Project"), { target: { value: WORK_REF } });
    expect(reviewButton().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("First message"), { target: { value: "   " } });
    expect(reviewButton().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("First message"), { target: { value: MESSAGE } });
    await waitFor(() => expect(reviewButton().disabled).toBe(false));
    expect((screen.getByLabelText("First message") as HTMLTextAreaElement).value).toBe(MESSAGE);
    expect(rig.transport.preview).toHaveLength(0);
    expect(rig.store.writes()).toHaveLength(0);
  });

  it("Review mints the fixture canonical key synchronously, selects it before any await, and renders the exact preview with zero store writes", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());

    // Synchronously, before the preview await settles: the ordinary original
    // key is selected and the exact fixture key was minted at the boundary.
    expect(rig.select).toHaveBeenCalledTimes(1);
    expect(rig.select.mock.calls[0][0]).toEqual({ work_ref: WORK_REF, operation_key: ORIGINAL_KEY });
    expect(rig.transport.preview).toHaveLength(1);
    expect(rig.transport.preview[0].args).toEqual({
      work_ref: WORK_REF,
      operation_key: ORIGINAL_KEY,
      message: MESSAGE,
    });
    expect(mintCalls).toBe(1);
    expect(rig.store.writes()).toHaveLength(0);

    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });

    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
    expect(screen.getByText(PROJECT_TITLE)).toBeTruthy();
    const shownMessage = screen.getByText(/Read source\./);
    expect(shownMessage.textContent).toBe(MESSAGE);
    expect(document.body.textContent).toContain(PREVIEW_DIGEST);
    expectActiveHeading("Review new conversation", ".new-conversation-preview");
    expect(rig.store.writes()).toHaveLength(0);
    expect(rig.store.pointers.get(OWNER_SCOPE)).toBeUndefined();
  });

  it("a rapid double-click on Review produces exactly one preview observation", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    const review=reviewButton();
    act(()=>{fireEvent.click(review);fireEvent.click(review);});

    expect(rig.transport.preview).toHaveLength(1);
    expect(rig.select).toHaveBeenCalledTimes(1);
    expect(mintCalls).toBe(1);

    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
  });

  it("Create sends the closed four-field wire exactly once, reserves and clears the store, and the Open gesture reads the verbatim initial response", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());
    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());

    const createButton = screen.getByRole("button", { name: "Create conversation" });
    fireEvent.click(createButton);
    fireEvent.click(createButton);
    expect(harness.api().hasUnresolvedOriginal).toBe(true);
    expectActiveHeading("New conversation",".mm-new-conversation-outcome");

    await waitFor(()=>expect(rig.transport.create).toHaveLength(1));
    expect(rig.transport.create[0].args).toEqual({
      work_ref: WORK_REF,
      operation_key: ORIGINAL_KEY,
      message: MESSAGE,
      preview_digest: PREVIEW_DIGEST,
    });
    expect(rig.transport.create[0].signal.aborted).toBe(false);
    expect(screen.getByText("Creating conversation…")).toBeTruthy();
    await waitFor(() => expect(rig.store.writes().length).toBeGreaterThanOrEqual(1));
    const reserve = rig.store.ops.filter((entry) => entry.op === "reserve");
    expect(reserve).toHaveLength(1);
    expect(reserve[0].scope).toBe(OWNER_SCOPE);
    expect(reserve[0].pointer).toEqual(ORIGINAL_POINTER);
    expect(rig.store.pointers.get(OWNER_SCOPE)).toEqual(ORIGINAL_POINTER);

    await act(async () => {
      rig.transport.create[0].resolve(FIXTURE.create);
    });
    await waitFor(() => expect(rig.transport.read).toHaveLength(1));
    expect(rig.transport.read[0].args).toEqual({ work_ref: WORK_REF, operation_key: ORIGINAL_KEY });
    expect(rig.store.pointers.get(OWNER_SCOPE)).toBeUndefined();
    expect(harness.api().hasUnresolvedOriginal).toBe(false);

    await act(async () => {
      rig.transport.read[0].resolve(FIXTURE.read);
    });
    await waitFor(() => expect(screen.getByText("Conversation created")).toBeTruthy());
    await waitFor(()=>expect(rig.transport.create).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Open initial response" }));
    await waitFor(() => expect(rig.transport.read).toHaveLength(2));
    await act(async () => {
      rig.transport.read[1].resolve(FIXTURE.read);
    });
    await waitFor(() => expect(screen.getByText("Your first message")).toBeTruthy());
    const shownOriginal = screen.getByText(/Read source\./);
    expect(shownOriginal.textContent).toBe(MESSAGE);
    expect(screen.getByText("Recovered one exact planner session.")).toBeTruthy();
    expectActiveHeading("Conversation", ".mm-new-conversation-outcome");
    expect(rig.store.pointers.get(OWNER_SCOPE)).toBeUndefined();
    await waitFor(()=>expect(rig.transport.create).toHaveLength(1));
  });

  it("initial store discovery with an empty store renders the draft and never dispatches status, read or create", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await waitFor(() =>
      expect(screen.queryByText("Checking for an original request…")).toBeNull(),
    );
    expect(screen.getByText("New conversation")).toBeTruthy();
    expect(harness.api().hasUnresolvedOriginal).toBe(false);
    expect(rig.transport.status).toHaveLength(0);
    expect(rig.transport.read).toHaveLength(0);
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.transport.preview).toHaveLength(0);
    expect(rig.store.writes()).toHaveLength(0);
  });
});

describe("retained originals and holds", () => {
  it("a retained original pointer routes to the outcome; Check reads status and an ABSENT or refused hold never redispatches create", async () => {
    const rig = makeRig();
    rig.store.pointers.set(OWNER_SCOPE, ORIGINAL_POINTER);
    const harness = mountJourney(rig);

    await waitFor(() =>
      expect(
        screen.getByText("An original conversation request needs a status check. Don’t create it again."),
      ).toBeTruthy(),
    );
    expect(harness.api().hasUnresolvedOriginal).toBe(true);
    expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.transport.status).toHaveLength(0);
    expect(rig.transport.read).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Check original request" }));
    await waitFor(() => expect(rig.transport.status).toHaveLength(1));
    expect(rig.transport.status[0].args).toEqual({ work_ref: WORK_REF, operation_key: ORIGINAL_KEY });
    await act(async () => {
      rig.transport.status[0].resolve(SYNTHETIC_ABSENT_STATUS);
    });
    await waitFor(() => expect(rig.transport.read).toHaveLength(1));
    await act(async () => {
      rig.transport.read[0].resolve(SYNTHETIC_ABSENT_READ);
    });
    await waitFor(() =>
      expect(
        screen.getByText("The outcome is not confirmed. Check the original request; do not create it again."),
      ).toBeTruthy(),
    );
    expect(rig.store.pointers.get(OWNER_SCOPE)).toEqual(ORIGINAL_POINTER);
    expect(rig.transport.create).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Check original request" }));
    await waitFor(() => expect(rig.transport.status).toHaveLength(2));
    await act(async () => {
      rig.transport.status[1].resolve(SYNTHETIC_REFUSED_STATUS);
    });
    await waitFor(() => expect(rig.transport.read).toHaveLength(2));
    await act(async () => {
      rig.transport.read[1].resolve(SYNTHETIC_ABSENT_READ);
    });
    await waitFor(() =>
      expect(screen.getAllByText("The outcome is not confirmed. Check the original request; do not create it again.").length).toBeGreaterThanOrEqual(1),
    );
    expect(rig.store.pointers.get(OWNER_SCOPE)).toEqual(ORIGINAL_POINTER);
    expect(rig.transport.create).toHaveLength(0);
    expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
  });

  it("a foreign pending pointer disables creation entirely and never leaks the foreign key", async () => {
    const rig = makeRig();
    rig.store.pointers.set(OWNER_SCOPE, FOREIGN_POINTER);
    const harness = mountJourney(rig);

    await waitFor(() =>
      expect(
        screen.getByText("Another request needs its existing status controls before a new conversation can be created."),
      ).toBeTruthy(),
    );
    expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
    expect(harness.api().hasUnresolvedOriginal).toBe(true);
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.transport.preview).toHaveLength(0);
    expect(rig.transport.status).toHaveLength(0);
    expect(screen.queryByText(/mmos-launch-/)).toBeNull();
  });
});

describe("owner, draft drift and back gestures", () => {
  it("an owner generation change during a pending preview withholds the old draft's preview data", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());
    expect(rig.transport.preview).toHaveLength(1);

    const nextOwner: OwnerContext = {
      principalScope: OWNER_SCOPE,
      generation: "synthetic-gen-2",
    };
    rig.owner.current = nextOwner;
    harness.update({ authGeneration: 2, draftOwner: { ...nextOwner } });
    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });

    await waitFor(() =>
      expect(screen.queryByText("Checking for an original request…")).toBeNull(),
    );
    expect(screen.queryByText("Review new conversation")).toBeNull();
    expect(document.body.textContent).not.toContain(PREVIEW_DIGEST);
    expect(rig.transport.read).toHaveLength(0);
    expect(rig.transport.create).toHaveLength(0);

    // The journey is usable again under the new epoch: an explicit new Review
    // mints a fresh key at the boundary and previews normally.
    fireEvent.change(screen.getByLabelText("First message"), { target: { value: MESSAGE } });
    await waitFor(() => expect(reviewButton().disabled).toBe(false));
    fireEvent.click(reviewButton());
    await waitFor(() => expect(rig.transport.preview).toHaveLength(2));
    expect(mintCalls).toBe(2);
    await act(async () => {
      rig.transport.preview[1].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
  });

  it("withholds a pending preview when the actual project read identity changes", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig, { projectReadIdentity: {} });
    await chooseProjectAndMessage(harness);
    fireEvent.click(reviewButton());
    act(() => harness.update({ projectReadIdentity: {} }));
    await act(async () => { rig.transport.preview[0].resolve(FIXTURE.preview); });
    await waitFor(() => expect(screen.getByText("The draft or project changed. Review it again before creating a conversation.")).toBeTruthy());
    expect(screen.queryByText("Review new conversation")).toBeNull();
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.store.writes()).toHaveLength(0);
  });

  it("refuses Create after a new project read replaced the reviewed identity", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig, { projectReadIdentity: {} });
    await chooseProjectAndMessage(harness);
    fireEvent.click(reviewButton());
    await act(async () => { rig.transport.preview[0].resolve(FIXTURE.preview); });
    const create = await screen.findByRole("button", { name: "Create conversation" });
    act(() => harness.update({ projectReadIdentity: {} }));
    expect(create).toHaveProperty("disabled", true);
    fireEvent.click(create);
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.store.writes()).toHaveLength(0);
  });

  it("a late preview after the draft changed is ignored with an explicit changed notice", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());
    expect(rig.transport.preview).toHaveLength(1);
    act(()=>harness.setDraft(WORK_REF, "changed draft text while preview in flight"));

    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() =>
      expect(
        screen.getByText("The draft or project changed. Review it again before creating a conversation."),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("Review new conversation")).toBeNull();
    await waitFor(() => expect(reviewButton().disabled).toBe(false));
    expect(rig.transport.read).toHaveLength(0);
  });

  it("Back during a preview aborts only that observation; the next Review reuses the same original key without re-minting", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());
    expect(rig.transport.preview).toHaveLength(1);
    expect(mintCalls).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    await waitFor(() => expect(screen.getByText("New conversation")).toBeTruthy());
    expect(rig.transport.preview[0].signal.aborted).toBe(true);
    expect(screen.queryByText("Review new conversation")).toBeNull();

    await waitFor(() => expect(reviewButton().disabled).toBe(false));
    fireEvent.click(reviewButton());
    expect(rig.transport.preview).toHaveLength(2);
    expect(mintCalls).toBe(1);
    expect(rig.select.mock.calls[1][0]).toEqual({ work_ref: WORK_REF, operation_key: ORIGINAL_KEY });
    expect(rig.transport.preview[1].args.operation_key).toBe(ORIGINAL_KEY);

    await act(async () => {
      rig.transport.preview[1].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
  });

  it("Back during a pending create neither cancels nor replays the controller operation", async () => {
    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);

    fireEvent.click(reviewButton());
    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Create conversation" }));

    await waitFor(()=>expect(rig.transport.create).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    expect(rig.back).toHaveBeenCalledTimes(1);
    expect(rig.transport.create[0].signal.aborted).toBe(false);

    await act(async () => {
      rig.transport.create[0].resolve(FIXTURE.create);
    });
    await waitFor(() => expect(rig.transport.read).toHaveLength(1));
    await act(async () => {
      rig.transport.read[0].resolve(FIXTURE.read);
    });
    await waitFor(() => expect(screen.getByText("Conversation created")).toBeTruthy());
    await waitFor(()=>expect(rig.transport.create).toHaveLength(1));
    expect(rig.store.pointers.get(OWNER_SCOPE)).toBeUndefined();
    expect(harness.api().hasUnresolvedOriginal).toBe(false);
  });
});

describe("remount, locale and focus discipline", () => {
  it("Back never sends, and remounting on the same store preserves the original pointer without resending", async () => {
    const rig = makeRig();
    rig.store.pointers.set(OWNER_SCOPE, ORIGINAL_POINTER);
    const first = mountJourney(rig);

    await waitFor(() =>
      expect(
        screen.getByText("An original conversation request needs a status check. Don’t create it again."),
      ).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    expect(rig.back).toHaveBeenCalledTimes(1);
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.transport.status).toHaveLength(0);
    expect(rig.transport.read).toHaveLength(0);
    first.unmount();

    const second = mountJourney(rig);
    await waitFor(() =>
      expect(
        screen.getByText("An original conversation request needs a status check. Don’t create it again."),
      ).toBeTruthy(),
    );
    expect(second.api().hasUnresolvedOriginal).toBe(true);
    expect(rig.store.pointers.get(OWNER_SCOPE)).toEqual(ORIGINAL_POINTER);
    expect(rig.transport.create).toHaveLength(0);
    expect(rig.transport.status).toHaveLength(0);
    expect(rig.transport.read).toHaveLength(0);
    expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
  });

  it("the zh-CN locale renders the draft in Chinese and still never creates without a valid draft", () => {
    const rig = makeRig();
    mountJourney(rig, { locale: "zh-CN" });
    expect(screen.getByText("新建对话")).toBeTruthy();
    expect(screen.getByLabelText("项目")).toBeTruthy();
    expect(screen.getByLabelText("第一条消息")).toBeTruthy();
    const review = screen.getByRole("button", { name: "预览对话" }) as HTMLButtonElement;
    expect((review as HTMLButtonElement).disabled).toBe(true);
    expect(rig.transport.preview).toHaveLength(0);
    expect(rig.transport.create).toHaveLength(0);
    expect(screen.queryByText("New conversation")).toBeNull();
  });

  it("preview focus follows the Review gesture but never steals external focus after asynchronous completion", async () => {
    const followed = makeRig();
    const followedHarness = mountJourney(followed);
    await chooseProjectAndMessage(followedHarness);
    fireEvent.click(reviewButton());
    await act(async () => {
      followed.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
    expectActiveHeading("Review new conversation", ".new-conversation-preview");
    followedHarness.unmount();

    const rig = makeRig();
    const harness = mountJourney(rig);
    await chooseProjectAndMessage(harness);
    fireEvent.click(reviewButton());
    expect(rig.transport.preview).toHaveLength(1);

    const external = document.createElement("button");
    external.id = "external-focus-target";
    document.body.appendChild(external);
    external.focus();
    expect(activeElement()).toBe(external);

    await act(async () => {
      rig.transport.preview[0].resolve(FIXTURE.preview);
    });
    await waitFor(() => expect(screen.getByText("Review new conversation")).toBeTruthy());
    expect(activeElement()).toBe(external);
    expect(screen.queryByText(/Read source\./)).not.toBeNull();
    external.remove();
  });
});
