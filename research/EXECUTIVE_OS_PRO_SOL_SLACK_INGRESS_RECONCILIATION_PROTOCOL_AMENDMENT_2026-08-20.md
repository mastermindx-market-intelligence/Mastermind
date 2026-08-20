# Executive OS Pro Sol Slack ingress — reconciliation protocol amendment

**Date:** 2026-08-20  
**Linear:** `MAS-48`  
**Status:** records-only architecture amendment.  
**Precedence:** highest for the dedicated CEO-ingress local protocol; where this conflicts with earlier “one operation only” wording, this file governs.

## 0. Finding

A dedicated ingress that exposes only high-level submission is secure but incomplete for exactly-once operational behavior.

After a local submission, the Slack daemon can observe an ambiguous transport outcome:

```text
CEO request -> Executive control process commits Job
            -> AF_UNIX reply is lost / daemon connection dies
            -> current Mastermind or Macro grounding later moves
```

Blind re-submit is forbidden. Reconstructing the canonical intent against newer grounding would conflict, and the Slack daemon is deliberately denied the generic operator socket and direct Executive SQLite reads. Therefore it needs one narrowly bounded readback primitive to answer one question:

> Does this Slack-namespace canonical CEO intent already exist, and if so what canonical receipt did Executive OS commit?

## 1. Ruling: two closed schemas, no generic command surface

The dedicated `CeoIngress` listener accepts exactly two versioned request schemas:

### `mastermind.executive_ceo_ingress_submit.v1`

Purpose: submit one high-level CEO request.

Exact conceptual payload:

```json
{
  "schema": "mastermind.executive_ceo_ingress_submit.v1",
  "request_id": "bounded transport correlation id",
  "observed_grounding": {
    "mastermind_sha": "<40 lowercase hex>",
    "macro_sha": "<40 lowercase hex>",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
  },
  "request": {
    "operation_key": "...",
    "objective": "...",
    "department": "...",
    "priority": 0,
    "execution_profile": "research_only"
  }
}
```

`request` may carry only the already-frozen optional high-level fields. Canonical intent id, actor, raw authorities, argv, grounding, branch and worktree remain server-derived.

### `mastermind.executive_ceo_ingress_status.v1`

Purpose: read back one previously derived **Slack-namespace** canonical CEO intent.

Exact conceptual payload:

```json
{
  "schema": "mastermind.executive_ceo_ingress_status.v1",
  "request_id": "bounded transport correlation id",
  "intent_id": "slack-<32 lowercase hex>"
}
```

The status handler delegates only to existing canonical CEO-intent resolution/readback. It creates no state and cannot inspect arbitrary Job ids, MCP intent ids, operator state, workers, backups or other Executive objects.

## 2. Structural security law

There is **no caller-supplied generic `command` field** on the CEO-ingress wire.

The listener dispatches only by exact versioned schema identity to two private handlers. Unknown schema => refusal before any Executive operation.

The `status` schema additionally requires the exact Slack intent namespace/pattern. It cannot be used to query existing MCP `mcp-*` intent identities or arbitrary caller-chosen CEO-intent ids.

The ingress path remains structurally unable to reach:

- generic `_dispatch_request(...)`;
- raw `submit-ceo-intent`;
- status/health/jobs/job/attempt operator APIs;
- dispatch/cancel/requeue;
- worker registration/disable or provider controls;
- backup/restore/retention;
- canary/service-control operations;
- future generic commands.

A future Executive command is unreachable by default because adding it to the operator dispatcher does not add an ingress schema/handler.

## 3. Reconciliation law

The Slack daemon's modifying workflow is:

1. derive the deterministic Slack intent id from Slack namespace + `operation_key`;
2. call dedicated ingress **status** first when recovering history, retrying after an ambiguous local response, or repairing a missing user-visible ACK;
3. if status returns a canonical receipt, that durable receipt is authoritative and no submit occurs;
4. if status returns typed `not_found`, evaluate the source request's `observed_grounding` against trusted current grounding through **submit**;
5. if observed grounding is stale/mismatched, create zero Job and require re-evaluation/new operation key;
6. if submit commits but its response is ambiguous, return to step 2 rather than blindly re-submitting.

For a live first delivery where there is no ambiguity, implementation may go directly to submit after deriving the intent id, because the existing CEO-intent command-id/fingerprint law already makes exact duplicate delivery idempotent. PR-B may still prefer status-first for one uniform path; either is acceptable if tests prove the same semantics.

## 4. Status response law

Success returns the existing canonical `mastermind.ceo_intent_receipt.v1` content, bounded inside the ingress response envelope. It does not invent a second receipt schema for durable state.

Typed outcomes are limited to:

- `found` + canonical receipt;
- `not_found`;
- malformed/unsupported Slack intent id;
- backend unavailable/internal bounded failure.

No arbitrary result/job payload is exposed by this status call. Full Job inspection remains with the existing read-only MCP used by Sol.

## 5. PR-A acceptance additions

PR-A must prove:

1. the ingress wire has no generic `command` key in either accepted schema;
2. submit and status are the exact only ingress schemas;
3. status accepts only `slack-<32hex>` ids;
4. status of an existing Slack intent returns the canonical CEO-intent receipt and changes zero runtime bytes/state;
5. status of a missing Slack intent is typed `not_found` and changes zero state;
6. MCP `mcp-*`, random CEO intent ids, Job ids and malformed ids are refused by ingress status;
7. ambiguous submit-after-commit can be recovered by status without creating a second Job;
8. current grounding may move after commit and status still returns the existing durable receipt;
9. if no durable intent exists and observed grounding moved, submit refuses and creates zero Job;
10. neither ingress handler calls generic `_dispatch_request` or exposes operator commands;
11. existing Operator listener behavior remains unchanged.

## 6. No-widen boundary

This amendment does not authorize:

- a third ingress action;
- arbitrary read access from the Slack daemon;
- direct SQLite reads;
- a generic command allowlist on the network-facing wire;
- a Slack lifecycle/status database;
- widening canonical CEO-intent provenance;
- worker execution, Wake, Agent OS mutation, Linear completion or GitHub mutation.

The dedicated ingress remains a very small adapter into existing CEO-intent authority: **one bounded submit + its necessary bounded canonical readback**.
