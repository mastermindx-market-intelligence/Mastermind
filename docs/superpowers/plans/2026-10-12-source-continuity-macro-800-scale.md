# Source Continuity Macro-800 Scale Implementation Plan

**Operation:** `research-vault-source-continuity-capacity-20261012-sol-001`
**Canonical owner:** Mastermind issue #346 / Research Vault release blocker on Macro PR #8871
**Protected pickup:** `a858ac249296ffaa7bf523863dea5917bbbc1f24`
**Protected predecessor:** PR #982 merge `6eb1989d8d8a893cf1e3ef3650b1efc49a7393e0` (Macro-490)
**Capability ceiling:** source-only / evidence-only until normal review and protected release gates

## Goal

Restore the canonical Source Continuity proof path for the live Macro estate by extending the incumbent complete collision census from exactly 490 to exactly 800 open pull requests. Preserve all identity, collision, revalidation, receipt, retry, persistence, transport, lifecycle, auth, authority and release semantics.

At pickup, Macro had 704 open pull requests, so protected Macro-490 correctly refused PR #8871 with `REMOTE_CENSUS_INCOMPLETE` before foreign-file enumeration. Closing more than 200 unrelated PRs or bypassing the canonical receipt would be broader and less safe than a bounded capacity successor. This operation does not modify, replace, rebase or acquire source custody over Macro PR #8871, and it does not replace the separate moving-collider PR #974.

## Measured synthetic envelope

The existing accepted `EstateHTTP` harness was run against current protected code with only temporary in-memory resource overrides. The incumbent two-pass algorithm measured:

| Open PRs | Baseline calls | Accepted adverse fanout calls | Normalized bytes, adverse |
|---:|---:|---:|---:|
| 490 | 998 | 1,140 | 729,565 |
| 704 | 1,432 | 1,574 | 761,671 |
| 750 | 1,524 | 1,666 | 768,571 |
| 800 | 1,626 | 1,768 | 776,075 |

The adverse shape is unchanged from the protected Macro-490 qualification: 54 extra ordinary file pages plus 17 saturation sentinels on each observation. A 1,920-call ceiling leaves 152 modeled calls of headroom at 800. The 128 MiB normalized-byte ceiling, 300-second cooperative deadline, 5,000,000-byte response cap, page-30 foreign-file sentinel and four-worker read topology remain unchanged.

A real live #8871 canary remains an acceptance gate. One attempted local read-only canary command was explicitly refused before dispatch by the provider safety layer; reconciliation found no process, file, repository or GitHub effect. It was not retried or moved to another carrier.

## Closed profile

```text
max open PRs:              800
max logical HTTP calls:    1,920
max normalized bytes:      128 MiB
cooperative time:          300 s
per-response body cap:     5,000,000 bytes
open-roster pages:         10 (unchanged; at most 1,000 rows)
```

The 801st open PR must refuse `REMOTE_CENSUS_INCOMPLETE` before any foreign-file enumeration.

## Preserved semantics

- one invocation-wide call/byte/time budget spans both complete observations;
- subject PR, base branch and open-roster semantic revalidation stay fail-closed;
- every foreign PR remains included in the complete collision census;
- ordinary and saturated foreign-file proof behavior remains unchanged;
- malformed, incomplete, colliding, identity-moving, budget-exhausted or deadline-expired observations retain their current refusal behavior;
- receipt and writer-gate schemas remain unchanged;
- no cache, retry loop, cursor, GraphQL/POST production path, second verifier, repository-specific bypass, persistence, auth widening, lifecycle or authority is introduced;
- no merge, writer release, Ready transition or production publication follows from this scale change alone.

## RED-first evidence

Before production constants change, the successor tests must fail because protected code still reports 490 / 1,152 and refuses stable estates above 490. Tests require:

- stable 600, 704, 720, 750, 799 and 800 estates to complete;
- 801 and 1,000 to refuse before foreign-file enumeration;
- the exact closed profile to report 800 / 1,920 while bytes, time and body limits remain unchanged;
- the accepted adverse 800 shape to complete at exactly 1,768 calls with 152 calls of headroom;
- exact call- and byte-budget one-under discriminators derived from the 800 harness;
- existing deadline, saturation, base-movement, semantic-revalidation, receipt and authority tests to remain green.

## Exact source scope

Exactly these paths are permitted:

1. `scripts/source_continuity.py`
2. `tests/test_source_continuity_macro_scale.py`
3. `tests/test_source_continuity_census_budget.py`
4. `tests/test_source_continuity_saturated_foreign_pr.py`
5. `tests/test_source_continuity_base_branch_semantics.py`
6. this plan

The production delta is limited to:

```python
_MAX_COLLISION_PRS = 800
_MAX_HTTP_CALLS = 1920
```

## Completion boundary

Before source acceptance require:

1. discriminating RED evidence on protected 490 / 1,152 production;
2. focused scale/census/saturation/base suites green after the two constant changes;
3. complete `tests/test_source_continuity*.py` family green;
4. exact call/byte/deadline one-unit-under discriminators green;
5. compile, `git diff --check`, exact-six-path scope and protected-base compatibility proof;
6. a successful real read-only Macro estate canary using a lawful surface, including exact #8871 source identity and resource counts;
7. exact-head hosted CI/security and independent non-author review;
8. canonical Source Continuity `REMOTE_COMPLETE_VERIFIED` for this carrier;
9. terminal source acceptance, writer release and maintenance-only protected release.

After protection, PR #8871 must rerun its exact-head writer gate and canonical `REMOTE_COMPLETE_VERIFIED`. Only then may its lawful release owner record `HOLD-RELEASED`, mark the same PR Ready, merge by expected head, allow the existing renderer to publish, and perform live delayed/failure/no-JS/mobile/401 acceptance.
