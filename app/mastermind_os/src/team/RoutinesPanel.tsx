import { useEffect, useId, useState } from "react";
import type { TeamRoster } from "./team-roster";
import "./routines.css";

/** HC10 — Routines · Schedule, run and delivery (15GA-0), hosted in the Team
 *  conversation workspace. Structure and copy follow the authored Paper
 *  extraction; every run/schedule VALUE comes from the `routine` record or the
 *  real roster. Paper sample data ("Engineering check-in", "20:30",
 *  "America / Vancouver"…) is never shipped: fields without a projection
 *  source render honest unknown-with-reason rows instead. The next occurrence
 *  deliberately has no field on the record — no scheduler projection exists in
 *  this build, so that row always says so rather than sampling a time. */

export type RoutineStatus = "scheduled" | "paused";
export type RoutineRunExecutionState =
  | "running"
  | "finished"
  | "failed"
  | "unknown";
export type RoutineRunDeliveryState =
  | "delivered"
  | "pending"
  | "failed"
  | "unknown";

/** Summary of the latest observed run. Null on the record means "not
 *  projected" — rendered as unknown-with-reason, never as a finished state. */
export interface RoutineRunSummary {
  /** Observed finish (or last-seen) time, exactly as the record carries it. */
  finishedAt: string;
  executionState: RoutineRunExecutionState;
  deliveryState: RoutineRunDeliveryState;
}

export interface RoutineRecentRun {
  finishedAt: string;
  executionState: RoutineRunExecutionState;
  deliveryState: RoutineRunDeliveryState;
}

/** The routine projection record. Owned by this panel's producer contract;
 *  `null` for the whole record means no routine projection is wired. */
export interface RoutineRecord {
  name: string;
  status: RoutineStatus;
  /** Instruction text the teammate runs on each occurrence. */
  instruction: string;
  /** Repeat rule string, verbatim from the projection (never composed here). */
  repeatRule: string;
  /** Timezone name from the projection — never a sampled zone. */
  timezone: string;
  /** Delivery target id, resolved against the real roster's bots. */
  deliveryTargetId: string | null;
  latestRun: RoutineRunSummary | null;
  recentRuns: RoutineRecentRun[] | null;
}

