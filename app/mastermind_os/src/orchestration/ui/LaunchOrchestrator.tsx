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
  projects: readonly LaunchChoice[];
  profiles: readonly LaunchChoice[];
  /** Owner-side pending signal. Disables the form; never releases the guard. */
  submitting: boolean;
  unavailableReason?: string;
  error?: string;
  onSubmit: (intent: LaunchForm, onComplete: LaunchCompletion) => void;
  onCancel: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Conservative UI ceiling for user-supplied goal text */
const MAX_GOAL_BYTES = 16384;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns the byte length of a UTF-8 string */
function utf8ByteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LaunchOrchestrator({
  projects,
  profiles,
  submitting,
  unavailableReason,
  error,
  onSubmit,
  onCancel,
}: LaunchOrchestratorProps) {
  const formId = useId();
  const goalId = `${formId}-goal`;
  const projectId = `${formId}-project`;
  const profileId = `${formId}-profile`;

  // Draft state — preserved across error and rerender
  const [draftGoal, setDraftGoal] = useState("");
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

  const completeLaunch = (token: number, outcome: LaunchOutcome) => {
    if (launchTokenRef.current !== token) return;
    launchTokenRef.current = null;
    setLaunchInFlight(false);
    if (outcome.status === "accepted") {
      // Success consumes the goal so the same intent cannot be launched twice
      // by a parent that stays mounted. A refusal keeps the draft.
      setDraftGoal("");
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

  const goalBytes = utf8ByteLength(draftGoal);
  const goalTooLong = goalBytes > MAX_GOAL_BYTES;
  const goalBlank = draftGoal.trim().length === 0;

  const canSubmit =
    !unavailableReason &&
    !launchPending &&
    !projectStale &&
    !profileStale &&
    !selectedProjectChoice?.unavailableReason &&
    !selectedProfileChoice?.unavailableReason &&
    !goalBlank &&
    !goalTooLong;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || launchTokenRef.current !== null) return;
    const token = ++tokenSeqRef.current;
    launchTokenRef.current = token;
    setLaunchInFlight(true);
    try {
      onSubmit(
        {
          goal: draftGoal,
          projectRef: selectedProject,
          profileRef: selectedProfile,
        },
        (outcome) => completeLaunch(token, outcome),
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
              aria-describedby={goalTooLong ? `${goalId}-length` : undefined}
              aria-invalid={!!goalError}
            />
            {goalTooLong && (
              <p id={`${goalId}-length`} className="field-error">
                Goal exceeds the {MAX_GOAL_BYTES} byte UTF-8 ceiling.
              </p>
            )}
          </div>

          {/* Project select */}
          <div className="form-field">
            <label htmlFor={projectId}>Project</label>
            <select
              id={projectId}
              value={selectedProject}
              onChange={(e) => setDraftProject(e.target.value)}
              disabled={launchPending}
            >
              {projects.map((p) => (
                <option key={p.ref} value={p.ref} disabled={!!p.unavailableReason}>
                  {p.unavailableReason ? `${p.label} — ${p.unavailableReason}` : p.label}
                </option>
              ))}
            </select>
            {selectedProjectChoice?.unavailableReason && (
              <p className="field-error" role="alert">
                {selectedProjectChoice.unavailableReason}
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
            >
              {profiles.map((p) => (
                <option key={p.ref} value={p.ref} disabled={!!p.unavailableReason}>
                  {p.unavailableReason ? `${p.label} — ${p.unavailableReason}` : p.label}
                </option>
              ))}
            </select>
            {selectedProfileChoice?.unavailableReason && (
              <p className="field-error" role="alert">
                {selectedProfileChoice.unavailableReason}
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
