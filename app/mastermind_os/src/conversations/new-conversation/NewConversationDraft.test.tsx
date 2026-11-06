// @vitest-environment jsdom
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NewConversationDraft } from "./NewConversationDraft";

afterEach(cleanup);

const projects = [
  { workRef: "proj-alpha", title: "Alpha project" },
  { workRef: "proj-beta", title: null },
];

const entry = (locale: "en" | "zh-CN", overrides: {
  onWorkRefChange?: (value: string | null) => void;
  onMessageChange?: (value: string) => void;
  onBack?: () => void;
  readOnly?: boolean;
  projectsState?: "reading" | "available" | "unavailable";
  projects?: readonly { workRef: string; title: string | null }[];
  previewControl?: ReactNode;
  feedback?: ReactNode;
} = {}) =>
  <NewConversationDraft locale={locale} projects={overrides.projects ?? projects}
    projectsState={overrides.projectsState ?? "available"} workRef={null}
    onWorkRefChange={overrides.onWorkRefChange ?? vi.fn()} message=""
    onMessageChange={overrides.onMessageChange ?? vi.fn()}
    readOnly={overrides.readOnly} previewControl={overrides.previewControl}
    feedback={overrides.feedback} onBack={overrides.onBack ?? vi.fn()} />;

const select = (label: string) => screen.getByLabelText(label) as HTMLSelectElement;
const messageBox = (label: string) => screen.getByLabelText(label) as HTMLTextAreaElement;

afterEach(() => { vi.restoreAllMocks(); });

