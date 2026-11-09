import { useEffect, useId, useRef, useState } from "react";
import { registerUnsavedNavigationHold } from "../../auth-navigation-guard";
import { LaunchRequestPreview, type LaunchRequestPreviewRead, type LaunchRequestPresentation } from "../../activation/LaunchRequestPreview";

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
  handoffText?: string;
  allowedWritePaths?: readonly string[];
  validation?: { readonly pytest_targets?: readonly string[]; readonly compileall_paths?: readonly string[]; readonly git_diff_check?: boolean };
}

/** App-owned user input only. These fields never retain a preview or authority. */
export interface LaunchDetailsDraft {
  acceptanceCriteria?: string;
  handoffText: string;
  writePathsText: string;
  testTargetsText: string;
  diffCheck: boolean;
  projectRef: string;
  profileRef: string;
}

const emptyLaunchDetails = (): LaunchDetailsDraft => ({
  acceptanceCriteria: "", handoffText: "", writePathsText: "", testTargetsText: "", diffCheck: true,
  projectRef: "", profileRef: "",
});

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
  /** A canonical project launch carries a handoff and explicitly requested code scope. */
  projectExecution?: boolean;
  projectFollowUp?: boolean;
  continuationMode?: "DURABLE" | "ATTENDED" | null;
  coordinatorModel?: string;
  executionScope?: { readonly repository: string; readonly commit: string } | null;
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
  initialDetails?: LaunchDetailsDraft | null;
  onDetailsChange?: (draft: LaunchDetailsDraft | null) => void;
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
const MAX_TAGGED_GOAL_BYTES = 4000;
const MAX_ACCEPTANCE_ITEMS = 6;
const ACCEPTANCE_MARKER = "[MASTERMIND_ACCEPTANCE_CRITERIA_V1:";

/** Preserve paragraphs using the line separator accepted by the Executive. */
function executiveGoal(goal: string): string | null {
  const normalized = goal.trim().replace(/\r\n?|\n/g, "\u2028").replace(/\t/g, " ");
  return /[\p{Cc}\p{Cs}]/u.test(normalized) ? null : normalized;
}

