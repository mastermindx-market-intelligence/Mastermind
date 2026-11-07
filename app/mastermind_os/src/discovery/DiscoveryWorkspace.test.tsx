// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiscoveryWorkspace } from "./DiscoveryWorkspace";
import type { DiscoveryWorkspaceProps } from "./DiscoveryWorkspace";
import type {
  DiscoveryCapability,
  DiscoveryItem,
  DiscoverySource,
  DiscoverySystemObservation,
  DiscoveryView,
  DiscoveryLimitation,
} from "./contract";
import type { KnowledgeProps } from "../knowledge/Knowledge";
import type { OfficeProjection, ProjectionContext, SourceClaim } from "../meta-ceo/projection";
import type { MissionSelection, EvidenceRef } from "../mission";
import type { ResultSelection } from "../result";

// The embedded Knowledge owner is the one child this workspace renders. The
// mock exists only to assert the exact prop seam (forwarded readers, host
// generation, draft port, requested tuple, return callback) and that the
// detour unmounts; it is not an acceptance or source-read proof. The parent
// owns real source→draft journey tests.
const knowledgeProps = vi.hoisted(() => {
  const recorded: Array<Record<string, unknown>> = [];
  return recorded;
});
vi.mock("../knowledge/Knowledge", () => ({
  Knowledge: (props: Record<string, unknown>) => {
    knowledgeProps.push(props);
    return (
      <div data-testid="knowledge-mock">
        <p>KNOWLEDGE_MOCK</p>
        <button type="button" onClick={() => (props.onReturnToSearch as (() => void) | undefined)?.()}>
          MOCK_RETURN
        </button>
      </div>
    );
  },
}));

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

const workSelection: MissionSelection = { workRef: "work-1", rootJobId: "root-1" };
const resultSelection: ResultSelection = {
  workRef: "work-1",
  rootJobId: "root-1",
  jobId: "job-9",
  attemptId: "attempt-2",
  resultEnvelopeDigest: "sha256:abc",
};
const evidence: EvidenceRef = {
  owner: "GITHUB",
  ref: "org/repo#12",
  field: "body",
  source_revision: "rev-e1",
  source_time: "2026-11-03T10:00:00Z",
  observed_at: "2026-11-03T10:05:00Z",
  freshness_state: "CURRENT",
};
const claim = (state: SourceClaim["state"] = "CURRENT"): SourceClaim => ({
  owner: "GITHUB",
  ref: "org/repo#12",
  revision: "rev-e1",
  observed_at: "2026-11-03T10:05:00Z",
  observed_at_kind: "LOCAL_ACQUISITION",
  state,
  coverage: "Supplied window only",
});

function context(overrides: Partial<ProjectionContext> = {}): ProjectionContext {
  return {
    authGeneration: 7,
    selection: { ...workSelection },
    sessionRef: "session-1",
    bindingGeneration: "bind-1",
    revisions: { mission: "m1", programs: "p1", result: "r1", conversation: "c1" },
    ...overrides,
  };
}

const officeClaim = (): SourceClaim => ({
  owner: "EXECUTIVE_OS",
  ref: "office-ref",
  revision: "rev-1",
  observed_at: "2026-11-03T09:00:00Z",
  state: "CURRENT",
  coverage: "Supplied window only",
});
const projected = () => ({ source: officeClaim(), value: null, reason: null });

function projection(contextOverrides: Partial<ProjectionContext> = {}): OfficeProjection {
  return {
    schema: "mastermind.product_projection.v1",
    context: context(contextOverrides),
    mission: projected(),
    programs: projected(),
    result: projected(),
    conversation: projected(),
    companyTotal: null,
    receipts: {
      delivery: null,
      pickup: null,
      start: null,
      effect: null,
      return: null,
      review: null,
      acceptance: null,
    },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" },
  };
}

