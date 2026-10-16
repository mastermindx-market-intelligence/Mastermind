# Commission 10 — discriminating validation specification

**Status: proposed acceptance specification, not implemented production tests.** The research publication may validate the arithmetic examples and document/reference structure. It does not claim that a production ownership adapter has passed T01–T60, that a real market backtest was run or that an evidence family earned authority.

The implementation owner must translate these cases into the incumbent owners' accepted schemas and typed states. State names below describe required meaning; they are not authorization to invent a second state vocabulary. Each implemented case must bind an exact fixture, expected response, command, result, source commit and reviewer-visible failure counterexample.

## 1. Temporal and knowledge-cut tests

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T01 | June 30 13F accepted August 14; query July 1 | Unavailable for prediction on July 1 | Quarter-end look-ahead |
| T02 | Public August 14, retained August 15; operational cutoff August 14 | Unavailable operationally; public-reconstruction mode may qualify under its separate policy | Backdated first observation |
| T03 | Previous-period selected catalog published after the cutoff | Two-period observation cannot qualify | Checking only the latest raw filing |
| T04 | Current raw receipt retained but current catalog generation not published | No positive owner-row result | Raw availability mistaken for compiled availability |
| T05 | Required identity/denominator/corporate-action generation becomes usable after cutoff | Dependent derived result withheld | Late dependency leakage |
| T06 | Public archive from 2019 first captured in 2026 with proved original public timestamp | May support labeled public reconstruction; actual observed_at remains 2026 | Blanket backfill rejection or false operational history |
| T07 | Original source at t1, later correction at t2; query between them | Original information set selected; latest-corrected view separate | Hindsight correction |
| T08 | Only a date is available; intraday cutoff inside that date | Apply accepted conservative native date-grain policy, not invented midnight | False timestamp precision |
| T09 | Filing after regular close; only daily prices available | No entry at the preceding close; use declared next tradable observation | Unexecutable announcement return |
| T10 | Identity epoch ends exactly at cutoff; successor begins then | Respect half-open interval and knowledge eligibility | Double selection at boundaries |
| T11 | Quarter-end snapshot followed by silence | Show stale last-disclosed inference, not proved continuous economic ownership | Snapshot-as-interval fabrication |
| T12 | Valid raw receipt without a selected security/row binding | Pointer-only/insufficient binding; cannot supply a share quantity | Source reference laundering |

## 2. Filing lineage and disclosed-position tests

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T13 | 13F restatement replaces the effective disclosed book | Later cutoff selects restated generation; earlier cutoff retains original | Amendment overwrite of history |
| T14 | Additional-holdings amendment adds rows rather than restates | Correct additive composition or typed unsupported composition; never generic replacement | Wrong amendment type |
| T15 | 13F-NT notice references another manager | Relationship/notice state, not zero holdings | Notice treated as liquidation |
| T16 | Current-quarter manager has not filed | Missing/pending and excluded from paired comparison | Pending filer treated as seller |
| T17 | Prior small holding absent from current report where optional omission is possible | Not-redisclosed/uncertain, not confirmed full exit | De minimis omission treated as a trade |
| T18 | Public incomplete report and later confidential-position release | Incomplete flag and later public-knowledge generation | Confidential holdings backdated |
| T19 | Shared-discretion/other-manager references cannot be reconciled | Retain relationships; withhold unsupported independent sum | Parent/filer double counting |
| T20 | Duplicate or malformed source row sequence with distinct original ordinals | Preserve source rows; ambiguity explicit | Silent row collapse |
| T21 | Amendment filed after January 3, 2023 for an earlier report period | Interpret applicable filing/form unit convention, not period-only convention | Thousand/dollar discontinuity |
| T22 | Value unit unproved but share quantity otherwise qualified | Share-only context may qualify; value/weight remains unavailable | Heuristic unit promotion |
| T23 | Split, ADR-ratio or share-class change between reports | Bind PIT adjustment; otherwise block comparable-change claim | Corporate-action false buying/selling |
| T24 | SEC row and vendor-normalized copy with same accession/source row | One source observation root, no second confirmation | Duplicate evidence amplification |

