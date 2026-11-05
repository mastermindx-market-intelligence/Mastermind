# Commission 8 — Data Observability, Coverage & Live Census Control Plane

Status: RESEARCH_ONLY / HARDENED_AUDIT / NO_IMPLEMENTATION_EFFECT  
Date: 2026-10-04  
Commission: Data Observability, Coverage & Live Census Control Plane  
Disposition of prior return: REJECT_AS_BUILD_PLAN; salvage selected external-source observations only  
Authority: research recommendation only. This document does not authorize code, deployment, vendor spend, data-source promotion, portfolio behavior changes, or a new control plane.

## Source pins and estate identity

This audit was performed against current source rather than the SHA in the original fan-out.

| Estate | Repository | Branch | Audited revision |
|---|---|---|---|
| Mastermind | mastermindx-market-intelligence/Mastermind | master | 84df29801d4078724c2b603a136de5aa1532cdfe |
| Macro / market-data estate | mastermindx-market-intelligence/macro | main | bb827bd1945505e6d33b5ba86950262ea99e7563 |
| Terminal / charting estate | mastermindx-market-intelligence/mastermind-terminal | master | 9e2f0bd94a2ee876c7dbafacb072414635277a36 |
| Executive research vault | mastermindx-market-intelligence/executive-dr-vault | main | ea422c92bd29800d1f7fb3ae850236cc44d8c890 |

Mastermind protected procedure was pinned at the Mastermind revision above. docs/sol_skills/INDEX.md at that revision enrolls ACTIVE_EXECUTION and SESSION_RELIABILITY; REVIEW_RETURN was also applied because this document audits a returned research artifact.

The executive-dr-vault repository currently contains only its initial encrypted create-only export contract. It is not a data catalog, lineage registry, or market-data health plane.

---

# Audit verdict on the prior research return

The prior return is not safe to implement as written. Its central conclusion — build a new centralized catalog/observability service because Mastermind lacks one — is materially incomplete and conflicts with current source ownership.

The most important missed fact is that the Macro estate already contains a substantial Data OS and output-health architecture:

- config/dataset_registry.yml is a committed dataset contract registry.
- lib/dataos/registry.py defines stable dataset IDs, ownership, producer, storage, grain, temporal profile, status, schema, freshness SLA, quality checks, licensing, code consumers, and a static dataset dependency DAG.
- lib/dataos/quality.py defines deterministic quality checks with explicit severities.
- engine/output_health.py defines mastermind.output_health.v1 and explicitly separates producer health, output health, reader health, blindness, staleness, unavailability, dependency propagation, and exact-versus-upper-bound dependency attribution.
- scripts/build_output_health.py derives the live view on demand and deliberately writes nothing, avoiding a second stale committed health file.
- admin/intelligence_os.py consumes that derived health view.
- scripts/freshness_sentinel.py and other existing quality owners already provide serving-plane observations.

Mastermind itself also already has relevant owners:

- scripts/system_census.py generates data/census/latest.json and data/census/CENSUS.md.
- config/contracts.yml plus control_plane/contracts.py own a set of cross-repo artifact freshness/degradation contracts.
- data_layer/macro_refresh.py enforces freshness anchors and existing FREEZE/ADVISORY degradation semantics.
- brain/portfolio_intelligence.py exposes bounded per-artifact health and refuses to silently promote missing, malformed, undated, or stale artifacts.
- portfolio/conviction.py and portfolio/risk_sizing.py already carry decision-path data-health diagnostics.
- the protected runtime-observability architecture explicitly forbids creating a second runtime health/observability read plane.
- the runtime observability implementation carrier PR #843 is still open and unmerged; it must not be treated as protected implementation.
- Portfolio V3 Decision Snapshot PR #673 is still open Draft; it must not be treated as protected capability.
- scheduler-health PR #777 is still open Draft; it must not be treated as protected capability.
- as-of decision-boundary PR #827 is open and unmerged; it must not be treated as protected behavior.

The prior return therefore made several material errors:

| Finding | Severity | Why it matters | Hardened correction |
|---|---|---|---|
| Missed Macro Data OS registry and output-health system | MAJOR | Makes the proposal greenfield when the estate already has canonical owners | Extend/federate existing owners; do not build another catalog |
| Proposed a central catalog service as a new authority | MAJOR | Violates one-owner/no-parallel-control-plane law | Build a read-only projection over owner-native contracts and observations |
| Treated data health as an investment evidence family | MAJOR | Conflates operational truth with alpha evidence and invites double counting | Data health is a validity/availability precondition and decision receipt, not alpha |
| Proposed Sharpe/predictive lift as the primary validation target | MAJOR | A safety control can be valuable without predicting returns | Validate detection, propagation, abstention/freeze behavior, incident reduction, and false-positive/negative rates |
| Temporal model collapsed multiple clocks into timestamp/as_of | MAJOR | Enables leakage and hides observer-vs-content freshness | Preserve event_time, as_of, observed_at, known_at/available_at, ingested_at, effective interval, correction generation, and measurement/run clocks |
| No explicit blindness state | MAJOR | A failed probe can be mistaken for healthy or missing | Preserve could_not_look / unknown separately from stale and unavailable |
| No coverage-denominator identity | MAJOR | “98% coverage” is meaningless without the expected universe generation | Bind coverage to an expected-universe ID/generation and report missing keys |
| No consumer-read receipt | MAJOR | Producer health does not prove the decision actually consumed healthy bytes | Add a bounded consumer observation/receipt contract |
| Commercial landscape contained stale/incorrect statements | MEDIUM | Vendor selection could be based on wrong product/license assumptions | Use current primary docs; keep vendors optional and subordinate to native owners |
| Suggested broad automatic “pause trading” behavior | MAJOR | This research commission has no trading authority and existing degradation classes differ by artifact | Reuse existing FREEZE/ADVISORY/consumer-specific semantics; no new portfolio rule in this commission |

Specific factual cleanup from the prior source table: OpenMetadata is not a fork of DataHub; “Atlassian Nexus” is not the relevant open metadata product; Apache Atlas, DataHub, OpenMetadata, OpenLineage, Great Expectations, Soda, dbt, Confluent and Datadog solve overlapping but different layers. Their current capabilities and licenses must be verified from primary documentation at implementation time.

