# F0: owner contracts, falsifiers, and measured temporal-filter cost

Status: PARTIAL. This is an integration crosswalk and research receipt, not a new data contract,
identity registry, admission service, feature store, evaluator, or runtime owner.

Mission: make the Chairman's market-experience direction executable without duplicating the
existing systems or representing retrospective reconstruction as the system's actual experience.
Meta-CEO retains integration/acceptance. Direct work reason: PRINCIPAL_JUDGMENT for the boundary
between public knowledge, operational possession, current-rule reconstruction, and served output.
No child worker, model call, paid service, production writer, or trade authority is started here.

## Exact evidence

Mastermind parent candidate: #967 / 4d8e17abfa245b3519a5950067e1fc87ac9936fa.
Protected procedure: 5060527c1d52639eb1bfd84413ab7419e7470cbd, Skillpack 1.0.1;
required procedures and delivery workflow were reloaded and byte-compared with the prior pin.
Macro source pin for this crosswalk: cdcfbb27681efcd86151dfb2149633f0b343dfde.
Source existence is not production acceptance. Old Agent OS next-action dates are not liveness.

| Owner file at the Macro pin | Git blob | Inspected contract |
|---|---|---|
| lib/dataos/temporal.py | 094b149a8b9158f19cb99c4005568c12db96ed41 | Full stdlib temporal owner, including known_at and as_of_filter |
| engine/neuralweb/market_memory.py | adffe89b75ea72d58d06fc6618da7ba487b6598a | Lines 105-228: canonical modes, PIT bases, domains, FeatureSpec and initial feature contracts |
| engine/company_intelligence/event_workspace.py | efdbd91156b2a94e6e8bdca7e8cae454a6860e68 | Lines 1-156: closed workspace/manifest keys, generation chain and authority |
| engine/theme_graph/store.py | 63b58860d35bd183c947c85088f83bd53359bb9f | Lines 1-157: append-only semantics, column sets, identity bridge and rights columns |

## Owner-to-owner crosswalk

| Required integration concept | Use the existing owner | Required boundary / missing proof |
|---|---|---|
| Publicly knowable observation | Data OS profile-specific known_at and as_of_filter | Publication-first coalescing is not evidence of operational possession. Missing public time may use later ingestion conservatively; never replace it with event/period time. |
| Actual operational experience | Market Memory operational_pit and actual-output owners | Require its accepted acquisition/receipt and served-output evidence. Do not invent another max(clock) policy in this adapter. |
| Retrospective reconstruction | Market Memory public_reconstruction and declared PIT basis | Keep source_vintage, public_reconstructed, recomputed_history, current_snapshot_backfill and unknown distinct. Current computation is not a historical system output. |
| Feature definition | Market Memory FeatureSpec and canonical feature/source registries | Preserve domain, unit, value_schema, required/allowed source roles, availability classes and transform version. Registry strings observed: feature_registry.2026-08-09.v1 and source_registry.2026-08-09.v1, both prefixed market_memory. |
| Company event identity | Earnings event_workspace.v1 event_id, aliases, issuer and fiscal_period | Resolve through existing issuer/event registries, not ticker-only matching. No extra top-level workspace key. |
| Event evidence revision | Earnings generation_id, sources, manifest v2 predecessor chain | generated_at is not source publication or acquisition. Reuse exact source/manifest references; nested source availability must be audited before an adapter is admitted. |
| Earnings absence | Existing warnings and typed-absence owner | consensus_unlicensed and reaction_not_joined are explicit warnings; never synthesize a beat/miss or response from absent evidence. |
| Semantic membership | GMI edge_id, src/dst, valid_from/to, evidence_time and belief_time | Preserve validity time versus belief time. Raw/latest membership is not historical membership. Reuse the accepted as-of reader; its exact current API/proof still needs recovery. |
| Cross-owner security identity | GMI identity_resolution sidecar and Data OS master | Preserve issuer_id, security_id, listing_key, resolution_asof/state, source receipts and master vintage. Unresolved joins remain unresolved. |
| Rights | GMI evidence licensing_internal_ok/display_ok/redistribution_ok and native source-rights owners | Internal analysis, display, redistribution and model training are different permissions. These columns alone do not demonstrate ML-training entitlement. No source has been rights-admitted by this F0 probe. |
| Revision selection | Native dataset vintage reader | as_of_filter returns all eligible revisions; it is NOT a latest-revision selector. Do not flatten them with keep-last or current snapshots. |
| Forecast/trial/outcome | Existing domain evaluator, Trial Ledger and Research Factory projection | This probe creates no experiment registration or model promotion. Memory, analogy and model agreement never supply rank/size/action authority. |

## Executable falsifiers

research/market_experience_f0_probe.py loads the exact hash-verified native Data OS module from
an existing checkout. It executes those verified source bytes without persisting a clone or a
bytecode cache. It does not change Data OS. All rows supplied to the probe are synthetic and
explicitly labelled; none enters a market store, historical evaluation or production consumer.

