---
schema: mastermind.w3c_dialogue_observation_authority_design.v1
operation: w3c-p0-dialogue-observation-authority-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# W3C-P0 Dialogue Observation Authority Design

## Status

This document freezes the missing authority and transport boundary between the existing
Executive runtime and the existing Agent Relay. It does not implement, install, enable, or
exercise that boundary.

Current capability is:

`SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_OBSERVATION_MODES / PRODUCTION_INERT`

The immediate consumer is the existing W3C carrier on Mastermind PR #357. That carrier contains
useful routing, persisted-Wake, and in-process loop components, but it is not releasable while its
candidate source is an arbitrary callback and its production entrypoint never composes a lawful
source.

## Outcome

After the implementation waves below, one bounded Agent Relay pass can:

1. read bounded Slack history through its existing client;
2. validate one canonical Agent Dialogue V2 parent as untrusted lookup input;
3. ask the existing Executive service for one exact, read-only observation-authority result;
4. distinguish an active current worker from an already-projected terminal RESULT;
5. suppress a cold Wake when the existing Relay process already owns the exact hot waiter;
6. invoke the existing `DialogueTurnObserver` and persisted Wake carrier without inventing
   Job, Attempt, Worker, RuntimeBinding, provider, target, or authority facts.

No stage is complete merely because the source compiles or the listener exists. The machine
capability is complete only when a real watched turn reaches the exact current target once, restart
re-observation produces zero second provider write, and target acknowledgement/source resolution
remain distinct downstream facts.

## Current-source capability ledger

- `PROVEN_LIVE`: none for this W3C observation path.
- `BUILT_NOT_PROVEN`: Agent Dialogue V2 parent ensure, WP-3 posting-time worker binding,
  RuntimeBinding projection, persisted Wake carrier, current-writer Codex Wake delivery, and the
  safe components on PR #357.
- `PARTIAL`: PR #357 routing/runtime composition; it is callback-driven, default-dark, and has no
  lawful production observation source.
- `DARK_OR_DISCONNECTED`: no production Relay-to-Executive observation transport is installed or
  enabled.
- `SPEC_ONLY`: this P0 authority and transport freeze.
- `NOT_BUILT`: the dedicated Executive observation listener, Relay observation client, bounded
  parent discovery, exact hot-waiter registry, and RET2 terminal projection receipt.
- `REJECTED_BY_DESIGN`: opening the Executive SQLite database from Relay, widening the general
  Executive control socket to the Relay principal, reusing CeoIngress for reads, trusting Slack
  prose as runtime authority, or treating provider `attention_inflight` as a dialogue waiter.

## Authority separation

### Agent Dialogue parent owner

The existing Agent Relay / `DialogueEngineV2` owns bounded Slack history, V2 parent parsing,
parent ensure/reconciliation, sender policy, and exact message lineage. A Slack parent is transport
evidence, not Executive lifecycle truth.

### Posting-time worker authority

WP-3 `resolve_company_dialogue_binding()` remains the write-time gate for one active worker posting
through Company Dialogue. Its `WorkerDialogueCaller` and BUSY-worker predicate must not be reused as
later observer authority.

### Active observation authority

The Executive runtime is the sole owner of current Job, Attempt, Worker, effective grant,
execution profile/policy, and current RuntimeBinding facts. The active observation lane must consume
the exact admission-owned commission/dialogue provenance and candidate-keyed Runtime resolver from
the existing ORION R2 operation after that source is protected. P0 does not rename, clone, or
reimplement that owner.

### Terminal observation authority

RET2 is the sole future owner of the post-time terminal RESULT projection receipt. A terminal
worker is no longer BUSY, so terminal observation can never be proven by WP-3. Slack RESULT text is
not authoritative without an exact RET2 receipt whose projection effect is known.

### Hot waiter owner

The existing Agent Relay process owns transient `wait_for_reply` calls. It must register the exact
validated dialogue waiter in memory before its first bounded poll and remove it in `finally`.
Provider adapter state is not equivalent. The registry is ephemeral and is not a new durable
watcher, cursor, inbox, or lifecycle plane.

### Wake owner

Wake Fabric remains the only owner of Wake identity, requested/delivery/effect-unknown state,
target acknowledgement, and source resolution. The observation service does not write Wake.

## Normative contract

