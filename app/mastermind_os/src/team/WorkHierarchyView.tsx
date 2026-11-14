/** HC21 — "Team · Parent work and scoped task dialogue" (board 1PB7-0).
 *
 * Left work hierarchy (448): parent work rows, then the DELEGATED WORK
 * section with task rows and a count. Right task dialogue (920): header,
 * facts row, task timeline, scoped task composer, footer.
 *
 * The delegated rows reuse the delegated-task binding vocabulary
 * (`DelegatedTaskState` from delegated-task.ts — the same five honest states
 * as DelegatedTaskCard), so this surface never invents a second state model.
 * Honesty law: `parentWork`/`delegated` are INDEPENDENT reads — each null
 * renders its own "not projected" state while the other still renders real
 * rows. Counts come only from the real arrays. With no `onCompose`, the
 * composer is disabled with a visible reason (no send path exists in this
 * build); nothing here ever fakes a dispatch. */
import { useId, useMemo, useRef, useState } from "react";
import type { DelegatedTaskState } from "./delegated-task";
import "./team.css";
import "./work-search.css";

export interface ParentWorkRow {
  id: string;
  title: string;
  meta: string | null;
}

export interface DelegatedWorkRow {
  id: string;
  title: string;
  state: DelegatedTaskState;
  owner: string | null;
}

export interface ScopedTaskTimelineStep {
  step: string;
  state: "done" | "pending" | "unknown";
  at: string | null;
}

/** The selected task's dialogue projection. `facts`/`timeline` are honest
 *  arrays: empty = a real read with nothing recorded, null timeline = not
 *  projected. */
export interface ScopedTaskDetail {
  id: string;
  title: string;
  owner: string | null;
  facts: { label: string; value: string }[];
  timeline: ScopedTaskTimelineStep[] | null;
}

interface Strings {
  heading: string;
  summary: string;
  hierarchyLabel: string;
  parentHeading: string;
  parentNotProjectedTitle: string;
  parentNotProjectedBody: string;
  parentZero: string;
  delegatedHeading: string;
  delegatedNotProjectedTitle: string;
  delegatedNotProjectedBody: string;
  delegatedZero: string;
  delegatedCount: (n: number) => string;
  openTaskReason: string;
  stateQueued: string;
  stateRunning: string;
  stateUnknown: string;
  stateDeclined: string;
  stateTerminal: string;
  taskLabel: string;
  dialogueHeading: string;
  dialogueNone: string;
  owner: (owner: string) => string;
  ownerNone: string;
  factsHeading: string;
  factsNone: string;
  timelineHeading: string;
  timelineNotProjected: string;
  timelineEmpty: string;
  stepDone: string;
  stepPending: string;
  stepUnknown: string;
  notObserved: string;
  composerHeading: string;
  composerLabel: string;
  composerPlaceholder: string;
  composerNote: string;
  composerDisabledReason: string;
  send: string;
  openTask: (title: string) => string;
}

