# Direct-provider execution and supervisory convergence design

**Operation:** `mastermind-provider-app-server-adapter-fabric-f0-20260906-sol-001`

**Owner:** continuing Web Sol / MastermindX1; not the native Integrator's identity.

**Carrier:** `C0BSBM78V1N/1788731079.486769`; source continuation `1788757510.809509`.

**Status:** architecture candidate / records-only / Draft-Hold; no runtime or provider admission.

**Basis:** protected Mastermind `87fcea41a0357ff59c615ecced73645364a42567`, same-SHA Skillpack 1.0.1 / bootstrap 1.

**Evidence:** [dated estate and accepted research qualifications](../../../research/PROVIDER_APP_SERVER_ADAPTER_ESTATE_2026-09-06.md).

**Execution plan:** [existing-owner delivery slices](../plans/2026-09-06-provider-app-server-adapter-fabric.md).

## 1. Outcome and non-rebuild boundary

A frontier CEO must manage a useful fleet rather than perform all implementation itself or serve as a polling daemon. The Chairman supplies an outcome, existing Executive machinery admits bounded work, economical eligible workers execute it, evidence reaches the exact responsible leader, and that leader resolves exceptions through review, repair and final acceptance. The outcome survives parent context exhaustion and does not depend on manual prompt carriage.

This design selects and composes existing contracts. It does not introduce a universal provider API, new child-work compiler, database, broker, scheduler, permission system, transcript archive or effect journal. The documentation record below is not loadable runtime configuration; its version is a documentation revision, not another wire protocol. No production consumer may import it as authority.

Authority precedence remains current Chairman direction and governing Executive/Agent OS laws, then the current admitted operation and accepted domain contracts, then implementation evidence. This candidate cannot overrule protected provider-auth rules, expand a worker grant, or release a source writer. Later accepted material source changes require explicit comparison, not blind reuse of this snapshot.

## 2. Two existing interface floors, three selected provider ports

Keep `WorkerExecutionAdapter` for the sealed foreground-worker floor and `OperatorHarnessAdapter` for rich session/turn operations. Their different responsibilities are deliberate. The rich contract already includes optional probe, staging, resume, steering, approval, fork and checkpoint seams; unsupported methods must remain unavailable rather than being emulated with a new provider-local state plane.

Codex keeps the existing rich App Server stdio implementation. Claude's first useful vertical remains the already-planned PF1 foreground CLI worker, with no session persistence or provider-native fanout. A later SDK wrapper or richer Claude port must preserve the existing lower floor and qualify its actual binary and capabilities; the research recommendation does not replace PF1. Grok uses the existing selected provider-neutral ACP implementation direction plus a Grok manifest, not a special Grok lifecycle. Richer ACP behavior may extend the existing optional rich interface only through a later admitted capability slice.

The provider entries below describe the selected next capability ceiling, not everything each vendor offers. A `SPEC_ONLY` selection does not deny the existence of provider tooling or separate preflight code. Codex `BUILT_NOT_PROVEN` does not assert that no other production lane exists; this program has not accepted its complete provider-to-supervisor journey.

## 3. Machine-checkable documentation selection

The test reads only this record and existing source syntax. It proves neither running providers nor the sufficiency of prose, permissions, cancellation or end-to-end integration. An independent reviewer must judge those claims against the cited source and original outcome.

