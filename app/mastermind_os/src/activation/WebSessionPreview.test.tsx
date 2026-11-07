// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  EvidenceRef,
  MissionDocument,
  MissionSelection,
  ReadState,
} from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";
import { WebSessionPreview } from "./WebSessionPreview";

// Exact fixture + exact selection: WS:ONE / JOB-1, resolved singleton, CURRENT.
const SELECTION: MissionSelection = { workRef: "WS:ONE", rootJobId: "JOB-1" };
const baseDocument = fixture as MissionDocument;

const cloneDocument = (): MissionDocument => structuredClone(baseDocument);

const withEvidence = (evidence: EvidenceRef[]): MissionDocument => {
  const next = cloneDocument();
  next.program.evidence = evidence;
  return next;
};

const withReadState = (state: ReadState): MissionDocument => {
  const next = cloneDocument();
  next.read_state.state = state;
  return next;
};

const withRoot = (
  over: Partial<
    Pick<
      MissionDocument["mission"],
      "root_job_ambiguous" | "root_job_candidates" | "runtime_root_state"
    >
  >,
): MissionDocument => {
  const next = cloneDocument();
  next.mission = { ...next.mission, ...over };
  return next;
};

const evidence = (overrides: Partial<EvidenceRef> = {}): EvidenceRef => ({
  owner: "EXECUTIVE_OS",
  ref: "directive:2026-09-18:new-web-session",
  field: "program.next_action",
  source_revision: "cr-4471",
  // The original source clocks stay distinct: source time vs observed at.
  source_time: "2026-09-18T16:05:00Z",
  observed_at: "2026-09-20T00:00:00Z",
  freshness_state: "CURRENT",
  ...overrides,
});

/** A foreign/private source that must never surface through a mismatched context. */
const privateEvidence = (): EvidenceRef[] => [
  evidence({
    owner: "SLACK",
    ref: "slack:private:web-creator-thread",
    field: "transport.dispatch_state",
    source_revision: null,
    source_time: null,
    freshness_state: "PARTIAL",
  }),
];

type User = ReturnType<typeof userEvent.setup>;

const fillRequiredDraft = async (user: User): Promise<void> => {
  await user.type(screen.getByLabelText("Role"), "Plan reviewer");
  await user.type(screen.getByLabelText("Objective"), "Review the selected work without launching");
  await user.type(screen.getByLabelText("When finished"), "Every attached source is verified");
  await user.type(screen.getByLabelText("Reason"), "This conversation cannot carry another turn");
};

const reviewButton = (): HTMLButtonElement =>
  screen.getByRole("button", { name: "Review launch" }) as HTMLButtonElement;