The corrected thesis is:

> Mastermind does not need a new authoritative data catalog. It needs a thin, automatically regenerated, point-in-time data-health federation that projects the current truth already owned by Macro Data OS, Mastermind contracts/census, Terminal read surfaces, and existing runtime observability — and makes missing, stale, partial, blind, rights-blocked, corrected, or dependency-degraded data impossible to silently interpret as neutral.

---

# A. Executive conclusion

## Recommendation

Build a small read-only Data Health Federation and Live Census Projection, not a new data platform.

The P0 product should be a compact machine-readable manifest that a session, agent, operator, Decision Snapshot builder, or research consumer can query cheaply without rescanning repositories or filesystems. The manifest is a projection, never the authority. Every field must retain its owner and source receipt.

The projection should answer, for each important asset:

- what it is and who owns it;
- whether the producer is healthy;
- whether the produced artifact exists and is current;
- whether the reader/served copy is current;
- whether the expected universe is complete and which keys are missing;
- what schema/contract generation is active;
- what rights state governs the asset;
- whether a correction/reprocessing generation is active;
- what upstream dependency failures apply;
- which critical consumers have observed it and with what status;
- whether the system was blind and could not establish health;
- what action class the owning contract requires when unhealthy.

This is P0-high importance because it protects every other evidence family from silent invalidity. It is not an alpha signal and should not receive portfolio weight.

## Architecture in one line

Owner-native contract + owner-native runtime observation + consumer read receipt -> deterministic federation -> compact current manifest + bounded history -> existing consumers.

## What not to build

Do not build:

- another authoritative dataset registry;
- another runtime/service observability plane;
- another lifecycle or incident system;
- a single opaque “data health score”;
- a generic LLM health classifier;
- a new trade gate;
- a warehouse-first catalog stack merely because commercial tools are available;
- a historical backtest that reconstructs health from present-day corrected files.

---

# B. Current-state census

## B1. Mastermind repository

### Static system census — LIVE but not live enough

scripts/system_census.py already generates:

- data/census/latest.json
- data/census/CENSUS.md

It scans runtime entry points, portfolio modules, data paths, source adapters, schema hints and system structure. The current committed latest.json is old relative to the present source, which proves the commission’s motivating concern: a useful census exists, but regeneration cadence and currentness are not reliable enough to serve as live health truth.

Correct role: regenerable architecture/system projection.

Incorrect role: canonical runtime data-health registry.

### Cross-repo artifact contracts — LIVE

config/contracts.yml and control_plane/contracts.py already declare selected artifact paths, source owner, schema, consumers, freshness budgets, authority, and degradation class. data_layer/macro_refresh.py consumes these contracts for FREEZE-class anchors and already distinguishes advisory degradation from freeze semantics.

Correct role: contract owner for the artifacts it already governs.

Gap: coverage is partial and contract vocabulary is narrower than the desired estate-wide manifest.

### Bounded consumer health — LIVE

brain/portfolio_intelligence.py already implements a strong local pattern:

- fixed allowlist of artifacts;
- explicit missing, malformed, undated, stale, fresh states;
- content as-of extraction;
- bounded source references;
- no generic arbitrary path reader;
- missing/malformed/stale data is reported rather than silently promoted.

Correct role: consumer-side read observation for its bounded surface.

Gap: not a global consumer receipt and not historical.

### Portfolio decision-path health — LIVE but local

portfolio/conviction.py, portfolio/risk_sizing.py and related tests carry data_health diagnostics and fail-closed/freeze semantics in specific decision paths.

Correct role: decision-owner diagnostics.

Gap: no uniform cross-estate receipt proving which data generation a decision consumed.

### Runtime observability — SPEC protected; implementation carrier unmerged

The protected Runtime Observability Fabric design owns service/process/worker diagnostic telemetry and explicitly forbids a second runtime health plane. PR #843 is open and unmerged.

Correct role: runtime/service telemetry.

Incorrect role: canonical dataset contract or market-data truth.

### Portfolio V3 Decision Snapshots — unmerged candidate

PR #673 is open Draft. The design direction is relevant because a Decision Snapshot is a natural future consumer of data-health receipts, but this commission must not claim that capability exists.

## B2. Macro repository

This is the largest correction to the prior return.

### Data OS registry — LIVE

config/dataset_registry.yml and lib/dataos/registry.py are committed and tested. The registry already models:

- dataset_id;
- layer;
- owner;
- producer;
- storage;
- format;
- grain;
- temporal_profile;
- version;
- status: PRODUCED / PROPOSED / RETIRED;
- identity fields;
- schema;
- timezone/frequency;
- vendor/endpoint;
- conflict policy;
- freshness_sla_hours;
- quality checks;
- code consumers;
- dataset inputs;
- licensing;
- supersession;
- notes.

The registry also exposes a static dataset dependency DAG and reverse consumers derived from declared inputs.

This is already the canonical seed for market-data contracts. Commission 8 must extend it only where requirements are genuinely missing.

### Data quality primitives — LIVE

lib/dataos/quality.py implements pure deterministic checks with explicit severity:

- completeness;
- freshness;
- uniqueness;
- validity;
- continuity;
- distribution;
- cross-source reconciliation;
- referential integrity;
- temporal integrity.

Severity is separate from the observation itself, which is the correct pattern.

### Output health — LIVE

engine/output_health.py is unusually aligned with this commission. It explicitly states:

- producer health != output health != reader health;
- “could not look” is not healthy and not unavailable;
- health is an operating fact, not a model input;
- content clocks outrank transport clocks when contractually valid;
- missing declared watermarks create blindness rather than fallback freshness;
- reader negatives can override producer optimism;
- dependency propagation distinguishes exact from upper-bound attribution;
- output health has no score, rank, promotion state, or authority mutation.

scripts/build_output_health.py derives this view on demand, writes nothing, and supports summary output. This is already a compact current health query surface for the Macro output estate.

### Freshness sentinel and serving health — LIVE

