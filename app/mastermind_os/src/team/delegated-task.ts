/** Presentation contract for a delegated task card (TD03 "Coding now", HC05).
 *
 * `authority: "preview"` means this surface may only observe: the card shows
 * the PREVIEW and EFFECT·NONE chips and disables dispatch. Only a real
 * admitted coding handoff on the Executive path can carry authority; the UI
 * never mints it.
 */
export type DelegatedTaskState = "queued" | "running" | "unknown" | "declined" | "terminal";

export interface DelegatedTaskResult {
  title: string;
  /** Where the result was delivered (origin bot/team/project). */
  deliveredTo: string;
  /** Delivery is never acceptance; the owner still reviews. */
}

export interface DelegatedTask {
  taskId: string;
  title: string;
  summary: string | null;
  state: DelegatedTaskState;
  /** Honest state reason (why unknown/declined, or terminal outcome). */
  stateReason: string | null;
  owner: string | null;
  route: readonly string[];
  authority: "preview" | "dispatch";
  lastActivity: string | null;
  result: DelegatedTaskResult | null;
}

export function delegatedTaskValid(task: DelegatedTask): boolean {
  if (task.taskId.length === 0 || task.taskId.length > 128) return false;
  if (task.title.length === 0 || task.title.length > 240) return false;
  if (task.summary !== null && task.summary.length > 480) return false;
  if (task.state === "unknown" && task.stateReason === null) return false;
  if (task.state === "declined" && task.stateReason === null) return false;
  if (task.result !== null && task.state !== "terminal") return false;
  if (task.result !== null && (task.result.title.length === 0 || task.result.deliveredTo.length === 0)) return false;
  if (task.route.length > 6 || task.route.some(chip => chip.length === 0 || chip.length > 64)) return false;
  return true;
}