<!-- W3C-P0-CONTRACT:START -->
```json
{
  "schema": "mastermind.w3c_dialogue_observation_authority.v1",
  "operation": "w3c-p0-dialogue-observation-authority-20260902-sol-001",
  "current_state": {
    "capability": "SPEC_ONLY",
    "authorized_modes": [],
    "production_armed": false,
    "provider_effect": false,
    "runtime_effect": false
  },
  "modes": {
    "ACTIVE_CURRENT_WORKER": {
      "status": "HELD_PREDECESSOR_UNPROTECTED",
      "authority_owner": "EXECUTIVE_RUNTIME_PLUS_PROTECTED_R2_DIALOGUE_BINDING",
      "required_facts": [
        "EXACT_PARENT_BINDING_RECEIPT",
        "EXACT_ROOT_AND_CHILD_JOB",
        "CURRENT_ACTIVE_ATTEMPT",
        "CURRENT_BUSY_WORKER",
        "CURRENT_RUNTIME_BINDING",
        "EFFECTIVE_GRANT_AND_PROFILE_ATTESTATION"
      ],
      "forbidden_substitutes": [
        "WORKER_DIALOGUE_CALLER_REPLAY",
        "SLACK_AUTHOR_ID",
        "MODEL_TEXT",
        "ACCOUNT_LABEL",
        "TITLE_OR_RECENCY",
        "CALLER_SUPPLIED_JOB_ATTEMPT_WORKER"
      ]
    },
    "TERMINAL_RESULT": {
      "status": "HELD_RET2_NOT_BUILT",
      "authority_owner": "RET2_TERMINAL_DIALOGUE_PROJECTION_RECEIPT",
      "required_facts": [
        "EXACT_PARENT_BINDING_RECEIPT",
        "COMPLETED_RUNTIME_TERMINAL_RECEIPT",
        "RET1_TERMINAL_CANDIDATE",
        "RET2_MESSAGE_IDENTITY",
        "RET2_PROJECTION_EFFECT_KNOWN"
      ],
      "accepted_projection_effects": [
        "APPLIED",
        "RECOVERED"
      ],
      "forbidden_substitutes": [
        "ACTIVE_WORKER_PREDICATE",
        "SLACK_RESULT_TEXT_ALONE",
        "MESSAGE_TIMESTAMP",
        "MODEL_SUMMARY",
        "EFFECT_UNKNOWN_PROJECTION"
      ]
    }
  },
  "request_contract": {
    "schema": "mastermind.executive_dialogue_observation_request.v1",
    "operation": "resolve_dialogue_observation",
    "exact_keys": [
      "schema",
      "request_id",
      "parent"
    ],
    "parent_is_untrusted_lookup_input": true,
    "parent_required_identity": [
      "schema",
      "fingerprint",
      "work_ref",
      "commission_ref",
      "session_ref",
      "operation_key",
      "watch_mode",
      "applies_to"
    ],
    "caller_forbidden_fields": [
      "root_job_id",
      "job_id",
      "attempt_id",
      "worker_id",
      "execution_profile_id",
      "capability_policy_digest",
      "runtime_binding",
      "native_handle",
      "account_label",
      "provider",
      "target_seat",
      "authority",
      "mode"
    ]
  },
  "response_contract": {
    "schema": "mastermind.executive_dialogue_observation_response.v1",
    "states": [
      "RESOLVED",
      "UNAVAILABLE",
      "UNKNOWN",
      "CONFLICT",
      "HELD"
    ],
    "resolved_modes": [
      "ACTIVE_CURRENT_WORKER",
      "TERMINAL_RESULT"
    ],
    "public_runtime_binding_fields": [
      "session_alias",
      "binding_id",
      "binding_generation",
      "reasoning_surface"
    ],
    "active_fields": [
      "root_job_id",
      "job_id",
      "attempt_id",
      "worker_id",
      "execution_profile_id",
      "execution_profile_digest",
      "capability_policy_digest",
      "runtime_binding",
      "parent_fingerprint",
      "evidence_digest"
    ],
    "terminal_fields": [
      "root_job_id",
      "job_id",
      "attempt_id",
      "worker_id",
      "parent_fingerprint",
      "message_key",
      "message_fingerprint",
      "terminal_digest",
      "result_digest",
      "projection_receipt_digest",
      "projection_effect",
      "evidence_digest"
    ],
    "always_false_authority_flags": [
      "action_authoritative",
      "provider_action_authorized",
      "wake_write_authorized",
      "lifecycle_write_authorized"
    ],
    "forbidden_response_fields": [
      "native_handle",
      "account_label",
      "provider_home",
      "credential_home",
      "token",
      "secret",
      "raw_message_body",
      "private_transcript",
      "local_path"
    ]
  },
  "mode_non_interchangeability": {
    "active_must_require_worker_busy": true,
    "terminal_must_not_require_worker_busy": true,
    "active_receipt_cannot_authorize_terminal": true,
    "terminal_receipt_cannot_authorize_active": true,
    "effect_unknown_terminal_is": "UNKNOWN"
  },
  "transport": {
    "owner_process": "EXISTING_EXECUTIVE_SERVICE",
    "listener_kind": "DEDICATED_READ_ONLY_AF_UNIX",
    "listener_socket": "/var/run/mastermind-executive/dialogue-observation.sock",
    "allowed_peer_uid": 457,
    "allowed_operations": [
      "resolve_dialogue_observation"
    ],
    "general_control_socket_reuse": false,
    "ceo_ingress_socket_reuse": false,
    "direct_database_access_from_relay": false,
    "request_is_enumeration_capable": false,
    "runtime_writes": false,
    "agent_os_writes": false,
    "slack_writes": false,
    "wake_writes": false,
    "default_enabled": false,
    "enabled_bind_failure": "CAPABILITY_NOT_READY",
    "bounded_request_bytes": 65536,
    "bounded_response_bytes": 65536
  },
  "relay_discovery": {
    "source": "BOUNDED_VALIDATED_V2_PARENT_HISTORY",
    "persistent_cursor": false,
    "parent_limit_required": true,
    "parent_deduplication_key": "PARENT_FINGERPRINT",
    "executive_request_per_parent": true,
    "unknown_parent_is_candidate": false,
    "conflicting_parent_is_candidate": false
  },
  "candidate_collection": {
    "interface": "ASYNC_BOUNDED_IMMUTABLE_TUPLE",
    "synchronous_iterable_callback_allowed": false,
    "worker_thread_allowed": false,
    "timeout_required": true,
    "maximum_cardinality_required": true,
    "maximum_inflight_collections": 1,
    "unresolved_collection_behavior": "NO_NEW_COLLECTION_ZERO_PROVIDER_EFFECT",
    "per_candidate_fault_isolation": true,
    "af_unix_service_must_remain_available": true
  },
  "active_waiter": {
    "owner": "EXISTING_AGENT_RELAY_PROCESS",
    "storage": "EPHEMERAL_MEMORY_ONLY",
    "register_at": "WAIT_FOR_REPLY_BEFORE_FIRST_POLL",
    "remove_at": "WAIT_FOR_REPLY_FINALLY",
    "key_fields": [
      "parent_fingerprint",
      "operation_key",
      "session_ref",
      "target_seat"
    ],
    "source_ref_is_key": false,
    "provider_attention_inflight_is_equivalent": false,
    "missing_or_failed_lookup": "FAIL_CLOSED_BEFORE_WAKE_PERSISTENCE",
    "restart_behavior": "REGISTRY_EMPTY_AND_WAKE_IDEMPOTENCY_REMAINS_AUTHORITY"
  },
  "failure_states": {
    "PARENT_INVALID": "REFUSE_ZERO_EFFECT",
    "PARENT_NOT_EXECUTIVE_BOUND": "HELD_ZERO_EFFECT",
    "ACTIVE_RUNTIME_UNAVAILABLE": "UNKNOWN_ZERO_EFFECT",
    "MULTIPLE_ACTIVE_BINDINGS": "CONFLICT_ZERO_EFFECT",
    "RET2_RECEIPT_MISSING": "HELD_ZERO_EFFECT",
    "RET2_EFFECT_UNKNOWN": "UNKNOWN_ZERO_EFFECT",
    "LISTENER_UNAVAILABLE": "UNKNOWN_ZERO_EFFECT",
    "COLLECTION_TIMEOUT": "UNKNOWN_ZERO_EFFECT",
    "COLLECTION_OVERFLOW": "REFUSE_PASS_ZERO_EFFECT",
    "WAITER_LOOKUP_UNAVAILABLE": "HELD_ZERO_EFFECT"
  },
  "no_rebuild": [
    "NO_NEW_JOB_ATTEMPT_WORKER_EVENT_LIFECYCLE",
    "NO_SECOND_RUNTIME_BINDING_OWNER",
    "NO_SECOND_AGENT_RELAY_SERVICE",
    "NO_SECOND_WAKE_LEDGER",
    "NO_CURSOR_OR_INBOX_DATABASE",
    "NO_GENERIC_EXECUTIVE_READ_GATEWAY",
    "NO_PROVIDER_PROCESS_MANAGER",
    "NO_TARGET_REGISTRY",
    "NO_RETRY_OR_FAILOVER_PLANE"
  ],
  "implementation_predecessors": {
    "ACTIVE_CURRENT_WORKER": [
      "R2_DIALOGUE_BINDING_AND_RUNTIME_RESOLVER_PROTECTED"
    ],
    "TERMINAL_RESULT": [
      "RET1_PROTECTED",
      "RET2_TERMINAL_PROJECTION_PROTECTED"
    ],
    "RELAY_CONSUMER": [
      "EXECUTIVE_OBSERVATION_LISTENER_PROTECTED",
      "ACTIVE_WAITER_REGISTRY_PROTECTED"
    ]
  }
}
```
<!-- W3C-P0-CONTRACT:END -->

