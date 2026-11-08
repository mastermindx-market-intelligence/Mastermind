import { useId, type ReactNode } from "react";
import "./new-conversation-draft.css";

export interface NewConversationDraftProps {
  locale: "en" | "zh-CN";
  contract?: "legacy-v1" | "native-v2";
  projects: readonly { workRef: string; title: string | null }[];
  projectsState: "reading" | "available" | "unavailable";
  workRef: string | null;
  onWorkRefChange: (value: string | null) => void;
  message: string;
  onMessageChange: (value: string) => void;
  readOnly?: boolean;
  previewControl?: ReactNode;
  feedback?: ReactNode;
  onBack: () => void;
}

/** Controlled unsent composition. This view neither creates nor previews a conversation. */
export function NewConversationDraft({ locale, contract="legacy-v1", projects, projectsState, workRef,
  onWorkRefChange, message, onMessageChange, readOnly, previewControl, feedback,
  onBack }: NewConversationDraftProps) {
  const zh = locale === "zh-CN";
  const text = (en: string, cn: string) => zh ? cn : en;
  const projectId = useId();
  const messageId = useId();
  const statusId = useId();
  const helperId = useId();
  // The conversation owner owns admission and project supply; this view only reflects it.
  const projectNote = projectsState === "reading"
    ? text("Loading projects…", "正在加载项目…")
    : projectsState === "unavailable"
      ? text("Projects could not be loaded.", "项目列表暂时无法读取。")
      : projects.length === 0
        ? text("No projects are available in this view.", "此视图暂无可用项目。")
        : null;
  return <section className="mm-new-conversation" lang={zh ? "zh-CN" : "en"}>
    <header className="mm-new-conversation-heading">
      <button type="button" onClick={onBack}>{text("Back to conversations", "返回对话")}</button>
      <h1>{text("New conversation", "新建对话")}</h1>
      <p>{text("Choose a project and write the first message.", "选择项目并填写第一条消息。")}</p>
    </header>
    <div className="mm-new-conversation-panel">
      <div className="mm-new-conversation-field">
        <label htmlFor={projectId}>{text("Project", "项目")}</label>
        <select id={projectId} value={workRef ?? ""} disabled={readOnly || projectNote != null}
          aria-describedby={projectNote != null ? statusId : undefined}
          onChange={event => onWorkRefChange(event.target.value === "" ? null : event.target.value)}>
          <option value="">{text("Choose a project", "选择项目")}</option>
          {projects.map(project =>
            <option key={project.workRef} value={project.workRef}>{project.title ?? project.workRef}</option>)}
        </select>
        {projectNote != null && <p id={statusId} className="mm-new-conversation-status">{projectNote}</p>}
      </div>
      <div className="mm-new-conversation-field">
        <label htmlFor={messageId}>{text("First message", "第一条消息")}</label>
        <textarea id={messageId} rows={6} value={message} disabled={readOnly}
          aria-describedby={helperId}
          onChange={event => onMessageChange(event.target.value)} />
        <p id={helperId} className="mm-new-conversation-helper">{contract==="native-v2"?text("Enter your message (up to 128 KiB of text).","请输入消息（最多128 KiB文本）。"):text("Use 1–700 characters.", "请输入1–700个字符。")}</p>
      </div>
      <p className="mm-new-conversation-caption">{text("Your message is a draft until you confirm creation.", "确认创建前，消息仍是草稿。")}</p>
    </div>
    {feedback != null && <div className="mm-new-conversation-feedback">{feedback}</div>}
    <footer className="mm-new-conversation-footer">
      <div className="mm-new-conversation-actions">
        {previewControl ?? <button type="button" disabled>{text("Review conversation", "预览对话")}</button>}
      </div>
      {previewControl == null && <p className="mm-new-conversation-note">{text("Preview is unavailable here.", "此处暂时无法预览。")}</p>}
    </footer>
  </section>;
}
