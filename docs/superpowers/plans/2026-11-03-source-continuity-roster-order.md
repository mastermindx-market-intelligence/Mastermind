# Source continuity: contain unproven multi-page collision coverage

## Current correction — November 4, 2026

This supersedes the roster-order proposal below wherever that proposal treats a
multi-page open-PR listing or tail union as complete coverage. The retained
consumer is the existing source-continuity CLI and its existing
`REMOTE_CENSUS_INCOMPLETE` result; there is no new controller or authority.

The accepted [reopened-collider counterexample](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2006#issuecomment-6613931737)
binds candidate `cc507363beff691a0979498c2ddab6c9c70553a0`. PR 1990 can
be closed during observation one, reopen after its tail, and be skipped in
observation two after PR 1000 closes. Its old creation order excludes it from
the newest-created tail. The candidate returns successful complete DISJOINT
evidence without reading that collider's files.

The separate [authenticated Macro ordering evidence](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2006#issuecomment-6614952253)
also disproves an updated-time page-one watermark as a coverage certificate.
An additional sweep, creation-number floor, unchanged observed membership, or
updated-time tail cannot qualify identities omitted from every observation.

### Bounded implementation

`_read_open_pull_roster` makes the existing oldest-created-first request for
page 1. It validates the list size and each row's positive integer number,
duplicate-free membership and open-state shape.

- A valid response shorter than 100 rows retains the existing single-response
  observation and custody-revalidation contract.
- Exactly 100 rows returns incomplete immediately, including a repository with
  exactly 100 actual open PRs. This response has no qualified end certificate.
- No later offset page, newest-created tail, foreign-file fanout, or merged
  union of different responses may convert that incomplete result to success.
- The existing first-observation guard, identity-aware conditional path,
  identityless fallback and legacy re-census all propagate incomplete coverage
  through `REMOTE_CENSUS_INCOMPLETE`, exit status 2.
- Existing malformed identity, missing-target, collision, changed-proof,
  authentication, retry and resource-limit rules remain in force.

The retained `newest_known` argument provides caller compatibility only; it is
not coverage evidence. The 4,096-call, 900-second, 768-MiB, 1,500-PR and
four-worker profile is unchanged. Those resource ceilings do not authorize
multi-page traversal or establish completeness. The historical 16-page ceiling
is retained, but the corrected reader refuses at the first full page.

### Acceptance and intentional limitation

This is a source-safety containment with an intentional availability reduction.
For repositories with at least 100 open PRs, qualified collision coverage is
unavailable through this reader. The result means missing coverage, not a
detected collision or a permission denial. It must not be promoted into a
complete NONE/DISJOINT result, a successful source-continuity receipt, custody
transfer, release eligibility, or repaired fleet throughput.

Single-response acceptance still uses the existing two-observation and identity
checks. It is not a new promise of an atomic, race-free repository snapshot.
A failed dependent census does not change writer ownership, cancel workers, or
block unrelated authorized work.

Tests preserve real CLI consumers for both checkpoint and remote-complete
requests across conditional, identityless and legacy transports. They cover
99/100/101/920/1500 rows, a short first observation followed by a full second,
malformed rows, missing targets, direct-detail identity checks, the accepted
reopened-collider scenario, real Git checkout verification, bounded file fanout,
shared worker admission, and unchanged authentication/retry limits.

Old large-estate success expectations are deliberately replaced by incomplete
coverage assertions. Independent resource-budget and worker tests use a
qualified short roster while retaining their relevant file fanout and actual
limits. Passing these tests does not qualify large-repository enumeration.

### Remaining permanent capability

Large-estate progress requires accepted coverage evidence through the existing
owner: a provider-supported snapshot or equivalent independently qualified
coverage plus the existing effect/freshness fence. A cursor or `state=all`
listing is not itself that proof. An exact-number scan also needs a qualified
upper bound and treatment of holes, transfer, deletion, reopening and same-count
replacement; resource capacity and identity coverage do not prove simultaneous
state.

Any future restoration must satisfy the existing call, time, byte and worker
limits against realistic Macro history and hostile churn, without another
ledger, watcher, queue, credential route or automatic retry. The current
correction supplies neither that capability nor production adoption.

Integrate through incumbent #2006 after current-head review and normal release
qualification. The original source and live writers are preserved. This source
contribution does not grant review approval, merge, installation or a new
runtime effect.

---

## Historical roster-order proposal — superseded for coverage

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

Oldest-first also puts the newest PRs at the end of the roster, where a closure skips a row. So after the oldest-first pages, `_read_open_pull_roster` reads one newest-first page:

```text
repos/{repo}/pulls?state=open&sort=created&direction=desc&per_page=100&page=1
```

A row on that page that the oldest-first pages did not return is appended and evaluated like any other roster row. A tail that is not a list or holds more than a page, a non-object row, a number that is not a positive int, or a number repeated within the tail refuses `REMOTE_PROBE_FAILED`. The 1,500-PR cap is checked again after the merge.

A full tail page covers only PRs created at least as recently as its oldest row. A reopened PR keeps its place in creation order, so the tail does not cover it. The second observation passes `newest_known`, the largest PR number in the first observation, from all three of its paths. If the tail page is full and every row on it is newer than `newest_known`, PRs opened between the observations may extend past it, so the census is `INCOMPLETE` and refuses `REMOTE_CENSUS_INCOMPLETE`.

| Change before the tail page is read | Result |
| --- | --- |
| PR opened since the first observation, skipped at the roster end by a closure | read from the tail page and freshly evaluated |
| 100 or more PRs opened since the first observation | `REMOTE_CENSUS_INCOMPLETE` |

`_open_pull_roster_semantics` now requires exactly these five query keys, with `sort=created` and `direction=asc`. A conditional replay of any other roster URL, including the old three-key URL and `direction=desc`, is unprovable and keeps the changed-representation refusal. The tail page is a plain read and is never replayed conditionally.

Second-observation revalidation (`_revalidate_collision_census`, the conditional path where every first-pass record has an identity). A first-pass PR missing from the second roster is read with one `repos/{repo}/pulls/{n}` call:

| Direct read | First-pass disjoint PR | First-pass colliding PR |
| --- | --- | --- |
| not an object | `REMOTE_PROOF_CHANGED` | `REMOTE_PROOF_CHANGED` |
| a different PR number, or an invalid identity | `REMOTE_PROBE_FAILED` | `REMOTE_PROBE_FAILED` |
| `state` not `open`/`closed` | `REMOTE_PROOF_CHANGED` | `REMOTE_PROOF_CHANGED` |
| `closed` | dropped from the census, as before | `REMOTE_PROOF_CHANGED`, as before |
| `open`, identity unchanged | first evidence reused | first evidence reused |
| `open`, identity moved | files re-read; a collision refuses | `REMOTE_PROOF_CHANGED`, as before |

The rows are checked in table order, so the PR number is checked before the state. So the direct read decides exactly as a roster row would. PRs that appear only in the second roster are still freshly evaluated. Re-reading the whole roster on a duplicate was considered and not added: oldest-first leaves only reopens before the cursor, and nothing in Macro's automation reopens PRs.

## Preserved semantics

- The pure verifier `control_plane/source_continuity.py` is unchanged. Receipt, refusal and writer-gate schemas are unchanged.
- The duplicate check still refuses `REMOTE_PROBE_FAILED`. Deduplicating would be unsafe: a duplicate and a skip in the same read would silently lose a row.
- Page size, the 16-page cap, the 1,500-PR cap, the short-page stop, every call, byte and time budget, and the bounded read retry are unchanged.
- A colliding PR still may not move or close between observations. A closed disjoint PR still drops out only after a direct read proves it closed.
- The identityless and legacy second-observation paths still re-run the full census and compare snapshots. They pick up oldest-first paging but not the direct reads.
- Cost: one call for the tail page on every roster read, so two per run. One extra call per first-pass PR missing from the second roster, which is at most the number of PRs that closed during the run. A colliding PR that closed now costs one direct read before it refuses.

## RED-first evidence

Against the #1983 head source (`0f7bcfc84`):

- A scenario probe against the new churn fake (`tests/test_source_continuity_roster_order.py`, 249 foreign PRs over three pages) reproduces the live failure. A PR opened mid-read in either observation ends rc=2 `REMOTE_PROBE_FAILED`. A closure mid-read in the second observation ends rc=1 `REMOTE_PROOF_CHANGED`, because the skipped open PR's direct read was taken as proof of change.
- 19 of the 25 new cases fail, including every scenario case. The 6 that pass on both sources are `_open_pull_roster_semantics` rejections of queries the old three-key check also rejected: `direction=desc`, `sort=updated`, a missing `sort`, page 17, a repeated key and an extra key.
- With only the roster URL reverted, so that the fake recognises the old query, the two re-prove cases in `tests/test_source_continuity_relevant_collision_semantics.py` fail: a missing disjoint PR and a missing collider, each with a direct read still reporting it open. The new moved-collider case and all the other cases pass on both sources.

The tail page repairs an independent review finding against `e6def1df7`: a PR opened after the first observation and then skipped at the roster end by a closure was never evaluated. Against `e6def1df7`, 11 of the 35 roster-order cases fail:

- the exact-query case, because no tail page is read;
- a new PR skipped at the roster end, disjoint or colliding: its files are read 0 times instead of once, so the PR is never evaluated and a colliding one goes undetected;
- a full tail of only new PRs ends rc 0 instead of rc 2 `REMOTE_CENSUS_INCOMPLETE`; the 99-row guard case fails only because no tail is read;
- six malformed tail pages (not a list, more than a page, a repeated row, a non-object row, a bool number, a zero number) end rc 0 instead of rc 2 `REMOTE_PROBE_FAILED`.

Removing the floor from either re-census call site, identityless or legacy, fails that path's 100-PR case in `test_full_tail_of_new_prs_leaves_a_full_second_census_incomplete` in `tests/test_source_continuity_macro_scale.py`: rc 1 `REMOTE_PROOF_CHANGED` instead of rc 2 `REMOTE_CENSUS_INCOMPLETE`.

Under the new source, all 714 `tests/test_source_continuity*.py` cases pass.

The new tests pin:

- the exact oldest-first query and the newest-first tail page, sent identically by both observations;
- a PR opened since the first observation and skipped at the roster end, read once from the tail page; a full tail of only new PRs is incomplete on all three second-observation paths, and a malformed tail fails closed;
- a PR opened mid-read in either observation appended once and freshly proved, with no direct reads; a colliding one refuses `REMOTE_PROOF_CHANGED`;
- a closure mid-read that skips a disjoint PR or a collider: exactly one direct read of the skipped PR, a receipt, and the collider still reported;
- a skipped PR that moved, closed, names another PR, or reports an unknown state;
- a collider skipped by the first roster but present in the second refuses, as a new collision;
- the residual reopen-before-cursor duplicate still refuses `REMOTE_PROBE_FAILED`;
- `_open_pull_roster_semantics` accepts only the five-key oldest-first query, in any key order.

## Exact source scope

1. `scripts/source_continuity.py`: the roster query and the tail page in `_read_open_pull_roster`, `newest_known` passed from both second-observation paths, the query check in `_open_pull_roster_semantics`, and the missing-PR branch in `_revalidate_collision_census` with its number-first check
2. `tests/test_source_continuity_roster_order.py` (new)
3. `tests/test_source_continuity_relevant_collision_semantics.py`: the open-but-missing case inverted from a refusal to a re-proof, a moved-collider case added, and the fake serves the tail page
4. roster URL and tail-page fixtures in `tests/test_source_continuity.py`, `tests/test_source_continuity_r3_hardening.py`, `tests/test_source_continuity_saturated_foreign_pr.py`, `tests/test_source_continuity_read_retry.py`, `tests/test_source_continuity_census_budget.py` and `tests/test_source_continuity_macro_scale.py` (call totals up by two per run); the estate fake takes `opened_between`, and the macro-scale file pins the floor on the identityless and legacy paths
5. this plan

## Residual risk

- Offset paging still skips a row when an earlier row closes mid-read. A PR skipped by both observations' rosters and older than the tail page is missed by the census, as before this change. That needs two specific events at the same page boundary inside a few-minute window. A PR opened between the observations and then skipped is read from the tail page; if 100 or more PRs open in between, the census refuses `REMOTE_CENSUS_INCOMPLETE` instead.
- The subject PR skipped by the second roster still refuses `REMOTE_PROOF_CHANGED`. The identityless and legacy paths still refuse `REMOTE_PROOF_CHANGED` after a skip. Both are fail-closed.
- A reopened PR older than the cursor still duplicates a row and refuses `REMOTE_PROBE_FAILED`.
- A PR closed during the first observation, reopened afterwards at or past the cursor, and then skipped by a closure in the second roster read is never evaluated. It is not a first-pass record, so it gets no direct read, and it keeps its creation place, so the tail does not reach it. A colliding one would go undetected. On `0f7bcfc84`, newest-first, the same skip had the same result, so this is not a regression; an independent re-review of `a67ca88ec` found it. In the conditional path, the reopen must also come after the first observation's conditional replay. A `sort=updated&direction=desc` tail with a floor at the first observation's start time would cover reopened and new PRs together. On 2026-11-03 at 08:50Z, Macro's 100 most recently updated open PRs spanned 11.6 hours, and 34 were updated in the past hour, so such a floor would rarely refuse. It would add a dependency on the local clock against GitHub's `updated_at`.
- GraphQL cursor pagination would be stable against both inserts and closures. It would change the transport, its budget accounting and the conditional-replay proofs, so it is out of scope.
- A live run has not exercised this change yet. One real-path run at Macro scale is the remaining proof. The token is shared, so that is at most one run.

A merge grants no runtime, deployment, ranking, serving or trading authority.
