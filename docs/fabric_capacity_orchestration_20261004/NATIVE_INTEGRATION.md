# Native Fabric integration and capacity producer contract

Status: implementation intake for existing owners; source PR #1247 does not itself install a native integration. Operation: `fabric-capacity-orchestration-upgrade-20261004-sol-001`. Baseline: Mastermind `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`.

## A. Current source increment and proof boundary

`control_plane/capacity_economics_projection.py` adds `project_capacity_bounded_preference` and immutable `CapacityProjectionScope` / `CapacityBoundedPreference` to the existing projection owner. The v1 economic API remains. The additive v2 validates a complete, fresh, scoped envelope and clamps a preference; it does not obtain observations, grant rights, normalize native quotas, reserve capacity, choose a weaker suitability tier or launch a process.

The two published stages are distinguishable. The first candidate passed 121 focused tests. Adversarial host/reviewer transplantation then reproduced two defects against that candidate; the repaired source binds both identities independently and passes 127 focused tests, including 500 seeded budget/monotonicity cases. These tests do not prove atomic fleet accounting or production throughput.

## B. Producer/caller join

The existing runtime caller constructs `CapacityProjectionScope` from canonical records, independently of the proposed envelope:

| Scope reference | Existing owner evidence required |
| --- | --- |
| root_operation_ref / operation_ref | Current root and proposed operation under the same admitted mission |
| ancestor_operation_refs | Complete intermediate ancestry, excluding root and self, with no cycles or aliases |
| quota_domain_ref | Actual shared subscription/account quota identity, not an API-key nickname |
| workload_ref | Versioned job-cost cohort tied to task type, selected model and effort |
| quota_window_refs | Complete applicable native quota-window identities and epochs from Provider Control |
| host_ref | The intended admitted placement, not another idle host |
| review_pool_ref | The matching accepted review/return capacity pool, not unrelated reviewer availability |

All tuples are immutable, unique and input-size bounded. These API-size bounds are not provider or root fan-out limits. A batch spanning hosts or review pools must be split into independently scoped candidates; there is no implicit summing across placements.

The envelope is JSON-shaped and closed. It contains `schema=mastermind.capacity_owner_envelope/v1`, `observation_ref`, `observed_at`, `valid_until`, option/provider/model identity, all scalar scope references above, and `constraints`. The clock and `max_age_seconds` are explicit existing-caller inputs. Neither a model-authored timestamp nor an arbitrary provider snapshot establishes authenticated evidence.

Each constraint has exactly `kind`, `scope`, `scope_ref`, `remaining`, and `evidence_ref`. `remaining` is a non-negative integer or null. It means owner-produced JOB-EQUIVALENT REMAINING HEADROOM for this workload after commitments, not the provider's advertised capacity or raw token balance.

Required concurrency scopes are provider, account, model, host, root, operation and review, plus every intermediate ancestor. Required start scopes are root, operation, every intermediate ancestor, and every applicable quota window. Scope sets must match exactly. A nonbinding resource still needs an owner-supported bound appropriate to the current finite request; do not use an invented giant number, null-as-unlimited, or omit the dimension.

If provider rate limits are distinct from agent concurrency, the producing owner must incorporate their current admissible job-equivalent bound into the provider headroom, preserving the underlying evidence. If a task fans out multiple simultaneous requests, normalize that footprint rather than treating one agent as one request. The projection does not implement another token bucket or refill clock.

The observation is assembled from the current owners' consistent state. Each constituent evidence reference must be current enough for its own source; an outer fresh timestamp must not launder stale inner facts. The envelope's validity cannot exceed the earliest constituent validity, and its observed-at cannot represent a newer complete view than the actual joined evidence. The projection validates outer freshness, not provenance or a distributed snapshot protocol; that obligation stays with the producer and live claim owner.

For current native-window budget Q, the owner can derive a conservative start bound using the remaining Q after unresolved commitments and a validated full-completion cost for this cohort. It must account for heterogeneous model costs and preserve native units in its source evidence. The projection never estimates a universal tokens-per-agent constant or adds monthly credits to request counts.

The emitted states are:

- `PREVIEW_READY`: positive bounded suggestion, still no reservation.
- `WAIT_CAPACITY`: all required facts known but a limiting dimension is zero.
- `WAIT_EVIDENCE`: at least one explicit unknown; no positive wave is suggested.
- A validation error: malformed, missing, stale, future, duplicate, transplanted or contradictory input; never treat it as permission to use the raw v1 hint.

