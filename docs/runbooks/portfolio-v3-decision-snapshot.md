# Portfolio V3 S0 Decision Snapshot — operator runbook

**Scope:** the S0 Decision Snapshot vertical only. No Claim, PM View, constructor, alpha
tilt, target, shadow account, learning policy, or execution logic exists yet. `autonomous`
remains the sole active US managed book. This CLI is read-mostly: `compose` is the only
command that writes anything, and everything it writes is an immutable, content-addressed
evidence file under `data/shadow/decision_snapshots/autonomous/`. The snapshot itself
always carries `write_permitted=false`, `execution_authority=false`, and
`numeric_target_authority=false` — **a Decision Snapshot is evidence, never an executable
target.** Nothing in this workflow places an order, sizes a position, or authorizes a
trade.

## Commands

Run from the repository root with `python3`.

### Compose one immutable snapshot

```bash
python3 scripts/portfolio_decision_snapshot.py compose \
  --book autonomous \
  --decision-cutoff 2026-09-15T20:00:00Z \
  --recorded-at 2026-09-15T20:01:00Z
```

Both `--decision-cutoff` and `--recorded-at` are required, explicit, timezone-aware UTC
timestamps. Neither clock is ever defaulted by the tool — the operator states, for the
record, exactly what point in time this snapshot's evidence is being judged against
(`decision_cutoff`) and exactly when it was captured (`recorded_at`). `compose` prints
one bounded receipt and nothing else — never the full snapshot body, its sources, or its
sections:

```json
{
  "schema": "mastermind.portfolio_decision_snapshot.compose_receipt.v1",
  "book": "autonomous",
  "snapshot_id": "sha256:...",
  "state": "PARTIAL",
  "coverage_state": "PARTIAL",
  "write_root": "data/shadow/decision_snapshots/autonomous",
  "write_permitted_outside_shadow": false,
  "execution_authority": false
}
```

### Check the latest snapshot (read-only)

```bash
python3 scripts/portfolio_decision_snapshot.py status \
  --book autonomous
```

`status` never composes. If nothing has ever been captured for the book it prints a typed
`NO_SNAPSHOT` object, not an error and not a freshly composed snapshot:

```json
{"schema": "mastermind.portfolio_decision_snapshot.cli_status.v1", "book": "autonomous", "status": "NO_SNAPSHOT"}
```

Otherwise it prints a compact, verified manifest (identity, clocks, state, coverage,
summary counts, and correction lineage) — never the raw source receipts or section rows.

### Inspect a snapshot or page a section (read-only)

```bash
python3 scripts/portfolio_decision_snapshot.py show \
  --book autonomous \
  --section risk_truth \
  --offset 0 \
  --limit 50
```

`show` with no `--section` prints the same compact manifest shape as `status` (or
`NO_SNAPSHOT`) — never the full section bulk. Add `--section <id>` to page one section's
rows through the accepted `section_page` function (bounded to 100 rows per page; use
`--offset`/`--limit` to walk further pages via the returned `next_offset`). Add
`--snapshot-id <id>` to inspect a specific prior snapshot instead of the latest one; an
unknown or corrupt ID is reported as a typed `not_found` / `corrupt_snapshot` error rather
than silently falling back to the latest snapshot.

The CLI accepts no `--path`, `--root`, `--url`, or `--output` override of any kind, and
the only accepted `--book` value is the lowercase literal `autonomous`. The write location
is always the fixed, displayed-only string `data/shadow/decision_snapshots/autonomous`.

## Reading `PARTIAL`, `#548`, and correction states honestly

`PARTIAL` is not a failure — it is the honest, expected result whenever a required domain
is not fully qualified as of `decision_cutoff`. A missing source is not an empty complete
source; a stale source is not calm; an unknown clock stays unknown. The composer folds
each section's own `coverage_state` into the root `coverage_state` (`BLOCKED` dominates,
then `PARTIAL`, then `COMPLETE`), and `state` mirrors `coverage_state` unless a same-cutoff
correction exists.

