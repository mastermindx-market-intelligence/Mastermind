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

## ChatGPT web-account identity versus the rotating Codex slot

The company may expose **one rotating Codex OAuth slot** at a time. That slot can currently resolve
to ChatGPT1 and later rotate to ChatGPT2 or ChatGPT3 according to whichever account OAuth is active.
It **does not identify or authorize all three ChatGPT web accounts** and cannot stand in for their
three separate native Tasks/Automations stores.

For watcher hardening, audit each exact web account's native Tasks/Automations store through that
account's signed-in ChatGPT web/app profile. Codex availability is not a watcher-store prerequisite.
Do not create or demand three simultaneous Codex CTO sessions. Do not infer account identity from the
currently active Codex OAuth, and do not reassign the rotating Codex slot merely to inspect a web
account's native tasks.

A ChatGPT web-account audit may use an ordinary exact Sol reasoning chat in that account. If the web
account/profile or native Tasks surface cannot be proven, return the typed account/surface blocker
with `effect=NONE`; do not substitute whichever Codex account is currently active.

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
surface exposes them. Wrap each item with an audit classification so ordinary reminders and unrelated
scheduled work are not misrepresented as Sol watcher defects.

The JSON input shape is:

```json
{
  "tasks": [
    {
      "id": "native-watcher-id",
      "title": "Human-readable title",
      "is_enabled": true,
      "audit_kind": "SOL_WATCHER",
      "prompt": "Full current prompt text"
    },
    {
      "id": "ordinary-reminder-id",
      "title": "Ordinary reminder",
      "is_enabled": true,
      "audit_kind": "NON_WATCHER",
      "prompt": "Unrelated task text"
    }
  ]
}
```

The native task ID must be present and unique. Do not invent a replacement ID when the native
surface omits one, and do not collapse two returned records with the same ID. Duplicate native task
IDs are an export/identity ambiguity and fail the complete account audit even when both entries are
disabled.

The enabled state must be a JSON boolean (`true` or `false`). Strings such as `"false"`, numeric
values, a missing field, or conflicting `is_enabled` and `enabled` fields fail closed; the validator
must not coerce them with language truthiness.

`SOL_WATCHER` is the default when `audit_kind` is omitted for backward compatibility. Use
`NON_WATCHER` only after directly verifying that the task is not a Sol/CEO/worker continuation,
program, parent, triage or account-hardening watcher. Unknown classifications fail closed.

Do not include credentials, cookies, account tokens, private provider session payloads or unrelated
chat transcripts. The export is an ephemeral audit input, not durable organizational truth.

Record the export time in UTC. If the native task surface cannot export JSON, transcribe only the
five fields above into a local temporary file and preserve the direct native task read as the source
receipt.

## Step 2 — Classify every enabled Sol watcher

Assign exactly one role from the current Skillpack:

- `ACTION_AUTHORITATIVE` — exact currently resolved Sol action target for one child/turn.
- `OBSERVER_ONLY` — sister Sol/account/surface may read but cannot modify the child.
- `PARENT_ORCHESTRATOR` — program-level loop reacts only to parent transitions and never races a
  dedicated child watcher.
- `TRIAGE_ONLY` — estate audit detects unconsumed returns and reconciles/reports without electing a
  child owner.

`ACTION_AUTHORITATIVE` requires one exact Slack carrier:

```text
CARRIER: slack:<channel-id>/<parent-message-ts>
```

The other three roles may use either one exact Slack carrier or a closed aggregate scope:

```text
CARRIER: aggregate:<stable-scope-id>
```

An aggregate scope is only a bounded read/oversight label. It never makes the task authoritative for
every child it can see. A parent or triage task that discovers an unconsumed child return must route
or reconcile the attention defect; the exact child action surface acts only after current action-
target proof or canonical transfer.

If current canonical evidence cannot resolve whether a watcher is action-authoritative, classify it
`OBSERVER_ONLY` or hold it disabled until canonical action-target transfer is proven. Do not upgrade
an ambiguous watcher merely because the account created the task historically.

## Step 3 — Run the deterministic audit

```bash
python3 scripts/audit_sol_watchers.py tasks.json > watcher-audit.json
status=$?
```

Exit codes:

- `0` — every enabled `SOL_WATCHER` task conforms and the export identity/classification envelope is valid;
- `1` — at least one watcher or export entry has a contract finding;
- `2` — malformed/unreadable top-level audit input.

The report summary separates `invalid_enabled_tasks`, `invalid_classification_tasks`, and
`invalid_export_tasks`, and lists `duplicate_task_ids`. An audit is not green when wrapper identity or
boolean typing is ambiguous merely because no enabled prompt was evaluated.

Enabled `NON_WATCHER` entries remain visible in the report but are excluded from watcher-conformance
counts. The validator is intentionally unable to inspect whether a native task really fired, whether
a scheduled surface can use Slack, or whether a Sol edge committed. Those remain direct runtime and
transport facts.

## Step 4 — Repair invalid prompts in place

For each invalid enabled watcher:

1. Re-read its exact operation and Slack carrier or closed aggregate scope.
2. Reconcile the latest valid semantic edge and current action-target role.
3. Preserve the existing native watcher ID, schedule, operation key and carrier whenever the task is
   otherwise healthy.
4. Replace or prepend the prompt with the exact `MMX_SOL_WATCHER_V1` header required by its role.
5. Remove positive notification-only instructions that cause an action-authoritative watcher to say
   “Sol action required,” “waiting for Sol,” “await Sol,” “defer to Sol,” “escalate to Sol,” or
   “pause for Sol.” A prohibition such as “do not wait for Sol” is valid and should remain explicit.
6. Add the exact-carrier fresh-read fence, current-Skillpack re-pin, same-carrier/no-blind-retry/no-
   lifecycle-inference laws, and terminal STOP-before-disarm sequence.
7. For every non-authoritative role (`OBSERVER_ONLY`, `PARENT_ORCHESTRATOR`, and `TRIAGE_ONLY`), remove
   positive authority to emit child `CONTINUE`, `RULING`, `REQUEST_REPAIR`, `STOP`, merge/release,
   retry/resubmit/requeue/fail over, or commission/start a successor. Explicit prohibitions remain
   valid and should be preserved.
8. Save the prompt through the native task surface and read it back. A local draft or proposed text
   is not a completed repair.

Disable rather than rewrite only when the task is terminal, duplicates another same-purpose watcher,
references an irreconcilably wrong carrier, or has no lawful current source. Disabling a child source
must not disable an independent aggregate seat/principal watcher resource.

## Step 5 — Re-export and prove account-local convergence

After all native writes:

1. re-export the current account task census;
2. rerun `python3 scripts/audit_sol_watchers.py`;
3. require exit `0` for enabled temporary Sol watchers and the export envelope;
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
