// @vitest-environment jsdom
import supplier from "../fixtures/project-journey-source-issued-388205.json";
import {decodePlanProposalOriginal} from "../planning/project-plan-proposal";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthState } from "../host";
import { ORIGINAL_OPERATION_ID_PREFIXES } from "../planning/plan-adoption-status";
import type { ProjectJourneySelection } from "./ProjectPlanningJourney";
import {
  CREATE_REQUEST_ID_HEX_CHARS,
  PLANNING_OPERATION_ID_HEX_CHARS,
  PLANNING_OPERATION_ID_PREFIX,
  PROJECT_JOURNEY_KEYS,
  projectJourneyUrl,
} from "./project-journey-location";
import {
  useProjectJourneyState,
  type ProjectJourneyHost,
  type ProjectJourneyStateProps,
} from "./useProjectJourneyState";

const hex = (chars: number, seed: string) => seed.repeat(Math.ceil(chars / seed.length)).slice(0, chars);
const createId = (seed: string) =>
  ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal + hex(CREATE_REQUEST_ID_HEX_CHARS, seed);
const planningKey = PLANNING_OPERATION_ID_PREFIX+hex(PLANNING_OPERATION_ID_HEX_CHARS, "0123456789abcdef");
const workRef = "WS:NEWPROJECT-ONE";
const jobId = "JOB-1";
const cidA = createId("a1b2c3d4e5");
const cidB = createId("f1e2d3c4b5");
const sel = (
  id = cidA,
  extra: Partial<ProjectJourneySelection> = {},
): ProjectJourneySelection => ({ createRequestId: id, workRef: null, planningOperationKey: null, jobId: null, ...extra });
const blankFlagUrl = "http://localhost:3000/os/?new_project=1";
/** Absolute helper output -> path form for replaceState in this jsdom origin. */
const toPath = (href: string) => {
  const url = new URL(href);
  return `${url.pathname}${url.search}`;
};
const ownedKeysOnly = (href: string) =>
  [...new URL(href).searchParams.keys()].every(key => (PROJECT_JOURNEY_KEYS as readonly string[]).includes(key));

let auth: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
function makeHost() {
  let generation = 0;
  const host: ProjectJourneyHost = {
    auth: {
      getState: () => auth,
      subscribe: () => () => {},
      signIn: async () => ({}),
      signOut: async () => ({}),
    },
    invalidationGeneration: () => generation,
  };
  return {
    host,
    expire: () => { auth = { status: "signed_out", reason: null, acquisition: false, content: false }; },
    bump: () => { generation += 1; },
  };
}
const epoch = { value: 1 };
const props = (host: ProjectJourneyHost): ProjectJourneyStateProps =>
  ({ host, authRevision: epoch.value, currentAuthRevision: () => epoch.value });
function setup(path = "/os/") {
  history.replaceState(null, "", path);
  const h = makeHost();
  window.MastermindMissionHost = h.host;
  const view = renderHook((p: ProjectJourneyStateProps) => useProjectJourneyState(p), { initialProps: props(h.host) });
  return { ...h, ...view };
}
type Harness = ReturnType<typeof setup>;
function mountAtSelection(value: ProjectJourneySelection) {
  return setup(toPath(projectJourneyUrl("http://localhost:3000/os/", value)));
}
function freshJourney() {
  const e = setup("/os/?new_project=1");
  act(() => { e.result.current.onSelection(sel(cidA)); });
  act(() => e.result.current.onGoalChange("Frozen"));
  return e;
}

beforeEach(() => {
  auth = { status: "signed_in", reason: null, acquisition: true, content: false };
  epoch.value = 1;
  history.replaceState(null, "", "/os/");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
});

