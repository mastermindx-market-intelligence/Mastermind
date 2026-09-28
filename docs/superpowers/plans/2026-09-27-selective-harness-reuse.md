# Selective Harness Reuse Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for the assigned existing writer, or `superpowers:subagent-driven-development` only through the existing lawful placement owner. Do not create a new principal, nested workspace, or duplicate reviewer. The Chairman assigned Sol the research/design and the current Codex builders the later surgical integration; no repeated Chairman dispatch ceremony is required.

**Goal:** Deliver a qualified opt-in DSH worker and portable approved tools without replacing the native OS execution paths.
**Architecture:** The current Python worker interface owns a pinned Node SDK runner per Attempt. Existing capability-policy/package, provider, lifecycle, result, and UI projection owners remain authoritative; a tiny donor MCP admission patch connects them.
**Tech Stack:** Existing Python worker contracts and process inspector; pinned DSH/Cordis Node runtime and public TypeScript SDK; existing official MCP transports; pytest and the donor/package's native test runner after its checked-in script is verified.
**Spec:** `docs/superpowers/specs/2026-09-27-selective-harness-reuse.md`.

## Global constraints

Mastermind base `55d7270570a0636dc19f75aecb38352386094ea1`; donor base `21638c56315ae6a2b552d6091945d3144c9af32e`. Re-pin current law and reconcile only overlapping/interface deltas before editing. No production flag, credential, provider call, package install on a shared host, service change, protected push, or release is authorized merely by this plan. Keep all legacy profiles and current native builders functioning. R1 is one runtime/session/task per Attempt with read-only tools, no extra input producers, no donor native subagents, no model-selected accounts/routes, no write or shell tools, no HMR/plugin manager, no background scheduling tools, and no hidden model-request retry. Existing worker interface and result shapes stay unchanged unless their actual owner accepts a necessary versioned amendment.

## Review focus

1. A project `.env`, home patch, compatibility exemption, or optional-bundle failure changes actual execution despite a superficially correct configuration dump: exercise Tasks 1 and 2.
2. A server changes schemas/instructions/resources during reconnect while the old tool remains listed: exercise Task 3 at both registration and call time.
3. Output validation fails after a remote tool acted, or cancellation returns before descendants stop: exercise Tasks 4 and 5 without inferring no effect.
4. A second queued input or foreign-session event contaminates the result attributed to the job: exercise Tasks 2 and 5.
5. The model makes another provider request after a retryable error or reaches an ambient credential: exercise Tasks 1 and 6 with actual wire counters.

## Delivery and source-custody map

New candidate files proposed for this bounded integration: `control_plane/dsh_worker.py`, `integrations/dsh_worker/runner.ts`, `integrations/dsh_worker/contracts.ts`, `integrations/dsh_worker/profile/`, `tests/test_dsh_worker.py`, `tests/test_dsh_worker_contract.py`, and `integrations/dsh_worker/tests/`. The integration package owns its lockfile/build artifact, not a mutable global install. The exact package-manager entrypoint is chosen from the owning repository's current build convention before the first edit; do not add a company-wide Node toolchain migration.

Incumbent-owned seams: `control_plane/worker_adapter.py` descriptor table; `worker_execution_contract.py`; `executive_agent_capabilities.py`; `executive_capability_packages.py`; `sol_capability_status.py`; native `claude_worker.py`; existing supervisor/broker/placement and app client/producer files. The new writer may propose and test amendments, but a conflicting current writer retains those files. Do not edit Runtime/cycle/hierarchy files as a shortcut for adapting DSH. Record any required amendment against its actual owner and allow path-disjoint adapter/falsifier work to continue.

Donor patch scope is initially restricted to the existing MCP client's tool-generation and connection-context publication boundaries plus their tests. A patch queue or pinned package build is a dependency artifact, not a new upstream fork of the UI, agent teams, account manager, or company scheduler. Any scope expansion beyond that requires a concrete failing requirement and Sol adjudication.

## Task 1 — Lock and prove the executable profile

