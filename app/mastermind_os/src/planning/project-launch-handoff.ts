import {
  officeLaunchWorkstreamAgrees,
  type OfficeLaunchOwnerState,
} from "../meta-ceo/preview";
import {
  sameProjectExecutionContext,
  type ProjectExecutionContextAvailable,
  type ProjectExecutionContext,
} from "./project-execution-context";

/** A preview for the existing launcher; it is not an admitted execution plan. */
export interface ProjectLaunchDraft {
  readonly context: ProjectExecutionContextAvailable;
  /** The user's exact text. Never inferred from a task status or truncated. */
  readonly goal: string;
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

/** Detach the preview from the view that produced it; this performs no I/O. */
export function createProjectLaunchDraft(
  context: ProjectExecutionContextAvailable,
  goal: string,
): ProjectLaunchDraft {
  return freeze({ context: structuredClone(context), goal });
}

export function sameProjectLaunchDraft(
  left: ProjectLaunchDraft,
  right: ProjectLaunchDraft,
): boolean {
  return left.goal === right.goal &&
    sameProjectExecutionContext(left.context, right.context);
}

/**
 * Equality does not establish source authenticity or freshness. The existing
 * plan reader and authenticated parent must supply their live acquisition fence.
 * Recheck this at handoff AND before the existing launcher prepares a command.
 */
export function projectLaunchContextIsCurrent(
  draft: ProjectLaunchDraft,
  current: ProjectExecutionContext,
  sourceIsCurrent: boolean,
): boolean {
  return sourceIsCurrent === true && current.state === "AVAILABLE" &&
    sameProjectExecutionContext(draft.context, current);
}

export type ProjectLaunchRefusal =
  | "PROJECT_CONTEXT_NOT_CURRENT"
  | "LAUNCH_OWNER_UNAVAILABLE"
  | "WORKSTREAM_MISMATCH"
  | "LAUNCH_COMMAND_HELD"
  | "LAUNCH_GOAL_PRESERVED";

export type ProjectLaunchOutcome =
  | { status: "OPENED"; reuseExisting: boolean }
  | { status: "REFUSED"; reason: ProjectLaunchRefusal };

export interface ProjectLaunchInspection {
  readonly current: ProjectExecutionContext;
  readonly sourceIsCurrent: boolean;
  /** Live state from the existing launch owner, not another launch store. */
  readonly owner: Omit<OfficeLaunchOwnerState, "handoffAlreadyOpen">;
  /** Only the existing launch owner's project handoff, if it has one. */
  readonly openedDraft: ProjectLaunchDraft | null;
}

/**
 * Effect-free handoff decision. OPENED permits opening the existing launch
 * draft only; it never grants submission, dispatch, adoption or task readiness.
 * When reuseExisting is true the caller must leave the current goal untouched.
 */
export function decideProjectLaunchHandoff(
  draft: ProjectLaunchDraft,
  inspection: ProjectLaunchInspection,
): ProjectLaunchOutcome {
  const { current, sourceIsCurrent, owner, openedDraft } = inspection;
  if (!projectLaunchContextIsCurrent(draft, current, sourceIsCurrent))
    return { status: "REFUSED", reason: "PROJECT_CONTEXT_NOT_CURRENT" };
  if (!owner.launchAvailable || owner.configuredWorkstream === null)
    return { status: "REFUSED", reason: "LAUNCH_OWNER_UNAVAILABLE" };
  if (!officeLaunchWorkstreamAgrees(draft.context.workRef, owner.selectedWorkstream) ||
      !officeLaunchWorkstreamAgrees(draft.context.workRef, owner.configuredWorkstream))
    return { status: "REFUSED", reason: "WORKSTREAM_MISMATCH" };
  if (owner.commandHeld)
    return { status: "REFUSED", reason: "LAUNCH_COMMAND_HELD" };
  if (openedDraft && sameProjectLaunchDraft(draft, openedDraft))
    return { status: "OPENED", reuseExisting: true };
  if (owner.retainedGoal.trim().length > 0)
    return { status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" };
  return { status: "OPENED", reuseExisting: false };
}