## Read transaction law

The Executive resolver opens one read transaction and re-derives every privileged identity. The
request never selects a Job, Attempt, Worker, RuntimeBinding, mode, or target. Parent data is first
validated as an exact V2 shape, then used only to locate an already-bound Executive dialogue
identity. Missing binding evidence is `HELD`; it is never repaired from Slack.

For active mode, the same snapshot must prove one current child, one current active Attempt, one BUSY
Worker, one current RuntimeBinding, and the exact protected R2 dialogue binding. The response expires
as evidence after the call. It is not a reusable capability token.

For terminal mode, the same snapshot must prove a completed terminal receipt and one exact RET2
projection receipt. `ATTEMPTED`, `EFFECT_UNKNOWN`, conflicting, or absent RET2 projection evidence
cannot authorize an observed terminal message.

## Relay consumer law

Relay discovers candidate parents only from bounded validated Slack history through its existing
client. It asks the dedicated Executive listener about each unique parent fingerprint, up to a hard
limit. The response does not replace Slack validation: the later observer must still reconstruct the
exact parent and message lineage from Slack. Executive truth answers who/what may be observed; Slack
answers what transport frames exist.

The current `RelayTurnCandidate` active-worker/caller shape on PR #357 is not the final public
contract. The later implementation must consume a closed observation-authority union and must not
require a replayed `WorkerDialogueCaller`.

