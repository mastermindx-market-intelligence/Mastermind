// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthState } from "../../host";
import type { OwnerContext } from "../../orchestration/operation-controller";
import {
  readFreshConversationLocation,
  writeFreshConversationLocation,
} from "../fresh-conversation-location";
import type { ConversationRequestSelection } from "./fresh-conversation-binding";
import {
  useFreshConversationDraftState,
  type FreshConversationDraftHost,
  type FreshConversationDraftStateProps,
} from "./useFreshConversationDraftState";

const hex = (chars: number, seed: string) =>
  seed.repeat(Math.ceil(chars / seed.length)).slice(0, chars);
const CREATE_PREFIX = "mmos-conversation-create-";
const mintedKey = (seed: string) => CREATE_PREFIX + hex(40, seed);
const workRef = "WS:Qualified.Project";
const otherWork = "WS:Other.Work";
const keyA = mintedKey("a1b2c3d4e5");
const keyB = mintedKey("f1e2d3c4b5");
const sel = (key = keyA, ref = workRef): ConversationRequestSelection =>
  Object.freeze({ work_ref: ref, operation_key: key });
const blankFlagUrl = "http://localhost:3000/os/?new_conversation=1";
const SAFE_KEYS = ["new_conversation", "conversation_work_ref", "conversation_operation_key"];
/** Absolute helper output -> path form for replaceState in this jsdom origin. */
const toPath = (href: string) => {
  const url = new URL(href);
  return `${url.pathname}${url.search}`;
};
const safeKeysOnly = (href: string) =>
  [...new URL(href).searchParams.keys()].every(key => (SAFE_KEYS as string[]).includes(key));

let auth: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
function makeHost() {
  let generation = 0;
  const request = vi.fn(async () => ({}));
  const host: FreshConversationDraftHost = {
    auth: {
      getState: () => auth,
      subscribe: () => () => {},
      signIn: async () => ({}),
      signOut: async () => ({}),
    },
    invalidationGeneration: () => generation,
    freshConversation: { request },
  };
  return {
    host,
    request,
    expire: () => {
      auth = { status: "signed_out", reason: null, acquisition: false, content: false };
    },
    signInAgain: () => {
      auth = { status: "signed_in", reason: null, acquisition: true, content: false };
    },
    bump: () => {
      generation += 1;
    },
    replaceGetState: () => {
      (host.auth as { getState: unknown }).getState = () => auth;
    },
    swapRequest: () => {
      (host.freshConversation as { request?: unknown }).request = async () => ({});
    },
    dropTransport: () => {
      (host as { freshConversation?: unknown }).freshConversation = undefined;
    },
  };
}
const ownerRef = { current: { principalScope: "exec:primary", generation: "gen-1" } as OwnerContext | null };
const getExecutiveOwner = () => ownerRef.current;
const epoch = { value: 1 };
const props = (host: FreshConversationDraftHost): FreshConversationDraftStateProps =>
  ({ host, authRevision: epoch.value, currentAuthRevision: () => epoch.value, getExecutiveOwner });
function setup(path = "/os/") {
  history.replaceState(null, "", path);
  const h = makeHost();
  window.MastermindMissionHost = h.host;
  const view = renderHook(
    (p: FreshConversationDraftStateProps) => useFreshConversationDraftState(p),
    { initialProps: props(h.host) },
  );
  return { ...h, ...view };
}
type Harness = ReturnType<typeof setup>;
function mountAtOriginal(value: ConversationRequestSelection) {
  return setup(toPath(writeFreshConversationLocation("http://localhost:3000/os/", value, true)));
}
function freshPane() {
  const e = setup("/os/?new_conversation=1");
  act(() => { e.result.current.onWorkRefChange(workRef); });
  act(() => e.result.current.onMessageChange("Frozen draft"));
  return e;
}
function restoreExternal(value: ConversationRequestSelection | null) {
  history.replaceState(
    null, "",
    toPath(writeFreshConversationLocation(window.location.href, value, true)),
  );
}