describe("New-project journey presentation state", () => {
  it("reads the initial URL: blank flag opens, closed hides, invalid closes with invalidLink", () => {
    const blank = setup("/os/?new_project=1");
    expect(blank.result.current).toMatchObject({ shown: true, invalidLink: false, selection: null, goal: "" });
    const closed = setup("/os/");
    expect(closed.result.current).toMatchObject({ shown: false, invalidLink: false, selection: null });
    const invalid = setup("/os/?new_project=2");
    expect(invalid.result.current).toMatchObject({ shown: false, invalidLink: true, selection: null });
  });

  it("adopts an initial selection URL as detached DATA without any host inference", () => {
    const e = mountAtSelection(sel(cidA, { workRef, planningOperationKey: planningKey, jobId }));
    expect(e.result.current.selection).toEqual(sel(cidA, { workRef, planningOperationKey: planningKey, jobId }));
    expect(e.result.current.shown).toBe(true);
  });

  it("opens a blank journey at the clean flag URL and resumes the known selection after hide", () => {
    const e = setup("/os/?legacy=secret&tracking=1#fragment");
    act(() => { expect(e.result.current.open()).toBe(true); });
    expect(window.location.href).toBe(blankFlagUrl);
    expect(ownedKeysOnly(window.location.href)).toBe(true);
    expect(e.result.current).toMatchObject({ shown: true, invalidLink: false, selection: null });

    const kept = mountAtSelection(sel(cidA));
    act(() => kept.result.current.hide());
    expect(kept.result.current.shown).toBe(false);
    expect(window.location.search).toContain(`project_create_request=${cidA}`);
    act(() => { expect(kept.result.current.open()).toBe(true); });
    expect(kept.result.current.shown).toBe(true);
    expect(kept.result.current.selection).toEqual(sel(cidA));
    expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidA)));
  });

  it("writes the safe selection URL synchronously before adopting state", () => {
    const e = setup("/os/?new_project=1");
    act(() => e.result.current.onGoalChange("First"));
    const order: string[] = [];
    const real = window.history.replaceState.bind(window.history);
    vi.spyOn(window.history, "replaceState").mockImplementation(function mocked(data, unused, url) {
      order.push(e.result.current.selection?.createRequestId ?? "blank");
      return real(data, unused, url);
    } as typeof window.history.replaceState);
    act(() => { e.result.current.onSelection(sel(cidA, { workRef })); });
    expect(order).toEqual(["blank"]);
    expect(e.result.current.selection).toEqual(sel(cidA, { workRef }));
    expect(e.result.current.selection).not.toBe(sel(cidA, { workRef }));
    expect(e.result.current.goal).toBe("First");
    expect(e.result.current.goalBelongsToSelection).toBe(true);
    expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidA, { workRef })));
  });

  it("preserves state and refs when the history write throws", () => {
    const e = setup("/os/?new_project=1");
    act(() => { e.result.current.onSelection(sel(cidA)); });
    act(() => e.result.current.onGoalChange("Unsent"));
    const selectionBefore = e.result.current.selection;
    const hrefBefore = window.location.href;
    vi.spyOn(window.history, "replaceState").mockImplementation(() => {
      throw new Error("HISTORY_REFUSED");
    });
    act(() => {
      expect(() => e.result.current.onSelection(sel(cidB, { workRef }))).toThrow("HISTORY_REFUSED");
    });
    expect(e.result.current.selection).toBe(selectionBefore);
    expect(e.result.current.goal).toBe("Unsent");
    act(() => { expect(() => e.result.current.open()).toThrow("HISTORY_REFUSED"); });
    expect(e.result.current.shown).toBe(true);
    expect(window.location.href).toBe(hrefBefore);
  });

  it("carries the blank-journey goal into its own minted CREATE synchronously", () => {
    const e = setup("/os/?new_project=1");
    act(() => e.result.current.onGoalChange("Exact private draft"));
    act(() => { e.result.current.onSelection(sel(cidB)); });
    expect(e.result.current.goal).toBe("Exact private draft");
    expect(e.result.current.goalBelongsToSelection).toBe(true);
    expect(e.result.current.selection).toEqual(sel(cidB));
    expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidB)));
  });

  it("keeps the draft across own and external same-CREATE evolution", () => {
    const e = mountAtSelection(sel(cidA));
    act(() => e.result.current.onGoalChange("Keep me"));
    act(() => { e.result.current.onSelection(sel(cidA, { workRef })); });
    expect(e.result.current.goal).toBe("Keep me");
    expect(e.result.current.selection).toEqual(sel(cidA, { workRef }));
    restoreExternal(sel(cidA, { workRef, planningOperationKey: planningKey, jobId }));
    act(() => e.result.current.restoreLocation());
    expect(e.result.current.goal).toBe("Keep me");
    expect(e.result.current.goalBelongsToSelection).toBe(true);
    expect(e.result.current.selection).toEqual(sel(cidA, { workRef, planningOperationKey: planningKey, jobId }));
    expect(e.result.current.retainedGoal).toBeNull();
  });

  it("refuses the silent overwrite on an external different CREATE and returns exactly", () => {
    const e = setup("/os/?new_project=1");
    act(() => { e.result.current.onSelection(sel(cidA)); });
    act(() => e.result.current.onGoalChange("Old same-actor goal"));
    restoreExternal(sel(cidB));
    act(() => e.result.current.restoreLocation());
    expect(e.result.current).toMatchObject({ shown: true, goal: "", goalBelongsToSelection: false });
    expect(e.result.current.selection).toEqual(sel(cidB));
    expect(e.result.current.retainedGoal).toEqual({ text: "Old same-actor goal", selection: sel(cidA), passivelyHeld: false });
    act(() => { expect(e.result.current.returnToRetainedGoal()).toBe(true); });
    expect(e.result.current.goal).toBe("Old same-actor goal");
    expect(e.result.current.selection).toEqual(sel(cidA));
    expect(e.result.current.retainedGoal).toBeNull();
    expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidA)));
  });

  it("parks the owned draft when a restore closes the journey and open resumes the retained goal", () => {
    const e = mountAtSelection(sel(cidA));
    act(() => e.result.current.onGoalChange("Held across close"));
    history.replaceState(null, "", "/os/");
    act(() => e.result.current.restoreLocation());
    expect(e.result.current).toMatchObject({ shown: false, invalidLink: false, selection: null, goal: "" });
    expect(e.result.current.retainedGoal).toEqual({ text: "Held across close", selection: sel(cidA), passivelyHeld: false });
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => { expect(e.result.current.open()).toBe(true); });
    expect(e.result.current.goal).toBe("Held across close");
    expect(e.result.current.selection).toEqual(sel(cidA));
    expect(e.result.current.retainedGoal).toBeNull();
    expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidA)));
  });

  it("closes with invalidLink on an invalid restore while keeping the owned draft held", () => {
    const e = mountAtSelection(sel(cidB, { workRef }));
    act(() => e.result.current.onGoalChange("Held across invalid"));
    history.replaceState(null, "", "/os/?new_project=2");
    act(() => e.result.current.restoreLocation());
    expect(e.result.current).toMatchObject({ shown: false, invalidLink: true, selection: null, goal: "" });
    expect(e.result.current.retainedGoal).toEqual({ text: "Held across invalid", selection: sel(cidB, { workRef }), passivelyHeld: false });
    expect(e.result.current.hasUnsentDraft()).toBe(true);
  });

  const drifts: readonly (readonly [string, (e: Harness) => void, boolean])[] = [
    ["a swapped global host without a rerender", e => { window.MastermindMissionHost = makeHost().host; }, false],
    ["an epoch drift with a rerender", e => { epoch.value = 2; e.rerender(props(e.host)); }, true],
    ["a source generation drift with a rerender", e => { e.bump(); e.rerender(props(e.host)); }, true],
    ["a replaced host at rerender", e => {
      const next = makeHost();
      window.MastermindMissionHost = next.host;
      e.rerender(props(next.host));
    }, true],
  ];
  it.each(drifts)("refuses stale callbacks after %s with zero mutations", (_label, drift, rerendered) => {
    const e = freshJourney();
    const stale = e.result.current;
    const hrefBefore = window.location.href;
    const replace = vi.spyOn(window.history, "replaceState");
    drift(e);
    act(() => {
      stale.onGoalChange("Late write");
      stale.onSelection(sel(cidB));
      expect(stale.open()).toBe(false);
      stale.restoreLocation();
      expect(stale.isHostCurrent()).toBe(false);
    });
    expect(window.location.href).toBe(hrefBefore);
    expect(replace).not.toHaveBeenCalled();
    if (rerendered) {
      // The old actor's draft is foreign to the fresh render: never returned
      // as current text, while the URL selection DATA stays exposed.
      expect(e.result.current.goal).toBe("");
      expect(e.result.current.goalBelongsToSelection).toBe(false);
      expect(e.result.current.selection).toEqual(sel(cidA));
      expect(e.result.current.hasUnsentDraft()).toBe(false);
      // The fresh render's own callbacks still own the screen.
      act(() => e.result.current.onGoalChange("Fresh actor"));
      expect(e.result.current.goal).toBe("Fresh actor");
    } else {
      expect(e.result.current.goal).toBe("Frozen");
      expect(e.result.current.selection).toEqual(sel(cidA));
    }
  });

  it.each(["host", "epoch", "generation"] as const)("refuses stale hide after no-render %s drift", boundary => {
    const e = setup("/os/?new_project=1");
    const oldHide = e.result.current.hide;
    if (boundary === "host") window.MastermindMissionHost = makeHost().host;
    else if (boundary === "epoch") epoch.value += 1;
    else e.bump();
    act(() => oldHide());
    expect(e.result.current.shown).toBe(true);
  });

  it("hides invalid-link presentation locally without rewriting the original URL", () => {
    const e = setup("/os/?new_project=0");
    const original = location.href;
    expect(e.result.current.invalidLink).toBe(true);
    act(() => e.result.current.hide());
    expect(e.result.current.invalidLink).toBe(false);
    expect(e.result.current.shown).toBe(false);
    expect(location.href).toBe(original);
  });

  it("keeps the exact currency proof and refuses when a read throws", () => {
    const e = setup("/os/?new_project=1");
    expect(e.result.current.isHostCurrent()).toBe(true);
    const getState = vi.spyOn(e.host.auth!, "getState").mockImplementation(() => {
      throw new Error("AUTH_READ_REFUSED");
    });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onGoalChange("Never"));
    expect(e.result.current.goal).toBe("");
    getState.mockRestore();
    const generation = vi.spyOn(e.host, "invalidationGeneration").mockImplementation(() => {
      throw new Error("GENERATION_REFUSED");
    });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onGoalChange("Never"));
    expect(e.result.current.goal).toBe("");
    generation.mockRestore();
    const revision = vi.spyOn(e.host, "invalidationGeneration").mockReturnValue(0);
    const throwRevision = () => { throw new Error("EPOCH_REFUSED"); };
    e.rerender({ host: e.host, authRevision: 1, currentAuthRevision: throwRevision });
    expect(e.result.current.isHostCurrent()).toBe(false);
    act(() => e.result.current.onGoalChange("Never"));
    expect(e.result.current.goal).toBe("");
    revision.mockRestore();
    e.rerender(props(e.host));
    act(() => e.result.current.onGoalChange("Recovered"));
    expect(e.result.current.goal).toBe("Recovered");
  });

  it("preserves only same-host owned text at passive expiry and clears on explicit revoke", () => {
    const e = setup("/os/?new_project=1");
    act(() => { e.result.current.onSelection(sel(cidA, { workRef })); });
    act(() => e.result.current.onGoalChange("Passive held text"));
    e.expire();
    act(() => e.result.current.invalidateAuth(true));
    expect(e.result.current.goal).toBe("");
    expect(e.result.current.retainedGoal).toEqual({ text: "Passive held text", selection: sel(cidA, { workRef }), passivelyHeld: true });
    expect(e.result.current.isHostCurrent()).toBe(false);
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    // Passive held text never becomes current again by itself.
    act(() => { expect(e.result.current.returnToRetainedGoal()).toBe(false); });
    expect(e.result.current.goal).toBe("");
    // Exact held passive same-host editing stays local and works while signed out.
    act(() => e.result.current.editRetainedGoal("Edited while held"));
    expect(e.result.current.retainedGoal?.text).toBe("Edited while held");
    act(() => e.result.current.invalidateAuth(false));
    expect(e.result.current.retainedGoal).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    expect(window.location.search).toContain(`project_create_request=${cidA}`);
  });

  it("never preserves foreign-host text and never exposes owned text to an unrelated actor", () => {
    const e = setup("/os/?new_project=1");
    act(() => e.result.current.onGoalChange("First actor words"));
    const next = makeHost();
    epoch.value = 2;
    window.MastermindMissionHost = next.host;
    e.rerender(props(next.host));
    act(() => e.result.current.invalidateAuth(true));
    expect(e.result.current.goal).toBe("");
    expect(e.result.current.retainedGoal).toBeNull();
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => { expect(e.result.current.returnToRetainedGoal()).toBe(false); });
    act(() => e.result.current.editRetainedGoal("Foreign edit"));
    act(() => e.result.current.discardRetainedGoal());
    expect(e.result.current.retainedGoal).toBeNull();
  });

  it("keeps hasUnsentDraft and invalidateAuth stable for mount-once parent wiring", () => {
    const e = setup("/os/?new_project=1");
    const probe = e.result.current.hasUnsentDraft;
    const invalidate = e.result.current.invalidateAuth;
    e.rerender(props(e.host));
    e.rerender(props(e.host));
    expect(e.result.current.hasUnsentDraft).toBe(probe);
    expect(e.result.current.invalidateAuth).toBe(invalidate);
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => e.result.current.onGoalChange("Off-view hold"));
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => e.result.current.hide());
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    // Draft edits are refused while the pane is hidden; the hold stays armed.
    act(() => e.result.current.onGoalChange(""));
    expect(e.result.current.goal).toBe("Off-view hold");
    expect(e.result.current.hasUnsentDraft()).toBe(true);
    act(() => { expect(e.result.current.open()).toBe(true); });
    act(() => e.result.current.onGoalChange(""));
    expect(e.result.current.goal).toBe("");
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    act(() => e.result.current.onGoalChange("Back"));
    act(() => e.result.current.invalidateAuth(false));
    expect(e.result.current.hasUnsentDraft()).toBe(false);
    expect(e.result.current.goal).toBe("");
  });

  it("refuses an invalid selection object with no write and no adoption", () => {
    const e = setup("/os/?new_project=1");
    const before = window.location.href;
    act(() => {
      expect(() => e.result.current.onSelection({ createRequestId: "not-an-id" } as unknown as ProjectJourneySelection))
        .toThrow("PROJECT_JOURNEY_SELECTION_INVALID");
    });
    expect(window.location.href).toBe(before);
    expect(e.result.current.selection).toBeNull();
  });

  it("never writes the goal into the URL and performs no network, storage or push calls", () => {
    const fetchSpy = vi.fn();
    const originalFetch = (window as { fetch?: unknown }).fetch;
    (window as { fetch?: unknown }).fetch = fetchSpy;
    const send = vi.spyOn(XMLHttpRequest.prototype, "send");
    const openXhr = vi.spyOn(XMLHttpRequest.prototype, "open");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const pushState = vi.spyOn(window.history, "pushState");
    try {
      const e = setup("/os/?new_project=1");
      act(() => e.result.current.onGoalChange("Secret goal words"));
      act(() => { e.result.current.onSelection(sel(cidA, { workRef })); });
      act(() => { expect(e.result.current.open()).toBe(true); });
      act(() => e.result.current.hide());
      act(() => e.result.current.onGoalChange("Second secret"));
      act(() => e.result.current.restoreLocation());
      expect(window.location.href).toBe(projectJourneyUrl("http://localhost:3000/os/", sel(cidA, { workRef })));
      expect(window.location.href).not.toContain("Secret");
      expect(window.location.href).not.toContain(encodeURIComponent("Secret"));
      expect(ownedKeysOnly(window.location.href)).toBe(true);
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(send).not.toHaveBeenCalled();
      expect(openXhr).not.toHaveBeenCalled();
      expect(setItem).not.toHaveBeenCalled();
      expect(pushState).not.toHaveBeenCalled();
    } finally {
      (window as { fetch?: unknown }).fetch = originalFetch;
    }
  });
});

