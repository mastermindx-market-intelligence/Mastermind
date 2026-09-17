# DSH N0 native-observation source conformance

## Mission and state

Operation: `harness-convergence-n0-native-observation-20260917-sol-001`.
Parent research: Mastermind #687, design commit
`64c024e4f675296c189fb482a6ec70547877d9c2`, plan
`docs/superpowers/plans/2026-09-17-dsh-native-observation-conformance.md`.
Source-intent receipt: #687 comment `5711628157`.
Protected implementation/procedure base:
`55a54fdaecef9cbf434492c3cce3b369dbc69b9b`, Skillpack 1.0.1/bootstrap 1.

The current Chairman recovery/continuation assigns Sol this bounded harness
source candidate. #600/#660/HF1/OHF/capability and Agent Evaluation retain their
existing ownership. No shared-owner adoption, worker START, or independent
review is asserted. Direct work uses the exposed attended source tools, not a
raw provider-spawn fallback or a second execution queue.

Before this candidate, the N0 observer/consumer existed only as a plan and
source-method probes. This candidate supplies original, runnable TypeScript
observation and one-handle coordination code, a strict Python consumer of the
existing OHF gate, and source-level/cross-language conformance tests.

**State: BUILT_NOT_PROVEN for production; N0 native acceptance is incomplete.**
The executed tests use explicitly artificial public-API contract doubles.
They are NOT a mounted DSH/Cordis Agent and NOT an installed native adapter.
The complete N0 acceptance still requires the real qualified native producer,
setup-time process/network negatives, and owned native-process cleanup.
Do not label a mapper, passing unit tests, or this source PR native completion.

## One bounded source surface

- `experiments/harness_convergence/dsh_native/observe.ts`: original exact-Agent
  collector; no loader, subprocess, provider prompt or company admission.
- `experiments/harness_convergence/dsh_native/fixture_host.ts`: one-handle
  coordinator and adapter for public `agents.create/setup`, given a Context
  that the qualified native owner already composed.
- `experiments/harness_convergence/dsh_native/ohf_consumer.py`: pure private
  payload intake and existing OHF comparison; no new gate or runtime command.
- `tests/harness_convergence/dsh_native_observation.spec.ts`: source tests with
  explicit contract doubles; its `--emit` mode runs the real original collector.
- `tests/harness_convergence/test_dsh_native_observation.py`: strict intake,
  original TypeScript-to-existing-Python comparison and negative-suite wrapper.
- This runbook.

No control-plane, existing native proxy, Agent Eval core/corpus, dependency lock,
workflow, credential, account, route, deployment or organizational record changes.
Research #687 remains records-only. A2 #692 is separate and unchanged.

## Trusted inputs, observation and proof limits

`createObserver` receives the exactly owned handle, native registry Context,
installed native selection reference and separately supplied owner recipe.
These are trusted same-process fixture-owner arguments, never model-selected
paths, arbitrary public callbacks, provider credentials or user JSON.
The owner recipe is an expectation, not a source of permission.

The observer calls public `tools.schemas(agent)` and `tools.get(name, agent)`
on that exact handle, not a global or newest-session lookup. It binds schema
order and actual registered definition/executable/render references to the
fixture's original definitions. Same-name/same-schema replacement and in-place
implementation changes refuse. `run_code` refuses the first native-only profile.
Native presentation is inferred from the pinned public tool-view semantics and
absence of its reserved transport; no private `modeFor` API is used.

Loader entries must exactly match the flat admitted recipe in order and be
active. Groups, disabled/pending/missing/unexplained entries refuse. Source
module and implementation digests associate these observations with the
**separately admitted supply recipe**; this collector does not hash a loaded
binary or claim that Loader diagnostics authenticate code origin. Qualification
must supply the immutable package/build/source association independently.

The installed selection is read and resolved through the native LLM service,
then selection, Agent identity, tool definitions and composition are checked
again after the await. Unknown/failed resolution is not a retained catalog
success. This is native effective configuration, not response-reported physical
model identity and not a promise that a later dispatch cannot drift. No call to
`stream`, `query`, `prompt`, or model work is made by these functions.

The private `dsh-native-observation/n0` payload is bounded transient evidence,
not a persisted canonical schema or ABI. It binds existing attempt/worker/
process-generation/native-session identifiers but allocates none of them.
Limits: 65,536 UTF-8 bytes, depth 32, 4,096 JSON nodes, 64 tools, 128 composition
rows, 128 properties/array elements, 8,192 string units. N0 admits safe integral
JSON numbers only; oversized, cyclic, accessor-bearing, non-JSON, duplicate-key
or malformed values refuse rather than truncate. ASCII object keys preserve
cross-language canonical ordering. Supplied evidence uses the existing pure
Agent Eval secret-shape rejector; no ambient secret inventory is read.

`compareNativeObservation` accepts bytes plus an independently supplied frozen
`NativeBinding`, requested OHF profile, and trusted host observation. It does
not accept a caller-provided ALLOW or completeness flag. Nested mutable binding
aliases, stale IDs, altered tool/schema/source digests, or missing fields refuse.
Host-observed capabilities/extensions cannot be cleared by a native payload.
Required unknown host facts refuse; optional unknown metadata is not globally
vetoed. The N0 closed-fixture recipe is the only context in which empty extension
inventories are used. This is not a general method for proving arbitrary
processes lack plugins or MCP.

The consumer derives the backend-private effective-config digest from the
validated native model/settings/tool/composition projection. It does NOT echo
a requested digest or trust an unrelated host config value. Configuration
identity excludes attempt/session IDs. Native token-setting or other config
drift reaches the existing `compare_launch` config refusal. Model mismatch,
sandbox refusal and final launch decision remain owned by the existing OHF
comparator. The result reports comparison evidence and `first_work_started=False`;
it submits no command or Job and grants no execution permission.

