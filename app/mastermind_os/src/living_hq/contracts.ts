/**
 * Shared presentation contract for the Company HQ, graph, and observatory builds.
 * This is not a transport schema, lifecycle, authorization proof, or data store.
 * Adapters must use existing owner decoders/qualifiers before creating these values.
 * The source owners, original IDs/statuses, coverage and missingness remain intact.
 */
import type { MissionSelection, EvidenceRef } from "../mission";
import type { ResultSelection } from "../result";
import type {
  ProjectionContext, SourceState, SourceClaim, ProjectedRead, OfficeProjection,
} from "../meta-ceo/projection";
import type {
  OrganizationObservation, qualifyOrganization,
} from "../organization/OrganizationWorkspace";

export type HQLocale = "en" | "zh-CN";
export type HQOrganization = NonNullable<ReturnType<typeof qualifyOrganization>>;

/** Null completeness is unknown, never an empty or complete population. */
export interface HQRead<T> extends ProjectedRead<T> {
  readonly loading: boolean;
  readonly complete: boolean | null;
}

/** Original source identity; a node ID is only a renderer key. */
export type HQTarget =
  | { readonly kind: "human"; readonly humanRef: string }
  | { readonly kind: "role"; readonly roleKey: string }
  | { readonly kind: "program" | "mission"; readonly selection: MissionSelection }
  | { readonly kind: "job"; readonly selection: MissionSelection; readonly jobId: string }
  | { readonly kind: "attempt"; readonly selection: MissionSelection; readonly jobId: string; readonly attemptId: string }
  | { readonly kind: "session"; readonly sessionRef: string }
  | { readonly kind: "trace"; readonly traceId: string; readonly eventId: string }
  | { readonly kind: "result"; readonly selection: ResultSelection }
  | { readonly kind: "host" | "model"; readonly ownerRef: string }
  | { readonly kind: "evidence"; readonly evidence: EvidenceRef };

/** Intent to use an existing application callback, never a new effect verb. */
export type HQNavigation =
  | { readonly kind: "mission"; readonly selection: MissionSelection }
  | { readonly kind: "job"; readonly selection: MissionSelection; readonly jobId: string }
  | { readonly kind: "result"; readonly selection: ResultSelection }
  | { readonly kind: "evidence"; readonly evidence: EvidenceRef }
  | { readonly kind: "back" };

export interface HQNode {
  readonly id: string;
  readonly target: HQTarget;
  readonly label: string;
  readonly description: string | null;
  /** Original owner status. No cross-owner 'done' or synthetic activity status. */
  readonly status: string | null;
  readonly source: SourceClaim;
  readonly evidence: readonly EvidenceRef[];
}

export type HQRelation =
  | "advisory_reporting"
  | "work_lineage"
  | "delegation"
  | "trace_parent"
  | "observed_placement"
  | "result_of"
  | "original_parent_consumption";

export interface HQEdge {
  readonly id: string;
  readonly sourceId: string;
  readonly targetId: string;
  readonly relation: HQRelation;
  readonly source: SourceClaim;
  readonly evidence: readonly EvidenceRef[];
}

export interface HQGraph {
  readonly nodes: readonly HQNode[];
  readonly edges: readonly HQEdge[];
  /** Owner-declared omissions; never turn these into phantom nodes. */
  readonly omissions: readonly string[];
}

/** Only already-authorized, sanitized display text; no arbitrary HTML or URL fetch. */
export type HQText =
  | { readonly state: "available"; readonly text: string; readonly truncated: boolean }
  | { readonly state: "withheld" | "unavailable"; readonly reason: string };

export interface HQTraceEvent {
  readonly id: string;
  readonly traceId: string;
  readonly parentEventId: string | null;
  readonly target: HQTarget;
  readonly kind: "session_event" | "tool_call" | "model_call" | "job" | "attempt" | "error" | "result" | "cancellation" | "retry";
  readonly label: string;
  readonly status: string | null;
  /** Source sequence and timestamps are separate; missing times stay missing. */
  readonly sequence: number | null;
  readonly occurredAt: string | null;
  readonly completedAt: string | null;
  readonly durationMs: number | null;
  readonly input: HQText;
  readonly output: HQText;
  readonly source: SourceClaim;
  readonly evidence: readonly EvidenceRef[];
}

export interface HQSession {
  readonly sessionRef: string;
  readonly label: string;
  readonly roleKey: string | null;
  readonly status: string | null;
  readonly source: SourceClaim;
}

export interface HQPlacement {
  readonly target: Extract<HQTarget, { kind: "attempt" }>;
  readonly hostRef: string | null;
  readonly modelRef: string | null;
  readonly source: SourceClaim;
  readonly evidence: readonly EvidenceRef[];
}

/** The exact qualified Office projection is retained, rather than reinterpreted. */
export interface LivingHQSnapshot {
  readonly schema: "mastermind.living_hq_presentation.v1";
  readonly context: ProjectionContext;
  readonly office: OfficeProjection;
  readonly organization: HQRead<HQOrganization>;
  readonly sessions: HQRead<readonly HQSession[]>;
  readonly graph: {
    readonly organization: HQRead<HQGraph>;
    readonly execution: HQRead<HQGraph>;
  };
  readonly traces: HQRead<readonly HQTraceEvent[]>;
  readonly placements: HQRead<readonly HQPlacement[]>;
}

/** Only data acquired by the incumbent composition; adapters perform no IO. */
export interface LivingHQInput {
  readonly binding: ProjectionContext;
  readonly office: OfficeProjection;
  readonly organization?: OrganizationObservation;
  readonly loading: Readonly<Partial<Record<"organization" | "sessions" | "graph" | "traces" | "placements", boolean>>>;
}

/** Return-critical UI state; retained by the existing parent navigation owner. */
export interface HQViewState {
  readonly query: string;
  readonly roleKeys: readonly string[];
  /** Unmodified source-owner status values, not a new lifecycle vocabulary. */
  readonly statuses: readonly string[];
  readonly sourceStates: readonly SourceState[];
}

export interface HQSurfaceProps {
  readonly snapshot: LivingHQSnapshot;
  readonly locale: HQLocale;
  readonly viewState: HQViewState;
  readonly onViewStateChange: (state: HQViewState) => void;
  readonly selected: HQTarget | null;
  readonly onSelect: (target: HQTarget | null) => void;
  readonly onNavigate: (destination: HQNavigation) => void;
  /** Reuse the one existing read owner; this callback does not create a poller. */
  readonly onRefresh?: () => void;
}

export interface CompanyHQProps extends HQSurfaceProps {}
export interface LivingHQGraphProps extends HQSurfaceProps {
  readonly mode: "organization" | "execution";
  readonly onModeChange: (mode: "organization" | "execution") => void;
}
export interface AgentObservatoryProps extends HQSurfaceProps {
  readonly traceId: string | null;
  readonly onTraceChange: (traceId: string | null) => void;
}
