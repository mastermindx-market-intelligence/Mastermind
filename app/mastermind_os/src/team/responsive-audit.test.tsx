// @vitest-environment jsdom
/* L2 responsive + keyboard hardening audit (390px mobile boards / 1440px
 * desktop) for the lane's NEW surfaces: HC18/HC12/HC19 (conversation
 * surfaces), HC10 (routines), HC20/HC21 (work-search), HC11 (code settings),
 * HC07 (code workbench), TD06/TD07 (project route review + run outcome).
 *
 * HONESTY NOTE — these are CONTRACT assertions, not rendered-layout proof.
 * jsdom has no layout engine: it never applies stylesheets and cannot
 * measure a box. What these tests actually prove:
 *   1. The stylesheet TEXT ships the responsive contract we authored
 *      (single-column collapse blocks that cover 390px/480px, full-width
 *      rails, wide-desktop measure caps, secondary contrast on :disabled,
 *      champagne focus rings) — parsed from the shipped .css source.
 *   2. The component DOM keeps every interactive control keyboard-reachable
 *      (real focus() in jsdom), uses no positive tabIndex (so DOM order IS
 *      the browser tab order), keeps authored roving tab stops, and keeps
 *      its Escape behavior.
 * A passing suite therefore locks the shipped contract; it does not
 * screenshot the 390px render. */
import React from "react";
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchContextView } from "./SearchContextView";
import { WorkHierarchyView } from "./WorkHierarchyView";
import { InboxNeedsYouPanel } from "./InboxNeedsYouPanel";
import { ReplyThreadPanel } from "./ReplyThreadPanel";
import { SplitConversationsWorkspace } from "./SplitConversationsWorkspace";
import { RoutinesPanel } from "./RoutinesPanel";
import { CodeSettingsPanel } from "../code/CodeSettingsPanel";
import { CodeWorkbench } from "../code/CodeWorkbench";
import { ProjectRouteReview } from "../projects/ProjectRouteReview";
import { ProjectRunOutcome } from "../projects/ProjectRunOutcome";

afterEach(cleanup);

/* ── Stylesheet reading (the vitest CSS pipeline only processes
 *  styles.css?raw; sibling tests read the .css from disk the same way).
 *  Vitest runs with cwd at the app root. */
const CSS_FILES = {
  conversation: "src/team/conversation-surfaces.css",
  workSearch: "src/team/work-search.css",
  routines: "src/team/routines.css",
  codeSettings: "src/code/code-settings.css",
  code: "src/code/code.css",
  routeRun: "src/projects/project-route-run.css",
} as const;

function readCss(path: string): string {
  return readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

/** One rule block, with the enclosing @media condition when nested. */
interface RuleBlock {
  selector: string;
  body: string;
  /** e.g. "(max-width: 800px)" for rules inside that media query; "" at top level. */
  media: string;
}

/** Split a stylesheet into rule blocks with brace matching (comments
 *  stripped first, so comment text can never confuse the walker). */
function ruleBlocks(css: string, media = ""): RuleBlock[] {
  const blocks: RuleBlock[] = [];
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf("{", i);
    if (open === -1) break;
    const selector = css.slice(i, open).trim();
    let depth = 1;
    let j = open + 1;
    while (j < css.length && depth > 0) {
      if (css[j] === "{") depth++;
      else if (css[j] === "}") depth--;
      j++;
    }
    const body = css.slice(open + 1, j - 1);
    if (selector.startsWith("@media")) {
      blocks.push(...ruleBlocks(body, selector.slice("@media".length).trim()));
    } else if (selector) {
      blocks.push({ selector, body, media });
    }
    i = j;
  }
  return blocks;
}

function blocks(path: string): RuleBlock[] {
  return ruleBlocks(readCss(path));
}

/** True when the block's grid collapses to exactly one fluid column — the
 *  authored form is either `1fr` or `minmax(0, 1fr)`. */
function isSingleColumn(body: string): boolean {
  return /grid-template-columns:\s*(?:minmax\(0,\s*1fr\)|1fr)\s*;/.test(body);
}