Eight native boundary observations passed:

1. An event published before the cutoff but acquired later is included by the publication-first
   EVENT filter. Therefore this output cannot by itself prove that Mastermind possessed it.
2. With publication absent and ingestion after the cutoff, the row is excluded.
3. A revision published after the cutoff is excluded at the earlier cutoff.
4. Once both revisions are known, both remain in the filter output. Dataset-native vintage
   selection is a separate necessary step, not something the filter promises.
5. An INTELLIGENCE object computed earlier but served later is excluded before serving.
6. DERIVED cannot masquerade as operational replay: PointInTimeError.
7. Naive publication timestamps are refused: TemporalError.
8. Event time without either availability clock is refused: PointInTimeError.

These are observed contracts, not findings that the owner is defective. The falsified integration
assumption is that one generic as-of filter also supplies possession, vintage selection, source
rights and replay proof. The first adapter must consume the specialized owners instead.

## Measured microbenchmark

Receipt: research/MARKET_EXPERIENCE_F0_PROBE_RECEIPT_2026-09-24.json.
Observed at 2026-09-24T12:31:57.188848+00:00, Darwin / Python 3.14.7.
Probe SHA-256: 0c2bc2ec4e2a425b014b469d3dbee4df0fb60b66b4c9650c7a05e9e1d708e813.
Temporal owner SHA-256: 4415404186f0b0d2870f42d9e4a0b95be87937863adf30cf015ed34e8bf92b67.

| Synthetic metadata rows | Median filtering wall time, three passes | Retained | Process lifetime peak RSS |
|---|---:|---:|---:|
| 2,000 | 0.001498 seconds | 1,000 | 28,295,168 bytes |
| 63,000 | 0.045395 seconds | 31,500 | 50,888,704 bytes |

Per-pass CPU times, raw timings and construction time are in the receipt. Peak RSS is the
process-lifetime high-water mark, not incremental stage memory or a maximum for the programme.
The row count matches the illustrative pilot's stock-day count, but these are NOT stock-day
histories, 512-feature tensors, text documents, earnings events or graph queries. Do not multiply
this rate into an ingestion, training, fleet-capacity or full-backfill promise. No p95 is claimed
from three passes. This measurement supports only that this native metadata-filter stage is small
on the tested host. It does not justify a hardware purchase or provider choice.

Instrumentation tests: 20 passed in 1.99 seconds, host process 31960, exit 0.
Production data admitted: 0. Model calls: 0. Incremental provider spending: $0.

## Pilot-selection and admission frontier

The 50-issuer/five-year shape remains a capacity scenario, NOT a selected or admitted cohort.
Do not invent ticker membership, source availability, historical sectors or training rights to
finish the manifest. Do not pick the companies with the easiest surviving documents after inspection.

Next manifest must reference the existing historical identity/universe snapshot and source-rights
receipts. Freeze decision dates, universe rule, era, sample seed/strata, missingness treatment,
source cutoffs and source revisions using metadata before any outcome or sealed-body inspection.
Issuer turnover, inactive names and dual-class securities must follow existing identity owners.
An incomplete source stays in the declared missingness denominator rather than being silently replaced.
No existing earnings/GMI holdout is reused as untouched acceptance evidence.

The first pre-forecast capability should reconstruct one eligible event context in the existing
consumer with explicit public-versus-operational mode and visible missingness. Historical retrieval
and forecasting stay held until the native availability/vintage/identity/rights joins are proven.
A price/macro-only baseline is a separately preregistered scope, never a quiet substitute for missing
earnings evidence. Extraction token distributions, actual source bytes, peak working sets, and cost
per accepted record remain unmeasured and must be returned by the licensed-input benchmark.

## Release and action boundaries

Mastermind #967's earlier CI run 35994389322 failed at
 tests/test_chairman_cognition_source_contract.py:308 because it requires the global strategy as_of
 to equal 2026-08-30, while this Chairman-directed strategy change correctly dates it 2026-09-24.
No other failure was identified in the bounded failure excerpt. Independent review remains absent.
The proposed repair should test a valid strategy date not predating the cognition objective while
preserving the existing objective, constraints, resource sum and review-trigger assertions.

A current source-collision inspection for that existing test was explicitly refused before dispatch.
The test is not edited here; that denied request is not retried or moved to a different tool/provider.
A later compound source-inventory/API-inspection request was also refused before dispatch; no dataset
read/admission effect is claimed from it. These are action-scoped tool limitations, not proof of an
entire platform outage. The independent new F0 source work and measurements above succeeded.

Macro #7936's ci-gate and main authority checks passed at its existing head. The separate
ci-authority/codex/merge-queue-pilot failure explicitly reports inactive_base_context for base main;
that is not an Agent OS validation failure. Required-check membership and release acceptance must
still be resolved through the existing release owner. No gate is bypassed and no merge is claimed.