## 3. Identity, denominator and replay integrity

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T25 | Current security row exists but no qualified predecessor | Insufficient history, not zero predecessor | False initiation magnitude |
| T26 | Two filers belong to one unresolved or overlapping complex | Exact eligible/excluded cohort; no invented independent breadth | Counting filers as decisions |
| T27 | Parent/strategy mapping learned in 2026 is offered to a 2024 cutoff | Exclude from operational historical identity set | Current-map survivorship |
| T28 | Issuer denominator is zero, later-dated or wrong class | Ownership fraction unavailable, not infinity or a capped ratio | Denominator mismatch |
| T29 | Deduplicated covered holders plus a separate overlapping 13D stake | Calculate covered-plane concentration separately; do not add legal planes | Mixed beneficial/discretion ownership |
| T30 | Catalog predecessor changes or a parser fix is presented under an old receipt | Exact generation binding/refusal; old receipt remains replayable | Mutable pointer or parser-vintage substitution |

## 4. Insider and beneficial-ownership tests — later source wave

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T31 | Form 4 P transaction explicitly described as private | Reported purchase, not verified open-market purchase | P-code overclaim |
| T32 | Form 4 S transaction explicitly private or with ambiguous terms | Separate reported sale state; no automatic market-sale inference | S-code overclaim |
| T33 | Grant, option exercise, tax withholding and gift rows | Separate transaction economics, not P/S-style conviction | Acquisition/disposition flag misuse |
| T34 | Form 4/A corrects one row while other original rows stand | Preserve unaffected transactions; replace only evidenced affected items | Whole-form replacement error |
| T35 | Derivative acquisition plus related exercise/disposition | Retain table/footnote linkage; no double-counted cash-equity purchase | Derivative/unit netting error |
| T36 | Plan flag unavailable in old data; later bulk extract adds it | Unknown remains unknown under original vintage; later extraction separately versioned | Missing plan flag treated as false |
| T37 | Covered FPI officer after March 18, 2026 and a conditionally exempt case | Versioned eligibility and order conditions; Form 3 not a purchase | Coverage-break pseudo-signal |
| T38 | New 13D without source-supported activist objective | Beneficial/purpose event with uncertain intent, not successful activism | Form label substituted for mechanism |
| T39 | QII, passive and exempt 13G filings with differing threshold changes | Correct historical category/deadline rules; actual public clock used for research | One universal 13G lag |
| T40 | 13D/A reports a new acquisition versus corrects an earlier percentage | Different economic-event and correction lineage | All amendments treated as factual corrections |

## 5. N-PORT/publication tests — later fund wave

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T41 | Current-regime third fiscal-month report filed publicly before its ordinary deadline | Use evidenced actual public filing time, not automatic deadline time | Deadline substituted for availability |
| T42 | First/second fiscal-month N-PORT submission is nonpublic | No public predictive feature | Nonpublic information leakage |
| T43 | Fund fiscal quarter differs from calendar quarter | Correct source quarter/month and comparison cohort | Calendar-quarter mismatch |
| T44 | February 2026 proposal treated as enacted | Reject rule-version selection; retain proposed status | Proposed law used as current data regime |
| T45 | Deferred 2024 monthly-public cadence applied in 2026 | Reject historical monthly-public assumption and threshold conflation | Future regulatory history invented |
| T46 | Multiple fund share classes point to one portfolio | Count portfolio holdings once; class state remains separate | Duplicated fund holdings |
| T47 | Later N-PORT amendment corrects a past portfolio | Later knowledge generation only; original cutoff unchanged | Corrected backtest |
| T48 | Public record omits restricted/miscellaneous or otherwise nonpublic detail | Incomplete coverage, not zero position | Public subset mistaken for complete book |

## 6. ETF residual and issuance tests — later fund wave

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T49 | Q0=100, S0=1000, S1=1100, Q1=110 | Residual exactly zero | Pro-rata scaling called active purchase |
| T50 | Same inputs except Q1=115; custom basket can explain five shares | Residual five, intent unverified | Causal interpretation from algebra alone |
| T51 | Gross creations and redemptions offset to zero net shares | Net issuance zero; gross volumes unknown unless separately observed | Net data treated as gross flow |
| T52 | Missing/proxy S, S0=0, or class shares paired with full portfolio | Typed unavailable/non-intent or unresolved basis | Fabricated true-S residual |
| T53 | Underlying security and fund unit splits | Normalize each evidenced unit basis independently | Split-induced residual |
| T54 | After-close unofficial trade notification omits offerings/redemptions | Partial transaction evidence at publication time; reconcile, do not infer full tape | Sponsor email treated as complete execution ledger |