describe("NewConversationDraft", () => {
  it("renders the quiet entry copy with exact controlled fields", () => {
    render(entry("en"));
    expect(screen.getByRole("heading", { name: "New conversation" })).toBeTruthy();
    expect(screen.getByText("Choose a project and write the first message.")).toBeTruthy();
    expect(screen.getByText("Your message is a draft until you confirm creation.")).toBeTruthy();
    expect(messageBox("First message").rows).toBe(6);
    expect(messageBox("First message").maxLength).toBe(-1);
    expect(screen.getByText("Use 1–700 characters.")).toBeTruthy();
    expect(screen.getByLabelText("Project")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back to conversations" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review conversation" })).toBeTruthy();
  });

  it("keeps explicit project choice and first message in the existing controlled owner", () => {
    const onWorkRefChange = vi.fn();
    const onMessageChange = vi.fn();
    render(entry("en", { onWorkRefChange, onMessageChange }));
    const project = select("Project");
    expect(project.value).toBe("");
    expect(project.selectedOptions[0]?.textContent).toBe("Choose a project");
    fireEvent.change(project, { target: { value: "proj-beta" } });
    expect(onWorkRefChange).toHaveBeenCalledTimes(1);
    expect(onWorkRefChange).toHaveBeenCalledWith("proj-beta");
    expect(project.value).toBe("");
    const draft = messageBox("First message");
    fireEvent.change(draft, { target: { value: "  source: [样例]\nnext line  " } });
    expect(onMessageChange).toHaveBeenCalledTimes(1);
    expect(onMessageChange).toHaveBeenCalledWith("  source: [样例]\nnext line  ");
    expect(draft.value).toBe("");
  });

  it("never selects a project or calls owners on mount or locale change", () => {
    const onWorkRefChange = vi.fn();
    const onMessageChange = vi.fn();
    const view = render(entry("en", { onWorkRefChange, onMessageChange }));
    expect(onWorkRefChange).not.toHaveBeenCalled();
    expect(onMessageChange).not.toHaveBeenCalled();
    view.rerender(entry("zh-CN", { onWorkRefChange, onMessageChange }));
    expect(onWorkRefChange).not.toHaveBeenCalled();
    expect(onMessageChange).not.toHaveBeenCalled();
    const project = select("项目");
    expect(project.value).toBe("");
    expect(project.selectedOptions[0]?.textContent).toBe("选择项目");
    expect(project.selectedOptions[0]?.disabled).toBe(false);
  });

  it("renders supplied titles verbatim with exact workRef fallback only when the title is absent", () => {
    render(entry("en", {
      projects: [
        { workRef: "proj-alpha", title: "Alpha project" },
        { workRef: "proj-beta", title: null },
      ],
    }));
    expect(screen.getAllByRole("option").map(option => option.textContent))
      .toEqual(["Choose a project", "Alpha project", "proj-beta"]);
    expect(select("Project").selectedOptions[0]?.textContent).toBe("Choose a project");
  });

  it("preserves the multiline draft, textarea node and focus through a locale rerender", () => {
    function Owner({ zh }: { zh: boolean }) {
      const [draft, setDraft] = useState("");
      return <NewConversationDraft locale={zh ? "zh-CN" : "en"} projects={projects}
        projectsState="available" workRef={null} onWorkRefChange={vi.fn()} message={draft}
        onMessageChange={setDraft} onBack={vi.fn()} />;
    }
    const view = render(<Owner zh={false} />);
    const textarea = messageBox("First message");
    fireEvent.change(textarea, { target: { value: "Retain this unsent draft\n保持原文" } });
    expect((screen.getByLabelText("First message") as HTMLTextAreaElement).value)
      .toBe("Retain this unsent draft\n保持原文");
    textarea.focus();
    view.rerender(<Owner zh />);
    expect(screen.getByLabelText("第一条消息")).toBe(textarea);
    expect(textarea.value).toBe("Retain this unsent draft\n保持原文");
    expect(document.activeElement).toBe(textarea);
  });

  it.each([
    { state: "reading" as const, projectCount: 1, en: "Loading projects…", zh: "正在加载项目…" },
    { state: "available" as const, projectCount: 0, en: "No projects are available in this view.", zh: "此视图暂无可用项目。" },
    { state: "unavailable" as const, projectCount: 1, en: "Projects could not be loaded.", zh: "项目列表暂时无法读取。" },
  ])("shows the plain $state project sentence in both locales and disables the select", ({ state, projectCount, en, zh }) => {
    const view = render(entry("en", { projectsState: state, projects: projects.slice(0, projectCount) }));
    expect(screen.getByText(en)).toBeTruthy();
    expect(select("Project").disabled).toBe(true);
    view.rerender(entry("zh-CN", { projectsState: state, projects: projects.slice(0, projectCount) }));
    expect(screen.getByText(zh)).toBeTruthy();
    expect(screen.queryByText(en)).toBeNull();
    expect(select("项目").disabled).toBe(true);
  });

  it("enables the select only for a supplied non-empty available project list", () => {
    render(entry("en"));
    expect(select("Project").disabled).toBe(false);
    for (const sentence of ["Loading projects…", "No projects are available in this view.", "Projects could not be loaded."]) {
      expect(screen.queryByText(sentence)).toBeNull();
    }
  });

  it("readOnly disables the fields while Back still calls only onBack", () => {
    const onBack = vi.fn();
    const onWorkRefChange = vi.fn();
    const onMessageChange = vi.fn();
    render(entry("en", { readOnly: true, onBack, onWorkRefChange, onMessageChange }));
    expect(select("Project").disabled).toBe(true);
    expect(messageBox("First message").disabled).toBe(true);
    expect(select("Project").value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onWorkRefChange).not.toHaveBeenCalled();
    expect(onMessageChange).not.toHaveBeenCalled();
  });

  it("passes caller preview and feedback nodes through without inventing a preview", () => {
    const review = vi.fn();
    render(entry("en", {
      previewControl: <button type="button" onClick={review}>Owner review</button>,
      feedback: <p>Original owner holds this conversation.</p>,
    }));
    fireEvent.click(screen.getByRole("button", { name: "Owner review" }));
    expect(review).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Preview is unavailable here.")).toBeNull();
    expect(screen.queryByText("Review conversation")).toBeNull();
    expect(screen.getByText("Original owner holds this conversation.")).toBeTruthy();
  });

  it("supplies the disabled fallback review when no preview control is provided", () => {
    render(entry("en"));
    const fallback = screen.getByRole("button", { name: "Review conversation" }) as HTMLButtonElement;
    expect(fallback.disabled).toBe(true);
    expect(screen.getByText("Preview is unavailable here.")).toBeTruthy();
    fireEvent.click(fallback);
    expect(screen.getByText("Preview is unavailable here.")).toBeTruthy();
  });

  it("supplies the complete Chinese entry copy without extra launch controls", () => {
    const onBack = vi.fn();
    render(entry("zh-CN", { onBack }));
    expect(screen.getByRole("heading", { name: "新建对话" })).toBeTruthy();
    expect(screen.getByText("选择项目并填写第一条消息。")).toBeTruthy();
    expect(screen.getByLabelText("项目")).toBeTruthy();
    expect(screen.getByLabelText("第一条消息")).toBeTruthy();
    expect(screen.getByText("请输入1–700个字符。")).toBeTruthy();
    expect(screen.getByText("确认创建前，消息仍是草稿。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "预览对话" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("此处暂时无法预览。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回对话" }));
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Add files|Options|Start project|Launch/)).toBeNull();
  });
});
