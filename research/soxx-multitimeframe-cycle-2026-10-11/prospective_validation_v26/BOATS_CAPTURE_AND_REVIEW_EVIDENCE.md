# V26 — actual SOXX BOATS capture and evidence-bearing review

## What changed, and what did not

The repaired V26 source at `5379fa54570ecfb7120e6bcfa65e5d583b81fb20` passed hosted **CI 38359566182**. The earlier initial-V26 run 38357399667 was cancelled after supersession, not passed. V25's prior D8 representation repair remains preserved; no identity guard, workflow, runtime control or v2–v24 result was changed by this evidence phase.

This phase established actual SOXX quote/trade presence in the incumbent archive, completed an all-captured-segment audit, and tested the reliability of a returned independent-review program. It **did not** establish a full-year or full-session SOXX dataset, an independently profitable exit, PIT admission, executable fills, a new collector, production publication or live trading.

## Complete audit of the existing short capture

Canonical owner: **Macro Data OS**, existing M2 archive `/Volumes/Mastermind/market-data/tiingo`. The installed `lib.dataos.tiingo_boats_tape.audit_boats_tape` git blob `76bf3a6c723d5f2d80804336fe03a5da1d1c9d46` matched Macro main `e06f4d24279aa820c34bf69ed5315f501f55c4be`. The upstream accepted qualified-manifest SHA256 was `8bea6d46a5fbff25b441814bb18a360e6bd4b3edcfb2b28b9e6555ab9e035c0e`. Six loaded owner-source SHA256s were checked unchanged before and after inspection.

Original owner capture: `tiingo-boats-raw-20261013-01a12ab6`. Its **2,000,000 frames in 2,000 segments** span **2026-10-13 00:00:19.596058–00:09:30.354887 UTC**, or **October 12, 20:00:19–20:09:30 ET**. This is approximately nine minutes eleven seconds. It excludes the beginning and almost all of the rest of the overnight session.

The literal vendor key is `soxx`, not `SOXX`. The owner's earlier uppercase-zero reports remain immutable; they were case-sensitive selection observations, not evidence that no SOXX messages existed. The owner's later nine-name lowercase sample did not include SOXX. This consumer therefore performed the missing exact-symbol audit through the incumbent reader, without changing raw spelling or creating an alias/identity owner.

| Whole captured interval, literal `soxx` | Observed count |
|---|---:|
| Q quote messages | 2,926 |
| T trade messages | 142 |
| B trade-break messages | 0 |
| Total selected message observations | 3,068 |
| Intra-segment event-epoch ordering flags | 11 |
| Identical-frame-repeat flags retained | 4 |

These are **message observations, not deduplicated unique economic events**. Zero B messages in this short capture does not prove no corrections outside it. Repeat diagnostics are bounded to each report; no cross-report deduplication or cross-segment quote continuation is claimed.

The conservative same-segment prior-quote diagnostic, using the owner's unchanged 1,000-ms maximum age, partitions the 142 T observations into **94 fresh-prior-quote, 33 no-prior-quote, and 15 quote-event-time newer than trade-event-time**; there were no stale-prior-quote classifications. All 142 retained **unqualified sale-condition fields**. That flag means their interpretation has not been admitted; it does not establish that all trades are invalid. A late trade print and an earlier-received quote can have different event-time order. These diagnostics do not establish order marketability, future-information leakage in a particular strategy, consolidated NBBO, or a usable fill price.

### Bounded execution and source custody

The owner's maximum-thirty-two-captures audit contract was unchanged. Three preselected chronological first/middle/last 32-receipt reports were verified first. They contained 0, 64 and 75 selected SOXX messages respectively. Their metadata was reused, not recomputed. Sixty disjoint complement reports then covered the remaining 1,904 receipts. The resulting **63 bounded reports cover every one of the 2,000 original receipts exactly once**. Original raw bodies and L1 projection lineage were reverified by the existing owner function. The six module hashes did not drift.

The complete audit process, M2 PID 87563, finished **exit 0**. It made **zero vendor requests, zero credential reads, zero archive/materialization writes and zero raw-market-row exports**. Only metadata was saved outside the archive. No stream, history downloader, background collector, schedule or production service was started.

