# C10 — one native two-period ownership seam

Partial MAS-265 dossier. Verdict: **reuse K2-C for a bounded 13F read; delayed holdings, beneficial ownership, insider transactions and ETF residuals retain different meanings**. MAS-275 remains gated; this is not a P1 launch.

## Immutable originals and retained value

- C10A, [Mastermind #1235 report](https://github.com/mastermindx-market-intelligence/Mastermind/blob/35e0e5ae81d3c1f24c3644a80eec2e779a2d7a98/research/ownership_positioning/2026-10-04/REPORT.md), head `35e0e5ae81d3c1f24c3644a80eec2e779a2d7a98`.
- C10B, [Mastermind #1239 hardening](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e46ccc9862628d362e41e5c0eb3a51c8a4128b28/research/ownership_positioning_hardening_2026_10_04/FINAL_REPORT.md), head `e46ccc9862628d362e41e5c0eb3a51c8a4128b28`.

Retain both research returns. Their useful common thesis is that each disclosure plane needs its own legal/economic perimeter, period/publication/system clocks, corrections, denominator and explicit unavailable states. A missing public row is not a proven exit. Keep filer, manager, vehicle, issuer and security/class distinct, and avoid counting the same assets several times across legal planes.

## Current owner and actual source consumer

Macro pin: `9201f1602bfe47e05a63d61802fbed6f7f55a19d`.

| Surface | Verified role |
|---|---|
| [`lib/institutional_intelligence.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/lib/institutional_intelligence.py) and `contracts/institutional_intelligence/` | K2-B research-intent contract/compiler, not a new holdings source |
| [`lib/institutional_13f_adapter.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/lib/institutional_13f_adapter.py), `PilotRequest`, `resolve_generation`, `select_effective_filing`, `select_security_row`, `run_pilot` | Existing K2-C read-only two-period pilot over institutional-census catalog/storage/models, K1 and K2-B; no persistence, schedule or score/rank/gate authority |
| [`scripts/build_smart_money.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/scripts/build_smart_money.py#L735), `_load_institutional_census`, `_read_institutional_census` | Concrete Smart Money/Ownership Intelligence Desk reader of bounded `data/institutional_13f/public/census_latest.json`; distinct 13D/G wire and holdings axes |

K2-C requests one filer CIK, CUSIP, ordered prior/current reporting periods and an aware cutoff. It checks generation availability, filing lineage, share units and raw receipts. Named refusal reasons include `generation_not_knowable_at_cutoff`, `not_yet_knowable`, ambiguous filing/rows, unsupported amendment/unit and source-receipt mismatch. An actual store outage or digest failure propagates as an owner exception instead of being relabeled missing data.

The Program CEO independently inspected the adapter and concrete desk reader. The desk code is not proof that it currently consumes K2-C receipts. No live holdings, generated census, retained two-period artifact or deployed user path was read. A mature N-PORT-to-K1/K2 consumer was **not located in this bounded review**; this is not a complete-repository absence claim or zero N-PORT coverage.

## Dispositions and legal-plane constraints

| Disposition | Integration ruling |
|---|---|
| **RETAIN** | Delayed holdings versus current flows, generation/cutoff receipts, reporting perimeter and partial-coverage honesty; native K1/K2 ownership. |
| **CORRECT** | A 13F position disappearance is not an observed sale. Preserve the owner's absence/refusal and `not_redisclosed` meaning where supported, rather than infer an exit. |
| **CORRECT** | 13F investment-discretion holdings, N-PORT fund observations, 13D/G beneficial-ownership disclosures, Form 4 transaction rows and sponsor ETF observations are different planes. They cannot be summed into one ownership percentage or flow. |
| **REJECT** | P/S transaction codes alone as proof of open-market insider net buying; ETF quantity residual as identified trading/intent; current stored holdings as contemporaneous investor flow; automatic portfolio authority. |
| **SUPERSEDE, duplicate routing only** | Both reports feed one owner-native 13F integration decision. No second ownership graph/master/ledger or parallel C10 implementation program. Broader original acceptance obligations remain intact. |

The SEC's [April 2025 final delay](https://www.sec.gov/rules-regulations/2025/04/s7-26-22), rechecked on 2026-10-04, lists the 2024 N-PORT amendments' compliance dates as November 17, 2027 for groups with at least $1 billion and May 18, 2028 for smaller groups. The [February 2026 N-PORT action](https://www.sec.gov/rules-regulations/2026/02/s7-2026-05) is labeled **proposed** in the inspected official record. Neither a future amendment nor a filing deadline proves that a particular record was public at a historical cutoff. This is a source-availability constraint, not a new legal-compliance engine. It does not assert that no public N-PORT filings exist today.

## Bounded slice, collisions and acceptance

When MAS-275 prerequisites and current custody clear, choose one named existing company-context or desk consumer for the exact K2-C receipt. First reconcile any K2-C semantic-repair carrier; source presence and an old owner name do not clear a live writer. Do not automatically wire the legacy desk merely because it already renders holdings.

Required positive evidence: same filer and same security/unit/perimeter, two increasing periods, cutoff-knowable owner generations and filing tips, unambiguous original/amended lineage, bound raw source receipts and actual consumer disposition. Report **reported position change**, with share/value basis and coverage, rather than current flow or intent. Preserve correction and source/accepted/retained/derived clocks without conflating the timestamps.

Required negatives: missing prior/current record; absent versus ambiguous row; unsupported put/call/principal measure; manager/vehicle/legal-plane mismatch; unit/class or historical identity mismatch; unresolved amendment; later generation; missing required rights/clock; and any request for an inferred exit or predictive effect. Genuine owner read/digest exceptions must remain distinct from typed data absence. A valid reference or compiling pilot receipt alone does not prove a real consumer used it.

13D/G, insider, N-PORT, ETF residuals and graph materialization remain separately qualified families. Historical source receipts and data-health/coverage proof precede P1 use. Empirical information value belongs to existing evaluation owners, after synthetic integrity gates.

## Procurement, nulls, falsifier and supersession

No vendor was purchased/contacted or selected. Delivered historical filing versions, identity/manager mappings, correction policies, source-use rights, total cost and incremental value remain **UNKNOWN/NOT_TESTED** here. Official filing access does not establish all downstream data-use entitlements. Any paid candidate must identify the missing consumer-specific gap and outperform the cheapest adequate native baseline under lawful sample evaluation.

Falsifier: a current accepted K2-C-to-consumer receipt for a lawful two-period pair would discharge that bounded integration proof; it would not certify every plane or current flow. Null/partial coverage is valid. Defer a consumer that requires unprovable public availability, manager aggregation or security identity rather than manufacture a number. Keep both original reports unchanged; this addendum reconciles the two-period path and does not close C10, MAS-265 or MAS-275.
