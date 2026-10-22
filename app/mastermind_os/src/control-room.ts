/** A bounded, detached projection of the incumbent authenticated CCR read.
 * No account label, refresh flag or observation timestamp grants authority.
 * Runtime status and action authorization remain with their existing owners.
 */
import { programsFromControlRoom, type ProgramCard } from "./mission";
import { decodeControlRoomNavigation, type ControlRoomNavigation } from "./control-room-navigation";

const FIELDS = [
  "control_room",
  "capabilities",
  "live_builds_active",
  "composed_at",
  "refresh_in_flight",
  "state_refresh_error",
  "source_validity",
] as const;
export type ControlRoomRead = {
  readonly state: "AVAILABLE";
  readonly programs: readonly Readonly<ProgramCard>[];
  readonly navigation: ControlRoomNavigation;
  readonly observedAt: string | null;
  readonly liveBuildsActive: boolean;
  readonly refreshInFlight: boolean;
  /** No projection-wide live/expiry inference from unrelated per-card proofs. */
  readonly freshness: "OWNER_QUALIFIED" | "UNKNOWN";
  readonly publicationSeq: number | null;
};
export type ControlRoomState = (
  | { state: "PENDING" }
  | { state: "UNAVAILABLE"; reason: string }
  | ControlRoomRead
) & {
  ownerRevision: number;
  refreshPending?: boolean;
};
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const timestamp = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 40 &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(
    value,
  ) &&
  Number.isFinite(Date.parse(value));

export function decodeControlRoomRead(raw: unknown): ControlRoomRead {
  if (
    !record(raw) ||
    Object.keys(raw).length !== FIELDS.length ||
    FIELDS.some((k) => !Object.hasOwn(raw, k)) ||
    typeof raw.live_builds_active !== "boolean" ||
    typeof raw.refresh_in_flight !== "boolean" ||
    !(raw.composed_at === null || timestamp(raw.composed_at)) ||
    !(
      raw.state_refresh_error === null ||
      typeof raw.state_refresh_error === "string"
    ) ||
    !record(raw.source_validity)
  )
    throw new Error("CONTROL_ROOM_RESPONSE_INVALID");
  // The upstream owner rejects a failed cache. Keep the same fail-closed
  // contract in the browser; do not render dependency exception text.
  if (raw.state_refresh_error !== null)
    throw new Error("CONTROL_ROOM_REFRESH_FAILED");
  const parsed = programsFromControlRoom(raw.control_room);
  if (parsed.state !== "AVAILABLE")
    throw new Error("CONTROL_ROOM_SOURCE_UNAVAILABLE");
  const validity = raw.source_validity;
  const qualified =
    validity.schema === "mastermind.control_room_source_validity.v1" &&
    Number.isSafeInteger(validity.publication_seq) &&
    (validity.publication_seq as number) > 0 &&
    Array.isArray(validity.cards);
  // Per-card TTL/permission proofs are never made into an overall LIVE badge.
  // Only the publication sequence is displayed; operational truth is unchanged.
  return Object.freeze({
    state: "AVAILABLE",
    navigation: decodeControlRoomNavigation(raw.control_room, raw.capabilities),
    programs: Object.freeze(
      parsed.programs.map((p) =>
        Object.freeze({
          ...p,
          rootCandidates: Object.freeze([
            ...p.rootCandidates,
          ]) as unknown as string[],
        }),
      ),
    ),
    observedAt: raw.composed_at as string | null,
    liveBuildsActive: raw.live_builds_active,
    refreshInFlight: raw.refresh_in_flight,
    freshness: qualified ? "OWNER_QUALIFIED" : "UNKNOWN",
    publicationSeq: qualified ? (validity.publication_seq as number) : null,
  });
}

// The accepted read decoder and fixed effect-aware action contract share one module entry.
export {
  CONTROL_ROOM_REQUEST_BYTES, CONTROL_ROOM_RESPONSE_BYTES, CONTROL_ROOM_UNKNOWN_OUTCOME,
  ControlRoomActionTransportError, controlRoomActionIsUncertain,
  decodeControlRoomActionPayload, decodeControlRoomActionResult, decodeControlRoomActionJson,
} from "./control-room-actions";
export type { ControlRoomOperation, ControlRoomDisposition, ControlRoomActionResult } from "./control-room-actions";