Retained complete metadata: M2 `/private/tmp/soxx1338_v26_owner_tape_full_20261013.json`, **91,218 bytes**, SHA256 **`10a38dfb96d485feda8745016ec12f6b7e6f8c62d19ab6baeff2b0db8d92ee17`**. Retained first-stage metadata: `/private/tmp/soxx1338_v26_owner_tape_20261013.json`, SHA256 **`ec500916c3d8775917bbff5bab8668b926599c3c226891a9a6abf8ebca45b725`**. The complete file binds all chronological offsets, receipt-reference digests, source hashes, quote-age classifications and limitations; no price or order-book rows appear in this public report.

For recovery, reuse these accepted metadata results. Re-audit only after a relevant source, method, receipt, clock or acceptance change. The missing historical-bars family remains distinct: the last qualified census had two AAPL/AMD REST receipts and **zero SOXX**; the later pathname-only check found only those same two files. Neither the nine-minute firehose nor broad EOD-history capture fills that gap.

The existing source request at [Macro #8698 / comment 6137771857](https://github.com/mastermindx-market-intelligence/macro/pull/8698#issuecomment-6137771857) was updated in place with these findings and the exact remaining need. It asks the incumbent owner for existing admitted SOXX history/access or the actual coverage/admission gate, including the earliest actually served date. It is not a duplicate acquisition command or permission to retry previously denied authentication/producer operations. The existing 53-request / 67-with-warmup plan remains only an offline plan.

## Independent review: inspect the test, not just its PASS

The first V26 review (`soxx1338-v26-code-review-20261013b`) returned a PASS later disproved by parent UTC-fold and arithmetic-overflow counterexamples. Those defects were repaired and all **39** focused synthetic tests passed before the successful CI on 5379fa5. The earlier code and negative research results remain recoverable; no inspected-year model was refitted.

The subsequent `soxx1338-v26-repair-review-20261013c` returned a complete program and claimed 19/19 checks. Its retained stdout SHA256 is **`99e4deb3f763c7c1e31be2adbcb707c820405ab73ad8078773329b23ace8bebf`**; exact returned program SHA256 **`e685f26023d83eb448ef00f6a2e3ce006c262d7c3b61306869afd4e01507f696`**. The byte-identical program is preserved at `tests/soxx_v26_review_falsifiers.py` as review evidence, including its incorrect count and weak UTC predicates. It is not an additional automatically accepted strategy test suite.

Parent execution of that unchanged program against the exact repaired module exited 0. A runtime observer counted **20 actual predicate calls**, of which **18 exercised the target module** and two merely compared Python constants. Its output nevertheless hardcoded `total=19`. More importantly, the same program also exited 0 after a task-private mutation replaced only `return value.astimezone(timezone.utc)` with `return value`. That proves its alleged UTC-fold coverage did not discriminate the broken behavior. The eighteen target predicates provide useful independent arithmetic/maturity evidence; the broad PASS and DST-coverage claim are **not accepted wholesale**.

A changed, narrow follow-on task, `soxx1338-v26-clock-falsifier-20261013d`, was submitted under the **same original root and parent `soxx1338-web-resume-20261013`**. Its acceptance criterion is a complete returned program that invokes the public helper APIs with one shared New York ZoneInfo object and both fall-back folds, passes the actual source, and fails the UTC-normalization mutant. It is not another broad summary review. At this evidence save its original normal-router MiniMax/mb launch was recorded, but no terminal result was available; the supported same-carrier current-output read returned `original_current_output_unconfirmed`. Do not relaunch or route around that read refusal. A later terminal return must be consumed and mutation-checked before any acceptance claim.

The **older** `soxx1338-accounting-review-20261013a` remains independently unresolved after `original_run_observation_unconfirmed`; it was neither duplicated nor displaced. A finished review program, active controller, published report, code CI and market-performance acceptance remain different facts.

## Remaining research boundary

The new helper prevents immature labels, silent removal of known episodes, false zero returns for unknown execution, improper partial-position costs, and misleading loss/profit accounting. It does not authenticate caller evidence, reconstruct missing entry universes, supply a statistical confidence model, or prove a funded portfolio's returns.

No genuinely independent cycle-failure **performance** sample was scored. The frozen prospective contract remains the next analysis design, with the old parent/stop/partial/horizon unchanged and the 30-minute and three-hour policies treated as separate claims. Longer source-qualified SOXX history, independent time/regime observations, point-in-time/correction/adjustment evidence and defensible execution/no-fill bounds remain outstanding. There is no live trading, model-originated sizing, accepted exit signal or production activation.
