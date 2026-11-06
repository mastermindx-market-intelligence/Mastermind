# Hermes primary inference through APPLICATION Fabric

Programme: [Mastermind #983 P2](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6695933514).
Operation: `hermes-primary-fabric-inference-20261106-sol-01`.
Parent task tree: C5 in `docs/SHARED_MODEL_POOL_CONTROL.md`, PR #2109.
Procedure/source base: `2f60dc913622da61a65a2cc6f8a793a81c61eea1`.

## Outcome

Hermes primary reasoning uses the existing qualified APPLICATION model/account
owner with internal host/session identity. Provider credentials, entitlements,
physical-account quota, reservation, billing and settlement stay at Fabric.
An ordinary turn, native tool round trip and original-result recovery must be
proved with a real eligible account before live acceptance.

## Native and owner evidence

Installed M2 Hermes v0.23.0 is clean at
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
Its supported ProviderProfile.create_client extension accepts an OpenAI-shaped
client. Native retry/fallback and middleware context must be qualified together
with that client.

Mastermind #2060 is merged. Reuse its APPLICATION consumer pattern in
`brain/fabric_inference.py`, not its text-only input/output restriction.
Macro #10740 at `2ef828e569b683b9dfaa94f81116da3ac55f6186` owns
ApplicationFabricFactory, llm_auth and FabricInferenceClient.
Its native protocol currently refuses streaming; its shared request whitelist
does not accept response_format. Its source-defined transports remain
unqualified/application-disallowed. These facts are blockers to live serving,
not permission to bypass qualification or install local provider keys.

## P2 implementation and acceptance

| Phase | Capability and proof |
| --- | --- |
| Native contract | Real v0.23 provider/client/middleware/error classification, ordered history, tool IDs and bounded responses. |
| Adapter | Disjoint native adapter and tests, current APPLICATION factory composition, no network broker or credential/routing/account store. |
| Owner integration | Coordinate missing role, routing requirements, structured-output, stream/cancel and original-result capabilities through the incumbent APPLICATION owner. |
| Qualification | Actual authenticated ordinary turn and harmless native tool conversation; original provider/model/account attribution, usage/budget enforcement and recovery with no duplicate effects. |

The adapter never executes model-requested tools. Hermes owns tool execution.
Unsupported semantics must refuse before dispatch; uncertain results never
trigger another provider request. Host strict selection narrows eligible
owner selection; an ineligible pin cannot relax to AUTO.

Automatic routing belongs to existing ModelRouter/Capacity:
suitability and required capabilities, qualified APPLICATION entitlement,
host restrictions, expected latency, price and physical-account headroom,
then the original atomic reservation. Model/account relationships are
many-to-many; pool membership never creates another physical quota bucket.

## Source custody

This package and its tests are the new source scope.
Do not change #2134 selected-child/auth/installer source, #2147 native Fabric
worker delegation, #2109/#2148 policy source or Macro #10740's original branch
without current source-custody reconciliation. The separate worker API
`fabric_request` is not an inference API.

Source, tests, native integration, protected release, installation, actual
provider serving and product acceptance are distinct. This initial plan is
source-persisted; no provider call, service activation or live result is claimed.