/** Find blocks whose selector list contains `selector` verbatim. */
function rulesFor(all: RuleBlock[], selector: string): RuleBlock[] {
  return all.filter((block) =>
    block.selector.split(",").map((part) => part.trim()).includes(selector),
  );
}

describe("L2 responsive contract — collapsed columns at 390px/480px", () => {
  it("every authored multi-column grid has a single-column collapse inside a max-width media query that covers the mobile boards", () => {
    const collapses: { path: string; selector: string }[] = [
      { path: CSS_FILES.conversation, selector: ".mm-cv-inbox-grid" },
      { path: CSS_FILES.conversation, selector: ".mm-cv-split-grid" },
      { path: CSS_FILES.workSearch, selector: ".mm-search-view" },
      { path: CSS_FILES.workSearch, selector: ".mm-work-view" },
      { path: CSS_FILES.routines, selector: ".mm-routines-grid" },
      { path: CSS_FILES.codeSettings, selector: ".mm-cs-body" },
      { path: CSS_FILES.code, selector: ".mm-workbench-grid" },
      { path: CSS_FILES.routeRun, selector: ".mm-route-review-grid" },
      { path: CSS_FILES.routeRun, selector: ".mm-run-grid" },
    ];
    for (const { path, selector } of collapses) {
      const collapse = blocks(path).find(
        (block) =>
          block.media.startsWith("(max-width:") &&
          rulesFor([block], selector).length > 0 &&
          isSingleColumn(block.body),
      );
      expect(collapse, `${selector} in ${path} must collapse to a single column inside a max-width media query`).toBeTruthy();
      // The collapse breakpoint must cover the 390px and 480px boards.
      const maxWidth = Number(/max-width:\s*(\d+)px/.exec(collapse!.media)?.[1]);
      expect(maxWidth).toBeGreaterThanOrEqual(480);
    }
  });

  it("no fixed grid track wider than the 390px viewport survives without a collapse rule (future-rail guard)", () => {
    for (const path of Object.values(CSS_FILES)) {
      for (const block of blocks(path)) {
        if (block.media) continue; // only authored desktop tracks matter
        const fixedTracks = [...block.body.matchAll(/grid-template-columns:[^;]*;/g)]
          .flatMap((match) => [...match[0].matchAll(/(\d+(?:\.\d+)?)px/g)])
          .map((track) => Number(track[1]))
          .filter((px) => px > 390);
        if (fixedTracks.length === 0) continue;
        // A fixed track wider than 390 must be part of a grid that collapses.
        for (const selector of block.selector.split(",").map((s) => s.trim())) {
          const collapse = blocks(path).find(
            (candidate) =>
              candidate.media.startsWith("(max-width:") &&
              rulesFor([candidate], selector).length > 0 &&
              isSingleColumn(candidate.body),
          );
          expect(
            collapse,
            `${selector} in ${path} has a fixed track wider than 390px (${fixedTracks.join(", ")}) but no single-column collapse`,
          ).toBeTruthy();
        }
      }
    }
  });

  it("no top-level element width exceeds 390px unless the same rule caps it at 100%", () => {
    for (const path of Object.values(CSS_FILES)) {
      for (const block of blocks(path)) {
        if (block.media) continue;
        const width = /(?:^|;)\s*width:\s*(\d+(?:\.\d+)?)px/.exec(`;${block.body.replace(/\n/g, " ")}`);
        if (!width) continue;
        const px = Number(width[1]);
        if (px <= 390) continue;
        expect(
          /max-width:\s*100%/.test(block.body),
          `${block.selector} in ${path} sets width: ${px}px at top level without max-width: 100%`,
        ).toBe(true);
      }
    }
  });

  it("fixed rails become full-width at ≤480px (thread 344 panel; routines select never relies on intrinsic option width)", () => {
    const thread = blocks(CSS_FILES.conversation).find(
      (block) => block.media === "(max-width: 480px)" && block.selector === ".mm-cv-thread",
    );
    expect(thread).toBeTruthy();
    expect(thread!.body).toContain("width: 100%");

    const select = blocks(CSS_FILES.routines).find(
      (block) => block.media === "(max-width: 480px)" && block.selector === ".mm-routines-select",
    );
    expect(select).toBeTruthy();
    expect(select!.body).toContain("width: 100%");
    expect(select!.body).toContain("max-width: none");
  });

  it("outer gutters come from the shell (main padding), and the lane files add no horizontal negative margins that would defeat them", () => {
    // Authored vertical pull-ups (e.g. margin: -8px 0 0) are legal; only a
    // negative HORIZONTAL margin could pull a rail past the shell gutter.
    for (const path of Object.values(CSS_FILES)) {
      const css = readCss(path);
      expect(css, `${path}: margin-left`).not.toMatch(/margin-left:\s*-/);
      expect(css, `${path}: margin-right`).not.toMatch(/margin-right:\s*-/);
      expect(css, `${path}: margin-inline`).not.toMatch(/margin-inline[^;:]*:\s*-/);
    }
  });
});

