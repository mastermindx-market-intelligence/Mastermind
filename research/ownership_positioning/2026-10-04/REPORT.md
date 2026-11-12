# Commission 10 — Institutional Ownership & Positioning Graph
## Hardened research, architecture and implementation recommendation

**Research date:** 2026-10-04. **Disposition:** complete research recommendation; acceptance and implementation remain separate. **Scope:** documentation and source investigation only. No market-outcome experiment, production pipeline modification, procurement, deployment, portfolio change or evidence-authority promotion was performed.

This report supersedes the attached `deep-research-report (17).md` as the Commission 10 recommendation, not the incumbent repositories' accepted contracts. The original file's SHA-256 is `1b4ebf1874b23980931145534d3c4e2f926153b17559a33859c6acce5873dd4d`. Its central distinction—ownership snapshots are not real-time flows—is retained. Its census, proposed new contract ownership, several financial interpretations and first implementation scope are materially revised. See [audit and census](AUDIT_AND_CENSUS.md), [source register](SOURCE_REGISTER.md), [source manifest](SOURCE_MANIFEST.json) and [acceptance specification](VALIDATION_SPEC.md).

**Evidence notation.** `Ixx` identifies an immutable internal source or exact PR in the source register; `Rxx` identifies a primary external source. Observed repository content, documented external capabilities, proposed architecture and unverified operational claims are distinguished. A fetched source is not automatically a fully reviewed or production-proven capability. Commercial descriptions are not licensed-data acceptance receipts.

## A. Executive conclusion

### A1. Build a coherent view over existing owners, not a new ownership platform

Mastermind should deliver a per-company answer to: **Who disclosed which kind of ownership or transaction, for what economic date, when could that information be used, what changed on a comparable basis, and which interpretations remain unsupported?** The answer should retain separate views of investment discretion, beneficial ownership, insider transactions, fund portfolios, fund-level issuance and inferred portfolio changes. It should show contradictions and uncertainty instead of translating every increase into institutional conviction.

The strategic opportunity is real, but the original report understates the installed foundation. Macro already contains a canonical universal 13F evidence/census owner, a separate curated desk, a K1 evidence-reference boundary, K2-B manager-complex/vehicle epochs and a deterministic research-intent compiler. The merged K2-C pilot binds a two-period security observation to actual owner rows and four cutoff-checked references. Terminal already has an Institutional ownership workspace. Research Vault is an application/data estate inside Macro, not the similarly named disaster-recovery repository. Rebuilding these would increase rather than reduce fragmentation. [I09–I12, I19–I21, I24, I27–I29](SOURCE_REGISTER.md)

**Recommendation:** adopt the existing source owners and extend their reference-compatible, effective-dated projections only where a demonstrated missing fact or semantic defect requires it. Start with a narrow read-only 13F vertical slice through K2-C and an existing company-context consumer. Add other legal disclosure types through separately bounded source adapters. Do not create a second raw archive, identity master, evidence ledger, experiment ledger, health store, publication pointer or portfolio control plane.

### A2. Importance and value hierarchy

The priority is **P0 for correctness and consumption of existing data**, **P1 for missing fund/transaction coverage and prospective capture**, and **conditional for predictive investment use**. The first payoff is truthful context: avoid imaginary selling, duplicate confirmations, false historical availability and misleading active-flow claims. A structural-risk feature can be valuable without forecasting positive returns. Return prediction, risk prediction and analyst usefulness need different acceptance evidence.

The graph is a logical set of relationships over incumbent artifacts. It does not justify a graph database by itself. Existing immutable canonical JSON and content-addressed generations remain authoritative where already specified; Parquet and graph-shaped views are reproducible query projections. A new storage engine is a later performance decision, not a research prerequisite. [I09](SOURCE_REGISTER.md)

### A3. The seven boundaries that determine whether the plan is sound

1. **Disclosed position is not economic position today.** A snapshot may be accurate for its stated date and still be old, partial and unsuitable for current trade attribution.
2. **A missing row is not necessarily an exit.** Missing filings, optional omissions, confidential treatment, eligibility changes and unresolved identities require different states.
3. **Public opportunity and actual system knowledge are different replay questions.** Neither may be silently substituted for the other.
4. **Legal ownership planes cannot be summed.** A parent 13F filer, its fund vehicle and a beneficial owner can describe overlapping interests.
5. **A quantity residual is not identified intent.** Even true fund shares outstanding does not remove custom-basket or non-trade explanations.
6. **Reference independence is not statistical independence.** Separate forms can reflect the same underlying economic event; separate vendors can repackage the same filing.
7. **Research completion is not build or promotion approval.** Section L is a proposed future commission, not an instruction executed in this audit.

## B. Current-state census

### B1. Source-law pin and scope of recensus

The attached report's Mastermind and Macro pins were superseded. The following revisions were resolved through live repository metadata and used for this bounded source census:

| Estate | Canonical repository | Default branch and pinned revision | Observed protection / scope |
|---|---|---|---|
| Mastermind | `mastermindx-market-intelligence/Mastermind` | `master` — `521720b09be2921e996d9396b522b1c4ca62041c` | Protected branch; Skillpack loaded at this exact revision |
| Macro | `mastermindx-market-intelligence/macro` | `main` — `79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f` | Branch metadata reported `protected: false`; not described here as protected |
| Terminal/charting | `mastermindx-market-intelligence/mastermind-terminal` | `master` — `1c708450187755160e1a5889b69598a2fcb1f0d1` | Protected branch; ownership workspace and API source present |
| Research Vault | Macro's `engine/research_vault/`, related API/catalog and research-intelligence modules | Same Macro revision | Separate application/data responsibility, not a separately inferred repository |

The Mastermind index identifies `mastermind.sol_skillpack.v1`, version `1.0.1`, minimum bootstrap major `1`. Required cold-start, active-execution, session-reliability, review-return and closeout procedures were read from the same protected pin. Publication uses one managed attended workspace; there is no direct protected-branch push. These are source/procedure observations, not runtime admission or deployment receipts. [I01–I02](SOURCE_REGISTER.md)

Mastermind's recursive tree was complete at 3,139 entries and Terminal's at 3,994 entries. Macro's first recursive result was truncated at 64,113 entries. That result was **not** used to assert absence: separate `engine`, `research` and `docs` subtrees were retrieved without truncation, and exact relevant paths and PR file lists were then inspected. The manifest records the selected file bytes, SHA-256, Git blob identity and source commit. This is a relevant-domain recensus, not an exhaustive audit of every dataset or runtime in the company.

### B2. Capability ledger

| Capability / owner | Evidence-supported state | Material finding and remaining gap |
|---|---|---|
| Macro `engine/institutional_census/` | `BUILT_NOT_PROVEN` by this audit | Immutable evidence, filing lineage, generation publication, paired cohorts and public context are implemented/documented. Current retained production generations and unattended operational health were not sampled. |
| Curated Smart Money desk / `collectors/edgar_13f.py` | `BUILT_NOT_PROVEN` | Separate bounded manager cohort, not the universal universe. Historical roster sizes must not become current coverage claims. |
| K1 evidence-reference validation | `BUILT_NOT_PROVEN` at the reviewed K2 interface | Existing references own provenance, clocks, rights, missingness and replay; copying these into a rival evidence envelope is prohibited. |
| K2-B `lib/institutional_intelligence.py` and contracts | `BUILT_NOT_PROVEN` | Manager-complex/filer/vehicle epochs and four distinct research planes already exist; full real-world population coverage is not established. |
| K2-C `lib/institutional_13f_adapter.py` | `BUILT_NOT_PROVEN` | Merged owner-native CUSIP, two-period selected-row binding, four reference cutoffs and a read-only proof lane. A source pilot is not proof that all issuers are served live. |
| Company institutional context | `BUILT_NOT_PROVEN` | Existing contracts, health and views; reuse the sidecar rather than adding another per-company store. |
| Ownership event wire | `BUILT_NOT_PROVEN` | Existing unfused event projection; preserve legal-family separation and receipt lineage. |
| Ownership crowding and forward ledger | `BUILT_NOT_PROVEN` | Display-only crowding and existing append-only/maturing outcome mechanisms. The original report missed these owners. |
| Beneficial ownership / insider lanes | `PARTIAL` for the proposed unified graph | Existing source/engine paths; transaction-line, joint-group, legal-regime and amendment compatibility require a bounded qualification. |
| ETF holdings / `engine/holdings_signals.py` | `PARTIAL` | Multiple residual concepts coexist. Legacy price-adjusted weight language overstates intent; K2 distinguishes true-S from proxy inputs. A universal clean historical true-S panel is not proven. |
| N-PORT canonical ownership adapter | `NOT_BUILT` in the bounded reviewed integration surface | No mature K1/K2-compatible historical ownership adapter was established. This is not a claim that no N-PORT data exists anywhere. |
| Terminal Institutional workspace | `BUILT_NOT_PROVEN` | PR #734 was merged September 25; `OwnershipPage.tsx`, company-context card/library/API exist. The input's dismissal based on repository description is wrong. |
| Research Vault | `BUILT_NOT_PROVEN` | Existing Macro ingestion/catalog/storage and research-intelligence interfaces. No private corpus was accessed or copied. |
| Mastermind `flows_13f`, held-risk and research desk | Source consumers present; operational state not re-proved | 13F context already influences legacy reasoning/flags. New graph authority remains zero; that does not mean existing legacy consumers are inert. |
| Portfolio V3 Decision Snapshot / claim ledger | `SPEC_ONLY` / documented `NOT_BUILT` | The current design still labels itself production-inert. This audit did not prove a deployed V3 replacement. |
| Mastermind static census | Stale generated artifact | Generated July 16, 2026 at `131290a`. This does not prove the underlying feeds are stale; Macro already specifies source-health alarms. |

