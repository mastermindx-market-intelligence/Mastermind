---
name: use-subagent-fabric
description: Use when an attended ChatGPT Web or Codex session needs bounded external-worker labor through the existing Mastermind M2 Subagent Fabric, including review, tests, research, census, or routine implementation.
---

# Use the existing Mastermind Subagent Fabric

Use the connected **Mastermind Subagent Fabric** tools for independently checkable leaf work. Keep coordinator judgment and acceptance with the parent. Native Codex forks are not external Fabric workers and can inherit the parent model. Do not substitute native Sol labor, create another orchestrator, or rebuild routing, queues, credentials or run state.

## Choose an admitted path

Load the current protected Mastermind procedures once at unfamiliar mission entry; reuse the compatible pin. Use an actually armed/admitted Executive route when appropriate. A read-only Executive connection or QUEUED intent is not dispatch. An existing Executive operation never becomes a new manual request.

This dedicated plugin is a typed attended interface to the existing M2 adapter. It requires a genuinely connected, authorized private channel. Installation, tool exposure, provider admission, worker START and result acceptance are separate facts. Missing optional Executive integration does not block an independently admitted new attended request. An explicit permission/consent denial never permits fallback through another actor or carrier.

## Dispatch one bounded child

For an unfamiliar connection, call `fabric_capabilities`; this observes the adapter, not provider admission. Resolve the **verified original operation root and immediate parent**. Web sessions must not invent `CODEX_THREAD_ID`, borrow a host's inherited native identity, or treat a root string as authentication. A new attended operation uses the incumbent operation/custody convention. Nested children retain the same original root and shared grant/capacity.

Choose one stable child ID once. `fabric_request` requires:

```text
run_id, root_id, parent_id
task_class: mechanical | fix_build | review | census | audit
task_complexity: C0_MECHANICAL | C1_ROUTINE_BOUNDED | C2_COMPLEX_BOUNDED | C3_FRONTIER_JUDGMENT
work_packet: objective, exact inputs, scope/non-goals, acceptance evidence, stop/return condition
```

Classify the child, not its parent's prestige. C3 requires `escalation_reason`. Let the existing router select a qualified economical provider/host; the tool does not accept host/model/account overrides. For review, use an actual author `subject_pool` when applicable, not a guessed provider. Include inputs in the packet or use verified worker-accessible references: Web `/mnt/data` and M2-only paths are not automatically available remotely. Keep packets within 16,000 characters and 32 KiB; avoid unnecessary disclosure or full-history dumps. Authorized work may legitimately involve keys or credentials; the request boundary does not scan, block or redact them.

**Hash presentation in request briefs:** In human/model-readable prose, show SHA-256 file hashes (64 hex) and git commit IDs (40 hex) as about **12 leading hex characters** (for example, `abc123def456`), clearly labeled as abbreviated. Preserve the **complete** digest/commit ID where required for machine verification, exact checkout, integrity checks, or executable commands, ideally in explicit structured identity fields rather than repeating it in prose. Never abbreviate the Fabric `run_id`, `root_id` or `parent_id`; those are exact correlation IDs, not hash displays. Do not rewrite a submitted packet or add a content-based refusal. This presentation rule avoids needless long hex strings in operator prose without weakening exact verification.

The tool checks the exact ID before submission. An existing run is inspected/reconciled, never replayed. Record its controller PID and original connection generation. `CONTROLLER_CREATED` does not prove worker START. Continue another useful parent-owned task without duplicating the child.

## Consume and verify

Observe only the same ID using `fabric_status`, bounded `fabric_wait`, or the original bound `fabric_controller_output`. Unchanged polling is not useful Pro work. No supported return path means no promise of background delivery.

Use `fabric_result` only when retained output is available and the ledger root matches. Read the **complete** response; use the existing `studio_output_page` receipt when output is paged. A preview or digest alone is not review. Result limits default to 8 KiB and permit at most 64 KiB. Oversized/unavailable output requires same-run recovery, not another worker.

After actual deterministic verification or authorized review, call `fabric_accept` with `by`, `expected_response_sha256`, and a concrete `verification_summary`. Supply `verification_summary` as one controlled evidence-basis code only: `deterministic_test_evidence` or `artifact_digest_comparison` for `by=deterministic`; `manual_result_review` or `independent_review_evidence` for `by=reviewer`. Free-form prose is rejected before any adapter call. Put the detailed review findings and evidence references in the existing source/review artifact, not this field. The code is an attestation of the method, not proof of the external checks. Never reattempt an acceptance whose effect is uncertain. It rechecks the response digest and reads back acceptance. The digest identifies the adapter response, not every referenced artifact; legacy acceptance is not an atomic cryptographic attestation. DONE or exit zero is not acceptance.

For `EFFECT_UNKNOWN`, lost modifying responses, existing IDs, or undelivered results: preserve the original root/run/PID, inspect the incumbent owner, and do not retry through another ID/host/carrier. Do not kill a controller or release a lease to simulate cancellation. A new chat or backend generation does not transfer custody or recreate a PID binding.

Protected procedures, actual resource permissions, source custody, admission and release controls remain controlling. The private channel identifies an enrolled machine-owner connection, not an authenticated individual Web conversation.
