# F0 source admissibility after real historical-membership qualification

Status: **PARTIAL / FAIL-CLOSED FOR TRAINING**. This record separates technical source quality from
rights, historical identity, operational possession and model authority. It is not a new source
registry, universe owner, feature store, evaluator or promotion plane.

## Evidence pins

- Mastermind operation: `market-experience-direction-20260924-astra-001`; existing PR #967.
- Current protected Skillpack: `605cd056c3463c992d85ba76dbcc90fbb758da75`,
  version 1.0.1. Required procedures were loaded from that same revision.
- Historical-membership upstream: `fja05680/sp500@a2430f2af0c79ddf0748e91de11bdeb1616ab5a7`.
  Interval blob `3ed3b0e8d9e6e63730c153ee1f13ddaf6ed281bb`; snapshot blob
  `656b033be9418db272f1903f4f8e79a2a8664e6a`.
- Existing acquisition owner: Macro `scripts/residual_alpha_pit.py`; do not replace it or run its
  top-level command as a membership-only act because it also downloads delisted prices and writes
  canonical data.
- Current rights/identity/event inspection pin: Macro
  `3a29e6145ce53ca4551adef866a5f73e62c8c4ff`.
- Current source-rights register blob:
  `research/licenses/PROPHET_US_SOURCE_RIGHTS_REGISTER_2026-09-23.md`
  / `a9ee6f288bfb2716facd88dcf2c5135ca8125303`.
- Massive operator entitlement record blob:
  `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md`
  / `3969a9aae918141b51baffbb0e17d8a2ec2485a0`.
- Canonical identity reader blob:
  `lib/dataos/identity.py` / `d9d5018aac47910bf2c802b1a74114a99511f74f`.
- Company event/document contracts:
  `events.py` `9d839a468ba0de2b2ea090bfe7d3ae698d303c44`,
  `documents.py` `21ef185557d54e8b4c24c4e84c6f94bf3ea1190b`,
  `event_workspace.py` `efdbd91156b2a94e6e8bdca7e8cae454a6860e68`,
  `event_workspace_build.py` `69d39a58ecc9cfd6143192f29eb2e0f62016aeb5`.

## What became true

The two pinned historical-membership representations are internally consistent over the frozen
2019-2023 diagnostic window when the interval table is read with its actual convention:
`start_date <= t < end_date`, with null end open.

Observed source structure:

| Check | Result |
|---|---:|
| interval rows | 1,262 |
| interval unique normalized symbols | 1,209 |
| snapshot rows | 2,720 |
| snapshot unique normalized symbols | 1,209 |
| source coverage | 1996-01-02 through 2026-08-18 |
| invalid rows | 0 |
| inverted finite intervals | 0 |
| overlapping same-symbol intervals | 0 |
| dot-to-dash normalization collisions | 0 |
| frozen quarter-end comparisons, 2019-2023 | 20 / 20 covered |
| end-exclusive exact member-set matches | 20 / 20 |

Quarter ends do not exercise every removal boundary. The final source date does: on
2026-08-18 the snapshot and end-exclusive interval reader both contain 503 names with identical
member-set SHA-256. An inclusive-end interpretation incorrectly retains **AVB** and **EQR**.
Therefore the existing Mastermind `loop/single_name_panel.py::members_asof` convention matches the
upstream converter; Macro `scripts/s13_reversal_phase0.py::_eligible` does not on a removal day.
No existing evaluator is changed or regraded by this F0 unit.

The exact receipt is
`research/MARKET_EXPERIENCE_F0_MEMBERSHIP_SOURCE_RECEIPT_2026-09-24.json`.
The reproducible offline checker is
`research/market_experience_f0_membership_source_audit.py`.

## What did NOT become true

Technical consistency is not source admission.

The upstream README says the older history is reconstructed from book-associated data plus later
Wikipedia/manual maintenance, warns selected changes are incomplete, and notes likely missing early
members. Its ticker strings are not durable issuer identity. The repository carries an MIT LICENSE,
but this F0 unit does **not** treat that software/repository license as a determination of rights in
the underlying S&P/index membership dataset.

Therefore:

- internal source qualification: **YES**;
- model-training use of this membership source: **NO / rights unresolved**;
- user redistribution of this membership source: **NO / rights unresolved**;
- historical operational possession by Mastermind: **NOT PROVEN**;
- announcement-time index-change availability: **NOT PROVEN**;
- stock pilot cohort admitted: **NO**.

The 50-issuer/five-year scenario remains a capacity shape, not a cohort.

## Canonical identity join

Membership tickers never become issuer keys directly. The existing Data OS identity spine remains
the only exact identity authority.

`VendorAliasTable` uses inclusive `valid_from` and exclusive `valid_to`, matching the qualified
membership interval convention. Historical naming must use the dated historical vendor spaces;
current-catalog aliases may not answer a historical naming question. The security master then
supplies the issuer axis, and issuer-level learning may aggregate only when its canonical
`issuer_state` is `RESOLVED`. Unresolved, ambiguous, evidence-conflict and deferred-identity rows
stay out of the joined denominator rather than being ticker-guessed.

