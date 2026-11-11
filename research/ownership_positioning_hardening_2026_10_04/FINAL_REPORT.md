# Commission 10 — Institutional Ownership & Positioning Graph
## Hardened research, architecture and implementation-admission report

**Research cut:** 4 October 2026. **Disposition:** completed research recommendation; implementation, procurement, deployment and predictive promotion remain uncommissioned. **Scope:** U.S. regulatory ownership and fund positioning, with explicit boundaries for foreign issuers and global extensions.

This report hardens the supplied 708-line Commission 10 report rather than treating its conclusions as current source truth. It preserves the useful snapshot-versus-flow distinction and rejects several unsafe details of the original design. The [audit register](AUDIT_LEDGER.md) records the changes. [Sources](SOURCES.md) distinguish current repository evidence, primary regulatory material, vendor documentation, historical literature and unverified inherited assertions. [Verification](VERIFICATION.md) separates executed research checks from tests a later implementation must perform.

## A. Executive conclusion

### Decision

**Build a logical, effective-dated ownership evidence graph over existing owners—not a second ownership warehouse, identity service, evidence store, universal collector, or investment score.** Start by recovering and qualifying the existing Macro K2-C institutional adapter and composing it with K1 EvidenceRef/Block/Recipe and K2-B manager-intent contracts. The first accepted result should be one honest, replayable ownership comparison for one existing consumer, including a useful typed refusal when identity or history is unavailable. Expansion to additional source families is a sequence of separately gated adaptations.

