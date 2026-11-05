/** Detached navigation observations from the incumbent Control Room. Programme, authentication, action
 * admission and all provider effects stay with their existing owners.
 */
import { MAX_RESPONSE_BYTES } from "./public-config";

export type ControlRoomRole = "chairman" | "ceo" | "coo" | "worker";
const LOCATOR_KIND = Object.freeze({
  chatgpt: "chatgpt_managed_env",
  claude_code: "claude_code_session",
  claude_desktop: "claude_desktop_url",
  cursor_agent: "cursor_agent_thread",
  codex: "codex_session",
} as const);
export type ControlRoomProvider = keyof typeof LOCATOR_KIND;
export type ControlRoomLocatorKind = (typeof LOCATOR_KIND)[ControlRoomProvider];
export type ControlRoomBindingSummary = Readonly<{
  binding_id: string;
  work_ref: string;
  role: ControlRoomRole;
  provider: ControlRoomProvider;
  seat_ref: string | null;
  locator_kind: ControlRoomLocatorKind;
  observed_at: string;
  last_verified_at: string | null;
}>;
export type ControlRoomBindingConflict = Readonly<{
  work_ref: string;
  role: ControlRoomRole;
  binding_ids: readonly string[];
}>;
export type ControlRoomCapabilityProvider = ControlRoomProvider | "aionui";
export type ControlRoomCapability = Readonly<{
  installed: boolean;
  version: string | null;
  state: "PARTIAL" | "NOT_INSTALLED" | "UNSUPPORTED";
  detail: string;
}>;
export type ControlRoomNavigation =
  | Readonly<{
      state: "AVAILABLE";
      /** Attached rows, then unbound rows; each keeps its exact local handle. */
      bindings: readonly ControlRoomBindingSummary[];
      unboundBindingIds: readonly string[];
      conflicts: readonly ControlRoomBindingConflict[];
      capabilities: Readonly<Partial<Record<ControlRoomCapabilityProvider, ControlRoomCapability>>>;
      /** The owner composed a bindings Mapping; this is not filesystem health. */
      bindingsPathPresent: boolean;
    }>
  | Readonly<{ state: "UNAVAILABLE"; reason: "CONTROL_ROOM_NAVIGATION_INVALID" }>;

export type ControlRoomDiscovery = Readonly<{
  chatgpt_environments: Readonly<{
    multilogin: readonly Readonly<{
      workspace_id: string; folder_id: string; profile_id: string; running: boolean;
    }>[];
    gologin: readonly Readonly<{ profile_id: string; running: boolean }>[];
  }>;
  claude_code_sessions: readonly Readonly<{
    project_dir: string; session_id: string; mtime: number;
  }>[];
  codex_sessions: readonly Readonly<{ session_id: string; date: string }>[];
  cursor: Readonly<{ supported: false; note: string }>;
}>;
export const CONTROL_ROOM_DISCOVERY_UNAVAILABLE = "CONTROL_ROOM_DISCOVERY_UNAVAILABLE";

const UNAVAILABLE = Object.freeze({
  state: "UNAVAILABLE", reason: "CONTROL_ROOM_NAVIGATION_INVALID",
} as const);
const ROLES = ["chairman", "ceo", "coo", "worker"] as const;
const PROVIDERS = ["chatgpt", "claude_code", "claude_desktop", "cursor_agent", "codex"] as const;
const CAPABILITY_PROVIDERS = [...PROVIDERS, "aionui"] as const;
const BINDING_FIELDS = [
  "binding_id", "work_ref", "role", "provider", "seat_ref", "locator_kind",
  "observed_at", "last_verified_at",
] as const;
// Same shape accepted by surface_bindings.UUID_RE; no UUID version inference.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const WORK_REF = /^(WS|JOB|PR):\S+$/;

function invalid(): never { throw new Error("CONTROL_ROOM_NAVIGATION_INVALID"); }
function record(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return invalid();
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return invalid();
  return value as Record<string, unknown>;
}
function own(value: object, key: string): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) return invalid();
  return descriptor.value;
}

