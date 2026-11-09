/** Team roster contract (mastermind.team_roster/v1) — a read-only projection of
 * enrolled Hermes bots from actual install sources. Unobserved facts stay
 * unknown with a typed reason; this parser is fail-closed like parseNativeView
 * and admits no transport, credential, authority or retry surface. */
export type RosterReadiness = "ready" | "degraded" | "unknown";
export type RosterGatewaySource = "control_socket_identify" | "gateway_lock" | "none";

export interface RosterGateway {
  observed: boolean; source: RosterGatewaySource;
  instanceId: string | null; authorityEpoch: number | null;
  codeVersion: string | null; pid: number | null; state: string | null;
}
export interface TeamBot {
  id: string; displayName: string; role: string; profilePath?: string;
  managed: boolean | null; host: string;
  gateway: RosterGateway; readiness: RosterReadiness; readinessReason: string;
  lastActivity: string | null; activitySummary: string | null; activityReason?: string;
}
export interface TeamRoster {
  schema: "mastermind.team_roster/v1"; generatedAt: string; host: string; bots: TeamBot[];
}

const readiness = new Set(["ready", "degraded", "unknown"]);
const gatewaySources = new Set(["control_socket_identify", "gateway_lock", "none"]);
const idPattern = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const hostPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const isoPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)$/;
const reasonPattern = /^[A-Z][A-Z0-9_]{1,63}$/;

function invalid(): never { throw new Error("NATIVE_RESPONSE_INVALID"); }
function text(value: unknown, maximum: number, options?: { empty?: boolean }): string;
function text(value: unknown, maximum: number, options: { nullable: true; empty?: boolean }): string | null;
function text(value: unknown, maximum: number, options: { nullable?: boolean; empty?: boolean } = {}): string | null {
  if (options.nullable && value === null) return null;
  if (typeof value !== "string" || (!options.empty && value.length === 0) || value.length > maximum) return invalid();
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return invalid();
  return value;
}
function integer(value: unknown, minimum = 0): number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum ? value : invalid();
}
function flag(value: unknown): boolean { return typeof value === "boolean" ? value : invalid(); }
function reason(value: unknown): string {
  return typeof value === "string" && reasonPattern.test(value) ? value : invalid();
}

function gateway(value: unknown): RosterGateway {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const v = value as Record<string, unknown>;
  const keys = ["observed", "source", "instanceId", "authorityEpoch", "codeVersion", "pid", "state"];
  if (Object.keys(v).some(key => !keys.includes(key)) || keys.some(key => !(key in v))) return invalid();
  const source = text(v.source, 64);
  if (!gatewaySources.has(source)) return invalid();
  const epoch = v.authorityEpoch;
  const observed = flag(v.observed);
  if (!observed && source !== "none") return invalid();
  return { observed, source: source as RosterGatewaySource,
    instanceId: text(v.instanceId, 160, { nullable: true, empty: true }),
    authorityEpoch: epoch === null ? null : integer(epoch, 1),
    codeVersion: text(v.codeVersion, 64, { nullable: true, empty: true }),
    pid: v.pid === null ? null : integer(v.pid, 1),
    state: text(v.state, 32, { nullable: true, empty: true }) };
}

function bot(value: unknown): TeamBot {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const v = value as Record<string, unknown>;
  const allowed = ["id", "displayName", "role", "profilePath", "managed", "host",
    "gateway", "readiness", "readinessReason", "lastActivity", "activitySummary", "activityReason"];
  if (Object.keys(v).some(key => !allowed.includes(key))) return invalid();
  for (const key of ["id", "displayName", "host", "gateway", "readiness", "readinessReason"]) {
    if (!(key in v)) return invalid();
  }
  const id = text(v.id, 64);
  if (idPattern.test(id) !== true) return invalid();
  const host = text(v.host, 64);
  if (host !== "unknown" && hostPattern.test(host) !== true) return invalid();
  const readinessValue = text(v.readiness, 16);
  if (readiness.has(readinessValue) !== true) return invalid();
  const managed = v.managed === null ? null : flag(v.managed);
  if ("profilePath" in v) {
    const path = text(v.profilePath, 512, { nullable: true, empty: true });
    if (path !== null && !path.startsWith("/")) return invalid();
  }
  const lastActivity = "lastActivity" in v ? text(v.lastActivity, 64, { nullable: true, empty: true }) : null;
  if (lastActivity !== null && isoPattern.test(lastActivity) !== true) return invalid();
  const activitySummary = "activitySummary" in v
    ? text(v.activitySummary, 240, { nullable: true, empty: true }) : null;
  const activityReason = "activityReason" in v && v.activityReason !== undefined
    ? reason(v.activityReason) : undefined;
  if (lastActivity === null && activityReason === undefined) return invalid();
  if (lastActivity !== null && activityReason !== undefined) return invalid();
  return { id, displayName: text(v.displayName, 240)!, role: text(v.role, 160, { empty: true, nullable: true }) ?? "",
    ...("profilePath" in v ? { profilePath: (v.profilePath as string | null) ?? undefined } : {}),
    managed, host, gateway: gateway(v.gateway),
    readiness: readinessValue as RosterReadiness, readinessReason: reason(v.readinessReason),
    lastActivity, activitySummary, ...(activityReason !== undefined ? { activityReason } : {}) };
}

export function parseTeamRoster(value: unknown): TeamRoster {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const v = value as Record<string, unknown>;
  const keys = ["schema", "generatedAt", "host", "bots"];
  if (Object.keys(v).some(key => !keys.includes(key)) || keys.some(key => !(key in v))) return invalid();
  if (v.schema !== "mastermind.team_roster/v1") return invalid();
  const generatedAt = text(v.generatedAt, 64);
  if (isoPattern.test(generatedAt) !== true) return invalid();
  const host = text(v.host, 64);
  if (host !== "unknown" && hostPattern.test(host) !== true) return invalid();
  if (!Array.isArray(v.bots) || v.bots.length > 64) return invalid();
  const bots = v.bots.map(bot);
  if (new Set(bots.map(item => item.id)).size !== bots.length) return invalid();
  if (new TextEncoder().encode(JSON.stringify(bots)).length > 262144) return invalid();
  return { schema: "mastermind.team_roster/v1", generatedAt, host, bots };
}
