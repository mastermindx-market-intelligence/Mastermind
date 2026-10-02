# Mastermind OS — Command Binding Spec v1 (item 3 · option 1: LAUNCH-only over the installed Web-CEO ingress)

**Status:** FROZEN by the seat (op `mastermind-headless-control-closure-20261001-fable-001`, ruling R3, 2026-10-02). **Amended to V1.1 by ruling R4; V1.2 editorial 2026-10-02 (§12 T11: `INVALID_PAYLOAD` per §6; example workstreams made §4-valid) (2026-10-02) carrying the counterpart REQUEST_REPAIR `#1046` issuecomment-5947637296 as D1 (status `not_found`/read failures retain the pointer), D2 (`workRef` from the pointer's original target, never current config), D3 (receipt `intent_id` authentication on submit AND status); §0/§4/§6/§7/§8/§12/§13/§14 changed, §11 owned files unchanged, `operation-controller.ts` still untouched.** Supersedes-in-part the `COMMAND_ROUTE_UNAVAILABLE` stub of `mastermindx-market-intelligence/Mastermind#1046` (head `089a745b9aa4`); adopts its contracts verbatim. Not a second command plane: the ONLY producer this binding touches is the installed, authenticated Web-CEO ingress (`submit_ceo_intent` → one QUEUED Job; `ceo_intent_status` → the durable receipt). SEND and STOP stay honestly `COMMAND_ROUTE_UNAVAILABLE` because master has no producer for SEND and exposes none for STOP (lane B, ledger §6). Option 2 (a `mastermind_os_command` MCP profile + closed command ingress) is RECORDED in §14 as an Executive-OS-owner commission, not built here.

Companion ledger: `research/MASTERMIND_HEADLESS_CONTROL_CONTINUATION_HANDOFF_2026_10_02.md` (facts cited below as "ledger §n").

## 0. Acceptance gates (NOT DONE UNLESS)

1. `pnpm -C app/mastermind_os typecheck` and `pnpm -C app/mastermind_os test` (or the repo's equivalent `npm run …`) are green on the stacked branch, with the NEW tests in §12 present and passing — numbers reported, not "all green". Baseline at `089a745b9aa4`, measured by the seat 2026-10-02 in the build worktree: `npm ci` → 103 packages; `npm run typecheck` → rc 0; `npx vitest run` → 13 files, 608 passed, 1 skipped, 0 failed. After the build: typecheck rc 0 and vitest ≥ 608 passed + every new test, 0 failed, the 1 pre-existing skip unchanged.
2. `completeOrchestratorCommandBinding(createExecutiveLaunchBinding(…))` returns non-null in a test (the host-facing contract is met by construction).
3. An accepted launch receipt passes `normalizeSelection` (`app/mastermind_os/src/mission.ts:1399`) — i.e. `OperationController` reaches `AcceptedState`, never `SELECTION_INVALID`, in a controller-level test modelled on `operation-controller.test.ts`.
4. Every one of the 12 gateway error codes has a test asserting its disposition + reason on BOTH the submit path (§7.2) and the status path (§8.3) — 24 assertions, table-driven is fine; every disposition `"refused"` mapping is justified by a cited line in the installed ingress showing the refusal fires BEFORE the durable Job write (§7.3). A code that can fire after the write maps to `"unknown"`, never `"refused"`.
5. `SafeReason` has NO new members; `OperationController`, `PendingPointerStore`, `OwnerContext`, `OperationPointer`, `EffectReceipt`, `FiniteCommandPort` are UNCHANGED (diff of `operation-controller.ts` is empty).
6. No credential, token, socket path or tunnel URL appears in source or tests; the transport is an injected interface (§3) and fixtures are copied from the installed schemas, not invented.
7. `makeMessageIntent` and `makeStopIntent` return `null`, and the view's session presentation carries `unavailableReason: COMMAND_ROUTE_UNAVAILABLE` with `stopLabel` undefined (§9) — with tests.
8. Branch is stacked on `089a745b9aa4`; the PR targets `sol/mastermind-os-work-frontend-convergence-20260928-sol-001`, is DRAFT, inherits #1046's HOLD, and NOTHING is pushed to #1046's branch itself. Files touched are exactly §11.
9. RETURN packet (§13) names every test count, the exact head sha, the PR number, and GAPS — a status note is not a return.
10. (V1.1) The D1–D3 discriminating tests T9–T12 (§12) are present and passing, and a controller-level assertion proves that NO `readOperation` result other than an authenticated accepted receipt clears a pointer or permits a second `submit_ceo_intent` call.

## 1. Scope

- Implement `FiniteCommandPort` for `kind: "launch"` only, as `ExecutiveLaunchCommandPort`, over two installed MCP tools of the `web_ceo_v2` profile: `submit_ceo_intent` (the single MODIFYING tool; `integrations/executive_mcp/schemas.py:676`) and `ceo_intent_status` (read; `schemas.py:644`).
- Provide `createExecutiveLaunchBinding(config, client, viewSource): OrchestratorCommandBinding` so the host can replace the #1046 stub without changing the controller or UI.
- OUT OF SCOPE: SEND/STOP producers (§9/§14), any change to Executive OS, the ingress, the gateway, auth, or the Mission read; any UI redesign; any new store beyond the controller's `PendingPointerStore`.

## 2. Contracts adopted verbatim (from `089a745b9aa4`, `app/mastermind_os/src/orchestration/operation-controller.ts`)

`OperationKind = "launch"|"message"|"stop"`; `CommandIntent {kind; payload: Readonly<Record<string,unknown>>; targetKey: string|null}`; `OwnerContext {principalScope; generation}`; `OperationPointer {operationKey; kind; targetKey}`; `EffectReceipt {operationKey; kind; targetKey; disposition: "accepted"|"refused"|"unknown"; missionSelection?: MissionSelection; reason?: string}`; `FiniteCommandPort {context(); prepare(intent) (sync, effect-free); submit(pointer,intent,signal); readOperation(pointer,signal)}`; `PendingPointerStore {read/write/clear(principalScope…)}`; `SafeReason` = the closed 25-member union at `:114-142` (`IDLE … REFUSED`). `MissionSelection {workRef: string; rootJobId: string}` with validators `ws = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/` and `job = /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/` (`mission.ts:430-433`).

Controller facts the binding must satisfy (`operation-controller.ts:575-630`): a `launch`+`accepted` receipt WITHOUT a valid `missionSelection` is RETAINED as `SELECTION_INVALID`; a `missionSelection` on anything else is `SELECTION_NOT_ALLOWED`; `operationKey`/`kind`/`targetKey` must echo the pointer exactly (`RECEIPT_MISMATCH`/`KIND_MISMATCH`/`TARGET_MISMATCH`); `"unknown"` is retained as `UNKNOWN_RECEIPT` and reconciled later through `readOperation`.

## 3. Transport (host-provided, credential-free)

```ts
export interface ExecutiveToolEnvelope { readonly ok: boolean; readonly data?: unknown; readonly error?: { readonly code: string; readonly message?: string } }
export interface ExecutiveToolClient {
  callTool(name: "submit_ceo_intent" | "ceo_intent_status", args: Readonly<Record<string, unknown>>, signal: AbortSignal): Promise<ExecutiveToolEnvelope>;
}
```
The host owns authentication (OAuth submit scope `mastermind.executive.intent.submit`, read scope `mastermind.executive.read`) and the endpoint; the binding never sees tokens, sockets or URLs. `data` is the `mastermind.executive_mcp_result.v1` envelope's data (for submit/status: a `mastermind.ceo_intent_receipt.v1|v2` document). `error.code` is one of the gateway's closed `ERROR_CODES` (`schemas.py`): `invalid_input, grounding_unavailable, grounding_changed, identity_unverified, backend_unavailable, backend_refused, authority_refused, not_found, output_too_large, timeout, production_write_disabled, internal_error`. Anything else, a thrown exception, or an aborted signal is a TRANSPORT failure (§7.2).

## 4. Launch form → ingress request

`LaunchForm {goal; projectRef; profileRef}` and `LaunchChoice {ref; label; unavailableReason?}` (`ui/LaunchOrchestrator.tsx:7-17`). Binding config, frozen per host session:

```ts
export interface LaunchBindingConfig {
  readonly workstream: string;            // /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/, ≤72 chars — becomes the Job's work_ref (ceo_intent.py:636)
  readonly priority: number;              // integer −100..100 (booleans refused)
  readonly attemptLimit?: 1 | 2 | 3;
  readonly allowedWritePaths?: readonly string[];   // ≤16, each ≤256 chars, repo-relative, no '..', no .git
  readonly validation?: { pytest_targets?: readonly string[] /*≤8*/; compileall_paths?: readonly string[] /*≤8*/; git_diff_check?: boolean };
  readonly projects: readonly LaunchChoice[];  // ref = department, /^[a-z][a-z0-9._-]{1,63}$/
  readonly profiles: readonly LaunchChoice[];  // ref ∈ {"research_only","bounded_code_change"}
}
```
`makeLaunchIntent(form)` returns `null` unless ALL hold: `goal` is a non-empty string ≤4000 chars (`MAX_OBJECTIVE_CHARS`); `projectRef` matches the department pattern and is one of `config.projects` without `unavailableReason`; `profileRef` is one of the two profiles and listed in `config.profiles` without `unavailableReason`; profile law — `bounded_code_change` requires ≥1 `allowedWritePaths` AND ≥1 validation entry, `research_only` forbids both (ToolSpec text, `schemas.py:676ff`; `ceo_request.py:170-214`). Otherwise:

```ts
{ kind: "launch", targetKey: workstream, payload: {
    operation_key, objective: goal, department: projectRef, priority, execution_profile: profileRef, workstream,
    ...(allowed_write_paths), ...(validation), ...(attempt_limit) } }
```
Only these caller fields cross the boundary; the gateway authors actor, grounding SHAs, branch, worktree, capabilities and validation argv (ToolSpec description).

## 5. Deterministic operation key (the item-6 recovery property)

```
operation_key = "mmos-launch-" + hex(sha256(canonicalJson({ v: 1, principalScope, workstream, department, execution_profile, objective, priority, allowed_write_paths?, validation?, attempt_limit? })))[0:40]
```
`canonicalJson` = keys sorted lexicographically at every depth, no whitespace, UTF-8, arrays in given order, no `undefined` members. Length is 52 and the alphabet is `[a-z0-9-]`, so it always satisfies the ingress pattern `^[a-z0-9][a-z0-9-]{2,95}$` (`ceo_request.py:215`, `MAX_OPERATION_KEY_CHARS = 96`).

- `OwnerContext.generation` is EXCLUDED on purpose: the key must survive a reopen so a recovered pointer maps to the same Job (item 6: "no duplicate root, no replay"). Generation staleness is the controller's epoch gate (`_gate`, `EPOCH_CHANGED`), not the key's job.
- Because the key covers the whole payload, this binding can never present "same key, changed payload" (which the ingress REFUSES rather than minting a second Job). A different payload is a different operation by construction; the same payload re-submitted returns the SAME Job (`duplicate: true`, still `accepted`).

## 6. `context()` and `prepare(intent)`

- `context()` returns the host's `OwnerContext` or `null` (`OWNER_ABSENT` is the controller's reason; the port never invents a scope).
- `prepare(intent)` is synchronous and effect-free: it re-validates the intent exactly as §4 (kind must be `"launch"`, `targetKey` must equal `payload.workstream` byte-for-byte — non-empty, §4 pattern — payload shape as produced by `makeLaunchIntent`; D2: the pointer carries the ORIGINAL owner target so a reopen reconstructs `workRef` from the pointer, never from the current config), re-derives the key and returns `{operationKey, kind: "launch", targetKey: payload.workstream}`. It MUST NOT throw for an intent `makeLaunchIntent` produced; for a foreign or malformed intent it throws `Error("INVALID_KIND")` / `Error("INVALID_PAYLOAD")`. PINNED controller behaviour (`operation-controller.ts`): a wrong `kind` is rejected as `INVALID_KIND` at `:333` and a non-object payload as `INVALID_PAYLOAD` at `:335` BEFORE `prepare` is called, and ANY throw from `prepare` is mapped to `_idle("MALFORMED_POINTER")` at `:361-363` — so the controller-visible outcome of a throwing `prepare` is `MALFORMED_POINTER`, and T3 asserts exactly that.

## 7. `submit(pointer, intent, signal)`

7.1 Call `client.callTool("submit_ceo_intent", intent.payload, signal)`. Verify the pointer's key equals `payload.operation_key` first (else `refused`/`MALFORMED_POINTER`).

7.2 Mapping (every branch tested):

| Result | disposition | reason (SafeReason) | missionSelection |
|---|---|---|---|
| `ok` and `data.schema ∈ {mastermind.ceo_intent_receipt.v1, …v2}` and `data.accepted === true` and `data.dispatched === false` and `data.job_id` passes `job()` **and `data.intent_id === intentIdForOperationKey(pointer.operationKey)` (§7.5, D3)** | `accepted` | `ACCEPTED` | `{ workRef: pointer.targetKey, rootJobId: data.job_id }` (D2 — `pointer.targetKey` equals `payload.workstream` by §6) |
| `ok`, structurally valid receipt but `data.intent_id` MISSING | `unknown` | `MALFORMED_RECEIPT` | — (D3) |
| `ok`, `data.intent_id` present but ≠ `intentIdForOperationKey(pointer.operationKey)` | `unknown` | `RECEIPT_MISMATCH` | — (D3: a foreign receipt is never adapted to this pointer) |
| `ok` but receipt malformed (schema/accepted/dispatched/job_id fail) | `unknown` | `MALFORMED_RECEIPT` | — |
| `ok` and `data.job_id` does not pass `job()` | `unknown` | `UNKNOWN_RECEIPT` | — (cannot happen with installed `JOB-{n:03d}` ids; kept as a fail-safe) |
| `invalid_input` | `refused` | `INVALID_PAYLOAD` | — |
| `authority_refused`, `backend_refused`, `production_write_disabled`, `identity_unverified`, `grounding_unavailable`, `grounding_changed` | `refused` | `REFUSED` | — |
| `not_found` | `unknown` | `UNKNOWN_RECEIPT` | — (D1: on the installed ingress `not_found` is raised ONLY by `_resolve_status_intent` — `executive_ceo_ingress.py:775-777` — so it is not a submit-path code; if it ever fires on submit it is not before-effect evidence and must retain the pointer) |
| `backend_unavailable`, `internal_error`, `output_too_large` | `unknown` | `UNKNOWN_RECEIPT` | — |
| `timeout`, aborted signal, thrown client error, unknown code | `unknown` | `TRANSPORT_ERROR` | — |

7.3 Justification obligation: for each `refused` row the builder cites the installed ingress line proving the refusal precedes the durable Job write (`control_plane/executive_ceo_ingress.py` `_handle_submit` :484ff "§11.2 submit pre-reconciliation — this order is load-bearing", and `_handle_normalized_submit`). If any such code can ALSO fire after the write, move it to `unknown` and say so. `unknown` is the safe default: the controller retains the pointer and §8 reconciles on the same carrier (never a blind retry, never a second submit).

7.4 The receipt echoes `operationKey`, `kind: "launch"`, `targetKey` (the original workstream, §6) from the pointer verbatim; the untouched controller compares all three (`operation-controller.ts:588-594`).

7.5 Receipt authentication (D3; applies to §7 and §8 alike): before adapting ANY `ok` result, compute `intentIdForOperationKey(pointer.operationKey)` (§8.1 law) and require `data.intent_id` to equal it byte-for-byte — the installed `_receipt` always carries `intent_id` (`control_plane/ceo_intent.py:880-912`, key at :894). Missing → `unknown`/`MALFORMED_RECEIPT`; present-but-different → `unknown`/`RECEIPT_MISMATCH`; the pointer is retained in both. Target/owner association: the operation key hashes `principalScope` AND `workstream` (§5), so a matching `intent_id` binds the receipt to this principal's exact workstream transitively; additionally `pointer.targetKey` must be a non-empty string matching the §4 workstream pattern, else `unknown`/`MALFORMED_POINTER`. Echoing the caller's pointer is never authentication — only the recomputed identity is.

## 8. `readOperation(pointer, signal)` — same-carrier reconciliation and reopen recovery

- `intent_id` is derived from the pointer alone: `intentIdForOperationKey(key) = "mcp-" + hex(sha256(utf8("mastermind.executive_mcp.operation_key.v1\0") + utf8(key)))[0:32]` (`ceo_request.py:140-147, 543-555`, `mcp_intent_id`). Pinned vector from the installed release: key `mmos-launch-0000000000000000000000000000000000000000` → `mcp-bc363e20e05f2ba03efc9af32fe8f80d` CONFIRMED on the installed release: `integrations/executive_mcp/schemas.py:422-426` `derive_intent_id(operation_key)` → `_ceo_request.mcp_intent_id`, called by `adapter.py:863` on the submit path; the Slack law (`slack-71dcefafe2800c6c0937abe57578510c` for the same key) does NOT apply to this transport.
- Call `client.callTool("ceo_intent_status", { intent_id }, signal)`; `ceo_intent_status` resolves intent ids only (never job ids).
- 8.1 Authentication first (D3): the same `intent_id` check as §7.5 on the status receipt.
- 8.2 Mapping: an AUTHENTICATED receipt as §7.2 row 1 → `accepted` with `missionSelection {workRef: pointer.targetKey, rootJobId: data.job_id}` (D2 — NEVER `config.workstream`: the receipt does not echo `work_ref` — `authority` carries only `requested`/`policy_sha256`/`authority_level`, `ceo_intent.py:893-912` — so the ORIGINAL workstream travels in the pointer the port itself minted, §6; see §14.3). `pointer.targetKey` null, empty, or failing the §4 workstream pattern → `unknown`/`MALFORMED_POINTER`, pointer retained.
- 8.3 EVERY other result is `unknown` and retains the pointer (D1): `not_found` → `UNKNOWN_RECEIPT` (the installed ingress raises it whenever `find_event_by_command_id` sees no event YET, `executive_ceo_ingress.py:775-777`; a late original completion is indistinguishable from never-submitted, so it is NOT terminal no-effect evidence — V1.0's `not_found → refused` row is WITHDRAWN); every refusal code on the READ (`invalid_input`, `authority_refused`, `identity_unverified`, `backend_refused`, `production_write_disabled`, `grounding_unavailable`, `grounding_changed`) → `UNKNOWN_RECEIPT` (a refused read says nothing about the submitted effect); `backend_unavailable`/`internal_error`/`output_too_large` → `UNKNOWN_RECEIPT`; `timeout`/abort/thrown/unknown code → `TRANSPORT_ERROR`; malformed → `MALFORMED_RECEIPT`; intent mismatch → `RECEIPT_MISMATCH`. `readOperation` therefore has exactly ONE clearing outcome — an authenticated accepted receipt — and NO `refused` disposition at all until the canonical owner supplies an explicit terminal no-effect settlement (§14.5). Until then an uncertain submission stays `unknown`, the controller's `PENDING_POINTER` forbids a second submit (one Job, never two), and the host shows it as pending reconciliation, never as failed.
- Reopen path (item 6 shape): host → `store.read(principalScope)` → pointer → controller `recover` → `readOperation` → receipt → `AcceptedState` with the ORIGINAL `rootJobId` AND the ORIGINAL `workRef` taken from the pointer (D2: a same-principal reopen under a different current workstream yields the original selection, and the host's `selectionMatches` — `host-command-bindings.ts:214-220` — then truthfully reports it as not the current selection instead of relabelling a WS-A Job as WS-B). No pointer? `RECOVER_NO_POINTER` is the controller's truth; the binding never fabricates one.

## 9. SEND / STOP — truthfully unavailable

`makeMessageIntent(sessionKey, text)` → `null`; `makeStopIntent(sessionKey)` → `null`; `prepare` on `kind ∈ {message, stop}` → `Error("INVALID_KIND")`. `getView().session` (when a session is shown) carries `unavailableReason: COMMAND_ROUTE_UNAVAILABLE`, `turnBusy: false`, `stopLabel: undefined`. Reasons (lane B, verified on master): SEND has no producer — the supervisor's only turn input is the Runtime-generated prompt (`executive_operator_supervisor.py:924-937`, `_prompt` :464-482) and the interactive profile is refused before claim (:306-312) and not routed to the planner (`executive_service.py:5651-5660`); STOP's producer is `cancel` (`executive_service.py:6965-6967` → `runtime.jobs.cancel_job`), reachable only over `control.sock` by peer uid and exposed by NO MCP profile or ingress schema. Inventing either here would be a second command plane.

## 10. Installed truth the UI must show, not hide

Today the installed gateway (`web_ceo_v2`, release `3c35c5f8`) serves `submit_ceo_intent` behind `policies.submit`, and the Executive's `ceo_submit_armed` is false and the control service sits in `AWAITING_CANARY` (ledger §6). A real submit therefore refuses (`authority_refused` / `backend_refused` / `production_write_disabled`), and the UI shows `refused` honestly. Nothing in this build simulates acceptance against production. Build acceptance = contract tests with a fake `ExecutiveToolClient` whose envelopes are copied field-for-field from the installed schemas; the real end-to-end journey is item 5 and stays `EXACT_HUMAN_GATE` until a worker is READY and `acceptance.sh` has run (ledger §0).

## 11. Owned files (exact; nothing else)

NEW `app/mastermind_os/src/orchestration/operation-key.ts` (canonicalJson, `operationKeyForLaunch`, `intentIdForOperationKey`) · NEW `…/operation-key.test.ts` · NEW `…/executive-launch-command-port.ts` (`ExecutiveToolClient`, `ExecutiveToolEnvelope`, `LaunchBindingConfig`, `ExecutiveLaunchCommandPort`, `createExecutiveLaunchBinding`) · NEW `…/executive-launch-command-port.test.ts` · EDIT `…/host-command-bindings.ts` ONLY by adding `export { createExecutiveLaunchBinding } from "./executive-launch-command-port";` (no change to existing exports, validators or `COMMAND_ROUTE_UNAVAILABLE`). `operation-controller.ts`, `mission.ts`, UI files: UNTOUCHED.

Base `089a745b9aa4`; worktree `/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/pr-1046-0aba301c36b4f1b0`, branch `claude/ssd-pr-1046-0aba301c36b4f1b0`. PR: DRAFT, base `sol/mastermind-os-work-frontend-convergence-20260928-sol-001`, title `[MASTERMIND OS][WORK][STACKED on #1046][DRAFT/HOLD] launch-only command binding over the installed Web-CEO ingress`.

## 12. Tests (named; all in vitest)

T1 `operation-key.test.ts`: determinism (same input → same key), payload sensitivity (each field changes the key), generation-independence, length 52, pattern `^[a-z0-9][a-z0-9-]{2,95}$`, canonicalJson key ordering/`undefined` dropping. T2 intent-id vector pinned (§8). T3 `makeLaunchIntent` matrix: each §4 refusal → `null`; happy path → exact payload. T4 `submit` matrix: all 12 codes + transport throw + abort + accepted (`duplicate` true and false) + malformed receipt + job_id shape (installed ids are `JOB-{n:03d}` — `control_plane/executive_runtime.py:10550` and `:11720`, e.g. `JOB-001` — which passes `job()`; fixtures use that shape). T5 `readOperation`: accepted → selection from config; `not_found` → refused; `unknown` codes retained. T6 SEND/STOP null + view `unavailableReason`. T7 `completeOrchestratorCommandBinding(binding) !== null`. T8 controller integration: `OperationController` + fake client → `AcceptedState` with `missionSelection` equal to `{workRef, rootJobId}`; reopen with pointer in store → recovered `AcceptedState` with the same `rootJobId`; no second `submit_ceo_intent` call during recovery (assert call log).

T9 (D1, controller-level, `executive-launch-command-port.test.ts`): late original completion — `submit` → transport timeout → `unknown`/`TRANSPORT_ERROR`, pointer retained; `recover()` with status `not_found` → STILL `unknown`/`UNKNOWN_RECEIPT`, pointer retained; a `submit` attempt now yields `PENDING_POINTER` and the fake client's `submit_ceo_intent` call count stays 1; a second `recover()` returning the authenticated receipt for `JOB-001` → `AcceptedState` with `rootJobId JOB-001` — exactly one Job ever named.
T10 (D1): status-read refusal — `recover()` whose status read returns each of the 12 codes (table-driven) → `unknown` with the §8.3 reason, pointer retained, next `submit` → `PENDING_POINTER`; asserts that NO status result other than the authenticated accepted receipt clears the pointer.
T11 (D2): same-principal A→B reopen — launch under `WS:PROJECT-A` → stored pointer `{operationKey: key_A, kind: launch, targetKey: "WS:PROJECT-A"}`; a NEW controller with `config.workstream = "WS:PROJECT-B"` and the same `principalScope` runs `recover()` → `AcceptedState.missionSelection.workRef === "WS:PROJECT-A"` with the original `rootJobId`, and `selectionMatches` against a `WS:PROJECT-B` current selection is false. Plus: a stored pointer with `targetKey: null` → `unknown`/`MALFORMED_POINTER`, retained; `prepare()` of an intent whose `targetKey ≠ payload.workstream` throws `INVALID_PAYLOAD`.
T12 (D3): foreign/missing intent id — submit path: `ok` receipt carrying the `intent_id` of a DIFFERENT key → `unknown`/`RECEIPT_MISMATCH`, pointer retained, controller never reaches `AcceptedState`; `intent_id` absent → `unknown`/`MALFORMED_RECEIPT`; the same two on the status path via `recover()`; positive control: the pinned vector key with `intent_id = mcp-bc363e20e05f2ba03efc9af32fe8f80d` → `accepted`.

## 13. RETURN packet (required shape)

`STATUS: DELIVERED|PARTIAL|BLOCKED` · `RESULT:` PR number + exact head sha + base sha `089a745b9aa4` + files changed · `EVIDENCE:` typecheck/test commands with pass/fail counts, the intent-id law confirmed with the server line, the job-id shape with its line, the 12-code justification table with ingress lines · the T9–T12 assertion counts and the REQUEST_REPAIR id `5947637296` they answer · `GAPS:` anything in §0 not met · `DEVIATIONS:` any divergence from §4–§9 with reason. A return that ends on "now let me…" or a status note is not a return.

## 14. Recorded for the Executive-OS owner (NOT built here) — option 2

14.1 `mastermind_os_command` MCP profile over a closed command ingress exposing `stop` as an authenticated `cancel` with peer identity (`executive_service.py:6965-6967` semantics preserved: QUEUED→CANCELLED, RUNNING→CANCEL_REQUESTED). 14.2 `message` needs a NEW supervisor turn-input producer (none exists; the interactive profile is refused before claim) — a Runtime/Supervisor design decision, Sol's. 14.3 Receipt v3 should echo `work_ref` so a reader can rebuild `MissionSelection` from the receipt alone instead of frozen config (§8). These go to the #1046 / Executive carrier as a proposal, not as work this seat starts.

14.5 (V1.1, D1 follow-up for the Executive-OS owner — NOT built here) Terminal no-effect settlement: `ceo_intent_status` answers `not_found` whenever `find_event_by_command_id` has no event (`executive_ceo_ingress.py:775-777`), which cannot distinguish never-submitted from not-yet-durable, so the binding treats it as `unknown` and retains the pointer. Only an owner-side settlement backed by the ingress's own evidence (e.g. a `no_effect` disposition proven from the submit ledger / `request_ref` negative proof) may ever map a status read to `refused`. Until it exists, the truthful cost is a pointer that stays `pending reconciliation` after an uncertain submission; the untruthful alternative was two Jobs.
