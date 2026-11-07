# C19 / C9 integration addendum: durable trial accounting qualification

Research evidence for MAS-264 and MAS-269. This is a new, bounded addendum to the
original Commission 9 research. It is not the missing full C19 package tracked by
MAS-282, an implementation commission, an Agent OS ledger, or a production gate.

## Original research and retained thesis

Preserve [Commission 9 PR #1242](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1242)
at `ac9c7345201e2c369a950663c297411f42837f03`, especially its
[P0A commission](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ac9c7345201e2c369a950663c297411f42837f03/research/commission_09_dataset_value_gauntlet/2026-10-04/IMPLEMENTATION_COMMISSION_P0A.md),
[audit](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ac9c7345201e2c369a950663c297411f42837f03/research/commission_09_dataset_value_gauntlet/2026-10-04/AUDIT_AND_RECENSUS.md),
and original synthetic receipt. At this review, that PR is draft/open; publication
is not research acceptance or implementation authority.

Retain its core thesis: qualify a dataset **use**, reuse incumbent Data OS,
TrialLedger and Lab, account for attempts/exposure before evaluation, preserve
negative results, and keep synthetic plumbing distinct from market value. Retain
Q01–Q20 in the original P0A commission without weakening or replacing them.

This addendum advances only the accounting part of that review. The complete
MAS-264 research set, P0A implementation, intended reader and full Q01–Q20
acceptance remain incomplete. No claim here closes MAS-264 or MAS-269.

## Current source census

Protected procedure: Mastermind `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`,
skillpack v1.0.1 / bootstrap major 1. Source census: Macro
`9201f1602bfe47e05a63d61802fbed6f7f55a19d` (`main`, 2026-10-04).
Exact GitHub contents reads, not a potentially truncated recursive tree, establish
these owners exist. Their blobs match the original C9 Macro evidence pin
`e570025bf3921ac26c3bdcb06ad25303677f325d`.

| Existing owner | Git blob at both revisions | Relevant seam |
|---|---|---|
| `engine/trial_ledger.py` | `eb364fe9fa53f46d0455e194d3e3ccdbb5732778` | `TrialLedger.log_trial`, `log_declared_budget`, `_load` |
| `engine/lab.py` | `430a074000ac259d199ec48c20842d784f611866` | `backtest`, `Trial`, existing research reader conventions |
| `engine/validation.py` | `e9bbe0e77ae571b62a9f5b8b8e4e7a950c035399` | Shared statistical/cost primitives; no copied replacement math |
| `lib/dataos/temporal.py` | `094b149a8b9158f19cb99c4005568c12db96ed41` | Native profiles, `known_at`, `as_of_filter` |

The temporal API's source-known semantics are not proof of actual historical
system consumption. P0A must preserve its declared temporal mode and separately
require the appropriate system/served evidence; no global meaning change is
authorized. Generated `data/oracle/...` files are not substitutes for the source
owners above. Dataset IDs remain owned by `config/dataset_registry.yml` and
`lib/dataos/registry.py`; this addendum creates no definitions there.

The unchanged validation blob preserves the relevance of original C9 SYN-01/02/03
(future-dependent cost warm-up, initial-capital drawdown, singular-design VIF).
Those remain the original author's expression-level demonstrations; they were
not rerun or represented as full-module/production tests in this review.

## Newly executed owner-module evidence

[probe_trial_ledger.py](probe_trial_ledger.py) verifies the exact SHA-256 of the
supplied owner module, imports that module, and constructs `TrialLedger` instances
with explicit temporary synthetic paths. A regular file temporarily obstructs the
intended ledger's parent directory. The first append raises `FileExistsError`.
The probe then removes only that synthetic obstruction and retries on the same
instance. A separate normal-write control verifies persistence and reload.

Execution: Python 3.14.7 on mini4; exit 0. The exact output is
[SYNTHETIC_LEDGER_RECEIPT.json](SYNTHETIC_LEDGER_RECEIPT.json).

| Case | Memory after failed append | Retry after I/O repair | Durable file | Reloaded count | Normal-write control |
|---|---:|---|---|---:|---:|
| Distinct trial | 1 | `False` (already seen) | absent | 0 | 1 |
| Declared budget | 7 | `False` (already seen) | absent | 0 | 7 |

The in-memory dedup/count mutation precedes the successful append. A caller that
catches the first error and retries the same instance cannot treat `False` as
proof of a prior durable record. Restart loses the memory-only accounting.
This is a demonstrated qualification failure for the P0A durable-before-evaluation
requirement. It does **not** prove that an actual caller evaluated after an error,
that real research was unlogged, or that every ledger operation is defective.

The probe uses `literal_n` and `declared_budget`: `effective_n` intentionally floors
at one and is not a durable-row count. Neither this fixture nor exit 0 certifies
Q09 as passed. Crash/power-loss durability, corrupted input, concurrent processes,
attempt identity and cohort exposure remain untested here.

Reproduce after obtaining the exact source through an authorized read:

```bash
python3 research/commission_19_c9_qualification/2026-10-04/probe_trial_ledger.py /absolute/path/to/pinned/trial_ledger.py
```

The source SHA-256 must be
`7b99683c9aee822df138d35b8294318e3316c3b6a8b5a80934614141a15413f7`.
A different source is refused before import; a later repair needs a new source
census and its own evidence, not changing this historical pin to obtain a pass.

## Dispositions and supersession

| Claim / proposal | Disposition | Consequence |
|---|---|---|
| Reuse Data OS, TrialLedger, Lab and validation | RETAIN | No replacement ledger, registry or statistics library. |
| C9 audit's memory-before-append risk | CORRECT evidence strength | Now directly reproduced for two methods on the pinned owner module; broader failure claims remain unproven. |
| Existing ledger counts suffice for durable evaluation admission | REJECT for this P0A use | No evaluation may proceed without a verified durable accounting receipt or an explicit refusal. |
| C9 SYN-01/02/03 require qualified methods or refusal | RETAIN | Source blob unchanged; no automatic repair or adoption of a conflicting candidate. |
| A synthetic success establishes alpha/decision value | REJECT | Real information and decision value remain `NOT_TESTED`. |

This addendum supersedes only the evidence classification of the stated C9
accounting risk. It does not replace the original research, narrow Q01–Q20, accept
the full research packet, or supersede source/authority/custody law.

## Integration boundary and next proof

The next bounded accounting action belongs to Macro's existing `TrialLedger`
owner. Before source work, resolve the live writer and complete the exact path
collision census. A historical workstream owner is not a current receiver.
Then either obtain an owner-approved compatible durability repair or keep the
P0A adapter unable to evaluate and return the precise accounting blocker. Merely
writing a second ledger or silently retrying a poisoned instance is inadmissible.

A repair must prove: normal persistence and reload; failed append cannot leave a
false durable receipt; a lawful retry is retained; corrupt/unreadable accounting
refuses evaluation; crash/concurrent custody has an explicit contract; and
config identity, attempts and cohort exposure remain distinct. Each proof must
observe the actual changed path. No market outcomes are needed for these cases.

One bounded scan inspected the newest 250 of 566 open Macro PRs. It found
[Macro #8271](https://github.com/mastermindx-market-intelligence/macro/pull/8271)
at `7b19b87eb61d3b5d04197d2c5e346e0163f894d5` touching `engine/validation.py`,
and #7871 at `df96a1e3a79d976c987470c12b0d15ccf579c5ef` touching the registry.
An older-page query failed HTTP 502. This is **not a complete collision census**
or a writer lease; no shared-source implementation is admitted by this addendum.
Snapshot PR #673 remains draft/open at
`0b960590c77101b3f3b5545896423f9ad07b7d56`; no replacement Snapshot is proposed.

No vendor rights, prices, entitlement, historical coverage or procurement choice
were newly verified. P0A rights/temporal/identity gates remain independent: a
strong metric cannot compensate for failed admission. Market/production/portfolio
authority is unchanged. The full C19 package's original source-custody refusal
remains MAS-282's separate recovery obligation.

## Verification and remaining uncertainty

Native Sol COO read-only review reproduced the receipt and returned PASS for the
bounded behavioral claim, source pin and synthetic isolation. The reviewer did
not grant source, release or production authority. `git diff --check` passed.
No production ledger, market data or holdout was opened; no core owner source was
changed. This is executable research evidence, not a shipped P0A capability.

Falsifier: a collision-resolved successor of the canonical owner proves that
append failure leaves no false durable state and that successful retry/reload
retains the record, with the owed crash/corruption/concurrency tests. Until then,
the demonstrated use remains `BLOCKED_DURABLE_ACCOUNTING`.
