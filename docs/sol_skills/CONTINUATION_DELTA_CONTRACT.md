---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.1.0
minimum_bootstrap_major: 1
skill: continuation_delta_contract
---

# Continuation Delta Contract (heavy reference)

Load this contract only when constructing or validating a `CONTINUATION_DELTA`
commission (`COMMISSION_WAVE.md` requires it for that mode; a genuinely new
independent wave does not need this token load).

## Design thesis

Continuation commissions are derived deltas, never copied-forward plans:

```
NEXT_WORKSET
    = OPEN + NEW + REVALIDATE_REQUIRED
    - DONE - SUPERSEDED - REJECTED - BINDING_DO_NOT_REDO
```

Only `NEXT_WORKSET` may appear in executable scope. A completed verification
may run again only when a named state change invalidates its earlier receipt —
that is revalidation, not redo.

No new lifecycle, queue, memory plane, or task database exists here. Agent OS
remains the anti-repeat organizational memory; GitHub remains implementation/
evidence truth; the commission manifest is an **ephemeral derivation artifact**
that owns no status, no history, no retries, and no runtime state.

## Commission modes

Every substantial Sol handoff declares one mode:

- `NEW_WAVE` — a genuinely new bounded wave. Comprehensive context allowed.
- `CONTINUATION_DELTA` — resuming the same carrier/wave/program, or a
  successor action whose scope depends on prior completed obligations.
  Delta-first: historical work may appear as evidence, but only IDs in the
  execution section are executable.

## Manifest schema (`mastermind.sol_commission.v1`)

The manifest is a YAML mapping — either a standalone `.yml` file, or the first
fenced ```yaml block carrying the schema id inside a `.md` commission document.

```yaml
schema: mastermind.sol_commission.v1
handoff_mode: CONTINUATION_DELTA        # or NEW_WAVE

identity:
  program_or_workstream: "WS:<KEY>"
  repository: owner/repo
  carrier:
    type: pull_request                  # or branch
    id: 6337                            # required for pull_request
    branch: branch/name
    pickup_sha: <40-hex>                # REQUIRED for CONTINUATION_DELTA
    completed_waves: [R3A, R3B]         # optional; feeds the staleness hint
  skillpack_sha: <40-hex>

sources:                                # REQUIRED for CONTINUATION_DELTA
  agentos_workstream:
    path: agentos/workstreams/WS-<KEY>.md
    observed_sha: <observed-sha>        # grammar below
    recorded_next_wave: R3B             # optional; feeds the staleness hint
  latest_handoff:
    path: agentos/handoffs/<...>.md
    observed_sha: <observed-sha>
    status: present                     # present | absent | unavailable
  github:
    default_branch_sha: <40-hex>
    carrier_head_sha: <40-hex>

obligations:
  - id: APP-01
    statement: <one obligation>
    disposition: OPEN                   # vocabulary below
    evidence: ["..."]                   # required in spirit for DONE
    prior_evidence: ["..."]             # REVALIDATE_REQUIRED only
    invalidated_by: ["..."]             # REVALIDATE_REQUIRED only
    blocked_on: "..."                   # BLOCKED
    hold_reason: "..."                  # required to hold OPEN/NEW/REVALIDATE
    deferred_to: "WS:<KEY>"             # independent-parallel-wave exemption

do_not_redo_reconciliation:
  - source: agentos/handoffs/<...>.md
    statement: "<the binding statement, verbatim>"
    disposition: HONORED                # or REFUTED
    refuted_by: ["<new canonical evidence>"]   # REFUTED only
    reopens: [APP-01]                   # only lawful with REFUTED + refuted_by

execution:
  ordered: [APP-01]                     # executable surface
  parallel: []                          # executable surface
  held: [R3C-COND-01]                   # declared, NOT executable

stop_condition: >
  Exact stop/return point.
