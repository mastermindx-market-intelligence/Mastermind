# LANE — Execution Return Path (Director F)

Branch `t3/execution-return-path` (base `7bbac9278`, worktree t3-5465a765).
Mission: T3_HANDOFF_V2 DONE_WHEN row 5 — the source-side return path: when a
T3-owned coding attempt settles, ONE authoritative `mastermind.execution_return/v1`
record is projected and delivered back to the ORIGINAL Hermes teammate
conversation/project, with delivery receipts distinct from acceptance.

## Deliverables and proof status

| Deliverable | Path | Status |
| --- | --- | --- |
| Pure v1 projector + vocabulary owner | `control_plane/execution_return_projection.py` | **PROVEN_BY_TEST** (29 tests) |
| Native return delivery (idempotent, receipt-closed) | `integrations/session_bridge/hermes_native_return.py` | **PROVEN_BY_TEST against injected fakes** (14 tests). The LIVE Secretary-composition session path (`SecretaryNativeSendTransport` over a real `HermesNativeSession`) is **SOURCE_ONLY** — tests never contact the live Hermes gateway, per lane constraint. |
| TS fail-closed mirror + colocated vitest | `app/mastermind_os/src/hermes-native/execution-return-contract.ts` (+ `.test.ts`) | **PROVEN_BY_TEST** (9 tests, includes fixture parity + digest parity on the Python-produced sample) |
| Cross-language fixtures | `integrations/mmos/fixtures/execution_return_v1/{vocabularies,sample_record,sample_receipt}.json` | **PROVEN_BY_TEST** (asserted equal by BOTH the Python and TS suites) |
| Executive runtime wiring of the projection | — (recommendation only; `executive_runtime.py` is a hard no-edit for this lane) | **SOURCE_ONLY** (named below) |

## Exact commands run (all green)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_execution_return_projection.py                  # 29 passed
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_session_bridge_native_return.py                 # 14 passed
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_execution_return_projection.py \
  tests/test_session_bridge_native_return.py                 # 43 passed
