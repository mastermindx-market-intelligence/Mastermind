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

## Real-input CPI source component (subsequent F0 evidence)

See MARKET_EXPERIENCE_F0_CPI_PROTOCOL_2026-09-24.md,
MARKET_EXPERIENCE_F0_CPI_RECEIPT_2026-09-24.json and
MARKET_EXPERIENCE_F0_CPI_FINDINGS_2026-09-24.md. This extends, not replaces,
the synthetic temporal-contract evidence above. Source pin for this component is
Macro b9d23ca4bce4308fa7466c4e0f5d318168a50f6f. The existing collector manifest
and exact CPI parquet bytes were verified; the native release-target owner
normalized 292553 real rows without loss and passed six fixed vintage/cutoff
structural checks. No new source intake, source store, product or learner.

Coverage must show observation periods separately from source-vintage periods:
1947-2026 observations here coexist with 1997-2026 vintage dates. This does not
establish 1947 operational knowledge, intraday availability or stock-universe
coverage. The collector manifest does not establish ML rights. Training and
promotion remain disabled; the overall stock pilot is still not admitted.

## Metadata-only identity/universe boundary (same F0 continuation)

Receipt: MARKET_EXPERIENCE_F0_IDENTITY_METADATA_2026-09-24.json, derived from
five exact existing owner artifacts at Macro b9d23ca4bce4308fa7466c4e0f5d318168a50f6f.
Host process 23815 read immutable Git bytes, captured SHA-256/Git blob identities,
read parquet footers, and decoded only membership snapshot_date/suite/source_shape.
No price/fundamental value columns, earnings bodies or stock outcomes were decoded.
No cohort selection, registration or production-data admission occurred.

| Existing source | Observed metadata | Consequence for the pilot |
|---|---|---|
| data/reference/_receipt.json | generated_at=2026-09-21T03:19:29, no explicit timezone; directory/CIK snapshot 2026-09-21 | Preserve the literal timestamp. Do not invent UTC or historical acquisition. Row-level clocks require their own native checks; this does not invalidate the entire identity spine. |
| data/reference/security_master.parquet | 2380 rows; stable security/issuer/listing IDs and effective_at/ingested_at columns | Identity substrate exists; row count is not historical index membership or issuer coverage. |
| data/reference/vendor_aliases.parquet | 6035 rows; vendor, security_id, valid_from/to, ingested_at | Resolve with the native historical-mode reader; current catalog aliases must not supply historical naming. |
| data/baskets/membership_history.parquet | 3114 rows; three snapshots from 2026-08-13 through 2026-09-04; suite=baskets | These are US thematic baskets, not S&P 500 constituents. They cannot substantiate a five-year index-membership universe. |
| data/breadth/constituents.parquet | 503 rows; columns name/sector/symbol only | This artifact alone has no historical membership or known-at dates. Do not back-apply it to a five-year universe. |

Native owner law: engine/theme_graph/identity_resolution.py at this pin (blob
8eefa1c2f5e5d3514f6487bf869f154ce2751011) forbids current-catalog vendor spaces
from serving as historical naming evidence. engine/basket_membership_pit.py
(blob 595d57405a36d445584ce4abfc2aee679f535d4c) explicitly labels fallback to
current memberships pit=False for dates before its history. These are useful
existing safeguards to consume, not new bugs or justification for a parallel store.

Falsified assumption: an available security master plus a current constituent list
already supplies the proposed historical pilot universe. It does not. This is a
bounded finding about the inspected sources, NOT proof that no suitable historical
membership dataset exists anywhere in the estate. The next recovery belongs to
the existing Data OS/universe owner: produce a source-bound historical membership
manifest and permitted-use evidence, or leave those issuer-periods uncovered.
Never silently switch to a survivor-only or current-member backtest.

Reproduce the metadata receipt by reading the five listed paths with
`git show <pinned-commit>:<path>`, checking SHA-256/Git blob, and using
`pyarrow.parquet.ParquetFile` footer counts/schema. Decode only the three declared
membership metadata columns for snapshot range/count. No source writer is involved.
The receipt's coverage block (708/718 resolved) is the producer's own named
coverage population, NOT the 2380-row master denominator or a 500-issuer score.

## Historical S&P membership source recovered by reference; removal-day falsifier

Continuation source pin: Macro 5600bb63b27978031769eb428911fe9b46572a92; protected Mastermind a29161fa0a44cca9927afe042b5f7ea25aae1736. Targeted source search found an existing acquisition path in scripts/residual_alpha_pit.py (blob cc3bd319a1c00fabba5e8d95df176be7402aedc7). It names fja05680/sp500/sp500_ticker_start_end.csv and writes data/breadth/sp500_pit_membership.parquet. That exact object is absent in current Macro Git and at the checked macro-main local path. This resolves the prior owner-location question; it does not prove global absence or justify another collector/store.

Upstream recovery reference: fja05680/sp500 at a2430f2af0c79ddf0748e91de11bdeb1616ab5a7. The exact interval table, original updated snapshot table, README and MIT LICENSE have been bound by Git metadata in MARKET_EXPERIENCE_F0_MEMBERSHIP_RECOVERY_2026-09-24.json. The README describes a book-associated seed plus subsequent Wikipedia/manual updates and potential early incompleteness. Repository licensing and source availability are not automatically accepted commercial/index-data/ML rights. Keep rights review with the existing owner; no cohort, new source, purchase or training is admitted.

A concrete source-semantics mismatch is now identified. Upstream PIT to Ticker Delta.ipynb cell 3 sets end_date when the ticker first disappears from a snapshot. Its interval is therefore start-inclusive/end-exclusive. Macro scripts/s13_reversal_phase0.py::_eligible instead tests end_date >= d. Mastermind loop/single_name_panel.py::members_asof already tests end_date > t and handles disjoint re-entry intervals. Reuse that existing correct reader for the proposed pilot, after source and identity admission; do not add another membership reader. No existing consumer is changed here and no live-score or historical-performance impact is claimed.

New research fixture research/market_experience_membership_boundaries.py reproduces the two reviewed executable function excerpts on synthetic entry/removal/gap/re-entry/open-end cases without importing the original modules or their TrialLedger. Seven date cases agree with the end-exclusive convention; the inclusive reader has one constructed removal-day mismatch. Container tests: 15 passed, 1 explicitly skipped, 0 failed. The skipped actual-repository AST equality check must execute in repository CI; absent native source fails CI unless the explicit excerpt-only test mode is selected. Source-only checksums on the Studio match the two tested files. This is a regression about code semantics, not a real-corpus benchmark or a new production service.

The frozen 20-date interval-versus-snapshot comparison remains NOT_RUN. The isolated computation environment had DNS failure for the download host, and no raw CSV was acquired there. The public GitHub reads and code inspection succeeded separately. Do not substitute synthetic results, notebook output counts or current membership for that missing corpus comparison. The observed MIT source is a recovery candidate, not blanket data-rights proof. Failed container downloads are technical acquisition failures, separate from the refused compound host-recovery request; no denied request is retried.

Exact next capability: obtain the two pinned upstream source objects through the existing universe/source owner, verify their Git hashes, run the frozen comparison with end-exclusive semantics and explicit coverage bounds, then bind canonical historical security/issuer resolution and earnings metadata. Restore or qualify the existing pipeline only under its current source custody; do not blindly execute residual_alpha_pit.main(), which also downloads delisted price data and writes canonical paths. The original strategy-date test repair and independent review remain open. No bulk upstream table, price, earnings body or outcome is republished in this unit.
