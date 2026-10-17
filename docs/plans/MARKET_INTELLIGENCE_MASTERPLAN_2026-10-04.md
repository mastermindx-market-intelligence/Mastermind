# Mastermind Institutional Market Intelligence — End-to-End Master Plan

**Program:** #1202  
**Date:** 2026-10-04  
**Protected source pin:** `c776f8dc8d3dabb0070b51ad7f04d71987ff6df1`  
**Status:** implementation master plan / architecture candidate / production proof required  
**Principal handoff:** Fable as C3 principal/integrator; bounded execution routes to least-scarce capable workers.  
**North star:** materially earlier, lower-latency, more accurate and more auditable investment intelligence without creating a second Mastermind control plane.

---

## 1. Executive verdict

Mastermind should build this program. The highest-value gap is not “more news.” It is the absence of a sufficiently granular, persistent, point-in-time intelligence state that joins authoritative events, supply-chain/technology ontology, company economics, earnings, tape confirmation and outcome learning.

The desired machine is:

```
authoritative source
  → evidence capture + source reconciliation
  → canonical event + lifecycle
  → entity / product / subtheme graph
  → persistent thesis state
  → company economic bridge
  → market/tape confirmation
  → calibrated research/shadow signal
  → portfolio intelligence
  → realized outcome + model/source calibration
```

The optics case is the golden failure replay. The correct lesson is not “catch S.5548 faster.” It is that Mastermind should have maintained an optical-networking thesis before the bill from the June 1260H designation, the August FCC restriction report, earnings/sell-side/company evidence, granular product architecture transitions, and correlated tape. S.5548 should have been a thesis delta/re-acceleration event, not thesis birth.

### Hard correction to the research premise

GovInfo records S.5548 as introduced **September 24, 2026**, read twice and referred to the Senate Committee on Homeland Security and Governmental Affairs. It is not enacted law. Its title/scope concerns federal procurement of certain optical transceivers. It must not be conflated with the broader reported FCC work on possible restrictions on new Chinese optical-transceiver models. The system must model these as separate event objects that may support the same thesis through different mechanisms.

Other required corrections/hardening:

1. **“Primary source first” does not mean “primary source only.”** Rumor/reporting can lead an official action by weeks or months. Reuters-like reports should enter as lower-authority event states with explicit uncertainty, then be upgraded/corroborated—not discarded until government publication.
2. **Publication time is not economic effective time.** Store `published_at`, `first_seen_at`, `effective_at`, `market_session`, `alerted_at`, and `ingested_at` separately.
3. **A bill, proposed rule, final rule, Covered List action, procurement prohibition, export control and sanctions designation are not interchangeable.** Lifecycle and legal mechanism are first-class.
4. **Ticker mapping is insufficient.** The graph must represent product/component/architecture exposure and customer/supplier relationships, with temporal validity and confidence.
5. **Headline sentiment is insufficient.** Every material event needs an explicit economic mechanism and an earnings bridge.
6. **Tape is evidence, not truth.** Correlated residual strength should raise investigative priority and thesis confidence only under calibrated rules; it must not circularly “prove” a thesis.
7. **Backtests must reproduce what was knowable at the time.** No revised taxonomy, later company mappings, final bill text, post-event earnings, or future consensus can leak backward.
8. **Cheap LLMs are not arithmetic or authority engines.** Use them for extraction, classification, dedupe candidates and routing; deterministic code and validated higher-reasoning stages own privileged calculations and portfolio-facing outputs.
9. **Institutional grade requires source health.** A feed that is silent is not necessarily healthy. Every source needs cursors, expected cadence, reconciliation/backfill and miss detection.
10. **Do not buy a giant data platform before proving the intelligence loop.** Direct authoritative sources + existing Research Vault + existing market data should establish P0 value; add vendors only for demonstrated coverage/latency/licensing gaps.

---

## 2. Current Mastermind architecture constraints

This program must extend incumbent owners:

- news/RSS and White House ingestion;
- Research Vault;
- earnings intelligence;
- baskets/themes;
- local Qwen/OpenAI-compatible inference;
- Executive OS / Agent OS;
- Capacity / Model Router / RuntimeBinding / Worker Fabric;
- portfolio intelligence;
- GitHub implementation/evidence.

