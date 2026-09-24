# Wake PR3 / WP-TW2 — Current Writer Endpoint Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Parent plan:** `docs/superpowers/plans/2026-08-29-wake-pr3-runtime-completion.md`  
**Operation:** `wake-pr3-wptw2-runtime-completion-plan-20260829-sol-001`  
**Protected reconciliation basis:** current protected source includes MAS-237 RuntimeBinding projection #257 at `75b90cfeb4752d2a356a463b351382c1e0c25cb1`, Skillpack v1.0.1 / bootstrap-major 1  
**Capability:** RECORDS_ONLY / no runtime authority

## 1. Narrow precedence

This amendment records the current-writer identity problem that W3C must solve before provider mutation. The later sibling record `2026-08-29-wake-pr3-native-delivery-owner-correction.md` is the controlling implementation-owner ruling wherever this amendment's earlier W3A wording differs.

Current controlling law is:

- exact Codex thread identity is necessary but not sufficient current-writer proof;
- the preferred canonical provider writer is the already-owned worker-local Operator Harness generation (`CodexOperatorAdapter` / WorkerBroker path), not a fresh standalone App Server;
- W3A stays on the SAME logical #250 carrier but must be repaired toward that existing current-writer owner;
- W3B remains transport/persistence defense-in-depth and is not the final provider-effect owner;
- W3C remains held until exact current writer/generation/session evidence is proven at action time.

All parent-plan no-rebuild, effect-unknown, target-acknowledgement and completion boundaries remain controlling.

## 2. Current first-party Codex finding

Current first-party Codex behavior distinguishes two materially different facts:

1. a persisted Codex thread/native handle can be loaded or resumed by an App Server process;
2. the same persisted thread identity does not by itself prove which process/generation is the current authorized writer for the live governed task.

Therefore:

> **Exact Codex thread identity is necessary but is not sufficient proof of exact current writer identity.**

A fresh standalone App Server that can load/resume the same persisted thread must not be treated as the current writer merely because the returned thread id matches. Starting a turn there while another governed generation may still own the task violates Mastermind's one-writer/effect-unknown law.

### 2.1 First-party local control transport is only an optional already-running-writer seam

Current first-party `codex app-server` exposes supported local Unix-socket control transport. That may be useful only for a genuinely already-running App Server writer whose ownership is independently proven. The default socket path alone is never identity and absence of a socket never authorizes daemon bootstrap/restart or a replacement writer.

The accepted Mastermind path is stronger where the Operator Harness owns the current generation: protected source can read `active_operator_binding_facts(...)` from the existing Runtime/OHF owner and project the RuntimeBinding without persisting a second registry. W3C should consume those canonical source facts and route provider mutation back through the existing WorkerBroker / worker-local `CodexOperatorAdapter` generation.

For any alternate already-running App Server seam, action-time proof would still need to bind endpoint/process generation and the loaded native thread to the accepted current writer before provider I/O. No GUI/title/recency fallback.

## 3. W3A interpretation — SAME #250 carrier, current implementation rejected

W3A remains the same logical operation/carrier, but its current process-spawning implementation is **not** an acceptable merge-ready production primitive.

PR #250 currently starts its own `AppServerClient` and cold-resumes the supplied thread. That is useful historical RED/protocol evidence only; it does not satisfy current-writer ownership and must not land in that form.

Repair the SAME #250 carrier toward this capability:

```text
trusted current RuntimeBinding + active OHF source facts
-> exact existing ProcessGenerationRef / worker-local generation
-> WorkerBroker / RemoteCodexOperatorAdapter attention operation
-> worker-local CodexOperatorAdapter revalidates exact generation + provider_session_id/current writer immediately before provider I/O
-> already-owned state.client performs one bounded attention turn/start
-> accepted/delivered observation
```

W3A MUST NOT:

- call `AppServerClient.start()` to create another writer;
- independently `thread/resume`, `thread/start` or `thread/fork` a persisted task;
- discover a task by title, timestamp, OCR, window order or newest-session heuristic;
- select/rotate RuntimeBinding or start/resume a generation;
- bypass an unresolved/effect-unknown current writer;
- make Agent Relay/Wake ledger the provider-effect owner;
- become production-armed by merge alone.

The repaired W3A provider-local boundary must preserve current Operator Harness effect-unknown law: once provider write may have begun, ambiguity is non-retryable until same-carrier reconciliation.

## 4. W3C current-writer gate

Before W3C may issue the first real provider mutation, trusted composition must prove all of:

1. the target `RuntimeBinding` is the current accepted binding for the logical session alias;
2. the binding's native handle/provider-session coordinate matches current canonical OHF source facts;
3. the exact current Worker/Attempt/process generation is identified from the existing Runtime/OHF owner, not invented from Slack/model/browser state;
4. the selected worker-local `CodexOperatorAdapter` generation/state is still current and matches those coordinates immediately before provider I/O;
5. no unresolved prior writer/effect exists for the same governed operation that would make another submission unsafe;
6. provider mutation uses the already-owned generation/client rather than a cold-resumed fresh process.

If current writer/generation/session cannot be proven, use the current typed fail-closed reconciliation state (for example `SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED` or the accepted equivalent). No provider call, fresh App Server, daemon bootstrap, GUI fallback, retry or failover is authorized.

## 5. MAS-237 / RuntimeBinding relationship

Protected #257 now provides the canonical **storeless** RuntimeBinding projection over existing Runtime/OHF source facts:

- `active_operator_binding_facts(...)` reads the accepted current Operator Harness source in one caller-owned snapshot;
- `project_runtime_binding(...)` derives the session alias/binding id/generation/native provider-session handle/account/surface without creating another persistence plane.

The projected `RuntimeBinding` is intentionally not a new writer-endpoint registry. W3C/current-writer delivery must combine it with current authoritative OHF generation/source facts and then revalidate inside the worker-local `CodexOperatorAdapter` immediately before provider mutation.

Do **not** widen RuntimeBinding persistence merely to duplicate worker/process/generation data already owned by Runtime/OHF. If a different already-running App Server seam is ever adopted, its endpoint/process proof must be derived from existing runtime-only ownership and remain non-persisted unless a separately adjudicated owner change is required.

## 6. Canary falsifier

A real W3C canary fails if any of the following is true:

- it starts a fresh standalone App Server and merely proves the same thread id;
- it performs an independent cold `thread/resume` before provider mutation;
- it bootstraps/restarts a daemon because an expected socket is absent;
- it cannot tie the chosen writer to the exact current RuntimeBinding + active OHF process generation;
- two processes/generations can concurrently issue turns to the same governed task;
- the old active writer is effect-unknown when another write begins;
- generation/provider-session/native-handle/Attempt identity changes after route derivation and before provider I/O;
- success is inferred from persisted/resumed history instead of one turn on the exact current owned generation.

The canary passes this gate only when the provider write occurs through the exact already-owned current writer and duplicate observation/restart produces zero second submission.

## 7. Do not rebuild

Do not create a new writer registry, thread database, GUI/session selector, daemon, provider lifecycle owner or retry system to satisfy this amendment. Reuse canonical RuntimeBinding / Runtime/OHF source facts / WorkerBroker / `CodexOperatorAdapter` ownership and extend only the smallest attention operation needed on the SAME W3A carrier.