describe("L2 responsive contract — wide desktop (≥1440px) keeps readable measure", () => {
  it("multi-column surfaces cap their content columns at the authored widths", () => {
    // Conversation surfaces: the 304-rail + detail grid and the split grid
    // cap at 1384px total; the shell absorbs anything wider.
    for (const selector of [".mm-cv-inbox-grid", ".mm-cv-split-grid"]) {
      const rule = blocks(CSS_FILES.conversation).find(
        (block) => !block.media && rulesFor([block], selector).length > 0,
      );
      expect(rule, `${selector} top-level rule`).toBeTruthy();
      expect(rule!.body).toContain("max-width: 1384px");
    }
    // Routines (744 editor + 344 rail) and code settings (248 nav + content)
    // center inside 1120px.
    for (const [path, selector] of [
      [CSS_FILES.routines, ".mm-routines-grid"],
      [CSS_FILES.codeSettings, ".mm-cs-body"],
    ] as const) {
      const rule = blocks(path).find(
        (block) => !block.media && rulesFor([block], selector).length > 0,
      );
      expect(rule, `${selector} top-level rule`).toBeTruthy();
      expect(rule!.body).toContain("max-width: 1120px");
    }
    // Work-search: the 448 results column is fixed and the context column is
    // capped at 920px — beyond that the grid leaves the rest to the shell.
    const view = blocks(CSS_FILES.workSearch).find(
      (block) => !block.media && rulesFor([block], ".mm-search-view").length > 0,
    );
    expect(view).toBeTruthy();
    expect(view!.body).toContain("448px minmax(0, 920px)");
    // Code workbench: conversation ≤ 640px and work panels ≤ 480px.
    const workbench = blocks(CSS_FILES.code).find(
      (block) => !block.media && rulesFor([block], ".mm-workbench-grid").length > 0,
    );
    expect(workbench).toBeTruthy();
    expect(workbench!.body).toContain("minmax(400px, 640px)");
    expect(workbench!.body).toContain("minmax(320px, 480px)");
  });
});

describe("L2 responsive contract — fixed slots and type at narrow widths", () => {
  it("the detail avatar keeps its fixed slot (flexShrink 0) so wrapped rows stay aligned", () => {
    const avatar = blocks(CSS_FILES.conversation).find(
      (block) => !block.media && block.selector === ".mm-cv-detail-avatar",
    );
    expect(avatar).toBeTruthy();
    expect(avatar!.body).toContain("flex-shrink: 0");
  });

  it("the search query label keeps its fixed slot so the query text aligns across rows", () => {
    const label = blocks(CSS_FILES.workSearch).find(
      (block) => !block.media && block.selector === ".mm-search-query-label",
    );
    expect(label).toBeTruthy();
    expect(label!.body).toContain("flex-shrink: 0");
  });

  it("≤480px keeps every font size the lane ships at or above 11px (readable, no micro-type)", () => {
    for (const path of Object.values(CSS_FILES)) {
      for (const block of blocks(path)) {
        if (block.media !== "(max-width: 480px)") continue;
        for (const size of [...block.body.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)]) {
          expect(Number(size[1]), `${block.selector} in ${path}`).toBeGreaterThanOrEqual(11);
        }
      }
    }
  });
});