/** Requirements in the existing objective, never a product-acceptance verdict. */
export function composeAcceptanceGoal(
  goal: string, criteria: string, preserveUntaggedGoal = false,
): string | null {
  const lines = criteria.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  if (lines.length > MAX_ACCEPTANCE_ITEMS || lines.some(line =>
    line.length > 500 || /[\p{Cc}\p{Cs}\u2028\u2029]/u.test(line),
  )) return null;
  const normalizedGoal = executiveGoal(goal);
  if (!normalizedGoal || [normalizedGoal, ...lines].some(part => part.includes(ACCEPTANCE_MARKER))) return null;
  const composed = lines.length
    ? `${normalizedGoal} ${ACCEPTANCE_MARKER}${JSON.stringify(lines)}]`
    : preserveUntaggedGoal ? goal : normalizedGoal;
  // Untagged project objectives retain their exact source text and operation
  // identity. Ordinary Executive launches still use their normalized wire form.
  // The stricter wire contract belongs only to tagged objectives. Ordinary
  // Unicode goals retain their existing UI and current consumer limits.
  return utf8ByteLength(composed) <= (lines.length ? MAX_TAGGED_GOAL_BYTES : MAX_GOAL_BYTES)
    ? composed : null;
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
  presentation = "standard",
  projects: defaultProjects,
  profiles: defaultProfiles,
  frontierModels: defaultFrontierModels,
  workstreams,
  defaultWorkstream,
  workstreamRef,
  onWorkstreamChange,
  lockWorkstream = false,
  projectExecution = false,
  projectFollowUp = false,
  continuationMode,
  coordinatorModel,
  executionScope,
  submitting,
  blocked = false,
  unavailableReason,
  error,
  initialDraft = "",
  onDraftChange,
  initialDetails,
  onDetailsChange,
  previewRequest,
  onSubmit,
  onCancel,
}: LaunchOrchestratorProps) {
  const criteriaCopy = locale === "zh-CN" ? {
    label: "验收条件（可选，每行一项）",
    placeholder: "完成任务时，需要证明哪些结果？",
    error: "最多填写六项条件，每项不超过 500 个字符（部分符号计为两个）。目标与条件合计不得超过 4,000 个 UTF-8 字节；请移除控制字符和保留标记。",
    help: "写下完成任务时要验证的结果。填写条件并不代表验证已通过。",
  } : {
    label: "Acceptance criteria (optional, one per line)",
    placeholder: "What must be demonstrably true when this mission is finished?",
    error: "Use at most six criteria, up to 500 characters each (some symbols count twice). Goal and criteria together must fit 4,000 UTF-8 bytes. Remove control characters and reserved markers.",
    help: "Describe the results to verify when the work is complete. These requirements do not mean verification has passed.",
  };
  const formId = useId();
  const goalId = `${formId}-goal`;
  const acceptanceId = `${formId}-acceptance`;
  const goalInput = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (projectExecution) goalInput.current?.focus(); }, [projectExecution, projectFollowUp]);
  const workstreamId = `${formId}-workstream`;
  const projectId = `${formId}-project`;
  const profileId = `${formId}-profile`;
  const frontierId = `${formId}-frontier`;

  // Draft state — preserved across error and rerender
  const [draftGoal, setDraftGoal] = useState(initialDraft);
  const [draftWorkstream, setDraftWorkstream] = useState("");
  const [draftDetails, setDraftDetails] = useState<LaunchDetailsDraft>(() =>
    projectExecution && initialDetails ? { ...emptyLaunchDetails(), ...initialDetails }
      : { ...emptyLaunchDetails(), acceptanceCriteria: initialDetails?.acceptanceCriteria ?? "" });
  const draftDetailsRef = useRef(draftDetails);
  draftDetailsRef.current = draftDetails;
  const { acceptanceCriteria = "", handoffText, writePathsText, testTargetsText, diffCheck } = draftDetails;
  const updateDetails = (change: Partial<LaunchDetailsDraft>) => {
    const next = { ...draftDetailsRef.current, ...change };
    draftDetailsRef.current = next;
    setDraftDetails(next);
    setRequestPreview(null);
    onDetailsChange?.(projectExecution ? next : next.acceptanceCriteria
      ? { ...emptyLaunchDetails(), acceptanceCriteria: next.acceptanceCriteria } : null);
  };
  const lines = (text: string) => text.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  const selectedWorkstream = workstreamRef ?? (draftWorkstream || defaultWorkstream);
  const selectedBinding = workstreams?.find(choice => choice.ref === selectedWorkstream);
  // A missing enrollment is unavailable; it never falls back to default choices.
  const projects = workstreams ? selectedBinding?.projects ?? [] : defaultProjects;
  const profiles = workstreams ? selectedBinding?.profiles ?? [] : defaultProfiles;
  const frontierModels = workstreams ? selectedBinding?.frontierModels : defaultFrontierModels;
  const workstreamUnavailable = workstreams !== undefined &&
    (!selectedBinding || !!selectedBinding.unavailableReason);
  const [draftChoices, setDraftChoices] = useState({
    workstream: selectedWorkstream, project: draftDetails.projectRef,
    profile: draftDetails.profileRef, frontier: "",
  });
  const choices = draftChoices.workstream === selectedWorkstream ? draftChoices :
    { workstream: selectedWorkstream, project: "", profile: "", frontier: "" };
  const draftProject = choices.project;
  const draftProfile = choices.profile;
  const draftFrontier = choices.frontier;
  const setDraftProject = (project: string) => {
    setDraftChoices({ ...choices, project });
    if (projectExecution) updateDetails({ projectRef: project });
  };
  const setDraftProfile = (profile: string) => {
    setDraftChoices({ ...choices, profile });
    if (projectExecution) updateDetails({ profileRef: profile });
  };
  const setDraftFrontier = (frontier: string) => setDraftChoices({ ...choices, frontier });
  const [requestPreview, setRequestPreview] = useState<{
    read: LaunchRequestPreviewRead;
    formKey: string;
    presentationKey: string;
    presentation?: LaunchRequestPresentation;
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
    draftGoal.length > 0 || acceptanceCriteria.length > 0 || handoffText.length > 0 || writePathsText.length > 0 || testTargetsText.length > 0 ||
    !diffCheck || draftWorkstream.length > 0 || draftProject.length > 0 || draftProfile.length > 0 ||
    launchTokenRef.current !== null || submitting || launchInFlight
  ), [draftGoal, acceptanceCriteria, handoffText, writePathsText, testTargetsText, diffCheck, draftWorkstream, draftProject, draftProfile, submitting, launchInFlight]);

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
      // A follow-up does not submit or consume retained initial-launch criteria.
      const empty = { ...emptyLaunchDetails(), acceptanceCriteria:
        projectFollowUp ? draftDetailsRef.current.acceptanceCriteria ?? "" : "" };
      draftDetailsRef.current = empty;
      setDraftDetails(empty);
      onDraftChange?.("");
      if (projectExecution) {
        setDraftChoices({ workstream: selectedWorkstream, project: "", profile: "", frontier: "" });
      }
      onDetailsChange?.(empty.acceptanceCriteria ? empty : null);
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
  const goalCharacters = [...draftGoal].length;
  const goalCharacterLimit = projectExecution && goalCharacters > 4000;
  const goalTooLong = goalBytes > MAX_GOAL_BYTES || goalCharacterLimit;
  const codeScope = projectExecution && selectedProfile === "bounded_code_change";
  const writePaths = lines(writePathsText);
  const testTargets = lines(testTargetsText);
  const handoffTooLong = projectExecution && utf8ByteLength(handoffText) > 32768;
  const scopeMissing = codeScope && (!writePaths.length || (!testTargets.length && !diffCheck));
  const scopeTooLarge = codeScope && (writePaths.length > 16 || testTargets.length > 8);

  const goalBlank = draftGoal.trim().length === 0;
  const composedGoal = projectFollowUp ? draftGoal : composeAcceptanceGoal(draftGoal, acceptanceCriteria, projectExecution);
  const acceptanceInvalid = !projectFollowUp && acceptanceCriteria.trim().length > 0 && composedGoal === null;
  const goalInvalid = !projectFollowUp && !goalBlank && !goalTooLong && !acceptanceInvalid && composedGoal === null;

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
    !goalTooLong && composedGoal !== null && !handoffTooLong && !scopeMissing && !scopeTooLarge;

  const previewForm: LaunchForm = {
    goal: composedGoal ?? draftGoal, projectRef: selectedProject, profileRef: selectedProfile,
    ...(selectedWorkstream !== undefined ? { workstreamRef: selectedWorkstream } : {}),
    ...(frontierRequired ? { frontierModelAlias: selectedFrontier } : {}),
    ...(projectExecution ? { handoffText } : {}),
    ...(codeScope ? { allowedWritePaths: writePaths,
      validation: { pytest_targets: testTargets, git_diff_check: diffCheck } } : {}),
  };
  const previewFormKey = JSON.stringify(previewForm);
  const presentationKey=JSON.stringify({goal:draftGoal,criteria:acceptanceCriteria,followUp:projectFollowUp});
  const visiblePreview = canSubmit && requestPreview?.formKey === previewFormKey && requestPreview.presentationKey===presentationKey &&
    requestPreview.mapper === previewRequest && requestPreview.projects === projects &&
    requestPreview.profiles === profiles && requestPreview.frontierModels === frontierModels
      ? requestPreview.read : null;
  const previewCurrentRequest = () => {
    if (!canSubmit || !previewRequest || launchTokenRef.current !== null) return;
    let read: LaunchRequestPreviewRead;
    try { read = previewRequest(previewForm); }
    catch { read = { state: "UNAVAILABLE" }; }
    const presentation=read.state==="PREPARED"&&read.goal===previewForm.goal&&composedGoal!==null?
      Object.freeze({preview:read,wireGoal:previewForm.goal,goal:draftGoal,
        criteria:Object.freeze(projectFollowUp?[]:acceptanceCriteria.split(/\r?\n/).map(line=>line.trim()).filter(Boolean))}):undefined;
    setRequestPreview({ read, formKey: previewFormKey, presentationKey,presentation,mapper: previewRequest,
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
        previewForm,
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
    ? goalCharacterLimit
      ? (locale === "zh-CN" ? "目标最多为 4,000 个字符。" : "Keep the goal within 4,000 characters.")
      : (locale === "zh-CN" ? `目标超过 ${MAX_GOAL_BYTES} 字节的 UTF-8 上限。` : `Goal exceeds ${MAX_GOAL_BYTES} byte UTF-8 limit.`)
    : goalBlank
      ? "Goal is required."
      : goalInvalid
        ? (locale === "zh-CN" ? "请移除目标中的控制字符和保留标记。" : "Remove unsupported control characters or reserved markers from the goal.")
        : undefined;

  return (
    <section className={`card launch-orchestrator${presentation === "composer" ? " launch-orchestrator-composer" : ""}`}>
      <div className="section-title">
        <div>
          <h2>{projectFollowUp ? (locale === "zh-CN" ? "继续此项目" : "Continue this project")
            : selectedProfile === "native_research_only" ? (locale === "zh-CN" ? "启动单个原生任务" : "Launch one native task")
            : (locale === "zh-CN" ? "开始工作" : "Start work")}</h2>
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
              <span>{projectFollowUp ? (locale === "zh-CN" ? "下一步消息" : "Follow-up message") : (locale === "zh-CN" ? "目标" : "Goal")}</span>
              {goalTooLong && (
                <span className="field-error">
                  {" "}
                  ({goalCharacterLimit ? `${goalCharacters}/4,000 ${locale === "zh-CN" ? "字符" : "characters"}` : `${goalBytes}/${MAX_GOAL_BYTES} bytes`})
                </span>
              )}
            </label>
            <textarea
              id={goalId}
              ref={goalInput}
              value={draftGoal}
              onChange={(e) => { setRequestPreview(null); setDraftGoal(e.target.value); onDraftChange?.(e.target.value); }}
              rows={presentation === "composer" ? 2 : 4}
              placeholder={projectFollowUp ? (locale === "zh-CN" ? "描述希望团队接下来做什么…" : "What should the team do next?")
                : (locale === "zh-CN" ? "描述你希望完成的目标…" : "Describe the objective for this launch…")}
              disabled={launchPending}
              aria-describedby={goalTooLong ? `${goalId}-length` : goalInvalid ? `${goalId}-invalid` : undefined}
              aria-invalid={!!goalError}
            />
            {goalTooLong && (
              <p id={`${goalId}-length`} className="field-error">
                {goalError}
              </p>
            )}
          </div>

          {goalInvalid && <p id={`${goalId}-invalid`} className="field-error" role="alert">{goalError}</p>}

          {!projectFollowUp && <div className="form-field launch-acceptance">
            <label htmlFor={acceptanceId}>{criteriaCopy.label}</label>
            <textarea id={acceptanceId} value={acceptanceCriteria}
              onChange={event => updateDetails({ acceptanceCriteria: event.target.value })}
              rows={3} placeholder={criteriaCopy.placeholder} disabled={launchPending}
              aria-invalid={acceptanceInvalid}
              aria-describedby={`${acceptanceId}-help${acceptanceInvalid ? ` ${acceptanceId}-error` : ""}`} />
            {acceptanceInvalid && <p id={`${acceptanceId}-error`} className="field-error" role="alert">{criteriaCopy.error}</p>}
            <p id={`${acceptanceId}-help`} className="muted">{criteriaCopy.help}</p>
          </div>}

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

          {projectExecution ? <>
            {executionScope ? <dl className="project-execution-scope">
              <dt>{locale === "zh-CN" ? "执行仓库" : "Execution repository"}</dt>
              <dd>{executionScope.repository}</dd>
              <dt>{locale === "zh-CN" ? "起始修订" : "Starting revision"}</dt>
              <dd><code style={{overflowWrap:"anywhere"}}>{executionScope.commit}</code></dd>
            </dl> : null}
            <p className="muted" role="status">{continuationMode === "DURABLE"
              ? (locale === "zh-CN" ? "团队会在后台继续工作，关闭应用后仍可返回查看进展。" : "The team continues in the background. You can close the app and return to its progress.")
              : (locale === "zh-CN" ? "此主机仅支持在线执行。请保持应用连接；断开后需检查原始任务状态。" : "This host supports an attended run. Keep the app connected; if it disconnects, check the original operation.")}
              {coordinatorModel ? ` · ${coordinatorModel}` : ""}</p>
            <div className="form-field">
              <label htmlFor={`${formId}-handoff`}>{locale === "zh-CN" ? "交接说明（可选）" : "Handoff (optional)"}</label>
              <textarea id={`${formId}-handoff`} rows={5} value={handoffText}
                onChange={event => updateDetails({ handoffText: event.target.value })} disabled={launchPending}
                aria-invalid={handoffTooLong} aria-describedby={`${formId}-handoff-help`} />
              <p id={`${formId}-handoff-help`} className={handoffTooLong ? "field-error" : "muted"}>
                {handoffTooLong
                  ? (locale === "zh-CN" ? "交接说明超过 32 KB，请缩短后再启动。" : "The handoff exceeds 32 KB. Shorten it before launching.")
                  : (locale === "zh-CN" ? "补充已有进展、约束和验收条件。团队会同时读取当前项目计划与文件。"
                    : "Add prior progress, constraints and acceptance conditions. The team also receives the current project plan and files.")}
              </p>
            </div>
            {codeScope ? <fieldset disabled={launchPending} className="project-execution-scope">
              <legend>{locale === "zh-CN" ? "请求的代码修改范围" : "Requested code scope"}</legend>
              <div className="form-field">
                <label htmlFor={`${formId}-paths`}>{locale === "zh-CN" ? "可修改的路径" : "Paths to change"}</label>
                <textarea id={`${formId}-paths`} rows={3} value={writePathsText}
                  onChange={event => updateDetails({ writePathsText: event.target.value })}
                  aria-describedby={`${formId}-paths-help`} />
                <p id={`${formId}-paths-help`} className="muted">{locale === "zh-CN"
                  ? "每行一个仓库相对路径，最多 16 个。启动前会验证实际权限。"
                  : "One repository-relative path per line, up to 16. Actual permissions are checked before work starts."}</p>
              </div>
              <div className="form-field">
                <label htmlFor={`${formId}-tests`}>{locale === "zh-CN" ? "Pytest 测试目标（可选）" : "Pytest targets (optional)"}</label>
                <textarea id={`${formId}-tests`} rows={2} value={testTargetsText}
                  onChange={event => updateDetails({ testTargetsText: event.target.value })} />
              </div>
              <label><input type="checkbox" checked={diffCheck} onChange={event => updateDetails({ diffCheck: event.target.checked })} />
                {locale === "zh-CN" ? "检查 diff 中的空白错误" : "Check the diff for whitespace errors"}</label>
              {(scopeMissing || scopeTooLarge) ? <p className="field-error">{locale === "zh-CN"
                ? "填写 1–16 个路径，并选择至少一项验证（最多 8 个测试目标）。"
                : "Provide 1–16 paths and at least one validation check, with up to 8 test targets."}</p> : null}
            </fieldset> : null}
          </> : null}

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
          {visiblePreview ? <LaunchRequestPreview preview={visiblePreview} presentation={requestPreview?.presentation}
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