/** A bound on the JSON leaves consumed by this projection, including their
 * container/key overhead. The transport still owns the complete raw body cap
 * and strict raw JSON decoder. This is not a second raw parser or data store.
 */
class Budget {
  private bytes = 0;
  add(count: number): void {
    this.bytes += count;
    if (this.bytes > MAX_RESPONSE_BYTES) invalid();
  }
  text(value: unknown, nonempty = false): string {
    if (typeof value !== "string" || (nonempty && !value.length) ||
        value.length > MAX_RESPONSE_BYTES - this.bytes) return invalid();
    // JSON.stringify escapes lone UTF-16 surrogates; refuse them explicitly.
    for (let i = 0; i < value.length; i++) {
      const unit = value.charCodeAt(i);
      if (unit >= 0xd800 && unit <= 0xdbff) {
        const next = value.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff)) return invalid();
      } else if (unit >= 0xdc00 && unit <= 0xdfff) return invalid();
    }
    this.add(new TextEncoder().encode(JSON.stringify(value)).byteLength);
    return value;
  }
  bool(value: unknown): boolean {
    if (typeof value !== "boolean") return invalid();
    this.add(value ? 4 : 5);
    return value;
  }
  number(value: unknown): number {
    if (typeof value !== "number" || !Number.isFinite(value)) return invalid();
    this.add(JSON.stringify(value).length);
    return value;
  }
  nullableText(value: unknown): string | null {
    if (value !== null) return this.text(value);
    this.add(4);
    return null;
  }
  object(keys: readonly string[]): void {
    this.add(2 + Math.max(0, keys.length - 1) + keys.length);
    for (const key of keys) this.text(key);
  }
}
function closed(value: unknown, keys: readonly string[], budget: Budget): Record<string, unknown> {
  const row = record(value);
  const actual = Reflect.ownKeys(row);
  if (actual.length !== keys.length || actual.some(key => typeof key !== "string" || !keys.includes(key)))
    return invalid();
  for (const key of keys) own(row, key);
  budget.object(keys);
  return row;
}
function list<T>(value: unknown, budget: Budget, decode: (row: unknown) => T,
                 cap = MAX_RESPONSE_BYTES): readonly T[] {
  if (!Array.isArray(value) || value.length > cap) return invalid();
  budget.add(2 + Math.max(0, value.length - 1));
  if (Reflect.ownKeys(value).length !== value.length + 1) return invalid();
  const result: T[] = [];
  for (let i = 0; i < value.length; i++) result.push(decode(own(value, String(i))));
  return Object.freeze(result);
}
function choice<T extends string>(value: unknown, choices: readonly T[], budget: Budget): T {
  const text = budget.text(value);
  if (!choices.includes(text as T)) return invalid();
  return text as T;
}
function matching(value: unknown, expression: RegExp, budget: Budget): string {
  const text = budget.text(value, true);
  const match = expression.exec(text);
  // JavaScript's $ may also match before a final newline. These fields must
  // match in full, without normalizing the exact observed handle or reference.
  if (!match || match.index !== 0 || match[0].length !== text.length) return invalid();
  return text;
}
function utc(value: unknown, budget: Budget): string {
  const text = budget.text(value);
  // The ordinary UTC form emitted by the incumbent owner. Display only;
  // neither an observation nor last verification grants current authority.
  if (!text.endsWith("Z") || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(text) ||
      text.startsWith("0000") || !Number.isFinite(Date.parse(text)) ||
      new Date(text).toISOString().slice(0, 19) !== text.slice(0, 19)) return invalid();
  return text;
}
function binding(value: unknown, budget: Budget): ControlRoomBindingSummary {
  const row = closed(value, BINDING_FIELDS, budget);
  const provider = choice(own(row, "provider"), PROVIDERS, budget);
  const locator_kind = choice(own(row, "locator_kind"), [LOCATOR_KIND[provider]], budget);
  const seat_ref = budget.nullableText(own(row, "seat_ref"));
  if (provider === "chatgpt" && (seat_ref === null || !seat_ref.trim())) return invalid();
  const verified = own(row, "last_verified_at");
  const last_verified_at = verified === null ? budget.nullableText(verified) : utc(verified, budget);
  return Object.freeze({
    binding_id: matching(own(row, "binding_id"), UUID, budget),
    work_ref: matching(own(row, "work_ref"), WORK_REF, budget),
    role: choice(own(row, "role"), ROLES, budget),
    provider, seat_ref, locator_kind,
    observed_at: utc(own(row, "observed_at"), budget),
    last_verified_at,
  });
}
function capability(value: unknown, provider: ControlRoomCapabilityProvider, budget: Budget): ControlRoomCapability {
  const row = closed(value, ["installed", "version", "state", "detail"], budget);
  const installed = budget.bool(own(row, "installed"));
  const version = budget.nullableText(own(row, "version"));
  const state = choice(own(row, "state"), ["PARTIAL", "NOT_INSTALLED", "UNSUPPORTED"], budget);
  const expected = provider === "aionui" ? "UNSUPPORTED" : installed ? "PARTIAL" : "NOT_INSTALLED";
  if (state !== expected || ((!installed || provider === "aionui") && version !== null)) return invalid();
  return Object.freeze({ installed, version, state, detail: budget.text(own(row, "detail")) });
}

