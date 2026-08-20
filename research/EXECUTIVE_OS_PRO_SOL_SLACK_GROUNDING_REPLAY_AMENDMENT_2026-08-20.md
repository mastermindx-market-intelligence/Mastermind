# Executive OS Pro Sol Slack ingress — grounding/replay amendment

**Date:** 2026-08-20  
**Linear:** `MAS-48`  
**Precedence:** this amendment governs wherever it is more specific than the parent Pro-Sol Slack ingress architecture or post-freeze reconciliation.  
**Status:** records-only architecture law; no runtime behavior is changed here.

## 0. Finding and ruling

The R2 history-replay design closes the Socket Mode protocol-ACK crash window without introducing a new queue, but it exposes a separate provenance risk:

```text
Sol reads Mastermind=A / Macro=B
    -> posts Slack CEO request
    -> Slack protocol envelope is ACKed
    -> daemon dies before Executive commit
    -> Mastermind and/or Macro moves to A2/B2
    -> history replay finds the old Slack message
```

If replay simply grounds that old request on A2/B2, the resulting canonical CEO intent would falsely claim the decision was made against organizational state Sol never saw.

**Ruling:** every `EXECOS/CEO_REQUEST_V1` message carries a required `observed_grounding` claim copied from the read-only Executive MCP preflight in the same Sol session. The claim does **not** grant authority. Trusted Executive admission compares it with host-observed current grounding before creating any Job.

An old uncommitted request is never silently re-grounded on newer state.

## 1. Session contract

A Sol session that may emit a CEO request MUST begin by reading the existing read-only Executive MCP state. The returned grounding becomes the source for the Slack request's `observed_grounding` object.

The Slack message shape becomes:

```text
EXECOS/CEO_REQUEST_V1
{
  "observed_grounding": {
    "mastermind_sha": "<40 lowercase hex>",
    "macro_sha": "<40 lowercase hex>",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
  },
  "request": {
    "operation_key": "stable-operation-key",
    "objective": "bounded outcome",
    "department": "executive-infrastructure",
    "priority": 0,
    "execution_profile": "research_only"
  }
}
```

`request` carries exactly the previously frozen high-level CEO-request business vocabulary. `observed_grounding` is a separate integrity/provenance claim; it is not part of the capability vocabulary and cannot contain authority, paths, argv, credentials, provider/model selection, branch, worktree, actor, Job id or canonical intent id.

No manual Chairman copy/paste is required: Sol reads the MCP result and composes the Slack action from that same session context.

## 2. Trust law

`observed_grounding` is **caller-claimed observation**, not trusted host truth.

It is admitted only when all of these hold:

1. exact key set and full lowercase SHA syntax validate;
2. boot packet schema is the exact supported schema;
3. the trusted Executive grounding provider independently observes the same Mastermind and Macro identities;
4. trusted grounding is re-read immediately before `ceo_intent.submit_intent(...)` and remains unchanged.

Therefore a compromised Slack user/process cannot select an old/future SHA to gain authority. A disagreement fails closed with zero Job.

The canonical raw `mastermind.ceo_intent.v1` grounding is written from the **trusted provider snapshot after equality is proven**, not by copying the Slack fields blindly.

## 3. Live-delivery behavior

For a new valid structured Slack request:

1. Socket Mode protocol ACK remains immediate and independent of Executive mutation.
2. Slack daemon validates transport + wire shape and forwards `{observed_grounding, request}` through the dedicated CEO-ingress listener.
3. Trusted Executive admission reads current grounding.
4. If claimed != trusted, return `grounding_changed_since_request`, zero Job.
5. Normalize/derive canonical CEO request fields.
6. Re-read trusted grounding immediately before canonical submit.
7. If trusted grounding moved between reads, return existing-style `grounding_changed`, zero Job.
8. Submit through the existing `ceo_intent.submit_intent` seam.
9. Only canonical success/reconciliation may produce the user-visible Executive ACK.

## 4. History-replay behavior

