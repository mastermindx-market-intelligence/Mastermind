import { describe, expect, it } from "vitest";
import type { CatalogRow } from "./catalog-contract";
import ownerSample from "../fixtures/fabric-catalog-m2-status-observation-20261014.json";
import { decodeFabricCatalog } from "./catalog-contract";
import { observedRunLineage } from "./catalog-lineage";

function run(id: string, parent: string | null, root = "root-label"): CatalogRow {
  return {
    run_id: id, controller_modified_at: null, reason_code: null,
    status: {
      schema: "mastermind.fabric_task_status.v1", run_id: id,
      root_id: root, parent_run_id: parent, state: "TERMINAL",
      rc: 0, signal: "ok", result_available: true, result_bytes: 42,
      accepted: false, accepted_by: null, acceptance_state: "NOT_ACCEPTED",
      acceptance_reason: "NO_OUTCOME",
    },
  };
}
describe("strict, bounded attended-run lineage", () => {
  it("keeps two actual M2 owner statuses as directly root-correlated, not fleet completeness", () => {
    const fixture = decodeFabricCatalog(ownerSample);
    const result = observedRunLineage(fixture.items);
    expect(result.size).toBe(2);
    for (const row of fixture.items) {
      const item = result.get(row.run_id)!;
      expect(item.state).toBe("ROOT_PARENT_LABEL");
      expect(item.contiguous_to_root_label).toBe(true);
      expect(item.path).toEqual([row.status!.root_id, row.run_id]);
      expect(item.observed_depth).toBe(1);
      expect(item.declared_nested_parent).toBe(false);
    }
    expect(fixture.source.scope).toBe("EXACT_RUN_SET");
    expect(fixture.coverage.scan_complete).toBe(false);
  });

  it("proves only contiguous source-declared parent chains within the supplied run set", () => {
    const rows = [run("child", "middle"), run("root-worker", "root-label"), run("middle", "root-worker")];
    const tree = observedRunLineage(rows);
    expect(tree.get("root-worker")).toMatchObject({ state: "ROOT_PARENT_LABEL", observed_depth: 1 });
    expect(tree.get("middle")).toMatchObject({ state: "OBSERVED_ANCESTRY", observed_depth: 2 });
    expect(tree.get("child")).toMatchObject({
      state: "OBSERVED_ANCESTRY", path: ["root-label", "root-worker", "middle", "child"],
      observed_depth: 3, declared_nested_parent: true, contiguous_to_root_label: true,
    });
  });

  it("labels an outside-response parent as unknown, not absent or idle", () => {
    const tree = observedRunLineage([run("child", "parent-outside")]);
    expect(tree.get("child")).toMatchObject({
      state: "PARENT_OUTSIDE_RESPONSE", path: ["parent-outside", "child"],
      observed_depth: null, contiguous_to_root_label: false, declared_nested_parent: true,
    });
  });

  it("never upgrades an incomplete parent chain through a downstream child", () => {
    const rows = [run("child", "middle"), run("middle", "outside")];
    const tree = observedRunLineage(rows);
    expect(tree.get("child")).toMatchObject({
      state: "PARENT_OUTSIDE_RESPONSE", path: ["outside", "middle", "child"],
      contiguous_to_root_label: false,
    });
  });

  it("does not attach unknown roots or parents", () => {
    const nullRoot = run("unknown-root", "some-parent");
    nullRoot.status!.root_id = null;
    const nullParent = run("unknown-parent", null);
    const noStatus: CatalogRow = { run_id: "unreadable", status: null,
      reason_code: "STATUS_UNAVAILABLE", controller_modified_at: null };
    const relations = observedRunLineage([nullRoot, nullParent, noStatus]);
    expect(relations.get("unknown-root")?.state).toBe("ROOT_UNVERIFIED");
    expect(relations.get("unknown-parent")?.state).toBe("PARENT_UNVERIFIED");
    expect(relations.get("unreadable")?.state).toBe("STATUS_UNAVAILABLE");
    for (const v of relations.values()) expect(v.contiguous_to_root_label).toBe(false);
  });

  it("does not join different original roots, even when parent run IDs happen to match", () => {
    const relations = observedRunLineage([run("child", "parent", "root-a"), run("parent", "root-b", "root-b")]);
    expect(relations.get("child")).toMatchObject({
      state: "ROOT_CONFLICT", path: ["parent", "child"],
      contiguous_to_root_label: false, observed_depth: null,
    });
  });

  it("quarantines cycles and self-parenting without an infinite walk", () => {
    const relations = observedRunLineage([run("x", "y"), run("y", "x"), run("z", "x"), run("self", "self")]);
    for (const key of ["x", "y", "z", "self"]) {
      expect(relations.get(key)?.state).toBe("PARENT_CYCLE");
      expect(relations.get(key)?.contiguous_to_root_label).toBe(false);
    }
  });

  it("does not join through a parent whose status cannot be established", () => {
    const noStatus: CatalogRow = { run_id: "parent", status: null, reason_code: "SOURCE_CHANGED",
      controller_modified_at: null };
    const relations = observedRunLineage([run("child", "parent"), noStatus]);
    expect(relations.get("child")?.state).toBe("PARENT_STATUS_UNAVAILABLE");
  });

  it("bounds traversal and never promotes duplicate identity", () => {
    const duplicates = observedRunLineage([run("same", "root-label"), run("same", "root-label")]);
    expect(duplicates.get("same")).toMatchObject({ state: "DUPLICATE_ID", contiguous_to_root_label: false });
    const deep = Array.from({length: 32}, (_, idx) =>
      run(`run-${idx}`, idx === 0 ? "root-label" : `run-${idx - 1}`));
    const chain = observedRunLineage(deep).get("run-31")!;
    expect(chain.observed_depth).toBe(32);
    expect(chain.path).toHaveLength(33);
    expect(observedRunLineage([...deep, run("over-limit", "run-31")]).has("over-limit")).toBe(false);
  });
});