const launchButton = (): HTMLButtonElement =>
  screen.getByRole("button", { name: "Launch unavailable" }) as HTMLButtonElement;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("inert preview stage", () => {
  it("renders the header, actual scope and both fixed controls with no effects", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} />,
    );
    expect(screen.getByRole("heading", { name: "Review a new session" })).toBeTruthy();
    expect(screen.getByText("Preview — not launched")).toBeTruthy();
    expect(screen.getByText("A new conversation does not create a new mission.")).toBeTruthy();
    expect(screen.getAllByText("WS:ONE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("JOB-1").length).toBeGreaterThan(0);
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual([
      "Review launch",
      "Launch unavailable",
    ]);
    expect(reviewButton().disabled).toBe(false);
    expect(launchButton().disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it("keeps launch disabled with only the factual capability note", () => {
    render(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
    expect(launchButton().disabled).toBe(true);
    expect(
      screen.getByText("This workspace has no qualified Web session launch capability."),
    ).toBeTruthy();
  });

  it("requires the four stated reasons before any local review exists", async () => {
    const user = userEvent.setup();
    render(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
    await user.click(reviewButton());
    expect(screen.getByText("Role is required.")).toBeTruthy();
    expect(screen.getByText("Objective is required.")).toBeTruthy();
    expect(screen.getByText("When finished is required.")).toBeTruthy();
    expect(screen.getByText("Why a new session is required.")).toBeTruthy();
    expect(screen.queryByText("Draft preview")).toBeNull();
  });

  it("reviews a complete local draft with guardrails left optional", async () => {
    const user = userEvent.setup();
    render(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    const review = within(screen.getByRole("region", { name: "Draft preview" }));
    expect(review.getByText("Plan reviewer")).toBeTruthy();
    expect(review.getByText("Review the selected work without launching")).toBeTruthy();
    expect(review.getByText("Every attached source is verified")).toBeTruthy();
    expect(review.getByText("This conversation cannot carry another turn")).toBeTruthy();
    expect(review.getByText("None")).toBeTruthy();
    expect(review.getByText("2026-09-20T00:00:00Z")).toBeTruthy();
    expect(launchButton().disabled).toBe(true);
  });

  it("keeps the draft and review across an unchanged passive rerender", async () => {
    const user = userEvent.setup();
    const view = render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} />,
    );
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    view.rerender(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
    expect(screen.getByRole("region", { name: "Draft preview" })).toBeTruthy();
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("Plan reviewer");
  });
});

describe("snapshot invalidation", () => {
  it.each(["Role", "Objective", "Guardrails", "When finished", "Reason"])(
    "invalidates the reviewed snapshot when the %s draft changes",
    async (label) => {
      const user = userEvent.setup();
      render(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
      await fillRequiredDraft(user);
      await user.click(reviewButton());
      expect(screen.getByRole("region", { name: "Draft preview" })).toBeTruthy();
      await user.type(screen.getByLabelText(label), " edited");
      expect(screen.queryByText("Draft preview")).toBeNull();
    },
  );

  it("clears the private draft and review when the source generation advances", async () => {
    const user = userEvent.setup();
    const view = render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} />,
    );
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    expect(screen.getByRole("region", { name: "Draft preview" })).toBeTruthy();
    const next = cloneDocument();
    next.generated_at = "2026-09-21T00:00:00Z";
    view.rerender(<WebSessionPreview document={next} selection={SELECTION} />);
    expect(screen.queryByText("Draft preview")).toBeNull();
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Reason") as HTMLTextAreaElement).value).toBe("");
  });

  it("clears the private draft on a selection identity change with no cross-context leak", async () => {
    const user = userEvent.setup();
    const view = render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} />,
    );
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    expect(screen.getByRole("region", { name: "Draft preview" })).toBeTruthy();
    view.rerender(
      <WebSessionPreview
        document={cloneDocument()}
        selection={{ workRef: "WS:ONE", rootJobId: "JOB-2" }}
      />,
    );
    expect(screen.queryByLabelText("Role")).toBeNull();
    expect(screen.queryByRole("region", { name: "Draft preview" })).toBeNull();
    expect(screen.getByText("The selected source does not match the selected root job.")).toBeTruthy();
    view.rerender(<WebSessionPreview document={cloneDocument()} selection={SELECTION} />);
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("region", { name: "Draft preview" })).toBeNull();
  });

  it("removes the reviewed draft and its receipt when the document becomes unavailable", async () => {
    const user = userEvent.setup();
    const view = render(
      <WebSessionPreview document={withEvidence(privateEvidence())} selection={SELECTION} />,
    );
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    // Receipts render in the brief and in the reviewed snapshot while matched.
    expect(screen.getAllByText("slack:private:web-creator-thread").length).toBe(2);
    view.rerender(<WebSessionPreview document={null} selection={SELECTION} />);
    expect(screen.getByText("No selected mission document is available.")).toBeTruthy();
    expect(screen.queryByText("slack:private:web-creator-thread")).toBeNull();
    expect(screen.queryByLabelText("Role")).toBeNull();
    expect(screen.queryByRole("region", { name: "Draft preview" })).toBeNull();
    expect(reviewButton().disabled).toBe(true);
  });

  it("does not retain a reviewed snapshot when receipts change under one generation", async () => {
    const user = userEvent.setup();
    const view = render(
      <WebSessionPreview document={withEvidence([evidence()])} selection={SELECTION} />,
    );
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    expect(screen.getAllByText("directive:2026-09-18:new-web-session").length).toBe(2);
    view.rerender(
      <WebSessionPreview
        document={withEvidence([evidence({ source_revision: "cr-4472" })])}
        selection={SELECTION}
      />,
    );
    expect(screen.queryByRole("region", { name: "Draft preview" })).toBeNull();
    expect(screen.getByText("cr-4472")).toBeTruthy();
  });
});