const STRINGS = {
  en: {
    heading: "Routines",
    back: "← Team",
    chipScheduled: "Scheduled",
    chipPaused: "Paused",
    instructionLabel: "What should happen?",
    instructionHint: "The instruction this teammate runs on each occurrence.",
    scheduleHeading: "Schedule",
    repeatLabel: "Repeat",
    timezoneLabel: "Timezone",
    deliveryHeading: "Deliver the result to",
    deliveryNote: "The run and its delivery are tracked separately.",
    deliveryUnsetOption: "No delivery target set",
    runBehaviorHeading: "Run behavior",
    executionLabel: "Execution",
    executionUnknown: "Unknown — no delivery target is selected on this roster",
    overlapLabel: "If a run is still active",
    overlapValue: "Gateway policy",
    editingNote:
      "No routine write path is wired in this build. Changes you type stay in this view and are not saved.",
    pauseAction: "Pause routine",
    resumeAction: "Resume routine",
    actionUnavailableReason:
      "No routine control path is wired in this build — this action stays disabled.",
    railHeading: "SCHEDULE & HISTORY",
    nextOccurrenceLabel: "Next occurrence",
    nextOccurrenceUnknown:
      "Not projected in this build — no scheduler projection is wired, so no time or zone is shown.",
    latestRunHeading: "Latest run",
    latestRunUnknown: "No run is projected for this routine yet.",
    executionStateLabel: "Execution",
    deliveryStateLabel: "Room delivery",
    openResult: "Open result in room →",
    openResultUnavailable:
      "No room result path is wired in this build for this run.",
    recentRunsHeading: "Recent runs",
    recentRunsUnknown: "Run history is not projected in this build.",
    recentRunsEmpty: "No runs recorded yet.",
    pauseNote:
      "Pausing the schedule stops future scheduled starts. Any active run keeps its own lifecycle and finishes independently.",
    unavailableTitle: "Routines are not projected in this build",
    unavailableBody:
      "No routine projection source is wired to this surface, so no schedule, run or delivery state is shown or inferred.",
    unavailableNote:
      "An absent projection is never filled with sample times, zones or run states.",
    execRunning: "Running",
    execFinished: "Finished",
    execFailed: "Failed",
    execUnknown: "Unknown",
    deliveryDelivered: "Delivered",
    deliveryPending: "Pending",
    deliveryFailed: "Failed",
    deliveryUnknown: "Unknown",
    recentRunsLabel: "Recent runs",
    rosterEmptyOption: "No teammates on the roster to deliver to",
  },
  "zh-CN": {
    heading: "例行任务",
    back: "← 团队",
    chipScheduled: "已排程",
    chipPaused: "已暂停",
    instructionLabel: "应该发生什么？",
    instructionHint: "该成员每次执行时运行的指令。",
    scheduleHeading: "排程",
    repeatLabel: "重复",
    timezoneLabel: "时区",
    deliveryHeading: "结果送达对象",
    deliveryNote: "运行与其送达是分开跟踪的。",
    deliveryUnsetOption: "未设置送达对象",
    runBehaviorHeading: "运行行为",
    executionLabel: "执行",
    executionUnknown: "未知——名册中未选择送达对象",
    overlapLabel: "如果一次运行仍在进行",
    overlapValue: "网关策略",
    editingNote:
      "此版本未接入例行任务写入路径。你输入的更改只保留在当前视图中，不会被保存。",
    pauseAction: "暂停例行任务",
    resumeAction: "恢复例行任务",
    actionUnavailableReason: "此版本未接入例行任务控制路径——该操作保持禁用。",
    railHeading: "排程与历史",
    nextOccurrenceLabel: "下次执行",
    nextOccurrenceUnknown:
      "此版本未投影——未接入排程投影，因此不显示任何时间或时区。",
    latestRunHeading: "最近一次运行",
    latestRunUnknown: "尚未投影该例行任务的任何运行。",
    executionStateLabel: "执行",
    deliveryStateLabel: "房间送达",
    openResult: "在房间中打开结果 →",
    openResultUnavailable: "此版本未接入该运行的房间结果路径。",
    recentRunsHeading: "近期运行",
    recentRunsUnknown: "此版本未投影运行历史。",
    recentRunsEmpty: "尚无运行记录。",
    pauseNote:
      "暂停排程会停止未来的计划启动。任何进行中的运行保留自己的生命周期并独立完成。",
    unavailableTitle: "此版本尚未投影例行任务",
    unavailableBody:
      "此界面尚未接入任何例行任务投影来源，因此不显示也不推断任何排程、运行或送达状态。",
    unavailableNote: "投影缺失时，绝不以示例时间、时区或运行状态填充。",
    execRunning: "运行中",
    execFinished: "已完成",
    execFailed: "已失败",
    execUnknown: "未知",
    deliveryDelivered: "已送达",
    deliveryPending: "待送达",
    deliveryFailed: "送达失败",
    deliveryUnknown: "未知",
    recentRunsLabel: "近期运行",
    rosterEmptyOption: "名册上没有可送达的成员",
  },
};

function executionLabel(
  state: RoutineRunExecutionState,
  t: typeof STRINGS.en,
): string {
  if (state === "running") return t.execRunning;
  if (state === "finished") return t.execFinished;
  if (state === "failed") return t.execFailed;
  return t.execUnknown;
}

function deliveryLabel(
  state: RoutineRunDeliveryState,
  t: typeof STRINGS.en,
): string {
  if (state === "delivered") return t.deliveryDelivered;
  if (state === "pending") return t.deliveryPending;
  if (state === "failed") return t.deliveryFailed;
  return t.deliveryUnknown;
}

/** Honest unknown row: value "Unknown"-class text plus its reason, styled
 *  secondary — never green, never a fabricated observation. */
function UnknownRow({
  label,
  reason,
}: {
  label: string;
  reason: string;
}) {
  return (
    <div className="mm-routines-fact">
      <dt>{label}</dt>
      <dd className="mm-routines-unknown">
        {reason}
      </dd>
    </div>
  );
}