function baseItems(): DiscoveryItem[] {
  return [
    {
      id: "p1",
      kind: "project",
      title: "Apollo rollout",
      summary: "Current work summary",
      searchText: "apollo rollout current",
      source: claim(),
      target: { kind: "project", selection: { ...workSelection }, mode: "current" },
    },
    {
      id: "p2",
      kind: "project",
      title: "Apollo archive",
      summary: null,
      searchText: "apollo archive history",
      source: claim("STALE"),
      target: { kind: "project", selection: { ...workSelection }, mode: "history" },
    },
    {
      id: "p3",
      kind: "project",
      title: "Apollo unbound",
      summary: null,
      searchText: "apollo unbound",
      source: claim(),
      target: { kind: "project", selection: null, mode: "current" },
    },
    {
      id: "c1",
      kind: "conversation",
      title: "Standup thread",
      summary: "Observed window excerpt",
      searchText: "standup thread window",
      source: claim(),
      target: { kind: "conversation", reference: "window-1" },
    },
    {
      id: "e1",
      kind: "evidence",
      title: "Incident note",
      summary: "Evidence excerpt text",
      searchText: "incident note github",
      source: claim(),
      target: { kind: "evidence", evidence: { ...evidence }, facet: "body" },
    },
    {
      id: "e2",
      kind: "evidence",
      title: "Withheld note",
      summary: null,
      searchText: "withheld note",
      source: claim("WITHHELD"),
      target: { kind: "evidence", evidence: { ...evidence }, facet: "body" },
    },
    {
      id: "e3",
      kind: "evidence",
      title: "Unrevised note",
      summary: null,
      searchText: "unrevised note",
      source: claim(),
      target: {
        kind: "evidence",
        evidence: { ...evidence, source_revision: null },
        facet: "body",
      },
    },
    {
      id: "r1",
      kind: "result",
      title: "Nightly envelope",
      summary: "Retained result record",
      searchText: "nightly envelope retained",
      source: claim(),
      target: { kind: "result", selection: { ...resultSelection }, role: "worker" },
    },
  ];
}

function baseSources(): DiscoverySource[] {
  return [
    {
      id: "s1",
      title: "Mission record",
      owner: "EXECUTIVE_OS",
      state: "CURRENT",
      reference: "office-ref",
      revision: "rev-1",
      observedAt: "2026-11-03T09:00:00Z",
      observedKind: "LOCAL_ACQUISITION",
      sourceTime: "2026-11-03T08:00:00Z",
      coverage: "Supplied window only",
      content: "OBSERVED",
      reason: null,
    },
    {
      id: "s2",
      title: "Conversation window",
      owner: "SLACK",
      state: "STALE",
      reference: "slack-ref",
      revision: null,
      observedAt: "2026-11-03T07:30:00Z",
      observedKind: "SOURCE_OBSERVATION",
      sourceTime: null,
      coverage: "Observed window only",
      content: "REFERENCE_ONLY",
      reason: null,
    },
    {
      id: "s3",
      title: "Programs digest",
      owner: "CONTROL_ROOM_CACHE",
      state: "UNAVAILABLE",
      reference: null,
      revision: null,
      observedAt: null,
      observedKind: null,
      sourceTime: null,
      coverage: "Not supplied",
      content: "UNAVAILABLE",
      reason: "OWNER_REVISION_MISMATCH",
    },
  ];
}

function baseCapabilities(): DiscoveryCapability[] {
  return [
    { id: "direction_preview", state: "READ_ONLY", target: "meta_ceo" },
    { id: "search", state: "READ_ONLY", target: "search" },
    { id: "return_review", state: "READ_ONLY", target: "knowledge" },
    { id: "source_context", state: "READ_ONLY", target: "sources" },
    { id: "placement", state: "PREVIEW_ONLY", target: null },
    { id: "release", state: "UNAVAILABLE", target: null },
  ];
}

const baseSystem = (): DiscoverySystemObservation => ({
  provider: "provider-x",
  installed: false,
  state: "NOT_INSTALLED",
  version: null,
  detail: "No enrollment was supplied for this host.",
  observedAt: "2026-11-03T06:00:00Z",
});

