import { useId, useRef, useState, type ReactNode } from "react";
import "./new-project-draft.css";

export interface NewProjectDraftProps {
  locale: "en" | "zh-CN";
  /** The containing route chooses the page heading; embedded callers keep h2. */
  headingLevel?: 1 | 2;
  goal: string;
  onGoalChange: (value: string) => void;
  goalReadOnly?: boolean;
  onGoalFocus?: () => void;
  attachmentsControl?: ReactNode;
  attachmentsPanel?: ReactNode;
  primarySummary?: ReactNode;
  optionsPanel?: ReactNode;
  /** The actual creation owner controls admission, pending effects and recovery. */
  startControl?: ReactNode;
  feedbackPanel?: ReactNode;
  startNote?: ReactNode;
}

/** Controlled unsent composition. This view neither creates nor addresses a project. */
export function NewProjectDraft({ locale, goal, onGoalChange, attachmentsControl,
  optionsPanel, startControl, feedbackPanel, startNote, attachmentsPanel, primarySummary, headingLevel = 2, goalReadOnly = false, onGoalFocus }: NewProjectDraftProps) {
  const zh = locale === "zh-CN";
  const Heading = headingLevel === 1 ? "h1" : "h2";
  const text = (en: string, cn: string) => zh ? cn : en;
  const goalId = useId();
  const optionsId = useId();
  const optionsButton = useRef<HTMLButtonElement>(null);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const closeOptions = () => {
    setOptionsOpen(false);
    optionsButton.current?.focus();
  };
  // Removing a supplied panel closes only its disclosure; the goal remains owned above.
  const optionsVisible = optionsOpen && optionsPanel != null;
  return <section className="mm-new-project" lang={zh ? "zh-CN" : "en"}>
    <header className="mm-new-project-heading">
      <p className="mm-new-project-eyebrow">{text("New project", "新项目")}</p>
      <Heading>{text("What would you like done?", "你希望完成什么？")}</Heading>
      <p>{text("Start with the outcome. I’ll work out the steps.", "从期望的结果开始。我会梳理具体步骤。")}</p>
    </header>
    <div className="mm-new-project-goal">
      <label htmlFor={goalId}>{text("Your goal", "你的目标")}</label>
      <textarea id={goalId} value={goal} readOnly={goalReadOnly} onFocus={onGoalFocus} onChange={event => onGoalChange(event.target.value)}
        rows={3} />
      <div className="mm-new-project-tools">
        {attachmentsControl ?? <button type="button" disabled>{text("Add files", "添加文件")}</button>}
        <button type="button" ref={optionsButton} disabled={optionsPanel == null}
          aria-expanded={optionsVisible} aria-controls={optionsId}
          onClick={() => setOptionsOpen(open => !open)}>{text("Options", "选项")}</button>
      </div>
      {attachmentsControl == null && <p className="mm-new-project-unavailable">{text("File attachments are unavailable.", "暂时无法添加文件。")}</p>}
      {optionsPanel == null && <p className="mm-new-project-unavailable">{text("Project options are unavailable.", "暂时无法设置项目选项。")}</p>}
      {attachmentsPanel}
    </div>
    {optionsVisible && <section id={optionsId} className="mm-new-project-options"
      aria-label={text("Project options", "项目选项")}
      onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); closeOptions(); } }}>
      <div className="mm-new-project-options-header"><h3>{text("Project options", "项目选项")}</h3>
        <button type="button" onClick={closeOptions}>{text("Close", "关闭")}</button></div>
      {optionsPanel}
    </section>}
    <footer className="mm-new-project-start">
      {primarySummary != null && <div className="mm-new-project-summary">{primarySummary}</div>}
      <div className="mm-new-project-start-control">{startControl ?? <button type="button" disabled>{text("Start project", "开始项目")}</button>}</div>
      <p>{startNote ?? (startControl != null ? text("Opens your project conversation.", "打开你的项目对话。") :
        text("Your goal is a draft. Project creation is unavailable.", "目标仍是草稿。暂时无法创建项目。"))}</p>
    </footer>
    {feedbackPanel != null && <div className="mm-new-project-feedback">{feedbackPanel}</div>}
  </section>;
}