describe("L2 known-defects contract — disabled contrast and focus (AT17/22 not replicated)", () => {
  it("every :disabled rule that sets a color uses --noir-text-secondary, never a lower-contrast gray", () => {
    for (const path of Object.values(CSS_FILES)) {
      for (const block of blocks(path)) {
        if (!block.selector.includes(":disabled")) continue;
        const color = /(?:^|;)\s*color:\s*([^;]+);/.exec(`;${block.body.replace(/\n/g, " ")}`);
        if (!color) continue;
        expect(
          color[1].trim(),
          `${block.selector} in ${path} must keep disabled text at --noir-text-secondary`,
        ).toBe("var(--noir-text-secondary)");
      }
    }
  });

  it("the preview-only submit (always disabled) is authored at secondary contrast", () => {
    const submit = blocks(CSS_FILES.routeRun).find(
      (block) => !block.media && block.selector === ".mm-route-submit",
    );
    expect(submit).toBeTruthy();
    expect(submit!.body).toContain("color: var(--noir-text-secondary)");
  });

  it("every surface stylesheet that draws its own focus ring uses the champagne outline", () => {
    for (const path of [
      CSS_FILES.conversation,
      CSS_FILES.workSearch,
      CSS_FILES.routines,
      CSS_FILES.codeSettings,
      CSS_FILES.code,
    ]) {
      const focusRules = blocks(path).filter((block) => block.selector.includes(":focus-visible"));
      expect(focusRules.length, `${path} ships focus-visible rules`).toBeGreaterThan(0);
      for (const rule of focusRules) {
        // Rules that only adjust colors must still leave a visible ring; the
        // shared ring is the champagne outline asserted here.
        if (rule.body.includes("outline")) {
          expect(rule.body).toContain("outline: 2px solid var(--noir-champagne)");
        }
      }
    }
  });
});

/* ── Component fixtures. Fixtures are PROP DATA ONLY and live in this test
 *  file — no sample data ships in the components (the Paper samples are
 *  forbidden in shipped copy; they never appear outside *.test.*). */
function makeBot(id: string, displayName: string) {
  return {
    id,
    displayName,
    role: "Teammate",
    managed: true,
    host: "m2studio",
    gateway: {
      observed: true,
      source: "control_socket_identify",
      instanceId: "gw-1",
      authorityEpoch: 3,
      codeVersion: "1.0.0",
      pid: 4242,
      state: "OPENED",
    },
    readiness: "ready",
    readinessReason: "GATEWAY_IDENTIFY_READY",
    lastActivity: "2026-11-09T00:00:00Z",
    activitySummary: "Answering",
  };
}

const rosterRead = {
  kind: "AVAILABLE" as const,
  roster: {
    schema: "mastermind.team_roster/v1",
    generatedAt: "2026-11-09T00:00:00Z",
    host: "m2studio",
    bots: [makeBot("scrum", "Daily Scrum Bot"), makeBot("quiet", "Quiet Analyst")],
  },
};

const inboxRequests = [
  {
    id: "r1",
    teammateId: "scrum",
    kind: "question" as const,
    summary: "Which sleeve owns the overnight sweep?",
    waitingSince: "2026-11-08T23:30:00Z",
    options: ["Engineering owns it", "Let the routine decide"],
    conversationExcerpt: [
      { author: "Daily Scrum Bot", text: "Asking about sleeve ownership.", at: "2026-11-08T23:30:00Z" },
    ],
  },
  {
    id: "r2",
    teammateId: "quiet",
    kind: "result_review" as const,
    summary: "Review the route-preview result before it is archived.",
    waitingSince: "2026-11-08T10:00:00Z",
    options: undefined,
    conversationExcerpt: null,
  },
];

const searchResults = [
  {
    id: "m1",
    conversationId: "c-alpha",
    conversationTitle: "Alpha room",
    author: "Engineering",
    text: "The route review landed",
    at: "2026-11-08T09:00:00Z",
    surrounding: {
      before: [{ author: "Director C", text: "Morning check starts now", at: "2026-11-08T08:59:00Z" }],
      after: [],
    },
  },
  {
    id: "m2",
    conversationId: "c-beta",
    conversationTitle: "Beta room",
    author: "Ops",
    text: "route review from ops",
    at: "2026-11-08T11:00:00Z",
    surrounding: null,
  },
];