**Files:** Create the private build/profile manifest under `integrations/dsh_worker/profile/`, its runtime artifact manifest, and `integrations/dsh_worker/tests/profile.test.ts`. Consume the existing immutable package/profile owner; do not replace its digest algorithm.
**Interface:** Define proposed `validateRuntimeBinding(binding: DshRuntimeBinding): ValidatedDshRuntimeBinding` in `integrations/dsh_worker/contracts.ts`. The binding contains exact artifact identity, profile/package digests, selected route/model/effort, capabilities, allowed environment variable names, and deadline inputs; no credential values. It is host-authored and validated, not model-authored.
- [ ] Write failing profile tests for case IDs H01–H08. Assert the runtime rejects changed artifacts, unexpected patches/includes, project `.env` influence, skipped required bundles, ambiguous compatible-version claims, and undeclared tools before the first model request.
- [ ] Run the integration package's declared profile test script, initially expecting those explicit failures. Record the exact command from its committed package metadata; no invented upstream script name.
- [ ] Build an isolated pinned runtime using the normal DSH entrypoint and an explicit profile. Positively allowlist the runner and child environments; keep startup directory separate from the agent workspace. Exclude the retry executor and forbidden model-facing plugins. Include required internal dependencies only with a tested non-exposure assertion.
- [ ] Compare configured closure, actual activated services/tools, and artifact digests. Assert no live API request or login occurs during keyless readiness. A missing required capability makes the job ineligible even when DSH would tolerate an optional plugin failure.
- [ ] Commit the scoped profile/build/verification candidate using the current source-custody route; keep it uninstalled and unarmed outside the isolated qualification environment.

## Task 2 — Real-runtime, credential-free falsifier

**Files:** Create `integrations/dsh_worker/runner.ts`, the bounded request/result types in `contracts.ts`, and `integrations/dsh_worker/tests/runner.test.ts` with a loopback deterministic model/MCP fixture. Test fixtures are not new production providers or services.
**Interfaces:** Define proposed `runAttempt(input: DshAttemptInput, binding: ValidatedDshRuntimeBinding): Promise<DshAttemptOutput>`. `DshAttemptInput` carries common job/run/worker identity, one task, workspace, one session ID, result-schema identity, grant references, and remaining deadline. `DshAttemptOutput` carries those identities, raw terminal observations, bounded root events/artifact references, usage observations, and cleanup evidence. It is an internal translation value, not a new lifecycle schema. The SDK interaction uses its public `DeepSeekHarness` API with explicit `dshBin`, `profile`, `patches`, `dshHome`, `processCwd`, `cwd`, `env`, route/model/effort, and timeout options.
- [ ] Write failing tests P01–P06: actual runtime issues a tool call against the real loopback MCP fixture, receives the expected source nonce, and returns the schema-valid result; a missing required MCP server, second input producer, foreign session result, malformed/oversized wire frame, and fake handshake compatibility cannot pass.
- [ ] Run the real pinned runtime against the deterministic model. The positive assertion includes one observed tools/call and exact received content; a model answer without that call fails even when its prose is correct.
- [ ] Implement one runtime/session/task ownership and bounded output collection. No arbitrary command-line arguments, public Node inspector, listening control endpoint, or model-supplied profile. Avoid private SDK process fields.
- [ ] Verify the root message's inbox receipt, whole-agent idle, terminal turn reason and absence of other input producers; retain bounded diagnostics. Do not map idle directly to success.
- [ ] Commit the independently testable falsifier and runner. The receipt is HERMETIC_REAL_RUNTIME only, not provider or fleet acceptance.

## Task 3 — Add exact MCP generation admission, not another MCP service

