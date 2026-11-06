import { describe, expect, it } from "vitest";
import fixture from "../fixtures/fabric-catalog-m2-status-observation-20261014.json";
import { decodeFabricCatalog } from "./catalog-contract";
import { decodeAttendedStatus } from "./attended-status";

/**
 * Two actual M2 local MCP fabric_status responses, selected by the existing
 * machine owner; metadata only. This is NOT an OAuth-authorized app read,
 * a complete run census, or a reason to enable the optional app producer.
 */
describe("installed M2 Fabric status -> strict OS catalog contract", () => {
  it("retains real accepted and unaccepted statuses without inventing all-fleet coverage", () => {
    const catalog = decodeFabricCatalog(fixture);
    expect(catalog.schema).toBe("mastermind.attended_fabric_catalog.v1");
    expect(catalog.availability).toBe("PARTIAL");
    expect(catalog.source.scope).toBe("EXACT_RUN_SET");
    expect(catalog.source.revision).toBeNull();
    expect(catalog.source.atomic).toBe(false);
    expect(catalog.coverage.scan_complete).toBe(false);
    expect(catalog.coverage.candidate_count).toBeNull();
    expect(catalog.coverage.omitted_count).toBeNull();
    expect(catalog.items).toHaveLength(2);
    const accepted = catalog.items.find(row => row.status?.accepted === true);
    const unaccepted = catalog.items.find(row => row.status?.accepted === false);
    expect(accepted?.status?.acceptance_state).toBe("ACCEPTED");
    expect(unaccepted?.status?.acceptance_state).toBe("NOT_ACCEPTED");
    expect(accepted?.status?.state).toBe("TERMINAL");
    expect(unaccepted?.status?.state).toBe("TERMINAL");
    expect(unaccepted?.status?.result_available).toBe(true);
    for (const row of catalog.items) {
      expect(row.status?.run_id).toBe(row.run_id);
      expect(decodeAttendedStatus(row.status, {
        runId: row.run_id, rootId: row.status!.root_id!,
      }).run_id).toBe(row.run_id);
      expect(JSON.stringify(row)).not.toMatch(/stdout|credential|prompt|authorization|controller_path/i);
    }
  });

  it("refuses elevating an exact-run sample into complete fleet coverage", () => {
    const malformed = structuredClone(fixture);
    malformed.availability = "AVAILABLE";
    expect(() => decodeFabricCatalog(malformed)).toThrow("FABRIC_CATALOG_INVALID");
  });

  it("refuses contradictions in actual status identity and acceptance on requalification", () => {
    const mismatch = structuredClone(fixture);
    mismatch.items[0].status!.run_id = "different-run";
    expect(() => decodeFabricCatalog(mismatch)).toThrow("FABRIC_CATALOG_INVALID");
    const contradictory = structuredClone(fixture);
    contradictory.items[0].status!.accepted = true;
    contradictory.items[0].status!.acceptance_state = "NOT_ACCEPTED";
    expect(() => decodeFabricCatalog(contradictory)).toThrow("FABRIC_CATALOG_INVALID");
  });
});
