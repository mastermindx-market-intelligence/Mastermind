# Commission 14 — Issuer Credit & Capital-Cost Intelligence

## Hardened research commission and bounded implementation recommendation

**Research cutoff:** 4 October 2026, UTC. **Status:** completed research recommendation; implementation and decision-authority promotion remain uncommissioned. **Mandate:** improve equity intelligence by explaining how credit conditions change an issuer's financing choices, cash flows and risk. Preserve the underlying observations and economic mechanisms; do not compress them into a generic bearish score.

This report supersedes the attached draft for this commission. It does not supersede existing Mastermind or Macro source law, accepted owner contracts, wave gates or portfolio authority. The audit included exact-revision source inspection, primary-source research, adjacent-project reconciliation and a synthetic execution of an existing pure debt extractor. It did not run a production pipeline, purchase or sample a paid feed, change portfolio behavior, or establish predictive alpha.

### Source custody and evidence boundaries

| Estate | Resolved repository | Inspected source snapshot | Protected head at final source recheck |
|---|---|---|---|
| Mastermind | `mastermindx-market-intelligence/Mastermind`, `master` | `a2646f458f9ff41ddcedd89b338be4a4349e6cd6` | `521720b09be2921e996d9396b522b1c4ca62041c` |
| Macro | `mastermindx-market-intelligence/macro`, `main` | `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3` | `59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc` |
| Terminal/charting | `mastermindx-market-intelligence/mastermind-terminal`, `master` | `1c708450187755160e1a5889b69598a2fcb1f0d1` | Same revision |
| Research Vault | Existing Macro estate, not a newly inferred repository | Same Macro snapshot | Same Macro final head; its own source and rights boundaries apply |

