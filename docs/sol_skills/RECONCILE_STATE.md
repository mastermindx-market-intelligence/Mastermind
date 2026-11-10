---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: reconcile_state
---

# RECONCILE STATE — Resolve Disagreement Without Creating Another Truth Store

Use when canonical/projection layers disagree, state is stale, transport reconnects, a modifying
response is ambiguous, an operation duplicates/conflicts, a worker/session may have moved a branch
unexpectedly, or a watcher/dialogue state is ambiguous.

## Mission

Recover the **single canonical fact for each layer**, preserve uncertainty where it genuinely exists,
and repair only the layer that is wrong. Never create a new database/ledger merely to remember that
two existing authorities disagree.

Apply `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` when the disagreement involves whether a
counterpart should still be waiting or whether a watcher was actually stopped.

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

### Dialogue/watcher uncertainty
A worker/COO may still be awaiting Sol, Sol may still be awaiting a worker, or one side claims a
watcher was stopped without proof the local wait/watch path was actually disabled.

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
* whether a dialogue contains an explicit `CONTINUE` or terminal `STOP` edge → validated lawful
  carrier/thread evidence; this does not become lifecycle truth.
* whether a temporary local watcher process/call was actually disabled → the local watcher surface's
  direct shutdown result, never an inferred Slack silence.

Do not “majority vote” among sources. Canonical ownership is conceptual, not numeric.

## Step 3 — Freeze identities before repair

Record exact identifiers relevant to the disagreement:

* repo + commit/PR/branch;
* `WS:<KEY>` / DEC / DSC / handoff;
* Linear `MAS-###`;
* Slack workspace/channel/message/thread/sender if transport evidence matters;
* Executive operation key / intent ID / Job ID if runtime evidence matters;
* current child operation key and last validated dialogue edge when watcher state matters;
* state timestamps/hashes/freshness.

A correction made against an ambiguous identity can create a second problem while hiding the first.

## Step 3A — Path-disjoint protected movement

Treat a reviewed candidate and its latest-base compatibility as separate evidence.

When protected master advances after a semantic review:

1. freeze the exact reviewed semantic head and candidate-owned path/blob set;
2. compare protected movement against candidate-owned paths;
3. perform a `material-source comparison` over the governing Skillpack, architecture/authority law,
   imported interfaces, dependency closure and proof contract;
4. obtain `latest-base merge-ref proof` (compatible identity/conflict-free composition) or an
   equivalent immutable integrated-candidate result;
5. read head CI/security, reviews, unresolved threads and capability claims. If native GitHub
   merge queue admission is permitted, required `merge_group` CI runs on its integrated candidate
   **after entry and before merge**; absence of checks on a prequeue synthetic merge ref is not an
   independent hold or a reason to create a new source commit;
6. classify review reuse according to
   `docs/superpowers/specs/2026-09-02-autonomy-release-compatibility-review-reuse.md`.

Do not merge protected master into the carrier merely to make `behind_by=0`.

When candidate-owned blobs and paths remain byte-identical, governing material source is unchanged,
protected movement is path/dependency-disjoint, the current merge ref is conflict-free and no blocker
or stronger capability claim appears, `semantic review may be reused` **before queue admission**.
Required integrated checks still must pass on the native `merge_group` candidate before the protected
merge; do not require nonexistent prequeue merge-ref check runs or falsely claim release readiness.
Refresh the compatibility receipt only; leave the source branch and substantive review intact.

When candidate semantics, governing source, dependency behavior, authority/security/effect/retry or
persistence meaning changes, obtain a new immutable semantic head and full review.

When materiality, integration identity or effect state is unknown, remain blocked. Do not create a
replacement branch/PR, rebase/reset/force, or use an ancestry-only join as a substitute for knowing
whether the candidate is compatible.

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
* status unavailable/ambiguous → retain the original `EFFECT_UNKNOWN`. Non-convergent or irreversible effects stay held. A **distinct, non-force, forward-only Git ref transition** may qualify under Step 4C, without pretending the historical operation was rejected or replaying it.

Never interpret client timeout/cancellation as proof the underlying synchronous mutation stopped.
Never auto-failover to another carrier. Uncertainty is an effect-scoped fence, not a permanent freeze of unrelated source qualification, tests, reviews or other provably independent work.

## Step 4A — Reported terminal, protected result still outstanding

An original process may have a terminal `rc=0` or an outcome digest while the canonical release checkpoint still requires an original privileged administrator-result reconciliation. These are **two distinct facts**, not a contradiction to resolve by choosing the more optimistic report.

