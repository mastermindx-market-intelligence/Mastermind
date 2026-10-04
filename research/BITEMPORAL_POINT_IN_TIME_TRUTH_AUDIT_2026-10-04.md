# Bitemporal Data, Corrections & Point-in-Time Truth
## Audit, hardening, and integration recommendation for MastermindX

**Status:** Research-only audited report. No implementation, deployment, purchase, vendor contact, trading change, or new source authority is authorized by this document.

**Audit date:** 2026-10-04

**Protected Mastermind source pin:** [84df29801d4078724c2b603a136de5aa1532cdfe](https://github.com/mastermindx-market-intelligence/Mastermind/commit/84df29801d4078724c2b603a136de5aa1532cdfe)

**Sibling source pins used for current-state context:**
- Macro: [f9ed175800257b228166dabe8b3ac9a55e74e237](https://github.com/mastermindx-market-intelligence/macro/commit/f9ed175800257b228166dabe8b3ac9a55e74e237)
- Terminal: [9e2f0bd94a2ee876c7dbafacb072414635277a36](https://github.com/mastermindx-market-intelligence/mastermind-terminal/commit/9e2f0bd94a2ee876c7dbafacb072414635277a36)
- Executive DR vault: [ea422c92bd29800d1f7fb3ae850236cc44d8c890](https://github.com/mastermindx-market-intelligence/executive-dr-vault/commit/ea422c92bd29800d1f7fb3ae850236cc44d8c890)

The earlier protected Mastermind reference d1594f3c7ae750db3f14b4eebf0de3460f84267a is stale. The audit re-read docs/sol_skills/INDEX.md, ACTIVE_EXECUTION.md, SESSION_RELIABILITY.md, and REVIEW_RETURN.md from the protected source pin above before modification.

This report is evidence and recommendation, not protected law. Existing owners remain owners. In particular, Macro already contains a temporal standard and executable temporal primitives; Portfolio V3 already specifies a Decision Snapshot/source-receipt direction. This report must not become a parallel temporal warehouse, correction ledger, lifecycle, queue, publication plane, or control plane.

---

## Audit findings / corrections to the prior draft

The hardening pass materially changes the answer.

1. **Point-in-time infrastructure is not absent.** Mastermind already has PIT-gated consumers, survivorship-aware membership reads, and append-only first-seen signal history. Macro has substantially more temporal infrastructure, including ALFRED vintage access, an executable temporal model, expectation-market clock fields, append-only prospective accrual, and a dedicated temporal standard. The problem is fragmentation, inconsistent semantics, incomplete adoption, and uneven source quality—not a blank-slate absence.

2. **Mastermind loop/fundamentals.py is causal, but its upstream annual availability clock is not a true filing timestamp.** The reader correctly filters to asof_date <= decision date and refuses today's fundamentals on a past date. However, current Macro evidence documents fundamentals_panel.parquet as using a conservative period_end + 120-day proxy for asof_date, not per-filer SEC publication/acceptance time. Calling that field a filing date is too strong. Macro's statements_quarterly.parquet is the stronger local fundamentals surface because it carries a genuine per-row filed field. See [Mastermind fundamentals reader](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/loop/fundamentals.py#L1-L16) and [Macro temporal standard](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/research/MASTERMIND_TEMPORAL_DATA_STANDARD.md).

3. **Restatement behavior is mixed, not uniformly safe or uniformly leaky.** Macro's annual statements path is documented as latest-filed-wins and therefore discards prior vintages; quarterly statements retain filed dates; the annual fundamentals panel uses a conservative lag proxy; ALFRED retains vintages; prospective expectation accrual is append-oriented. The right remediation is source-specific, not a universal database rewrite.

4. **A common temporal vocabulary already exists in Macro.** [lib/dataos/temporal.py](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/lib/dataos/temporal.py) defines period/event/effective/published/ingested/computed/served clocks and fail-closed PIT reads. Any Mastermind-side implementation should interoperate with that vocabulary and with Portfolio V3 receipts instead of inventing a second standard.

5. **Historical analyst-estimate PIT is still not mature, but current/prospective expectation infrastructure is more advanced than the prior draft implied.** Macro's current expectation collector carries source_effective_at, source_published_at, provider_observed_at, system_observed_at, correction_state, supersedes_observation_id, observation_id, and collection_session_id. Its institutional-vendor bake-off still correctly concludes SAMPLE_REQUIRED / PROBE_FURTHER for LSEG I/B/E/S, FactSet, S&P Capital IQ Estimates, and Visible Alpha; public product claims are not record-level proof or rights clearance. See [collector](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/collectors/equity_revisions.py) and [VEND-0 bake-off](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/research/alpha_intelligence/expectation_market_dynamics/VEND_0_INSTITUTIONAL_ESTIMATES_BAKEOFF_2026-08-23.md).

6. **Portfolio V3's richer source-receipt/Decision Snapshot contract remains specification/plan evidence in Mastermind, not proven implementation.** Searches for mastermind.portfolio_source_receipt.v1, portfolio_decision_snapshot, DecisionSnapshot, and correction_generation found the Portfolio V3 spec/plan and no corresponding portfolio implementation at the protected pin. See [V3 design](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md) and [S0 Decision Snapshot plan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md).

7. **Historical index membership is PIT-aware but source-limited.** The S&P 400/600 reconstruction in Macro walks Wikipedia current constituents and changes logs backward, explicitly admitting coverage ceilings and orphan-change risk. That is materially better than current-membership look-ahead, but it is not equivalent to an official licensed historical constituent file. See [midsmall_pit.py](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/scripts/midsmall_pit.py).

8. **known_at cannot be a universal alias for as_of, observed_at, ingested_at, or filesystem mtime.** The hardened model distinguishes market availability from Mastermind's own first durable knowledge and from actual served-output replay. A historical vendor backfill may prove when the market could have known a value without proving that Mastermind actually possessed it then.

9. **Storage technology is not the decision.** SQL:2011 system-versioned tables, Delta Lake, event sourcing, append-only JSONL, Parquet generations, or a relational ledger can all implement the logical semantics. None is mandated here. The existing estate already uses several lawful physical forms.

10. **No SEC, FINRA, or other regulatory rule found in this audit requires Mastermind to implement this architecture.** Regulatory filing deadlines matter as source latency facts; they are not architecture mandates.

11. **Universal statistical thresholds are rejected.** No blanket p < 0.05, coverage > 50%, or correlation > 0.9 rule is recommended. Acceptance and kill criteria must be predeclared for the specific evidence family, horizon, economic use, missingness pattern, and trial count.

---

# A. Executive conclusion

MastermindX does not need a new bitemporal warehouse. It needs a **small, enforceable temporal contract across existing owners**, plus source-specific repair where historical availability is currently proxied, overwritten, or unrecoverable.

The highest-value finding is that the estate already contains most of the conceptual pieces:

- Mastermind has PIT-gated fundamentals consumption, PIT membership consumption, append-only first-seen signal history, lag-aware 13F doctrine, and a Portfolio V3 source-receipt/Decision Snapshot design.
- Macro has ALFRED vintage handling, temporal profiles, fail-closed as-of primitives, a temporal standard, PIT membership builders, a prospective expectation-market collector with multiple clocks and correction lineage, and an institutional estimates vendor bake-off.
- The remaining institutional gap is **conversion of these local disciplines into a common evidence contract that every historical research or decision consumer can enforce without guessing**.

The P0 recommendation is therefore not "build bitemporality." It is:

1. establish a current cross-repo temporal census and semantic mapping;
2. distinguish actual source publication/availability clocks from conservative proxies;
3. attach a minimal source/record receipt to existing artifacts;
4. make historical research consumers fail closed when the required clock is absent or only current-state data exist;
5. implement Portfolio V3's existing Decision Snapshot direction without a second correction ledger; and
6. validate that each incremental evidence family adds independent predictive information rather than duplicating existing price, breadth, macro, revisions, or positioning evidence.

The central invariant is simple: **a decision at cutoff T may consume only a record whose admissible availability clock is proven to be <= T under the declared replay mode.** The hard part is declaring which clock is admissible for each source and refusing to substitute a weaker clock silently.

---

# B. Current-state census: built versus spec

Protected-state vocabulary is used where possible. "BUILT_NOT_PROVEN" means code/tests or artifacts exist but this audit did not prove current production execution.

| Capability | Evidence | State | Hardened interpretation |
|---|---|---|---|
| Mastermind annual fundamentals PIT read | loop/fundamentals.py filters asof_date <= t and explicitly rejects current fundamentals for past dates | BUILT_NOT_PROVEN | Consumer logic is causal; upstream annual asof_date is a conservative 120-day proxy, not a true filing timestamp |
| Mastermind single-name PIT membership | loop/single_name_panel.py reads start_date/end_date intervals and applies membership as of t | BUILT_NOT_PROVEN / PARTIAL | Correct interval consumption; upstream 400/600 history is reconstructed from Wikipedia changes logs with coverage ceilings |
| Mastermind signal history | brain/signal_history.py append-only JSONL, KEEP-FIRST per day/ticker, never overwrites first observed state | BUILT_NOT_PROVEN | Strong local first-seen primitive; missed days remain unreconstructable |
| Mastermind SQL system of record | sql/0001_schema.sql | BUILT_NOT_PROVEN | Mutable operational state with coarse asof fields; not a general PIT corpus and should not be turned into one by default |
| Mastermind research desk temporal doctrine | brain/research_desk.py | BUILT_NOT_PROVEN | Correctly treats 13F as lagged context and forbids tying quarter-end holdings to recent price moves |
| Portfolio V3 Decision Snapshot / source receipt | V3 spec + S0 plan | SPEC_ONLY | Good direction; no corresponding portfolio implementation found at protected pin |
| Portfolio V3 correction_generation | V3 spec + S0 plan | SPEC_ONLY | Artifact-generation concept exists in design only; do not create a second correction ledger |
| Macro temporal profiles / fail-closed PIT | research/MASTERMIND_TEMPORAL_DATA_STANDARD.md + lib/dataos/temporal.py | BUILT_NOT_PROVEN | Existing temporal owner/primitives; adoption and consumer coverage, not vocabulary invention, are the main gap |
| Macro ALFRED vintage path | collectors/fred.py + engine/pit.py referenced by temporal standard | BUILT_NOT_PROVEN / PARTIAL | Vintage capability exists; temporal standard documents adoption gaps and historical drift between configured and materialized series at its audit date |
| Macro annual EDGAR fundamentals panel | data/edgar/fundamentals_panel.parquet contract | PARTIAL | PIT-gated by period_end + 120d proxy; safe as a declared conservative approximation, not true publication time |
| Macro quarterly EDGAR statements | statements_quarterly.parquet | PARTIAL | Carries genuine filed date; extraction/as_of and restatement semantics still need explicit treatment per use |
| Macro annual normalized statements | statements.parquet / collectors/edgar_facts.py | PARTIAL | Latest-filed-wins behavior discards prior vintages; not historical-replay safe |
| Macro prospective expectation revisions | collectors/equity_revisions.py | BUILT_NOT_PROVEN / PARTIAL | Multiple clocks and correction lineage are present; institutional historical PIT depth remains unproven |
| Institutional estimates history | VEND-0 bake-off | SAMPLE_REQUIRED | Four credible candidates; no winner, no rights clearance, no record-level replay proof |
| Fine-grained dynamic subtheme identity | trend protocol and theme framework | PARTIAL | Theme/source versioning exists, but no single canonical effective-dated dynamic subtheme identity layer was proven |
| Static census | data/census/CENSUS.md generated 2026-07-16 | STALE_EVIDENCE | Useful inventory, but nearly three months old at this audit and missing later Macro temporal work |

### Wider ecosystem identity check

- mastermindx-market-intelligence/Mastermind — protected source repo.
- mastermindx-market-intelligence/macro — actual Macro repo; Mastermind .gitmodules points vendor/macro at this repository.
- mastermindx-market-intelligence/mastermind-terminal — actual Terminal repo.
- mastermindx-market-intelligence/executive-dr-vault — accessible DR artifact vault. No separate repository literally matching "Research Vault" was resolved in the organization search used for this audit; treat that identity as UNKNOWN rather than aliasing it without evidence.

---

# C. State of the art relevant to MastermindX

Institutional PIT systems separate at least three ideas that are often collapsed:

1. **valid/effective time** — when a fact applies to the world;
2. **availability/transaction time** — when a source or provider made that version knowable; and
3. **system/replay time** — when the consuming system actually possessed or served it.

A robust finance implementation then adds revision lineage, immutable receipts, source identifiers, corporate-action/entity identity, and an explicit decision cutoff.

For economic data, ALFRED is a canonical public example: observation dates describe the period, while realtime_start/realtime_end describe the vintage interval. The FRED API also supports initial-release-only output and explicit vintage dates.

For filings, SEC EDGAR exposes filing/acceptance metadata, but the SEC explicitly notes that acceptance time is not the same thing as guaranteed public availability on sec.gov; public dissemination can lag. That distinction is exactly why source_published_at, provider_available_at, observed_at, and ingested_at should not be collapsed.

For analyst expectations, institutional products explicitly market PIT snapshots rather than lagged current databases. The key differentiator is not "has history" but whether a record-level sample proves as-known values, revision/correction lineage, fiscal-period identity, contributor entitlements, and lawful storage/derived-data rights.

For model validation, finance-specific leakage controls matter because labels and features often overlap through time. Purging/embargoing is appropriate when train/test label intervals overlap; it is not a ritual to apply blindly. Multiple-testing controls and backtest-overfitting diagnostics are required when many variants are tried.

**Storage neutrality:** bitemporal semantics do not imply a mandatory physical database. MastermindX already has append-only JSONL, Parquet histories, relational state, immutable content-addressed design proposals, and forward logs. The logical contract should sit above those forms.

**Recompute is not replay:** recomputing a 2022 input with 2026 code can be reproducible without reproducing what the system actually emitted in 2022. Actual replay requires served-output or Decision Snapshot evidence.

---

# D. Source landscape

"Cost class" is deliberately coarse. Public product pages are not authoritative quotes. Contract rights remain UNKNOWN until the applicable agreement/order form is reviewed.

| Source | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| SEC EDGAR / data.sec.gov | US public filings, XBRL facts, insider and institutional forms | Deep filing history; API coverage varies by endpoint | Filing/acceptance driven; public dissemination can lag acceptance | High for filing chronology when acceptance/filing metadata retained | Amendments and later filings are explicit; normalized fact stores can still overwrite if collector discards vintages | Public access subject to SEC fair-access policy; downstream reuse still needs source-specific care | Public/free | Filing-time fundamentals, Form 4, 13F, earnings/event anchors |
| SEC Form 4 | Officers, directors, >10% holders | EDGAR history | Generally due by end of second business day after reportable transaction | High for disclosed transaction chronology; not real-time trading flow | Amendments possible | Public filing | Public/free | Insider context with explicit filing lag |
| SEC Form 13F | Qualifying institutional managers | EDGAR history | Due within 45 days after quarter end | High for what was filed; intrinsically stale for live-flow inference | Amendments possible | Public filing | Public/free | Lagged positioning context, never recent dip-buying inference |
| FRED / ALFRED | US macro/economic series | Series-dependent; vintage histories available for many revisable series | Release-dependent; ALFRED says additions/revisions are generally added as soon as possible, typically within one business day | Very high where realtime/vintage coverage exists | Explicit vintages and real-time periods | Public API terms | Public/free | Revision-aware macro replay and initial-release studies |
| Official S&P DJI index pages/data products | S&P index definitions and constituents | Current public constituent views; historical constituent entitlement not established here | Index-announcement/effective-date dependent | Potentially high if licensed historical membership is obtained | Index reconstitutions/changes explicit | Historical use/redistribution rights UNKNOWN without contract | Commercial/unknown | Canonical historical membership if licensed |
| Existing Wikipedia-derived S&P 400/600 reconstruction | Free public changes logs + current members | Approx. 2012+ mid-cap; approx. 2020+ small-cap per current script | Page/update dependent | Better than current-membership look-ahead, but not official and incomplete | Orphan adds skipped conservatively | Public-page reuse considerations | Public/free | Research fallback with explicit coverage ceiling |
| LSEG I/B/E/S Point-in-Time | Global analyst estimates | Vendor claims US to 1976 / non-US to 1987 for product family; PIT product details vary | Vendor brochure describes PIT snapshots and scheduled delivery; exact entitlement must be sampled | Promising; record-level semantics not yet sampled | Public material supports historical/PIT products; exact correction lineage unproven | RIGHTS_UNVERIFIED | Commercial/quote | Institutional expectations, revisions, surprise baselines |
| FactSet Estimates PIT Consensus | Global consensus estimates | PIT history publicly described from Dec. 2009 | Daily snapshots; delivery cadence documented by product | Promising; sample required for Mastermind semantics | PIT methodology explicitly distinguishes later QA/currency/dilution effects | RIGHTS_UNVERIFIED | Commercial/quote | Consensus history and revision chronology |
| S&P Capital IQ Estimates Snapshot | Global sell-side estimates | Snapshot history since Aug. 2016; broader estimate history is deeper | Snapshot every two hours per official product page | Strong public PIT claim with spEffectiveDate/spToDate; sample still required | All estimate changes represented in snapshot product claim | RIGHTS_UNVERIFIED | Commercial/quote | Intraday-ish expectation history and revision analysis |
| S&P Compustat Financials Snapshot | Standardized company fundamentals | North America PIT snapshots since 1987 per Marketplace | Product page says intraday dataset latency | Strong commercial PIT claim | Point-in-time snapshot changes with associated point dates | RIGHTS_UNVERIFIED | Commercial/quote | Long-horizon PIT fundamentals and entity/corporate-action research |
| Visible Alpha | Granular broker models/KPIs | Official product page cites historical depth by region; exact PIT replay semantics not established here | Intraday/current updates marketed | Useful candidate, but no record-level PIT contract proven | Revision activity marketed; lineage semantics need sample | RIGHTS_UNVERIFIED | Commercial/quote | Deep KPI expectations after sample/rights gate |
| Cboe DataShop historical options | US options datasets | Product-specific | Product-specific | Potentially strong for historical options if trade/quote timestamps and NBBO context are licensed | Product-specific | Commercial license | Commercial | Historical options microstructure/volatility; avoid signed-flow claims without required quote context |
| Nasdaq Historical TotalView-ITCH | Nasdaq order/trade events | Official page says back to 2014 | T+1 historical logs | High event-time fidelity for Nasdaq book events | Exchange corrections are feed/product specific | Exchange/vendor agreement governs use | Commercial | Market microstructure and auction/order-book research |
| CFTC Commitments of Traders | Futures positioning | Viewable weekly reports from 2005; compressed history is deeper | Weekly; report date is not release date | Good if release date is separately retained | Revisions/corrections source-specific | Public government data | Public/free | Macro positioning with explicit release lag |
| USAspending API | Federal awards/contracts | Endpoint-dependent; history varies by award type | Administrative/reporting lag | Moderate; not a trading-timestamp source | Award updates/modifications occur | Public government data | Public/free | Government-contract evidence with modification lineage |
| House / Senate PTR disclosures | Reportable personal securities transactions | Electronic public disclosures | Earlier of 30 days after notice or 45 days after transaction for House; Senate no later than 30 days after notice and never later than 45 days after transaction | Good for disclosed transactions, poor for real-time inference | Amendments possible | Public disclosure; scraping/redistribution terms must be respected | Public/free | Political-positioning context with explicit disclosure lag |
| NYSE / Nasdaq real-time market data | Exchange quotes/trades/order books | Product-specific | Real time for subscribed feeds | High event-time quality when direct-feed semantics are retained | Feed corrections/cancels are product-specific | Contracted; redistribution/non-display terms matter | Commercial | Price/quote/order-book evidence where latency and rights justify cost |

### Primary public source notes

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC EDGAR timestamp/dissemination FAQ: https://www.sec.gov/about/webmaster-frequently-asked-questions
- SEC Form 4 instructions: https://www.sec.gov/about/forms/form4data.pdf
- SEC Form 13F FAQ: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f
- FRED observations/vintages: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- FRED real-time periods: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- ALFRED help: https://alfred.stlouisfed.org/help
- LSEG quant/PIT brochure: https://www.lseg.com/content/dam/data-analytics/en_us/documents/brochures/lseg-data-for-quant-research-brochure.pdf
- FactSet PIT methodology: https://insight.factset.com/hubfs/Resources%20Section/White%20Papers/ID11996_point_in_time.pdf
- S&P Capital IQ Estimates: https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates
- S&P Compustat Financials: https://www.marketplace.spglobal.com/en/datasets/compustat-financials-%288%29
- Visible Alpha: https://www.spglobal.com/market-intelligence/en/solutions/products/visible-alpha-insights
- Nasdaq TotalView/Historical ITCH: https://www.nasdaq.com/products/data/equities/nasdaq
- CFTC COT history: https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm
- USAspending API: https://api.usaspending.gov/
- House financial disclosure: https://ethics.house.gov/financial-disclosure/
- Senate financial disclosure: https://www.ethics.senate.gov/public/index.cfm/financialdisclosure
- NYSE market-data contracts/policies: https://www.nyse.com/market-data/pricing-policies-contracts-guidelines

---

# E. Canonical data model

## E1. Do not create one giant temporal table

The smallest useful contract has two layers:

### Artifact/source receipt

Required where an artifact enters or crosses an owner boundary:

- receipt_schema_version
- source_id
- source_owner
- source_uri or source_locator
- artifact_digest
- schema_or_definition_id
- observed_at
- ingested_at, when distinct and available
- source_published_at, nullable
- provider_available_at, nullable
- clock_basis for every non-null availability clock
- coverage_state
- freshness_state
- rights_class
- correction_generation, when the artifact itself has generations
- parent_receipt_ids or input_receipts for derived artifacts

This should extend/map to Portfolio V3's existing source-receipt direction rather than replace it.

### Record-level temporal fields

Only datasets that need record-level replay carry record clocks:

- entity_id and source-native identifier
- metric/event identifier
- period_start / period_end, when the record describes an interval
- event_at, when an event actually occurred
- effective_from / effective_to, when applicability differs from event time
- source_published_at, when the original source made the information public
- provider_available_at, when an intermediary made the record available
- system_observed_at / ingested_at, when Mastermind first durably captured it
- revision_seq or correction_generation
- supersedes_record_id
- payload_hash
- source_receipt_id
- missingness_reason / entitlement_state where applicable

No source is forced to populate clocks it cannot know. Unknown remains null plus an explicit basis/state.

## E2. Harden known_at into two concepts

A single persisted known_at is too easy to misuse across research and actual-system replay.

**market_available_at** answers: when could a market participant with this declared source/provider have obtained this version?

**system_known_at** answers: when did Mastermind itself first durably possess this version?

Eligibility then depends on replay mode:

- Historical market simulation may use market_available_at if the source/provider proves it and the historical entitlement/source assumption is declared.
- Actual Mastermind replay requires system_known_at and, for emitted intelligence, the served Decision Snapshot/forward-log record.
- Forward-accrued local data can conservatively use first durable ingestion/observation as system_known_at.
- A backfilled current snapshot with no historical availability metadata is **not** historical PIT merely because its period_end is old.
- A conservative proxy such as period_end + 120 days may be used only when typed as a proxy; it must never be relabeled as an actual filing/publication timestamp.

## E3. Clock semantics

| Clock | Meaning | Never substitute with |
|---|---|---|
| period/event time | what/when the underlying event or period describes | publication or knowledge time |
| effective time | when a rule, membership, split, identifier, or classification applies | ingestion time |
| source_published_at | when the source says the version was published/accepted/released | filesystem mtime |
| provider_available_at | when a vendor made that version available | source publication if vendor delay is unknown |
| observed_at | when the collector observed the artifact/record | event time |
| ingested_at / system_known_at | first durable Mastermind possession | a historical period date |
| correction time/generation | when a later version superseded an earlier one | original publication time |
| decision_cutoff_at | the instant against which admissibility is tested | run date without timezone/session semantics |
| served_at | when Mastermind actually emitted an intelligence artifact | recomputation time |

Filesystem mtime is provenance about a local file, not evidence of when the market could know its contents. Portfolio V3's plan is correct to keep filesystem_observed_at separate.

## E4. Corrections

Corrections append or supersede. They do not erase the prior as-known record.

A lawful chain preserves:
- immutable prior payload hash;
- new payload hash;
- correction/revision generation;
- supersedes link;
- the new publication/provider/system clock;
- a reason/class when known: source amendment, vendor correction, parser correction, mapping correction, corporate-action restatement, or manual quarantine.

Do not create a second correction ledger if an owner already has one. Store lineage with the owner or in the existing receipt/forward-log primitive and expose it through the common contract.

---

# F. Derived intelligence

The temporal substrate is useful only if it produces inspectable evidence.

Deterministic first:
- estimate revision velocity by horizon and fiscal period;
- consensus dispersion and contributor count;
- surprise relative to the exact pre-event vintage;
- guidance-versus-consensus gap;
- revision breadth across a sector/theme;
- macro initial-release versus revised-value delta;
- correction sensitivity: how much a signal changes across vintages;
- staleness/coverage/entitlement flags;
- entity/membership continuity;
- first-seen versus later-confirmed event state;
- source disagreement across independent evidence families.

Do **not** collapse these into one opaque score when the dimensions answer different questions. A consumer may derive a decision score later, but the underlying evidence remains inspectable.

LLM use should be downstream and bounded:
- summarize dated evidence;
- reconcile conflicting source narratives;
- propose causal mechanisms and falsifiers;
- map a new event to existing evidence families;
- explain why a record is excluded.

LLMs should not invent timestamps, infer missing rights, decide PIT eligibility from prose, silently repair entity history, or synthesize missing historical estimates.

---

# G. Integration map

| Producer | Canonical artifact / owner | Evidence family | Consumer |
|---|---|---|---|
| SEC EDGAR | Macro data/edgar owner; source receipt references accession/filing clocks | fundamentals / filings / insider / institutional | loop/fundamentals.py, portfolio held-risk, research desk |
| FRED / ALFRED | Macro fred_vintage + engine/pit | macro initial-release/revision evidence | Macro regime/transmission -> Mastermind market view / portfolio context |
| Macro expectation collector | Macro expectation_market_dynamics owner | earnings expectations / revisions / dispersion | portfolio/held_risk.py earnings_expectation, research desk |
| S&P membership builders / future licensed source | Macro breadth membership owner | universe identity / survivorship | loop/single_name_panel.py and research validation |
| Mastermind brain/signal_history.py | Mastermind signal-history JSONL owner | first-seen engine evidence | brain/research desk / audit |
| Portfolio V3 source receipts | Portfolio owner | provenance / freshness / coverage / corrections | Decision Snapshot and portfolio consumers |
| Portfolio V3 Decision Snapshot | Portfolio owner | actual served decision evidence | UI, audit, later learning/replay |
| Terminal | presentation/consumer surface | display only unless it owns an explicit served receipt | human review |

No new warehouse is required by this map. Producers remain authoritative for their data; receipts make cross-owner consumption auditable.

---

# H. Empirical validation

## H1. Temporal correctness tests

Before predictive testing, prove the data is admissible.

Required adversarial fixtures:
- a revision published after the decision cutoff;
- a late-arriving record whose event date is old but system-known time is new;
- a vendor backfill with no historical availability timestamp;
- an amended SEC filing;
- a ticker rename/merger/share-class change;
- a membership change effective after announcement;
- a duplicate record with a later correction;
- a timezone/DST boundary;
- an after-hours filing whose legal filing date and acceptance timestamp differ;
- a missing/rights-blocked record that must remain missing rather than become zero.

The test must fail if any future or unknown-clock record enters a research-tier PIT read.

## H2. Historical replay

For every scored historical experiment, persist:
- decision cutoff;
- replay mode: market simulation versus actual-system replay;
- source receipt IDs;
- code version;
- entity/universe version;
- feature definitions;
- label interval;
- transaction-cost/slippage assumptions where the result is intended to inform trading.

Use revision-aware source vintages. For actual-system replay, use served/Decision Snapshot evidence rather than current-rule recomputation.

## H3. Predictive validation

Predeclare:
- hypothesis and mechanism;
- universe;
- feature definitions;
- horizons;
- primary metric;
- economic use;
- missingness policy;
- number of variants/trials;
- acceptance and kill criteria.

Use walk-forward or rolling-origin evaluation. When feature/label intervals overlap across train/test boundaries, purge overlapping observations and apply an embargo sized to the leakage mechanism. Do not use random IID folds for serially dependent financial labels.

Control data snooping/multiple testing with a method appropriate to the experiment family, such as false-discovery control, White-style reality-check logic, probability-of-backtest-overfitting analysis, or a deflated performance statistic. No single method is mandatory for every study.

Required ablations:
- new evidence family alone;
- existing evidence baseline alone;
- baseline + new evidence;
- same test with revisions/latest data substituted to quantify leakage tax;
- same test with current survivors only versus survivorship-safe universe where available;
- same test excluding low-coverage/rights-ambiguous rows;
- negative controls with deliberately shifted or irrelevant features.

The promotion question is not "is the signal significant?" It is "does it add stable, economically relevant, temporally admissible information beyond evidence Mastermind already consumes?"

Useful references:
- Bailey et al., Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Bailey & López de Prado, Deflated Sharpe Ratio: https://doi.org/10.2139/ssrn.2460551
- Harvey, Liu & Zhu, ...and the Cross-Section of Expected Returns: https://doi.org/10.1093/rfs/hhv059
- White, A Reality Check for Data Snooping: https://doi.org/10.1111/1468-0262.00152
- López de Prado, Advances in Financial Machine Learning, ch. 7 for purged financial cross-validation: https://www.oreilly.com/library/view/advances-in-financial/9781119482086/c07.xhtml

---

# I. Risks and failure modes

1. **Clock collapse.** as_of, event date, filing date, provider availability, ingestion, and decision cutoff become interchangeable labels.
2. **Proxy masquerade.** A conservative lag such as +120 days is later described as an actual filing/publication timestamp.
3. **Backfill look-ahead.** Today's corrected vendor database is projected backward without a historical availability field.
4. **Restatement overwrite.** Latest-filed-wins normalization destroys prior vintages.
5. **Survivorship.** Current ticker/universe membership is applied backward.
6. **Entity drift.** Ticker reuse, mergers, ADRs, share classes, fiscal-year changes, and corporate actions are mapped incorrectly.
7. **Adjustment-vintage drift.** Adjusted price history changes after later splits/dividends without recording adjustment vintage.
8. **Partial PIT.** Some legs are vintage-correct while other inputs silently remain latest-revised.
9. **Missingness laundering.** unavailable, rights-blocked, stale, and legitimate zero are collapsed.
10. **Rights leakage.** Raw vendor records, derived features, display, redistribution, or model-training rights are assumed from product marketing.
11. **Duplicate control plane.** A new temporal warehouse/correction ledger competes with Macro temporal primitives, Portfolio V3 receipts, or existing forward logs.
12. **Stale census.** A generated inventory is treated as live truth months later.
13. **LLM authority leakage.** A model invents publication times, corrections, or entity mappings.
14. **Evidence double-counting.** Analyst revisions, earnings surprise, price momentum, and news all encode the same underlying event but are counted as independent confirmation.
15. **Research/production conflation.** A statistically interesting result is wired into sizing/trading before rights, replay, independence, and production-path proof.

---

# J. Build priority

## P0

1. **Current temporal census + semantic map.** Reconcile Mastermind, Macro, Terminal, and Portfolio V3 at pinned revisions. Explicitly map existing fields rather than renaming them globally.
2. **Producer truth repair.** Where true filing/publication clocks exist, prefer them over synthetic lags; where only a proxy exists, type it as a proxy and preserve the limitation.
3. **Minimal receipt adapter.** Extend Portfolio V3's existing receipt direction so cross-owner artifacts carry digest, source, clocks/bases, coverage, rights, and correction generation without creating a new warehouse.
4. **Fail-closed research reads.** Historical scoring/calibration must refuse a source whose required availability clock is absent or unknown. Display-tier degradation may remain visible but must be machine-labeled.
5. **Decision Snapshot S0.** Implement the already-designed immutable Portfolio V3 snapshot/receipt path as the actual replay owner; do not create a separate served-history plane.
6. **Expectation-lane proof.** Verify the current Macro expectation collector's prospective accrual, correction lineage, and held-risk consumption end-to-end before seeking deeper vendor history.

## P1

- Evaluate licensed institutional analyst-estimate samples under the existing VEND-0 frozen design; no procurement winner without record-level replay and rights proof.
- Replace/reconcile reconstructed index membership with an official historical source if the research value justifies rights/cost.
- Add explicit adjustment-vintage/corporate-action treatment where adjusted price history is used for historical inference.
- Expand options history only with the quote/trade context needed for the intended claim.
- Repair annual/quarterly fundamentals lineage so genuine SEC filing/acceptance clocks are preserved where available.

## P2

- Political transaction, government-contract, ETF-flow, and richer news/event temporal enrichment after P0 consumers can ingest them without clock collapse.
- Fine-grained effective-dated dynamic subtheme identity after the existing theme/version owner is identified and extended.
- Cross-source source-disagreement and correction-sensitivity analytics.

## Defer

- A wholesale physical rewrite of every dataset into one bitemporal database.
- Expensive low-latency exchange feeds unless a named consumer capability and measured latency need justify them.
- Commercial vendor procurement before frozen-sample semantics and rights review.

## Reject

- A second correction ledger, temporal warehouse, queue, lifecycle, publication plane, or feature store.
- Filesystem mtime as market knowledge time.
- Historical backtests on current snapshots with arbitrary lags presented as actual availability.
- LLM-generated timestamps or inferred rights.
- Opaque aggregate "data quality" or "truth" scores that hide the underlying dimensions.

---

# K. Proposed implementation phases

These are recommendations only. This report does not execute them.

### Phase 0 — Reconcile and freeze semantics
Deliver a current cross-repo temporal census, field dictionary, owner map, and explicit mapping between Macro temporal profiles and Portfolio V3 receipt fields. Acceptance: no duplicate owner or clock meaning.

### Phase 1 — Repair source clocks
Prioritize SEC fundamentals, ALFRED coverage, membership identity, expectation accrual, and adjustment-vintage gaps. Acceptance: every historical research source either proves its admissible clock or fails closed with a typed reason.

### Phase 2 — Receipts and Decision Snapshot
Implement the existing Portfolio V3 source-receipt/immutable snapshot plan using owner-provided digests and clocks. Acceptance: a decision can be reconstructed from immutable receipts without reading mutable latest files.

### Phase 3 — Expectation history
Run the existing VEND-0 frozen sample against authorized vendor data if and only if access/rights are separately approved. Acceptance: record-level as-known replay, correction lineage, entity/fiscal mapping, null semantics, and written rights all pass.

### Phase 4 — Empirical validation
Pre-register incremental hypotheses, run revision-aware walk-forward tests, leakage falsification, multiple-testing controls, ablations, and economic-cost checks. Acceptance: incremental information survives out-of-sample and does not disappear when PIT discipline is tightened.

### Phase 5 — Consumer promotion
Only after production-path proof, wire the evidence into existing consumers. Keep deterministic eligibility/clock checks outside the LLM. Promotion requires explicit evidence that the consumer reads the same canonical artifact validated in research.

---

# L. Exact bounded follow-on implementation commission — DO NOT EXECUTE HERE

> **Mission:** Implement P0 temporal interoperability and Portfolio V3 Decision Snapshot S0 without creating a new warehouse, correction ledger, lifecycle, queue, feature store, or publication plane.
>
> **Protected source:** Re-pin Mastermind protected master and Macro main at commission start. Load current protected procedures from the same Mastermind commit.
>
> **Allowed scope:** Mastermind + Macro code/tests/docs required for (1) a semantic adapter between existing Macro temporal fields and Portfolio V3 source receipts; (2) explicit typed clock-basis metadata; (3) fail-closed research-tier PIT eligibility; (4) immutable Decision Snapshot/source receipts using the existing Portfolio V3 design; and (5) bounded tests/fixtures proving corrections, late arrivals, missing clocks, proxy clocks, and decision cutoffs.
>
> **Must reuse:** Macro lib/dataos/temporal.py and existing owner-specific append-only histories; Mastermind Portfolio V3 source-receipt/Decision Snapshot design; existing forward logs/receipts where they already own replay.
>
> **Must not do:** no new temporal warehouse; no duplicate correction ledger; no vendor purchase/contact; no live trading/sizing change; no LLM timestamp inference; no backfill that fabricates historical known-at; no silent default flip of production macro PIT basis.
>
> **DONE_WHEN:** one end-to-end fixture demonstrates that a decision at cutoff T includes only admissible records, excludes a correction first available after T, preserves the later correction as a new generation, distinguishes proxy versus actual clocks, reconstructs the immutable Decision Snapshot from receipts, and passes targeted tests plus repository review. Production/live promotion remains a separate approval.
>
> **Evidence required:** pinned SHAs, changed-file list, tests and exact commands/results, sample receipts/snapshot digests, negative leakage test, no-duplicate-owner review, and explicit remaining UNKNOWN/RIGHTS_BLOCKED states.
>
> **Stop condition:** stop before vendor procurement, production deployment, live trading effects, or any new source authority.

---

# Source-quality / confidence notes

### High confidence — repository evidence
Claims about Mastermind code/spec state are pinned to 84df29801d4078724c2b603a136de5aa1532cdfe. Claims about Macro temporal primitives and vendor bake-off are pinned to f9ed175800257b228166dabe8b3ac9a55e74e237. Code/spec presence is not the same as production proof; this report therefore uses BUILT_NOT_PROVEN/PARTIAL where runtime evidence was not obtained.

Key Mastermind references:
- [docs/sol_skills/INDEX.md](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/docs/sol_skills/INDEX.md)
- [loop/fundamentals.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/loop/fundamentals.py)
- [loop/single_name_panel.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/loop/single_name_panel.py)
- [brain/signal_history.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/brain/signal_history.py)
- [brain/research_desk.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/brain/research_desk.py)
- [portfolio/held_risk.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/portfolio/held_risk.py)
- [research/TREND_PERSISTENCE_PROTOCOL.md](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/research/TREND_PERSISTENCE_PROTOCOL.md)
- [data/census/CENSUS.md](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/data/census/CENSUS.md)
- [Portfolio V3 design](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md)
- [Portfolio V3 S0 plan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/84df29801d4078724c2b603a136de5aa1532cdfe/docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md)

Key Macro references:
- [Mastermind Temporal Data Standard](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/research/MASTERMIND_TEMPORAL_DATA_STANDARD.md)
- [lib/dataos/temporal.py](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/lib/dataos/temporal.py)
- [collectors/equity_revisions.py](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/collectors/equity_revisions.py)
- [VEND-0 Institutional Estimates Bake-Off](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/research/alpha_intelligence/expectation_market_dynamics/VEND_0_INSTITUTIONAL_ESTIMATES_BAKEOFF_2026-08-23.md)
- [S&P 400/600 PIT reconstruction](https://github.com/mastermindx-market-intelligence/macro/blob/f9ed175800257b228166dabe8b3ac9a55e74e237/scripts/midsmall_pit.py)

### High confidence — primary public sources
SEC, Federal Reserve Bank of St. Louis, CFTC, USAspending, House/Senate ethics pages, NYSE/Nasdaq, and official vendor product documentation are used for narrow claims about published interfaces, deadlines, product coverage, or advertised PIT behavior.

### Medium confidence — vendor capability before sampling
LSEG, FactSet, S&P Capital IQ, Compustat, and Visible Alpha claims are **vendor-origin product claims** until an authorized record-level sample is tested. They do not establish Mastermind entitlements, exact delivered schema, correction behavior, latency under contract, or legal rights.

### Explicit UNKNOWNs
- Exact organization-wide vendor entitlements and rights schedules.
- Exact authoritative commercial prices for comparable institutional entitlements.
- A separate repository identity for the originally named "Research Vault."
- Production proof that every built temporal path is currently exercised by the live consumer path.
- Official historical S&P 1500 constituent entitlement/coverage available to this project.
- Historical vendor availability clocks for sources that expose only current snapshots.
- Whether all later Macro changes after the pinned commit preserve the same temporal semantics.

These UNKNOWNs are not blockers to the research conclusion. They are gates for any later implementation, procurement, or production promotion.
