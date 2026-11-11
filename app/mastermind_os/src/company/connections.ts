import type { CompanyRecord, CompanySnapshot } from "./contract";

export interface ConnectionRef { readonly owner: string; readonly kind: string; readonly id: string }
export interface CompanyConnection {
  readonly relation: string;
  readonly from: ConnectionRef;
  readonly to: ConnectionRef;
  readonly state: "VISIBLE" | "OUTSIDE_VISIBLE_WINDOW" | "CONFIGURED_NOT_LIVE_VERIFIED";
}
export interface CompanyConnections {
  readonly state: "CURRENT" | "PARTIAL" | "WITHHELD";
  readonly coverage: "VISIBLE_SOURCE_WINDOW";
  readonly consistency: "SEPARATE_READS_NOT_ATOMIC";
  readonly collectionCoverage: readonly Readonly<{ collection: string; state: string; loaded: number; hasMore: boolean; restrictedCount: number }>[];
  readonly relationships: readonly CompanyConnection[];
  readonly findings: readonly Readonly<{ code: string; relation: string; refs: readonly ConnectionRef[] }>[];
  readonly findingsOmitted: number;
  readonly outsideWindowCount: number;
  readonly withheldRelationshipCount: number;
  readonly dependencies: "NOT_PROJECTED";
  readonly executionLineage: "NOT_PROJECTED";
  readonly parentConsumption: "NOT_OBSERVED";
  readonly helpAvenues: readonly Readonly<{ kind: string; state: string }>[];
}

const kinds: Record<string, string> = { people: "agent", projects: "project", goals: "goal", work: "issue" };
const relations = [
  ["people", "reportsTo", "reports_to", "agent"],
  ["projects", "goalId", "project_goal", "goal"], ["projects", "leadAgentId", "project_lead", "agent"],
  ["goals", "parentId", "goal_parent", "goal"], ["goals", "ownerAgentId", "goal_owner", "agent"],
  ["work", "parentId", "issue_parent", "issue"], ["work", "projectId", "issue_project", "project"],
  ["work", "goalId", "issue_goal", "goal"], ["work", "assigneeAgentId", "issue_assignee", "agent"],
] as const;
const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const ref = (kind: string, id: string, owner = "paperclip"): ConnectionRef => ({ owner, kind, id });
const invalid = (): never => { throw new Error("SOURCE_CONNECTIONS_INVALID"); };
const nativeId = (value: unknown): string => typeof value === "string" && uuid.test(value) ? value.toLowerCase() : invalid();

/** Recompute solely from decoded visible records. No graph/source registry or
 * native identity is created. This also checks the optional server projection. */
