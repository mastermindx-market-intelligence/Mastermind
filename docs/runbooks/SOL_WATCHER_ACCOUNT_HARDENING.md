# Sol Watcher Account Hardening Runbook

## Purpose

Harden temporary Sol Task/Automation/condition-watch prompts on each ChatGPT account without
creating a watcher registry, cross-account task controller, lifecycle plane, action-owner table,
queue, retry path or credential bridge.

This ceremony is **account-local-only mutation**. Each ChatGPT account may inspect and repair only
its own native task store unless a separately accepted host capability explicitly proves broader
authority. A Slack message, GitHub branch, sister-account receipt or apparent browser access does not
grant cross-account task mutation.

The canonical procedure is the current protected `docs/sol_skills/WATCHER_ACTION_LOOP.md`. The audit
CLI is a read-only conformance check:

```bash
python3 scripts/audit_sol_watchers.py tasks.json > watcher-audit.json
```

A passing prompt audit does not prove runtime consumption, scheduled execution, Slack read/write,
exact-session Wake, target acknowledgement or source resolution.

## Preconditions

Before changing any watcher on an account:

1. Load current protected `docs/sol_skills/INDEX.md` from
   `mastermindx-market-intelligence/Mastermind` and record the exact protected Skillpack SHA.
2. Load same-SHA `WATCHER_ACTION_LOOP.md`, `RECONCILE_STATE.md`, and
   `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`.
3. Read the account's native task list directly through that account's current Task/Automation
   surface.
4. Do not infer an action-authoritative Sol target from account number, newest tab, latest response,
   apparent health, remaining quota or timestamp order. **Never elect by recency.**
5. Preserve one operation/carrier binding. A prompt repair does not create a new logical child,
   retry a provider effect or transfer action authority.

## Step 1 — Export the account-local task census

Export every native task visible to the current account, including disabled tasks where the native
surface exposes them. The minimum JSON input shape is:

```json
{
  "tasks": [
    {
      "id": "native-task-id",
      "title": "Human-readable title",
      "is_enabled": true,
      "prompt": "Full current prompt text"
    }
  ]
}
```

Do not include credentials, cookies, account tokens, private provider session payloads or unrelated
chat transcripts. The export is an ephemeral audit input, not durable organizational truth.

Record the export time in UTC. If the native task surface cannot export JSON, transcribe only the
four fields above into a local temporary file and preserve the direct native task read as the source
receipt.

## Step 2 — Classify every enabled watcher

Assign exactly one role from the current Skillpack:

- `ACTION_AUTHORITATIVE` — exact currently resolved Sol action target for one child/turn.
- `OBSERVER_ONLY` — sister Sol/account/surface may read but cannot modify the child.
- `PARENT_ORCHESTRATOR` — program-level loop reacts only to parent transitions and never races a
  dedicated child watcher.
- `TRIAGE_ONLY` — estate audit detects unconsumed returns and reconciles/reports without electing a
  child owner.

If current canonical evidence cannot resolve whether a watcher is action-authoritative, classify it
`OBSERVER_ONLY` or hold it disabled until canonical action-target transfer is proven. Do not upgrade
an ambiguous watcher merely because the account created the task historically.

## Step 3 — Run the deterministic audit

```bash
python3 scripts/audit_sol_watchers.py tasks.json > watcher-audit.json
status=$?
```

Exit codes:

- `0` — every enabled task conforms to the structured prompt contract;
- `1` — at least one enabled task has a contract finding;
- `2` — malformed/unreadable audit input.

The validator is intentionally unable to inspect whether a native task really fired, whether a
scheduled surface can use Slack, or whether a Sol edge committed. Those remain direct runtime and
transport facts.

## Step 4 — Repair invalid prompts in place

For each invalid enabled watcher:

1. Re-read its exact operation and Slack carrier.
2. Reconcile the latest valid semantic edge and current action-target role.
3. Preserve the existing native watcher ID, schedule, operation key and carrier whenever the task is
   otherwise healthy.
4. Replace or prepend the prompt with the exact `MMX_SOL_WATCHER_V1` header required by its role.
5. Remove notification-only instructions that cause an action-authoritative watcher to say “Sol
   action required,” “waiting for Sol,” or “stand by for Sol's ruling.”
