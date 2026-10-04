# Commission 12 — Sector-Specific Physical & Operational Telemetry
## Hardened research, architecture, and implementation masterplan

**Version:** 2.0 — independently re-censused hardening, 2026-10-04  
**Status:** RESEARCH_COMPLETE / IMPLEMENTATION_PROPOSED / PRODUCTION_INERT  
**Scope:** research and documentation only; no source purchase, live data mutation, deployment, empirical promotion, or portfolio authority.  
**Evidence companion:** [Audit and primary-source ledger](02_AUDIT_AND_SOURCE_LEDGER.md).

This is the complete replacement recommendation for the supplied Commission 12 report, not a short supplement. The supplied report's economic framing is retained; changes to its census, source qualifications, priorities, temporal semantics, validation, and follow-on scope are explicit in the companion's A01–A20 disposition table. Nothing here supersedes protected source law or an incumbent owner's accepted experimental freeze.

## A. Executive conclusion

### A.1 What Mastermind should build

Build a **Sector Physical Truth Spine as a small extension of existing Macro measurement and artifact owners**, not a greenfield alternative-data platform and not six parallel ingestion programs. Its product is an inspectable, historically reproducible bridge:

> physical or operational observation → evidenced company exposure → operating KPI forecast → earnings transmission → expectation comparison → separately tested market or risk information.

The word truth names an ambition for measurement provenance, not certainty. A survey estimate, an announced facility, a modeled visit forecast, and a measured shipment are different evidence types. They must never acquire equivalent standing because they pass through the same schema.