beforeEach(() => {
  auth = { status: "signed_in", reason: null, acquisition: true, content: false };
  epoch.value = 1;
  ownerRef.current = { principalScope: "exec:primary", generation: "gen-1" };
  history.replaceState(null, "", "/os/");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
});

describe("New-conversation draft presentation state", () => {
  it("never adopts after a synchronous URL write changes the owner", () => {
    const e = freshPane();
    const real = history.replaceState.bind(history);
    vi.spyOn(history, "replaceState").mockImplementation((data, unused, url) => {
      real(data, unused, url);
      ownerRef.current = { principalScope: "exec:other", generation: "g2" };
    });
    act(() => expect(() => e.result.current.onOriginalKeySelected(sel())).toThrow("FRESH_CONVERSATION_CONTEXT_CHANGED"));
    expect(e.result.current.originalLookup).toBeNull();
    e.rerender(props(e.host));
    expect(e.result.current.message).toBe("");
  });

  it("keeps passive text editable when the real Executive owner disappears, without command authority", () => {
    const e = freshPane();
    e.expire();
    ownerRef.current = null;
    epoch.value += 1;
    act(() => e.result.current.invalidateAuth(true));
    e.rerender(props(e.host));
    expect(e.result.current.retainedDraft?.text).toBe("Frozen draft");
    expect(e.result.current.draftOwner).toBeNull();
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.editRetainedDraft("Held only"));
    expect(e.result.current.retainedDraft?.text).toBe("Held only");
    expect(e.result.current.open()).toBe(false);
    ownerRef.current = { principalScope: "exec:other", generation: "g2" };
    e.signInAgain();
    e.rerender(props(e.host));
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
  });

  it("reads the initial URL: blank flag opens, closed hides, invalid and duplicate keys close invalid", () => {
    const blank = setup("/os/?new_conversation=1");
    expect(blank.result.current).toMatchObject({
      shown: true, invalidLink: false, workRef: null, message: "",
      draftOwner: null, originalLookup: null, retainedDraft: null, navigationEpoch: 0,
    });
    const closed = setup("/os/");
    expect(closed.result.current).toMatchObject({ shown: false, invalidLink: false, originalLookup: null, message: "" });
    for (const bad of [
      "/os/?new_conversation=0",
      "/os/?new_conversation=1&new_conversation=1",
      "/os/?conversation_work_ref=WS:ONE",
      `/os/?conversation_operation_key=${keyA}`,
      "/os/?conversation_work_ref=WS:ONE&conversation_operation_key=foreign",
    ]) {
      const invalid = setup(bad);
      expect(invalid.result.current).toMatchObject({ shown: false, invalidLink: true, originalLookup: null });
    }
  });

  it("adopts an initial selection URL as detached lookup DATA with its reading owner and invents no message", () => {
    const e = mountAtOriginal(sel(keyA));
    expect(e.result.current.shown).toBe(true);
    expect(e.result.current.originalLookup).toEqual({
      selection: sel(keyA),
      owner: { principalScope: "exec:primary", generation: "gen-1" },
    });
    expect(e.result.current.originalLookup?.selection).not.toBe(sel(keyA));
    expect(Object.isFrozen(e.result.current.originalLookup?.selection)).toBe(true);
    expect(e.result.current.originalLookup?.owner).not.toBe(ownerRef.current);
    expect(e.result.current.workRef).toBe(workRef);
    expect(e.result.current.message).toBe("");
    expect(e.result.current.draftOwner).toBeNull();
    expect(e.result.current.navigationEpoch).toBe(0);
  });

  it("opens a blank pane at the clean flag URL and resumes the known original after hide", () => {
    const e = setup("/os/?legacy=secret&tracking=1#fragment");
    act(() => { expect(e.result.current.open()).toBe(true); });
    expect(window.location.href).toBe(blankFlagUrl);
    expect(safeKeysOnly(window.location.href)).toBe(true);
    expect(e.result.current).toMatchObject({ shown: true, invalidLink: false, workRef: null });
    expect(e.result.current.message).toBe("");

    const kept = mountAtOriginal(sel(keyA));
    act(() => kept.result.current.hide());
    expect(kept.result.current.shown).toBe(false);
    expect(window.location.search).toContain(`conversation_operation_key=${keyA}`);
    act(() => { expect(kept.result.current.open()).toBe(true); });
    expect(kept.result.current.shown).toBe(true);
    expect(kept.result.current.originalLookup?.selection).toEqual(sel(keyA));
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyA), true));
  });

  it("opens an explicitly new presentation: parks unsent text, writes the blank URL, bumps the epoch once", () => {
    const e = freshPane();
    const before = e.result.current.navigationEpoch;
    act(() => { expect(e.result.current.open("new")).toBe(true); });
    expect(e.result.current.navigationEpoch).toBe(before + 1);
    expect(e.result.current.retainedDraft).toEqual({
      text: "Frozen draft", workRef, selection: null, passivelyHeld: false,
    });
    expect(e.result.current.message).toBe("");
    expect(e.result.current.draftOwner).toBeNull();
    expect(window.location.href).toBe(blankFlagUrl);
    // Resuming the parked draft does not bump the epoch again.
    act(() => { expect(e.result.current.open()).toBe(true); });
    expect(e.result.current.message).toBe("Frozen draft");
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.navigationEpoch).toBe(before + 1);
    expect(window.location.href).toBe(blankFlagUrl);
  });

  it("writes the safe lookup URL synchronously before adopting state", () => {
    const e = freshPane();
    act(() => e.result.current.onMessageChange("First"));
    const order: string[] = [];
    const real = window.history.replaceState.bind(window.history);
    vi.spyOn(window.history, "replaceState").mockImplementation(function mocked(data, unused, url) {
      order.push(e.result.current.workRef ?? "blank");
      return real(data, unused, url);
    } as typeof window.history.replaceState);
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    expect(order).toEqual([workRef]);
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
    expect(e.result.current.originalLookup?.selection).not.toBe(sel(keyA));
    expect(e.result.current.message).toBe("First");
    expect(e.result.current.draftOwner).toEqual({ principalScope: "exec:primary", generation: "gen-1" });
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyA), true));
    expect(safeKeysOnly(window.location.href)).toBe(true);
  });

  it("preserves state and refs when the history write throws and propagates the fixed error", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Unsent"));
    const lookupBefore = e.result.current.originalLookup;
    const hrefBefore = window.location.href;
    vi.spyOn(window.history, "replaceState").mockImplementation(() => {
      throw new Error("HISTORY_REFUSED");
    });
    act(() => {
      expect(() => e.result.current.onOriginalKeySelected(sel(keyB))).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
      expect(() => e.result.current.open()).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
      expect(() => e.result.current.open("new")).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
      expect(() => e.result.current.onWorkRefChange(otherWork)).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
      expect(() => e.result.current.returnToRetainedDraft()).not.toThrow();
    });
    expect(e.result.current.originalLookup).toBe(lookupBefore);
    expect(e.result.current.message).toBe("Unsent");
    expect(e.result.current.workRef).toBe(workRef);
    expect(e.result.current.shown).toBe(true);
    expect(window.location.href).toBe(hrefBefore);
  });

  it("carries the exact blank-pane draft into its own minted key of the same chosen work without an epoch bump", () => {
    const exact = "  padded\tline\n\u{1F600}\u{10348} tail ";
    const e = freshPane();
    act(() => e.result.current.onMessageChange(exact));
    const before = e.result.current.navigationEpoch;
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    expect(e.result.current.message).toBe(exact);
    expect(e.result.current.draftOwner).toEqual({ principalScope: "exec:primary", generation: "gen-1" });
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
    expect(e.result.current.workRef).toBe(workRef);
    expect(e.result.current.navigationEpoch).toBe(before);
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyA), true));
  });

  it("parks without transplant when a different original key arrives locally and never self-induces an epoch", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Original A text"));
    const before = e.result.current.navigationEpoch;
    act(() => { e.result.current.onOriginalKeySelected(sel(keyB)); });
    expect(e.result.current.message).toBe("");
    expect(e.result.current.draftOwner).toBeNull();
    expect(e.result.current.navigationEpoch).toBe(before);
    expect(e.result.current.retainedDraft).toEqual({
      text: "Original A text", workRef, selection: sel(keyA), passivelyHeld: false,
    });
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyB));
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyB), true));
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(true); });
    expect(e.result.current.message).toBe("Original A text");
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
    expect(e.result.current.retainedDraft).toBeNull();
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyA), true));
  });

  it("keeps the draft across a same-original restore and parks with an epoch bump on a changed external original", () => {
    const e = mountAtOriginal(sel(keyA));
    act(() => e.result.current.onMessageChange("Keep me"));
    restoreExternal(sel(keyA));
    act(() => e.result.current.restoreLocation());
    expect(e.result.current.message).toBe("Keep me");
    expect(e.result.current.navigationEpoch).toBe(0);
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));

    restoreExternal(sel(keyB));
    act(() => e.result.current.restoreLocation());
    expect(e.result.current.message).toBe("");
    expect(e.result.current.navigationEpoch).toBe(1);
    expect(e.result.current.retainedDraft).toEqual({
      text: "Keep me", workRef, selection: sel(keyA), passivelyHeld: false,
    });
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyB));
  });

  it("keeps a blank-pane draft across a blank restore and never resets the same original", () => {
    const e = freshPane();
    act(() => e.result.current.onMessageChange("Held across blank restore"));
    restoreExternal(null);
    act(() => e.result.current.restoreLocation());
    expect(e.result.current.message).toBe("Held across blank restore");
    expect(e.result.current.navigationEpoch).toBe(0);
    expect(e.result.current.shown).toBe(true);
    expect(e.result.current.originalLookup).toBeNull();
    // The same-blank restore is a no-reset: the ephemeral choice stays.
    expect(e.result.current.workRef).toBe(workRef);
    // A keyed draft restoring to blank is a changed original: park + bump.
    const keyed = freshPane();
    act(() => { keyed.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => keyed.result.current.onMessageChange("Keyed draft"));
    restoreExternal(null);
    act(() => keyed.result.current.restoreLocation());
    expect(keyed.result.current.message).toBe("");
    expect(keyed.result.current.navigationEpoch).toBe(1);
    expect(keyed.result.current.retainedDraft?.text).toBe("Keyed draft");
    expect(keyed.result.current.originalLookup).toBeNull();
  });

  it("parks on a restore that closes the original and holds the draft across an invalid restore", () => {
    const e = mountAtOriginal(sel(keyB));
    act(() => e.result.current.onMessageChange("Held across close"));
    history.replaceState(null, "", "/os/");
    act(() => e.result.current.restoreLocation());
    expect(e.result.current).toMatchObject({
      shown: false, invalidLink: false, originalLookup: null, workRef: null, message: "",
    });
    expect(e.result.current.navigationEpoch).toBe(1);
    expect(e.result.current.retainedDraft).toEqual({
      text: "Held across close", workRef, selection: sel(keyB), passivelyHeld: false,
    });
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => { expect(e.result.current.open()).toBe(true); });
    expect(e.result.current.message).toBe("Held across close");
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyB));
    expect(e.result.current.retainedDraft).toBeNull();

    const invalid = mountAtOriginal(sel(keyA));
    act(() => invalid.result.current.onMessageChange("Held across invalid"));
    history.replaceState(null, "", "/os/?new_conversation=0");
    act(() => invalid.result.current.restoreLocation());
    expect(invalid.result.current).toMatchObject({ shown: false, invalidLink: true, originalLookup: null, message: "" });
    expect(invalid.result.current.retainedDraft?.text).toBe("Held across invalid");
    expect(invalid.result.current.hasUnsentDraft()).toBe(true);
  });

  const drifts: readonly (readonly [string, (e: Harness) => void, boolean, boolean])[] = [
    ["a swapped global host without a rerender", e => { window.MastermindMissionHost = makeHost().host; }, false, true],
    ["an epoch drift with a rerender", e => { epoch.value = 2; e.rerender(props(e.host)); }, true, true],
    ["a source generation drift with a rerender", e => { e.bump(); e.rerender(props(e.host)); }, true, true],
    ["a replaced host at rerender", e => {
      const next = makeHost();
      window.MastermindMissionHost = next.host;
      e.rerender(props(next.host));
    }, true, true],
    ["a replaced auth getState without a rerender", e => { e.replaceGetState(); }, false, true],
    ["a replaced transport request without a rerender", e => { e.swapRequest(); }, false, true],
    ["a dropped freshConversation transport without a rerender", e => { e.dropTransport(); }, false, true],
    ["a moved Executive owner without a rerender", e => {
      ownerRef.current = { principalScope: "exec:secondary", generation: "gen-1" };
    }, false, true],
    ["a same-principal owner generation advance with a rerender", e => {
      epoch.value = 2;
      ownerRef.current = { principalScope: "exec:primary", generation: "gen-2" };
      e.rerender(props(e.host));
    }, true, false],
  ];
  it.each(drifts)("refuses stale callbacks after %s with zero mutations", (_label, drift, rerendered, lookupExposed) => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    const stale = e.result.current;
    const hrefBefore = window.location.href;
    const replace = vi.spyOn(window.history, "replaceState");
    drift(e);
    act(() => {
      stale.onMessageChange("Late write");
      stale.onWorkRefChange(otherWork);
      stale.onOriginalKeySelected(sel(keyB));
      expect(stale.open()).toBe(false);
      expect(stale.open("new")).toBe(false);
      stale.hide();
      stale.restoreLocation();
      expect(stale.returnToRetainedDraft()).toBe(false);
      expect(stale.isHostCurrent()).toBe(false);
    });
    expect(window.location.href).toBe(hrefBefore);
    expect(replace).not.toHaveBeenCalled();
    if (rerendered) {
      // The old actor's draft is foreign to the fresh render: never returned
      // as current text, while the URL lookup DATA stays exposed to the same
      // principal, and the fresh render's own callbacks still own the screen.
      expect(e.result.current.message).toBe("");
      expect(e.result.current.draftOwner).toBeNull();
      if (lookupExposed) expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
      else expect(e.result.current.originalLookup).toBeNull();
      expect(e.result.current.hasUnsentDraft()).toBe(false);
      act(() => e.result.current.onMessageChange("Fresh actor"));
      expect(e.result.current.message).toBe("Fresh actor");
    } else {
      expect(e.result.current.message).toBe("Frozen draft");
      expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
    }
  });

  it("never lets old callbacks be authorized by a later render", () => {
    const e = freshPane();
    const stale = e.result.current;
    epoch.value = 2;
    ownerRef.current = { principalScope: "exec:primary", generation: "gen-2" };
    e.rerender(props(e.host));
    const replace = vi.spyOn(window.history, "replaceState");
    act(() => {
      stale.onMessageChange("Late write");
      stale.onOriginalKeySelected(sel(keyB));
      expect(stale.open()).toBe(false);
      expect(stale.returnToRetainedDraft()).toBe(false);
      expect(stale.isHostCurrent()).toBe(false);
    });
    expect(replace).not.toHaveBeenCalled();
    act(() => e.result.current.onMessageChange("Fresh actor"));
    expect(e.result.current.message).toBe("Fresh actor");
    expect(e.result.current.draftOwner).toEqual({ principalScope: "exec:primary", generation: "gen-2" });
  });

  it("refuses an invalid original object with no write and no adoption", () => {
    const e = freshPane();
    const before = window.location.href;
    const foreign = { work_ref: "WS:X", operation_key: "foreign" } as ConversationRequestSelection;
    act(() => {
      expect(() => e.result.current.onOriginalKeySelected(foreign)).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
    });
    expect(window.location.href).toBe(before);
    expect(e.result.current.originalLookup).toBeNull();
  });

  it("preserves only same-host owned text at passive expiry and clears on explicit revoke", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Passive held text"));
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    expect(e.result.current.message).toBe("");
    expect(e.result.current.draftOwner).toBeNull();
    expect(e.result.current.retainedDraft).toEqual({
      text: "Passive held text", workRef, selection: sel(keyA), passivelyHeld: true,
    });
    expect(e.result.current.isHostCurrent()).toBe(false);
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    // Passive held text never becomes current again by itself.
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(false); });
    expect(e.result.current.message).toBe("");
    // Exact held passive same-host editing stays local and works while signed out.
    act(() => e.result.current.editRetainedDraft("Edited while held"));
    expect(e.result.current.retainedDraft?.text).toBe("Edited while held");
    act(() => e.result.current.invalidateAuth(false));
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    expect(e.result.current.workRef).toBeNull();
    // The safe URL lookup DATA is presentation the parent still owns.
    expect(window.location.search).toContain(`conversation_operation_key=${keyA}`);
    expect(e.result.current.shown).toBe(true);
  });

  it("never preserves foreign-host or foreign-principal text and never exposes it to an unrelated actor", () => {
    const e = freshPane();
    act(() => e.result.current.onMessageChange("First actor words"));
    const next = makeHost();
    epoch.value = 2;
    window.MastermindMissionHost = next.host;
    ownerRef.current = { principalScope: "exec:secondary", generation: "gen-1" };
    e.rerender(props(next.host));
    act(() => e.result.current.invalidateAuth(true));
    expect(e.result.current.message).toBe("");
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(false); });
    act(() => e.result.current.editRetainedDraft("Foreign edit"));
    act(() => e.result.current.discardRetainedDraft());
    expect(e.result.current.retainedDraft).toBeNull();
  });

  it("never exposes passively held text to a different known principal on the same host", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Mine only"));
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    expect(e.result.current.retainedDraft?.passivelyHeld).toBe(true);
    epoch.value = 3;
    ownerRef.current = { principalScope: "exec:secondary", generation: "gen-9" };
    e.rerender(props(e.host));
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(false); });
    act(() => e.result.current.editRetainedDraft("Cross edit"));
    expect(e.result.current.retainedDraft).toBeNull();
    // The explicit revoke clears what the new principal can never see.
    act(() => e.result.current.invalidateAuth(false));
    expect(e.result.current.hasUnsentDraft()).toBe(false);
  });

  it("rebinds an owned passive draft after same-principal reauthentication on the explicit gesture only", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Reauth text"));
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    e.signInAgain();
    epoch.value = 2;
    ownerRef.current = { principalScope: "exec:primary", generation: "gen-2" };
    e.rerender(props(e.host));
    expect(e.result.current.retainedDraft).toEqual({
      text: "Reauth text", workRef, selection: sel(keyA), passivelyHeld: true,
    });
    expect(e.result.current.message).toBe("");
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(true); });
    expect(e.result.current.message).toBe("Reauth text");
    expect(e.result.current.draftOwner).toEqual({ principalScope: "exec:primary", generation: "gen-2" });
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.isHostCurrent()).toBe(true);
    expect(window.location.href).toBe(writeFreshConversationLocation("http://localhost:3000/os/", sel(keyA), true));
  });

  it("never returns or exposes a retained draft across a replaced host", () => {
    const e = freshPane();
    act(() => e.result.current.onMessageChange("Old host text"));
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    e.signInAgain();
    const next = makeHost();
    epoch.value = 2;
    window.MastermindMissionHost = next.host;
    ownerRef.current = { principalScope: "exec:primary", generation: "gen-2" };
    e.rerender(props(next.host));
    expect(e.result.current.retainedDraft).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    const replace = vi.spyOn(window.history, "replaceState");
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(false); });
    expect(replace).not.toHaveBeenCalled();
  });

  it("parks on a work change away from an owned draft with the blank URL and no transplant", () => {
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
    act(() => e.result.current.onMessageChange("Work-bound text"));
    act(() => { e.result.current.onWorkRefChange(otherWork); });
    expect(window.location.href).toBe(blankFlagUrl);
    expect(e.result.current.workRef).toBe(otherWork);
    expect(e.result.current.originalLookup).toBeNull();
    expect(e.result.current.message).toBe("");
    expect(e.result.current.retainedDraft).toEqual({
      text: "Work-bound text", workRef, selection: sel(keyA), passivelyHeld: false,
    });
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => { expect(e.result.current.returnToRetainedDraft()).toBe(true); });
    expect(e.result.current.originalLookup?.selection).toEqual(sel(keyA));
    expect(e.result.current.workRef).toBe(workRef);
    // Re-selecting the current work is a no-op with no URL write.
    const replace = vi.spyOn(window.history, "replaceState");
    act(() => e.result.current.onWorkRefChange(workRef));
    expect(replace).not.toHaveBeenCalled();
  });

  it("hides locally without rewriting the URL, refuses hidden edits, and keeps the hold armed", () => {
    const e = freshPane();
    act(() => e.result.current.onMessageChange("Off-view hold"));
    const hrefBefore = window.location.href;
    const replace = vi.spyOn(window.history, "replaceState");
    act(() => e.result.current.hide());
    expect(e.result.current.shown).toBe(false);
    expect(window.location.href).toBe(hrefBefore);
    expect(e.result.current.message).toBe("Off-view hold");
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => e.result.current.onMessageChange(""));
    expect(e.result.current.message).toBe("Off-view hold");
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    expect(replace).not.toHaveBeenCalled();
    act(() => { expect(e.result.current.open()).toBe(true); });
    act(() => e.result.current.onMessageChange(""));
    expect(e.result.current.message).toBe("");
    expect(e.result.current.hasUnsentDraft()).toBe(false);
  });

  it("never writes the message into the URL and performs no network, storage, mint or push calls", () => {
    const fetchSpy = vi.fn();
    const originalFetch = (window as { fetch?: unknown }).fetch;
    (window as { fetch?: unknown }).fetch = fetchSpy;
    const send = vi.spyOn(XMLHttpRequest.prototype, "send");
    const openXhr = vi.spyOn(XMLHttpRequest.prototype, "open");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const pushState = vi.spyOn(window.history, "pushState");
    try {
      const e = freshPane();
      act(() => { e.result.current.onOriginalKeySelected(sel(keyA)); });
      act(() => { expect(e.result.current.open("new")).toBe(true); });
      act(() => e.result.current.onMessageChange("Second secret"));
      act(() => e.result.current.restoreLocation());
      // The blank restore keeps the freshly authored draft and the parked one.
      expect(e.result.current.message).toBe("Second secret");
      expect(e.result.current.retainedDraft?.text).toBe("Frozen draft");
      expect(e.result.current.navigationEpoch).toBe(1);
      expect(window.location.href).toBe(blankFlagUrl);
      expect(window.location.href).not.toContain("Second secret");
      expect(window.location.href).not.toContain(encodeURIComponent("Second secret"));
      expect(window.location.href).not.toContain("Frozen draft");
      expect(safeKeysOnly(window.location.href)).toBe(true);
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(send).not.toHaveBeenCalled();
      expect(openXhr).not.toHaveBeenCalled();
      expect(setItem).not.toHaveBeenCalled();
      expect(pushState).not.toHaveBeenCalled();
      // The injected transport method is only ever identity-checked, never invoked.
      expect(e.request).not.toHaveBeenCalled();
    } finally {
      (window as { fetch?: unknown }).fetch = originalFetch;
    }
  });

  it("keeps hasUnsentDraft and invalidateAuth stable for mount-once parent wiring", () => {
    const e = freshPane();
    const probe = e.result.current.hasUnsentDraft;
    const invalidate = e.result.current.invalidateAuth;
    e.rerender(props(e.host));
    e.rerender(props(e.host));
    expect(e.result.current.hasUnsentDraft).toBe(probe);
    expect(e.result.current.invalidateAuth).toBe(invalidate);
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => e.result.current.onMessageChange("Hold"));
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => e.result.current.hide());
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => { expect(e.result.current.open()).toBe(true); });
    act(() => e.result.current.onMessageChange(""));
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => e.result.current.onMessageChange("Back"));
    act(() => e.result.current.invalidateAuth(false));
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    expect(e.result.current.message).toBe("");
  });

  it("fails closed with masked reads when auth, generation, epoch or owner probing throws", () => {
    const e = freshPane();
    expect(e.result.current.isHostCurrent()).toBe(true);
    const getState = vi.spyOn(e.host.auth!, "getState").mockImplementation(() => {
      throw new Error("AUTH_READ_REFUSED");
    });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onMessageChange("Never"));
    e.rerender(props(e.host));
    expect(e.result.current.message).toBe("");
    getState.mockRestore();
    const generation = vi.spyOn(e.host, "invalidationGeneration").mockImplementation(() => {
      throw new Error("GENERATION_REFUSED");
    });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onMessageChange("Never"));
    e.rerender(props(e.host));
    expect(e.result.current.message).toBe("");
    generation.mockRestore();
    const throwRevision = () => { throw new Error("EPOCH_REFUSED"); };
    e.rerender({ host: e.host, authRevision: 1, currentAuthRevision: throwRevision, getExecutiveOwner });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onMessageChange("Never"));
    expect(e.result.current.message).toBe("");
    const throwOwner = () => { throw new Error("OWNER_REFUSED"); };
    e.rerender({ host: e.host, authRevision: 1, currentAuthRevision: () => epoch.value, getExecutiveOwner: throwOwner });
    expect(e.result.current.isHostCurrent()).toBe(false);
    expect(e.result.current.originalLookup).toBeNull();
    act(() => e.result.current.onMessageChange("Never"));
    expect(e.result.current.message).toBe("");
    e.rerender(props(e.host));
    act(() => e.result.current.onMessageChange("Recovered"));
    expect(e.result.current.message).toBe("Recovered");
  });

  it("round-trips the native custom-scheme origin through the actual location adapter", () => {
    const href = "tauri://localhost/os/?message=PRIVATE#PRIVATE";
    const out = writeFreshConversationLocation(href, sel(keyA), true);
    expect(out.startsWith("tauri://localhost/os/?")).toBe(true);
    expect(readFreshConversationLocation(out)).toEqual({ valid: true, open: true, selection: sel(keyA) });
    expect(safeKeysOnly(out)).toBe(true);
    expect(out).not.toContain("PRIVATE");
    const blank = writeFreshConversationLocation(href, null, true);
    expect(readFreshConversationLocation(blank)).toEqual({ valid: true, open: true, selection: null });
  });

  it("returns detached copies of lookup, owner and retained data without mutating inputs", () => {
    const input = sel(keyB);
    const e = freshPane();
    act(() => { e.result.current.onOriginalKeySelected(input); });
    expect(input).toEqual(sel(keyB));
    const lookup = e.result.current.originalLookup;
    expect(lookup?.selection).not.toBe(input);
    expect(Object.isFrozen(lookup?.selection)).toBe(true);
    expect(lookup?.owner).not.toBe(ownerRef.current);
    act(() => e.result.current.onMessageChange("Copy check"));
    expect(e.result.current.draftOwner).toEqual(ownerRef.current);
    expect(e.result.current.draftOwner).not.toBe(ownerRef.current);
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    const retained = e.result.current.retainedDraft;
    expect(retained?.selection).toEqual(sel(keyB));
    expect(retained?.selection).not.toBe(input);
    act(() => e.result.current.onOriginalKeySelected(input));
    expect(e.result.current.retainedDraft?.selection).not.toBe(input);
  });
});
