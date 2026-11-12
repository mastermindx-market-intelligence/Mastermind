/** Actual company decoder/projection, with fixture-backed source records.
 * node --experimental-transform-types scripts/qualify_paperclip_connections.mjs
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { registerHooks } from "node:module";

// Match the application's extensionless TS module resolution, without replacing
// any application function or providing a mock decoder/projection.
registerHooks({ resolve(specifier, context, nextResolve) {
  try { return nextResolve(specifier, context); }
  catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" && /^\.\.?\//.test(specifier) && !/\.[a-z]+$/.test(specifier)) {
      return nextResolve(specifier + ".ts", context);
    }
    throw error;
  }
} });
const { decodeCompanyRead } = await import("../app/mastermind_os/src/company/contract.ts");
const { projectCompanyConnections, sameConnections } = await import("../app/mastermind_os/src/company/connections.ts");
const fixture = JSON.parse(await readFile(new URL("../tests/fixtures/paperclip_connections.json", import.meta.url), "utf8"));
const fresh = () => structuredClone(fixture);
let checks = 0;
const check = run => { run(); checks += 1; };
const decoded = decodeCompanyRead(fresh(), { view: "overview" });
check(() => assert.equal(decoded.connections.state, "CURRENT"));
check(() => assert.equal(decoded.connections.relationships.length, 10));
check(() => assert.equal(decoded.connections.dependencies, "NOT_PROJECTED"));
check(() => assert.equal(decoded.connections.executionLineage, "NOT_PROJECTED"));
check(() => assert.equal(decoded.connections.parentConsumption, "NOT_OBSERVED"));
check(() => assert.equal(decoded.connections.consistency, "SEPARATE_READS_NOT_ATOMIC"));
check(() => assert.ok(decoded.connections.helpAvenues.filter(row => ["consult", "delegate", "resume"].includes(row.kind)).every(row => row.state === "NOT_BOUND_IN_THIS_SURFACE")));
const supplied = fresh();
supplied.connections = structuredClone(decoded.connections);
check(() => assert.ok(sameConnections(decodeCompanyRead(supplied, { view: "overview" }).connections, decoded.connections)));
for (const change of [
  graph => { graph.helpAvenues.find(row => row.kind === "delegate").state = "COMMAND_BOUND"; },
  graph => { graph.relationships[0].to.id = "00000000-0000-4000-8000-999999999999"; },
  graph => { graph.executionLineage = "COMPLETE"; },
  graph => { graph.extra = { arbitrary: true }; },
  graph => { graph.relationships.push(structuredClone(graph.relationships[0])); },
]) {
  const candidate = structuredClone(supplied); change(candidate.connections);
  check(() => assert.throws(() => decodeCompanyRead(candidate, { view: "overview" }), /COMPANY_RESPONSE_INVALID/));
}
for (const [kind, field] of [["people", "reportsTo"], ["goals", "parentId"], ["work", "parentId"]]) {
  const candidate = fresh(), [first, second] = fixture.collections.people.items;
  candidate.collections[kind].items = [{ id: first.id, [field]: second.id }, { id: second.id, [field]: first.id }];
  const graph = decodeCompanyRead(candidate, { view: "overview" }).connections;
  check(() => assert.equal(graph.state, "WITHHELD"));
  check(() => assert.equal(graph.relationships.length, 0));
  check(() => assert.ok(graph.findings.some(row => row.code === "VISIBLE_CYCLE")));
}
const partial = fresh();
delete partial.collections.goals;
const partialGraph = decodeCompanyRead(partial, { view: "overview" }).connections;
check(() => assert.equal(partialGraph.state, "PARTIAL"));
check(() => assert.deepEqual(partialGraph.findings, []));
check(() => assert.ok(partialGraph.relationships.some(row => row.state === "OUTSIDE_VISIBLE_WINDOW")));
const hidden = fresh();
hidden.runtimeBindings.push({ ...hidden.runtimeBindings[0], agentId: "00000000-0000-4000-8000-999999999998", profileRef: "private:hidden" });
hidden.projectBindings.push({ projectId: "00000000-0000-4000-8000-999999999999", workRef: "WS:PRIVATE-HIDDEN" });
check(() => assert.ok(!JSON.stringify(projectCompanyConnections(hidden)).includes("private:hidden")));
check(() => assert.ok(!JSON.stringify(projectCompanyConnections(hidden)).includes("PRIVATE-HIDDEN")));
const backlog = fresh(); backlog.capabilities = ["create_backlog"];
check(() => assert.equal(decodeCompanyRead(backlog, { view: "overview" }).connections.helpAvenues.find(row => row.kind === "create_backlog").state, "COMMAND_BOUND"));
console.log(JSON.stringify({ state: "PASS", checks, consumer: "actual TypeScript company decoder", source: "SYNTHETIC", runtime: "NOT_EXERCISED" }));