All v2 outputs retain `NONE_PREVIEW_ONLY`, `binding_verification=NOT_PERFORMED`, `live_admission=false`, `selection_is_commitment=false`, and required claim-time revalidation. The original hint is visibly labelled unbounded. Do not pass the inner `preference` to an execution path in place of the bounded result. Runtime integration must handle the status explicitly and recompute admission transactionally.

## C. Transactional admission and conservation

The existing Capacity/Executive claim transaction revalidates the current canonical root, ancestors, realm, host, model and all limiting windows before allocating. It charges all descendants against shared scopes without issuing independent per-orchestrator copies of account capacity. Two simultaneous positive previews are not two reservations. If the operation is also the root, its shared budget is one owner obligation, not two independent charges.

Budget conservation includes unresolved remote attempts, retries, reviewers and final-return obligations. Before releasing a hold, establish the original attempt's terminal state and required provider/process evidence. A timeout or TTL alone does not suffice. Cancellation must use the original owner and preserve late results; a new child ID cannot bypass a held claim.

The native kit broker's model-aware acquisition and model-blind `_plan_pool` are a concrete integration mismatch. Its owner should make advisory planning model-aware using the SAME cap/held logic as admission, and label TTL-based wait hints honestly. Do not implement a parallel planner that acquires leases, add another SQLite broker, or mutate the active kit before its canonical source and installed generation are reconciled. Known configured GLM account10/full5/Flash20 is a test counterexample, not authority to raise any limit.

The provider ledger and host registry must include legacy and Executive work during cutover. De-duplicate by canonical obligation identity; do not double-count one imported lease or ignore a legacy process. A supposedly read-only kit command that initializes/GCs its database is not an observational adapter and requires its own effect classification.

## D. Native client embedding

A native parent uses the installed existing Fabric tool contract, through #1217's projection where applicable and #600/#1041's execution/return owners. Tool discovery must expose actual supported actions and bounds. This document intentionally invents no `fabric.spawn` API, MCP server name, credential path or shell launcher.

The deterministic client adapter carries existing identifiers, the exact brief and source refs into the admitted submission. Child creation remains with the Executive owner; status and result consumption remain with the same original parent/attempt. Direct native subagents are usable only when that path is admitted and all their effects and consumption are charged to the same envelope. Do not run a free-standing built-in subagent and merely annotate it afterward as governed Fabric execution.

Installation proof must show the parent and intended descendants actually see the selected tools, retain the correct permissions and resolve explicit worker models. An instruction saying "delegate cheaply" is not configuration evidence. Use an already-enrolled server connection rather than a new service. Map project/user/managed precedence and actual installed-client semantics; preserve human trust/approval gates.

A native settings sample is not production configuration. Local per-session thread/depth caps are only supplemental. Canonical claims must cover features not subject to those local limits, along with resumes and delayed results. When the installed client cannot provide that control, it remains unqualified for the affected autonomous lane.

### Current primary-source observations, checked 2026-10-04

These findings guide qualification; they are not entitlement or installed-version evidence.

**Codex [S1].** The current subagent page documents `agents.max_concurrent_threads_per_session`, `agents.default_subagent_model`, and `agents.default_subagent_reasoning_effort`. A child can inherit the parent's model/effort when no selection overrides it; custom agents also inherit omitted session settings such as MCP configuration. Therefore test resolved configuration, not only file presence. The fetched general configuration reference did not expose the same agents keys; confirm actual installed-version support instead of copying older field names.

**Claude Code [S2].** Its documented nesting and concurrency controls are `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` and `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`. Some paths, including resumes, are not constrained identically; the local cap is not a global admission guarantee. Plugin subagent frontmatter ignores `mcpServers`, unlike applicable project/user definitions. Non-interactive late nested results may return to the main conversation after their launching subagent ends. These differences need explicit capability and return tests.

**Alibaba [S3].** The Personal Token Plan page, updated September 28, states that weekly quota was removed September 22, 2026 and quota resets per subscription month. It restricts Personal usage to interactive tool use, subscriber-only use and one device. Do not sum locally configured account/key caps into an unattended multi-host entitlement. Verify the actual plan and permitted surface; any different eligible realm still requires normal enrollment and spending authority.

