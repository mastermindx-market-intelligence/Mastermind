// @vitest-environment jsdom
// Synthetic unit fixtures only: every id, digest and envelope below is a
// labelled "unit" construction for this suite. None is a captured production
// payload, a real SessionBridge read or a Runtime proof — the parent owns both.
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FreshConversationTurnPanel } from "./FreshConversationTurnPanel";
import type { FreshConversationTurnData } from "./fresh-conversation-turn";
import type { OperationState } from "../../orchestration/operation-controller";

afterEach(cleanup);

const unitReference = {
  schema: "mastermind.fresh_conversation_reference.v1" as const,
  work_ref: "conv-unit-0000000000000002",
  root_job_id: "job-unit-root-0000000002",
  root_event_id: 42,
  root_event_sha256: "sha256-unit-root-event-00000000001",
  principal_scope_sha256: "sha256-unit-scope-0000000000001",
};
const unitReceipt = {
  state: "CONSUMED" as const,
  event_id: 43,
  event_sha256: "sha256-unit-receipt-000000000001",
  initial_digest: "sha256-unit-initial-00000000001",
};
const unitResult = {
  digest: "sha256-unit-followup-00000000001",
  envelope: { summary: "Unit follow-up reply line", role: "assistant" },
};
const unitLocator = {
  work_ref: "conv-unit-0000000000000002",
  root_job_id: "job-unit-root-0000000002",
  job_id: "job-unit-leaf-00000000002",
  attempt_id: "attempt-unit-000000000002",
};

const unitData = (overrides: Partial<FreshConversationTurnData> = {}): FreshConversationTurnData => ({
  schema: "mastermind.executive.fresh_conversation_turn_data.v1",
  work_ref: "conv-unit-0000000000000002",
  operation_key: null,
  reference: unitReference,
  turn_key: null,
  state: "CONSUMED",
  effect: "COMMITTED",
  initial_consumption: unitReceipt,
  locator: unitLocator,
  result: null,
  parent_consumed: false,
  can_send: true,
  ...overrides,
});