## 7. Consumer, authority and outcome gates

| ID | Fixture / perturbation | Required result | Failure detected |
|---|---|---|---|
| T55 | Two projections of one filing enter company context and research narrative | Same receipt/event dependency retained; no extra vote | Consumer multiplicity mistaken for independence |
| T56 | Source unavailable versus quiet day with no new filing | Distinct native health states and retained last-good context | Empty success hiding outage |
| T57 | Rights-blocked source or restricted payload requested by a public view | No prohibited payload/derived use; typed blocked state | Readability treated as display license |
| T58 | Adapter attempts source publication, portfolio write, rank/gate or authority change | Refused; new authority booleans remain false | Research adapter becomes decision plane |
| T59 | Late or unmatured outcomes supplied during feature/roster selection | Refused by existing experiment protocol; no parallel outcome ledger | Outcome leakage or trial-budget evasion |
| T60 | Claimed real consumer projection cannot reproduce selected rows/cutoff | Fail acceptance or label hermetic-only; exact receipt/path required | Schema-only proof presented as end-to-end delivery |

## 8. Worked synthetic examples for report verification

These examples test reasoning and arithmetic, not repository code. All identifiers and numbers below are synthetic.

### X1 — max-of-dependencies

A filing is public at 14:00 UTC; raw receipt retained at 14:05; prior catalog at 13:00; current catalog at 14:07; required identity mapping at 14:10; actual projection ready at 14:12. Its operational usable time is no earlier than **14:12**. At 14:06 the raw receipt exists but the projection is not admissible. Public reconstruction under a declared historical latency policy is a different result, not proof that this system acted at 14:00.

### X2 — true-S residual and non-identification

With Q0=100, S0=1000 and S1=1100, expected proportional holdings are 110. Q1=110 produces residual **0**; Q1=115 produces residual **5**. Both a discretionary five-share trade and a five-share non-pro-rata basket adjustment are compatible with the latter numbers. The arithmetic alone cannot choose the mechanism.

### X3 — concentration bases

Two disjoint covered holders own 30 and 20 shares of a 100-share class. Covered fraction is **0.5**. Covered-holder HHI is **0.6² + 0.4² = 0.52**. The issuer-denominator square sum is **0.3² + 0.2² = 0.13**. The other 50 shares are unobserved; their distribution cannot be invented. Adding an overlapping 30-share beneficial-owner report would not establish 80% independent coverage.

### X4 — finite experiment budget

Eight primary specifications plus two secondary horizon checks for each primary plus two exploratory interactions yield **8 + 8×2 + 2 = 26**. Only the eight primary tests participate in the first confirmatory family under the stated correction; descriptive/interaction findings do not self-promote.

### X5 — source versus operational time

A 2019 source archived publicly in its original version but collected in 2026 has `observed_at` in 2026. A public-opportunity reconstruction can use a proven 2019 public clock under a declared policy. An operational replay cannot pretend the 2026 capture happened in 2019. This is a mode distinction, not a missing-value fill.

## 9. Promotion record and refusal conditions

A future accepted test result must include the exact source and candidate code commits, input hashes, replay mode, immutable generations, dependency cutoffs, expected/actual output, missingness and rights, test-command exit status and any independently reviewed real-source receipt. A documentation checker is not a production test runner, and a synthetic fixture is not a real portfolio observation.

Stop the implementation slice if it requires a new raw store, weakening K1 clocks, bypassing owner-native row binding, an unapproved data source, portfolio authority or unavailable rights. Complete independent hermetic work and return the exact gate; do not turn a blocked real-source read into an invented successful projection.

For the research publication itself, [VALIDATION_RECEIPT.json](VALIDATION_RECEIPT.json) records only the checks actually executed. T01–T60 remain proposed until separately implemented and run.
