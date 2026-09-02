---
schema: mastermind.w3c_dialogue_observation_authority_design.v1
operation: w3c-p0-dialogue-observation-authority-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# W3C-P0 Dialogue Observation Authority Design

## Status and outcome

This records-only freeze separates three authorities that current W3C PR #357 cannot lawfully synthesize: active Executive worker observation, post-terminal ORION R2 RESULT observation, and the Agent Relay's ephemeral hot waiter. Current capability is `SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_OBSERVATION_MODES / PRODUCTION_INERT`.

After later implementation, the existing Agent Relay may validate bounded V2 parent/message history, resolve one exact observation through the existing Executive service, suppress a redundant cold Wake when the same Relay already owns the exact waiter, and feed the existing observer/Wake owners. P0 itself implements and authorizes none of that.

## Owner and no-rebuild boundary

- `DialogueEngineV2` owns bounded Slack history, exact V2 parent/message validation, ensure/reconciliation, sender policy, and reply lineage. Slack is transport evidence, not lifecycle authority.
- WP-3 owns posting-time active-worker authorization only. `WorkerDialogueCaller` is never replayed as observation authority.
- Executive Runtime plus the protected ORION R2 admission-owned dialogue binding/current resolver own active Job/Attempt/BUSY Worker/effective-grant/profile/current RuntimeBinding truth.
- The already-started ORION R2 operation `ad-ret1-terminal-return-transport-r2-20260830-orion-001` owns post-time terminal RESULT message identity and effect-known projection receipt. A terminal worker is no longer BUSY, so WP-3 cannot prove terminal observation. No parallel RET2 projection carrier may be minted for this capability.
- The existing Agent Relay process owns only an ephemeral exact waiter around `wait_for_reply`; provider `attention_inflight` is non-equivalent.
- Wake Fabric remains sole Wake request/delivery/effect-unknown/ACK/source-resolution owner.
- Rejected: Relay database access, broad general-control access, CeoIngress reuse, another daemon/ledger/cursor/queue/registry/retry plane, model/Slack/account/title/time authority, a worker-thread callback escape, or a second terminal projection operation.

## Normative contract

