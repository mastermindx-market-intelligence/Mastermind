/** Closed diagnostic vocabulary shared by the Executive transports and the
 * later mission glue. Diagnostics are finite plain observations: booleans,
 * null or enum strings, never raw payloads, provider details or error text.
 * Unknown stays unknown, and reading a snapshot performs no invocation,
 * subscription, retry or mutation. */
export type DiagnosticHostKind = "native" | "web" | "unknown";

export type DiagnosticPhase =
  | "unknown" | "not_requested" | "pending" | "auth_unavailable"
  | "transport_failure" | "invalid_response" | "expired" | "ready";

export interface ExecutiveDiagnosticSnapshot {
  readonly kind: DiagnosticHostKind;
  readonly authAvailable: boolean | null;
  readonly phase: DiagnosticPhase;
  readonly contextReadReason?: DiagnosticReadReason;
}

export interface MissionDiagnosticSnapshot {
  readonly hostKind: DiagnosticHostKind;
  readonly launchConfigured: boolean | null;
  readonly frontendResourceConfigured: boolean | null;
  readonly nativeResourceConfigured: boolean | null;
  readonly acquisitionAvailable: boolean | null;
  readonly contentAvailable: boolean | null;
  readonly executiveAvailable: boolean | null;
  readonly executiveContextPhase: DiagnosticPhase;
  /** Existing native auth-status attempt; separate from the context request. */
  readonly executiveTransportPhase?: DiagnosticPhase;
  readonly executiveReadReason?: DiagnosticReadReason;
}

const KINDS: readonly DiagnosticHostKind[] = ["native", "web", "unknown"];
const PHASES: readonly DiagnosticPhase[] = ["unknown", "not_requested", "pending",
  "auth_unavailable", "transport_failure", "invalid_response", "expired", "ready"];
const isKind = (value: unknown): value is DiagnosticHostKind => KINDS.includes(value as DiagnosticHostKind);
const isPhase = (value: unknown): value is DiagnosticPhase => PHASES.includes(value as DiagnosticPhase);
const nullableBoolean = (value: unknown): value is boolean | null => value === null || typeof value === "boolean";
const plainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value) &&
  [Object.prototype, null].includes(Object.getPrototypeOf(value));

const MISSION_KEYS =
  "acquisitionAvailable,contentAvailable,executiveAvailable,executiveContextPhase," +
  "frontendResourceConfigured,hostKind,launchConfigured,nativeResourceConfigured";

/** Decode an already-closed mission diagnostics payload. Extra or unknown
 * fields, wrong enums or types, arrays and non-plain objects are rejected;
 * the input is never stringified or echoed into the result. */
export function decodeMissionDiagnostics(value: unknown): MissionDiagnosticSnapshot | null {
  try {
    if (!plainObject(value)) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some((key) => typeof key !== "string")) return null;
    const hasTransportPhase = Object.hasOwn(descriptors, "executiveTransportPhase");
    const hasReadReason = Object.hasOwn(descriptors, "executiveReadReason");
    const expected = MISSION_KEYS.split(",");
    if (hasTransportPhase) expected.push("executiveTransportPhase");
    if (hasReadReason) expected.push("executiveReadReason");
    if ((keys as string[]).sort().join(",") !== expected.sort().join(",") ||
        keys.some((key) => !("value" in descriptors[key as string]))) return null;
    // Read data descriptors only: no user getter is evaluated or retained.
    const row = Object.fromEntries((keys as string[]).map((key) => [key, descriptors[key].value]));
    if (!nullableBoolean(row.launchConfigured) || !nullableBoolean(row.frontendResourceConfigured) ||
        !nullableBoolean(row.nativeResourceConfigured) || !nullableBoolean(row.acquisitionAvailable) ||
        !nullableBoolean(row.contentAvailable) || !nullableBoolean(row.executiveAvailable) ||
        !isKind(row.hostKind) || !isPhase(row.executiveContextPhase) ||
        (hasTransportPhase && !isPhase(row.executiveTransportPhase)) ||
        (hasReadReason && !isDiagnosticReadReason(row.executiveReadReason))) return null;
    return Object.freeze({
      hostKind: row.hostKind,
      launchConfigured: row.launchConfigured,
      frontendResourceConfigured: row.frontendResourceConfigured,
      nativeResourceConfigured: row.nativeResourceConfigured,
      acquisitionAvailable: row.acquisitionAvailable,
      contentAvailable: row.contentAvailable,
      executiveAvailable: row.executiveAvailable,
      executiveContextPhase: row.executiveContextPhase,
      ...(hasTransportPhase ? { executiveTransportPhase: row.executiveTransportPhase as DiagnosticPhase } : {}),
      ...(hasReadReason ? { executiveReadReason: row.executiveReadReason as DiagnosticReadReason } : {}),
    });
  } catch { return null; }
}

/** Exact closed failure vocabulary. Only these exact native closed codes or
 * these exact local sentinel messages yield a phase; a private, foreign or
 * missing message stays "unknown". The reason text itself never enters a
 * snapshot. Cancelled and auth-epoch changes deliberately resolve to
 * "unknown" so no stale phase can be resurrected. */
const CLOSED_CODE_PHASES = {
  AUTHENTICATION_REQUIRED: "auth_unavailable",
  SOURCE_UNAVAILABLE: "transport_failure",
  ACCESS_REFUSED: "transport_failure",
  SELECTION_UNAVAILABLE: "transport_failure",
  RESPONSE_INVALID: "invalid_response",
  RESPONSE_BOUND: "invalid_response",
  PROGRAM_RESPONSE_INVALID: "invalid_response",
  PROGRAM_OBSERVATION_INVALID: "invalid_response",
  AUTHENTICATION_CHANGED: "unknown",
  READ_CANCELLED: "unknown",
  EXECUTIVE_AUTH_REQUIRED: "auth_unavailable",
  EXECUTIVE_UNAVAILABLE: "unknown",
  EXECUTIVE_AUTH_CHANGED: "unknown",
  EXECUTIVE_TRANSPORT_UNAVAILABLE: "transport_failure",
} as const;

export type DiagnosticReadReason = keyof typeof CLOSED_CODE_PHASES | "NONE" | "UNKNOWN";
export function isDiagnosticReadReason(value: unknown): value is DiagnosticReadReason {
  return typeof value === "string" && (value === "NONE" || value === "UNKNOWN" || Object.hasOwn(CLOSED_CODE_PHASES, value));
}

/** Map a current read failure to its closed phase. Accepts only an exact
 * closed code string or an Error whose exact message is allowlisted;
 * everything else is "unknown". */
export function closedReadFailureReason(reason: unknown): DiagnosticReadReason {
  try {
    const descriptor = reason instanceof Error ? Object.getOwnPropertyDescriptor(reason, "message") : undefined;
    const message = typeof reason === "string" ? reason
      : descriptor && "value" in descriptor && typeof descriptor.value === "string" ? descriptor.value : null;
    return message !== null && Object.hasOwn(CLOSED_CODE_PHASES, message)
      ? message as keyof typeof CLOSED_CODE_PHASES : "UNKNOWN";
  } catch { return "UNKNOWN"; }
}

export function closedReadFailurePhase(reason: unknown): DiagnosticPhase {
  const code = closedReadFailureReason(reason);
  return code === "NONE" || code === "UNKNOWN" ? "unknown" : CLOSED_CODE_PHASES[code];
}
