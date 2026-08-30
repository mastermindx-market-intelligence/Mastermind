# Wake PR3 / WP-TW2 — Native Delivery Owner Correction

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Logical planning operation:** `wake-pr3-wptw2-runtime-completion-plan-20260829-sol-001`  
**Carrier:** existing Mastermind PR #249 / branch `sol/wake-pr3-runtime-completion-plan-20260829`  
**Protected basis:** `Mastermind@0604158caca9e3b8a43ec57dd36ca4dadf05198b`, Skillpack v1.0.1 / bootstrap-major 1  
**State:** RECORDS_ONLY / no runtime, provider, host, service, credential, target or production arming effect

## 1. Precedence

This record narrowly supersedes the parent plan's W3A assumption that permanent Wake delivery should construct/start a fresh `scripts.ohf.laboratory.AppServerClient` and `thread/resume` the current native thread. It also narrows the earlier current-writer endpoint amendment where that amendment still described the process-owning W3A implementation as an acceptable merge-ready production primitive.

Everything else remains controlling: Wake persistence/effect-unknown law, W3B's transport-agnostic carrier, no-second-writer law, exact current RuntimeBinding, W3C's existing Agent Relay ownership, production-disarmed defaults and MAS-229's separate consumption ACK.

## 2. Current canonical owner

Protected source already has the one-writer Codex execution owner:

- `control_plane.codex_operator_adapter.CodexOperatorAdapter`
  - `_GenerationState` owns the exact current `AppServerClient`, `provider_session_id`, process identity, attestation and `ProviderWriterState`;
  - `begin_turn(...)` resolves the exact generation, validates the turn/launch decision and performs `turn/start` through that already-owned client;
- `control_plane.remote_codex_operator_adapter.RemoteCodexOperatorAdapter`
  - proxies typed Operator Harness calls over the existing WorkerBroker Unix socket;
  - `begin_turn(...)` forwards exact operation/turn/generation/launch identity to worker-local `ohf-begin-turn`;
- `control_plane.executive_worker_broker`
  - owns the dedicated worker-UID broker operation boundary and accepted OHF operation vocabulary;
- `OperatorHarnessOrchestrator` and Executive Runtime
  - own control-side current-generation/busy/effect-intent ordering and lifecycle correlation.

The concrete App Server process therefore belongs to the existing worker-local generation. Wake must extend this owner rather than create a parallel App Server/session path.

## 3. W3A carrier correction — SAME operation / SAME PR #250

PR #250 remains the same logical W3A carrier. Its current production class is `REQUEST_CHANGES` because it calls `AppServerClient.start()` and therefore creates a second App Server before `thread/resume`.

Do not replace #250, reopen #174, or mint a second Wake transport operation. Repair the same #250 carrier toward this observable capability:

> Given a Wake nudge already routed to a canonically current RuntimeBinding, deliver one attention-only exact-current-writer turn through the existing Operator Harness current generation, while preserving the existing provider-effect owner and refusing any current-generation/session/writer drift before provider I/O.

### 3.1 Required implementation ownership

The final provider mutation must occur inside the existing worker-local Codex owner. An acceptable bounded implementation may add one explicit **attention-only current-generation** operation to the existing Operator Harness / WorkerBroker / `CodexOperatorAdapter` surface and a narrow Wake dispatcher/client adapter over it.

The provider-local operation must:

1. resolve the exact existing `ProcessGenerationRef` / generation state; never create/resume/start a generation;
2. require the RuntimeBinding/native provider session coordinate supplied by trusted composition to match the state's exact `provider_session_id` / current writer identity;
3. prove the state/client/process is still the current writer immediately before the `turn/start` write;
4. refuse if the generation is absent, stale, moved, busy in a way current harness law forbids, or writer identity disagrees;
5. use the already-owned `state.client`; never call `AppServerClient.start()`, `thread/start`, `thread/fork`, cold `thread/resume`, daemon bootstrap, GUI selection or another provider;
6. emit only the fixed bounded Wake attention instruction + opaque Wake identities; it grants no lifecycle/authority and must not masquerade as a normal work/result turn;
7. preserve the current Operator Harness effect-unknown boundary: once provider write may have begun, ambiguity is non-retryable until same-carrier reconciliation;
8. return typed accepted/delivered evidence to existing Wake transport code without inventing `TARGET_ACKNOWLEDGED`.