The commission header's `d1594f3c7ae750db3f14b4eebf0de3460f84267a` is not the protected Mastermind revision observed for this run. The attached draft already cited this run's bootstrap Mastermind pin, but that did not make its wider census complete. Bootstrap used the current `docs/sol_skills/INDEX.md` and required source-law files; skillpack schema `mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap major 1 was compatible. Source conclusions below refer to these revisions, not a claim that all live services ran successfully on the research date. Mutable pull-request status is recorded separately. [M01][M02][X01][T01]

The final recheck found one newer Mastermind commit and two newer Macro commits. Complete compare lists show no change to the inspected credit, financing, identity, portfolio or source-law paths. The changes add Trend Persistence C1 preregistration/records and harden the China THS collection/CI lane; the latter does not alter CCW, Capital Structure or F09 jobs. The new Trend document was reviewed for relevant historical-classification limits in B6. Original evidence retains its exact snapshot pin, and the separate drift receipts establish which conclusions carry to the final protected heads. Future implementation must still use then-current CI/source gates. [R01][R02][M13]

**Evidence labels:** *observed source* means code, contracts or committed artifacts were inspected; *executed research test* means the bounded synthetic test described in B; *documented vendor capability* means public product documentation, without a licensed payload or delivery audit; *proposal* means a future requirement or experiment. A declaration, schema, green validator or recent commit is not by itself end-to-end operational proof.

## A. Executive conclusion

### A1. Build on the existing capital-structure owner

Mastermind should develop an issuer financing evidence capability inside Macro's existing **Capital Structure and Credit Intelligence** program. The canonical program is `capital-structure-intelligence`; `ccw` is its alias. Existing Capital Structure V2, Corporate Credit Watch (CCW), Data OS identity and FIF accounting ownership already cover much of the architecture the draft proposed anew. The first priority is to qualify and connect those capabilities, including their historical source selection, instrument meaning, correction handling and consumer boundaries. Creating a parallel issuer-credit state store would increase reconciliation risk. [X02][X03][X04][X05]

The capability should answer five practical questions:

1. **What financing obligation actually exists?** Identify the obligor, guarantor, priority, principal, payment/reset dates, conditions and currency from qualified evidence.
2. **What changed in the price of comparable debt?** Separate a transaction, quote or evaluated price from changes in the risk-free curve, options, liquidity and instrument composition.
3. **When does that change affect this issuer's cash?** Model maturities, floating resets, hedges, cash resources, conditional facilities and feasible funding alternatives.
4. **What has the equity market already incorporated?** Compare credit evidence with contemporaneously available equity, options, filings, expectations and macro information.
5. **Does credit add useful information?** Establish incremental value against a strong contractual-financing baseline, with lawful history, honest clocks and an untouched evaluation period.

Keep refinancing need, funding-price change, cash-interest transmission, covenant pressure, distress acceleration, credit-equity divergence and capital-access improvement separately inspectable. A higher secondary yield can reflect rates or illiquidity without changing today's coupon. A refinancing can improve near-term liquidity while increasing future interest, encumbering collateral or diluting existing equity. The representation must support mixed outcomes.

### A2. Priority and recommended decision

**Accept the research direction and commission a bounded P0 qualification phase.** Its value is high for financing-dependent issuers and for avoiding false confidence in existing evidence. The value of a new paid market-credit feed remains conditional. There is enough source evidence to justify repairing historical eligibility and instrument semantics; there is not enough evidence to authorize a data purchase, a trading signal or a new risk gate.

The first eligible cohort should be USD nonfinancial corporate issuers with clearly identified, ordinary debt and usable disclosures. Include investment-grade and speculative-grade issuers in separately evaluated strata. Prioritize refinancing exposure, floating exposure, cash burn and liquidity constraints as testable economic hypotheses. Banks, insurers, structured credit, convertibles and complex hybrids need distinct methods before inclusion. This is a tractability choice, not a finding that their credit contains no equity information.

### A3. Material changes from the draft

| Issue addressed in this hardening | Hardened conclusion | Consequence |
|---|---|---|
| Incomplete census of issuer market credit | CCW already computes bond YTM/g-spread and issuer/theme/sector series from sponsor holdings | Qualify and reuse this lane before proposing another feed or engine |
| A new canonical issuer-credit snapshot | Existing owner and conceptual `capital_structure_state.v2` already exist | Extend owner contracts; no competing root state |
| Debt extractor treated as historically selectable | An executed synthetic case selects a future filing despite an earlier cutoff | P0 must bind eligible source versions before calculation |
| Sponsor-held maturity exposure could be read as issuer debt | Fund-held par is sampled portfolio exposure, not issuer principal outstanding | Separate the two quantities in contracts, labels and tests |
| Instrument-candidate status not reconciled with the incumbent owner | Existing W2B/W3A terms principally concern registration fee-table evidence | Do not infer issued debt, capacity, coupons or maturity from those candidates |
| Context-only labels assumed safe | Directional lens rows participate in confluence; the held-risk proxy can set severity | Initial context must remain outside reducers; prove output invariance |
| Long history equated with PIT history | Historical files, revised ratings and backfilled analytics have different availability | Require field/generation-specific eligibility and replay mode |
| Lead-lag review needs a contemporary replication target | Newer research supports conditional bond-to-equity transmission and changing CDS discovery | Add the July 2026 working paper and market-structure qualifications; preserve the draft's rejection of universal leadership |
| Small pilots or percentage-valid rows as promotion gates | Engineering coverage and statistical power answer different questions | Require every admitted row valid; estimate power and allow inconclusive results |
| Annual rate delta used as full cash-flow model | Timing, principal changes, reset terms, hedges, fees and accounting matter | Use period cash-flow scenarios and separate annual run-rate outputs |

These changes are grounded in the census, source landscape, contract design and experiment below. Full finding disposition and source receipts accompany this report in `HARDENING_AUDIT.md` and the evidence JSON files.

## B. Current-state census

### B1. Existing owners and actual build state

| Component | Observed capability | Qualification and material gap |
|---|---|---|
| Capital Structure and Credit Intelligence | Macro program registry owns corporate credit and capital-structure evidence; `ccw` resolves to it | Context-only owner; program registration grants no equity selection or sizing authority [X02] |
| Capital Structure V2 workstream | Existing owned paths, SEC evidence/term work, W2 proof dependencies, later W3/W4 gates | Current source records W2C/W2D as built but unproved; W3/W4 remain held. Historical owner label `coo-fable` is not a current writer lease [X03] |
| Conceptual issuer state | `capital_structure_state.v2` includes instruments, cash funding, transactions, uncertainty and change events | Architecture destination, not evidence that a complete issuer capital twin is operational [X04] |
| SEC evidence and term contracts | Retained-source manifest, source hashes, document term observations, parser and correction generations | Reuse exact lifecycle semantics. External receipt/proof dependencies remain material [X05][X06][X07] |
| W2B/W3A candidate terms | Registration fee-table amount, proposed price, aggregate offering value, fee/rate and exact evidence spans; candidate projection | Candidate evidence is not a resolved security or outstanding financing. Broader debt terms need explicit extensions and acceptance [X06][X08][X09] |
| F09 financing calculations | `debt_maturity.v1`, `cash_runway.v1`, `capital_need.v1`; debt/cash builders and caches | Reuse calculations subject to historical input selection, cash definition and source-clock qualification [X10][X11][X12][X13] |
| CCW market-credit lane | Five SSGA holdings inputs; YTM, g-spread, issuer/theme/sector/market series, bond panel, sampled maturity wall | Sponsor valuation basis; incomplete source-clock envelope, historical mapping and correction treatment [X14][X15] |
| Credit momentum | Velocity/acceleration and theme equity-credit sign quadrants | Descriptive output, not residualized issuer alpha; equity/credit terminal-date alignment requires repair before validation [X16] |
| Credit window | IG/HY aggregate OAS drift/range and MOVE context; `SCORED=False` | Macro financing climate, not evidence a particular issuer can issue [X17] |
| Covenant headroom | Existing view-model code | Committed health reports zero covenant observations/issuers; a model file does not prove populated, definition-correct coverage [X18][X19] |
| Data OS / FIF | Canonical internal issuer/security identities and existing accounting reuse map | Current identity is not historical lineage. CIK is source-filer identity, not the internal issuer key [X20][X21] |
| Mastermind held risk / lenses | Earnings expectation SUE/revision fields, financial-risk checks and evidence synthesis | No mature historical revision series is established merely by those fields; directional rows can influence confluence [M03][M04] |
| Portfolio V3 | Evidence independence, source receipts, decision snapshots and `balance_sheet_credit` family specified | Inspected design is `SPEC_ONLY`; exact snapshot implementation/consumption not proved by this bounded census [M05] |
| Terminal | Existing security overview with capital-structure debt/cash/EV context and sector-sensitive financial presentation | Reuse the existing context surface later; no separate credit warehouse is justified [T01] |
| Research Vault | Macro's private research ingestion, catalog/search and API estate | Research documents can support cited extraction hypotheses, not replace canonical market or contractual facts [X22] |

### B2. Corporate Credit Watch: useful machinery with distinct measurement limits

CCW consumes holdings for SPSB, SPIB, SPLB, JNK and SPHY, Treasury curve pillars, aggregate IG OAS and issuer/theme mappings. Its declared `corp_credit.v1` authority fields are all false. It already contains substantial pricing-convention checks, near-par callable exclusions and composition controls. Retain those investments and assess their coverage; neither their existence nor a passing output proves that all supported bonds have correct contractual terms or historical availability. [X14][X15]

The central distinction is **what the holdings measure**. A fund's par amount is its position in an issue. It is not the issue's full outstanding amount, and the fund basket is not the issuer's complete liability perimeter. The current maturity-wall calculation sums those holdings. Consequently, an apparent fall in an issuer's wall can result from a sponsor selling the bond. It need not indicate repayment or reduced refinancing needs. Aggregation weights based on held par likewise describe the sample, not issuer debt weights. Preserve sampled-market coverage separately from contractual liabilities. [X14]

Historical qualification is incomplete in concrete ways. Holdings rows have `as_of` but no complete retention/correction envelope; same-date revised sponsor files are skipped by a keep-first path; a missing source date can be guessed as the prior business day. Issuer matching uses current registry prefixes and then substring matches, with first match winning. Applying that registry across history can retroactively change issuer attribution. Derived series can be rebuilt with current mappings and calculations. These are specific P0 issues, not grounds to discard all existing CCW output. [X14][X15]

Credit momentum's displayed divergence is a theme-level sign quadrant. The inspected equity calculation uses the last 22 equity prices without proving that its endpoint matches the credit endpoint. It should remain a descriptive context observation until timing, issuer linkage and baseline residualization are qualified. [X16]

### B3. Completed temporal falsifier

The exact pinned `engine/debt_maturity.py` was executed as a pure function with two synthetic annual observations and an earlier requested cutoff. No production data or pipeline was used. The full input/result and source blob are retained in the evidence packet. [X10]

| Input or output | Value |
|---|---|
| Requested `as_of` | `2025-06-01` |
| Eligible old filing | `filed=2025-02-01`, accession `old`, next-12-month principal `100` |
| Ineligible later filing | `filed=2026-02-01`, accession `future`, next-12-month principal `999` |
| Observed extractor result | `selected_filed=2026-02-01`, `selected_accn=future`, `y1=999`, `status=reported` |

The code sorts candidate annual facts by filing/end date and selects the latest without filtering them by the requested cutoff. `as_of` participates in output dating/staleness, not eligible historical fact selection. **This falsifies a claim that the extractor alone is PIT-safe. It does not establish that a live downstream decision actually consumed future information.** `capital_need.py` rejects future-filed inputs, but cannot recover the eligible old fact after the upstream function discarded it. Optional downstream source-clock checks are also not proof when those clocks are absent. [X10][X11]

`cash_runway.py` has a similar latest-observation selection pattern. The debt builder's current per-CIK cache replaces JSON; today's cache is not an archive of all information sets. A future implementation should select an eligible retained source generation before invoking existing calculations and reject unprovable historical rows. It should not create a second debt ledger or reconstruct yesterday from current Companyfacts. [X12][X13]

### B4. Freshness, acceptance and generated census

Committed CCW `latest.json` and credit-momentum output are dated 10 September, with underlying data dated 8 September. The retained validator says PASS, but its iShares comparison has a 57-day date gap. A comparison between g-spread and index OAS is also not an OAS accuracy test: the measures, constituents and options treatment differ. These artifacts establish generated outputs and the validator's verdict at their own dates; they do not prove 4 October accrual, matched-day pricing quality, complete PIT eligibility or actual Mastermind consumption. [X23][X24][X25]

Capital Structure health, generated 26 September, reports durable ingestion verdict `ok` while the discovery horizon is `degraded_discovery`: expected SEC index date 25 September, latest discovered/compiled filing date 17 September. Covenant observations and covered issuers are both zero against 2,999 eligible exhibits. Overall ingestion health must therefore be separated from discovery freshness, field extraction coverage and consumer usability. This source observation is not a diagnosis of a present live outage. [X19]

Mastermind's static census is dated 16 July. This report is a fresh source recensus; it does not hand-edit that generated census or pretend to refresh production observability. Future acceptance should report last attempted/last successful source acquisition, source economic date, retention time, generation publication time, eligible issuer coverage and last consumer receipt as different fields. [M06]

### B5. Existing decision paths require stronger containment

In `portfolio/held_risk.py`, the interest-coverage proxy is CFO divided by 5% of long-term debt. Its comment describes a fallback, but the inspected block runs whenever the relevant raw financials/debt exist, without a guard that leverage ratios are absent. It can set a critical flag. The proxy does not measure reported interest expense, cash interest or contractual funding cost. Replacing it during a supposedly read-only evidence phase would change risk behavior; that belongs in a separately accepted consumer change. [M03]

`portfolio/lenses.py` includes directional non-bloc rows in confluence synthesis. Therefore attaching `authority=false` or calling a new row context-only is insufficient if its bull/bear direction reaches that reducer. P0 context belongs outside directional synthesis. Any later integration must demonstrate invariant confluence, held-risk severity, sizing, entry/exit, gates and settlement outputs under context perturbations before claiming zero authority. [M04]

The V3 design already names `balance_sheet_credit` as an evidence family. Reuse it and existing source-root/receipt conventions. An additional independent vote for bond price, its calculated yield, its spread, and a CDS curve inferred from the same bond would violate the purpose of independence controls. The inspected design and snapshot plan do not establish a fully live Decision Snapshot system; do not build a parallel one to compensate. [M05]

### B6. Adjacent plans and surviving gaps

| Existing carrier, observed 4 October | State at inspection | Required reconciliation |
|---|---|---|
| Macro PR #8308 | Open draft; head `446ffd0f1062dd064c0716b576ceba7ce90acf2b` | Prophet Cycle funding/original-equity recovery scenarios already consume capital need/share counts; coordinate financing alternatives [P01] |
| Macro PR #8397 | Open draft; head `f6443f34f66c434e2ebfffb37cb3ba568de9f2b6` | Bonds mechanism explanation under the existing credit-desk carrier; reuse evidence/view seam [P02] |
| Macro PR #7119 | Open draft; head `c68d8bd4296df18e35d98b16a7e06f3588c22288` | Old maturity persistence carrier; newer source evidence prevents treating its body as current absence [P03] |
| Macro PR #8051 | Merged 27 September; merge `5e0ebcb161b460d63252208f040067c6b922e805` | Read-only yield-momentum consumer already landed; not an open duplicate [P04] |

Mastermind's PIT fundamentals loader, single-name panel, research desk, bottleneck and thematic/trend research were also inspected. They provide existing integration and empirical machinery. The trend protocol records missing mature analyst-revision and individual-stock institutional-flow history and finer dynamic subtheme identity. Those remain documented limitations to test against current available histories, not eternal declarations of absence across all repositories. The loader's timestamp filter and delisted-universe work are useful, but do not automatically qualify every joined feature or eliminate data-selection bias. [M07][M08][M09][M10][M11][M12]

The existing `collectors/edgar_dilution.py` also detects selected shelf/prospectus filing occurrences into an accession-deduplicated event store with filing-date and first-seen fields. Its source establishes an adjacent detection seam, not normalized issued debt, refinancing terms or current live accrual. Preserve that detector's existing consumers; reconcile its accession references through the Capital Structure source owner when qualifying financing events. Do not extend it into a competing debt ledger or assume this report retires it. [X28]

The final Mastermind head adds the frozen Trend Persistence C1 preregistration. It describes a new sector substrate but explicitly records its sector labels as current, with `era_correct=False`, and identifies missing labels concentrated among future index leavers in its diagnostic dates. This is a dated statement in the adjacent preregistration, not an independent parquet audit by this commission. It strengthens the need to qualify historical sector controls and missingness, rather than assuming an artifact named PIT has era-correct labels. Preserve that family's frozen dates and tests; this commission does not rerun them or treat its current-sector labels as historical issuer-credit identity. [M13]

The confirmed gaps are a qualified historical issuer/obligation map; evidence-backed debt terms beyond registration candidates; correct historical source-version selection; contemporaneous market/reference observations; issuer-specific financing feasibility; populated covenant coverage; measured consumption; and incremental predictive validation. These are narrower and more actionable than an unqualified claim that Mastermind lacks credit data.

## C. State-of-the-art research

### C1. Credit leadership is conditional

Norden and Weber's historical study reports equity leadership of CDS and bond spreads in its early-2000s sample, with CDS often leading bonds. It establishes neither a universal current ordering nor economic causality from predictive sequencing. Kapadia and Pu's work explains why equity-credit differences can persist under liquidity, funding and arbitrage constraints; divergence need not be an exploitable equity mispricing. [S01][S02]

There is newer affirmative evidence. Hameed, Titman, Wei and Zhang's working paper, revised 23 July 2026, reports negative bond returns predicting equities, especially for low-rated issuers, institutionally traded bonds and lottery-like stocks, with stronger results where bond trading is high relative to stock trading. The primary abstract was verified; full-text sample construction, coefficients, costs and controls were not accessible in this investigation. Treat the result as a replication target, with those limitations visible. [S03]

OFR's 2024 research finds that single-name CDS leadership of bonds and downgrade anticipation weakened after post-crisis regulatory changes. It is a price-discovery result, not proof of equity alpha. The NY Fed's Global Credit Cycle work, revised May 2026, emphasizes common and nonlinear credit variation involving spreads and equity volatility. This makes a strong macro/equity-volatility baseline necessary before claiming independent issuer credit information. [S04][S05]

No primary evidence reviewed here establishes a stable ranking of GICS sectors where credit reliably leads equities. Direct research support for low-rating/institutional-trading cohorts should be distinguished from the following economic hypotheses:

| Test stratum | Plausible transmission to equity | Principal alternative explanation |
|---|---|---|
| Near maturities, limited cash, negative cash generation | Refinancing terms alter liquidity, interest and dilution choices soon | Bond weakness already reflects equity/filing information |
| Material floating or soon-reset debt | Benchmark or spread resets change cash interest without a new bond | Rates/hedges already explain the effect |
| Capital-intensive telecom/media, REITs, utilities | Long-lived assets and funding schedules create visible financing sensitivity | Duration, regulation, property/asset values and business shocks dominate |
| Cyclical industrial, consumer or energy borrowers | Operating stress and refinancing constraints can reinforce each other | Commodity/cycle factor double counting |
| Net cash and no near-term financing need | Useful comparison with weaker near-term interest transmission | Credit may still reveal business deterioration; do not assume zero information |
| Banks and insurers | Deposits, regulatory capital, bail-in hierarchy and liability structure matter | Industrial debt/FCF ratios are structurally inappropriate |

These are preregistered strata to evaluate, not recommended portfolio tilts.

### C2. Institutional design lessons

An institutional capability needs a security master, contractual cash flows, distinguishable market observations, valuation conventions, source/version lineage and a financing scenario layer. Commercial evaluated pricing improves coverage by combining observations and models; it does not turn every price into a transaction. Credit-market functioning should also be distinguished from spread level. The NY Fed Corporate Bond Market Distress Index and Federal Reserve excess-bond-premium work illustrate those separate macro questions. Reuse Macro's aggregate owner if additional controls are justified; do not create a second regime engine. [S06][S07][V01][V02][V03]

The useful research question is consequently not whether credit is generally smarter than equity. It is whether a particular observation, with a lawful and historically eligible timestamp, changes a financing forecast or an equity outcome after the information Mastermind already has is accounted for.

## D. Source landscape and acquisition decision

### D1. Comparison of realistic sources

**Reading the table:** public product documentation is evidence of an advertised/documented capability, not of an entitlement, licensed payload, current issuer match, historical replay or accepted all-in quote. Cost classes below are comparative procurement categories; no commercial price is invented. Rights require a purpose-specific entitlement record for storage, derived output, LLM processing and redistribution.

| Source | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| SEC filings, exhibits, filing XBRL | SEC reporting filers, including foreign filers; debt notes, agreements, prospectuses, actions | Accession documents; tagging/term coverage varies | Filing/API processing, not guaranteed identical clocks | Strong public event anchors; retained/parser history still required | Amendments, fact restatements and parser changes distinct | Public access; observe SEC access policy and embedded-content limits | Public; engineering substantial | Contractual debt, cash interest, issuance and covenants [S08] |
| Current SEC Companyfacts/Frames | Standard entity-wide taxonomy aggregates | Historical periods in a current payload | Current API/nightly bulk | Not an archived vintage store; Frames is last-filed | Current corrections can replace earlier interpretation | Same source boundary | Public | Discovery and current aggregates, with accession-bound selection [S08] |
| Existing SSGA holdings / CCW | Five fund samples; sponsor positions and valuations | Retained forward observations; history/coverage must be censused | Sponsor publication cadence; not transaction time | Incomplete current clocks/mappings; qualify before replay | Same-date update handling currently weak | Sponsor/internal/derived rights not established by public URL | Public-access inputs; rights and engineering gate | Qualified descriptive bond sample and cross-check [X14][X15] |
| FINRA TRACE live/EOD products | Eligible reported bond trades; product exclusions apply | Separate purchased historical products | Reporting and dissemination rules, not an execution-time feed | Original public price replay needs lifecycle/dissemination proof | Cancels/corrections/reversals and late reports | Product agreement; identifiers and redistribution separate | Published schedules plus integration/rights | Observed cash-bond transactions and liquidity [S09][S10][S11][S14] |
| FINRA enhanced/historic and Rule 144A | Rich delayed trade fields; 144A separate entitlement | Product-specific releases | Delayed historical release | Some fields were unavailable contemporaneously | Raw event status and prior-reference chain | Production eligibility depends on agreement | Published schedule; not all-in quote | Research only after field availability audit [S12][S13][S14] |
| FINRA Academic | Restricted historical research product | At least 36-month delay | Delayed | Not automatically originally disseminated history | Product-specific history | Higher-education eligibility; no commercial dependency | Restricted research | Reject as Mastermind production source [S13][S14] |
| FINRA public FixedIncomeMarket API | Public fixed-income views/statistics | Endpoint-dependent | Endpoint-dependent | Not a replacement for entitled transaction replay | Endpoint terms and revisions | Specific noncommercial/redistribution conditions | Public, purpose-restricted | Bounded lawful checks, not assumed enterprise feed [S15] |
| Treasury curves / NY Fed SOFR | USD reference rates and published curve conventions | Official dated histories | Scheduled publications; SOFR revisions possible | Use actual publication and vintage for each value date | Official revised publications | Public source terms | Public | Treasury comparisons and contractual reset reference [S16][S17] |
| ICE indices via FRED | Aggregate IG/HY OAS and related series | Exact-series restrictions; HY OAS page notes 2026 rolling-history change | Daily releases | Archive and release-time proof still needed | Provider/index revisions | ICE restrictions survive FRED access | Public display; licensed uses may cost | Existing macro controls, not issuer credit [S18][S19] |
| Public SEC SBSDR dissemination | Single-name/narrow-based security-based swap transactions | Modern reporting history; no invented pre-regime public tape | Applicable reporting/dissemination rules | Requires lifecycle, schema and field-time normalization | Amend/cancel/terminate actions | Repository and data-use terms | Public access, high engineering | Experimental CDS observations, not a ready daily curve [S20][S21][S22] |
| ICE evaluated pricing / EET | Global fixed-income evaluations and supporting transparency | Product-specific | EOD/continuous products | Original published generations must be demonstrated | Evaluation challenges/revisions | Enterprise and derived redistribution/AI terms | Enterprise quote | Sparse-bond valuation alternative [V01][V12] |
| Bloomberg BVAL / IBVAL | Evaluated and front-office reference pricing; distinct products | Product-specific | Product-dependent | Support score helps measurement, not temporal proof | Delivery/model/challenge versions need audit | Terminal access is not enterprise feed entitlement | Enterprise quote | Terms/pricing comparison and supported evaluations [V02][V13] |
| LSEG Pricing Service / Yield Book | Evaluations and calculated analytics | Historical analytics advertise calculations from 2008 | Product-dependent | Historical analytics explicitly recomputed/backfilled | Model/reference and challenge versions matter | Enterprise contract | Enterprise quote | Competing price/analytics option with vintage controls [V03][V04] |
| S&P ratings / agency APIs | Issuer/issue rating, outlook/watch; agency scope differs | Long advertised history | Product-specific | S&P catalog explicitly labels PIT = No | Announcement/action/correction history must be sampled | Agency/data-provider and downstream rights | Enterprise quote | Qualified rating action series, not automatic PIT [V05][V06] |
| Moody's / Fitch | Ratings, research and delivery products | Product-specific | Scheduled feeds/API/product dependent | Original action-time/correction replay unverified | Product-specific | Agency enterprise/research-use terms | Enterprise quote | Alternative rating events and definitions [V07][V08][V14] |
| S&P cash/CDS pricing | Cash-bond and single-name CDS products, including evaluated curves | Product-specific | Product-dependent | Distinguish observed from modeled and original from rebuilt | Version history required | Enterprise contract | Enterprise quote | Conditional market-data option; source dependence explicit [V09][V10] |
| FactSet / MarketAxess CP+ | Distribution of modeled fixed-income pricing | Entitlement-specific | Workstation/feed products | Integration announcement is not original-vintage proof | Upstream model/source revisions | Both distribution and upstream terms | Enterprise quote | Existing-estate fit if licensed; not independent raw trades [V11] |
| OpenFIGI / CGS identifiers | Mapping and identifier/reference relationships | Current mapping does not prove historical joins | API/reference updates | Retain real mapping receipts; Data OS owns identity | Corporate actions and remaps | OpenFIGI access does not settle CGS or other input rights | Public mapping / licensed reference | Crosswalk support under canonical identity [S23][S24] |

### D2. Current-rule and source traps that change the design

FINRA Notice 25-17 retained the 15-minute outer reporting limit; the previously approved one-minute limit never became effective. Its changes took effect 8 June 2026. Optional aggregation of qualifying managed-account allocations changes trade-count interpretation. IG/non-IG dissemination caps remain $5m/$1m, and exact uncapped size arrives later under the historical release regime, including the six-month-after-calendar-quarter timing described in the notice. Do not treat reporting deadline as actual public latency, capped size as exact size, or later quantity as known at execution. [S09][S10][S11]

The enhanced format's `T/X/C/R/Y` statuses and prior report date/reference require lifecycle reconstruction. Keep the raw report chain and derive an as-known economic-trade view; do not count cancellations or duplicate reporting as new independent trades. The abbreviated reference needs a scoped key. A disseminated price and its later uncapped/counterparty fields can have different eligible times. Standard historical, 144A and Academic products are distinct. An actual sample contract/file specification is needed before implementation. [S12][S13][S14]

The historical yield field is FINRA-calculated and may be blank; preserve its origin separately from local YTM, YTW or OAS. Transaction prices also require the specified markup/markdown and commission-inclusion semantics, rather than an assumed clean institutional mid. [S12]

SEC Companyfacts excludes many custom or dimensional instrument facts. Original accession documents and exhibits are needed for debt terms; current Frames/Companyfacts cannot supply an assumed historical vintage. The public filing time, API delivery time, local retention and later extraction each answer different questions. [S08]

Public CDS transaction records need all applicable payment terms, including running coupon/spread and upfront amount, currency and direction where applicable, to interpret price, along with reference entity, maturity, seniority and documentation. An upfront payment is not universally required to be nonzero; a missing required element must not be assumed zero. A UTI identifies a transaction; a termination is not a new daily quote. The SEC FAQ is staff guidance, and a 2026 consultation is not an enacted new reporting rule. Modern public reporting cannot be retroactively assumed for old back-reported transactions. [S20][S21][S22]

Two commercial examples make procurement proof especially important. LSEG's historical analytics brochure describes recomputation and systematic backfilling. S&P describes evaluated CDS curves inferred from issuer bonds or bond-adjusted sector spreads and a modeled CDS-bond basis. The former is not proof of originally published analytics; the latter is not independent confirmation of the same bond signal. [V04][V10]

### D3. Bounded procurement recommendation

P0 should use existing retained evidence and lawful public documents to establish a reliable foundation. Next, compare an entitled transaction route with one evaluated-price route on a common, predefined sample. Request no purchase during this commission. Before a later contract, require the supplier to demonstrate: active and dead issue coverage; original issuance/default/exchange history; contemporaneous reference terms and issuer mapping; actual delivery latency; revision/cancel archives; evaluative/model flags; historical sample provenance; and rights for intended internal, LLM and downstream uses.

An engineering pilot of roughly 12–30 carefully chosen issuers may expose plumbing and accounting errors. It cannot establish equity alpha. Include clean noncallable bonds, a finance subsidiary/guarantor case, a floating/hedged case, refinancing/tender history, a defaulted/delisted case and an unsupported hybrid. A provider failing original-history or rights requirements can still serve a clearly labeled current context use if that use is worthwhile and permitted; it cannot supply a claimed historical predictive experiment.

## E. Canonical data model and temporal semantics

### E1. Minimum model: extend existing contracts

The following are logical field groups for an owner-approved extension, **not newly minted production schema names**. Implementation must version changes through existing contracts and gates. Existing closed schemas must not receive undeclared fields. Preserve the distinction between evidence, resolved facts, market observations, calculated scenarios and consumer projections.

| Logical record / existing owner | Minimum useful fields | Required semantic boundary |
|---|---|---|
| Retained source manifest, Capital Structure | Existing source/document IDs, accession/URL, content hash, receipt/generation, media/type, rights/use class, supersession | Reuse `capital_structure_source_manifest` and current `source_manifest.jsonl`; do not create another root source log [X05][X07] |
| Document term observation / candidate term | Existing evidence IDs; span/page/table/context; raw and normalized term; unit/currency; source/extractor version; uncertainty; correction link | Existing `capital_structure.document_term_observation.v1` and `capital_structure.instrument_candidate_term.v1` remain candidates until qualified resolution [X06][X08][X09] |
| Resolved obligation extension, Capital Structure instruments | Internal security/instrument reference; obligor/guarantor links; outstanding principal and scope; issue/settlement/maturity; amortization; currency; coupon/reset; priority/collateral; call/put/convert/PIK/deferral; status | Registration amount is not issued/outstanding debt. Resolve issuer versus issue and legal obligation versus economic parent exposure |
| Historical identity relationships, Data OS | Internal `ISS:`/`SEC:` keys; source identifiers including CIK/ISIN/CUSIP/FIGI; relation type; economic interval; observation/correction evidence | Add only through the existing identity owner. Current grouping cannot be backdated or inferred solely from shared CIK [X20][X21] |
| Market report/observation, existing CCW/market owner | Instrument; source event and revision; execution/evaluation/report/release times; price side/type; size or cap state; currency; settlement; flags; direct/model basis; source roots | Transaction, quote, evaluated price and bond-implied CDS are distinct. Retain raw lifecycle; clean derivative never destroys raw events |
| Analytics projection, existing CCW | Input IDs/versions; curve ID/time; cash-flow convention; price age; YTM/g-/z-/OAS type; model version; composition and quality state | Derived from eligible inputs; no relabeling g-spread as OAS or sponsor price as executable financing |
| Rating action extension | Agency; issuer/issue/seniority/currency scope; original scale; action/watch/outlook/withdrawal; public/effective times; prior action; correction | Withdrawal/missing is not a low rating; cross-agency notch mapping never erases scope |
| Financing event extension, Capital Structure transactions | Announcement, pricing, settlement and use-of-proceeds stages; terms; amount; debt retirement; fees; liens/guarantees; committed/conditional status | An announced deal, shelf, mandate, priced issue and settled funds are different states |
| Financing scenario, Capital Structure cash funding / existing capital need | Eligible fact references; horizon; baseline; principal path; contractual rates/resets; hedge path; available-cash conditions; funding assumptions; outcome ranges | Proposed refinancing is a scenario, not a source fact. Keep inaccessible/unknown funding as states, not an extreme finite rate |
| Context projection, existing Mastermind seam | As-known cutoff; evidence roots; observation vector; source-age/coverage; mechanism narrative; status; explicit all-false authority | Separate factual/shadow context from directional reducers; one existing evidence family, no parallel decision controller |

For every monetary quantity, specify currency, scale, gross/net status, legal perimeter, accounting/economic definition and date/period. A debt ladder should retain exact contractual dates where available, otherwise fiscal-year-anchored intervals with precision flags. It cannot silently roll a disclosed next-twelve-month bucket forward as time passes. Repayment, issuance and exchange events are necessary to update principal between reports.

Missing, not applicable, not observed, stale, conflicted, unsupported and verified zero are separate states. A missing covenant or interest tag must never become zero risk or infinite coverage. Confidence should describe an evidence issue or quantified model uncertainty, not disguise missing facts in a single confidence score.

A qualified financing projection may also conclude **not economically material within the stated horizon**, using an explicit amount/threshold and supported exposures. That state concerns the modeled financing channel; it does not assert that credit prices contain no information about the business.

### E2. Preserve incumbent clock meanings

The existing Capital Structure retention decision defines `first_known_at` as verified retention of the first evidence occurrence whose generation later canonicalizes, frozen at Git publication; it is not simply the Git commit timestamp. In term contracts, `source_available_at` represents durable retained-source availability, while term `available_at` is the extraction/parser-correction production time. A new parser applied today to an old filing must not backdate its term output to the original filing date. Preserve those meanings and expose role mappings where other sources use different names. [X05][X26]

Candidate-term records also preserve `point_in_time.source_term_available_at` for the direct observation and their own `point_in_time.available_at` for candidate compilation. Candidate availability cannot borrow the direct term's earlier clock: source availability must precede or equal direct-term availability, which must precede or equal candidate availability. Violations are quarantined. [X27]

| Temporal role | Meaning and required treatment |
|---|---|
| `event_time` | Real-world execution, corporate action, rating announcement or other event; never automatically observation time |
| `as_of` / source measurement period | What the value describes: balance-sheet date, holdings date, evaluation date or fiscal interval; preserve date-only uncertainty |
| `observed_at` | When the specific observer/source observation was made; distinguish vendor observation from Mastermind receipt |
| Publicly available time | Earliest supported public dissemination of the exact field/version, including reporting exceptions and delayed historical fields |
| `known_at` / source availability roles | Name the observer and evidence basis. Map to incumbent retention/public semantics; do not create an ambiguous universal synonym |
| `ingested_at` | Actual system receipt of retained bytes, with content hash and source receipt |
| Derived `available_at` | When the calculation/extraction generation actually became usable; preserve parser correction timing |
| `effective_from` / `effective_to` | Half-open economic validity interval of a term, mapping or action, independent of when it became known |
| `correction_generation` | Append-only source/parse/model revision identity and supersession chain, including cancellation/tombstone where appropriate |
| Label available time | When an outcome was observable for training/evaluation, distinct from its economic period |

Use UTC timestamps with original timezone/calendar metadata; retain source precision. A date-only filing fact does not justify a midnight signal. If a source date was guessed, mark it inferred and exclude it from precise-time tests unless a conservative eligibility rule resolves the uncertainty.

### E3. Three replay modes, three different claims

1. **Actual-system replay.** Use only raw generations, identity versions, parser outputs and calculations the system had retained and made eligible by the historical decision time. For each required input, usable time must be no earlier than the applicable receipt/qualification/derived-generation availability. A later model can be researched against old observations, but that is a new counterfactual strategy experiment, not a reconstruction of what the former system actually computed.
2. **Hypothetical public-information replay.** Use proven contemporaneously public values and terms, plus a declared feasible acquisition/processing lag. A retrospective extractor may evaluate what a prospective strategy could have extracted, but its rules must be frozen using training data, and neither revised source fields nor later reference/identity knowledge can enter the historical signal. Label the operational history as hypothetical.
3. **Retrospective description.** Use current corrected/backfilled information with explicit current knowledge. This can describe history or diagnose models; it cannot support claims of historical tradability or original information possession.

For an observation admitted at cutoff `t`, all required source, identity, model and derivative generations must satisfy the chosen mode's eligibility rules. The selected economic relationship must be valid at its relevant event time and known by the cutoff. When a record contains richer fields published later, either maintain field-level clocks or delay the whole feature until its latest required field is eligible. A record-level timestamp set to its earliest component is unsafe.

Corrections append new knowledge. An as-known replay includes the version then available, even if later found wrong; a latest-corrected diagnostic is a different view. Cancellation and correction logic must not retroactively remove erroneous observations that were genuinely visible at a historical decision, nor preserve canceled trades as fresh observations after their cancellation became known. Retain enough history to reproduce both views.

### E4. Identity and debt perimeter

Represent obligor, parent, guarantor, secured collateral pool, co-issuer and equity beneficiary as different relationships. Finance subsidiaries can issue parent-guaranteed debt; secured operating-company bonds can protect creditors differently from holdco equity. A merger changes economic lineage, and an exchange can retire one instrument and create another. Current ticker, issuer-name substring or shared CIK is insufficient to reconstruct these links historically. Data OS's current reader expressly lacks historical issuer lineage, making effective-dated relations a real dependency. [X20]

Separate three principal quantities: contractual instrument amount outstanding, consolidated issuer debt under an accounting definition, and a fund's held par. A reconciliation bridge may connect them, with dates, perimeter differences, leases, discounts and currency adjustments. They must never be silently summed or equated. No instrument inference should acquire authority just because it balances to a reported total.

### E5. Extraction and model roles

Perform deterministic parsing, unit/sign checks, exact-span validation, cash-flow arithmetic, identifier constraints, accounting reconciliations and chronology checks before LLM interpretation. Cheap models may classify exhibits, identify candidate tables/clauses, propose term types and summarize a validated structured observation. Their output remains a candidate with exact evidence references and a model/prompt version.

Use frontier models only where ambiguity merits the cost: compare conflicting covenant definitions, explain a complex financing mechanism, identify missing dependencies, or review a scenario for contradictory assumptions. A model must not invent coupon schedules, assert covenant compliance from incomplete definitions, assign historical availability, decide a legal issuer relationship from a name alone, estimate undocumented debt capacity as fact, or grant decision authority. Rights must permit the intended model processing. Numeric outputs in a narrative come from the deterministic projection and cite its evidence, not from model memory.

## F. Derived intelligence and economic transmission

### F1. Measurement before interpretation

For each supported bond, validate price convention, accrued interest, settlement date, currency, payment schedule, day count, holiday treatment and redemption/call assumptions. Start with ordinary fixed-rate noncallable debt. Treasury inputs must identify the official methodology and curve type used. [S16]

The proposed calculation specification distinguishes a government-benchmark yield difference (g-spread), a cash-flow discount-curve spread (z-spread), and an option-adjusted spread requiring an option model and explicit reference assumptions (OAS). Do not label a Treasury par-yield subtraction OAS. This typing is an implementation requirement; Treasury documentation does not certify the credit analytics.

Changes require two comparable endpoints. A stale sponsor or transaction price against today's Treasury curve can manufacture a credit shock. Preserve price and benchmark age, source type, same-instrument continuity, bid/mid/ask basis and liquidity state. Use an ex-ante issue-selection rule and fixed/comparable baskets; publish a composition contribution separately when an issuer curve changes membership. Unsupported instruments produce a typed gap, not a fallback plausible-looking yield.

### F2. Required inspectable outputs

| Output | Calculation / observation | Mechanism and qualification |
|---|---|---|
| Refinancing need and timing | Contractual maturities/amortization plus planned commitments minus usable cash generation and eligible resources, by period | Gross obligations, cash budget and uncovered gap remain visible; scenario capital sources are not already secured |
| Marginal funding-cost change | Comparable observed issue/curve versus matched baseline; rates, credit and concession components separately | Secondary cost indication with range and source quality, not a guarantee of issuance |
| Incremental cash-interest path | Scenario versus baseline contractual principal/rate/reset/hedge cash flows | Timing and principal changes translate credit into forward fundamentals |
| Credit-equity divergence | Eligible credit innovation versus past-fitted equity/options/rate/macro expectation | Residual descriptive/predictive quantity, not automatic mispricing or arbitrage |
| Distress acceleration | Qualified same-instrument credit change/acceleration plus dated cash/maturity/covenant observations | Separate liquidity, measurement and fundamental channels; no compound independent votes |
| Capital-availability improvement | Actual pricing/settlement, extension, new commitment or collateral release, with conditions | Show amount, tenor, cash proceeds, collateral and cost tradeoffs; an open macro window is insufficient |
| Covenant pressure | Document-defined ratio/basket calculation with source terms, period, adjustments and trigger | Headroom only when all material definitions/inputs are qualified; unknown otherwise |
| Rating/outlook transition | Agency action, scope and timing | Confirmation/event context; do not assume it leads markets or average away scope |

Report maturity exposure at exact dates or intervals and configurable horizons such as 6/12/24/36 months, with the original fiscal anchor. A maturity scheduled twelve months after an old fiscal year-end is not a new next-twelve-month obligation on every later display date. Include issue retirements, tenders and restructuring status where evidenced.

### F3. Cash-interest transmission

For scenario `s` and reporting horizon `h`, calculate:

`DeltaCashInterest_h(s) = CashInterest_h(s) - CashInterest_h(baseline)`

`CashInterest_h(s) = sum_i integral_h[P_i(u,s) × contractual_cash_rate_i(u,s) du] + net_cash_hedge_settlements_h(s) + cash_fees_classified_as_interest_h(s)`

The integral is a conceptual specification; implementation uses the contract's actual day count, accrual/payment dates and principal schedule. Keep PIK, capitalized interest, discount/issuance-cost amortization, extinguishment accounting, tender/make-whole payments and financing fees separately classified. Do not include each item in both cash interest and a separate cash outflow.

Illustrative arithmetic, before fees, hedges and taxes:

| Scenario | Annual recurring interest change | Approximate first calendar-year change for 1 July refinancing | Other cash movement |
|---|---|---|---|
| $100m at 4% refinanced into $100m at 8% | $8m − $4m = **+$4m** | **+$2m** under a half-year convention | Principal retirement funded by new borrowing |
| $20m repaid from cash; remaining $80m refinanced at 8% | $6.4m − $4m = **+$2.4m** | **+$1.2m** | **$20m financing cash use**, not another operating FCF expense |
| Existing fixed-rate bond's secondary yield rises, no reset/refinancing | **$0 immediate coupon change** | **$0** from that price move alone | Potential later funding/valuation information |

Actual contractual schedules replace the half-year approximation. The familiar `principal × (new_rate − old_rate)` is a special case with unchanged principal and comparable rate definitions. A finite secondary YTM does not prove that any principal can be refinanced. If access is closed or unknown, model cash repayment, conditional facilities, asset sales or explicitly hypothetical equity/exchange alternatives as separate scenarios; do not solve infeasibility with an arbitrary very high rate.

### F4. Floating rates, hedges and actual financing access

Use the actual index tenor, reset convention, floor/cap, spread step-up, payment lag and day count. Overnight compounded SOFR, term SOFR and a simple spot-rate addition are different contracts. The NY Fed reference publication date can differ from the rate's value date and revisions can occur; bind the eligible publication. Distinguish contractual fixed/floating share from economic exposure after swaps and caps. [S17]

A dated filing example illustrates the importance: Verizon's Q1 2026 report describes fixed-rate exposure including hedges and quantifies sensitivity of its remaining floating exposure. That is evidence for modeling swaps and reset exposure, not a present investment conclusion about Verizon. Its May 2026 junior subordinated note prospectus includes reset and optional interest-deferral features; a simple cash coupon model or automatic missed-payment default label would be inappropriate. Route such hybrids out of the initial simple-instrument cohort. [S25][S26]

Committed revolver size is not always drawable liquidity. Conditions, borrowing bases, collateral, letters of credit, covenant compliance, maturity and legal-entity restrictions can limit availability. Draws also increase debt and interest. Keep unrestricted usable cash, minimum operating cash, restricted cash, committed eligible liquidity and speculative access separate. Do not simultaneously count the same cash as a maturity resource and as funding for the operating plan, or count a revolver draw as both an independent asset and net cash without its liability.

For a new issue, preserve announcement, price, settlement, proceeds and retirement stages. A refinancing may lower liquidity risk while increasing interest or seniority claims. New-issue concession is meaningful only against a comparable contemporaneous issuer/peer curve, currency, tenor, guarantee and priority. Compare all-in cash proceeds and terms; coupon alone can conceal discount, fees or collateral costs.

### F5. Coverage, covenants, cash flow and valuation

Calculate reported EBIT/interest expense and EBITDA/interest expense only with explicit definitions, periods and normalization. Gross expense differs from net expense after interest income; negative earnings or zero/negative denominators require states. Cash interest differs from accrual expense, PIK, capitalized interest and fee amortization. A CFO/cash-interest ratio is an after-interest ratio when CFO includes those payments. If a pre-interest cash-coverage measure is needed, add back only verified operating-classified cash interest, and retain tax/working-capital qualifications. It is not interchangeable with covenant coverage.

Covenants require the actual agreement definition: permitted EBITDA adjustments, acquisition windows, netting limits, restricted subsidiaries, springing tests, cure rights, baskets and measurement dates. Avery Dennison's June 2024 agreement disclosure, for example, contains a normal leverage threshold and a conditional acquisition-related step-up. A generic reported leverage ratio cannot determine compliance without those definitions. Report an evidence gap when terms are incomplete; a language model's interpretation cannot certify breach or headroom. [S27]

For `FCF = reported CFO − capex`, operating-classified cash interest is already embedded. Apply only the scenario's incremental interest change relative to the same baseline. Principal repayment and new borrowing belong in financing/cash availability, not a second FCF expense. If an existing forecast already updates refinancing interest, adding the new delta again is double counting.

After-tax impact is `−DeltaCashInterest + DeltaRealizedCashTaxSaving`, with the tax saving explicitly scenario-dependent. Do not assume a statutory shield for loss-making or deduction-constrained issuers. A later detailed tax module would need period/jurisdiction-correct rules and issuer tax capacity; current US interest-deduction guidance illustrates why a current rule cannot be blindly back-applied. Leave the shield unknown or ranged when the evidence is insufficient. [S28]

Keep valuation conventions explicit. FCFF with WACC, FCFE with cost of equity, and APV treat financing differently. Passing after-interest CFO-based cash flow into an enterprise valuation and independently applying another financing discount can count the same effect twice. A distressed promised YTM is not simply the issuer's executable cost of funding or investors' expected return. This commission does not require a new WACC score or a valuation engine; it requires a clean financing cash-flow bridge that a later accepted valuation owner can consume.

### F6. Credit innovations and mechanism narratives

Fit the expected credit change using only past training data and already eligible market/rate/sector/equity-volatility/option/liquidity information. Keep raw change, expected common component, residual and uncertainty visible. A residual is conditional statistical information, not proof of causality. Compare bond price, yield and spread as transformations of the same observation; test quoted/traded CDS separately from bond-inferred CDS.

A useful narrative follows an auditable chain: **source observation → obligation exposure → timing/financing assumption → cash-flow range → existing equity expectations → unresolved evidence**. For example: “The comparable bond spread widened; 40% of identified principal matures inside the scenario horizon; refinancing at the indicated range would increase cash interest by X–Y; actual access remains unproved.” Every number comes from eligible calculations, and the narrative retains uncertainty and any offsetting improvement in liquidity. There is no forced bull/bear conclusion.

## G. Mastermind integration map

| Producer | Canonical artifact / data owner | Evidence family | Consumer and authority boundary |
|---|---|---|---|
| SEC accession/XBRL/exhibit retention | Existing Capital Structure source manifest and term contracts; FIF owns reused accounting facts | Source roots feeding `balance_sheet_credit` | Existing debt/cash/capital-need calculations after historical selection; no second raw parser in consumer |
| Qualified security/obligor relationships | Data OS identity and effective-dated relation extension | Identity/provenance dependency | Capital Structure/CCW use the same resolved references; ambiguous joins quarantined |
| Existing sponsor holdings | CCW retained observation/analytics extension | Market-credit evidence with sponsor/model ancestry | Descriptive context and qualified forward shadow; no assumed transaction or debt-outstanding authority |
| Later entitled bond/CDS/rating source | Existing market/Capital Structure owner contracts | Root-linked market/rating evidence | Only accepted measures and supported cohorts; no parallel source truth store |
| Debt terms, cash facts, financing events | Capital Structure instruments/cash funding/transactions; reuse F09 | Financing mechanism inside `balance_sheet_credit` | Existing funding scenarios, including Prophet Cycle coordination |
| Macro credit/rate conditions | Existing Macro credit-window/rate owner | Common factor/control, not another independent issuer vote | Scenario assumptions and empirical controls |
| Deterministic financing projection | Existing owner context projection, with source/assumption receipts | Inspectable family dimensions | Research desk, single-name factual context and later existing Terminal surface |
| Research Vault documents / LLM candidates | Research Vault citations and qualified source-linked term candidates | Research context until verified | Explanation/extraction review; never independent market facts from prose |

Mastermind remains the owner of portfolio decisions. Macro produces evidence and financing mechanisms; Terminal renders qualified context. Existing V3 source/independence/Decision Snapshot work remains the authority for any later accepted decision integration. No new scheduler, control plane, portfolio score, autonomous escalation or shadow-to-live shortcut is introduced by this research.

The initial consumer seam must be factual and structurally excluded from `lenses.synthesize` and held-risk mutation. All-false authority metadata is necessary but insufficient. A later authority proposal needs its own accepted consumer diff, exact replay/invariance or intentionally changed-behavior proof, empirical results and rollback boundary. It must reconcile the existing held-risk proxy instead of quietly replacing it during producer hardening. [M03][M04][M05]

## H. Empirical validation program

### H1. Separate the claims

The experiment has four distinct questions: whether the data is valid; whether disclosed terms improve financing forecasts; whether market-credit observations add information beyond that foundation; and whether any surviving information is useful under a particular decision policy. Passing an earlier question does not answer a later one. No such predictive experiment was completed during this commission.

Use identical eligible issuer-dates and training/tuning budgets for these comparisons:

| Model set | Information available by the cutoff | Comparison it supports |
|---|---|---|
| B0: existing baseline | Actually available PIT equity, options, accounting, SUE/revisions, market/sector/rate/macro information, events and existing risk inputs | What Mastermind could already know |
| B1: financing foundation | B0 plus qualified debt terms, maturity/reset/hedge exposure, cash/accrual interest, financing events, age/missingness/liquidity controls | Incremental value of contractual and accounting hardening |
| B2: market credit | B1 plus qualified issuer bond/credit observations and prespecified exposure interactions | Incremental value of market prices over disclosed financing information |
| Later B3 extensions | B2 plus separately qualified rating or independently sourced CDS observations | Marginal value after source ancestry/overlap controls |

B0 must be instantiated from available historical data, not an aspirational list. Report a core baseline and an options/revisions-complete subset if mature PIT series are unavailable. “Incremental to options” is unsupported on rows without options. B1 must include ordinary accounting/maturity information already present in B0 only once; define the actual delta in a feature ledger. Include missingness/observation age in the baseline so a feed does not win merely by identifying liquid covered issuers.

Historical sector controls also require eligible classifications. Do not import the current-sector labels described in the new Trend C1 preregistration as era-correct data. If historical sector identity is unavailable, use a predeclared supportable factor benchmark and a separately labeled sensitivity; do not silently create historical group membership. [M13]

### H2. Freeze the hypothesis register before the final sample

**Primary equity endpoint:** 20-trading-day equity total return residual relative to a preregistered factor/sector benchmark, beginning at the next executable equity timestamp after the whole signal is usable. Estimate deterioration and improvement separately; symmetry is a hypothesis, not a constraint. Report effect per one training-period standard deviation of the eligible credit innovation, confidence interval and paired forecast improvement.

**Primary mechanism endpoint:** matched next-four-quarter cash-interest burden or period change, using a predeclared observable definition and fiscal alignment. Compare B2 against B1's contractual rate/reset/refinancing baseline. Distinguish reported accrual expense and actual cash interest; use missing/censored labels rather than silently substituting one for the other, subject to H3's informative-failure treatment.

Secondary endpoints may include 1/5/63/126-trading-day returns, drawdowns, calibrated adverse-event probability, refinancing terms/settlement, equity dilution, FCF or expectation revisions. Each needs its own definition, publication clock and censoring rule. Freeze the confirmatory family, practical improvement thresholds and multiplicity procedure; remaining cohorts/horizons are exploratory. Do not choose a new primary after a negative result.

The final untouched block should target at least 24 months if lawful original-vintage history supports it, with more history needed for regime and rare-event claims. This is a design aspiration, not proof such a dataset exists or that two years is sufficient. CCW's short forward-accrual history cannot be turned into a multiyear original-information backtest. If older eligible history is unavailable, use a clearly prospective study and wait for mature labels rather than fabricate history.

### H3. Universe, clocks and construction

Begin with historical listed issuers, then record credit coverage. Retain failed, delisted, merged and unquoted equities and retired/exchanged/defaulted bonds with appropriate outcome rules. Current holdings or present bond lists cannot define the old eligible universe. Include total returns through delisting under an explicit source rule; missing delisting returns are not zero.

Freeze supported instrument classes and issuer relations. Both endpoints of a change must meet source-age, curve-age and same-instrument/composition requirements. The signal clock is no earlier than the latest required field's eligible time. An after-equity-close bond observation cannot be traded at that day's equity close. Later exact TRACE size, a modern issuer mapping, an amended filing or today's call schedule cannot enter an earlier public-information feature.

A filing about a later outcome is a valid label only once observable; it is never an earlier predictor. Training at date T uses only labels matured and available by T. Purge labels overlapping validation/final boundaries and account for horizon-dependent embargoes; annual mechanism labels require longer boundaries than 20-day returns. Retain missing later filings and right-censor recent issuers. No financing issuance does not establish denied access; bond disappearance does not establish default. Treat merger, exchange, repayment and failure as separate terminal or competing states.

Missing mechanism labels after bankruptcy, restructuring or reporting cessation are informative selection, not automatically benign censoring. Audit label availability against prior credit stress and subsequent failure. Prespecify a competing-failure endpoint and sensitivity bounds or a justified selection model for the cash-interest analysis; report complete-case and failure-inclusive results separately. Do not claim calibrated interest forecasts for the original universe solely from the surviving filers, or classify interest cessation after default as improved financing capacity.

### H4. Models, dependence and evidence independence

Start with an interpretable regularized model and one bounded nonlinear challenger. Fit transformations, missing-value rules, winsorization, normalizers, cohort cutoffs and issue-selection policies using past training data only. Credit residualization also belongs inside the chronological training loop. Past-only cross-fitting can estimate conditional information; it does not turn association into causality. Auxiliary price-discovery/VAR analysis is not a substitute for out-of-sample equity prediction. [S29]

Include rates, equity volatility and nonlinear interactions in a stronger sensitivity baseline, reflecting the common-credit literature. Inspect correlated source roots: the same trade's price/yield/spread, vendor evaluations based on shared TRACE observations, bond-implied CDS and a rating action triggered by already public information should not acquire separate decision votes merely because separate columns exist.

Issuer-days are dependent within issuer, across market dates and across overlapping labels. Use issuer and calendar-time dependence together, supplemented by paired date-block bootstrap of B1/B2 forecast loss differences. Block length and episode rules must reflect horizon and crisis dependence. Nested-model comparison requires an appropriate method; a standard nonnested equal-accuracy test is not automatically valid. These statistical choices should be reviewed against the actual model and sample. [S30][S31]

### H5. Metrics, costs and power

Report paired out-of-sample loss/R-squared improvement, partial rank information and effect sizes with uncertainty. For adverse-event models, use calibration, Brier/log loss, precision/recall at a frozen alert budget and prevalence-matched comparisons. AUPRC on a different prevalence sample is not directly comparable. Show coverage and exclusions alongside performance, including the difficult distressed/illiquid cohort.

Before viewing the final block, set the minimum practically useful effect. For forecasting, define an error or calibrated-alert improvement that would change a specified research workflow. For a later equity shadow attribution, require a conservative cost hurdle covering equity spreads, commissions, impact, turnover, signal delay and capacity; if shorting is modeled, include borrow availability/fees and dividends. Do not subtract bond trading costs from an equity-only attribution, or imply that this research authorizes any trading. License/engineering expense belongs in the capability cost-benefit decision separately.

Power is a gate before interpreting significance. An illustrative independent-observation approximation for 5% two-sided size and 80% power is `(1.96 + 0.84)^2 / rho^2`: about **3,136 effective observations for correlation 0.05** and **8,711 for 0.03**. These are not issuer-day requirements or empirical sample counts. Dependence, multiple tests and rare outcomes can increase the needed raw sample sharply. Use Fisher-z or simulation for the final design, with clustering, actual label prevalence and alert policy. A 12–30-issuer engineering sample cannot demonstrate alpha.

Report minimum detectable effect separately for major preregistered cohorts. A nonsignificant result with wide intervals is **inconclusive**, not a proof of no information. A confidence bound excluding the prespecified useful effect can support a null/kill conclusion. Fix interim looks and decision dates; do not repeatedly extend a rolling sample until significance appears.

### H6. Required falsifiers and sensitivities

| Test | What failure would reveal |
|---|---|
| Rotate credit signals across issuers within date/PIT cohort | Market/common-factor or coverage artifact rather than issuer information |
| Test reverse equity-to-credit direction and B2 after eligible equity controls | Bidirectional information may coexist; only loss of incremental B2 value supports an echo/omitted-equity explanation |
| Add realistic dissemination/processing lags; align after-close signals | Claimed value depends on impossible execution timing |
| Same-instrument, liquid and matched-price/curve-time subsets | Stale marks, benchmark mismatch or composition changes manufacture the result |
| B1 foundation-only and full-options/revisions subsets | Market feed inherits accounting or omitted-options information |
| Leave out each major crisis; inspect event episodes | One regime or repeated rows from a few failures dominate general claims |
| Separate pre-event warning from postannouncement/postdefault recognition | Distress classification is retrospective rather than actionable |
| Compare low-transmission net-cash/no-near-maturity cohort | Financing mechanism differs from broad business information |
| Separate raw trades, evaluations and independently observed CDS | Apparent confirmations share the same underlying source/model |
| Reproduce using as-known and latest-corrected views separately | Performance is being created by future revisions or hindsight mapping |

Do not require the hypothesized low-rated effect to survive deleting the entire distressed cohort. Instead verify that it precedes the outcome, is not stale-price error, is sufficiently broad within that cohort and is feasible at its actual costs and coverage. A valid conditional finding should remain conditional.

### H7. Admission, progression and kill decisions

**Every admitted row must satisfy all required identity, temporal, correction, rights and measurement constraints.** A 99.5% valid-row target is not an acceptable backtest admission rule. Report a separate coverage aspiration, for example at least 95% of the bounded intended pilot cases if feasible; the remainder is explicitly quarantined. Neither 95% coverage nor 100% admitted-row validity establishes predictive power.

Progress only when quality passes, the study can detect a useful effect, and final results exceed predeclared practical thresholds with appropriate uncertainty/multiplicity and stability across the claimed scope. Preserve four distinct outcomes: supported conditional value; informative null; underpowered/incomplete; and invalid source/method. A source failure blocks the affected experiment. A market-alpha failure can reject predictive promotion while retaining valuable factual debt context.

Stop or defer when original-history/rights cannot be established at reasonable cost, eligible issuer matches are insufficient, a useful effect is excluded by the confidence bound, the effect disappears with feasible timing or strong B1/options controls, results depend on future corrections, or the useful cohort is not actionable under the proposed costs/capacity. Do not promote solely because a dashboard looks plausible or an in-sample distress classifier is accurate.

## I. Risks and failure modes

| Failure mode | Detection / treatment | Promotion consequence |
|---|---|---|
| Future filings or parser generations enter history | Retained-source eligibility before selection; falsifier from B; separate replay modes | Reject affected historical rows and experiment |
| Current issuer mapping applied to old obligations | Dated obligor/guarantor/source relations; ambiguous joins quarantined | No issuer prediction until relation is supportable |
| Sponsor-held par read as total liabilities | Typed scope and portfolio-versus-issuer reconciliation | Block refinancing calculation from that quantity |
| Shelf/registration candidate becomes debt or capacity | Require priced/settled/contractual evidence and resolved instrument | Candidate remains non-authoritative |
| Fresh rates applied to stale bond prices | Endpoint age tests and common timestamp subsets | Exclude manufactured shock; report coverage loss |
| Callable, distressed or hybrid bond forced into simple yield math | Supported-instrument classifier and convention checks | Unsupported state; separate model commission |
| Illiquidity or absent data looks like stability | Fresh-observation flag, censored/missing states and coverage audit | No zero-change imputation as positive evidence |
| Ratings/backfilled curves/TRACE enriched fields leak | Field/action/generation clocks and original-version sample | Descriptive-only if replay cannot be proven |
| Vendor logos counted as independent evidence | Input ancestry and bond-implied CDS tagging | No independent vote from shared roots |
| Secondary price mistaken for financing access | Actual transaction/commitment lifecycle; feasibility states | Access remains unknown/conditional |
| Cash, fees, interest, hedges or tax counted twice | Period cash bridge and definition reconciliation | Block numerical projection until reconciled |
| Covenant false precision | Exact definitions, measurement period and evidence completeness | Unknown headroom; no inferred breach from label |
| Directional context changes portfolio behavior | Out-of-reducer design plus consumer invariance tests | Separate accepted decision change required |
| Tiny or survivor-only backtest appears significant | Historical universe, matured labels, clustered power and final holdout | Inconclusive or invalid; no promotion |
| Vendor lock-in / rights mismatch | Exportable source IDs, versioned adapters, retained permitted receipts; entitlement audit | Stop acquisition or use only permitted bounded purpose |
| Green top-level health hides empty/stale content | Source freshness, extraction coverage, publication and consumption separately | No live/PIT acceptance from one verdict |

Market microstructure, accounting and issuer relationships vary globally. A later international extension needs local disclosure/reporting rules, holiday/settlement conventions, currencies, insolvency/priority treatment and source rights. Do not extrapolate US TRACE/SEC semantics to European, Asian, private-loan or sovereign instruments. The initial narrow coverage must be visible in every report and performance denominator.

## J. Build priority

| Priority | Bounded capability | Rationale and gate |
|---|---|---|
| **P0** | Owner/contract reconciliation; retained-source eligibility and correction fixtures; debt/cash definition audit; CCW measurement/freshness/mapping qualification; consumer containment proof | Existing source defects can invalidate future research. Begin offline and preserve W2/W3/W4 gates |
| **P0** | Source/coverage/consumer receipts and a frozen B0/B1/B2 hypothesis register | Prevent false claims of live operation, PIT history or incremental value |
| **P1** | Qualified obligation/interest/reset/hedge fields and period financing scenarios within accepted Capital Structure/FIF owners | Direct forward-fundamental usefulness for a bounded industrial-corporate cohort; requires source and identity dependencies |
| **P1** | One entitled transaction-versus-evaluation pilot, original-vintage audit and forward shadow | Establish whether additional market data is worth its cost; separate purchase acceptance |
| **P2** | Qualified ratings, observed CDS, contractual covenants, richer secured/guarantor structure and additional markets | Valuable only after adequate terms, rights, history and incremental tests; avoid broad premature coverage |
| **Defer** | Complex hybrids, convertibles, private loans, financial institutions and general WACC/valuation automation | Distinct cash-flow/legal/sector methods; not safe extensions of simple bond math |
| **Defer** | Any directional lens, held-risk replacement, portfolio gate, sizing or live decision integration | Separate policy commission after validated evidence and exact consumer acceptance |
| **Reject** | Generic bearish credit score; independent votes for transformations of one source; new issuer registry/parallel credit state; shelf equals capacity; fund-held par equals debt; backdating modern extraction; Academic product as commercial feed | Misstates economics, violates source ownership or defeats historical/rights validity |

P0 and P1 ranking does not imply authority to skip the existing Capital Structure wave dependencies. If current owner proof is pending, the permissible work is offline qualification, evidence/contract preparation and exact dependency resolution. Current source should be repinned before any later phase starts.

## K. Proposed implementation phases

### Phase 0 — Accept scope and freeze the qualification target

Rebootstrap and repin all touched repositories; reread current owner gates and relevant open carriers. Register this work as an extension of `capital-structure-intelligence`, identify the exact write footprint and retain the evidence packet. Freeze supported instrument/issuer classes, replay modes, data rights, evaluation claims and non-authority boundaries. Do not interpret research acceptance as approval for a paid feed, a pipeline run or held W3/W4 work.

**Exit evidence:** accepted owner/scope map, collision disposition, immutable base revisions and a finite fixture list. If source moved, record the specific changed dependency; do not restart unrelated research.

### Phase 1 — P0 offline qualification and eligible-input adapter

Implement only the bounded handoff in L. Reproduce the future-filing selection issue, then demonstrate an opt-in existing-owner adapter that selects eligible retained inputs before calling existing calculations. Exercise corrections, parser timing, missing terms, source scope and unsupported mappings. Qualify the CCW sample's price/curve/issuer/date limitations in a machine-readable research report. No scheduler, live data mutation or portfolio consumer changes.

**Exit evidence:** source/temporal invariants, paired old/future fixture, explicit quarantines, no new persistence plane, no default caller changes and a reviewed gap list. This proves the opt-in adapter, not a claim that all legacy callers were repaired or that W2 operational proof has completed.

### Phase 2 — Owner-approved foundation integration

After current proof gates and the additional exact F09/CCW path scope are accepted, wire qualified source selection into existing debt/cash calculations and extend permitted debt/interest/hedge fields. Establish Data OS historical relationships for the bounded cohort. Reconcile contractual principal with reported debt using dated perimeter bridges. Add period financing scenarios under the existing Capital Structure/Prophet seams. Prove current and historical outputs and failure states; do not quietly change held-risk severity.

**Exit evidence:** end-to-end source-to-context receipts, verified economic examples, qualified coverage/freshness, correct history/corrections and consumer invariance. A rejected/unknown input remains visibly rejected/unknown.

### Phase 3 — Market-data sample and acquisition decision

Obtain a separately authorized lawful sample/entitlement. Compare transaction and evaluation routes on identical instruments/dates, audit old versions/defaulted history, source/reference timing, corrections and rights. Estimate operational coverage, latency, portability and all-in costs. Begin forward retention only through an accepted existing pipeline owner.

**Exit evidence:** signed-off field/rights/temporal matrix, reproducible sample quality and a buy/no-buy/defer recommendation. A catalog or demonstration chart is insufficient. No historical alpha claim from a current evaluated/backfilled sample.

### Phase 4 — Preregistered empirical evaluation and shadow

Execute H with fixed baselines, matched samples, matured labels, proper dependence and practical thresholds. Separate historical public-information research from actual-system forward shadow. Report all preregistered tests, nulls, excluded coverage and power. Maintain frozen authority.

**Exit evidence:** reproducible research packet, uncertainty/calibration/cost analysis, sensitivity/falsifier results and supported/null/inconclusive/invalid classification. Conditional scope remains explicit.

### Phase 5 — Optional consumer decision proposal

Only after the previous evidence supports a useful decision application, propose the exact modification to the existing V3/held-risk/lens owner. State how evidence independence, source receipts, rollback, policy thresholds and Decision Snapshots will work in the then-current implementation. An accepted factual context system can remain the final product if predictive promotion is not justified.

**Exit evidence:** a separately reviewed and authorized consumer commission. No automatic promotion from research or shadow success.

## L. Exact bounded implementation handoff

### Commission to issue only if this research is accepted

**Title:** C14-P0A — Qualify historical financing inputs inside the existing Capital Structure owner.

**Mission:** Build an offline, opt-in qualification adapter and regression evidence that prevent a historical financing calculation from selecting an ineligible filing/source/parser generation. Preserve the existing source manifest, candidate-term lifecycle, identity ownership and pure debt/cash calculation semantics. Produce a reviewable PR and evidence report. This commission does not authorize a data purchase, live pipeline execution, default caller change, held W3/W4 implementation, or portfolio behavior change.

**Authority and routing:** Operate under `capital-structure-intelligence` and `WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2`. Rebootstrap and pin protected Mastermind/Macro; read current path ownership, source-law and wave gates. The research pins and PR heads in this report are starting receipts, not a license to use stale source. Reconcile #8308, #8397, #7119 and the already merged #8051 by current exact state. Resolve the current worker/writer lease through normal ownership; the historical `coo-fable` label is not one.

**Bounded write footprint:**

- Reuse an existing equivalent selector if the fresh census finds one. Otherwise add the proposed pure helper `engine/capital_structure/financing_input_eligibility.py` inside the existing owned directory. This is a computation adapter, not a canonical store or new schema family.
- Add focused tests/fixtures at `tests/test_capital_structure_financing_input_eligibility.py` and an owner-approved fixture location under the existing test estate. Tests may contain only synthetic data or public/licensed evidence permitted for that purpose.
- Update only the relevant qualification/interface section of `docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md`, plus a bounded qualification report in `research/commission14/` and necessary owner receipt through the existing procedure.
- Treat `engine/debt_maturity.py`, `engine/cash_runway.py`, `engine/capital_need.py`, `engine/corp_credit.py`, their builders, Data OS schemas, production `data/` artifacts, pipelines, Mastermind `portfolio/` code and Terminal as **read-only in P0A**. Later fixes/wiring require their exact accepted owner footprint; the V2 workstream's current `owns_paths` does not itself grant all F09/CCW paths.

**Required behavior:**

1. Accept an explicit cutoff and replay mode, plus existing retained source/term inputs with their actual receipt, public/effective, parser and correction fields. Preserve source hashes/generation IDs. Do not invent clocks for records that lack them.
2. Select the latest eligible fact/version **within** the available information set before invoking a debt/cash calculation. Enforce fiscal context, units, legal/perimeter identity and economic validity. A newest ineligible filing must not hide an older eligible one. Later corrections must not alter earlier as-known results.
3. Distinguish actual-system, hypothetical public-information and retrospective modes. Reject a historical claim when required availability or identity cannot be established. Return typed missing/ambiguous/unsupported states; never replace them with zero or inferred safe coverage.
4. Pass a filtered, source-bound input to the existing pure extractor in tests. Do not change its default production caller or imply its unguarded legacy use became safe. Document the exact integration seam and residual callers for a later P0B commission.
5. Generate an offline qualification report for the available sample: eligible and quarantined rows/issuers, source/price/curve age, correction and identity gaps, sponsor-held versus contractual principal, and unsupported instrument types. Existing generated health/PASS status is a separate observation.
6. Preserve all existing authority fields and avoid a new directional lens/context row. No portfolio or live consumer is changed. Explain the later invariance tests required before wiring.

**Mandatory fixtures and acceptance evidence:**

- Reproduce the exact B3 two-filing counterexample against the pinned unmodified extractor; record source blob and observed future selection.
- Show the opt-in adapter selecting accession `old` and value `100` at cutoff `2025-06-01`; show the later filing only after its required availability becomes eligible. If the fixture lacks enough actual-system clocks, the actual-system case must reject it rather than fabricate a receipt; a separate fully timestamped synthetic fixture proves the positive path.
- Cover a later amendment/correction, a later parser re-extraction of old retained bytes, same-day source-time uncertainty, a missing/ambiguous historical obligor link, an empty required term, mismatched units/fiscal context, and a withdrawn/canceled version.
- Cover a candidate compiled after an already available direct term: the candidate stays ineligible before its own compiler availability, even when its source and direct observation are already eligible.
- Cover fund-held par versus contractual principal so it cannot be admitted as an issuer maturity ladder. Cover a callable/hybrid bond that must remain unsupported by the simple pricing path.
- Prove deterministic replay at the same cutoff/generation, exact evidence references, no history rewrite, no persistence side effect and no default caller/portfolio/pipeline changes. Test the actual economic/temporal invariants rather than merely mirroring implementation branches.
- Require 100% validity for admitted cases and explicit quarantines for all unresolved ones. Coverage is reported separately. No alpha, production freshness, complete legacy fix or wave-gate release may be claimed from these tests.

**Deliverables:** One bounded code/test/documentation PR in the owning repository; immutable source receipts; input/output fixtures; a qualification table; a precise remaining-integration list for F09/CCW/Data OS identifying each discovered unguarded caller by path, residual historical-use risk and responsible owner; and a follow-on recommendation of proceed, narrow or defer. Publish through the current source-law workspace procedure and verify the exact pushed head. Do not merge, deploy, run live collectors or change decision authority under this commission.

**Stop/narrow conditions:** If an equivalent qualified adapter already exists, test/reuse it and limit the diff to the demonstrated gap. If required historical bytes, clock meanings, identity lineage or rights are unavailable, quarantine those cases and complete the remaining bounded evidence; do not fabricate history. If current owner gates or active path custody block a mutation, finish the concrete read-only/test design and identify the exact dependency. A new owner store, broad refactor or live proof-manufacturing run is out of scope.

**Acceptance boundary:** P0A succeeds when the opt-in path is demonstrably correct and its limitations are reviewable. It does not claim all financing history is complete, that issuer market credit predicts equity, or that the subsequent integration/data-purchase/policy commissions are authorized.

---

## Research source register

Internal source links are immutable at the census revisions; adjacent PR links are mutable and their inspected heads are recorded in B6 and the evidence manifest. Public sources were reviewed during this research on 4 October 2026. No paid payload, negotiated license, vendor cost quote or full Hameed et al. paper was inspected. Provider web claims remain distinct from observed integration behavior. The following compact register supports the inline reference links; source/evidence JSON retains more granular source custody.

### Mastermind, Macro and Terminal

- **M01–M02:** Current bootstrap/source-law index and repository linkage.
- **M03–M06:** Held-risk/lens code, V3 specification and dated generated census.
- **M07–M13:** Existing PIT panel/fundamentals, research/thematic owners, documented history gaps and final-head Trend C1 update.
- **X01–X09:** Macro pin, canonical program/workstream, state design and retained/candidate-term contracts.
- **X10–X18:** Existing debt/cash/capital-need, CCW/momentum/window and covenant code.
- **X19–X28:** Health, identity, FIF, Research Vault, committed output quality, retention/candidate clocks and adjacent filing detector.
- **T01:** Terminal overview source.
- **P01–P04:** Adjacent carrier status, treated separately from protected source.
- **R01–R02:** Complete protected-revision comparisons used for the final drift review.

### Primary public research and source documentation

- **S01–S07:** Academic/institutional lead-lag, arbitrage, common-credit and market-functioning research; S03 abstract only.
- **S08–S24:** SEC, FINRA, rates, index and identifier documentation; separate rules, staff guidance, product terms and current mapping claims.
- **S25–S27:** Dated SEC-hosted issuer examples for hedges, hybrids and covenant definitions; not current investment opinions.
- **S28–S31:** Official tax guidance and primary statistical-method research used to define later validation requirements.
- **V01–V14:** Vendor public documentation and product disclosures, without licensed capability/PIT acceptance.

[M01]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/sol_skills/INDEX.md> "Mastermind current bootstrap/source-law index"
[M02]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/.gitmodules> "Mastermind Macro repository linkage"
[M03]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/portfolio/held_risk.py> "Held-risk earnings and interest proxy"
[M04]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/portfolio/lenses.py> "Lens synthesis and confluence"
[M05]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md> "Portfolio V3 risk-first design"
[M06]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/data/census/CENSUS.md> "Generated census, July 16 2026"
[M07]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/loop/fundamentals.py> "PIT fundamental loader"
[M08]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/loop/single_name_panel.py> "Single-name panel"
[M09]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/brain/research_desk.py> "Research desk"
[M10]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/brain/bottleneck.py> "Bottleneck owner"
[M11]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/research/TREND_PERSISTENCE_PROTOCOL.md> "Trend persistence protocol"
[M12]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/source_thematic_rotation_framework.md> "Thematic rotation framework"
[X01]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/config/mastermind_programs.yml> "Macro research revision"
[X02]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/config/mastermind_programs.yml> "Canonical capital-structure-intelligence and ccw alias"
[X03]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md> "Capital Structure V2 workstream and gates"
[X04]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md> "Capital Structure V2 masterplan"
[X05]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md> "Capital Structure contract"
[X06]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/CAPITAL_STRUCTURE_ISSUER_STATE_W3_BUILD_DOCKET.md> "W3 issuer-state build docket"
[X07]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/contracts/capital_structure_source_manifest.schema.json> "Retained source manifest schema"
[X08]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/contracts/capital_structure_document_term_observation.schema.json> "Document term observation schema"
[X09]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/contracts/capital_structure_instrument_candidate_term.schema.json> "Instrument candidate term schema"
[X10]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/debt_maturity.py> "Debt maturity extractor"
[X11]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/capital_need.py> "Capital need read model"
[X12]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/cash_runway.py> "Cash runway read model"
[X13]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_debt_maturity.py> "Debt maturity builder/cache"
[X14]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/corp_credit.py> "Corporate Credit Watch engine"
[X15]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/collectors/corp_bond_holdings.py> "Sponsor bond holdings collector"
[X16]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/credit_momentum.py> "Credit momentum engine"
[X17]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/credit_window.py> "Aggregate credit-window context"
[X18]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/covenant_headroom.py> "Covenant headroom view model"
[X19]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/capital_structure/health.json> "Committed Capital Structure health"
[X20]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/config/identity_seams.yml> "Canonical identity seams"
[X21]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/financial_intelligence_fabric/FIF_3A1_REUSE_MAP.md> "FIF accounting and identity reuse map"
[X22]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/RESEARCH_VAULT_MASTERPLAN.md> "Research Vault masterplan"
[X23]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/corp_bonds/latest.json> "Committed CCW latest output"
[X24]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/corp_bonds/credit_momentum.json> "Committed credit momentum output"
[X25]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/corp_bonds/validation.json> "Committed CCW validation"
[X26]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/decisions/DEC-CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK.md> "Canonical first_known_at retention decision"
[T01]: <https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/1c708450187755160e1a5889b69598a2fcb1f0d1/terminal/components/fin/OverviewPage.tsx> "Terminal overview"
[S01]: <https://pure.eur.nl/en/publications/the-co-movement-of-credit-default-swap-bond-and-stock-markets-an-/> "Norden and Weber (2009), institutional publication record"
[S02]: <https://people.umass.edu/nkapadia/docs/kp_04302010.pdf> "Kapadia and Pu, author-hosted 2010 manuscript"
[S03]: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4728568> "Hameed, Titman, Wei and Zhang, July 2026 working-paper abstract"
[S04]: <https://www.financialresearch.gov/working-papers/2024/07/17/do-credit-default-swaps-still-lead/> "OFR WP 24-04: Do Credit Default Swaps Still Lead?"
[S05]: <https://www.newyorkfed.org/research/staff_reports/sr1094> "NY Fed Staff Report 1094: The Global Credit Cycle"
[S06]: <https://www.newyorkfed.org/research/policy/cmdi> "NY Fed Corporate Bond Market Distress Index"
[S07]: <https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html> "Federal Reserve: Recession Risk and the Excess Bond Premium"
[S08]: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces> "SEC EDGAR application programming interfaces"
[S09]: <https://www.finra.org/rules-guidance/notices/25-17> "FINRA Regulatory Notice 25-17"
[S10]: <https://www.finra.org/rules-guidance/rulebooks/finra-rules/6730> "FINRA Rule 6730 reporting requirements"
[S11]: <https://www.finra.org/rules-guidance/rulebooks/finra-rules/6750> "FINRA Rule 6750 dissemination"
[S12]: <https://www.finra.org/sites/default/files/AppSupportDoc/p353157.pdf> "FINRA Enhanced Historic corporate bond layout"
[S13]: <https://www.finra.org/filing-reporting/trace/historic-academic-data> "FINRA historic and academic data information"
[S14]: <https://www.finra.org/rules-guidance/rulebooks/finra-rules/7730> "FINRA Rule 7730 products and fees"
[S15]: <https://developer.finra.org/specific-terms-fixed-income-data> "FINRA Fixed Income API specific terms"
[S16]: <https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology> "US Treasury yield curve methodology"
[S17]: <https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates> "NY Fed reference rate publication and revision information"
[S18]: <https://fred.stlouisfed.org/series/BAMLH0A0HYM2> "FRED ICE BofA US High Yield OAS"
[S19]: <https://fred.stlouisfed.org/series/BAMLC0A0CM> "FRED ICE BofA US Corporate OAS and rights notes"
[S20]: <https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/frequently-asked-questions-regulation-sbsr> "SEC staff Regulation SBSR FAQ"
[S21]: <https://www.sec.gov/newsroom/press-releases/2021-80> "SEC 2021 SDR registration and initial reporting compliance"
[S22]: <https://www.sec.gov/rules-regulations/public-comments/s7-2026-22> "SEC 2026 reporting consultation docket, not enacted rule"
[S23]: <https://www.openfigi.com/api/documentation> "OpenFIGI API documentation"
[S24]: <https://www.cusip.com/services/license-fees.html> "CGS licensing requirements statement"
[S25]: <https://www.sec.gov/Archives/edgar/data/732712/000073271226000023/vz-20260331.htm> "Verizon Q1 2026 Form 10-Q"
[S26]: <https://www.sec.gov/Archives/edgar/data/732712/000119312526221003/d148236d424b2.htm> "Verizon May 2026 junior subordinated note prospectus"
[S27]: <https://www.sec.gov/Archives/edgar/data/8818/000119312524170372/d844816d8k.htm> "Avery Dennison June 2024 credit agreement disclosure"
[S28]: <https://www.irs.gov/instructions/i8990> "IRS current Form 8990 instructions"
[S29]: <https://www.nber.org/papers/w23564> "Chernozhukov et al., double/debiased machine learning"
[S30]: <https://www.kellogg.northwestern.edu/faculty/petersen/htm/papers/standarderror.html> "Petersen, standard errors in finance panel data"
[S31]: <https://www.nber.org/papers/t0326> "Clark and West, nested forecast model comparison"
[V01]: <https://www.ice.com/fixed-income-data-services/data-and-analytics/pricing/evaluated-pricing> "ICE evaluated pricing and transparency"
[V02]: <https://professional.bloomberg.com/products/data/enterprise-catalog/pricing/evaluated-pricing/> "Bloomberg BVAL evaluated pricing"
[V03]: <https://www.lseg.com/en/data-analytics/market-data/data-analytics-pricing/evaluated-pricing-data> "LSEG evaluated pricing"
[V04]: <https://www.lseg.com/content/dam/data-analytics/en_us/documents/brochures/lseg-pricing-service-and-yield-book-historical-analytics-brochure.pdf> "LSEG and Yield Book historical analytics brochure"
[V05]: <https://www.marketplace.spglobal.com/en/datasets/ratingsxpress-s-p-credit-ratings-%2833%29> "S&P Credit Ratings catalog with PIT metadata"
[V06]: <https://xpressapi.marketplace.spglobal.com/swagger/> "S&P Agency Ratings API"
[V07]: <https://www.moodys.com/web/en/us/capabilities/company-reference-data/datahub.html> "Moody's DataHub"
[V08]: <https://www.fitchratings.com/research-and-data/fitch-ratings-pro> "Fitch Ratings PRO"
[V09]: <https://www.spglobal.com/market-intelligence/en/solutions/products/pricing-data-bonds-corporate-sovereign> "S&P corporate and sovereign bond pricing"
[V10]: <https://www.spglobal.com/market-intelligence/en/solutions/products/single-name-pricing-data> "S&P single-name CDS pricing, including bond-implied evaluated curves"
[V11]: <https://investor.factset.com/news-releases/news-release-details/factset-brings-ai-powered-fixed-income-data-investors-first-add> "FactSet MarketAxess CP+ integration announcement"
[P01]: <https://github.com/mastermindx-market-intelligence/macro/pull/8308> "Prophet funding recovery draft"
[P02]: <https://github.com/mastermindx-market-intelligence/macro/pull/8397> "Bonds mechanism explanation draft"
[P03]: <https://github.com/mastermindx-market-intelligence/macro/pull/7119> "Historical maturity persistence carrier"
[P04]: <https://github.com/mastermindx-market-intelligence/macro/pull/8051> "Merged credit yield-momentum consumer"
[X27]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/capital_structure/instrument_candidates.py> "Candidate compiler availability clocks"
[V12]: <https://www.ice.com/fixed-income-data-services/data-and-analytics/pricing/enhanced-evaluation-transparency> "ICE Enhanced Evaluation Transparency"
[V13]: <https://professional.bloomberg.com/products/data/enterprise-catalog/pricing/ibval-front-office/> "Bloomberg IBVAL Front Office"
[X28]: <https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/collectors/edgar_dilution.py> "Existing EDGAR dilution/refinancing filing-occurrence detector"
[V14]: <https://www.fitchratings.com/products> "Fitch products and delivery channels"
[M13]: <https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/research/TREND_PERSISTENCE_PREREG_C1.md> "Final-head Trend Persistence C1 preregistration; section0 and initial125lines reviewed"
[R01]: <https://github.com/mastermindx-market-intelligence/Mastermind/compare/a2646f458f9ff41ddcedd89b338be4a4349e6cd6...521720b09be2921e996d9396b522b1c4ca62041c> "Final protected revision drift comparison: mastermindx-market-intelligence/Mastermind"
[R02]: <https://github.com/mastermindx-market-intelligence/macro/compare/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3...59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc> "Final protected revision drift comparison: mastermindx-market-intelligence/macro"