<!-- W3C-P0-CONTRACT:START -->
```json
{"active_waiter":{"key_fields":["parent_fingerprint","operation_key","session_ref","target_seat"],"missing_or_failed_lookup":"FAIL_CLOSED_BEFORE_WAKE_PERSISTENCE","owner":"EXISTING_AGENT_RELAY_PROCESS","provider_attention_inflight_is_equivalent":false,"register_at":"WAIT_FOR_REPLY_BEFORE_FIRST_POLL","remove_at":"WAIT_FOR_REPLY_FINALLY","restart_behavior":"REGISTRY_EMPTY_AND_WAKE_IDEMPOTENCY_REMAINS_AUTHORITY","source_ref_is_key":false,"storage":"EPHEMERAL_MEMORY_ONLY"},"candidate_collection":{"af_unix_service_must_remain_available":true,"interface":"ASYNC_BOUNDED_IMMUTABLE_TUPLE","maximum_cardinality_required":true,"maximum_inflight_collections":1,"per_candidate_fault_isolation":true,"synchronous_iterable_callback_allowed":false,"timeout_required":true,"unresolved_collection_behavior":"NO_NEW_COLLECTION_ZERO_PROVIDER_EFFECT","worker_thread_allowed":false},"current_state":{"authorized_modes":[],"capability":"SPEC_ONLY","production_armed":false,"provider_effect":false,"runtime_effect":false},"failure_states":{"ACTIVE_RUNTIME_UNAVAILABLE":"UNKNOWN_ZERO_EFFECT","COLLECTION_OVERFLOW":"REFUSE_PASS_ZERO_EFFECT","COLLECTION_TIMEOUT":"UNKNOWN_ZERO_EFFECT","LISTENER_UNAVAILABLE":"UNKNOWN_ZERO_EFFECT","MULTIPLE_ACTIVE_BINDINGS":"CONFLICT_ZERO_EFFECT","PARENT_INVALID":"REFUSE_ZERO_EFFECT","PARENT_NOT_EXECUTIVE_BOUND":"HELD_ZERO_EFFECT","R2_EFFECT_UNKNOWN":"UNKNOWN_ZERO_EFFECT","R2_RECEIPT_MISSING":"HELD_ZERO_EFFECT","WAITER_LOOKUP_UNAVAILABLE":"HELD_ZERO_EFFECT"},"implementation_predecessors":{"ACTIVE_CURRENT_WORKER":["R2_DIALOGUE_BINDING_AND_RUNTIME_RESOLVER_PROTECTED"],"RELAY_CONSUMER":["EXECUTIVE_OBSERVATION_LISTENER_PROTECTED","ACTIVE_WAITER_REGISTRY_PROTECTED"],"TERMINAL_RESULT":["RET1_PROTECTED","ORION_R2_TERMINAL_PROJECTION_PROTECTED"]},"mode_non_interchangeability":{"active_must_require_worker_busy":true,"active_receipt_cannot_authorize_terminal":true,"effect_unknown_terminal_is":"UNKNOWN","terminal_must_not_require_worker_busy":true,"terminal_receipt_cannot_authorize_active":true},"modes":{"ACTIVE_CURRENT_WORKER":{"authority_owner":"EXECUTIVE_RUNTIME_PLUS_PROTECTED_R2_DIALOGUE_BINDING","forbidden_substitutes":["WORKER_DIALOGUE_CALLER_REPLAY","SLACK_AUTHOR_ID","MODEL_TEXT","ACCOUNT_LABEL","TITLE_OR_RECENCY","CALLER_SUPPLIED_JOB_ATTEMPT_WORKER"],"required_facts":["EXACT_PARENT_BINDING_RECEIPT","EXACT_ROOT_AND_CHILD_JOB","CURRENT_ACTIVE_ATTEMPT","CURRENT_BUSY_WORKER","CURRENT_RUNTIME_BINDING","EFFECTIVE_GRANT_AND_PROFILE_ATTESTATION"],"status":"HELD_PREDECESSOR_UNPROTECTED"},"TERMINAL_RESULT":{"accepted_projection_effects":["APPLIED"],"authority_owner":"EXISTING_ORION_R2_TERMINAL_DIALOGUE_PROJECTION_RECEIPT","forbidden_substitutes":["ACTIVE_WORKER_PREDICATE","SLACK_RESULT_TEXT_ALONE","MESSAGE_TIMESTAMP","MODEL_SUMMARY","EFFECT_UNKNOWN_PROJECTION","PARALLEL_RET2_PROJECTION_CARRIER"],"required_facts":["EXACT_PARENT_BINDING_RECEIPT","COMPLETED_RUNTIME_TERMINAL_RECEIPT","RET1_TERMINAL_CANDIDATE","R2_MESSAGE_IDENTITY","R2_PROJECTION_EFFECT_KNOWN"],"status":"HELD_R2_TERMINAL_PROJECTION_UNPROTECTED"}},"no_rebuild":["NO_NEW_JOB_ATTEMPT_WORKER_EVENT_LIFECYCLE","NO_SECOND_RUNTIME_BINDING_OWNER","NO_SECOND_AGENT_RELAY_SERVICE","NO_SECOND_WAKE_LEDGER","NO_CURSOR_OR_INBOX_DATABASE","NO_GENERIC_EXECUTIVE_READ_GATEWAY","NO_PROVIDER_PROCESS_MANAGER","NO_TARGET_REGISTRY","NO_RETRY_OR_FAILOVER_PLANE","NO_SECOND_TERMINAL_PROJECTION_OPERATION"],"operation":"w3c-p0-dialogue-observation-authority-20260902-sol-001","relay_discovery":{"conflicting_parent_is_candidate":false,"executive_request_per_parent":true,"parent_deduplication_key":"PARENT_FINGERPRINT","parent_limit_required":true,"persistent_cursor":false,"source":"BOUNDED_VALIDATED_V2_PARENT_HISTORY","unknown_parent_is_candidate":false},"request_contract":{"caller_forbidden_fields":["root_job_id","job_id","attempt_id","worker_id","execution_profile_id","capability_policy_digest","runtime_binding","native_handle","account_label","provider","target_seat","authority","mode"],"exact_keys":["schema","request_id","parent"],"operation":"resolve_dialogue_observation","parent_is_untrusted_lookup_input":true,"parent_required_identity":["schema","work_ref","commission_ref","session_ref","operation_key","watch_mode","allowed_sol_user_ids","created_at","fingerprint"],"schema":"mastermind.executive_dialogue_observation_request.v1"},"response_contract":{"active_fields":["root_job_id","job_id","attempt_id","worker_id","execution_profile_id","execution_profile_digest","capability_policy_digest","runtime_binding","parent_fingerprint","evidence_digest"],"always_false_authority_flags":["action_authoritative","provider_action_authorized","wake_write_authorized","lifecycle_write_authorized"],"forbidden_response_fields":["native_handle","account_label","provider_home","credential_home","token","secret","raw_message_body","private_transcript","local_path"],"public_runtime_binding_fields":["session_alias","binding_id","binding_generation","reasoning_surface"],"resolved_modes":["ACTIVE_CURRENT_WORKER","TERMINAL_RESULT"],"schema":"mastermind.executive_dialogue_observation_response.v1","states":["RESOLVED","UNAVAILABLE","UNKNOWN","CONFLICT","HELD"],"terminal_fields":["root_job_id","job_id","attempt_id","worker_id","parent_fingerprint","message_key","message_fingerprint","terminal_digest","result_digest","projection_receipt_digest","projection_effect","evidence_digest"]},"schema":"mastermind.w3c_dialogue_observation_authority.v1","transport":{"agent_os_writes":false,"allowed_operations":["resolve_dialogue_observation"],"allowed_peer_uid":457,"bounded_request_bytes":65536,"bounded_response_bytes":65536,"ceo_ingress_socket_reuse":false,"default_enabled":false,"direct_database_access_from_relay":false,"enabled_bind_failure":"CAPABILITY_NOT_READY","general_control_socket_reuse":false,"listener_kind":"DEDICATED_READ_ONLY_AF_UNIX","listener_socket":"/var/run/mastermind-executive/dialogue-observation.sock","owner_process":"EXISTING_EXECUTIVE_SERVICE","request_is_enumeration_capable":false,"runtime_writes":false,"slack_writes":false,"wake_writes":false}}
```
<!-- W3C-P0-CONTRACT:END -->