scripts/freshness_sentinel.py and related quality artifacts observe user-visible publication. These should feed the federation as owner-native observations, not be replaced.

### Data OS research documents — historically valuable, status labels stale in places

research/MASTERMIND_DATA_OS_ARCHITECTURE.md and research/MASTERMIND_DATA_QUALITY_FRAMEWORK.md are older architecture/spec records whose headers still describe portions as proposed or untracked. Current code proves that important pieces were subsequently committed. Their architectural reasoning remains useful; their historical status statements are not current capability truth.

This itself is a data-observability lesson: durable research docs need machine-checkable current-state references rather than being treated as live status.

## B3. Terminal repository

Terminal has many local read-state and feed-health contracts, including:

- feed freshness/latency health in hub surfaces;
- explicit fresh/stale/missing/unavailable states;
- read receipts for some sector/company intelligence surfaces;
- last-good/stale behavior in selected clients;
- nightly wiring tests proving producers are actually invoked.

Gap: no single canonical Terminal-wide dataset registry comparable to Macro Data OS. Terminal should therefore publish bounded consumer/read receipts into the federation rather than become a second dataset-contract owner for Macro-produced assets.

## B4. Executive research vault

executive-dr-vault is currently an encrypted create-only backup-export repository. It is not an observability system and should remain outside the data-health control plane except as a separately governed backup/export asset if later required.

## B5. Material gaps after current-source reconciliation

The real gaps are narrower and more valuable than the prior report claimed:

1. No cross-repo compact projection joins owner-native contract truth with current health.
2. No uniform consumer-read receipt proves which asset generation a decision/research packet actually used.
3. Coverage denominators are inconsistent and often lack a stable expected-universe generation.
4. Rights are present in some registries but not normalized enough for estate-wide machine use.
5. Correction/reprocessing state is not uniformly exposed in health manifests.
6. Producer, artifact, reader and consumer health are not consistently joined across repositories.
7. Static census regeneration is not automatically tied to source changes or current manifest generation.
8. Agent/session query cost remains higher than necessary outside Macro’s existing output-health surface.
9. Historical health observations are not uniformly retained with point-in-time semantics.
10. Open PRs contain useful future behavior, but current protected source cannot rely on them.

---

# C. State-of-the-art research

The external state of the art supports the architecture Mastermind is already converging toward: contracts plus deterministic checks plus lineage plus explicit runtime observations, with a catalog as a projection rather than a substitute for source truth.

## C1. OpenLineage

OpenLineage models jobs, runs and datasets and supports dataset facets for schema, version, lifecycle state, data quality metrics and assertions. Run events distinguish lifecycle transitions such as START and COMPLETE/FAIL. Its extensibility model allows custom facets with versioned schemas.

Implication for Mastermind: OpenLineage is a strong interoperability/export format for future P1/P2 job and dataset lineage. It should not replace Macro’s dataset registry or Executive/runtime owners.

## C2. Open Data Contract Standard

The Linux Foundation AI & Data Bitol Open Data Contract Standard provides a vendor-neutral YAML structure covering schema, quality, SLAs, ownership/team, infrastructure, terms/limitations and authoritative definitions.

Implication: use ODCS as a cross-check and possible export/import target. Do not force a migration if the existing Macro registry can express Mastermind’s needs more simply.

## C3. DataHub and OpenMetadata

Both provide metadata/catalog/lineage/data-contract capabilities. DataHub documents producer-oriented contracts built from verifiable assertions such as freshness, schema, volume and quality. OpenMetadata documents schema, quality, SLA, terms-of-use and security sections on data contracts.

Implication: both are credible future catalog backends if Mastermind reaches a scale where self-hosted metadata operations are cheaper than maintaining the native projection. Neither is justified as P0 because the estate already owns the core contract and health primitives.

## C4. dbt freshness

dbt’s freshness model separates declared warning/error thresholds from the loaded-at field/query used to measure actual recency, and emits machine-readable freshness artifacts. Current dbt documentation also warns that metadata-based freshness is not reliable for every storage pattern.

Implication: freshness must bind to a declared content clock when possible. File mtime or transport time is not a universal substitute.

## C5. Great Expectations and Soda

Great Expectations and Soda are useful assertion/test runners. Soda’s current contract model explicitly distinguishes failed checks from execution errors, which maps well to Mastermind’s need to distinguish “bad data” from “could not evaluate.”

Implication: these are optional assertion engines, not required architecture. Mastermind already owns pure quality checks; adoption should require a concrete connector or maintenance advantage.

## C6. Datadog Data Observability

Datadog’s current Data Observability product includes catalog, lineage, quality monitoring and jobs monitoring. Its quality monitoring supports freshness, row count, column metrics and schema change for supported warehouses/data systems. Datadog also supports custom jobs using OpenLineage.

Mastermind already has a Datadog runtime-observability relationship, so this is strategically relevant. But current Data Observability support is strongly oriented to warehouses, Spark/Airflow/dbt and supported integrations. Mastermind’s estate is heavily Git/files/R2/custom-pipeline based.

Implication: P2 evaluation only. Verify US5 product support, entitlement, custom-job coverage, data-source fit, retention, pricing and rights before any purchase or integration. Existing Datadog runtime telemetry does not make Datadog the owner of dataset truth.

## C7. Confluent Schema Registry

Confluent Schema Registry is excellent for Kafka/event schema compatibility. It is not a general batch/file data catalog.

Implication: defer unless Mastermind introduces an event-stream substrate that actually needs producer/consumer schema compatibility.

## Institutional design principles supported by the survey

1. Contract and observation are different objects.
2. Producer success does not prove artifact freshness.
3. Artifact freshness does not prove reader freshness.
4. Reader freshness does not prove a consumer used that generation.
5. A failed observation is not a healthy observation.
6. Content clocks and transport clocks must not be silently substituted.
7. Coverage requires a denominator and denominator generation.
8. Schema evolution needs compatibility policy, not merely a hash.
9. Lineage should preserve confidence/exactness where dependencies are inferred.
10. Health should remain multi-dimensional and inspectable.

---

# D. Source landscape

This table evaluates observability/contract technologies, not market-data vendors.

