# T3 Code — Capacity Fabric source wiring

Parent: [#983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
This source candidate connects the native T3 provider format to existing local
gateway owners. Installed activation and `t3_code` consumer acceptance remain
under the original programme and its receipts.

## Retained source behavior

The defaults prepare `fabric_claude` and `fabric_experiential` entries for the
existing Anthropic and Experiential gateways. T3 selects a model within that
explicit provider binding. Gateway owners retain admission, credentials,
request effects and provider-refusal handling. The adapter introduces no
cross-pool chooser, alias cascade, independent cooldown or retry owner.

| Component | Existing responsibility used by this source |
|---|---|
| `endpoints.py` | Fixed default gateway locations, local token inputs and catalogue reads |
| `registration.py` / `__main__.py` | `status`, `plan`, authorized `apply`, and `verify` over those bindings |
| `t3_config.py` | T3's provider settings format, backup/atomic write and separate provider homes |
| Experiential gateway | Existing durable admission, bounded queue, key selection and one upstream send |
| Capacity Fabric view | Read-only current observations, with `admission_authorized=false` |

Default registrations point to `127.0.0.1:8312` and `127.0.0.1:8311`.
Registration preserves unrelated providers and the existing default model.
A configuration write does not establish that a running thread used it.

## Experiential Anthropic Messages surface

The incumbent gateway adds `POST /v1/messages` and
`POST /v1/messages/count_tokens` through its existing admission owner.
The operator-deployed `EXPLABS_ANTHROPIC_MODELS` list is the exact model
boundary for this wire surface:

- Empty configuration refuses before RPM/slot reservation.
- The request model must exactly match an admitted slug.
- Routing overrides and invalid/duplicate JSON are refused.
- An optional `x-fabric-plan-policy` header binds to the deployed catalogue;
  a mismatched digest is refused before admission.
- Streaming, typed refusals and the single-send boundary stay with the
  existing gateway. No new model/pool fallback is introduced.

The new wire helpers are in
`ops/native_fabric/experiential_proxy/anthropic_policy.py`. They reuse the
incumbent strict JSON and refusal types; the historically sealed
`control_plane/experiential_plan_policy.py` and provider profile retain their
original bytes. The existing paired CI archive includes the new leaf module
alongside the gateway so it executes the complete source closure.

## Source-scope correction

The later branch proposal at
[`ecbbbc0563c74db0945972ac4cd4481f0853a55f`](https://github.com/mastermindx-market-intelligence/Mastermind/commit/ecbbbc0563c74db0945972ac4cd4481f0853a55f)
introduced a separate `unified_router` service and a default port8313 entry.
Its implementation independently selected pools/models, maintained route
cooldown eligibility and could read provider keys for direct dispatch without
an incumbent placement/admission decision. It is excluded from this source
delivery, together with its dedicated tests and default registration.

The inspected implementation sent once per HTTP request; its failure state
affected later requests. The exclusion concerns control ownership, not a
claim that the same request was automatically replayed. Any broader all-pools
feature must be integrated through existing placement, admission and
credential owners, with their original grant and effect semantics.

This correction preserves the original Capacity Fabric monitor/read feature
and the independently scoped existing-gateway protocol/registration work.
The monitor cannot supply execution or routing authority.

## Historical claims and remaining acceptance

The earlier branch document reported November9 gateway deployment,
registration and backups, with receipts said to be in its delivery thread.
This source recovery has not verified those installed effects and does not
relabel those claims as current acceptance. Their original provenance is
preserved at the immutable commit above and remains with #983.

Source/default removal does not attest that a port8313 service was stopped,
that an installed `capacity_fabric` entry was removed, or that a selected
runtime changed. Existing provider entries are preserved by registration;
any live reconciliation requires the original owner, exact receipts and
current authority. The pre-existing direct Experiential provider is likewise
outside this source correction.

The original release boundary remains: select and verify the exact source,
prove installed gateway bindings and fresh runtime observations, then retain
real T3 launch, occupancy and result-consumption evidence under #983.
#2182's original uncertain publication and all credential/runtime holds remain
unchanged. No provider call, installation or consumer activation is claimed.
