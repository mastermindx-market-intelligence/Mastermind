/** Synthetic safe metadata only; never a machine ledger upload. */
export function fixtureSnapshot() {
  return {
    schema: "mastermind.local_fabric_owner_runs.v1",
    scope: "LOCAL_MACHINE_OWNER",
    basis: "RETAINED_LEDGER_OUTCOMES_ONLY",
    observed_at_unix_s: 1792244500,
    coverage: {
      active_workers: null, file_tail_bytes: 12_345,
      machine_wide_fleet_complete: false, source_records_complete: false,
      total_records: null,
    },
    rows: [
      { run_id: "child-01", root_id: "owner-root", parent_run_id: "operator-01",
        model: "MiniMax-M3", pool: "minimax", rc: 0, signal: "ok", recorded_at_unix_s: 1792244400 },
      { run_id: "operator-01", root_id: "owner-root", parent_run_id: "owner-root",
        model: "glm-5.3-flash", pool: "glm", rc: 0, signal: "ok", recorded_at_unix_s: 1792244300 },
      { run_id: "other-root", root_id: "different-root", parent_run_id: "different-root",
        model: null, pool: "bailian", rc: 79, signal: "other", recorded_at_unix_s: null },
    ],
  };
}