const ALL_LIMITATIONS: DiscoveryLimitation[] = [
  "BOUNDED_SCOPE",
  "NO_PEOPLE_INDEX",
  "NO_GLOBAL_HISTORY",
  "NO_GENERIC_SOURCE_READER",
  "CONTROL_ROOM_NOT_SUPPLIED",
];

function view(overrides: Partial<DiscoveryView> = {}): DiscoveryView {
  return {
    context: context(),
    scope: "SUPPLIED_WORKSPACE",
    items: baseItems(),
    sources: baseSources(),
    capabilities: baseCapabilities(),
    systems: [baseSystem()],
    limitations: [...ALL_LIMITATIONS],
    ...overrides,
  };
}

let container: HTMLDivElement;
let root: Root | null = null;

function baseProps(overrides: Partial<DiscoveryWorkspaceProps> = {}): DiscoveryWorkspaceProps {
  return {
    view: view(),
    projection: projection(),
    mode: "Search",
    locale: "en",
    theme: "dark",
    ...overrides,
  };
}

async function mount(props: DiscoveryWorkspaceProps) {
  root = createRoot(container);
  await act(async () => {
    root!.render(<DiscoveryWorkspace {...props} />);
  });
}

async function rerender(props: DiscoveryWorkspaceProps) {
  await act(async () => {
    root!.render(<DiscoveryWorkspace {...props} />);
  });
}

function button(label: string) {
  const match = [...container.querySelectorAll<HTMLButtonElement>("button")].find(
    (element) => (element.getAttribute("aria-label") || element.textContent?.trim()) === label,
  );
  expect(match, `button ${label}`).toBeTruthy();
  return match!;
}

async function click(label: string) {
  await act(async () => {
    button(label).click();
  });
}

function items() {
  return [...container.querySelectorAll<HTMLElement>("[data-disc-item]")];
}

function preview() {
  const panel = container.querySelector<HTMLElement>(".discovery-preview");
  expect(panel, "preview panel").toBeTruthy();
  return panel!;
}

function searchInput() {
  const field = container.querySelector<HTMLInputElement>(".discovery-search-input");
  expect(field, "search input").toBeTruthy();
  return field!;
}

async function type(query: string) {
  const field = searchInput();
  // React tracks the instance-level value property; writing through the
  // prototype setter is what makes the synthetic onChange see the new text.
  const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    setValue.call(field, query);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function inspect(id: string) {
  const target = container.querySelector<HTMLElement>(`[data-disc-item="${id}"]`);
  expect(target, `item ${id}`).toBeTruthy();
  await act(async () => {
    target!.click();
  });
}

async function pressEscape() {
  // React collects synthetic listeners upward from the event target, so the
  // keydown must start inside the rendered tree; jsdom does not move focus on
  // click, so dispatch from the workspace root instead of activeElement.
  const target = container.querySelector(".atelier-discovery") ?? container;
  await act(async () => {
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
}

beforeEach(() => {
  knowledgeProps.length = 0;
  container = document.createElement("div");
  document.body.append(container);
});

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount();
    });
    root = null;
  }
  container.remove();
});