## Hot waiter law

The current observer callback keyed by `source_ref` cannot represent a waiter that began before the
future reply message existed. The later W3C repair must query by exact parent identity plus target
seat. Registration derives one target seat from the validated caller direction and expected message
types. Mixed or ambiguous direction refuses registration; it never defaults to no waiter.

Restart clears the in-memory waiter registry because the waiting coroutine no longer exists. Wake
ledger identity/reconciliation remains the durable no-duplicate authority.

## Implementation waves

1. **W3C-P1 Executive active observation.** After ORION R2 protects its admission-owned binding and
   current resolver, add the pure observation reducer and one dedicated read-only listener inside the
   existing Executive service. Default disabled. No Relay modification.
2. **W3C-P2 Relay waiter and async discovery.** Add the exact in-memory waiter registry, dedicated
   client, bounded parent discovery, async immutable candidate collection, and real default-disarmed
   composition inside the existing Agent Relay process. Do not add a daemon.
3. **RET2 terminal projection.** Produce one immutable RESULT frame and exact post-time projection
   receipt through the existing Agent Dialogue/Relay owner. No direct Slack client, outbox, or retry
   plane.
4. **W3C-P3 terminal observation extension.** Extend the same Executive observation resolver to
   consume the protected RET2 receipt. No second endpoint or mode inference.
5. **W3C-P4 one-target canary.** Explicitly enable one disposable route and prove one watched turn,
   one Wake, one current-writer provider turn, exact target acknowledgement/source resolution, and
   zero duplicate write after restart.

## Stop condition

P0 is complete when these records are protected and future workers can implement without inventing
an authority owner. P0 does not authorize W3C implementation, listener installation, host config,
target arming, provider I/O, RET2, or a production canary.