/** Separately fail closed for navigation while the existing Programme parser
 * retains its own whole-document and Programme laws. No input is modified.
 */
export function decodeControlRoomNavigation(controlRoom: unknown, capabilities: unknown): ControlRoomNavigation {
  try {
    const budget = new Budget();
    budget.object(["control_room", "capabilities"]);
    const room = record(controlRoom);
    budget.object(["schema", "sources", "work", "unbound_surfaces", "binding_conflicts"]);
    if (budget.text(own(room, "schema")) !== "mastermind.chairman_control_room.v1") return invalid();
    const sources = record(own(room, "sources"));
    budget.object(["bindings_path_present"]);
    const bindingsPathPresent = budget.bool(own(sources, "bindings_path_present"));
    const workRefs = new Set<string>();
    const ids = new Set<string>();
    const bindings: ControlRoomBindingSummary[] = [];
    const append = (raw: unknown): ControlRoomBindingSummary => {
      const row = binding(raw, budget);
      if (ids.has(row.binding_id)) return invalid();
      ids.add(row.binding_id);
      bindings.push(row);
      return row;
    };
    // Same 500-work-card bound as programsFromControlRoom; it is not a
    // fabricated binding-row quota. All consumed rows share the byte budget.
    list(own(room, "work"), budget, raw => {
      const card = record(raw);
      budget.object(["work_ref", "bindings"]);
      const ref = matching(own(card, "work_ref"), WORK_REF, budget);
      if (workRefs.has(ref)) return invalid();
      workRefs.add(ref);
      list(own(card, "bindings"), budget, item => {
        const row = append(item);
        if (row.work_ref !== ref) return invalid();
        return row;
      });
    }, 500);
    const unboundBindingIds = list(own(room, "unbound_surfaces"), budget, raw => {
      const row = append(raw);
      if (workRefs.has(row.work_ref)) return invalid();
      return row.binding_id;
    });
    if (!bindingsPathPresent && bindings.length) return invalid();

    // Transient consistency checking only. Keep exact handles and the entire
    // ambiguous group; never choose or collapse a role's navigation target.
    const key = (ref: string, role: ControlRoomRole) => JSON.stringify([ref, role]);
    const grouped = new Map<string, ControlRoomBindingSummary[]>();
    for (const row of bindings) {
      const group = key(row.work_ref, row.role);
      const previous = grouped.get(group);
      if (previous) previous.push(row); else grouped.set(group, [row]);
    }
    const expected = new Map<string, readonly string[]>();
    for (const [group, rows] of grouped) {
      if (rows.length <= 1) continue;
      if (rows.every(row => row.provider === "chatgpt") &&
          new Set(rows.map(row => row.seat_ref)).size === rows.length) continue;
      expected.set(group, rows.map(row => row.binding_id).sort());
    }
    const conflicts = list(own(room, "binding_conflicts"), budget, raw => {
      const row = closed(raw, ["work_ref", "role", "binding_ids"], budget);
      const work_ref = matching(own(row, "work_ref"), WORK_REF, budget);
      const role = choice(own(row, "role"), ROLES, budget);
      const binding_ids = list(own(row, "binding_ids"), budget, id => matching(id, UUID, budget));
      const group = key(work_ref, role);
      const wanted = expected.get(group);
      const sorted = [...binding_ids].sort();
      if (!wanted || sorted.length !== wanted.length || sorted.some((id, i) => id !== wanted[i]))
        return invalid();
      expected.delete(group);
      return Object.freeze({ work_ref, role, binding_ids });
    });
    if (expected.size) return invalid();
    const census = record(capabilities);
    const censusKeys = Reflect.ownKeys(census);
    if (censusKeys.some(key => typeof key !== "string" ||
        !CAPABILITY_PROVIDERS.includes(key as ControlRoomCapabilityProvider))) return invalid();
    budget.object(censusKeys as string[]);
    const decoded: Partial<Record<ControlRoomCapabilityProvider, ControlRoomCapability>> = {};
    for (const provider of censusKeys as ControlRoomCapabilityProvider[])
      decoded[provider] = capability(own(census, provider), provider, budget);
    // An empty census is a valid unknown observation, not an absent grant.
    return Object.freeze({
      state: "AVAILABLE", bindings: Object.freeze(bindings), unboundBindingIds,
      conflicts, capabilities: Object.freeze(decoded), bindingsPathPresent,
    });
  } catch { return UNAVAILABLE; }
}

