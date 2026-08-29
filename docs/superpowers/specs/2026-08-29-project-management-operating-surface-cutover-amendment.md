# Mastermind-X Project-Management Operating-Surface Cutover Amendment

**Date:** 2026-08-29  
**Owner:** Sol / existing Operating-Surface Convergence + `WS:CHAIRMAN-CONTROL-ROOM`  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / HOLD-FOR-SOL`  
**Incident projection:** Linear `MAS-191`  
**Existing architecture carrier:** Mastermind PR #211  
**Protected procedure re-pin used for this amendment:** `Mastermind@c4c39423f595cfe669961b871405eb2b13ff65c2`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1.

This amendment narrows the already-approved Operating-Surface Convergence architecture in response to the Chairman-observed project-visibility incident. It creates no new workstream, lifecycle, queue, database, identity plane, scheduler, projector, Slack bot, runtime authority, or implementation release.

## 1. Chairman outcome

The Chairman must be able to open **Linear + Chairman Control Room** and answer, without reconstructing Slack history:

1. what material programs/workstreams are active;
2. what selected human-relevant child waves/gates exist under each;
3. which logical role is accountable for the next turn;
4. whether each item is waiting, blocked, returned, terminal, or unknown;
5. what GitHub / Agent OS / Executive evidence supports the displayed claim; and
6. what the exact lawful next action is.

`#agent-dispatch` must not be the place where the Chairman discovers what the company is doing.

## 2. Canonical ownership is unchanged

| Fact | Canonical owner |
|---|---|
| organizational workstream/program/wave/decision/discovery/handoff identity | Agent OS |
| Job / Attempt / Worker / Event lifecycle and CEO-intent admission | Executive OS |
| implementation, branch, PR, CI, merge and proof | GitHub |
| provider/account/host capacity evidence | existing Shared AI Provider Control / Capacity Fabric |
| human project/portfolio navigation and selected collaboration projection | Linear |
| dialogue, delivery, ACK/START/RESULT prose and hot-state transport | Slack / Agent Relay |
| composed turn-owner / attention / current-state view | Control Room / Executive Steward over existing owners |

Linear `In Progress` never proves an Executive Attempt is running. Slack `ACK`, `START` or `RESULT` never substitutes for canonical runtime or GitHub proof. A project-management improvement must not make Linear or Slack a second lifecycle store.

## 3. Selected human projection law

Not every Executive Job, Attempt, provider event, Slack protocol message, PR or subagent action deserves a Linear issue.

A **selected human-relevant work object** is one of:

- a bounded CEO/COO wave that needs durable human navigation;
- one independently useful deliverable;
- one production-proof / acceptance gate;
- one Chairman/admin action that can block a material program; or
- one explicit reconciliation/CEO-attention object whose absence would make material work invisible.

Default mapping:

```text
Agent OS WS:<KEY> / accepted program owner
    -> Linear Project

selected human-relevant wave / gate / deliverable / admin action
    -> Linear Issue under that Project

GitHub carrier(s), Agent OS identity, runtime/attention evidence, Slack dialogue
    -> linked evidence/projection on that issue
```

Runtime Jobs/Attempts and provider-account/session identities remain underneath this surface and are not projected as one Linear issue per runtime object.

## 4. Logical accountability, not provider identity

Human-visible accountability is role/responsibility based:

- `Sol` / CEO;
- `Fable` / COO when a sustained principal responsibility exists;
- `CTO Sol` / bounded technical-staff responsibility where applicable;
- a named governed worker role only when that distinction is useful to a human operator;
- `Chairman/Admin` for explicit human gates.

`Claude4`, `Claude8`, ChatGPT seat numbers, Codex process IDs, hosts and provider realms are runtime/transport evidence. They must not become durable project owners merely because they executed one Attempt.

## 5. Commission-time projection target

The target end-state is **projection before normal human-visible dispatch**, not delayed Slack archaeology.

For a newly admitted selected work object, the projection pipeline must be able to derive or bind before/with dispatch:

- exact organizational parent (`WS:<KEY>` or accepted program owner);
- stable operation/wave identity;
- Linear Project binding;
- stable Linear Issue binding;
- logical accountable role;
- exact canonical source/evidence links;
- current typed gate / blocker when available;
- exact next action or explicit unknown/reconciliation state;
- Slack dialogue carrier if Slack is used.

The Linear issue is a projection of admitted organizational intent and evidence. It does not itself admit an Executive Job.

## 6. Temporary containment while automation is incomplete

Until MAS-65 -> MAS-64 -> MAS-66 -> OSC-C1 / MAS-189 is production-proven:

1. **Preserve started/effect-unknown carriers in place.** Do not migrate an active branch/PR/thread merely to clean Linear.
2. **No new broad Slack-only fanout.** A selected human-relevant object should receive an exact Linear projection before normal dispatch whenever the current connected surface can do so safely.
3. If an urgent selected object cannot be projected, explicitly mark it `UNPROJECTED / RECONCILIATION_REQUIRED`, link it to its canonical parent/carrier, and repair that projection in the same Sol operating cycle where practical.
4. `UNPROJECTED` is a visibility defect, not a new lifecycle state and not permission to duplicate the work.
5. Existing stale Linear objects are repaired from canonical owners; they are never allowed to overwrite Agent OS / Executive OS / GitHub truth.
6. Prefer closing/reconciling existing carriers over creating additional OPEN_PICKUP work while the estate is visibly fragmented.

The temporary Slack containment notice is transport guidance only. This protected amendment is the durable architecture candidate.

## 7. Slack after cutover

Slack remains useful, but its purpose becomes narrow:

- delivery / attention;
- semantic dialogue (`ACK`, `PROGRESS`, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, `RULING`, `CONTINUE`, `STOP`);
- link/pointer to canonical work and evidence;
- exact carrier thread for reciprocal continuation where current law requires it.

The full operator handoff contract still must be recoverable from canonical sources. A compact Slack envelope may point to that canonical packet only when the receiver is proven able to read it. Do not shrink a worker packet merely to make Slack prettier if that would make execution ambiguous.

## 8. Linear issue/update semantics

OSC-C1 must freeze deterministic selection and correction behavior before live issue/comment mutation. At minimum:

- immutable binding to exact organizational work identity; no fuzzy title matching;
- no issue for every Executive Job/Attempt or raw Slack event;
- no automatic `Done` from Slack `RESULT`, GitHub merge, or Linear-native automation unless the selected issue's semantic acceptance condition is actually complete;
- accepted-return comments/status updates are source-attributed projections, not authority;
- remote/manual Linear edits use optimistic re-read / explicit disagreement behavior;
- missing/null/unavailable canonical evidence is shown as unavailable/unknown, never as empty healthy state;
- superseded/rejected/terminal work is corrected without deleting historical evidence required for audit;
- app-actor attribution is preferred for automated projection; provider session identities are never impersonated as human users.

## 9. Control Room responsibility composition

The Control Room / Executive Steward must eventually compose, without another durable store:

```text
program / workstream
selected child issue / gate
logical accountable role
turn_owner
attention_health
organizational state
GitHub carrier/proof state
Executive runtime binding when available
typed wait/blocker
parent_active_no_successor condition
exact next lawful action
source freshness / disagreement
```

This is a read/attention composition over existing owners. It cannot invent a runtime, claim a worker, retry an effect-unknown operation, or treat a missing Slack reply as proof of failure.

## 10. Recovery dependency graph

The visibility cutover continues existing owners in place:

```text
MAS-65 / Macro #6182
  deterministic Agent OS -> Linear portfolio plan
        |
MAS-64
  dedicated Portfolio Projector app actor
        |
MAS-66
  project-only read/diff/apply
        |
OSC-C1 / MAS-189
  selected issue/gate + accepted-return comment/update projection

parallel / joined for full operating truth:
  Session Truth R1
  WP-1 (merged, production-inert contract/service)
  WP-2 company-dialogue MCP
  WP-TW1 deterministic turn classifier
  WP-TW2 -> existing Wake
  Wake native transport (merged; ACK/source-resolution still separate)
  Operator Continuity / Capacity
  OCR-6 Executive Steward / Responsibility Matrix
  Control Room exact product proof
```

No arrow authorizes a downstream wave merely because this amendment exists. Each existing carrier retains its own review and production-proof gate.

## 11. Cutover modes

### CONTAINMENT

- selected new work is not allowed to disappear silently into Slack;
- existing active carriers remain in place;
- stale selected Linear projections are repaired manually from canonical evidence;
- no claim that automation is live.

### SHADOW

- projector/selection logic computes what Projects/Issues/updates should exist;
- no or bounded canary mutation;
- discrepancies are measured against current estate.

### HYBRID

- proven app actor manages approved Linear Project fields and separately promoted selected Issue/update fields;
- humans/agents may collaborate through Linear while canonical owners remain unchanged;
- Slack continues as dialogue transport.

### EXECUTIVE-FIRST

- admitted company work and governed dialogue/attention mechanically produce the required selective projections;
- Chairman does not perform routine projection reconciliation.

### FULL FABRIC

- Control Room + Linear expose complete truthful portfolio/attention state;
- Wake/Dialogue/Steward/Capacity provide the governed continuation loop;
- Chairman performs zero routine Slack archaeology, message shuttling, watcher repair, session hunting or provider-account selection.

Promotion between modes requires current Sol acceptance and real evidence; merged architecture or green CI is not enough.

## 12. Acceptance canaries

The operating-surface project-management cutover is not accepted until all of the following can be demonstrated on real concurrent work:

1. every materially active canonical workstream has a truthful Project projection or an explicit typed projection defect;
2. every currently selected human-relevant CEO/COO wave/gate has exactly one Linear Issue binding under the correct parent;
3. no duplicate issue is created when the same operation is observed again;
4. an already-running Slack carrier receives a projection without moving/restarting the carrier;
5. a GitHub merge that does not complete the issue cannot false-close the Linear issue;
6. a Slack `RESULT` cannot false-close the issue or prove runtime completion;
7. a stale Linear status is corrected from canonical evidence without mutating the canonical owner;
8. a provider-account/session change does not change durable logical accountability;
9. a child STOP with active parent and no successor becomes a visible `needs_sol` / parent-continuation condition through the accepted responsibility composition;
10. Chairman can answer the six outcome questions in Section 1 from Linear + Control Room without reading `#agent-dispatch`.

## 13. Non-goals

This amendment does **not**:

- replace Slack with Linear;
- make Linear canonical runtime or organizational truth;
- create a Slack-to-Linear task bot that infers authority from prose;
- create an issue for every Job, Attempt, PR, Slack message or worker process;
- create another project/work/task database;
- authorize provider/account selection or runtime failover;
- authorize MAS-64, MAS-66, MAS-189, WP-TW2, OCR-6 or any other implementation by itself;
- migrate active effect-unknown work;
- weaken current approval, proof, correction or one-carrier laws.

## 14. Completion boundary

Merge of this amendment would make only the project-management operating-surface ruling durable. It would not make Projector mutation, issue projection, Responsibility Matrix, automatic Wake, provider routing, or FULL FABRIC live.

The product acceptance ruler is intentionally simple:

> **If the Chairman still has to read `#agent-dispatch` to discover what material projects exist, who owns their next turn, what is blocked, or what happens next, Operating-Surface Convergence is not complete.**
