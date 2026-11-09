# Bitemporal Data, Corrections & Point-in-Time Truth
## Commission 5 — hardened research, current-source audit, and owner-native build recommendation

**Research revision:** R2, 2026-10-04. **Existing carrier:** [Mastermind PR #1221][R00].

**Authority boundary:** This is a completed research recommendation, not an implementation authorization, protected architectural law, production certification, vendor order, or investment recommendation. No production source, pipeline, dataset, account, trading behavior, deployment, or data-source authority is changed by this report. Section L is a proposed subsequent commission and has **not** been executed.

**Replacement scope:** Replace the report at this same path on PR #1221. The previous report remains recoverable at commit `01fc1846471e482a4d68842ad53c6294478001e2`; its SHA-256 is `918dcd055a3d54009c2b3a952d32818869d43064aed98002b8326903d63d576f`. This revision preserves the no-new-warehouse conclusion but supersedes the old current-state census, temporal qualification, acceptance criteria, and implementation sequence. Existing owner contracts and accepted source law are not superseded.

### Evidence cut and method

| Estate | Resolved repository / branch | Immutable audit pin | What this pin establishes |
|---|---|---|---|
| Mastermind | `mastermindx-market-intelligence/Mastermind`, protected `master` | `521720b09be2921e996d9396b522b1c4ca62041c` | Governing procedure and inspected source/specification |
| Macro | `mastermindx-market-intelligence/macro`, `main` | `617c5818b0493e1843c652be881f72cbebfac123` | Inspected producer, temporal, and financial-research source; not a deployed generation |
| Terminal | `mastermindx-market-intelligence/mastermind-terminal`, `master` | `1c708450187755160e1a5889b69598a2fcb1f0d1` | Inspected Company Intelligence server boundary |
| Executive DR vault | `mastermindx-market-intelligence/executive-dr-vault`, `main` | `ea422c92bd29800d1f7fb3ae850236cc44d8c890` | Repository identity only; not the identity of every Research Vault product or local checkout |

The four heads were resolved through authenticated repository metadata on 2026-10-04. The commissioning reference `d1594f3c7ae750db3f14b4eebf0de3460f84267a` and the previous report's pins are historical, not current authority. The same-pin `INDEX`, `COLD_START`, `ACTIVE_EXECUTION`, `SESSION_RELIABILITY`, `REVIEW_RETURN`, `WEB_CEO_DELEGATION`, and `CLOSEOUT` procedures were consumed; Skillpack `mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap major 1. [R01]

This is a **targeted, evidence-bounded recensus**, not an exhaustive filesystem or production audit. Exact source files, existing architecture, selected PR metadata/file inventories, public primary documentation, and seven synthetic characterization cases were examined. Materialized Parquet stores, licensed vendor samples, deployment bindings, every consumer, and real investment outcomes were not certified. Two broader/detailed source-read requests were refused before execution; they were not retried through alternate carriers. In particular, the draft S0 implementation's presence is established by its PR file inventory, not a fresh implementation test or full module review. These limits are kept separate from actual observed defects.

Repository citations refer to immutable source. Public documentation was reviewed on 2026-10-04; public vendor descriptions remain vendor claims until an authorized sample and contract qualify them. Recommendations and synthetic examples below are proposed design, not claims about installed behavior.

---

# A. Executive conclusion

## A1. Decision

**Build a small, enforceable temporal interoperability boundary over the existing owners, beginning with one financial-evidence-to-consumer qualification slice. Do not build another temporal warehouse.**

The strategic value is high: a system cannot establish whether evidence adds predictive information when its historical features contain later revisions, its entity mappings come from the future, or its “decision replay” reads today's mutable files. Temporal integrity is a prerequisite for credible expectation, fundamental, positioning, and portfolio research. It is not itself an alpha signal and should not receive an opaque truth score or portfolio weight.

The estate is not starting from zero. Macro has a generic temporal helper, FRED release/vintage paths, prospective revisions, membership history, and a substantially richer Calcbench/Fundamental Forensics temporal design. Mastermind has existing historical consumers and signal archives, a protected Portfolio V3 source-receipt design, and an **unmerged S0 implementation in PR #673**. The opportunity is to qualify these different guarantees and connect them without copying their authority. [R02], [R03], [R04], [R05], [R06], [R07], [R08], [R09]

The original plan was too reassuring in three places. A 120-day availability proxy does not recover an overwritten filing vintage. A helper that filters a timestamp does not select the correct version, validate the complete source, or prove actual system possession. A field called `published_at` can mean source publication in one owner and publication of a derived result in another. These are architectural correctness issues, not naming cleanup.

## A2. The promise must be precise

Mastermind should be able to answer four different questions without substituting one for another:

1. **Recorded decision:** What exact artifact did the system actually emit at that time?
2. **Operational knowledge:** What source versions, mappings, and validated inputs could the specified Mastermind consumer actually use then?
3. **Historical market reconstruction:** What could a participant with the declared source/channel have known then, according to evidence reconstructed now?
4. **Latest revised analysis:** What does today's corrected database say about that earlier period?

The fourth is useful diagnostics; it is not the first three. Reconstructing an earlier market information set today is legitimate when its evidence and historical channel assumptions are explicit, but it must never claim that Mastermind possessed those bytes at the historical decision.

The enforceable guarantee is therefore conditional: **every admitted input must have sufficient evidence for its declared replay mode, source channel, cutoff, identity, revision policy, and rights scope; otherwise the consumer must expose a typed refusal or bounded partial result.** There is no honest universal guarantee about unknown publication times or archives that were never retained.

## A3. First recommendation and stopping point

Accept this report as a recommendation for a **C5-P0 qualification slice**, not a company-wide rewrite. The later owner should reconcile the incumbent financial-query and Portfolio S0 carriers, freeze the clock mapping, and prove one immutable financial response entering the existing source-receipt/snapshot boundary. It must demonstrate positive availability, late arrival, correction, withdrawal, unknown-clock refusal, and unchanged earlier replay. It must not reconstruct the whole S0 program or acquire institutional history as a prerequisite.

The later rollout proceeds family by family. Temporal correctness gates come before predictive research; actual production promotion remains with existing source, consumer, rights, and release owners. A reduction in apparent backtest performance after removing leakage is a successful integrity result, not a reason to weaken the rules.

---

# B. Current-state census and hardening audit

## B1. What is present, and what is not proved

`BUILT_NOT_PROVEN` means executable source or an implementation candidate exists without a fresh production-path proof in this audit. `PARTIAL` means the observed behavior solves only part of the required guarantee. `SPEC_ONLY` applies to a specification on its inspected branch; it must not erase an implementation on another branch.

| Capability / owner | Current evidence | Classification | Material qualification |
|---|---|---|---|
| Annual fundamentals consumption, Mastermind | `loop/fundamentals.py`, especially loader and `_pit_row` | PARTIAL | Filters `asof_date <= t`; does not authenticate that date as original publication or preserve missing upstream vintages. Its source is Macro's modeled annual panel. [R02] |
| Annual EDGAR modeled panel, Macro | `collectors/edgar.py` | PARTIAL | Builds `asof_date = period_end + reporting_lag_days`, default 120 days. This is a model assumption, not evidence of availability for each selected value. [R03] |
| Annual normalized statements, Macro | `collectors/edgar_facts.py::_annual`, `_statements_for` | PARTIAL; unsuitable as authoritative historical vintages | Latest-filed selection collapses earlier occurrences into fiscal-year values and returns period ends. A period-end/future-period guard does not restore discarded filing chronology. [R04] |
| Quarterly statements | Described in the existing temporal standard as carrying `filed` | PARTIAL / detailed producer and store not recertified | A date-valued `filed` column is stronger than a fixed lag, but does not alone prove intraday publication, accession-coherent metrics, or retained revisions. [R05] |
| Generic temporal vocabulary and helper, Macro Data OS | `lib/dataos/temporal.py`, read in full and exercised synthetically | BUILT_NOT_PROVEN / PARTIAL | Rejects naive timestamps and non-PIT-readable profiles; its filter does not enforce all declared fields, choose a winning revision, or distinguish public availability from own ingestion. [R06] |
| Initial macro release path | `collectors/fred.py` | BUILT_NOT_PROVEN / PARTIAL | Default vintage collection uses `output_type=4`, initial releases. This is not the complete sequence of values known after later revisions. A separate all-vintages helper also exists. [R07] |
| Macro release-basis router | `engine/pit.py` | PARTIAL | Distinguishes vintage/calendar/reference provenance; non-vintaged release paths can shift latest values by modeled lags. The label `release` alone is not strict-PIT certification. [R08] |
| Calcbench/Fundamental Forensics temporal architecture | Protected Wave 3A docket; raw-ledger source artifact located | BUILT_NOT_PROVEN at declared docket scope | Existing five clocks, typed periods, revision events, governed mappings, cutoff-visible receipts, and source/system cutoff distinction must be reused. Historical docket tests are not fresh tests in this audit. [R09] |
| Financial-query service | Current source search locates `engine/fundamental_forensics/query_service.py` and response/request schemas | Source presence confirmed; detailed service review not completed | Do not infer production issuer service or complete ledger-selection proof from a schema or golden fixture. [R10] |
| Portfolio V3 architecture / S0 plan | Protected design and plan; #658 merged | SPEC_ONLY on protected design surface | Existing closed receipt, immutable snapshot, read-only account boundary, size limits, and no-new-ledger rules remain controlling. [R11], [R12], [R13] |
| Portfolio S0 implementation | #673 open/draft, 16 changed files including source, contract, adapter, API, and tests | Unmerged implementation candidate / BUILT_NOT_PROVEN | Corrects the previous report's estate-wide “spec only” implication. No new S0 project should be started over it. [R14] |
| Signal first-seen archive, Mastermind | `brain/signal_history.py` | BUILT_NOT_PROVEN / PARTIAL | KEEP-FIRST per `(asof, ticker)` provides a useful daily archive; not every intraday decision, complete raw-source lineage, or cross-owner atomic snapshot. [R15] |
| Historical membership consumer | `loop/single_name_panel.py` | BUILT_NOT_PROVEN / PARTIAL | Applies `start <= t < end`. Effective membership alone does not prove that the membership or its classification was known then. [R16] |
| S&P 400/600 reconstruction | `scripts/midsmall_pit.py`; prior census and current source retained | Source reconstruction, not official-feed certification | Do not equate reconstructed changes with licensed complete history. No current on-disk completeness measurement was performed. [R17] |
| New historical-leaver sector work | Macro #8403 is merged | Merged substrate; coverage not recertified | Its existence invalidates a claim that no such work exists; it does not establish complete era-correct sector labels or outcome coverage. [R18] |
| Prospective estimate observations | `collectors/equity_revisions.py` | BUILT_NOT_PROVEN / PARTIAL | Real observation/session/lineage fields and anti-backdating guard exist. Source effective/publication fields are null in the inspected observation construction; historical provider availability is not thereby proved. [R19] |
| Existing earnings-expectation consumer | `portfolio/held_risk.py::_lane_earnings_expectation` | BUILT_NOT_PROVEN | SUE and revision context already have a consumer. A temporal qualification must feed that owner, not create a competing earnings-risk lane. [R20] |
| Research desk / themes / portfolio evidence | Existing starting-point files and protected V3 design | Existing adjacent architecture; not exhaustively recertified | The commission is temporal integrity, not a re-ranking or replacement of those products. See B4. [R21], [R22], [R23], [R24] |
| Terminal Company Intelligence boundary | `terminal/app/api/company-intelligence/[symbol]/route.ts` | BUILT_NOT_PROVEN | Existing server-side resolution, normalization, no-store response, and typed error paths. This read does not prove complete consumer PIT enforcement or authorize a new browser fetch path. [R25] |
| Research Vault product | Macro `engine/research_vault/__init__.py` | Code owner resolved; runtime unproved | Existing private-source ingestion/catalog/search namespace is in Macro and is display-tier. The Executive DR vault is not automatically the same product. [R26] |
| Generated Mastermind census | `data/census/CENSUS.md` | Stale inventory evidence | Still reports generation at `2026-07-16T23:46:57.358909+00:00`, commit `131290a`. Counts are not current operational proof. [R27] |

The `.gitmodules` file resolves `vendor/macro` to the actual Macro repository, but that is not proof that a running Mastermind process uses the latest Macro main or the same materialized dataset generation. Later production qualification must bind deployed code, the actual submodule/local binding, source artifacts, and consumer receipt together. [R28]

## B2. Concrete findings and dispositions

| ID | Finding in the previous recommendation or observed substrate | Severity for the proposed guarantee | R2 disposition |
|---|---|---|---|
| F01 | Annual +120-day proxy described as safely conservative PIT | BLOCKER | Reclassify as modeled sensitivity input only unless exact value-vintage and availability evidence qualify it. Section E gives a counterexample. |
| F02 | Timestamp filter treated as a complete temporal read | BLOCKER | Separate eligibility, graph/version selection, state validation, dependency closure, and consumer readiness. Preserve the helper's limited positive guarantees. |
| F03 | `published_at` means source publication in Data OS but result publication in the Calcbench mapping | BLOCKER | Owner-specific semantic mapping; no global rename or field-name coalescing. |
| F04 | Own-system replay can admit a publicly dated record ingested later | BLOCKER | Explicit replay modes and scoped durable/consumer-ready boundaries. |
| F05 | S0 implementation overlooked | MAJOR | Reconcile #673; preserve its source custody and closed v1 contract. |
| F06 | Initial-release FRED history conflated with all historical vintages | MAJOR | Freeze version-selection policy; first print and latest known at cutoff are different valid experiments. |
| F07 | Filing date/acceptance treated as public dissemination time | BLOCKER for exact intraday claims | Preserve the native acceptance field, separately qualify publication/channel availability and timestamp precision. |
| F08 | Corrections treated as a single latest-row problem | BLOCKER | Preserve lineage, correction evidence clocks, withdrawal, conflict, and out-of-order arrival semantics. |
| F09 | Hash or receipt treated as proof of selection completeness | MAJOR | Require a cutoff-visible inventory/ledger witness; selected-value consistency alone is weaker. |
| F10 | Uncertain/date-only timestamps lack a safe boundary rule | BLOCKER for fine-grained replay | Carry bounded time evidence; do not invent midnight availability. |
| F11 | One end-to-end fixture proposed as sufficient acceptance | MAJOR | Forty specified adversarial cases, positive controls, mutation requirements, and a genuine same-generation consumer proof. |
| F12 | Public API availability assumed to imply broad AI/commercial/retention rights | BLOCKER for new use | Current FRED terms and per-source agreements require a rights-owner determination; no data authority is granted here. |
| F13 | Future entity mappings, universe membership, or adjustment vintages can contaminate otherwise-PIT features | BLOCKER | Include these dependencies in the cutoff-visible input graph and distinguish event knowledge from effective applicability. |
| F14 | Missing rows/failed observations become neutral values | MAJOR | Preserve typed missingness and expected-denominator evidence; test the zero-versus-missing distinction. |
| F15 | Broad parallel P0 across all families competes with existing owners | MAJOR | One bounded financial-response/receipt slice first; other families follow separate owner admissions. |
| F16 | Source-built and source-merged status used as live proof | MAJOR | Explicit source/runtime/rights/consumer proof boundaries throughout. |
| F17 | Current-rule or current-LLM recomputation mislabeled historical intelligence | MAJOR | Record rule/model/corpus availability and label reconstruction; literal replay returns stored outputs. |
| F18 | Physical time-travel assumed to retain old data indefinitely | MAJOR | Storage-neutral retention and restore obligations; history deletion must produce explicit unreplayability, not invented recovery. |

These findings change the recommendation. They do not assert that every current production decision is contaminated or that the magnitude of past bias has been measured. That would require actual artifact generations, historical cutoffs, and consumer-path evidence.

## B3. Discriminating evidence actually executed

Seven hermetic cases exercised the **unchanged** `lib/dataos/temporal.py` at the Macro audit pin. No network, market records, production state, model, or backtest was used. The code file SHA-256 was `4415404186f0b0d2870f42d9e4a0b95be87937863adf30cf015ed34e8bf92b67`; the complete local characterization JSON SHA-256 was `b3d7305593e5e7468b5f8a9620af208578c951783c3c2a0094a84c42f055ab81`.

All cases used cutoff `2026-01-15T12:00:00Z`.

| Case | Submitted condition | Observed behavior | What it does and does not prove |
|---|---|---|---|
| C1 | Revisable row published Jan 1, ingested Feb 1 | Row returned | Publication wins the coalesce. It is not proof of operational possession by Jan 15. |
| C2 | Original Jan 1 and revision Jan 10 both before cutoff | Both returned | The helper filters, not selects one authoritative version. |
| C3 | Revisable row contains publication but lacks period, ingestion, and revision fields | Row returned | Profile metadata is not complete row-contract enforcement at this function. |
| C4 | Intelligence served Jan 1, expires Jan 2 | Row returned | Historical emission can still be replayed; this function alone does not certify current eligibility/freshness. |
| C5 | Publication Feb 1 | Empty result | Positive evidence that the publication cutoff is enforced. |
| C6 | Naive publication timestamp | `TemporalError` | Positive evidence that timezone ambiguity is rejected. |
| C7 | DERIVED profile | `PointInTimeError` | Positive evidence that a recomputable artifact is not silently treated as replayable. |

The interpretation matters: returning an expired historical emission is not inherently a replay bug; promoting it as fresh decision evidence would be. Similarly, returning all versions can be correct for a filter API. The defect is the **broader guarantee attributed to that helper**, not a demand to change its API silently. Appendix 1 includes the reproducible characterization recipe. The forty cases in H are future acceptance requirements and were not executed against a new implementation.

## B4. Existing and adjacent work: preserve custody

| Carrier | Observed state / head | Required relationship to Commission 5 |
|---|---|---|
| Mastermind #658 | Merged architecture/plan | Preserve its authority boundaries; this report does not reopen the Portfolio product design. [R13] |
| Mastermind #673 | OPEN/DRAFT, `0b960590c77101b3f3b5545896423f9ad07b7d56` | Existing S0 implementation owner; coordinate any receipt adaptation rather than building a replacement. [R14] |
| Macro #7518 | OPEN, `a58ef81168687ff6aedcb37ed0070dab05cdbe9b` | Cross-filing lineage candidate; no assumed merge, source lease, or authority to change lineage semantics. [R29] |
| Macro #8064 | OPEN, `2fcedafa46b30e5b0fb74b779f72f6116ad9a0ee` | Existing SRC-A1 revision-index work; preserve writer and pending effects. [R30] |
| Macro #8312 | OPEN/DRAFT, `69d8c407e7033b9aa1e2fb4699398b454d7864c2` | Information-to-Price source/evaluation adjacency; temporal qualification is a dependency, not a competing science project. [R31] |
| Macro #8403 | MERGED, `a9463933178b141b89ffbfc54742c7a7781d8f0f` | Consume the current historical-leaver substrate and its actual coverage limits, not old absence assumptions. [R18] |
| Mastermind #1224 | OPEN, `7cbb03a85cfa96b2a880c297b01fd1c8df3038d4` | Adjacent observability research proposes read receipts and health federation; reconcile to one consumer receipt owner. Proposal is not accepted law. [R32] |
| Mastermind #1223 | OPEN/DRAFT, `41b1230cdfe42f7d9e15920cde47449b6acef6cf` | Analyst revisions/subthemes source research; reuse its diligence, do not create a separate vendor bake-off. [R33] |

PR status is not live source-writer admission. The later implementer must perform one fresh exact-carrier, source-lease, pending-effect, and changed-path reconciliation before modifying any overlap. Historical authorship is not a perpetual lock; unknown or active effects cannot be cleared by this report. This research pass changes none of those carriers.

The original starting points `portfolio/lenses.py`, `brain/research_desk.py`, `brain/bottleneck.py`, the trend protocol, and the thematic framework remain relevant consumers or doctrine. [R35] Their presence and applicable architecture were recovered, but this targeted audit does not claim every path, study, regional dataset, or classification is temporally qualified. In particular, mature historical analyst revisions, effective-dated fine-grained subthemes, and individual-stock institutional flows remain **source-specific proof questions**, not universal claims of absence. [R21], [R22], [R23], [R24]

# C. State of the art and architectural choice

## C1. Bitemporal storage is necessary in some domains, but insufficient by itself

The useful database distinction is **valid time** (when a fact applies) versus **system/transaction time** (when that database records a version). XTDB documents this distinction directly. Financial research additionally needs source/channel availability and the consuming system's actual readiness. A database can preserve its own history accurately while containing a vendor's retrospectively revised history. [P01]

SQL Server's system-versioned tables illustrate a subtler boundary: documented system-time periods use the **transaction begin time**. That is not automatically the moment a downstream consumer could read the committed data. A transaction begun at 09:00 and committed at 09:12 must not, solely because its system-time start is 09:00, qualify an operational 09:05 decision. This is an application-level qualification requirement, not an assertion that the database's documented behavior is defective. [P02]

Similarly, physical time travel has retention limits. Delta's documented vacuum behavior can remove data files needed to read older versions. A table version or content hash without retained, authorized, restorable input bytes is not sufficient replay evidence. Storage retention, rights, and recovery must agree. [P03]

**Recommendation:** retain native storage choices. A small immutable owner manifest over Parquet/JSONL can be sufficient for a bounded research dataset; an existing relational ledger can serve correction-rich fact histories. Introduce a different database only after a measured native-owner limitation, not to make architecture diagrams uniform.

## C2. Financial vintages are an empirical concept, not just a schema feature

Croushore and Stark's real-time-data work establishes the relevance of vintage choice to macroeconomic analysis and forecasting. The Philadelphia Fed's current data service separates complete vintage histories from selected first/second/third releases. The question “what was the first print?” is not identical to “what did the latest available database show on date T?” [P04], [P05]

FRED/ALFRED makes a similar distinction in its API. Observation periods and real-time vintage periods differ; real-time intervals use inclusive dates, and observation output types distinguish all vintages, changed observations, and initial releases. An internal half-open timestamp model needs an explicit, precision-preserving adapter rather than silently interpreting a vintage date as midnight publication. [P06], [P07]

**Implication for Mastermind:** a first-release dataset can support a correctly defined first-release study, while being insufficient for a latest-known-vintage reconstruction. A release calendar plus today's revised values is neither. The source's native vintage policy must travel with the result.

## C3. An institution's “PIT product” is a specific delivered contract

A vendor's long historical coverage does not imply the same start date, frequency, granularity, correction policy, or methodology history for its PIT product.

FactSet's published PIT methodology describes daily local-market consensus snapshots, historical reconstruction beginning in December 2009, and a methodological break: earlier history uses a later methodology convention rather than reproducing every historical methodology choice. It also distinguishes research dates, input dates, and later quality-control changes. This older methodology document is useful evidence about a particular product design, not a current entitlement or universal FactSet service guarantee. It supports daily snapshot research, not automatic event-by-event intraday inference. [P08]

S&P's current Capital IQ Estimates page separately describes an Estimates Snapshot offering with two-hour snapshots, history beginning in August 2016, and effective/from-to fields. That cadence constrains what can be claimed within a snapshot interval. The broader Estimates product and the snapshot service must not be treated as interchangeable. [P09]

LSEG describes both general I/B/E/S history and separate PIT-oriented backtesting datasets. Its public materials distinguish coverage and delivery cadence; the long start dates of a broad estimates archive cannot be transferred to a specific PIT consensus or contributor-level extract without a sample. [P10], [P11]

**Recommendation:** compare source-channel-version tuples, not vendor brands. Do not choose a procurement winner in this commission.

## C4. Publication, receipt, and reconstruction are different observations

The SEC explicitly distinguishes EDGAR acceptance from first availability on its public website and does not publish a universal first-public-availability timestamp. Its API documentation also distinguishes submissions, extracted XBRL facts, and bulk files. Company Facts and frames are useful interfaces, but a current normalized endpoint is not an immutable historical delivery receipt. [P12], [P13]

A raw market-data feed provides another caution. Databento documents publisher event, receive, and output timestamps as different fields; some snapshot receive timestamps describe snapshot generation rather than the original historical receive event. The source profile must qualify the actual record type, flags, and channel. A promising column name is not sufficient. [P14], [P15]

These examples lead to a general engineering requirement: attach a **claim about a clock and its evidence**, not merely a timestamp. Exact public dissemination may remain unknown even when acceptance is exact. Actual own-system receipt may be exact even when original public publication is unknown. Neither should be fabricated to fill the other's column.

## C5. Alternatives and why the recommendation wins

| Alternative | Advantage | Failure or cost | Ruling |
|---|---|---|---|
| New enterprise bitemporal warehouse for all families | Uniform queries and centralized optimization | Duplicates mature owners, expands rights/retention exposure, encourages a second source-of-truth and migration before consumer proof | Reject as the default; reopen only for a measured constraint with owner approval |
| Rename all source timestamps to `known_at` | Superficially simple | Erases source-versus-system meaning, precision, availability basis, and semantic differences between producers | Reject |
| Keep every local convention with documentation only | Lowest initial engineering cost | Cannot enforce cross-family eligibility or prove consumer use; source labels can overclaim | Insufficient |
| Add one universal mandatory record with every possible clock | Easy conceptual completeness | Forces guessed timestamps, enormous null surfaces, unrelated schema changes, and false uniformity | Reject |
| Existing-owner profiles, native receipts, deterministic qualification, existing consumer snapshot | Preserves local expertise and custody; supports incremental proof and honest partial coverage | Requires explicit adapters and a conformance test suite; not a one-line universal query | Recommend |

The strongest counterargument is fragmentation: federation can leave ten subtly different implementations. The response is not another storage plane. It is a **shared conformance specification, one owner for each semantic adapter, and discriminating consumer tests**. Native producers keep their domain selection logic; cross-domain callers must not reimplement filing arbitration or macro-vintage selection from rows.

---

# D. Source landscape, delivery diligence, and rights

## D1. Comparison at the usable-product level

History below is product-specific evidence or explicitly unknown. No row asserts Mastermind currently holds a license, a delivered sample, or an approved right to train models. Cost classes are budgeting categories, not quotes.

| Source / exact family | Coverage | History | Latency / delivery | PIT quality | Corrections | Rights / unresolveds | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| SEC submissions, accession documents, XBRL APIs | US filing identities and financial facts | Endpoint-dependent filing history; older submissions may require additional files | JSON APIs and nightly bulk; not a guaranteed first-publication clock | Strong source chronology when exact accession and qualified availability are retained | Amendments and subsequent filings must retain original occurrences; current frames are not vintage archives | Public source access subject to fair-access requirements; private vendor enrichment/identifier rights do not become public | Public access plus engineering/storage | Filing evidence and a low-cost temporal qualification canary. [P12], [P13] |
| FRED/ALFRED real-time observations | Macro series supported by each endpoint | Series-specific vintages; not every series has equal history | API vintage/date queries; native date precision | Useful for declared first-release or vintage reconstruction, not automatic intraday publication | Native real-time periods/output types require explicit interpretation | **New use requires rights review**; current service and underlying-series terms must both be satisfied | No access charge for ordinary service; rights and operations remain material | Methodology comparison and admitted macro-vintage research. [P06], [P07], [P16] |
| Philadelphia Fed real-time datasets | Selected macroeconomic variables | Complete histories and selected release sequences, per variable | Downloadable research vintages; current page describes monthly updates | Strong for the provided research-vintage questions, not a live-release feed | Release/version selection explicit | Verify the dataset's applicable terms and attribution before the intended use | Public research access | Independent macro revision benchmark. [P05] |
| Eurostat vintage database | Selected principal indicators, not every Eurostat series | Indicator-specific monthly vintage history | Official description says archive vintages arrive roughly two months after initial release | Good retrospective vintage resource with an important archive-delay distinction | Vintage dimension and changed-observation representation | Source terms and redistribution/AI scope must be checked; access is not universal permission | Public access plus normalization | Test separation of historical release from later archival availability. [P17], [P18] |
| Bundesbank real-time database | Selected German macroeconomic time series | Series-specific; official material describes many histories from 2005, some earlier | Research real-time database rather than universally tick-timed releases | Potential comparative vintage source | Keep native vintage dimensions and changes in definitions | Dataset-specific rights and exact time semantics require admission | Public research access | Non-US robustness and temporal adapters. [P19] |
| LSEG I/B/E/S PIT / backtesting offering | Estimates/consensus and related financial histories, exact package dependent | Do not substitute broad I/B/E/S start dates for the contracted PIT extract | Public pages describe different update/delivery arrangements across datasets | Candidate; no delivered rows qualified here | Require correction, deletion, contributor, currency and fiscal-period treatment | Quote, historical entitlement assumptions, non-display, derived-data, retention and AI use all unresolved | Institutional quote / feed entitlement | Deep historical expectations after the incumbent bake-off and sample gate. [P10], [P11] |
| FactSet PIT consensus, documented methodology | Consensus snapshots; not necessarily broker-detail history | Methodology paper describes Dec 2009 onward | Daily local-market snapshot design in that document | Candidate for daily research; pre/post methodology regimes must be recorded | Preserve QA changes and input/research-date differences | Historical methodology is not the current order form; revalidate SKU, timezone, fields and rights | Institutional quote | Daily consensus reconstruction and vendor-comparison controls. [P08] |
| S&P Capital IQ Estimates Snapshot | Estimates snapshot product, distinct from generic estimates history | Public product page states Aug 2016 onward | Two-hour snapshots described; API/bulk package must be confirmed | Candidate at its supported snapshot granularity | Effective/from-to version fields require sample verification | Contract governs actual schema, corrections, redistribution and model use | Institutional quote | Intraday-coarse expectations research, not sub-snapshot event inference. [P09] |
| Exchange-origin data via a licensed normalized vendor; Databento as documented example | Specific venue/dataset trades, quotes, bars, reference data | Varies by dataset; no universal historical start assumed | Event/receive/output clocks and product-specific delivery | Strong candidate for precise source timestamps when flags and channel semantics qualify | Must prove cancel/correction and adjustment behavior for the chosen schema; not inferred from generic documentation | Exchange non-display/redistribution obligations plus vendor terms; derived rights require confirmation | Usage/subscription plus applicable exchange fees | Price/event-clock reference and adjustment-vintage validation. [P14], [P15], [P20] |
| Official index membership / corporate-action history, source to be selected by incumbent owner | Licensed index/security universe and actions | Exact history and leaver coverage not established here | Contract-dependent files/feed | Potential improvement over reconstructed membership; no sample accepted | Announcement, effective date, corrected membership, and identifier epoch all required | Existing entitlement unknown; do not presume constituent or identifier redistribution permission | Exchange/index/vendor quote | Survivorship-safe universe and identity evidence after a measured gap justifies cost |
| Existing owner-retained first-party observations | Whatever Mastermind actually captured with verifiable receipts | Begins at the earliest proven retained generation, not the oldest event date | Native pipeline receipts | Best evidence for operational-as-known and actual decisions | Preserve append-only native revisions and immutable snapshots | First-party state rights do not clear embedded third-party payloads | Storage/engineering | Immediate operational proof; no invented historical backfill |
| Research Vault private-source metadata and receipts | Existing authorized document intake and public-safe catalog | Only retained, entitled inventory can be asserted | Native sidecar/ingest/publication owners | Receipt time can support operational knowledge; document date is not possession | Content replacements and withdrawals require versioned owner receipts | Original documents stay private and under their applicable licenses | Existing service/rights costs | Provenance context; not a new source of trading authority. [R26] |

Political, insider, 13F, government-award, options, ETF/fund and news families are not rejected. They inherit the same profile-based requirements and stay under their existing producers. Their event or reporting period, original disclosure, vendor delivery, corrections, and system receipt must be qualified separately. This temporal commission does not justify a new acquisition program for every family.

## D2. A material public-source rights finding

The current FRED legal page includes restrictions on use in connection with software/system development and machine learning/AI, as well as source-dependent rights and additional API terms. Its scope includes related services. Public access, public-domain underlying facts, and a free API key must not be interpreted as blanket authorization for this commission's intended storage, commercial display, or model use. [P16]

**Required disposition:** obtain an authoritative determination from Mastermind's existing rights/legal owner for the exact intended use and any existing written permission. This report neither concludes that all incumbent use is unlawful nor changes or disables existing pipelines. New procurement, acquisition, training, or promotion that depends on those rights remains gated. Direct access to an original statistical producer is an alternative to investigate under that producer's own terms, not an automatic workaround or permission.

## D3. Frozen commercial sample request — only after separate authorization

Reuse the existing institutional-estimates bake-off rather than creating a second vendor competition. The later rights/source owner should request an authorized, small extract with **one fixed issuer/fiscal-period set and a preregistered question set**. Do not optimize the sample to issuers whose data already look clean. [R34]

The decisive sample should contain an ordinary update, a late contributor, an amendment or vendor correction, a removed estimate, a fiscal-year change, a ticker/security change, a currency conversion, a corporate action where relevant, and an explicitly uncovered observation. Require these deliverables:

- A field dictionary distinguishing event/reference, contributor research date, input date, provider delivery, database validity, and correction timestamps, including timezone and precision.
- Original and revised payload versions; provenance for deletions and backfills; the meaning of an absent row versus a missing value.
- Both a historical extract and, where lawfully available, independently archived as-delivered snapshots. Reconcile discrepancies rather than treating the newer extract as its own audit oracle.
- Identifier, contributor, fiscal-period, accounting basis, unit, currency and methodology histories; the contracted scope of PIT coverage versus merely general historical coverage.
- Written scope for internal use, storage/retention after termination, derived features, display, redistribution, embeddings, inference and training, together with usage/egress and exchange pass-through costs.

Record a requirement as `PROVED`, `CONTRADICTED`, or `UNRESOLVED`, with the exact sample/contract reference. Marketing text cannot resolve the last state. A vendor with excellent current data but unrecoverable original vintages can still be suitable for prospective capture; it cannot be promoted as a historical-PIT provider by applying a guessed lag.

## D4. Cost, lock-in, and source diversity

Compare total incremental ownership cost, not a subscription headline: acquisition and entitlement, normalization, correction replay, identifier licensing, durable retention, egress, recovery tests, consumer integration, and future exit. Model storage from observed issuer-period-version counts and payload sizes; do not estimate by multiplying only current-row counts. High-frequency message retention and daily consensus snapshots have fundamentally different cost shapes.

Require an exportable native-identifier crosswalk, versioned schema dictionary, immutable source receipts, and a documented termination/retention outcome. Do not promise perpetual raw-data replay when a contract requires deletion. Conversely, do not discard lawful historical versions merely because a warehouse's default retention expires.

Two vendors that normalize the same filing are not two independent economic evidence families. Preserve originating accession/event/contributor identity alongside vendor identity. Source diversity is useful for error detection and availability, but should not inflate confidence through duplicated economic information.

# E. Canonical temporal model and deterministic query semantics

Everything introduced in this section is a **logical contract proposal**, not a new deployed schema, enum, registry, or service. Native names remain native. A shared meaning must not be confused with authority to change a closed consumer contract.

## E1. Three independent choices for every query

A query must specify:

**Information-set mode:** recorded-decision replay, operational-as-known, historical market reconstruction, or latest-revised diagnostics.

**Version policy:** source-original/as-reported, first-system-known, latest eligible as of cutoff, or explicitly typed latest-restated. These are not synonyms. A comparative recast is not automatically a correction to the original filing; a more recent ingestion is not automatically a newer source version.

**Economic applicability:** the observation period or valid-time interval about which the question is asked. “We know a membership change has been announced” differs from “the security is already a member.”

| Proposed mode | Evidence required | Permissible output | Forbidden claim |
|---|---|---|---|
| `RECORDED_DECISION_REPLAY` | Existing immutable emitted snapshot/output and its original identity | Exact stored result, including historical errors or missingness; later audit may be shown separately | Recompute current inputs and call them the old decision |
| `OPERATIONAL_AS_KNOWN` | Own retained source, necessary metadata/mapping/rule availability, and consumer-ready boundary by T | Cutoff-visible reconstruction of that specified system's usable inputs; literal output only if actually recorded | Backdate a newly acquired historical archive to the event date |
| `MARKET_AS_KNOWN_RECONSTRUCTION` | Qualified historical availability for the declared public/licensed channel, plus source version and reconstruction provenance | Reconstructed historical information set, with reconstruction time R and method version | Claim actual Mastermind possession or historically available implementation without evidence |
| `LATEST_REVISED_DIAGNOSTIC` | Current authorized source and explicit latest-version policy | Restated comparison, correction sensitivity, data repair analysis | Historical predictive or operational-PIT certification |

The information-set mode and computation method are separate. A current deterministic rule applied to a correctly reconstructed 2020 information set is a **current-method historical experiment**, not proof that the rule or system existed in 2020. Training, parameter selection, and label timing still need independent controls.

Use explicit query clocks rather than overloading one `as_of`: economic/reference time V, historical source-knowledge cutoff T, own-system evidence cutoff S, and reconstruction/execution time R. For operational-as-known, S is the relevant historical system cutoff, no later than the decision. For market reconstruction performed now, retained archive evidence may be visible at S=R while the economic source information must still qualify at T. This is compatible in principle with the native financial owner's separate source and recorded-at cutoffs, but exact API compatibility remains its owner's responsibility. The current reconstruction program may have been authored after T; its version and R are disclosed. It may not import outcome-selected mappings, later economic facts, or current classifications into the historical information set. A separately labeled present-day restated interpretation belongs in diagnostics, not in the certified historical-information features.

## E2. Clock dictionary and uncertainty

| Concept | Meaning | Native examples / handling | Not a substitute |
|---|---|---|---|
| `event_time` / `event_at` | When the underlying transaction, event, or observation occurred | Preserve source-native occurrence identity and event sequence | Disclosure, receipt, or decision time |
| `period_start`, `period_end` | Economic interval or instant described by a statistic | Typed fiscal instant/duration, trading bar, macro reference period | When the value became known |
| `effective_from`, `effective_to` | When a relationship, membership, identity or rule applies | Prefer internal half-open intervals; retain native endpoint convention | Announcement or acquisition time |
| Source acceptance | When a filing system accepted a submission | Preserve `accepted_at` as acceptance evidence | Guaranteed public dissemination |
| Source publication | When the source made this version available through the specified channel | Nullable, with source evidence and precision | A date inferred from fiscal period end |
| Provider availability | When the entitled vendor/channel made this version obtainable | Product, region, entitlement and dataset version are part of identity | Contributor research date or source release alone |
| Observation | When a specified observer received/saw the object | Distinguish provider observer from Mastermind observer and repeated polls | Durable capture or successful consumer validation |
| Ingestion / retention | When the bytes and receipt were durably captured by the specified system | Native `recorded_at`, `ingested_at`, capture commit receipt | Transaction start, download start, or filesystem touch |
| Consumer readiness | When required normalization, metadata, validation and publication dependencies became usable by this consumer | Prefer existing owner publication/commit receipts; do not create a second operational log | Raw retention before parsing/validation finished |
| Mapping/rule availability | When a mapping, identity edge, formula, calendar or policy became available | Existing governed definition ID, hash and availability clock | Effective applicability backdated to an earlier period |
| Computation | When a derived artifact was produced | Existing code/model/definition and dependency references | Historical source availability |
| Served publication | When the result was actually exposed to its consumer | Native Calcbench `published_at` maps here, not to source publication | Upstream source `published_at` |
| Correction knowledge | When correction/retraction/lineage evidence became visible | Its own event/version, effective scope and clocks | The timestamp of the fact it corrects |
| Decision cutoff | Latest admitted knowledge boundary for a declared decision | UTC instant plus consumer/session/calendar policy | Render time or a timezone-free date |
| `as_of` | Owner-specific label, not a universal clock | Interpret only through that owner's field contract | `known_at` by name similarity |

A clock assertion should conceptually include `(native_field, raw_value, semantic_basis, precision, timezone_or_calendar, lower_bound, upper_bound, evidence_reference)`. These can be represented in an existing producer receipt/profile; they do not require nine new columns on every dataset.

For a timestamp known only to lie within an interval, eligibility requires that the evidence establishes the event **no later than the cutoff**. A precise timestamp may use `timestamp <= T` only when precision and sequencing support equality. A date-only release with no authoritative timezone cannot be assigned an exact UTC midnight. A date and known source timezone can yield a conservative end-of-day bound; without a finite qualified upper bound, strict admission is refused. The timezone/calendar and interpretation version are retained.

Native interval conventions require explicit conversion. For a date-vintage API with inclusive endpoints, retain its original dates and declare the calendar used to derive any internal half-open interval. Do not treat a vintage date as an exact intraday publication time. Open-ended sentinels such as `9999-12-31` represent unbounded native validity; avoid timestamp overflow or inventing a last publication instant. Sparse changed-observation histories also require native reconstruction of each period's applicable vintage; they are not a complete snapshot simply because the latest file downloaded successfully. [P06], [P07]

Do not impose a universal “every clock increases” rule across independently synchronized systems. Clock skew, different scopes and heterogeneous timestamp semantics can violate naive comparisons. Validate only the ordering relations that the source contract guarantees. If observed clock uncertainty prevents ordering around T, refuse that fine-grained claim or use a coarser predeclared decision grid.

**Same timestamp is not necessarily same order.** If both release and decision are stamped to the same second but the source has no sequence or finer timing proof, a test must not assume the data arrived first. Use an existing source sequence/commit order, a qualified uncertainty bound, or conservative exclusion. Adding a magic millisecond is not evidence.

## E3. Eligibility is a dependency proof, not `coalesce`

For a version `v`, consumer `c`, cutoff `T`, mode `m`, and requested valid time `V`, define:

```text
eligible(v, c, T, V, m) =
    identity_and_payload_valid(v)
    AND native_policy_admits(v, requested_version_policy)
    AND required_channel_or_system_dependencies_visible(v, c, T, m)
    AND applicability_matches(v, V, query_semantics)
    AND current_use_is_authorized(v, c, intended_use)
    AND no_cutoff_visible_withdrawal_or_unresolved_conflict(v)
```

This is a specification of obligations, not a proposal to duplicate each native engine in a generic Python evaluator. An announcement query can admit a known future-effective change; a membership-at-V query cannot activate it before its valid interval starts.

For operational-as-known reads, every **necessary** dependency must have a qualified own-system availability bound at or before T: captured source, required filing metadata, mapping, identity, normalization, and consumer publication where applicable. The maximum of those qualified bounds summarizes readiness; it does not manufacture evidence for missing bounds.

For market reconstruction, use the declared source or licensed-channel availability evidence. A provider's delay is required when that provider is the assumed route, but not when the research explicitly and lawfully models direct source access instead. Public publication is not universally required for an entitled private channel. Conversely, a vendor's research date does not prove its delivery date. No universal `max(all columns)` or `coalesce(published, ingested)` captures these distinctions.

Current permission to perform the research and the historical channel/entitlement assumption are separate. Today's acquired archive may reconstruct historical market availability under a declared channel assumption without implying Mastermind held that subscription then. Actual-system replay requires the actual historical possession and system evidence.

## E4. Minimal logical objects and ownership

### Object 1: Native fact/version or snapshot member

Only a revising or stateful source needs row-level version semantics. The conceptual minimum is:

```text
source_owner + source_id + native_record_or_occurrence_id
logical_fact_key + entity/security/identifier_epoch
period_or_valid_interval + unit/currency/context/definition
value_or_typed_state
native_version_id + revision_kind + predecessor/evidence_references
native_clock_assertions
payload_digest + capture_or_source_receipt_reference
```

The `logical_fact_key` must distinguish economically different facts: issuer versus listed security; share class; unit and currency; fiscal period; duration versus instant; accounting/consolidation scope; source concept and dimensional context; and source methodology where material. Not every source needs every attribute, but omitted distinctions must be justified by its profile. A ticker is a label, not durable issuer/security identity.

### Object 2: Native acquisition or query receipt

This proves the exact bytes or selected native result and its bounded evidence, using the existing source owner:

```text
owner/profile/schema/definition identity
source locator or closed native object reference
capture identity + byte hash + logical hash when distinct
retained-at and relevant source/channel clock evidence
coverage inventory or generation reference
native revision/selection policy and query cutoffs
input/mapping/identity/calculation receipts
rights and allowed-use reference
result state, bounds, truncation, and refusal reasons
```

A byte hash proves content identity, not truth, past possession, source completeness, or authorization. A signed receipt authenticates its signer and assertions only to the extent that the existing trust contract supports them. Do not add a new signature service merely to avoid qualifying the actual capture boundary.

### Object 3: Existing Portfolio source receipt and Decision Snapshot

Do **not** introduce a competing `temporal_source_receipt` database. The existing Portfolio v1 source receipt is already the consumer envelope. Its protected plan names the following fields; any new required field or enum must be reconciled by the existing contract owner rather than inserted ad hoc: [R12]

```text
schema, source_id, domains, producer, owner, artifact,
source_schema, schema_version, definition_id, artifact_digest,
observed_at, known_at, as_of, generated_at, filesystem_observed_at,
correction_generation, freshness_state, coverage_state, rights_class,
authority_class, status, required, bytes, rows_total, rows_returned,
omitted_rows, clock_basis, error_code
```

Rich native temporal metadata can remain in the referenced owner artifact or query receipt. The adapter qualifies the existing `known_at` and `clock_basis` meaning; it must not claim that a scalar carries every historical guarantee. Where v1 cannot express a necessary distinction, the correct action is an owner-approved versioned contract change or typed non-admission, not weakening validation or adding unrecognized keys.

| Existing consumer field | Proposed mapping obligation | Forbidden shortcut |
|---|---|---|
| `artifact_digest` | Exact verified producer generation/result bytes under native serialization | Hash of a mutable pathname or URL text |
| `known_at` + `clock_basis` | Qualified availability for the consumer's declared mode, retaining native evidence by reference | Copy `as_of`, source acceptance, provider research date, or external mtime without qualification |
| `observed_at` | The observer and scope stated by the source contract | Invent a timestamp because the field is required |
| `generated_at` | Artifact-generation clock if truly supplied | Use run time to backdate an underlying record |
| `correction_generation` | Existing artifact generation/content identity | Treat it as a global row revision number or a new correction ledger |
| `coverage_state` and row counts | Bounded returned versus expected inventory, including omissions | Mark an unreadable or truncated response complete |
| `rights_class` / `authority_class` | Existing owner-approved use and authority classification | Derive permission from a public URL or grant execution authority |
| `filesystem_observed_at` | Local-file observation metadata | External market availability |

The protected S0 first-party book-state file-mtime allowance is narrow and must remain labeled `FILE_MTIME_FIRST_PARTY_STATE`; it does not establish the historical contents of an overwritten external artifact. The existing flags `write_permitted=false`, `execution_authority=false`, and `numeric_target_authority=false` remain unchanged. [R12]

## E5. Revision resolution: cutoff first, native lineage second

The correct conceptual order is:

```text
1. Bind query mode, source/system cutoffs, valid-time request, native policy,
   consumer contract, code/definition version, and authorized input generations.
2. Verify those immutable generations and their bounded inventories.
3. Project source facts and selection-driving economic evidence to T; apply the
   native system-evidence cutoff S and explicitly declared reconstruction policy.
4. Resolve logical identity and applicability within that projected evidence.
5. Apply the native source-original / first-known / latest-eligible / restated policy.
6. Apply visible withdrawals and conflicts before removing missing-valued rows.
7. Derive only from eligible dependencies; preserve missingness and uncertainty.
8. Return the value/state, inclusion/exclusion basis, native receipts and coverage.
9. Seal or consume through the existing owner snapshot/publication boundary.
```

**Projection must precede arbitration.** A later correction, classification, duplicate decision, or quarantine entry must not alter an earlier operational projection's value, status, reason, identifiers, receipt, or digest. This invariance compares the same query, consumer contract, and authorized access envelope. A later rights revocation may deny retrieval today, but must not rewrite the historical artifact or pretend the denial existed at the original decision. A later audit can state that the historical result was wrong; it cannot rewrite the result as though the correction were known then.

A late-ingested *older* source revision must not displace a newer eligible revision solely because it arrived most recently. Conversely, the largest revision number in today's store may be future-hidden. Resolve the native version graph after cutoff projection. Equal-ranking incompatible versions must return an explicit conflict unless the existing owner supplies a deterministic, justified arbitration rule. Lexicographic ID order is not financial truth.

Corrections have more than one scope:

| Kind | Meaning | Required temporal treatment |
|---|---|---|
| Source amendment/restatement | Issuer/source changes a reported assertion | New occurrence with its own publication/availability and typed lineage |
| Comparative recast | A later filing presents a prior period under a different representation | Preserve representation and original occurrence; do not assume it replaces every original fact |
| Vendor correction | Provider repairs its delivery/normalization | Original delivery remains in operational history; repaired version gets new availability |
| Parser correction | Mastermind fixes interpretation of retained bytes | Keep raw bytes and old interpretation; new parser/definition availability cannot be backdated |
| Mapping/identity correction | A later rule changes concept/entity attribution | Version the mapping evidence and its availability as well as effective scope |
| Withdrawal/retraction | Source removes the authority of an earlier assertion | Visible tombstone suppresses the targeted value; null filtering must not resurrect it |
| Backfill | Old economic period arrives in a new capture | Retention is current; historical market reconstruction needs separate availability proof |
| Quality quarantine | Current assessment finds an unsafe or corrupt observation | Preserve historical record and an independently timed audit exclusion; mode determines whether the exclusion was known then |

Reuse the native Calcbench/Fundamental Forensics revision vocabulary and ledger. A row revision ID, a raw-file generation, a query-result digest, and a Portfolio `correction_generation` are related but distinct identities. They must not be collapsed into one global integer. [R09], [R12]

## E6. Duplicate observations, coverage and negative knowledge

Idempotency must not destroy evidence. Re-reading an identical source object can share a content digest while retaining a new acquisition receipt. Two identical economic values can be distinct disclosures, contributors, or transactions. Byte-identical XBRL occurrences can retain separate occurrence identities; unchanged value does not prove unchanged provenance.

A content-deduplicated snapshot can avoid repeated data rows, but an **observation of no change** still needs a successful, scoped acquisition/coverage receipt when it is used to establish freshness. A failed poll cannot be substituted for “nothing happened.” Reuse existing collector run/capture records; do not create a universal polling ledger.

Required missingness distinctions include: not yet released; not reported; outside coverage; not entitled; transport failed; parsing failed; ambiguous identity; uncertain timestamp; withdrawal; expired evidence; and valid structural zero. A missing dividend observation must not become zero merely because a numerical helper can make an expression evaluate. Source-specific proof of a structural zero is different from `None` or a missing field. The inspected annual-factor helper's zero conversion deserves a bounded owner review, not a global accounting-rule change in this research PR. [R02]

An honest coverage statement identifies its denominator: intended source universe, native snapshot inventory, policy-excluded rows, returned rows, and unreadable/omitted rows. “100% of returned records passed” does not establish completeness when records silently disappeared. Selection-optimality requires an immutable candidate inventory or native ledger witness, not only the selected record's receipt. The Calcbench docket explicitly limits its accepted receipt proof to selected-occurrence consistency; preserve that limitation until a stronger owner proof exists. [R09]

## E7. Effective-dated identity, membership and adjustments

Store or reference issuer identity separately from security/share-class identity and ticker alias intervals. A merger, spin-off, ADR conversion, ticker reuse or exchange move can change the security relationship without changing the reported company in the same way. Each mapping has effective applicability **and** the time its evidence/rule was available.

For a membership query at V, resolve the owner interval and its cutoff-visible evidence. For an announcement feature, future-effective membership may be known at T but must remain a prospective event, not current inclusion. Historical sector/subtheme classifications need their own definition/effective/knowledge versions. Today's industry label cannot be silently used to select a historical cohort, even if all numerical features have correct filing clocks.

Adjustment vintages belong to the feature dependency set. A future split, dividend, FX method, or vendor correction can change a historical price/volume representation. Freeze the feature's admissible adjustment basis and normalization; keep ex-post outcome adjustments separate. A return metric can legitimately use later realized prices as labels after their availability, but future rescaling cannot leak into pre-decision thresholds, price floors, market-cap estimates, or volume features.

The proposed contract therefore includes references to the native entity/universe/sector/calendar/adjustment owners, not copies of those databases. Existing membership and historical-leaver work must supply its actual coverage and version evidence. [R16], [R18]

## E8. Worked temporal examples

### Example 1: a fixed lag cannot repair revised values

Synthetic fiscal period ends on December 31. The original value is 100, released March 1. A later restatement changes it to 70 on September 1. An October download retains only 70 and stamps it as `period_end + 120 days`, approximately late April. A June backtest then sees 70, although the revision was not available until September.

Increasing the modeled delay somewhat does not prove safety for arbitrary restatements or late filers. The necessary evidence is the **correct value version and its qualified availability**, not a delay attached to today's value. A lag-proxy experiment can remain an explicitly modeled sensitivity study; it cannot certify an actual historical information set.

### Example 2: market and operational knowledge can both be correct and differ

All times here are synthetic UTC timestamps on the same day, with exact availability assumed for illustration:

| Version | Value/state | Qualified channel availability | Own consumer-ready time |
|---|---|---|---|
| v1 | 100 | 09:01 | 09:05 |
| v2, supersedes v1 | 80 | 10:01 | 10:07 |
| v3, withdraws the fact | WITHDRAWN | 11:01 | 11:06 |

| Decision cutoff | Market reconstruction, latest eligible | Operational-as-known, latest eligible |
|---|---|---|
| 09:03 | 100 | NOT_YET_AVAILABLE |
| 10:03 | 80 | 100 |
| 10:08 | 80 | 80 |
| 11:03 | WITHDRAWN | 80 |
| 11:07 | WITHDRAWN | WITHDRAWN |

After v3 arrives, the stored 10:08 decision must still return its original bytes. A new audit may annotate the later withdrawal, but must not silently replace the old decision. If v0, an older source version, arrives at 11:08, it must not resurrect the fact.

### Example 3: known future applicability

A membership change is announced Monday at 18:00, observed by the consumer at 18:02, effective Friday's open. On Tuesday it can be an admissible future-event feature. It cannot make the stock a current index constituent on Tuesday. A correction to the effective date disclosed Wednesday must not alter Tuesday's cutoff-visible event description.

## E9. Atomicity, caching, hashing and lawful retention

A decision spanning owners should bind a **vector of immutable producer generations**, not claim a nonexistent global transaction. Each producer proves its own generation is complete and published; the consumer validates the chosen generation and cutoff for each required section. Missing required evidence yields the existing BLOCKED/PARTIAL/INVALID semantics, not a mixed-generation “complete” snapshot.

Protect against time-of-check/time-of-use changes: resolve a generation once, verify its manifest and payload digests, reject unreadable or mismatched parts, and avoid rereading an unversioned latest path during composition. A cache key must include source generation, query/cutoff, native selection policy, mapping/definition identity, rights scope where relevant, and serialization version. Correct data under the wrong cached query is still incorrect.

Preserve the existing S0 canonical serializer, qualified SHA-256 identifiers, content-addressed files, and size limits. Do not add a mutable latest pointer or correction index forbidden by its plan. Content addressing does not require publishing private raw payloads into GitHub. [R12]

Retention must satisfy both research recovery and actual rights. When a source must be removed under a governing agreement, the lawful owner records the deletion/retention disposition and any permitted hash/metadata tombstone. A digest-only record must say `UNREPLAYABLE_BYTES_UNAVAILABLE` or the accepted equivalent; it cannot certify exact replay. Backups, compaction, garbage collection, and restores must preserve the required owner generation closure or explicitly reduce the guarantee. No storage operation is executed by this commission.

# F. Derived intelligence and deterministic-before-LLM boundaries

## F1. Useful outputs without an opaque aggregate score

| Output | Deterministic definition | Consumer value | Qualification |
|---|---|---|---|
| Availability margin | `T - qualified_availability_upper_bound` for each admitted dependency | Shows whether evidence was comfortably available or sits near the cutoff | Unknown bounds remain unknown; margins from different clock semantics are not averaged |
| Source-to-system delay | Qualified own readiness minus qualified channel availability | Identifies acquisition/normalization latency and missed opportunities | Report only when the clocks are comparable and uncertainty permits the subtraction |
| Revision delta | New versus prior eligible value under the same fact key, unit, period and representation | Shows what changed, by how much, and from which source version | Separate issuer restatement, vendor repair, parser repair and recast |
| Revision age / stability | Time and number of eligible revisions since a declared original version | Supports interpretation of provisional versus mature observations | Not a universal confidence score or automatic risk reduction |
| Coverage vector | Expected, returned, excluded, missing, stale, rights-blocked and unassessable counts | Makes partial evidence actionable without pretending missing means neutral | Denominator and universe generation must be explicit |
| Correction impact set | Native derived artifacts/decisions that depend on a corrected version | Supports targeted review and recomputation | Follow existing dependency/publication owners; no new global correction queue |
| Replay discrepancy | Difference between immutable recorded output and a separately labeled recomputation | Separates historical emission, bug repair and current-method analysis | Never overwrite the original decision |
| Vintage sensitivity | Matched-support result differences across first-release, latest-known, proxy and latest-revised panels | Quantifies the importance of temporal assumptions | Diagnostic only; direction and magnitude must be measured, not assumed |
| Duplicate economic origin | Shared accession/event/contributor dependencies across signals/vendors | Prevents false independent confirmation | Do not conflate economically distinct observations with equal numeric values |
| Latent missingness warning | Required family absent or acquisition incomplete at T | Prevents “all clear” inferred from no records | Requires a known expected family/universe, not a new synthetic risk score |

Absolute changes should carry units; percentage changes need a declared denominator and a zero-denominator policy. Use exact decimal/rational treatment where the native financial owner requires it. Do not derive a numerical confidence from timestamp precision or coverage unless a separately validated, interpretable model explicitly supports that use.

## F2. Deterministic responsibilities

Before any model receives evidence, deterministic native code must establish identity, schema, units, fiscal geometry, clock parsing, timezone/precision, valid-time applicability, cutoff eligibility, correction/withdrawal policy, source rights, coverage, bounded payloads and exact source references. It must select eligible vintages, calculate differences, and validate the dependency closure. An LLM must not decide whether an unsupported timestamp is “probably safe.”

Cheap models may propose document taxonomy, extract candidate dates with exact source spans, group potentially related filings, draft descriptions of already-computed revisions, or flag ambiguous mappings for review. Their outputs remain candidates until the source/definition owner validates them. Extracted dates are not automatically publication clocks; a report's printed date does not establish when the system received it.

Frontier models are appropriate for difficult cross-source interpretation, explaining disagreements, evaluating an architecture tradeoff, or designing falsifiers. They do not create rights, availability, correction lineage, missing values, probability calibration, or source authority. No model should be called merely to wrap a timestamp filter or canonical hash.

## F3. Historical model leakage

A current language model may encode knowledge learned after a historical cutoff. Restricting retrieved documents does not prove that its generated interpretation is historically information-pure. Literal replay therefore returns archived model outputs and their original evidence/prompt/model identifiers where lawfully retained. A current-model historical experiment is labeled as such and cannot establish original historical intelligence.

For controlled model research, record the model and prompt version, retrieval-corpus generation, allowed source cutoff, output artifact and any training/fine-tuning data admission. Prefer deterministic historical feature construction; use blinded source packets and negative controls for interpretive tasks. Do not claim that a model-version label reveals its precise training cutoff or guarantees the absence of memorized future events.

---

# G. Mastermind integration map and compatibility obligations

## G1. Producer → owner → evidence family → consumer

| Producer/input | Existing canonical owner or artifact | Evidence family | Existing consumer / permitted extension |
|---|---|---|---|
| SEC filing occurrences and source metadata | Fundamental Forensics/Calcbench native acquisition, ledger, period/mapping/query receipts | Fundamental facts and revisions | Existing financial-query response; then owner-approved Portfolio S0 source adapter; no direct generic row arbitration. [R09], [R10], [R12] |
| Broad EDGAR panels | Existing Macro EDGAR collector and panel artifacts | Current screens / modeled fundamental research | Existing `loop/fundamentals.py`; label proxy basis, and later substitute qualified native evidence only through that owner. [R02], [R03], [R04] |
| Macro release/vintage observations | Existing FRED collector and `engine/pit.py` | Macro state and revisions | Existing macro consumers, with full required-leg qualification and explicit first-print/latest-known mode. No silent production basis flip. [R07], [R08] |
| Prospective analyst estimates/revisions | Existing SRC-A1 collector/history and #8064 | Expectations changes | Information-to-Price and held-risk earnings-expectation lane after exact generation/clock qualification. [R19], [R20], [R30], [R31] |
| Index/universe/classification evidence | Existing membership and historical-sector owners | Universe, sector/theme context | Existing membership consumers and research panels; retain effective and knowledge versions. [R16], [R17], [R18] |
| Price/quote/action evidence | Existing market-data/adjustment owners, not a new C5 price store | Priceability and market reaction | Native return/technical consumers; distinct feature and outcome adjustment vintages |
| Daily archived signals | `brain/signal_history.py` | Historical system observations | Existing outcome/calibration path; do not replace it with an unauthorized ledger. [R15] |
| Portfolio source receipts and decision sections | Existing S0 contracts/composer/source adapter, #673 | Decision evidence across domains | Existing Portfolio inspector/snapshot API; preserve read-only book authority and v1 compatibility. [R12], [R14] |
| Company Intelligence projection | Existing Macro producer and Terminal server-side resolver/normalizer | User-facing source context | Existing same-origin Company Intelligence boundary; do not add browser-side alternate source fetches. [R25] |
| Licensed/private research documents | Existing Research Vault sidecar, capture/catalog/search and publication owners | Research context | Existing authorized display/retrieval; temporal metadata cannot widen document redistribution or signal authority. [R26] |
| Temporal health projection | Existing Data OS/census/consumer-receipt ownership, reconciled with C8 proposal | Operational completeness, not alpha | Existing health/census surface; no second registry or data-health factor. [R05], [R06], [R27], [R32] |

## G2. Compatibility rules

The shared boundary must be an **adapter to existing guarantees**, not an importer of private internals. Consumers should ask the native financial or macro query owner for a qualified result, not copy its ledger and recompute selection in Portfolio or Terminal.

A partial consumer can be useful: return the available source sections and the exact missing/blocked sections, provided the current consumer contract permits that result. A required unavailable dependency must block the dependent claim. A visually complete card is not evidence of complete source coverage.

Keep source truth, data health, analytical inference, and decision authority separate. A qualified temporal receipt does not grant portfolio sizing, trade origination, ranking, alert escalation, or execution permission. A historically correct observation can still be irrelevant, misleading, unlicensed for display, or highly correlated with another observation.

Before any schema change, the later owner must bind: native source schema and revision; consumer schema and allowed enums; digest/serialization law; clock mapping; required-versus-optional sections; rights; correction visibility; pagination/coverage; and exact failure behavior. Unsupported versions fail closed. There is no “compatible enough” fallback to latest JSON.

## G3. No-new-plane inventory

This commission proposes **no new warehouse, graph authority, experiment registry, polling ledger, correction queue, source publisher, portfolio account, retry lifecycle, rights service, or research source of truth**. Native append-only stores may gain qualified metadata under their owners. Existing artifact/publication machinery may gain an adapter. The Portfolio snapshot is the consumer record; the source receipt is not a second copy of all raw history.

The name “common source receipt” describes interoperability, not a mandate for every subsystem to serialize the same giant object. The source remains authoritative for its records; the consumer remains authoritative for what it consumed; neither rewrites the other's history.

---

# H. Empirical validation, honest replay and falsification

## H1. Three different acceptance questions

**Engineering correctness:** Does the implementation return only the input versions authorized by its declared temporal contract, with correct states, complete lineage and reproducible identity?

**Historical feasibility:** Are there enough lawful, genuinely versioned observations to estimate the intended relationship at the chosen cadence and universe, without survivorship or revision leakage?

**Incremental predictive usefulness:** Does an eligible evidence family improve a predeclared outcome beyond the existing baseline at a practically meaningful scale?

These questions have separate verdicts. Engineering can pass while historical depth is insufficient. Historical feasibility can pass while incremental predictive value is null. A null predictive result cannot justify admitting future information. Commission 5's infrastructure should be accepted for honest decision reconstruction, not required to discover profitable alpha.

## H2. Forty mandatory acceptance scenarios — proposed, not executed here

These are a casebook for the future implementation owner, not a claim of forty passing tests. Each case must bind the exact native source/query/consumer contracts and include both positive and negative controls. “Refuse” means a typed owner-compatible result or error, not a successful empty object.

| ID | Fixture / adversarial change | Required outcome |
|---|---|---|
| T01 | Exact valid source, all required dependencies available before T | Admit the expected value and exact receipt/generation; establish a positive control |
| T02 | Source publication before T, own retention after T | Market reconstruction may admit under qualified channel evidence; operational-as-known excludes |
| T03 | Source retained before T, necessary normalization/publication completes after T | Operational consumer excludes until ready; raw possession alone does not certify usable evidence |
| T04 | Publication is a date with unknown timezone or unbounded timing | Refuse exact intraday eligibility; preserve the date and reason |
| T05 | Date-only evidence has a validated finite upper bound before a coarse decision cutoff | Admit only under the declared coarse policy; never relabel as an exact event timestamp |
| T06 | Naive timestamp / malformed offset | Reject deterministically; no host-timezone default |
| T07 | Same instant represented using different explicit UTC offsets | Equivalent admission and canonical instant; preserve raw provenance separately |
| T08 | DST fold/gap in a local timestamp without sufficient disambiguation | Refuse ambiguity; with validated offset/calendar evidence, select the correct instant |
| T09 | Release and decision share coarse timestamp but no ordering proof | Conservative exclusion or typed uncertainty; equality alone does not establish precedence |
| T10 | Source event occurred before T but disclosed after T | Exclude from historical knowledge features, regardless of economic event date |
| T11 | Original and correction both before T | Native latest-eligible policy selects the correction; as-reported policy still selects its defined original |
| T12 | Correction first becomes visible after T | Earlier value, state, reason, IDs and receipt hash are unchanged |
| T13 | Older source version ingested after a newer eligible version | Ingestion order does not incorrectly replace the newer source version |
| T14 | Visible withdrawal carries no numeric value | Return withdrawn state; do not filter nulls first and resurrect the predecessor |
| T15 | New information declares a future withdrawal after the historical cutoff | Prior operational/recorded result remains unchanged; later audit annotation is separate |
| T16 | Two conflicting eligible revision branches without qualified arbitration | Refuse the ambiguous answer; do not choose by random order or ID sort |
| T17 | Parser correction applies to old raw bytes but the parser became available after T | Current-method diagnostic may change; historical system projection does not |
| T18 | Mapping/lineage evidence arrives after T, effective for an older period | Do not backdate its availability or change the earlier cutoff-projected receipt |
| T19 | Identical payload re-ingested | No duplicate economic weighting; retain the legitimate new acquisition receipt |
| T20 | Identical values from distinct disclosures/contributors | Preserve distinct occurrence identity; equality is not proof of duplicate evidence |
| T21 | Future-hidden unrelated record appended to the ledger | Earlier selected value, exclusion reasoning and receipt identity remain unchanged |
| T22 | Annual value is restated after T, latest download stamped with +120-day lag | Strict-PIT qualification fails unless the original value-vintage evidence is supplied |
| T23 | Initial-release macro series is used for a latest-known-vintage query after a revision | Reject the policy mismatch or return an explicitly initial-release result; do not claim all-vintage replay |
| T24 | Non-vintaged macro leg uses latest value shifted by release calendar | Mark proxy/diagnostic; cannot pass the strict full-leg PIT gate |
| T25 | One required macro leg missing; caller would silently skip its replacement | Entire requested PIT comparison is incomplete/refused; no vacuous “same frame confirms PIT” success |
| T26 | Membership announced before T but effective after requested V | Event feature can admit the announcement; membership-at-V remains unchanged |
| T27 | Current sector/subtheme label is retrospectively attached to a historical name | Exclude from era-correct classification unless the native mapping's knowledge evidence qualifies |
| T28 | Ticker reused / security share class changed | Resolve correct security epoch or refuse; no join solely on ticker text |
| T29 | Future corporate action changes a historical adjusted-price series | Feature calculation retains its cutoff-admissible adjustment basis; labels may use a separately declared outcome basis |
| T30 | Missing/unreported cash-flow component versus explicitly reported zero | Preserve the distinction in value, state, coverage and downstream calculation |
| T31 | Failed collection run reports no observations | Emit failure/unknown coverage, not “no event” or fresh empty success |
| T32 | Identical successful poll contains no changes | Preserve the acquisition/coverage proof without unnecessarily duplicating source facts |
| T33 | Selected record is valid but the source inventory/page is truncated | Selected-occurrence consistency may hold; complete coverage/optimal selection must not be claimed |
| T34 | Source pointer changes during snapshot composition | Use one verified immutable generation or refuse; no cross-generation successful result |
| T35 | Manifest digest or a required payload chunk does not match | Reject and preserve error evidence; never fall back silently to latest |
| T36 | Mixed required inputs include one future/unknown-clock dependency | Dependent claim is withheld; unrelated permitted sections may remain partial under the existing contract |
| T37 | Content is public-looking but lacks the required use/retention/AI entitlement | Rights refusal remains explicit; no automatic source or display authority |
| T38 | Old input bytes are lawfully deleted or unavailable after retention expiry | Exact raw replay reports unreplayable; permitted hashes/metadata do not impersonate retained bytes |
| T39 | An old recorded decision used data later shown to be invalid | Return the original immutable decision separately from the new audit; no rewritten history |
| T40 | Same immutable inputs/query serialized in a different order/process | Canonical result identity is stable; changing a substantive dependency or policy changes the identity |

All cutoff tests need at least one admissible record and one deliberately inadmissible record. A reader that rejects everything cannot pass. Required mutations include replacing readiness with event date, dropping a required dependency, changing withdrawal order, using a current mapping, and changing the source generation between validation and use. A mutation kill must fail for the intended semantic reason rather than an unrelated missing fixture.

## H3. Honest replay protocol

Every scored historical experiment or operational replay must bind its exact source generation vector; query mode; version policy; source and system cutoff; valid-time request; admitted source/channel assumptions; identifier/universe/classification versions; rule/code/model versions; feature definitions; label interval and label availability; rights scope; exclusions; and missingness policy.

For a recorded decision, first retrieve and verify the original emitted artifact. Then, only if authorized, perform a separately identified recomputation. Never use a recomputed output to fill a hole in an actual decision history without an explicit “not recorded” state.

For a historical reconstruction, retain reconstruction time R, the archive and metadata actually consulted at R, and the evidence supporting historical availability at T. Historical access credentials must not be fabricated. A publicly documented old release can support reconstruction even though this study retrieved it now; it cannot prove operational possession at T.

Quarantine discovered temporal errors without deleting the original historical evidence or quietly improving historical metrics. Report results under the original protocol and under the corrected protocol when scientifically appropriate, with explicit changes in denominators and exclusion rules. An input selected because of a later outcome must not be laundered into a supposedly blind earlier test.

## H4. Temporal sensitivity study, without burning existing holdouts

No market-data outcome study was run in this research pass. A later admitted study should freeze its population and four input variants before reading results:

| Variant | Purpose | Eligibility |
|---|---|---|
| Q: qualified cutoff-visible native vintages | Primary honest-history analysis | All necessary temporal/identity/right proofs satisfied |
| F: first-release-only panel | Tests sensitivity to revision-policy choice | Only when the question explicitly permits first prints |
| L: modeled-lag panel | Measures approximation sensitivity | Clearly labeled proxy; not the primary certified-PIT result |
| O: latest-revised panel | Diagnostic oracle comparison | Never used for promotion or feature selection |

Compare Q/F/L/O first on **matched issuer-period support** so changes in coverage are not confused with changes in information. Then separately report each variant's full admissible coverage, missingness, and production-feasible fallback. Do not drop unprofitable, delisted, renamed, or thin-history names to make the matched sample look representative. Quantify the remaining selection limitation.

The diagnostic difference between O and Q can be called a revision-sensitivity or leakage-sensitivity estimate; it is not necessarily positive and is not a clean causal estimate of trading losses. Units, vintage policy, source population and model fitting must remain aligned for the comparison.

Existing trend, factor, Information-to-Price and other registered studies retain their frozen trials and sealed holdouts. Commission 5 does not authorize rerunning, retuning, re-registering or spending those outcome sets. Native experiment owners must admit any subsequent temporal-sensitivity study and preserve previous reported results and their no-promotion history.

## H5. Optional incremental predictive program for a qualified evidence family

After temporal qualification and historical feasibility, a separate family owner may preregister a predictive question. Examples: whether an eligible fundamental revision improves prediction of the next *first-released* revenue/EPS observation; whether a macro vintage improves a fixed-horizon nowcast; whether a documented expectations change adds information beyond existing SUE and price/breadth evidence. These are hypotheses, not established results.

Specify the target's publication/label-availability convention. Training at T cannot use labels whose outcome interval ended before T but whose realization was not yet observable. Distinguish ex-post economic-final targets from first-release targets and do not switch after seeing results.

Use expanding/rolling-origin evaluation with time-ordered splits. Purge observations whose feature/label intervals cross training/test boundaries, and size any embargo to the actual dependence mechanism. Fit imputation, scaling, mapping choices, feature selection and hyperparameters inside the training window. Random row splits are inappropriate for a panel with shared issuers, events and overlapping financial horizons.

The baseline should contain the best applicable existing evidence: price trend/volatility/liquidity, size, broad market and era-correct sector context, existing SUE/revision signals, and same-origin source information already consumed. Compare baseline, new family alone, and baseline plus new family. A second representation of the same filing does not automatically constitute independent information.

For numerical forecasts, declare an error metric and practical improvement margin; for probabilities, use a proper score and calibration with coverage; for cross-sectional associations, report rank/linear association as appropriate with dependence-aware uncertainty. A trading study needs separate cost, execution-delay, turnover and liquidity assumptions, with horizon fixed in advance. Proposed 5/20/60-session return horizons are an example menu, not three automatic confirmatory trials or new trading authority.

Report issuer/event/time dependence, effective sample size and confidence intervals. Predeclare the experiment family and number of variants; use a justified multiplicity method and separate exploratory from confirmatory findings. Harvey, Liu and Zhu motivate stronger multiple-testing discipline; Bailey and coauthors provide a framework for diagnosing backtest overfitting. Neither supplies a universal threshold that excuses a flawed information set or guarantees live performance. [P21], [P22]

Power planning must use a declared practically meaningful effect and the actual eligible sample, not the raw vendor row count. A wide interval or insufficient independent events yields **INCONCLUSIVE**, not success or a forced negative conclusion. Failure to improve the baseline is a valid reason not to promote an expensive evidence family, but not a reason to abandon basic temporal integrity.

## H6. Prospective shadow and production-path acceptance

Once a later owner is authorized, use a bounded prospective window over the exact target consumer and producer generations. Freeze the window, expected schedule/universe, allowed missingness, scope and latency budget before it begins. A prospective window starts when valid capture begins; it is not backfilled from today's snapshots.

Require every expected decision/source slot to resolve to a verified receipt or explicit permitted missing/refusal state. The acceptance target for unexplained generation mismatches and prohibited future inputs is **zero**; it is not “low enough on average.” Report p50/p95/p99 latency only after measurement, with clock uncertainty and failed observations included. Do not invent current performance figures.

Production proof must show that the actual consumer reads the same qualified artifact identity tested by the research/adapter, including its error path. A green unit suite, merged schema, or visually correct page cannot establish that chain. Rollback preserves prior production behavior and the immutable shadow evidence; this commission authorizes neither rollout nor rollback execution.

# I. Risks, failure modes, and explicit non-claims

| Risk | How it could fail | Required control / accountable owner |
|---|---|---|
| False precision | Date-only or acceptance timestamp presented as exact public availability | Producer clock profile and finite-bound admission; consumer refuses unsupported resolution |
| Revision laundering | Current corrected values given historical modeled timestamps | Native version/lineage owner preserves originals; historical study labels proxies |
| Selection leakage | Future mapping, quarantine, source inventory or classification changes past selection | Cutoff-project all selection evidence; test future-append invariance |
| Cross-owner mismatch | Valid receipts refer to different or uncommitted generations | Existing consumer binds an immutable generation vector and verifies closure |
| Survivorship and denominator bias | Only current securities or successfully parsed rows are evaluated | Universe/identity owner plus expected inventory and explicit missingness |
| Silent neutralization | Absent evidence becomes zero or “no risk” | Typed missingness and required-input withholding in the native consumer |
| Source correlation | Multiple vendors or derived signals repeat the same economic origin | Keep origin/dependency references; existing independence owner handles economic weighting |
| Vendor lock-in | PIT logic depends on undocumented proprietary corrections or unexportable history | Authorized sample/contract, exportability, exit and retention diligence |
| Rights conflict | Public API or licensed source used beyond its allowed storage/AI/display scope | Existing rights owner determines exact permitted use; no new-use promotion while unresolved |
| Historical LLM leakage | Current model supplies future facts despite cutoff-limited retrieval | Deterministic features, archived-output replay and explicit current-model experiment labeling |
| Resource explosion | All vintages, event streams and nested receipts overwhelm storage or consumer payloads | Native owner budgets, bounded DAG references, query limits and measured retention economics |
| Overengineering | New platform delays fixing a real consumer | One source-to-consumer qualification slice and no-new-plane acceptance |
| Weak audit oracle | A receipt generated from the selected value is used to prove complete selection | Independent immutable candidate inventory/native ledger witness and positive/negative controls |
| Self-certification | Implementation author treats its tests or this report as independent acceptance | Separate exact-head non-coauthor review and actual consumer proof before release |
| Stale research | Today’s pins or vendor pages treated as permanently current | Bounded relevant-delta check at implementation pickup and source contract renewal |

**Not claimed by this report:** complete estate coverage; a current live data census; deployed S0; complete original analyst-estimate history; vendor rights approval; production correctness; positive alpha; repaired historical results; a new live source; or completion of the broader Mastermind data-to-decision program.

The report can still be complete as research: the recommendation is concrete, the key evidence is pinned, the unverified facts are bounded, and the follow-on admission/test requirements are explicit. An honest build-ready recommendation must identify facts the implementation owner needs to establish rather than inventing them here.

---

# J. Build priority and kill criteria

## J1. Prioritized decision

| Priority | Recommendation | Why now / prerequisite | Exit condition |
|---|---|---|---|
| P0 | Accept explicit replay-mode, clock-basis and version-policy semantics through existing owners | Prevents misleading “PIT” claims without a platform migration | One reviewed compatibility matrix maps native producer meaning to the existing consumer contract |
| P0 | Qualify the first financial-query-to-S0 receipt slice after custody admission | Reuses the richest existing temporal work and supplies an actual consumer | Positive/negative same-generation proof with no new state plane or book authority |
| P0 | Classify modeled-lag and insufficiently clocked histories honestly | Prevents a proxy from being silently promoted as verified history | Existing owners acknowledge exact query restrictions; no production basis flip in this research PR |
| P0 | Determine rights for intended new source storage/model/commercial uses | Temporal capture is useless if the intended retention/use is not authorized | Written existing-owner disposition for each admitted source/use |
| P1 | Qualify macro first-release versus latest-known-vintage consumers and complete-leg coverage | Only after source/rights qualification and native owner admission | Correct vintage selection and no silent non-vintage fallback in the requested strict mode |
| P1 | Preserve prospective estimates, event and decision receipts with real readiness clocks | Every missed prospective observation is unrecoverable as an actual receipt | Exact native observation/consumer identities and append-only correction behavior |
| P1 | Bind universe, identifier, sector/subtheme and adjustment versions | Numerical PIT alone cannot prevent selection leakage | Era-correct or explicitly unavailable dependencies in historical queries |
| P1 | Extend operational health through existing Data OS/census owners | Static census does not show current artifact/consumer completeness | Read-only generation/coverage projection, reconciled with C8, without an alpha score |
| P2 | Authorized commercial historical-vintage bake-off | Only after a measured coverage gap and incumbent source-owner decision | Exact SKU/sample proves incremental historical utility and acceptable rights/cost |
| P2 | Broaden temporal conformance to options/flows/funds/news/relationships and regions | Each source has distinct event/disclosure/availability semantics | Native family-specific proofs and an existing consumer, not just another schema |
| DEFER | Universal intraday availability claims for coarse archives | Insufficient clock precision or original delivery evidence | Reopen only when source-qualified bounds or independent archived delivery exist |
| DEFER | All-estate historical reconstruction and full query-serving expansion | Would swallow existing S0/Calcbench/product programs | Existing program owner admits a concrete capability with demonstrated demand and capacity |
| REJECT | New temporal warehouse or duplicate correction/receipt authority by default | Adds state and migration risk before user value | Only a separately evidenced architectural exception could change the ruling |
| REJECT | Backdating current captures, fixed-lag certification, hidden latest fallbacks | Makes the core guarantee false | No exception based on attractive backtest performance |
| REJECT | One opaque truth/availability/independence score that affects trades | Conceals distinct evidence and grants unintended authority | Keep dimensions inspectable; any investment use needs separate scientific and policy acceptance |

## J2. When not to build or promote a source family

Do not build a new collector when a canonical owner already supplies the necessary qualified evidence. Do not buy history when the use case only needs prospective capture, when the history is latest-restated despite a PIT label, or when allowed retention cannot support the intended replay. Do not launch a predictive program when eligible observations, independent events, label availability, or universe coverage cannot support a meaningful test.

Do not promote a signal family when its apparent contribution disappears after same-origin baselines and proper timing controls, when uncertainty remains too wide for the declared practical effect, or when cost/latency/rights make the measured improvement unusable. Report negative and inconclusive outcomes without retuning against the held-out result.

**Do not kill the temporal integrity boundary because it exposes missing data or lowers apparent alpha.** Its purpose is to make Mastermind's claims true. Prefer a narrower, honestly qualified product to a broad but unverifiable historical claim.

---

# K. Proposed implementation phases, dependencies and acceptance

This is a sequence of bounded recommendations, not an active implementation schedule. Each modifying phase requires then-current procedure, source custody and owner acceptance. Engineering effort and latency budgets must be estimated from the admitted slice, not invented from vendor marketing or repository size.

| Phase | Existing accountable role | Bounded output | Acceptance / next gate |
|---|---|---|---|
| K0 — source and custody admission | Assigned CEO with native source and S0 owners | Current exact heads, affected paths, pending-effect disposition, rights/use classification, one clock/contract mapping | No unresolved modifying collision; blocked reads/effects remain explicit; later phase is authorized rather than inferred |
| K1 — one native temporal qualification slice | Financial query/ledger owner plus Portfolio S0 adapter owner | One issuer/direct-metric chain and one existing source-receipt consumer, using native source selection | Positive and negative cases, exact receipt identity, closed-schema compatibility and no new state plane |
| K2 — independent review and bounded shadow | Non-coauthor reviewer and existing consumer/release owner | Exact-head review, generation-consumption proof, prospectively captured shadow receipts | No open correctness/rights/authority blocker; required current checks and source-to-consumer evidence; no trade promotion |
| K3 — macro and prospective expectations | Native macro/SRC-A1 and research consumers | Qualified first-release/latest-known policies, complete-leg refusal, real prospective capture | Source/rights feasibility; correction and missingness cases; no duplicate vendor program |
| K4 — selection dependencies and additional families | Existing identity, membership, price, event and regional owners | Effective/knowledge-versioned dependency references and family-specific temporal profiles | All dependent feature/universe claims qualify or visibly abstain; no present-day mapping leakage |
| K5 — historical usefulness study | Existing experiment/evaluation owner | Preregistered temporal sensitivity and, separately, family-specific incremental-value results | Eligible samples, no holdout reuse, dependence/multiplicity/power treatment, explicit null/inconclusive results |
| K6 — governed rollout and durable closeout | Existing product/source/release owners | Approved consumer rollout, monitoring and recovery evidence, updated native capability/census records | Actual authorized user/machine path proved; source and decision histories preserved; later changes monitored by existing owners |

K1 is not dependent on purchasing a vendor feed, launching a warehouse, or completing the entire Portfolio V3 product. Conversely, K1 cannot bypass the incumbent S0 contract simply because that candidate is unmerged. When a dependency is not yet accepted, a bounded fixture-based compatibility proof may proceed, but it must remain labeled development proof and cannot claim native adoption.

A phase is not complete merely because a document, schema or standalone test exists. Each output must have its named consumer and a failure behavior. At every boundary, distinguish source present, tests run, source accepted, runtime bound, actual consumer read, and independently accepted capability.

### Rollout and rollback design requirements

The first operational deployment, if later authorized, should add a read-only qualification/shadow path that does not silently change existing rankings, score inputs, macro basis, account state, or user decisions. Consumer-visible qualification can be rolled back through the existing release path while retaining captured evidence. A failed qualification must not trigger an automatic substitute source, purchased entitlement, or retry plane.

Historical repair is a separate, explicit output: preserve old result identifiers, describe which assumptions were wrong, produce corrected results under a new experiment/artifact identity, and keep the old no-promotion or rejection record. Do not make reported historical performance appear cleaner by deleting rows or changing earlier receipts in place.

---

# L. Exact bounded follow-on implementation commission — PROPOSED, NOT EXECUTED

> **Commission title: C5-P0 — Native financial temporal qualification into the existing Decision Snapshot boundary**
>
> You are the later implementation principal for one bounded temporal-integrity slice. The full Commission 5 R2 report in Mastermind PR #1221 is your research input, not authority to assume source custody, buy data, or activate trading behavior.
>
> **Outcome:** For one owner-admitted issuer and one governed direct financial metric, prove that an existing native financial result can enter the existing Portfolio source-receipt/Decision Snapshot boundary only under a declared information-set mode, correct source/system cutoffs, exact generation, qualified availability, and current use rights. Demonstrate ordinary availability, late arrival, revision, withdrawal, unavailable/ambiguous inputs, and invariance of earlier replay after future information is appended.
>
> **First recover, do not rebuild:** Re-pin current protected Mastermind procedure and actual Macro/Terminal source. Reconcile Mastermind #673, Macro #7518, and any modifying financial-query/receipt carriers and pending effects before touching their paths. Preserve #8064/#8312 and other owners unless the admitted slice demonstrably intersects them. An old PR head is evidence, not a source lease. Do not repeat refused actions through alternate actors or silently clear unresolved effects.
>
> **Architecture:** Reuse the native Fundamental Forensics/Calcbench source, period, mapping, revision-selection and query receipt owners. Do not implement generic filing arbitration in Portfolio. Reuse the existing S0 v1 source receipt, canonical serializer, immutable snapshot boundary and payload limits. Rich source clocks remain in native referenced receipts. Where a required distinction cannot be represented, obtain an owner-approved versioned contract change or return a typed non-admission; do not loosen closed validation.
>
> **Source and rights:** Prefer existing lawfully retained source evidence and synthetic adversarial fixtures. The source owner selects the issuer/metric before acceptance results are inspected. Require exact accession/context/units and capture/availability evidence for any real source example. Treat SEC acceptance as acceptance, not guaranteed public publication. New historical downloads, FRED/ALFRED software/model use, commercial samples, procurement and redistribution require separate existing-owner rights authorization; this commission supplies none by itself.
>
> **Bounded data:** One issuer, one direct metric, at least two meaningful source versions and a withdrawal/conflict fixture. Use the native typed period and one clearly specified economic interval. This is not a mandate to expand the metric catalog, calendarize every issuer, build a peer browser, or complete all Calcbench Wave 3B work. If actual retained real-source versions are unavailable, the source limitation is part of the result; never manufacture an original vintage.
>
> **Permitted work after admission:** The smallest native adapter/validation and test changes needed to qualify this result and feed the existing consumer. Acquire an isolated workspace through current procedure. Freeze an exact allowed-path set with the actual source owners; research path suggestions are not modifying authority. Use test-first development and independent review under current procedure.
>
> **Ordered execution:**
> 1. Produce the exact source/consumer/rights/custody admission receipt and compatibility matrix.
> 2. Add discriminating RED tests for the relevant E/H obligations, preserving positive controls and all existing owner policies.
> 3. Implement only the admitted native adapter/qualification gap; keep production behavior unchanged unless separately authorized by its release owner.
> 4. Exercise the native source response through the existing receipt/snapshot consumer with identical artifact identities. No synthetic test may be reported as a live source-to-consumer proof.
> 5. Apply all forty H2 cases at the appropriate owner boundary, or document why a case belongs to an unmodified downstream family and retain it as an explicit later gate. The slice must cover T01–T25 and T30–T40 where relevant to the financial source, receipts and replay; it must not claim universal family qualification from this slice.
> 6. Run the existing owning suites, validate the no-effect boundary and obtain non-coauthor exact-head review. Reconcile current-base movement under protected review-reuse rules, not by repeatedly merging master for cosmetic freshness.
> 7. Return for source/consumer acceptance. No production, ranking, portfolio or trading activation occurs solely because tests or review pass.
>
> **Required proof:** Exact source and candidate heads; changed-path list; native source/query and consumer schema versions; query modes and cutoffs; mapping and generation references; RED/GREEN outcomes; semantic mutation evidence; original/revised/withdrawn result identities; future-append invariance; failed-poll/unknown-clock/missing-value behavior; rights disposition; bounded byte/row coverage; no new persistence or authority plane; independent reviewer disposition; required exact-head/current-base checks; and actual runtime/consumer proof only if separately authorized and actually performed.
>
> **Hard non-goals:** No new warehouse, source registry, source publisher, correction queue, temporal ledger, experiment registry, portfolio book, scheduler, worker fabric, retry plane, browser alternate fetch, paid source, or opaque confidence score. Do not modify portfolio account/fills/NAV/targets/pending orders, retune a detector, consume a protected holdout, or change source/score/trade authority. Do not replace the incumbent S0 or financial query program.
>
> **Stop/refuse conditions:** Unresolved custody or effect; unsupported source availability; unknown required rights; absent immutable generation; incompatible schema; incomplete necessary source inventory; unsafe version conflict; inability to demonstrate real consumer binding. Complete source-independent tests/documentation where safe, but report the exact unproven capability and owner gate rather than inventing success.
>
> **Acceptance boundary:** The slice is development-complete only after its defined tests and independent review pass on the exact candidate. It is source-accepted only under the existing owner process. It is operationally qualified only after authorized actual producer-to-consumer proof. Those are distinct receipts. Completing this slice does not mean all Commission 5 families or the broader Portfolio V3 program are complete.
>
> **Return:** One durable result on the admitted existing carrier, with the exact evidence above, limitations and one concrete next dependency. Preserve the original report, old historical results, incumbent source custody, and all prior no-promotion decisions. Do not execute the next phase without its required owner admission.

---

# Appendix 1. Reproducible characterization of the existing helper

The following is a **research verification recipe**, not production implementation or a proposal to change the helper. It uses only a byte-verified local copy of the existing Macro module at the pinned audit commit. The seven observed results are reported in B3. The recipe deliberately distinguishes behavior characterization from a claim that the API should perform every downstream obligation.

```python
from hashlib import sha256
from pathlib import Path
import runpy

# Supply the already-authorized local copy of the pinned source; no network read.
source = Path("lib/dataos/temporal.py")
expected = "4415404186f0b0d2870f42d9e4a0b95be87937863adf30cf015ed34e8bf92b67"
assert sha256(source.read_bytes()).hexdigest() == expected
module = runpy.run_path(str(source))
profile = module["TemporalProfile"]
read = module["as_of_filter"]
cutoff = "2026-01-15T12:00:00Z"
row = {
    "id": "original", "value": 100, "revision_seq": 0,
    "period_end": "2025-12-31T00:00:00Z",
    "published_at": "2026-01-01T12:00:00Z",
    "ingested_at": "2026-02-01T12:00:00Z",
}
cases = [
    ("C1", [row], profile.REVISABLE_RELEASE),
    ("C2", [dict(row, ingested_at="2026-01-02T12:00:00Z"),
             dict(row, id="revision", value=80, revision_seq=1,
                  published_at="2026-01-10T12:00:00Z",
                  ingested_at="2026-01-11T12:00:00Z")],
     profile.REVISABLE_RELEASE),
    ("C3", [{"id": "partial", "published_at": "2026-01-01T12:00:00Z"}],
     profile.REVISABLE_RELEASE),
    ("C4", [{"id": "expired", "served_at": "2026-01-01T12:00:00Z",
              "expires_at": "2026-01-02T12:00:00Z"}], profile.INTELLIGENCE),
    ("C5", [dict(row, published_at="2026-02-01T12:00:00Z")],
     profile.REVISABLE_RELEASE),
    ("C6", [dict(row, published_at="2026-01-01T12:00:00")],
     profile.REVISABLE_RELEASE),
    ("C7", [{"id": "derived", "computed_at": "2026-01-01T12:00:00Z"}],
     profile.DERIVED),
]
for case_id, rows, kind in cases:
    try:
        print(case_id, [value["id"] for value in read(rows, cutoff, kind)])
    except (module["TemporalError"], module["PointInTimeError"]) as error:
        print(case_id, type(error).__name__)
```

Observed IDs/exceptions in order: `['original']`; `['original', 'revision']`; `['partial']`; `['expired']`; `[]`; `TemporalError`; `PointInTimeError`.

# Appendix 2. Research acceptance and residual proof ledger

| Required commission component | Delivered here | Not implied |
|---|---|---|
| A–L full recommendation | Executive decision, source census, state of art, landscape, contracts, features, owner map, validation, risks, priorities, phases and exact future commission | Implementation approval |
| Current protected source | Explicit immutable procedure and inspected source pins, plus prepublication delta record below | A continuously current live estate |
| Duplicate/adjacent work | S0, financial lineage, prospective revisions, historical membership, observability and analyst-history carriers reconciled at source-metadata level | Writer custody transfer |
| Temporal semantics | Modes, version policies, uncertainty, corrections, withdrawal, identity, missingness, generation and rights rules | Deployed universal enforcement |
| Deterministic/model responsibilities | Admission and numerical logic deterministic; models bounded to interpretation/candidate extraction | Model-generated facts or clocks |
| Honest replay and leakage program | Forty future cases, positive controls, mutation obligations, sensitivity and prospective protocols | Forty implementation tests executed or any alpha backtest |
| Empirical evidence this pass | Seven unchanged-helper characterization cases | Live data correctness or market-performance estimates |
| Source diligence | Primary documentation with specific PIT cadence/history and current rights caveats | Vendor samples, contracts, purchases or licensed data admission |
| Final publication | Same-path replacement on the same PR, followed by remote exact-byte verification | Merge, deployment or protected architectural acceptance |

Unresolved proof questions are assigned, not hidden: the **source owner** must certify current materialized vintage/inventory and channel clocks; the **financial and S0 owners** must reconcile detailed implementation/custody and actual adapter compatibility; the **rights owner** must determine exact allowed use; the **runtime/consumer owner** must prove actual generation consumption; the **experiment owner** must admit any historical or forward study; the **independent reviewer/release owner** must accept a later candidate. No new implementation work was assigned to these owners by publishing this research.

The Research Vault product-code identity is resolved to the Macro namespace; a separate local upstream checkout/remote and the live private capture estate were not certified. The private Executive DR repository identity is recorded separately. No proprietary documents, vendor datasets, or private raw captures are reproduced here.


# Appendix 3. Source register and reference scope

Repository references use the immutable audit pins. PR links are carrier references; the observed heads/states are frozen in B4, and a future reader must recheck their live state. R10 establishes current search-visible schema/source presence only; its full service implementation was not recertified. R17 and R21–R24 establish adjacent source/architecture context, not exhaustive executable-path acceptance. R09 is an existing build/acceptance docket: its historical test counts and scope are attributed to that docket, not to this pass.

Public references P01–P22 were reviewed on 2026-10-04. P08 is a historical vendor methodology paper; current SKU/schema/rights must be reconfirmed. P09–P11 and P20 are vendor descriptions, not authenticated delivery or price quotes. P04, P21 and P22 are original research/author-hosted research records; their general methodological conclusions do not substitute for Mastermind-specific results. No proprietary dataset, source corpus, or substantial vendor text is reproduced.

[R00]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1221
[R01]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/sol_skills/INDEX.md
[R02]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/loop/fundamentals.py#L29-L112
[R03]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/collectors/edgar.py#L470-L717
[R04]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/collectors/edgar_facts.py#L194-L355
[R05]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/research/MASTERMIND_TEMPORAL_DATA_STANDARD.md
[R06]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/lib/dataos/temporal.py
[R07]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/collectors/fred.py#L139-L264
[R08]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/engine/pit.py#L223-L381
[R09]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md
[R10]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/engine/fundamental_forensics/query_service.py
[R11]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md#L660-L710
[R12]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md
[R13]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/658
[R14]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/673
[R15]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/brain/signal_history.py#L1-L96
[R16]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/loop/single_name_panel.py#L103-L124
[R17]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/scripts/midsmall_pit.py
[R18]: https://github.com/mastermindx-market-intelligence/macro/pull/8403
[R19]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/collectors/equity_revisions.py#L288-L509
[R20]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/portfolio/held_risk.py#L734-L837
[R21]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/portfolio/lenses.py
[R22]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/brain/research_desk.py
[R23]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/research/TREND_PERSISTENCE_PROTOCOL.md
[R24]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/source_thematic_rotation_framework.md
[R25]: https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/1c708450187755160e1a5889b69598a2fcb1f0d1/terminal/app/api/company-intelligence/%5Bsymbol%5D/route.ts
[R26]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/engine/research_vault/__init__.py
[R27]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/data/census/CENSUS.md#L1-L9
[R28]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/.gitmodules
[R29]: https://github.com/mastermindx-market-intelligence/macro/pull/7518
[R30]: https://github.com/mastermindx-market-intelligence/macro/pull/8064
[R31]: https://github.com/mastermindx-market-intelligence/macro/pull/8312
[R32]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1224
[R33]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1223
[R34]: https://github.com/mastermindx-market-intelligence/macro/blob/617c5818b0493e1843c652be881f72cbebfac123/research/alpha_intelligence/expectation_market_dynamics/VEND_0_INSTITUTIONAL_ESTIMATES_BAKEOFF_2026-08-23.md
[R35]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/brain/bottleneck.py
[P01]: https://docs.xtdb.com/about/time-in-xtdb.html
[P02]: https://learn.microsoft.com/en-us/sql/relational-databases/tables/temporal/overview?view=sql-server-ver17
[P03]: https://docs.databricks.com/aws/en/delta/vacuum
[P04]: https://www.philadelphiafed.org/the-economy/macroeconomics/a-real-time-data-set-for-macroeconomists
[P05]: https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists
[P06]: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
[P07]: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
[P08]: https://insight.factset.com/hubfs/Resources%20Section/White%20Papers/ID11996_point_in_time.pdf
[P09]: https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates
[P10]: https://www.lseg.com/en/data-analytics/asset-management-solutions/portfolio-management/backtest-your-portfolio-performance
[P11]: https://www.lseg.com/en/data-catalogue/company-data/ibes-estimates/broker-estimates
[P12]: https://www.sec.gov/about/webmaster-frequently-asked-questions
[P13]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
[P14]: https://databento.com/docs/standards-and-conventions/common-fields-enums-types
[P15]: https://databento.com/docs/standards-and-conventions
[P16]: https://fred.stlouisfed.org/legal/
[P17]: https://ec.europa.eu/eurostat/web/euro-indicators/information-data
[P18]: https://ec.europa.eu/eurostat/cache/metadata/en/euroind_vtg_esms.htm
[P19]: https://www.bundesbank.de/en/statistics/time-series-and-real-time-data/-/macroeconomic-real-time-database-622290
[P20]: https://databento.com/pricing/
[P21]: https://www.nber.org/papers/w20592
[P22]: https://escholarship.org/uc/item/4w1110bb

# Appendix 4. Final source-drift and research verification record

Prepublication repository recheck: **2026-10-04T08:33:24Z**. Protected Mastermind advanced to `17b9fa1363db6071d338be3373a4fdb11fc0076d`; Macro main advanced to `0bbc246fe1c023684bb36ae2ac7795668eafef97`. Terminal and the separately identified Executive DR vault remained at the audit pins. Macro main and the Executive DR vault main were observed unprotected; no branch-protection change was made.

The complete Mastermind comparison contained one managed-multi-repository-workspace commit changing 18 files. It did not change the cited temporal/fundamental/Portfolio sources or the governing Skillpack files. All seven consumed procedure files were then reloaded at the newer protected pin and byte-compared with the audit pin: unchanged. This supplies current publication procedure without rewriting the historical evidence cut.

The Macro comparison covered six intervening commits, including China source-provenance work, rendered pages, and nightly Prophet artifacts. Its file list reached GitHub's 300-file comparison limit, so absence from that list was **not** treated as exhaustive proof. Ten load-bearing temporal/financial/revision source and research files were fetched individually at the new Macro head and compared byte-for-byte with the audit copies: all unchanged. Nightly outcome/artifact contents were not read or evaluated in this pass. This is bounded source compatibility, not an all-estate or runtime recertification.

| Rechecked Macro source | SHA-256 at both audit and prepublication pins |
|---|---|
| `lib/dataos/temporal.py` | `4415404186f0b0d2870f42d9e4a0b95be87937863adf30cf015ed34e8bf92b67` |
| `research/MASTERMIND_TEMPORAL_DATA_STANDARD.md` | `2b258fa8830c90ae41121557f4ed76561a7fdf5b8f52426fda326b5a2c53adf2` |
| `collectors/fred.py` | `f130d871b605f1c1d40105fb2ec46645464dce6ff2ea465c7c24d4d5e06ef849` |
| `engine/pit.py` | `c2f98b3034b86f260189de5ed6a1b683a8945ccd49787adf6180687a2e92ac44` |
| `collectors/edgar_facts.py` | `d6a3d9ed27abdf7572cd41ac190a226dca775045389bb71270b568483ba8f2c0` |
| `collectors/edgar.py` | `d6e3be060fc7ade17e31551795f25806ac414fe5ec7988c31039acc9c7dbba7c` |
| `collectors/equity_revisions.py` | `3e949c96d82da19fd6e42da9a1697f05d13d8897c2b6eabc7808f54b8431b0eb` |
| `scripts/midsmall_pit.py` | `25707aaca30ebfb133ed69f2c8201703427abc52a7893fd61112a3495a5b4ed9` |
| `research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md` | `d8ab6c4c36c0fea0de5bb4aec4b32fcae3d4d9e489cce2d7419c55523b3fb72f` |
| `research/alpha_intelligence/expectation_market_dynamics/VEND_0_INSTITUTIONAL_ESTIMATES_BAKEOFF_2026-08-23.md` | `040e7c8980a4e11a9c3ec273c53fce21605f17e8cf0ed6d3cf18a32942dee9a6` |

The author's integrated-document review clarified three potentially misleading edges before publication: separate historical source/system/reconstruction clocks; historical result identity versus present access revocation; and date-vintage interval/sentinel conversion. A formatting review separated adjacent reference labels so citations cannot resolve accidentally to a neighboring source. These are author hardening checks, not an independent implementation review.

Publication verification is reported on the same PR against the immutable uploaded commit: complete A–L structure, defined references, forty future case IDs, seven observed characterization cases, executable recipe consistency, original-input hash, balanced Markdown structure, and exact remote content identity. These checks do not certify production, vendor rights, historical dataset coverage, or investment performance.

**Research boundary:** the requested replacement research and proposed follow-on commission are complete as documents; broader implementation and production qualification remain unexecuted. The next action is owner acceptance of this research, followed by fresh custody/rights admission for section L—not another greenfield temporal platform.
