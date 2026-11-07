/** Original safe journey identity, not a READ/action grant or a draft copy. */
import type { ProjectJourneySelection } from "../projects/ProjectPlanningJourney";
import { projectJourneyUrl } from "../projects/project-journey-location";
export function projectGoalDraftScope(value: ProjectJourneySelection | null): string | null {
  try {
    if (value === null) return "project-goal.v1:blank";
    if (!value || typeof value !== "object" || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
    const fields = Object.getOwnPropertyDescriptors(value), keys = ["createRequestId", "workRef", "planningOperationKey", "jobId"];
    if (Reflect.ownKeys(fields).length !== 4 || keys.some(k => !Object.hasOwn(fields, k) || !fields[k].enumerable || !Object.hasOwn(fields[k], "value"))) return null;
    const selected = Object.fromEntries(keys.map(key => [key, fields[key].value])) as unknown as ProjectJourneySelection;
    // Reuse the incumbent dependency/ID grammar; this pure builder performs
    // no navigation and the URL is never requested or persisted here.
    projectJourneyUrl("https://app.mastermind-x.com/os/", selected);
    return "project-goal.v1:" + JSON.stringify(keys.map(key => fields[key].value));
  } catch { return null; }
}
