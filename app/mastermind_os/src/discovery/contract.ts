/** Ephemeral read presentation over existing decoded owners. No acquisition,
 * catalogue registry, credentials, permission, recipient or command authority. */
import type { MissionSelection, EvidenceRef } from "../mission";
import type { OfficeProjection, ProjectionContext, SourceClaim, SourceState } from "../meta-ceo/projection";
import type { ResultSelection } from "../result";
import type { ControlRoomState } from "../control-room";

export type DiscoveryMode = "Search" | "Sources" | "Tools";
export type DiscoveryKind = "project" | "conversation" | "evidence" | "result";
export type DiscoveryTarget =
  | { kind: "project"; selection: MissionSelection | null; mode: "current" | "history" }
  | { kind: "conversation"; reference: string }
  | { kind: "evidence"; evidence: EvidenceRef; facet: string }
  | { kind: "result"; selection: ResultSelection; role: string };
export interface DiscoveryItem {
  id: string;
  kind: DiscoveryKind;
  title: string;
  /** Exact supplied text or clearly bounded excerpt; never a generated summary. */
  summary: string | null;
  searchText: string;
  source: SourceClaim;
  target: DiscoveryTarget;
}
export interface DiscoverySource {
  id: string;
  title: string;
  owner: string;
  state: SourceState;
  reference: string | null;
  revision: string | null;
  observedAt: string | null;
  observedKind: "LOCAL_ACQUISITION" | "SOURCE_OBSERVATION" | null;
  sourceTime: string | null;
  coverage: string;
  content: "OBSERVED" | "REFERENCE_ONLY" | "UNAVAILABLE";
  reason: string | null;
}
export interface DiscoveryCapability {
  id: "direction_preview" | "search" | "return_review" | "source_context" | "placement" | "release";
  state: "READ_ONLY" | "PREVIEW_ONLY" | "UNAVAILABLE";
  target: "meta_ceo" | "search" | "knowledge" | "sources" | null;
}
export interface DiscoverySystemObservation {
  provider: string;
  installed: boolean;
  state: "PARTIAL" | "NOT_INSTALLED" | "UNSUPPORTED";
  version: string | null;
  detail: string;
  observedAt: string | null;
}
export type DiscoveryLimitation = "BOUNDED_SCOPE" | "NO_PEOPLE_INDEX" | "NO_GLOBAL_HISTORY" |
  "NO_GENERIC_SOURCE_READER" | "CONTROL_ROOM_NOT_SUPPLIED";
export interface DiscoveryInputs {
  projection: OfficeProjection;
  /** Actual separately paired current-window owner, never inferred from Office. */
  conversation?: OfficeProjection;
  /** Existing ownerRevision must match the current projection auth generation. */
  controlRoom?: ControlRoomState;
}
export interface DiscoveryView {
  context: ProjectionContext;
  scope: "SUPPLIED_WORKSPACE";
  items: readonly DiscoveryItem[];
  sources: readonly DiscoverySource[];
  capabilities: readonly DiscoveryCapability[];
  systems: readonly DiscoverySystemObservation[];
  limitations: readonly DiscoveryLimitation[];
}
