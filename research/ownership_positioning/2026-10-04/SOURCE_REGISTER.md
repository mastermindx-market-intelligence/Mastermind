# Commission 10 — source register

**Access/review date: 2026-10-04.** External pages are mutable unless a release/document version is specified. A website checked on this date is not a warranted contract, legal opinion, licensed sample or production-health proof. This register contains source links and bounded findings, not proprietary datasets or copied research text. The attached draft's session-local citation tokens were not reused as evidence.

## Internal evidence and immutable source identities

Mastermind pin: `521720b09be2921e996d9396b522b1c4ca62041c` (`master`, protected when read). Macro pin: `79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f` (`main`, protection flag false when read). Terminal pin: `1c708450187755160e1a5889b69598a2fcb1f0d1` (`master`, protected when read). Selected original file digests and Git blob IDs are in [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json).

“Source reviewed” means relevant source text/contracts were inspected. “Fetched” means exact bytes were retained and hashed; it does not imply every line was independently audited. No current R2/private-source runtime or browser acceptance is implied by either.

| ID | Exact evidence | Bounded use in this report |
|---|---|---|
| I01 | [Protected Skillpack index](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/sol_skills/INDEX.md) and same-pin COLD_START, ACTIVE_EXECUTION, SESSION_RELIABILITY, REVIEW_RETURN, CLOSEOUT | Atomic source-law bootstrap; all required texts read. Not runtime permission. |
| I02 | [Mastermind AGENTS.md](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/AGENTS.md#L196-L217) | One managed workspace, scoped PR publication, no direct master push; research/implementation/trading authority separation. |
| I03 | [Static census, lines 1–5](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/data/census/CENSUS.md#L1-L5) | Generated July 16, 2026; not a live feed-health verdict. |
| I04 | [portfolio/lenses.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/portfolio/lenses.py#L590-L623) | Existing flows_13f source consumer; relevant source excerpts reviewed, not live behavior tested. |
| I05 | [held_risk.py, lines 1125–1131](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/portfolio/held_risk.py#L1125-L1131) | Existing VIP selling context flag. |
| I06 | [research_desk.py, lines 50–70](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/brain/research_desk.py#L50-L70) | Existing multi-family research context and lag warning. |
| I07 | [Portfolio V3 design](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md#L1-L23) and [capability table](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md#L270-L285) | Source explicitly labels itself SPEC_ONLY/production-inert and lists unbuilt V3 capabilities; not a substitute for a runtime census. |
| I08 | [Trend Persistence protocol](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/research/TREND_PERSISTENCE_PROTOCOL.md) | Incumbent PIT/incrementality/research discipline; fetched source, relevant methodological context. |
| I09 | [Institutional 13F Census](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/docs/INSTITUTIONAL_13F_CENSUS.md) | Fully reviewed 162-line owner contract: four tiers, clocks, amendments, canonical JSON, paired cohorts, units, research readiness and health alarms. |
| I10 | [K2 institutional contract README](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/contracts/institutional_intelligence/README.md#L1-L160) | Reviewed lines 1–160: K1 references, actual-retention clocks, four-reference K2-C row basis, existing identity epochs, true-S/proxy separation and research planes. |
| I11 | [K2-C adapter](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/lib/institutional_13f_adapter.py) | Exact source fetched; implementation existence and contract interpreted through I10/I24 and merged PR. No production adapter execution. |
| I12 | [K2 compiler](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/lib/institutional_intelligence.py) and [recipe schema](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/contracts/institutional_intelligence/manager_intent_recipe.v1.schema.json) | Exact files fetched; the reviewed README defines the adopted boundary. Not a claim of an exhaustive compiler security audit. |
| I13 | [B0 current-repository institutional census](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/research/alpha_intelligence/censuses/B0/B0_CURRENT_REPO_INSTITUTIONAL_CENSUS.md) | Prior research to reconcile, not fresh operational truth. |
| I14 | [ownership_ledger.py](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/ownership_ledger.py#L1-L116) | Reviewed relevant comments/function excerpts: forward cohorts, sole nightly advancer, append/mature behavior; no outcome run performed. |
| I15 | [holdings_signals.py](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/holdings_signals.py#L1-L73) | Reviewed legacy weight-residual labels/math excerpts; semantic contrast with true-S K2. No runtime modification. |
| I16 | [ownership_crowding.py](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/ownership_crowding.py) | Existing display-only context, ADV/days-to-exit/crowding functions; not a proven fragility forecast. |
| I17 | [ownership_event_wire.py](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/ownership_event_wire.py) | Fetched existing event projection; preserve the prior no-fusion owner precedent. |
| I18 | [Company institutional context](https://github.com/mastermindx-market-intelligence/macro/tree/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/company_institutional_context) | contracts.py, views.py and health.py fetched; existing destination to adopt, not a live API proof. |
| I19 | [Terminal OwnershipPage.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/1c708450187755160e1a5889b69598a2fcb1f0d1/terminal/components/fin/OwnershipPage.tsx) | Current source exists, together with the company-context card. No browser inspection was run. |
| I20 | [Terminal company-context library](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/1c708450187755160e1a5889b69598a2fcb1f0d1/terminal/lib/companyInstitutionalContext.ts) | Library and matching API route fetched; repository description is not an adequate implementation census. |
| I21 | [Research Vault masterplan](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/research/RESEARCH_VAULT_MASTERPLAN.md#L33-L80) | Reviewed storage/catalog/rights excerpts; Macro vault modules fetched. This resolves the real estate, not a private production bucket inspection. |
| I22 | [Existing Stock Identity directory](https://github.com/mastermindx-market-intelligence/macro/tree/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/engine/stock_identity) | Owner identified by I29; no exhaustive mapping-population audit claimed. |
| I23 | [B0 source and rights registry](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/research/alpha_intelligence/censuses/B0/B0_SOURCE_AND_RIGHTS_REGISTRY.md) | Prior rights/availability work must be adopted and revalidated, not replaced by assumptions from public websites. |
| I24 | [K2-C pilot specification](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md) | Reviewed owner-read/proof-lane excerpts: source-bound rows, typed failures and restricted read-only workflow. |
| I25 | [Macro PR #7354](https://github.com/mastermindx-market-intelligence/macro/pull/7354) | OPEN DRAFT at census; head `b8833c40cb4c9541cc4449e72f5c5f8be8308d1a`; research-document deep reading, not canonical ownership acquisition. |
| I26 | [Macro PR #7387](https://github.com/mastermindx-market-intelligence/macro/pull/7387) | OPEN DRAFT at census; head `7931b0f5360d526b18191f987f5ec11d432a66eb`; longitudinal institutional-document evidence. |
| I27 | [Terminal PR #734](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/734) | MERGED 2026-09-25T03:27:29Z; head `b2b511144d609acf807ffc8bdcb35b61ea5b613a`; promoted Institutional workspace. |
| I28 | [Macro PR #6533](https://github.com/mastermindx-market-intelligence/macro/pull/6533) | MERGED 2026-08-27T08:54:36Z; head `9b331df00b5346e287999e5271d368e3ec3c7a4c`; K2-C owner-read adapter pilot. |
| I29 | [B0 collision/adoption map](https://github.com/mastermindx-market-intelligence/macro/blob/79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f/research/alpha_intelligence/censuses/B0/B0_COLLISION_AND_ADOPTION_MAP.md) | Fully reviewed 85-line prior map: no duplicate stores, identity/health/evaluation owners, source restrictions and historical Quiver warning. PR #5911 merged this prior research. |
| I30 | [PIT fundamentals](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/loop/fundamentals.py), [single-name panel](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/loop/single_name_panel.py), [experiment registry](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/brain/experiment_registry.py) | Existing methodology/registration source files fetched; no new experiments or broad runtime qualification. |

Additional exact source files, including beneficial-ownership collectors/engines, fund collectors, institutional census internals, V3 S0 plan, thematic framework and root instructions, are enumerated in the manifest. They are supporting source availability, not extra independently tested capabilities.

## External primary sources

## R01
**SEC — Frequently Asked Questions About Form 13F.** [Official FAQ](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f). Relevant sections: reporting universe/deadline; discretion and other managers; trade date; optional small-position omission; XML and value-unit changes. Staff guidance should be read with the operative form/rules. No private SEC feed or filing population was downloaded.

## R02
**SEC — Form 13F Data Sets.** [Official dataset documentation](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets). Structured bulk history, as-filed extraction and documented bulk corrections. Dataset revision time is distinct from the filing's original public time; download coverage does not certify every row's units or completeness.

## R03
**SEC — Modernization of Beneficial Ownership Reporting**, adopted October 10, 2023, Releases 33-11253 / 34-98704. [Final release PDF](https://www.sec.gov/files/rules/final/2023/33-11253.pdf). Filing-deadline comparison tables on printed pages 10–11 were inspected visually, as were effective/compliance discussions. Exact current thresholds and exceptions were cross-checked against official [17 CFR 240.13d-1](https://www.ecfr.gov/current/title-17/chapter-II/part-240/subject-group-ECFRb8a264d3a4d1c48/section-240.13d-1) and [17 CFR 240.13d-2](https://www.ecfr.gov/current/title-17/chapter-II/part-240/subject-group-ECFRb8a264d3a4d1c48/section-240.13d-2). Preserve strict greater-than thresholds, percentage-point rather than relative changes, passive eligibility, denominator-only exceptions and the applicable cessation of amendment duty. The report's table is an architecture summary, not an exhaustive legal rules engine.

## R04
**SEC — Sections 13(d)/13(g) and Regulation 13D-G Compliance and Disclosure Interpretations.** [Current staff interpretations](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/exchange-act-sections-13d-13g-regulation-13d-g-beneficial-ownership-reporting). Supports preserving category, trade/event and disclosure distinctions. Current staff interpretations must not be projected into earlier periods without a versioned legal regime.

## R05
**SEC — Form 4 and instructions**, reviewed form revision 03-26. [Official form PDF](https://www.sec.gov/files/form4.pdf). Transaction-code and amendment/plan instruction pages were inspected visually. P/S include private transactions; Form 4/A may address particular lines. This document defines disclosure semantics, not a model of insider intent.

## R06
**SEC — Insider Transactions Data Sets.** [Official dataset documentation](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets). Structured Forms 3/4/5 history from January 2006 and the July 2025 reprocessing notice for the AFF10B5ONE field. Public bulk versions are not guaranteed to match a system's original ingestion.

## R07
**SEC — Holding Foreign Insiders Accountable Act: Section 16(a) Reporting Requirements.** [Official requirements and exemptive orders](https://www.sec.gov/about/divisions-offices/division-corporation-finance/holding-foreign-insiders-accountable-act-section-16a-reporting-requirements). Reviewed page updated May 20, 2026. Effective March 18, 2026 for covered FPI directors/officers; conditional orders include Releases 34-104931 and 34-105517. Country presence alone does not establish satisfaction of an order.

## R08
**SEC — HFIA Act Frequently Asked Questions.** [Official FAQ](https://www.sec.gov/about/divisions-offices/division-corporation-finance/holding-foreign-insiders-accountable-act-frequently-asked-questions). Complements R07 on initial reports and filing requirements. Regime/role-specific eligibility must be preserved; newly required reporting is not itself a transaction.

## R09
**SEC — Form N-PORT/N-CEN delay of effective and compliance dates**, Investment Company Act Release 35538, April 16, 2025. [Official docket](https://www.sec.gov/rules-regulations/2025/04/s7-26-22), [final release](https://www.sec.gov/files/rules/final/2025/ic-35538.pdf). N-PORT dates deferred to November 17, 2027 / May 18, 2028. Do not confuse cadence thresholds with separate Names Rule thresholds or assume N-CEN has the same delay.

## R10
**SEC — Form N-PORT Reporting**, proposed February 18, 2026, IC-35962 / S7-2026-05. [Official docket](https://www.sec.gov/rules-regulations/2026/02/s7-2026-05), [proposed release](https://www.sec.gov/files/rules/proposed/2026/ic-35962.pdf#page=9). The docket was explicitly Proposed when checked. Table 1 on printed page 9 was visually inspected: current quarter-based submission/public-third-month-on-filing versus deferred monthly disclosure and proposed quarterly release. The proposal is not current final law.

## R11
**SEC — Form N-PORT Data Sets.** [Official public dataset documentation](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets). Public structured history begins October 2019. A dataset containing monthly-form records is not evidence that every month was public. No nonpublic portfolio data was accessed.

## R12
**SEC — Exchange-Traded Funds: Small Entity Compliance Guide.** [Official Rule 6c-11 guide](https://www.sec.gov/investment/exchange-traded-funds-small-entity-compliance-guide), [2019 adoption announcement](https://www.sec.gov/newsroom/press-releases/2019-190). Relevant requirements: daily disclosure for covered products and custom-basket flexibility. The guide is not proof that every ETF/ETP falls under that rule or uses pro-rata baskets.

## R13
**ARK Funds — Trade Notifications.** [First-party service description and limitations](https://www.ark-funds.com/ark-trade-notifications). Observed distinctions: daily portfolio files versus notifications, exclusions, later files and unofficial/unreconciled status. The page is not a full historical execution dataset. Potentially stale boilerplate, including settlement language, was not adopted as a current market rule.

## R14
**ARK Funds — Historical Trades FAQ.** [First-party archive statement](https://helpcenter.ark-funds.com/do-you-share-historical-trades), [holdings download FAQ](https://helpcenter.ark-funds.com/where-can-i-download-the-latest-etf-holdings). The reviewed page says historical trade archives are not provided. Prospective retention and redistribution require separate source-rights qualification.

## R15
**SEC — Developer Resources.** [Official access guidance](https://www.sec.gov/about/developer-resources). Existing EDGAR APIs/files/RSS and fair-access limit, stated across machines. Later implementation must use the incumbent acquisition owner and a shared access budget; this report does not authorize bulk crawling or a new ingestion client.

## R16
**Electronic Code of Federal Regulations — 17 CFR 240.13d-3.** [Official determination-of-beneficial-owner rule](https://www.ecfr.gov/current/title-17/chapter-II/part-240/subject-group-ECFRb8a264d3a4d1c48/section-240.13d-3). Relevant: class aggregation, acquisition rights and holder-specific denominator treatment. Store reported legal fractions separately from a generic common-share fraction.

## R17
**FactSet — Ownership Standard DataFeed overview.** [Vendor publication](https://insight.factset.com/resources/at-a-glance-factset-ownership-standard-datafeed). Historical product overview, not a newly tested feed. Historical coverage claims are product-scope claims; current fields, latency, revisions, entitlements and price remain unverified.

## R18
**LSEG — Ownership data catalogue.** [Vendor dataset page](https://www.lseg.com/en/data-catalogue/company-data/ownership/ownership), [company ownership overview](https://www.lseg.com/en/data-analytics/financial-data/company-data/company-ownership-information-profiles). Advertised history differs by US/global and institutional/fund/insider source. No licensed extract was inspected.

## R19
**LSEG — Ownership API.** [Vendor developer catalogue](https://developers.lseg.com/en/api-catalog/refinitiv-data-platform/ownership-API). Existence of an API is documented; original public-time precision and historical correction behavior require a sample contract and replay test.

## R20
**S&P Global Marketplace — Ownership.** [Vendor dataset listing](https://www.marketplace.spglobal.com/en/datasets/ownership-%2820%29). Public listing describes history, filing/holding dates and delivery channels. Its PIT label is not proof of retained historical normalization vintages or intraday availability. No quote or licensed delivery tested.

## R21
**Morningstar Direct Web Services — Managed Investments Async OpenAPI.** [Vendor OpenAPI documentation](https://developer.morningstar.com/direct-web-services/documentation/direct-web-services/investment-details---managed-investments---async/openapi-specification). Reviewed request capabilities include a bounded history request and delta loading. Request limits do not establish total coverage or first-public timestamps.

## R22
**Morningstar Data — Holdings API documentation.** [Vendor documentation](https://docs-analyticslab.morningstar.com/1.3.1/morningstar_data/holdings.html). Portfolio-date retrieval is documented; availability and historical revision lineage remain separate qualification questions. This versioned page does not prove current account entitlement.

## R23
**Bloomberg — Data License.** [Vendor delivery overview](https://professional.bloomberg.com/products/data/data-license/). General machine-delivery capabilities documented. Ownership-specific source history, redistribution and programmatic rights were not established; a terminal subscription must not be assumed sufficient.

## R24
**WhaleWisdom — API help.** [Vendor API](https://whalewisdom.com/help/api). The documented `include_13d` option can blend/replace latest 13F positions with later D/G information. That convenience must be disabled or explicitly separated in a canonical 13F experiment. API fields are not an SEC acceptance-time warranty.

## R25
**WhaleWisdom — Subscription information.** [Vendor plans/history](https://whalewisdom.com/info/subscription_info). Used only to establish self-service versus enterprise delivery and advertised Q1 2001 history. No purchase recommendation or fixed future price is inferred.

## R26
**Quiver Quantitative — Hedge Fund Activity dataset.** [Vendor endpoint documentation/sample](https://api.quiverquant.com/datasets/hedge-fund-activity). Shows Date and ReportPeriod as separate fields; does not certify that a date-only timestamp is the first public availability. No additional account or source authority was granted.

## R27
**Benzinga — Institutional Portfolio Intelligence API.** [Vendor product documentation](https://www.benzinga.com/apis/cloud-product/institutional-portfolio-intelligence-api/). Advertised 13F history and normalized delivery; marketing flow labels do not override legal disclosure semantics. Current contract/rights/latency remain untested.

## R28
**Coval, Joshua; Stafford, Erik — Asset Fire Sales (and Purchases) in Equity Markets.** [NBER Working Paper 11357](https://www.nber.org/papers/w11357), published JFE 86(2), 2007, 479–512. Primary abstract and publication record reviewed; no numerical replication. Used for the forced-flow mechanism, not a current alpha forecast.

## R29
**Lou, Dong — A Flow-Based Explanation for Return Predictability.** [LSE Financial Markets Group publication record](https://www.fmg.ac.uk/publications/academic-journals/flow-based-explanation-return-predictability), RFS 25(12), 2012, 3457–3489. Bibliographic primary record verified. This audit does not claim full-text methodological verification from that record alone.

## R30
**Greenwood, Robin; Thesmar, David — Stock Price Fragility.** [Publisher article/abstract](https://www.sciencedirect.com/science/article/pii/S0304405X11001474), JFE 102(3), 2011, 471–490. Primary abstract/introduction reviewed. Supports studying ownership structure plus correlated liquidity shocks, not treating HHI as a complete fragility estimate.

## R31
**Cohen, Lauren; Malloy, Christopher; Pomorski, Lukasz — Decoding Inside Information.** [NBER Working Paper 16454](https://www.nber.org/papers/w16454), published JF 2012. Primary abstract/publication record reviewed. No replication or claim that a 2026 P/S-code strategy earns the paper's reported returns.

## R32
**Brav, Alon; Jiang, Wei; Partnoy, Frank; Thomas, Randall — Hedge Fund Activism, Corporate Governance, and Firm Performance.** [Author-institution record/abstract](https://business.columbia.edu/faculty/research/hedge-fund-activism-corporate-governance-and-firm-performance), JF 63, 2008, 1729–1775. Primary abstract reviewed. Activism/event mechanisms do not establish an executable post-filing strategy or make every 13D activist.

## R33
**Edelen, Roger; Ince, Ozgur; Kadlec, Gregory — Institutional Investors and Stock Return Anomalies.** [Publisher article/abstract](https://www.sciencedirect.com/science/article/pii/S0304405X16000039), JFE 119(3), 2016, 472–488. Primary abstract/introduction reviewed. Important contrary evidence: institutional-demand associations depend on horizon and can oppose anomaly returns; no blanket smart-money presumption.

## R34
**Friberg, Richard; Goldstein, Itay; Hankins, Kristine — Corporate Responses to Stock Price Fragility.** [Publisher article/abstract](https://www.sciencedirect.com/science/article/pii/S0304405X24000187), JFE, March 2024, article 103795. Primary abstract/introduction reviewed. Used to motivate corporate-risk/context outcomes, not to claim causal identification in Mastermind data.

## Research limitations and source-admission rules

This register verifies documentation and selected source code, not all licensed fields, historical vintages or live service health. SEC datasets, issuer/sponsor filings and vendor derivatives are not interchangeable. Primary legal text controls deadlines; actual observed publication controls the information set. Vendor documentation controls only what is represented publicly, until a lawful sample and contract prove what will be delivered.

No proprietary corpus, broker research text, vendor data dump, private Research Vault PDF or credential was copied. No API account, subscription or automated source capture was created. Public URLs are references; retention and commercial use of underlying content remain governed by the existing source-rights owner.
