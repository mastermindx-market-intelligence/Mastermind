import { decodeAttendedStatus, type AttendedStatus } from "./attended-status";

/** Consumer-only shape. No default producer, filesystem access, grants or registry. */
export interface CatalogRow {
  run_id: string;
  controller_modified_at: string | null;
  status: AttendedStatus | null;
  reason_code: "STATUS_UNAVAILABLE" | "SOURCE_CHANGED" | "STATUS_INVALID" | null;
}
export interface FabricCatalog {
  schema: "mastermind.attended_fabric_catalog.v1";
  availability: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE";
  observed_at: string;
  source: {
    owner: "ATTENDED_FABRIC";
    observation_kind: "CONTROLLER_STATUS_SNAPSHOT";
    revision: string | null;
    scope: "MACHINE_OWNER" | "EXACT_RUN_SET";
    atomic: false;
    time_basis: "LOCAL_READ";
  };
  coverage: {
    returned_count: number; candidate_count: number | null; omitted_count: number | null;
    scan_complete: boolean; status_complete: boolean;
  };
  items: CatalogRow[];
  reason_codes: string[];
}
export const CATALOG_LIMIT = 32;
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const HASH = /^[0-9a-f]{64}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
const ROW_REASONS = ["STATUS_UNAVAILABLE", "SOURCE_CHANGED", "STATUS_INVALID"] as const;
const REASONS = ["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SCAN_LIMIT", "ROWS_OMITTED", "STATUS_PARTIAL"] as const;
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const natural = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const time = (v: unknown): v is string => typeof v === "string" && ISO.test(v) && Number.isFinite(Date.parse(v));

/** Decode only metadata; arbitrary producer fields and output text never reach the view. */
export function decodeFabricCatalog(raw: unknown): FabricCatalog {
  const fail = (): never => { throw new Error("FABRIC_CATALOG_INVALID"); };
  if (!record(raw) || raw.schema !== "mastermind.attended_fabric_catalog.v1" ||
      !["AVAILABLE", "PARTIAL", "UNAVAILABLE"].includes(raw.availability as string) || !time(raw.observed_at) ||
      !record(raw.source) || !record(raw.coverage) || !Array.isArray(raw.items) || raw.items.length > CATALOG_LIMIT ||
      !Array.isArray(raw.reason_codes) || raw.reason_codes.length > REASONS.length ||
      raw.reason_codes.some(r => !REASONS.includes(r as never)) || new Set(raw.reason_codes).size !== raw.reason_codes.length) return fail();
  const source = raw.source, c = raw.coverage;
  if (source.owner !== "ATTENDED_FABRIC" || source.observation_kind !== "CONTROLLER_STATUS_SNAPSHOT" ||
      source.atomic !== false || source.time_basis !== "LOCAL_READ" || !["MACHINE_OWNER", "EXACT_RUN_SET"].includes(source.scope as string) ||
      !(source.revision === null || typeof source.revision === "string" && HASH.test(source.revision)) ||
      !natural(c.returned_count) || c.returned_count !== raw.items.length ||
      !(c.candidate_count === null || natural(c.candidate_count)) || !(c.omitted_count === null || natural(c.omitted_count)) ||
      typeof c.scan_complete !== "boolean" || typeof c.status_complete !== "boolean") return fail();
  if (c.candidate_count !== null && (c.candidate_count < c.returned_count ||
      c.omitted_count !== null && c.candidate_count - c.returned_count !== c.omitted_count)) return fail();
  if (c.scan_complete && (c.candidate_count === null || c.omitted_count === null)) return fail();
  if (raw.availability === "AVAILABLE" && (!c.scan_complete || !c.status_complete || source.revision === null)) return fail();
  if (raw.availability === "UNAVAILABLE" && (raw.items.length !== 0 || c.candidate_count !== null || c.omitted_count !== null ||
      c.scan_complete || c.status_complete || source.revision !== null)) return fail();
  const seen = new Set<string>();
  const items = raw.items.map((row): CatalogRow => {
    if (!record(row) || typeof row.run_id !== "string" || !ID.test(row.run_id) || seen.has(row.run_id) ||
        !(row.controller_modified_at === null || time(row.controller_modified_at)) ||
        !(row.reason_code === null || ROW_REASONS.includes(row.reason_code as never))) return fail();
    seen.add(row.run_id);
    let status: AttendedStatus | null = null;
    if (row.status !== null) {
      if (!record(row.status) || row.reason_code !== null) return fail();
      // The existing decoder checks an expected run plus a possible root. When the owner
      // has no root, this local validation token is never emitted or used as permission;
      // decodeAttendedStatus retains root_id=null and the UI disables root navigation.
      const expectedRoot = row.status.root_id === null ? row.run_id : row.status.root_id;
      if (typeof expectedRoot !== "string") return fail();
      try { status = decodeAttendedStatus(row.status, { rootId: expectedRoot, runId: row.run_id }); }
      catch { return fail(); }
    } else if (row.reason_code === null) return fail();
    if (c.status_complete && status === null) return fail();
    return { run_id: row.run_id, controller_modified_at: row.controller_modified_at as string | null,
      status, reason_code: row.reason_code as CatalogRow["reason_code"] };
  });
  return {
    schema: "mastermind.attended_fabric_catalog.v1", availability: raw.availability as FabricCatalog["availability"],
    observed_at: raw.observed_at, source: { owner: "ATTENDED_FABRIC", observation_kind: "CONTROLLER_STATUS_SNAPSHOT",
      revision: source.revision as string | null, scope: source.scope as FabricCatalog["source"]["scope"], atomic: false, time_basis: "LOCAL_READ" },
    coverage: { returned_count: c.returned_count, candidate_count: c.candidate_count as number | null,
      omitted_count: c.omitted_count as number | null, scan_complete: c.scan_complete, status_complete: c.status_complete },
    items, reason_codes: raw.reason_codes as string[],
  };
}

/**
 * Browser-facing consumer guard, not an authorization grant.
 *
 * A machine-owner catalog may be valid diagnostic metadata, but it must
 * never be projected as a signed-in user's permitted run set. The actual
 * Workspace owner must still authorize each original run server-side.
 */
export function decodeBrowserScopedFabricCatalog(raw: unknown): FabricCatalog {
  const document = decodeFabricCatalog(raw);
  if (document.source.scope !== "EXACT_RUN_SET")
    throw new Error("FABRIC_CATALOG_SCOPE_REFUSED");
  return document;
}
