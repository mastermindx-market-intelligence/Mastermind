# Source Continuity Roster Order Implementation Plan

**Predecessor:** `2026-11-03-source-continuity-read-retry.md` (Mastermind #1983), whose residual risk names this follow-up
**Consumers:** release gate 4 for the Macro vertical carriers (macro#7870, macro#8250), currently met by a manual five-leg substitute
**Capability ceiling:** source-only until normal review and release gates

## Goal

Stop a PR opened while the open-PR roster is being read from refusing a Macro-scale census. #1983's live proof completed its first observation, then the second observation refused `REMOTE_PROBE_FAILED` after 17 roster calls. No read failed. macro#10641 was opened during that roster read.

The roster is read in offset pages. GitHub's `pulls` list defaults to newest-first, so a new PR inserts before the cursor, pushes one row already read onto the next page, and the census's duplicate check refuses. This change reads the roster oldest-first. It also stops treating a first-pass PR's absence from the second roster as closure, because a PR closed mid-read makes offset paging skip a row in either order.

## Bound evidence

- #1983 live run (2026-11-03 03:51Z, macro#7870, 918 open PRs). First observation complete: 1,570 calls, `OVERLAP` with 301 colliders. Second observation refused `REMOTE_PROBE_FAILED` after 17 calls with an empty stderr, so the refusal was semantic. macro#10641 was created at 03:56:16Z, during that read. This cause is inferred from the call count and the creation time; it was not instrumented.
- GitHub's REST `GET /repos/{owner}/{repo}/pulls` takes `sort` (default `created`) and `direction` (default `desc` for `created`). Offset pagination is computed against the live list on every page.
- Before this change, `_revalidate_collision_census` refused `REMOTE_PROOF_CHANGED` when a first-pass disjoint PR was missing from the second roster and a direct read said it was still open. A colliding PR missing from the second roster refused without a read.

## Design

Roster query (`_read_open_pull_roster`):

```text
repos/{repo}/pulls?state=open&sort=created&direction=asc&per_page=100&page={1..16}
```

With oldest-first offset paging:

| Change during a roster read | Before the cursor | After the cursor |
| --- | --- | --- |
| PR opened | never: a new PR sorts last | appended, read normally |
| PR closed | the next page skips one row | not read, as before |
| older PR reopened | a row is duplicated: refuses `REMOTE_PROBE_FAILED` | read normally |

Newest-first, every PR opened during the read duplicates a row. Oldest-first, only a reopened PR can, which is rare.

`_open_pull_roster_semantics` now requires exactly these five query keys, with `sort=created` and `direction=asc`. A conditional replay of any other roster URL, including the old three-key URL and `direction=desc`, is unprovable and keeps the changed-representation refusal.

Second-observation revalidation (`_revalidate_collision_census`, the conditional path where every first-pass record has an identity). A first-pass PR missing from the second roster is read with one `repos/{repo}/pulls/{n}` call:

| Direct read | First-pass disjoint PR | First-pass colliding PR |
| --- | --- | --- |
| not an object, or `state` not `open`/`closed` | `REMOTE_PROOF_CHANGED` | `REMOTE_PROOF_CHANGED` |
| a different PR number, or an invalid identity | `REMOTE_PROBE_FAILED` | `REMOTE_PROBE_FAILED` |
| `closed` | dropped from the census, as before | `REMOTE_PROOF_CHANGED`, as before |
| `open`, identity unchanged | first evidence reused | first evidence reused |
| `open`, identity moved | files re-read; a collision refuses | `REMOTE_PROOF_CHANGED`, as before |

So the direct read decides exactly as a roster row would. PRs that appear only in the second roster are still freshly evaluated. Re-reading the whole roster on a duplicate was considered and not added: oldest-first leaves only reopens before the cursor, and nothing in Macro's automation reopens PRs.

## Preserved semantics

- The pure verifier `control_plane/source_continuity.py` is unchanged. Receipt, refusal and writer-gate schemas are unchanged.
- The duplicate check still refuses `REMOTE_PROBE_FAILED`. Deduplicating would be unsafe: a duplicate and a skip in the same read would silently lose a row.
- Page size, the 16-page cap, the 1,500-PR cap, the short-page stop, every call, byte and time budget, and the bounded read retry are unchanged.
- A colliding PR still may not move or close between observations. A closed disjoint PR still drops out only after a direct read proves it closed.
- The identityless and legacy second-observation paths still re-run the full census and compare snapshots. They pick up oldest-first paging but not the direct reads.
- Cost: one extra call per first-pass PR missing from the second roster, which is at most the number of PRs that closed during the run. A colliding PR that closed now costs one direct read before it refuses.

## RED-first evidence

Against the #1983 head source (`0f7bcfc84`):

- A scenario probe against the new churn fake (`tests/test_source_continuity_roster_order.py`, 249 foreign PRs over three pages) reproduces the live failure. A PR opened mid-read in either observation ends rc=2 `REMOTE_PROBE_FAILED`. A closure mid-read in the second observation ends rc=1 `REMOTE_PROOF_CHANGED`, because the skipped open PR's direct read was taken as proof of change.
- 19 of the 25 new cases fail, including every scenario case. The 6 that pass on both sources are `_open_pull_roster_semantics` rejections of queries the old three-key check also rejected: `direction=desc`, `sort=updated`, a missing `sort`, page 17, a repeated key and an extra key.
- With only the roster URL reverted, so that the fake recognises the old query, the two re-prove cases in `tests/test_source_continuity_relevant_collision_semantics.py` fail: a missing disjoint PR and a missing collider, each with a direct read still reporting it open. The new moved-collider case and all the other cases pass on both sources.

Under the new source, all `tests/test_source_continuity*.py` cases pass.

The new tests pin:

- the exact oldest-first query, sent identically by both observations;
- a PR opened mid-read in either observation appended once and freshly proved, with no direct reads; a colliding one refuses `REMOTE_PROOF_CHANGED`;
- a closure mid-read that skips a disjoint PR or a collider: exactly one direct read of the skipped PR, a receipt, and the collider still reported;
- a skipped PR that moved, closed, names another PR, or reports an unknown state;
- a collider skipped by the first roster but present in the second refuses, as a new collision;
- the residual reopen-before-cursor duplicate still refuses `REMOTE_PROBE_FAILED`;
- `_open_pull_roster_semantics` accepts only the five-key oldest-first query, in any key order.

## Exact source scope

1. `scripts/source_continuity.py`: the roster query in `_read_open_pull_roster`, the query check in `_open_pull_roster_semantics`, and the missing-PR branch in `_revalidate_collision_census`
2. `tests/test_source_continuity_roster_order.py` (new)
3. `tests/test_source_continuity_relevant_collision_semantics.py`: the open-but-missing case inverted from a refusal to a re-proof, and a moved-collider case added
4. roster URL fixtures in `tests/test_source_continuity.py`, `tests/test_source_continuity_r3_hardening.py`, `tests/test_source_continuity_saturated_foreign_pr.py` and `tests/test_source_continuity_read_retry.py`
5. this plan

## Residual risk

- Offset paging still skips a row when an earlier row closes mid-read. A PR skipped by both observations' rosters is missed by the census, as before this change. A PR opened between the observations and then skipped by the second roster is also missed. Both need two specific events at a page boundary inside a few-minute window.
- The subject PR skipped by the second roster still refuses `REMOTE_PROOF_CHANGED`. The identityless and legacy paths still refuse `REMOTE_PROOF_CHANGED` after a skip. Both are fail-closed.
- A reopened PR older than the cursor still duplicates a row and refuses `REMOTE_PROBE_FAILED`.
- GraphQL cursor pagination would be stable against both inserts and closures. It would change the transport, its budget accounting and the conditional-replay proofs, so it is out of scope.
- A live run has not exercised this change yet. One real-path run at Macro scale is the remaining proof. The token is shared, so that is at most one run.

A merge grants no runtime, deployment, ranking, serving or trading authority.
