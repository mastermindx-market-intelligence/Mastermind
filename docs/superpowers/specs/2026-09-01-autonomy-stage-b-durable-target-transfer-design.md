# Stage B durable Sol target correction v3

Protected basis: `Mastermind@24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8`; operation `stage-b0-r1-real-owner-gap-repair-20260902-sol-001`; state `SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_MODES / PRODUCTION_INERT`.

This replaces the v1/v2 implementation gate. Current Git has empty, test-overlay-only `root_job_bindings`; `with_root_job_bindings()` accepts a caller complete-map overlay; `policy_digest()` excludes it; and no `ceo + codex` target exists. Those surfaces, RuntimeBinding, Wake ACK, placement, Slack, and model prose are not root-assignment authority. Initial assignment is held; succession cannot bootstrap it; cross-alias transfer has no owner. The real ACK is typed `WakeAcknowledgement`, command `<wake_id>:ACK`; the former consumption-ACK schema/fields were fictional. Machine vocabulary is `chatgpt-sol`, never `chatgpt-web`.

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "schema":"mastermind.autonomy_stage_b_f0_contract.v3",
  "protected_source_sha":"24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8",
  "repair_operation":"stage-b0-r1-real-owner-gap-repair-20260902-sol-001",
  "supersedes":["mastermind.autonomy_stage_b_f0_contract.v1","mastermind.autonomy_stage_b_f0_contract.v2"],
  "claim":"SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_MODES / PRODUCTION_INERT",
  "stage_b1":"NOT_AUTHORIZED / ZERO_SUPPORTED_MODES / PRODUCTION_DISARMED",
  "supported_modes":[],
  "supported_surfaces":[],
  "modes":{
    "INITIAL_ASSIGNMENT":{"state":"HELD","missing":["root_binding_assignment_owner","codex_ceo_target_owner"]},
    "SAME_ALIAS_GENERATION_SUCCESSION":{"state":"HELD","missing":["valid_current_stage_b_assignment"]},
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER":{"state":"HELD","missing":["cross_alias_authority_owner"]}
  },
  "root_authority":{"state":"MISSING_OWNER","non_authority":["caller overlay","policy_digest","defaults","RuntimeBinding","Wake ACK","placement","Slack/model prose"],"identity":["root_job_id","target_seat","session_alias","catalog_digest","revision_or_epoch","immutable_receipt","authority_provenance","replay_correction_law"],"discriminator":"different aliases for one root/seat never yield interchangeable authority"},
  "codex_ceo_target":{"state":"ABSENT","owner":"wake_session_targets.json + SessionTargetRegistry","production_armed":false},
  "command":{"schema":"UNFROZEN_PENDING_OWNER_FIELDS","caller_id":false,"derived_id":"SOL-TARGET-<sha256(canonical semantics)[0:32]>","lookup":"before mutable reads","foreign":"COMMAND_REPLAY_CONFLICT","race":"one append; loser EXPECTED_REVISION_MISMATCH","unknown":"reconcile same id; no retry/failover"},
  "ack":{"owner":"wake_ack_ingress + wake_ledger + WakeLedgerRepository","aggregate":"wake","event":"TARGET_ACKNOWLEDGED","command_id":"<destination_wake_id>:ACK","type":"control_plane.wake_ledger.WakeAcknowledgement","fields":["obligation_id","ack_mode","target_seat","session_alias","reasoning_surface","binding_id","acknowledged_at","claimed_obligation_ids","operator_authority_receipt","binding_generation","delivered_command_id"],"forbidden":["consumed_turn_reference","acknowledgement_token","mastermind.wake_consumption_ack/v1"],"law":"read exact causal request/delivery/ACK; Stage B writes no ACK or release"},
  "release":{"event":"OHF_RECONCILE_OBSERVATION","type":"mastermind.operator_harness_reconcile_observation/v1","required":["process_liveness=PROVEN_DEAD","provider_writer_state=RELEASED"]},
  "history":{"state":"NOT_BUILT","owner":"future immutable root-Job Runtime Events"},
  "projection":["copy all roots and seats","replace selected root ceo only after authority proof","preserve unrelated roots and sibling seats","call with_root_job_bindings once with complete map"],
  "transaction":["refuse until predecessor protected","derive/lookup command id","BEGIN IMMEDIATE","read root/authority/catalog/current binding/ACK/release","append at most one immutable root-Job event","reconcile only by same id"],
  "no_rebuild":{"tables":[],"migrations":[],"registries":[],"runtime_rows_mutated":false,"provider_or_slack_calls":false,"production_armed":false},
  "next":"STAGE-B-P0_ROOT_TARGET_AUTHORITY_ARCHITECTURE_FREEZE"
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

Next is a records-only freeze for one durable Executive-owned root/seat/alias authority receipt and one canonical production-disarmed Codex CEO target through the existing catalog, with full-map projection, root-scoped resolution, and conflicting-overlay refusal. Only its protected proof can authorize a new Stage-B1 source law. This carrier adds no target store, registry, lifecycle, queue, lease, provider action, or canary.