| Source / option | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| Mastermind native federation over existing owners | Git/files/R2/custom pipelines; exact estate fit | Can retain bounded observations by design | On-demand / producer cadence | Highest if clocks are preserved | Native correction_generation and receipts can be added | Internal | Low infra / medium engineering | P0 canonical approach |
| Macro Data OS registry + output_health | Macro datasets and published outputs | Static contracts + on-demand current health; history varies by producer | On-demand | Strong current semantics; existing blindness and content-clock rules | Per-domain today | Internal | Already paid | P0 owner for Macro market-data truth |
| OpenLineage | Jobs/runs/datasets across many tools | Event history when collector retains it | Runtime events | Strong event-time model; PIT depends on retention | Versioned facets/events | Apache-2.0 | Low license / medium ops | P1/P2 interoperability and lineage export |
| ODCS | Data contract description | Version-control history | N/A contract-time | Strong contract versioning; runtime health external | Contract version history | Apache-2.0 | Low | Contract vocabulary cross-check/export |
| DataHub OSS / Cloud | Broad metadata, lineage, assertions, catalog | Platform-managed metadata history | Near-real-time depending ingestion | Good metadata PIT; physical data PIT depends integrations | Platform assertion/metadata history | OSS Apache-2.0; Cloud commercial | Medium to high | Defer until native projection operational cost becomes material |
| OpenMetadata / Collate | Metadata, lineage, quality, contracts | Platform-managed | Near-real-time depending ingestion | Good metadata PIT; physical data PIT depends integrations | Contract/test history | OSS Apache-2.0; managed commercial | Medium to high | Same decision class as DataHub |
| Great Expectations Core | Assertion execution across supported data sources | User-retained validation results | Pipeline/scheduled | Good if validation time and data version are stored | User-owned | Apache-2.0 core | Low to medium | Optional assertion runner |
| Soda contracts / Cloud | Schema/freshness/quality checks | Verification history when retained | Pipeline/scheduled | Good if run/data clocks retained | Verification history | Mixed OSS/commercial by component | Medium | Optional assertion runner / managed quality |
| dbt freshness | dbt sources/models | Machine-readable freshness artifacts | Scheduled/on-demand | Strong for declared loaded-at semantics | Artifact history if retained | dbt product/license dependent | Medium | Only if dbt becomes a material owner |
| Datadog Data Observability | Supported warehouses/lakes/jobs plus OpenLineage custom jobs | SaaS retention | Near-real-time/scheduled | Good operational PIT if events retained | Platform-managed | Commercial | High | P2: leverage existing vendor only after fit/US5/price proof |
| Confluent Schema Registry | Kafka/event schemas | Versioned schemas | Real-time | Strong schema PIT | Native versioning/compatibility | Commercial/open components; verify exact edition | Medium | Defer until streaming schema compatibility is a real need |

Commercial capability, retention, site availability, pricing and license terms must be reverified at implementation time. Marketing pages are not authority for contract terms.

---

# E. Canonical data model

The minimum useful design is four records, not one giant table.

## E1. DataAssetContract — owner-native, versioned

This is the producer promise. Macro’s existing DatasetContract should remain the market-data owner; other estates should map to the same projection vocabulary without duplicating ownership.

Minimum fields:

- dataset_id — stable semantic identity.
- contract_version.
- authority_repo and authority_ref/path.
- owner.
- producer_id / producer_path.
- storage_kind and storage_locator class.
- format.
- grain.
- identity_basis.
- schema_version or schema_digest.
- temporal_profile.
- event_time_field.
- as_of_field.
- known_at / available_at semantics.
- ingested_at semantics.
- effective_from / effective_to semantics where applicable.
- correction_policy and correction_generation semantics.
- expected_cadence.
- freshness_slo with calendar/basis.
- coverage_contract:
  - expected_universe_owner;
  - expected_universe_id;
  - expected_universe_generation;
  - required_keys or denominator rule.
- rights:
  - state: ALLOWED / RESTRICTED / UNKNOWN / EXPIRED / BLOCKED;
  - license_ref;
  - permitted_use;
  - redistribution;
  - verified_at.
- dependencies: dataset IDs only.
- dependency_requirement: required / optional per edge.
- degradation_class: reuse existing owner semantics where defined.
- criticality.
- lifecycle_status: PRODUCED / PROPOSED / RETIRED.

Do not copy every source’s entire schema into the compact manifest. Keep a schema/version pointer and a small compatibility summary.

## E2. DataHealthObservation — append-only observation

This says what an observer actually saw.

Minimum fields:

- observation_id.
- dataset_id.
- contract_version.
- observed_at — when the health observer measured.
- observer_id and observer_version.
- producer_run_id if known.
- source_receipt / content_hash / generation.
- latest_event_time.
- content_as_of.
- available_at / known_at if measured.
- ingested_at if measured.
- correction_generation.
- schema_version_observed.
- producer_state.
- artifact_state.
- reader_state.
- assessment_status: complete / partial / could_not_look.
- decided_by plane.
- freshness_lag.
- latency.
- row_count / byte_count where meaningful.
- coverage:
  - expected_count;
  - observed_count;
  - coverage_pct;
  - expected_universe_generation;
  - missing_key_count;
  - bounded missing_key sample or external receipt.
- quality findings by independent dimension.
- rights_state observed.
- dependency_state summary with exact/upper confidence.
- reason_codes.
- expires_at / next_expected_observation where meaningful.

Critical law: missing observation fields remain null/unknown. They never become zero, neutral or healthy.

## E3. ConsumerReadReceipt — proves consumption, not production

This is the missing cross-estate primitive.

Minimum fields:

- receipt_id.
- consumer_id and consumer_version/build.
- decision/research/run identity.
- dataset_id.
- required_or_optional.
- read_started_at / read_completed_at.
- observed_contract_version.
- observed_data_generation/content_hash.
- observed_content_as_of.
- observed_health_state.
- health_observation_id used.
- read_status: consumed / absent / stale / malformed / unavailable / blind / rights_blocked.
- fallback_used and fallback_dataset_id if any.
- consumer_effect: accepted / degraded / abstained / frozen / held / display_only / no_effect.
- reason_codes.

