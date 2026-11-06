# Shared model-pool control: company-wide audit and implementation

Programme: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC. Secretary consumer: #2082, merged #2085.
Operation: `shared-model-pool-control-20261105-c4`.
Protected source/procedure pin: `5bfbbc7e5e4f08db73644cf6332be7c75fd68915`.
Chairman assignment: November 5, 2026; audit Mastermind OS model consumers and make the incumbent shared pools flexibly configurable without duplicating keys or breaking consumers.
This is a source task tree, not a new runtime/project/permission database.

## Product outcome

One operator workflow for existing model resources: inspect configured pools, models, credential-reference readiness and consumer bindings; propose a bounded change; inspect its exact impact; publish through the existing configuration owner; admit new work against that revision while original requests retain their selected identities. Adding a compatible model or rotating a key reference must not require editing every consumer. A pool that is configured but unqualified must remain visibly unavailable, not silently runnable.

DONE_WHEN: all named application/worker/Secretary consumers use the same canonical resource definitions and owner-backed capacity/account limits; supported changes are revision-fenced, recoverable and explainable; real installed consumers demonstrate correct current routing and original-request recovery. Source, deployment, account qualification, and real provider usage remain separate evidence. Zero downtime is an objective, not an unproved guarantee.

## Canonical owners and immutable boundaries

- Native Fabric `pick.py` owns worker/application selection within qualified policy. `lease_broker.py`, existing account configuration and lease database own accounts, admission and leases. No replacement router or ledger.
- Executive ModelRouter owns task suitability, not provider credentials or every HTTP completion. Executive Runtime owns Jobs/Attempts/effects for worker tasks.
- Macro Shared AI Provider Control and the application integration in Mastermind #2060 / Macro #10740 own application inference, operation identity, usage and permitted product profiles. Do not turn each completion into a new Executive Job.
- Existing role-specific Workspace/COO authentication and original Dialogue/Wake return remain distinct from shared capacity. Shared pools do not share user identity.
- Existing source/configuration publishers and finite installer prepare/apply/reconcile actions retain writes, CAS and rollback. The new configuration helpers must not create a service, secret store, credential issuer, queue or parallel registry.
- Existing provider account/product restrictions remain enforced. A model being listed or a key existing does not establish permission for an application workload.

## Initial evidence-backed audit

| Consumer/domain | Observed source state | Required convergence |
| --- | --- | --- |
| Mastermind Brain/CIO/committee/risk/strategist and paper loops | Protected `brain/client.py` defaults to shared Codex/Claude waterfall; explicit production_mode delegates to Macro. It also contains explicit direct API compatibility mode. | Preserve the live contract and no-replay semantics; adopt the existing application Fabric factory through #2060, not a second client. |
| Brain chat, advisor, translation | #2060 at e5e16bb contains the active compatibility migration; not yet merged at initial audit. | Consume its original source/queue; do not duplicate its workers or rewrite its branch. |
| Secretary GB1/S2 | SDK and signed fixture join merged in #2085, but installed caller still not proved. Grok has acknowledged the existing binding audit. | Mount existing SDK through authenticated host; reuse pools and existing credentials rather than native BYOK-key copies. |
| Executive workers | `ModelRouter` reads `config/executive_worker_routes.json`; provider/model aliases are data but execution adapters/capabilities remain qualified. | Keep task suitability separate from pool/account capacity; preserve current Job/Attempt bindings. |
| Native Fabric workers | `pick.py` consumes `pools.yaml`; Broker consumes existing accounts YAML. Picker has process-local cache; Broker uses mtime cache and last-good fallback. | Add coherent, revisioned configuration observation and safe transition analysis in these owners; do not silently revive removed policy through cache fallback. |
| Application pools | #983 comment6672146510 identifies nine known pool IDs but Go/Bailian-only executable grants and fixed-model service variants; account/product restrictions remain. | The existing A/B/E and shared client chain must expand qualification and bind from the same catalog, preserving original turns before new config/key checks. |
| Mastermind OS Resources | Current panel shows execution-system inventory and retained provider capacity, not a pool/configuration editor. The retained capacity v1 contract is MiniMax-specific. | Show configured vs qualified vs enabled vs currently usable separately, with explicit stale/unavailable evidence and change impact. |
| Hermes native BYOK | Separate optional role-service inference architecture; empty role files do not prove shared Fabric unavailable. | Do not activate or duplicate credentials simply to access existing shared workers. |

