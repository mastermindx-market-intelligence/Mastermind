# DSH ACP Worker N1 — provider-free native predecessor

## Identity and proof ceiling

Operation: `harness-convergence-n1-dsh-acp-worker-20260918-sol-001`.

Parent research: Mastermind #687. Source-intent receipts:
- #687 comment `5727606144` — one real pinned DSH ACP process through existing Worker v1 owners.
- #687 comment `5727619334` — bounded provider-scoped ACP model-option encoding seam.
- #687 comment `5727845894` — bounded cancellation frame-guard repair proven by real DSH.

Current protected pickup base: `61a2ff79aba4e8a5685e779707ad5c4426cf5cc5`,
Skillpack 1.0.1/bootstrap 1.

Pinned DSH: `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`.

This wave is a **provider-free predecessor**, not the complete N1 read/research
worker described later by #687 design commit
`382ebbbb4cdfd2155dacbf0884efda8862a0b7c3`.
It proves that the real pinned DSH ACP server can be owned by the existing
Mastermind ACP process/worker path. It intentionally keeps tool-call updates
unadmitted and uses an inert in-process model adapter. It grants no production
route, provider credential, read tool, OpenCode Go account, or rich resume.

## Capability demonstrated

The tested machine journey is:

```text
WorkerLaunchSpec (READ/RESEARCH, clean exact git base)
-> AcpNativeProcessOwner launches exact signed Node + fixed DSH ACP bundle
-> Python agent-client-protocol 0.12.1 initializes the real DSH ACP v1 server
-> DSH creates one real Agent/session
-> Mastermind selects the exact requested model through DSH's opaque
   canonical [provider, model] ACP selector
-> inert DSH model returns one schema-valid JSON response
-> existing AcpReadOnlyTurn/AcpWorkerAdapter validates it
-> existing WorkerResult/CollectionReceipt reports success
-> workspace remains unchanged
-> DSH process and owned Python tasks settle
```

Negative paths prove:
- schema-invalid model output becomes `INVALID_RESULT / ACP_RESULT_REJECTED`;
- cancellation of a real in-flight DSH prompt reaches a known
  `CANCELLED` WorkerResult and settles;
- a real DSH tool call remains refused by the current read-only ACP policy and
  is preserved as effect-unknown rather than silently elevated.

No external model/provider request is made. The fixture's `FixtureAdapter` is
the only model implementation and is bundled into the fixed process.

## Source surface

Tracked changes:
- `integrations/acp_worker/turn.py`
- `integrations/acp_worker/adapter.py`
- `tests/test_acp_worker_turn.py`
- `experiments/harness_convergence/dsh_worker/acp_fixture.ts`
- `tests/harness_convergence/test_dsh_acp_worker.py`
- this runbook

No Worker lifecycle, broker schema, provider catalog, Model Router, subscription
binding, credential owner, workflow, Agent OS, N0/#756, A2/#692, or OpenCode Go
source is changed.

## Common seam 1 — provider-scoped ACP model selector

Pinned DSH ACP exposes model select values as canonical JSON arrays
`[provider, model]`. `WorkerLaunchSpec.model` remains the provider-neutral
plain model id and may not contain that opaque ACP encoding.

`AcpProfile.model_option_provider` is therefore a closed secret-free profile
fact. `model_option_value(model)` produces canonical compact JSON only when a
fixed provider is present; legacy profiles remain plain-model behavior.

The turn:
- verifies the expected encoded value is advertised;
- sets that exact value when necessary;
- compares prompt-time config updates to that encoded value;
- continues to report the plain `spec.model` as observed Worker model identity.

The provider string and model are still token-validated. This does not enroll a
provider or let a Job inject arbitrary ACP selector syntax.

## Common seam 2 — cancellation frame guard

A real DSH cancellation produced a valid already-in-flight
`agent_message_chunk` after Mastermind had set the semantic
`ACP_CANCEL_REQUESTED` error, and before DSH returned terminal
`stopReason=cancelled`.

Previously `_TurnFrameGuard.admit_update` rejected any update whenever
`turn._error` was already non-null, even if the current update introduced no
new violation. The strict frame owner converted that to `UPDATE_NOT_ADMITTED`
and made a known cancellation effect-unknown.

The repair makes `AcpReadOnlyTurn.validate_update(..., commit=False)` return
the refusal introduced by **that update**. The frame guard poisons only when
that return is non-null. Existing semantic error state is never cleared or
overwritten.

A valid in-flight text update can therefore cross framing during cancellation,
while a new unadmitted tool update still poisons the frame.

## Fixed native supply

Supply root used for executed proof:

`/tmp/mmx-dsh-research-20260917-sol-001/n1-supply`

That location is a local reproducibility cache, not a company package registry.

`supply-manifest.json` records:
- schema: `mastermind.dsh_n1_fixed_supply/v1`
- upstream commit:
  `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`