const parentWork = [
  { id: "w1", title: "Teamlink adapter", meta: "Mastermind OS · wave 4" },
  { id: "w2", title: "Fleet route hardening", meta: null },
];

const delegatedWork = [
  { id: "t1", title: "Repair launch refusal", state: "queued" as const, owner: "Director C" },
  { id: "t2", title: "Verify route preview", state: "running" as const, owner: "Engineering" },
];

const selectedTask = {
  id: "t1",
  title: "Repair launch refusal",
  owner: "Director C",
  facts: [{ label: "Complexity", value: "C2_COMPLEX_BOUNDED" }],
  timeline: [
    { step: "Handoff admitted", state: "done" as const, at: "2026-11-08T09:00:00Z" },
    { step: "Runtime slot", state: "pending" as const, at: null },
  ],
};

const routineRecord = {
  name: "Morning portfolio sweep",
  status: "scheduled" as const,
  instruction: "Summarize overnight moves for the sleeve owners.",
  repeatRule: "Weekdays at launch",
  timezone: "Asia/Shanghai",
  deliveryTargetId: "scrum",
  latestRun: {
    finishedAt: "2026-11-08T01:00:00Z",
    executionState: "finished" as const,
    deliveryState: "delivered" as const,
  },
  recentRuns: [],
};

const providers = [
  {
    id: "glm-fabric",
    name: "GLM Fabric",
    ready: true,
    executable: "/opt/fabric/bin/agent",
    args: "--stdio",
    defaultModel: "glm-5.3",
    connectionAuth: "held" as const,
    capabilities: [{ label: "Runs / streaming", state: "available" as const, note: null }],
  },
];

const environments = [
  { id: "m2studio", label: "M2 Studio" },
  { id: "hermes-shell", label: "Hermes Shell" },
];

const routeReview = {
  root_run_ref: "root-wo19-coding-7",
  immediate_parent_run_ref: "run-41",
  logical_child_key: "fleet-launch-repair",
  operation_key: "op-77",
  runtime_kind: "fabric-native",
  task_kind: "code",
  effective_complexity: "C2_COMPLEX_BOUNDED",
  request_digest: "a".repeat(64),
  host: null,
  runtime: null,
  engine: null,
  model: null,
  pool: null,
};

/* ── Keyboard reachability helpers (jsdom focus is real; layout is not). */

/** Everything a browser Tab would stop on, in DOM order. jsdom cannot walk
 *  Tab itself, so this is the ordered proxy: no positive tabIndex anywhere
 *  means DOM order == tab order (asserted per surface below). */
function tabStops(root: ParentNode): HTMLElement[] {
  const nodes = root.querySelectorAll<HTMLElement>(
    "button, input, select, textarea, a[href], [tabindex]",
  );
  return Array.from(nodes).filter((el) => {
    if (el.hasAttribute("disabled")) return false;
    if (el.getAttribute("tabindex") === "-1") return false;
    if (el.closest("[hidden]")) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    return true;
  });
}

/** Assert the reachability contract for a mounted surface: no positive
 *  tabIndex, at least one tab stop, every stop actually takes focus, and
 *  every enabled interactive control is either a stop or an authored
 *  roving row (tabindex -1 with a focused sibling in its list). */