describe("attached sources", () => {
  it("shows exact bounded receipts with explicit distinct clocks for the exact selection", () => {
    const { container } = render(
      <WebSessionPreview
        document={withEvidence([
          evidence(),
          evidence({
            owner: "AGENT_OS",
            ref: "agentos:WS:ONE:handoff-2026-09-19",
            field: "mission.root_job_id",
            source_revision: "ao-912",
            source_time: "2026-09-19T09:30:00Z",
          }),
        ])}
        selection={SELECTION}
      />,
    );
    expect(screen.getByText("Generated at")).toBeTruthy();
    // Generated at plus one observed-at receipt per attached source.
    expect(screen.getAllByText("2026-09-20T00:00:00Z").length).toBe(3);
    expect(screen.getByText("directive:2026-09-18:new-web-session")).toBeTruthy();
    expect(screen.getByText("agentos:WS:ONE:handoff-2026-09-19")).toBeTruthy();
    expect(screen.getByText("cr-4471")).toBeTruthy();
    expect(screen.getByText("ao-912")).toBeTruthy();
    expect(screen.getByText("2026-09-18T16:05:00Z")).toBeTruthy();
    expect(screen.getByText("2026-09-19T09:30:00Z")).toBeTruthy();
    // Read-state token once in task details, once per receipt freshness.
    expect(screen.getAllByText("CURRENT").length).toBe(3);
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it.each<[string, MissionSelection]>([
    ["work", { workRef: "WS:TWO", rootJobId: "JOB-1" }],
    ["root job", { workRef: "WS:ONE", rootJobId: "JOB-2" }],
  ])("hides the foreign source entirely on a %s mismatch", (_kind, selection) => {
    render(<WebSessionPreview document={withEvidence(privateEvidence())} selection={selection} />);
    expect(screen.queryByText("slack:private:web-creator-thread")).toBeNull();
    expect(screen.queryByText("SLACK")).toBeNull();
    expect(screen.queryByLabelText("Role")).toBeNull();
    expect(reviewButton().disabled).toBe(true);
    expect(launchButton().disabled).toBe(true);
  });

  it.each<[string, MissionDocument, string]>([
    [
      "ambiguous root",
      withRoot({ root_job_ambiguous: true, root_job_candidates: ["JOB-1", "JOB-2"] }),
      "The root job of the selected source is ambiguous.",
    ],
    [
      "unresolved root",
      withRoot({ runtime_root_state: "CONFLICT" }),
      "The root job of the selected source is not resolved.",
    ],
    [
      "unavailable source",
      withReadState("UNAVAILABLE"),
      "The selected source is unavailable.",
    ],
  ])("hides the private source on a %s", (_name, document, reason) => {
    const next = structuredClone(document);
    next.program.evidence = privateEvidence();
    render(<WebSessionPreview document={next} selection={SELECTION} />);
    expect(screen.getByText(reason)).toBeTruthy();
    expect(screen.queryByText("slack:private:web-creator-thread")).toBeNull();
    expect(reviewButton().disabled).toBe(true);
  });

  it("reports the missing source reason for a null document or null selection", () => {
    render(<WebSessionPreview document={null} selection={SELECTION} />);
    expect(screen.getByText("No selected mission document is available.")).toBeTruthy();
    cleanup();
    render(<WebSessionPreview document={cloneDocument()} selection={null} />);
    expect(screen.getByText("No mission selection is active.")).toBeTruthy();
  });

  it.each<[ReadState, string]>([
    ["PARTIAL", "Partial source — some source sections are unavailable."],
    ["HISTORICAL", "Historical source — not the current source generation."],
  ])("qualifies a %s source explicitly and still reviews locally", async (state, phrase) => {
    const user = userEvent.setup();
    render(<WebSessionPreview document={withReadState(state)} selection={SELECTION} />);
    expect(screen.getByText(phrase)).toBeTruthy();
    expect(screen.getByText(state)).toBeTruthy();
    await fillRequiredDraft(user);
    await user.click(reviewButton());
    expect(screen.getByRole("region", { name: "Draft preview" })).toBeTruthy();
  });
});

describe("bounded receipt list", () => {
  it("shows the first eight receipts, counts the rest, and shows all on demand", async () => {
    const user = userEvent.setup();
    const ten = Array.from({ length: 10 }, (_, index) =>
      evidence({
        ref: `directive:2026-09-${String(10 + index).padStart(2, "0")}:web-session`,
        source_revision: `cr-${4471 + index}`,
      }),
    );
    render(<WebSessionPreview document={withEvidence(ten)} selection={SELECTION} />);
    expect(screen.getAllByText(/^directive:2026-09-/)).toHaveLength(8);
    expect(screen.getByText("Showing 8 of 10 attached sources.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Show all" }));
    expect(screen.getAllByText(/^directive:2026-09-/)).toHaveLength(10);
    expect(screen.queryByText("Showing 8 of 10 attached sources.")).toBeNull();
  });

  it("renders duplicate receipts without a synthetic identity", () => {
    const { container } = render(
      <WebSessionPreview
        document={withEvidence([evidence(), evidence()])}
        selection={SELECTION}
      />,
    );
    expect(screen.getAllByText("directive:2026-09-18:new-web-session")).toHaveLength(2);
    expect(container.querySelectorAll(".wsp-source")).toHaveLength(2);
  });
});

describe("localisation", () => {
  it("presents the zh controls, fixed capability sentence and disabled launch", () => {
    render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} locale="zh-CN" />,
    );
    expect(screen.getByRole("heading", { name: "审核新会话" })).toBeTruthy();
    expect(screen.getByText("预览 — 未启动")).toBeTruthy();
    expect(screen.getByText("新对话不会创建新任务。")).toBeTruthy();
    expect(screen.getByText("会话简报")).toBeTruthy();
    expect(screen.getByLabelText("角色")).toBeTruthy();
    expect(screen.getByLabelText("目标")).toBeTruthy();
    expect(screen.getByText("附带来源")).toBeTruthy();
    expect(screen.getByLabelText("护栏")).toBeTruthy();
    expect(screen.getByLabelText("完成条件")).toBeTruthy();
    expect(screen.getByText("为何需要新会话")).toBeTruthy();
    expect(screen.getByLabelText("理由")).toBeTruthy();
    expect(screen.getByText("此工作区没有已认证的 Web 会话启动能力。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "审核启动" })).toBeTruthy();
    const launch = screen.getByRole("button", { name: "启动不可用" }) as HTMLButtonElement;
    expect(launch.disabled).toBe(true);
  });

  it("reviews a zh draft and reports required reasons in zh", async () => {
    const user = userEvent.setup();
    render(
      <WebSessionPreview document={cloneDocument()} selection={SELECTION} locale="zh-CN" />,
    );
    await user.click(screen.getByRole("button", { name: "审核启动" }));
    expect(screen.getByText("角色必填。")).toBeTruthy();
    expect(screen.getByText("目标必填。")).toBeTruthy();
    expect(screen.getByText("完成条件必填。")).toBeTruthy();
    expect(screen.getByText("为何需要新会话必填。")).toBeTruthy();
    expect(screen.queryByText("草稿预览")).toBeNull();
    await user.type(screen.getByLabelText("角色"), "评审");
    await user.type(screen.getByLabelText("目标"), "审阅当前工作");
    await user.type(screen.getByLabelText("完成条件"), "全部来源已核对");
    await user.type(screen.getByLabelText("理由"), "当前会话无法继续承接");
    await user.click(screen.getByRole("button", { name: "审核启动" }));
    expect(screen.getByText("草稿预览")).toBeTruthy();
    expect(screen.getByText("评审")).toBeTruthy();
    expect(screen.getByText("未填写")).toBeTruthy();
  });

  it("reports the missing source reason in zh", () => {
    render(<WebSessionPreview document={null} selection={SELECTION} locale="zh-CN" />);
    expect(screen.getByText("没有可用的已选任务文档。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "审核启动" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