**MiniMax [S4].** The official indexed subscription listing describes tier-dependent concurrent-agent ranges, including Ultra 6-7, and shared consumption across models. Its interactive page did not yield a complete readable plan payload in this inspection. Exact subscribed limits, window semantics and unattended eligibility remain unverified; a locally configured cap of seven is not sufficient evidence.

**GLM.** The installed account/model limits and protected model aliases were observed, but no authoritative per-account current remaining quota was read. Keep those facts separate. API keys sharing a quota domain must not be treated as independent capacity.

Sources:
- [S1] https://learn.chatgpt.com/docs/agent-configuration/subagents (Model and reasoning selection; Custom agents; Global settings).
- [S2] https://code.claude.com/docs/en/sub-agents (Configure subagents; nested subagents; concurrent subagent limit; MCP scoping).
- [S3] https://www.alibabacloud.com/help/en/model-studio/token-plan-personal-overview (Quota reset; important information before subscribing).
- [S4] https://platform.minimax.io/subscribe (official indexed listing; full current account payload not obtained).

## E. Incumbent work packages and non-overlap

| Existing carrier | Requested next consumer capability | Proof before calling it complete |
| --- | --- | --- |
| #1041, operation `mastermind-os-orchestrator-launchpad-20260926-sol-001` | Join complete owner observations and v2 projection into existing hierarchy admission without changing sole runtime custody | Concurrent sibling claims conserve root/provider budgets; review/repair/final return charged; terminal shutdown/death/release and parent consumption proven |
| #600, operation `agent-fabric-end-to-end-fable-integration-20260913-sol-001` | Qualify one heterogeneous native program using the existing principal and current hierarchy source | Actual two-provider work, independent review, exact parent result consumption; Web re-entry only if separately proven |
| #1217, Studio/native client projection | Prove capability discovery and selected per-client configuration for the existing admitted tools | Actual parent and child tool inventory, attenuated identity, supported model/effort mapping, and original-return addressing |
| Provider Control / current native broker owner, coordinated through the existing Fabric intake | Supply versioned quota domains/window sets and model-aware planning from existing authoritative accounting | Real configured/observed/forecast distinction, shared-key accounting, reset/429 handling and current usage eligibility |

#1041 was re-observed open/draft at head `b3816bb75fa328ec6df1f92a77e8377016efdc8e`; its body cites an older tested head, so those older test counts are not asserted for this current head. #600 remains a draft plan at `a5c4f0f4c9561874ded59abf9a9466fe33734538`. Historical depth/slot counts in that plan are not deployed current policy. This operation does not modify either incumbent's implementation files or claim their workers are live.

## F. Acceptance sequence and measured ramp

1. Shadow projection: replay real sanitized owner observations without spawning. Compare v1 hints, v2 bounds and actual claim decisions; investigate disagreement rather than silently clamping away producer errors.
2. One leaf: an already-admitted native parent submits one useful bounded packet, proves process/model/realm and source identity, consumes its result and releases only on proper terminal evidence.
3. One domain: execute independent siblings plus review/repair under attenuated grants. Demonstrate concurrent overlap, not merely sequential successful children. Preserve the original parent and return IDs.
4. Mixed provider: use two currently permitted qualified providers, with shared host/root/reviewer limits enforced. Inject a spent window and a 429; no oversubscription or unapproved fallback is allowed.
5. Failure/recovery: lost submit response, duplicate submit, resumed child, parent/session loss, late result, stale fact, partial quota reset and uncertain stop. Every existing effect is reconciled before another carrier can recreate it.
6. Production ramp: compare matched task cohorts against baseline accepted quality, frontier time, completion cost, queue age, repair frequency and stranded returns. Pick thresholds under the existing owner policy before the trial; this plan asserts no arbitrary percentage improvement.

Each stage records source candidate, selected installed generation, exact runtime/attempt/worker/claim references, result digest, test/review evidence, and next owner action. A dashboard screenshot, authored settings file, queued task or passing isolated test cannot substitute for a missing stage.

## G. Current frontier

The source projection, focused tests, reviewable amendment and this integration contract are the independent #1247 contribution. Runtime producer adoption, law-loader adoption, native installation, plan entitlement, atomic claim behavior and complete parent-return canaries are still open. Preserve the original managed workspace and all previously recorded host refusals; do not replay those effects through another surface. Source review and incumbent intake can proceed without pretending the native gate has cleared.
