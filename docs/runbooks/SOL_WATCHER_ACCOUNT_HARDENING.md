# Sol Watcher Account Hardening Runbook

## Purpose

Harden temporary Sol Tasks/Automations on each ChatGPT account without creating a watcher registry, cross-account task controller, lifecycle plane, action-owner table, queue, retry path, or credential bridge.

This ceremony is **account-local-only mutation**. Each ChatGPT account may inspect and repair only its own native task store unless a separately accepted host capability proves broader authority. Slack, GitHub, a sister-account receipt, or apparent browser access does not grant cross-account task mutation.

The current protected `docs/sol_skills/WATCHER_ACTION_LOOP.md` is canonical. The audit is read-only:

```bash
python3 -m scripts.audit_sol_watchers tasks.json > watcher-audit.json
```

A passing prompt audit does not prove runtime consumption, scheduled execution, Slack read/write, exact-session Wake, target acknowledgement, or source resolution.

## ChatGPT web-account identity versus the rotating Codex slot

The company may expose **one rotating Codex OAuth slot** at a time. That slot can resolve to ChatGPT1, ChatGPT2, or ChatGPT3 as OAuth rotates. It **does not identify or authorize all three ChatGPT web accounts** and cannot stand in for their three native Tasks/Automations stores.

Audit each exact web account's native Tasks/Automations store through that account's signed-in profile. Codex availability is not a watcher-store prerequisite. Do not demand three simultaneous Codex sessions, infer web-account identity from the active OAuth slot, or rotate the slot merely to inspect a native task store.

If an account profile or native Tasks/Automations surface cannot be proven, return the typed account/surface blocker with `effect=NONE`; do not substitute another account.

## Preconditions

Before changing any watcher:

1. Load current protected `docs/sol_skills/INDEX.md` and record the exact protected Skillpack SHA.
2. Load same-SHA `WATCHER_ACTION_LOOP.md`, `RECONCILE_STATE.md`, and `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`.
3. Read the exact account-local native task list and task IDs.
4. Reconcile the current action target. Never infer authority from account number, newest tab, latest response, remaining quota, or timestamp. The rule is **never elect by recency**.
5. Preserve the existing operation/carrier. Prompt hardening does not create a child, retry an effect, or transfer authority.

## Step 1 — Export the account-local task census

Export enabled and disabled tasks when available. Classify ordinary reminders separately:

```json
{
  "tasks": [
    {
      "id": "native-watcher-id",
      "title": "Sol continuation watcher",
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

The native task ID must be present and unique. Trim `id` and `task_id` independently before alias equality and duplicate census. Never invent a missing identity or collapse duplicate records. Duplicate native task IDs fail the complete audit even when disabled.

The enabled state must be a JSON boolean. Missing, string, numeric, or conflicting `is_enabled`/`enabled` values fail closed. Unknown `audit_kind` values fail closed. `SOL_WATCHER` remains the backward-compatible default only when classification is omitted.

Do not export credentials, cookies, account tokens, provider payloads, raw session handles, or unrelated transcripts. The census is ephemeral audit input, not organizational truth.

## Step 2 — Classify enabled Sol watchers

Assign exactly one closed role:

- `ACTION_AUTHORITATIVE` — exact current Sol action target for one child turn.
- `OBSERVER_ONLY` — sister account/surface may read but cannot modify the child.
- `PARENT_ORCHESTRATOR` — acts only on parent transitions and never races a child watcher.
- `TRIAGE_ONLY` — detects and reconciles/reports unconsumed returns without becoming owner.

ACTION_AUTHORITATIVE requires one exact Slack carrier:

```text
CARRIER: slack:<channel-id>/<parent-message-ts>
```

The other roles may use one exact Slack carrier or `aggregate:<stable-scope-id>`. An aggregate is a bounded read scope, never child authority. If action ownership is ambiguous, keep the watcher disabled or classify it non-authoritative until canonical action-target transfer is proven.

## Step 3 — Audit the current export

```bash
python3 -m scripts.audit_sol_watchers tasks.json > watcher-audit.json
status=$?
```

Exit codes:

- `0` — enabled `SOL_WATCHER` tasks conform and the export wrapper is valid;
- `1` — at least one prompt or wrapper finding;
- `2` — malformed or unreadable top-level input.

The report separates `invalid_enabled_tasks`, `invalid_classification_tasks`, `invalid_export_tasks`, and `duplicate_task_ids`. Enabled `NON_WATCHER` entries remain visible but are excluded from watcher-conformance counts.

## Step 4 — Render and replace invalid prompts

Do not patch prose. Do not prepend a header. Do not add another prohibition synonym. The only lawful mutation is to replace the complete native task prompt with renderer output.

For each invalid enabled watcher:

1. Re-read the exact native task ID, schedule, operation, carrier, latest handled edge, and current role.
2. Call the repository-owned pure renderer:

   ```python
   render_watcher_prompt(
       role=<closed role>,
       operation_key=<existing operation>,
       carrier=<existing exact carrier>,
       latest_handled_edge=<current edge or NONE>,
   )
   ```

3. Confirm the output begins with `MMX_SOL_WATCHER_V1`, contains the exact role-derived seven headers, one blank line, and exact `MMX_SOL_WATCHER_BODY_V1` body.
4. Replace the complete native task prompt on the same task ID. Preserve schedule, operation, carrier, and enabled state unless a separate terminal/duplicate ruling requires disabling.
5. Read the task back immediately. Normalize only CRLF/lone-CR to LF and remove terminal newline characters, then compare byte-for-byte with renderer output.
6. Any other difference—including BOM, spaces, tabs, header/body reorder, extra blank lines, comments, Markdown, examples, or appended prose—is `CANONICAL_PROMPT_MISMATCH`.
7. If write response is lost or readback cannot establish the effect, classify `EFFECT_UNKNOWN`. Do not repeat the modification on another account and do not cross-account retry or fail over.

Natural-language polarity is not a validity boundary. Renderer identity replaces synonym scanning. A non-authoritative watcher cannot gain child authority because there is no free-form body channel.

Disable instead of replacing only when the task is terminal, duplicates another same-purpose watcher, has an irreconcilably wrong carrier, or lacks lawful current source. Disabling one child watcher must not disable a separate aggregate seat/principal watcher.

## Step 5 — Re-export and prove convergence

After account-local writes:

1. re-export the account task census;
2. rerun `python3 -m scripts.audit_sol_watchers`;
3. require exit `0`;
4. compare native IDs, schedules, roles, carriers, and enabled states before/after;
5. list changed or disabled watcher IDs;
6. preserve unresolved action-authority conflicts instead of forcing a green report.

## Required account receipt

Each account returns:

```text
ACCOUNT_WATCHER_HARDENING_RECEIPT
account/surface identity: <pseudonymous exact identity>
export time: <UTC timestamp>
protected Skillpack SHA: <40-hex>
active watcher count: <integer>
validator command/result: <module command + exit status>
watchers: <id, title, role, operation key, carrier, valid/finding codes>
changed or disabled watcher IDs: <list or []>
unresolved action-authority conflicts: <list or []>
native readback proof: <bounded task-surface receipt + canonical prompt digest>
```

Do not include secrets or raw native handles. Watcher IDs are transport hot state, not Executive or Agent OS lifecycle authority.

## Three-account adverse canary

Run only after all three account receipts are clean.

### Canary A — one authoritative action, two observers

1. Bind one harmless test child to one exact current Sol action target.
2. Make one worker `DECISION_REQUEST` visible to all three accounts.
3. Require **one authoritative action** from the bound account and **two observer accounts** to remain read-only.
4. Prove exactly one same-carrier Sol edge, zero competing edges, zero duplicate Wake/Job, and zero successor commission.

### Canary B — unavailable authority

1. Make the authoritative account unavailable before it writes.
2. Verify observers refuse takeover merely because they are responsive.
3. Perform canonical action-target transfer through the existing owner.
4. Only the newly resolved account may act.
5. Prove newest tab, account number, timestamp order, and newest Slack response never elect replacement authority.

### Canary C — self-deadlock regression

Present a fixture with worker `RESULT` or `DECISION_REQUEST`, worker waiting for Sol, current role `ACTION_AUTHORITATIVE`, and a decision inside current Chairman intent. The watcher must produce `SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER`; notification-only output fails.

### Canary D — exact prompt drift

For every role, mutate one character, header order, body line, trailing space, internal blank line, Markdown quote, or appended “safe” prohibition. Require `CANONICAL_PROMPT_MISMATCH`. CRLF/lone-CR transport and terminal newline removal are the only accepted normalizations.

## Completion and rollback

Account hardening is complete only when:

- all three account receipts are present;
- every enabled temporary Sol watcher validates;
- exact native readback matches renderer output;
- one action-authoritative/two-observer canary passes;
- no task ID unexpectedly multiplied;
- no authority conflict is hidden;
- one real no-Chairman continuation cycle succeeds.

If a known safe prompt replacement makes a task unreadable or changes identity, restore the previous prompt on the same task ID. If effect is ambiguous, preserve `EFFECT_UNKNOWN`, do not repeat elsewhere, and reconcile that account-local surface.

Temporary watchers remain transitional. Retire them only after the canonical Agent Dialogue -> Wake -> exact RuntimeBinding/current writer -> acknowledgement/source-resolution path is production-proven for that responsibility.