Primary source evidence: #983, #2060, #2082/#2085; #983 comments6672146510 and6672509264; protected `brain/client.py`, `control_plane/model_router.py`, `common/workspace_resource_capacity_contract.py`, native `candidate/{pick,lease_broker}.py`.

## Configuration design

1. Preserve existing source documents as owners. Produce a **derived**, bounded, secret-free view, never a second editable pool registry.
2. Distinguish provider connection, physical account/quota bucket, model, executable recipe/harness, logical pool, workload policy, and credential reference/generation. A model name does not create capacity; Go-hosted GLM is not an extra GLM account.
3. Operator changes carry exact base revision and candidate digest. Validate complete candidate and cross-references before publication. Duplicate IDs, unsupported adapters, dangling models, malformed limits and secret values are rejected.
4. Candidate activation uses existing owner prepare/apply/reconcile; validation is not permission. Preserve original admitted operation/account/model/recipe and key generation during recovery. Never fail over an unknown effect just because configuration changes.
5. Draining prevents new selection without killing active work. Removal or credential-rebinding requires original lease/account closure evidence; additive disabled candidates are safe to stage but not auto-enable.
6. Consumers use stable workload/role contracts and receive selected identity from the owner. Optionality and capability differences remain explicit; text-only, tool, structured-output, hard output cap and preferred-output profiles are not interchangeable.
7. Credential values remain with original secure-store/provider owners. The control surface accepts references only and must not print keys, hash secrets as public identity, expose filesystem paths or transfer credentials across roles.
8. Invalid/stale candidates do not alter current published config. Every existing owner can independently refuse selection. No claim of transactional cross-file activation unless the original publication owner supplies it.

## Bounded phases

| ID | Deliverable | State / next action |
| --- | --- | --- |
| C0 | Current consumer and owner audit with live-writer boundaries | Initial audit complete; independent bounded return may add source facts. |
| C1 | Existing-owner configuration snapshot/validation/impact helpers, secret-free and no effects | First executable slice implemented in ModelRouter and operator CLI; native account/pool integration remains separate to avoid #2060/A-core live writers. |
| C2 | Integrate coherent loader/configuration generations into incumbent owners after original path custody is clear | Preserve #2060 and new A-core/J/process-carrier effects; no overlapping writes. |
| C3 | Mastermind OS authenticated configured-routing inspection | Fixed Workspace READ → backend ModelRouter and web/native Resources consumer implemented in source; web production build passes. Physical pools/live activation and deployed browser proof are not yet joined. |
| C4 | Existing publisher activation, key-reference rotation, drain/rollback and original-request recovery | Actual source/config grants and provider qualification required; no standalone installer. |
| C5 | Migrate all named consumers and prove installed operations | Real product paths, not source assertions. |

Current implementation priority: C1 configuration safety and consumer inventory. Paid Fabric is preferred for independently bounded extraction/build work. Principal retains C3 architectural decisions and integration. Direct work justification: PRINCIPAL_JUDGMENT for reconciling independent owner schemas and active writers, then LOWER_TOTAL_OVERHEAD for the smallest non-overlapping consumer join. No discretionary test suites are launched under the Chairman's current no-tests instruction; native required CI/security gates remain unchanged and unrun proof must be labelled unrun.

## Explicit active-source exclusions

Do not edit queued #2060 source or original workers' `lease_broker.py`, `go_lease_capability.py`, `go_lease_gateway.py`, native command/transport/result files, remote process carrier, or installer manifests while their custody/effects remain active. New additive helper paths do not grant authority to modify those owners. No direct provider call, credential read/rotation, live broker reload, shared service restart, duplicate task, or reinterpretation of held provider terms is authorized by this document.

## Current frontier

Source workspace is managed by the existing Studio mmx-workspace publisher on operation `shared-model-pool-control-20261105-c4`. Reuse this operation and source branch. Preserve #2085 as merged DO_NOT_REDO and the existing Grok Secretary binding audit. This expansion is tied to #983, not a replacement programme or a second Fabric. Agent OS organizational link remains PLAN_NOT_ORG_LINKED until recorded by its normal source writer.
