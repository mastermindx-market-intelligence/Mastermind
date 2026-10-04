# Commission 17 — Evidence register

**Audit date:** 2026-10-04. Repository evidence is pinned to exact commits. Public product pages establish documented capabilities, not Mastermind entitlement, complete point-in-time history, installed runtime, or predictive acceptance.

C0–C9 are repository/owner evidence. W1–W25 are primary-source research and source qualifications. Proposed methods in MASTERPLAN are architectural recommendations unless this register identifies an observed implementation. Code, tests, committed artifacts, PR proposals, and live proof are kept separate.

**Input draft:** deep-research-report (10).md, SHA-256 12deeb2ce141b3bc797931181da5d345d5206cf9f9fc4d3ea64ec116df5e3410. Original conversation citation tokens were not treated as durable evidence.

<a id="c0"></a>

## C0 — Immutable source baseline and protected Skillpack

**Evidence class:** exact source plus branch metadata observed by the hardening run; no installed-runtime proof.

| Repository | Audited commit | Evidence |
|---|---|---|
| Mastermind | `a2646f458f9ff41ddcedd89b338be4a4349e6cd6` | [Immutable commit](https://github.com/mastermindx-market-intelligence/Mastermind/commit/a2646f458f9ff41ddcedd89b338be4a4349e6cd6); the `master` branch read reported protected. |
| Macro | `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3` | [Immutable commit](https://github.com/mastermindx-market-intelligence/macro/commit/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3); the `main` branch read reported `protected=false`. |
| mastermind-terminal | `1c708450187755160e1a5889b69598a2fcb1f0d1` | [Immutable commit](https://github.com/mastermindx-market-intelligence/mastermind-terminal/commit/1c708450187755160e1a5889b69598a2fcb1f0d1); the branch API reported protected. No Terminal implementation was required for this bounded MRI/RIC census. |

Branch protection is a time-specific API observation, not a property proven by a Git commit. All code links below use the audited Macro SHA, unless explicitly identified as a held proposal.

Protected [Skillpack INDEX lines 1–6](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/sol_skills/INDEX.md#L1-L6) states schema `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`; [22–57](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/sol_skills/INDEX.md#L22-L57) binds the atomic source load and canonical owners. [73–78](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/sol_skills/INDEX.md#L73-L78) supplies the capability-state vocabulary. Procedure reading proves no runtime admission or production capability.

### Publication-time default-branch recheck

- Mastermind protected master: **521720b09be2921e996d9396b522b1c4ca62041c**. [Exact comparison](https://github.com/mastermindx-market-intelligence/Mastermind/compare/a2646f458f9ff41ddcedd89b338be4a4349e6cd6...521720b09be2921e996d9396b522b1c4ca62041c) contains one commit and one added file, research/TREND_PERSISTENCE_PREREG_C1.md. No loaded procedure or audited owner file changed.
- Macro main: **59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc**, branch protection still false in the branch API. [Exact comparison](https://github.com/mastermindx-market-intelligence/macro/compare/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3...59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc) contains two commits: THS collection-completeness/CI tests and Trend Persistence organizational records. No audited MRI/RIC/expectation source changed.
- Terminal remained **1c708450187755160e1a5889b69598a2fcb1f0d1**, protected.

These bounded comparisons preserve the reviewed source conclusions without replacing immutable deep-census references with moving branches. They do not assert that future branch movement is irrelevant; a later implementation rechecks its own affected interfaces and custody.

<a id="c1"></a>

## C1 — Market Belief, K3E, and federation/incorporation boundaries

**Evidence class:** current committed owner decisions and reuse matrix; no refreshed Linear workflow-state claim.

- [Market Belief decision, lines 7–24](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/decisions/DEC-MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE.md#L7-L24): composition over owner-native expectation/surprise/positioning/incorporation; MAS-119/Cell C common semantics; Alpha-E/MAS-118 family-specific incorporation; no universal belief database, expectation score, gap score, or fair-value object.
- [K3E decision, lines 7–28](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/decisions/DEC-K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE.md#L7-L28): K3E-0 belongs to existing Alpha-Intelligence Integration, is distinct from canonical K3-E, and creates no new truth, event, residual, identity, publication or lifecycle owner.
- [Owner and reuse matrix, lines 1–54](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/alpha_intelligence/expectation_market_dynamics/OWNER_AND_REUSE_MATRIX.md#L1-L54): use existing domain truth and owner-lane work, not substitute stores.

These decisions identify owners. Their historical references to MAS-118/119 status are not October-4 status verification. A future adapter must reconcile the then-accepted common contract; this commission does not implement either owner.

<a id="c2"></a>

## C2 — MRI official actuals, same-vintage truth, and provenance

**Evidence class:** inspected implementation and tests; existing foundation BUILT_NOT_PROVEN in this audit, full proposed intraday/multi-revision coverage PARTIAL.

- [release_actuals.py:20–78](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_actuals.py#L20-L78): actual admitted event/source map covers CPI, PPI, PCE, NFP, and claims. FOMC is not in this MRI target map.
- [release_actuals.py:281–320](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_actuals.py#L281-L320): separate observed, source-release and verification timestamps; causality guards.
- [release_actuals.py:378–483](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_actuals.py#L378-L483): official-source/hash/target/unit normalization to `release_actual.v1`.
- [release_actuals.py:659–720](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_actuals.py#L659-L720): first receipt preserved, later differences become correction candidates; canonical eligible receipt selection.
- [release_target_truth.py:194–343](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_target_truth.py#L194-L343): same-release-vintage level selection, explicit unavailable receipts and nonofficial published-proxy label. Date-level `as_of` is not intraday availability proof.
- [build_release_forecast.py:2191–2295](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L2191-L2295): official metric first, same-vintage proxy second, defect-tagged legacy operational fallback third.
- [release_provenance.py:1–34](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_provenance.py#L1-L34), [93–170](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_provenance.py#L93-L170): existing source/coverage classification and per-prediction snapshot composition; metadata remains without scoring authority.
- [test_release_actuals.py:1–400](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_actuals.py#L1-L400): existing receipt and integrity fixtures were inspected, not executed.

First-print machinery exists. It does not prove every release family, multi-period revision graph, exact event-time consensus, naturally observed release, or served consumer.

<a id="c3"></a>

## C3 — Mixed expectation reference and market-source fallback

**Evidence class:** directly inspected computation, source-reader and producer behavior.

- [release_market_context.py:1–91](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_market_context.py#L1-L91): context-only authority; internal-model distribution, market benchmark and reaction lookup are distinct enrichments.
- [release_market_context.py:605–684](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_market_context.py#L605-L684): median of Cleveland/Kalshi/Polymarket numeric values, model-minus-reference difference, sigma normalization and ±0.35 band. This is not economist consensus or actual release surprise.
- [release_market_context.py:287–474](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_market_context.py#L287-L474): CPI headline/core/MoM target checks; file-level stale gating and latest matching snapshot; explicit stale-null dictionaries; no caller-supplied historical cutoff.
- [build_release_forecast.py:3692–3750](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L3692-L3750): Kalshi preferred, Polymarket only when Kalshi object is None; numeric parsing and mixed-reference assembly. A stale non-null Kalshi object is not equivalent to absent source.
- [test_release_market_context.py:763–791](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_market_context.py#L763-L791): incumbent mixed-median behavior tested by fixtures; source semantics must migrate explicitly rather than be redefined silently.

The source code documents intent to suppress incompatible sources; the tests do not certify all real quote units, event identity, intraday clocks, or source entitlements.

<a id="c4"></a>

## C4 — Existing MRI producer, publisher paths, and model/schema distinction

**Evidence class:** implementation and DAG wiring, not deployment verification.

- [build_release_forecast.py:1–56](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L1-L56): incumbent writer and paths: `data/release_forecast/latest.json`, `site/macrodata/release_forecast.json`, `forward_ledger.jsonl`, `scoreboard.json`, `official_actuals.jsonl`, and `input_snapshots/`.
- [build_release_forecast.py:4300–4365](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L4300-L4365): actual emitted schema is `release_forecast.v2`, `upcoming[]` structure, all score/size/trade flags false, owner and display writes. The module's v1 header is stale.
- [config/dag.yml:1515–1566](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/config/dag.yml#L1515-L1566): official receipt reconciliation precedes MRI build in declared nightly wiring.
- [release_forecast_v3.py:1–20](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/release_forecast_v3.py#L1-L20): `v3_factor` is a PCA/ridge model challenger. Its filename does **not** prove a `release_forecast.v3` schema migration or a current migration carrier.

No second writer, forecast ledger, generic expectation database or new publisher is warranted by Commission 17. New fields require current carrier reconciliation and versioned compatibility.

<a id="c5"></a>

## C5 — Event-window reader mismatch

**Evidence class:** direct static producer-versus-reader comparison; live effect not observed.

- [event_window.py:481–519](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/event_window.py#L481-L519): reader expects `site/release_forecast/latest.json`, uppercase top-level sections, and preferentially reads `surprise_skew.sigma`.
- [build_release_forecast.py:3676–3687](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L3676-L3687): producer distinguishes standardized position from `sigma_scale_pp`; C4 pins actual publication path and array shape.
- [event_window.py:590–675](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/event_window.py#L590-L675): intended ex-ante event-risk composition, existing options/context inputs and no projection/score alteration.

Classification is PARTIAL. A real producer-format fixture and later natural-time/served proof are required. This audit did not claim the site is currently displaying a bad value or a new repair has landed.

<a id="c6"></a>

## C6 — Checked-in artifact: no clean-forward accuracy claim

**Evidence class:** committed artifact bytes; no installed or served-runtime read.

- [data/release_forecast/latest.json:1–21](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/release_forecast/latest.json#L1-L21): `asof=2026-10-03T20:19:46Z`, experimental legacy target epoch, `coherent_current_projection_n=0`, `clean_forward_cpi_n=0`, accuracy withheld, `street_consensus=unavailable`.
- [same artifact:23–69](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/data/release_forecast/latest.json#L23-L69): a populated historical score row is explicitly evaluation-ineligible with defect notices.
- [producer:4311–4328](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/scripts/build_release_forecast.py#L4311-L4328): authority-preserving methodology declarations and withheld-performance state.

These fields constrain claims about MRI's current evidence. They do not establish company-wide absence of subscriptions or invalidate separately admitted evidence from other programs.

<a id="c7"></a>

## C7 — Legacy news surprise and inspected compatibility tests

**Evidence class:** direct source for the legacy leaf and tests; discovered ancillary consumer paths; no executed tests or browser proof.

- [macro_surprise.py:1–34](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/macro_surprise.py#L1-L34): latest-revised FRED, revised-prior/trend/z-score comparisons, consensus/ALFRED deferred **for this leaf**. This does not establish absence of MRI actual/vintage machinery.
- [test_release_market_context.py:632–908](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_market_context.py#L632-L908): expectation-reference tests and a temporary fixture-tree integration test. The name “live path” does not mean production acceptance.
- [test_release_radar_ui.py:89–115](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_radar_ui.py#L89-L115): Release Radar test targets `templates/dashboard.html.j2`.
- [UI tests:1063–1106](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_radar_ui.py#L1063-L1106), [1261–1294](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_radar_ui.py#L1261-L1294): mixed expectation median preferred, benchmark median fallback excludes market-implied objects, CLE/MKT tags, no affirmative consensus labeling.
- [test_release_forecast_producer.py:1–90](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_release_forecast_producer.py#L1-L90): incumbent producer test suite; full source was inspected for expectation/actual/ledger integration seams, but no test run is claimed.

Code search also located `scripts/build_news.py`, `site/news/macro_releases.json` and `templates/news.html.j2`; these ancillary paths were not fully audited. Dashboard template retrieval returned empty content with a valid blob identity, so its behavior is **test-specified**, not directly source-verified or browser-proven here.

<a id="c8"></a>

## C8 — RIC and Fed-path owners, workstream and October-3 contract

**Evidence class:** inspected implementation and committed organizational records, with their stated proof limits.

- [rate_futures.py:1–16](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/collectors/rate_futures.py#L1-L16): incumbent Yahoo-delivered ZQ/SR3 pricing collector and display-only context purpose.
- [fed_path.py:1–20](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/fed_path.py#L1-L20), [221–253](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/fed_path.py#L221-L253): incumbent policy-target, SEP and market-path composition. Existence does not qualify all source/basis/freshness behavior; relevant held repairs are C9.
- [rates_inflation_command.py:1–39](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/rates_inflation_command.py#L1-L39), [1210–1272](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/engine/rates_inflation_command.py#L1210-L1272): context-only composition, existing nightly ledger rule and MRI artifact consumer.
- [RIC composition decision:6–26](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/decisions/DEC-RIC-CANONICAL-COMPOSITION-BOUNDARIES.md#L6-L26), [55–65](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/decisions/DEC-RIC-CANONICAL-COMPOSITION-BOUNDARIES.md#L55-L65): preserve MRI, calendar, options, transmission, policy, risk and learning owners; MRI retains its own empirical promotion ruler.
- [RIC workstream:1–109](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/workstreams/WS-RATES-INFLATION-COMMAND.md#L1-L109): incumbent program includes MRI completion, named ceo-sol owner, unfinished source/composition/evaluation/production obligations.
- [October-3 granular-regime handoff:1–62](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/handoffs/RATES-INFLATION-COMMAND-2026-10-03-granular-regime-contract.md#L1-L62), [73–112](https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/handoffs/RATES-INFLATION-COMMAND-2026-10-03-granular-regime-contract.md#L73-L112): reviewed descriptive contract, one additive RIC projection, no probabilities/ranking, implementation and owner repairs still owed.

Records describe their own checkpoint state; this investigation did not re-adjudicate held changes or refresh their production proof.

<a id="c9"></a>

## C9 — Open carrier collision census

**Evidence class:** GitHub PR metadata read 2026-10-04 plus proposal descriptions. All entries were open, draft, `merged=false` at inspection. Head SHA pins the inspected proposal identity; titles/descriptions and mergeability are mutable. Proposal claims are not protected law, active custody receipts or newly verified live evidence.

| Lane | PR | Exact observed head | Collision |
|---|---|---|---|
| Policy-pricing source/basis | [#7521](https://github.com/mastermindx-market-intelligence/macro/pull/7521) | `8da98209ad4a34450745780666c48b6999f2bfb2` | Dates and ZQ/EFFR versus SR3/SOFR identity through Fed-path/RIC/stance |
| Policy-pricing measurement | [#7923](https://github.com/mastermindx-market-intelligence/macro/pull/7923) | `15ccca764331af56562d441497047ba58af0b961` | Contract/reference-period/weight identity; matched-contract move versus roll |
| Policy-pricing forward evidence | [#7940](https://github.com/mastermindx-market-intelligence/macro/pull/7940) | `9c2f2d3ebd2c4867fed9eb942855dc2d1d05676a` | Existing keep-FIRST policy repricing ledger; stacked on #7923 branch |
| MRI release-reaction context | [#7965](https://github.com/mastermindx-market-intelligence/macro/pull/7965) | `aa2567921d4e65a19fa49c4be29599e456181757` | Descriptive regime-conditioned reaction lookup repair |
| EPMD/Information→Price source acceptance | [#8312](https://github.com/mastermindx-market-intelligence/macro/pull/8312) | `69d8c407e7033b9aa1e2fb4699398b454d7864c2` | Native SRC-A1/company expectation capture evidence; canonical records unmerged |
| EPMD/EXP-1 consumer | [#8337](https://github.com/mastermindx-market-intelligence/macro/pull/8337) | `13910854fbd652dcdf975301bdc8c6728c2e4767` | Explicit-cutoff company expectation reader; depends on #8312 and current integration |
| Integrated regime architecture | [#7088](https://github.com/mastermindx-market-intelligence/macro/pull/7088) | `a6ccf23bfdee5e0f40f69390d9a83af9c9e25f47` | Existing records-only regime architecture parent under RIC |

This bounded census is not an exhaustive inventory of every branch. Recheck relevant heads, dependencies and owned paths before future edits. Do not interpret SRC-A1/EXP-1 company expectation evidence as macro-release poll coverage, or any v3 model as a v3 artifact-schema migration.

<a id="w1"></a>

## W1 — Current FRED rights and proposed archival uses

**Primary source:** [FRED legal terms](https://fred.stlouisfed.org/legal/). **Accessed:** 2026-10-04.

The retrieved page has no clear overall effective date. General terms contemplate prior written Bank permission and permit specified internal commercial uses subject to other terms. Separate API prohibitions (k) and (l) address software/AI development or training and storage, caching, archiving, and database incorporation; those clauses contain no local express permission exception. Underlying data-owner rights also remain applicable. Proposed archival/model uses require source-and-use qualification against applicable agreements and permissions. Mastermind's agreements were not inspected; this is a procurement qualification issue, not a finding that existing research is unlawful.

<a id="w2"></a>

## W2 — Direct statistical sources, reuse, and changing archive formats

**Primary sources:** [BLS reuse statement](https://www.bls.gov/opub/copyright-information.htm); [BEA reuse statement](https://www.bea.gov/help/faq/145); [CPI archive](https://www.bls.gov/bls/news-release/cpi.htm); [Employment Situation archive](https://www.bls.gov/bls/news-release/empsit.htm); [BEA GDP release and archive notice](https://www.bea.gov/news/2026/gdp-advance-estimate-4th-quarter-and-year-2025). **Accessed:** 2026-10-04.

BLS describes its publications as public domain except previously copyrighted photographs and illustrations; its emblem is separately protected. BEA permits use and reproduction unless otherwise stated. Both request attribution. Their dated release archives provide practical official-actual pilot paths. BEA announced retirement of GDP news-release PDF/Excel tables beginning April 9, 2026, and warns that linked interactive tables update to subsequent data; original release values belong in its Data Archive. The CPI archive explicitly records no October 2025 publication. Qualify exceptions at artifact level, retrieve the intended vintage, and preserve missing-release status. A file downloaded today is an archival reconstruction, not proof that Mastermind received those bytes at the historical release time.

<a id="w3"></a>

## W3 — FRED and ALFRED vintage dates are not intraday receipts

**Primary sources:** [API real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html); [release dates](https://fred.stlouisfed.org/docs/api/fred/release_dates.html); [ALFRED help](https://alfred.stlouisfed.org/help); [download semantics](https://alfred.stlouisfed.org/help/downloaddata). **Accessed:** 2026-10-04.

API real-time bounds use inclusive calendar dates; defaults generally select information available today. Source release dates need not equal FRED/ALFRED availability. ALFRED generally adds new or revised data within one business day, and vintage-date provenance can depend on the original source, provider, or FRED availability. Sources do not always retain earlier estimates, and unchanged releases may be absent from vintage-date lists. ALFRED also warns that transforms of rounded levels can differ from published growth rates. These features support qualified vintage reconstruction, not proof of availability immediately before a release or complete same-day revision chains. Preserve date provenance and precision, verify each series' coverage, and apply W1's separate rights qualification.

<a id="w4"></a>

## W4 — Philadelphia SPF and Livingston coverage has material historical limits

**Primary sources:** [SPF overview](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/survey-of-professional-forecasters); [release-date history](https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-release-dates.txt?hash=CE16E2057464DBD7A139FFE6188B48EC&sc_lang=en); [SPF documentation](https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-documentation.pdf?hash=8408A4F1BF351A3C268B40F6BC7B95AA&sc_lang=en); [ID caveats](https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-caveats.pdf?hash=7D3DACF403F4BB692F8756AD91EDF6C6&sc_lang=en); [Livingston overview](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/livingston-survey). **Accessed:** 2026-10-04.

SPF began in 1968 and provides aggregate, individual, and probability forecasts. True deadlines/publication dates before 1990Q2 are unknown; 1990Q2 forecasts were collected retrospectively. Variables, horizons, and probability bins change: core CPI/PCE densities began in 2007Q1 and unemployment densities in 2009Q2. GDP density growth uses annual averages, while core CPI/PCE density growth uses Q4/Q4. Early IDs can be reused, and later IDs do not guarantee stable person-level continuity. Livingston began in 1946 and supplies semiannual individual/aggregate histories and errata. These histories require variable-era qualification, explicit correction handling, and identity-confidence rules. They do not establish uninterrupted release-minute consensus or universally precise public availability. Preserve original bins and target conventions before comparing forecast distributions or revisions.

<a id="w5"></a>

## W5 — New York Fed survey collection precedes public availability

**Primary sources:** [Survey of Market Expectations](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations); [SME FAQs](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations/faqs-survey-of-market-expectations). **Accessed:** 2026-10-04.

Questions are published when distributed, roughly two weeks before FOMC; results and data normally appear approximately three weeks after the meeting, following the minutes. The Desk can request postmeeting response updates. The Primary Dealer Survey operated from 2002, but public results start in 2011; the Market Participants Survey ran from 2014. Their January 2025 merger into SME expanded the nondealer panel while retaining dealer/nondealer breakdowns. A public premeeting information set can use only an already published vintage, regardless of when respondents answered the current survey. Store response status, publication time, subgroup, and population break. Changes across the merger cannot automatically be attributed to the same participants revising forecasts. Survey beliefs also do not establish participants' actual positions.

<a id="w6"></a>

## W6 — Statistical revisions, early release, and reissued text are different events

**Primary sources:** [BLS CPI detailed-report archive](https://www.bls.gov/cpi/tables/detailed-reports/); [May 2024 early-release notice](https://www.bls.gov/ces/notices/2024/early-data-release-05152024.htm); [June 12, 2024 CPI release](https://www.bls.gov/news.release/archives/cpi_06122024.htm). **Accessed:** 2026-10-04.

BLS's historical CPI detailed-report archive explains January revisions to seasonally adjusted indexes and changes for the preceding five years. Its May 15, 2024 notice documents approximately thirty minutes of early availability for a subset of files. The June 12, 2024 CPI release carries a same-day reissue note correcting a CPI-W paragraph. These examples justify separate handling of statistical revision, component-specific availability anomaly, and publication correction. The reissue note does not establish a revised headline CPI value; the early-release notice does not establish early publication of every component. Scheduled time therefore cannot serve as universal first-publication evidence. Preserve the affected artifact and field scope, revision reason, and uncertainty about unrecoverable earlier versions; do not collapse every change into an economic revision.

<a id="w7"></a>

## W7 — LSEG Reuters Polls is a qualification candidate, not a proven winner

**Primary sources:** [Reuters Polls Consensus catalogue](https://www.lseg.com/en/data-catalogue/economics/economic-macro-forecasts/reuters-polls-consensus); [LSEG historical-poll retrieval discussion](https://community.developers.lseg.com/discussion/133869/reuters-polls-retrieval). **Accessed:** 2026-10-04.

LSEG documents historical polling revisions from 1999, traceability to polling points, and multiple delivery routes. Its catalogue markets real-time content while the Datastream Data Loader listing includes a minimum end-of-day service designation. LSEG's own support discussion shows that an economic-indicator historical call may retrieve actuals even when a separate field displays current poll consensus; detailed content selection requires product support. This does not prove that historical consensus is unavailable. It establishes the need to qualify the exact product, endpoint, fields, delivery frequency, and chosen indicators. No entitlement, complete pre-release revision chain, correction lineage, timestamp precision, contributor metadata, or current price was verified. P0 should request matched samples and explicit storage/model-use terms before a vendor decision.

<a id="w8"></a>

## W8 — Trading Economics documents PIT, with unresolved as-of depth

**Primary sources:** [Point-in-time calendar documentation](https://docs.tradingeconomics.com/economic_calendar/point-in-time/); [calendar schema](https://docs.tradingeconomics.com/economic_calendar/schema/). **Accessed:** 2026-10-04.

Trading Economics describes historical calendar retrieval preserving original event values. Its illustrated endpoint selects an event-date range; that example does not demonstrate a separate historical as-of selector or every pre-release poll revision. The schema distinguishes economist consensus `Forecast` from the provider's own `TEForecast`. `Date` is UTC, `DateSpan` conveys time precision, and `LastUpdate` records the latest insertion/change rather than independently proving each field's first publication. `Previous` and `Revised` distinguish the updated prior-period value from its previously reported value. Include the provider in P0 comparison, but require two pre-event snapshots and a subsequent correction for one event. Do not silently substitute the model forecast, infer contributor distributions, or certify all-vintage coverage from the PIT product name.

<a id="w9"></a>

## W9 — Consensus Economics and Bloomberg are distinct additional options

**Primary sources:** [Consensus Economics historical files](https://www.consensuseconomics.com/excel-economic-data/); [Continuous Consensus API](https://www.consensuseconomics.com/api-continuous-consensus-forecasts/); [Bloomberg Economics](https://professional.bloomberg.com/products/bloomberg-terminal/research/economics/). **Accessed:** 2026-10-04.

Consensus Economics documents preserved survey databases with individual forecasts and mean/high/low/standard-deviation statistics. Historical starts vary by regional product; 1989 is not universal coverage. Its subscription-dependent REST/CSV service adds daily continuous updates between monthly surveys and includes panellist identifiers. Bloomberg documents consensus and individual forecasts, historical surprise analysis, and programmatic economic feeds. Neither public description establishes Mastermind's access, complete macro poll vintages, timestamp semantics, correction retention, or model/redistribution rights. Company-estimates PIT capabilities cannot establish macro-consensus capabilities. Consensus Economics is a plausible P1 fixed-target global revision source; monthly survey history alone is insufficient evidence of release-minute consensus. Bloomberg belongs in the P0 comparison when already entitled or an authorized sample is available. Prices remain quote-required.

<a id="w10"></a>

## W10 — Public nowcasts require output publication and model-vintage controls

**Primary sources:** [Atlanta Fed GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow); [Atlanta Fed terms](https://www.atlantafed.org/terms-of-use); [Cleveland Fed inflation nowcasting](https://www.clevelandfed.org/our-research/indicators-and-data/inflation-nowcasting). **Accessed:** 2026-10-04.

GDPNow is a mechanical model estimate, not an official Federal Reserve forecast; methodology generally changes between tracked quarters. Its 2011Q3–2014Q1 deep archive predates public launch, while tracking archives begin in 2014Q2. Output follows underlying releases with additional latency. Cleveland generally updates inflation nowcasts around 10 a.m. Eastern on business days and distinguishes monthly, annualized-quarterly, and annual inflation conventions. Its website and research implementation differ in a food-price component; current methodology also identifies substitution for missing October 2025 CPI. Prelaunch simulations cannot demonstrate historical public availability, and a same-day post-release nowcast cannot be the prerelease prior. Neither page certifies every historical snapshot. Atlanta's terms include noncommercial reproduction conditions and separate third-party rights, requiring specific commercial-use qualification.

<a id="w11"></a>

## W11 — SEP projections are conditional judgments, not decision probabilities

**Primary sources:** [Federal Reserve SEP guide](https://www.federalreserve.gov/monetarypolicy/guide-to-the-summary-of-economic-projections.htm); [June 17, 2026 SEP](https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm). **Accessed:** 2026-10-04.

Participants project economic outcomes conditional on their own assessments of appropriate policy. GDP and inflation use Q4/Q4 changes, unemployment uses the fourth-quarter average, and the policy-rate projection concerns the year-end target midpoint or level. The June 2026 release provides an explicit 2 p.m. EDT publication header. Marginal medians, central tendencies, ranges, dot counts, and historical forecast-error bands describe different objects; the central tendency removes three highest and three lowest projections. These outputs do not identify a single coherent joint forecast or supply probabilities of future FOMC decisions. Historical error bands also need not equal participants' current subjective uncertainty. Any comparison with market pricing must align the economic target, timing convention, and available publication vintage before computing a gap.

<a id="w12"></a>

## W12

**CME FedWatch API and methodology. Accessed 2026-10-04.**

Primary sources:

- [cmegroup.com · fedwatch-api.html](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html)
- [cmegroup.com · understanding-the-cme-group-fedwatch-tool-methodology.html](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html)

**Supported claim.** CME advertises JSON REST delivery, an EOD FedWatch plan at $25/month, a separate 60-second probability stream, and extended history dating to 2015. Its methodology converts 30-Day Federal Funds futures prices into a binary probability tree using 25 bp increments, assumptions about EFFR responses, and non-meeting anchor months. Thus, the output is a specified methodology's implied policy distribution; its outcome support is not independently recovered from a full options surface.

**Critical limit.** The product page does not demonstrate historical intraday resolution, retention of every original published probability generation, correction receipts, actual Mastermind entitlements, or permitted downstream uses. An exchange-authoritative price still does not identify an unrestricted distribution. The methodology article's older description of EFFR as a weighted average should defer to the New York Fed's current median definition. Advertised price is not an accepted procurement quote.

<a id="w13"></a>

## W13

**ZQ, SR3 and SOFR-option conventions. Accessed 2026-10-04.**

Primary sources:

- [cmegroup.com · 22.pdf](https://www.cmegroup.com/rulebook/CBOT/III/22.pdf)
- [cmegroup.com · 460.pdf](https://www.cmegroup.com/rulebook/CME/IV/400/460.pdf)
- [cmegroup.com · sofr-options-the-new-criteria-to-hedge-interest-rate-risk.html](https://www.cmegroup.com/articles/2026/sofr-options-the-new-criteria-to-hedge-interest-rate-risk.html)
- [newyorkfed.org · effr](https://www.newyorkfed.org/markets/reference-rates/effr)

**Supported claim.** ZQ final settlement uses the arithmetic calendar-day average of EFFR, with preceding-rate carry on non-publication days. SR3 uses compounded SOFR across its specified reference quarter and calendar-day accrual spans. Both rules specify rounding and final-fixing conventions. Current SOFR options use American exercise and deliver into a particular futures contract; standard, serial and mid-curve options have different underlier mappings. EFFR is a volume-weighted median published for the previous business day.

**Critical limit.** The policy announcement, policy-effective date, option expiration, futures final settlement and reference period are distinct. Simple quarterly interpolation does not identify meeting-end policy rates. Raw American premiums do not automatically support European density formulas. Production admission requires current reference data and the applicable historical contract generation; illustrative educational examples are not instrument master records.

<a id="w14"></a>

## W14

**Atlanta Fed Market Probability Tracker. Accessed 2026-10-04.**

Primary sources:

- [atlantafed.org · market-probability-tracker](https://www.atlantafed.org/research-and-data/data/market-probability-tracker)
- [atlantafed.org · market-probability-tracker_estimation-specifics.pdf](https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/market-probability-tracker/market-probability-tracker_estimation-specifics.pdf)
- [atlantafed.org · market-probability-tracker_simplex-regression.pdf](https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/market-probability-tracker/market-probability-tracker_simplex-regression.pdf)

**Supported claim.** MPT estimates distributions from CME options referencing three-month compounded-average SOFR. The page describes daily updates normally using the previous day's data and the four nearest-expiring quarterly contracts. Its linked methods describe constrained basis-mixture estimation, Bayesian priors and underidentification; the implementation note includes a fallback using futures rates without a forward/futures adjustment. The site links historical data and source code.

**Critical limit.** This is a model-based, lagged benchmark, not five-minute release data or an observed next-meeting target-rate distribution. Independent reconstruction must reconcile option-expiry and underlying-reference horizons, exercise assumptions and model generations. Older Eurodollar-based history requires transition treatment. The linked ZIP and XLSX were discovered, but the web reader rejected their formats; no inspection of those files or complete vintage inventory is claimed. CME's permission to Atlanta does not itself grant users equivalent raw-market-data rights.

<a id="w15"></a>

## W15

**Treasury curves and matched inflation compensation. Accessed 2026-10-04.**

Primary sources:

- [home.treasury.gov · treasury-yield-curve-methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)
- [home.treasury.gov · yield-curve-methodology-change-information-sheet](https://home.treasury.gov/policy-issues/financing-the-government/yield-curve-methodology-change-information-sheet)
- [federalreserve.gov · tips-yield-curve-and-inflation-compensation.htm](https://www.federalreserve.gov/data/tips-yield-curve-and-inflation-compensation.htm)

**Supported claim.** Treasury's official yields are par-curve outputs derived from indicative market inputs. It adopted monotone-convex interpolation on December 6, 2021, while preserving earlier official observations computed with its previous method. Federal Reserve fitted nominal and TIPS curves allow maturity-matched inflation-compensation measures. Such compensation can reflect inflation expectations and risk premiums.

**Critical limit.** Par yields are not zero-coupon rates and cannot be inserted directly into exact zero-coupon forward formulas. Nominal/real comparisons require matched maturity, conventions, source timing and model generation. Neither raw compensation nor its forward rate is a pure expected-inflation observation. The daily published curve does not establish intraday repricing. Methodology changes must be distinguished from economic movement, and current downloaded histories must not be presumed to preserve all historical publication receipts or original curve vintages.

<a id="w16"></a>

## W16

**New York Fed ACM term-premium estimates. Accessed 2026-10-04.**

Primary sources:

- [newyorkfed.org · term-premia-tabs](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs?stream=business)
- [newyorkfed.org · sr340.html](https://www.newyorkfed.org/research/staff_reports/sr340.html)
- [libertystreeteconomics.newyorkfed.org · short-dated-term-premia-and-the-level-of-inflation](https://libertystreeteconomics.newyorkfed.org/2022/09/short-dated-term-premia-and-the-level-of-inflation/)

**Supported claim.** The ACM service supplies modeled term premiums, fitted yields and expected average short-rate components for annual maturities from one to ten years, with daily and month-end histories extending to 1961. Term premiums are not directly observable. The methodological paper describes a regression-based term-structure model, and the accompanying research explains the decomposition relative to fitted zero-coupon yields. The service states that these are not official FOMC or Federal Reserve policy estimates.

**Critical limit.** Component identities require the same yield convention and model vintage; an observed-minus-fitted residual may remain. A current par yield cannot be forced to equal components from different fitted series. Today's historical download does not prove the estimates published at earlier cutoffs. Daily model movements neither establish five-minute decompositions nor independently identify the causal source of policy news.

<a id="w17"></a>

## W17

**Cleveland Fed inflation-expectations model. Accessed 2026-10-04.**

Primary sources:

- [clevelandfed.org · inflation-expectations](https://www.clevelandfed.org/our-research/indicators-and-data/inflation-expectations)
- [clevelandfed.org · revisions-to-inflation-expectations.pdf](https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/indicators-and-data/inflation-expectations/revisions-to-inflation-expectations.pdf)

**Supported claim.** Cleveland estimates inflation expectations across 1–30-year horizons, with inflation/real risk-premium and real-rate outputs, using Treasury yields, CPI, inflation swaps and survey inputs. It explicitly excludes TIPS as model inputs. The service says it publishes results before 4 p.m. on CPI-release day and combines inputs from different points in the month. Its current notice discloses substitution of an October 2025 CPI nowcast because that BLS observation was not released. A revision notice documents restored historical values and CPI seasonal-adjustment changes in 2019.

**Critical limit.** This is a monthly statistical model, not a direct decomposition of Mastermind's chosen par breakeven. A monthly workbook label is not month-start or 8:30 a.m. availability. Preserve publication and input generations, imputation flags and dependency links; agreement with its survey or market inputs is not independent corroboration.

<a id="w18"></a>

## W18

**ICE inflation curves versus named inflation benchmarks. Accessed 2026-10-04.**

Primary sources:

- [ice.com · ice-swap-rate](https://www.ice.com/iba/ice-swap-rate?showiframe=true)
- [ice.com · Inflation_Swaps.pdf](https://www.ice.com/publicdocs/Inflation_Swaps.pdf)
- [idd.ice.com · Zero_Coupon_Inflation_Sw.htm](https://idd.ice.com/IRHelp/Content/FM/Zero_Coupon_Inflation_Sw.htm)
- [idd.ice.com · Inflation_Curve.htm](https://idd.ice.com/IRHelp/Content/FM/Inflation_Curve.htm)

**Supported claim.** ICE's current named inflation-swap benchmarks include GBP UK RPI and EUR HICP excluding tobacco. Its 2026 notice makes extension to a USD CPI benchmark conditional on sufficient data. Separately, its derivatives-analytics documentation describes inflation curves and zero-coupon inflation swaps, including index interpolation, lag and seasonality settings. Those documents evidence distinct product families, not one interchangeable rate feed.

**Critical limit.** Do not infer that a live USD CPI benchmark exists from the conditional notice, or infer that no commercial USD curve exists. Qualify the exact product, index, supported tenors, data cut, pricing method, history and entitlement. Zero-coupon and year-on-year swaps have different payoffs. A benchmark may use dealer-to-client inputs or interpolation rather than a directly executable quote; vendor affiliation does not remove those distinctions.

<a id="w19"></a>

## W19

**CFTC positioning and publication timing. Accessed 2026-10-04.**

Primary sources:

- [cftc.gov · index.htm](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [cftc.gov · index.htm](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)
- [cftc.gov · tfmexplanatorynotes.pdf](https://www.cftc.gov/idc/groups/public/%40commitmentsoftraders/documents/file/tfmexplanatorynotes.pdf)

**Supported claim.** COT generally reports Tuesday positions on Friday at 3:30 p.m. Eastern, with holiday-related changes. TFF distinguishes dealer/intermediary, asset-manager/institutional, leveraged-fund and other-reportable categories. Classification reflects reported business purpose rather than known reasons for individual positions. Futures-only and futures-and-options-combined reports have different coverage, and spreading/option-delta conventions affect reconciliation. The FAQ says historical release dates are available only for the displayed 13 months.

**Critical limit.** Tuesday's exposure date is not public knowability. Earlier inferred release calendars need an explicit inference qualification and conservative intraday admission. Category net positions do not reveal complete cash/derivative exposures, trader motivation or an event-specific bet. Do not count overlapping long/short/spreading trader counts as unique participants. Preserve contract/report type, reference date, actual publication evidence and source generation when building historical positioning features.

<a id="w20"></a>

## W20

**CME volume, open interest and settlement timing. Accessed 2026-10-04.**

Primary sources:

- [cmegroup.com · about-settlements.html](https://www.cmegroup.com/trading/about-settlements.html)
- [cmegroup.com · volume-open-interest.html](https://www.cmegroup.com/market-data/volume-open-interest.html)
- [cmegroup.com · daily-bulletin.html](https://www.cmegroup.com/market-data/daily-bulletin.html)

**Supported claim.** CME explains that its settlement display can pair the current trading day's volume with the previous trading day's open interest. Its volume/open-interest reporting distinguishes preliminary and final reports. It also states that settlement values for instruments without volume or open interest can be provided for web users without being based on market activity or published on MDP. Each open futures transaction has both a buyer and a seller; only one side is counted in open interest.

**Critical limit.** A fresh page timestamp does not prove freshness of each field. Admission must preserve trade date, position-reference date, publication time and preliminary/final status separately. Open-interest increases are not signed demand or bullish intent. A modeled/nontraded settlement should not receive the same liquidity confidence as an executable bid/ask observation. Specific product/feed timing requires qualification rather than extrapolation from a webpage convention.

<a id="w21"></a>

## W21

**Public swap-repository transaction evidence. Accessed 2026-10-04.**

Primary sources:

- [cmegroup.com · data.html](https://www.cmegroup.com/market-data/repository/data.html)
- [cmegroup.com · cme-swap-data-repository.html](https://www.cmegroup.com/trading/global-repository-services/cme-swap-data-repository.html)
- [cftc.gov · 2020-21568.html](https://www.cftc.gov/LawRegulation/FederalRegister/finalrules/2020-21568.html)
- [newyorkfed.org · 0513flem.pdf](https://www.newyorkfed.org/medialibrary/media/research/epr/2013/0513flem.pdf)

**Supported claim.** CME provides publicly reported swap transaction/pricing data and distinguishes execution timestamps from dissemination subject to regulatory delays. Its public-use notice distinguishes direct use from commercial benefits delivered to external clients. CFTC's reporting framework includes anonymity, caps and delayed public dissemination. New York Fed research documents U.S. zero-coupon inflation-swap conventions, including NSA CPI-U and lagged index-reference periods.

**Critical limit.** Transaction evidence is not a continuous executable curve or unrestricted redistribution license. Execution time cannot substitute for public availability, capped amounts are not exact full sizes, and lifecycle changes require source-specific handling. Sparse coverage and unmatched conventions can defeat curve reconstruction. Exact current delay/size thresholds and available schemas require implementation diligence; the 2013 market sample is not evidence of present liquidity. No claim of a qualified current USD curve sample is made.

<a id="w22"></a>

## W22

**SF Fed U.S. Monetary Policy Event-Study Database. Accessed 2026-10-04.**

Primary sources:

- [frbsf.org · us-monetary-policy-event-study-database](https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/)
- [frbsf.org · financial-market-effects-of-fomc-communication-evidence-from-a-new-event-study-database](https://www.frbsf.org/research-and-insights/publications/working-papers/2025/12/financial-market-effects-of-fomc-communication-evidence-from-a-new-event-study-database/)

**Supported claim.** The USMPD page was updated September 17, 2026; its companion paper was revised August 27, 2026. It provides high-frequency event-window changes in futures, OIS, Treasury/TIPS yields, equity indexes and exchange rates. Separate statement, press-conference, combined-event and minutes windows include timestamps and metadata. The site supplies monetary-surprise construction code and identifies LSEG Tick History as its main raw-data source. The paper supports evaluating communication windows separately and jointly.

**Critical limit.** Use this as a documented retrospective benchmark before unnecessary raw-tick reconstruction. It does not replace live market pricing or release consensus, establish what Mastermind possessed at historical cutoffs, or extend access rights to underlying proprietary ticks. Published factor code still requires its sample/normalization assumptions. A result favoring combined windows in one study does not prove that window is universally optimal.

<a id="w23"></a>

## W23

**Target/path factors, information effects and risk-premium identification. Accessed 2026-10-04.**

Primary sources:

- [federalreserve.gov · do-actions-speak-louder-than-words-the-response-of-asset-prices-to-monetary-policy-actions-and-statements.htm](https://www.federalreserve.gov/econres/feds/do-actions-speak-louder-than-words-the-response-of-asset-prices-to-monetary-policy-actions-and-statements.htm)
- [ecb.europa.eu · ecb.wp2133.en.pdf](https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2133.en.pdf)
- [frbsf.org · an-alternative-explanation-for-the-fed-information-effect](https://www.frbsf.org/research-and-insights/publications/working-papers/2021/09/an-alternative-explanation-for-the-fed-information-effect/)
- [frbsf.org · futures-prices-as-risk-adjusted-forecasts-of-monetary-policy](https://www.frbsf.org/research-and-insights/publications/working-papers/2006/09/futures-prices-as-risk-adjusted-forecasts-of-monetary-policy/)

**Supported claim.** Gürkaynak–Sack–Swanson motivate separate current-target and future-path factors. Jarociński–Karadi use rate/equity comovement and identification assumptions to separate policy from information shocks. Bauer–Swanson provide a competing explanation based on responses to previously public news. Piazzesi–Swanson document risk premiums in federal funds futures, challenging literal physical-expectation readings.

**Critical limit.** Raw repricing, fitted factors, causal shocks and physical forecasts are different objects. A sign pair is not unique causal identification; a reproducible PCA is still estimated. Preserve windows, training samples, factor rotations, controls and restrictions. Historical risk-premium results are not a calibrated 2026 correction. Evaluate competing mechanisms and out-of-sample stability rather than allowing one cited model to dictate regime or portfolio behavior.

<a id="w24"></a>

## W24 — Forecast disagreement and individual uncertainty are separate concepts

**Primary source:** [Federal Reserve, February 2015 Monetary Policy Report, Part 3, forecast-uncertainty discussion](https://www.federalreserve.gov/monetarypolicy/mpr_20150224_part3.htm). **Accessed:** 2026-10-04.

The Federal Reserve explicitly distinguishes uncertainty surrounding an individual's projection from divergence among participants' most-likely outcomes. Its historical forecast-error ranges illustrate uncertainty using prior prediction errors, with stated qualifications about risk balance and changing economic conditions. This official methodological explanation supports separating cross-sectional point-forecast disagreement, an individual's elicited predictive distribution, and historically estimated error distributions. It does not prove a fixed empirical relationship among them or calibrate a new density for Mastermind. The engineering implication is to retain statistic type and construction: panel IQR must not become a predictive interval by relabeling, and average respondent probabilities must remain distinct from the fraction of respondents selecting a particular mode. Any transformation needs explicit assumptions and separate validation.

<a id="w25"></a>

## W25 — ECB and Bank of England surveys provide qualified global extensions

**Primary sources:** [ECB SPF](https://www.ecb.europa.eu/stats/ecb_surveys/survey_of_professional_forecasters/html/index.en.html); [SPF definitions](https://www.ecb.europa.eu/stats/ecb_surveys/survey_of_professional_forecasters/html/about_the_survey.en.html); [ECB SMA releases](https://www.ecb.europa.eu/stats/ecb_surveys/sma/html/all-releases.en.html); [Bank of England September 2026 MaPS](https://www.bankofengland.co.uk/markets/market-intelligence/survey-results/2026/market-participants-survey-results-september-2026). **Accessed:** 2026-10-04.

ECB SPF began in 1999 and provides quarterly point/density forecasts, anonymous microdata, and fixed/rolling horizons. SMA questionnaires began in 2019, public aggregate results in June 2021, and CSV publication in June 2022 with backfill. Its calendar distinguishes fielding, deadline, and publication. The reviewed Bank of England round was collected September 2–4, 2026 and published September 18, after the September 17 meeting. It separates modal forecast percentiles, mean assigned probabilities, and question-specific counts; GDP/CPI expectations condition on respondents' rate expectations. These sources are P1 extensions subject to actual publication and rights qualification. Backfilled file availability is not historical format availability. Central-bank hosting does not make respondent forecasts the bank's own views, and probability averages are not modal-response frequencies.