const STRINGS: Record<"en" | "zh-CN", Strings> = {
  en: {
    heading: "Work",
    summary:
      "Parent work with its delegated tasks, and the scoped dialogue for the selected task.",
    hierarchyLabel: "Work hierarchy",
    parentHeading: "Parent work",
    parentNotProjectedTitle: "Parent work not projected in this build",
    parentNotProjectedBody:
      "No parent-work read exists in this build; no rows are shown.",
    parentZero: "No parent work is projected in this read.",
    delegatedHeading: "Delegated work",
    delegatedNotProjectedTitle: "Delegated work not projected in this build",
    delegatedNotProjectedBody:
      "No delegated-work read exists in this build; task rows and counts come only from a real read.",
    delegatedZero: "No delegated tasks are projected in this read.",
    delegatedCount: (n) => `${n} task${n === 1 ? "" : "s"}`,
    openTaskReason: "Opening a task dialogue is not wired in this build.",
    stateQueued: "Queued",
    stateRunning: "In progress",
    stateUnknown: "Outcome unknown",
    stateDeclined: "Declined",
    stateTerminal: "Finished",
    taskLabel: "Scoped task",
    dialogueHeading: "Task dialogue",
    dialogueNone: "Select a delegated task to open its dialogue.",
    owner: (owner) => `Owner ${owner}`,
    ownerNone: "No owner observed",
    factsHeading: "Task facts",
    factsNone: "No task facts are projected.",
    timelineHeading: "Task timeline",
    timelineNotProjected: "The timeline is not projected for this task.",
    timelineEmpty: "No timeline steps are recorded.",
    stepDone: "Done",
    stepPending: "Pending",
    stepUnknown: "Unknown",
    notObserved: "Not observed",
    composerHeading: "Scoped task composer",
    composerLabel: "Message this task",
    composerPlaceholder: "Write a direction for this task…",
    composerNote:
      "The composer speaks to this task's scope only — not the whole conversation.",
    composerDisabledReason:
      "No send path exists in this build — the composer is disabled.",
    send: "Send to task",
    openTask: (title) => `Open task dialogue — ${title}`,
  },
  "zh-CN": {
    heading: "工作",
    summary: "父级工作及其受派任务，以及所选任务的范围内对话。",
    hierarchyLabel: "工作层级",
    parentHeading: "父级工作",
    parentNotProjectedTitle: "此构建未投影父级工作",
    parentNotProjectedBody: "此构建中不存在父级工作读取；不显示任何行。",
    parentZero: "该读取中没有投影父级工作。",
    delegatedHeading: "受派工作",
    delegatedNotProjectedTitle: "此构建未投影受派工作",
    delegatedNotProjectedBody:
      "此构建中不存在受派工作读取；任务行与计数只来自真实读取。",
    delegatedZero: "该读取中没有投影受派任务。",
    delegatedCount: (n) => `${n} 个任务`,
    openTaskReason: "此构建未接通打开任务对话的路径。",
    stateQueued: "排队中",
    stateRunning: "进行中",
    stateUnknown: "结果未知",
    stateDeclined: "已拒绝",
    stateTerminal: "已完成",
    taskLabel: "受派任务",
    dialogueHeading: "任务对话",
    dialogueNone: "从层级中选择一个受派任务，打开其对话。",
    owner: (owner) => `负责人 ${owner}`,
    ownerNone: "未观测到负责人",
    factsHeading: "任务事实",
    factsNone: "未投影任务事实。",
    timelineHeading: "任务时间线",
    timelineNotProjected: "该任务未投影时间线。",
    timelineEmpty: "未记录时间线步骤。",
    stepDone: "已完成",
    stepPending: "待进行",
    stepUnknown: "未知",
    notObserved: "未观测",
    composerHeading: "任务输入框",
    composerLabel: "向该任务发消息",
    composerPlaceholder: "为该任务写一条指示…",
    composerNote: "输入框只作用于该任务的范围——不是整个对话。",
    composerDisabledReason: "此构建不存在发送路径——输入框已停用。",
    send: "发送给任务",
    openTask: (title) => `打开任务对话 — ${title}`,
  },
};

function stateLabel(state: DelegatedTaskState, t: Strings): string {
  if (state === "queued") return t.stateQueued;
  if (state === "running") return t.stateRunning;
  if (state === "unknown") return t.stateUnknown;
  if (state === "declined") return t.stateDeclined;
  return t.stateTerminal;
}

function stepMark(state: ScopedTaskTimelineStep["state"]): string {
  if (state === "done") return "✓";
  if (state === "pending") return "•";
  return "?";
}