### 3.2 Control-side path

Control-side composition must remain inside the existing WorkerBroker/remote-adapter/orchestrator ownership chain. A Wake adapter may request the new attention operation only after current RuntimeBinding/current-generation evidence is available. It may not directly reach into `_GenerationState`, bypass the broker, or construct a worker-local provider client from the Agent Relay process.

If the existing orchestrator needs one narrow attention operation/effect-intent classification to preserve current provider-write ordering, extend that owner. Do not make Agent Relay or Wake ledger the provider-effect authority.

### 3.3 Required RED / mutation controls

Before production code for the repaired W3A carrier:

- a second `AppServerClient.start()` or any new App Server process must fail the test;
- wrong/moved `provider_session_id` or native handle must refuse before provider I/O;
- wrong/moved `ProcessGenerationRef` must refuse before provider I/O;
- provider writer/current-generation change between control-side routing and worker-local I/O must be detected at the worker-local boundary;
- `thread/start`, `thread/fork`, independent `thread/resume`, GUI/title/recency/deep-link fallback and alternate-provider failover must be absent;
- lost provider response after write begins must remain effect-unknown and must not produce a second submission on replay;
- current generated Codex V2 text input shape must be honored, including required `text_elements` for `UserInput::Text` when using the current schema;
- `DELIVERED` must not be accepted as target consumption or source resolution.

## 4. Desktop / other already-running App Server writers

The existing OHF generation is the preferred production owner where that is the canonical RuntimeBinding. A different already-running App Server writer may later be addressable through first-party Unix control transport only if MAS-237/current runtime proves endpoint path+inode, owner process generation and exact loaded thread, and the same provider-I/O one-writer checks are enforced.

Absence of such proof is `SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED`. It never authorizes daemon bootstrap/restart or a new standalone writer.

## 5. W3B remains independent and transport-agnostic

W3B remains the SAME logical operation and implementation branch `wptw2-persisted-wake-carrier-20260829-sol-001`. PR #251 is closed, unmerged historical RED/draft evidence only; it must not be revived or treated as the release carrier. As of this correction, the current same-branch release carrier is PR #254. At any later action time, re-read canonical GitHub and continue only the current same-operation/same-branch carrier rather than hard-coding a superseded PR number.

The current W3B release carrier may land independently if current-base, exact-head green and review-clean because it owns only:

`Agent Dialogue observer -> canonical Wake obligation -> Executive events ledger -> persisted dispatcher selection`.

Its current-binding callback is defense-in-depth and must fail closed on movement. It is **not** the final TOCTOU/current-writer authority. The selected native dispatcher must revalidate exact current generation/session/writer at the final worker-local I/O boundary defined above.

## 6. W3C remains held

Agent Relay runtime composition remains held until:

1. MAS-237 current RuntimeBinding/current-writer projection is accepted/protected;
2. repaired current-writer native delivery from the same #250 logical carrier is accepted;
3. W3B is accepted;
4. trusted production `TurnRoutingFacts` derivation exists;
5. current A2 Agent Relay host/enrollment/runtime gates are satisfied.

No second Agent Relay daemon/service and no provider SDK inside the turn observer.

## 7. Completion ruler unchanged

Native continuity is not complete when the current W3A/W3B source carriers merge. Required production proof remains:

```text
valid watched turn
-> deterministic Wake obligation
-> persisted one-attempt delivery identity
-> exact current RuntimeBinding
-> exact current writer generation/session revalidated at worker-local I/O
-> one bounded attention turn through existing owner
-> DELIVERED / DELIVERED_UNACKNOWLEDGED
-> MAS-229 trusted exact target consumption
-> TARGET_ACKNOWLEDGED
-> SOURCE_RESOLVED
```

with zero second writer, zero title/tab hunting, zero blind retry/failover and zero Chairman intervention during the accepted canary.
