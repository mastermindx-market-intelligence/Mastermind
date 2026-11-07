// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NewProjectDraft } from "./NewProjectDraft";

afterEach(cleanup);

describe("NewProjectDraft", () => {
  it("keeps raw goal edits in the existing controlled owner", () => {
    const changed = vi.fn();
    render(<NewProjectDraft locale="en" goal="" onGoalChange={changed} />);
    fireEvent.change(screen.getByLabelText("Your goal"), { target: { value: "  source: [样例]\nnext line  " } });
    expect(changed).toHaveBeenCalledExactlyOnceWith("  source: [样例]\nnext line  ");
    expect((screen.getByLabelText("Your goal") as HTMLTextAreaElement).value).toBe("");
  });

  it("never creates a project or opens a fake file picker when owners are absent", () => {
    render(<NewProjectDraft locale="en" goal="" onGoalChange={vi.fn()} />);
    for (const label of ["Start project", "Add files", "Options"]) {
      expect((screen.getByRole("button", { name: label }) as HTMLButtonElement).disabled).toBe(true);
    }
    expect(screen.getByText("Your goal is a draft. Project creation is unavailable.")).toBeTruthy();
    expect(screen.getByText("File attachments are unavailable.")).toBeTruthy();
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(screen.queryByText("Working")).toBeNull();
    expect(screen.queryByText("Opens your project conversation.")).toBeNull();
  });

  it("preserves the textarea and owner draft through locale, option and failure changes", () => {
    function Owner({ zh, failed }: { zh: boolean; failed: boolean }) {
      const [goal, setGoal] = useState("");
      return <NewProjectDraft locale={zh ? "zh-CN" : "en"} goal={goal} onGoalChange={setGoal}
        optionsPanel={<p>Explicit synthetic option</p>}
        feedbackPanel={failed ? <p>Original creation owner refused the request.</p> : undefined} />;
    }
    const view = render(<Owner zh={false} failed={false} />);
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Retain this unsent goal\n保持原文" } });
    fireEvent.click(screen.getByRole("button", { name: "Options" }));
    expect(screen.getByText("Explicit synthetic option")).toBeTruthy();
    view.rerender(<Owner zh failed />);
    expect(screen.getByRole("textbox")).toBe(textarea);
    expect((textarea as HTMLTextAreaElement).value).toBe("Retain this unsent goal\n保持原文");
    expect(screen.getByText("Original creation owner refused the request.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.getByRole("textbox")).toBe(textarea);
    expect((textarea as HTMLTextAreaElement).value).toBe("Retain this unsent goal\n保持原文");
  });

  it("returns focus for Close and Escape without moving the goal field", () => {
    render(<NewProjectDraft locale="en" goal="Synthetic draft" onGoalChange={vi.fn()}
      optionsPanel={<input aria-label="Actual option" />} />);
    const options = screen.getByRole("button", { name: "Options" });
    fireEvent.click(options);
    const option = screen.getByLabelText("Actual option");
    option.focus();
    fireEvent.keyDown(option, { key: "Escape" });
    expect(screen.queryByLabelText("Actual option")).toBeNull();
    expect(document.activeElement).toBe(options);
    fireEvent.click(options);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(document.activeElement).toBe(options);
  });

  it("passes actual attachment/start controls through with their existing admission", () => {
    const start = vi.fn();
    const attach = vi.fn();
    const view = render(<NewProjectDraft locale="en" goal="Explicit synthetic goal" onGoalChange={vi.fn()}
      attachmentsControl={<button onClick={attach}>Owner attach</button>}
      startControl={<button disabled onClick={start}>Owner start</button>} />);
    fireEvent.click(screen.getByRole("button", { name: "Owner start" }));
    expect(start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Owner attach" }));
    expect(attach).toHaveBeenCalledTimes(1);
    view.rerender(<NewProjectDraft locale="en" goal="Explicit synthetic goal" onGoalChange={vi.fn()}
      startControl={<button onClick={start}>Owner start</button>} />);
    fireEvent.click(screen.getByRole("button", { name: "Owner start" }));
    expect(start).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Created")).toBeNull();
  });

  it("supplies complete Chinese empty-state copy without samples or wizard steps", () => {
    render(<NewProjectDraft locale="zh-CN" goal="" onGoalChange={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "你希望完成什么？" })).toBeTruthy();
    expect(screen.getByLabelText("你的目标")).toBeTruthy();
    expect(screen.getByText("目标仍是草稿。暂时无法创建项目。")).toBeTruthy();
    expect(screen.queryByText(/Step 1|Working|workspace name/i)).toBeNull();
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
  });
});

it("keeps embedded h2 by default and supplies one route h1 on request",()=>{
 const change=vi.fn();
 const view=render(<NewProjectDraft locale="en" goal="Retained goal" onGoalChange={change}/>);
 const textarea=screen.getByRole("textbox");
 expect(screen.getByRole("heading",{level:2,name:"What would you like done?"})).toBeTruthy();
 expect(screen.queryByRole("heading",{level:1})).toBeNull();
 view.rerender(<NewProjectDraft headingLevel={1} locale="en" goal="Retained goal" onGoalChange={change}/>);
 expect(screen.getAllByRole("heading",{level:1})).toHaveLength(1);
 expect(screen.getByRole("textbox")).toBe(textarea);expect(change).not.toHaveBeenCalled();
});

it('keeps goal label and toolbar outside the field and places concise primary before long feedback',()=>{
 render(<NewProjectDraft locale="en" goal="Exact goal" onGoalChange={vi.fn()}
  attachmentsControl={<input aria-label="Retained actual chooser" type="file"/>}
  attachmentsPanel={<p>Actual staged state</p>} primarySummary={<p>Verified supplied profile</p>}
  startControl={<button>Create through owner</button>} feedbackPanel={<p>Long original result</p>}/>);
 const textarea=screen.getByRole('textbox'),toolbar=screen.getByLabelText('Retained actual chooser').closest('.mm-new-project-tools')!;
 expect(textarea.contains(toolbar)).toBe(false);
 expect(textarea.compareDocumentPosition(toolbar)&Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
 expect(screen.getByRole('button',{name:'Create through owner'}).compareDocumentPosition(screen.getByText('Long original result'))&Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
 expect(screen.getByText('Verified supplied profile').closest('footer')).toBeTruthy();
});