<!-- ASF_SOURCE_RECORD -->
```json
{
  "record_type": "DOCUMENTATION_ONLY_SELECTION",
  "version": 1,
  "scope": {
    "source_paths": ["research/PROVIDER_APP_SERVER_ADAPTER_ESTATE_2026-09-06.md", "docs/superpowers/specs/2026-09-06-provider-app-server-adapter-fabric-design.md", "docs/superpowers/plans/2026-09-06-provider-app-server-adapter-fabric.md", "tests/test_provider_app_server_adapter_source_law.py"],
    "runtime_writes": [], "provider_invocations": 0, "production_armed": false
  },
  "owners": {
    "lifecycle": "Executive OS",
    "placement": "Existing Model Router and Capacity claim",
    "continuation": "Existing Wake and RuntimeBinding",
    "organizational_memory": "Macro Agent OS",
    "implementation_evidence": "GitHub",
    "transport": "Slack",
    "supervisor_projection": "Existing Control Room and Steward"
  },
  "interfaces": {
    "sealed_worker": {"path": "control_plane/worker_adapter.py", "symbol": "WorkerExecutionAdapter", "methods": ["start", "collect_result", "cancel", "run_validation_argv"]},
    "rich_operator": {"path": "control_plane/operator_harness_contract.py", "symbol": "OperatorHarnessAdapter", "methods": ["describe_capabilities", "validate_requested_profile", "start_session", "begin_turn", "read_events", "interrupt_turn", "collect_candidate_result", "graceful_stop", "cancel", "reconcile"]}
  },
  "providers": {
    "codex": {
      "transport": "codex-app-server-stdio", "interface": "rich_operator",
      "capability_state": "BUILT_NOT_PROVEN", "cancel_completion": "turn/completed:interrupted",
      "resume": "SOURCE_SUPPORTED_NOT_LIVE_PROVEN", "actual_binary_required": true,
      "identity": "SAME_WORKER_REALM_REQUIRED", "model": "REQUESTED_AND_OBSERVED_SEPARATE",
      "quota": "OPTIONAL_FRESH_REALM_BOUND_OR_UNKNOWN", "activation": "SEPARATE_EXISTING_OWNER_GATE"
    },
    "claude": {
      "transport": "claude-foreground-cli", "interface": "sealed_worker",
      "capability_state": "SPEC_ONLY", "cancel_completion": "closed-profile terminal plus identity-safe cleanup",
      "resume": "NOT_ADMITTED_FIRST_SLICE", "actual_binary_required": true,
      "identity": "SAME_WORKER_REALM_REQUIRED", "model": "REQUESTED_AND_OBSERVED_SEPARATE",
      "quota": "OPTIONAL_FRESH_REALM_BOUND_OR_UNKNOWN", "activation": "SEPARATE_EXISTING_OWNER_GATE"
    },
    "grok": {
      "transport": "acp-stdio", "interface": "sealed_worker",
      "capability_state": "SPEC_ONLY", "cancel_completion": "original session/prompt response:cancelled",
      "resume": "UNVERIFIED", "actual_binary_required": true,
      "identity": "SAME_WORKER_REALM_REQUIRED", "model": "REQUESTED_AND_OBSERVED_SEPARATE",
      "quota": "OPTIONAL_FRESH_REALM_BOUND_OR_UNKNOWN", "activation": "SEPARATE_EXISTING_OWNER_GATE"
    }
  },
  "effects": {
    "intent_before_dispatch": true, "unknown_disposition": "RECONCILE_SAME_OPERATION",
    "retry_unknown": false, "provider_failover_unknown": false,
    "account_failover_unknown": false, "host_failover_unknown": false,
    "process_exit_proves_remote_cancellation": false, "candidate_result_completes_job": false
  },
  "supervision": {
    "independent_work": "EXECUTIVE_CHILD_JOB",
    "ephemeral_helpers": "PARENT_GRANT_NO_INDEPENDENT_EFFECT",
    "native_lineage": "OBSERVED_PARENT_ATTEMPT_OR_UNKNOWN",
    "permission_ceiling": "CHILD_SUBSET_OF_PARENT",
    "budgets": "EXISTING_OWNER_UNCHANGED",
    "cost_order": "SUITABILITY_THEN_CAPACITY",
    "gui": "COMPARATOR_NOT_EXECUTION_OWNER",
    "result_target": "EXISTING_RESULT_AND_PARENT_WAKE",
    "unknowns": "EXPLICIT_NOT_IDLE", "new_store": false
  },
  "proof": {
    "record_tests_prove": "DOCUMENT_COHERENCE_AND_SOURCE_SEAM_EXISTENCE_ONLY",
    "required_real_journey": ["admitted_job", "atomic_worker_claim", "attested_execution", "canonical_result", "independent_review", "parent_consumption", "visible_consumer", "terminal_reconciliation"],
    "failure_cases": ["lost_launch_response", "wrong_realm", "model_mismatch", "schema_drift", "late_cancel", "duplicate_result", "stale_parent", "worker_crash", "capacity_exhaustion", "host_interruption"],
    "executed_by_f0": false, "provider_proof_complete": false
  }
}
```