/** Observed candidates only. Directory-derived session/path/date strings are
 * intentionally not upgraded into a validated Bind locator or live proof.
 */
export function decodeControlRoomDiscovery(raw: unknown): ControlRoomDiscovery {
  try {
    const budget = new Budget();
    const root = closed(raw, ["chatgpt_environments", "claude_code_sessions", "codex_sessions", "cursor"], budget);
    const environments = closed(own(root, "chatgpt_environments"), ["multilogin", "gologin"], budget);
    const multilogin = list(own(environments, "multilogin"), budget, raw => {
      const row = closed(raw, ["workspace_id", "folder_id", "profile_id", "running"], budget);
      return Object.freeze({
        workspace_id: matching(own(row, "workspace_id"), UUID, budget),
        folder_id: matching(own(row, "folder_id"), UUID, budget),
        profile_id: matching(own(row, "profile_id"), UUID, budget),
        running: budget.bool(own(row, "running")),
      });
    }, 200);
    const gologin = list(own(environments, "gologin"), budget, raw => {
      const row = closed(raw, ["profile_id", "running"], budget);
      return Object.freeze({
        profile_id: matching(own(row, "profile_id"), /^[0-9a-f]{24}$/, budget),
        running: budget.bool(own(row, "running")),
      });
    }, 200);
    const claude_code_sessions = list(own(root, "claude_code_sessions"), budget, raw => {
      const row = closed(raw, ["project_dir", "session_id", "mtime"], budget);
      return Object.freeze({
        project_dir: budget.text(own(row, "project_dir"), true),
        session_id: budget.text(own(row, "session_id"), true),
        mtime: budget.number(own(row, "mtime")),
      });
    }, 40);
    const codex_sessions = list(own(root, "codex_sessions"), budget, raw => {
      const row = closed(raw, ["session_id", "date"], budget);
      return Object.freeze({
        session_id: budget.text(own(row, "session_id"), true),
        date: budget.text(own(row, "date"), true),
      });
    }, 40);
    const cursor = closed(own(root, "cursor"), ["supported", "note"], budget);
    if (budget.bool(own(cursor, "supported")) !== false) return invalid();
    return Object.freeze({
      chatgpt_environments: Object.freeze({ multilogin, gologin }),
      claude_code_sessions, codex_sessions,
      cursor: Object.freeze({ supported: false, note: budget.text(own(cursor, "note")) }),
    });
  } catch { throw new Error(CONTROL_ROOM_DISCOVERY_UNAVAILABLE); }
}