6. Add the exact-carrier fresh-read fence, current-Skillpack re-pin, same-carrier/no-blind-retry/no-
   lifecycle-inference laws, and terminal STOP-before-disarm sequence.
7. For observer/parent/triage tasks, remove any authority to `CONTINUE`, `RULING`,
   `REQUEST_REPAIR`, `STOP`, merge/release, retry or commission a successor outside the declared
   role.
8. Save the prompt through the native task surface and read it back. A local draft or proposed text
   is not a completed repair.

Disable rather than rewrite only when the task is terminal, duplicates another same-purpose watcher,
references an irreconcilably wrong carrier, or has no lawful current source. Disabling a child source
must not disable an independent aggregate seat/principal watcher resource.

## Step 5 — Re-export and prove account-local convergence

After all native writes:

1. re-export the current account task census;
2. rerun `python3 scripts/audit_sol_watchers.py`;
3. require exit `0` for enabled temporary Sol watchers;
4. compare native watcher IDs and schedules before/after;
5. identify every changed or disabled watcher ID;
6. preserve any unresolved action-authority conflicts rather than forcing them green.

## Required account receipt

Each of the three ChatGPT accounts returns one receipt containing exactly:

```text
ACCOUNT_WATCHER_HARDENING_RECEIPT
account/surface identity: <pseudonymous exact account or approved surface identity>
export time: <UTC timestamp>
protected Skillpack SHA: <40-hex>
active watcher count: <integer>
validator command/result: <command + exit status>
watchers: <for each: id, title, role, operation key, carrier, valid/finding codes>
changed or disabled watcher IDs: <list or []>
unresolved action-authority conflicts: <list or []>
native readback proof: <bounded task-surface receipt>
```

Do not include credentials or raw provider-native handles. Watcher IDs are transport hot state, not
Agent OS lifecycle authority.

## Three-account adverse canary

Run only after all three account receipts are clean.

### Canary A — one action target, two observers

1. Bind one harmless watcher-enabled test child to an exact current Sol action target through the
   accepted responsibility/action-target path.
2. Make the same worker `DECISION_REQUEST` visible to all three Sol accounts.
3. Require **one authoritative action** from the bound account and **two observer accounts** to
   remain read-only.
4. Prove exactly one same-carrier Sol edge, zero competing leaves, zero duplicate Wake, zero duplicate
   Job and zero successor commission.

### Canary B — authoritative account unavailable

1. Make the current action-authoritative account unavailable before it writes a semantic edge.
2. Verify the two observers refuse to take over merely because they are responsive.
3. Perform canonical action-target transfer through the existing owner.
4. Only after transfer, allow the newly resolved account to act.
5. Prove timestamp order, newest tab and newest Slack responder never choose the replacement.

### Canary C — FF/FIF self-deadlock regression

Present a fixture equivalent to:

```text
worker RESULT / REQUEST_CHANGES
worker says it is waiting for Sol
current watcher role = ACTION_AUTHORITATIVE
findings are decidable inside current Chairman-authorized scope
```

The watcher must produce `SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER`. Output equivalent to “Sol action
required” or “waiting for Sol” fails as `NOTIFICATION_ONLY_SELF_DEADLOCK`.

## Completion and rollback

Account hardening is complete only when:

- all three account receipts are present;
- every enabled account-local temporary Sol watcher validates;
- the adverse canary proves one action-authoritative edge and two observers;
- no native task ID unexpectedly multiplied;
- no action-authority conflict was hidden;
- a real no-Chairman continuation canary succeeds.

If a prompt repair makes a task unreadable or changes its operation/carrier identity, restore the
previous prompt on the same native watcher ID where effect is known and safe. If native update effect
is ambiguous, classify it `EFFECT_UNKNOWN`, do not repeat the update on another account, and reconcile
the account-local task surface.

Temporary prompt hardening remains transitional. Retire redundant Class-M watchers only after the
canonical Agent Dialogue -> Wake -> exact RuntimeBinding/current writer -> acknowledgement/source-
resolution path is production-proven for the corresponding responsibility.