A consumer receipt must not grant the consumer authority to redefine the producer contract.

## E4. LiveDataManifest — derived compact projection

This is what agents query.

It is generated from E1-E3 plus existing system census and runtime health owners. It is not manually edited.

Top level:

- schema: mastermind.data_health_manifest.v1.
- generated_at.
- source_pins.
- projection_version.
- coverage_of_registry.
- critical_assets_total / assessed / healthy / degraded / stale / unavailable / blind / rights_blocked.
- unresolved_dependency_count.
- stale_contract_count.
- open_correction_count.
- manifest_health.

Per asset, keep only bounded fields:

- dataset_id.
- owner.
- contract_version.
- state.
- assessment_status.
- content_as_of.
- observed_at.
- freshness_lag.
- coverage_pct + denominator generation.
- schema_version.
- rights_state.
- correction_generation.
- producer_state.
- reader_state.
- critical_dependency_state.
- critical_consumer_state.
- degradation_class.
- reason_codes.
- source_ref.

A detailed query can then dereference the owner-native record.

## Temporal semantics

The commission’s clock vocabulary must be explicit:

- event_time: when the underlying economic/market event occurred.
- as_of: the domain snapshot’s stated reference time.
- observed_at: when this observer actually looked.
- known_at / available_at: earliest time Mastermind could lawfully possess/use the fact.
- ingested_at: when Mastermind persisted it.
- effective_from / effective_to: interval during which a mapping/schema/identity rule applies.
- correction_generation: monotone correction/reprocessing lineage.
- producer_run_time: when the producer execution occurred.
- health_measured_at: when health was evaluated.

Historical reconstruction must filter on known_at/available_at and the health observation that existed at the historical decision timestamp. A later correction cannot rewrite what a historical decision knew.

---

# F. Derived intelligence

All P0 calculations are deterministic.

## Freshness and latency

- content_age = health_measured_at - content_as_of, only when content_as_of is the declared governing clock.
- producer_latency = producer_completed_at - scheduled/nominal time.
- availability_latency = known_at/available_at - event_time.
- ingestion_latency = ingested_at - known_at/available_at.
- serving_latency = reader_observed_at - content_as_of.

Do not substitute file mtime for content_as_of unless the contract explicitly declares write-time authority.

## Coverage

- coverage_pct = observed expected keys / expected keys.
- missing_key_count.
- missing_key_sample.
- critical_missing_count.
- coverage_delta versus prior valid observation.
- denominator_generation_changed flag.

Coverage without denominator identity is invalid.

## Historical depth

- first_valid_event_time.
- first_known_at.
- last_valid_event_time.
- continuous_span.
- gap count / largest gap.
- PIT_replayable flag with reason.

A file’s oldest row is not sufficient to claim historical PIT depth.

## Schema and contract state

- schema_changed.
- compatibility: compatible / breaking / unknown.
- contract_changed.
- undeclared_field / missing_required_field.
- consumer_contract_mismatch.

## Correction state

- correction_generation.
- correction_open.
- correction_supersedes_generation.
- affected_time_range.
- affected_key_count.
- historical_decision_impact_unknown/known.

## Dependency health

- required_upstream_worst_state.
- optional_upstream_worst_state.
- dependency_bound: exact / upper / unknown.
- blast_radius_count.
- stale_propagation_depth.

Reuse Macro output_health’s exact-vs-upper discipline rather than claiming exact lineage from inferred edges.

## Rights state

- allowed_for_research.
- allowed_for_internal_decision.
- allowed_for_product_display.
- allowed_for_redistribution.
- rights_verified_at.
- rights_expiry.
- rights_unknown flag.

Rights UNKNOWN is not ALLOWED.

## Consumer health

- latest successful read.
- latest consumed generation.
- consumer lag behind producer.
- stale-consumption count.
- blind-consumption count.
- fallback count.
- abstention/freeze count due to data health.

## No opaque score

Do not aggregate these into a 0-100 health score. A stale-but-complete dataset, a fresh-but-5%-coverage dataset, a rights-blocked dataset and a blind observer are operationally different and require different responses.

---

## Anomaly detection

P0 anomaly detection should remain deterministic and inspectable:

- fixed SLO breaches;
- rolling median/MAD or robust z-score for row count, coverage and latency;
- calendar-aware cadence deviations;
- change-point flags only when enough clean history exists;
- separate seasonal baselines for session/day/week effects where required.

An anomaly is an observation, not a health verdict by itself. The contract determines severity. ML anomaly detection is P2 and must beat these deterministic baselines on false-positive/false-negative and operator-value metrics before promotion.

## Legitimate LLM use

Cheap LLMs may:

- summarize a deterministic incident bundle for an owner;
- explain which contract dimensions failed in plain language;
- draft a ticket or operator handoff from cited receipts;
- classify unstructured documentation into candidate metadata fields for human review;
- produce a bounded daily digest of already-resolved health facts.

Frontier LLMs may:

- investigate a complex multi-repository incident after deterministic health has identified the affected assets;
- propose competing root-cause hypotheses across lineage, schema, correction and consumer receipts;
- reconcile ambiguous historical documentation during an audit;
- review a proposed contract/schema change for hidden blast radius.

Neither cheap nor frontier models may:

- set health state;
- set rights state;
- invent missing timestamps or coverage denominators;
- decide that a blind probe is healthy;
- override an owner-native contract;
- create portfolio/ranking/sizing authority;
- silently repair or replay a failed producer.

Every LLM output remains advisory and must cite the deterministic receipts it used.

# G. Mastermind integration map