## 4. Execution, cancellation and identity

The Executive operation owns the normalized semantic request and pre-effect identity. The provider adapter receives only the already-bound grant, workspace, provider-private configuration and allowed action; it must not choose a different account, filesystem root, model or host because a request failed. A repeated same-operation request reconciles the existing effect. A changed payload conflicts rather than spending the same identity on another action. An uncertain dispatch remains sticky on the same owner/carrier until canonical reconciliation.

Keep requested configuration, observed launch capabilities, provider-reported identity and actual served output separate. Bind observations to exact executable, process generation, Attempt, workspace and provider realm, with observation time and provenance. Provider-shaped strings are untrusted input. Missing or stale quota remains unknown, and account status without same-worker credential provenance does not attest the executing account. Public projections receive only accepted secret-free facts; raw home paths, account PII, tokens, headers and vendor error prose do not become result metadata.

Credentials remain with the existing provider/host owner. In particular, the current PF1 contract's dedicated-principal native Claude login is not replaced by `setup-token` or environment credentials because an SDK tutorial offers them. A same-Build-realm Grok restriction is not validated through an unrelated API key. F0 creates no login, enrollment, authentication refresh, account migration or host configuration.

For Codex, the record's cancellation terminal is the interrupted turn event, not the interrupt request's acknowledgement. For ACP, it is the cancelled response to the original prompt, after handling pending permissions and updates. Both still owe accepted identity-safe cleanup and Executive reconciliation. Claude's first sealed path must preserve its closed protocol/real-exit evidence and existing cleanup contract; a SIGTERM/no-result path must remain uncertain rather than invent a provider terminal. Cleanup deadlines do not extend semantic result acceptance, and local process absence never by itself proves remote billing cessation.

Advertised resume, fork or helper capabilities do not authorize their use. Actual supported operation behavior and the existing epoch/writer-transfer law must be qualified before a richer slice. The first Claude sealed proof deliberately has no resumable session. The Grok load/resume gap is retained, not emulated through a new local conversation database. Provider-internal retry behavior must be characterized by the existing version/profile owner; no adapter may claim at-most-once provider activity from the absence of a retry event alone.

## 5. Hierarchy without invisible work

| Required primitive | Existing owner / integration rule |
| --- | --- |
| Spawn, parent-child topology and dependency joins | Existing Executive child-work admission and orchestration lifecycle; no provider-created canonical Job ID |
| Context construction and compaction | Existing boot/grounding and durable evidence references; a chat summary is working memory, not current authority |
| Tool and capability inheritance | Existing effective grant/profile and provider compiler; child capability is a subset, never an ambient parent credential inheritance |
| Workspace isolation | Existing broker/workspace identity and source-writer census; per-worker owned source, no shared checkout takeover |
| Message, progress and result | Existing event/result owners and transport; progress and receipt delivery never imply acceptance |
| Review and repair | Existing closed role-result validation and independent-review relationship; exact artifact binding, bounded repair cycle |
| Recursive delegation | Independently reviewable/effectful work re-enters existing child-work admission; ephemeral cognition remains parent-bounded |
| Depth, width, spend and host capacity | Existing budget, Model Router and Capacity owners; F0 supplies no new defaults or scheduler |
| Cancel, liveness and failure recovery | Existing operation/epoch/process identities and effect reconciliation; no retry or cross-realm transfer while effect is unknown |
| Durable resumption and parent attention | Existing RuntimeBinding/Wake plus Agent OS continuity; exact current target, actual consumption, stale-session refusal |