Existing #983 already defines the convergence direction for VPS/website reasoning onto canonical Fabric. #515 defines first-party worker orchestration lineage. Treat both as dependencies/evidence, not permission to invent a new market-intelligence worker system.

### Fabric/VPS rule

At program start, Fable must reconcile whether the required VPS→Fabric path is `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, or `BROKEN`. Do not assume it is complete because source exists. Do not replace it with a direct provider waterfall if incomplete. Close only the exact missing path needed for intelligence workloads.

---

## 3. Product outcome and measurable SLOs

The product is not complete when documents are ingested. It is complete when Mastermind can detect, understand, quantify, confirm, remember, and learn from market-moving developments earlier.

### P0 machine outcomes

For a material event:

1. capture authoritative/credible evidence;
2. identify duplicates/syndication and lifecycle relation;
3. map affected ontology nodes/entities/securities;
4. update one or more persistent theses;
5. quantify plausible company impact with assumptions/scenarios;
6. compare with current earnings/consensus and market expectations;
7. evaluate tape/subtheme confirmation;
8. emit a why-now intelligence object and calibrated shadow signal;
9. preserve exact point-in-time state;
10. score later outcomes and update calibration.

### Initial SLO targets

These are engineering targets to validate, not promises:

| Class | Capture-to-normalized-event target | Alert target | Notes |
|---|---:|---:|---|
| SEC/official machine-readable | p50 < 10s, p95 < 60s | p95 < 90s | subject to source publication latency |
| official RSS/API/press room | p50 < 30s, p95 < 3m | p95 < 5m | cadence-aware |
| high-value wire/vendor | provider-dependent | < 2m after receipt | license-dependent |
| company IR | p95 < 2m | < 4m | direct IR preferred |
| lower-priority trade press | < 10m | < 15m | batching allowed |

Every latency metric must decompose `source_publication → first_seen → ingested → normalized → thesis_updated → alerted`.

---

## 4. Canonical source registry and reconciliation plane

Build one source registry used by all market-intelligence ingestion.

### Source record

```yaml
source_id:
publisher:
source_class: government_api|government_feed|company_ir|sec|wire|trade_press|research|other
authority_tier: primary|official_derivative|high_quality_secondary|secondary
jurisdiction:
domains:
endpoint:
transport: api|rss|atom|json|xml|html|email|webhook|bulk
auth_mode:
license_policy:
expected_cadence:
poll_policy:
latency_class:
cursor_strategy:
revision_semantics:
document_id_strategy:
backfill_strategy:
rate_limit:
health_slo:
last_success_at:
last_new_document_at:
last_reconciled_at:
silence_threshold:
owner:
```

### P0 U.S. primary-source coverage

Implement direct connectors/registry entries for:

- Congress.gov API + GovInfo bill/text/record confirmation;
- Federal Register API;
- Regulations.gov API;
- SEC EDGAR submissions + companyfacts/XBRL + filing RSS where useful;
- White House releases/orders/fact sheets;
- FCC press releases, dockets/ECFS and Covered List/security actions;
- Commerce/BIS rules, entity-list/export-control publications;
- Treasury/OFAC sanctions;
- USTR tariffs/trade actions;
- Defense/Section 1260H and contract/industrial-base releases;
- SAM.gov / USAspending procurement and awards where market-relevant;
- FTC/DOJ antitrust;
- FDA/CMS for healthcare;
- DOE/FERC/EPA for energy/utilities;
- DOT/FAA/NHTSA for transportation;
- CISA/NIST for cybersecurity/standards;
- USDA where agriculture-sensitive;
- committee/member releases for high-market-impact committees/members.

Registry expansion is data, not code architecture. Add sources without adding new ingestion control planes.

### Reconciliation

Every connector implements:

```
poll/read
→ normalize source-native ID + revision
→ append raw evidence
→ advance durable cursor only after commit
→ periodic independent backfill/reconciliation
→ detect gaps/silence/revisions
```

Health states: `HEALTHY | LATE | SILENT_SUSPECT | GAP_DETECTED | AUTH_FAILED | RATE_LIMITED | SCHEMA_DRIFT | DOWN`.

A green HTTP 200 with no new documents is not sufficient health proof.

---

## 5. Raw evidence ledger

The raw layer is immutable evidence, not interpretation.

Required fields:

```yaml
evidence_id:
source_id:
source_native_id:
source_revision:
canonical_url:
content_hash:
published_at:
first_seen_at:
ingested_at:
effective_at: null
retrieved_at:
title:
mime_type:
language:
raw_content_ref:
extracted_text_ref:
license_policy:
correction_of: null
supersedes: null
provenance_chain:
```

Store raw bytes/text only where rights permit. Where full-text storage is not permitted, store licensed references, metadata, hashes and permitted evidence spans.

---

## 6. Canonical event graph

An event is a normalized market-relevant state transition supported by evidence.

### Event schema

```yaml
event_id:
event_type:
lifecycle_state:
legal_or_business_mechanism:
published_at:
first_seen_at:
effective_at:
market_session:
source_authority:
evidence_refs: []
cluster_id:
supersedes_event_id: null
contradicts_event_ids: []
affected_nodes: []
affected_entities: []
affected_securities: []
direction_by_entity: {}
materiality:
novelty:
confidence:
horizon:
reversibility:
mechanism_summary:
evidence_spans: []
model_receipts: []
deterministic_validation:
created_at:
updated_at:
```

### Lifecycle examples

Government:
`reported → drafting → proposed → comment/open → revised → final → effective → stayed/blocked → superseded`

Legislation:
`rumored → draft/public → introduced → committee → chamber_passed → reconciled → enrolled → signed/vetoed → effective`

Company:
`rumor → announcement → guidance → contract/customer confirmation → shipment → revenue_ramp → realized_financials`

### Deduplication

Use layered dedupe:

1. deterministic URL/native-ID/hash exactness;
2. syndicated-copy fingerprints;
3. entity/time/event-type candidate blocking;
4. embedding/cheap-model similarity;
5. higher-reasoning adjudication only for ambiguous high-materiality clusters.

Never increase confidence merely because 40 outlets copied one wire.

---

## 7. Market ontology and knowledge graph

The ontology must be finer than GICS and temporal.

### Core hierarchy

```
market
→ sector
→ industry
→ subsector
→ theme
→ subtheme
→ technology / architecture
→ product
→ component / material
→ supply-chain role
→ company
→ security
```

All edges are many-to-many and carry:

`valid_from, valid_to, confidence, provenance, relationship_type, exposure_weight, revenue_sensitivity, geography, customer/supplier context`.

### Optics reference resolution

```
AI infrastructure
  → networking/interconnect
    → optical networking
      → scale-up
      → scale-out
      → scale-across
      → DCI
      → pluggable transceivers
        → 400G / 800G / 1.6T / 3.2T
      → CPO
      → NPO
      → OCS
      → ELS/ELSFP
      → silicon photonics
      → InP lasers/modulators/detectors
      → VCSEL
      → FAU / precision fiber assemblies
      → coherent-lite / ZR/ZR+