cd app/mastermind_os
npx vitest run src/hermes-native/execution-return-contract.test.ts   # 9 passed (1 file)
npx vitest run src/hermes-native/                                     # 91 passed (8 files) — no Director-B regression
npx tsc -b --pretty false                                             # clean exit 0
```

Negative cases proven (both languages where applicable): wrong namespace →
`NAMESPACE_MISMATCH`; missing/malformed seal → `SEAL_MISSING`; missing any
original-binding field → `ORIGINAL_BINDING_MISSING`; acceptance forgery
(input claims `accepted` → output stays `not_accepted`, flagged
`acceptance_claim_refused`); ambiguous send → `unknown` receipt and **no
second send ever** (transport call count stays 1); redelivery → prior
receipt verbatim; unknown/partial GitHub evidence → honest stage
(`pr_open`/`result_only`, `checks_state: unknown`), never green; stage
re-forged with a *matching* digest → refused by the stage-vs-evidence
invariant; conversation mismatch → refused before dispatch.

## Contract summary (v1)

- Stage ladder (closed, proven-only): `result_only → branch_pushed → pr_open →
  checks_green | checks_failed → merged → installed_unknown`. `checks_green`
  requires EVERY observed check concluded success/skipped; a proven merge plus
  an *unproven* installation claim is `installed_unknown` (never "installed").
- `acceptance` is closed to exactly `not_accepted` in v1. No producer of
  `accepted` exists in this generation; a future acceptance owner mints its
  own schema revision.
- Digest: sha256 over canonical JSON (sorted keys, no spaces, raw UTF-8) of
  the record minus the two derived identity fields; `return_id =
  "execret-" + digest[:32]`. Canonicalization is byte-identical in Python and
  TS (proven on the committed sample, unicode included).
- Delivery receipt: `mastermind.execution_return_delivery/v1`, states
  `delivered | unknown | refused`; `submission_id = "execret-" +
  sha256(return_digest, conversation_id)[:32]` — deterministic, so the native
  seam recognizes a replayed delivery as the SAME submission. Delivered
  requires a transport ref; unknown cannot carry one; only refused carries a
  refusal code. All three states are terminal for the deliverer: redelivery
  returns the prior receipt and never sends again.

## Reuse decisions (compose, not duplicate)

- `control_plane/executive_terminal_return.py` — the "pure projection of a
  sealed terminal result, typed refusals, no I/O" law; followed, not copied.
- `control_plane/teamlink_contracts.py` + `teamlink-contract.ts` —
  vocabulary-closure style, deterministic id mint (`tlm-` → `execret-`),
  unknown-outside-the-retry-law, and the TS-mirror/fixture-parity testing
  pattern (B3's precedent) reused directly.
- `integrations/session_bridge/hermes_native.py` — the EXISTING send seam
  (`HermesNativeSession.request(binding, native_request)`); my adapter is a
  duck-typed narrow port over it. Native request shape
  `{operation: "submit", target, submission_id, text}` adopted from
  `control_plane/native_continuation.py::_hermes_native_request` — no new
  transport verb invented.
- `control_plane/t3_execution_adapter.py` (read-only, per lane rules) —
  consumed shapes: `T3ThreadLaunchReceipt` (thread_id/run_id/project_id/
  request_namespace/client_request_id), `T3ResultReference`,
  `result_ledger_entry(run_id)`, `T3AdapterRunState.binding`, and the
  namespace law (`t3_request_namespace`: identity is (authenticated
  namespace, key)). **Not edited.**
- `control_plane/child_execution_contracts.py` — `ExecutionBinding` v1.1
  (`caller_namespace`, `operation_key`, `t3_*` refs) as the source of the
  attempt-side namespace/T3 identity facts.

No leaves were delegated to Flash workers: the contract work is small and
interlocking; direct implementation was cheaper than handoff + re-verification
(the mission permits but does not require delegation).

## Gaps for the integrator (Director C / executive seam)

1. **Original-requester carriage is missing upstream (blocking for live use).**
   `ChildExecutionRequest` and `ExecutionBinding` v1.1 carry
   `root_ref`/`logical_child_key`/`operation_key`/T3 refs but **no Hermes
   teammate id / conversation id / project id**. My projector correctly
   refuses (`ORIGINAL_BINDING_MISSING`) without them. Recommendation: extend
   `ChildExecutionRequest` (a v1.2 optional block, sparse like the v1.1
   fields — a v1 request digests identically) so the ORIGINAL requester
   binding is persisted at admission and re-readable at settlement.
2. **Recommended single wiring point (do NOT scatter calls).** The projection
   belongs at the terminal seal of a t3-native attempt:
   `control_plane/executive_runtime.py::Runtime.complete_attempt` /
   `Runtime._terminal` (line ~21292–21415) — the one point where the seal
   digest exists, the attempt is durably terminal, and the T3
   `T3AdapterRunState` (binding + `result_ledger_entry`) joins by run id.
   Post-commit (after the `JOB_COMPLETED` event is durably written), in the
   same completion path: read the sealed facts + freshly read GitHub evidence
   (each field unknown-safe), call `project_execution_return`, then
   `HermesExecutionReturnDeliverer.deliver` through `SecretaryNativeSendTransport`
   bound to the original Hermes selection. Persist the receipt in the
   Executive transaction (my in-process ledger is request-scoped by design —
   no new database from this lane).
3. **GitHub lifecycle evidence reader does not exist.** The repo has review
   readers (`github_review_result_reader.py`) but no reader for a coding
   attempt's OWN branch/PR/checks/merge state. Until one exists, wire the
   projector with whatever the `WorkerResult` git manifest carries and leave
   the rest null — the record degrades honestly (`result_only`/`branch_pushed`
   …) and never claims green from missing evidence.
4. **Native submit seam result contract.** `SecretaryNativeSendTransport`
   maps the native statuses ADMITTED/OBSERVED(+admission) → delivered,
   NOT_SUBMITTED/REFUSED/UNAVAILABLE → refused, EFFECT_UNKNOWN/malformed →
   unknown, and the pre-dispatch `BridgeError` guard codes
   (`binding_unavailable`, `ingress_unavailable`, `backend_unavailable`) →
   clean refusal. If the native port's admitted status vocabulary changes,
   that mapping (and only that mapping) needs updating.
5. **No auto-retry/reconciliation owner.** After an `unknown` receipt the
   deliverer is deliberately inert; reconciliation of the ORIGINAL
   `submission_id` is an Executive-runtime concern (read the native
   conversation by id, observe whether the submission landed, then append the
   observed state — never re-send blind).

## Effects boundary

Source-only lane: no live Hermes gateway contact, no Executive writes, no
push, no PR, paper-only. Nothing here restarts or reconfigures any service;
`executive_runtime.py`, `worker_adapter.py`, `executive_worker_routes.json`,
`t3_execution_adapter.py`, `src-tauri/**`, React/CSS and live profiles are
untouched.
