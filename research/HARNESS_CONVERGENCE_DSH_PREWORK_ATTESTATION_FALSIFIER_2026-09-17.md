# DSH pre-work attestation: protocol boundary and executed owner-gate falsifier

Date: 2026-09-17. Parent: `harness-convergence-dsh-teardown-20260916-sol-001`, existing Mastermind PR #687. Evidence marker: `harness-convergence-dsh-prework-falsifier-20260917-sol-001`.

**Disposition: AUTHOR-SIDE CONFORMANCE EVIDENCE / DRAFT / PRODUCTION INERT.** Current Chairman takeover and continuation authorize this additive research record. It adds no implementation, native adapter, source-owner transfer, Executive Job, provider turn, deployment, or release authority. The eight preceding research artifacts remain intact. This is not another harness teardown or a replacement programme.

## 1. Outcome and bounded decision

Mastermind needs heterogeneous models to complete real coding, research and sustained operator work with useful company context, governed tools, readable evidence, and safe continuation. A protocol connection is not that outcome.

The next DSH realization must establish an actual effective environment before a work turn, while retaining the existing Worker/OHF lifecycle and capability owners. This review asks one narrower question:

> Can the pinned, stock DSH ACP pre-work responses alone truthfully populate Mastermind's existing rich-harness attestation and authorize the first work turn?

**Decision: not from those response fields alone.** The protocol supplies a useful native session and route-selection transport, but it is not a complete effective-environment attestation. A native/host-owned evidence producer is still needed. Preserve `mastermind.worker_adapter/v1` and `mastermind.operator_harness/v1`; this result does not justify a new ABI or universal Harness OS.

This conclusion is scoped to the official pinned stock ACP implementation. It is not a claim about every third-party DSH bridge, every future upstream release, or an already-installed production adapter.

## 2. Immutable evidence identity

Protected Mastermind procedure/source: `42d210bc07a75234092ff5be71f6038ccacaa884`, Skillpack 1.0.1 / bootstrap 1. Research parent before this addition: `ffb02ad6542dcae47c640dade53eb1b5d1c56e97`.

Official upstream: `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`.

| Source | Git blob | Decisive range |
| --- | --- | --- |
| DSH `packages/acp/acp/src/index.ts` | `b346dd763dd7c58641b072e688efd1fafba03d08` | 176-235: initialize, authenticate, session creation and returned fields |
| DSH `packages/acp/acp/src/model-control.ts` | `9138bcdcd7dd5b580249ebaa1659e7536d4c3820` | 143-230: catalog-derived configuration state and route resolution |
| DSH `packages/acp/acp/src/session.ts` | `3fff075359b525269311b87a971b629a50392f38` | 119-172: MCP mounting during create/resume |
| DSH `packages/acp/acp/src/mcp.ts` | `527b064bba60048d1d237e3218c0fa376281d5d5` | 21-74: stdio/HTTP client composition |
| Mastermind `control_plane/operator_harness_contract.py` | `54df0b7a5abf0b713d5e37a40059802b1a894f08` | 957-998 and 2706-2825: requested/observed contract and comparator |
| Mastermind `tests/test_ohf_p1a_operator_harness_contract.py` | `70328d1e5423323e9ff58412e1f1d3a2bc14e209` | 143-204: existing synthetic reference fixtures |

Upstream entry/session/MCP source downloads were checked against the previously retained exact Git tree; the model-control source was read through the exact-commit GitHub file path. The two Mastermind blobs were checked in the retained source workspace and match protected `42d210bc...`.

Primary-source links:

- [ACP entry](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/acp/acp/src/index.ts)
- [Model selection](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/acp/acp/src/model-control.ts)
- [Session composition](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/acp/acp/src/session.ts)
- [MCP composition](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/packages/acp/acp/src/mcp.ts)
- [Mastermind comparator](https://github.com/mastermindx-market-intelligence/Mastermind/blob/42d210bc07a75234092ff5be71f6038ccacaa884/control_plane/operator_harness_contract.py)

## 3. What the stock protocol does and does not establish

### 3.1 Session identity and protocol support are not effective capability evidence

At the pinned source, `initialize` returns protocol version, static `agentInfo`, selected ACP protocol capabilities, and an empty authentication-method list. `session/new` returns its new session ID plus configuration options after composition and a persistence flush. Neither response contains the complete effective plugin/tool closure, executable digest, sandbox/network enforcement observation, provider-principal attestation, or native-helper ceiling required by the Mastermind profile.

The static ACP `agentInfo.version` value is not an executable supply-chain digest or proof of the installed application version. ACP image/MCP/session protocol advertisements are not a census of the effective model-facing tools.

`authenticate` resolves successfully without authenticating a caller or provider principal. That is a documented trusted-stdio-controller design, not a defect to conceal with a fabricated `AuthRealmFact`. Mastermind's existing process/realm/transport owners must provide the needed authentication evidence.

### 3.2 A configured model is not an observed served model

`AcpModelControl` renders options from the LLM service's provider/model catalog and resolved selection. This supports selection consistency but does not independently attest the actual served model. After a previously resolved state, failed route re-resolution can retain the selected option with internal `routeAvailable=false`; the presence of a displayed option is therefore not a fresh route-health receipt either.

Do not copy `requested_model` or a model option into `ObservedHarnessAttestation.served_model` merely to pass TX-4. A backend unable to supply the required pre-work observation remains unsupported for that profile unless an existing, separately authorized bounded probe satisfies the owning law. A hidden bootstrap inference is not a no-work initialization.

### 3.3 No model prompt does not mean no effects

Session create/resume mounts the requested MCP clients during Agent setup. Standard stdio entries carry an absolute command, arguments and environment; HTTP entries carry URLs and headers. New-session creation also flushes an empty session to persistence before returning.

Consequently, a future no-provider probe must freeze application/profile composition, allowed MCP mounts and process/network boundaries BEFORE initialization/session creation. Checking only that `session/prompt` was never sent is insufficient to prove no subprocess, network or persistence effects. An empty request MCP list also does not by itself prove absence of host/global plugin capabilities.

These are source-derived effects and ordering, not a claim that this research executed them.

## 4. Executed falsifier through the existing Mastermind gate

A provider-free Python probe invoked the real protected `compare_launch` and `first_work_turn_allowed`, using existing synthetic reference fixtures. It did not install/run DSH, invoke any model/provider, open a provider realm, submit an Executive Job, or modify runtime state. Python and read-only Git commands were used.

The fixture names and values are synthetic Codex reference data, not DSH runtime identities. This is an owner-contract experiment, not a native DSH canary.

| Trial | Actual result |
| --- | --- |
| Fully observed reference fixture | `ALLOW` (positive control) |
| Only handshake-level observations retained | `REFUSE_SERVED_MODEL_UNKNOWN` |
| Model improperly filled from configuration, binary still unknown | `REFUSE_UNATTESTABLE` |
| Effective config identity missing | `REFUSE_UNATTESTABLE` |
| Sandbox observation missing | `REFUSE_UNATTESTABLE` |
| Network observation missing | `REFUSE_UNATTESTABLE` |
| Required capability missing | `REFUSE_MISSING_REQUIRED` |
| Unexpected effective MCP | `REFUSE_UNCLASSIFIED` |
| Forbidden effective plugin | `REFUSE_FORBIDDEN` |
| Otherwise complete reference with unknown MCP/plugin census represented only in `unknown_fields` | `ALLOW` (mapper anti-pattern control) |

All ten expected outcomes were asserted. The saved recipe was executed again and reproduced the result bytes exactly.

Result SHA-256: `f3d5d1caee26bca0482b2459ec2dc05391d198d3f2740944d51224958345c2b3`.
Recipe SHA-256: `121afaa4a21dac1f56640845aadf2c79ae9e0e62fd319052cee2980b3eb2492a`.
Execution environment: existing isolated MacBook review environment, CPython 3.12.14, pytest 9.1.1. No source files were changed for this probe.

### The load-bearing mapper counterexample

The comparator uses actual attestation fields; it does not treat the `unknown_fields` tuple as an automatic veto. An otherwise passing observation with empty MCP/plugin inventories still passes when those inventories are merely described as unknown in metadata.

**Unknown census is not verified empty census.** The future DSH adapter must refuse before publishing an apparently complete attestation when a required effective inventory cannot be observed. Logging uncertainty in metadata while filling required fields from the request is not fail-closed behavior.

This does not establish an exploit in a current production adapter, which was not exercised. It also does not justify rejecting every optional unknown field globally: the profile's load-bearing evidence and existing producer contract must determine completeness. No common comparator or capability-policy change is made by this record.

## 5. Bounded implementation direction and owner map

Keep the existing backend-realization matrix and original product thesis. The next DSH-specific implementation question is an observed-evidence producer and its existing-gate consumer, not a second runtime:

1. **Before startup:** the current supply/profile/native-process owner fixes exact executable/dependency/profile identity and a minimal explicit composition. No arbitrary user-selected executable, provider endpoint, credential, MCP command, fallback, automatic producer or plugin installation is admitted by the Job.
2. **During controlled initialization:** the native DSH adapter obtains only the session/route facts the protocol actually supplies. An admitted native/host observation path must separately establish required effective tool/plugin/skill closure, config identity, policy enforcement and realm/model evidence. Observations bind to the existing Attempt/process generation; no new identity registry or transcript store.
3. **Before the first work turn:** unavailable load-bearing evidence returns the existing typed refusal/unsupported path. Do not manufacture an `ObservedHarnessAttestation` from requested settings. On complete evidence, use the existing OHF comparison rather than a new admission service.
4. **Negative proof first:** inject an unobserved census, unexpected global plugin/MCP, changed profile/binary, absent model evidence, retry/fallback exposure, and wrong resumed session/workspace. Refuse before work. Account for setup-time MCP and persistence effects, not only model requests.
5. **Real vertical later:** only after source review, supply/runtime/realm/profile admission and effect gates, run one bounded native task with actual input, visible tool work, validated result, cancellation/cleanup and exact parent consumption. Preserve common v1 contracts and incumbent HF1/OHF/ACP/capability ownership.

No fresh provider experiment, activation, supply installation or runtime profile is authorized by this research decision. Shared-owner adoption and independent review remain explicit gates. Where native served-model or full effective-state observation is unavailable, the honest output is unsupported for that profile, not false parity or a global rejection of DSH.

## 6. Relationship to A2 repair and continuation

#692 remains the separate host-factor evidence-lock slice at `a5ad195e224cacb364862e4987f669b2bb3f261e`; this research adds no files to that implementation PR.

At this phase's terminal CI observation, run `35194351639`, test job `105113940108`, completed successfully, including its full repository test gate. Five exact-head check-runs report success: repository test, CodeQL, and Python, JavaScript/TypeScript, and Actions analysis. This supersedes the prior nonterminal CI observation, not the separate release/acceptance requirements. An exact-head independent review was requested on #692 as review `5232606865` and assigned through GitHub to `mastermindx-3`; request/delivery is not a verdict or worker START. Broader Agent Evaluation adoption remains unconfirmed.

The immediate Sol action is to consume attributable #692 review and the existing owner's adoption decision, then adjudicate its bounded release with current-base compatibility. In parallel, this DSH finding supplies the exact first native-conformance implementation boundary to the existing harness/capability owners; it must not be lost behind the host-factor supporting slice.

### Stop and recoverability

This is a material conformance-decision checkpoint, not harness completion. Resume from this record, the current #687/#692 heads, and their latest exact review/owner returns. Do not repeat the eight-artifact teardown, 787-test A2 proof, or this ten-case probe unless their input identities change. Do not expose future sealed holdouts, create a replacement programme or another scheduler/host/evaluator/permission plane.

No native DSH process, provider/model call, credential action, new worker, deployment, route change or background Sol continuation occurred. The retained MacBook A2 workspace is unchanged; its previously reported canonical-release discrepancy remains separate housekeeping, not permission for forced cleanup.

## Appendix — exact provider-free reproduction recipe

Run from a source checkout with the two exact Mastermind blobs in section 2, using the existing isolated Python test environment and `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`. This is public development evidence, not a sealed evaluation holdout. The recipe asserts both behavior and the complete JSON result digest.

```python
"""Synthetic OHF comparator probe; no DSH/provider execution or runtime mutation."""
import dataclasses
import hashlib
import json
import subprocess
from pathlib import Path
from tests.test_ohf_p1a_operator_harness_contract import _requested, _observed
from control_plane.operator_harness_contract import compare_launch, first_work_turn_allowed
assert subprocess.check_output(["git", "hash-object", "control_plane/operator_harness_contract.py"], text=True).strip() == "54df0b7a5abf0b713d5e37a40059802b1a894f08"
req = _requested(expected_config_digest="cfg")
base = _observed()
unknown = dict(served_model=None, harness_version=None, harness_binary_digest=None,
    capabilities=(), effective_skills=(), effective_mcp=(), effective_plugins_or_apps=(),
    sandbox_state=None, approval_state=None, network_state=None,
    effective_config_digest=None, workspace=None,
    unknown_fields=("served_model", "harness_binary_digest", "capabilities", "sandbox_state",
                   "approval_state", "network_state", "effective_config_digest", "workspace"))
cases = [
    ("fully_observed_reference_fixture", req, base, True),
    ("handshake_only_observations", req, dataclasses.replace(base, **unknown), False),
    ("unproven_model_filled_from_config_still_missing_binary", req,
     dataclasses.replace(base, **{**unknown, "served_model": req.requested_model}), False),
    ("missing_effective_config_identity", req, dataclasses.replace(base, effective_config_digest=None), False),
    ("missing_sandbox_observation", req, dataclasses.replace(base, sandbox_state=None), False),
    ("missing_network_observation", req, dataclasses.replace(base, network_state=None), False),
    ("missing_required_capability", req, dataclasses.replace(base, capabilities=(), effective_skills=()), False),
    ("unexpected_effective_mcp", req, dataclasses.replace(base, effective_mcp=("ambient-unreviewed-mcp",)), False),
    ("forbidden_effective_plugin", req, dataclasses.replace(base, effective_plugins_or_apps=("codex_apps",)), False),
    ("empty_census_with_unknown_fields_metadata", req,
     dataclasses.replace(base, unknown_fields=("effective_mcp", "effective_plugins_or_apps")), True),
]
rows = []
for name, requested, observed, expected in cases:
    result = compare_launch(requested, observed)
    allowed = first_work_turn_allowed(result.decision)
    assert allowed is expected, (name, "unexpected result")
    rows.append(dict(case=name, decision=result.decision.value, first_work_allowed=allowed,
        mismatch_reasons=list(result.mismatch_reasons),
        unknown_required_observations=list(result.unknown_required_observations)))
receipt = dict(scope="SYNTHETIC_OWNER_COMPARATOR_PROBE_NOT_DSH_RUNTIME",
    mastermind_commit="42d210bc07a75234092ff5be71f6038ccacaa884",
    contract_blob="54df0b7a5abf0b713d5e37a40059802b1a894f08",
    dsh_source_commit="0d1f50007f9bca3f52b06e1c3074fa14d5fb0720",
    provider_calls=0, dsh_processes=0, runtime_mutations=0, cases=rows,
    finding="unknown_fields metadata alone does not reject an otherwise complete attestation. An adapter must never turn an unobserved capability census into empty observed tuples.")
payload = json.dumps(receipt, indent=2) + "\n"
assert hashlib.sha256(payload.encode()).hexdigest() == "f3d5d1caee26bca0482b2459ec2dc05391d198d3f2740944d51224958345c2b3"
print(payload, end="")
```