| Producer / owner | Canonical owner-native artifact | Federation role | Consumer |
|---|---|---|---|
| Macro collectors / Data OS | config/dataset_registry.yml + lib/dataos | Dataset contract authority for Macro data | Macro engines, Mastermind, Terminal |
| Macro Eval OS | mastermind.output_health.v1 derived by scripts/build_output_health.py | Output/reader/dependency health observation | Admin, federation, future Decision Snapshots |
| Macro freshness sentinel / quality audits | Existing sentinel/audit receipts | Serving and quality evidence | Output health + federation |
| Mastermind system census | data/census/latest.json generated by scripts/system_census.py | Architecture/system projection | Sessions/agents |
| Mastermind artifact contracts | config/contracts.yml + control_plane/contracts.py | Contract authority for selected cross-repo artifacts | macro_refresh, portfolio consumers |
| Mastermind macro refresh | data_layer/macro_refresh.py | Producer/refresh/freeze observation | Daily portfolio path |
| Mastermind portfolio intelligence | brain/portfolio_intelligence.py | Bounded consumer read health | Research/portfolio context |
| Mastermind decision path | conviction/risk sizing/held risk owners | Consumer effect receipt | Portfolio manager / Decision Snapshot |
| Terminal feed/read modules | Existing per-surface read states | Consumer read receipt source | Terminal UI |
| Runtime Observability Fabric | protected runtime diagnostics owner | Service/process telemetry only | Ops / Control Room |
| Datadog | Existing runtime sink; optional future data-observability sink | External projection only | Operators |
| Live Data Manifest compiler | NEW, read-only projection | Federation, not authority | Agents, sessions, dashboards, snapshots |

The federation must never become the writer of owner-native contracts, producer state, runtime state, portfolio authority or rights decisions.

---

# H. Empirical validation program

The prior return’s “does data health improve Sharpe?” framing is rejected as the primary test.

## H1. Contract and resolver tests

Create a synthetic matrix covering:

- producer green, artifact stale;
- producer failed, artifact still current;
- producer current, reader stale;
- artifact missing;
- artifact malformed;
- observer blind/could_not_look;
- content clock missing but transport clock fresh;
- coverage denominator changes;
- partial universe;
- schema breaking change;
- rights expired/unknown;
- correction generation opens;
- required dependency stale;
- optional dependency stale;
- dependency cycle;
- inferred upper-bound lineage;
- consumer reads stale generation;
- consumer fallback;
- consumer cannot read;
- consumer abstains/freezes.

Every state transition must have a falsifier. A resolver that returns healthy for all inputs must fail the suite.

## H2. Historical incident replay

Use real, already documented Mastermind/Macro incidents where lawful evidence exists:

- stale vendored Macro checkout;
- missing stockdata/R2 legs;
- stale or partial freshness-registry coverage;
- missing stores that previously failed open to null;
- identity/coverage gaps where one member silently disappeared;
- producer success with stale output;
- reader-plane degradation.

For each incident, ask:

1. Would the proposed manifest have detected it before the affected consumer?
2. Which exact reason code would fire?
3. Would the system have been healthy, degraded, stale, unavailable or blind?
4. Would the existing owner’s degradation semantics have prevented silent neutralization?
5. Could the manifest reconstruct only what was knowable then?

## H3. Shadow production

Run the federation read-only for a defined observation period before any decision gating.

Measure:

- critical-asset registration coverage;
- assessed-vs-blind ratio;
- false-positive alert rate;
- false-negative incidents found manually but missed by manifest;
- median and p95 detection lag;
- producer/output/reader disagreement frequency;
- coverage-drop incidents;
- rights-unknown incidents;
- correction events;
- stale-consumption and blind-consumption counts;
- manifest generation/query latency;
- operator time to identify root cause;
- duplicate alerts per root cause.

## H4. Decision integrity tests

Fault-inject data failures into a non-production test path and verify:

- missing required data never becomes neutral;
- stale required data invokes the owning degradation class;
- optional missing data remains explicitly absent;
- held positions follow existing freeze/hold/de-risk semantics, not a new commission-defined rule;
- no health state flips an investment direction by itself;
- Decision Snapshot/read receipt records the data state used.

## H5. Point-in-time replay

For historical replay at decision time T:

- use only contracts effective at or before T;
- use only health observations observed at or before T;
- use only data generations available at or before T;
- do not apply later correction generations;
- preserve blind/unknown states;
- preserve the expected-universe generation that existed at T.

A present-day filesystem scan is not historical health evidence.

## H6. Success criteria

P0 promotion should require, at minimum:

- every P0-critical decision input has an owner-native contract or an explicit unresolved gap;
- no injected missing/stale/blind required input becomes healthy or neutral;
- every manifest field has an owner/source receipt;
- no second authoritative registry is created;
- consumer receipt semantics are proven on at least one Mastermind and one Terminal path;
- manifest generation is bounded enough for routine agent/session use;
- historical replay can reproduce at least a small incident corpus without future leakage.

## H7. Kill criteria

Do not promote or continue the build if:

- the federation requires manual duplication of owner-native metadata to stay current;
- it becomes the writer of contract/runtime/portfolio truth;
- health cannot distinguish blindness from absence;
- coverage cannot name its denominator generation;
- consumer receipts cannot bind to a concrete data generation;
- point-in-time reconstruction requires current corrected files;
- alert noise is high enough that operators routinely ignore it;
- a commercial platform requires migrating canonical truth away from current owners without a measured operational benefit;
- the compact manifest is slower/more expensive than bounded direct owner queries for the critical set.

Predictive-alpha kill criterion: do not treat data-health state as alpha at all under this commission. If someone later hypothesizes that vendor outages or revision events themselves predict returns, that is a separate preregistered research commission.

---

# I. Risks and failure modes

## Duplicate authority

Largest architectural risk. A “central catalog service” can quietly become the place where teams edit ownership, rights, schema or lineage, diverging from source owners.

Mitigation: projection-only; every field carries authority_ref and source_ref.

## Stale manifest

A live census can itself become stale.

Mitigation: generated_at, source pins, per-source observed_at, manifest_health, and no committed latest file as sole runtime truth. A cached copy must expose expiry.

## Silent neutralization

Missing or stale inputs may collapse to None/0/neutral in downstream logic.

Mitigation: typed read status plus consumer receipt; explicit required/optional semantics; fault-injection tests.

## Blindness conflated with absence

Network/auth/parser failure can be reported as “missing.”

Mitigation: could_not_look is first-class and never converts to healthy.

## False freshness

File mtimes, transport timestamps or wrapper generation times can refresh while content is frozen.

Mitigation: contract-declared content clock; transport clocks disclosed separately.

## Coverage false precision