function expectKeyboardReachable(container: HTMLElement, label: string): HTMLElement[] {
  const stops = tabStops(container);
  expect(stops.length, `${label}: at least one tab stop`).toBeGreaterThan(0);
  for (const el of container.querySelectorAll<HTMLElement>("[tabindex]")) {
    expect(
      Number(el.getAttribute("tabindex")),
      `${label}: positive tabIndex would break DOM tab order`,
    ).toBeLessThanOrEqual(0);
  }
  for (const el of stops) {
    el.focus();
    expect(document.activeElement, `${label}: ${el.className || el.tagName} must take focus`).toBe(el);
  }
  const enabled = Array.from(
    container.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href]"),
  ).filter((el) => !el.hasAttribute("disabled") && !el.closest("[hidden]") && !el.closest('[aria-hidden="true"]'));
  for (const control of enabled) {
    // A tabindex -1 control is reachable when it is a member of an authored
    // roving group (same class + role) that keeps one tab stop; the arrow
    // movement itself is asserted per surface below.
    const reachable =
      stops.includes(control) ||
      (control.getAttribute("tabindex") === "-1" &&
        stops.some(
          (stop) =>
            stop.className === control.className &&
            stop.getAttribute("role") === control.getAttribute("role"),
        ));
    expect(reachable, `${label}: enabled control "${control.textContent?.slice(0, 40)}" must be keyboard-reachable`).toBe(true);
  }
  return stops;
}

