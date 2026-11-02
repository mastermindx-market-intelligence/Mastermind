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

## Preserved semantics

- One invocation-wide call, byte and time budget still spans both observations.
- Open-roster and subject-PR semantic revalidation remain fail-closed.
- The saturated foreign-PR tree proof and page-30 sentinels are unchanged.
- Malformed, incomplete, colliding, identity-moving, budget-exhausted and second-moving observations keep their existing treatment. A collider that moves between the two observations still yields `REMOTE_PROOF_CHANGED`, as in the live run.
- Receipt and writer-gate schemas are unchanged. The change adds no cache, retry, cursor, GraphQL path, repository-specific profile, persistence, auth widening or authority.
- The 1,501st open PR refuses `REMOTE_CENSUS_INCOMPLETE` before any foreign-file enumeration, and the roster never reads beyond page 16.

## RED-first evidence

Run against protected master source, the updated tests fail on: every estate from 491 to 1,500; the 1,501+ refusal at 16 roster pages; the closed profile; the measured-profile scaling; the 768 MiB byte boundary; the 900 s timeout clip; the about-1,000-PR live-fanout estate; and the 1,500 exact and one-under call and byte discriminators. Under the new source, all 580 `tests/test_source_continuity*.py` cases pass.

The roster page ceiling is discriminating: with `_MAX_ROSTER_PAGES` forced to 10 a 1,000-PR estate refuses, and with 15 a 1,500-PR estate refuses.

## Exact source scope

1. `scripts/source_continuity.py`: the profile constants and the two roster reads that used `_MAX_PAGES`
2. `tests/test_source_continuity_census_budget.py`
3. `tests/test_source_continuity_macro_scale.py`
4. `tests/test_source_continuity_base_branch_semantics.py`
5. `tests/test_source_continuity_saturated_foreign_pr.py`
6. this plan

## Residual risk

The live run also saw one transient 20 s timeout on a saturated PR's `git/trees` read (macro PR 7084; re-probe 0.56 s). The census has no retry, so a timeout like this still ends the run fail-closed with `REMOTE_PROBE_FAILED`. That is correct but can be noisy. Retry is out of scope here.

A merge grants no runtime, deployment, ranking, serving or trading authority.