1. Bind the existing operation/request ID and its original authorized carrier, observed terminal receipt/digest, canonical checkpoint/revision, result-read authorization and any explicit denial. A historical owner or ChatGPT thread is a provenance pointer, not proof that the old conversation remains alive or is the only person who can ever lead recovery.
2. Where current authority actually permits **consuming the already-requested result on its original carrier**, reconcile through the existing original operation's authorized result/status interface, without issuing a new operation or reader. Require the canonical checkpoint owner to record/read back the resulting disposition.
3. When that exact protected read was explicitly denied or the present session lacks its required authority, do **not** reattempt, invoke an alternate privileged reader, change account/tool/provider, copy credentials, infer release from a message, or restart services to sidestep the hold. Keep the dependent modification held. The current assigned session still owns nonprivileged diagnosis, truthful existing-issue/handoff updates and all provably disjoint authorized work.
4. A genuine human-only gate describes a specific unavailable credential, physical ceremony or nondelegable control, the permitted resolver function and original result identity. "Original author/administrator/chat must act" alone is not a human-control proof. If unrelated ready work exists, this is a held **lane**, not an `EXACT_HUMAN_GATE` finalization of the entire mission.
5. If successor authority cannot presently be proven, record the missing **capability**, not a new owner registry or invented lease transfer. Await the lawful existing installer/runtime/credential decision while retaining the original operation and no-duplicate-effect invariants.

The active turn and its stopping criteria remain owned by `ACTIVE_EXECUTION.md`; this section adds no retry or modification authority.

## Step 4B — Owner-gate triage and takeover discipline

**Responsibility survives a chat; a chat does not own work forever.** Separate role, receiver and lease. Inspect fresh live claim, source-writer custody and pending effects once through their owners; unknown is not expired. Old authors/titles/chats are not liveness. Preserve live/uncertain modifiers; actual lease replacement needs existing CAS/fencing and successor admission. With assignment and no displaced writer/effect, act without a ghost ACK. The active assigned session owns the next recovery action: incumbent reconciliation, independent work, or exact unavailable recovery capability and reachable resolver. This does not transfer STARTed work.

### Prove an owner gate before using it to stop

A factual/source owner is a **place to retrieve evidence or perform an effect**, not
a permanent human/session staffing assignment. For an assigned continuing
mission, run this bounded **owner-gate triage** once before telling the Chairman
that another session, reviewer or team must act:

1. **Name the exact blocked action** and its target/operation/PR/head. Distinguish
   a past assistant's "owner must act" claim from an actual tool receipt, native
   rule, live writer/lease, permission refusal or unreconciled effect.
2. **Check effective execution/custody**: current assignment, exposed action/tool,
   source writer, original carrier/effect, and genuine remaining review/release
   rules. No live competing writer/effect and a permitted action means the
   **current session executes now**, even if the previous chat is archived.
3. **Requested GitHub reviewer is not mandatory approval.** Check actual
   branch protection, CODEOWNERS, active rulesets and binding explicit holds
   at the current head. A 403/unknown read does not prove approval is required
   *or* waived. Preserve real non-author approvals and no-self-merge.
4. **Disabled or protected runtime is an action gate, not a ghost owner.**
   A disabled Control service plus an unresolved protected administrator result
   cannot be restarted merely to bypass the hold. Keep the original operation
   intact, inspect its lawful readback once where permitted, and advance
   genuinely disjoint work. Do not obtain the same denied effect via another
   account, reader or carrier.
5. **Exit with an executable action, not a department.** If a real human-only
   credential, physical ceremony, admin permission or mandatory non-author
   release control is demonstrated, identify exactly that control and an
   addressable way to obtain it. Mark only the dependent lane held; do not
   claim whole-mission `EXACT_HUMAN_GATE` while another safe phase remains.

This is a diagnostic ordering inside existing ownership and Step 8 rules.
It creates no gate state, approval, account, queue, lease, retry path or release
permission. Do not reopen an already-denied protected-result operation.

## Step 4C — Safe forward progress after legacy Git-push uncertainty

The original action and its historical `EFFECT_UNKNOWN` remain recorded. **Do
not replay, rehome, force-push, or claim old-call rejection.** A distinct **new
forward-only Git ref operation** may be admitted on the *same original registered
workspace, publisher, branch, and origin* when all of these are proven:

1. Original push process ended/fenced; no active writer, conflicting lease,
   queued publication, safety/permission denial or pending external effect.
2. Exact current remote ref and PR head freshly observed; immutable proposed
   head is a strict descendant of both the remote head and relevant original
   intended commit. Preserve original source; divergence is a HOLD.
3. The **installed** publisher advertises the specific recovery schema,
   validates prior legacy action identity, uses a **new stable action ID** and
   durable receipt, and executes only an atomic **non-force fast-forward** ref
   update. Stale ref, wrong target, protected branch and concurrent non-FF
   advance are refused. No force, force-with-lease or alternate carrier.
4. New result is read back against the exact remote/PR. A lost new callback
   is reconciled by *that* ID, never another push. An old action's historical
   outcome is not reclassified because a new publication succeeded.