describe("L2 keyboard hardening — component reachability and Escape (jsdom)", () => {
  it("SearchContextView: rows keep one roving tab stop, arrows move focus, Escape clears the selection", () => {
    const onCloseSelection = vi.fn();
    const { container } = render(
      <SearchContextView
        query="route review"
        results={searchResults}
        selectedId="m1"
        onSelectResult={() => {}}
        onCloseSelection={onCloseSelection}
      />,
    );
    expectKeyboardReachable(container, "SearchContextView");
    // Exactly one search row is a tab stop (roving tabindex).
    const rows = Array.from(container.querySelectorAll<HTMLElement>(".mm-search-row"));
    expect(rows).toHaveLength(2);
    expect(rows.filter((row) => row.tabIndex === 0)).toHaveLength(1);
    expect(rows.filter((row) => row.tabIndex === -1)).toHaveLength(1);
    // ArrowDown moves focus within the list without leaving it.
    rows[0]!.focus();
    fireEvent.keyDown(rows[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1]!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(rows[0]);
    // Escape clears the selection through the provided callback.
    fireEvent.keyDown(container.querySelector(".mm-search-surface")!, { key: "Escape" });
    expect(onCloseSelection).toHaveBeenCalledTimes(1);
  });

  it("WorkHierarchyView: task rows keep one roving tab stop; Escape clears the selection", () => {
    const onCloseSelection = vi.fn();
    const { container } = render(
      <WorkHierarchyView
        parentWork={parentWork}
        delegated={delegatedWork}
        selectedTask={selectedTask}
        onOpenTask={() => {}}
        onCompose={() => {}}
        onCloseSelection={onCloseSelection}
      />,
    );
    expectKeyboardReachable(container, "WorkHierarchyView");
    const rows = Array.from(container.querySelectorAll<HTMLElement>(".mm-work-task-row"));
    expect(rows.filter((row) => row.tabIndex === 0)).toHaveLength(1);
    rows[0]!.focus();
    fireEvent.keyDown(rows[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(container.querySelector(".mm-work-surface")!, { key: "Escape" });
    expect(onCloseSelection).toHaveBeenCalledTimes(1);
  });

  it("InboxNeedsYouPanel: request cards, search and composer controls stay reachable; disabled controls are excluded", () => {
    const { container } = render(
      <InboxNeedsYouPanel
        roster={rosterRead}
        requests={inboxRequests}
        selectedId="r1"
        onSelectRequest={() => {}}
        onAnswer={() => {}}
      />,
    );
    const stops = expectKeyboardReachable(container, "InboxNeedsYouPanel");
    // Search input and both request cards are stops, in DOM order.
    expect(stops.some((stop) => stop.classList.contains("mm-cv-search"))).toBe(true);
    expect(container.querySelectorAll(".mm-cv-request-card")).toHaveLength(2);
    // Without a send path the composer textarea is disabled and correctly
    // excluded from tab stops (it renders, but never traps Tab).
    const textarea = container.querySelector("textarea");
    expect(textarea?.hasAttribute("disabled")).toBe(true);
    expect(stops).not.toContain(textarea);
  });

  it("ReplyThreadPanel: controls reachable; Escape closes through onClose", () => {
    const onClose = vi.fn();
    const { container } = render(
      <ReplyThreadPanel
        origin={{
          author: "Director C",
          text: "Where does the sweep land?",
          at: "2026-11-08T09:12:00Z",
          onViewOriginal: () => {},
        }}
        replies={[
          {
            id: "rep-1",
            author: "Engineering",
            text: "In the sleeve report.",
            at: "2026-11-08T09:15:00Z",
            taskLink: { label: "Open task", onOpen: () => {} },
          },
        ]}
        attachment={{ name: "sweep-summary.md", kind: "Markdown", onOpenPreview: () => {} }}
        onReply={() => {}}
        onMention={() => {}}
        onClose={onClose}
      />,
    );
    expectKeyboardReachable(container, "ReplyThreadPanel");
    fireEvent.keyDown(container.querySelector(".mm-cv-thread")!, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("SplitConversationsWorkspace: both panes keep independent reachable composers", () => {
    const { container } = render(
      <SplitConversationsWorkspace
        panes={[
          {
            id: "p1",
            header: { title: "Alpha room", subtitle: "Active now" },
            excerpt: [{ author: "Engineering", text: "First pane.", at: "2026-11-08T09:00:00Z" }],
          },
          {
            id: "p2",
            header: { title: "Beta room", subtitle: "Read-only" },
            excerpt: [],
          },
        ]}
        onCompose={() => {}}
      />,
    );
    const stops = expectKeyboardReachable(container, "SplitConversationsWorkspace");
    // Two panes → two enabled textareas; empty drafts keep both sends disabled.
    const textareas = container.querySelectorAll("textarea");
    expect(textareas).toHaveLength(2);
    expect(textareas[0]!.hasAttribute("disabled")).toBe(false);
    expect(textareas[1]!.hasAttribute("disabled")).toBe(false);
    expect(stops).toContain(textareas[0]);
    expect(stops).toContain(textareas[1]);
    expect(container.querySelectorAll("button.mm-cv-send[disabled]")).toHaveLength(2);
  });

  it("RoutinesPanel: controls reachable; Escape returns through onBack", () => {
    const onBack = vi.fn();
    const { container } = render(
      <RoutinesPanel
        roster={rosterRead.roster}
        routine={routineRecord}
        onPause={() => {}}
        onResume={() => {}}
        onBack={onBack}
      />,
    );
    expectKeyboardReachable(container, "RoutinesPanel");
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("CodeSettingsPanel: nav items reachable; document-level Escape closes through onClose", () => {
    const onClose = vi.fn();
    const { container } = render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
        onMoreProviders={() => {}}
        onClose={onClose}
      />,
    );
    const stops = expectKeyboardReachable(container, "CodeSettingsPanel");
    // The × close is wired here, so it is a stop; nav items are stops too.
    expect(stops.filter((stop) => stop.classList.contains("mm-cs-nav-item")).length).toBeGreaterThan(4);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("CodeWorkbench: rail toggle and tabs reachable; arrow keys move between tabs", () => {
    const { container } = render(<CodeWorkbench attemptId="runs/att-42" />);
    expectKeyboardReachable(container, "CodeWorkbench");
    const tabs = Array.from(container.querySelectorAll<HTMLElement>('[role="tab"]'));
    expect(tabs).toHaveLength(3);
    tabs[0]!.focus();
    fireEvent.keyDown(tabs[0]!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(tabs[1]);
    fireEvent.keyDown(tabs[1]!, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("ProjectRouteReview and ProjectRunOutcome: enabled controls reachable; unwired actions stay disabled with their reason", () => {
    const { container: routeContainer } = render(
      <ProjectRouteReview route={routeReview} onBack={() => {}} />,
    );
    expectKeyboardReachable(routeContainer, "ProjectRouteReview");
    // The preview-only submit is disabled (and therefore not a tab stop).
    const submit = screen.getByRole("button", { name: "Submit request" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(tabStops(routeContainer)).not.toContain(submit);

    cleanup();
    const { container: runContainer } = render(
      <ProjectRunOutcome
        run={null}
        breadcrumb={["Code", "Run"]}
        subject="Engineering"
        onOpenCode={() => {}}
      />,
    );
    expectKeyboardReachable(runContainer, "ProjectRunOutcome");
  });
});
