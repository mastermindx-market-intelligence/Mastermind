/** `mastermind.team_roster/v1` — Director B's projected team roster contract.
 *
 * Field names (contract prose → JSON keys, camelCase like the incumbent
 * `mastermind.hermes_native_view.v1`): bot id → `botId`, display name →
 * `displayName`, role → `role`, profile → `profile`, gateway instance →
 * `gatewayInstance`, host → `host`, readiness → `readiness`
 * ({ready|degraded|unknown} + `reason`), last activity ISO|null →
 * `lastActivity`, activity summary → `activitySummary`.
 *
 * Parsing is fail-closed: any unknown key, wrong type or invalid value makes
 * the whole roster UNAVAILABLE — a partial roster is never partially trusted.
 */
export type TeamReadiness = "ready" | "degraded" | "unknown";

export interface TeamRosterEntry {
  botId: string;
  displayName: string;
  role: string;
  profile: string | null;
  gatewayInstance: string | null;
  host: string | null;
  readiness: TeamReadiness;
  /** Reason is required exactly when readiness is not `ready`. */
  readinessReason: string | null;
  /** ISO 8601 timestamp or null when never observed. */
  lastActivity: string | null;
  activitySummary: string | null;
}

export interface TeamRosterView {
  schema: "mastermind.team_roster.v1";
  bots: readonly TeamRosterEntry[];
}

export type TeamRosterRead =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "AVAILABLE"; roster: TeamRosterView };

const READINESS = new Set(["ready", "degraded", "unknown"]);
const BOT_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

function invalid(reason: string): never {
  throw new Error(reason);
}

function record(value: unknown, allowed: readonly string[], required: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("TEAM_ROSTER_INVALID");
  const object = value as Record<string, unknown>;
  if (Object.keys(object).some(key => !allowed.includes(key)) || required.some(key => !(key in object))) invalid("TEAM_ROSTER_INVALID");
  return object;
}

function text(value: unknown, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) invalid("TEAM_ROSTER_INVALID");
  return value;
}

function optionalText(value: unknown, maximum: number): string | null {
  return value === null ? null : text(value, maximum);
}

function botEntry(value: unknown): TeamRosterEntry {
  const required = ["botId", "displayName", "role", "profile", "gatewayInstance", "host", "readiness", "readinessReason", "lastActivity", "activitySummary"];
  const row = record(value, required, required);
  const botId = text(row.botId, 128);
  if (BOT_ID.exec(botId)?.[0] !== botId) invalid("TEAM_ROSTER_INVALID");
  const readiness = text(row.readiness, 16);
  if (!READINESS.has(readiness)) invalid("TEAM_ROSTER_INVALID");
  const readinessValue = readiness as TeamReadiness;
  const readinessReason = optionalText(row.readinessReason, 240);
  // A healthy row carries no reason; an unhealthy row must explain itself.
  if (readiness === "ready" && readinessReason !== null) invalid("TEAM_ROSTER_INVALID");
  if (readiness !== "ready" && readinessReason === null) invalid("TEAM_ROSTER_INVALID");
  const lastActivity = optionalText(row.lastActivity, 40);
  if (lastActivity !== null && ISO.exec(lastActivity)?.[0] !== lastActivity) invalid("TEAM_ROSTER_INVALID");
  return {
    botId,
    displayName: text(row.displayName, 160),
    role: text(row.role, 160),
    profile: optionalText(row.profile, 512),
    gatewayInstance: optionalText(row.gatewayInstance, 160),
    host: optionalText(row.host, 160),
    readiness: readinessValue,
    readinessReason,
    lastActivity,
    activitySummary: optionalText(row.activitySummary, 480),
  };
}

/** Fail-closed parser for `mastermind.team_roster/v1`. Throws on any defect. */
export function parseTeamRoster(value: unknown): TeamRosterView {
  const root = record(value, ["schema", "bots"], ["schema", "bots"]);
  if (root.schema !== "mastermind.team_roster.v1") invalid("TEAM_ROSTER_INVALID");
  if (!Array.isArray(root.bots) || root.bots.length > 64) invalid("TEAM_ROSTER_INVALID");
  const bots = root.bots.map(botEntry);
  if (new Set(bots.map(bot => bot.botId)).size !== bots.length) invalid("TEAM_ROSTER_INVALID");
  return { schema: "mastermind.team_roster.v1", bots };
}

/** Read the roster through the existing mission host facade, fail-closed.
 *  Until Director B's projection is installed, every host reports no source
 *  and the caller renders the honest unverified-roster state. */
export function readTeamRoster(host: unknown): TeamRosterRead {
  const source = (host as { teamRoster?: { read?: unknown } } | undefined)?.teamRoster;
  if (!source || typeof source !== "object" || typeof source.read !== "function") {
    return { kind: "UNAVAILABLE", reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED" };
  }
  let raw: unknown;
  try {
    raw = (source.read as () => unknown)();
  } catch {
    return { kind: "UNAVAILABLE", reason: "TEAM_ROSTER_SOURCE_READ_FAILED" };
  }
  if (raw === null || raw === undefined) return { kind: "UNAVAILABLE", reason: "TEAM_ROSTER_SOURCE_EMPTY" };
  try {
    return { kind: "AVAILABLE", roster: parseTeamRoster(raw) };
  } catch {
    return { kind: "UNAVAILABLE", reason: "TEAM_ROSTER_SOURCE_INVALID" };
  }
}
