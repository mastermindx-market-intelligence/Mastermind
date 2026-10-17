# C16 — reconcile both reports around incumbent source uses

Partial MAS-266 dossier. Verdict: **preserve both reports; qualify one existing source-to-KPI-to-consumer path before any company-effect or commercial expansion**. MAS-277 remains dependency-held; this source review does not launch P1.

## Immutable originals and retained findings

- C16A, [Macro #8420 masterplan](https://github.com/mastermindx-market-intelligence/macro/blob/5a1400c4817e3f239d50de066aca00343171a6b5/research/operational_sensors/COMMISSION_16_OPERATIONAL_ALTERNATIVE_DATA_MASTERPLAN_2026-10-04.md), head `5a1400c4817e3f239d50de066aca00343171a6b5`, with its estate census, diligence, audit and manifest.
- C16B, [Mastermind #1238 hardened report](https://github.com/mastermindx-market-intelligence/Mastermind/blob/087566cb8a11d33a4b1d02d8e5177fa772fbbd94/research/commission16_operational_sensors/COMMISSION_16_HARDENED_REPORT.md), head `087566cb8a11d33a4b1d02d8e5177fa772fbbd94`, with its audit, sources and manifest.

Both describe proposed, unexecuted follow-on work. Retain their measurement-first rule: source qualification, operational-KPI skill, incremental expectation information and investment value are different claims. Preserve mapping generations, denominators, correction history and adverse missingness. One source needs a specific KPI bridge and accepted consumer; a broad sensor warehouse is not the outcome.

The two returns are complementary research, not competing permissions or two implementation programs. C16A's source census identifies adjacent DOL hiring and Census trade owners; C16B also identifies them and reports a bounded Census artifact inspection as `parquet_absent=true`, 0/29 codes and 0/11 themes. Those are **original-author observations at their evidence cuts**, not fresh runtime measurements or proof that all trade data is absent today. Preserve the distinction between source code, rendered output and real measured coverage.

## Current recensus: one concrete existing consumer

Macro source pin: `9201f1602bfe47e05a63d61802fbed6f7f55a19d`.

| Existing surface | Source evidence and boundary |
|---|---|
| [`collectors/eia.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/eia.py), `EiaAdapter.fetch`, `_fetch_one` | Existing weekly series collector; per-series failures can yield partial results; all-series failure raises. Reads source spreadsheets into normal date-indexed EIA series. It is not, by this code alone, a retained release-vintage/actual-system receipt service. |
| [`scripts/build_commodities.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/scripts/build_commodities.py#L413), `_oil_supply_read` | Concrete reader calls `store.read("eia", name)`, including `refinery_util`, and places its latest finite rounded value in the oil-page supply view. It requires crude-stock context before constructing the panel; this is a real dependency, not a standalone all-series completeness claim. |
| [`engine/commodity_supply_context.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/commodity_supply_context.py), `last_value` and context helpers | Existing physical-balance display helpers; source law keeps the leaf outside scoring/conviction/alerts/MRS/latest.json. Seasonal inventory context is distinct from raw refinery utilization. |

The specific reuse candidate is **EIA weekly U.S. refinery utilization (%) → the same aggregate KPI → existing Commodity Vector oil-page supply view**. This is a source-eligibility baseline shared with C12's physical telemetry scope. It does not infer issuer exposure, revenue, EPS, expectation surprise or price direction, and does not satisfy C16's eventual company-KPI evidence requirements.

The Program CEO independently checked the exact reader, collector and context module. No Parquet data or live dashboard was read. Code references establish the intended source path, not an actual served-generation or runtime-consumption receipt. Module commentary about rapid release repricing is not new empirical evidence and does not establish a percent-already-priced conclusion.

## Dispositions, contradictions and ownership

| Disposition | Ruling |
|---|---|
| **RETAIN** | One source/measurement/consumer, native source owners, explicit correction and denominator semantics, no direct sensor-to-portfolio authority. |
| **CORRECT** | Existing DOL/trade/EIA code and a rendered panel do not prove usable historical vintages, complete coverage or consumer use. Separate original report evidence from current source and from uninspected runtime. |
| **CORRECT** | Source-as-known reconstruction and actual-system replay need different evidence. A date index/current mapping or current revised history cannot silently stand in for a past observation/recording/consumption receipt. |
| **CORRECT** | Use the concrete Commodity Vector reader for this baseline; do not invent a new generic K1 research-block consumer. K1 reference validity would not prove the economic KPI bridge or actual consumption. |
| **SUPERSEDE, duplicate routing only** | Treat both C16 reports as inputs to one owner-native integration decision. This removes duplicate proposed routing, not either original report's findings or acceptance obligations. |
| **REJECT** | All-alt-data warehouse, guessed company exposure, broad vendor-history entitlement, automatic investment effect, or a price-direction claim from a physical context panel. |

C12/C16 source overlap must remain a single underlying evidence lineage. It cannot count as two independent signals because two commissions described it. MAS-277 retains its health/native-expectation prerequisites and source-custody gates. Current writer/PR clearance was not obtained. Commercial merchant/app/logistics and company-mapping work remains a later conditional decision, not silently replaced by the aggregate EIA example.

## Bounded next slice and acceptance

When the incumbent owner accepts the scope and dependencies clear, qualify one allowed EIA generation through the existing `_oil_supply_read` path. Preserve source/publication precision, actual observation/recording, native digest/generation, metric/unit, partial-series health, correction ancestry and actual rendered/read disposition. First check for existing receipts before proposing new instrumentation. Preserve current display behavior.

Discriminating cases:

- Valid current aggregate utilization with an exact source/read generation; source unavailable versus partial other-series failure.
- Missing crude prerequisite and missing utilization remain different reasons; neither becomes zero utilization.
- Latest revised history is not admitted as an original first-release vintage; date-only publication crossing a cutoff is unresolved.
- A post-cutoff correction or changed mapping cannot alter a sealed historical answer.
- Source/retention/use rights unknown or blocked prevents the new requested use, without inventing entitlement or deleting original metadata.
- An issuer revenue/price-direction request is refused without a separately qualified exposure/KPI model; no automatic effect is added.

Historical replay is **unqualified in this review**, not proven impossible for every owner archive. A prospective receipt could qualify only after its own clocks and retention are demonstrated. Full-system collector/renderer tests and real natural-time evidence are still owed.

## Procurement, null outcomes and supersession

No paid feed was selected or contacted. Keyless access in the existing collector does not settle operation-specific retention, derivative, display or model-use rights. Engineering/retention costs, rights, complete coverage, actual vintages and incremental economic/decision value remain **UNKNOWN/NOT_TESTED**.

For any commercial candidate, require the named company KPI and reader, a causal/economic measurement bridge, denominator/mapping history, delivered original vintages/corrections, lawful rights, total cost and the cheapest adequate public/native baseline. Compare KPI skill and incremental value separately; null or inconclusive value can justify no purchase. Defer a candidate lacking lawful history, a named consumer or a defensible KPI bridge. Never rescue it by relaxing replay semantics or fabricating exposure.

Falsifier: accepted current owner receipts may prove historical retained releases, actual consumption or a company-level bridge absent from this source-only review. Reuse those facts if supplied; do not build an alternative owner. Both original C16 returns remain unchanged. This dossier reconciles a common source-use baseline and duplicate routing only; it does not close all C16 families, MAS-266 or MAS-277.