The original report correctly identifies the strategic need, but substantially understates the existing integration architecture. Macro already has a merged owner-read 13F adapter; its K1 contracts explicitly prohibit the new universal identity and physical evidence-store shortcuts that the original minimum schemas could invite. Terminal has a merged Institutional ownership workspace, not merely unrelated prototypes. Research Vault is a subsystem of Macro; the similarly named disaster-recovery repository is not the research estate. These are design-changing corrections, not documentation polish. [I02](SOURCES.md#i02) [I03](SOURCES.md#i03) [I04](SOURCES.md#i04) [I05](SOURCES.md#i05)

### What the user should ultimately receive

For a security and decision cutoff, the existing company/research surface should answer: **Who disclosed which kind of interest, for what economic date, when did that disclosure become public and actually available to this system, what changed on a comparable basis, what overlaps with other reports, and what remains unknowable?** It should offer the underlying receipt and correction lineage, not replace them with a confidence adjective.

A useful output might say: “Among the same 32 reporting entities whose two eligible filings were available at this cutoff, 11 increased reported common-share holdings and 8 decreased them. Four additional incoming reports remain unavailable. These are quarter-end disclosed-position changes, not current buying. Seven reports share a manager complex; that grouping does not establish statistical independence.” Those numbers are illustrative, not an observed production result.

The dimensions remain separate: institutional investment-discretion snapshots; beneficial-ownership and disclosed-purpose events; insider transactions; fund-vehicle portfolios; fund net issuance; non-proportional ETF holdings changes; and ownership structure/crowding. Different source families may still share information, entities, economic mechanisms and transaction origins.

### Priority and economic rationale

P0 is **trust and reuse**, not broad acquisition: native clocks, lawful identity resolution, correction replay, precise missingness, and one owner-bound consumer. P1 is source-specific coverage and empirical research. A risk/context feature can justify itself through fewer false claims and better coverage without earning return-prediction authority. No observed evidence in this commission establishes a new ownership alpha or authorizes a portfolio action.

The revised recommendation makes four distinctions that must survive every implementation:

1. **Observed position change is not identified trading intent.** ETF custom baskets can produce a nonzero holdings residual without an active market trade. A 13F disappearance is not necessarily a liquidation.
2. **Public-information reconstruction is not actual system replay.** Historical publication evidence can support a clearly labeled simulation; it cannot manufacture a historical observation, ingestion, parser or feature-emission receipt.
3. **Owner reuse is not readiness.** Merged code, successful CI and historical proof runs are separate from a current, complete, consumer-visible runtime proof.
4. **Regulatory regimes are effective-dated data.** The February 2026 N-PORT proposal is not the currently operative regime; March 2026 foreign-insider requirements and conditional exemptions change the Form 4 coverage universe. [R03](SOURCES.md#r03) [R04](SOURCES.md#r04) [R07](SOURCES.md#r07) [R08](SOURCES.md#r08)

## B. Current-state census and collision audit

### B1. Source-law and repository identities

The current protected Mastermind source was pinned before research publication. Same-revision Skillpack files were acquired for cold start, active execution, session reliability, delegation, review and closeout. The report uses the following immutable census cut; these SHAs are evidence, never permission for a future implementation to ignore a newer protected procedure.

| Estate | Resolved repository and branch | Census SHA | Protection observed |
|---|---|---|---|
| Mastermind | `mastermindx-market-intelligence/Mastermind`, `master` | `521720b09be2921e996d9396b522b1c4ca62041c` | true |
| Macro / institutional data / organizational records | `mastermindx-market-intelligence/macro`, `main` | `79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f` | false in branch response; not described here as protected |
| Charting / Terminal | `mastermindx-market-intelligence/mastermind-terminal`, `master` | `1c708450187755160e1a5889b69598a2fcb1f0d1` | true |
| Research Vault | Macro subsystem, not a separately inferred repository | same Macro SHA | owner-specific private storage rules still apply |

The original report's Mastermind `a2646f4…` and Macro `d2904d4…` pins are superseded as current-state evidence. The user prompt's earlier `d1594f3…` is also historical. Complete Mastermind and Terminal trees were obtained. **Macro's root recursive tree was truncated**; complete `engine`, `docs`, `research`, `contracts` and `agentos` subtrees were therefore obtained separately. An absence inferred from the truncated tree is not accepted. Exact native files were also fetched by pinned path. [I01](SOURCES.md#i01)

**Closing movement check, 2026-10-04T08:04:39Z:** Mastermind and Terminal remained at the pinned heads above. Macro advanced two commits to `617c5818b0493e1843c652be881f72cbebfac123`. The compare response listed only `agentos/handoffs/TREND-PERSISTENCE-2026-10-04.md`, `agentos/workstreams/WS-TREND-PERSISTENCE.md` and `agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md`; it showed no change to the ownership/K1/K2 native files used by this report. The immutable acquisition cut remains `79251a2…`; the organizational movement is recorded rather than silently replacing the evidence pin. [I10](SOURCES.md#i10)

### B2. Evidence strength and audit limits

The census acquired 66 exact-revision files, with byte counts, SHA-256 and Git-blob hashes. **Acquisition is not semantic inspection.** The accompanying source inventory does not certify that every line of every downloaded file was reviewed. This pass directly inspected the K1 evidence-contract README, the relevant organizational workstream record, source-law procedures, current PR records and workflow-run metadata. Two bounded source-extraction calls were refused before execution; they were not retried or routed around. Consequently, detailed current behavior of several downloaded engines and freshness payloads remains unverified in this pass.

This limitation changes the claims, not the architecture into guesswork: current file existence, merged adapter identity, native contract restrictions, product integration and active collisions are independently evidenced. Runtime freshness, exact current Quiver behavior, the static census's current content and the complete Portfolio V3 implementation state are **not recertified** merely because the original report asserted them. The implementation handoff makes these explicit preconditions, not hidden assumptions.

Use these capability distinctions: `BUILT_NOT_PROVEN` for verified source/merged capability without current end-to-end proof; `PARTIAL` for bounded supported capability; `SPEC_ONLY` only when supported by an inspected specification; and `UNKNOWN` for an audit fact not established. `UNKNOWN` is an evidence disposition, not a new organizational runtime state.

### B3. Capability map

| Capability / exact seam | What this pass establishes | Current disposition and remaining proof |
|---|---|---|
| Macro `contracts/evidence_foundation/` and `lib/evidence_foundation.py` | K1 owner-pointer, block and recipe contracts exist; README inspected; workstream records accepted K1 merge | Contracts accepted/on main. Not a live universal evidence mesh. Automatic relation effects remain unavailable in v1. |
| Macro `contracts/institutional_intelligence/`, `lib/institutional_intelligence.py` | K2-B contract owner exists; accepted contract-only release recorded | Reuse owner. Do not infer live manager ontology, history or investment authority from schema existence. |
| Macro `lib/institutional_13f_adapter.py` | Merged PR #6533 defines owner-row → receipt → native CUSIP → K1 → K2-B composition | `BUILT_NOT_PROVEN` for current consumer outcome in this audit; historical successful proof jobs are not a newly examined production receipt. |
| Macro `engine/institutional_census/` plus catalog/raw-receipt contracts | Exact source files and immutable schema seams acquired; existing SEC census is the incumbent 13F owner | Reuse. Recent successful census jobs establish execution metadata, not complete data health or PIT replay quality. |
| Macro curated `collectors/edgar_13f.py` and Smart Money desk | Current files exist; original describes a curated featured cohort | Do not expand featured roster into the universal census or treat today's roster as historical selection. Current roster count not recertified. |
| Macro `engine/company_institutional_context/` | Source present; Terminal's merged institutional page explicitly consumes this incumbent owner | Existing integration, current runtime and generation health unverified. |
| Terminal `OwnershipPage.tsx`, `CompanyInstitutionalContextCard.tsx`, same-origin route and library | PR #734 merged; creates Institutional page within Ownership and preserves Insider sibling | Source-built product, not a greenfield UI task. No browser/runtime proof performed by this commission. |
| Macro `collectors/beneficial_ownership.py`, `engine/beneficial_ownership.py` | Exact source present | Existing producer to qualify, not authority to assert amendment/clock correctness. |
| Macro ETF/ARK collectors and `engine/holdings_signals.py` | Exact source present | Prior report's proxy-quality findings remain hypotheses pending direct current code and source-state proof. |
| Macro `ownership_flow.py`, `ownership_crowding.py`, `ownership_ledger.py`, `ownership_event_wire.py` | Additional existing modules acquired; original plan understated overlap | Collision surface. Do not rebuild calculators/ledgers without proving a specific deficiency and assigning repair to their owner. |
| Form 4 / N-PORT end-to-end plane | Original describes partial integrations; current named N-PORT PR search returned no match | Absence of a title match is not proof of `NOT_BUILT`. Freeze additions behind owner and data-history qualification. |
| Mastermind `portfolio/lenses.py`, `held_risk.py`, `brain/research_desk.py` | Current files acquired; original describes actual 13F consumers | Treat functions as candidate existing consumers; detailed current behavior not freshly certified. No consumer authority change. |
| Mastermind `loop/fundamentals.py`, `loop/single_name_panel.py`, `research/TREND_PERSISTENCE_PROTOCOL.md`, `brain/experiment_registry.py` | Current methodological seams acquired | Reuse existing PIT/universe/experiment owners after owner-specific qualification; no new grader or experiment registry. |
| Portfolio V3 specification and S0 plan | Current specification/plan files located; original says Decision Snapshot/claim ledger are SPEC_ONLY | Preserve as future seam until current implementation evidence proves otherwise. This audit does not convert inherited SPEC_ONLY into a fresh universal absence claim. |
| Macro Research Vault / research-intelligence adapter | Actual subsystem and active development carriers resolved | Existing research-document owner, separate from position/transaction truth. Private text never becomes a public ownership corpus. |
| Static `data/census/CENSUS.md` | File acquired; original claimed July 16 generation | That timestamp is inherited, not independently reread here. Operational observability remains a necessary gate regardless. |

Key receipts: K1/K2 organizational record [I02](SOURCES.md#i02), inspected K1 contract [I03](SOURCES.md#i03), merged K2-C [I04](SOURCES.md#i04), Terminal [I05](SOURCES.md#i05), acquired-file manifest [I06](SOURCES.md#i06).

### B4. Execution metadata is useful but not an end-to-end proof

The last five census workflow runs returned by the API were successful, the most recent `37120635828` created `2026-10-03T11:44:44Z` at `d3c77b6621372b2252c007ce88885e28049e6b42`. The K2-C proof workflow returned four successful August 27 runs; most recent `33058222640` at `f244f0b34330cac9c98a815a3c0e97d0ba5b1d7f`. No matching raw proof artifact was opened and adjudicated in this pass. Thus “nothing exists” is false, and “currently production-proven” would also be unsupported. [I07](SOURCES.md#i07)

There is organizational drift: the inspected workstream's K2 next-action prose still calls for commissioning K2-C, while PR #6533 is already merged. Preserve the discrepancy, use the exact adapter and its proof lineage, and reconcile the current owner before a new commission. A historic author or workstream owner label is not a current writer lease.

### B5. Duplicate and adjacent programs

| Carrier at audit cut | Exact head / state | Relationship and no-rebuild instruction |
|---|---|---|
| Macro #6533 | merged `0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e` | K2-C 13F adapter. Recover current descendant and prior semantic repair, do not issue a replacement adapter project. |
| Terminal #734 | merged `94403c1dd6693c41ae2100a9deafa2ce968ffa1b` | Existing Ownership → Institutional page. Extend through its current context owner only. |
| Macro #7354 | `b8833c40cb4c9541cc4449e72f5c5f8be8308d1a`, open draft | Research Vault top-N institutional-document deep read; not institutional positions. Potential narrative consumer, no parallel PDF store. |
| Macro #7387 | `7931b0f5360d526b18191f987f5ec11d432a66eb`, open draft | Institutional RIO surface deltas, explicitly not semantic belief authority. Do not confuse prose changes with ownership changes. |
| Macro #8338 | `90336ccdd7173dd856e9c00b81e267ab3cc7abb3`, open draft | Intelligence Workspace 2.0 architecture; Investigation over existing research/layout owners. |
| Terminal #777 | `525ccabb9fed1ba4cc862ed4b40a6e3915465c6c`, open, not draft | Private retained Investigation/layout/Earnings context. Candidate future reader, not accepted ownership storage authority. |
| Macro #8398 | `50cdddbeab9130fd4206db7cf8a39e3df17ba525`, open draft | China public-fund accrual through existing Tushare plane. Defer global expansion; do not duplicate this source. |
| Mastermind #1203 | `b41bba31d5dc4a15a8ec8b2eaa8babf411b7d0a6`, open draft | Event → thesis → signal architecture candidate, not a new accepted control plane. |
| Mastermind #1232 | `5dcd57fb22f0be6c4a5cfe750c4c3829f762f235`, open draft | Commission 7 lineage/independence hardening. Align terminology but retain accepted K1 restrictions over candidate prose. |

These are a bounded relevant collision census, not a claim that all organizational work was enumerated. Direct PR links and captured state are in [Sources](SOURCES.md#i08). No incumbent branch was modified by this research.

## C. State-of-the-art research and implications

### C1. Institutional practice is semantic normalization plus provenance

The useful commercial pattern is normalized holder/fund/issuer identity, source coverage and date semantics, not a generic “smart money” label. FactSet documents report, filing and processing/transfer dates; LSEG offers broad ownership and entity coverage; S&P explicitly markets holding and filing dates as PIT; Morningstar exposes fund-portfolio endpoints; DTCC sells composition-file history. These are different services with different evidence guarantees. A vendor's “PIT” label does not prove preservation of every historical revision or actual delivery vintage. [V01](SOURCES.md#v01) [V02](SOURCES.md#v02) [V03](SOURCES.md#v03) [V04](SOURCES.md#v04) [V06](SOURCES.md#v06)

Institutional normalization must separate the legal holder, reporting filer, investment discretion, fund vehicle, share class, group membership, issuer and security. A manager can report multiple mandates; a fund can share advisers; a beneficial-ownership group can overlap persons and vehicles; a security can have multiple listings. A tree-shaped manager→filer→fund assumption is useful for display but unsafe as the canonical ontology.

### C2. Literature supports competing mechanisms, not automatic alpha

| Primary research | What it contributes | Design implication / competing explanation |
|---|---|---|
| Wermers, mutual-fund herding; Nofsinger and Sias, institutional herding and feedback trading | Historical association between holdings changes, herding and returns | Separate contemporaneous price effects, momentum-following and post-disclosure predictability. Older samples do not validate the current source pipeline. |
| Coval and Stafford, asset fire sales | Flow-induced trades can generate price pressure and reversals | Selling need not reveal bad private information. Flow distress can be a different feature from manager conviction. |
| Cohen, Malloy and Pomorski, routine versus opportunistic insider trades | Transaction behavior and prior patterns can distinguish informative subsets | Classifications must be constructed using prior history only; no full-sample “skill” or routine label. |
| Brav, Jiang and Kim; Bebchuk, Brav and Jiang on activism | Operational and longer-horizon outcomes offer mechanisms beyond the filing-day price jump | Control for selection; separate governance changes from returns available after the public disclosure. |
| Edmans on blockholders | Voice and exit are distinct governance channels with costs and benefits | Ownership concentration is not unconditionally bullish; mandate and incentives matter. |
| Ben-David, Franzoni and Moussawi on ETF ownership | ETF activity can connect ownership with volatility/arbitrage | Evaluate crowding and liquidity risk separately from directional return prediction. |

Sources [P01–P08](SOURCES.md#p01). These studies justify hypotheses and controls, not assumed effect sizes, a present-day trading recommendation or a guarantee of causal identification.

### C3. The frontier relevant to Mastermind

The priority is a reproducible information set with legally different assertions preserved, not a graph database or an LLM that guesses the hidden portfolio. Cross-source corroboration can improve verification while adding zero predictive novelty. Conversely, a pre-specified interaction may matter even when a univariate signal does not. The empirical program must distinguish source novelty, statistical conditional information, and the economic mechanism.

## D. Source landscape and regulatory regimes

### D1. Regulatory and first-party source comparison

“Free” below means no source subscription price established here, not zero engineering/legal cost or unrestricted redistribution. Bulk-release dates and individual-filing publication dates are different clocks.

| Source | Coverage | History | Latency / deadline | PIT quality | Corrections | Rights / cost | Best use |
|---|---|---|---|---|---|---|---|
| SEC 13F-HR/HR-A/NT | Reportable investment-discretion positions, not full economic portfolio | Structured SEC bulk from 2013; older EDGAR formats require separate qualification | Quarter-end state, ordinarily filed within 45 days | Strong only with actual public availability and original vintage | Restatement vs added-holdings amendment, confidential releases, bulk revisions | Public access subject to access rules; identifier rights remain separate; free acquisition | Broad ownership context and paired disclosed-position changes |
| SEC N-PORT | Registered-fund portfolio records within form scope, not every pooled vehicle | Public bulk from 2019 | Operative regime: quarterly public third-month observation, delayed; details below | Public subset and public-release time required | Filing amendments, bulk republishing, fiscal-period alignment | Public SEC, free acquisition | Vehicle-level structural ownership; mutual-fund/ETF reconciliation |
| Schedule 13D/G | Beneficial ownership and relevant purpose/control disclosures | Long EDGAR history; uniform structured regime only from Dec 18, 2024 | Category-specific legal clocks below | High event utility with release time; event date is not knowability | Amendments change fields/items, retain prior unamended assertions | Public SEC; free acquisition | Major holders, purpose changes, qualifying activism |
| Forms 3/4/5 and amendments | Section 16 ownership and transaction disclosures, subject to eligibility/exemptions | SEC insider bulk from Jan 2006; coverage/regime changes must be modeled | Form 4 ordinarily two business days, exceptions exist | High for reported transaction, not necessarily exact execution time or open-market status | Line/item corrections; unamended Form 4 rows need not repeat | Public SEC; free acquisition | Separate transaction intelligence, grants/exercises/withholding distinguished |
| ETF sponsor holdings | Fund-specific disclosed portfolio, with transparency regime identified | Website-dependent; current snapshots do not imply archive | For ETFs relying on Rule 6c-11: prior-close holdings before next regular open | Capture publication bounds, source timezone and bytes | Silent replacements/format changes possible | Sponsor terms, archival/display/derived rights unresolved per source | Daily state changes, not identified AP trades |
| Sponsor fund shares/NAV/assets | Vehicle or share-class units and financial state | Sponsor-dependent | Typically dated daily on useful product pages; not uniformly verified | Pair same cut, class, currency and unit basis | Restatements, distributions, share splits | Source-specific; no permission inferred from a visible website | Net issuance and residual normalization |
| Mutual-fund sponsor portfolios / N-CSR statements | Full or partial portfolios, varying instruments and reporting periods | Fund-dependent; historical N-Q/N-CSR archives may supplement pre-N-PORT periods | Monthly/quarterly/semiannual or source-specific | Public timestamp and completeness essential | Restatements and partial/top-holdings disclosures | Source-specific; free acquisition not unrestricted rights | Coverage supplement, not live flow |
| Issuer capital structure / corporate actions | Share-class denominators, splits, mergers, conversion/ADR ratios | Filing/reference-source dependent | Public filing/event time | Requires matching economic date plus known-at date | Later denominator or identifier revisions | SEC plus licensed reference services as applicable | Prevent false trades and invalid ownership percentages |
| DTCC ETF composition service | Creation/redemption composition files and supplements, not a universal executed-trade tape | Provider documents history from Nov 1, 2007 | Batch and near-real-time supplemental products | Delivery vintage and portfolio type must be proved | File revisions/substitutions; licensed documentation | Commercial, quote required | Basket qualification after the public baseline proves a need |

References: [R01](SOURCES.md#r01) [R02](SOURCES.md#r02) [R05](SOURCES.md#r05) [R06](SOURCES.md#r06) [R09](SOURCES.md#r09) [R10](SOURCES.md#r10) [V06](SOURCES.md#v06).

### D2. Deadline and schema facts that change the design

**13F.** Keep CIK, accession, report period, report type, other included managers, CUSIP, optional FIGI, class, discretion, voting authority, put/call and quantity type. SH and PRN are not interchangeable. The January 2023 form change from thousands of dollars to dollars makes unit/version provenance mandatory. A position can be omitted under the de-minimis exception only when both the share and value tests are met: fewer than 10,000 shares and less than $200,000. Therefore even an incoming filed report does not, by itself, prove economic liquidation. The Official 13(f) List changed to TXT for Q4 2025 onward; parsers must not assume a permanent PDF-only source. [R01](SOURCES.md#r01)

**13D/G.** The following summarizes the operative post-2024 regime; legal eligibility and transition conditions remain part of the full rule, not a scalar “lag” column.

| Filing category | Initial deadline | Amendment timing |
|---|---|---|
| 13D | Generally five business days after crossing the applicable >5% threshold or relevant loss of 13G eligibility | Two business days after material change; a one-percentage-point ownership change is presumptively material |
| 13G qualified institutional investor | Generally 45 days after calendar quarter-end with the relevant >5% position; accelerated five-business-day month-end rule above 10% | Material-change quarter-end +45 days; accelerated month-end +five business days for applicable >10% / >5-percentage-point changes |
| 13G exempt investor | Generally quarter-end +45 days after the applicable >5% condition | Material-change quarter-end +45 days |
| 13G passive investor | Five business days after applicable >5% acquisition | Material-change quarter-end +45 days; two business days for applicable >10% / >5-percentage-point changes |

The SEC final rule's tables and operative text were inspected, including the month-end measurement rules. Preserve exact trigger rules instead of interpreting every 13G change as equally recent. 13D deadlines changed effective February 5, 2024; revised 13G deadlines required compliance September 30, 2024; structured filing became mandatory December 18, 2024. Never impose the modern lag/schema on the older sample. [R06](SOURCES.md#r06)

A 13G non-control certification is not an index-fund label. A 13D is not proof of an activist campaign; Item 4 and related arrangements matter. Joint filing parties and shared dispositive/voting power are overlapping legal assertions, not additive holdings. The adopted rule did not enact a blanket equation between every cash-settled derivative and beneficial ownership. [R06](SOURCES.md#r06)

**Form 4.** The current form codes P/S include open-market **or private** purchases/sales, and may describe derivative securities. Table I/Table II, direct/indirect ownership, footnotes, weighted-average prices, transaction dates, deemed execution exceptions and Rule 10b5-1 indication require distinct fields. A checked plan box is reported plan-related metadata, not an independent finding that a trade is lawful, discretionary or uninformed. Form 4/A need not repeat unchanged rows; wholesale replacement can erase valid transactions. [R09](SOURCES.md#r09)

**2026 foreign-insider coverage.** The HFIA Act changed reporting for directors/officers of relevant foreign private issuers effective March 18, 2026. Initial Form 3 coverage is not a new acquisition. The SEC's March 5 conditional exemption covers qualifying issuer jurisdictions/regulations, including Canada, Chile, the EEA, Korea, Switzerland and the UK; actual reporting and timely public English availability are conditions. An issuer's listing venue alone does not establish eligibility. Freeze issuer/person eligibility and exemption status point-in-time, and audit later orders at implementation start. [R07](SOURCES.md#r07) [R08](SOURCES.md#r08)

### D3. N-PORT: three regimes, not one future assumption

| Regime | Status at this research cut | Filing / public availability consequence |
|---|---|---|
| Pre-2024 framework still operative | Current | Three monthly reports filed within 60 days of fiscal-quarter end; the third-month report is public upon filing, while the first two are nonpublic. Do not manufacture all-month public history. |
| 2024 adopted amendments, delayed in 2025 | Adopted but deferred | Monthly filing within 30 days and monthly public disclosure after 60 days. Compliance delayed to Nov 17, 2027 for groups with at least $1bn, May 18, 2028 for smaller groups. |
| February 18, 2026 proposal, IC-35962 | Proposed, not established here as final | Would generally move monthly filing to 45 days and public disclosure back to the third fiscal month after 60 days. Proposed additional changes are not current fields or historical public data. |

The official proposal page and its comparison table were checked. This is a dated regulatory-state finding, not a guarantee against future amendments. A separate names-rule N-PORT timing change uses a different asset threshold; do not confuse it with the $1bn reporting-cadence threshold. A regulatory registry needs `rule_id`, legal status, issue/effective/compliance dates, filer eligibility, public subset, schema version and source receipt. [R03](SOURCES.md#r03) [R04](SOURCES.md#r04) [R05](SOURCES.md#r05) [R11](SOURCES.md#r11)

### D4. Observed commercial capabilities versus unproved claims

No licensed API, confidential contract, proprietary sample or purchase was used. The following are **observed public documentation claims**, not certified coverage or rights. Cost is quote/entitlement-dependent unless explicitly stated; unsourced dollar-sign rankings from the original are withdrawn.

| Provider | Documented useful capability / history claim | Delivery | Unproved before admission | Stance |
|---|---|---|---|---|
| FactSet | Ownership standard feed documents holder/fund normalization, report/filing/transfer dates; legacy documentation describes equity history from 1999 | Standard feed / documented query interfaces | Current entitlement, exact universe, unrevised vintages, historical delivery, redistribution | Strong identity/history bakeoff candidate; old sample documentation is not a current SLA |
| LSEG | Global ownership and profiles; API documentation claims global history from 1997 and deeper U.S. subsets | API, feeds and cloud/bulk options documented | Different company/security coverage grains; vintage/correction preservation; customer rights | Compare exact target population and source receipts, not marketing counts |
| S&P Global | Ownership catalog claims global history from 2004; defines PIT using holding and filing dates | API/feed/cloud offerings | Filing date alone does not establish correction-vintage replay; factor products inherit source dependence | Candidate accelerator, not a second canonical 13F truth |
| Morningstar | Managed-investment portfolio endpoints and batch interfaces | Documented OpenAPI; portfolio holdings and delta requests | Sixty-month request window is not total history; historical publication, correction and fund-class coverage remain unproved | Particularly relevant to fund/vehicle depth |
| WhaleWisdom | 13F history from 2001, 13D/G from 2006; tiered API/history access | CSV/JSON API; enterprise feed arrangements | Free website access does not authorize scraping; consumer subscription is not commercial redistribution | Lower-complexity normalization comparison, subject to license |
| DTCC | Composition files, historical PCF and supplemental files | Licensed files / data service | Execution versus proposed basket, gross activity, corrections and exact rights | Defer paid basket layer until residual-identification need is demonstrated |
| Quiver | Incumbent supplemental source according to original and B0 research | Existing integration, not newly tested here | Current `ReportPeriod` versus acceptance behavior not revalidated; duplicate-source issue remains | Retain as supplemental; quarantine unsupported replay, never independent confirmation of the same SEC filing |
| Bloomberg | Original shortlist only; no sufficiently specific machine-delivery contract qualified here | Not qualified in this pass | All machine-use, history, revision and display conditions | Defer unless existing licensed rights and a discriminating need are established |

Sources [V01–V06](SOURCES.md#v01). A source can be excellent operationally yet unusable for a specific historical test. Conversely, an expensive source may be justified by entity resolution and analyst time saved even if it contributes no independent alpha.

The RFI must request the same accession-level challenge set from every provider: original and amended 13F, confidential release, joint 13D/G, partial Form 4/A, a fund merger/share-class change, a corporate action, one sponsor file silently replaced, and two historical delivery vintages. Require raw-source IDs, original units, publication timestamps with precision, first vendor availability, revision IDs, bulk/API limits, retention after termination, derived/display/redistribution/model-training permissions and a fully costed quote. Reject an answer that merely repeats “point in time.”

### D5. Source-specific identifiers, machine readability and amendment admission

| Source | Identity / machine-readable grain | Effective date versus receipt | Amendment and history qualification |
|---|---|---|---|
| 13F | Filer CIK + accession + native information-table row; CUSIP/class/instrument/discretion and optional FIGI | Report-period state; no individual trade time inferred | Parse actual form/schema version and restatement/addition flag; preserve raw document and bulk-delivery versions |
| N-PORT | Registrant CIK, series identity/LEI where supplied, accession/report date, investment row with reported identifiers such as CUSIP/ISIN/LEI | Fund fiscal-month portfolio date; public-release clock separate from submission | Structured source plus public-subset rules; amendments preserve original knowledge and never expose nonpublic months retrospectively |
| 13D/G | Accession, issuer/class, each reporting person's identity, filing category, group relation and item/cover-page assertion | Legal trigger and stated ownership basis; public dissemination may be later | Modern structured XML with narratives/footnotes; older HTML/text not assumed schema-equivalent; no complete replacement without item-level lineage |
| Forms 3/4/5 | Accession, issuer, reporting person, Table I/II row and footnote links | Holding/transaction/deemed date differs from filing availability | Structured XML and explicit amendment row correspondence; code/plan/eligibility version retained |
| Sponsor ETF / mutual-fund file | Exact vehicle/series/class, source object hash, dated row, instrument and quantity unit | Holdings cut, fund-share cut and public capture must be aligned | CSV/XLS/JSON/HTML/PDF varies by sponsor; no inferred historical archive, amendment marker or stable API |
| N-CSR / N-CSRS | Registrant/series, accession, fiscal period and schedule-of-investments document/table | Filing generally within ten days after transmitting the annual/semiannual shareholder report, not a fixed quarter-end filing offset | Electronic filings, document/interactive-data mix; amendments and incorporated portions need native document lineage; historic coverage qualified by actual retained accessions |
| DTCC PCF | Licensed portfolio/file type, ETF identifier, business date, file version and constituent row | Composition/service date and delivery time, not proved execution time | Standard/custom/supplemental records need entitled specification and revision proof before normalizing as a trade-oriented source |

The current N-PORT form and N-CSR instructions were consulted as schema/deadline references; regime applicability still follows D3 rather than an unversioned form download. [R13](SOURCES.md#r13) [R14](SOURCES.md#r14) [R15](SOURCES.md#r15)

Beneficial ownership also requires holder-specific acquisition-rights semantics. Rule 13d-3 includes relevant rights exercisable within sixty days and a separate control-purpose provision; not every convertible instrument is immediately counted. A 2026 SEC-filed 13D amendment explicitly excludes convertible-note shares under a 9.99% limitation with a 61-day waiver condition. This is a concrete example of why a mechanical quantity/issuer-shares ratio cannot replace the filed legal assertion. It is a reported example, not a general conclusion that every blocker is legally effective. [R16](SOURCES.md#r16) [R17](SOURCES.md#r17)

## E. Canonical data model and temporal semantics

### E1. Architecture choice: logical graph, native custody

The original five new `ownership_*.v1` tables are **not approved new stores or wire contracts**. Their useful concepts must first be mapped onto incumbent source receipts, catalog rows, K1 references and K2-B composition. K1 already records native identity, clocks, rights, correction/replay semantics, missingness and authority. Creating an ownership receipt that independently re-decides those fields would create the very duplicate truth plane the commission prohibits. [I03](SOURCES.md#i03) [I04](SOURCES.md#i04)

Use relational/columnar owner-native facts and pointer composition initially. A graph query can be implemented as a bounded join without a graph database. Persist a new domain artifact only when an existing owner cannot represent a required fact, its owner accepts the extension, and a named consumer justifies the storage and lifecycle. A future materialized index must beat direct owner readers against a measured requirement; theoretical future query complexity is insufficient.

The canonical subject remains the native subject until the incumbent identity owner supplies an admissible bridge. A CUSIP is not a proven current listing ID, a CIK is not a share class, and a similar manager name is not a merger. The first vertical may legitimately end with `identity_unresolved`; a successful-looking join would be worse than a useful refusal. K1's v1 all-false authority and empty automatic-effect relation set remain unchanged.

### E2. Minimum logical contracts: proposals for owner-routed extension

The following is a field-level research specification, **not deployed JSON Schema**. `native_*` values are pointers or exact original fields, not duplicated authority. Use the existing versioning owner; a renamed native clock or changed identity meaning requires its accepted compatibility process.

| Logical object / grain | Required semantic fields beyond native receipt reuse | Disallowed shortcut |
|---|---|---|
| Source binding: one exact filing/document/delivery version | Native owner/store/schema, accession/object ID, row/document selector, original-byte digest, parser version, original unit/precision, publication-evidence basis, rights reference, public/nonpublic classification | New global source ID replacing accession or native generation |
| Position assertion: one reporting party/vehicle × security/instrument × period × legally distinct assertion row | Native holder/vehicle/security IDs; `assertion_basis`; quantity and type; instrument/put-call; class/currency; reported value and unit; voting/dispositive/discretion fields; source row; completeness/omission state | Flattening beneficial interest, discretion, stock, options and principal amount into interchangeable shares |
| Beneficial-ownership assertion: one party/group × class × filing assertion | Sole/shared voting and dispositive counts; reported aggregate and percentage; denominator basis; rights-acquirable amounts; group/party membership; Item 4/6 source spans; governing eligibility rule | Summing group total plus all group members or inferring activism from form name |
| Insider transaction: one source transaction row × reporting party relation | Table I/II, transaction/deemed date, code, acquired/disposed, instrument, quantity, price/range, direct/indirect nature, post-transaction holding, derivative terms, footnote refs, plan indication, correction linkage | Form-level net buy score or treating P/S as exclusively exchange trades |
| Fund state: one portfolio/vehicle/share class × dated observation | Shares outstanding with class scope, NAV/assets/cash/currency, settlement/cut convention, share split, holdings denominator, basket type if actually known | Dividing whole-fund AUM by one class's NAV or calling secondary trading volume fund inflow |
| Relationship assertion: one typed native entity relation × evidentiary vintage | Relation kind, native endpoints, source basis, economic interval/precision, knowledge interval, resolution method and status | A second universal identity namespace or an unsupported one-parent hierarchy |
| Consumer observation: one deterministic feature recipe × exact input set × subject × cutoff | Feature/version, native refs, units, cohort, input generations, availability mode, computed value or typed refusal, numerator/denominator, caveats, output-emission time, all-false authority | Caller-authored confidence or family label creating independent decision authority |

`assertion_basis` should distinguish at least `investment_discretion_reported`, `fund_portfolio_asset`, `beneficial_voting`, `beneficial_dispositive`, `pecuniary_interest_reported` and `transaction_reported`. A single source can support several bases, but they are not automatically additive. Existing owners must approve actual enums; this report does not mutate closed vocabularies.

### E3. Entity and overlap rules

A manager complex, legal adviser, SEC filer, fund series, fund share class, beneficial-owner group, insider person, issuer, security and listing are separate roles. A legal entity can play more than one role. Retain CIK, CRD/SEC numbers, series/class IDs, CUSIP, FIGI, ISIN and vendor IDs as typed identifiers with validity and knowledge evidence. Do not publish proprietary identifier mappings merely because an identifier appeared in a public filing.

A fund's N-PORT holding may also be inside its adviser's 13F total. A parent's 13G disclosure may include subsidiary interests. A shared Form 4 may report the same transaction for multiple persons. These observations corroborate different legal assertions; adding their quantities inflates economic ownership. Introduce an inspectable overlap relation through the owner, not a blanket automatic cancellation. K1 v1 relation labels remain descriptive/manual-only, even for `exact_duplicate`; local accession idempotency inside the canonical acquisition owner is a different, already-owned operation. [I03](SOURCES.md#i03)

Manager-complex grouping reduces one form of duplication but does not establish information independence: different complexes can mimic the same index, broker research or price trend. Conversely, two strategies within one complex can differ. Publish `distinct_complex_count` and its mapping coverage, not `independent_manager_count` unless separately justified by an accepted statistical/lineage study.

### E4. Temporal contract

Every time-bearing input retains its **native field name, timezone, precision, uncertainty and provenance**. The cross-source view maps these into classes without overwriting the originals. Explicit unknowns include a reason and the consequence for eligibility; null is not midnight, zero, or the previous period.

| Clock / field concept | Meaning and invariant |
|---|---|
| `event_time` | Actual underlying transaction/legal trigger time, if reported. Do not infer quarter-long transaction dates from a position snapshot. |
| `as_of` / native report period | Economic date described. A portfolio state is a dated observation, not proof of continuous ownership until next disclosure. |
| `source_published_at` | Source publication or SEC acceptance where it actually signifies public dissemination; nonpublic N-PORT acceptance is not public release. |
| `available_at` / public `known_at` | Earliest substantiated public access time, with source and precision. Distinct from this system's first observation. |
| `observed_at` | Actual first observation by the relevant collector, not today assigned to a historical backfill. |
| `ingested_at` / recorded time | Actual persistence into the owner. Must not predate observation without an explicit legacy import meaning. |
| `effective_from/to` | Only a supported economic relationship interval. A snapshot does not automatically populate a continuous interval. |
| `knowledge_effective_from/to` | Interval in which that version was the applicable disclosed/system belief in the named replay mode. Supersession is source- and mode-specific. |
| `correction_generation` and separate version axes | Filing amendment, public release, bulk revision, vendor revision, parser reprocessing and identity correction must be distinguishable. One integer cannot stand for all six. |
| `computed_at` / `emitted_at` | Actual derived-output production. In system replay, a feature is not available before this event simply because inputs already existed. |

These concepts must map to K1's seven existing clock classes (`world_valid`, `source_published`, `knowable`, `observed`, `system_recorded`, `belief_or_build`, `review_due`) rather than replace its names with a lossy universal date. [I03](SOURCES.md#i03)

### E5. Three honest query modes

**Public-information reconstruction.** A research simulation uses original source vintages and proven public availability, plus a predeclared realistic processing/execution delay. It may use a modern research parser only when explicitly labeled current-rule reconstruction, with the parser's look-ahead risks audited. It is not described as the system's historical behavior.

**Captured-system replay.** A historical query requires original observation/persistence receipts, eligible identity/rights versions, the code/configuration actually available under the declared replay contract, and feature emission by the cutoff. No reconstruction can fabricate these missing receipts.

**Latest-corrected forensic view.** Uses later corrections to explain what is now believed to have happened. It is useful for quality analysis but cannot score a strategy as if corrected facts had been available earlier.

For a reconstructed deterministic observation, `public_eligible_at` is no earlier than the latest substantiated availability among all necessary inputs, mappings, denominator and correction versions, plus the frozen operational delay. For actual system replay, eligibility also requires each dependency's real observation/recording and the derived output's real emission. An after-close disclosure cannot be traded at that already-passed close.

A date-only source establishes an interval in its native timezone. Admit it only after a conservative upper bound and the execution policy, or reject it for intraday studies. Weekend/holiday rollover and exchange sessions use versioned calendars. Distinguish legal filing timeliness from actual market tradability.

Example, synthetic: a June 30 holding is publicly released August 14 at 17:20 ET, observed August 17 at 09:00, persisted at 09:02, and projected at 09:06. It cannot enter a June 30 backtest. A public-information simulation may enter no earlier than its predeclared post-release tradable point; actual system replay cannot use the projection before August 17 at 09:06. A September amendment leaves the August information set unchanged.

### E6. Correction, missingness and completeness

Amendment semantics are source-specific. A 13F restatement may replace the relevant prior report; an added-holdings amendment supplements it; a Form 4/A can amend selected rows while leaving unmentioned rows intact. A later public confidential-position release is new knowledge, not a retroactive public fact. Bulk-vendor or parser corrections require their own receipt even when the underlying filing did not change. Ambiguous lineage is quarantined rather than guessed.

A comparable pair requires both source states, compatible instruments/units, valid corporate-action handling, eligible knowledge clocks, a resolvable entity relation and a declared report scope. It still does **not** prove all economic ownership was disclosed. Missing states include `not_yet_filed`, `not_in_public_subset`, `notice_only`, `confidential_or_omittable`, `source_unavailable`, `rights_blocked`, `identity_unresolved`, `incompatible_units`, `correction_unresolved` and `history_not_retained`; these names are descriptive proposals, not permission to extend K1's closed enums silently.

Store a snapshot point at its stated date. A display can carry the last disclosed fact forward with an increasing age and an explicit `last_disclosed` label. That is a statement about current knowledge, not an interval of known continuous ownership.

## F. Derived intelligence and invalid interpretations

### F1. Deterministic features, not one fused score

| Feature / proposed label | Exact calculation or observation | Necessary caveat |
|---|---|---|
| Paired disclosed-share change | Corporate-action-consistent `q1 - q0` for a valid pair | Not a trade path, dollar flow, or current position |
| Disclosed increase/decrease breadth | Counts and share of eligible comparable reporting entities/complexes by sign | Freeze cohort; show unavailable reporters and mapping coverage |
| First disclosed / no longer disclosed | Presence transition in comparable report scope | Not necessarily economic initiation/liquidation because of reportability, omissions and custody changes |
| Reported-book allocation change | Change in share of the same reportable book, plus price-only counterfactual | Not total portfolio conviction; valuation and book-boundary changes can drive weights |
| Major-holder event | New public assertion, disclosed percentage change, legal category or reported-purpose change | Separate issuer dilution from holder quantity change; percentage basis may be holder-specific |
| Potential activism | Source-backed purpose/arrangements classification with spans | 13D alone is insufficient; no automatic activist probability |
| Insider purchase/sale classification | Code, table, instrument, footnotes, price and plan metadata | P/S is not necessarily open-market common equity; non-cash transactions remain separate |
| Fund net issuance | Split-adjusted `S1 - S0` | Net, not gross creations and redemptions; not secondary-market volume |
| Approximate net issuance dollars | `NAV_reference × (S1-S0)` with cut/basis disclosed | Approximation; settlement, distributions, fees, share-class and multi-currency cases can differ |
| Non-proportional ETF holding change | Split/corporate-action-adjusted `H1 - H0 × S1/S0` | Residual under proportional-scaling assumption, not identified discretionary trade |
| Observed-holder concentration | Cohort-defined HHI/top-holder metrics below | Incomplete and overlapping legal claims cannot be described as full issuer ownership |
| Crowding/co-holding structure | Inspectable concentration, fund similarity, mandate and liquidity dimensions | No opaque “crowding score”; dependence and adverse liquidity channels remain separate |

These are proposed research features, not measured predictive results.

### F2. Why ETF residuals do not identify active trading

Let a fund initially have 100 outstanding units and hold 1,000 shares of a security. At the next disclosure it has 110 units and holds 1,100 shares. The proportional residual is zero. This is consistent with pure scaling, but also with offsetting active trades; zero residual does not prove zero discretionary activity.

Now suppose the second holding is 1,150. The residual is 50. Two observationally compatible mechanisms are: a proportional 100-share in-kind creation plus a 50-share market purchase; or a custom creation basket containing 150 shares and no market purchase. Holdings and shares outstanding are identical. Therefore even perfect shares-outstanding data does not identify the underlying active market trade. Cash substitutions, corporate actions and settlement differences add ambiguity. Rule 6c-11 expressly permits custom baskets, and DTCC distinguishes standard/custom composition services. [R10](SOURCES.md#r10) [V06](SOURCES.md#v06)

Use `non_proportional_holdings_change` or `pro_rata_residual`; reserve `observed_trade` for a trade-oriented source that actually reports it. A sponsor's disclosed trade file is a distinct source with its own completeness, timing and rights—not confirmation that every holdings residual is a trade. Improving true fund-share data remains worthwhile, but it repairs the scaling input, not the identification problem.

### F3. Concentration and denominators

For a non-overlapping, explicitly defined observed holder cohort with quantities `q_i`, `HHI_observed = sum((q_i / sum(q))^2)` describes concentration **within that cohort**. Separately, `sum((q_i / S)^2)` with eligible issuer-class shares `S` is an observed partial issuer-basis quantity, not the full issuer HHI. Do not normalize missing holders away and call the result comprehensive.

Synthetic example: observed holders own 40 and 10 shares, while the issuer has 100 shares. Observed-cohort HHI is 0.68; their partial issuer-basis sum is 0.17. The unobserved 50 shares could belong to one holder or many. Neither 0.68 nor 0.17 identifies complete ownership concentration. Add parent/subsidiary overlap and even the observed sum can exceed economic ownership unless claims are resolved.

Record the denominator's class, economic date, publication/knowledge date, basic/diluted/float or legal basis and treatment of acquirable securities. A contemporaneously filed shares-outstanding value may describe a different economic date from the holding. A disclosed 13D percentage and a recomputation using a later issuer denominator are different observations. Report both with bases or refuse comparability; do not silently “correct” the legal filing.

### F4. Explicitly prohibited interpretations

“Quarter-end ownership buying happened today”; “a missing or omitted position is a confirmed sale”; “13F is the whole long/short book”; “a 13G filer is a passive index investor”; “13D always means activism”; “every Form 4 acquisition is a cash conviction purchase”; “ETF inflow equals constituent buying”; “shares normalization proves active intent”; “distinct complexes are independent evidence”; “three vendor copies are three confirmations”; “the latest corrected table proves historical knowability”; and “no current filing means zero interest” are all prohibited without the source-specific evidence needed to establish the narrower claim.

### F5. LLM boundary

Deterministic owners compute quantities, units, corporate-action adjustments, cohorts, denominators, eligibility, lineage, rights gates, missingness and feature outputs first. LLMs do not repair these numerically or invent dates.

A cheaper model can propose bounded Item 4/6 purpose categories, extract explicit footnote propositions, suggest aliases for review, and summarize already-validated differences. Each output carries model/prompt version, exact source spans, extraction confidence/calibration evidence if used, ambiguity and an abstention option. An alias suggestion cannot merge identities. A model's explanation cannot convert P/S into open-market trading without supporting text.

A frontier model is justified for a contested multi-document activist case, conflicting legal assertions or a synthesis connecting a verified ownership event with independently sourced fundamentals. Escalate only after deterministic contradictions and missingness are exposed. Maintain rights-safe source access, prompt-injection isolation, token/cost accounting and a human/owner review path. Publicly available source content is data, never instructions. Neither model tier grants trading or evidence-promotion authority.

## G. Integration map and ownership boundaries

| Producer | Incumbent canonical custody / proposed extension seam | Evidence class | Existing consumer / boundary |
|---|---|---|---|
| SEC 13F | Macro institutional census, raw receipt/catalog/holding row → existing `lib/institutional_13f_adapter.py` | Disclosed investment-discretion snapshot | K1 refs + K2-B intent; company context; no second 13F truth |
| SEC 13D/G | Existing beneficial-ownership producer; qualify native accession/item/version semantics | Beneficial assertion and disclosed-purpose event | Company/research context, with separate legal and inference fields |
| SEC insider filings | Existing insider source owner after precise census; transaction-row adaptation | Insider transaction | Existing insider consumer; never unioned numerically with 13F |
| N-PORT | Fund-source owner to be resolved/admitted; native series/class/position/public-release semantics | Fund-portfolio snapshot | Cross-check and vehicle-level context; no all-month public fiction |
| Sponsor portfolios / shares / NAV | Existing holdings collectors and normalization owner | Fund state, net issuance, proportional-model residual | Existing holdings research/context; no identification of AP market trades |
| Issuer class / listing / corporate actions | Existing Data OS / stock-identity and accepted native alias owners | Identity and denominator evidence | Native bridge only; no new house-global identity service |
| Ownership domain projections | K1 Ref/Block/Recipe and K2-B manager-intent composition | Fact, deterministic view and inference kept separate | Terminal incumbent Institutional card / research desk after owner acceptance |
| Research Vault documents | Existing private Research Vault / RIO owners | Source-backed narrative claims | Explanatory context only; no copied proprietary research corpus in this graph |
| Evaluation / predictions / outcomes | Existing experiment and grading owners | Frozen experiment and prospective evidence | No second outcome ledger or ranker |
| Portfolio V3 | Only an actually accepted current implementation of its snapshot/claim seam | Future governed receipt consumption | No prerequisite to build a substitute portfolio control plane now |

The Terminal #734 integration is especially important: it consumes the existing Company Intelligence v1 institutional context and does not silently insert that sidecar into the v2 current-event truth plane. Preserve exact generation and subject bindings. A future Investigation can reference accepted context; it does not become a new holder truth store. [I05](SOURCES.md#i05) [I08](SOURCES.md#i08)

K1 source-independence, information-novelty and mechanism-independence declarations remain `declarative_unverified` in v1. Automatic deduplication/suppression across evidence legs would require an independently accepted owner-native lineage capability, not this report's permission. The Commission 7 candidate is adjacent research, not authority to change that contract.

## H. Empirical validation program

### H1. Two different acceptance questions

**Engineering/context utility:** Can a user see the correct disclosed fact, period, source, lineage and limitation without duplicate counting or fabricated precision? Measure receipt resolvability, exact replay agreement, source-to-consumer latency, mapping/paired coverage, correction propagation, failure visibility and time saved relative to current readers. This can justify a bounded context feature without predicting returns.

**Predictive utility:** Does a pre-specified feature improve an out-of-sample target beyond a strong existing baseline at genuinely actionable availability, with plausible costs and stable coverage? No result has been run or claimed here. This section is the proposed protocol to freeze with the incumbent evaluation owner before outcome access.

### H2. Dataset admission before labels

Construct a source inventory by family, period, filer eligibility, report type, native schema, raw version availability, timestamp precision, missingness, rights, share-class mapping and corporate-action coverage. Compare rows accepted and rejected against the universe, not only successful rows. Keep all historical filers, fund closures and delisted securities that the source/universe design admits. A current famous-manager roster is an explicit descriptive subset, not a valid historical manager-selection experiment.

The intended first U.S. equity experiment uses point-in-time common-equity listings and clearly tagged ADR/FPI strata. Funds, preferreds, debt principal amounts and option-underlying counts are not silently mixed with common shares. Exact exchange, liquidity and price filters must be frozen from input availability and intended consumer scope, not tuned using outcomes. Missing delisting proceeds and corporate-action gaps are exclusions with denominators, not a zero return.

Every experiment declares one of the three modes in E5. Public-information reconstruction can be scientifically useful; actual-system replay is stricter. Report performance separately. A sponsor's current download cannot establish a daily historical panel. A modern filing parser must not use future amendments, future manager hierarchies or today's security alias table as if historically known.

### H3. Proposed confirmatory experiment budget

The following six primary tests are a **proposal for owner acceptance**, not a claim that an experiment has been registered or run. Freeze definitions, cutoff rules, estimator, baselines, sampling and primary horizon before labels are unsealed. Each additional feature variant, subgroup, threshold or horizon is recorded in the existing hypothesis ledger.

| Family | One proposed primary test | Primary horizon / target | Controls and decisive alternative explanation |
|---|---|---|---|
| 13F disclosed breadth | Incremental predictive contribution of paired, corporate-action-consistent disclosed-share breadth | 60 trading sessions; date-level rank association and nested-model out-of-sample improvement | Size, sector, liquidity, momentum, beta, volatility, prior ownership, coverage and filing cohort; distinguish momentum-following |
| 13D disclosed purpose/event | Post-actionable-disclosure abnormal return for source-classified purpose events | 20 sessions after the first eligible execution point | Prior returns, size/liquidity, sector, concurrent known events, issuer/holder clustering; pre-filing and immediate announcement returns excluded from executable return |
| 13G major-holder change | Incremental contribution of quantity-based holder change within legal/mandate strata | 60 sessions | Passive/QII/exempt categories, index/mandate data known at cutoff, dilution and cohort effects |
| Insider transactions | Incremental contribution of qualified common-equity purchase observations/clusters versus incumbent insider baseline | 20 sessions | Prior-only routine classification, role, disclosed transaction economics, plan status, earnings-calendar information known at cutoff |
| ETF residual | Incremental contribution of non-proportional holdings change beyond raw net issuance and price controls | 5 sessions | Sponsor/fund effects, mandate/rebalance, currency, settlement and basket uncertainty; not labeled active intent |
| Ownership concentration | Incremental risk forecast rather than directional alpha | Next 20-session downside semivariance; held-out forecast loss | Size, liquidity, volatility, sector, index membership and incomplete-coverage flags |

For the first five return-oriented families, freeze the main estimand and one associated out-of-sample evaluation metric, rather than declaring every IC, bucket return and Sharpe ratio a separate route to success. For concentration, define downside semivariance deterministically as the sum of squared negative daily returns over the target window and compare forecast loss to the baseline. All secondary diagnostics remain visible regardless of sign.

Use multiplicity control across the six primary hypotheses—proposed Holm family-wise control at 5%, subject to the evaluation owner's approved protocol. A failed primary test cannot be rescued by silently relabeling a secondary horizon as primary. Exploratory variants require another frozen test with a new untouched sample or prospective cohort. A pre-specified interaction may be tested even if both marginal effects are null, but it consumes declared experiment budget and must improve the joint baseline out of sample; this corrects the original report's overly rigid “every component must survive alone” rule.

### H4. Splits, inference and leakage guards

Use calendar-ordered development, validation and untouched evaluation windows, with embargo/purge lengths at least covering label overlap and information overlap relevant to the design. Exact dates are chosen only after the source-only coverage audit, recorded before outcomes, and not moved to improve results. Retain a truly prospective stream after the retrospective evaluation.

Cluster by information origin and calendar/filing cohort; repeated securities within one manager filing and overlapping forward windows are not independent trials. Use pre-specified date-block bootstrap or suitable multiway clustered inference; disclose the number of effective independent blocks rather than using row count as sample size. Manager fixed effects do not cure endogenous selection or missing history. The old empirical literature is a hypothesis source, not a power estimate for this universe.

Set minimum detectable economically useful effect and power from development-only variability, realistic costs and the intended decision use. Insufficient independent observations means `INCONCLUSIVE`, not a flexible p-value threshold. Do not invent “six months is enough” or count thousands of within-season rows as thousands of independent experiments.

Required leakage falsifiers include swapping public availability for report date, replacing as-filed vintages with latest corrected data, substituting today's roster/identity edges, and admitting date-only observations at same-day open. These intentionally invalid variants must be labeled negative-control demonstrations, never admissible strategies. A large improvement under leakage is a diagnostic warning, not evidence of the feature's value.

### H5. Baseline, costs and ablations

The price/factor baseline includes only variables available at the forecast cutoff: sector, size, beta, volatility, liquidity, short- and medium-term returns and any existing PIT fundamental/earnings predictors the consumer actually uses. Compare nested versions with and without each family, with the same universe, missingness handling and tuning budget. Include raw fund net issuance before testing ETF residuals, and the incumbent insider feature before testing new insider classification.

Mandatory ablations: receipt/time eligibility; corporate actions; manager-complex grouping; public versus actual-system mode; original versus corrected vintages; known versus unresolved mandate; high versus low mapping coverage; filing-era regimes; mega-cap exclusion; leave-one-manager/season-out sensitivity; and the separately tagged FPI regime. Select ablations before outcome inspection where they affect confirmatory interpretation.

For tradable claims, use attainable entry prices after publication/processing, spreads, slippage, turnover, market impact and capacity assumptions tied to an explicit execution model. Report public filing-day jumps separately from post-entry returns. A statistically significant pre-publication association or impractically stale net effect is not a usable signal. A 13G comparison group is informative but not a randomized counterfactual for 13D activism; causal language requires a separately defended design.

### H6. Promotion and kill rules

A family advances only through separate decisions: **source-qualified → descriptive/context accepted → research hypothesis frozen → retrospective evidence assessed → prospective shadow assessed → explicitly governed consumer admission**. These are research-stage descriptions, not a new runtime state machine. Promotion consumes the existing evaluation and authority mechanisms.

Kill or permanently demote a construction when its apparent benefit requires report-date leakage, future revisions, survivor rosters, guessed identity, inferred zero from missingness, incompatible units, or source rights that prohibit the minimum replay evidence. Defer rather than call alpha when history or statistical power is inadequate. Retain a useful context-only feature when risk/verification utility is established but return prediction fails. Stop procurement when a public baseline provides the same usable information at lower total cost and no vendor-specific operational benefit justifies the expense.

The ETF residual may survive as a predictive observable while the “active trade” interpretation remains rejected. The graph can be useful while the alpha hypothesis is null. Both outcomes must remain possible.

## I. Risks, failure modes and acceptance fixtures

### I1. Highest-consequence risks

The dominant risks are semantic rather than computational: confusing reporting discretion with ultimate economic ownership; propagating later corrections backward; counting a parent, subsidiaries and funds together; inferring trades from partial snapshots; and treating a legal filing category as an investor's economic mandate. Temporal identity and rights are inputs to eligibility, not optional metadata added after feature calculation.

Operational risks include source schema drift, EDGAR throttling, partial filing-season outages, silently overwritten sponsor downloads, source timezone ambiguity, absent public-release receipts, and healthy workflow exits that conceal incomplete output. Design a source-specific health surface with last successful receipt, public/observed/processed-through clocks, backlog, amendment/confidential-release backlog, mapping coverage, paired-cohort coverage, unresolved quantity units, public-subset eligibility and consumer-generation readback. Do not overwrite the global system census or manufacture an alternative health authority.

Governance risks include rebuilding K1, changing an all-false envelope, automatically suppressing relations in K1 v1, granting a vendor cleaner-table authority, conflating narrative confidence with source reliability, and accidentally deploying source-only research via an existing workflow. This publication changes only a research directory; no production path or workflow is modified.

Rights risks include licensed identifier restrictions, source archive limits, vendor termination clauses, redistribution of normalized records, and copying Research Vault text into a public repository. Record permissions separately for raw storage, internal research, backtesting, derived features, external display, redistribution, retention and model training. `publicly_viewable` does not imply `redistributable` or `model_training_allowed`.

### I2. Required adversarial fixture matrix for the later implementer

These are **36 specified acceptance cases, not 36 executed production tests**. The executed finite arithmetic checks in `verify_research.py` have a narrower scope.

| ID | Adversarial input | Required result |
|---|---|---|
| T01 | June quarter-end report released in August | Ineligible in June |
| T02 | Filing publicly released before local capture | Reconstruction and actual-system replay differ correctly |
| T03 | After-close filing | No entry at the already-passed close |
| T04 | Date-only publication with intraday cutoff | Conservative interval bound or refusal |
| T05 | Nonpublic N-PORT month | Not admitted as public evidence |
| T06 | 2024 delayed / 2026 proposed N-PORT rule applied to old data | Regime mismatch refused |
| T07 | New FPI Form 3 after March 2026 | Coverage change, not new buying |
| T08 | Claimed FPI exemption based only on listing venue | Eligibility unresolved/refused |
| T09 | Incoming manager has not filed | Missing, not seller |
| T10 | 13F-NT | Notice, not zero portfolio |
| T11 | Small position disappears from filed 13F | No unsupported confirmed liquidation |
| T12 | Confidential holding becomes public later | New knowledge; prior replay unchanged |
| T13 | 13F added-holdings amendment | Correct supplemental lineage, not blind replacement |
| T14 | 13F restatement | Relevant prior assertion replaced only in new knowledge state |
| T15 | Form 4/A repeats only corrected line | Unchanged valid rows survive |
| T16 | Bulk dataset republished without new filing | Bulk version separate from source amendment |
| T17 | Parser repair changes normalized quantity | New derived vintage; no forged source timestamp |
| T18 | Dollars versus thousands / SH versus PRN | Exact unit handling or typed refusal |
| T19 | Option underlying count next to stock shares | No common-share ownership sum |
| T20 | Security split/CUSIP/class migration | No fabricated initiation/exit |
| T21 | Future manager-parent mapping supplied | Historical cutoff rejects future edge |
| T22 | CIK/CUSIP guessed into a listing ID | Native unresolved subject retained |
| T23 | Parent/child 13G plus fund N-PORT plus adviser 13F | No additive economic ownership without overlap proof |
| T24 | Joint Form 4 reporters | One economic transaction not multiplied blindly |
| T25 | Private P purchase or derivative P row | Not mislabeled open-market common-stock purchase |
| T26 | 10b5-1 checkbox absent or unknown | Not silently converted to false/discretionary |
| T27 | Same quantity but denominator dilution | Percent change not called holder selling |
| T28 | Observed HHI versus issuer denominator | Metrics remain distinct with incomplete coverage |
| T29 | Pure proportional ETF scaling | Residual zero within declared numerical tolerance |
| T30 | Custom basket produces positive residual | Residual not identified as a market trade |
| T31 | Fund share split or class-specific NAV | No fabricated issuance or whole-fund AUM conversion |
| T32 | SEC filing and vendor copy | Shared origin visible; K1 v1 automatic suppression remains off |
| T33 | Source rights block required leg | Fail closed, not successful degraded evidence laundering |
| T34 | Derived output emitted after cutoff | Actual-system replay excludes it |
| T35 | Corrected input has missing predecessor / mismatched subject | Refuse composition |
| T36 | Healthy workflow but missing/old consumer generation | Not accepted as end-to-end live proof |

### I3. Security and publication design

Use bounded official access, cache lawfully, honor rate limits and avoid parallel downloads designed to bypass service limits. Raw filing footnotes and research documents are untrusted content. Models receive only required rights-permitted text and cannot execute source instructions. Do not place tokens, broker data, personal identifiers beyond legitimately published filing fields, proprietary vendor samples or full research PDFs in this public research package.

No data access is licensed by this report. Unknown rights block the affected ingestion/display or training action; they need not block mathematical reasoning, public-document comparison or development of synthetic acceptance cases.

## J. Build priority

| Priority | Bounded recommendation | Gate / kill boundary |
|---|---|---|
| P0 | Recover current K2-C/K2-B/K1 owner state and exact prior repair/proof lineage | No replacement project, no live incumbent displacement, no new store |
| P0 | Freeze one consumer's native-clock, correction and unresolved-identity contract | Public reconstruction and actual-system replay distinct; all-false authority |
| P0 | Prove one same-filer two-period 13F projection or useful fail-closed refusal | Receipt → native row → exact subject → consumer output, no guessed bridge |
| P0 | Qualify source/consumer health and pair completeness at that seam | Successful workflow alone insufficient |
| P1 | Source-specific 13D/G and insider amendments/transaction typing | Current legal regime, precise rows, joint ownership, native history and rights |
| P1 | True fund-share data plus honest ETF residuals | Fund/class/cut/corporate actions; no active-trade identification claim |
| P1 | N-PORT vehicle history where public release can be proved | Fiscal/public subset, eligibility and historical schema qualification |
| P1 | Concentration/context features and preregistered family experiments | Denominators/overlap first; no scalar sponsorship score |
| P2 | Vendor bakeoff for history, identity, source coverage or operating cost | Licensed sample, correction challenge and total-cost comparison required |
| P2 | Optional graph materialization / cross-owner index | Named consumer and measured direct-reader failure; owner-approved storage only |
| Defer | Global full-ownership expansion and intraday basket/AP inference | Coordinate China #8398; no universal cadence or ownership ontology assumptions |
| Defer | Manager-skill models and activist probability models | Prior-only histories, valid outcomes, calibration and prospective proof first |
| Reject | New universal 13F collector, parallel identity/evidence/outcome plane | Incumbent owners exist |
| Reject | Snapshot delta labeled real-time flow; residual labeled observed active trade | Identification not supported by available measurements |
| Reject | Automatic K1 v1 relation suppression or positive investment authority | Contrary to accepted contract |
| Reject | Backdating sponsor snapshots or later corrections; opaque ownership score | Unreplayable / hides evidence dimensions |

## K. Sequenced implementation recommendation

### Phase 0 — Reconcile the existing seam

The later owner fresh-pins protected Mastermind, Macro and Terminal, reads current K1/K2 contracts, identifies the actual active carrier/lease and inspects K2-C historical and current proof artifacts. Recover the August semantic-repair lineage rather than implementing from the old PR body. Recheck the original's claims about Quiver timing, fund-share proxies, static census age, consumers and V3 with direct current code/runtime evidence. These are explicit unresolved audit questions, not pre-authorized repair targets.

**Exit:** source/owner/consumer identity, discrepancy ledger, required native fields and one bounded change set accepted. **Stop:** missing authority or an unreconciled live/effect-unknown writer. Do not create a new workstream simply to make the portfolio look complete.

### Phase 1 — One 13F comparison, native composition only

Reuse canonical 13F owner readers and existing K2-C adaptation. Prove a complete evidence chain for one same-filer pair and a separate refusal case. Add only the smallest owner-approved domain semantics needed to distinguish snapshot date, public availability, real observation, amendment version and output generation. Retain native CUSIP identity when no accepted bridge exists. Use a local/synthetic fixture path unless a separately admitted read-only production proof is necessary.

**Exit:** discriminating fixtures, exact-source reproduction, source-only diff, existing consumer contract demonstration and honest capability state. **Stop:** any need for a second store, unapproved schema evolution, live pipeline change, identity service or authority increase.

### Phase 2 — Qualify existing 13D/G and insider sources

Separate commissions adapt existing producers. Validate legal categories, group/party overlap, row-level amendments, instrument economics and the 2026 FPI coverage break. Add Item 4/footnote extraction only when deterministic source fields are insufficient, with exact source spans and abstention.

**Exit:** source-specific replay and missingness proofs, not a common undifferentiated “buying” stream. No additional source purchase.

### Phase 3 — Fund portfolios and issuance

Qualify N-PORT public history and sponsor archive rights. Resolve portfolio series versus share class, same-cut shares/NAV/holdings and corporate actions. Retain the non-identification caveat for residuals even when normalization improves. Public sponsor pages demonstrate that useful daily fields exist; they do not prove archived vintages or stable interfaces. [R12](SOURCES.md#r12)

**Exit:** a lawful, replayable bounded fund panel and exact coverage table. **Stop:** inability to prove historical public release, lack of archival rights, or material same-cut mismatch. Prospective capture can proceed in a separately authorized owner lane rather than fabricating history.

### Phase 4 — Context utility and frozen empirical evaluation

First measure correct presentation and analyst utility against the existing surface. Then register the accepted H-section protocol through the incumbent evaluation owner before outcomes. Run retrospective studies only on admitted data, preserve nulls, and start prospective shadow evaluation only through an explicit commission.

**Exit:** named accepted contextual utility or evidence sufficient for the next gated research stage. Failure of alpha does not erase context value; neither context value nor a p-value grants portfolio authority.

### Phase 5 — Targeted acceleration and eventual governed consumption

Run a vendor bakeoff only for a measured gap. Consider physical graph/index materialization only after a failed direct-reader requirement. Integrate with a genuinely accepted future Decision Snapshot/claim owner, not an imagined implementation. Record cost, lock-in, retention and exit plan before purchase. Any investment authority is a separate admission decision through existing governance.

### Planning envelope and sequencing discipline

Do not attach invented calendar commitments to unresolved data rights and owner state. Estimate each phase after its predecessor fixes input scope. The first engineering commission should be no broader than the one 13F seam and its tests; 13D/G, Form 4, N-PORT, ETF normalization, graph persistence, observability for the whole platform, and predictive experiments are **not bundled into that first job**. Parallel research on rights/regulatory semantics is safe; parallel source mutation of the same incumbent owner is not.

## L. Exact follow-on implementation commission — not executed

> **Title:** Recover and qualify the incumbent institutional 13F evidence seam.
>
> **Assignment condition:** Issue this commission only after the responsible owner accepts this research recommendation and current source custody/admission are resolved. This text is a future implementation handoff, not authority to execute during Commission 10.
>
> **User outcome:** For one explicitly selected existing consumer, produce an exact, inspectable comparison of two eligible disclosed 13F positions—or a truthful typed refusal—with report period, public availability, actual system clocks where retained, native subject, source receipts, amendment lineage and no investment authority.
>
> **Source law:** Fresh-pin protected Mastermind and the current canonical Macro/Terminal revisions. Load the required Skillpack at one protected revision. Read current K1 EvidenceRef/Block/Recipe, K2-B manager-intent contracts, `lib/institutional_13f_adapter.py`, the 13F owner readers/catalog, current native identity law, the latest K2-C semantic-repair/proof carrier, and the current existing consumer contract. The research pins in this report are historical evidence only.
>
> **Custody and collisions:** Determine whether an existing K2-C repair operation/PR remains active. Continue that lawful carrier when required; do not replace an active writer or duplicate its work. Reconcile pending effects before any retry. Check Commission 7, company-context/Terminal ownership and relevant source-law changes. Acquire/reuse the assigned workspace through the current canonical launcher. Record PICKUP_ACK and separate START where the existing carrier requires them; no invented organizational parent or alternate queue.
>
> **Allowed outcome boundary:** Reuse existing owner accessors, source receipts, native identities and correction mechanisms. Make the smallest owner-approved adapter/fixture/consumer-contract repair necessary to prove this one seam. No physical ownership graph, new global ID, new source store, universal collector, scheduler, alternative grader, source purchase or production rollout is authorized. If the existing contract cannot express a necessary field, return the exact versioned owner-extension proposal before changing a closed schema.
>
> **Required pre-change findings:** Verify, rather than inherit, the current K2-C proof status; source publication and retained observation clocks; exact two-period row availability; amendment semantics; quantity/value units; subject compatibility; report completeness; and consumer generation pin. Record which original report claims remain unproved. Workflow success is not a substitute for a source-to-consumer receipt.
>
> **Implementation target:** One same-filer, same-instrument two-period comparison with a declared report scope and corporate-action policy, plus one deliberately unresolvable case. Existing owner-native CUSIP identity is acceptable; fabricated listing resolution is not. The output exposes disclosed increase/decrease or no-longer-disclosed status, not current flow or confirmed liquidation without additional evidence. All five existing authority booleans stay false.
>
> **Clocks:** Preserve native names and precision. Distinguish public-information reconstruction, captured-system replay and latest-corrected forensics. No derived output may precede its required inputs or actual emission in system replay. A later amendment, bulk revision, parser repair or identity correction cannot rewrite a prior eligible generation. A snapshot's economic date does not establish continuous ownership until the next report.
>
> **Required tests:** Exercise T01–T04, T09–T23, T32–T36 insofar as they touch this 13F seam; Form 4-specific cases remain specification-only for later work. Explicitly prove missing-manager/notice/omittable-position behavior, added-holdings versus restatement lineage, units and instrument separation, future identity rejection, exact cutoff behavior, immutable prior replay and source rights refusal. Run the incumbent K1/K2 suites affected by the exact diff. Demonstrate a passing valid pair and a discriminating invalid/refused pair, not only a happy-path schema check. Do not claim the unrelated future family tests passed.
>
> **Production boundary:** Default to fixture/local proof. A production owner-read must have the existing owner's separately valid read-only admission and exact permitted principal/path. Do not dispatch a workflow, change collector schedules, backfill live stores or publish new production projections under a general “research accepted” interpretation. A successful source PR is not deployment permission.
>
> **Deliverables:** Exact source/custody/collision pins; minimal scoped diff; native-contract adoption map; input/receipt hashes; actual test commands/results bound to semantic head; deterministic valid and refused projections; clock/correction/coverage explanation; rights status; consumer compatibility evidence; and a capability ledger distinguishing accepted contracts, built source and current live proof. Publish on the lawful source branch/PR with no autonomous merge or trading change.
>
> **Escalation/stop conditions:** An unreconciled writer or effect, unknown required public clock, unsupported unit/subject, ambiguous amendment, blocked rights, insufficient retained history, or need for a new identity/store/authority plane stops the affected action. Return the exact typed blocker and the smallest owner decision needed. Continue independent permitted tests or documentation; do not invent missing facts to keep the lane green.
>
> **Completion:** The one named consumer seam is reproducible from exact owner evidence at the specified cutoff, required affected tests pass on the exact candidate, all authority remains false, and publication is verified. A useful refusal is accepted only when it is the correctly specified outcome, not a substitute for a valid pair that the source was expected to support. State any remaining `BUILT_NOT_PROVEN` runtime obligations explicitly.
>
> **Stop after this seam.** Do not proceed automatically to 13D/G, Form 4, N-PORT, ETF residuals, vendor procurement, graph persistence, empirical promotion, Portfolio V3 implementation or trading. Those require their own bounded commissions.
