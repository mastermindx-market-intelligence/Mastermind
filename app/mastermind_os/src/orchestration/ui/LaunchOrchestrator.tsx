import { useEffect, useId, useRef, useState } from "react";
import { registerUnsavedNavigationHold } from "../../auth-navigation-guard";
import { LaunchRequestPreview, type LaunchRequestPreviewRead } from "../../activation/LaunchRequestPreview";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LaunchChoice {
  ref: string;
  label: string;
  unavailableReason?: string;
}

export interface LaunchWorkstreamChoice extends LaunchChoice {
  readonly projects: readonly LaunchChoice[];
  readonly profiles: readonly LaunchChoice[];
  readonly frontierModels?: readonly LaunchChoice[];
}

export interface LaunchForm {
  workstreamRef?: string;
  goal: string;
  projectRef: string;
  profileRef: string;
  frontierModelAlias?: string;
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
  /** Presentation only; all original selection and submission guards remain shared. */
  presentation?: "standard" | "composer";
  workstreams?: readonly LaunchWorkstreamChoice[];
  defaultWorkstream?: string;
  workstreamRef?: string;
  onWorkstreamChange?: (ref: string) => void;
  lockWorkstream?: boolean;
  projects: readonly LaunchChoice[];
  profiles: readonly LaunchChoice[];
  frontierModels?: readonly LaunchChoice[];
  /** Owner-side pending signal. Disables the form; never releases the guard. */
  submitting: boolean;
  /** A retained operation or unreadable store prevents a new submission. */
  blocked?: boolean;
  unavailableReason?: string;
  error?: string;
  /** Optional App-owned presentation draft, never a credential or host state. */
  initialDraft?: string;
  onDraftChange?: (text: string) => void;
  /** Explicit, effect-free owner mapper. Preview never prepares or submits an operation. */
  previewRequest?: (intent: LaunchForm) => LaunchRequestPreviewRead;
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
  presentation = "standard",
  projects: defaultProjects,
  profiles: defaultProfiles,
  frontierModels: defaultFrontierModels,
  workstreams,
  defaultWorkstream,
  workstreamRef,
  onWorkstreamChange,
  lockWorkstream = false,
  submitting,
  blocked = false,
  unavailableReason,
  error,
  initialDraft = "",
  onDraftChange,
  previewRequest,
  onSubmit,
  onCancel,
}: LaunchOrchestratorProps) {
  const formId = useId();
  const goalId = `${formId}-goal`;
  const workstreamId = `${formId}-workstream`;
  const projectId = `${formId}-project`;
  const profileId = `${formId}-profile`;
  const frontierId = `${formId}-frontier`;

  // Draft state — preserved across error and rerender
  const [draftGoal, setDraftGoal] = useState(initialDraft);
  const [draftWorkstream, setDraftWorkstream] = useState("");
  const selectedWorkstream = workstreamRef ?? (draftWorkstream || defaultWorkstream);
  const selectedBinding = workstreams?.find(choice => choice.ref === selectedWorkstream);
  // A missing enrollment is unavailable; it never falls back to default choices.
  const projects = workstreams ? selectedBinding?.projects ?? [] : defaultProjects;
  const profiles = workstreams ? selectedBinding?.profiles ?? [] : defaultProfiles;
  const frontierModels = workstreams ? selectedBinding?.frontierModels : defaultFrontierModels;
  const workstreamUnavailable = workstreams !== undefined &&
    (!selectedBinding || !!selectedBinding.unavailableReason);
  const [draftChoices, setDraftChoices] = useState({
    workstream: selectedWorkstream, project: "", profile: "", frontier: "",
  });
  const choices = draftChoices.workstream === selectedWorkstream ? draftChoices :
    { workstream: selectedWorkstream, project: "", profile: "", frontier: "" };
  const draftProject = choices.project;
  const draftProfile = choices.profile;
  const draftFrontier = choices.frontier;
  const setDraftProject = (project: string) => setDraftChoices({ ...choices, project });
  const setDraftProfile = (profile: string) => setDraftChoices({ ...choices, profile });
  const setDraftFrontier = (frontier: string) => setDraftChoices({ ...choices, frontier });
  const [requestPreview, setRequestPreview] = useState<{
    read: LaunchRequestPreviewRead;
    formKey: string;
    mapper: NonNullable<LaunchOrchestratorProps["previewRequest"]>;
    projects: readonly LaunchChoice[];
    profiles: readonly LaunchChoice[];
    frontierModels: readonly LaunchChoice[] | undefined;
  } | null>(null);

  // In-flight launch owned by this component: armed synchronously when
  // onSubmit is dispatched, resolved only by its correlated completion.
  const [launchInFlight, setLaunchInFlight] = useState(false);
  // Synchronous duplicate latch and correlation token. `null` means idle; a
  // number is the token of the dispatch currently in flight. The completion
  // closure captures that token, so only the matching dispatch can release
  // the guard — a stale or duplicated completion is a no-op.
  const launchTokenRef = useRef<number | null>(null);
  const tokenSeqRef = useRef(0);

  // Draft goals and exact pending-command handles must survive automatic
  // identity renewal. No form content enters browser credential storage.
  useEffect(() => registerUnsavedNavigationHold(() =>
    draftGoal.length > 0 || draftWorkstream.length > 0 || draftProject.length > 0 || draftProfile.length > 0 ||
    launchTokenRef.current !== null || submitting || launchInFlight
  ), [draftGoal, draftWorkstream, draftProject, draftProfile, submitting, launchInFlight]);

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
      onDraftChange?.("");
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

  const frontierRequired = selectedProfile !== "native_research_only" &&
    (frontierModels !== undefined || draftFrontier !== "");
  const selectedFrontier = draftFrontier ||
    frontierModels?.find((choice) => !choice.unavailableReason)?.ref ||
    frontierModels?.[0]?.ref || "";
  const frontierChoice = frontierModels?.find((choice) => choice.ref === selectedFrontier);
  const frontierError = frontierRequired
    ? (!frontierChoice ? (locale === "zh-CN" ? "请选择可用的 CEO 以继续。" : "Select an available CEO choice to continue.") : frontierChoice.unavailableReason)
    : undefined;

  const goalBytes = utf8ByteLength(draftGoal);
  const goalTooLong = goalBytes > MAX_GOAL_BYTES;
  const goalBlank = draftGoal.trim().length === 0;

  const canSubmit =
    !blocked &&
    !unavailableReason &&
    !workstreamUnavailable &&
    !launchPending &&
    !projectStale &&
    !profileStale &&
    !frontierError &&
    !selectedProjectChoice?.unavailableReason &&
    !selectedProfileChoice?.unavailableReason &&
    !goalBlank &&
    !goalTooLong;

  const previewForm: LaunchForm = {
    goal: draftGoal, projectRef: selectedProject, profileRef: selectedProfile,
    ...(selectedWorkstream !== undefined ? { workstreamRef: selectedWorkstream } : {}),
    ...(frontierRequired ? { frontierModelAlias: selectedFrontier } : {}),
  };
  const previewFormKey = JSON.stringify(previewForm);
  const visiblePreview = canSubmit && requestPreview?.formKey === previewFormKey &&
    requestPreview.mapper === previewRequest && requestPreview.projects === projects &&
    requestPreview.profiles === profiles && requestPreview.frontierModels === frontierModels
      ? requestPreview.read : null;
  const previewCurrentRequest = () => {
    if (!canSubmit || !previewRequest || launchTokenRef.current !== null) return;
    let read: LaunchRequestPreviewRead;
    try { read = previewRequest(previewForm); }
    catch { read = { state: "UNAVAILABLE" }; }
    setRequestPreview({ read, formKey: previewFormKey, mapper: previewRequest,
      projects, profiles, frontierModels });
  };

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
          ...(selectedWorkstream !== undefined ? { workstreamRef: selectedWorkstream } : {}),
          ...(frontierRequired ? { frontierModelAlias: selectedFrontier } : {}),
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
      : undefined;

  return (
    <section className={`card launch-orchestrator${presentation === "composer" ? " launch-orchestrator-composer" : ""}`}>
      <div className="section-title">
        <div>
          <h2>{selectedProfile === "native_research_only" ? (locale === "zh-CN" ? "启动单个原生任务" : "Launch one native task") : (locale === "zh-CN" ? "开始工作" : "Start work")}</h2>
        </div>
      </div>

      {unavailableReason ? (
        <div className="empty">
          <p>{unavailableReason}</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          {/* Goal textarea */}
          <div className="form-field launch-goal">
            <label htmlFor={goalId}>
              <span>{locale === "zh-CN" ? "目标" : "Goal"}</span>
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
              onChange={(e) => { setRequestPreview(null); setDraftGoal(e.target.value); onDraftChange?.(e.target.value); }}
              rows={presentation === "composer" ? 2 : 4}
              placeholder={locale === "zh-CN" ? "描述你希望完成的目标…" : "Describe the objective for this launch…"}
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

          {workstreams !== undefined && <div className="form-field">
            <label htmlFor={workstreamId}>{locale === "zh-CN" ? "工作流" : "Workstream"}</label>
            <select id={workstreamId} value={selectedWorkstream ?? ""}
              disabled={launchPending || lockWorkstream}
              aria-invalid={workstreamUnavailable}
              aria-describedby={workstreamUnavailable ? `${workstreamId}-error` : undefined}
              onChange={event => {
                const ref = event.target.value;
                setRequestPreview(null);
                setDraftWorkstream(ref);
                setDraftChoices({ workstream: ref, project: "", profile: "", frontier: "" });
                onWorkstreamChange?.(ref);
              }}>
              {!selectedBinding && <option value={selectedWorkstream ?? ""} disabled>
                {locale === "zh-CN" ? "工作流不可用" : "Workstream unavailable"}
              </option>}
              {workstreams.map(choice => <option key={choice.ref} value={choice.ref}
                disabled={!!choice.unavailableReason}>{choice.label}</option>)}
            </select>
            {workstreamUnavailable && <p id={`${workstreamId}-error`} className="field-error" role="alert">
              {locale === "zh-CN" ? "此工作流未登记。请选择可用的工作流。" : "This workstream is not enrolled. Select an available workstream."}
            </p>}
          </div>}

          {/* Project select */}
          <div className="form-field">
            <label htmlFor={projectId}>{locale === "zh-CN" ? "项目" : "Project"}</label>
            <select
              id={projectId}
              value={selectedProject}
              onChange={(e) => { setRequestPreview(null); setDraftProject(e.target.value); }}
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
            <label htmlFor={profileId}>{locale === "zh-CN" ? "执行方式" : "Profile"}</label>
            <select
              id={profileId}
              value={selectedProfile}
              onChange={(e) => { setRequestPreview(null); setDraftProfile(e.target.value); }}
              disabled={launchPending}
              aria-invalid={!!profileError}
              aria-describedby={[profileError ? `${profileId}-error` : "",selectedProfile === "native_research_only" ? `${profileId}-meaning` : ""].filter(Boolean).join(" ") || undefined}
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
            {selectedProfile === "native_research_only" ? <p id={`${profileId}-meaning`} className="muted">
              {locale === "zh-CN" ? "直接运行一个只读任务，不创建规划或子任务。" : "Run one read-only task directly, without planning or child tasks."}
            </p> : null}
          </div>

          {frontierRequired && (
            <div className="form-field">
              <label htmlFor={frontierId}>{locale === "zh-CN" ? "指定 CEO" : "Requested CEO"}</label>
              <select
                id={frontierId}
                value={selectedFrontier}
                onChange={(e) => { setRequestPreview(null); setDraftFrontier(e.target.value); }}
                disabled={launchPending}
                aria-invalid={!!frontierError}
                aria-describedby={frontierError ? `${frontierId}-error` : `${frontierId}-help`}
              >
                {!frontierChoice && <option value={selectedFrontier} disabled>{locale === "zh-CN" ? "CEO 选项不可用" : "CEO choice unavailable"}</option>}
                {frontierModels?.map((choice) => (
                  <option key={choice.ref} value={choice.ref} disabled={!!choice.unavailableReason}>
                    {choice.unavailableReason ? `${choice.label} — ${choice.unavailableReason}` : choice.label}
                  </option>
                ))}
              </select>
              <p id={`${frontierId}-help`}>{locale === "zh-CN" ? "记录此项目指定的 CEO。" : "Records your requested CEO for this project."}</p>
              {frontierError && <p id={`${frontierId}-error`} className="field-error" role="alert">{frontierError}</p>}
            </div>
          )}

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
          {visiblePreview ? <LaunchRequestPreview preview={visiblePreview}
            projects={projects} profiles={profiles} frontierModels={frontierModels} locale={locale} /> : null}
          <div className="form-actions">
            {previewRequest ? <button type="button" disabled={!canSubmit}
              onClick={previewCurrentRequest}>
              {locale === "zh-CN" ? "预览请求范围" : "Preview requested scope"}
            </button> : null}
            <button type="submit" disabled={!canSubmit} className="primary">
              {launchPending ? (locale === "zh-CN" ? "正在启动…" : "Launching…") : (locale === "zh-CN" ? "启动" : "Launch")}
            </button>
            <button type="button" onClick={onCancel} disabled={launchPending}>
              {locale === "zh-CN" ? "取消" : "Cancel"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