## Transaction and transport law

The request carries one exact validated `mastermind.agent_dialogue_parent.v2` object only as untrusted lookup input. It cannot select a mode, Job, Attempt, Worker, RuntimeBinding, target, provider, or authority. The Executive owner re-derives every privileged fact in one read snapshot. Missing binding evidence is held, not repaired from Slack.

The future transport is one default-disabled, read-only AF_UNIX listener inside the existing Executive service process, restricted to UID 457 and `resolve_dialogue_observation`. It neither reuses the general control socket nor CeoIngress and it is not enumeration-capable.

Active mode requires one current active Attempt, BUSY Worker, exact protected R2 parent binding, profile/policy attestation, and current RuntimeBinding. Terminal mode requires one completed terminal receipt plus one exact ORION R2 `APPLIED` projection receipt. Recovery is a proof path to `APPLIED`, not a second projection state. The two modes are non-interchangeable; effect-unknown terminal evidence remains unknown.

## Relay and waiter law

Relay discovers only bounded, unique, fully validated V2 parents through its existing shared Slack client. Candidate collection is async, time/cardinality bounded, returns an immutable tuple, permits one in-flight collection, uses no synchronous iterable or worker thread, and cannot stop the accepted AF_UNIX service.

The hot waiter key is exact parent fingerprint + operation key + session ref + target seat. Registration occurs before the first `wait_for_reply` poll and removal occurs in `finally`. `source_ref` cannot be the key because the future reply does not exist when waiting begins. Missing waiter evidence fails closed before Wake persistence. Restart clears the ephemeral waiter; Wake ledger identity remains durable duplicate authority.

## Implementation sequence

1. P1: after the existing ORION R2 operation protects its active binding/current resolver, add the pure active observation reducer and dedicated Executive listener, default disabled.
2. P2: add the Relay observation client, bounded parent discovery, async collection, exact waiter registry, and real default-disarmed composition inside the existing Agent Relay process.
3. R2 terminal projection: continue the already-started ORION R2 operation until it protects one immutable RESULT and effect-known receipt. Do not mint a parallel RET2 projection operation.
4. P3: extend the same Executive resolver for the protected ORION R2 terminal receipt; no second endpoint.
5. P4: run one disposable target canary proving one Wake/provider turn/ACK/source resolution and zero duplicate write after restart.

## Stop condition

P0 is complete only when these records and mutation-discriminating source-law tests are protected. It grants no implementation, listener install, host/config change, target arming, provider I/O, new terminal projection operation, canary, or production acceptance.
