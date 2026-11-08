// @vitest-environment node
import { it, expect } from "vitest";
import v4 from "./fixtures/current-grants.json";
import v5 from "./fixtures/v5-current-grants.json";
import { decodeCurrentProjectAccess } from "./project-access-current";
it("keeps the original eight grants separate from the v5 ten-action owner", () => {
  const old = decodeCurrentProjectAccess(v4, v4.selection),
    current = decodeCurrentProjectAccess(v5, v5.selection);
  expect(old).toEqual(v4);
  expect(current).toEqual(v5);
  expect(
    old?.availability === "AVAILABLE" &&
      old.grants?.some(
        (row) => String(row.action) === "read_latest_project_data",
      ),
  ).toBe(false);
});
it.each([
  "grant_schema",
  "row_count",
  "data_scope",
  "proposal_scope",
  "sibling_action",
  "extra",
  "foreign_source",
])(
  "refuses malformed/foreign v5 %s without falling back to eight-slot authority",
  (change) => {
    const body = structuredClone(v5);
    if (change === "grant_schema")
      body.grant_schema = "mastermind.workspace_acquisition_bindings.v4";
    else if (change === "row_count") body.grants.pop();
    else if (change === "data_scope") body.grants[9].scope = "PROJECT";
    else if (change === "proposal_scope") body.grants[8].work_ref = "WS:OTHER";
    else if (change === "sibling_action")
      body.grants[9].action = "publish_project_proposal";
    else if (change === "extra") Object.assign(body, { eligible: true });
    else body.source.path = "agentos/workstreams/WS-OTHER.md";
    expect(decodeCurrentProjectAccess(body, v5.selection)).toBeNull();
  },
);
it("does not evaluate array or new grant accessors", () => {
  let reads = 0;
  const body = structuredClone(v5);
  Object.defineProperty(body.grants[9], "supply", {
    enumerable: true,
    get() {
      reads++;
      return "SUPPLIED";
    },
  });
  expect(decodeCurrentProjectAccess(body, v5.selection)).toBeNull();
  expect(reads).toBe(0);
  const other = structuredClone(v5);
  Object.defineProperty(other.grants, "9", {
    enumerable: true,
    get() {
      reads++;
      return v5.grants[9];
    },
  });
  expect(decodeCurrentProjectAccess(other, v5.selection)).toBeNull();
  expect(reads).toBe(0);
});
