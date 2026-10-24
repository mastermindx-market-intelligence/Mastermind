# Persistent Fabric sessions and automatic recovery

## Commission and source

Chairman commission: preserve worker and orchestrator responsibility through model/pool exhaustion, context pressure and unavailable concurrency; automatically triage recoverable stops and visibly queue until equivalent capacity is available. Source/procedure pin: `25c4b7923734392b1013afae179966985819d847`. Source operation: `fabric-session-continuity-20261012-web-001`. This document is an implementation design, not production admission or a grant to replace a live writer.

## Architecture decision

Keep the existing Executive Job as the stable logical worker/session. Every provider process and native conversation is a replaceable execution Attempt beneath that Job. Preserve root, parent, goal, grant, accepted work and continuation references; never pretend a new provider conversation is the same physical process. Native same-harness model changes may preserve a native conversation when explicitly supported. Cross-provider changes start a new admitted Attempt and reconstruct task state from the provider-neutral OperatorContinuation contract. Provider-private compaction blobs are not portable memory.

Do not create another scheduler, router, queue, account store, lease broker or memory database. Executive owns Job/Attempt/Event/queue/retry/fencing. Existing Model Router establishes task-qualified model equivalence; Capacity chooses an eligible host/account/pool. Agent OS, GitHub and existing checkpoint/capsule producers own durable work context. Existing parent-return transport reports outcomes, not inferred success.

## Current source gaps

The installed `fabric_task.py` is a thin stable-run adapter, SHA256 `cbd46bd88a4e5d545c77010bfb9eb1997399fe4f5cc67596210e849858eddd99`, not a general retry or context engine. Its account-local non-Git source has another live integration lane; this operation does not overwrite it. Mastermind #1365 owns pinned/auto model-host preview. #1253 owns pool-family accounting; #1247/#1248 own capacity/task-fit. #1289 owns immutable continuation PREPARE/ACK and depends on #656 source compilation; its production two-Attempt/cross-provider journey is unproven. #1344 owns retained native Codex continuation. Reuse, do not duplicate, those implementations.

`executive_retry_safety.py` already defines SAFE_NON_MODIFYING_QUOTA_ROLLOVER. However `_retry_safety_material` classifies every RATE_LIMITED Attempt as UNKNOWN/effect-unknown and `commit_coo_retry_decision` accepts only TX9_DETACHED. Enabling quota rollover requires a positive source-derived release proof, not deleting these fences.

## Recovery contract

Stops are not interchangeable. Quota/rate limit, context capacity, output limit, provider concurrency, authentication, permission/safety refusal, transport detachment, process crash and semantic failure require distinct typed observations. Unknown evidence remains unknown. Safety/permission denial never authorizes another provider/account; authentication requires its existing repair owner. Detached streams and timeouts do not prove remote death. EFFECT_UNKNOWN always requires same-carrier reconciliation.

For automatic quota rollover, the first source increment is deliberately non-modifying only. Require the exact current terminal Attempt, original grant limited to READ/RUN_TESTS with no write paths, remaining attempt allowance, a canonical JOB_RATE_LIMITED Event, and positive canonical OHF evidence that every predecessor generation ended, released the provider writer and released the Executive writer. No candidate, result, seal, unknown effect or current provider epoch may survive. Re-derive all evidence in the existing atomic COO retry transaction. Preserve the same Job and checkpoint, clear only the settled predecessor's capacity hold, keep the exhausted quota class RATE_LIMITED, and let the existing scheduler perform the next placement. Duplicate notifications reconcile the original command Event; they do not create new Attempts.

A modifying worker needs sealed source/artifacts, reconciled external operations and admitted successor custody through the existing continuation owners. This increment must not quietly treat ordinary coding workers as read-only or clear their effect fences. An exhausted retry budget is not a successful or cancelled mission; expose the need for an authorized allowance decision.

## Placement and waiting

A recovery request prefers (1) another eligible independent pool for the same qualified model, then (2) another qualified model in the required task tier. Model, provider, harness, subscription pool, budget scope and host are separate. Cursor is a harness/product, not an equivalence proof. An account-wide exhausted budget excludes all routes sharing that budget, including routes on other hosts. A safety refusal is not a quota signal. Unknown/expired telemetry cannot be promoted to available capacity.

When no eligible slot is available, keep the existing Job QUEUED and report why, the original Attempt, accepted checkpoint, allowed task tier, known reset/return condition and queue position only when the existing owner supplies it. Do not fabricate an ETA or queue position. Capacity events/reset observations wake the existing scheduler; no new polling daemon. Preserve original global root/descendant grants and capacity ceilings during a 30-worker interruption storm.

## Context persistence

Reserve space for response, tool output and compaction based on the selected model's observed context window. No universal model token limit or elapsed-time rotation rule. Compact before overflow when the adapter supports it; otherwise save the current semantic frontier and request a new Attempt. The compact portable frontier carries objective, constraints/grant references, source revisions, accepted artifacts and tests, DO_NOT_REDO, unfinished action, unresolved effects, pending children and parent-return obligations. Keep large logs in source-owned artifacts and retrieve by reference. A smaller target model must fit mandatory state plus reserves; never silently truncate safety/custody/next-action fields to make it fit.

## Implementation sequence and verification

1. Add source-derived quota-release material and new adversarial tests. Observe RED for a valid positive-release non-modifying rollover. Preserve fail-closed behavior for missing/forged events, active generations, effect uncertainty, modifying grants and exhausted allowance.
2. Wire that material into the existing retry classifier and COO transaction, including exact command replay validation. Test same-Job checkpoint preservation, exhausted-pool exclusion, atomic duplicate delivery and queue persistence without a successor slot.
3. Add deterministic bounded recovery/context diagnostics for orchestrators. Diagnostics never grant execution or reserve capacity. Tests cover quota vs context vs authorization, unknown telemetry, all-slots-busy and smaller-target context budgets.
4. Publish the source candidate and exact evidence. Integrate the existing pool selector, pool-family accounting and immutable continuation candidates under their incumbents. Qualify adapter stop events and real provider routes, then run admitted same-model/different-pool and cross-provider useful-work/parent-return canaries. Do not claim fleet adoption from tests or a PR.

## Acceptance

Thirty interrupted logical workers retain thirty Jobs and no more than one current admitted writer each. Completed source work is not repeated. Qualified replacement pools are used only after canonical release/retry gates. Fully occupied or exhausted equivalent capacity visibly queues. Context exhaustion preserves mandatory state. A parent can inspect all affected workers without reading raw transcripts. Production acceptance requires real provider/model/account/host receipts, durable restart recovery, successor useful action and original-parent consumption, in addition to tests and review.