The current estate already has an EIA petroleum collector, a physical-balance display, a power-scarcity engine, and a generation-queue collector. The principal gaps are release-vintage preservation, consistent measurement semantics, company exposure, truthful coverage, and incremental validation—not the total absence of physical signals. The correct first move is to reuse and harden those owners. [M03](02_AUDIT_AND_SOURCE_LEDGER.md#m03) [M04](02_AUDIT_AND_SOURCE_LEDGER.md#m04)

### A.2 The investment case must remain conditional

A better operating forecast can be useful without predicting excess returns. Physical observations may already be priced, describe an industry rather than an issuer, or improve risk diagnosis instead of return ranking. Build priority therefore follows economic interpretability, existing-owner reuse, admissible history, and the ability to disprove a mechanism—not the number of impressive datasets available.

The recommended first program contains **two bounded, admission-gated pilots**:

1. **Energy/refining:** preserve EIA release vintages around the incumbent collector, then test whether regional or national operating observations improve a prespecified issuer-throughput forecast beyond what the current oil-balance owner already provides.
2. **Industrial/rail operations:** qualify STB carrier-service observations, then test a narrow productivity/cost bridge to a prespecified carrier operating KPI. This is preferable to assuming a free, complete, carrier-specific AAR history. Actual STB fields, publication timing and issuer mapping must pass qualification before implementation proceeds.

**AI/datacenter power is a parallel prospective source-qualification track, not an immediately backtestable company signal.** Separate generation/storage queues from load requests, planned from energized capacity, and bulk grid load from datacenter-attributable demand. Existing public process material does not establish the desired company-level large-load history. [S03](02_AUDIT_AND_SOURCE_LEDGER.md#s03) [S04](02_AUDIT_AND_SOURCE_LEDGER.md#s04) [S05](02_AUDIT_AND_SOURCE_LEDGER.md#s05)

All six sector maps remain in scope for the end-state architecture. Only the first two families enter the initial implementation recommendation; other sectors have explicit later admission gates.

### A.3 What this audit materially changes

The uploaded report was too expansive at P0 and too generous about reusable historical infrastructure. The newest protected Mastermind research records previously used confirmation dates and states that a recently built sector substrate contains current-as-of labels rather than era-correct historical sectors. Neither a `HOLDOUT_START` constant nor PIT membership makes those labels or dates newly eligible for confirmation. [M06](02_AUDIT_AND_SOURCE_LEDGER.md#m06) [M08](02_AUDIT_AND_SOURCE_LEDGER.md#m08)

The checked-in power queue is still a **2023 seed with a July 2026 collection timestamp**. This is a direct example of why acquisition freshness cannot substitute for source vintage. LBNL's current source describes generation/storage requests and excludes load interconnections; relabeling it as AI load would be a semantic error, not a missing feature. [M04](02_AUDIT_AND_SOURCE_LEDGER.md#m04) [S05](02_AUDIT_AND_SOURCE_LEDGER.md#s05)

The revised decision is: **approve the architecture for bounded research acceptance; do not interpret publication of this report as permission to implement, purchase, deploy, backtest restricted outcomes, or promote a feature.** The exact conditional implementation commission is Section L.

## B. Current-state census

### B.1 Source identity and method

The audit pinned Mastermind `master` at **`521720b09be2921e996d9396b522b1c4ca62041c`**, Macro `main` at **`79251a22d731cf3f7e8d8ba2185bfcd0e9bb098f`**, and Terminal `master` at **`1c708450187755160e1a5889b69598a2fcb1f0d1`**. Mastermind's branch endpoint reported protection. The relevant protected INDEX and procedure material were read from the same Mastermind revision. These are source pins, not deployment attestations. [M01](02_AUDIT_AND_SOURCE_LEDGER.md#m01)

Current-state terms are deliberately bounded: **SOURCE_PRESENT** means inspected code exists; **ARTIFACT_OBSERVED** means bytes were inspected; **RECORDED_RESULT** means an incumbent document reports a result; **SPEC_ONLY** describes a specification; **NOT_ESTABLISHED** means the audit did not prove a capability. No component is labeled production-proven from code alone.

### B.2 Existing owners, actual gaps, and no-rebuild boundaries

| Area | Inspected owner or artifact | Evidence state | What exists | Actual gap / Commission 12 action |
|---|---|---|---|---|
| External petroleum collection | Macro `collectors/eia.py` | SOURCE_PRESENT | Historical XLS parser and partial-failure handling | Returned series lack release-vintage fields; wrap the owner rather than duplicate it. |
| Oil physical context | Macro `engine/commodity_supply_context.py`; `research/OIL_PHYSICAL_TIGHTNESS.md` | SOURCE_PRESENT / RECORDED_RESULT | Seasonal inventory anomalies, cover, neutral balance display and prior score-rejection rationale | Require same-cut operands, coverage disclosure, vintage-safe features and increment beyond this incumbent baseline. |
| Power physical context | Macro `engine/power_scarcity.py` | SOURCE_PRESENT | Output/utilization/price/queue legs and display bands | Legs mix measurement types, available-leg means change composition, and tight-only logs are not a full opportunity panel. |
| Generation queue | Macro `collectors/lbnl_queue.py`; `data/eia/interconnection_queue.json` | SOURCE_PRESENT / ARTIFACT_OBSERVED | Collector, configured URL override, dated seed and stale disclosure | Committed seed remains through-2023; source-year, edition-year and collector time require distinct treatment. |
| Artifact seam | Mastermind `config/contracts.yml`; Macro synapse references | SOURCE_PRESENT | Explicit owner, consumers, allowed effects, freshness and degradation | Telemetry must become a bounded research artifact through the existing seam, not a second control plane. |
| Company decision matrix | Mastermind `portfolio/lenses.py` | SOURCE_PRESENT | Inspectable lens rows; confluence and authority distinctions | Adding a context row is not automatically production-inert. P0 does not enter this path. |
| Bottleneck reasoning | Mastermind `brain/bottleneck.py`; Macro power owner | SOURCE_PRESENT | RS-anchored order-layer reasoning plus separate Macro physical context | Preserve existing owners; measured constraints may later support or contradict RS rather than equating RS with physical truth. |
| Research proposals | Mastermind `brain/research_desk.py` | SOURCE_PRESENT | Causal research and falsifiers feeding existing gated proposals | No P0 telemetry in armed prompts or proposal consumers. |
| Earnings expectations | Mastermind `portfolio/held_risk.py` | CURRENT-PIN SEARCH EVIDENCE | Revision-direction fields are consumed | A field such as `est_chg_30d` does not establish historical analyst-vintage depth. |
| Fundamental and price research | Mastermind `loop/fundamentals.py`, `loop/single_name_panel.py` | SOURCE_PRESENT | Availability-date lookup, deep/delisted union and explicit hygiene policies | Underlying data, label precision, corporate actions, clipping, membership and holdout use still require experiment-specific qualification. |
| Decision memory | Mastermind `brain/signal_history.py` | SOURCE_PRESENT | KEEP-FIRST daily ticker records | Daily first-read memory does not preserve all intraday releases. Producer vintage records must be referenced, not squeezed into overwriting daily rows. |
| Outcomes | Prediction, outcome and shadow owners named by protected research | OWNER REFERENCES VERIFIED | Existing grading conventions | Reuse and separately qualify exact owner contracts; do not invent a telemetry outcome ledger. |
| V3 evidence architecture | Protected Portfolio V3 design | SPEC_ONLY record; full current runtime NOT_ESTABLISHED | Approved independence/claims/snapshot architecture | Do not infer current production readiness from the design or infer all later code is absent. |
| Research Vault | Macro catalog/corpus/ingestion/UI paths; Terminal estate | SOURCE DISCOVERY | Research-document workflows in more than Terminal alone | Documents are not canonical physical observations, nor permission to mine/rehost proprietary broker text. |
| Observability | `data/census/CENSUS.md`, contract metadata | ARTIFACT OBSERVED | Generated census and contracts | Dates remain July 16 and July 6 respectively. Do not hand-edit generated files or use old counts as current runtime evidence. |

Evidence: [M02](02_AUDIT_AND_SOURCE_LEDGER.md#m02)–[M11](02_AUDIT_AND_SOURCE_LEDGER.md#m11). Runtime health, complete historical row coverage, and downstream deployed consumption were not measured in this research run.

### B.3 Adjacent work to reconcile before implementation

Existing oil physical-balance and carry research is a binding baseline, not a source of convenient features to repackage as new discovery. The prior oil score decision is recorded research; Commission 12 did not reproduce its statistics. Macro power scarcity and its queue collector own incumbent measurements, while Mastermind's bottleneck owner interprets order-layer context. The WTI transmission/explorer program, conditional-fusion research, release-calendar owner and China project-capacity research are adjacent carriers to consult, not rewrite. [M03](02_AUDIT_AND_SOURCE_LEDGER.md#m03) [M10](02_AUDIT_AND_SOURCE_LEDGER.md#m10)

Existing Theme/Neural Web identities and issuer relationships must be reused where their contracts are adequate. `entity_exposure` below is a proposed evidence extension or materialized view of those owners, not permission to create a new company identity graph. If ownership cannot be reconciled, implementation stops at a contract proposal.

Phrase and branch searches did not establish an exact existing Commission 12 carrier. That supports a new **documentation** carrier, not a claim that the estate lacks physical telemetry. Search results also included host-resource telemetry and proprietary Research Vault reports; neither is a canonical sector observation source.

### B.4 Preliminary hypotheses adjudicated

The estate clearly contains substantial existing financial, price, macro and alternative-context consumers, but this audit does not certify the completeness of every originally listed options, ownership, fund, news or political dataset. Those families are existing controls to qualify, not invented clean panels.

The historical analyst-revision, individual-stock flow and fine-grained dynamic-theme gaps remain **not established as solved** within the inspected evidence. The protected research explicitly warns against fabricating those histories. A current revision consumer or current theme membership cannot settle the question. [M07](02_AUDIT_AND_SOURCE_LEDGER.md#m07) [M11](02_AUDIT_AND_SOURCE_LEDGER.md#m11)

The most important new constraint is historical identity and data reuse: the current preregistration explicitly documents current sector labels and consumed confirmation dates. Commission 12 must not recycle them under a new name or call a current classification historically effective. [M08](02_AUDIT_AND_SOURCE_LEDGER.md#m08)

## C. State-of-the-art research and architectural implications

### C.1 Treat telemetry as real-time measurement, not a factor shopping list

The relevant methodological precedent is release-aware nowcasting: information arrives at different times, frequencies and revision states, and each release's contribution depends on what was already known. The inspected Federal Reserve nowcasting research supports this framing; it does not demonstrate issuer or stock-return predictability for Commission 12. [S17](02_AUDIT_AND_SOURCE_LEDGER.md#s17)

Use native-frequency observations and explicit forecast origins. A monthly orders release, weekly service report and hourly grid observation should not be converted into a retrospectively smooth daily panel and then treated as simultaneous new information. A held value can be displayed between releases, but its age and original release identity must remain visible; repeated daily rows do not become repeated independent evidence.

Start with a seasonal/issuer baseline and a parsimonious deterministic bridge or regularized regression. Consider mixed-frequency distributed lags, state-space models or hierarchical partial pooling only when a prespecified baseline fails in a way those methods address. Complexity must win out of sample and preserve input-vintage provenance. A large model cannot repair absent release timestamps or unidentifiable company exposure.

### C.2 The economic transmission must be an explicit model

An observation may affect volume, realized price, mix, input cost, utilization, working capital, or capital recovery. These channels can offset. For example, a capacity expansion can raise output while depressing price; greater traffic can increase sales but require discounts; a utility's load growth may not translate immediately into retained margin. The mechanism is therefore a vector of KPI effects, not a mandatory positive/negative stock label.

Keep an inspectable decomposition such as:

`revenue = relevant units × realized price`,

`operating profit = revenue − variable costs − fixed operating costs`,

with explicit scope, fiscal period, foreign-exchange basis, and exposure uncertainty. These are proposed accounting bridges, not estimated coefficients. Company-specific coefficients require filing evidence and subsequent validation.

### C.3 Separate independent measurement from independent economic information

Two vendors may observe overlapping payment transactions. A rail series may explain part of a materials shipment series. Oil stocks, backwardation and producer shares may reflect one common shock. Multiple publishers and model summaries do not create independent votes.

Preserve both **measurement lineage**—raw source, contributor panel, transformations, shared inputs—and **economic dependence**—which common demand/supply factor or transmission path could drive the observations. Independence is evaluated conditionally through incumbent-baseline comparisons, ablations and exposure tests, not asserted by a family name.

### C.4 Financial discovery requires an experiment budget

The factor-discovery literature motivates accounting for all attempted constructions, horizons and selection decisions. A nominally significant feature found after many trials is not a clean confirmation. [S18](02_AUDIT_AND_SOURCE_LEDGER.md#s18)

The appropriate architecture includes a frozen manifest and a durable attempt receipt in existing research governance. It does not need a new experimentation platform. The manifest records selected source versions, transforms, KPI targets, lag rules, controls, missingness policy, model selection, horizons, labels, admissible dates and stopping rules before confirmation is accessed.

### C.5 Institutional source quality is multidimensional

A vendor can have excellent granularity but weak original-vintage retention, or a useful history but unacceptable derived-data rights. Government data can have long histories yet revised-latest downloads; exchange inventories can have good clocks but restrictive usage terms. Select the smallest source portfolio that resolves a specific economic uncertainty with admissible history, not the source with the largest advertised coverage.

## D. Source landscape and admission decisions

### D.1 Qualification vocabulary

**DOC:** official methodology/product documentation inspected. **ARTIFACT:** actual data bytes inspected. **CANDIDATE:** named lead without sufficient primary qualification in this audit. **HOLD:** a required right, clock, mapping or schema remains unproved. A DOC source is not yet automatically admitted for implementation.

Cost classes are **public access**, **subscription**, or **enterprise/quote-only**. They are planning classes, not prices. Total cost also includes mapping, corrections, monitoring, retention, legal review and exit portability. No precise commercial quotation was obtained.

| Source / evidence | Coverage | History | Frequency and latency | PIT quality | Corrections | Rights | Cost class | Best use / decision |
|---|---|---|---|---|---|---|---|---|
| EIA WPSR; DOC, incumbent adapter present | Petroleum stocks, refinery operations, supply | Long series; original-vintage depth must be reconstructed and checked per series | Weekly; scheduled release, holiday and delivery-channel differences | Conditional on actual first-release receipts | Estimates and releases can change | Agency/API/reuse policy; verify chosen archive use | Public access | P0 energy pilot through incumbent collector, not a new energy platform. [S01](02_AUDIT_AND_SOURCE_LEDGER.md#s01) |
| EIA electric operating data; DOC | BA demand/forecast, generation, interchange; capability and sales at other frequencies | Series-dependent historical bundles | Hourly observations; ingestion cadence differs by route | Native operating history is not proof of every first vintage | Forecast updates, reporting corrections | Public API subject to terms | Public access | Prospective grid baseline; not firm-specific AI demand. [S02](02_AUDIT_AND_SOURCE_LEDGER.md#s02) |
| STB rail-service reports; DOC, sample HOLD | Carrier operational measures | Archives and rule-dependent coverage | Weekly; filing and public posting are different days | Potentially strong with archived publication identity | Restatements and metric-definition changes need versioning | Public agency reports; chosen retention/use still documented | Public access | Second P0 pilot only after workbook and issuer-map qualification. [S03](02_AUDIT_AND_SOURCE_LEDGER.md#s03) |
| ERCOT large-load process; DOC/indexed notice | Process, eligibility and verification status information | New regime; no complete project history established | Event/process-driven | Public project-level feed not proved | Stage changes and verification central | Public forms do not authorize access to restricted submissions | Public documents; detailed feed unknown | Prospective source inquiry only; no promised historical queue collector. [S04](02_AUDIT_AND_SOURCE_LEDGER.md#s04) |
| LBNL Queued Up; DOC plus incumbent seed ARTIFACT | Transmission generation/storage requests, not load | Annual editions; current retrospective dataset not same as old editions | Annual publication, data through prior year | Requires original edition retention | Retrospective project/status changes | CC BY 4.0 attribution to LBNL and GridTracker | Public access | Repair source semantics and vintage handling through incumbent owner later. [S05](02_AUDIT_AND_SOURCE_LEDGER.md#s05) |
| Fed G.17; DOC | Industrial production and capacity utilization | Long, classification dependent | Monthly releases and revisions | Archived releases useful; exact timing still qualified | Preliminary, monthly and benchmark revisions | Public source; underlying definitions retained | Public access | Industrial controls and revision fixtures, not direct issuer utilization. [S06](02_AUDIT_AND_SOURCE_LEDGER.md#s06) |
| ALFRED/FRED; DOC | Vintage delivery for supported series | Per-series vintage availability | Date-granular vintage access, not necessarily intraday release | Strong tool only where original-vintage coverage exists | Real-time periods expose changes | Upstream rights remain applicable | Public API access subject to terms | Reconstruction tool, never universal PIT certificate. [S07](02_AUDIT_AND_SOURCE_LEDGER.md#s07) |
| Census M3; DOC | Nominal orders, shipments and inventories | Long, with taxonomy breaks | Monthly | Archive-first, not latest-series backfill | Revisions and seasonal/classification changes | Public agency materials | Public access | Industrial demand/backlog controls; not transformer unit counts. [S08](02_AUDIT_AND_SOURCE_LEDGER.md#s08) |
| Census retail; DOC | Industry sales/inventory benchmarks | Long program, non-homogeneous regimes | Monthly advance and later estimates | Retain actual release vintage | Population, benchmark and classification changes | Public agency materials | Public access | Consumer-panel calibration; not company sales. [S09](02_AUDIT_AND_SOURCE_LEDGER.md#s09) |
| Baker Hughes; DOC | Rig activity by supported geography/type | Long archive; exact metric coverage to qualify | Weekly/monthly products | First-publication reconstruction needed | Historical corrections/definition changes | Public download is not blanket redistribution permission | Public access; intended rights review | P1 activity control unless a prespecified energy bridge needs it. [S10](02_AUDIT_AND_SOURCE_LEDGER.md#s10) |
| WSTS/SIA/ESIA; DOC | Billings; licensed units, product, region and ASP detail | Product-specific long histories/editions | Monthly, delivery after reference month | Original report editions and averaging conventions required | Product classification and report revisions | Internal-use/redistribution distinctions explicit | Public summary plus subscription | P1 unit-versus-price decomposition; public billings descriptive first. [S11](02_AUDIT_AND_SOURCE_LEDGER.md#s11) |
| SEMI fab products; DOC | Capacity, construction, ramps, equipment plans | Commercial history and forecasts; version access unknown | Quarterly product updates | Must retain forecast editions and late corrections | Project schedules/size revisions are substantive data | User-tier and enterprise contract; machine use unknown | Subscription/enterprise | P1 after fab exposure and a bounded sample contract. [S12](02_AUDIT_AND_SOURCE_LEDGER.md#s12) |
| LME; DOC | Warehouse stocks, warrant states and market prices | Product and delay tier dependent | Daily/delayed; off-warrant methodology changed | Route-specific vintages and licensing needed | Stock adjustments and reporting changes | Derived/non-display/distribution rights separately evaluated | Public views plus licensed products | P1 materials; no blanket P0 permission to archive or distribute. [S13](02_AUDIT_AND_SOURCE_LEDGER.md#s13) |
| USGS cement; DOC | Regional production/shipments | Historical reports, series specific | Monthly, actual release lag to measure | Original reports useful; revision policy to qualify | Survey revisions and archive migration | Public agency material; retain attribution/terms | Public access | P1 direct tons→issuer volume pilot candidate. [S14](02_AUDIT_AND_SOURCE_LEDGER.md#s14) |
| Consumer Edge Apollo; vendor DOC | Merchant transaction panel | Vendor advertises history from 2014; vintage history unproved | Advertised daily/multiple delivery routes | Panel and mapping vintages unqualified | Contributor/methodology/merchant revisions | Contract, retention, model and derived rights unknown | Enterprise/quote-only | One bounded consumer pilot, not production procurement approval. [S15](02_AUDIT_AND_SOURCE_LEDGER.md#s15) |
| Placer.ai; vendor DOC | POI/chain traffic, same-store and forecast products | Historical panel vintages not established | Multiple aggregation frequencies | Cohort and forecast/observed separation required | Device, POI and panel changes | Commercial terms not obtained | Enterprise/quote-only | Traffic decomposition only where incremental to transactions. [S16](02_AUDIT_AND_SOURCE_LEDGER.md#s16) |
| AAR/BTS, PMI providers, AISI/Worldsteel | Freight, surveys, steel activity | CANDIDATE: exact product histories unqualified here | Usually periodic; verify product calendar | Do not inherit PIT from reputation | Publication and methodology specific | Public summaries versus paid detail distinguished | Public/subscription, unresolved | Later official/industry baselines, not certified company feeds. |
| TrendForce; FreightWaves/DAT; Earnest/Circana | Memory prices, truckload data, consumer panels | CANDIDATE: no licensed sample in this audit | Product-specific, no certified latency | Unknown original-vintage/panel fidelity | Must contract for correction methodology | Commercial intended-use rights unknown | Quote-only | P1 comparative diligence only when an economic bridge is specified. |
| DC Byte/Baxtel; CBRE/JLL; Dell'Oro/Omdia | Facilities, market capacity, network/product shipments | CANDIDATE: no complete PIT facility/product history established | Event/quarterly products, verify | Planned/shipped/installed/operating stages differ | Restated facilities, product and project estimates | Research publication is not underlying database license | Quote-only or public reports | P1/P2 after power and facility definitions. |
| Kpler/Vortexa; CME; physical-price vendors | Shipping, market curves, assessed commodity prices | CANDIDATE: product-specific archives | Faster data often licensed; verify | Inference and exchange correction rules distinct | Cargo relabeling, contract-roll and benchmark revisions | Retention, derived and redistribution contracts essential | Subscription/enterprise | P2 shipping; existing market-price controls first. |

Candidate-only rows are a diligence backlog, not assertions that every named product supplies all listed capabilities. Their unresolved fields and the exclusion of proprietary report copying are explicit in the [source ledger](02_AUDIT_AND_SOURCE_LEDGER.md#5-candidate-only-sources-and-explicit-diligence-debt).

### D.2 Procurement decision rule

Before recommending purchase, require a lawful sample, data dictionary, stable IDs, representative old and new releases, original-subscriber versus restated-history policy, correction/retraction feed, measured route latency, panel/methodology history, and an intended-use schedule. The schedule must separately address storage, quantitative research, inference through external LLM providers, model training, derived metrics, customer display, export and termination.

Choose one commercial measurement family at a time. A second vendor can test measurement robustness, but overlapping panels do not supply a second independent vote. Reject a feed that is merely a repackaging of prices or issuer results while marketed as new physical evidence.

A successful public aggregate alpha test is **not an absolute prerequisite** for a granular vendor sample: the aggregate may fail because it cannot isolate a firm's exposure. The exception requires a precise, preregistered reason granularity should resolve the failure, a lawful bounded sample and a public/issuer comparator. It is not permission to buy first and search for a profitable story afterward.

## E. Canonical data model and temporal semantics

### E.1 Six logical contracts, not six new services

Retain the supplied plan's six useful logical contracts. Implement them, if accepted later, as extensions of existing producers, registries and research artifacts. Do not assume a new database, message bus, scheduler, graph service or control plane is required. A versioned file/Parquet projection and immutable receipt manifest may be sufficient for the first pilots; storage selection belongs to the implementation owner after size and rights are known.

The required invariant is that a result can be reconstructed from **the exact values, definitions, mappings, entitlements and model state available at its cutoff**, not simply from today's dataset with an old date filter.

### E.2 Clocks and time precision

| Field | Required meaning | Common invalid substitution |
|---|---|---|
| `period_start`, `period_end` | Measurement interval for a flow, average or accounting period; timezone and boundary convention explicit | Calling a weekly average an instantaneous Friday event |
| `event_time` | Physical event instant when meaningful; nullable for interval estimates | Fabricating one event timestamp for all survey observations |
| `as_of` | The state/reference date or report-as-of to which the source's observation refers | Using collection time as economic reference date |
| `published_at` | Actual source publication time, with evidence and precision | Using a planned release calendar as actual availability |
| `available_at` / `known_at` | One canonical source-availability clock, under a specified channel and entitlement; aliases must agree | Dating bulk-file access at the agency's earlier release time |
| `observed_at` | First time Mastermind's collector encountered those bytes | Backdating a new collector's observation into old history |
| `ingested_at` | Durable landing time | Pretending download success means the record was admitted |
| `admitted_at` | Time validated data became usable by the designated consumer | Using later validated data in an earlier actual replay |
| `effective_from`, `effective_to` | Half-open valid-time interval for a mapping, identity or definition | Assigning today's ownership to all previous periods |
| `knowledge_from`, `knowledge_to` | When that version was known; independently versioned from valid time | Backdating a subsequently discovered relationship |
| `correction_generation` | Local immutable lineage sequence for a logical observation | Treating highest ingestion counter as latest valid source revision |

Store UTC instants and the original timezone, including daylight-saving interpretation. Date-only sources carry `availability_lower_bound`, `availability_upper_bound`, `time_precision` and `timing_basis`. A conservative upper bound can permit end-of-day/next-session research; it cannot support an intraday event claim. Unknown bounds are a historical admission failure, not an opportunity for an LLM to invent a time.

Do **not** impose `known_at >= event_time` universally. Forecasts and planned capacity can legitimately be known before the event period. They must be tagged as forecasts/plans with a forecast-origin vintage. A future-dated actual observation without a valid explanation is quarantined. The original plan's requested clocks are preserved; these additions remove ambiguity rather than replacing them.

### E.3 Replay modes

Three modes must never be pooled without labels:

**ACTUAL_SYSTEM_REPLAY:** all required source observations, entity links, metric definitions, rights and model versions were observed, ingested and admitted by the consumer cutoff. The snapshot proves what Mastermind actually had. Later corrections and later-known mappings are excluded.

**PUBLIC_ARCHIVE_RECONSTRUCTION:** the original public release and its lawful historical availability can be evidenced, but Mastermind did not necessarily collect it then. This can answer a separately admitted historical research question about information it could have possessed. It cannot be represented as an actual past Mastermind decision. Revised-latest downloads alone do not qualify.

**EX_POST_DESCRIPTION:** only today's revised history, current labels or later mappings exist. Such data may describe an economy or debug schemas, but cannot support a historical predictive claim.

Newly acquired proprietary subscriber histories are not automatically admissible counterfactual feeds. Initial P0 confirmation does not use hypothetical historical subscriptions. A later research owner would need explicit approval, historical service-tier/availability and original-version evidence, lawful retrospective use, and a separately labeled estimand. This prevents a marketing claim of PIT coverage from silently bypassing the commission's possession constraint.

### E.4 `physical_observation.v1`

Minimum logical fields:

```text
observation_id, logical_observation_key, source_id, source_record_id,
source_release_id, source_revision_id, supersedes_observation_id,
metric_id, metric_definition_version, sector_family,
subject_type, subject_id, geography_id, product_id,
value, value_status, lower_bound, upper_bound,
unit_dimension, unit, scale, currency, price_basis,
measurement_kind, frequency, aggregation_basis, seasonal_adjustment,
period_start, period_end, event_time, as_of,
published_at, available_at, timing_basis, time_precision,
availability_lower_bound, availability_upper_bound,
observed_at, ingested_at, admitted_at,
effective_from, effective_to, knowledge_from, knowledge_to,
correction_generation, vintage_id, methodology_version,
source_receipt_id, quality_flags, retraction_state
```

`measurement_kind` is a closed vocabulary: **measured_quantity, survey_estimate, nominal_monetary, market_price, modeled_estimate, forecast, planned_capacity, status_transition**. Units also state stock/flow/rate/ratio semantics. Zero, suppressed, missing, stale, not applicable and unavailable are distinct states. Never serialize an unknown numeric value as zero.

An observation ID binds source, logical metric-period-subject identity, source version and payload hash. A retried identical download produces the same record; an economic revision produces a new version. Late arrival of an older publication does not supersede a newer source revision simply because it has a larger local generation. Conflicting revisions without a resolvable source order are quarantined.

Retractions have explicit lineage. A withdrawn value can remain reproducible in a past lawful decision snapshot while becoming inadmissible for new decisions. Contractual deletion obligations still control retained content; preserve tombstone/provenance metadata only where permitted. Append-only design is not a license to retain prohibited data forever.

### E.5 `source_receipt.v1`

```text
source_receipt_id, source_id, source_release_id,
endpoint_or_product, delivery_channel, request_parameters,
retrieved_at, http_status_or_delivery_receipt,
published_at_evidence, payload_hash, content_length,
raw_blob_pointer_or_retention_tombstone,
collector_version, parser_version, schema_version,
source_methodology_version, timing_precision,
entitlement_id, entitlement_valid_from, entitlement_valid_to,
use_permissions, retention_rule, export_rule,
license_evidence_ref, correction_policy_ref
```

Request parameters and receipts must exclude API secrets, cookies and personal data. `use_permissions` is a typed matrix, not one `rights_ok` boolean. Raw blobs reside only in a lawful storage location; public GitHub stores research documents, synthetic fixtures or expressly redistributable material, not purchased datasets or broker corpora.

A payload hash proves byte identity, not truth, authorized use or timeliness. A receipt with a hash but no applicable right or publication basis remains blocked.

### E.6 `metric_definition.v1`

The registry supplies canonical name, measurement kind, unit dimension and scale, numerator/denominator, product/geography scope, native calendar, aggregation rule, seasonal convention, expected release and revision policy, source priority, freshness budget, missingness vocabulary, and lineage/dependence tags. Definitions are versioned with knowledge time.

Examples of hard rejection: treating nominal M3 orders as transformer units; using a manufacturing-utilization fallback under a utility-utilization metric; joining MW and MWh; mixing fiscal and calendar quarters; treating a three-month moving average as an unsmoothed monthly observation; or filling a missing actual with a forecast. A fallback is admissible only under an explicit definition-compatible rule, otherwise it is a different metric.

Source priority does not mean latest-arriving wins. Retain competing observations as distinct and expose disagreements. The canonical view is a governed selection over immutable inputs, not deletion of inconvenient versions.

### E.7 `entity_exposure.v1`

This is an extension/view over the incumbent identity and relationship owners. It contains issuer ID/CIK, security ID, facility/project/product/region identifiers, metric and KPI IDs, exposure type, direction, materiality basis, denominator, weight or interval, evidence references, valid-time and knowledge-time intervals, and correction lineage.

Separate **legal owner, economic beneficiary, operator, supplier, customer and minority/JV exposure**. Ticker strings are display aliases, not durable issuer identities. A facility's nameplate capacity, economic ownership share and supplier revenue share are not interchangeable weights.

Weights may be unknown. An unmapped load increase remains regional context; it must not be spread across an AI-power basket as if each constituent had disclosed exposure. A later-discovered supplier relationship cannot be inserted into earlier snapshots. P0 starts with a small filing-supported issuer cohort, not a universal supply-chain graph.

### E.8 `kpi_transmission_model.v1`

```text
model_id, version, issuer_or_peer_scope, metric_ids, kpi_id,
mechanism, expected_sign_conditions, lag_structure,
features_and_transform_versions, controls, missingness_policy,
training_period, training_data_manifest, training_label_available_cut,
fit_at, available_at, selection_manifest, code_digest,
parameter_values_or_artifact_hash, uncertainty_method,
validation_state, allowed_use, falsifiers
```

The model and its normalization statistics must themselves be PIT. Training is restricted by when labels became available, not merely by the fiscal period they describe. A model fitted today is not historically available unless it is explicitly a walk-forward fit reconstructed under the approved research protocol.

A coefficient or probability is not entered merely because a frontier model offered a plausible narrative. P0 uses reproducible deterministic estimation. Structural relationships whose sign changes with margin or capacity conditions encode those conditions rather than forcing one directional score.

### E.9 `operational_evidence_snapshot.v1`

Contains snapshot ID, experiment/decision cutoff, replay mode, issuer, sector family, source-observation IDs and hashes, metric-definition versions, exposure versions, model version, feature values, KPI estimate and interval, baseline estimate, expectation source or missing reason, coverage/age/revision/reliability states, contradictions, dependence metadata, authority ceiling and source receipts.

No mandatory composite score exists. For one company the snapshot can state: volume improving; realized-price comparison missing; capacity additions adverse to industry pricing; issuer exposure partial; consensus unavailable. These are useful separate facts.

Later approved integration attaches immutable references to the existing decision owner. It does not replace KEEP-FIRST history, invent a second outcome ledger, or make every source revision a new investment decision.

## F. Sector-native derived intelligence and economic transmission

The following are **falsifiable proposed bridges**, not measured predictive findings. Each source must pass D/E before its numerical observations or transformations can enter a research result.

### F.1 Energy — first pilot

| Metric | Company KPI bridge | Earnings relationship | Sign/lag and principal falsifier | Admission |
|---|---|---|---|---|
| Refinery net inputs / utilization | Region-weighted or, where justified, national activity → issuer throughput | Throughput × realized unit margin, less operating costs | Throughput often contemporaneous with the quarter; margin may offset volume. Fails if company maintenance/exposure explains all apparent increment. | P0, reuse EIA owner; regional granularity only if actually available and mapped. |
| Crude/product inventories and cover | Physical balance → regional margin/working-capital environment | Can affect realizations, feedstock cost and storage economics in opposing ways | Seasonal draws are not automatic positive earnings or returns; revisions/timing may erase apparent surprise. | P0 explanatory inputs only where within the frozen metric budget. |
| Rig counts | Basin/type activity → service demand and later production | Service revenue and fixed-cost absorption; production response depends on productivity/completions | Positive activity channel is conditional, not fixed barrels per rig. | P1 unless the pilot's registered target requires it. |
| Gas storage / LNG operational volumes | Regional gas balance or terminal utilization → volume and contract exposure | Commodity realizations versus tolling/contract revenue differ | Weather, maintenance, nominations and contract design can dominate. | P1. |
| Crack/calendar spreads | Market pricing control, not physical observation | Approximate margin/carry environment, not issuer realized margin | Equity and commodity reaction may already price the physical release. | Reuse qualified incumbent market data; do not count as independent physical proof. |

Sources and incumbent boundaries: [M03](02_AUDIT_AND_SOURCE_LEDGER.md#m03), [S01](02_AUDIT_AND_SOURCE_LEDGER.md#s01), [S02](02_AUDIT_AND_SOURCE_LEDGER.md#s02), [S10](02_AUDIT_AND_SOURCE_LEDGER.md#s10).

The initial target is a company's **full-quarter refinery throughput at a fixed forecast origin**, not a manufactured EPS estimate. A disclosed capacity/exposure bridge is required before a national observation becomes an issuer feature. If only national context can be supported, the artifact remains national context. Company-specific margins, outages and product mix are explicit controls or missingness disclosures, not LLM-imputed values.

### F.2 Industrials and freight — second pilot

| Metric | Company KPI bridge | Earnings relationship | Sign/lag and principal falsifier | Admission |
|---|---|---|---|---|
| Carrier speed / terminal dwell, if confirmed in admitted STB workbooks | Network fluidity → asset turns, service productivity and cost | Lower operating cost for a given traffic/mix may improve operating ratio | Congestion may reflect stronger demand; better speed may reflect weak volume. Direction conditional on demand/mix. | P0 source qualification then one fixed operating-KPI test. |
| Rail carloads/intermodal units | Carrier/category movements → traffic volume | Units × revenue per unit, less fuel/labor/network costs | Route length, modal shifts, pricing and acquisition changes can break the relationship. | P1 AAR or issuer source qualification, not assumed free STB volume coverage. |
| Truck tenders/rejections/rates | Panel demand/capacity → carrier utilization/yield | Loaded miles, price and empty-mile costs determine profit | Contributor and lane mix, contract share and fuel surcharge can dominate. | P1 bounded commercial sample only. |
| M3 orders/unfilled orders/shipments | Industry nominal demand/backlog → issuer order or shipment context | Backlog conversion and margin, net of cancellations | Inflation and long-cycle aircraft/defense orders can mimic volume acceleration. | P1 public control with vintage and category mapping. |
| G.17 utilization / PMIs | Industry output utilization or survey diffusion → operating backdrop | Fixed-cost absorption hypothesis, not observed issuer margin | Aggregate/survey measures may add nothing beyond issuer disclosures. | P1 controls; PMIs are survey evidence, not physical quantities. |
| Port loaded/empty TEUs | Port flow → local logistics demand | Throughput and capacity-cost exposure | Transshipment, port substitution and empty containers break total-TEU attribution. | P2 normalized port definitions. |

Sources: [S03](02_AUDIT_AND_SOURCE_LEDGER.md#s03), [S06](02_AUDIT_AND_SOURCE_LEDGER.md#s06), [S08](02_AUDIT_AND_SOURCE_LEDGER.md#s08); other entries remain candidate-only under D. The proposed primary target is a comparably defined **issuer operating ratio**, forecast before quarter end. Different accounting definitions require a documented reconciliation or exclusion. This pilot does not promise that the agency's service dataset alone predicts revenue.

### F.3 AI and datacenter — high strategic importance, prospective qualification

| Metric/state | Company KPI bridge | Earnings relationship | What must not be inferred | Priority |
|---|---|---|---|---|
| Actual grid demand, weather/calendar normalized | Attributable demand → utility MWh sales | Sales, tariff, marginal cost, rate recovery and financing determine earnings | BA-level load growth is not proven datacenter load or a specific supplier order. | Prospective baseline qualification. |
| Large-load project stage transitions | Verified project maturity → future utility/customer demand | Connection timing affects sales, infrastructure use and capital recovery | Requested, approved, contracted and energized MW are different states; private submissions are not a public feed. | P1 only after lawful project data demonstrated. |
| Generation/storage queue | Potential supply and grid investment pipeline | Conditional generation/equipment opportunities | Not load requests; total queued GW is not expected realized capacity without a validated transition model. | Reconcile incumbent LBNL owner. |
| Commissioned, energized and occupied datacenter capacity | Usable capacity → billable/occupied capacity | Occupied deliverable capacity × contractual economics | Shell MW, IT MW, facility MW and metered MWh are not interchangeable; PUE is not constant by fiat. | P1 facility disclosures/sample. |
| Transformer/switchgear orders and backlog | Supplier product/territory exposure → backlog conversion | Volume, price and capacity determine revenue and margin | Aggregate electrical-equipment dollars do not reveal transformer units or lead times; orders may precede energization by years. | P1; public aggregate context first. |
| Network/optical shipments and accelerator deployments | Shipped units → installed/qualified capacity, subject to inventory | Vendor revenue depends on recognition, ASP/mix and channel terms | Shipment is not deployment; installed accelerator counts cannot be inferred mechanically from power load. | P2, no synthetic GPU census. |
| Cooling content/installations | Density/design and commissioned projects → supplier shipments | Content per installation and margin | Design win, order, delivery and revenue recognition are distinct. | P2. |

The operative state model is a **typed set of source-attested transitions**, not a universal linear funnel. Projects may withdraw, resize, split, merge or regress. Store project identity and change lineage. Estimate energization probabilities only after sufficiently representative outcome data and a frozen model exist; do not assign probability one to projects that later survived. [M04](02_AUDIT_AND_SOURCE_LEDGER.md#m04) [S02](02_AUDIT_AND_SOURCE_LEDGER.md#s02) [S04](02_AUDIT_AND_SOURCE_LEDGER.md#s04) [S05](02_AUDIT_AND_SOURCE_LEDGER.md#s05)

### F.4 Semiconductors

| Metric | Company KPI bridge | Earnings relationship | Confounder/falsifier | Priority |
|---|---|---|---|---|
| Product billings versus units/ASP | Addressable segment → unit demand versus price/mix | Revenue decomposition, not one generic cycle score | Currency, product migration and share changes dominate aggregate billings. | P1; public billings descriptive, licensed unit detail separately qualified. |
| Wafer shipment area / wafer starts | Input demand or fab activity → supplier/fab volume | Volume and utilization affect fixed-cost absorption | Shipment area is not starts; wafer diameter, node, yield and inventory differ. | P1 if exact series is qualified; no automatic substitution. |
| Fab capacity/ramp/move-in milestones | Facility/product exposure → qualified production capacity and tool demand | Ramp, qualification and spending recognition determine revenue | Nominal capacity is not usable yield or utilization; export restrictions and project deferrals matter. | P1 SEMI or issuer evidence. |
| Memory contract and spot prices | Product-weighted realized ASP → revenue/gross margin | Operating leverage conditional on cost and mix | Spot market is marginal; generic quotes may not represent company contract realizations. | P1 bounded methodology/sample gate. |
| Lead times/inventories/utilization | Orders/stock imbalance → future shipments and cost absorption | Pricing power or correction risk | Vendor estimates derived from revenues/prices may be circular evidence. | P1/P2, audit methodology. |
| HBM / advanced-packaging capacity | Qualified bottleneck throughput → memory/packaging/downstream volume | Scarcity rents and shipment limits | Booked, nameplate and qualified capacity differ; yield and customer certification matter. | P2. |

Sources: [S11](02_AUDIT_AND_SOURCE_LEDGER.md#s11), [S12](02_AUDIT_AND_SOURCE_LEDGER.md#s12); other product claims are candidates. M3 is not a substitute for fine-grained semiconductor physical data. [S08](02_AUDIT_AND_SOURCE_LEDGER.md#s08)

### F.5 Consumer

| Metric | Company KPI bridge | Earnings relationship | Confounder/falsifier | Priority |
|---|---|---|---|---|
| Merchant spending | Covered-channel spend → addressable issuer sales | Sales after refunds/timing/channel mix | Cash, international, B2B and panel changes can dominate; merchant is not always issuer. | P1, one panel first. |
| Customer count × frequency × ticket | Demand decomposition → transactions and realized basket value | Revenue; margin still needs pricing/promotion/mix | Contributor reweighting and identity changes can manufacture growth. | P1 if data supports each component. |
| Same-store foot traffic | Comparable visits × independently calibrated conversion/ticket → store sales | Volume versus promotional profitability | Visits are not purchases; same-store growth omits openings/closures. | P1 only if incremental to transactions. |
| POS units and realized prices | Product/retailer coverage → sell-through and share | Net realized price × units; wholesale sell-in lag differs | Retailer coverage, promotions, private label and SKU migration. | P1 bounded sample. |
| Channel inventory / out-of-stock | Sell-through and stock → replenishment or markdown pressure | Future orders and gross margin | Website availability is not verified distribution-center inventory. | P2. |
| Web/app activity and projected visits | Attention or model forecast → hypothesis for future demand | No direct earnings relationship without conversion evidence | Bots, paid marketing and forecasts mislabeled actuals. | P2/context; explicitly typed. |

Use Census retail as an industry calibration control, not a numeric filler for a missing company panel. Report same-store and total-company targets separately. Structural breaks in panel composition must remain visible even if a vendor retrospectively smooths the history. [S09](02_AUDIT_AND_SOURCE_LEDGER.md#s09) [S15](02_AUDIT_AND_SOURCE_LEDGER.md#s15) [S16](02_AUDIT_AND_SOURCE_LEDGER.md#s16)

### F.6 Materials

| Metric | Company KPI bridge | Earnings relationship | Confounder/falsifier | Priority |
|---|---|---|---|---|
| Exchange on-/off-warrant stocks by location | Deliverable local availability → scarcity/pricing context | Producer realization or processor input costs | Financing, warehouse transfers and warrant status are not final demand. | P1 rights-gated LME. |
| Production, shipments and utilization | Regional product volume → issuer tons/units sold | Price × volume minus variable/fixed costs | Production is not shipment; import substitution and ownership geography matter. | P1 official/industry source qualification. |
| Cement regional shipments | Relevant territory → issuer volume | Tons × realized price with local freight and energy costs | Weather, acquisition changes and distribution radius. | P1 USGS candidate bridge. |
| Physical premiums / treatment charges | Product/region terms → realized price or conversion margin | Effects differ for miners, smelters and downstream users | Assessed benchmarks versus transactions; contract lags and hedges. | P1 after license and methodology sample. |
| Capacity/outages and freight | Asset event → lost/added saleable volume | Utilization, fixed cost and working capital | Nameplate, equity share and economic ownership differ. | P1/P2 issuer/regulatory evidence. |
| Futures curve / cash spreads | Market expectation/control | Carry and marginal scarcity pricing | Not independent physical evidence; inventory and price may be one shock. | Reuse existing market owners. |

Sources: [S13](02_AUDIT_AND_SOURCE_LEDGER.md#s13), [S14](02_AUDIT_AND_SOURCE_LEDGER.md#s14); unqualified benchmark/industry products remain candidates.

### F.7 Deterministic work before LLM reasoning

Deterministically validate source permissions and payloads; resolve approved IDs; normalize dimensions and scales; link revisions; establish admissible time bounds; align native calendars and fiscal periods; select PIT mappings; compute trailing-only baselines and seasonal changes; quantify missingness, staleness and coverage; apply frozen KPI models; and compare against a pre-release baseline. Every output carries its inputs and code version.

A **physical surprise** is a release minus the forecast available before that release. It is not simply year-over-year growth. An **expectation gap** requires a separately qualified expectation vintage. An internal seasonal nowcast is not Street consensus; unavailable consensus is stated as unavailable.

Cheap LLMs may classify source text, summarize methodology changes, propose evidence-backed entity candidates, or explain deterministic anomalies. Unstructured extraction remains a candidate with a quoted source span; values, dates and joins are not admitted until rule-based or reviewed verification succeeds. LLMs may not originate numerical observations, manufacture historical availability, backfill missingness, select contradictory source values by plausibility, or confer authority.

Frontier reasoning is reserved for ambiguous mechanisms, contradictory observations and second-order falsifiers—for example, whether power demand and supplier orders imply a bottleneck migration or merely different project timing. Its output distinguishes **observed, derived, inferred, speculative and unknown**. No LLM path writes authoritative physical rows or changes portfolio behavior.

## G. Mastermind integration map

| Producer | Canonical owner/artifact seam | Evidence family | Initial consumer | Later separately accepted consumer |
|---|---|---|---|---|
| Existing EIA adapter plus receipt extension | Macro collection/store conventions and versioned research projection | `physical_energy_balance` | Isolated KPI research | Existing evidence/decision snapshots by reference |
| Qualified STB source, only if no incumbent found | Macro collection conventions; bounded research artifact | `physical_freight_industrial` | Isolated carrier-KPI research | Existing research/prediction owners |
| Existing power/LBNL plus qualified grid sources | Macro power/measurement owners | `physical_power_datacenter`, with generation/load subtypes separate | Prospective source and attribution study | Existing bottleneck interpretation owner |
| WSTS/SEMI/issuer product data | Macro source normalization | `physical_semiconductor_cycle` | Segment/KPI study | Existing research evidence owner |
| Census plus one qualified consumer panel | Macro external-data owner | `physical_consumer_demand` | Coverage/nowcast study | Existing company evidence owner |
| USGS/LME/issuer material data | Macro external-data owner | `physical_materials_inventory` | Material/KPI study | Existing evidence owner |
| Approved source snapshots | Mastermind incumbent decision-memory contract | Namespaced observations and contradictions | None in live P0 | `brain.signal_history` or accepted successor references |
| Realized financial/market outcomes | Existing prediction/outcome/shadow owners | Outcome truth | Authorized research only | Existing calibration/attribution |
| Research documents | Existing GitHub/Vault document workflows | Research provenance, not numeric source truth | Human/orchestrator review | Read-only document presentation |

The architecture is producer-owned collection, consumer-owned interpretation, and incumbent-owned portfolio authority. `config/contracts.yml` and its Macro producer declarations are the seam. A later contract must name an allowed effect and concrete consumers; there is no generic promotion by being called a physical family. [M02](02_AUDIT_AND_SOURCE_LEDGER.md#m02)

P0 artifacts are not registered into live lenses, confluence, prompts, rankings, eligibility, alerts, sizing, fills or risk gates. Read-only inputs can still alter an armed model's recommendations, so isolation includes prompt/context reachability, not only write permissions. [M05](02_AUDIT_AND_SOURCE_LEDGER.md#m05)

## H. Empirical validation program

### H.1 Three distinct claims, three distinct outcomes

**Measurement claim:** the data is correctly typed, source-bound, lawful, and available as represented.

**Economic claim:** at a fixed forecast origin, it improves the operating KPI it purports to measure beyond issuer seasonality and incumbent information.

**Market/risk claim:** after information available at the chosen decision time, it improves a prespecified forward return or downside forecast. This is not yet a portfolio-profit claim.

A measurement pass and an economic null can end the program. An economic pass and market null can justify descriptive use. A risk-only pass advances only as risk information. Inadequate power is **INCONCLUSIVE**, not a successful null or grounds to search indefinitely for a better horizon.

### H.2 Pilot manifest and bounded experiment budget

Before reading confirmatory labels, freeze the following proposed first program:

| Dimension | Energy pilot | Rail pilot |
|---|---|---|
| Source family | EIA petroleum, through incumbent adapter | STB carrier service, contingent on qualification |
| Scope ceiling | At most 3 prespecified metric definitions; at most 6 filing-qualified issuers | At most 3 prespecified metric definitions; at most 6 filing-qualified issuers |
| Primary operating target | Comparably defined full-quarter refinery throughput | Comparably defined full-quarter operating ratio |
| Primary forecast origin | 28 calendar days before the issuer's fiscal quarter end, using only then-available information | Same rule |
| Development model budget | Seasonal/issuer baseline and no more than 2 prespecified augmented model forms | Same ceiling |
| Confirmation selection | Exactly one model/configuration selected without confirmation outcomes | Same rule |
| Market target, if separately admitted | 20-trading-session SPY-relative total return | Same rule |
| Risk target, if separately admitted | 90th-quantile forecast of 60-session maximum drawdown depth | Same rule |

These values are **proposed engineering/research constraints**, not empirically established optimal horizons or calibrated commercial return hurdles. An implementation owner may not tune them after viewing confirmation. Any justified change is reviewed and frozen before that access.

The confirmatory budget is **2 families × (1 KPI + 1 return + 1 risk claim) = 6 potential primary tests**, with no more than **2 augmented model forms per family in development**. Unrun or blocked primary tests are retained as untested, not replaced with winning alternatives. The manifest records every development attempt; family names do not conceal transform/vendor trials. Section H.5 specifies a conservative multiplicity rule over the six planned primary hypotheses.

Company selection uses disclosed operating relevance, comparable reporting, stable identifiers and available mapping evidence before outcome inspection. Current winners, familiar AI beneficiaries, or companies selected because their historical stocks performed well are not an admissible cohort rule.

### H.3 Measurement and history admission before modeling

For each source, inspect lawful original releases and current data, reconcile units and field definitions, measure coverage by period and issuer, and document correction policy. Include an actual pair of publication vintages where available. If no real correction pair exists, use a clearly synthetic correction fixture for software semantics and disclose that empirical correction behavior remains unmeasured.

A historical file with many dates is not historical availability proof. If original timing cannot be reconstructed, use only prospective capture. No pre-release query, future mapping, later model, invalid rights interval, or corrected-latest value may pass the replay predicate.

Inspect label provenance separately. Reported company KPI values can themselves be restated; the manifest chooses first reported or later reconciled economic truth and records both clocks. Later outcomes are legitimate labels after they mature, but cannot become training labels before publication. Earnings-release availability may precede the 10-Q; choose a lawful, evidenced source rather than mechanically assigning a filing date to all information.

### H.4 KPI forecast test

Compare the same forecast origins and eligible company-quarters across:

- **B0:** issuer seasonality, prior reported KPI and already-public guidance where qualified;
- **B1:** B0 plus qualified incumbent sector/physical context and ordinary macro/price controls appropriate to the KPI;
- **C:** B1 plus exactly the candidate measurement/bridge improvement.

The candidate must beat **B1**, not a deliberately weak no-data baseline. For energy, this explicitly includes information already exposed by the oil-balance owner. More precise timestamps or better issuer mapping can be valuable, but the measured increment must be attributed to that improvement rather than described as discovery of EIA data.

Primary loss is out-of-sample **MAE in the KPI's economically meaningful units**, with percentage improvement relative to B1. RMSE, signed bias, interval coverage, lead-time stability and missingness are secondary. Avoid MAPE for near-zero denominators. Preserve a common comparison cohort and separately report excluded or unavailable periods.

The independent outcome unit is primarily **company-quarter**, with shared quarter/source shocks respected. Thirteen weekly updates to one quarter's forecast are not thirteen independent realized earnings observations. A separate lead-time analysis can retain all forecast updates, but uncertainty must account for their shared label and overlapping inputs.

Proposed economic advancement requires at least **5% point-estimate MAE reduction**, a multiplicity-adjusted confidence assessment supporting positive improvement, and no unexplained dependence on one issuer/episode or a timing/missingness assumption. This is a proposed materiality floor, not proof that 5% is achievable or universally optimal. Power planning targets 80% power to detect that floor using conservative development-period block dependence; inadequate independent quarters yields INCONCLUSIVE.

### H.5 Statistical design and multiplicity

Use chronological walk-forward development. Purge training observations whose targets are not known before the next forecast cut. Respect the incumbent owner's embargo requirements and any longest-horizon overlap at fold boundaries. Retain one final confirmation read on admitted untouched/prospective dates.

The current protected C1 record makes prior-use and current-sector-label limitations explicit. All previously examined historical dates are development unless a separate untouched-data receipt proves otherwise. Commission 12 does not edit or rerun frozen V2/B2 instruments, import their favorable findings, or call their panel a new holdout. Prospective confirmation is the default where historical reuse cannot be cleanly excluded. [M08](02_AUDIT_AND_SOURCE_LEDGER.md#m08)

Use paired loss differences and calendar/source-release block resampling, preserving issuer clustering. With very few carriers or highly common shocks, do not rely on a large-row-count asymptotic t-test. Date-level/HAC calculations may be useful where their sample assumptions hold, but they do not magically create independent quarters. Report effective block counts, issuer concentration and uncertainty sensitivity.

Apply **Holm family-wise control at 0.05 over the six planned primary tests**, conservatively treating blocked/unrun hypotheses as non-rejections. Gates prevent testing market claims for a measurement- or KPI-failed construction; they do not recycle unused significance budget into new hypotheses. Secondary horizons, variants, interactions and diagnostic charts remain exploratory unless a new prospective preregistration is approved.

Report confidence intervals and economic magnitude, not only pass/fail. Keep failed models, admission failures and null results in the existing research record. A final read cannot be repeated with a changed panel, subgroup or threshold while preserving its original confirmatory label.

### H.6 Market information and downside tests

Define the information set and decision time before testing:

**Release-information question:** did a physical release add information beyond pre-release market/issuer knowledge? Controls must be measured before the release; same-day post-release prices can be mediators rather than valid pre-treatment controls.

**Actionable-after-release question:** after the data was actually available and a realistic processing/execution delay elapsed, does it add anything beyond then-current prices and existing evidence? Post-release price controls are appropriate for this different question. A null here does not prove that the original release contained no information.

For the bounded pilot, the primary return forecast is 20-session SPY-relative total return, assessed by MAE improvement over a price/fundamental/macro baseline. The primary risk forecast uses pinball loss for the 90th quantile of nonnegative 60-session drawdown depth. Baselines include trailing return, volatility, beta, qualified size/fundamentals, incumbent physical context and relevant commodity prices. Each control must be PIT-qualified; missing consensus is not replaced by today's consensus.

Sector controls require era-correct identity, not merely a file with PIT in its name. With a small issuer cohort, cross-sectional rank IC and decile monotonicity are diagnostics only where estimable, not the primary claim. Do not pretend six carrier observations form a deep daily factor universe. Company/family-specific effects and shared shocks require explicit uncertainty.

The same proposed 5% point loss-reduction floor and positive adjusted evidence apply to forecast advancement. Return and risk claims are adjudicated separately. A later translated trading-policy claim additionally needs prespecified turnover, liquidity, capacity, transaction costs, slippage, borrow where applicable, data costs and delayed availability; this research does not authorize that policy or infer profitability from forecast loss alone.

### H.7 Falsifiers and hostile tests

The value claim fails or is demoted when incumbent features explain the increment, the mapping is too weak to predict the operating target, realistic publication latency erases it, the sign depends on one regime without an ex-ante mechanism, or revisions/missingness determine the result.

Run time-shift and impossible-future tests, wrong-exposure negative controls, leave-one-issuer/episode diagnostics, raw-versus-corrected vintage sensitivity, and source-panel break analysis. Negative controls must be selected before confirmation, not chosen afterward to flatter the candidate.

For price labels, audit splits, delistings, stale marks, true tail moves and the effects of clipping/gap policies. The current panel code's hygiene is an explicit choice, not a guarantee that all downside observations are valid. Reuse approved loaders without silently changing frozen experiments; report any label-validity block to their owner. [M06](02_AUDIT_AND_SOURCE_LEDGER.md#m06)

### H.8 Results not supplied by this commission

No new KPI effect size, IC, Sharpe ratio, backtest P&L, vendor ROI or production accuracy is claimed. The output is the research design and source/capability audit. The exact empirical claims remain gated by data, rights, identity, power and prospective confirmation.

## I. Risks, failure modes, and kill criteria

| Failure mode | Required control | Disposition when unresolved |
|---|---|---|
| Latest revised history used as first print | Release lineage and knowledge-cut replay | Historical research HOLD; prospective-only capture may proceed after acceptance. |
| Source timing inferred from calendar | Channel-specific evidence and time bounds | No intraday claim; unknown bounds block historical admission. |
| False issuer attribution | Disclosed effective/knowledge-dated exposure | Retain aggregate context; do not manufacture company coverage. |
| Nominal/forecast/price masquerading as physical quantity | Typed measurement ontology | Reject mislabeled metric or create a separately named evidence type. |
| Current ownership/theme/sector projected backward | Bitemporal mappings and era-correct labels | Historical company/control test blocked. |
| Redundant sources count twice | Upstream lineage, incumbent controls and ablations | Demote duplicate information; second panel can remain measurement QA. |
| Low power disguised as null | Effective outcome counts and pre-read power gate | INCONCLUSIVE; no repeated peeking. |
| Vendor panel or method restates history | Method/version archive and break tests | Segment eras or reject unavailable original vintages. |
| Public access mistaken for permission | Operation-specific rights matrix | Source HOLD; no raw retention/publication or external LLM use. |
| Cheap source already explains value | Cost/increment comparison | Terminate unnecessary commercial pilot. |
| Source lock-in | Export/termination rules and canonical IDs | No procurement recommendation without a viable exit policy. |
| Descriptive artifact affects trading | Consumer and prompt reachability checks | P0 cannot be connected; separate acceptance required. |
| Numeric LLM fabrication | Verified extraction and deterministic transformations | Reject candidate observation/model output. |
| Production health inferred from code | Current runtime/artifact receipts | Capability remains not production-proven. |

**Reject before building** a source with unresolvable rights, no usable source identity, irrecoverable publication history for its proposed historical use, or fundamentally circular price-derived measurement advertised as independent physical truth.

**Stop the issuer bridge** when no lawful evidence supports company exposure. **Kill the KPI construction** on an adequately powered prespecified failure. **Demote to descriptive** if measurement/KPI value exists but no market increment does. **Advance only a risk claim** when only risk survives. **Preserve INCONCLUSIVE** when a valid test cannot yet discriminate. None of these outcomes authorizes widening the project to rescue the thesis.

## J. Build priority

| Priority | Recommended work | Explicit ceiling |
|---|---|---|
| P0 | Source-law and owner recensus; temporal/receipt/metric/exposure contracts; isolated replay tests; two gated energy and rail pilots; bounded coverage/observability evidence | No more than two source families, three selected metrics and six qualified issuers per family in the initial manifest; no live consumer or scheduler changes. |
| P0 research, not P0 feed deployment | AI-power source access, generation/load taxonomy, facility attribution and stale-seed analysis | Prospective qualification; no private project access, synthetic accelerator census, or company-alpha backtest. |
| P1 | Semiconductor units/fab or memory sample; materials official-volume bridge; one consumer panel; qualified grid/facility histories; selected industrial controls | One justified family/sample at a time; rights and incremental-information gates. |
| P2 | Shipping inference, network/optical trackers, advanced packaging/HBM, cooling, detailed project lead times and a second vendor panel | Only after a specific unresolved mechanism and data contract justify granularity. |
| Defer | Historical dynamic subtheme/flow/analyst-revision interactions without canonical vintages; universal facility graph; large multi-country collector program | Do not replace missing histories with current snapshots. |
| Reject | Opaque physical-truth score; queue=energized; nominal dollars=units; forecasts=actuals; revised-latest historical signals; unlicensed copying; second outcome/market-risk/theme authority | No implementation path under this commission. |

This ranking is an architectural recommendation based on reuse and falsifiability, not an empirically measured ranking of expected trading returns.

## K. Phased implementation recommendation

| Gate | Work and accountable role | Deliverable | Exit condition | Blocked path |
|---|---|---|---|---|
| G0 — custody | Later implementation principal with incumbent Macro/Mastermind owners | Current pins, applicable procedures, collision/owner map, allowed paths and data-use ruling | Exact owners and research-only scope accepted | No new adapters, schemas or outcome access if ownership unresolved. |
| G1 — source admission | Data producer owner plus rights reviewer | Two source dossiers, original-release samples, timing bounds, rights matrix, coverage | Selected source/metric/issuer identities and allowed operations evidenced | Drop/hold a failed source; no silent replacement. |
| G2 — temporal foundation | Existing producer engineering owner | Six logical contract extensions, immutable lineage and isolated replay fixtures | All applicable hostile tests below pass; no production reachability | Stop at fixtures if original history cannot be admitted. |
| G3 — economic bridge | Research owner with issuer-KPI evidence | Frozen exposure map, KPI definitions, baseline/candidate model budget and attempt manifest | Targets, sample unit, prior-use and power rules frozen before labels | No returns-first feature selection. |
| G4 — economic evaluation | Authorized experiment owner | Development and one admitted confirmation read, with nulls/coverage | KPI gate adjudicated or INCONCLUSIVE recorded | Failed constructions do not enter market testing. |
| G5 — incremental information | Existing prediction/outcome owner | Separately admitted market/risk comparisons under the same manifest | Correct clocks/controls, multiplicity, adequate power and stable increment | Context remains context; no portfolio action. |
| G6 — advisory proposal | Existing evidence/decision owner | Read-only presentation and immutable-reference integration design | Explicit owner review of authority and consumer impact | No live brain/lens registration merely because a study passed. |
| G7 — later promotion | Separate accepted commission | Policy, cost/capacity, prospective production safety and attribution evidence | Independent release/promotion decision | Outside this research and initial implementation scope. |

Source qualification and conceptual exposure work may proceed in parallel, but outcomes are not opened to keep a worker occupied while identity, rights or scientific gates remain unresolved. Commercial procurement and global expansion are optional later branches, not dependencies needed to finish P0.

### K.1 Required acceptance matrix

These are **specified tests, not tests executed in this research run**. The future implementation must return exact fixtures, commands, results and candidate commit hashes.

| Test | Adversarial input | Required result |
|---|---|---|
| T01 | Decision immediately before actual release | Observation excluded. |
| T02 | EIA bulk bytes arrive after earlier agency release | Bulk consumer cannot use earlier timestamp without evidence of another admitted channel. |
| T03 | STB submission dated Wednesday, public posting later | Filing time never substitutes for public availability. |
| T04 | Date-only source with no intraday proof | Intraday claim blocked; conservative bound explicitly applied where approved. |
| T05 | Later correction changes a historical value | Earlier snapshot reproduces old admitted version unchanged. |
| T06 | Older source release arrives after a newer release | Arrival counter does not regress canonical source revision. |
| T07 | Same payload retried | Idempotent observation/receipt relationship, no duplicate economic evidence. |
| T08 | Equal revision IDs with conflicting values | Quarantine and named conflict; no arbitrary last-write wins. |
| T09 | Retraction | No new use after retraction knowledge; past lawful snapshot reproducible subject to retention rules. |
| T10 | Stock and flow operands from incompatible periods | Feature rejected or explicitly aligned under a frozen rule; no silent latest/latest ratio. |
| T11 | MW versus MWh, percent versus fraction, dollars versus units | Dimensional validation fails the invalid substitution. |
| T12 | LBNL generation queue presented as load queue | Semantic rejection, separate metric identity. |
| T13 | 2023 seed retrieved in 2026 | Source vintage remains 2023; collector freshness does not label measurement current. |
| T14 | Manufacturing utilization offered as utility fallback | Not treated as definition-equivalent without explicit accepted evidence. |
| T15 | Relationship effective earlier but only discovered later | Excluded before its knowledge time. |
| T16 | Current sector labels with `era_correct=False` used historically | PIT-control admission fails. |
| T17 | Recycled ticker or changed issuer/operator | Stable issuer/security/facility identity required; ambiguous join unresolved. |
| T18 | Model trained on a KPI whose report was not yet public | Training row excluded; model manifest records label-availability cut. |
| T19 | Forecast published before its target period | Retained as forecast with origin; never substituted for actual. |
| T20 | Missing/suppressed value or entire source outage | Missing state preserved; no zero, neutral score or apparent negative evidence. |
| T21 | Methodology or panel changes | Version/break retained; no silently homogenized history. |
| T22 | Unknown/expired archive, derived or LLM-use right | Relevant operation blocked; no raw data in public GitHub or unapproved model context. |
| T23 | Thirteen weekly forecasts of one company quarter | One economic outcome cluster, not thirteen independent labels. |
| T24 | Only TIGHT-state incumbent logs available | Cannot claim full-opportunity evaluation without coverage of non-fire states. |
| T25 | Previously consumed holdout relabeled C12 | Prior-use gate blocks confirmation claim. |
| T26 | More source panels with same upstream contributors | Lineage reveals common information; no automatic independent vote. |
| T27 | A telemetry file is added to an armed prompt/lens | Authority-isolation test fails even if all file access is read-only. |
| T28 | Full pilot run | Only allowlisted isolated research paths change; live books, fills, targets, risk and owner-ledger bytes remain unchanged. |

## L. Exact bounded follow-on implementation commission

**Issue only after this research is explicitly accepted. This text is a proposed commission, not an instruction executed by the research author.**

### IMPLEMENTATION COMMISSION — C12 / P0: REUSE-FIRST PHYSICAL EVIDENCE FOUNDATION

**Outcome.** Produce a reproducible, source-bound, correction-safe research artifact that shows whether a small set of physical/operational observations can improve a specified issuer KPI forecast. Complete the bounded foundation and admissible research proof; do not create portfolio authority or a new data/control plane.

**Authority.** This follow-on, when separately issued, authorizes only isolated data-contract, source-admission, adapter-extension, deterministic transformation, receipt, replay-fixture, research-harness and research-document work in explicitly allowlisted paths. It authorizes no commercial purchase, new subscription, live collector schedule, deployment, production source overwrite, portfolio sizing/ranking/gating/execution change, armed-model context injection, or publication of restricted data. Passing a test grants no additional authority.

**Bootstrap and owner gate.** Re-resolve current protected Mastermind and current Macro/Terminal source identities. Read the exact applicable protected INDEX and procedures, not this report's historical pins by default. Record the immutable C12 handoff commit consumed. Inspect the existing EIA, oil-context, power, LBNL, release-calendar, identity/exposure, artifact, decision-memory and outcome owners. Reconcile current adjacent carriers and freezes. Do not create a competing producer, identity registry, theme authority, outcome ledger or market-risk engine. If a current owner conflicts with this proposal, return the exact conflict for adjudication before editing that owner.

**Bounded sources and cohort.** The initial sources are (1) EIA petroleum through the incumbent `EiaAdapter` extension and (2) STB carrier-service data only after actual workbook/schema/publication/rights qualification and a current search for an existing STB owner. The ceiling is three selected metric definitions and six filing-qualified issuers per family. Select them by operating relevance and available provenance before outcomes. Do not silently substitute AAR, a paid vendor, another sector, or a larger universe if admission fails. The AI-power track is a source/semantics dossier only; no project-data harvesting or alpha test is included.

**G1 deliverable.** Return source identity, exact delivery channel, legal-use matrix, original-release examples, available vintage/correction evidence, unit/calendar definitions, time precision/bounds, stable identifiers, issuer-KPI definition/filing receipts, and period/issuer coverage. A current long history without original availability is not admitted historical data. Where lawful public-archive reconstruction cannot be proven, restrict the family to prospective capture after acceptance. Do not fabricate past Mastermind collection times or hypothetical subscription access.

**G2 deliverable.** Implement the minimum six logical contract extensions in Section E using existing storage and ownership conventions. Preserve event/reference, publication/availability, observation/ingestion/admission, valid/knowledge and correction clocks. Add source supersession, idempotency, retraction, dimensional validation, explicit missingness, rights checks and immutable snapshot references. Raw retention follows source contracts; public research artifacts must not contain restricted payloads or credentials. Schemas and synthetic fixtures may be completed without live source collection.

**Isolation.** Use an isolated worktree/branch and research output location under current source-law rules. No scheduler, production configuration, live source-cache or portfolio path is changed. No live consumer imports or armed prompts read the new artifact. Existing KEEP-FIRST decision history is not overwritten or extended with unapproved live inputs. Verify actual consumer reachability; a display/context label alone is insufficient. Any necessary production integration is a separate later acceptance decision.

**G3 research freeze.** Before confirming outcomes, produce the Section H manifest: two families; one primary company-quarter KPI per family; a fixed forecast origin 28 days before fiscal quarter end; baseline and at most two prespecified augmented development models; exact eligible data/cohort; mapping and label availability; prior-use receipt; power rule; missingness and revision policy; and no more than six potential primary KPI/return/risk hypotheses. The report's 5% loss-reduction floor and 80% planning power are proposed constraints to accept or revise before confirmation, never tune afterward. Freeze the final candidate and manifest hash. Respect all current V2/B2/C1 and other incumbent freezes; do not rerun or modify them.

**G4/G5 execution boundary.** Only after rights, data, identity, label-availability, prior-use and power gates are cleared may the authorized research owner execute admitted experiments. Compare against issuer seasonality and qualified incumbent physical context, not a weak empty baseline. Treat company-quarter/release clusters correctly; purge unavailable labels; use declared block uncertainty and Holm control over the six planned primary tests. Market/risk work requires the economic gate and its own admitted information set. Distinguish pre-release information from actionable after-release increment. Never replace missing analyst consensus with current values or later-known sector labels.

**Required proof.** Implement and run every applicable T01–T28 test in Section K. Return exact commands, fixture versions, result counts, candidate SHA and changed paths. A synthetic test verifies implementation semantics, not actual historical vendor fidelity; label it accordingly. Separately demonstrate real-source timing and correction behavior to the extent admitted data supports it. Do not claim deployed health from unit tests, KPI utility from schema tests, or portfolio value from forecast loss.

**Observability.** Publish a bounded research receipt showing source/reference period, original release, latest actual admission, expected cadence, missing periods, revision lineage, semantic/methodology changes, map coverage, rights state and consumer authority ceiling. Separate a fresh collector from a stale source vintage. Reconcile generated census/contracts through their incumbent generator or an explicitly labeled scoped supplement; do not hand-edit generated truth or widen into an estate-wide cleanup.

**Deliverables and acceptance.** Return the source dossiers; ownership/allowed-path map; contract and synthetic fixtures; actual admitted-source sample receipts where lawful; hostile-test report; reproducible replay examples; exposure/KPI registry; frozen experiment and attempt manifest; admitted development/confirmation results if gates permit; explicit nulls, failures and inconclusive outcomes; and a proposed next-family decision. If empirical gates are not met, completion of the bounded foundation must clearly state that no predictive claim is accepted. Do not produce invented statistics to make the delivery look complete.

**Stop rules.** Stop the affected lane and return exact evidence if rights are unknown, timing cannot support the requested claim, an issuer bridge is unverifiable, outcome access would violate a freeze, adequate power is absent, owner custody conflicts, or work requires production authority. Preserve useful independent schema/documentation work within scope, but do not replace a blocked source or reopen outcomes to keep activity going.

**Promotion ceiling.** All accepted output remains research/shadow only. A future advisory integration, vendor purchase, live scheduling change, decision-snapshot attachment or portfolio policy requires a separately accepted commission from the incumbent owner. Do not execute such a commission as part of this one.
