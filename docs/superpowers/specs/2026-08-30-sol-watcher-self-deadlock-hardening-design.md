# Sol Watcher Self-Deadlock Hardening Design

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Approval:** Current live Chairman directive; written-spec review explicitly auto-approved.  
**Authoring procedure basis:** `mastermindx-market-intelligence/Mastermind@fefd774701ea285b466cac2646a584801f4a976a`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1.  
**Current-base reconciliation:** protected `5a7046c46046a2ecf597c849aaab914b4f7cd5e1`; intervening Chat-native Meta-CEO source law is preserved and path-disjoint.  
**Operation:** `sol-watcher-self-deadlock-hardening-20260830-sol-001`

## Outcome

A Sol-owned continuation watcher must never detect an in-scope worker `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, conclude that Sol owes the next decision, and then end by waiting for Sol. The exact action-authoritative Sol watcher either writes the lawful same-carrier Sol edge or returns one typed reason why it cannot. Sister Sol accounts may observe the same return but may not create a competing semantic edge without canonical action-target transfer.

## Incident

The FF/FIF principal returned `RESULT / REQUEST_CHANGES` on Macro PR #6676 and correctly re-armed its exact-thread watcher. The ChatGPT CEO watcher repeatedly recognized that the worker was waiting for Sol but emitted notification-only summaries instead of performing the already-authorized Sol ruling. Both sides therefore waited for the same Sol role, and the program stopped until an interactive Sol turn manually supplied `SOL REQUEST_REPAIR / CONTINUE`.

The protected procedure already required `DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT`. The failure survived because live scheduled watcher prompts were free-form and no deterministic contract rejected notification-only self-deadlock output.

## Architecture

This wave adds a pure, storeless prompt-contract validator and account-local audit CLI. It does not add a watcher daemon, task registry, action-owner table, lifecycle state, queue, retry plane, cursor, database, provider session, or transport.

The contract is embedded in each temporary Sol watcher prompt:

```text
MMX_SOL_WATCHER_V1
WATCHER_ROLE: ACTION_AUTHORITATIVE | OBSERVER_ONLY | PARENT_ORCHESTRATOR | TRIAGE_ONLY
OPERATION_KEY: <stable operation key>
CARRIER: <slack:<channel-id>/<parent-ts> | aggregate:<stable-scope-id>>
LATEST_HANDLED_EDGE: <semantic edge or NONE>
ACTION_REQUIRED_EVENTS: <closed comma-separated set>
ACTION_REQUIRED_OUTCOME: <closed value by role>
SISTER_SOL_POLICY: <closed value by role>
```

The prompt body still carries current procedure, source reconciliation, scope, failure states, and terminal cleanup. The structured header only makes the most dangerous invariants mechanically auditable.

`ACTION_AUTHORITATIVE` always requires one exact Slack carrier. `aggregate:<stable-scope-id>` is available only to `OBSERVER_ONLY`, `PARENT_ORCHESTRATOR`, or `TRIAGE_ONLY`, and identifies a bounded read/oversight scope rather than authority over every child it contains. Aggregate observers must fresh-read each exact child carrier used for a conclusion. An exact child semantic edge still requires the current exact action target and exact lawful carrier.

## Role law

### `ACTION_AUTHORITATIVE`

The exact currently resolved Sol target for the child turn. It must declare:

```text
ACTION_REQUIRED_EVENTS: BLOCKED,DECISION_REQUEST,RESULT
ACTION_REQUIRED_OUTCOME: SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER
SISTER_SOL_POLICY: OBSERVE_ONLY_UNLESS_EXACT_ACTION_TARGET
```

On an action-required event, a positive terminal instruction equivalent to `Sol action required`, `waiting for Sol`, or `stand by for Sol's ruling` is a contract failure. A prohibition or regression sentence such as `do not wait for Sol` is not itself a finding. Valid completion of that watcher turn requires one of:

1. a lawful same-carrier `CONTINUE`, `RULING`, `REQUEST_REPAIR`, `PARK/HOLD`, or terminal `STOP`; or
2. a typed blocker naming the actual boundary, such as `CHAIRMAN_ONLY`, `ATTENTION_OWNER_CONFLICT`, `EFFECT_UNKNOWN`, `CARRIER_UNREADABLE`, `WRITE_UNAVAILABLE`, or `SOURCE_LAW_CONFLICT`.

### `OBSERVER_ONLY`

May read, compare, project, and report. It must not emit child-semantic modification. It declares:

```text
ACTION_REQUIRED_EVENTS: NONE
ACTION_REQUIRED_OUTCOME: OBSERVE_ONLY_NO_MODIFY
SISTER_SOL_POLICY: NEVER_ACT_WITHOUT_CANONICAL_TRANSFER
```