**Files:** Donor `packages/mcp/mcp-client/src/tools.ts` at `ToolBridgeOptions`/`syncTools`, the connection-owned context boundary `src/server-context.ts` plus the existing caller that supplies its connection, and package tests. Add the Mastermind companion guard in `integrations/dsh_worker/`; use the documented `ctx.tools.guard(guard)` synchronous deny mechanism after `tools/pre-execute`.
**Interfaces:** Introduce a proposed optional trusted generation-admission callback to the existing tool bridge options. Its input is the configured server identity plus the complete discovered tool definitions and current connection identity; its output is an immutable approved subset/binding or a refusal. Our profile requires it. No independent persistence or discovery loop. Execution calls carry/revalidate the admitted binding before the existing `client.callTool` invocation.
- [ ] Write failing M01–M12 tests: extra discovered tool, changed input/output schema, raw/public-name normalization collision, duplicate name, reconnect drift, stale generation after failed sync, same-name hostile replacement, own-scope ungranted tool, direct call bypass, instruction change, ungranted resource access, and a false read-only annotation.
- [ ] Prove at least one current donor test demonstrates the initial defect: `syncTools` registers an extra tool or republishes changed instructions without the Mastermind grant. Do not weaken donor baseline tests to conceal the difference.
- [ ] Add pre-registration filtering/validation at `syncTools` before Phase 2, plus execution-time binding checks. On a material refusal invalidate the old executable grant as well as rejecting the proposed generation; do not mistake retaining old definitions for current authorization.
- [ ] Gate `registerServerContext` publication separately. Resource permission and bounded attributed instructions must be explicit; R1 otherwise exposes neither. Add the monotonic all-tools guard so filtering cannot be bypassed through own-scope registration or direct invocation.
- [ ] Run donor bridge tests and Mastermind integration tests, including a positive server with only its approved subset. Freeze the minimal patch and exact patched-artifact digest. Submit an upstreamable change only as a separately authorized publication, not automatically from this task.

## Task 4 — Bind process execution to the common worker adapter

**Files:** Create `control_plane/dsh_worker.py` and `tests/test_dsh_worker.py`. Propose only the necessary descriptor insertion in incumbent `worker_adapter.py`; descriptor readiness and production route admission remain separate.
**Interface:** Implement `DshWorkerAdapter` with the exact five methods of `WorkerExecutionAdapter` and the existing common values. Use an injected reviewed runtime binding and the existing `ProcessInspector`, workspace preparation, artifact, validation, and cleanup patterns. `start()` returns the owned runner's `WorkerProcessRef`, not a PID claimed by model output. Optional recovery is not advertised until its tests pass.
- [ ] Write failing W01–W07 tests for the adapter interface, binary/profile mismatch, wrong workspace/base/UID, PID reuse, initialization timeout, surviving child after root exit, and crash/recovery before collection.
- [ ] Run `python -m pytest -q tests/test_dsh_worker.py --tb=short`; expect the new discriminators to fail before implementation.
- [ ] Implement spawn/attestation under the existing host-owned process boundary, finite deadlines with cleanup reserve, read-only status, and idempotent same-process cancellation/collection. Reuse shared primitives only through a reviewed existing seam; do not copy private Codex internals wholesale or refactor its active implementation to satisfy this adapter.
- [ ] Observe actual process-tree exit and immutable process identity. A failed cleanup preserves the original execution as unresolved. A recovery probe never creates a second runtime or sends the task again.
- [ ] Run the new suite plus the exact existing worker-adapter/contract tests identified by the incumbent owner. Commit only the assigned files and hand the descriptor amendment to its current writer where collision exists.

## Task 5 — Translate results, uncertainty, and artifacts

**Files:** `control_plane/dsh_worker.py`, `integrations/dsh_worker/contracts.ts`, result translation in the runner, and `tests/test_dsh_worker_contract.py` / runner tests.
**Interfaces:** Define proposed `translate_dsh_result(spec: WorkerLaunchSpec, observation: Mapping[str, object]) -> WorkerResult` in `dsh_worker.py`. The common adapter owns validation and collection; the mapping is an internal observed runner output, not a model authority assertion. Preserve `CollectionReceipt` hashes and the existing artifact limits.
- [ ] Write failing R01–R09 tests for wrong job/run/worker identity, root/descendant substitution, absent/malformed terminal reason, max-token/error mapped to success, oversized or out-of-root artifact, remote effect followed by invalid output, lost result after dispatch, duplicate collection, and cancellation racing successful completion.
- [ ] Run `python -m pytest -q tests/test_dsh_worker_contract.py --tb=short`, verifying the test checks the real outcome distinction rather than merely a status string.
- [ ] Derive the terminal reason from validated root `turn/end` events; the TypeScript RunResult has no finishReason property. Validate task schema, required tool evidence, artifacts and Git manifest before success. Preserve bounded raw diagnostic evidence without exporting credentials or full sensitive responses.
- [ ] Map uncertain effects through the existing supervisor/runtime policy; do not invent a new worker status or authorize automatic retry on generic error. Prove exactly one result is consumed for the same Attempt.
- [ ] Run all new worker/runner tests and the incumbent result-consumer suite against the exact candidate. Commit the tested composition.

