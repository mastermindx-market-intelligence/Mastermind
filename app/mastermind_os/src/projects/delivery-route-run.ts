/** TD06/TD07 journey-step data contracts (Paper boards TD06 node 117C-0
 * "Route · Review execution" and TD07 node 11GQ-0 "Run · Result and return
 * path").
 *
 * These are typed props the parent (App through ProjectDeliveryPanel) wires
 * later; the components that consume them never fetch and never invent. Every
 * nullable field degrades honestly at the view layer ("Not projected" with the
 * reason naming the missing source), so both journey steps render fully from
 * null props.
 *
 * Field names follow the same rule as `src/team/delegated-task.ts` and
 * `src/hermes-native/execution-return-contract.ts`: the snake_case names ARE
 * the shared admission contract's wire names; UI adaptation happens in views.
 */

import type { DelegatedTaskBinding } from "../team/delegated-task";
import type {
  ExecutionReturnDeliveryReceipt,
  ExecutionReturnRecord,
} from "../hermes-native/execution-return-contract";

/** The admission-binding facts the route-review step can honestly show today:
 *  exactly the `ExecutionBinding` fields the shared contract projects. The
 *  requester facts (owner/project/return) are deliberately absent —
 *  `PENDING_REQUESTER_FIELDS` in delegated-task.ts documents that v1.1 has no
 *  requester block, and this projection never invents contract fields the
 *  Python side lacks. */
export type RouteReviewBinding = Pick<
  DelegatedTaskBinding,
  | "root_run_ref"
  | "immediate_parent_run_ref"
  | "logical_child_key"
  | "operation_key"
  | "runtime_kind"
  | "task_kind"
  | "effective_complexity"
  | "request_digest"
>;

/** TD06 — the proposed coding route under review, before dispatch. Binding
 *  facts come from the admitted handoff's contract; the placement fields are
 *  the admission proposal's own (host/runtime/engine/model/pool). A null
 *  placement field means admission has not proposed that slot yet — the view
 *  renders "Not projected", never a guessed value. */
export interface DelegatedRouteReview extends RouteReviewBinding {
  host?: string | null;
  runtime?: string | null;
  engine?: string | null;
  model?: string | null;
  pool?: string | null;
}

/** TD07 — one settled (or settling) run's projected outcome. `executionReturn`
 *  is Director F's parsed mastermind.execution_return/v1 record; when the run
 *  exists but the record is still null the surface shows the honest
 *  "Preparing the result" state, never a fabricated stage. `trail` is fed by
 *  the retained-activity read; null = that read is not wired to the surface. */
export interface DelegatedRunTrailStep {
  readonly title: string;
  readonly detail: string | null;
  readonly timestamp: string | null;
}

export interface DelegatedRunOutcome {
  executionReturn?: ExecutionReturnRecord | null;
  deliveryReceipt?: ExecutionReturnDeliveryReceipt | null;
  trail?: readonly DelegatedRunTrailStep[] | null;
}
