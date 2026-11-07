# M2 attended Hermes: gateway host composition

Parent: [Hermes APPLICATION adapter #2155](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2155).
Assignment: `hermes-capacity-m2-20261106-c3`.
Source/procedure pin: `ad6275a9c4d237bce75e52d0d6a8f41264b4ded5`.
This is an additive consumer follow-on. It does not take the active APPLICATION transport writer's branch or release custody.

## Correct live path

The inspected M2 Hermes source is clean v0.23.0 at
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
Its current `HermesCLI._init_agent` in
`hermes_cli/cli_agent_setup_mixin.py` constructs
`hermes_cli.gateway_agent.GatewayAgent`, which sends `prompt.submit` to the
existing gateway. It does **not** run the primary AIAgent in the CLI process.

The actual in-process gateway constructor is
`gateway/session_execution.py::GatewaySessionAgentMixin._build_fresh_agent`.
It invokes `TurnContext.AIAgent`; the original gateway builds that context in
`gateway/run_turn.py::_run_agent_build_turn_context`.
The native gateway owns session admission, run generation, history, tool execution,
interrupts, worker lifecycle and result delivery. Preserve those owners.

## Added composition

`attended_host.AttendedHost` registers one existing native execution middleware.
The authenticated host supplies a qualified original APPLICATION factory, its
original operation/session/task identities, a current authorization callback,
strict model, and a proved-new admission. A scoped `AttendedTurn` lazily creates
one original binding at the first authorized native request and retains it
across tool calls and facade/agent reconstruction. A failed bind is not retried.

The reserved consumer relation is
`attended -> hermes-attended / hermes_attended_fabric`.
It is **not an enrolled owner relation**. `ApplicationBinding.from_factory`
continues requiring the exact original factory and independently qualified
owner service. No Brain/Ask, mmmeta or mmsecretary identity is borrowed.

The host attaches `turn.create_gateway_agent` to its original
`TurnContext.AIAgent` before native execution. Only the keyless Fabric runtime
is accepted. Existing nonempty credentials, endpoints, credential pools and
fallbacks refuse; they are never silently cleared. Native conversation and tool
options pass to the already qualified `create_primary_agent`.

Activate the same turn around the existing executor invocation, with the
gateway's current context propagation. Its current-authorization callback must
check the original session/admission/generation owner, independently of incoming
LLM metadata. Close on normal completion or interruption; retain the original
close receipt, including unknown/unsettled effects. Local close is not a
provider cancellation or physical lease-release receipt.

## Source integration and remaining installation

This module supplies the tested host-composition seam. It does not automatically
patch or restart the live gateway, edit `config.yaml`, create an alternate
launcher, or add another account, credential, session, lease or usage registry.
The tested follow-on now includes the native keyless resolver extension and
original-admission gateway hook as a pinned Hermes core patch, plus a real
PluginManager entrypoint. [Gateway composition](GATEWAY_COMPOSITION.md) defines
that source integration and its exact limits. These files are not installed in
the live gateway. Setting `model.provider: mastermind-fabric` alone remains an
invalid installation.

The following live prerequisites remain separate:

1. Original APPLICATION owner enrollment and qualification of the attended
   relation, one tool-capable account/model, original admission and settlement.
2. Release/install of the tested native core hook, keyless route resolution and
   plugin entrypoint. The qualified source covers the local in-process gateway;
   managed-worker and non-local paths remain unqualified and refuse.
3. Release/install of the original application handler. Neither port 4142 nor
   the actual owner-pinned endpoint port 50142 was listening on M2 at the
   2026-11-07 01:14 UTC check; the selected installed shim lacked that handler.
4. GLM coding-plan tool/usage qualification and shared account admission.
   The inspected generic APPLICATION pool admitted bailian, not GLM.
   Experiential's original eligibility/explicit-use conditions stay binding.

Oh My Hermes can supply a model/effort choice. The original Fabric owner must
select an eligible physical account and reserve shared headroom. Neither the
category choice nor a native Hermes auth-pool row proves Fabric admission.
Reasoning-effort forwarding, streaming and AUTO/strict-pool qualification remain
their original protocol/selection work, not features claimed by this module.

## Qualification boundaries

Unit tests distinguish retained binding, original close uncertainty, authorization
revocation, wrong session/task, native context isolation, scope re-entry, gateway
route collision and no factory retry after failure. Installed-native tests use
the actual gateway constructor, primary model execution and native tool/result
continuation, against the original APPLICATION client and a loopback fixture.

Fixture factory/host authorization is deliberate test data. These checks do not
prove live service enrollment, CLI RPC activation, a real provider account,
budget/usage settlement or production installation. The M2's concurrently
changed local-Qwen root/secretary selections remain untouched.

## Final candidate evidence

Candidate `83f78197ad0c21ade49059b880582c1fc9f7c61b` passed 81 native-runtime
qualification cases with zero failures/errors/skips and zero external provider
connections. Hosted CI and both Python 3.12/3.13 offline contract jobs succeeded
for that same candidate. The exact source manifest and limits are retained in
[the machine receipt](qualification/gateway_native_receipt.json). Receipt and
documentation commits after the tested candidate do not change those tested
product/test files. Live RPC, shared account balancing and provider acceptance
remain unproven.
