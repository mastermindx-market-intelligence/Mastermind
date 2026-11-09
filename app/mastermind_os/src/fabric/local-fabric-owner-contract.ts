/** User-selected, local machine-owner Fabric history. NOT an OS principal grant. */
export interface LocalOwnerRun {
  run_id: string;
  root_id: string | null;
  parent_run_id: string | null;
  pool: string | null;
  model: string | null;
  signal: string | null;
  rc: number | null;
  recorded_at_unix_s: number | null;
}
export interface LocalOwnerSnapshot {
  schema: "mastermind.local_fabric_owner_runs.v1";
  scope: "LOCAL_MACHINE_OWNER";
  basis: "RETAINED_LEDGER_OUTCOMES_ONLY";
  observed_at_unix_s: number;
  coverage: {
    machine_wide_fleet_complete: false;
    source_records_complete: boolean;
    file_tail_bytes: number;
    total_records: null;
    active_workers: null;
  };
  rows: LocalOwnerRun[];
}
export const MAX_IMPORT_BYTES = 65_536;
const id = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const label = /^[A-Za-z0-9_.: -]{1,80}$/;

function object(x: unknown): Record<string, unknown> | null {
  return x !== null && typeof x === "object" && !Array.isArray(x)
    ? x as Record<string, unknown> : null;
}
function exact(x: Record<string, unknown>, names: string[]) {
  return Object.keys(x).length === names.length && names.every(k => Object.prototype.hasOwnProperty.call(x, k));
}
function idOrNull(x: unknown): string | null | undefined {
  return x === null ? null : typeof x === "string" && id.test(x) ? x : undefined;
}
function labelOrNull(x: unknown, max: number): string | null | undefined {
  return x === null ? null : typeof x === "string" && x.length <= max && label.test(x) ? x : undefined;
}
function count(x: unknown, max = 5_000_000_000): x is number {
  return typeof x === "number" && Number.isSafeInteger(x) && x >= 0 && x <= max;
}
function invalid(): never { throw new Error("LOCAL_FABRIC_SNAPSHOT_INVALID"); }

export function decodeLocalOwnerSnapshot(raw: unknown): LocalOwnerSnapshot {
  const source = object(raw);
  if (!source || !exact(source, ["schema", "scope", "basis", "observed_at_unix_s", "coverage", "rows"]) ||
      source.schema !== "mastermind.local_fabric_owner_runs.v1" ||
      source.scope !== "LOCAL_MACHINE_OWNER" ||
      source.basis !== "RETAINED_LEDGER_OUTCOMES_ONLY" ||
      !count(source.observed_at_unix_s) || source.observed_at_unix_s < 1_600_000_000) invalid();
  const coverage = object(source.coverage);
  if (!coverage || !exact(coverage, ["machine_wide_fleet_complete", "source_records_complete", "file_tail_bytes", "total_records", "active_workers"]) ||
    coverage.machine_wide_fleet_complete !== false ||
    typeof coverage.source_records_complete !== "boolean" ||
    !count(coverage.file_tail_bytes, 262_144) ||
    coverage.total_records !== null || coverage.active_workers !== null) invalid();
  if (!Array.isArray(source.rows) || source.rows.length > 32) invalid();
  const seen = new Set<string>();
  const rows: LocalOwnerRun[] = [];
  for (const item of source.rows) {
    const row = object(item);
    if (!row || !exact(row, ["run_id", "root_id", "parent_run_id", "pool", "model", "signal", "rc", "recorded_at_unix_s"])) invalid();
    const runId = idOrNull(row.run_id), rootId = idOrNull(row.root_id),
      parentId = idOrNull(row.parent_run_id), pool = labelOrNull(row.pool, 32),
      model = labelOrNull(row.model, 80), signal = labelOrNull(row.signal, 32);
    const rc = row.rc === null ? null : typeof row.rc === "number" && Number.isInteger(row.rc) &&
        row.rc >= -1024 && row.rc <= 1024 ? row.rc : undefined;
    const stamp = row.recorded_at_unix_s === null ? null : count(row.recorded_at_unix_s) &&
      row.recorded_at_unix_s >= 1_600_000_000 ? row.recorded_at_unix_s : undefined;
    if (!runId || rootId === undefined || parentId === undefined ||
        pool === undefined || model === undefined || signal === undefined ||
        rc === undefined || stamp === undefined || seen.has(runId)) invalid();
    seen.add(runId);
    rows.push({
      run_id: runId, root_id: rootId, parent_run_id: parentId,
      pool, model, signal, rc, recorded_at_unix_s: stamp,
    });
  }
  return {
    schema: "mastermind.local_fabric_owner_runs.v1",
    scope: "LOCAL_MACHINE_OWNER",
    basis: "RETAINED_LEDGER_OUTCOMES_ONLY",
    observed_at_unix_s: source.observed_at_unix_s as number,
    coverage: {
      machine_wide_fleet_complete: false, source_records_complete: coverage.source_records_complete as boolean,
      file_tail_bytes: coverage.file_tail_bytes as number, total_records: null, active_workers: null,
    },
    rows,
  };
}