```

### Grammar: `observed_sha` (blob-proof representation)

Exactly one of:

- `<40-hex>` — the commit SHA at which the source was read;
- `blob:<40-hex>` — the git blob SHA-1 of the file's exact bytes
  (`git hash-object <file>` / `git ls-tree <commit> -- <path>`);
- no `observed_sha`, with `status: unavailable` plus a non-empty `reason`
  (or `status: absent` when no such record exists yet).

Anything else is `MALFORMED_MANIFEST`.

### Obligation dispositions

`DONE`, `OPEN`, `NEW`, `BLOCKED`, `SUPERSEDED`, `REJECTED`,
`REVALIDATE_REQUIRED` — meanings per the Continuation Delta Law.
`REVALIDATE_REQUIRED` demands BOTH `prior_evidence` and a concrete
`invalidated_by` event.

### Surface legality

- **Executable** (`execution.ordered` / `execution.parallel`): only `OPEN`,
  `NEW`, `REVALIDATE_REQUIRED`. `DONE`/`SUPERSEDED`/`REJECTED` there is a
  replay collision; `BLOCKED` there is `EXECUTION_DISPOSITION_ILLEGAL`.
- **Held** (`execution.held`): `BLOCKED` always; `OPEN`/`NEW`/
  `REVALIDATE_REQUIRED` only with an explicit `hold_reason`;
  `DONE`/`SUPERSEDED`/`REJECTED` never (settled work is reported settled, not
  held — `HELD_DISPOSITION_ILLEGAL`).
- **Every ID on every surface (held included) must be declared in
  `obligations`** — otherwise `UNDECLARED_EXECUTION`.
- An `OPEN`/`NEW`/`REVALIDATE_REQUIRED` obligation must be executable, held,
  or carry `deferred_to: WS:<KEY>` naming the independent workstream that owns
  it — otherwise `DARK_OPEN_WORK`.

## Deterministic linter

```
python3 scripts/sol_commission_lint.py path/to/handoff.md
python3 scripts/sol_commission_lint.py path/to/handoff.md \
    --agentos-context path/to/context_bundle.json