const unitPointer = {
  operationKey: "opk-unit-0000000000000002",
  kind: "message" as const,
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

interface EntryOverrides {
  data?: FreshConversationTurnData | null;
  operationState?: OperationState | null;
  activity?: "keeping" | "sending" | "checking" | null;
  message?: string;
  readOnly?: boolean;
  keepControl?: ReactNode | null;
  sendControl?: ReactNode | null;
  checkControl?: ReactNode | null;
  feedback?: ReactNode;
  onMessageChange?: (value: string) => void;
}

const entry = (locale: "en" | "zh-CN", overrides: EntryOverrides = {}) => {
  const onMessageChange = overrides.onMessageChange ?? vi.fn();
  const onKeep = vi.fn();
  const onSend = vi.fn();
  const onCheck = vi.fn();
  const ui = <FreshConversationTurnPanel locale={locale} data={overrides.data ?? null}
    operationState={overrides.operationState ?? null} activity={overrides.activity ?? null}
    message={overrides.message ?? ""} onMessageChange={onMessageChange}
    readOnly={overrides.readOnly ?? false}
    keepControl={"keepControl" in overrides ? overrides.keepControl
      : <button type="button" onClick={onKeep}>Unit keep</button>}
    sendControl={"sendControl" in overrides ? overrides.sendControl
      : <button type="button" onClick={onSend}>Unit send</button>}
    checkControl={"checkControl" in overrides ? overrides.checkControl
      : <button type="button" onClick={onCheck}>Unit check</button>}
    feedback={overrides.feedback ?? null} />;
  return { ui, onMessageChange, onKeep, onSend, onCheck };
};

const input = () => screen.getByLabelText("Your next message") as HTMLTextAreaElement;

describe("FreshConversationTurnPanel", () => {
  it("unkept window asks for the first-response receipt and never offers a send", () => {
    const handle = entry("en", { data: unitData({ initial_consumption: null, can_send: true }) });
    render(handle.ui);
    expect(screen.getByRole("heading", { name: "Continue this conversation" })).toBeTruthy();
    expect(screen.getByText("Keep the first response to continue.")).toBeTruthy();
    expect(screen.queryByLabelText("Your next message")).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.getByRole("button", { name: "Unit keep" })).toBeTruthy();
    expect(screen.queryByText("Continuing is unavailable here right now. Your message remains a draft.")).toBeNull();
  });

  it("kept window renders the controlled draft, forwards exact text and fires no action", () => {
    const draft = "  Follow-up draft 新消息\n";
    const handle = entry("en", { data: unitData(), message: draft });
    render(handle.ui);
    expect(screen.getByText("First response kept")).toBeTruthy();
    const area = input();
    expect(area.value).toBe(draft);
    expect(area.hasAttribute("maxLength")).toBe(false);
    expect(area.disabled).toBe(false);
    expect(screen.getByRole("button", { name: "Unit send" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Unit keep" })).toBeNull();
    fireEvent.change(area, { target: { value: "替换后的后续消息  \n\t" } });
    expect(handle.onMessageChange).toHaveBeenCalledTimes(1);
    expect(handle.onMessageChange).toHaveBeenCalledWith("替换后的后续消息  \n\t");
    expect(handle.onKeep).not.toHaveBeenCalled();
    expect(handle.onSend).not.toHaveBeenCalled();
    expect(handle.onCheck).not.toHaveBeenCalled();
  });

  it("can_send alone neither synthesizes nor revokes the owner send slot", () => {
    const barred = entry("en", { data: unitData({ can_send: false }) });
    render(barred.ui);
    expect(screen.getByRole("button", { name: "Unit send" })).toBeTruthy();
    cleanup();
    const unkept = entry("en", { data: unitData({ initial_consumption: null, can_send: true }) });
    render(unkept.ui);
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    cleanup();
    const ownerless = entry("en", { data: unitData(), sendControl: null });
    render(ownerless.ui);
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.getByText("Continuing is unavailable here right now. Your message remains a draft.")).toBeTruthy();
  });

  it("recorded window shows the follow-up body once, without a second input or action", () => {
    const handle = entry("en", {
      data: unitData({ state: "RECORDED", result: unitResult, turn_key: "unit-turn-0001", can_send: false }),
      message: "Sent follow-up text", feedback: <p>Unit feedback line</p>,
    });
    render(handle.ui);
    expect(screen.getByText("Follow-up response recorded")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Follow-up response" })).toBeTruthy();
    expect(screen.getByText("Unit follow-up reply line")).toBeTruthy();
    expect(screen.getByText("Reading this result does not acknowledge it.")).toBeTruthy();
    expect(screen.getByText("First response kept")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("heading",{name:"Initial response"})).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit keep" })).toBeNull();
    expect(screen.getByRole("button", { name: "Unit check" })).toBeTruthy();
    expect(screen.getByText("Unit feedback line")).toBeTruthy();
    expect(screen.queryByText("Follow-up response accepted")).toBeNull();
    expect(screen.queryByText("Follow-up response applied")).toBeNull();
    expect(screen.queryByText("Continuing is unavailable here right now. Your message remains a draft.")).toBeNull();
  });

  it("unknown controller dominates a recorded success heading and the receipt", () => {
    const handle = entry("en", {
      data: unitData({ state: "RECORDED", result: unitResult }),
      operationState: unitController("unknown"),
    });
    render(handle.ui);
    expect(screen.getByText("The original request needs a status check. Don’t send it again.")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
    expect(screen.getByText("First response kept")).toBeTruthy();
    expect(input().disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit keep" })).toBeNull();
  });

  it("reconciliation-required data and unknown effect dominate success headings too", () => {
    const handle = entry("en", { data: unitData({ state: "RECONCILIATION_REQUIRED", effect: "UNKNOWN" }) });
    const { rerender } = render(handle.ui);
    expect(screen.getByText("The original request needs a status check. Don’t send it again.")).toBeTruthy();
    rerender(entry("en", { data: unitData({ state: "RECORDED", effect: "UNKNOWN", result: unitResult }) }).ui);
    expect(screen.getByText("The original request needs a status check. Don’t send it again.")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
  });

  it("absent after an attempt is a hold, not clearance to replay", () => {
    const handle = entry("en", { data: unitData({ state: "ABSENT", can_send: false }) });
    render(handle.ui);
    expect(screen.getByText("No follow-up is recorded for this original request yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit keep" })).toBeNull();
    expect(screen.getByText("Continuing is unavailable here right now. Your message remains a draft.")).toBeTruthy();
    expect(input().disabled).toBe(false);
  });

  it("pending activity labels hold the input and hide both action slots", () => {
    const handle = entry("en", { data: unitData(), activity: "keeping" });
    const { rerender } = render(handle.ui);
    expect(screen.getByText("Keeping response…")).toBeTruthy();
    expect(input().disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit keep" })).toBeNull();
    rerender(entry("en", { data: unitData(), activity: "sending" }).ui);
    expect(screen.getByText("Sending message…")).toBeTruthy();
    rerender(entry("en", { data: unitData(), activity: "checking" }).ui);
    expect(screen.getByText("Checking original request…")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
    expect(screen.queryByText("已记录后续回复")).toBeNull();
  });

  it("a busy controller never states a completed or cancelled follow-up", () => {
    const handle = entry("en", {
      data: unitData({ state: "RECORDED", result: unitResult }),
      operationState: unitController("submitting"),
    });
    const { rerender } = render(handle.ui);
    expect(screen.getByText("Sending message…")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
    rerender(entry("en", { data: unitData({ state: "RECORDED" }), operationState: unitController("checking") }).ui);
    expect(screen.getByText("Checking original request…")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
  });

  it("controller refusal stays non-green and preserves the draft message", () => {
    const draft = "Still a unit draft";
    const handle = entry("en", {
      data: unitData({ effect: "NONE" }),
      operationState: unitController("refused"), message: draft,
    });
    render(handle.ui);
    expect(screen.getByText("The request was refused. Your message remains a draft.")).toBeTruthy();
    expect(screen.queryByText("Follow-up response recorded")).toBeNull();
    expect(input().value).toBe(draft);
  });

  it("readOnly holds the draft input without inventing an operation state", () => {
    const handle = entry("en", { data: unitData(), readOnly: true });
    const { rerender } = render(handle.ui);
    expect(input().disabled).toBe(true);
    rerender(entry("en", { data: unitData() }).ui);
    expect(input().disabled).toBe(false);
  });

  it("renders the zh continuation copy with reset tracking under the zh lang root", () => {
    const handle = entry("zh-CN", {
      data: unitData({ state: "RECORDED", result: unitResult, turn_key: "unit-turn-0001" }),
    });
    const view = render(handle.ui);
    expect(view.container.firstElementChild?.getAttribute("lang")).toBe("zh-CN");
    expect(screen.getByRole("heading", { name: "继续此对话" })).toBeTruthy();
    expect(screen.getByText("已保留第一条回复")).toBeTruthy();
    expect(screen.getByText("已记录后续回复")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "后续回复" })).toBeTruthy();
    expect(screen.queryByLabelText("下一条消息")).toBeNull();
    view.rerender(entry("zh-CN",{data:unitData()}).ui);
    expect(screen.getByLabelText("下一条消息")).toBeTruthy();
    expect(screen.getByText("消息将保留在此对话中。")).toBeTruthy();
  });

  it("null window invents no receipt, no state and no raw source values", () => {
    const handle = entry("en", { data: null });
    const view = render(handle.ui);
    expect(screen.getByText("Keep the first response to continue.")).toBeTruthy();
    expect(screen.queryByLabelText("Your next message")).toBeNull();
    expect(screen.queryByRole("button", { name: "Unit send" })).toBeNull();
    expect(screen.getByRole("button", { name: "Unit keep" })).toBeTruthy();
    const details = view.container.querySelector("details");
    expect(details?.hasAttribute("open")).toBe(false);
  });

  it("raw ids, hashes and effect stay inside one closed native disclosure", () => {
    const handle = entry("en", { data: unitData({ state: "RECORDED", result: unitResult, turn_key: "unit-turn-0001" }) });
    const view = render(handle.ui);
    const details = view.container.querySelectorAll("details");
    expect(details.length).toBe(1);
    expect(details[0]?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Sources and request")).toBeTruthy();
    expect(screen.getByText(unitResult.digest).closest("details")).not.toBeNull();
    expect(screen.getByText(`event ${unitReceipt.event_id} · ${unitReceipt.event_sha256}`)
      .closest("details")).not.toBeNull();
    expect(screen.getByText(unitReference.principal_scope_sha256).closest("details")).not.toBeNull();
    expect(screen.getAllByText("Not supplied").length).toBeGreaterThan(0);
    expect(screen.getByText("COMMITTED")).toBeTruthy();
  });
});

it("keeps two mounted owner-supplied editors independently labelled and suppresses stale refused action slots",()=>{
 const first=entry("en",{data:unitData()}),second=entry("en",{data:unitData()});
 const view=render(<>{first.ui}{second.ui}</>);const inputs=screen.getAllByRole("textbox",{name:"Your next message"});
 expect(inputs).toHaveLength(2);expect(new Set(inputs.map(node=>node.id)).size).toBe(2);
 view.rerender(entry("en",{data:unitData(),operationState:unitController("refused")}).ui);
 expect(screen.queryByRole("button",{name:"Unit send"})).toBeNull();expect(screen.queryByRole("button",{name:"Unit keep"})).toBeNull();
 expect(screen.getByRole("button",{name:"Unit check"})).toBeTruthy();
});

it("labels only the exact supplied recorded turn message, never a different current draft",()=>{
 const raw="  Original follow-up\n原文 🙂  ";
 render(<FreshConversationTurnPanel locale="en" data={unitData({state:"RECORDED",result:unitResult})} operationState={null}
 activity={null} message="Different new unsent draft" originalTurnMessage={raw} onMessageChange={vi.fn()} readOnly={true}/>);
 expect(screen.getByText(raw,{normalizer:value=>value}).textContent).toBe(raw);
 expect(screen.queryByText("Different new unsent draft")).toBeNull();
 expect(screen.getByText("Your message")).toBeTruthy();
});

it.each(["en","zh-CN"] as const)("unknown Keep %s shows only original-status recovery without an unavailable-draft conclusion",locale=>{
 render(entry(locale,{operationState:unitController("unknown"),message:"",data:null}).ui);
 expect(screen.getByText(locale==="en"?"The original request needs a status check. Don’t send it again.":"原请求需要查询状态。请勿再次发送。")).toBeTruthy();
 expect(screen.queryByText(locale==="en"?"Continuing is unavailable here right now. Your message remains a draft.":"此处暂时无法继续对话。消息仍是草稿。")).toBeNull();
 expect(screen.getByRole("button",{name:"Unit check"})).toBeTruthy();
});