export function RoutinesPanel({
  locale = "en",
  roster,
  routine,
  onBack,
  onPause,
  onResume,
  onOpenResult,
}: {
  locale?: "en" | "zh-CN";
  /** The real team roster — the only source of delivery-target options. */
  roster: TeamRoster;
  /** Null = no routine projection is wired; the panel says so. */
  routine: RoutineRecord | null;
  onBack?: () => void;
  /** Absent → the pause action renders disabled with a visible reason. */
  onPause?: () => void;
  /** Absent → the resume action renders disabled with a visible reason. */
  onResume?: () => void;
  onOpenResult?: () => void;
}) {
  const t = STRINGS[locale];
  const headingId = useId();
  const toggleReasonId = useId();
  const openResultReasonId = useId();

  // Controlled editor state, seeded from the record. There is no write path:
  // edits stay local and the footer says so (editingNote).
  const [instructionDraft, setInstructionDraft] = useState(
    routine?.instruction ?? "",
  );
  const [deliveryDraftId, setDeliveryDraftId] = useState(
    routine?.deliveryTargetId ?? "",
  );
  useEffect(() => {
    setInstructionDraft(routine?.instruction ?? "");
    setDeliveryDraftId(routine?.deliveryTargetId ?? "");
  }, [routine]);

  // Escape returns to the conversation workspace (onBack). Document-level so
  // it works regardless of which inner control holds focus; removed on unmount.
  useEffect(() => {
    if (!onBack) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onBack();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onBack]);

  if (routine === null) {
    return (
      <section className="mm-routines" aria-labelledby={headingId}>
        <h1 id={headingId} tabIndex={-1}>
          {t.heading}
        </h1>
        {onBack ? (
          <button type="button" className="mm-team-back" onClick={onBack}>
            {t.back}
          </button>
        ) : null}
        <div className="card mm-routines-unavailable">
          <p className="mm-eyebrow">{t.unavailableTitle}</p>
          <p>{t.unavailableBody}</p>
          <p className="muted">{t.unavailableNote}</p>
        </div>
      </section>
    );
  }

  const executionTarget = roster.bots.find(
    (bot) => bot.id === deliveryDraftId,
  );
  const pauseAction = routine.status === "scheduled";
  const toggleLabel = pauseAction ? t.pauseAction : t.resumeAction;
  const toggleHandler = pauseAction ? onPause : onResume;

  return (
    <section className="mm-routines" aria-labelledby={headingId}>
      <h1 id={headingId} tabIndex={-1}>
        {t.heading}
      </h1>
      <div className="mm-routines-grid">
        {/* Editor column (744). */}
        <div className="mm-routines-editor">
          {onBack ? (
            <button type="button" className="mm-team-back" onClick={onBack}>
              {t.back}
            </button>
          ) : null}
          <header className="mm-routines-head">
            <h2>{routine.name}</h2>
            <span
              className="mm-chip mm-routines-status"
              data-routine-status={routine.status}
            >
              {routine.status === "scheduled"
                ? t.chipScheduled
                : t.chipPaused}
            </span>
          </header>

          <div className="mm-routines-field">
            <label htmlFor="mm-routines-instruction">
              {t.instructionLabel}
            </label>
            <textarea
              id="mm-routines-instruction"
              className="mm-routines-instruction"
              value={instructionDraft}
              onChange={(event) => setInstructionDraft(event.target.value)}
            />
            <p className="mm-routines-hint">{t.instructionHint}</p>
          </div>

          <div className="card mm-routines-card">
            <h3>{t.scheduleHeading}</h3>
            <dl className="mm-routines-facts">
              <div className="mm-routines-fact">
                <dt>{t.repeatLabel}</dt>
                <dd>{routine.repeatRule}</dd>
              </div>
              <div className="mm-routines-fact">
                <dt>{t.timezoneLabel}</dt>
                <dd>{routine.timezone}</dd>
              </div>
            </dl>
          </div>

          <div className="mm-routines-field">
            <label htmlFor="mm-routines-delivery">{t.deliveryHeading}</label>
            <select
              id="mm-routines-delivery"
              className="mm-routines-select"
              value={deliveryDraftId}
              onChange={(event) => setDeliveryDraftId(event.target.value)}
            >
              <option value="">
                {roster.bots.length === 0
                  ? t.rosterEmptyOption
                  : t.deliveryUnsetOption}
              </option>
              {roster.bots.map((bot) => (
                <option key={bot.id} value={bot.id}>
                  {bot.displayName}
                </option>
              ))}
            </select>
            <p className="mm-routines-hint">{t.deliveryNote}</p>
          </div>

          <div className="card mm-routines-card">
            <h3>{t.runBehaviorHeading}</h3>
            <dl className="mm-routines-facts">
              {executionTarget ? (
                <div className="mm-routines-fact">
                  <dt>{t.executionLabel}</dt>
                  <dd>{executionTarget.displayName}</dd>
                </div>
              ) : (
                <UnknownRow
                  label={t.executionLabel}
                  reason={t.executionUnknown}
                />
              )}
              <div className="mm-routines-fact">
                <dt>{t.overlapLabel}</dt>
                <dd>{t.overlapValue}</dd>
              </div>
            </dl>
          </div>

          <footer className="mm-routines-footer">
            <button
              type="button"
              className="mm-routines-toggle"
              onClick={toggleHandler}
              disabled={!toggleHandler}
              aria-describedby={toggleHandler ? undefined : toggleReasonId}
            >
              {toggleLabel}
            </button>
            <p className="mm-routines-reason">{t.editingNote}</p>
          </footer>
          {!toggleHandler ? (
            <p className="mm-routines-reason" id={toggleReasonId}>
              {t.actionUnavailableReason}
            </p>
          ) : null}
        </div>

        {/* Right rail (344) — SCHEDULE & HISTORY. */}
        <aside className="mm-routines-rail" aria-label={t.railHeading}>
          <p className="mm-routines-rail-heading">{t.railHeading}</p>
          <div className="card mm-routines-rail-card">
            <dl className="mm-routines-facts">
              <UnknownRow
                label={t.nextOccurrenceLabel}
                reason={t.nextOccurrenceUnknown}
              />
            </dl>
          </div>
          <div className="card mm-routines-rail-card">
            <h3>{t.latestRunHeading}</h3>
            {routine.latestRun === null ? (
              <p className="mm-routines-unknown">{t.latestRunUnknown}</p>
            ) : (
              <>
                <dl className="mm-routines-facts">
                  <div className="mm-routines-fact">
                    <dt>{t.executionStateLabel}</dt>
                    <dd
                      className="mm-routines-state"
                      data-execution={routine.latestRun.executionState}
                    >
                      {executionLabel(routine.latestRun.executionState, t)}
                    </dd>
                  </div>
                  <div className="mm-routines-fact">
                    <dt>{t.deliveryStateLabel}</dt>
                    <dd
                      className="mm-routines-state"
                      data-delivery={routine.latestRun.deliveryState}
                    >
                      {deliveryLabel(routine.latestRun.deliveryState, t)}
                    </dd>
                  </div>
                  <div className="mm-routines-fact">
                    <dt>{t.latestRunHeading}</dt>
                    <dd>{routine.latestRun.finishedAt}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="mm-routines-open-result"
                  onClick={onOpenResult}
                  disabled={!onOpenResult}
                  aria-describedby={
                    onOpenResult ? undefined : openResultReasonId
                  }
                >
                  {t.openResult}
                </button>
                {!onOpenResult ? (
                  <p className="mm-routines-reason" id={openResultReasonId}>
                    {t.openResultUnavailable}
                  </p>
                ) : null}
              </>
            )}
          </div>
          <div className="card mm-routines-rail-card">
            <h3>{t.recentRunsHeading}</h3>
            {routine.recentRuns === null ? (
              <p className="mm-routines-unknown">{t.recentRunsUnknown}</p>
            ) : routine.recentRuns.length === 0 ? (
              <p className="mm-routines-unknown">{t.recentRunsEmpty}</p>
            ) : (
              <ul className="mm-routines-runs" aria-label={t.recentRunsLabel}>
                {routine.recentRuns.map((run, index) => (
                  <li key={`${run.finishedAt}-${index}`}>
                    {run.finishedAt} —{" "}
                    {executionLabel(run.executionState, t)} ·{" "}
                    {deliveryLabel(run.deliveryState, t)}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="mm-routines-pause-note">{t.pauseNote}</p>
        </aside>
      </div>
    </section>
  );
}
