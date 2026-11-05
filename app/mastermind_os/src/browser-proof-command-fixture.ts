/** Test-only ready composer. Imported only by browser-proof, never the product entry. */
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type { EffectReceipt, OperationPointer, PendingPointerStore } from "./orchestration/operation-controller";

export function createFixtureCommandBinding(store: PendingPointerStore): OrchestratorCommandBinding {
  let sequence = 0;
  // No transport exists: every command settles as a synthetic refusal, including recovery.
  const refuse = async (pointer: OperationPointer): Promise<EffectReceipt> => ({
    ...pointer, disposition: "refused",
  });
  return {
    port: {
      context: () => ({ principalScope: "source-fixture-composer", generation: "fixture-1" }),
      prepare: intent => ({ operationKey: `source-fixture-command-${++sequence}`, kind: intent.kind, targetKey: intent.targetKey }),
      submit: refuse,
      readOperation: refuse,
    },
    store,
    getView: () => ({
      projects: [{ ref: "source-fixture-project", label: "SOURCE FIXTURE · Project" }],
      profiles: [
        { ref: "governed_project", label: "SOURCE FIXTURE · Planned project" },
        { ref: "native_research_only", label: "SOURCE FIXTURE · One read-only task" },
      ],
      frontierModels: [{ ref: "fixture-ceo", label: "SOURCE FIXTURE · CEO choice" }],
      session: null,
    }),
    subscribe: () => () => {},
    makeLaunchIntent: form => ({ kind: "launch", targetKey: "source-fixture-launch", payload: { ...form } }),
    makeMessageIntent: () => null,
    makeStopIntent: () => null,
  };
}