A percentage can hide the most important missing names or a changed universe.

Mitigation: denominator generation, critical missing count, missing-key receipt/sample.

## Correction leakage

Later corrected data can make historical systems look healthier than they were.

Mitigation: append-only health observations and correction generation; historical queries filter on known_at/observed_at.

## Rights drift

A dataset can remain technically healthy after use rights expire or change.

Mitigation: rights_state is independent of freshness and quality; UNKNOWN/BLOCKED cannot be collapsed into healthy.

## Correlated alerts

One upstream outage can create hundreds of downstream red assets.

Mitigation: root-cause grouping plus dependency blast radius; do not suppress downstream state, but deduplicate notifications.

## Inferred lineage overstated as exact

Static code/producer inference can create false edges.

Mitigation: exact / upper / unknown dependency confidence, following Macro output_health.

## Vendor lock-in

Commercial catalog/observability products can become the only place where lineage or quality history exists.

Mitigation: canonical internal contract/observation schemas; vendors receive/export projections.

## LLM false authority

An LLM incident summary can hallucinate cause or recommend unsafe action.

Mitigation: deterministic state first; LLM outputs are summaries/hypotheses with cited receipts and no health/rights/portfolio authority.

---

# J. Build priority

## P0

1. Freeze the federation boundary: projection, not authority.
2. Define mastermind.data_health_manifest.v1 and mastermind.data_consumer_receipt.v1.
3. Reuse Macro Data OS registry and mastermind.output_health.v1 as first-class inputs.
4. Add Mastermind adapters for config/contracts.yml, system census and bounded consumer health.
5. Add one Terminal consumer-receipt adapter for a critical Macro-fed surface.
6. Normalize coverage denominator identity, rights state, correction generation and blindness.
7. Produce a compact current manifest with bounded summary and per-asset detail.
8. Add deterministic failure-propagation tests proving “missing never becomes neutral.”
9. Add a cheap query surface for sessions/agents.
10. Preserve source pins and observation clocks.

## P1

1. Broaden consumer receipts across critical Mastermind and Terminal paths.
2. Retain bounded append-only health history for PIT incident replay.
3. Add schema compatibility classification.
4. Add exact/upper dependency blast-radius queries.
5. Add root-cause grouping and alert deduplication.
6. Integrate with future Decision Snapshots only after that owner is protected.
7. Export OpenLineage events/facets where useful without changing ownership.
8. Add dashboard views over the manifest.

## P2

1. Evaluate Datadog Data Observability/OpenLineage ingestion against the real custom-file/R2 estate.
2. Evaluate DataHub or OpenMetadata only if native metadata operations become a measured burden.
3. Add adaptive anomaly detection for metrics with enough clean history.
4. Add LLM incident summaries and investigation assistance over deterministic receipts.
5. Add richer column-level quality only where consumers demonstrate value.

## Defer

- Confluent Schema Registry until a real Kafka/event compatibility problem exists.
- Warehouse-first tooling while the estate remains primarily files/R2/custom pipelines.
- Full column-level profiling of every dataset.
- ML anomaly detection before deterministic SLOs and coverage are trustworthy.
- Cross-repo automatic remediation.

## Reject

- New authoritative central catalog.
- One opaque health score.
- LLM-determined health state.
- Health-as-alpha weighting.
- Silent fallback from missing to neutral.
- Historical health reconstructed from current corrected state.
- Vendor adoption without rights, retention, export and lock-in diligence.

---

# K. Proposed implementation phases

These are implementation recommendations only; this research does not execute them.

## Phase 0 — Source reconciliation and contract freeze

Deliverables:

- exact owner map;
- exact P0 asset list;
- frozen projection schema;
- frozen consumer receipt schema;
- mapping from existing Macro/Mastermind/Terminal states into the projection;
- explicit no-rebuild boundaries.

Acceptance:

- no duplicated authority;
- every field has an owner;
- open/unmerged PR behavior is excluded from current capability claims.

## Phase 1 — Read-only manifest compiler

Build a pure/read-only compiler that:

- reads Macro Data OS contracts;
- reads Macro output_health;
- reads Mastermind contracts and system census;
- reads bounded Terminal consumer observations;
- emits mastermind.data_health_manifest.v1;
- writes no canonical state.

Acceptance:

- deterministic output for pinned inputs;
- explicit blind states;
- bounded runtime;
- source refs on every asset.

## Phase 2 — Consumer receipts

Instrument one critical Mastermind consumer and one Terminal consumer to emit bounded read receipts.

Acceptance:

- receipt binds to data generation/content hash where available;
- required missing/stale state is explicit;
- no portfolio behavior change beyond existing owner semantics.

## Phase 3 — Coverage, rights and correction completeness

Fill the three most important semantic gaps:

- expected-universe generation;
- normalized rights state;
- correction generation/supersession.

Acceptance:

- coverage percentage cannot exist without denominator identity;
- rights UNKNOWN never renders ALLOWED;
- historical queries can select the generation known at time T.

## Phase 4 — Historical health ledger and replay

Retain bounded append-only observations sufficient for incident replay.

Acceptance:

- replay selected real incidents without current-state leakage;
- correction generations remain distinct;
- blind observations remain blind.

## Phase 5 — Dashboarding and alerting

Build human views and alerts from the same manifest.

Acceptance:

- root-cause grouping;
- downstream blast radius visible;
- alert routing names an owner;
- no separate dashboard truth store.

## Phase 6 — External interoperability

Pilot OpenLineage export and, only if justified, Datadog Data Observability ingestion.

Acceptance:

- native owner truth remains canonical;
- external system can be removed without losing contract/history truth;
- cost and operational burden measured.

## Phase 7 — Optional catalog platform decision

Only after measured native operating cost exists, compare DataHub/OpenMetadata/managed alternatives.

Decision criterion: total maintenance burden, connector coverage, agent query value, rights/security fit, exportability, and lock-in — not feature count.

---

# L. Exact implementation handoff

## FOLLOW-ON IMPLEMENTATION COMMISSION — DATA HEALTH FEDERATION P0

You are implementing the accepted P0 of Commission 8 for MastermindX.