```

Zero-network, deterministic, validation-only. **It authorizes nothing.**

### Hard findings

| Finding | Fires when |
|---|---|
| `MALFORMED_MANIFEST` | unparseable/mis-typed manifest, unknown disposition/mode/status, bad SHA grammar, unreadable bundle |
| `HANDOFF_REPLAY_COLLISION` | a `DONE` obligation appears in executable scope |
| `SUPERSEDED_WORK_REOPENED` | a `SUPERSEDED` obligation appears in executable scope |
| `REJECTED_WORK_REOPENED` | a `REJECTED` obligation appears in executable scope |
| `OBLIGATION_STATE_COLLISION` | the same obligation ID is declared more than once |
| `UNJUSTIFIED_REVALIDATION` | `REVALIDATE_REQUIRED` lacking prior evidence or a concrete invalidating event |
| `UNBOUND_CONTINUATION` | `CONTINUATION_DELTA` without an exact 40-hex carrier `pickup_sha` |
| `UNDECLARED_EXECUTION` | any execution surface (held included) references an undeclared ID |
| `EXECUTION_DISPOSITION_ILLEGAL` | a non-eligible disposition (e.g. `BLOCKED`) in executable scope |
| `HELD_DISPOSITION_ILLEGAL` | settled work held, or `OPEN`-class work held without `hold_reason` |
| `DARK_OPEN_WORK` | `OPEN`/`NEW`/`REVALIDATE_REQUIRED` neither executable, held, nor `deferred_to: WS:<KEY>` |
| `NOTHING_TO_COMMISSION` | `CONTINUATION_DELTA` with an empty executable surface — the lawful response is to emit a `NOTHING_TO_COMMISSION` report to the Chairman instead of a commission; never manufacture work to clear it |
| `DNR_REOPEN_WITHOUT_REFUTATION` | `REFUTED` without `refuted_by`, or `reopens` mapping DNR-covered work toward execution without a lawful refutation |
| `DNR_COVERAGE_MISSING` | with a context bundle: a binding `do_not_redo` statement has no reconciliation entry |
| `ORGANIZATIONAL_STATE_NOT_RECONCILED` | `CONTINUATION_DELTA` missing workstream/latest-handoff/github source identity without an explicit unavailable/absent declaration |

### Warnings (never manufacture authority)

| Finding | Fires when |
|---|---|
| `POSSIBLE_STALE_ORG_STATE` | best-effort only: the author supplied both `sources.agentos_workstream.recorded_next_wave` and `identity.carrier.completed_waves`, and the recorded next wave is already listed completed. No wave-ID ordering semantics exist; absence of this warning proves nothing. |
| `DNR_COVERAGE_UNPROVEN` | no context bundle supplied — only the author's declared reconciliation was validated |
| `NEW_WAVE_WITH_EXISTING_CARRIER` | `NEW_WAVE` bound to an existing pull request — possibly the wrong mode |

### `--agentos-context` comparison semantics (exact)

The bundle is JSON: `{"do_not_redo": [<statement>, ...]}` (a mapping of
source → list is also accepted and flattened). For every bundle statement, a
`do_not_redo_reconciliation` entry must exist whose `statement` is **exactly
equal after normalization** — casefold, whitespace collapsed to single spaces,
leading/trailing space and trailing periods stripped. Nothing fuzzier. A
missing match is hard `DNR_COVERAGE_MISSING`. Compile the bundle from the
current Agent OS workstream + latest handoff (`scripts/agentos.py
compile-context` in the macro repo is the preferred bounded read path).

## Enforcement honesty

The linter runs where the procedure says it runs (`COMMISSION_WAVE.md`
Completion Subtraction Gate, step 6). Live Sol handoffs are chat artifacts
that pass through no CI, so for free-form live handoffs this contract is
**procedurally mandatory, technically advisory** — unless/until a handoff
passes through an enforced carrier (e.g. a committed manifest validated in a
repository gate). Do not represent a lint pass as an authorization, and do not
represent the existence of this tool as automatic enforcement.

## Known deterministic blind spots

- **ID renaming / laundering.** Renaming a settled obligation (`DUR-01` →
  `DUR-01B`, or re-wording its statement) re-opens it invisibly to any
  deterministic check — the linter validates DECLARED reconciliation, not
  semantic identity. This blind spot is owned by `do_not_redo` reconciliation
  (statement coverage), the `REVIEW_RETURN.md` obligation reconciliation, and
  Skillpack pressure testing. Never claim the linter proves non-replay.
- **Semantic DNR completeness.** Without a bundle the linter cannot know what
  binding statements exist (`DNR_COVERAGE_UNPROVEN`); with a bundle it proves
  coverage of the bundle only, not of every durable record in the company.
- **Wave ordering.** `POSSIBLE_STALE_ORG_STATE` is best-effort; the
  `DURABLE_STATE_STALE` judgment in `COLD_START.md` owns staleness detection.

## Over-hardening guard (Case K)

Repeated context is verbosity; repeated executable effect is replay. Only
`execution.ordered` / `execution.parallel` are executable surfaces — a linter
or reviewer that treats descriptive history ("Completed — do not repeat"
sections, evidence lists, long reference appendices) as executable recreates
the incident in the opposite direction. When a duplication dispute arises, run
the `RECONCILE_STATE.md` instruction census before conceding or re-issuing
anything.

## `DURABLE_STATE_STALE`

Classify when GitHub proves a material wave or adjudication advanced while
Agent OS still presents an older wave/next action as current. Material
`DURABLE_STATE_STALE` blocks commissioning work that depends on the stale
organizational sequence: repair the owning Agent OS record/handoff first or in
the same bounded records operation before dispatch. This is reconciliation of
the knowledge plane, not a runtime execution gate — and the repair itself must
respect history: supersede stale records with a newer record/handoff, never
rewrite the historical one to pretend it was not emitted.

## Founding incident

`tests/incident_replays/fixtures/2026-08-25-xpv2-continuation-replay/` (macro
`WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2`): a stale 08-21 handoff still
dispatched R3B after R3B/R3B.1/R3B.2 had completed, and the #6388 workstream
repair itself went stale hours later when carrier #6337 merged
(`APPROVE_WITH_CONDITIONS`, five R3C-owned conditions, R3C not authorized).
The corpus pins both failure shapes RED forever — the copied-forward
commission and the harder lawfully-derived-from-stale-records commission — and
the lawful continuation delta green.
