# Sol Watcher Self-Deadlock Hardening Design

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `sol-watcher-self-deadlock-hardening-20260830-sol-001`  
**Repair operation:** `sol-watcher-pr268-polarity-repair-20260901-sol-001`  
**Carrier:** Mastermind PR #268 / `sol/sol-watcher-self-deadlock-hardening-20260830`

## Outcome

A Sol-owned continuation watcher must never detect an in-scope worker `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, conclude that Sol owes the next decision, and then wait for Sol. The exact action-authoritative Sol surface either writes the lawful same-carrier edge or returns one typed blocker. Sister Sol accounts may observe but cannot race the child without canonical action-target transfer.

## Incident and root cause

The FF/FIF worker returned `RESULT / REQUEST_CHANGES` and correctly kept its continuation path alive. The CEO-side watcher repeatedly recognized that the worker was waiting for Sol but emitted notification-only summaries. Both sides waited for the same role.

The underlying defect was not merely a missing phrase. Temporary watcher prompts were free-form English, and validity depended on a growing natural-language polarity scanner. Explicit prohibitions, double negations, sequencing clauses, Markdown, and contradictory later instructions could be misclassified. The scanner therefore became an accidental authority parser.

Historical regex/polarity candidates—including quarantined commit `4454f607ae02b990c8418ab6f946ddd568fe486c`—remain evidence only. They are preserved in ancestry but are not release candidates.

## Architecture

This wave adds a pure standard-library renderer/validator and read-only account-export audit. It adds no watcher daemon, task store, action-owner table, lifecycle, queue, retry plane, cursor, database, provider session, or transport.

The only valid managed prompt is the exact output of:

```python
render_watcher_prompt(
    *,
    role: WatcherRole | str,
    operation_key: str,
    carrier: str,
    latest_handled_edge: str = "NONE",
) -> str
```

The renderer derives the role contract. Callers may supply only identity fields. Output is:

```text
MMX_SOL_WATCHER_V1
WATCHER_ROLE: <role>
OPERATION_KEY: <operation>
CARRIER: <carrier>
LATEST_HANDLED_EDGE: <edge>
ACTION_REQUIRED_EVENTS: <derived>
ACTION_REQUIRED_OUTCOME: <derived>
SISTER_SOL_POLICY: <derived>

MMX_SOL_WATCHER_BODY_V1
<exact frozen numbered body>
```

There is no terminal newline.

## Canonical identity law

Validation performs only these transport normalizations:

1. CRLF to LF;
2. lone CR to LF;
3. removal of terminal newline characters.

It does not trim spaces/tabs, case-fold, Unicode-normalize, reorder fields, ignore blank lines, parse Markdown, or accept added prose. After structural identity fields are valid, the normalized document must equal renderer output byte-for-byte. Any drift returns `CANONICAL_PROMPT_MISMATCH`.

Legacy finding enum values remain available for report-schema compatibility. Natural-language polarity is not a validity boundary and cannot make a noncanonical prompt valid.

## Closed roles

### `ACTION_AUTHORITATIVE`

- exact current action target only;
- exact Slack carrier required;
- events `BLOCKED,DECISION_REQUEST,RESULT`;
- outcome `SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER`;
- verifies current target authority from canonical owners;
- writes one same-carrier Sol edge or returns a typed blocker;
- never asks/waits/defers/escalates to Sol;
- verifies terminal STOP before disarming.

### `OBSERVER_ONLY`

- read/report only;
- may use exact Slack or bounded `aggregate:` carrier;
- cannot write child continuation/ruling/repair/park/hold/stop;
- cannot merge/release/auto-merge, retry/fail over, or start a successor;
- cannot elect authority by recency or responsiveness.

### `PARENT_ORCHESTRATOR`

- acts only on canonically proven parent transitions;
- cannot consume or answer a dedicated child return;
- never races the child action surface.

### `TRIAGE_ONLY`

- detects/reconciles/reports unconsumed returns;
- preserves unresolved owner/carrier/effect collisions;
- never becomes action target merely because it discovered the defect.

## Exact body ownership

The exact numbered common prefix and role tails are source constants in `control_plane/sol_watcher_contract.py`. Procedure documentation may display them, but native prompts must be generated from source rather than copied by hand. No role may add, remove, reorder, paraphrase, annotate, quote, or append body content.

Operation-specific facts remain in the seven headers and current canonical systems—not in free-form body text.

## Account-export audit

`scripts/audit_sol_watchers.py` remains read-only. It accepts a JSON list or an object containing `tasks`, validates each enabled `SOL_WATCHER`, and emits `mastermind.sol_watcher_audit.v1`.

Wrapper law is preserved:

- `id` or `task_id` must be present and nonempty;
- aliases are trimmed independently and must agree;
- canonical IDs must be unique, including disabled tasks;
- enabled state must be a real JSON Boolean;
- conflicting enabled aliases fail;
- `audit_kind` is `SOL_WATCHER` or `NON_WATCHER`; unknown values fail;
- non-object entries fail;
- report separates invalid prompt, classification, export, and duplicate-ID findings.

The documented clean-checkout command is:

```text
python3 -m scripts.audit_sol_watchers tasks.json
```

A green report proves prompt conformance only, not task execution, Slack I/O, Wake, acknowledgement, or source resolution.

## Three-account rollout

Each ChatGPT web account owns its own native task store. The one rotating Codex OAuth slot does not identify or authorize all three accounts.

For each account:

1. export current tasks;
2. reconcile one role per watcher and the current action target;
3. render the complete replacement prompt;
4. replace the complete prompt on the same native task ID;
5. read back and compare byte-for-byte after permitted newline normalization;
6. if effect is ambiguous, record `EFFECT_UNKNOWN` and do not retry/fail over to another account;
7. re-export and require audit exit 0.

Then run one-authoritative/two-observer canaries, unavailable-authority transfer, self-deadlock regression, and exact prompt-drift mutations.

## No-rebuild boundaries

Executive OS remains the sole Job/Attempt/Worker/Event owner. Agent Dialogue, Wake, RuntimeBinding, current provider writer, acknowledgement, and source resolution remain their existing owners. This wave creates no new runtime or authority plane and does not make Autonomy production-live.

## Acceptance

Source acceptance requires:

1. exact renderer body equality for all four roles;
2. all lawful carrier combinations and invalid renderer inputs proven;
3. CRLF/lone-CR and terminal newline accepted; all other drift rejected;
4. every historical B1/B2/B3/composition witness rejected through `CANONICAL_PROMPT_MISMATCH`;
5. export identity/Boolean/classification/duplicate behavior preserved;
6. CLI module invocation proven;
7. Skillpack/runbook/design/plan synchronized;
8. current protected base, exact nine-path carrier, hosted repository/security green;
9. independent immutable-head adversarial review;
10. PR remains DRAFT/HOLD until Sol release adjudication.

Maximum source claim: `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

`PROVEN_LIVE` additionally requires all three native account receipts, exact prompt readback, one authoritative/two observer canary, canonical transfer test, and one real no-Chairman continuation cycle.