export function projectCompanyConnections(snapshot: Pick<CompanySnapshot,
  "collections" | "runtimeBindings" | "projectBindings" | "capabilities">): CompanyConnections {
  const rows: Record<string, readonly CompanyRecord[]> = {}, visible: Record<string, Set<string>> = {};
  const coverage: { collection: string; state: string; loaded: number; hasMore: boolean; restrictedCount: number }[] = [];
  const findings: { code: string; relation: string; refs: ConnectionRef[] }[] = [];
  const edges: CompanyConnection[] = [];
  let findingCount = 0;
  const finding = (code: string, relation: string, refs: ConnectionRef[] = []) => {
    findingCount += 1;
    if (findings.length < 64) findings.push({ code, relation, refs });
  };
  for (const [collection, kind] of Object.entries(kinds)) {
    const source = snapshot.collections[collection], state = source?.state ?? "NOT_REQUESTED";
    const items = state === "CURRENT" ? source!.items : [];
    if (!Array.isArray(items) || items.length > 50) invalid();
    rows[collection] = items;
    visible[kind] = new Set();
    coverage.push({ collection, state, loaded: items.length, hasMore: Boolean(source?.hasMore), restrictedCount: source?.restrictedCount ?? 0 });
    for (const row of items) {
      const id = nativeId(row.id);
      if (visible[kind]!.has(id)) finding("DUPLICATE_ID", collection, [ref(kind, id)]);
      visible[kind]!.add(id);
    }
  }
  for (const [collection, field, relation, targetKind] of relations) {
    for (const row of rows[collection]!) {
      const raw = row[field];
      if (raw === undefined || raw === null) continue;
      const origin = ref(kinds[collection]!, nativeId(row.id));
      if (typeof raw !== "string" || !uuid.test(raw)) { finding("MALFORMED_REFERENCE", relation, [origin]); continue; }
      const target = raw.toLowerCase(), destination = ref(targetKind, target);
      edges.push({ relation, from: origin, to: destination, state: visible[targetKind]!.has(target) ? "VISIBLE" : "OUTSIDE_VISIBLE_WINDOW" });
      if (origin.kind === destination.kind && origin.id === destination.id) finding("SELF_REFERENCE", relation, [origin]);
    }
  }
  for (const relation of ["reports_to", "goal_parent", "issue_parent"]) {
    const parent = new Map(edges.filter(edge => edge.relation === relation && edge.state === "VISIBLE").map(edge => [edge.from.id, edge]));
    const visited = new Set<string>();
    for (const start of parent.keys()) {
      const trail: string[] = [], positions = new Map<string, number>();
      let cursor = start;
      while (parent.has(cursor) && !visited.has(cursor)) {
        if (positions.has(cursor)) {
          const cycle = trail.slice(positions.get(cursor));
          if (cycle.length > 1) finding("VISIBLE_CYCLE", relation, cycle.map(key => parent.get(key)!.from));
          break;
        }
        positions.set(cursor, trail.length);
        trail.push(cursor);
        cursor = parent.get(cursor)!.to.id;
      }
      trail.forEach(key => visited.add(key));
    }
  }
  const joins = [
    { sourceKind: "agent", targetKind: "profile", owner: "hermes", relation: "runs_as", cap: 128,
      rows: snapshot.runtimeBindings.map(binding => ({ source: binding.agentId, target: binding.profileRef,
        valid: binding.runtime === "hermes" && binding.qualification === "CONFIGURED_NOT_LIVE_VERIFIED" })) },
    { sourceKind: "project", targetKind: "workstream", owner: "agentos", relation: "tracks_work", cap: 256,
      rows: snapshot.projectBindings.map(binding => ({ source: binding.projectId, target: binding.workRef,
        valid: /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(binding.workRef) })) },
  ];
  for (const join of joins) {
    if (join.rows.length > join.cap) invalid();
    const sources = new Set<string>(), targets = new Set<string>();
    for (const binding of join.rows) {
      const id = nativeId(binding.source);
      if (!visible[join.sourceKind]!.has(id)) continue;
      const origin = ref(join.sourceKind, id), target = binding.target;
      if (!binding.valid || typeof target !== "string" || !target.length || target.length > 192 || /[\u0000-\u001f]/.test(target)) {
        finding("MALFORMED_BINDING", join.relation, [origin]); continue;
      }
      if (sources.has(id) || targets.has(target)) finding("AMBIGUOUS_BINDING", join.relation, [origin]);
      sources.add(id); targets.add(target);
      edges.push({ relation: join.relation, from: origin, to: ref(join.targetKind, target, join.owner), state: "CONFIGURED_NOT_LIVE_VERIFIED" });
    }
  }
  if (edges.length > 550) invalid();
  const outside = edges.filter(edge => edge.state === "OUTSIDE_VISIBLE_WINDOW").length;
  const partial = outside > 0 || coverage.some(row => row.state !== "CURRENT" || row.hasMore || row.restrictedCount > 0);
  return {
    state: findings.length ? "WITHHELD" : partial ? "PARTIAL" : "CURRENT",
    coverage: "VISIBLE_SOURCE_WINDOW", consistency: "SEPARATE_READS_NOT_ATOMIC",
    collectionCoverage: coverage, relationships: findings.length ? [] : edges,
    findings, findingsOmitted: findingCount - findings.length, outsideWindowCount: outside,
    withheldRelationshipCount: findings.length ? edges.length : 0,
    dependencies: "NOT_PROJECTED", executionLineage: "NOT_PROJECTED", parentConsumption: "NOT_OBSERVED",
    helpAvenues: [
      { kind: "browse_team", state: "READ_ROUTE" }, { kind: "inspect_runtime", state: "READ_ROUTE" },
      { kind: "create_backlog", state: snapshot.capabilities.includes("create_backlog") ? "COMMAND_BOUND" : "NOT_BOUND_IN_THIS_SURFACE" },
      ...["consult", "delegate", "resume"].map(kind => ({ kind, state: "NOT_BOUND_IN_THIS_SURFACE" })),
    ],
  };
}

/** Walk only the bounded expected shape; unfamiliar or missing fields fail.
 * This does not traverse arbitrary deeply nested input or trust action claims. */
export function sameConnections(actual: unknown, expected: unknown): boolean {
  if (expected === null || typeof expected !== "object") return actual === expected;
  if (Array.isArray(expected)) return Array.isArray(actual) && actual.length === expected.length
    && expected.every((value, index) => sameConnections(actual[index], value));
  if (!actual || typeof actual !== "object" || Array.isArray(actual)) return false;
  const a = actual as Record<string, unknown>, e = expected as Record<string, unknown>;
  return Object.keys(a).length === Object.keys(e).length
    && Object.keys(e).every(key => Object.hasOwn(a, key) && sameConnections(a[key], e[key]));
}
