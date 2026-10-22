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
