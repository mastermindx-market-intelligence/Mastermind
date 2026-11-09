import { expect, it } from "vitest";
import { projectDeclaredDependencies as project } from "./office-dependencies";
const known = [{ workRef: "WS:ONE", title: "One" }];
const card = () => ({
  work_ref: "WS:ONE",
  agent_os: {
    workstream: "ONE",
    source: "agentos/workstreams/WS-ONE.md",
    state: "blocked",
    depends_on: ["WS:TWO"],
    unmet_dependencies: ["WS:TWO"],
  },
});
it("retains an outside endpoint without inventing a row or ranking", () => {
  const rows = project([card()], known);
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    state: "AVAILABLE",
    declared: ["WS:TWO"],
    unmet: ["WS:TWO"],
  });
});
it("distinguishes legitimate empty dependencies from missing metadata", () => {
  const c = card();
  c.agent_os.depends_on = [];
  c.agent_os.unmet_dependencies = [];
  expect(project([c], known)[0]).toMatchObject({
    state: "AVAILABLE",
    declared: [],
    unmet: [],
  });
  expect(
    project(
      [{ ...c, agent_os: { ...c.agent_os, source: null, state: null } }],
      known,
    )[0],
  ).toMatchObject({ state: "UNAVAILABLE", declared: null, unmet: null });
});
it.each([
  { workstream: "OTHER" },
  { source: "agentos/workstreams/WS-OTHER.md" },
  { state: "UNKNOWN" },
  { depends_on: ["WS:TWO", "WS:TWO"] },
  { depends_on: ["WS:ONE"] },
  { depends_on: ["WS:TWO\n"] },
  { unmet_dependencies: ["WS:THREE"] },
  { depends_on: null },
])("withholds malformed graph metadata %j", (change) =>
  expect(
    project(
      [{ ...card(), agent_os: { ...card().agent_os, ...change } }],
      known,
    )[0].state,
  ).toBe("UNAVAILABLE"),
);
it.each([
  { raw: [] },
  { raw: [card(), card()] },
  { raw: [{ ...card(), work_ref: "WS:OTHER" }] },
])("refuses foreign or mismatched collection membership", ({ raw }) =>
  expect(project(raw, known)[0].declared).toBeNull(),
);
it("never invokes a metadata getter", () => {
  let reads = 0;
  const c = card();
  Object.defineProperty(c.agent_os, "source", {
    get() {
      reads++;
      return "agentos/workstreams/WS-ONE.md";
    },
  });
  expect(project([c], known)[0].state).toBe("UNAVAILABLE");
  expect(reads).toBe(0);
});

it("projects only dependency fields, never Runtime navigation operands", () => {
  const rows = project(
    [card()],
    [Object.assign({}, known[0], { rootJobId: "JOB-PRIVATE" })],
  );
  expect(Object.keys(rows[0]).sort()).toEqual(
    [
      "workRef",
      "title",
      "state",
      "source",
      "readiness",
      "declared",
      "unmet",
    ].sort(),
  );
});