function restoreExternal(value: ProjectJourneySelection | null) {
  history.replaceState(null, "", value === null ? "/os/" : toPath(projectJourneyUrl(window.location.href, value)));
}


describe("safe original planning proposal navigation",()=>{
  const original=decodePlanProposalOriginal((supplier.samples[12].request as {arguments:unknown}).arguments);
  const selected:ProjectJourneySelection={createRequestId:supplier.identities.creation_request_id,
    workRef:original.work_ref,planningOperationKey:original.operation_key,jobId:original.proposal_request.selection.job_id};
  it("commits metadata before callbacks, retains Back/reopen and never remints an original",()=>{
    const h=mountAtSelection(selected);
    act(()=>h.result.current.onProposalOriginalChange(original));
    expect(h.result.current.proposalOriginal).toEqual(original);
    const href=location.href;expect(href).not.toContain('Private first request');
    act(()=>h.result.current.hide());act(()=>{expect(h.result.current.open()).toBe(true);});
    expect(h.result.current.proposalOriginal).toEqual(original);expect(location.href).toBe(href);
    h.unmount();const reopened=setup(toPath(href));expect(reopened.result.current.proposalOriginal).toEqual(original);
  });
  it("foreign job/CREATE or no-render Host replacement cannot transfer original authority",()=>{
    const h=mountAtSelection(selected);act(()=>h.result.current.onProposalOriginalChange(original));
    act(()=>h.result.current.onSelection({...selected,createRequestId:cidB}));expect(h.result.current.proposalOriginal).toBeNull();
    window.MastermindMissionHost=makeHost().host;
    expect(()=>h.result.current.onProposalOriginalChange(original)).toThrow();
    expect(h.result.current.proposalOriginal).toBeNull();
  });
});