A native helper is not automatically an Executive Job. Read-only short-lived cognition may remain internal to its admitted parent. Material mutations, independently accepted proof products and worker results must be represented through the already-accepted child-work mechanism before their effects occur. An observed unjoined process can appear as unjoined activity, but the observer cannot retroactively mint an admission to make the dashboard complete.

## 6. The supervisor's coherent experience

The human tree and bounded machine response must project the same admitted responsibility and attributable evidence through existing readers. Keep the safe singular action-target lookup separate from plural observation. Two real concurrent children must not cause the observer to choose the newest session as the current action target. The existing plural-reader and authenticated first-read work are the integration path, not a reason to create another inbox or copy a Runtime database.

For each branch show execution state, current work phase, exact material artifact, observation age, pending decision and evidence quality as separate dimensions. Fresh polling cannot make an old artifact fresh. A heartbeat is liveness evidence, not useful accomplishment. Loss of a browser stop button cannot turn unknown activity into idle Capacity. Truncation and unavailable joins stay visible.

The model-facing response should expand only material changes and the branch needing judgment. Routine dependency progression, duplicate detection and bounded aggregation remain deterministic owner work. Frontier reasoning supplies decomposition and adjudication; Fable is reserved for genuinely ambiguous principal work, not every waiting loop. Provider brand is not a permanent organizational rank.

A control request is separate from its effect: repair requested, delivered, consumed and begun; cancellation requested, terminal evidence and cleanup; source approved, released and proven in production. Parent wake delivery and parent ACK remain separate from source resolution. The responsible leader must actually read the result and issue the appropriate continuation or STOP. A successor receives current canonical facts rather than simply continuing a stale transcript.

## 7. Failure behavior and acceptance

The first accepted loop needs real admission, atomic selection, attested execution, canonical result, independent review, parent consumption, a useful visible consumer and terminal reconciliation. The initial canary should be small and reversible; larger nested or multi-host experiments follow only on accepted lower-level proof. No arbitrary number of workers is a completion threshold without an observed complete journey.

Before each later real canary, the existing owner freezes exact input/artifact identities, allowed provider effects and budget, expected positive outcome, adversarial controls, cleanup and stop conditions. Include lost-launch response, wrong realm, mismatched model, schema drift, late cancel, duplicate result, stale parent, worker crash, exhausted capacity and host interruption where that slice exercises them. Use the same real path for the positive and relevant negative control. Tests of configuration absence must hold all other policy/auth variables constant; capability advertisements and GUI presence are not functional or causal proof.

A dedicated canary realm can prove absence of a GUI dependency without quitting other workers' applications. Verify the actual target process/interface and output path, not merely a screenshot of closed windows. Browser proof is additionally owed for a user-facing supervisory consumer. Remote-host proof must use existing MH1 transport/host ownership, keep credentials local, and reconcile interrupted effects on the same host/Attempt rather than silently rescheduling them elsewhere.

Measure accepted useful outcomes, end-to-end elapsed time, repair rounds, intervention count, dropped/duplicate returns, model/host resource cost and recovery correctness through existing telemetry owners. New agents or Macs increase usable capacity only after eligibility and isolation are proven. No productive-hour or cost multiplier is asserted by F0.

## 8. Freeze and release consequences

Freeze this selection only after independent non-author architecture/security review and current-base repository checks. The four-path source candidate is production-inert. A source merge protects a decision and its bounded plan, not an adapter installation, provider entitlement, first-read endpoint, parent wake or autonomous fleet. The record test's paired mutations are documentation checks, not evidence that the runtime enforces these boundaries.

Existing HF1, PF1, first-read, plural-reader, Wake, role-loadability and release owners retain their current operations and exact source boundaries. Their admitted repairs do not wait for another F0 diagram. Any new implementation request follows the established owner and its complete path/consumer closure. Do not revive terminal C0/A0/G0 research children or the spent CAP provider attempt. No static instruction in this file grants START, rebind, merge, deployment or financial/trading authority.
