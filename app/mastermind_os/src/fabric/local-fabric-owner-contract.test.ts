import { describe, expect, it } from "vitest";
import { decodeLocalOwnerSnapshot, MAX_IMPORT_BYTES } from "./local-fabric-owner-contract";
import { fixtureSnapshot } from "./local-fabric-owner-fixture";

describe("M2 local machine-owner snapshot — offline format only", () => {
  it("accepts a small retained ledger snapshot without claiming fleet state", () => {
    const record = decodeLocalOwnerSnapshot(fixtureSnapshot());
    expect(record.scope).toBe("LOCAL_MACHINE_OWNER");
    expect(record.rows).toHaveLength(3);
    expect(record.coverage.active_workers).toBeNull();
    expect(record.coverage.total_records).toBeNull();
    expect(record.coverage.machine_wide_fleet_complete).toBe(false);
  });

  it("refuses a machine owner's records disguised as an OS user-authorized source", () => {
    const data = fixtureSnapshot();
    for (const spoofed of [
      { ...data, scope: "EXACT_RUN_SET" },
      { ...data, schema: "mastermind.attended_fabric_catalog.v1" },
      { ...data, basis: "LIVE_CONTROLLER_STATUS" },
      { ...data, extra: "unsafe" },
    ]) expect(() => decodeLocalOwnerSnapshot(spoofed)).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
  });

  it("never accepts raw outputs, credentials, hidden fields or fake acceptance in a row", () => {
    for (const extra of [{ key: "API_KEY" }, { prompt: "private" },
      { accepted: true }, { state: "RUNNING" }, { stdout: "private" }]) {
      const data = fixtureSnapshot();
      expect(() => decodeLocalOwnerSnapshot({
        ...data, rows: [{ ...data.rows[0], ...extra }],
      })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
    }
  });

  it("refuses unsafe identifiers, cross-row duplication, and overbound lists", () => {
    const data = fixtureSnapshot();
    expect(() => decodeLocalOwnerSnapshot({
      ...data, rows: [{ ...data.rows[0], run_id: "<script>" }],
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
    expect(() => decodeLocalOwnerSnapshot({
      ...data, rows: [data.rows[0], { ...data.rows[0] }],
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
    expect(() => decodeLocalOwnerSnapshot({
      ...data, rows: Array.from({ length: 33 }, (_, i) => ({
        ...data.rows[0], run_id: "run-" + i,
      })),
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
  });

  it("requires exact unknown/partial coverage instead of active or acceptance claims", () => {
    const data = fixtureSnapshot();
    expect(() => decodeLocalOwnerSnapshot({
      ...data, coverage: { ...data.coverage, machine_wide_fleet_complete: true },
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
    expect(() => decodeLocalOwnerSnapshot({
      ...data, coverage: { ...data.coverage, active_workers: 0 },
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
    expect(() => decodeLocalOwnerSnapshot({
      ...data, coverage: { ...data.coverage, file_tail_bytes: 400_000 },
    })).toThrow("LOCAL_FABRIC_SNAPSHOT_INVALID");
  });

  it("never returns arbitrary source fields even after successful decode", () => {
    const data = fixtureSnapshot();
    const decoded = decodeLocalOwnerSnapshot(data);
    expect(Object.keys(decoded.rows[0]).sort()).toEqual([
      "model", "parent_run_id", "pool", "rc", "recorded_at_unix_s", "root_id", "run_id", "signal",
    ]);
    expect(MAX_IMPORT_BYTES).toBe(65_536);
  });
});
