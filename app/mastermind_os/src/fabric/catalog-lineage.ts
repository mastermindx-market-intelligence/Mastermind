import { CATALOG_LIMIT, type CatalogRow } from "./catalog-contract";

/** A claim about rows in one bounded observation, never all native M2 workers. */
export type RunLineageState =
  | "ROOT_PARENT_LABEL"
  | "OBSERVED_ANCESTRY"
  | "PARENT_OUTSIDE_RESPONSE"
  | "PARENT_STATUS_UNAVAILABLE"
  | "ROOT_UNVERIFIED"
  | "PARENT_UNVERIFIED"
  | "ROOT_CONFLICT"
  | "PARENT_CYCLE"
  | "DUPLICATE_ID"
  | "STATUS_UNAVAILABLE";

export interface RunLineage {
  state: RunLineageState;
  /** Ordered observed labels/edges only, not a proof of worker START or permission. */
  path: string[];
  /** True only when a contiguous parent chain terminates at the declared root label. */
  contiguous_to_root_label: boolean;
  /** Count of source-declared edges from that label; unknown for partial chains. */
  observed_depth: number | null;
  /** Parent run ID was supplied and differs from the original correlation root label. */
  declared_nested_parent: boolean;
}

/**
 * Qualify ancestry using only rows in this one authorized catalog response.
 * A root label is a correlation anchor, not necessarily a runnable worker or
 * principal. Absent/filtered ancestors never become source-verified workers.
 * No result, attempt, provider, user, authorization or retry is inferred.
 */
export function observedRunLineage(rows: readonly CatalogRow[]): Map<string, RunLineage> {
  const source = rows.slice(0, CATALOG_LIMIT);
  const byId = new Map<string, CatalogRow>();
  const duplicates = new Set<string>();
  for (const row of source) {
    if (byId.has(row.run_id)) duplicates.add(row.run_id);
    byId.set(row.run_id, row);
  }
  const state = (kind: RunLineageState, path: string[], nested = false): RunLineage => ({
    state: kind, path, contiguous_to_root_label: false, observed_depth: null,
    declared_nested_parent: nested,
  });
  const memo = new Map<string, RunLineage>();

  function resolve(runId: string, pathIds: Set<string>): RunLineage {
    if (duplicates.has(runId)) return state("DUPLICATE_ID", [runId]);
    if (pathIds.has(runId)) return state("PARENT_CYCLE", [runId]);
    const cached = memo.get(runId);
    if (cached) return cached;
    const row = byId.get(runId);
    if (!row?.status) return state("STATUS_UNAVAILABLE", [runId]);
    const status = row.status;
    if (!status.root_id) return state("ROOT_UNVERIFIED", [runId]);
    if (!status.parent_run_id) return state("PARENT_UNVERIFIED", [runId]);
    const nested = status.parent_run_id !== status.root_id;
    if (status.parent_run_id === runId) return state("PARENT_CYCLE", [runId], nested);
    if (status.parent_run_id === status.root_id) {
      const result: RunLineage = {
        state: "ROOT_PARENT_LABEL",
        path: [status.root_id, runId],
        contiguous_to_root_label: true,
        observed_depth: 1,
        declared_nested_parent: false,
      };
      memo.set(runId, result);
      return result;
    }
    const parent = byId.get(status.parent_run_id);
    if (!parent) return state("PARENT_OUTSIDE_RESPONSE", [status.parent_run_id, runId], nested);
    if (!parent.status) return state("PARENT_STATUS_UNAVAILABLE", [status.parent_run_id, runId], nested);
    if (parent.status.root_id !== status.root_id) {
      return state("ROOT_CONFLICT", [status.parent_run_id, runId], nested);
    }
    const next = new Set(pathIds);
    next.add(runId);
    const resolved = resolve(status.parent_run_id, next);
    const chain = [...resolved.path, runId].slice(0, CATALOG_LIMIT + 1);
    if (!resolved.contiguous_to_root_label) {
      return state(resolved.state, chain, nested);
    }
    const result: RunLineage = {
      state: "OBSERVED_ANCESTRY", path: chain,
      contiguous_to_root_label: true,
      observed_depth: (resolved.observed_depth ?? 0) + 1,
      declared_nested_parent: true,
    };
    memo.set(runId, result);
    return result;
  }

  const output = new Map<string, RunLineage>();
  for (const row of source) output.set(row.run_id, resolve(row.run_id, new Set()));
  return output;
}
