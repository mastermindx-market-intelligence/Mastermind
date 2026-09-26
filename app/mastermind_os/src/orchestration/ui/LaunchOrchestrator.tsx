import { useEffect, useId, useRef, useState } from "react";

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

export interface LaunchOrchestratorProps {
  projects: readonly LaunchChoice[];
  profiles: readonly LaunchChoice[];
  submitting: boolean;
  unavailableReason?: string;
  error?: string;
  onSubmit: (intent: LaunchForm) => void;
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

  // Duplicate-submit latch: armed when onSubmit fires, released only by an
  // observed owner signal below. Never by a timer.
  const submitLatchRef = useRef(false);
  const prevOwnerRef = useRef({ submitting, error });

  useEffect(() => {
    const prev = prevOwnerRef.current;
    prevOwnerRef.current = { submitting, error };
    if (prev.submitting && !submitting) {
      // Owner reported a completed submit cycle.
      submitLatchRef.current = false;
    } else if (error !== prev.error) {
      // Owner reported a refused outcome.
      submitLatchRef.current = false;
    }
  });

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
    !submitting &&
    !projectStale &&
    !profileStale &&
    !selectedProjectChoice?.unavailableReason &&
    !selectedProfileChoice?.unavailableReason &&
    !goalBlank &&
    !goalTooLong;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || submitLatchRef.current) return;
    submitLatchRef.current = true;
    onSubmit({
      goal: draftGoal,
      projectRef: selectedProject,
      profileRef: selectedProfile,
    });
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
              disabled={submitting}
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
              disabled={submitting}
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
              disabled={submitting}
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
              {submitting ? "Launching…" : "Launch"}
            </button>
            <button type="button" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