describe("DiscoveryWorkspace", () => {
  it("renders one bounded search hero", async () => {
    await mount(baseProps());
    const headings = container.querySelectorAll("h1");
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toBe("Search");
    expect(container.textContent).toContain("SEARCH AVAILABLE SOURCES");
    expect(container.textContent).toContain("Only the supplied workspace window is searched");
    expect(container.textContent).toContain("not established");
    expect(container.textContent).not.toContain("People0");
  });

  it("filters the supplied text case-insensitively and reports real counts", async () => {
    await mount(baseProps());
    expect(container.querySelector(".discovery-status")!.textContent).toBe("8 supplied results");
    await type("APOLLO");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("3 supplied results");
    expect(items()).toHaveLength(3);
    await type("zzz-nothing");
    expect(container.textContent!.split("No supplied results match this search.")).toHaveLength(2);
  });

  it("distinguishes unavailable and withdrawn sources from a completed empty search", async () => {
    const unavailable = view({ items: [], sources: [] });
    await mount(baseProps({ view: unavailable }));
    expect(container.querySelector('[role="status"]')!.textContent).toBe("Search sources are unavailable. No search results can be confirmed.");
    expect(container.textContent).not.toContain("No supplied results match this search.");
    await rerender(baseProps());
    await type("zzz-nothing");
    expect(container.textContent!.split("No supplied results match this search.")).toHaveLength(2);
    await rerender(baseProps({ view: unavailable, locale: "zh-CN" }));
    expect(container.querySelector('[role="status"]')!.textContent).toBe("搜索来源暂不可用，无法确认搜索结果。");
    expect(items()).toHaveLength(0);
  });

  it("scopes project, conversation and knowledge (evidence+result) types", async () => {
    await mount(baseProps());
    await click("Knowledge");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("4 supplied results");
    expect(items().map((element) => element.getAttribute("data-disc-item"))).toEqual(["e1", "e2", "e3", "r1"]);
    await click("Projects");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("3 supplied results");
    await click("Conversations");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("1 supplied result");
    await click("All");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("8 supplied results");
  });

  it("caps visible results at eight with a real counted show-all", async () => {
    const many = Array.from({ length: 10 }, (_, index): DiscoveryItem => ({
      id: `pj${index}`,
      kind: "project",
      title: `Bulk project ${index}`,
      summary: null,
      searchText: `bulk project ${index}`,
      source: claim(),
      target: { kind: "project", selection: { ...workSelection }, mode: "current" },
    }));
    await mount(baseProps({ view: view({ items: many }) }));
    expect(items()).toHaveLength(8);
    expect(container.textContent).toContain("10 supplied results");
    expect(container.textContent).toContain("nothing in the supplied window is dropped");
    await click("Show all 10 supplied results");
    expect(items()).toHaveLength(10);
  });

  it("retains owner order without reordering", async () => {
    await mount(baseProps());
    expect(items().map((element) => element.getAttribute("data-disc-item"))).toEqual(
      baseItems().map((item) => item.id),
    );
  });

  it("inspect shows exact source metadata and the observed excerpt", async () => {
    await mount(baseProps());
    expect(preview().textContent).toContain("Inspect a supplied result");
    await inspect("p1");
    const panel = preview().textContent ?? "";
    expect(panel).toContain("Apollo rollout");
    expect(panel).toContain("Observed excerpt");
    expect(panel).toContain("Current work summary");
    expect(panel).toContain("Source metadata");
    expect(panel).toContain("GITHUB");
    expect(panel).toContain("org/repo#12");
    expect(panel).toContain("rev-e1");
    expect(panel).toContain("CURRENT");
    expect(panel).toContain("Supplied window only");
  });

  it("opens projects only through the actual callback and preserves current/history", async () => {
    const onOpenProject = vi.fn();
    await mount(baseProps({ onOpenProject }));
    await inspect("p1");
    await click("Open project (current)");
    expect(onOpenProject).toHaveBeenCalledTimes(1);
    expect(onOpenProject).toHaveBeenCalledWith({ workRef: "work-1", rootJobId: "root-1" }, "current");
    await inspect("p2");
    await click("Open project (history)");
    expect(onOpenProject).toHaveBeenLastCalledWith({ workRef: "work-1", rootJobId: "root-1" }, "history");
    await rerender(baseProps());
    await inspect("p1");
    expect(button("Open project (current)").disabled).toBe(true);
    expect(preview().textContent).toContain("Project route not supplied on this surface.");
  });

  it("keeps an unbound project record closed", async () => {
    await mount(baseProps());
    await inspect("p3");
    expect(button("Open project (current)").disabled).toBe(true);
    expect(preview().textContent).toContain("This project item has no supplied selection.");
  });

  it("opens the conversation observed window only through the actual route", async () => {
    const onOpenConversation = vi.fn();
    await mount(baseProps({ onOpenConversation }));
    await inspect("c1");
    expect(preview().textContent).toContain("observed window only");
    await click("Open conversation window");
    expect(onOpenConversation).toHaveBeenCalledTimes(1);
    await rerender(baseProps());
    await inspect("c1");
    expect(button("Open conversation window").disabled).toBe(true);
    expect(preview().textContent).toContain("Conversation route not supplied on this surface.");
  });

  it("never guesses a URL or claims denial when no source route exists", async () => {
    await mount(baseProps());
    await inspect("e1");
    expect(button("Open original content").disabled).toBe(true);
    expect(preview().textContent).toContain(
      "Original content is not supplied on this surface; no source route was provided.",
    );
    expect(container.innerHTML).not.toContain("http");
    expect(container.textContent!.toLowerCase()).not.toContain("permission");
  });

  it("opens original content only for a complete CURRENT tuple, forwarded unchanged", async () => {
    const onOpenSource = vi.fn();
    await mount(baseProps({ sourceProps: { onOpenSource } as DiscoveryWorkspaceProps["sourceProps"] }));
    await inspect("e1");
    await click("Open original content");
    expect(onOpenSource).toHaveBeenCalledTimes(1);
    expect(onOpenSource).toHaveBeenCalledWith({
      owner: "GITHUB",
      ref: "org/repo#12",
      revision: "rev-e1",
      mode: "current",
    });
    await inspect("e2");
    expect(button("Open original content").disabled).toBe(true);
    expect(preview().textContent).toContain("the evidence state is WITHHELD");
    await inspect("e3");
    expect(button("Open original content").disabled).toBe(true);
    expect(preview().textContent).toContain("The supplied evidence tuple is incomplete");
  });

  it("names the exact missing port when open source cannot run", async () => {
    await mount(baseProps());
    await inspect("r1");
    expect(button("Open source").disabled).toBe(true);
    const missing = preview().textContent ?? "";
    expect(missing).toContain("readResultReferences");
    expect(missing).toContain("readResult");
    expect(missing).toContain("hostGeneration");
    const half = { readResultReferences: vi.fn(async () => ({})) } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await rerender(baseProps({ sourceProps: half }));
    expect(button("Open source").disabled).toBe(true);
    expect(preview().textContent).toContain("readResult, hostGeneration");
    const boolHost = {
      readResultReferences: vi.fn(async () => ({})),
      readResult: vi.fn(async () => ({})),
      hostGeneration: true,
    } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await rerender(baseProps({ sourceProps: boolHost }));
    expect(button("Open source").disabled).toBe(true);
    expect(preview().textContent).toContain("hostGeneration");
  });

  it("renders the real Knowledge owner with the exact requested seam", async () => {
    const readResultReferences = vi.fn(async () => ({}));
    const readResult = vi.fn(async () => ({}));
    const onOpenSource = vi.fn();
    const draftPort: NonNullable<KnowledgeProps["draftPort"]> = {
      projection: projection(),
      text: "unsent owner draft",
      revision: 3,
      insertion: null,
      append: () => true,
      undo: () => true,
    };
    const proj = projection();
    const sourceProps = {
      readResultReferences,
      readResult,
      hostGeneration: "gen-9",
      draftPort,
      onOpenSource,
    } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await mount(baseProps({ projection: proj, sourceProps }));
    await inspect("r1");
    await click("Open source");
    expect(knowledgeProps).toHaveLength(1);
    const seam = knowledgeProps[0];
    expect(seam.requestedResult).toEqual({
      workRef: "work-1",
      rootJobId: "root-1",
      jobId: "job-9",
      attemptId: "attempt-2",
      resultEnvelopeDigest: "sha256:abc",
    });
    expect(seam.projection).toBe(proj);
    expect(seam.readResultReferences).toBe(readResultReferences);
    expect(seam.readResult).toBe(readResult);
    expect(seam.hostGeneration).toBe("gen-9");
    expect(seam.draftPort).toBe(draftPort);
    expect(seam.onOpenSource).toBe(onOpenSource);
    expect(seam.locale).toBe("en");
    expect(typeof seam.onReturnToSearch).toBe("function");
    expect(container.querySelector(".discovery-heading")).toBeNull();
    expect(container.textContent).toContain("KNOWLEDGE_MOCK");
  });

  it("returning from the source keeps the query and returns focus to the item", async () => {
    const sourceProps = {
      readResultReferences: vi.fn(async () => ({})),
      readResult: vi.fn(async () => ({})),
      hostGeneration: 42,
    } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await mount(baseProps({ sourceProps }));
    await type("nightly");
    await inspect("r1");
    await click("Open source");
    await click("MOCK_RETURN");
    expect(container.querySelector('[data-testid="knowledge-mock"]')).toBeNull();
    expect(searchInput().value).toBe("nightly");
    expect(document.activeElement?.getAttribute("data-disc-item")).toBe("r1");
  });

  it("shows unavailable, not stale content, when the record leaves the window", async () => {
    const sourceProps = {
      readResultReferences: vi.fn(async () => ({})),
      readResult: vi.fn(async () => ({})),
      hostGeneration: "gen-1",
    } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await mount(baseProps({ sourceProps }));
    await inspect("r1");
    await click("Open source");
    expect(knowledgeProps.length).toBe(1);
    const reduced = view({ items: baseItems().filter((item) => item.id !== "r1") });
    await rerender(baseProps({ view: reduced, sourceProps }));
    expect(container.textContent).toContain("This item is no longer in the supplied window.");
    expect(knowledgeProps.length).toBe(1);
    await click("Back to search");
    expect(searchInput()).toBeTruthy();
    expect(container.querySelector(".discovery-status")!.textContent).toBe("7 supplied results");
  });

  it("clears private query and selection before paint when identity changes", async () => {
    const sourceProps = {
      readResultReferences: vi.fn(async () => ({})),
      readResult: vi.fn(async () => ({})),
      hostGeneration: "gen-1",
    } as unknown as DiscoveryWorkspaceProps["sourceProps"];
    const readers = () =>
      ({
        readResultReferences: vi.fn(async () => ({})),
        readResult: vi.fn(async () => ({})),
      }) as unknown as DiscoveryWorkspaceProps["sourceProps"];
    await mount(baseProps({ sourceProps }));
    await type("apollo");
    await inspect("p1");
    expect(preview().textContent).toContain("Apollo rollout");
    // Auth generation moves; the derived view is re-supplied with it.
    await rerender(
      baseProps({
        projection: projection({ authGeneration: 8 }),
        view: view({ context: context({ authGeneration: 8 }) }),
        sourceProps,
      }),
    );
    expect(searchInput().value).toBe("");
    expect(preview().textContent).toContain("Inspect a supplied result");
    // Selected work moves.
    await type("apollo");
    await inspect("p1");
    await rerender(
      baseProps({
        projection: projection({ selection: { workRef: "work-2", rootJobId: "root-1" } }),
        view: view({ context: context({ selection: { workRef: "work-2", rootJobId: "root-1" } }) }),
        sourceProps,
      }),
    );
    expect(searchInput().value).toBe("");
    // Binding generation moves.
    await type("apollo");
    await inspect("p1");
    await rerender(
      baseProps({
        projection: projection({ bindingGeneration: "bind-2" }),
        view: view({ context: context({ bindingGeneration: "bind-2" }) }),
        sourceProps,
      }),
    );
    expect(searchInput().value).toBe("");
    // The caller's actual host generation moves.
    await type("apollo");
    await inspect("p1");
    await rerender(baseProps({ sourceProps: { ...readers(), hostGeneration: "gen-2" } as DiscoveryWorkspaceProps["sourceProps"] }));
    expect(searchInput().value).toBe("");
    expect(preview().textContent).toContain("Inspect a supplied result");
  });

  it("renders unavailable without private content on context mismatch", async () => {
    await mount(baseProps());
    await type("apollo");
    await inspect("p1");
    await rerender(baseProps({ projection: projection({ authGeneration: 99 }) }));
    expect(container.querySelectorAll("h1")).toHaveLength(1);
    expect(container.querySelector("h1")!.textContent).toBe("Unavailable");
    expect(container.querySelector(".discovery-search-input")).toBeNull();
    expect(container.textContent).not.toContain("Apollo rollout");
    expect(container.textContent).not.toContain("org/repo#12");
    expect(container.textContent).not.toContain("provider-x");
    expect(container.textContent).not.toContain("BOUNDED_SCOPE");
    // Revision drift alone is enough.
    const drifted = projection();
    drifted.context.revisions = { ...drifted.context.revisions, mission: "m2" };
    await rerender(baseProps({ projection: drifted }));
    expect(container.querySelector("h1")!.textContent).toBe("Unavailable");
    // Selected-work drift alone is enough.
    await rerender(baseProps({ projection: projection({ selection: { workRef: "work-9", rootJobId: "root-1" } }) }));
    expect(container.querySelector("h1")!.textContent).toBe("Unavailable");
  });

  it("separates observed, reference-only and unavailable sources with clocks", async () => {
    const onRefreshSources = vi.fn();
    const onOpenPreferences = vi.fn();
    await mount(baseProps({ mode: "Sources", onRefreshSources, onOpenPreferences }));
    expect(container.querySelector("h1")!.textContent).toBe("Sources");
    expect(container.textContent).toContain("Review missing evidence and freshness");
    expect(container.textContent).toContain("Observed copy");
    expect(container.textContent).toContain("Reference only");
    const explained = (container.textContent ?? "").replace(
      "Health, connectivity or live status is not inferred here.",
      "",
    );
    expect(/health|connected|live/i.test(explained)).toBe(false);
    await inspect("source:s1");
    const panel = preview().textContent ?? "";
    expect(panel).toContain("Mission record");
    expect(panel).toContain("Local acquisition");
    expect(panel).toContain("2026-11-03T09:00:00Z");
    expect(panel).toContain("2026-11-03T08:00:00Z");
    expect(panel).toContain("a decoded projection, not the full canonical original");
    await inspect("source:s2");
    expect(preview().textContent).toContain("This is not an access denial");
    await inspect("source:s3");
    expect(preview().textContent).toContain("OWNER_REVISION_MISMATCH");
    await click("Refresh observations");
    expect(onRefreshSources).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Dark");
    await click("Open display preferences");
    expect(onOpenPreferences).toHaveBeenCalledTimes(1);
  });

  it("closes source controls when their callbacks are absent", async () => {
    await mount(baseProps({ mode: "Sources" }));
    expect(button("Refresh observations").disabled).toBe(true);
    expect(container.textContent).toContain("Refreshing observations is not supplied on this surface.");
    expect(button("Open display preferences").disabled).toBe(true);
    expect(container.textContent).toContain("Display preferences are not supplied on this surface.");
    expect(container.textContent).toContain("Not supplied");
  });

  it("shows supplied system observations and limitations as plain observations", async () => {
    await mount(baseProps({ mode: "Sources" }));
    expect(container.textContent).toContain("System observations");
    expect(container.textContent).toContain("provider-x");
    expect(container.textContent).toContain("NOT_INSTALLED");
    expect(container.textContent).toContain("No enrollment was supplied for this host.");
    expect(container.textContent).toContain("BOUNDED_SCOPE");
    expect(container.textContent).toContain("only the supplied window is searched");
    expect(container.textContent).toContain("NO_PEOPLE_INDEX");
    expect(container.textContent!.toLowerCase()).not.toContain("manage access");
  });

  it("gates tools on capability state plus the actual callback", async () => {
    const onModeChange = vi.fn();
    const onOpenMetaCeo = vi.fn();
    const onOpenKnowledge = vi.fn();
    await mount(baseProps({ mode: "Tools", onModeChange, onOpenMetaCeo, onOpenKnowledge }));
    expect(container.querySelector("h1")!.textContent).toBe("Tools");
    expect(container.textContent).toContain("CAPABILITIES, IN CONTEXT");
    expect(container.textContent).toContain("Project context");
    expect(container.textContent).toContain("work-1");
    await click("Search");
    await click("Open search");
    expect(onModeChange).toHaveBeenCalledWith("Search");
    await click("Source context");
    await click("Open source context");
    expect(onModeChange).toHaveBeenCalledWith("Sources");
    await click("Direction preview");
    await click("Open Meta-CEO office");
    expect(onOpenMetaCeo).toHaveBeenCalledTimes(1);
    await click("Return review");
    await click("Open return review");
    expect(onOpenKnowledge).toHaveBeenCalledTimes(1);
    await click("Placement");
    expect(button("Open placement").disabled).toBe(true);
    expect(container.textContent).toContain("never accepts or releases");
    await click("Release");
    expect(button("Open release").disabled).toBe(true);
    // An UNAVAILABLE capability stays closed even with a live callback.
    const caps = baseCapabilities().map((capability) =>
      capability.id === "search" ? { ...capability, state: "UNAVAILABLE" as const } : capability,
    );
    await rerender(baseProps({ mode: "Tools", onModeChange, onOpenMetaCeo, onOpenKnowledge, view: view({ capabilities: caps }) }));
    await click("Search");
    expect(button("Open search").disabled).toBe(true);
    expect(container.textContent).toContain("Unavailable in the supplied capabilities");
    // A capability id never invents an absent or different owner destination.
    await rerender(baseProps({ mode: "Tools", onOpenMetaCeo, view: view({ capabilities:
      baseCapabilities().map((capability) => capability.id === "direction_preview"
        ? { ...capability, target: null } : capability) }) }));
    await click("Direction preview");
    expect(button("Open Meta-CEO office").disabled).toBe(true);
    // Missing callbacks keep read-only cards closed and name the exact port.
    await rerender(baseProps({ mode: "Tools" }));
    await click("Direction preview");
    expect(button("Open Meta-CEO office").disabled).toBe(true);
    expect(container.textContent).toContain("Meta-CEO route");
    await click("Return review");
    expect(button("Open return review").disabled).toBe(true);
    await click("Source context");
    expect(button("Open source context").disabled).toBe(true);
    expect(container.textContent!.toLowerCase()).not.toContain("manage access");
  });

  it("escape closes the selection without losing the query and restores focus", async () => {
    await mount(baseProps());
    await type("apollo");
    await inspect("p1");
    await pressEscape();
    expect(searchInput().value).toBe("apollo");
    expect(preview().textContent).toContain("Inspect a supplied result");
    expect(document.activeElement?.getAttribute("data-disc-item")).toBe("p1");
  });

  it("guards Enter navigation during IME composition", async () => {
    await mount(baseProps());
    await type("apollo");
    const field = searchInput();
    await act(async () => {
      field.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "ap" }));
    });
    await act(async () => {
      field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    expect(preview().textContent).toContain("Inspect a supplied result");
    await act(async () => {
      field.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "apollo" }));
    });
    await act(async () => {
      field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    expect(preview().textContent).toContain("Apollo rollout");
  });

  it("localizes static labels for zh-CN and leaves supplied records raw", async () => {
    await mount(baseProps({ locale: "zh-CN" }));
    expect(container.querySelector(".atelier-discovery")!.getAttribute("lang")).toBe("zh-CN");
    expect(container.querySelector("h1")!.textContent).toBe("搜索");
    expect(container.textContent).toContain("搜索可用来源");
    expect(container.textContent).toContain("项目");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("8 条已提供结果");
    await inspect("e1");
    const panel = preview().textContent ?? "";
    expect(panel).toContain("证据上下文");
    expect(panel).toContain("GITHUB");
    expect(panel).toContain("org/repo#12");
  });

  it("keeps the query when the caller swaps Search/Sources/Tools on one key", async () => {
    await mount(baseProps());
    await type("apollo");
    await rerender(baseProps({ mode: "Sources" }));
    await rerender(baseProps({ mode: "Tools" }));
    await rerender(baseProps({ mode: "Search" }));
    expect(searchInput().value).toBe("apollo");
    expect(container.querySelector(".discovery-status")!.textContent).toBe("3 supplied results");
  });
});
