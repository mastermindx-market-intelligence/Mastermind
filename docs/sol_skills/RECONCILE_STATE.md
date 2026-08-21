---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.0
minimum_bootstrap_major: 1
skill: reconcile_state
---

# RECONCILE STATE — Resolve Disagreement Without Creating Another Truth Store

Use when canonical/projection layers disagree, state is stale, transport reconnects, a modifying
response is ambiguous, an operation duplicates/conflicts, or a worker/session may have moved a
branch unexpectedly.

## Mission

Recover the **single canonical fact for each layer**, preserve uncertainty where it genuinely
exists, and repair only the layer that is wrong. Never create a new database/ledger merely to
remember that two existing authorities disagree.

## Step 1 — Classify the disagreement

Common classes:

### Projection disagreement
Linear/Slack/generated view differs from Agent OS/GitHub/Executive canonical state.

### Organizational disagreement
Handoff/WS next action differs from newer DEC/DNR/accepted architecture or later proof.

### Implementation disagreement
Branch/PR/default branch differs from the expected pickup/merge state.

### Runtime disagreement
Slack receipt/client result differs from Executive canonical intent/Job state.

### Grounding disagreement
Executive-host grounding differs from newer remote repository state.

### Transport uncertainty
Request may have committed but reply/receipt was lost.

### Duplicate/conflict
Same stable operation identity reappears with same or changed semantic payload.

Name the class before deciding the repair.

## Step 2 — Identify the owner of the disputed fact

Examples:

* Job status → Executive OS, never Slack/Linear.
* current merged code → GitHub default branch.
* workstream decision → current Agent OS decision/source law.
* portfolio status → Linear only as the projection being compared.
* message delivery → Slack.
* whether runtime actually saw/claimed work → canonical runtime/session evidence, not delivery.

Do not “majority vote” among sources. Canonical ownership is conceptual, not numeric.

## Step 3 — Freeze identities before repair

Record exact identifiers relevant to the disagreement:

* repo + commit/PR/branch;
* `WS:<KEY>` / DEC / DSC / handoff;
* Linear `MAS-###`;
* Slack workspace/channel/message/thread/sender if transport evidence matters;
* Executive operation key / intent ID / Job ID if runtime evidence matters;
* state timestamps/hashes/freshness.

A correction made against an ambiguous identity can create a second problem while hiding the first.

## Step 4 — Ambiguous modifying outcome

If a modifying operation may have begun but the client lost the response:

```text
classify EFFECT_UNKNOWN
→ keep the same carrier binding
→ derive/reuse the same stable intent identity
→ query the canonical status path
```

Then:

* canonical accepted receipt → reconcile/report it; no resubmit;
* canonical conflict → report conflict; no new operation under the same key;
* true canonical `not_found` → re-read current state/grounding before deciding whether the same
  operation may be resubmitted through the same carrier;
* status unavailable/ambiguous → remain uncertain and fail closed.

Never interpret client timeout/cancellation as proof the underlying synchronous mutation stopped.
Never auto-failover to another carrier.

## Step 5 — Duplicate/conflict semantics

A stable operation key identifies one logical operation.

* same key + same canonical fingerprint/payload → same operation / duplicate reconciliation;
* same key + changed normalized payload → conflict/refusal, not a second Job;
* changed work → new explicit operation key.

Slack message/event IDs are transport evidence, not canonical operation identity.

## Step 6 — Slack edit/delete semantics

Only the original top-level eligible message-create event can originate a command candidate.

* edit/delete before canonical submit and detected by source reread → refuse uncommitted candidate;
* edit/delete after canonical submit begins → cannot cancel the mutation; reconcile Executive status;
* thread reply/edit/delete events never originate new work.

## Step 7 — Reconnect/restart semantics

When B2 is production-proven, a reconnected Relay does not become write-ready merely because the
WebSocket is connected.

Expected conceptual sequence:

```text
CONNECTED
→ RECONCILING
→ bounded history complete
→ READY
```

If the accepted bridge epoch cannot be fully traversed within the reviewed bounds, remain
`RECONCILIATION_INCOMPLETE`; do not skip old work or introduce a hidden replay cursor DB.

## Step 8 — Stale `SOL_STATE`

Once C1 is live:

* stale state may still be displayed as stale evidence;
* it cannot authorize a new modifying operation;
* do not refresh freshness by copying old Executive values into a new wrapper;
* if Executive state cannot be refreshed, expected state is DEGRADED / `do_not_submit=true`.

## Step 9 — Host/remote grounding disagreement

V1 server grounding remains exact whole-repository SHA according to accepted Executive law.

If remote GitHub advanced beyond the Executive-host grounding:

1. identify the exact host revision from approved state;
2. identify the newer remote revision;
3. compare the **material decision-source artifacts** used for the intended operation—relevant
   architecture/authority/WS/DEC/Skillpack—not arbitrary entire diff volume;
4. material source changed → re-evaluate/refuse until host/current context is reconciled;
5. only unrelated data/render/publication paths moved and material sources are byte-identical →
   Sol may reason against the known host grounding, while the server still applies exact grounding
   equality/TOCTOU rules.

Do not invent a selective server grounding epoch in V1. Use the F0 falsifier before commissioning
that future architecture.

## Step 10 — Linear false-green repair

When Linear says Done/In Progress/etc. but canonical evidence disagrees:

1. determine the capability's declared completion law;
2. determine actual canonical implementation/production state;
3. repair Linear as **projection**;
4. preserve the canonical source unless it is independently wrong;
5. explain what caused the false-green if it can recur (e.g. docs PR linked with merge-is-done).

Never close a production-proof gate because a sibling implementation PR merged.

## Step 11 — Unexpected branch movement

If a branch expected to be empty/behind now contains commits:

* do not reset/force-push/rebase over it;
* inspect commit identity/message/diff;
* search for a PR/worker return;
* classify it as concurrent work, expected builder return or unauthorized drift;
* review it under `REVIEW_RETURN.md` when it is real work.

## Step 12 — Correction destination

Repair the owning/projection layer only:

* Agent OS record stale → Agent OS correction/handoff under lawful owner;
* Linear stale → Linear projection update;
* Slack missing receipt → reconstruct from canonical Executive status, not new lifecycle state;
* GitHub branch/PR issue → GitHub bounded repair;
* runtime canonical defect → dedicated Executive repair under its architecture.

After a material cross-session reconciliation, use `CLOSEOUT.md` so the next session can recover it.

## Reconciliation output

```text
Disagreement class
Canonical owner
Exact identities/revisions
What is known
What is uncertain
Which layer is wrong/stale
Repair performed or withheld
Whether modification is safe now
Exact next action
```

## K3 pass criteria

A fresh Sol confronted with stale/duplicate/ambiguous/colliding state reaches one canonical
answer per layer, performs zero duplicate modification, performs zero cross-carrier failover, and
does not create a new truth store to make reconciliation easier.