Sources: [I03–I21, I24, I27–I30](SOURCE_REGISTER.md). Detailed disagreements and exact read surfaces are in [AUDIT_AND_CENSUS.md](AUDIT_AND_CENSUS.md).

### B3. Existing contracts materially change the architecture

K2-B is already an in-memory, deterministic, persistence-free compiler with five false authority booleans. Its observations bind to complete K1 references; they do not manufacture their own rights, replay or coverage fields. Manager complexes, filers and vehicles already have effective, valid and knowable epochs, closed decision-mode categories and correction lineage. K2-C adds a `source_backed_owner_row` basis: previous/current raw receipts plus previous/current catalog generations, with accession, row identity/hash and owner-native CUSIP. Raw-receipt operational knowability is `max(accepted_at, retained_at)`; catalog availability is its publication time. All bound dependencies must qualify at the cutoff. [I10–I12, I24](SOURCE_REGISTER.md)

Consequently, the original five-schema proposal is useful only as a **logical requirements checklist**. It is not authorization to instantiate five new canonical stores. The actual design task is mapping missing source-native facts to incumbent owners, extending accepted contracts additively where necessary and proving the real read path.

### B4. Adjacent projects and collision ruling

Macro PR #6533 is merged and owns the K2-C pilot. PR #5911 is the prior B0 source/rights/collision census. Their work must be adopted, not rediscovered as greenfield architecture. Terminal PR #734 is merged and supplies an existing presentation destination. Macro PR #7354 (`b8833c40cb4c9541cc4449e72f5c5f8be8308d1a`) and #7387 (`7931b0f5360d526b18191f987f5ec11d432a66eb`) were open drafts: they concern institutional research-document reading and longitudinal evidence, not a second ownership source. Their outputs are not accepted main-branch capability. Shared evidence vocabulary/rights changes in the draft semiconductor carrier #7870 are an interface collision to recheck before any implementation that touches those shared contracts. [I25–I29](SOURCE_REGISTER.md)

The B0 census also names Stock Identity, theme identity, Synapse artifact registration, existing company context, source-health ownership and forward evaluation. Those remain the integration homes. Its historical warning about Quiver `ReportPeriod` filtering is carried as **an unresolved standing risk**: this pass did not independently re-prove the current offending code path. It must not be laundered into a newly verified production defect or silently dismissed. [I13, I23, I29](SOURCE_REGISTER.md)

### B5. Preliminary hypotheses: what this commission did and did not establish

The selected source reads confirm substantial existing ownership consumption, PIT fundamental and survivorship methodology, and the distinction between V3 design and production. They do not recertify the completeness or history of every options, breadth, earnings-expectation, analyst-revision, theme, political or government-contract lane listed in the shared prompt. In particular, a mature historical analyst-revision series and canonical fine-grained dynamic subtheme history were **not established as available controls**. The ownership validation program must accept those controls only after their actual owners qualify a historical panel. Missing unrelated evidence must not be fabricated to make the research specification look complete. [I08, I30](SOURCE_REGISTER.md)

## C. State-of-the-art research and its implications

The literature supports distinct mechanisms, not the blanket proposition that institutions know better. The following are research motivations and counterarguments, not replications or expected Mastermind returns. Where only an abstract or publisher summary was accessible, that is the review depth; no unavailable methods or numerical reproduction is claimed.