This F0 unit does not materialize that join yet.

## Source admissibility for the first learning loop

The first learning loop must be assembled from sources whose **technical clocks and permitted use**
both pass. Current in-repo evidence yields this matrix:

| Source family | Technical role | Model-learning posture now | Ruling |
|---|---|---|---|
| Massive `massive_stock_day` | daily U.S. stock OHLCV, rolling history | recorded AI/ML + derived-use rights for this feed, subject to per-feed conditions | **candidate trainable price substrate after actual R2 coverage/identity audit** |
| SEC EDGAR company filings/releases | issuer event evidence with acceptance/observation clocks | current rights register records acquisition, processing, storage, model use and redistribution | **candidate trainable event substrate** |
| recovered S&P membership source | historical universe intervals | underlying index-data rights unresolved | **technical qualification only; no training** |
| transcripts `rp_public_primary_v1` | event context | profile name is not a rights grant; model use unresolved | **context-only, not a training source** |
| consensus estimates | expectation context | explicitly unlicensed | **absent; never synthesize beat/miss** |
| FRED/ALFRED CPI | macro vintage context | technically validated, but current rights register records model-use posture as UNKNOWN/not a source | **context/research only until rights reconciled** |
| Yahoo/yfinance bars | historical price context | model use and redistribution unresolved; personal-use label is adverse | **not a training source** |

The Massive entitlement record covers bars, archives, reference data, derived materials and AI/ML
at the enterprise scope, but also states that per-dataset written conditions can override it.
The current `massive_stock_day` rights row is explicitly recorded as model-usable. The store itself
is a rolling approximately five-year archive; its code records an observed floor of 2021-07-06 at
the 2026-07-03 probe. This means broad license rights do not manufacture older price history.

## Implication for the pilot

Do **not** silently execute the earlier literal 2019-2023 stock-learning pilot with the recovered
free membership source or Yahoo prices.

The first trainable market-learning slice should instead be selected only after:

1. the existing Massive R2 daily store is audited for actual date/name completeness and the exact
   per-feed entitlement remains valid;
2. membership/universe definition is supplied by a rights-qualified existing source owner, or the
   recovered source receives an explicit rights determination;
3. historical tickers join to canonical security and RESOLVED issuer identities at the decision
   date;
4. SEC-backed earnings/event metadata coverage is measured without reading a sealed evaluation
   outcome set;
5. the cohort, dates, missingness denominator and evaluation split are frozen **before** outcome
   inspection.

Until those gates pass, the system may research source mechanics and context, but it may not call
the result a trainable cohort or a validated forecasting corpus.

## Existing earnings contract to reuse

No new event model is required. The Company Intelligence contracts already carry the necessary
shape:

- canonical issuer/fiscal-period event identity;
- `source_available_at` and `observed_at` as distinct clocks;
- exact document ids, content hashes, revisions and supersession;
- filing key `(CIK, accession)`, never fuzzy date;
- typed absences and source-specific rights state;
- immutable workspace generations and correction chain;
- `context_only` authority and false rank/size/gate flags.

The next event-coverage audit should project only source metadata and rights state first. Consensus
remains `consensus_unlicensed`; missing reaction remains `reaction_not_joined`; transcript content
does not become a training source because it is present.

## Verification and remaining proof

New source-audit tests plus the prior membership-boundary tests: **27 passed, 0 failed**.
The first attempt to import the entire panel module failed because its vendored Macro `lib` package
was unavailable in that workspace environment. The test was corrected to AST-extract and execute
only the repository-native `members_asof` function; no fallback semantics were substituted.

Still unproven:

- current R2 Massive store completeness and per-security coverage;
- a rights-qualified historical index-universe source;
- historical identity join coverage and denominator;
- SEC-only event coverage for the eventual pilot;
- user-facing consumer;
- forecast quality, calibration or incremental value;
- any model-training cost.

No production writer, training, paid model call, forecast publication or promotion is performed by
this source-qualification unit.

## Exact continuation

Audit the **existing** R2 `massive_stock_day` manifest/store through its current owner and return
actual coverage bounds, missing-day/name diagnostics and the feed-specific entitlement reference.
In parallel, project metadata-only SEC event coverage by canonical issuer/date through the existing
Company Intelligence contracts. Do not select the stock cohort until the historical-universe rights
gate and canonical identity join are resolved.


## Live substrate census after source admission ruling

A bounded live read of the existing R2 `massive_stock_day` manifest returned HTTP 200. The object
was last modified 2026-09-24T04:33:08Z and reported 21,603 published objects: 21,602 ticker stores
plus the manifest. The embedded collector state reported:

- coverage 2021-07-06 through 2026-09-22;
- 1,361 processed weekdays;
- zero maximum missing-weekday run across the full processed range;
- zero recent maximum missing-weekday run over the trailing 90 business days;
- SPY anchor 2021-07-06 through 2026-09-22 with 1,310 rows and max calendar gap 4 days.

