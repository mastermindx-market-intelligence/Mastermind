# W1 equal-duration descriptive comparison — development result

**Capability state: BUILT_NOT_PROVEN / DEVELOPMENT ONLY.** This result is subordinate to parent Mastermind #1183 and W0 child #1195. It does not close W0, register `issuer_state_transition.v1`, admit annual/YoY semantics, create public rights, register a trial, or prove a production path.

## Why this comparator exists

Current FIF source law distinguishes a typed `annual` period from a generic `duration`. A typed annual period requires explicit fiscal-year semantics. The current financial-query wire contract admits only `duration` and `instant`; the current Financial Intelligence Packet schema likewise emits only those two wire period kinds. The captured AAPL owner cells therefore cannot become annual merely because their labels say FY2024/FY2025 or because each interval infers 52 weeks.

The W1 positive demonstration is consequently narrowed to a factual statement the existing owner bytes can support:

> reported AAPL revenue over two adjacent, equal-length, same-filing generic duration intervals changed by the amount shown below.

It does **not** say annual revenue, YoY growth, fiscal-year growth, organic growth, acceleration, material improvement, inflection, or investment signal.

## Exact verified input

Owner response SHA-256:
`a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af`

Method-before-execution SHA-256:
`b183fa79087c1f2bc4f53f6eba345553cfbb1eed55d6751c1ce3af525dbf7c08`

Both owner cells are:

- metric `revenue` / `metric.revenue/v1`;
- mapping `mapping.revenue/v1`, mapping digest `ef978677cbbce3a8f65ae7910e5ea1a772df296bae81fe91fe599f6b5e7ff5aa`;
- concept `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`;
- USD with empty explicit and typed dimensions;
- exact same SEC source revision: accession `0000320193-25-000079`, document `sec_document_d23a609841f9a32489dd7abc952d39622540f8a24905612bda1d43e5577860b8`, source-body SHA `548ae59778cf08ee0f2ee088e7ece20d947076c3c01f74d2d65db4c2777e436a`;
- reported XBRL `decimals=-6`, `precision=null`;
- generic `duration`, `calendar_kind=unknown`, `fiscal_year=null`, `fiscal_year_weeks=null`, `week_count=null`, `semantics=[duration]`.

Intervals:

- prior: 2023-10-01 through 2024-09-28, 364 inclusive days;
- current: 2024-09-29 through 2025-09-27, 364 inclusive days.

They are adjacent and non-overlapping. Their source display labels are retained but excluded from the semantic comparison identity.

## Development result

Deterministic comparison identity:

`i3devcmp_75b3515ed838ab4f97ac8ed9`

Reported-value arithmetic:

- prior: `391035000000 USD`;
- current: `416161000000 USD`;
- exact reported-value difference: `25126000000 USD`;
- exact percentage over the reported values: `502520 / 78207`;
- single half-even display: **6.43%**.

Flags remain:

- `owner_typed_annual=false`;
- `annual_or_yoy_claim_permitted=false`;
- `comparison_admitted=false`;
- `product_publication_admitted=false`;
- `trial_registered=false`;
- `emitted_at=null`;
- authority `context_only / display_only`;
- economic interpretation `null`.

The exact machine record is `evidence/equal-duration-comparison/result.json`. R2 verification receipt: `evidence/EQUAL_DURATION_COMPARISON_R2.json`. The semantic identity now also binds owner source-native issuer `0000320193`; changing the cell, provenance, selected-source, or XBRL-context issuer refuses instead of preserving the same comparison ID.

Before comparator-specific checks run, `load_verified_comparison()` now reuses the shared `baseline_replay.owner_snapshot()` owner-response validator. That validator binds the canonical metric-query receipt schema/proof scope/selection proof, declared entity/metric/period membership, recomputed unsigned-receipt `query_hash`, status/state and reason consistency, selected-fact issuer/period/unit/source/clocks, and coverage. Comparator code therefore owns equal-duration comparability + arithmetic rather than a second partial FIF response parser.

## Adversarial verification

`test_equal_duration_comparison.py` currently has **22 passing tests**. It refuses:

- annual relabeling;
- unequal or overlapping/non-contiguous intervals;
- a different filing revision;
- metric/definition/mapping/concept drift;
- unit or dimensional-scope drift;
- reported precision mismatch;
- non-value/refused cells;
- nonpositive percentage baselines;
- response-identity substitution;
- cell/provenance/source/context issuer-identity drift;
- value `status/state` disagreement or refusal reasons on value cells.

It separately proves that changing FY display labels does not change the semantic comparison identity.

The normal repository consumer entry `tests/test_i3_baseline_fixture_consumer.py` now includes this comparator suite beside the existing baseline, source-binding and verified-reader suites.

## What remains open

This development result satisfies the **positive mathematical comparison demonstration** only. It does not satisfy:

- typed annual/fiscal-year or YoY admission;
- source-owner acceptance of a new financial wire period kind;
- public/model-use rights;
- authenticated Terminal/Macro integration;
- actual experiment/exposure registration;
- independent exact-head architecture review;
- green release CI;
- production producer→user/machine proof.

The existing cross-filing asset case remains independently refused until FIF supplies owner-issued cutoff-visible lineage. No comparison result here weakens that refusal.
