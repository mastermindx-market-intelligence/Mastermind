import { useLayoutEffect, useRef, useState } from "react";
import type { ProjectPlanRead, ProjectPlanSelection } from "./project-plan";
import { projectExecutionContext } from "./project-execution-context";
import { createProjectLaunchDraft, type ProjectLaunchDraft, type ProjectLaunchOutcome,
  type ProjectLaunchRefusal } from "./project-launch-handoff";

export interface ProjectPlanLaunchInspection {
  readonly read: ProjectPlanRead;
  readonly selection: ProjectPlanSelection;
  readonly isCurrent: () => boolean;
}
export interface ProjectStartWorkProps {
  inspection: ProjectPlanLaunchInspection | null;
  locale?: "en" | "zh-CN";
  disabled?: boolean;
  operationHold?: "checking" | "pending" | null;
  onStart: (draft: ProjectLaunchDraft, inspection: ProjectPlanLaunchInspection) =>
    ProjectLaunchOutcome | Promise<ProjectLaunchOutcome>;
}
type Status = { kind: "idle" | "opening" | "opened" } |
  { kind: "refused"; reason: ProjectLaunchRefusal };
const reasons: Record<ProjectLaunchRefusal, [string, string]> = {
  PROJECT_CONTEXT_NOT_CURRENT: ["Refresh the project plan before starting work.", "请刷新项目计划后再开始工作。"],
  LAUNCH_OWNER_UNAVAILABLE: ["Execution is not available for this project yet.", "此项目暂时无法执行工作。"],
  WORKSTREAM_MISMATCH: ["The launch does not match this project. Refresh the workspace.", "启动配置与此项目不符，请刷新工作区。"],
  LAUNCH_COMMAND_HELD: ["A launch is already pending. Check its original status.", "已有启动请求待确认，请查看原始请求的状态。"],
  LAUNCH_GOAL_PRESERVED: ["Your existing work draft is preserved. Finish or close that draft first.", "已保留你现有的工作草稿，请先完成或关闭该草稿。"],
};
function current(inspection: ProjectPlanLaunchInspection | null): boolean {
  try { return inspection?.isCurrent() === true; } catch { return false; }
}

/** Opens the existing reviewable launch form; this control never submits work. */
export function ProjectStartWork({ inspection, locale = "en", disabled = false, operationHold = null, onStart }: ProjectStartWorkProps) {
  const chinese = locale === "zh-CN";
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const flight = useRef(0);
  const busy = useRef(false);
  const live = useRef(inspection);
  live.current = inspection;
  const workRef = inspection?.selection.work_ref;
  const read = inspection?.read;
  useLayoutEffect(() => {
    ++flight.current;
    busy.current = false;
    setStatus({ kind: "idle" });
    return () => { ++flight.current; busy.current = false; };
  }, [read, workRef]);

  const start = async () => {
    if (disabled || operationHold || busy.current) return;
    const captured = live.current;
    if (!captured || !current(captured)) {
      setStatus({ kind: "refused", reason: "PROJECT_CONTEXT_NOT_CURRENT" });
      return;
    }
    let draft: ProjectLaunchDraft;
    try {
      const context = projectExecutionContext(captured.read, captured.selection);
      if (context.state !== "AVAILABLE") throw new Error("Unavailable project");
      // The visible project objective is an editable initial goal, not a grant.
      draft = createProjectLaunchDraft(context, context.objective);
    } catch {
      setStatus({ kind: "refused", reason: "PROJECT_CONTEXT_NOT_CURRENT" });
      return;
    }
    busy.current = true;
    const token = ++flight.current;
    setStatus({ kind: "opening" });
    const stillCurrent = () => token === flight.current &&
      live.current?.read === captured.read &&
      live.current.selection.work_ref === captured.selection.work_ref &&
      current(captured) && current(live.current);
    try {
      const outcome = await onStart(draft, captured);
      if (stillCurrent()) setStatus(outcome.status === "OPENED"
        ? { kind: "opened" } : { kind: "refused", reason: outcome.reason });
    } catch {
      if (stillCurrent()) setStatus({ kind: "refused", reason: "LAUNCH_OWNER_UNAVAILABLE" });
    } finally {
      if (token === flight.current) {
        busy.current = false;
        // A source fence may change without a React render while the read waits.
        if (!stillCurrent()) setStatus({ kind: "refused", reason: "PROJECT_CONTEXT_NOT_CURRENT" });
      }
    }
  };
  let message: string | null = null;
  if (operationHold === "checking") message = chinese ? "正在检查之前的工作…" : "Checking previous work…";
  else if (operationHold === "pending") message = chinese
    ? "开始新的执行前，请先确认之前工作的状态。"
    : "Check the status of earlier work before starting another run.";
  else if (status.kind === "refused") message = reasons[status.reason][chinese ? 1 : 0];
  else if (status.kind === "opened") message = chinese
    ? "请检查下方的启动设置，点击启动后才会开始工作。"
    : "Review the launch setup below. Work starts when you launch it.";
  else if (!inspection) message = chinese
    ? "读取当前项目计划后即可开始工作。" : "Read the current project plan to start work.";
  else if (disabled) message = chinese ? "登录后即可开始工作。" : "Sign in to start work.";
  return <span className="mm-project-workspace__control">
    <button type="button" className="mm-project-workspace__control-button"
      disabled={disabled || operationHold !== null || inspection === null || status.kind === "opening"}
      onClick={() => { void start(); }} aria-busy={status.kind === "opening"}>
      {status.kind === "opening" ? chinese ? "正在打开…" : "Opening…" : chinese ? "开始工作" : "Start work"}
    </button>
    {message && <span className="mm-project-workspace__control-why mm-project-workspace__muted"
      role={status.kind === "refused" ? "alert" : "status"}>{message}</span>}
  </span>;
}
