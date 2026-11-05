// @vitest-environment jsdom
// Synthetic unit fixtures only: every id, digest, envelope and state below is a
// labelled "unit" construction for this suite. None is a captured production
// payload, a real SessionBridge read or a Runtime proof — the parent owns both.
import type {ReactNode} from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NewConversationOutcome, FreshConversationInitialResponse } from "./NewConversationOutcome";
import type { FreshConversationData } from "./fresh-conversation";
import type { OperationState } from "../../orchestration/operation-controller";

afterEach(cleanup);

const unitData = (overrides: Partial<FreshConversationData> = {}): FreshConversationData => ({
  schema: "mastermind.executive.fresh_conversation_data.v1",
  work_ref: "conv-unit-0000000000000001",
  operation_key: "opk-unit-0000000000000001",
  state: "ADMITTED",
  effect: "NONE",
  parent_consumed: false,
  can_send: false,
  preview: null,
  locator: null,
  session: null,
  result: null,
  ...overrides,
});

const unitLocator = {
  work_ref: "conv-unit-0000000000000001",
  root_job_id: "job-unit-root-000000001",
  job_id: "job-unit-leaf-0000000001",
  attempt_id: "attempt-unit-0000000001",
};
const unitSession = {
  attempt_id: "attempt-unit-0000000001",
  generation: "generation-unit-00000001",
  binding_digest: "bind-unit-digest-0000000000001",
};
const unitResult = {
  digest: "sha256-unit-result-00000000000001",
  envelope: {
    summary: "Unit reply line one\n\nUnit reply line three",
    role: "assistant",
    proposed_actions: [{ kind: "unit-noise" }],
  },
};

const unitPointer = {
  operationKey: "opk-unit-0000000000000001",
  kind: "conversation_create" as const,
  targetKey: null,
};

const unitController = (
  status: "idle" | "submitting" | "checking" | "accepted" | "refused" | "unknown",
): OperationState => {
  switch (status) {
    case "submitting": return { status, pointer: unitPointer, reason: "SUBMITTING" };
    case "checking": return { status, pointer: unitPointer, reason: "CHECKING" };
    case "accepted": return { status, pointer: null, reason: "ACCEPTED" };
    case "refused": return { status, pointer: null, reason: "REFUSED" };
    case "unknown": return { status, pointer: unitPointer, reason: "UNKNOWN_RECEIPT" };
    case "idle": return { status, pointer: null, reason: "IDLE" };
  }
};

const entry = (locale: "en" | "zh-CN", overrides: {
  data?: FreshConversationData | null;
  operationState?: OperationState | null;
  originalMessage?: string | null;
  projectTitle?: string | null;
  opened?: boolean;
  busy?: boolean;
  canOpen?: boolean;
  onCheck?: () => void;
  onOpen?: () => void;
  onBack?: () => void;
  continuation?:ReactNode;
} = {}) =>
  <NewConversationOutcome locale={locale} data={overrides.data ?? null}
    operationState={overrides.operationState ?? null}
    originalMessage={overrides.originalMessage ?? null}
    projectTitle={overrides.projectTitle ?? null} opened={overrides.opened ?? false}
    busy={overrides.busy ?? false} canOpen={overrides.canOpen ?? true}
    onCheck={overrides.onCheck ?? vi.fn()} onOpen={overrides.onOpen ?? vi.fn()}
    onBack={overrides.onBack ?? vi.fn()} continuation={overrides.continuation} />;

const buttonNames = () => screen.getAllByRole("button").map(button => button.textContent ?? "");

const fieldPre = (container: HTMLElement, fieldLabel: string) => {
  const field = Array.from(container.querySelectorAll(".mm-new-conversation-outcome-field"))
    .find(node => node.textContent?.includes(fieldLabel));
  return field?.querySelector(".mm-new-conversation-outcome-pre") ?? null;
};

const noOfferedActions = () => {
  for (const name of buttonNames()) {
    expect(name).not.toMatch(/Create|Retry|Resend|Cancel|Send/);
  }
};

afterEach(() => { vi.restoreAllMocks(); });

