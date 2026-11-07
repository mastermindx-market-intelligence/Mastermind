import type { ProjectPlanRead, ProjectPlanSelection } from "./project-plan";
import type { PlanAdoptionTransport } from "./plan-adoption-port";
import type { AuthState } from "../host";

/** The current ProjectPlanPanel supplies its one fenced READ; never reread it. */
export interface PlanAdoptionInspection {
  readonly read: ProjectPlanRead;
  readonly selection: ProjectPlanSelection;
  readonly proposalId: string;
  readonly isCurrent: () => boolean;
  readonly canRead: () => boolean;
}
/** Structural subset of S7's fixed authenticated MissionHost boundary. */
export interface PlanAdoptionWorkflowHost {
  readonly sourceOperations?: PlanAdoptionTransport;
  readSourceOperationContext?(request:{action:"ADOPT_PLAN";workRef:string;signal:AbortSignal}):Promise<unknown>;
  invalidationGeneration?:()=>number;
  auth?:{getState:()=>AuthState;subscribe:(listener:(state:AuthState)=>void)=>()=>void};
}
