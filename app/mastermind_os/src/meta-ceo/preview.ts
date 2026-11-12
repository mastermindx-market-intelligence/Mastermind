import { sameTarget, type OfficeProjection, type ProjectionContext, type SourceClaim } from "./projection";
export interface DirectionPreview {
  schema: "mastermind.composer_preview.v1";
  effectExpectation: "NONE";
  recipient: "Meta-CEO";
  draft: string;
  context: ProjectionContext;
  contextRefs: SourceClaim[];
  contentPermission: "NOT_PROJECTED";
  commandPermission: "NOT_PROJECTED";
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}
export function createDirectionPreview(projection: OfficeProjection, draft: string): DirectionPreview {
  return freeze<DirectionPreview>({
    schema: "mastermind.composer_preview.v1", effectExpectation: "NONE", recipient: "Meta-CEO", draft,
    context: structuredClone(projection.context),
    contextRefs: [projection.mission, projection.programs, projection.result, projection.conversation]
      .filter(read => read.source.state === "CURRENT" && read.value !== null)
      .map(read => structuredClone(read.source)),
    contentPermission: "NOT_PROJECTED", commandPermission: "NOT_PROJECTED",
  });
}
export function previewIsCurrent(preview: DirectionPreview, context: ProjectionContext): boolean {
  return preview.context.authGeneration === context.authGeneration && sameTarget(preview.context, context) &&
    (Object.keys(context.revisions) as Array<keyof ProjectionContext["revisions"]>)
      .every(key => preview.context.revisions[key] === context.revisions[key]);
}

/**
 * Stable refusal codes for the Office → existing launch owner handoff.
 *
 * A refusal never prepares, submits or mutates an operation. It keeps the
 * Office draft and every existing launch goal exactly as they were.
 */
export type OfficeLaunchRefusal =
  | "PREVIEW_NOT_CURRENT"
  | "LAUNCH_OWNER_UNAVAILABLE"
  | "WORKSTREAM_MISMATCH"
  | "LAUNCH_GOAL_PRESERVED"
  | "LAUNCH_COMMAND_HELD";

export type OfficeLaunchOutcome =
  | { status: "OPENED" }
  | { status: "REFUSED"; reason: OfficeLaunchRefusal };

/** The existing launch owner's state, read at the moment of the request. */
export interface OfficeLaunchOwnerState {
  /** The operator-configured launch workstream; null when no manifest is mounted. */
  configuredWorkstream: string | null;
  /** The Office's exact selected workstream; null when nothing is selected. */
  selectedWorkstream: string | null;
  /** The existing launch binding can offer a handoff right now. */
  launchAvailable: boolean;
  /** An unsent launch goal already exists and must not be replaced. */
  retainedGoal: string;
  /** An original launch command is pending or held on its own pointer. */
  commandHeld: boolean;
  /** This exact handoff is already open on the existing launch owner. */
  handoffAlreadyOpen: boolean;
}

/**
 * The Office's exact selection and the configured launch must name one
 * workstream. An Office Mission work_ref is never a project or department:
 * it is not mapped onto a launch choice, and it is never guessed from a
 * title. The frozen preview must name a concrete enrolled workstream; an
 * unselected Office never falls back to the normal launcher's default.
 */
export function officeLaunchWorkstreamAgrees(
  selectedWorkstream: string | null,
  configuredWorkstream: string | null,
): boolean {
  if (configuredWorkstream === null) return false;
  return selectedWorkstream !== null && selectedWorkstream === configuredWorkstream;
}

/**
 * Effect-free decision for the Office → existing launch owner handoff.
 *
 * The frozen preview must still be current for the live Office context, the
 * existing launch owner must be able to offer a handoff, and no existing
 * unsent launch goal or held original command may be replaced. Revisiting an
 * already open handoff is idempotent: it never places a second launch owner
 * and never replaces the goal that handoff already placed. The decision
 * itself prepares, submits and mutates nothing.
 */
export function decideOfficeLaunchHandoff(
  preview: DirectionPreview,
  context: ProjectionContext,
  owner: OfficeLaunchOwnerState,
): OfficeLaunchOutcome {
  if (!previewIsCurrent(preview, context)) return { status: "REFUSED", reason: "PREVIEW_NOT_CURRENT" };
  if (!owner.launchAvailable || owner.configuredWorkstream === null)
    return { status: "REFUSED", reason: "LAUNCH_OWNER_UNAVAILABLE" };
  if (!officeLaunchWorkstreamAgrees(owner.selectedWorkstream, owner.configuredWorkstream))
    return { status: "REFUSED", reason: "WORKSTREAM_MISMATCH" };
  if (owner.commandHeld) return { status: "REFUSED", reason: "LAUNCH_COMMAND_HELD" };
  if (owner.handoffAlreadyOpen) return { status: "OPENED" };
  if (owner.retainedGoal.trim().length > 0) return { status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" };
  return { status: "OPENED" };
}
