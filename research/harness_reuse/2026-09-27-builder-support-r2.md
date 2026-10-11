# Builder support R2 — close the tool-dispatch identity gap

**Operation:** `deepseek-harness-mastermind-integration-20260927-sol-001`. **Parent packet:** Mastermind #1037 at `7e4d8412f4314b63c0240a1d2c92c0b7438c943a`. **Status:** source-backed design refinement and proposed regression fixture; NOT_RUNTIME_REPRODUCED. No production patch, installation, provider call, account action, or worker assignment.

## Decision to test before implementing Task 3

R1 section 7 correctly requires exact definition/generation binding, but its reference to `ctx.tools.guard()` must not be read as proof that this hook alone enforces that property until the body executes. Keep the invariant; qualify the implementation. A displayed tool name, identical JSON schema, and successful pre-execution guard do not identify the later callable body.

## Pinned source evidence

All donor sources below are at `deepseek-ai/deepseek-harness@21638c56315ae6a2b552d6091945d3144c9af32e`. The [core tool source](https://github.com/deepseek-ai/deepseek-harness/blob/21638c56315ae6a2b552d6091945d3144c9af32e/packages/core/tools/src/index.ts), Git blob `ca89f370febac1fa24f84cc25351a186866fe7e7`, has this ordering: `prepareExecution` performs `guardReason`; `dispatchScheduledExecution` awaits the `tools/execute` waterfall; `dispatchToolBody` then calls `resolveExecution(name, agent, nested)` and invokes the resulting definition. `createExecution` separately captures content projection/finalization earlier. These are inspected source facts, not an executed interleaving.

The [session checkpoint policy](https://github.com/deepseek-ai/deepseek-harness/blob/21638c56315ae6a2b552d6091945d3144c9af32e/packages/session/session-checkpoint-policy/src/index.ts), blob `0fc456eb08853b9fe54d0bf9ca3a26c05b4413cf`, demonstrates a legitimate asynchronous `tools/execute` wrapper: it awaits session persistence before delegating. R1 does not necessarily enable that plugin; this is evidence that the extension boundary permits suspension. MCP resynchronization and approved runtime configuration must be considered separately from arbitrary hostile plugin code.

The proposed test follows the [existing ToolRuntime fixture setup](https://github.com/deepseek-ai/deepseek-harness/blob/21638c56315ae6a2b552d6091945d3144c9af32e/packages/core/tools/tests/execution-mode.spec.ts), blob `333909c24a9313cf1b05ddc094726c345bc2afb0`: real Cordis Context, SystemPrompt, ToolRuntime and public tool registration. It supplies only in-memory bodies and a deterministic awaited wrapper. No fake ToolRuntime, model, network service, or host process is involved in the proposed test.

## Ready-to-run falsifier, not a passing test claim

Copy `2026-09-27-dispatch-binding.probe.ts.txt` beside the pinned donor's existing core tool tests as `dispatch-binding.spec.ts`; use the donor checkout's declared test command. The four cases require: (1) unchanged approved body executes once; (2) permission denied before the guard invokes no body or wrapper; (3) same-name replacement during the awaited wrapper invokes neither old nor replacement body and returns refusal; (4) revocation during that wrapper invokes no body and returns refusal. Source inspection predicts the last two expose the unsupported assumption; actual RED results are still owed.

Each negative case uses a guard stronger than a name allowlist: live permission plus exact registered-definition object equality. Therefore a failing result cannot be repaired merely by comparing tool names. Keep the positive case so a blanket all-tools denial cannot pass. The wrapper supplies a deterministic microtask boundary, not a sleep or probabilistic timing race. When adapting to the real MCP client, also exercise reconnect/generation revocation and own-scope shadowing, preserving the same no-unapproved-body assertion.

## Smallest acceptable repair boundary

After reproducing the cases, inspect the donor tool owner's dispatch boundary. Prefer the smallest compatible mechanism that revalidates the admitted definition and current generation immediately before calling the resolved body, without another asynchronous gap. A recheck/move of the existing guard may be sufficient for part of the contract; establish that with tests rather than asserting it. If the current API cannot express exact-definition binding, propose a small opt-in hook in the existing core tool owner. Do not implement a parallel tool registry, proxy, scheduler, or permission service.

Do not merely retain and run a revoked old object. Ensure body, declared output, and projection/finalization refer to a coherent admitted execution, and that postprocessing cannot convert a completed external effect into an authorized retry. A separate delayed-return test must cover generation movement while a body is awaiting. Arbitrary malicious plugin code remains outside the in-process guard's security guarantee; the immutable trusted plugin closure and host isolation remain essential. This is a Mastermind integration-contract issue, not a claim of a remotely exploitable upstream vulnerability.

## Scope, proof and support routing

This expands the falsifiers within existing M05/M07 and Task 3; it does not mark any of the original 53 acceptance cases passed or create a new program. Tasks 1–2 profile/loopback preparation remain independent. Native Codex/Claude capability delivery and the current combined OS release must not wait on this donor question. Existing shared app/runtime/hierarchy/provider writers remain untouched.

Verification performed here: the fixture passes Node v22.16.0 `--experimental-strip-types --check` (syntax only). No donor dependencies were installed, no Vitest suite ran, and no actual guard failure or repair was executed. Direct container source download was unavailable; source facts were read through GitHub/web instead. Keep that limit visible in the builder return.

Standing support covers exact donor/API compatibility, scope and credential isolation, useful capability parity, tests and CI failures, cancellation/recovery and result attribution, usage/cost accounting, rollout/rollback, and Agent OS continuity. On a concrete request, return an exact head, failing case or interface and current writer; Sol provides bounded analysis or in-scope repair without taking an incumbent source lease. This note itself neither assigns a worker nor grants production authority.