export function WorkHierarchyView({
  locale = "en",
  parentWork,
  delegated,
  selectedTask,
  onCompose,
  onOpenTask,
  onCloseSelection,
}: {
  locale?: "en" | "zh-CN";
  /** null = no parent-work read in this build (honest note, no rows). */
  parentWork: ParentWorkRow[] | null;
  /** null = no delegated-work read in this build (honest note, no rows). */
  delegated: DelegatedWorkRow[] | null;
  /** null = no task dialogue open (honest placeholder). */
  selectedTask: ScopedTaskDetail | null;
  onCompose?: (text: string) => void;
  onOpenTask?: (taskId: string) => void;
  /** Escape clears the selection through this callback; absent = a no-op,
   *  never a focus trap. */
  onCloseSelection?: () => void;
}) {
  const t = STRINGS[locale];
  const uid = useId().replace(/[^a-zA-Z0-9-]/g, "");
  const taskRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [draft, setDraft] = useState("");

  const when = useMemo(() => {
    const format = new Intl.DateTimeFormat(locale, {
      dateStyle: "short",
      timeStyle: "short",
    });
    return (value: string | null) => {
      if (value === null) return t.notObserved;
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : format.format(date);
    };
  }, [locale, t]);

  const tasks = delegated ?? [];
  const focusIndex = selectedTask
    ? Math.max(
        0,
        tasks.findIndex((row) => row.id === selectedTask.id),
      )
    : 0;

  const focusRow = (index: number) => {
    taskRefs.current[index]?.focus();
  };
  const onTaskKeyDown = (
    event: React.KeyboardEvent,
    index: number,
  ) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusRow(Math.min(index + 1, tasks.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusRow(Math.max(index - 1, 0));
    } else if (event.key === "Home") {
      event.preventDefault();
      focusRow(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusRow(tasks.length - 1);
    }
  };
  const onSurfaceKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" && onCloseSelection) {
      event.preventDefault();
      onCloseSelection();
    }
  };

  const send = () => {
    const text = draft.trim();
    if (!onCompose || !text) return;
    onCompose(text);
    setDraft("");
  };

  return (
    <section
      className="mm-work-surface"
      aria-labelledby={`${uid}-heading`}
      onKeyDown={onSurfaceKeyDown}
    >
      <h2 id={`${uid}-heading`} tabIndex={-1}>
        {t.heading}
      </h2>
      <p className="muted">{t.summary}</p>
      <div className="mm-work-view">
        {/* ── Left · work hierarchy (448) ─────────────────────────────── */}
        <aside className="mm-work-hierarchy" aria-label={t.hierarchyLabel}>
          <section className="mm-work-parents" aria-label={t.parentHeading}>
            <h3>{t.parentHeading}</h3>
            {parentWork === null ? (
              <div className="mm-work-honest" role="status">
                <p className="mm-eyebrow">{t.parentNotProjectedTitle}</p>
                <p>{t.parentNotProjectedBody}</p>
              </div>
            ) : parentWork.length === 0 ? (
              <p className="mm-honest-line">{t.parentZero}</p>
            ) : (
              <ul className="mm-work-parent-rows">
                {parentWork.map((row) => (
                  <li key={row.id} className="mm-work-parent-row">
                    <span className="mm-work-parent-title">{row.title}</span>
                    {row.meta ? (
                      <small className="mm-work-parent-meta">{row.meta}</small>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section
            className="mm-work-delegated"
            aria-label={t.delegatedHeading}
          >
            <h3>
              {t.delegatedHeading}
              {/* Count only ever from the real array — never when null. */}
              {delegated !== null ? (
                <span
                  className="mm-work-count"
                  data-testid="mm-work-count"
                >
                  {t.delegatedCount(delegated.length)}
                </span>
              ) : null}
            </h3>
            {delegated === null ? (
              <div className="mm-work-honest" role="status">
                <p className="mm-eyebrow">{t.delegatedNotProjectedTitle}</p>
                <p>{t.delegatedNotProjectedBody}</p>
              </div>
            ) : tasks.length === 0 ? (
              <p className="mm-honest-line">{t.delegatedZero}</p>
            ) : (
              <>
                <ul className="mm-work-task-rows">
                  {tasks.map((row, index) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className="mm-work-task-row"
                        ref={(node) => {
                          taskRefs.current[index] = node;
                        }}
                        data-state={row.state}
                        data-selected={selectedTask?.id === row.id}
                        aria-current={
                          selectedTask?.id === row.id ? "true" : undefined
                        }
                        aria-label={t.openTask(row.title)}
                        tabIndex={index === focusIndex ? 0 : -1}
                        disabled={!onOpenTask}
                        onClick={() => onOpenTask?.(row.id)}
                        onKeyDown={(event) => onTaskKeyDown(event, index)}
                      >
                        <span className="mm-work-task-title">{row.title}</span>
                        <span
                          className="mm-chip mm-chip-state"
                          data-state={row.state}
                        >
                          {stateLabel(row.state, t)}
                        </span>
                        {row.owner ? (
                          <small className="mm-work-task-owner">
                            {row.owner}
                          </small>
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
                {!onOpenTask ? (
                  <p className="mm-pane-reason">{t.openTaskReason}</p>
                ) : null}
              </>
            )}
          </section>
        </aside>

        {/* ── Right · task dialogue (920) ─────────────────────────────── */}
        <div className="mm-work-dialogue" aria-label={t.dialogueHeading}>
          {selectedTask === null ? (
            <div className="mm-work-honest" role="status">
              <p className="mm-eyebrow">{t.dialogueHeading}</p>
              <p>{t.dialogueNone}</p>
            </div>
          ) : (
            <>
              <header className="mm-work-dialogue-head">
                <p className="mm-eyebrow">{t.taskLabel}</p>
                <h3>{selectedTask.title}</h3>
                <p className="mm-context-sub">
                  {selectedTask.owner
                    ? t.owner(selectedTask.owner)
                    : t.ownerNone}
                </p>
              </header>
              <section aria-label={t.factsHeading}>
                <h4 className="mm-dialogue-heading">{t.factsHeading}</h4>
                {selectedTask.facts.length === 0 ? (
                  <p className="mm-honest-line">{t.factsNone}</p>
                ) : (
                  <dl className="mm-work-facts">
                    {selectedTask.facts.map((fact) => (
                      <div key={`${fact.label}:${fact.value}`}>
                        <dt>{fact.label}</dt>
                        <dd>{fact.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </section>
              <section aria-label={t.timelineHeading}>
                <h4 className="mm-dialogue-heading">{t.timelineHeading}</h4>
                {selectedTask.timeline === null ? (
                  <p className="mm-honest-line">{t.timelineNotProjected}</p>
                ) : selectedTask.timeline.length === 0 ? (
                  <p className="mm-honest-line">{t.timelineEmpty}</p>
                ) : (
                  <ol className="mm-work-steps">
                    {selectedTask.timeline.map((step, index) => (
                      <li
                        key={`${step.step}-${index}`}
                        className="mm-work-step"
                        data-state={step.state}
                      >
                        <span className="mm-work-step-mark" aria-hidden="true">
                          {stepMark(step.state)}
                        </span>
                        <span className="mm-work-step-name">{step.step}</span>
                        <span className="mm-visually-hidden">
                          {step.state === "done"
                            ? t.stepDone
                            : step.state === "pending"
                              ? t.stepPending
                              : t.stepUnknown}
                        </span>
                        <small className="mm-work-step-at">
                          {when(step.at)}
                        </small>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
              <footer
                className="mm-work-composer"
                aria-label={t.composerHeading}
              >
                <label htmlFor={`${uid}-composer`}>{t.composerLabel}</label>
                <textarea
                  id={`${uid}-composer`}
                  value={draft}
                  placeholder={
                    onCompose ? t.composerPlaceholder : t.composerDisabledReason
                  }
                  disabled={!onCompose}
                  aria-describedby={`${uid}-composer-note`}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      (event.metaKey || event.ctrlKey)
                    ) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                <div>
                  <button
                    type="button"
                    className="mm-pane-action"
                    disabled={!onCompose || draft.trim().length === 0}
                    onClick={send}
                  >
                    {t.send}
                  </button>
                </div>
                {onCompose ? (
                  <p className="mm-pane-reason" id={`${uid}-composer-note`}>
                    {t.composerNote}
                  </p>
                ) : (
                  <p className="mm-pane-reason" id={`${uid}-composer-note`}>
                    {t.composerDisabledReason}
                  </p>
                )}
              </footer>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
