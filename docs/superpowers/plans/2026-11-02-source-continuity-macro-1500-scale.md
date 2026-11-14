# Source Continuity Macro-1500 Scale Implementation Plan

**Predecessor:** `2026-09-24-source-continuity-macro-490-scale.md` (Mastermind #346 line) and #938 (Macro census byte ceiling)
**Consumers:** release gate 4 for the Macro vertical carriers (macro#7870, macro#8250), currently met by a manual five-leg substitute
**Capability ceiling:** source-only until normal review and release gates

## Goal

Make the read-only collision census complete at Macro's real scale. On 2026-11-02 Macro had about 903–907 open PRs, while protected source refused at 491. Every census against a Macro carrier therefore ended rc=2 `REMOTE_CENSUS_INCOMPLETE`, so gate 4 has been met by hand.

The census keeps covering every open PR. It does not sample, cache, cursor or skip rows. It still refuses `REMOTE_CENSUS_INCOMPLETE` when the estate exceeds the ceiling or any budget runs out.

## Bound evidence

A read-only production-path measurement of macro#7870 on 2026-11-02 used the stdlib transport, four workers, conditional roster revalidation and every ceiling lifted. It recorded:

| quantity | measured | old budget | result under old budget |
| --- | --- | --- | --- |
| open PRs | 903 | 490 | refused at roster |
| logical HTTP calls | 1,537 | 1,152 | over |
| normalized bytes | 286,139,447 | 134,217,728 | over |
| wall clock | 277.13 s + 8.75 s | 300 s | 95% used |

Call breakdown: subject files 2. First census 1,525: roster 10, files 1,081, compare 9, commits 18, trees 407. Second census 10 (roster only). Latency p50 0.535 s, p95 1.17 s. Largest response 2,830,536 bytes, under the unchanged 5,000,000-byte cap. 50 foreign PRs needed more than one files page (179 extra calls), and 9 were saturated at page 30.

Measurement caveats. The totals exclude the tree proof of saturated PR 7084, which timed out once (about 50 calls). The second census stopped after its 10 roster calls because a collider had moved (`REMOTE_PROOF_CHANGED`), so it measured the roster-only reuse cost, not a full second pass.

Shipped-caps real-path run (2026-11-03 00:35Z): macro#7870 at `d418ed38`, 908 open PRs, production transport, no ceiling lifted. The first observation ran 1,561 calls, 269,848,038 normalized bytes and 465.6 s. All three are inside the new budgets, and the run got past the old 491-PR refusal. It then ended `REMOTE_PROBE_FAILED` on one failed read. The transport does not record which read failed. The network was slow during the run (465.6 s against 277 s for a similar call count), and the next API call hit a TLS handshake timeout. So the caps no longer bind, but this run does not prove a completed census.

The old roster loop also shared `_MAX_PAGES = 10` with subject-PR files. A roster stops only at its first short page, so 1,000 or more open PRs could never complete, whatever `_MAX_COLLISION_PRS` said. The new roster gets its own `_MAX_ROSTER_PAGES`.

## Closed profile

```text
max open PRs:              1,500
max roster pages:          16  (= 1,500 // 100 + 1, the empty page proves completion)
max logical HTTP calls:    4,096
max normalized bytes:      768 MiB
cooperative time:          900 s
per-response body cap:     5,000,000 bytes (unchanged)
foreign PR workers:        4 (unchanged; GitHub secondary limits)
subject-PR file pages:     10 (unchanged)
```

Scaling the 903-PR measurement linearly to 1,500 PRs gives 2,553 calls, 475 MB and 475 s. The budgets leave 1.60×, 1.69× and 1.89× headroom. A complete 1,500-PR census costs about half of a 5,000/hour REST token, which callers that share a token must plan for.

That headroom is for the reuse path. With a conditional transport (production `_stdlib_http_get`), the second observation replays the strict reads by ETag, re-reads only the roster, and re-proves only foreign PRs whose identity moved or is new. If any foreign roster row has no parseable identity, such as a deleted fork with `head.repo: null`, the second observation is a full re-census. Scaled from the live numbers, that path exhausts the call budget near 1,210 open PRs, bytes near 1,380 and time near 1,470. Past that it refuses `REMOTE_CENSUS_INCOMPLETE`, fail-closed. On 2026-11-03 none of Macro's 908 open PRs had a null head repository, and at 908 even the full re-census fits (about 3,070 calls).

A run that exhausts the call budget costs up to 4,096 reads, about 82% of a 5,000/hour token. The cooperative 900 s budget can overrun by one in-flight read (at most 20 s), so callers need a timeout of at least 920 s. That is longer than a 600 s foreground tool limit, so run long censuses in the background.

## Preserved semantics

- One invocation-wide call, byte and time budget still spans both observations.
- Open-roster and subject-PR semantic revalidation remain fail-closed.
- The saturated foreign-PR tree proof and page-30 sentinels are unchanged.
- Malformed, incomplete, colliding, identity-moving, budget-exhausted and second-moving observations keep their existing treatment. A collider that moves between the two observations still yields `REMOTE_PROOF_CHANGED`, as in the live run.
- Receipt and writer-gate schemas are unchanged. The change adds no cache, retry, cursor, GraphQL path, repository-specific profile, persistence, auth widening or authority.
- The 1,501st open PR refuses `REMOTE_CENSUS_INCOMPLETE` before any foreign-file enumeration, and the roster never reads beyond page 16.

## RED-first evidence

Run against protected master source, the updated tests fail on: every estate from 491 to 1,500; the 1,501+ refusal at 16 roster pages; the closed profile; the measured-profile scaling; the 768 MiB byte boundary; the 900 s timeout clip; the about-1,000-PR live-fanout estate; and the 1,500 exact and one-under call and byte discriminators. Under the new source, all 584 `tests/test_source_continuity*.py` cases pass (580 before the review repairs below).

The roster page ceiling is discriminating: with `_MAX_ROSTER_PAGES` forced to 10 a 1,000-PR estate refuses, and with 15 a 1,500-PR estate refuses.

Review repairs (independent review, PASS_WITH_MINORS). A conditional, parallel estate fixture with full identity rows pins the production reuse path at 1,000 and 1,500 PRs. Each foreign PR is read once, the roster twice, and every strict read is replayed by ETag. A deleted-fork row pins the full-re-census fallback. The census worker count now reads `_FOREIGN_PR_WORKERS`, and a test that sets it to 1 fails against the old hard-coded `min(4, ...)`. The large-fanout refusal is pinned to the call budget (exactly 4,096 transport reads).

## Exact source scope

1. `scripts/source_continuity.py`: the profile constants, the two roster reads that used `_MAX_PAGES`, and the census worker count
2. `tests/test_source_continuity_census_budget.py`
3. `tests/test_source_continuity_macro_scale.py`
4. `tests/test_source_continuity_base_branch_semantics.py`
5. `tests/test_source_continuity_saturated_foreign_pr.py`
6. this plan

## Residual risk

Both live runs at this scale lost one read. The measurement run hit a 20 s timeout on a saturated PR's `git/trees` read (macro PR 7084; re-probe 0.56 s). The shipped-caps run failed on a read the transport did not identify. Right afterwards a single 22 KB read of PR 7084 took 8.8 s. The census has no retry, and `_stdlib_http_get` raises a bare `_RemoteProbeError` that drops the cause. At about 1,560 reads, one slow or failed read therefore ends the run fail-closed with `REMOTE_PROBE_FAILED`. That is the correct refusal, but gate 4 will not complete reliably at Macro scale until there is a bounded retry for idempotent transient failures (timeouts and 5xx, inside the shared budget) and a recorded failure cause. Both are out of scope here.

The roster uses offset paging (`page=N`). A PR opened or closed while the roster is being read can shift rows between pages, and sixteen pages widen that window compared with ten. A duplicated row refuses. A row skipped by one roster read is caught by the other observation's roster. A row skipped by both reads goes unnoticed. That needs two shifts that both land on the same row, and it was already possible at ten pages, so this change widens an existing risk rather than adding a new one.

The full-re-census fallback refuses above about 1,210 open PRs, as described under the closed profile.

A merge grants no runtime, deployment, ranking, serving or trading authority.