| Primary research | Finding relevant to this commission | What Mastermind should test / not infer |
|---|---|---|
| Coval and Stafford, *Asset Fire Sales (and Purchases) in Equity Markets*, JFE 2007; NBER working paper | Flow-constrained mutual funds can create temporary pressure through common holdings; the working-paper sample spans 1980–2003. | Separate forced liquidity demand from informed stock selection. Do not transfer old price-pressure magnitudes to current ETFs. [R28](SOURCE_REGISTER.md#r28) |
| Greenwood and Thesmar, *Stock Price Fragility*, JFE 2011 | Ownership composition and correlated liquidity needs can matter for volatility and comovement; concentration alone is insufficient. | Begin with structural risk, then evaluate flow covariance only where real historical inputs exist. Do not call HHI a complete fragility measure. [R30](SOURCE_REGISTER.md#r30) |
| Cohen, Malloy and Pomorski, *Decoding Inside Information*, JF 2012 | Routine and non-routine insider activity differ in information content. | Estimate any routine-trading label only from history available before each event; do not use future behavior to classify the past. [R31](SOURCE_REGISTER.md#r31) |
| Brav, Jiang, Partnoy and Thomas, *Hedge Fund Activism, Corporate Governance, and Firm Performance*, JF 2008 | The authors study interventions and corporate outcomes, not simply all large ownership stakes. | Classify disclosed objectives and distinguish announcement reaction from post-disclosure implementable returns. A 13D is a candidate case, not proof of a value-creating campaign. [R32](SOURCE_REGISTER.md#r32) |
| Edelen, Ince and Kadlec, *Institutional Investors and Stock Return Anomalies*, JFE 2016 | Relations between institutional demand and returns can reverse with the measurement horizon; institutional buying is not uniformly informed. | Preregister horizon and sign. Retain adverse or null results instead of relabeling them as patient smart money. [R33](SOURCE_REGISTER.md#r33) |
| Friberg, Goldstein and Hankins, *Corporate Responses to Stock Price Fragility*, JFE 2024 | The authors relate fragility to precautionary corporate behavior, including cash and investment. | Test whether positioning helps explain corporate financing or risk outcomes, not just next-month alpha; observational portability remains unproved. [R34](SOURCE_REGISTER.md#r34) |

Lou's 2012 *A Flow-Based Explanation for Return Predictability* is a relevant further methodological reference; the primary institutional publication record was verified, not a full independent replication. [R29](SOURCE_REGISTER.md#r29)

The institutional engineering implication is a separation of **observations, mechanisms and predictions**. A holder change is an observation. “Redemptions forced a sale” is a mechanism requiring vehicle-flow evidence. “The price will recover” is a prediction requiring a frozen, out-of-sample test. Those three statements must have different types and acceptance gates. Keeping them separate makes contradictions useful: a growing disclosed stake can coexist with fund outflows, passive index demand, deteriorating fundamentals or an activist's unsuccessful plan.

## D. Source landscape and legal-regime matrix

### D1. Public, regulatory and first-party sources

The deadlines below describe ordinary requirements, not a compliance opinion for every exception. Implementation needs a versioned jurisdiction/form/filer-category calendar and must use actual publication, not an inferred deadline, for availability. Source-specific exceptions and exemptive relief remain visible.

| Source | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| SEC 13F | Investment discretion over reportable securities; not a complete economic book | Structured bulk begins July 2013; source archive reaches earlier | Quarterly, generally due within 45 days | Strong only with original public filing and generation clocks | Restatement, additional-holdings amendment, confidential release, bulk revisions | Public access; attached third-party material and identifier licensing still require care | No data fee; engineering/storage | Delayed disclosed-position and comparable-reporter context |
| SEC N-PORT | Registered-fund portfolio observations; public subset only | Public structured series begins October 2019 | Current regime: quarter-based filing/publication; see D3 | Public release must be distinguished from private submission | NPORT amendments and revised bulk extracts | Public released records, not nonpublic months | No data fee; medium integration | Mutual-fund/ETF vehicle holdings and validation |
| Schedule 13D | Beneficial-ownership events and disclosed purposes | Long EDGAR history; modern XML regime | Generally five business days initially, two for material amendments | Event date is not public-knowledge date | Item-specific updates, new events and corrections | Public source | No data fee; text/identity work | Control-purpose and major-holder case intelligence |
| Schedule 13G | QII, passive and exempt beneficial owners | Long EDGAR history; modern XML regime | Category/threshold dependent | Mixed lags; preserve category | Quarterly material-change and accelerated amendments | Public source | No data fee | Large-holder structure; regime transitions |
| Form 4, with Forms 3/5 context | Section 16 transactions and ownership; non-derivative and derivative tables | SEC insider bulk begins January 2006 | Generally two business days; exceptions remain typed | Good when actual acceptance, transaction and footnotes retained | Line-specific Form 4/A additions/corrections | Public source | No data fee | Reported insider transaction economics, not automatic bullishness |
| Sponsor ETF holdings | Fund/portfolio-specific disclosed holdings | Often current-only unless lawfully retained | Usually daily for transparent products | Publication/capture dependent | Same URL may overwrite bytes; no uniform archive promise | Sponsor-specific storage/display/redistribution terms | No fee to view; capture cost | Current portfolio state and prospective comparisons |
| Sponsor NAV / fund shares outstanding | Fund- or class-level units and NAV, not stock trades | Product/source dependent | Daily when supplied | Requires synchronized as-of and publication clocks | Restatements, split/class changes | Source-specific | Free-to-enterprise | Net issuance and normalization inputs |
| Sponsor trade notifications | Explicit, but potentially incomplete, trade reports | Source-specific; ARK says no historical trade archive | After execution/day-end for the reviewed ARK service | Stronger transaction semantics than a holdings residual, but not necessarily reconciled | Supplementary files and omissions | Terms and capture permission required | Free-to-view; retention cost | Validation of inferred changes, not a comprehensive tape |
| Mutual-fund sponsor disclosures | Full, partial or top holdings depending on product | Variable | Monthly/quarterly or less often | Uneven timestamps and coverage | Vendor/sponsor-specific | Source-specific | Variable | Supplement N-PORT; never turn top holdings into a full portfolio |
| Issuer filings and incumbent reference owners | Security class, share count, corporate actions and identity | Source-specific PIT history | Filing/event cadence | Denominator and mapping clocks are dependencies | Issuance, splits, restatements, class changes | Existing source/identifier rights | Existing/free-to-commercial | Ownership fractions and false-change controls |

Source basis: [R01–R16](SOURCE_REGISTER.md). Access cost is not total cost; reconciliation, rights review, monitoring and identifiers can dominate a nominally free feed.

### D2. 13F, 13D/G and Form 4 particulars

**13F.** Preserve filer CIK, accession, source row ordinal, report date, acceptance, security/class identifier, put/call, share/principal unit, reported value, discretion, voting fields and other-manager references. XML became mandatory May 20, 2013. The value convention changed to nearest dollars for filings made from January 3, 2023, including amendments concerning older periods; historical forms used thousands. Optional omission of a position requires both fewer than 10,000 shares and value below $200,000. [R01–R02](SOURCE_REGISTER.md)

Design consequences are substantial. Parse unit semantics from the filing/schema generation, not the economic quarter. Preserve anomalous filings as unresolved rather than certifying a unit from a price heuristic. Use `not_redisclosed` rather than `confirmed_exit` unless additional evidence rules out omission and identity discontinuity. Distinguish a notice from a portfolio; preserve shared discretion and parent/other-manager relations before counting independent holders. A holdings-row absence is not an executed sale, even when the manager filed.

**Schedules 13D/G.** The 2023 final amendments shortened deadlines and introduced structured-data requirements, with new 13G timing compliance from September 30, 2024 and structured-data compliance from December 18, 2024. Earlier historical periods must retain their old reporting regime. [R03–R04](SOURCE_REGISTER.md)

| Category | Ordinary initial filing trigger/deadline under the reviewed current framework | Amendment handling to encode |
|---|---|---|
| 13D | More than 5%, generally five business days; loss of 13G eligibility can also trigger | Material changes generally within two business days; one percentage point is a presumptively material change, not the only one |
| 13G qualified institutional investor (QII) | Generally 45 days after calendar quarter-end when above 5% at quarter-end; if above 10% before quarter-end, five business days after the first month-end at which ownership exceeds 10% | Material changes: 45 days after quarter-end. After initial filing, above 10% measured at month-end: five business days after that month-end; thereafter a change exceeding five percentage points of the class: five business days after the relevant month-end |
| 13G exempt investor | Generally 45 days after the relevant calendar quarter-end | Material changes: 45 days after quarter-end; do not incorrectly apply the QII accelerated category to all exempt holders |
| 13G passive investor | Generally five business days after crossing 5%, while eligible for the passive category | Material changes: 45 days after quarter-end; after initial filing, crossing above 10%, then increases/decreases exceeding five percentage points of the class: two business days after the triggering event |

The accelerated change threshold is **more than five percentage points of the class**, not a 5% relative change in the holder's position. The quarterly 13G amendment rule excludes a change caused solely by a change in total shares outstanding; a filed reduction to 5% or less ends the applicable continuing amendment duty unless a new filing requirement arises. Passive 13G eligibility requires ownership below 20% and the applicable non-control conditions; crossing 20% or losing eligibility invokes the relevant 13D transition rules. Encode these exceptions by rule version, rather than applying a single “13G lag.” Filing acceptance can occur after trading hours; the modern D/G filing cutoff is 10 p.m. Eastern, not the equity-market close. [R03](SOURCE_REGISTER.md#r03)

A 13D/A can disclose **a new economic event**, not just correct an old error. Preserve item-level effective dates and stated purposes. `13g_to_13d_transition` is evidence of a disclosure-regime change, not automatic proof of an activist's skill or a successful intervention. The reported beneficial fraction can include acquisition rights and holder-specific denominator treatment under Rule 13d-3; it is not interchangeable with common shares outstanding from an unrelated issuer date. [R04, R16](SOURCE_REGISTER.md)

**Form 4.** SEC code `P` means an open-market **or private** purchase; `S` similarly includes private sales. The original `insider_open_market_net = P − S` is therefore wrongly named without additional transaction evidence. Preserve code, acquired/disposed flag, price and footnote range, security/derivative table, direct/indirect ownership, role, plan indicator and exact amended lines. Grants, exercises, withholding and gifts are not interchangeable purchase economics. [R05](SOURCE_REGISTER.md#r05)

The dataset's July 2025 reprocessing added the Rule 10b5-1 field for certain earlier bulk windows. That is a bulk-extract revision, not proof that the field existed in Mastermind's historic ingestion. A checked plan box reports intended reliance, not proven legal compliance or lack of information. Form 4/A can amend particular lines while leaving others intact. [R05–R06](SOURCE_REGISTER.md)

**Material 2026 coverage break:** the HFIA Act extended Section 16(a) reporting to directors and officers of covered foreign private issuers from March 18, 2026. SEC orders provide conditional relief for qualifying foreign regimes, with additional relief in May. This is neither blanket coverage of every foreign insider nor a universal extension to every foreign 10% holder. Encode issuer/role/regime eligibility, order conditions and dates; do not interpret a new Form 3 as a purchase or missing exempt reports as inactivity. [R07–R08](SOURCE_REGISTER.md)

### D3. N-PORT must be modeled by the rule in effect, not the most attractive future cadence

| Regime | Filing and public-data implication | Status at this research cut |
|---|---|---|
| Current pre-reform cadence | Monthly observations are submitted on the fund's fiscal-quarter cycle, due 60 days after quarter-end; only the third month's report is public under this regime | Baseline for current historical source qualification |
| 2024 adopted amendments, deferred in 2025 | Monthly filing within 30 days and monthly public disclosure after 60 days; larger fund-group implementation deferred to November 17, 2027, smaller groups to May 18, 2028 | Adopted but not a basis for claiming monthly public 2026 history |
| February 18, 2026 proposal, IC-35962 | Proposes 45-day monthly filing and restoration of quarterly public disclosure, among other changes | SEC docket still identified it as **Proposed** when checked; not treated as final law |

The cadence deferral uses a $1 billion fund-group threshold; do not import the different $10 billion threshold from the separate Names Rule timetable. The exact implementation-start rules must be rechecked before a future adapter is released. [R09–R11](SOURCE_REGISTER.md)

Record fiscal quarter, portfolio month and public-release status separately. A deadline is not an observed public timestamp; early public availability requires evidence, and nonpublic first/second months remain unavailable. One fund series can have multiple share classes: class identifiers must not multiply the same portfolio. N-PORT is valuable for structural holdings and validation; it does not supply a real-time mutual-fund allocation tape.

### D4. ETF holdings, actual trade notifications and flow identifiability

Rule 6c-11 requires prior-business-day portfolio disclosures before regular trading for ETFs relying on that rule and permits custom baskets. Not every exchange-traded product relies on that rule. Therefore daily transparency must be established product by product, and a creation basket must not be assumed identical to the published portfolio. [R12](SOURCE_REGISTER.md#r12)

ARK offers a useful first-party distinction: daily holdings and trade notifications are separate products; notifications exclude creation/redemption activity and certain offerings, are described as unofficial/unreconciled, can be supplemented, and are not a comprehensive execution ledger. Its help center says historical trade archives are not provided. The trade-email upload time is not the exact execution time. These explicit limitations are better evidence than a generic vendor “smart money flow” label. [R13–R14](SOURCE_REGISTER.md)

A future lawful prospective capture can compare a residual with an explicitly disclosed trade, but neither source is universal ground truth. Do not collect through prohibited browser workarounds, assume unrestricted archives or infer trade settlement conventions from stale website boilerplate. The current B0 source restrictions remain controlling unless formally superseded. [I23, I29](SOURCE_REGISTER.md)

### D5. Commercial normalization and history accelerators

The table distinguishes public documentation from a validated delivery. **No licensed sample, entitlement, executed license or current quote was inspected.** Cost classes are deliberately not invented dollar estimates.

| Source | Coverage/history represented in reviewed public documentation | Delivery/latency represented | PIT/correction evidence still required | Rights and cost class / decision |
|---|---|---|---|---|
| FactSet Ownership | Global institutional/fund normalization; a historical overview describes equity history from 1999 | Standard datafeed; exact subscribed interfaces require qualification | Original publication clocks, coverage by source/era, inactive entities, revision vintages | Enterprise quote; identity/history bakeoff candidate, not pre-approved |
| LSEG Ownership | Global ownership/funds; advertised depth varies by market/source, including longer US 13F history | Ownership API plus feed/cloud channels | Source-form identity, timestamp precision, changed-history feed and survivor coverage | Enterprise quote; strong global/identity candidate |
| S&P Global Ownership | Public listing advertises history from 2004 and filing/holding dates | API/feed/cloud distribution; daily update descriptions | “PIT” defined by dates is insufficient to certify intraday availability or correction replay | Enterprise quote; test actual vintage semantics |
| Morningstar managed investments | Fund/vehicle/holdings focus | Reviewed async API allows up to 60 months per request and supports delta loading | Request span is not a history guarantee; require publication rather than only portfolio date | Enterprise quote; strong fund complement candidate |
| Bloomberg Data License | Enterprise data delivery capabilities; ownership-specific coverage not proved here | REST/SFTP/cloud products documented | Exact ownership package, historical vintages and machine entitlement | Enterprise quote; defer unless an existing license supplies incremental value |
| WhaleWisdom | 13F specialist; advertised history from Q1 2001 | API and enterprise delivery options | Disable/segregate `include_13d` behavior that can replace latest 13F holdings with D/G data; preserve source family and clocks | Paid self-service / enterprise; convenience benchmark, not canonical replacement |
| Quiver | Convenient current 13F-change endpoint | Sample separates `Date` and `ReportPeriod` | A date-at-midnight is not certified acceptance time; reconcile to SEC accession and avoid existing duplicate authority | Paid/API entitlement unverified; supplemental only |
| Benzinga institutional portfolio API | Advertises normalized 13F history from 2013 and active/delisted coverage | JSON/CSV/flat-file delivery described | Verify accession/time/correction fields; “capital flow” marketing does not change snapshot semantics | Quote/contract required; optional normalization benchmark |

Sources: [R17–R27](SOURCE_REGISTER.md). Historical start dates are vendor claims at differing product scopes, not promises that every required field has that vintage.

**Bakeoff design.** Give each candidate the same stratified, rights-cleared source set: ordinary 13F, additional-holdings amendment, restatement, notice, confidential release, manager merger, class change, 13D/G group, Form 4/A, N-PORT series/classes and fund-share split. Require original IDs, first-public precision, first-delivered time, full correction history, raw/normalized linkage, row-level explanations, inactive coverage, bulk/API limits and permitted uses. Compare mapping accuracy, arrival distribution, exception rate, correction replay and total operating cost against the incumbent public owner. A vendor wins only a demonstrated missing delta. No vendor becomes an independent confirmation of its own underlying SEC source.

**Procurement kill:** do not buy merely to obtain a larger holder count, a proprietary composite, an unlicensed terminal export or a latest-corrected historical table. Reject offers that cannot retain enough source/vintage evidence to reproduce the intended experiment. Rights review must separately cover storage, backtests, internal analytics, LLM processing/training, customer display, derived-data distribution, audit retention and termination/export. Public accessibility is not permission for all of these uses.

## E. Canonical data model and temporal semantics

### E1. Logical graph, incumbent custody

The graph should answer relationships without confusing their legal meanings. The minimum nodes are manager complex, reporting filer, adviser, fund portfolio/vehicle, fund share class, beneficial-owner party/group, insider/person, issuer and security/share class. They are not a compulsory hierarchy: advisers and filers can relate to multiple vehicles; a joint filing group can contain persons and entities; a company parent does not necessarily identify an independent investment decision center.

Reuse K2's epoch identities and the existing Stock Identity bridge. Preserve typed external identifiers—CIK, CRD/SEC identifiers, series/class IDs, CUSIP, ISIN, FIGI and exchange-qualified ticker—only when lawfully supplied and evidenced. A ticker is a time-dependent alias, not a security primary key. K2-C's owner-native CUSIP is not silently converted into a resolved Data OS security axis. Name similarity may create a review candidate, never an authoritative merge. [I10–I13, I24, I29](SOURCE_REGISTER.md)

| Logical requirement from original report | Existing authority to adopt | Smallest proposed extension, only if missing |
|---|---|---|
| Source event / receipt | Native source owner plus accepted K1 EvidenceRef | Source-specific form version, public/private state, typed amendment purpose and transaction-line locator; no second raw ledger |
| Position snapshot | 13F canonical owner rows; incumbent sponsor/fund owners for their own data | Explicit legal-position plane, completeness reason, original quantity/unit and exact row binding |
| Effective-dated entity edge | K2 manager/filer/vehicle epochs and existing identity owners | Proven adviser, joint-group, insider or fund-class relations not represented today; no competing global IDs |
| Fund vehicle state | Existing holdings/fund-flow owner; K2 Fund Flow Pressure inputs | True shares-outstanding observation, class/portfolio aggregation basis, NAV and date alignment |
| Derived positioning observation | K2 recipe/compiler and native consumer projections | Typed descriptive measures and unresolved states, with source/transform dependency references |
| Insider transaction | Incumbent insider acquisition owner | Separate transaction-line grain, not a position row overloaded with transaction semantics |
| Evaluation / freshness | Existing ownership ledger, Eval/experiment and source-health owners | Required metrics or adapter-specific dimensions, not another scheduler or outcome table |

The published interface should be a deterministic, read-only projection of these owners. If an existing contract cannot express a necessary fact, the implementation must return a named schema amendment for its owner; it must not silently bypass the validator or emit a lookalike parallel schema. [I09–I18](SOURCE_REGISTER.md)

### E2. Natural keys, payloads and lineage

The following is a **requirements-level model**, not a claim that these fields have already been added:

| Logical record | Natural grain / identity | Required payload and refusal conditions |
|---|---|---|
| Filing observation | Source namespace + accession/object ID + original byte digest + source generation | Form/schema, filer, original publication evidence, public status, report period, amendment relationship, parser version. Same URL with changed bytes is a new observation, not an overwrite. |
| Disclosed position | Filing generation + original row identity + legal plane | Subject security/class, reporting party/vehicle, quantity and unit, value/currency/unit certainty, discretion/voting fields, put/call or derivative classification. Never merge rows solely by ticker. |
| Beneficial interest | Filing/item/party or group + security class + stated effective date | Reported percentage, share count, voting/dispositive powers, denominator basis and acquisition rights, purpose references; overlap unresolved remains explicit. |
| Insider transaction | Accession + table + source row/footnote binding + amendment lineage | Transaction/deemed date, code, acquired/disposed, amount, reported price/range, security, direct/indirect, post-transaction holding, role and plan state. Do not join unrelated transactions by equal price/date. |
| Vehicle state | Portfolio or fund share class + state date + source generation | Shares outstanding and adjustment basis, NAV, AUM, currency, coverage, publication/observation clocks. A class's shares cannot normalize the entire multi-class portfolio without a proved bridge. |
| Identity relation | Existing entity epoch pair + relationship type + evidence reference | Effective, valid and knowable intervals; confidence/resolution and correction lineage; overlap and parentage separate from evidence independence. |
| Derived observation | Recipe version + input reference set + cutoff/mode + subject + measure | Deterministic value or typed absence, denominator, units, coverage, dependency digest, permitted interpretation and all-false new authority. |

Preserve original source values even when normalized outputs are rejected. Public raw receipts belong in their accepted source stores, not in Git. Sensitive insider/person data and licensed identifiers should be minimized in public projections. A public research package should contain design and provenance references, not replicated commercial datasets.

### E3. Required clocks and their specific meanings

| Field/concept | Definition | Important non-equivalence |
|---|---|---|
| `event_time` | Stated economic or legal event time, when known | Quarter-end is not the unknown time of every underlying trade |
| `as_of` | Time/date described by a snapshot | Not public availability |
| `source_published_at` / `public_available_at` | Evidenced first public availability of this source generation | Submission or acceptance of a nonpublic record is not publication |
| `observed_at` / incumbent `first_seen_at` | First actual observation/retention by the system | Cannot be backfilled to a date before capture |
| `ingested_at` | Actual persistence/processing time | Not the event time and not automatically consumer readiness |
| `known_at` / `available_at` | Compatibility field bound to an explicit replay mode and native owner clock | No unqualified universal timestamp that hides different questions |
| `effective_from`, `effective_to` | Source-supported legal/economic interval for a relation or state | A point snapshot does not prove uninterrupted ownership to the next report |
| `knowledge_effective_from/to` | Interval during which a particular generation is selected under the declared knowledge mode | Later knowledge can change interpretation without changing the original event |
| `correction_generation` | Immutable lineage version for a correction | Distinguish source amendment, parser fix, identifier remap and bulk re-extract |
| `time_precision`, `timezone`, uncertainty bounds | Resolution and temporal uncertainty of the source | A date must not masquerade as a known intraday timestamp |
| `derived_ready_at` / dependency publication times | Latest time all necessary input generations were usable and the actual result was available | A raw filing does not make a later mapping or feature computation available earlier |

Where the native owner uses different names, publish an explicit mapping rather than creating a fifth temporal vocabulary. K1/K2's currently accepted date-grain rule remains controlling until its owner approves an amendment. A proposed future timezone-aware interval representation must not be slipped into an adapter as a relaxation of that rule. [I09–I10, I29](SOURCE_REGISTER.md)

### E4. Three replay modes, never mixed within a result

**1. Actual operational replay.** What could this system's consumer actually have used at time `t`? Select only original source and derived generations whose actual retention, validation, catalog publication and consumer-readiness dependencies were satisfied. For the existing K2-C raw receipt, start with `max(accepted_at, retained_at)` and also check both catalog publication clocks and every additional mapping/denominator dependency. Do not weaken the four-reference gate. [I10–I12](SOURCE_REGISTER.md)

**2. Historical public-information reconstruction.** What was publicly obtainable at time `t`, under an explicitly assumed acquisition/processing policy? An immutable historical public filing with a reliable acceptance/publication timestamp may support this study even if Mastermind first collected it in 2026. Record its real 2026 capture separately. Reconstruct only the public source generation and identities genuinely supportable at `t`, then apply a frozen and disclosed latency rule. Label the result counterfactual/public-opportunity research, **not Mastermind's actual historical track record**.

**3. Latest-corrected forensic view.** What does the latest available correction say about a past date? Useful for reconciliation and explaining a changed conclusion, but forbidden as the historical prediction information set.

The original report's blanket rejection of all backfilled data lacking historical system observation is too broad. Its underlying prohibition on look-ahead is correct. The repaired rule allows defensible public reconstruction while refusing invented first-seen clocks, undocumented historical vendor vintages, current-only sponsor reconstructions and corrected-future leakage.

For a derived observation with dependencies `D`, the design invariant is:

```text
eligible(d, t, mode) must hold for every d in D
availability_floor = max(mode_specific_availability(d) for d in D)
result must use the generation selected at t, not the latest generation today
actual operational use additionally requires actual materialization/readiness
```

A date-only source must use the conservative bound imposed by its accepted owner. A filing published after market close must not earn the return from the preceding close. A legal deadline, a bulk ZIP publication date and an original filing's public timestamp are three different facts.

### E5. Corrections and missingness

Treat source amendments by their actual semantics: replacement/restatement, additional holdings, a new event, correction of specified items, or an unresolved relation. A Form 4/A must not erase unaffected original transactions. An N-PORT amendment cannot rewrite a previous public information set. A newly published confidential 13F position becomes observable at release, not at the old quarter-end. A SEC bulk package can be republished without a new source filing; capture that delivery revision separately. [R01–R06, R11](SOURCE_REGISTER.md)

Required missingness distinctions include: no filing yet, notice-only, not reportable, optionally omitted/unknown, confidentially omitted, security not found in an otherwise qualifying filing, incomplete portfolio, unresolved identifier, ambiguous duplicate/shared position, missing prior period, unavailable true-S, rights blocked, publication time unknown and source outage. These are proposed required meanings; implementation should reuse the closest accepted native states and request an additive amendment only where no faithful state exists.

Do not replace missing values with zero. An explicit zero, a disclosed disposition, an absent row and an unavailable predecessor have different evidential force. A forward-filled snapshot is labeled an inferred last-disclosed state with its age and coverage; it does not manufacture an `effective_to` or assert that the holding stayed constant.

### E6. Evidence independence and overlap

Assign identity at three levels: original source observation, economic event/campaign and analytic mechanism. SEC and vendor copies of the same accession share an observation root. A 13D and a Form 4 about one acquisition can be different disclosures of the same economic event. Different funds within one manager complex need not be independent decisions. Conversely, shared parent ownership alone does not prove all managers execute the same strategy.

The graph should preserve overlap relationships and dependency references, not force every correlated pair into one simplistic family label. Count a unique source once; compute manager breadth only on resolved decision-center cohorts; measure residual statistical dependence empirically. Conflicting quantities from legally different planes remain visible until reconciled. Do not silently sum them or let an LLM select the more persuasive number.

## F. Derived intelligence: calculations, useful interpretations and invalid claims

### F1. Deterministic primitives before language-model reasoning

The deterministic layer must resolve source lineage, select point-in-time generations, validate rows/units, apply evidenced corporate actions, construct comparable cohorts, bind identities, check rights, calculate all quantities and publish coverage. The language layer receives the result and receipts; it does not determine arithmetic, availability or authority.

| Output | Definition / input requirement | Safe interpretation | Main reason to withhold |
|---|---|---|---|
| `reported_position_change` | Comparable adjusted quantities, same legal plane and subject; `Q1 − Q0` | Change between disclosed snapshots | Missing predecessor, ambiguous class/units, shared-discretion overlap |
| `newly_disclosed_position` | Current disclosed row without a comparable prior disclosure | Newly visible in the selected reporting cohort | Must not be called a new purchase without separate transaction evidence |
| `not_redisclosed_position` | Prior row absent from qualifying current public disclosure | No longer present in that public disclosure | Does not establish liquidation, especially with omission or confidentiality |
| `independent_complex_breadth` | Increasing/decreasing resolved decision-center counts plus exact eligible/excluded set | Breadth of comparable disclosed change | Unresolved complex overlap, unmatched periods or cohort drift |
| `reported_sleeve_weight_change` | Same reported sleeve, proved values/units and complete denominator | Reallocation within the disclosed sleeve | Not the manager's economic gross/net portfolio weight |
| `beneficial_interest_change` | Same party/group, class and denominator basis across filings | Disclosed change in legal beneficial interest | Denominator shift or overlapping joint reports |
| `purpose_or_regime_change` | Source-backed Item 4/category changes | A research case about stated intent | Filing form alone does not prove activism or likely success |
| `reported_purchase_sale_net` | Eligible P/S transaction economics with footnotes and exclusions | Net reported purchase/sale activity | Private/open-market ambiguity; missing price or derivative conversion |
| `verified_open_market_purchase` | Additional source evidence establishes market purchase | Narrower insider evidence | P code alone is insufficient |
| `net_fund_share_issuance` | Corporate-action-adjusted `S1 − S0` | Net change in vehicle units | Does not identify gross creations and redemptions separately |
| `non_pro_rata_quantity_residual` | `Q1 − Q0 × S1/S0` with true synchronized S | Deviation from proportional portfolio scaling | Not proof of active trade or intent; custom baskets/rebalances remain |
| `covered_holder_concentration` | Deduplicated same-plane covered positions and explicit denominator | Structure of observed ownership subset | Unknown overlap or mixed dates/classes |
| `liquidity_exposure_context` | Covered holdings versus an independently qualified ADV basis | Scenario context, not liquidation timing | Gross/net assumptions, stale ADV or unknown seller participation |

The currently accepted K2 compiler may use different field labels. Any user-facing semantic repair should be a versioned compatibility change, not a silent rename of a runtime contract. [I10, I15–I18](SOURCE_REGISTER.md)

### F2. Fund-flow decomposition: what the algebra does and does not identify

For one consistent portfolio basis, let `Q0,Q1` be split-adjusted security quantities and `S0,S1` actual fund shares outstanding at matched dates. With `S0 > 0`:

```text
net_share_issuance = S1 - S0
proportional_quantity = Q0 * S1 / S0
quantity_residual = Q1 - proportional_quantity
residual_fraction_of_prior = quantity_residual / Q0   # only when Q0 > 0
```

If `Q0=100`, `S0=1,000`, `S1=1,100`, proportional scaling predicts `Q1=110` and the residual is zero. If observed `Q1=115`, the residual is five shares. That five-share residual could arise from a discretionary trade, a non-pro-rata creation basket, an index rebalance, an in-kind adjustment or a data/corporate-action discrepancy. The calculation is exact conditional on its inputs; the causal label is not identified by the equation. [R12](SOURCE_REGISTER.md#r12)

For a vehicle, `NAV × ΔS` can be a **net issuance value approximation** under a stated valuation convention. It is not necessarily actual cash received, gross creation volume or AP purchases of a particular constituent. AUM change combines returns, distributions, currency and issuance; substituting it for net investor flows without adjustment is invalid. A price-adjusted weight residual is yet another measure and must not be described as the same object as a true-S quantity residual.

The same formula does not apply to a 13F manager: there is no common fund-share denominator for an aggregate discretion book. Fund-class shares also cannot be scaled against consolidated portfolio holdings without an evidenced aggregation basis. Split adjustment is required for both underlying security and vehicle units. Zero or missing `S0` produces typed unavailability, not infinity or a zero signal.

### F3. Concentration and denominator discipline

For a deduplicated, comparable, same-plane set of observed holders `H`, with quantities `q_h` and qualified issuer-class shares `O`:

```text
covered_shares = sum(q_h for h in H)
covered_fraction = covered_shares / O
covered_holder_hhi = sum((q_h / covered_shares)**2 for h in H)
issuer_fraction_square_sum = sum((q_h / O)**2 for h in H)
top_k_issuer_fraction = sum(k largest q_h) / O
```

`covered_holder_hhi` describes concentration **inside the observed subset**. `issuer_fraction_square_sum` is the observed holders' contribution on an issuer denominator. They are not interchangeable. Unobserved holders are not zero; the full-market HHI is unknown. Do not report coverage above 100% as a usable concentration estimate or automatically cap it to hide double counting. Investigate overlap, stock lending/reported discretion, dates, classes and denominator semantics first.

A beneficial owner's legal fraction can require a different denominator because of acquisition rights. Store its reported percentage and basis separately; do not “correct” it with the latest issuer share count or combine such percentages across parties as if they were disjoint common shares. [R16](SOURCE_REGISTER.md#r16)

A true fragility model additionally needs the volatility and covariance of owners' liquidity demand. A simple holder count, HHI or days-to-exit scenario is not that model. Deferring a covariance model when historical flows are inadequate is preferable to presenting a precise-looking proxy as observed fragility. [R30](SOURCE_REGISTER.md#r30)

### F4. What the finished evidence card should make visible

A future existing-company-context card should state the legal plane, original reporting entity, resolved complex/vehicle where supported, economic date, public and operational availability, snapshot age, comparable coverage, exact measure and denominator, source generation, amendment indicator and allowed interpretation. A concise contradiction line should identify missing prior filings, incomplete public coverage, denominator changes, alternative mechanical explanations or inconsistent source planes.

Example, entirely synthetic: **“Two comparable filings show 100 to 120 reported common shares as of March 31 and June 30. The later filing became public August 14 and usable by this system August 15. This is a delayed disclosed-position increase, not evidence of buying today. One related filer is excluded because shared discretion is unresolved.”** This is more useful than a sponsorship score because the user can see what is known and what would overturn it.

## G. Mastermind integration and LLM boundary

### G1. Producer → owner → evidence → consumer

| Producer | Canonical artifact/data owner | Reference/measure plane | Consumer and boundary |
|---|---|---|---|
| SEC 13F discovery/raw evidence | Macro institutional census and immutable catalog | K1 raw/catalog refs → K2-C selected rows | Existing company context / ownership workspace; no new collector |
| SEC 13D/G | Existing beneficial-ownership acquisition/engine | Party/group/item source facts → compatible K1 references | Ownership event wire and company research; purpose is evidence, not buy authority |
| SEC insider filings | Existing insider owner | Transaction-line references; separate insider family | Existing insider context / research desk; no P-only market-purchase claim |
| Public N-PORT | Later bounded adapter under the adopted fund/source owner | Portfolio series snapshot, release and amendment lineage | Vehicle map and fund research; no private-month reconstruction |
| Sponsor holdings and true-S observations | Existing holdings/fund-flow owner | Holdings and unit-state refs → K2 fund-flow calculation | Descriptive residual/issuance context; no constituent-flow claim |
| Stock/issuer reference and corporate actions | Existing Stock Identity / source owners | Effective and knowable mappings, class and unit basis | Every join and denominator calculation |
| Manager/filer/vehicle relationships | Existing K2 epochs and accepted bridges | Resolution, overlap, decision-mode and correction refs | Comparable cohorts and explanatory graph views |
| Research Vault / document extraction | Existing Macro vault and research-intelligence owners | Quoted/extracted source spans, not numeric source replacement | Narrative synthesis; licensed text remains subject to existing rights |
| Ownership observations | Existing research/experiment and ownership outcome owners | Frozen hypothesis/feature/receipt bindings | Forward evaluation and eventual separately approved evidence promotion |
| Qualified future evidence | Existing V3 owner, once built and accepted | Independent claims/receipts | Decision Snapshot only through its accepted interface; no preemptive V3 build |

Sources: [I09–I29](SOURCE_REGISTER.md). The graph does not write to portfolio state. The existing portfolio mutation authority stays unchanged. Legacy 13F readers should be assessed individually for semantic/lineage defects; this research does not silently disable or strengthen their current behavior.

### G2. Cheap LLMs: bounded extraction, not source truth

A low-cost model can propose entity aliases, classify Schedule 13D Item 4 language into a small source-backed taxonomy, identify amendment spans, summarize stated changes, or flag a sponsor-column interpretation for review. Require exact source spans, source generation, model/prompt version, a bounded output schema, confidence and abstention. Numeric fields must be copied from deterministic parsing or explicitly marked unverified extraction; all arithmetic is recomputed deterministically.

Evaluate extraction against a held-out human-reviewed set covering negation, disclaimers, joint groups, rescinded proposals and amendments. A model that confuses “may seek a board seat” with “has won a board seat” cannot publish an authoritative event. Model self-confidence is not a calibrated probability. Hosted processing of restricted research or person data requires the source owner's rights approval; a readable PDF is not a blanket training license.

### G3. Frontier LLMs: synthesis with a constrained evidence packet

Use a frontier model for an activist-case synthesis where multiple filings, company responses, capital structure and fundamentals genuinely conflict, or for explaining why a positioning interpretation changed. Supply deterministic facts and a dependency graph; require separation of disclosed facts, inferred mechanisms, competing explanations and falsifiers. It may suggest a hypothesis for a future registered experiment, not pick a winner by looking at outcomes.

No LLM may assign historical availability, repair missing positions by invention, merge identities autonomously, treat an ETF residual as proven intent, compute final quantities, author evaluation outcomes, choose portfolio weights or promote evidence authority. Prompt injection in filings/vendor documents is data, not instructions. The authoring report also creates no new orchestration lane or model budget.

## H. Empirical validation program

### H1. Separate four questions before any outcome access

**Contract validity:** does the observation mean what its label claims and reproduce the correct generation at the cutoff? **Context utility:** does it reduce analyst mistakes and make ownership changes explainable? **Risk information:** does it improve a prespecified volatility, liquidity or drawdown-risk forecast? **Return information:** does it add implementable predictive information after existing evidence, costs and disclosure latency? Passing one does not imply passing the others.

The existing ownership forward-ledger and experiment/evaluation owners must hold the research registration, outcome maturity and grading. No parallel backtest database or new authority state machine is recommended. The attached report's existing-horizon menu becomes a finite protocol below. The proposed registration is not executed by this research commission. [I08, I14, I30](SOURCE_REGISTER.md)

### H2. Proposed finite first research slate

Each row has one primary specification and horizon. Signs, transformations, exclusions, benchmark, costs and the exact outcome source must be frozen before its evaluation sample is opened. Additional specifications count as new trials, not harmless robustness tweaks.

| ID | Family / unit | Primary outcome and horizon | Required controls / main falsifier |
|---|---|---|---|
| H01 | Comparable 13F complex breadth; security × available filing/cohort event | Incremental rank association with 60-session forward residual return | Price momentum, size, sector, liquidity, volatility, value/quality where PIT; disappears under correct availability or fixed cohort |
| H02 | Ownership concentration; security × qualifying snapshot update | Improvement in 20-session realized-volatility forecast | Existing volatility/liquidity/index controls; fails when denominator/overlap corrected |
| H03 | Source-classified 13D purpose event; security × campaign event | 20-session return after executable post-publication entry | Event/news/earnings and passive/control-category comparators; only pre-entry announcement jump explains effect |
| H04 | 13G major-holder change; security × party/regime event | 20-session residual return | Holder category, index/passive membership, denominator change; sign vanishes within category |
| H05 | Qualified insider purchase/sale cluster; security × event cluster | 20-session residual return | Existing insider baseline, role, plan disclosure, earnings proximity and price history; private/award transactions drive result |
| H06 | True-S non-pro-rata ETF quantity residual; security × synchronized vehicle observation | 5-session residual return | Raw holdings change, net issuance, momentum, passive/index rebalance and fund effects; custom-basket/mechanical cases dominate |
| H07 | Net fund-share issuance; fund × public observation | Improvement in forecasting the absolute fund premium/discount five sessions ahead | Current premium/discount, fund return, liquidity and lagged issuance; cannot survive distinction between net issuance and AUM change |
| H08 | N-PORT fund-holder breadth; security × public portfolio release | 60-session residual return | Same-sample 13F baseline, fund coverage, filing lag and corporate actions; nothing incremental after overlap/delay |

**Budget:** eight primary tests; at most two secondary horizon checks per primary (16 descriptive checks); at most two explicitly named exploratory interactions: H01 × H05 and H02 × H07 where lawful identity links exist. Total initial specification budget: **26**. The eight primary tests use Holm family-wise correction at a prespecified 5% level; the secondary and interaction results cannot justify promotion without a new sealed confirmation. This is a proposed scientific budget, not permission to run 26 experiments now.

The two interactions prevent an unnecessarily strong rule in the original report: useful conditional complementarity need not require each marginal feature to pass alone. But interaction search must be finite, preregistered and independently confirmed; it is not a back door to an opaque aggregate score.

### H3. Dataset and information-set construction

Build the study from immutable source generations, not a vendor's current view of the past. Every row must carry source family, legal plane, economic date, selected availability mode, source/identity/corporate-action generations and feature dependencies. Keep both the admitted cohort and excluded cohort with reasons. Join prices, outcomes and factors using the existing qualified PIT/security owners. Preserve delisted securities and historical eligibility rather than selecting today's ticker list or featured managers. [I08, I30](SOURCE_REGISTER.md)

Manager skill labels, roster selection, routine-insider classification, missingness imputation, normalization, winsorization and model tuning must be trained only on prior/training information. A current-map 13F research bench marked `point_in_time: false` cannot supply a historical selected-manager universe. The existing eight-retained-quarter readiness rule is a source-governance minimum, not proof of statistical power for every proposed study. [I09–I10](SOURCE_REGISTER.md)

Separate **incremental information** from **expanded coverage**. Compare baseline and augmented models on an identical eligible sample, then separately report the new names/dates reached by a source. Do not compare a complete baseline with a selectively observable augmented set and attribute the difference to alpha. Include missingness and reporting-lag diagnostics, but do not use future missingness as a feature.

### H4. Time, folds and implementability

Use purged, embargoed expanding-window evaluation; train only on observations whose labels have matured before the fold's fitting cutoff. The embargo must cover the maximum outcome overlap in that experiment, not an arbitrary fixed number copied across 5-, 20- and 60-session labels. Cluster or block inference by date/filing season and by related issuer/manager event where needed. Thousands of holdings from one filing batch are not thousands of independent shocks.

Before identifying a final historical holdout, the experiment owner must audit whether that period's outcomes or related hypotheses have already been inspected by adjacent projects. A historically old period cannot be called untouched merely because a new document says so. If an uncontaminated historical holdout cannot be established, historical evidence is exploratory and confirmation starts prospectively after the accepted registration cutoff.

For event studies, report both the market's announcement-window reaction and the **implementable** return from the first allowed entry after public/operational availability plus frozen processing latency. Use exchange calendars, time zones and the actual next tradable session. A same-day closing price before a late EDGAR acceptance is not an executable entry. Daily bars do not establish intraday fills. Record spread, slippage, turnover, price impact, delisting returns and shortability/borrow costs when the design requires shorts. A paper-only long strategy must not inherit an unimplementable long-short backtest result.

Historical public reconstruction and actual operational replay must be separate result panels. In a sensitivity panel, add explicit acquisition/processing delays and exclude the immediate announcement move. If the result exists only under zero-latency execution or optimistic quarter-end timing, it is not admissible as an operational edge.

### H5. Metrics, power and decision rules

Report sample size at the independent event/date level, eligible coverage, exclusion reasons, source/identity completeness, lag distributions, missingness by era and correction incidence. For return features use out-of-sample rank IC, bucket monotonicity, calibrated directional probability if modeled, incremental residual fit and costed portfolio diagnostics. For risk features use a proper forecast loss such as QLIKE or a frozen calibration criterion rather than requiring positive alpha. For context utility use a blinded, fixed set of ownership questions and measure factual-error rate, provenance retrieval and correction handling against the incumbent interface.

Before outcome access, use training-only or synthetic/block-resampled noise to estimate the minimum detectable effect at the chosen error/power target. The experiment owner must specify an economically material effect floor tied to intended turnover and conservative costs. If the available sample cannot resolve that floor with adequate power, the correct result is `INSUFFICIENT_EVIDENCE`, not a relaxed significance rule or a larger post-hoc horizon menu. Do not invent a universal “500 events is enough” threshold.

**Promotion requires all of:** admitted rights and temporal lineage; no unresolved semantic blocker; improvement on the prespecified primary criterion after the fixed multiplicity policy; stability in predeclared eras/cohorts; implementation-aware cost/latency survival; and a separately accepted consumer use. A feature may remain descriptive even after a null predictive result. Neither an interesting p-value nor a green parser test grants portfolio authority.

### H6. Negative controls and adversarial tests

Require publication-shift placebos, shuffled manager identities within lawful cohorts, duplicated-vendor observations, deliberately late amendments, tomorrow's identity map and unfiled incoming reporters. The harness should refuse leaked fixtures, not merely obtain lower returns. Verify that missing N-PORT months, proxy S values, Form 4 private purchases and mixed beneficial/13F shares cannot enter the wrong feature family.

The [validation specification](VALIDATION_SPEC.md) defines 60 discriminating contract cases plus worked algebraic examples. These are acceptance requirements for the future implementer; this report does not claim those production tests have been run. The current publication validation checks document structure, reference closure, source-manifest integrity and illustrative arithmetic only.

## I. Risks, failure modes and kill criteria

| Risk | Why it can create a convincing false result | Required response / kill criterion |
|---|---|---|
| Public versus operational clock collapse | Backfills appear to have existed in production years earlier | Separate replay modes; reject any operational track-record claim without actual retained generations |
| Snapshot-as-interval or trade inference | A delayed disclosed position becomes a fabricated current holding or trade tape | Preserve snapshot age and inference label; reject current-flow language |
| Missing-as-zero | Unfiled, omitted or confidential positions become imaginary sales | Typed missingness; no exit without stronger evidence |
| Legal-plane overlap | Parent filer, fund vehicle, insider and joint owner inflate shares/breadth | No cross-plane sum; resolve overlaps or withhold aggregate |
| Value-unit and class errors | Thousand/dollar, ADR, split or class changes manufacture conviction | Source-version and corporate-action binding; unresolved values excluded |
| Latest-corrected history | Later amendments or vendor repairs improve old predictions | Immutable source/parse/delivery lineage and replay of the original information set |
| Survivorship and skill selection | Today's successful managers are backtested as a historical roster | PIT eligibility and training-only selection; kill if present-day roster explains the edge |
| ETF causal overclaim | A residual is called active buying despite baskets or non-trade changes | Retain descriptive residual; require independent transaction evidence for intent labels |
| N-PORT regime confusion | Future monthly public data or private months appear in a 2026 study | Versioned publication regime; reject nonpublic observations |
| Form 4 misclassification and 2026 coverage shift | Awards/private trades or newly covered foreign officers look like alpha | Transaction/role/regime/plan semantics; era-appropriate denominator |
| Correlated confirmations | One filing reaches several UI/LLM paths as independent votes | Source/event dependency graph plus empirical dependence analysis |
| Repeated outcome search | Many horizons/managers create a selected winner | Finite trial budget, exposure audit and sealed confirmation |
| Rights and lock-in | A usable feature cannot lawfully retain or display its evidence | Rights gate before ingestion/use; reject provenance-stripping licenses |
| Observability theater | A refreshed document is mistaken for a healthy live source | Measure native source publication/backlog/generation health through existing owner |
| Infrastructure without consumption | A graph is built but no analyst can answer a company question | First wave must prove an existing read-only consumer path, not just schemas |

**Economic kill:** demote predictive use when the effect disappears with realistic availability, common-sample controls, corrected overlap, costs or out-of-sample testing; when a handful of securities or one filing season dominate; or when an equivalent public source provides the same information at lower total rights/operating cost. Do not keep an expensive family solely because the graph looks sophisticated.

**Architectural kill:** reject a second 13F truth, a new house identity island, a rival evaluation/health ledger, unapproved source scraping, unlicensed corpus duplication, a universal “smart-money score” or any direct source-to-portfolio mutation. Retain existing owners even when a source adapter needs a repair.

## J. Build priority

These are recommendations within the company's current priority/authority process, not a new autonomous backlog or change to strategic state.

| Priority | Bounded outcome | Why this order |
|---|---|---|
| **P0** | Reconcile this report with K1/K2-B/K2-C and existing source custody | The original greenfield contract plan would duplicate working foundations |
| **P0** | One exact 13F owner-read → existing company-context projection, with cutoff and missingness proof | Proves useful consumption before adding sources |
| **P0** | Identify and bound legacy false-flow/P-only/duplicate-source interpretations | Prevents stronger-looking but false intelligence; no unreviewed live change |
| **P0** | Native health/readiness and research-mode labeling | Static-document freshness is not source health; public reconstruction is not actual operation |
| **P1** | Source-native Form 4 and D/G semantic adapters, including amendment and 2026 regime fixtures | Higher-resolution disclosure semantics with existing acquisition owners |
| **P1** | Lawful prospective true-S/sponsor capture and public N-PORT vehicle mapping | Fills genuinely missing inputs; no invented past sponsor archive |
| **P1** | Descriptive concentration and explicit overlap/denominator context | Useful risk information even without return-predictive success |
| **P1** | Register and run the finite validation slate when data gates clear | Determines incremental value rather than assuming it |
| **P2** | Commercial normalization/history/identity bakeoff | Buy measured missing capability, not another copy of public filings |
| **P2** | Global extensions and flow-covariance/fragility research | Only after jurisdictional rights, taxonomy and historical inputs qualify |
| **Defer** | Intraday AP/constituent-demand reconstruction and manager-skill forecasting | Hard identification and entitlement problems; no prerequisite to the first useful product |
| **Defer** | V3 integration until its owner is built and accepted | Avoid preempting the portfolio program; existing context consumers can improve sooner |
| **Reject** | New universal 13F collector, opaque sponsorship score, current-only reconstructed backtest, mixed legal ownership sum, automatic portfolio authority | Duplicate, misleading or outside authority |

## K. Proposed implementation phases

### K0 — Accept the research and freeze compatibility

Re-pin then-current protected Mastermind and current canonical Macro/Terminal identities; reconcile relevant PRs and material contract changes only. Adopt the incumbent source/identity/evidence/evaluation/consumer map. Review the audit findings as proposed semantic changes, not already accepted runtime law. Freeze the first wave's exact files, evidence fixtures, consumer and non-goals. No production purchase, ingest or outcome access follows merely from accepting this document.

**Exit:** signed scope/owner map, exact compatibility differences, permitted source reads, denied operations and a finite acceptance checklist. If the existing K2-C cannot support the slice, return its exact missing interface rather than creating an alternative.

### K1 — Existing-source read-only vertical slice

Use K2-C on immutable 13F owner generations, including one comparable positive case and all relevant negative cases. Bind to the existing company-context projection in a hermetic/read-only proof path. Show legal plane, economic/public/operational dates, coverage, source generation and non-flow interpretation. Add no collector, commercial source, scheduler, production artifact writer or outcome model.

**Exit:** exact owner readback, deterministic projection, negative/correction replay proof, zero write effects and a reviewer who can answer the specified company questions. Schema-only success is insufficient. This is the only implementation wave proposed for immediate separate commissioning in section L.

### K2 — Transaction and beneficial-ownership semantics

Under separate owner-approved commissions, extend incumbent Form 4 and D/G adapters with line/item-level amendment semantics, party/group overlap, source-backed purposes and legal-regime dates. Preserve original reported values and contradictory interpretations. Test foreign-issuer eligibility/exemptions and P/S private-trade classification. Avoid a new source truth where current acquisition already exists.

**Exit:** rights-cleared, cutoff-valid native records and one narrow existing consumer for each admitted source; no trading authority.

### K3 — Missing vehicle data and prospective capture

Qualify public N-PORT cadence and fund series/class relationships, then admit a bounded panel. Qualify sponsor publication/correction/rights behavior and true fund shares outstanding for a small defined product set. Preserve missing days and late corrections. Reconcile holdings and trade notifications where permitted, without treating either as a comprehensive execution record.

**Exit:** source coverage and latency measured, actual retention proven, true-S versus proxy states separate, fund/portfolio basis reconciled. No unverified sponsor history backfill.

### K4 — Registered research and shadow evaluation

Freeze the H01–H08 slate through the existing experiment owner after data/exposure gates. Complete the mechanical replay tests before outcome access. Run historical/public-opportunity and operational/prospective panels separately. Grade using the existing outcome owners; retain nulls and documented exclusions. Context utility can be accepted independently of return prediction.

**Exit:** complete registered results, trial accounting, cost/latency sensitivity and a narrow proposed consumer authority. A separate approval is still required to integrate a predictive feature or change portfolio behavior.

### K5 — Optional vendor/global extension and eventual V3 consumption

Commission an evidence-backed vendor bakeoff only for a known missing history/identity/latency delta. Global expansion must first qualify each legal disclosure regime rather than assume US rules. Feed a future V3 Decision Snapshot only when its accepted owner interface exists; do not build V3 under an ownership commission.

**Exit:** incremental-value and rights/exit-cost decision, or an explicit defer/reject result. No procurement or authority change is automatic.

**Dependency order:** K0 → K1; K2/K3 may proceed independently after their own owner/rights gates; K4 depends on the admitted data for each hypothesis, not on every family being complete; K5 is optional. The company does not need a fully populated global graph before delivering a truthful company-context improvement.

## L. Exact bounded follow-on implementation commission

> **Proposed only — not issued or executed by this research report.** Acceptance must name the implementation owner and the current governing contracts. This commission intentionally replaces the attached report's oversized “foundation” wave, which bundled new N-PORT acquisition, identity, concentration, flows, observability and broad integration.

### Title

**C10-W1 — Prove the existing 13F owner-read path in an existing company-context projection, without new source or portfolio authority.**

### Required outcome

For one specified company/security and a bounded set of immutable previous/current 13F owner generations, produce a read-only evidence projection that answers: who disclosed the position; which legal plane it belongs to; its economic date; when it became public and operationally usable; what comparable quantity changed; what coverage/overlap is unresolved; and why this is not real-time flow. The same path must refuse or downgrade the negative fixtures below. Deliver the projection through an existing company-context interface or a hermetic fixture of that interface, not through a new product/store.

### Start and source-law gate

Follow the then-current Mastermind bootstrap. Pin protected Mastermind plus actual Macro and Terminal source identities; load required skills atomically. Reconcile the live owner/PR/collision state for K1, K2-B, K2-C, institutional census and company context. Use one lawful source-custody workspace. Record pickup/start through the assigned carrier where required. A historical branch label is not a current writer lease.

Name exact read principals, immutable catalog/receipt identities, consumer fixture and allowed changed paths before edits. If permissions, native generations or the current accepted contract are unavailable, return the exact missing gate and complete only independent hermetic work. Do not obtain broader credentials, dispatch production ingestion or route around a denial.

### Mandatory reuse

Reuse `engine/institutional_census/`, accepted K1 EvidenceRef validation, K2 manager/filer/vehicle epochs and `lib/institutional_13f_adapter.py`. Preserve owner-native CUSIP and typed unresolved Data OS identity. Reuse `engine/company_institutional_context/` as the first consumer boundary. Existing source receipts and immutable canonical JSON remain truth; no second 13F or identity store is permitted.

### Allowed work

Implement only the minimum additive read adapter/projection and tests required for this slice. Expose the source's legal plane, exact period/clock/row bindings, selected generation, comparable quantity, coverage, source-reference digest and a non-flow interpretation. Preserve existing field compatibility or obtain owner approval for an additive contract revision. Reuse native missingness/rights/authority states; do not introduce a parallel envelope that weakens them.

Public-opportunity reconstruction can be described in fixtures, but **operational K2-C behavior must retain its existing actual-retention and catalog-publication checks**. No backdated operational clock is allowed. Numeric demonstrations may be synthetic only when explicitly labeled; any claimed real company projection must read the declared canonical rows.

### Discriminating acceptance tests

Pass the relevant cases T01–T30 and T55–T60 in [VALIDATION_SPEC.md](VALIDATION_SPEC.md), including:

- a quarter-end snapshot is unusable before public availability and, operationally, before all actual raw/catalog/derived dependencies;
- the previous and current rows bind to exact raw receipts and catalog generations; a raw receipt alone cannot claim a security quantity;
- missing predecessor, unfiled incoming manager, notice-only, optional omission/confidentiality and unresolved shared discretion do not become zero or confirmed selling;
- additional-holdings and restatement amendments preserve the prior information set and select the correct later composition;
- value units, security class, corporate actions and row ambiguity cannot manufacture a comparable change;
- duplicated SEC/vendor copies cannot become extra independent confirmation;
- current identities or later parser corrections cannot silently improve a historical operational replay;
- the projection uses the incumbent company-context boundary, retains typed degraded states and never exposes prohibited underlying payloads;
- every new authority boolean remains false, no portfolio state changes, no scheduled job or source publication is created.

Record exact test commands, results, candidate head, selected source hashes and changed-file set. Independent review must distinguish hermetic contract proof, real owner-read proof and production/browser proof. Do not claim the latter where it was not commissioned or executed.

### Explicit exclusions

No new N-PORT collector, sponsor capture, ETF residual engine, Form 4/D-G source adapter, manager-skill model, empirical market-outcome run, new experiment/outcome/health ledger, vendor purchase, broad identity migration, production deployment, V3 implementation, ranking change, portfolio sizing/gating, or trading integration. Do not expand the featured roster into the census population. Do not edit CI or unrelated pipelines merely to keep work moving.

### Required return

Return one scoped PR with source-law pins and compatibility map; actual owner-read receipts or explicitly labeled hermetic-only limitation; the deterministic consumer projection and negative fixtures; exact test results and an authority/no-write effect statement; unresolved gaps with named owners; and an implementation closeout explaining what became true and what remains `BUILT_NOT_PROVEN`. The first reviewer should be able to reproduce the quantity and cutoff from the cited owner references without relying on the author's narrative.

**Stop at this read-only slice.** K2–K5, outcome access, production deployment, vendor procurement and evidence promotion each require a separate accepted commission. This research package does not execute or pre-authorize them.