This is an implementation commission, but it is narrowly bounded. Do not create a new authoritative data catalog, runtime observability plane, lifecycle, queue, incident system, portfolio rule, rights authority, or vendor dependency.

### Source law

At START:

1. Pin current protected mastermindx-market-intelligence/Mastermind master and load the current protected bootstrap procedures from that same revision.
2. Pin current mastermindx-market-intelligence/macro main and mastermindx-market-intelligence/mastermind-terminal master.
3. Reconcile current source against this research report; this report is recommendation, not authority over newer protected source.
4. Inspect open PRs touching the proposed paths and preserve one-writer/collision law.
5. Do not consume behavior that remains only in unmerged PRs.

### Outcome

Build a read-only, automatically regenerated Data Health Federation P0 that lets sessions/agents cheaply query current data health without rescanning the estate and without duplicating owner-native truth.

### Must reuse

- Macro config/dataset_registry.yml and lib/dataos/registry.py as the market-data contract owner.
- Macro mastermind.output_health.v1 and scripts/build_output_health.py as the output/reader/dependency health owner.
- Mastermind scripts/system_census.py and data/census projection.
- Mastermind config/contracts.yml / control_plane/contracts.py for the artifacts they already own.
- Mastermind existing bounded consumer health patterns.
- Existing runtime observability owners for service/process telemetry only.

### P0 deliverables

1. A versioned mastermind.data_health_manifest.v1 schema.
2. A versioned mastermind.data_consumer_receipt.v1 schema.
3. A pure/read-only manifest compiler that federates owner-native inputs.
4. A compact summary query suitable for agent/session use.
5. One detailed per-asset query.
6. One Mastermind consumer receipt integration.
7. One Terminal consumer receipt integration.
8. Deterministic tests for stale, missing, malformed, blind, partial coverage, rights unknown/blocked, correction generation, required dependency failure, optional dependency failure and stale consumer read.
9. Source receipts and exact revision pins in every generated manifest.
10. Documentation of no-rebuild boundaries and operational ownership.

### Required semantics

The implementation must preserve:

event_time  
as_of  
observed_at  
known_at / available_at  
ingested_at  
effective_from / effective_to  
correction_generation  
producer_run_id / health_measured_at

It must distinguish:

producer health  
artifact/output health  
reader/served-copy health  
consumer read health  
blind/could-not-look

It must bind coverage to an expected-universe generation.

It must keep freshness, coverage, schema, rights, correction, producer, reader, consumer and dependency states independently inspectable. No aggregate health score.

### Forbidden

- no new authoritative dataset registry;
- no generic path reader;
- no LLM state classifier;
- no automatic vendor purchase or SaaS dependency;
- no new trading/ranking/sizing authority;
- no silent null/zero/neutral fallback;
- no historical replay from present corrected files;
- no migration of Macro Data OS ownership into Mastermind;
- no second runtime health plane;
- no external catalog as canonical truth.

### Deterministic-before-LLM rule

All state resolution, freshness math, coverage math, schema compatibility, rights state, correction state, dependency propagation and consumer status are deterministic.

LLMs may later summarize incidents or propose investigation hypotheses from cited receipts. They may not set health state, rights state, degradation class or portfolio effect.

### Acceptance tests

P0 is accepted only when:

1. current-source owner boundaries are proven;
2. all P0-critical fields carry source/authority references;
3. injected missing/stale/blind required inputs never become healthy or neutral;
4. coverage cannot be emitted without denominator generation;
5. consumer receipts bind to a concrete observed data generation where available;
6. manifest generation is deterministic and bounded;
7. one Mastermind and one Terminal real consumer path are proven end to end;
8. the compiler can run when an owner is unreachable and reports blindness instead of fabricating absence;
9. no existing owner or portfolio behavior is silently replaced;
10. independent review confirms no duplicate control plane.

### Release boundary

Source merge proves only the P0 federation implementation that was actually tested. It does not prove all datasets are onboarded, all consumers are instrumented, external Data Observability is live, historical replay is complete, Decision Snapshots are protected, or portfolio behavior has changed.

End the implementation with exact evidence, remaining coverage gaps, source pins, and the next bounded phase. Do not self-promote P1/P2.

---

# External primary references

OpenLineage object model and facets:
https://openlineage.io/docs/spec/object-model/
https://openlineage.io/docs/spec/facets/
https://openlineage.io/docs/spec/facets/dataset-facets/data_quality_assertions/

Open Data Contract Standard:
https://github.com/bitol-io/open-data-contract-standard
https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/README.md

DataHub:
https://docs.datahub.com/docs/managed-datahub/observe/data-contract
https://github.com/datahub-project/datahub

OpenMetadata:
https://docs.open-metadata.org/v1.12.x/api-reference/data-contracts
https://github.com/open-metadata/OpenMetadata

Great Expectations:
https://greatexpectations.io/

Soda:
https://docs.soda.io/
https://docs.soda.io/reference/contract-language-reference
https://docs.soda.io/soda-documentation/soda-v3/data-contracts/data-contracts-verify

dbt freshness:
https://docs.getdbt.com/docs/deploy/source-freshness
https://docs.getdbt.com/reference/resource-configs/freshness
https://docs.getdbt.com/reference/artifacts/dbt-artifacts

Datadog Data Observability:
https://docs.datadoghq.com/data_observability/
https://docs.datadoghq.com/data_observability/quality_monitoring/
https://docs.datadoghq.com/data_observability/lineage/
https://docs.datadoghq.com/data_observability/jobs_monitoring/openlineage/
https://docs.datadoghq.com/data_observability/integration_overhead/

Confluent Schema Registry:
https://docs.confluent.io/platform/current/schema-registry/index.html

---

# Final research disposition

Commission 8 is accepted as a high-priority architecture need only in its hardened form:

- federate, do not centralize authority;
- reuse Macro Data OS and output health;
- preserve blindness and point-in-time clocks;
- add consumer receipts;
- bind coverage to denominator generations;
- keep rights/corrections independent;
- treat health as decision validity, not alpha;
- expose one compact current manifest for agents and operators;
- make external observability/catalog products optional projections, not owners.

No implementation effect was performed by this research report.