## Task 6 — Prove route, quota, and retry discipline

**Files:** Integration profile/runner tests and only the current provider-binding consumer seam authorized by its owner. No new provider registry, account store, balance table, or scheduler.
**Interfaces:** Consume the existing owner-selected provider/model/execution-mode binding and its reservation/accounting reference. Return observed usage through existing `WorkerResult.usage`; retain requested model versus observed served model separately.
- [ ] Write failing E01–E07 tests: ambient credential discovery, unapproved endpoint/redirect, hidden retry after timeout/429, two harnesses charging one entitlement as two pools, output cap mistaken for total budget, and unverified served identity.
- [ ] Use a counting loopback endpoint first. Assert one admitted model request for the no-retry error case, no credential lookups outside the supplied mechanism, no native developer-account fallback, and no silent alternate route.
- [ ] Qualify the selected transport libraries' retry behavior in the actual built artifact; donor retry-plugin omission alone is not sufficient. Reject an unqualified route rather than inserting another retry shim or proxy.
- [ ] Only after source/host/provider-policy/budget gates pass, run one bounded real provider request and collect its actual usage. No provider canary is preauthorized by this source plan; use the existing owner to admit it.
- [ ] Commit the source tests and return the exact route/profile/host qualification evidence. Do not claim the catalog as a whole is qualified.

## Task 7 — Native baseline, app consumption, and release qualification

**Files:** Existing native capability package/profile consumer and app status/result consumer owned by the current builders; no blanket write envelope over #999 Runtime/cycle or #1007 shared files. Add only the tests each incumbent requires for the consumed interface.
**Interfaces:** Existing `CapabilityFact` / `project_sol_capability_status()` / `CapabilityStatus` and the actual current app producer-client method. Reuse the current parent result/Wake path; this plan introduces no alternative app launch/message/reopen endpoint.
- [ ] Native owner first proves the required tool-bearing baseline task through an existing route; do not block it on DSH. Preserve current Claude authentication/realm repairs and qualify its richer profile separately.
- [ ] App owner pins the real build-readiness task, source/devserver identity, expected result schema, and destination parent. Run the DSH worker only through actual existing admission/broker placement, then prove parent consumption, artifact visibility, truthful availability, and stop/recovery behavior.
- [ ] Exercise U01–U04: source-only never looks live; missing auth/dependency remains specific; the parent consumes the correct result exactly once; disarming DSH for new jobs does not disturb native work or replay an uncertain Attempt.
- [ ] Repeat the equivalent task on a second independently eligible provider. Compare quality and measured resource use with the native baseline; no fabricated performance or cost improvement.
- [ ] Obtain independent exact-head review and current hosted checks, then the existing integrator releases the exact artifact through its normal process. Record source, installed, runtime, and accepted-product proof separately. Update the existing Macro Agent OS records through their current writer and read them back.

## Receiver-ready handoff and next execution boundary

The accompanying builder packet is an integration addendum to existing programs, not a new worker assignment disguised as a reply. First receiving action: reconcile current owned paths and consume the architecture; keep ongoing launchpad/backend/hierarchy work moving; place the path-disjoint Tasks 1–3 falsifier through the existing capable Codex worker owner when available. Native capability delivery proceeds independently. Record actual PICKUP and START separately if a new bounded child is commissioned. No model/seat label is a verified native-session target. Return exact candidate head, completed case IDs and proof levels, unresolved failures, runtime artifact identity, and parent-consumption evidence on the established carrier. Unchanged waiting does not justify another worker, branch, audit cycle, or observer.