## Setup, cancellation and cleanup

`nativeFixtureFactory` uses the already-provisioned native Context and the real
pinned `installModelSelection` supplied by its trusted owner. It snapshots the
binding/recipe before setup awaits, installs native presentation and two
artificial in-memory tools before publication, and passes the creation signal
through the public factory. The qualified Context must contain only the fixed
minimal native composition plus a provider-free LLM resolver/adapter.
This source does not provision that Context, discover packages or install DSH.

`withOwnedFixture` holds an observation until the owned Agent handle is disposed
and no longer registered. Capture failures still dispose; cleanup failures
return `CLEANUP_UNSETTLED` rather than a success. A cancelled setup or teardown
cannot publish late success. Unexpected errors are translated to bounded codes
without echoing supplied error text. A factory failure without a returned
handle is `SETUP_FAILED_EFFECT_UNRESOLVED`; source code cannot claim the
unobserved factory rolled back. The native factory/process owner must reconcile.

A settled handle is NOT proof of OS process-group, MCP/network or persistence
cleanup. The result explicitly scopes cleanup to the owned Agent handle.
`provider_turns_started=0` counts this coordinator's own work-turn invocations;
`provider_calls_observed=null` states that upstream provider activity was not
measured. Do not turn that null into a global zero-provider assertion.

## Executed development proof

Environment observed: MacBook, Node 26.8.1, CPython 3.12.14, pytest 9.1.1.
No package installation, DSH application launch or provider call was used for
these source tests. TypeScript was executed by Node type stripping; a compiler
check against the complete native dependency/type closure is still outstanding.

- Initial TypeScript/Python suites were RED while implementation was absent.
- Additional RED cases exposed and repaired host-capability laundering,
  optional-unknown over-rejection, setup signal loss, raw error leakage,
  cancellation during teardown, native effective-config echo, permissive digest
  coercion, and mutable factory binding/recipe capture.
- Current TypeScript source suite: **29 passed, zero failures/skips**.
- Current selected Python suite: **110 passed, zero failures/errors/skips**;
  this includes 45 new source-conformance tests and 65 existing OHF contract/wire
  tests. Two Python tests execute original TypeScript: actual produced JSON
  reaches the existing comparator, and the complete TypeScript negative suite
  is checked. Do not add those executions again as independent native trials.
- Eight targeted forbidden mutants each failed its intended assertion: omitted
  Agent scope, removed implementation check, host-capability laundering, missing
  binding check, missing late-cancel check, native-config echo, mutable binding
  alias, and mutable recipe alias. Source bytes were restored after each probe.

Reproduction on an already prepared source-test environment:

```sh
node --test --test-reporter=tap tests/harness_convergence/dsh_native_observation.spec.ts
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  --noconftest -p no:cacheprovider -q \
  tests/harness_convergence/test_dsh_native_observation.py \
  tests/test_ohf_p1a_operator_harness_contract.py \
  tests/test_operator_harness_wire.py
```

`--noconftest` deliberately excludes unrelated global fixtures; this is selected
source proof, NOT full repository CI. The Python wrapper explicitly skips the
TypeScript path without Node >=24; such a skip is missing cross-language proof,
not conformance success. No skip occurred in the observed local run.

## Native supply and execution gate — still held

Official pinned upstream:
`deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`.
The inspected root is `@deepseek-ai/dsh-root` version `0.1.6-alpha.1`, package
manager `pnpm@11.7.0`, Node constraint `^22.19.0 || >=24.0.0`.
Native source lock Git blob: `cdf7dd28775dc60a82f63a1766bdd141ce0073db`.
Native source lock SHA-256: `ca131858949bd12b2acfc227b1af7dfa3c8d65e74b234824d5c741e6421010a1`.
Root package SHA-256: `5dec5c24e746dac82e3da6084fb3a14d0e85ad9154570c7fd457974112f38b08`.

These are verified source identities, NOT installed artifacts or a native grant.
Workspace dependencies and native peer services require a fixed qualified
closure. The existing supply/native-process/capability owner must supply exact
executable/package/build hashes and notices, an isolated no-provider fixture
principal/process grant, a real minimal Context/fixture LLM adapter, and measured
setup-time network/process/persistence restrictions. The source-test Node
executable is not implicitly an admitted DSH toolchain. Do not run a floating
installer or the stock ACP application to obtain a green fixture.

## Acceptance and exact continuation

Keep the implementation Draft until exact-head repository/security checks and
independent source review are consumed. Shared-owner adoption is separate from
request/delivery. No previous reviewer request or Fable thread proves START.
N0 source construction is independent of A2 #692 release; do not bundle their
source or repeat the unchanged teardown/A2 tests.

Sol's next native action is qualification of the exact runtime/supply recipe
through the existing owner and then the real mounted Agent fixture. That proof
must exercise this producer and consumer, both setup failures and cancellation,
unexpected setup-time network/process actions, wrong generation, incomplete
source provenance and verified native cleanup. Until then N0 remains incomplete
and no Worker/OHF route may be registered. #660's real-resume requirement remains
unchanged; this one-shot coordinator does not qualify as that rich operator.

No branch replacement, force push, extra registry, package service, runtime
loop, credential store or permission system is authorized. Unknown effects stay
on their original carrier. Preserve the existing research and use this exact
source candidate for any repair. A source/test checkpoint is not product or
native acceptance; the parent harness mission remains active.