- upstream archive SHA-256:
  `61ea8b495bec3f1debcfd58b95350edb2d48548493e0af4111244399dc29dd22`
- upstream lock SHA-256:
  `ca131858949bd12b2acfc227b1af7dfa3c8d65e74b234824d5c741e6421010a1`
- Node binary SHA-256:
  `ebd2d552c7bebde593dd0390530963ad28de56bccde6ce387cdbe55fb0b6fb8e`
- fixture entry SHA-256:
  `38584b0b13ff97458922505bfe7ea6fde15cea0c2fe476b7319fdcfe8f24e2b6`
- built fixture SHA-256:
  `ed789cd8a0dc7e818dda93e6953e353329f4f869055ae3f80bba3e81a0790c44`
- strict typecheck: PASS
- upstream ACP declarations: PASS
- lifecycle scripts executed: false
- provider calls during build: 0

The fixed external package receipt includes the pinned
`@agentclientprotocol/sdk@1.4.0` package used by DSH. Python controls the other
side with `agent-client-protocol==0.12.1`; interoperability is proven by the
real process tests rather than inferred from package version numbering.

## Executed verification

Environment:
- CPython 3.12.14
- pytest 9.1.1
- Python `agent-client-protocol==0.12.1`
- exact fixed Node/DSH supply above

Focused native/common suite:

```sh
MMX_DSH_N1_SUPPLY=/tmp/mmx-dsh-research-20260917-sol-001/n1-supply \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/tmp/mmx-dsh-n1-venv/bin/python -m pytest --noconftest -p no:cacheprovider -q \
  tests/harness_convergence/test_dsh_acp_worker.py \
  tests/test_acp_worker_turn.py \
  tests/test_acp_worker_broker.py \
  tests/test_acp_probe_boundary.py
```

Fresh result: **109 tests, 0 failures, 0 errors, 0 skips**.

The separate real Python ACP SDK conformance script:

```sh
/tmp/mmx-dsh-n1-venv/bin/python tests/acp_sdk_conformance.py
```

Fresh result: **PASS, 13 cases**, provider-free subprocess peers.

The script currently emits a CPython event-loop-close destructor warning after
its successful result on this macOS environment. Its own cases, fixture exit,
cleanup assertions and process exit are successful. This warning is not treated
as proof of a DSH defect or suppressed in source by this wave.

### Discriminating mutations

Two in-memory forbidden mutations were executed without changing source bytes:

1. Replace provider-scoped model rendering with legacy plain-model rendering.
   The exact provider-scoped selection test fails with
   `ACP_MODEL_UNAVAILABLE`.
2. Restore the old frame-guard rule that rejects whenever any turn error
   pre-exists. The cancellation-frame regression fails because the valid
   in-flight update becomes `UPDATE_NOT_ADMITTED`.

After each process, imported module state ended with the subprocess; source
bytes were never edited by those mutation probes. The fresh green suite above
runs the real candidate.

## Real-native cases

`tests/harness_convergence/test_dsh_acp_worker.py` runs these cases against
the actual pinned DSH ACP process when `MMX_DSH_N1_SUPPLY` is present:

1. success -> existing `WorkerResult.SUCCEEDED`, exact structured output;
2. invalid result -> `WorkerResult.INVALID_RESULT`, no structured output;
3. in-flight cancellation -> known `WorkerResult.CANCELLED`, settled owner;
4. DSH tool call -> current read-only profile refuses it and preserves
   effect-unknown status.

Every case uses an exact clean temporary git workspace and the existing native
owner. Positive/known-terminal receipts require unchanged workspace and settled
process/capture state.

## What this does not prove

This predecessor does **not** prove:
- useful read/research tool work;
- N0/native pre-prompt capability attestation in the ACP worker;
- production OS sandbox policy for this ACP process;
- OpenCode Go or DeepSeek provider admission;
- real provider identity or credential origin;
- provider quota/economics;
- write/test authority;
- resume or rich sustained operator behavior;
- parent consumption of a useful research answer;
- any harness quality advantage.

The `tool-call` case is intentionally negative and demonstrates the next
policy boundary.

## Continuation

The parent design is #687
`docs/superpowers/specs/2026-09-18-dsh-acp-read-research-worker-design.md`
at `382ebbbb4cdfd2155dacbf0884efda8862a0b7c3`.

After this provider-free predecessor is reviewed/accepted, the next useful
capability is:
- pre-prompt native attestation through existing OHF;
- exact observed-tool lifecycle allowance in ACP;
- two bounded read-only DSH tools;
- OS sandbox;
- provider-free scripted read-tool journey;
- then, separately, a real provider canary only after existing Go realm/binding/
  capacity/canary/usage gates are cleared.

Do not widen this predecessor into provider activation or rich resume.