`market_structure` in particular stays `PARTIAL` until Sector Central's native-ID,
bounded-paging, correction-safe reader (PR #548) is protected and consumed by this
snapshot's source layer. S0 only captures #548's *raw artifact receipt* today — it does
not reimplement #548's ownership. Do not treat a `market_structure` gap as an S0 defect;
treat it as an open upstream dependency, and re-check `status`/`show` after #548 lands to
see the gap close on the next compose.

A correction never overwrites anything. Composing again at the *same* `decision_cutoff`
after the underlying source generation set has changed produces a **new** immutable file
with `state="CORRECTED_GENERATION_AVAILABLE"` and `correction.status="CORRECTED"`,
carrying the prior snapshot ID(s) in `correction.same_cutoff_prior_snapshot_ids`. The
original file is never touched, never deleted, and remains independently verifiable.
Composing again at the same cutoff with an *unchanged* source generation set is a no-op:
the existing snapshot is returned (`created: false` in the underlying result) and no new
file is written — this is why re-running `compose` for the same decision is always safe by
itself.

## Same-carrier reconciliation for an ambiguous compose effect

If a `compose` invocation is interrupted (killed, timed out, the operator's connection
drops) before its receipt is observed, its on-disk effect is ambiguous: the write may have
completed, partially completed, or never started. **Do not blindly re-run `compose` and do
not blindly treat it as failed.**

State the real limitation up front: `status` can identify only the single current latest
snapshot for the book. It does not answer "does a snapshot for cutoff `T1` exist" once a
later cutoff `T2` has since been composed, and `show` has no `--decision-cutoff` selector
— only `--snapshot-id`, which an operator whose receipt was never printed does not have.
Reconcile in this order:

1. Run `status --book autonomous`. If its manifest's `decision_cutoff` equals the
   interrupted invocation's `--decision-cutoff`, the interrupted compose *is* the current
   latest snapshot: it completed. Take the `snapshot_id` from that manifest and, if you
   need the full verified detail, fetch it with `show --book autonomous --snapshot-id
   <id-from-status>`. Do not compose again for that cutoff.
2. If `status`'s `decision_cutoff` does not match the interrupted cutoff — including a
   `NO_SNAPSHOT` result, or a newer cutoff that could be hiding the interrupted older one
   — `status`/`show` alone cannot prove or disprove that the interrupted cutoff was ever
   written. Fall back to a read-only scan of the fixed storage directory, verifying each
   candidate's own canonical `decision_cutoff` field rather than guessing from filenames or
   listing order:

   ```bash
   python3 -c "
   import json
   from portfolio import decision_snapshot as ds
   for row in ds.list_snapshots('autonomous', limit=100):
       print(json.dumps(row, sort_keys=True))
   "
   ```

   This calls the same accepted, verified read path (`decision_snapshot.list_snapshots`)
   the CLI itself is built on, bounded to 100 rows to match its closed limit, and prints
   only manifest rows — it opens nothing for writing and creates nothing. It is a
   diagnostic snippet run from the repository root, not a fourth CLI subcommand; do not
   wire this into `scripts/portfolio_decision_snapshot.py`. Scan the printed rows for the
   interrupted `decision_cutoff`.
3. If a printed row's `decision_cutoff` matches, the interrupted compose completed — do
   not run it again. If no row matches after this scan, classify the outcome
   `EFFECT_UNKNOWN` and **stop**. Do not recommend a fresh `compose`, and do not hand the
   operation to another carrier or session on the theory that "it probably didn't write" —
   an `O_EXCL` write that completed and then failed only to print its receipt is
   indistinguishable from "never started" without this scan. A fresh `compose` for that
   exact `(book, decision_cutoff)` becomes lawful only once this exact canonical
   reconciliation proves `not_found` for that cutoff and its source generation set — never
   before.
4. If `status` or `show` instead raise a typed `corrupt_snapshot` error for a partially
   written sibling file, that is a distinct, already-reported condition: the store's
   create-once (`O_EXCL`) persistence guarantees a genuinely partial write is never
   silently adopted as valid. Treat it the same as step 2 — reconcile which cutoff the
   corrupt file was for before deciding anything — never as automatic license to retry.
5. A same-cutoff retry with an *unchanged* source generation set is documented above as an
   idempotent no-op. That fact describes what happens for a cutoff you have already
   reconciled by steps 1–3; it is not permission to skip that reconciliation and retry a
   cutoff whose effect is still unknown.
6. Never guess at intent across two different decision cutoffs or two different books —
   reconcile the exact same `(book, decision_cutoff)` pair the interrupted call used.

## Rollback

Rolling back this S0 operator workflow means removing the three files this release
introduced (`scripts/portfolio_decision_snapshot.py`,
`tests/test_decision_snapshot_cli.py`, this runbook) and reverting the commit that added
them. It does **not** mean deleting any snapshot file already written under
`data/shadow/decision_snapshots/autonomous/`. Every persisted snapshot is immutable
evidence of what the system observed at a real point in time; removing the operator
tooling that produced it must never destroy that evidence. If a rollback is required,
confirm afterward that `data/shadow/decision_snapshots/autonomous/*.json` is unchanged —
the snapshot files themselves are not part of what gets rolled back.

## Before/after V2-state hash procedure (no-effect verification)

This CLI, and the `decision_snapshot` module it calls, must never mutate any existing
Portfolio V2 state. Verify this directly, the same way the owning no-effect regression
(`tests/test_decision_snapshot_no_effect.py`, Task 7) verifies it: hash the seven canonical
V2 state files for the book **before** and **after** running `compose`, and require every
hash to be byte-identical:

```text
data/portfolios/autonomous/account.json
data/portfolios/autonomous/fills.jsonl
data/portfolios/autonomous/nav_history.jsonl
data/portfolios/autonomous/decisions.jsonl
data/portfolios/autonomous/pending_orders.json
data/portfolios/autonomous/pending_target.json
data/portfolios/autonomous/_pending_decision.json
```

Procedure:

1. For each of the seven paths, if the file exists, record its SHA-256 digest; if it does
   not exist, record `ABSENT` for that path. **Only stat/read the path — never open it for
   writing, and never create it.** A file that is legitimately absent (for example, no
   pending order queued) must still be `ABSENT` after the run, not created as a byproduct
   of checking it.
2. Run one `compose` invocation.
3. Recompute all seven digests/`ABSENT` markers the same way.
4. Require every one of the seven entries to be identical before and after. Also confirm
   exactly one new file appeared under
   `data/shadow/decision_snapshots/autonomous/*.json`, and that its name matches the
   printed `snapshot_id`.
5. Any digest change, or any `ABSENT` path that became present (or vice versa), is a hard
   failure of the no-effect boundary — stop and treat it as a defect in the source layer,
   not in this CLI.

This procedure records state; it never repairs, backfills, or recovers it. It intentionally
does not call `portfolio.paper_account._load_account()` or any other account-recovery path,
because that function can mutate state as a side effect of loading it.