```

A company can occupy several nodes simultaneously. Exposure weights change over time.

### Graph sources

Seed from company filings/IR/product catalogs, standards/MSA membership, earnings transcripts, Research Vault, reputable industry sources and analyst evidence. Every model-suggested edge remains `candidate` until evidence-backed.

---

## 8. Persistent thesis engine

A thesis is not a bag of headlines. It is a durable hypothesis with evidence, mechanisms, catalysts and falsifiers.

### Thesis schema

```yaml
thesis_id:
title:
scope_nodes: []
beneficiaries: []
losers: []
state: watch|forming|investable|high_conviction|reaccelerating|decaying|falsified|closed
created_at:
state_changed_at:
horizon:
mechanisms: []
evidence_for: []
evidence_against: []
catalysts: []
falsifiers: []
economic_models: []
tape_state:
earnings_state:
confidence:
confidence_components:
next_checks: []
last_material_delta:
point_in_time_version:
```

### Confidence update law

Do not use a naïve additive score. Compute components separately:

- source authority;
- evidence independence;
- mechanism clarity;
- economic magnitude;
- timing clarity;
- company exposure confidence;
- cross-source corroboration;
- earnings/estimate confirmation;
- tape confirmation;
- contradiction/falsifier pressure;
- recency/decay.

Then calibrate thesis-state transitions empirically from historical outcomes.

Price confirmation can increase tactical confidence while reducing remaining expected upside. Preserve both facts separately.

---

## 9. LLM pool integration

### Principle

Use the cheapest reliable model for each bounded task. Models propose; deterministic systems validate privileged fields.

### Routing matrix

| Task | Default tier | Escalation |
|---|---|---|
| language detection / boilerplate stripping | deterministic/local | none |
| entity/ticker/product extraction | local Qwen / cheap structured model | stronger model on low confidence |
| taxonomy candidate assignment | local Qwen | stronger model for novel nodes |
| dedupe candidate scoring | embeddings + local model | stronger adjudicator for material ambiguity |
| event type/lifecycle extraction | local structured model | stronger model if legal state ambiguous |
| evidence-span extraction | local model | stronger model for long/complex docs |
| novelty summary | cheap model + retrieval | stronger if high materiality |
| beneficiary/loser candidate hypotheses | cheap model | mandatory stronger review before signal use |
| thesis synthesis | stronger model | frontier only for genuinely complex cross-domain cases |
| economic impact narrative | stronger model | deterministic arithmetic + independent review |
| portfolio sizing/trade authority | **not delegated to cheap model** | incumbent portfolio/risk authority only |

### Evaluation harness

Create a frozen, versioned benchmark containing:
- government lifecycle classification;
- entity/ticker extraction;
- optics product taxonomy;
- syndicated-story dedupe;
- contradictory evidence;
- company exposure mapping;
- earnings bridge extraction;
- numeric unit tests;
- adversarial hallucination cases.

Metrics: precision/recall/F1 by task, schema-valid rate, evidence-grounded rate, calibration/Brier score where probabilistic, latency, cost/document and abstention quality.

No model is promoted because of generic benchmarks. Promote only on Mastermind task data.

---

## 10. Economic / earnings impact engine

The engine produces scenarios, not false precision.

### Causal bridge

```
event
→ addressable market / restricted share / demand delta
→ company exposure
→ share shift / units / ASP
→ capacity/utilization constraints
→ gross margin
→ opex/capex
→ revenue
→ EBIT/EBITDA
→ EPS / FCF
→ timing
→ valuation sensitivity
```

### Required scenario object

```yaml
scenario_id:
event_id:
company_id:
case: bear|base|bull
probability:
assumptions:
  addressable_revenue:
  share_shift:
  units:
  asp:
  capacity:
  gross_margin:
  opex:
  capex:
timing:
revenue_delta:
eps_delta:
fcf_delta:
valuation_method:
valuation_delta:
confidence_interval:
evidence_refs:
formula_version:
model_receipt:
review_status:
```

Arithmetic is deterministic. Models may populate candidate assumptions only with cited evidence. Unit mismatches, impossible margins, time-period conflicts and double-counted segment revenue fail closed.

For policy events, probability tree must distinguish legal scope and pathway. Example: S.5548 federal procurement prohibition is not the same scenario as a broad FCC import restriction; model them independently and combine only with explicit conditional logic.

---

## 11. Tape and subtheme confirmation

Build a subtheme-strength service keyed to ontology nodes.

Features:

- raw and residual returns vs market/sector/factors;
- 1h/1d/5d/20d acceleration;
- breadth across mapped securities;
- volume/turnover z-scores;
- gap and intraday persistence;
- cross-sectional dispersion;
- rolling pair/subtheme correlation;
- event-time abnormal returns;
- options volume/skew/IV where licensed and useful;
- estimate/EPS/revenue revision breadth;
- earnings surprise and guide changes;
- short-interest/borrow only if reliable.

### Investigation trigger

A broad parent theme can be weak while a narrow subtheme is strong. Trigger when a minimum breadth of high-exposure names shows significant positive residuals/volume/co-movement relative to parent, especially when paired with recent evidence deltas.

Thresholds must be learned from historical false-positive/true-positive rates. Start conservative and run shadow.

---

## 12. Point-in-time outcome learning

Create an immutable prediction ledger.

```yaml
prediction_id:
as_of:
event_id:
thesis_id:
signal_version:
model_versions:
ontology_version:
source_versions:
alerted_at:
expected_direction:
expected_horizon:
confidence:
expected_magnitude_band:
evidence_available_as_of:
market_data_snapshot_ref:
consensus_snapshot_ref:
later_outcomes:
  rel_1h:
  rel_1d:
  rel_5d:
  rel_20d:
  rel_60d:
  estimate_revision_20d:
  realized_earnings:
```

### Backtest law

- event-time timestamps normalized to market calendar/timezone;
- no revised source data unless revision existed at `as_of`;
- delisted/acquired names retained;
- universe membership point-in-time;
- syndicated stories clustered before counting;
- consensus/estimates point-in-time;
- taxonomy edges use the version known then;
- transaction costs/slippage only when evaluating executable strategies;
- research signal performance separated from portfolio policy performance.

Learn calibration by `source × event_type × subtheme × thesis_state × model_confidence × tape_state`.

Graduation:
`research_only → shadow → portfolio_input → accepted_production_input`.

No automatic trade authority is granted by statistical performance.

---

## 13. Optics golden replay

Build a point-in-time replay corpus covering at least June–September 2026.

Minimum checkpoints:

1. June 8/10: InnoLight 1260H designation/publication.
2. Aug 4: credible report of possible FCC restriction on new Chinese optical transceiver models and immediate U.S. optics market reaction.
3. Aug 5 onward: Research Vault/sell-side supply-shift evidence.
4. Aug earnings/company guidance for LITE/COHR/AAOI/CIEN and relevant peers.
5. Aug 25: Coherent announces planned PhotonLink launch.
6. Sep 8/15/17/20/21: company product/architecture evidence around CPO/NPO/ELS/scale-across/pluggable optical systems.
7. Sep 21: Coherent PhotonLink launch includes >10 CPO engagements, >10 NPO engagements, anchor customers/LTAs and expected Q4 CY2026 revenue ramp; Lumentum product evidence.
8. Sep 24: S.5548 introduced and referred.

For every checkpoint ask:
- what evidence existed exactly then?
- what ontology nodes changed?
- which companies had direct/indirect exposure?
- what was the economic mechanism?
- what was already priced?
- did tape independently confirm?
- what thesis state should have resulted?
- what would the alert have said without hindsight?

Acceptance: the system must produce a watch/formation state before August, an investable or explicitly justified non-investable state by the August catalyst window, and a later confidence/tactical re-acceleration only when evidence supports it. Do not hard-code the desired answer; the replay must be able to falsify this hypothesis.

---

## 14. Institutional source strategy: build vs buy

### Build/direct

Use direct official/company sources for authority, timestamps, revision semantics and full control:
- Congress/GovInfo;
- Federal Register/Regulations;
- SEC EDGAR;
- agency releases/dockets;
- company IR/filings;
- selected standards/public technical sources.

### Buy selectively

Use vendors where they provide a demonstrated advantage in:
- ultra-low-latency wires;
- normalized global company news;
- transcripts;
- point-in-time consensus/estimate revisions;
- options/market microstructure;
- licensed full text;
- historical archives;
- entity symbology.

Vendor evaluation matrix:
`coverage, p50/p95 latency, timestamp semantics, historical depth, corrections, identifiers, licensing/full-text rights, redistribution, API reliability, rate limits, cost, support, point-in-time guarantees`.

Never let a vendor's taxonomy become the canonical ontology. Map it into Mastermind.

---

## 15. Intelligence UX

Every high-materiality intelligence object should answer:

- **What changed?**
- **Why now?**
- **Source/lifecycle:** rumor, draft, introduced bill, final rule, company announcement, etc.
- **What thesis changed?**
- **Affected subtheme/products/components.**
- **Beneficiaries/losers and why.**
- **Economic scenario range.**
- **Tape confirmation/divergence.**
- **What is already priced?**
- **Confidence and contradictions.**
- **Next catalysts/falsifiers.**
- **Exact evidence links/spans.**
- **What Mastermind knew before this event.**

This is the decision surface; raw headline streams remain drill-down evidence.

---

## 16. Observability and operations

Dashboards/alerts:

- source freshness/lag/silence/gaps;
- ingest success and schema drift;
- event dedupe cluster rates;
- unclassified/low-confidence queue;
- ontology unknown-node rate;
- model schema/error/abstention rates;
- cost per 1k documents and per material event;
- thesis update latency;
- alert latency;
- economic-model validation failures;
- shadow-signal precision/calibration;
- replay/backfill divergence;
- data-license policy violations;
- end-to-end golden canary.

Disaster recovery:
- immutable raw evidence references;
- replayable normalization;
- versioned ontology/models/formulas;
- idempotent event/thesis updates;
- source cursor recovery;
- no duplicate alert after replay;
- explicit `EFFECT_UNKNOWN` for modifying downstream actions.

---

## 17. Security, governance and licensing

- secrets only in incumbent secret owner;
- least-privilege source credentials;
- no model sees credentials;
- untrusted document text is data, never authority;
- prompt-injection-resistant extraction;
- allowlisted outbound fetchers;
- evidence provenance on every derived object;
- PII minimized;
- licensed full text stored/served only under contract;
- model provider retention/training settings governed;
- material model outputs independently reviewable;
- no model-created portfolio/trading authority.

---

## 18. Work breakdown and sequencing

### W0 — Current-state census + research audit [P0]

Owner: Fable principal + independent auditor.

Deliver:
- reconcile existing ingestion, Research Vault, earnings, themes, market data, model router, Fabric/VPS and portfolio interfaces;
- audit deep-research report claim-by-claim where available;
- optics point-in-time source pack;
- gap map: reuse / extend / replace / do-not-build.

Done when: every proposed component has an incumbent owner decision and no duplicate plane is introduced.

### W1 — Source registry + authoritative connectors [P0]

Start with Congress/GovInfo, Federal Register, Regulations, SEC, FCC, BIS, Treasury/OFAC, White House and company IR.

Done when: source cursors, revisions, backfill and silence detection are proven by injected misses/revisions.

### W2 — Evidence ledger + event normalization [P0]

Done when: same story from primary + wire + syndication becomes one evolving event cluster with correct lifecycle and provenance.

### W3 — Ontology/graph v1 [P0]

Seed AI infrastructure/optics plus two unrelated validation domains (e.g. power/grid and healthcare policy) to avoid optics overfitting.

Done when: temporal many-to-many mappings support event→subtheme→company→security and supply-chain reasoning.

### W4 — Persistent thesis engine [P0]

Done when: evidence updates existing theses, contradictions can lower confidence, stale theses decay, and new headlines do not create duplicate theses.

### W5 — Model routing/evaluation [P0]

Benchmark local Qwen and incumbent cheap/standard models on frozen Mastermind tasks. Integrate with existing Capacity/Model Router.

Done when: routing is evidence-based, cost/latency measured, fallbacks explicit, and high-materiality escalation works without duplicate orchestration.

### W6 — Economic/earnings bridge [P0]

Done when: event scenarios produce deterministic auditable revenue/EPS/FCF ranges against point-in-time company/consensus inputs with unit validation.

### W7 — Tape/subtheme confirmation [P0]

Done when: narrow subtheme leadership can trigger investigation even if parent theme is weak, with false-positive rate measured in shadow.

### W8 — Outcome store/backtesting [P0]

Done when: optics and cross-sector historical replays are leakage-safe and reproduce exact as-of state.

### W9 — Signal + portfolio interface + UX [P1]

Integrate research/shadow signals into incumbent portfolio intelligence. Do not create a new portfolio engine.

### W10 — Institutional hardening [P1]

Latency, failover within authorized source policy, replay, DR, observability, licensing, security, cost budgets, chaos tests.

### W11 — Production acceptance [P0/P1 gate]

Real-path optics replay plus live canaries across government, company, earnings and tape sources. Independent audit before any portfolio graduation.

---

## 19. The 20% that captures ~80% of value

Build these first:

1. source registry/reconciliation for the highest-authority/highest-impact sources;
2. immutable evidence timestamps/provenance;
3. granular ontology + entity/supply-chain mapping;
4. persistent thesis state;
5. local cheap-model extraction/dedupe with strong-model escalation;
6. subtheme tape detector;
7. optics point-in-time replay and outcome store.

Defer:
- exhaustive international government coverage;
- patents at scale;
- exotic alternative data;
- fully autonomous causal discovery;
- complex graph databases before relational/document representations prove insufficient;
- portfolio automation;
- ultra-low-latency infrastructure below the actual source/vendor publication latency.

---

## 20. Fable orchestration handoff

### Mission

Own the program until the institutional market-intelligence flywheel is production-proven end to end. Preserve existing Mastermind authorities. Decompose implementation into bounded, independently testable verticals and route each to the least-scarce capable worker.

### WHY FABLE

Concrete C3 witnesses:
- unresolved cross-system boundaries among ingestion, Research Vault, earnings, themes, model routing, Fabric/VPS, portfolio and evaluation;
- architecture decisions change canonical data contracts and persistent intelligence state;
- long-horizon integration requires continuous adjudication of source truth, point-in-time semantics and duplicate-owner risk;
- acceptance requires cross-domain forensic reasoning, not merely code completion.

### Fable must not

- become the default coder for every wave;
- create a second scheduler/queue/model router;
- bypass #983/#515 Fabric owners;
- directly arm providers because a canonical route is incomplete;
- equate source merge with production proof;
- authorize trading/portfolio effects;
- rewrite historical evidence to make the optics thesis look earlier.

### Required routing receipt per child

```
TASK_COMPLEXITY:
BUSINESS_IMPACT:
EXECUTION_RISK:
AMBIGUITY:
TOPOLOGY:
FRONTIER_WITNESS:
PREFERRED_AVENUE:
WHY FABLE or WHY NOT FABLE:
EXPECTED OUTPUT:
ACCEPTANCE PROOF:
```

Default bounded engineering to Codex/Terra/Luna; use Sonnet/Opus for specific difficult bounded work; reserve Fable for principal ambiguity/integration.

### First actions

1. Re-pin current protected procedure and master.
2. Read #1202, this plan, #983 and #515.
3. Reconcile current Fabric/VPS state and incumbent source owners.
4. Locate the completed deep-research report and produce a claim-level audit ledger: `claim → source → status → correction → architecture consequence`.
5. Build the optics point-in-time golden corpus.
6. Freeze canonical schemas only after mapping incumbent schemas to avoid duplication.
7. Commission W1/W2/W3 as separable bounded verticals with independent reviewers.
8. Establish shadow-only acceptance before portfolio integration.

---

## 21. Acceptance matrix

The program is not done unless all are true:

- [ ] source registry covers P0 primary sources with reconciliation;
- [ ] source silence/miss/revision injection tests pass;
- [ ] immutable first-seen/published/effective/alert timestamps exist;
- [ ] dedupe prevents syndicated confidence inflation;
- [ ] event lifecycle distinguishes rumor/proposal/bill/final/effective;
- [ ] ontology resolves optics to component/product/architecture depth;
- [ ] temporal supply-chain/company mappings have provenance;
- [ ] persistent thesis engine accumulates and contradicts evidence;
- [ ] cheap-model routing meets frozen precision/recall and abstention thresholds;
- [ ] economic scenarios are deterministic, unit-safe and evidence-backed;
- [ ] tape layer detects narrow subtheme leadership independently;
- [ ] point-in-time replay is leakage-safe;
- [ ] optics replay creates useful thesis state before S.5548 without hindsight hard-coding;
- [ ] at least two unrelated domains validate generality;
- [ ] shadow signals have measured calibration/false-positive rates;
- [ ] portfolio interface uses incumbent authority;
- [ ] Fabric/VPS integration is real-path proven for required workloads;
- [ ] latency SLOs measured from source publication to alert;
- [ ] source/model/data costs are observable and bounded;
- [ ] licensing/security review passes;
- [ ] production canaries and replay recovery show no duplicate events/alerts/effects;
- [ ] independent audit accepts the end-to-end user/machine journey.

---

## 22. Immediate implementation frontier

The next safe implementation frontier is **not** “build everything.” It is:

1. current-state/source-owner census;
2. claim-level audit of the research report;
3. optics golden corpus;
4. canonical source registry + evidence/event schema mapping to incumbent code;
5. first vertical: one government source + one company/SEC source → event → optics subtheme → persistent thesis → shadow alert → outcome record.

Once that vertical is real and replayable, expand source breadth and economic/tape sophistication while preserving the same canonical contracts.

This sequence maximizes verified learning per unit of engineering and prevents a large, expensive data platform from being built before the intelligence flywheel itself is proven.
