---
schema: mastermind.w3c_dialogue_observation_authority_design.v1
operation: w3c-p0-dialogue-observation-authority-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# W3C-P0 Dialogue Observation Authority Design

## Status and outcome

This records-only freeze separates three authorities that current W3C PR #357 cannot lawfully synthesize:

1. current active-worker truth owned by Executive Runtime plus the existing ORION R2 dialogue binding;
2. post-terminal RESULT projection truth owned by the same already-started ORION R2 operation; and
3. the Agent Relay process's exact ephemeral `wait_for_reply` waiter.

Current capability is `SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_OBSERVATION_MODES / PRODUCTION_INERT`.
P0 implements, installs, enables and exercises none of the later runtime path.

## Owner and no-rebuild boundary

- `DialogueEngineV2` owns bounded Slack history, exact V2 parent/message validation, sender policy and reply lineage. Slack is transport evidence, not Executive lifecycle truth.
- WP-3 owns posting-time active-worker authorization only. `WorkerDialogueCaller` is never replayed as observation authority.
- Executive Runtime plus the protected ORION R2 admission-owned dialogue binding/current resolver own active Job, Attempt, BUSY Worker, effective-grant/profile and current RuntimeBinding truth.
- The already-started operation `ad-ret1-terminal-return-transport-r2-20260830-orion-001` owns terminal RESULT identity and the effect-known projection receipt. No parallel RET2 projection carrier may be minted.
- The existing Agent Relay process owns only an ephemeral exact waiter around `wait_for_reply`; provider `attention_inflight` is non-equivalent.
- Wake Fabric remains the sole Wake request, delivery, effect-unknown, acknowledgement and source-resolution owner.
- Rejected: Relay database access, broad general-control access, CeoIngress reuse, another daemon/ledger/cursor/queue/registry/retry plane, model/Slack/account/title/time authority, worker-thread callback escape, or a second terminal-projection operation.

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
      "status": "HELD_R2_TERMINAL_PROJECTION_UNPROTECTED",
      "authority_owner": "EXISTING_ORION_R2_TERMINAL_DIALOGUE_PROJECTION_RECEIPT",
      "required_facts": [
        "EXACT_PARENT_BINDING_RECEIPT",
        "COMPLETED_RUNTIME_TERMINAL_RECEIPT",
        "RET1_TERMINAL_CANDIDATE",
        "R2_MESSAGE_IDENTITY",
        "R2_PROJECTION_EFFECT_KNOWN"
      ],
      "accepted_projection_effects": [
        "APPLIED"
      ],
      "forbidden_substitutes": [
        "ACTIVE_WORKER_PREDICATE",
        "SLACK_RESULT_TEXT_ALONE",
        "MESSAGE_TIMESTAMP",
        "MODEL_SUMMARY",
        "EFFECT_UNKNOWN_PROJECTION",
        "PARALLEL_RET2_PROJECTION_CARRIER"
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
      "work_ref",
      "commission_ref",
      "session_ref",
      "operation_key",
      "watch_mode",
      "allowed_sol_user_ids",
      "created_at",
      "fingerprint"
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
    "owner_user": "_mastermind_exec",
    "owner_uid": 450,
    "peer_user": "_mastermind_agent_relay",
    "allowed_peer_uid": 457,
    "host_identity_source": [
      "ops/executive_os/a2_agent_relay_enrollment.py::EXEC_UID=450",
      "ops/executive_os/a2_agent_relay_enrollment.py::RELAY_UID=457",
      "ops/executive_os/a2_agent_relay_enrollment.py::_RELAY_GROUP_MEMBERS includes _mastermind_exec"
    ],
    "listener_kind": "DEDICATED_READ_ONLY_AF_UNIX",
    "socket_parent": "/var/run/mastermind-dialogue-observation",
    "listener_socket": "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
    "socket_parent_owner_uid": 450,
    "socket_parent_group_gid": 457,
    "socket_parent_mode": "0710",
    "socket_owner_uid": 450,
    "socket_group_gid": 457,
    "socket_mode": "0660",
    "peer_credentials_required": true,
    "parent_symlink_forbidden": true,
    "socket_symlink_forbidden": true,
    "replacement_requires_owned_stale_inode": true,
    "socket_cleanup_requires_identity_match": true,
    "general_control_parent_reuse": false,
    "allowed_operations": [
      "resolve_dialogue_observation"
    ],
    "max_requests_per_connection": 1,
    "general_control_socket_reuse": false,
    "ceo_ingress_socket_reuse": false,
    "direct_database_access_from_relay": false,
    "request_is_enumeration_capable": false,
    "unbound_response_is_uniform": true,
    "runtime_writes": false,
    "agent_os_writes": false,
    "slack_writes": false,
    "wake_writes": false,
    "default_enabled": false,
    "enabled_bind_failure": "CAPABILITY_NOT_READY",
    "permission_or_inode_conflict": "CAPABILITY_NOT_READY",
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
    "R2_RECEIPT_MISSING": "HELD_ZERO_EFFECT",
    "R2_EFFECT_UNKNOWN": "UNKNOWN_ZERO_EFFECT",
    "LISTENER_UNAVAILABLE": "UNKNOWN_ZERO_EFFECT",
    "LISTENER_PERMISSION_CONFLICT": "CAPABILITY_NOT_READY_ZERO_EFFECT",
    "LISTENER_INODE_CONFLICT": "CAPABILITY_NOT_READY_ZERO_EFFECT",
    "PEER_UID_REFUSED": "REFUSE_ZERO_EFFECT",
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
    "NO_RETRY_OR_FAILOVER_PLANE",
    "NO_SECOND_TERMINAL_PROJECTION_OPERATION"
  ],
  "implementation_predecessors": {
    "ACTIVE_CURRENT_WORKER": [
      "R2_DIALOGUE_BINDING_AND_RUNTIME_RESOLVER_PROTECTED"
    ],
    "TERMINAL_RESULT": [
      "RET1_PROTECTED",
      "ORION_R2_TERMINAL_PROJECTION_PROTECTED"
    ],
    "RELAY_CONSUMER": [
      "EXECUTIVE_OBSERVATION_LISTENER_PROTECTED",
      "ACTIVE_WAITER_REGISTRY_PROTECTED"
    ]
  }
}
```
<!-- W3C-P0-CONTRACT:END -->

## Read-transaction law

The request carries one exact validated `mastermind.agent_dialogue_parent.v2` object only as untrusted lookup input. It cannot select a mode, Job, Attempt, Worker, RuntimeBinding, target, provider or authority. The Executive owner re-derives every privileged fact in one read snapshot. Missing binding evidence is held, never repaired from Slack.

Active mode requires one current Attempt, BUSY Worker, exact protected R2 parent binding, profile/policy attestation and current RuntimeBinding. Terminal mode requires one completed Runtime receipt plus one exact ORION R2 `APPLIED` projection receipt. Recovery is a proof path to canonical `APPLIED`, not a second projection state.

## Host and transport law

The future listener is inside the existing Executive service process but uses a dedicated runtime directory. It must not share the general Executive-control socket or parent directory. Current protected enrollment fixes `_mastermind_exec` at UID 450 and `_mastermind_agent_relay` at UID/GID 457, with the Executive user admitted to the Relay group. The dedicated parent is owned `450:457` at mode `0710`; the socket is owned `450:457` at mode `0660`. Only peer UID 457 may issue the single operation.

Startup validates absolute paths, parent/final-component non-symlink identity, owner/group/mode and any stale socket inode before unlink or replacement. A foreign, ambiguous or mismatched inode is `CAPABILITY_NOT_READY`; it is never overwritten. Shutdown removes only the inode identity created by this process. These filesystem rules grant reachability without exposing the general Executive socket family.

## Relay and waiter law

Relay discovers only bounded, unique, fully validated V2 parents through its existing shared Slack client. Candidate collection is async, time/cardinality bounded, returns an immutable tuple, permits one in-flight collection, uses no synchronous iterable or worker thread, and cannot stop the accepted AF_UNIX service.

The hot waiter key is exact parent fingerprint + operation key + session ref + target seat. Registration occurs before the first `wait_for_reply` poll and removal occurs in `finally`. `source_ref` cannot be the key because the future reply does not exist when waiting begins. Missing waiter evidence fails closed before Wake persistence. Restart clears the ephemeral waiter; Wake ledger identity remains the durable duplicate authority.

## Implementation sequence

1. P1: after existing ORION R2 protects its active binding/current resolver, add the pure active-observation reducer and dedicated Executive listener, default disabled.
2. P2: add the Relay observation client, bounded parent discovery, async collection, exact waiter registry and real default-disarmed composition inside the existing Relay process.
3. R2 terminal projection: continue the already-started ORION R2 operation until it protects one immutable RESULT and effect-known receipt; do not mint a parallel RET2 operation.
4. P3: extend the same Executive resolver for the protected R2 terminal receipt; no second endpoint.
5. P4: run one disposable target canary proving one Wake/provider turn/ACK/source resolution and zero duplicate write after restart.

## Stop condition

P0 is complete only when these records and mutation-discriminating source-law tests are protected. It grants no implementation, listener install, host/config change, target arming, provider I/O, new terminal-projection operation, canary or production acceptance.
