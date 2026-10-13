import { useId, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LaunchChoice {
  ref: string;
  label: string;
  unavailableReason?: string;
}

export interface LaunchForm {
  goal: string;
  projectRef: string;
  profileRef: string;
}

/** Explicit terminal outcome of one dispatched launch. */
export type LaunchOutcome = { status: "accepted" } | { status: "refused" };

/**
 * Correlated completion handle for exactly one dispatched launch.
 *
 * Host contract:
 * - Call `onComplete` exactly once with the terminal outcome.
 * - Only an object whose `status` is exactly `"accepted"` or `"refused"` is
 *   terminal. The outcome is validated before any latch, pending, or draft
 *   mutation. Missing, null, array, unknown, non-string, throwing-getter, or
 *   proxy values stay visibly in flight; the same handle remains usable for a
 *   later valid reconciliation and does not throw.
 * - `"accepted"`: the launch succeeded. The guard releases and the goal draft
 *   is cleared, so a still-mounted parent cannot accidentally relaunch it.
 * - `"refused"`: the launch was rejected. The guard releases and the draft is
 *   preserved for an explicit retry. Surface the reason via the `error` prop.
 * - Never calling `onComplete` — a void/lost host — or throwing from the
 *   callback leaves the launch visibly in flight and does NOT authorize a
 *   retry. There is no timer-based or inference-based unlock.
 * - The handle is correlated to its own dispatch: it stays valid across
 *   rerenders (an owner may store it and reconcile the same pending action
 *   later without a remount), and a stale handle — superseded by a later
 *   dispatch or completion — is a no-op.
 *
 * `submitting` and `error` are display/owner-state inputs only. Neither a
 * pending edge nor a changed error string ever releases the guard.
 */
export type LaunchCompletion = (outcome: LaunchOutcome) => void;

export interface LaunchOrchestratorProps {
  locale?: "en" | "zh-CN";
  projects: readonly LaunchChoice[];
  profiles: readonly LaunchChoice[];
  /** Owner-side pending signal. Disables the form; never releases the guard. */
  submitting: boolean;
  /** A retained operation or unreadable store prevents a new submission. */
  blocked?: boolean;
  unavailableReason?: string;
  error?: string;
  onSubmit: (intent: LaunchForm, onComplete: LaunchCompletion) => void;
  onCancel: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Conservative UI ceiling for user-supplied goal text */
// The Executive launch adapter limits objective to 4,000 characters.
// Use a conservative UTF-8 byte ceiling so the visible UI never promises a
// launch the existing command adapter will reject.
const MAX_GOAL_BYTES = 4000;
const MAX_ACCEPTANCE_ITEMS = 6;
// Versioned human-readable section in the existing objective. This is a
// requirement description, not signed proof or a product-acceptance verdict.
const ACCEPTANCE_OPEN = " [MASTERMIND_ACCEPTANCE_CRITERIA_V1:";
const ACCEPTANCE_CLOSE = "]";
/**
 * Executive rejects Cc/Cs characters, including CR/LF, in its 4000-char
 * objective. Preserve paragraph boundaries as U+2028 (Zl) and reject invalid
 * controls/surrogates. Do not loosen or duplicate the Executive normalizer.
 */
function executiveGoal(goal: string): string | null {
  const normalized = goal.trim().replace(/\r\n?|\n/g, "\u2028").replace(/\t/g, " ");
  return /[\p{Cc}\p{Cs}]/u.test(normalized) ? null : normalized;
}
/** A versioned requirements suffix, not signed proof or a product verdict. */
export function composeAcceptanceGoal(goal: string, criteria: string): string | null {
  const lines = criteria.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length > MAX_ACCEPTANCE_ITEMS || lines.some((line) =>
    line.length > 500 || /[\p{Cc}\p{Cs}\u2028\u2029]/u.test(line),
  )) return null;
  const normalizedGoal = executiveGoal(goal);
  if (normalizedGoal === null) return null;
  // The marker is reserved: a second occurrence makes the source ambiguous.
  if ([normalizedGoal, ...lines].some((part) =>
    part.includes("[MASTERMIND_ACCEPTANCE_CRITERIA_V1:"),
  )) return null;
  const composed = lines.length
    ? `${normalizedGoal}${ACCEPTANCE_OPEN}${JSON.stringify(lines)}${ACCEPTANCE_CLOSE}`
    : normalizedGoal;
  return utf8ByteLength(composed) <= MAX_GOAL_BYTES ? composed : null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns the byte length of a UTF-8 string */
function utf8ByteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

/**
 * Snapshot a terminal status from a completion argument.
 * Reads `status` once; a throw, missing value, array, or any other shape is
 * not terminal. Extra own fields are ignored when status is exact.
 */
function readTerminalStatus(outcome: unknown): "accepted" | "refused" | null {
  try {
    if (typeof outcome !== "object" || outcome === null || Array.isArray(outcome)) {
      return null;
    }
    const status = Reflect.get(outcome, "status");
    if (status === "accepted" || status === "refused") return status;
    return null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LaunchOrchestrator({
  locale = "en",
  projects,
  profiles,
  submitting,
  blocked = false,
  unavailableReason,
  error,
  onSubmit,
  onCancel,
}: LaunchOrchestratorProps) {
  const criteriaCopy = locale === "zh-CN" ? {
    label: "验收条件（可选，每行一项）",
    placeholder: "完成这项任务时，哪些结果必须有证据证明？",
    error: "最多填写六项条件，每项不超过 500 个字符。目标和条件合计不得超过 4,000 个 UTF-8 字节。",
    help: "验收条件会随任务目标提交，用于后续验证；填写条件不代表验证已通过。",
  } : {
    label: "Acceptance criteria (optional, one per line)",
    placeholder: "What must be demonstrably true when this mission is finished?",
    error: "Use at most six criteria (500 characters each). Goal and criteria together must fit 4,000 UTF-8 bytes.",
    help: "Criteria travel with the existing mission goal. They are requirements for validation, not a claim that checks have passed.",
  };
  const formId = useId();
  const goalId = `${formId}-goal`;
  const projectId = `${formId}-project`;
  const profileId = `${formId}-profile`;
  const acceptanceId = `${formId}-acceptance`;

  // Draft state — preserved across error and rerender
  const [draftGoal, setDraftGoal] = useState("");
  const [draftAcceptance, setDraftAcceptance] = useState("");
  const [draftProject, setDraftProject] = useState("");
  const [draftProfile, setDraftProfile] = useState("");

  // In-flight launch owned by this component: armed synchronously when
  // onSubmit is dispatched, resolved only by its correlated completion.
  const [launchInFlight, setLaunchInFlight] = useState(false);
  // Synchronous duplicate latch and correlation token. `null` means idle; a
  // number is the token of the dispatch currently in flight. The completion
  // closure captures that token, so only the matching dispatch can release
  // the guard — a stale or duplicated completion is a no-op.
  const launchTokenRef = useRef<number | null>(null);
  const tokenSeqRef = useRef(0);

  const launchPending = submitting || launchInFlight;

  const completeLaunch = (token: number, outcome: unknown) => {
    const status = readTerminalStatus(outcome);
    if (status === null) return;
    if (launchTokenRef.current !== token) return;
    launchTokenRef.current = null;
    setLaunchInFlight(false);
    if (status === "accepted") {
      // Success consumes the goal so the same intent cannot be launched twice
      // by a parent that stays mounted. A refusal keeps the draft.
      setDraftGoal("");
      setDraftAcceptance("");
    }
  };

  // Default selection — first eligible choice, falling back to the first item
  // so an all-unavailable list still renders its options (and stays blocked).
  const firstEligibleProject = projects.find((p) => !p.unavailableReason);
  const firstEligibleProfile = profiles.find((p) => !p.unavailableReason);
  const selectedProject = draftProject || firstEligibleProject?.ref || projects[0]?.ref || "";
  const selectedProfile = draftProfile || firstEligibleProfile?.ref || profiles[0]?.ref || "";

  const selectedProjectChoice = projects.find((p) => p.ref === selectedProject);
  const selectedProfileChoice = profiles.find((p) => p.ref === selectedProfile);
  // A selection missing from the current choices is stale (removed upstream):
  // it must stay disabled rather than submit a ref nobody can resolve.
  const projectStale = !selectedProjectChoice;
  const profileStale = !selectedProfileChoice;
  const projectError = projectStale
    ? selectedProject
      ? "Your previous project is no longer available. Select an available project to continue."
      : "No projects are currently available."
    : selectedProjectChoice.unavailableReason;
  const profileError = profileStale
    ? selectedProfile
      ? "Your previous profile is no longer available. Select an available profile to continue."
      : "No profiles are currently available."
    : selectedProfileChoice.unavailableReason;

  const goalBytes = utf8ByteLength(draftGoal);
  const composedGoal = composeAcceptanceGoal(draftGoal, draftAcceptance);
  const acceptanceInvalid = draftAcceptance.trim().length > 0 && composedGoal === null;
  const goalTooLong = goalBytes > MAX_GOAL_BYTES;
  const goalInvalid = !acceptanceInvalid && !goalTooLong && composedGoal === null;
  const goalBlank = draftGoal.trim().length === 0;

  const canSubmit =
    !blocked &&
    !unavailableReason &&
    !launchPending &&
    !projectStale &&
    !profileStale &&
    !selectedProjectChoice?.unavailableReason &&
    !selectedProfileChoice?.unavailableReason &&
    !goalBlank &&
    !goalTooLong &&
    composedGoal !== null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || launchTokenRef.current !== null) return;
    const token = ++tokenSeqRef.current;
    launchTokenRef.current = token;
    setLaunchInFlight(true);
    try {
      onSubmit(
        {
          goal: composedGoal ?? draftGoal,
          projectRef: selectedProject,
          profileRef: selectedProfile,
        },
        (outcome) => {
          try {
            completeLaunch(token, outcome);
          } catch {
            // A throw while reading or applying the outcome is not terminal:
            // the launch stays in flight and the handle remains usable.
          }
        },
      );
    } catch {
      // A thrown host callback is not an accepted or refused outcome: the
      // launch stays visibly in flight and does not authorize a retry.
    }
  };

  const goalError = goalTooLong
    ? `Goal exceeds ${MAX_GOAL_BYTES} byte UTF-8 limit.`
    : goalBlank
      ? "Goal is required."
      : goalInvalid
        ? "Goal contains an unsupported control or a reserved marker, or exceeds the serialized limit."
        : undefined;

  return (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>Launch Orchestrator</h2>
        </div>
      </div>

      {unavailableReason ? (
        <div className="empty">
          <p>{unavailableReason}</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          {/* Goal textarea */}
          <div className="form-field">
            <label htmlFor={goalId}>
              <span>Goal</span>
              {goalTooLong && (
                <span className="field-error">
                  {" "}
                  ({goalBytes}/{MAX_GOAL_BYTES} bytes)
                </span>
              )}
            </label>
            <textarea
              id={goalId}
              value={draftGoal}
              onChange={(e) => setDraftGoal(e.target.value)}
              rows={4}
              placeholder="Describe the objective for this launch…"
              disabled={launchPending}
              aria-describedby={goalTooLong ? `${goalId}-length` : goalInvalid ? `${goalId}-invalid` : undefined}
              aria-invalid={!!goalError}
            />
            {goalTooLong && (
              <p id={`${goalId}-length`} className="field-error">
                Goal exceeds the {MAX_GOAL_BYTES} byte UTF-8 ceiling.
              </p>
            )}
            {goalInvalid && (
              <p id={`${goalId}-invalid`} className="field-error" role="alert">
                Remove unsupported control characters or reserved markers. The original objective must fit 4,000 UTF-8 bytes.
              </p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor={acceptanceId}>{criteriaCopy.label}</label>
            <textarea
              id={acceptanceId}
              value={draftAcceptance}
              onChange={(e) => setDraftAcceptance(e.target.value)}
              rows={3}
              placeholder={criteriaCopy.placeholder}
              disabled={launchPending}
              aria-invalid={acceptanceInvalid}
              aria-describedby={acceptanceInvalid ? `${acceptanceId}-error` : undefined}
            />
            {acceptanceInvalid && (
              <p id={`${acceptanceId}-error`} className="field-error" role="alert">
                {criteriaCopy.error}
              </p>
            )}
            <p className="muted">{criteriaCopy.help}</p>
          </div>

          {/* Project select */}
          <div className="form-field">
            <label htmlFor={projectId}>Project</label>
            <select
              id={projectId}
              value={selectedProject}
              onChange={(e) => setDraftProject(e.target.value)}
              disabled={launchPending}
              aria-invalid={!!projectError}
              aria-describedby={projectError ? `${projectId}-error` : undefined}
            >
              {projectStale && (
                <option value={selectedProject} disabled>
                  {selectedProject ? "Previous project — unavailable" : "No projects available"}
                </option>
              )}
              {projects.map((p) => (
                <option key={p.ref} value={p.ref} disabled={!!p.unavailableReason}>
                  {p.unavailableReason ? `${p.label} — ${p.unavailableReason}` : p.label}
                </option>
              ))}
            </select>
            {projectError && (
              <p id={`${projectId}-error`} className="field-error" role="alert">
                {projectError}
              </p>
            )}
          </div>

          {/* Profile select */}
          <div className="form-field">
            <label htmlFor={profileId}>Profile</label>
            <select
              id={profileId}
              value={selectedProfile}
              onChange={(e) => setDraftProfile(e.target.value)}
              disabled={launchPending}
              aria-invalid={!!profileError}
              aria-describedby={profileError ? `${profileId}-error` : undefined}
            >
              {profileStale && (
                <option value={selectedProfile} disabled>
                  {selectedProfile ? "Previous profile — unavailable" : "No profiles available"}
                </option>
              )}
              {profiles.map((p) => (
                <option key={p.ref} value={p.ref} disabled={!!p.unavailableReason}>
                  {p.unavailableReason ? `${p.label} — ${p.unavailableReason}` : p.label}
                </option>
              ))}
            </select>
            {profileError && (
              <p id={`${profileId}-error`} className="field-error" role="alert">
                {profileError}
              </p>
            )}
          </div>

          {/* Error message */}
          {error && (
            <div
              id={`${formId}-error`}
              className="form-error"
              role="alert"
              // tabIndex=-1 so an integrator can focus this element
              tabIndex={-1}
            >
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="form-actions">
            <button type="submit" disabled={!canSubmit} className="primary">
              {launchPending ? "Launching…" : "Launch"}
            </button>
            <button type="button" onClick={onCancel} disabled={launchPending}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