### `PARENT_ORCHESTRATOR`

May act only on parent transitions that are explicitly disjoint from an active child's dedicated action watcher. It declares:

```text
ACTION_REQUIRED_EVENTS: PARENT_TRANSITION
ACTION_REQUIRED_OUTCOME: PARENT_EDGE_ONLY_NO_CHILD_RACE
SISTER_SOL_POLICY: NEVER_ACT_ON_DEDICATED_CHILD_RETURN
```

A parent may use an aggregate scope but cannot answer a dedicated child return.

### `TRIAGE_ONLY`

May identify unconsumed returns and route or reconcile attention. It does not become action-authoritative merely because it discovered the defect. It declares:

```text
ACTION_REQUIRED_EVENTS: UNCONSUMED_RETURN
ACTION_REQUIRED_OUTCOME: RECONCILE_OR_REPORT_NO_DUPLICATE
SISTER_SOL_POLICY: NEVER_ELECT_BY_RECENCY
```

A triage task may use an aggregate scope. The exact child action surface must act or receive canonical transfer before a modifying child edge is written.

## Contract validation

`control_plane.sol_watcher_contract.validate_watcher_prompt()` is deterministic and standard-library only. It verifies:

- discriminator and required fields;
- closed role/outcome/event/policy combinations;
- exact Slack carrier for action authority and closed aggregate scope for non-authoritative roles;
- current-procedure re-pin instruction;
- exact-carrier fresh-read instruction;
- same-carrier/no-blind-retry/no-lifecycle-inference/terminal-STOP laws;
- positive notification-only anti-patterns without false-rejecting explicit prohibitions;
- observer/parent/triage authority widening.

`scripts/audit_sol_watchers.py` accepts an account-local JSON export and emits a machine-readable report. Every wrapper entry declares `audit_kind: SOL_WATCHER | NON_WATCHER`; omission defaults to `SOL_WATCHER` for backward compatibility. Enabled `NON_WATCHER` tasks remain visible but are excluded from watcher-conformance counts. Unknown audit kinds fail closed. The CLI never connects to ChatGPT, Slack, GitHub, Executive OS, or a provider and never mutates a task.

## Three-account deployment

Each ChatGPT account audits only its own native task store. The accounts return receipts containing:

- account/surface identity;
- export time;
- current protected Skillpack SHA;
- active watcher count;
- each watcher ID/title/role/operation/carrier;
- validator result and finding codes;
- exact watcher IDs changed or disabled;
- unresolved action-authority conflicts.

A sister account receipt does not grant that account authority over another account's children. Cross-account canaries require one canonical action target and observer-only behavior from the other two surfaces.

The rollout uses two phases: read-only account preflight while the source carrier is DRAFT, then in-place native task mutation only after exact-head source release and a fresh same-carrier Sol continuation. Slack delivery alone is not native task consumption; exact account-session placement or a typed unavailable result is required.

## Runtime continuation program

This immediate wave is transitional hardening, not the final event-driven solution. The permanent path remains the accepted owners:

```text
Agent Dialogue turn classifier
-> persisted Wake obligation/carrier
-> trusted current RuntimeBinding and exact action target
-> existing current provider writer/generation
-> exact reasoning-session Wake
-> target acknowledgement
-> source resolution
```

Existing W3A/W3C/MAS-229/AD-SOL1 carriers must be continued rather than duplicated. Temporary Class-M watcher prompts are removed only after the corresponding event-driven path is production-proven.

## Acceptance

1. The FF/FIF notification-only prompt is rejected with `NOTIFICATION_ONLY_SELF_DEADLOCK`.
2. A valid action-authoritative watcher passes, including explicit `do not wait for Sol` law.
3. A sister-Sol observer that can modify the child is rejected.
4. Action authority refuses an aggregate carrier; bounded observer/parent/triage aggregate scopes pass.
5. Malformed/missing carrier, operation, role, or handled-edge identity fails closed.
6. The CLI produces stable JSON and nonzero status for invalid enabled watchers while excluding declared non-watchers from watcher counts.
7. The Skillpack explicitly requires the structured contract for new/materially updated temporary Sol watchers and names notification-only self-deadlock as a K3 failure.
8. Focused tests and repository CI are green on the exact final head.
9. All three account-local preflight and mutation receipts plus the one-authoritative/two-observer canary exist before `PROVEN_LIVE` is claimed.

## Non-goals

No automatic task-store mutation, no cross-account login or credential handling, no account selection by model, no Executive lifecycle mutation, no Slack lifecycle authority, no provider wake, no new action-owner store, no W3C production activation, no replacement of existing W3A/W3B/AD-SOL1 carriers, and no claim that a passing prompt audit proves runtime consumption.