History recovery MUST resolve canonical intent identity/status **before** evaluating current grounding.

For each structured historical message:

1. derive the Slack canonical intent id from the transport namespace + `operation_key` only;
2. query canonical `ceo_intent_status(intent_id)`;
3. if a canonical intent already exists, treat that receipt as authoritative and repair only missing Slack user-visible ACK state; do not re-ground or create another Job;
4. if no canonical intent exists, compare `observed_grounding` from the Slack source message with current trusted grounding;
5. if equal, admission may proceed under the normal double-read TOCTOU fence;
6. if different, mark/refuse `stale_observed_grounding` (or a reviewed equivalent), create no Job, and tell Sol/operator that the request must be re-evaluated against current state and resubmitted under a **new operation key**.

This is conservative by design: a decision that was never canonically accepted does not gain new factual grounding merely because transport recovery occurred later.

## 5. Idempotency interaction

The existing law remains:

- canonical Slack intent id is derived from transport namespace + `operation_key` alone, not payload or grounding;
- same accepted intent id resolves through existing Executive state;
- a changed business payload under the same operation key conflicts/refuses;
- `observed_grounding` is checked before first commit, but after a canonical intent exists the durable receipt wins on replay;
- a stale uncommitted request requires a new operation key after re-evaluation, preventing an old operation identity from being silently repurposed under new company state.

No additional dedupe or grounding table is authorized.

## 6. PR-A implication

PR-A remains Slack-network-free but MUST now model the complete trusted admission seam.

Recommended first-party boundary:

```text
control_plane.ceo_request
    - normalize high-level business request
    - transport-specific intent-id derivation
    - privileged capability / branch / worktree / validation derivation
    - observed-grounding validation/equality law
    - trusted grounding snapshot/recheck interface
    - canonical mastermind.ceo_intent.v1 construction
```

The module MUST NOT discover filesystems, Git repositories, environment variables, sibling paths or vendor roots itself. A trusted grounding provider is injected by host composition.

PR-A fixture proof uses temporary Git-backed identities/provider stubs and proves:

- exact claimed/current grounding succeeds;
- mismatched claimed/current grounding creates zero Job;
- grounding movement between first read and canonical submit creates zero Job;
- canonical envelope grounding comes from trusted snapshot, not untrusted input bytes;
- same operation + same request + canonical prior receipt reconciles even when current grounding later moved;
- public MCP schema/snapshot and MCP-specific ID behavior are unchanged after shared-policy refactor.

Production grounding composition is PR-C scope. The current Executive estate already has an exact-SHA control-owned Mastermind administrative Git checkout. PR-C must separately freeze a fresh Agent-OS-capable Macro root/source and must not use `ceo_boot_packet.resolve_macro_root()`'s environment/sibling/vendor fallback ladder as mutation authority.

## 7. Wire/error amendments

The hard Slack discriminator remains `EXECOS/CEO_REQUEST_V1` and the whole-message 4,500 UTF-8 byte ceiling remains.

New required top-level keys are exactly:

- `observed_grounding`
- `request`

Minimum additional typed errors:

- `grounding_claim_invalid`
- `grounding_changed_since_request`
- `stale_observed_grounding`

Exact externally rendered vocabulary may be consolidated during PR-A review, but all three semantic failure states must remain distinguishable from authority denial, malformed business request and backend outage.

## 8. No-widen boundary

This amendment does NOT authorize:

- model-supplied authority or execution fields;
- trusting claimed SHAs without independent host verification;
- changing existing MCP tool schemas merely to add Slack fields;
- adding a grounding database, Slack queue or replay cursor table;
- using stale `vendor/macro` as modifying authority;
- silently re-grounding an uncommitted historical request after company state changed;
- automatic worker execution, Wake, Linear completion or Agent OS mutation.

## 9. Acceptance effect

PR #91 architecture acceptance now requires this amendment together with the parent architecture and R2 reconciliation. PR-A handoff must cite this file with highest precedence for grounding/replay semantics.