describe("NewConversationOutcome", () => {
  it("renders the quiet unclaimed fallback with closed raw sources and only parent callbacks", () => {
    const onBack = vi.fn();
    const view = render(entry("en", { onBack }));
    expect(screen.getByRole("heading", { name: "New conversation" })).toBeTruthy();
    expect(screen.getByText("Conversation status is unavailable here.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
    expect(screen.getByRole("button", { name: "Check original request" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back to conversations" })).toBeTruthy();
    expect(screen.queryByText("Going back does not cancel the original request.")).toBeNull();
    noOfferedActions();
    const details = view.container.querySelector("details");
    expect(details?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Sources and access")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("never calls owners on mount, on a locale rerender or on the parent read gesture", () => {
    const onCheck = vi.fn();
    const onOpen = vi.fn();
    const onBack = vi.fn();
    const view = render(entry("en", { onCheck, onOpen, onBack }));
    view.rerender(entry("zh-CN", { onCheck, onOpen, onBack }));
    view.rerender(entry("zh-CN", { onCheck, onOpen, onBack, opened: true }));
    view.rerender(entry("en", { onCheck, onOpen, onBack, opened: true }));
    expect(onCheck).not.toHaveBeenCalled();
    expect(onOpen).not.toHaveBeenCalled();
    expect(onBack).not.toHaveBeenCalled();
  });

  it("keeps the unconfirmed warning above stale CREATED data and offers no create or resend", () => {
    const onCheck = vi.fn();
    const onOpen = vi.fn();
    const onBack = vi.fn();
    render(entry("en", {
      data: unitData({ state: "CREATED", effect: "COMMITTED", locator: unitLocator, session: unitSession }),
      operationState: unitController("unknown"),
      canOpen: true, onCheck, onOpen, onBack,
    }));
    expect(screen.getByText("The outcome is not confirmed. Check the original request; do not create it again."))
      .toBeTruthy();
    expect(screen.queryByText("Conversation created")).toBeNull();
    // The warning outranks the stale created claim for status copy, while the
    // read control still follows only the parent gate plus strict server data.
    expect(screen.getByRole("button", { name: "Open initial response" })).toBeTruthy();
    expect(screen.getByText("Going back does not cancel the original request.")).toBeTruthy();
    noOfferedActions();
    fireEvent.click(screen.getByRole("button", { name: "Check original request" }));
    expect(onCheck).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
    expect(onBack).not.toHaveBeenCalled();
  });

  it.each([
    { status: "submitting" as const, en: "Creating conversation…", zh: "正在创建对话…" },
    { status: "checking" as const, en: "Checking original request…", zh: "正在查看原请求…" },
  ])("shows the plain $status sentence in both locales with the back annotation", ({ status, en, zh }) => {
    const view = render(entry("en", { operationState: unitController(status) }));
    expect(screen.getByText(en)).toBeTruthy();
    expect(screen.getByText("Going back does not cancel the original request.")).toBeTruthy();
    view.rerender(entry("zh-CN", { operationState: unitController(status) }));
    expect(screen.getByText(zh)).toBeTruthy();
    expect(screen.queryByText(en)).toBeNull();
    expect(screen.getByText("返回不会取消原请求。")).toBeTruthy();
  });

  it.each([
    {
      state: "ADMITTED" as const,
      en: "Conversation request accepted. The conversation is not confirmed yet.",
      zh: "对话请求已接收，尚未确认对话已创建。",
    },
    {
      state: "ABSENT" as const,
      en: "No outcome can be confirmed for this original request yet.",
      zh: "尚未确认此原请求的结果。",
    },
  ])("reports $state data without a created claim or an open control", ({ state, en, zh }) => {
    const view = render(entry("en", { data: unitData({ state }) }));
    expect(screen.getByText(en)).toBeTruthy();
    expect(screen.queryByText("Conversation created")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
    expect(screen.getByText("Going back does not cancel the original request.")).toBeTruthy();
    view.rerender(entry("zh-CN", { data: unitData({ state }) }));
    expect(screen.getByText(zh)).toBeTruthy();
    expect(screen.queryByText("对话已创建")).toBeNull();
  });

  it("claims created only for a real session binding plus locator and exposes the open control", () => {
    const onOpen = vi.fn();
    const view = render(entry("en", {
      data: unitData({ state: "CREATED", effect: "COMMITTED", locator: unitLocator, session: unitSession }),
      canOpen: true, onOpen,
    }));
    expect(screen.getByText("Conversation created")).toBeTruthy();
    expect(screen.queryByText("Going back does not cancel the original request.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open initial response" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
    const partial = [
      unitData({ state: "CREATED", locator: unitLocator, session: null }),
      unitData({ state: "CREATED", locator: null, session: unitSession }),
    ];
    for (const data of partial) {
      view.rerender(entry("en", { data, canOpen: true, onOpen }));
      expect(screen.queryByText("Conversation created")).toBeNull();
      expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
      expect(screen.getByText("Conversation status is unavailable here.")).toBeTruthy();
    }
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("reports settled as the completed original request and never as created", () => {
    const onOpen = vi.fn();
    const view = render(entry("en", {
      data: unitData({ state: "SETTLED", effect: "COMMITTED" }), canOpen: true, onOpen,
    }));
    expect(screen.getByText("Original request completed")).toBeTruthy();
    expect(screen.queryByText("Conversation created")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
    view.rerender(entry("en", {
      data: unitData({ state: "SETTLED", effect: "COMMITTED", locator: unitLocator }),
      canOpen: true, onOpen,
    }));
    fireEvent.click(screen.getByRole("button", { name: "Open initial response" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("withholds the open control when the parent has not granted canOpen", () => {
    render(entry("en", {
      data: unitData({ state: "CREATED", locator: unitLocator, session: unitSession }), canOpen: false,
    }));
    expect(screen.getByText("Conversation created")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
  });

  it("disables check and open while busy and keeps back free of a cancel label", () => {
    const onCheck = vi.fn();
    const onOpen = vi.fn();
    render(entry("en", {
      data: unitData({ state: "CREATED", locator: unitLocator, session: unitSession }),
      busy: true, canOpen: true, onCheck, onOpen,
    }));
    const check = screen.getByRole("button", { name: "Check original request" }) as HTMLButtonElement;
    const open = screen.getByRole("button", { name: "Open initial response" }) as HTMLButtonElement;
    expect(check.disabled).toBe(true);
    expect(open.disabled).toBe(true);
    fireEvent.click(check);
    fireEvent.click(open);
    expect(onCheck).not.toHaveBeenCalled();
    expect(onOpen).not.toHaveBeenCalled();
    noOfferedActions();
  });

  it("reports a refused request with the draft retained and no cancel or retry control", () => {
    render(entry("en", { operationState: unitController("refused") }));
    expect(screen.getByText("The request was refused. Your message remains a draft.")).toBeTruthy();
    expect(screen.queryByText("Going back does not cancel the original request.")).toBeNull();
    noOfferedActions();
  });

  it("shows the opened initial response verbatim with the exact first message and no send affordance", () => {
    const onCheck = vi.fn();
    const onBack = vi.fn();
    const view = render(entry("en", {
      data: unitData({
        state: "CREATED", effect: "COMMITTED", locator: unitLocator, session: unitSession, result: unitResult,
      }),
      originalMessage: "Unit first line\n\nUnit third line\twith a tab",
      projectTitle: "Alpha project",
      opened: true, canOpen: true, onCheck, onBack,
    }));
    expect(screen.getByRole("heading", { name: "Conversation" })).toBeTruthy();
    expect(screen.getByText("Alpha project")).toBeTruthy();
    expect(screen.getByText("Only the initial response is shown here.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Initial response" })).toBeTruthy();
    expect(fieldPre(view.container, "Your first message")?.textContent)
      .toBe("Unit first line\n\nUnit third line\twith a tab");
    expect(fieldPre(view.container, "Initial response")?.textContent)
      .toBe("Unit reply line one\n\nUnit reply line three");
    expect(view.container.textContent).not.toContain("assistant");
    expect(view.container.textContent).not.toContain("unit-noise");
    expect(screen.getByText("Reading this result does not acknowledge it.")).toBeTruthy();
    expect(screen.getByText("Further messages are not available in this view yet.")).toBeTruthy();
    noOfferedActions();
    fireEvent.click(screen.getByRole("button", { name: "Check original request" }));
    expect(onCheck).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Open initial response" })).toBeNull();
  });

  it.each([
    { result: null, parentConsumed: false, caption: false },
    { result: unitResult, parentConsumed: true, caption: false },
    { result: unitResult, parentConsumed: false, caption: true },
  ])("gates the acknowledgement caption on a present unread result (caption: $caption)", ({ result, parentConsumed, caption }) => {
    const view = render(entry("en", {
      data: unitData({
        state: "SETTLED", effect: "COMMITTED", locator: unitLocator, result,
        parent_consumed: parentConsumed as false, // Deliberately malformed presentation input; real wire rejects true.
      }),
      opened: true,
    }));
    const response = fieldPre(view.container, "Initial response");
    if (result == null) {
      expect(screen.getByText("The initial response is not available yet.")).toBeTruthy();
      expect(response).toBeNull();
    } else {
      expect(response?.textContent).toBe("Unit reply line one\n\nUnit reply line three");
    }
    const seen = screen.queryByText("Reading this result does not acknowledge it.");
    expect(seen != null).toBe(caption);
  });

  it("keeps raw technical codes inside one closed sources disclosure", () => {
    const view = render(entry("en", {
      data: unitData({
        state: "CREATED", effect: "COMMITTED", locator: unitLocator, session: unitSession, result: unitResult,
      }),
      operationState: unitController("accepted"),
    }));
    const details = view.container.querySelector("details");
    expect(details).toBeTruthy();
    expect(details?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Sources and access")).toBeTruthy();
    const hidden = details?.textContent ?? "";
    for (const code of [
      "mastermind.executive.fresh_conversation_data.v1",
      "CREATED",
      "opk-unit-0000000000000001",
      "conv-unit-0000000000000001",
      "job-unit-root-000000001",
      "attempt-unit-0000000001",
      "generation-unit-00000001",
      "bind-unit-digest-0000000000001",
      "sha256-unit-result-00000000000001",
      "ACCEPTED",
      "Parent consumed",
      "can_send",
    ]) expect(hidden).toContain(code);
    const outside = (view.container.textContent ?? "").replace(hidden, "");
    for (const code of [
      "opk-unit", "conv-unit", "job-unit", "attempt-unit", "generation-unit",
      "bind-unit", "sha256-unit", "mastermind.executive",
    ]) expect(outside).not.toContain(code);
  });

  it("renders the complete plain Chinese copy for both views", () => {
    const view = render(entry("zh-CN", { data: unitData({ state: "RECONCILIATION_REQUIRED" }) }));
    expect(view.container.firstElementChild?.getAttribute("lang")).toBe("zh-CN");
    expect(screen.getByRole("heading", { name: "新建对话" })).toBeTruthy();
    expect(screen.getByText("结果尚未确认。请查看原请求状态，不要再次创建。")).toBeTruthy();
    expect(screen.getByText("返回不会取消原请求。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看原请求状态" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回对话" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "查看首条回复" })).toBeNull();
    view.rerender(entry("zh-CN", {
      data: unitData({
        state: "CREATED", effect: "COMMITTED", locator: unitLocator, session: unitSession, result: unitResult,
      }),
      originalMessage: "单元首行\n\n单元第三行",
      projectTitle: "示例项目",
      opened: true,
    }));
    expect(screen.getByRole("heading", { name: "对话" })).toBeTruthy();
    expect(screen.getByText("示例项目")).toBeTruthy();
    expect(screen.getByText("此处仅显示首条回复。")).toBeTruthy();
    expect(screen.getByText("你的首条消息")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "首条回复" })).toBeTruthy();
    expect(fieldPre(view.container, "你的首条消息")?.textContent).toBe("单元首行\n\n单元第三行");
    expect(fieldPre(view.container, "首条回复")?.textContent).toBe("Unit reply line one\n\nUnit reply line three");
    expect(screen.getByText("查看此结果并不表示已确认接收。")).toBeTruthy();
    expect(screen.getByText("此视图暂不支持继续发送消息。")).toBeTruthy();
    expect(screen.getByText("来源与访问")).toBeTruthy();
    noOfferedActions();
  });
});

it("keeps unresolved original status visible while the readonly response is open",()=>{
 render(entry("en",{data:unitData({state:"CREATED",locator:unitLocator,session:unitSession,result:unitResult}),operationState:unitController("unknown"),opened:true}));
 expect(screen.getByRole("status").textContent).toContain("do not create it again");
 expect(screen.getByText(unitResult.envelope.summary,{normalizer:value=>value})).toBeTruthy();
});
it("renders the reusable original result body without fabricating an old operation-key DTO",()=>{
 render(<FreshConversationInitialResponse locale="zh-CN" result={unitResult} originalMessage={"  原消息\nline  "} caption="实际调用方提供的说明"/>);
 expect(screen.getByText("首条回复")).toBeTruthy();expect(screen.getByText(unitResult.envelope.summary,{normalizer:value=>value})).toBeTruthy();
 expect(screen.getByText("实际调用方提供的说明")).toBeTruthy();expect(screen.queryByText("Operation key")).toBeNull();
});

it.each(["en","zh-CN"] as const)("labels a genuine caller-selected follow-up body separately in %s",locale=>{
 render(<FreshConversationInitialResponse locale={locale} result={unitResult} originalMessage={null} responseKind="followup" headingLevel={3}/>);
 expect(screen.getByRole("heading",{name:locale==="en"?"Follow-up response":"后续回复",level:3})).toBeTruthy();
 expect(screen.queryByRole("heading",{name:locale==="en"?"Initial response":"首条回复"})).toBeNull();
 expect(screen.getByText(unitResult.envelope.summary,{normalizer:value=>value}).textContent).toBe(unitResult.envelope.summary);
 expect(screen.queryByText(locale==="en"?"Your first message":"你的首条消息")).toBeNull();
});

it.each([['en','Check the original request to view its status.'],['zh-CN','请查看原请求以了解其状态。']] as const)("does not call an unread selected original unavailable (%s)",(locale,copy)=>{
  const {rerender}=render(<NewConversationOutcome locale={locale} data={null} operationState={null} originalMessage={null} projectTitle={null} opened={false} busy={false} canOpen={false} awaitingCheck onCheck={()=>{}} onOpen={()=>{}} onBack={()=>{}}/>);
  expect(screen.getByText(copy)).toBeTruthy();
  expect(screen.queryByText(/Conversation status is unavailable here|此处暂时无法查看对话状态/)).toBeNull();
  rerender(<NewConversationOutcome locale={locale} data={null} operationState={null} originalMessage={null} projectTitle={null} opened={false} busy={false} canOpen={false} awaitingCheck={false} onCheck={()=>{}} onOpen={()=>{}} onBack={()=>{}}/>);
  expect(screen.getByText(locale==='en'?'Conversation status is unavailable here.':'此处暂时无法查看对话状态。')).toBeTruthy();
});

it.each(["en","zh-CN"] as const)("opened %s scope follows actual supplied continuation without claiming a reply already exists",locale=>{
 render(entry(locale,{opened:true,continuation:<p>Actual caller continuation slot</p>}));
 expect(screen.queryByText(locale==="en"?"Only the initial response is shown here.":"此处仅显示首条回复。")).toBeNull();
 expect(screen.getByText(locale==="en"?"The first response and any recorded follow-up are shown here.":"此处显示首条回复及已记录的后续回复。")).toBeTruthy();
 expect(screen.queryByText(locale==="en"?"Further messages are not available in this view yet.":"此视图暂不支持继续发送消息。")).toBeNull();
 expect(screen.getByText("Actual caller continuation slot")).toBeTruthy();
 expect(screen.getByRole("button",{name:locale==="en"?"Check initial request":"查看首次请求状态"})).toBeTruthy();
});