This is substantially stronger than a static code claim: it is a live owner manifest, but it remains
a store-level receipt. It does not prove every one of 21,602 tickers has every eligible session.
Per-security coverage and canonical identity remain the next audit.

The existing Company Intelligence event-workspace marker is healthy but narrow:
`event_workspace_manifest.v2`, generation `3be5e93e4bc42804dc816973`, generated
2026-07-30T20:30:28Z, `event_count=5`, with canonical period aliases for AAPL, DHI, KBH, PHM and
TOL. This proves the event contract is operational for a bounded issuer set; it does not provide the
broad historical primary-source event population required by the Chairman's learning vision.

The broader Earnings Intelligence health plane is genuinely broad and healthy for its current job:
at Macro `3a29e6145ce53ca4551adef866a5f73e62c8c4ff`, health blob
`6e4230c983fef1f12b8c682d1d540776d2ff038a` reports 54,834 rows, 4,472 issuers,
54,527 canonical issuer-period rows and 2,937 QoQ-eligible issuers, with a valid transported
generation and latest call date 2026-09-17. It also explicitly marks itself
`is_context_only=true` and `display_only=true`.

That distinction is load-bearing. The historical tier is the transported EquityDesk archive with a
forward score overlay. The current rights register classifies EquityDesk / earnings-call score
families as internal-only or not registered for model use. Therefore the broad earnings plane is
valuable calibration/display context but **not** the training corpus for Market Experience.

### Revised critical path

The first learning loop is not blocked on compute. Its load-bearing missing substrate is now clear:

1. **Price:** live Massive daily history is a viable licensed/model-usable candidate from its actual
   stored floor, subject to per-security coverage and identity audit.
2. **Issuer events:** the existing Company Intelligence contract is the correct owner and data
   shape, but its production event population must be expanded historically from primary SEC
   evidence rather than replaced with a new event system.
3. **Universe:** historical S&P membership remains technically qualified but rights-gated. Do not
   train on it or silently replace it with current survivors.
4. **Expectations:** consensus remains absent until a licensed source exists.
5. **Evaluation:** cohort and temporal splits remain frozen only after source/identity/rights
   admission; development-visible source audits never become untouched holdouts.

The smallest architecture-consistent implementation is therefore a historical **SEC reconstruction
path inside the existing Company Intelligence owner**. It should backfill issuer events using
canonical CIK/accession identity, SEC acceptance time as public availability, actual backfill
acquisition time as operational observation, explicit `public_reconstruction` mode, immutable
source/revision hashes and typed absence. It must never relabel reconstructed history as historical
Mastermind possession.

This does not authorize a source backfill in this F0 record. It defines the exact capability the
existing owner must provide and the acceptance conditions for the first trainable slice.

Receipt:
`research/MARKET_EXPERIENCE_F0_LIVE_SUBSTRATE_RECEIPT_2026-09-24.json`.


## SEC foundation correction: reuse before build

A fresh current-main audit found that the broad SEC event anchor and part of the historical revision
path already exist. This narrows the prior "historical SEC reconstruction" implementation proposal.

At Macro `836379db84f9e34354f54e2fb26cd2065d186034`:

- `data/edgar/earnings_8k_dates.parquet` contains 98,975 exact Item-2.02 rows across
  1,314 CIKs, 2004-08-24 through 2026-07-02;
- 1,143 CIKs span at least eight years;
- all 98,975 rows have parseable SEC acceptance times;
- the per-CIK manifest has 1,315 `ok` entries and zero recorded missing older-file shards.

But the committed store is the **legacy** five-column shape. It lacks `accession`, `form` and
`report_date`, while the current collector already specifies those fields and the canonical
`(cik, accession)` dedup. Exact revision-aware reconstruction therefore requires a migration or
source reconciliation through the incumbent collector owner, not a new event-source system.

The current Company Intelligence refresh path also already carries historical revisions for its
registered issuer set with separate SEC availability and current observation clocks. Source comments
preserve the August 2026 production incident in which an incorrectly unbounded discovery run
published roughly 170 historical homebuilder events before timeout; subsequent code bounded
first-ever discovery and canonicalized the forward boundary. This is evidence to **reuse the
revision chain and avoid another unbounded backfill**, not permission to reproduce the incident.

Revised next build:

1. migrate/reconcile the broad SEC anchor to canonical accession/form/report-date identity;
2. use one permanently development-visible issuer to prove keyed anchor → exact SEC release bytes →
   existing Company Intelligence workspace in a non-publishing sandbox;
3. label the consumer-side result as `public_reconstruction` and retain current acquisition time;
4. only then broaden coverage under the existing owner and rights rules.

Evidence:
`research/MARKET_EXPERIENCE_F0_SEC_FOUNDATION_CENSUS_2026-09-24.md` and
`research/MARKET_EXPERIENCE_F0_SEC_ANCHOR_RECEIPT_2026-09-24.json`.