**Explicit permission/safety refusal**, irreversibles (trades, payments,
messages, runtime deploys/merges), and uninspectable active processes stay
held. Source/tests/research on disjoint lanes continue. Full qualification,
failure matrix and #9596 references:
`docs/runbooks/uncertain-git-publication-recovery.md`. No source-only policy
grants installation, CI waiver, review, merge or production acceptance.

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

## Step 8 — Dialogue/watcher reconciliation

A watcher is attention/transport only. Do not use watcher state to invent Job/Attempt/Worker status,
completion, retry authority or a next wave.

When dialogue state is uncertain:

1. read the exact lawful carrier/thread and identify the latest valid semantic return/edge;
2. distinguish worker return (`BLOCKED` / `DECISION_REQUEST` / `RESULT`) from Sol adjudication;
3. if a worker return exists with no later explicit Sol `CONTINUE`/`RULING`/`REQUEST_REPAIR`/`STOP`
   edge, treat the dialogue as **awaiting Sol**, not terminal by silence;
4. if a terminal Sol STOP exists, keep the child operation terminal even when watcher shutdown later
   fails;
5. if the local watcher cannot be proven disabled, report `WATCH_STOP_FAILED` (or current accepted
   typed equivalent) rather than claiming clean shutdown;
6. never let a leftover watcher originate a retry, merge, new commission or continuation;
7. any independent next child operation requires a new lawful operation key/carrier/commission and
   fresh reciprocal continuation setup.

If the historical dialogue contract requires one terminal consumption receipt after STOP, absence
of that receipt means transport/dialogue consumption remains unresolved; it does **not** reopen the
terminal child operation or authorize a new wave.

## Step 9 — Stale `SOL_STATE`

Once C1 is live:

* stale state may still be displayed as stale evidence;
* it cannot authorize a new modifying operation;
* do not refresh freshness by copying old Executive values into a new wrapper;
* if Executive state cannot be refreshed, expected state is DEGRADED / `do_not_submit=true`.

## Step 10 — Host/remote grounding disagreement

V1 server grounding remains exact whole-repository SHA according to accepted Executive law.

If remote GitHub advanced beyond the Executive-host grounding:

1. identify the exact host revision from approved state;
2. identify the newer remote revision;
3. compare the **material decision-source artifacts** used for the intended operation—relevant
   architecture/authority/WS/DEC/Skillpack—not arbitrary entire diff volume;
4. material source changed → re-evaluate/refuse until host/current context is reconciled;
5. only unrelated data/render/publication paths moved and material sources are byte-identical → Sol
   may reason against the known host grounding, while the server still applies exact grounding
   equality/TOCTOU rules.

Do not invent a selective server grounding epoch in V1. Use the F0 falsifier before commissioning
that future architecture.

Step 3A is a GitHub release-review optimization only. It does not change Executive Runtime's exact
server grounding or allow a stale host to perform modifying work.

## Step 11 — Linear false-green repair

When Linear says Done/In Progress/etc. but canonical evidence disagrees:

1. determine the capability's declared completion law;
2. determine actual canonical implementation/production state;
3. repair Linear as **projection**;
4. preserve the canonical source unless it is independently wrong;
5. explain what caused the false-green if it can recur (e.g. docs PR linked with merge-is-done).

Never close a production-proof gate because a sibling implementation PR merged.

## Step 12 — Unexpected branch movement

If a branch expected to be empty/behind now contains commits:

* do not reset/force-push/rebase over it;
* inspect commit identity/message/diff;
* search for a PR/worker return;
* classify it as concurrent work, expected builder return or unauthorized drift;
* review it under `REVIEW_RETURN.md` when it is real work.

A branch that is merely behind protected master is not unexpected movement and does not require an
ancestry-only commit. Apply Step 3A.

## Step 13 — Correction destination

Repair the owning/projection layer only:

* Agent OS record stale → Agent OS correction/handoff under lawful owner;
* Linear stale → Linear projection update;
* Slack missing receipt → reconstruct from canonical Executive status, not new lifecycle state;
* dialogue missing explicit edge → post the required edge in the same lawful carrier; do not create
  a replacement operation to make the history look closed;
* watcher shutdown failed → preserve terminal child state, report transport defect and clean up the
  watcher without granting it new authority;
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
Semantic head and current integration proof when GitHub release state moved
Review reuse classification
Dialogue edge / watcher state when applicable
Repair performed or withheld
Whether modification is safe now
Exact next action
```

## K3 pass criteria

A fresh Sol confronted with stale/duplicate/ambiguous/colliding state reaches one canonical answer per
layer, performs zero duplicate modification, performs zero cross-carrier failover, does not create a
new truth store to make reconciliation easier, does not create ancestry-only commits for path-disjoint
protected movement, and never resolves watcher/dialogue ambiguity by treating silence as a terminal
receipt.