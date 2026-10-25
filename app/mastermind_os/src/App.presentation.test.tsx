// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { MetaCeoOffice } from "./meta-ceo/MetaCeoOffice";
import { projectOffice, type OfficeInput, type ProjectionContext } from "./meta-ceo/projection";
import { decodeMission } from "./mission";
import missionFixture from "./fixtures/mission-v2-current-128c46f6.json";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue({ state: "BUILT_NOT_PROVEN" }) }));
beforeEach(() => {
  history.replaceState(null, "", "/os/?work_ref=WS%3AONE&root_job_id=JOB-1");
  delete window.MastermindMissionHost;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost; });

describe("explicit shell presentation", () => {
  it("defaults to English and dark without borrowing browser preferences", () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("zh-CN");
    localStorage.setItem("theme", "light");
    try {
      const { container } = render(<App />);
      const shell = container.querySelector(".shell")!;
      expect(shell.getAttribute("lang")).toBe("en");
      expect(shell.getAttribute("data-theme")).toBe("dark");
    } finally { localStorage.removeItem("theme"); }
  });

  it("changes render inputs without losing the company draft or its focused control", () => {
    const { container, rerender } = render(<App />);
    const field = screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "Keep my exact 公司 direction." } });
    field.focus();
    rerender(<App locale="zh-CN" theme="light" />);
    expect(container.querySelector(".shell")?.getAttribute("lang")).toBe("zh-CN");
    expect(container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("textbox", { name: "给 Meta-CEO 的方向" })).toBe(field);
    expect(field.value).toBe("Keep my exact 公司 direction.");
    expect(document.activeElement).toBe(field);
    expect(screen.queryByRole("button", { name: /^(Send|发送)$/ })).toBeNull();
    rerender(<App locale="en" theme="dark" />);
    expect(screen.getByRole("textbox", { name: "Direction to Meta-CEO" })).toBe(field);
    expect(field.value).toBe("Keep my exact 公司 direction.");
  });

  it("localizes Office copy while preserving exact owner text, reasons and preview content", () => {
    const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
      sessionRef: null, bindingGeneration: null, revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };
    const raw = structuredClone(missionFixture);
    raw.program.title = "Owner 原文 project";
    raw.program.next_action = "Do exactly this. 不改写。";
    const input: OfficeInput = { programs: null, result: null, conversation: null, mission: { context,
      source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1", observed_at: "2026-10-13T02:00:00Z", state: "CURRENT", coverage: "COMPLETE" },
      value: decodeMission(raw, context.selection!)! } };
    const projection = projectOffice(input, context), onDraftChange = vi.fn();
    const { rerender } = render(<MetaCeoOffice locale="zh-CN" projection={projection}
      draft={{ text: "Original private draft 原样", context }} onDraftChange={onDraftChange} />);
    expect(screen.getByRole("heading", { name: "让整个公司有方向地前进。" })).toBeTruthy();
    expect(screen.getAllByText("Do exactly this. 不改写。").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "查看方向预览" }));
    const preview = screen.getByRole("region", { name: "方向预览" });
    expect(preview.textContent).toContain("Original private draft 原样");
    expect(preview.textContent).toContain("EFFECT_NONE");
    rerender(<MetaCeoOffice locale="en" projection={projection}
      draft={{ text: "Original private draft 原样", context }} onDraftChange={onDraftChange} />);
    expect(screen.getByRole("region", { name: "Direction preview" })).toBe(preview);
    expect(onDraftChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review direction preview" }));
  });
});
