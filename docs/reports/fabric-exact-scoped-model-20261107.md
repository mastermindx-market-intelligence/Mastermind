# Exact scoped Fabric model routing — source proof, 2026-11-07

## Outcome and authority

This slice adds an exact-model constraint to the existing scoped application authority. It uses the incumbent picker, application lease, request intent, native/HTTP dispatch, settlement and usage owners. It creates no new account picker, lease table, queue, credential store or retry owner.

Mission: [Mastermind #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
Contract: [exact-model commission](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6702440510).
Direct continuation: [source-linked ruling](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6702811159).
Verified governing pin: e37dc82f070fd391e29f0dbd0bf46b022166beea.

Paired Macro implementation: abab96df55f82cb5c26459a6f51b568d73a6a6f8, tree d56a8cba688c2d9422dfba8a779714f87901b505, [PR10740](https://github.com/mastermindx-market-intelligence/macro/pull/10740). Its normal push and exact remote ref readback succeeded. Native implementation starts at Mastermind 312be66141bf58c564a11818d63ddd3f958ca0c0; this commit contains its additions.

## Versioned contract

| Contract | Unscoped historical | Scoped AUTO | Scoped exact |
|---|---|---|---|
| A selection | v1, including accepted fixed-pool null preparatory records | v2 | v3 |
| C inspection/binding | original fixed fields | v2 | v3 |
| Public routing | original fixed response | route.v1 | route.v2 |
| Requested model | historical concrete/null semantics | explicit null | canonical concrete model |
| Payload | historical behavior | substitute only selected model | unchanged original model/body |
| Routed request digest | historical concrete null / preparatory AUTO digest | required digest | null |
| Successful scoped result | existing fixed validation | selected = served | requested = selected = served |

The v2 application and observation envelopes are retained. Closed validators enforce the inspection/route version pairing. Existing v1/v2 records are not reinterpreted.

A exact-model selection searches only registered, granted, scoped, compilable candidates bearing that model. The one incumbent picker can select a pool different from the service default. Current policy, grant, source, account, credential reference and fresh room checks remain in the existing transaction.

B recovers the original operation before looking at current routes. For a concrete scoped request it compares the supplied scope with the frozen original before returning a receipt. Historical null-AUTO receipt recovery remains unchanged. A new request cannot widen the frozen capability needs, omit its original body, change the model, or acquire another dispatch through replay.

The existing release-trigger migration remains unchanged. Six additive v3 guards protect concrete requests with null routed digests from update/delete/REPLACE, terminal rewriting, lease substitution and premature release. Their deterministic definitions are verified on initialization. A damaged v3 record is protected by its version and cannot escape through SQL null logic. Zero-step closure remains possible.

## Qwen control form

The existing Bailian Responses driver accepts one additional closed plaintext form for exact qwen3.8-flash: temperature=0, reasoning_effort="none", stream=false, a hard token bound and one user message or system-plus-user messages. Both controls are required together. They become Responses temperature:0 and reasoning:{effort:"none"}; the exact model, prompt (including any /no_think) and input remain unchanged.

The logical and wire digests include these controls. Unsupported models, partial/mistyped controls, tools/history expansions and streaming refuse before preparation. MiniMax and unsupported Go/native grammars are not widened. Requests without these controls retain their prior canonical wire bytes. Source compilation does not prove live entitlement or backend qualification.

## Verification receipts

All provider responses, credentials, grants, qualification and native process evidence in these tests are synthetic. The factory, client, B handler, picker, A SQLite owner and H compiler execute their actual source.

| Proof | Result | Log SHA-256 |
|---|---|---|
| Native auto, scoped, HTTP transport suites | 127 passed; 101 subtests passed; rc0 | 2d8731b54a6717605bd9cca0165e0cc7b5c6efda09a4787ca18904a72e7ae93a |
| Existing Macro factory/inspection/client/native-client suites | 195 passed; rc0 | ea9c2cdf996dcc36d83e77ba6ff118fca0c8903b4ef6ea0785a3ac7c33d68ad6 |
| New actual C/auth/client/B/picker/A/H composition | 31 passed; rc0 | e39109a775fcce56e08a3811f9278b362327da3b0dcddca448fde82516781af3 |
| Exact composition under the newly enrolled CI command | 31 passed; zero skips; rc0 | e1a3e7ff834e0f96dda2e9d9cb2d388dd68413e40af74257ee7e46de130b48c7 |
| CI shard, policy and RWE contracts | 408 passed; rc0 | 69110520a8f77501daa69db7764ba1af34726bc5bea646995af5400287737840 |

The final trailing-newline correction was AST-identical. The paired fixture pin was updated to those exact bytes and all 19 native source/fixture blobs were verified again. Both repository diffs passed whitespace checks.

The 31-test composition covers pure immutable narrowing; fresh owner/workload/capability checks before credentials; exact Qwen controls; requested/selected/served equality; unchanged original digest and null routed digest; one lease/send; scope and model conflicts; observed usage on malformed or mismatched replies; no invented pool attribution; close preserving observation; and receipt-only recovery without another send or usage count.

The canonical CI now includes the native AUTO/scoped suites and a separate no-skips exact composition proof using the pinned Macro commit. Its actual GitHub verdict is a separate receipt; this report does not claim that verdict or a deployment.

## Paid source returns and remaining runtime work

Exact02 (fabric-app-exact-scoped-model-20261107-02, controller 17209) terminated rc1, reason provider_turn_limit, without a usable patch. The footer reports process receipt saved, provider outcome recorded and transport cleanup; usage receipt is missing. No retry, provider permission denial, token count, cost or acceptance is inferred. Root performed this bounded direct continuation after recording that result.

J preserving-migration01 (fabric-app-j-preserving-migration-20261107-01, controller 80170) returned source with rc0, but it is not accepted or installed. The exact returned gzip patch is retained under review_evidence/fabric_application/j-preserving-migration-source-candidate-20261107.patch.gz, SHA-256 2fea72fcd5053f2ce16bcdfe685c8f761e9a47379baee4886a1bd93223355a31; expanded patch SHA-256 55abc3c1c0b71a49c8e5240d633d2d7b1d33fa107154328cd32f4146bf409c28.

Static judgment identified repairs needed in that candidate: bounded interpretation of the unchanged original string-envelope receipt; complete-or-held import of both original slots; installed config/manifest binding; legacy helper quiescence and fail-closed marker errors; strict directory fsync for the one-use intent; a recoverable preserving upgrade; and UNKNOWN on ambiguous transport failures. The returned activation procedure must not be used as written. Keeping the candidate as source evidence does not activate it.

The existing original J UNKNOWN state and C3 collection cache remain intact. Production activation, real account/recipe qualification, native-purpose factory/consumer/startup joins, E3's explicit model migration and the remaining VPS consumer proofs are still owed. No new Executive Job or service-principal plane is required for model-only Metabolism calls; the existing A/B/J application-operation owner remains the intended join.
