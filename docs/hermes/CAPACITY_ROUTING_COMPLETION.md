# Hermes capacity-routing completion

## Scope and source custody

Current Chairman assignment: assess the prior “Audit Hermes capacity routing”
session and complete its implementation. The exact prior chat was not retrieved;
the recovered requirements and current source are the evidence used here.

Canonical programme: [Mastermind #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983),
including the [original two-lane Hermes contract](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6695933514)
and [this recovery's source-linked plan](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6703172666).
Operation: `hermes-capacity-routing-completion-20261107-c4`.
Protected compatible procedure/source base:
`5f8c13da926011fb5fdc8cea21287b532ac968db`.

The active primary APPLICATION carriers #2155/#2186 and final composition #2175
remain with their live writers. This change extends the already merged OMH
integration (#2162/#2168), preserving its single native tool and read-only scope.
It does not reopen their source work, enroll a production role, or change the
shared selector.

## Audit findings

1. Installed upstream Hermes at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`
   constructs an independent AIAgent per native delegated task. It can inherit
   the parent's provider/key but has a distinct session and model-call loop.
   Concurrent inference calls using that physical account share its allowance;
   a child is not a free extra provider lane. Agent count and simultaneously
   active requests are different quantities.
2. Z.ai's [official usage policy](https://docs.z.ai/devpack/usage-policy)
   describes concurrency limits as plan-dependent and dynamic. The user's
   approximate seven-lane expectation is not a verified fixed entitlement.
   This change hard-codes no provider capacity.
3. Observed M2 default Hermes uses local `qwen3:14b`, allows up to 32 native
   children and enrolls only the read-only capacity MCP server. This is not
   evidence of the user's separate Ubuntu/z.ai bot configuration.
4. OMH was installed and callable, but its model/effort suggestions had no
   canonical capacity-preview consumer. This change closes that concrete
   read-only integration gap.
5. Native worker delegation source #2147 is merged. Real native execution
   enrollment/START/result acceptance is separate and not proved by that merge.
   Controlled Executive role profiles already disable built-in delegation and
   use exact selected-child `mmx_delegate`.
6. The inspected primary adapter #2155 at
   `470b479b53e0120b26f238d9251489ebdef260c5` binds an exact primary agent,
   session, admission and turn. It does not construct ordinary native-child
   admission bindings. Copying its provider into a child is insufficient.
   Its active owner remains responsible for the APPLICATION composition and
   installed role acceptance.

## Implemented outcome

The existing `mmx_omh route` tool/command obtains actual OMH advice, then submits
explicit validated task class and complexity to the existing native capacity
preview. Canonical selection remains in Fabric. No model, account, pool,
credential, retry or fallback is taken from OMH. Native MCP permission remains
required and is not self-granted by the plugin.

Output separates recommendations, declared requirements, and the canonical
non-reserving preview. Refusals do not leak a fallback recommendation. The native
profile, source descriptor and registration are rechecked after the external
call. The same slash command supports existing conversations through the
incumbent command owner; model tools follow Hermes' normal next-session rule.

## Qualification and remaining acceptance

The new tests first failed on the absent route action (14 failures). After the
implementation and current-profile revalidation repair, the affected existing
suite passed **199 tests and 9 subtests**:
`tests/test_hermes_omh_native.py`,
`tests/test_hermes_omh_recommendations.py`,
`tests/test_hermes_omh.py`,
`tests/test_executive_plan_schema_versions.py`, and
`integrations/hermes_delegate/tests/test_delegate.py`.

A direct read-only call to the incumbent M2 preview returned
`PREVIEW_ONLY`, `reserved: false` and
`selection_rechecked_at_request: true`. This is a transport baseline, not the
native composed canary or proof that the previewed worker model can execute.
Native composed qualification, exact protected release, installed command
readback, and actual concurrent APPLICATION/worker-account acceptance remain
distinct gates and will be recorded with their real receipts.

The bounded paid census retained its original run
`hermes-capacity-routing-contract-census-20261107-c4-01` and reached terminal
failure (rc1, unrecognized MiniMax-M3/turn limit). Result SHA-256:
`d2683e6b9a81a08ff66695353c23fb1505344fdc7fcdac68eb0be2fa6f7f1816`.
It produced no audit, was not accepted, and was not retried. Direct source work
is retained for principal integration judgment and the uniquely available
installed-runtime access; no native labor was silently substituted for that
Fabric worker.

Full mission acceptance still requires primary and concurrent child calls to be
admitted through their original owners, share one physical-account capacity
ledger across aliases, honor its configured ceiling, and retain original
request/lease identity through interruption. This preview implementation alone
does not establish that outcome.


## Composed native proof

The actual installed Hermes owner/loader, tool registry, command dispatcher and
MCP client passed on the implementation at
`27dbfa14ed572da5eecad7fc8d8f6a00747ec94c`.
Evidence: `integrations/hermes_omh/qualification/capacity_route_receipt.json`.
The native tool **and** slash command returned
`ROUTE_PREVIEW_NOT_ADMITTED`; the real capacity owner returned a non-reserving
preview, and forced-pool/cross-profile requests refused. The native guarded
process made zero network connection attempts. No provider inference,
reservation, admission, worker dispatch or production profile edit occurred.

The implementation plugin is SHA-256
`e72da67dfb64314c849c8b44b44c25e7707e3576f003df7a3ccabf3326a2cb70`.
The receipt also binds the final qualification harness SHA-256; the harness was
corrected to use Hermes' own `hermes_yaml`, preserve its bounded connection
timeout and acquire the incumbent per-profile plugin manager. This removed a
test-only second-manager collision without changing plugin behavior or the
Hermes dependency environment. The earlier failed harness attempts are not
counted as successful qualification.

The route observed during this proof is a time-local preview, not an execution
or model-quality endorsement. In particular, the earlier paid worker's
MiniMax-M3 launch failure is retained; a successful preview does not erase it.
Protected PR: [#2196](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2196).
Protected merge and installed production command readback remain separate from
this isolated-profile native proof.


## Hosted-stack repair

Initial exact-head hosted run
[42346944088](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42346944088)
failed in `hermes_models/tests/test_contract.py`: an inherited assertion still
expected commercial ModelArk aliases to be absent until already-merged #1824.
The routing-preview implementation does not change that catalog.

The existing Hermes owner's exact repair from
`d7d5bfdb4bc656473a7e940dee07d0b437aed40d` was adopted as a dependency, matching
the #2155 test postimage Git blob
`a7cc6976bcd71872a18a1675a8df73887520f918`. This reuses the original repair.
The test verifies exact present-but-inert aliases, unchanged enabled/autonomous
flags for every provider, and a separate legacy absent-catalog case. No production
model/routing behavior, credential, admission or capacity policy changed.
The complete affected `hermes_models` suite passed **23 tests** locally.


## Original queue conflict reconciliation

The original native queue entry was applied once, then reported UNMERGEABLE
against its three-PR predecessor base `e41fa100251b692567751936bdc7243be8aa15db`.
That base is a queue composition, **not a protected merge receipt**; protected
master remained `5f8c13da926011fb5fdc8cea21287b532ac968db`.

A real `git merge-tree` analysis isolated one content conflict:
`integrations/hermes_models/tests/test_contract.py`. PR #2179's published
head `9eec2b2c9f4a0c25ae6a2b127abcb401da9336ad` carries test blob
`af180a1b66febba5531ad89a21a65cdcada8c953`, while our first dependency reuse
carried the other existing Hermes variant. This carrier now consumes #2179's
exact **already-published** test postimage so it can compose with that predecessor.
Its 23-test package passes, including explicit absent/present/eligible fixture
cases that still grant no authority.

This does not publish or consume #2179's separate unpublished c744ef repair,
change its realm pin, retry its refused publication, or alter its queue effect.
The original #2196 branch, PR and operation remain the delivery carrier.
The unchanged native routing implementation retains its earlier qualification;
the new exact PR head still requires its own hosted checks and queue readback.
