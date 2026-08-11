# Mastermind Portfolio v2 — Forward-Evaluation Ruling

**Ruling date:** 2026-08-11 (America/Vancouver)

**Applies to:** US Brain (`autonomous`), CN Brain (`china`), and HK Brain (`hk`)

**Related audit:** `docs/US_BOARD_AUDIT_AND_PORTFOLIO_V2_2026-08-08.md`

**Authority boundary:** paper-only; deterministic code owns eligibility, sizing, settlement, and state mutation

## Ruling

Portfolio v2 is **unproven**. It is an attributable architecture that can now be evaluated; it is
not evidence of alpha, better selection, or better exits. The pre-v2 US losses, the CN/HK recovery,
replay results, local tests, and a successful deployment are useful design and correctness evidence.
None is forward performance evidence for v2.

The exact merged v2 commit is deployed and live health is proven. The architecture is therefore
frozen through a bounded evidence window. During that window:

- no second US allocator, replacement portfolio architecture, or discretionary intraday PM;
- no behavior-changing prompt, candidate, sizing, eligibility, holding, or exit-policy retune;
- no new model, filesystem, child-agent, sizing, fill, or self-promotion authority;
- no promotion of a lesson, context plane, Neural Web output, Prophet state, or shadow feature into
  direct trade authority;
- no transfer of market-specific US, CN, or HK rules into another market.

Correctness, safety, data-integrity, and evidence-ledger repairs remain mandatory. Those repairs
must be the smallest change that restores the frozen contract and must be recorded as a cohort
event. If a repair changes portfolio behavior, the affected before/after evidence is stratified;
it is never silently pooled.

The governing principle is:

> Stop rebuilding the portfolio manager long enough to learn whether the portfolio manager works.

## What is frozen

The evaluated architecture is the one described in the August 8 audit:

1. `autonomous` is the sole active US stock-selection book. Flagship, Heavyweight, and ETF Brain
   remain archived, historically readable, operationally inert, and absent from active exposure.
2. One accountable PM per market compares a bounded, provenance-bearing opportunity set and emits
   typed `ADD`, `HOLD`, `TRIM`, and `EXIT` intent.
3. Prophet, sector, technical, Oracle, Terminal, options, and Neural Web packets are context. They
   cannot size, fill, or mutate a paper account.
4. Trusted deterministic code enforces venue/instrument eligibility, converts ordinal conviction to
   bounded weights, validates the complete target, checks prices, settles, and writes state.
5. Omission is not a sale. An ordinary trim or full exit requires explicit typed intent and evidence.
6. US, CN, and HK share the evidence, explicit-exit, outcome, lesson, and execution-safety contracts
   while retaining market-specific intake, currency, benchmark, calendar, and microstructure rules.
7. Research children are read-only; the sealed root PM is the only model surface allowed to submit a
   book. The shared Codex-first provider waterfall remains the provider plane.
8. Portfolio learning is observational/request-only. The public Mastermind AI chatbot remains a
   separate product with no paper-account mutation path.

## Cohort boundary: v2 starts at deployment, not at repository history

The sole authority for the forward cohort is the ignored VPS runtime marker:

```text
data/portfolio_forward_evaluation/start.json
```

The marker uses a transactional two-phase release boundary. With the service stopped, the exact
release code creates a `pending_health` marker and captures the legacy baselines. The marker becomes
`active` only after all of the following are true:

1. the exact merge commit is deployed from Git;
2. `/health` proves that exact commit, `paper_only=true`, the intended reasoning policy, and a healthy
   scheduled runtime;
3. archived US books are inert;
4. the pre-v2 autonomous pending target is quarantined;
5. cutover did not mutate the existing autonomous account or fills; and
6. the three active book stores are readable.

`start.json` records the exact deployment SHA and evaluation date. For each book it also records the
preexisting decision, fill, NAV, close-event, and post-sell identities; the append-only row identities
include canonical content hashes where the underlying contract is mutable or lacks a stable ID.
Point-in-time `account.json` and `latest.json` are read at evaluation time but never used as cumulative
event counts. A calendar date by itself is not a sufficient boundary. Historical files can contain
multiple rows on the same date, a deployment can occur between runs, and existing holdings
deliberately survive cutover.

Until an active marker exists, the evaluator reports `not_started`, writes no daily snapshot, and
reports zero post-v2 samples. Pending initialization establishes a measurement basis; it does **not** reset an
account, rewrite a fill, manufacture a NAV point, or treat surviving holdings as new v2 entries.
The stopped-service baseline itself has zero post-v2 decisions, fills, marks, closed positions,
post-sell outcomes, and lesson applications. Only rows after the stored baseline identities and
within the marker's start/as-of window can accrue after activation.

Pending initialization occurs while durable portfolio writers are stopped. Exact-SHA health then
proves the commit, reasoning policy, and scheduled runtime before an atomic finalization activates
the cohort. The deployment read-verifies active status before acceptance and preserves that original
marker across later releases; a redeploy cannot silently restart a disappointing cohort. Before the
first post-marker mark, status is
`awaiting_first_post_mark_snapshot`.

Every daily output is one idempotent row per `(book, asof)` under:

```text
data/portfolio_forward_evaluation/<book>/
```

The machine contracts are:

- `mastermind.portfolio_forward_evaluation.start.v1` for `start.json`;
- `mastermind.portfolio_forward_evaluation.v1` for
  `data/portfolio_forward_evaluation/<book>/<asof>.json` and `<book>/latest.json`; and
- `mastermind.portfolio_forward_evaluation.status.v1` for the compact read surface.

`GET /api/forward-evaluation` is read-only and exposes that status. It cannot initialize the cohort,
run a model, mark a price, submit a target, settle a queue, or repair a missing source.
Book/evaluator lifecycle status includes `not_started`, `awaiting_first_post_mark_snapshot`,
`available`, `stale_after_error`, `archived`, `unsupported_book`, and `unknown_book`; an explicit
before-start, future, or invalid request reports `before_evaluation_start`, `future_asof`, or
`invalid_request` rather than returning a plausible empty snapshot.

Re-running the same inputs for the same book/date must reproduce the same logical snapshot and must
not increase a count. Replacing a corrected snapshot must preserve correction provenance.

### Current sample state

PR #15 was merged and deployed at exact commit
`3c4ef7f8b823baa4bb032c76add1960fa6d5a0c7`. Live `/health` returned HTTP 200 with that exact
commit, `paper_only=true`, the intended reasoning policy, and a healthy scheduler. The canonical
marker is `active`. All three books are awaiting their first post-marker snapshot; these zero counts
are the honest live state and provide no performance evidence:

| Book | Evaluation state | Snapshots | Decisions | Effective decisions | Material changes | Fills | Full closes | Mature post-sell rows | Lesson applications |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| US Brain (`autonomous`) | `awaiting_first_post_mark_snapshot` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| CN Brain (`china`) | `awaiting_first_post_mark_snapshot` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| HK Brain (`hk`) | `awaiting_first_post_mark_snapshot` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The deployment record below was captured from live evidence, not inferred from Git:

| Field | Current value |
|---|---|
| Merged v2 SHA | `3c4ef7f8b823baa4bb032c76add1960fa6d5a0c7` |
| Deployed v2 SHA | `3c4ef7f8b823baa4bb032c76add1960fa6d5a0c7` |
| Release state | `active` |
| Evaluation marker SHA-256 | `75d5182d55ffc7e569f50008d9293682cadf56130d42b00eaba23412e2e8585c` |
| Evaluation start | `2026-08-11` |
| First eligible review session | pending the first post-marker exact benchmark mark; book-specific |
| 20-session checkpoint | each book's session 20 after its first eligible mark |
| 40-session checkpoint | each book's session 40 after its first eligible mark |
| 60-session architecture review | each book's session 60 after its first eligible mark |

The canonical marker and the copy visible inside the service mount namespace have the same hash.
`/api/portfolios` reports only `autonomous`, `china`, and `hk` as active portfolio brains; the
Flagship, Heavyweight, and ETF scheduler entries are archived with no next run. Account and fill
bytes were unchanged across cutover:

| Book | `account.json` SHA-256 before/after | `fills.jsonl` SHA-256 before/after |
|---|---|---|
| `autonomous` | `75a954f706f9259b573d953f2f502e717fde0c17a6a5a0afd01dd9379651bfa3` | `a1d157a3dc4be429dff629c9e03bc33722568644fc158b75a70e97a5be98a36d` |
| `china` | `b44a4974f6cbe93905fe235295f25577a068cf33eee3dff9ab5dee10d004cc98` | `a437823821ec52e261730a5c81ed4df2314de6f4de445a5cf8d409bcfb3e90cc` |
| `hk` | `c54f156133f1b6035fa497e5a3b63ed6d0fa25be4243826d93c16873e00122f6` | `9c06db100d449429e100c16988d43847a056c78fd71aa00731262f510f69cf78` |

The legacy autonomous pending target is absent from the executable path and has one recoverable,
hash-matched quarantine receipt from scheduler startup. Authenticated Heavyweight and ETF manual-run
routes returned HTTP 410 before any model call. `/api/portfolio_learning` reports a clean cold start:
zero lessons, presentations, queued or executed applications, post-sell rows, and cross-market
requests. Its live contract explicitly keeps public Mastermind AI state and authority separate.

### Legacy/pre-v2 evidence is a separate cohort

The August 8 audit recorded the following historical US churn. It remains diagnostic reference only:

| Legacy book | Closed positions | Closed in <=1 day | Closed in <=3 days | v2 denominator? |
|---|---:|---:|---:|---|
| Flagship | 118 | 73 (61.9%) | 93 (78.8%) | No |
| Heavyweight | 45 | 20 (44.4%) | 30 (66.7%) | No |
| old US Brain | 11 | 0 | not enumerated in the audit | No |
| ETF Brain | not enumerated in the audit | not enumerated | not enumerated | No |

Pre-v2 CN/HK returns and trades are also excluded from v2 counts. Historical rows may be used for a
clearly labelled replay, schema migration check, or prior failure-rate comparison. They may not be
appended to the forward cohort, used to satisfy a minimum sample, or presented as v2 performance.

### Clean-base test reproduction

A complete offline run on clean `origin/master` commit
`0340714af3986fd33d0c47f27f93626ab810b988` collected 3,715 tests and reproduced 31 failures with
an offline fuse that prevented the run from making provider or model calls. Unrelated host processes
were outside the run and were not treated as test evidence. The dependency checkout was pinned at Macro revision
`256c757b3c4f0ec759571c29a30a71387d0a18f8` but intentionally sparse to `engine` and `lib`; it did
not contain runtime `site/` or `data/regime/` artifacts.

`origin/master` later advanced to `26b31066f4a850445b1bd25c4ee45d4f59938537` through a
README-only change. Its executable and test trees are identical to the reproduced baseline above.

```bash
PYTHONPATH="/private/tmp:$PWD" \
  python -m pytest -q -p mastermind_offline_fuse -p no:cacheprovider
```

| Classification | Count | Exact base evidence |
|---|---:|---|
| `STALE_TEST` | 11 | obsolete password-auth seams (2); no-query/real-book API assumptions in `test_bear`, `test_tracking`, and `test_web` (3); retired Flagship PM telemetry (1); obsolete 0.20 churn-zone fixture (1); obsolete `_get_price_at` outcome mock (1); obsolete scheduler `auth.enabled` seam (1); pre-lobe-freshness Treasury market-plane fixtures (2) |
| `DATE_ROT` | 7 | four freshness tests hard-code 2026-07-05; one maturity test calls wall-clock `matured()` despite a 2026-07-06 fixture clock; two Treasury fixtures call 2026-07-09 “fresh” under a five-day budget |
| `RUNTIME_STATE_DEPENDENT` | 3 | legacy daily test expects a real book despite absent runtime Macro state (1); two experiment evaluator tests read a tracked real registry whose rows were later changed to `status: matured` (2) |
| `AUTH/ENV_DEPENDENT` | 8 | two legacy Flagship overnight tests, `test_phase1` (1), `test_phase2` (2), `test_research_paper` (2), and `test_smoke` (1) require the absent runtime Macro regime/stock artifacts |
| `PREEXISTING_BASELINE` | 2 | Neural Web empty-candidate lifecycle test exposes false sibling resolution (1); authority-map conformance finds two unmapped observational AI flags (1) |
| `REGRESSION_FROM_V2` | 0 | the final candidate's 21 failures all reproduce as the same exact nodes on the clean base |

The precise first-order evidence behind the non-obvious classifications is:

- `test_pm_conviction_record_full_fields` returns before telemetry because the test neither patches
  `client.available()` nor supplies auth, and it targets the retired Flagship PM path.
- `test_held_name_in_churn_zone_is_retained` says 0.20 is above the exit floor, but the source floor
  has been 0.25 since the AVGO/NVDA repair. A historical collision-safe test fix already derived the
  fixture from the live 0.25-to-0.30 band.
- `test_append_outcomes_matured_appends_rows` patches `_get_price_at`, but production grading moved
  to exact bar-index `_grade_outcome`; the patched seam is no longer called.
- the two real experiment-seed assertions expect `blocked_missing_evidence`, while the committed
  registry rows already say `matured`, so the evaluator correctly returns `ready_for_review` from
  that input.
- the Neural Web failure was a real, preexisting observational-lifecycle defect: an empty candidate
  context ran only the `candidate_context_empty` detector but tombstoned three sibling row-level
  drift codes as resolved. The continuation applies the bounded fix described below.
- the authority-map failure is repaired by the v2 branch's explicit A4 observational/request-only
  entries for `MASTERMIND_AI_LOOP` and `MASTERMIND_AI_REVIEW_LLM`.

The exact Neural Web cause is a loss of detector granularity. `build()` treats any non-empty drift
list as proof that the whole `contract_drift` detector family ran. `_derive_nudges_state()` then adds
that family to `ran_kinds`, and `_update_nudge_registry()` resolves every absent open code whose
`_code_kind()` is `contract_drift`. With an empty `candidate_context`, the one emitted
`candidate_context_empty` row therefore falsely proves that the row-level graph-conflict, FDR, and
bottom-state detectors ran, even though they had zero rows to inspect.

The continuation's collision-safe repair makes the resolution guard preserve sibling codes when
`candidate_context_empty` is the aggregate diagnosis. The current candidate still opens
`candidate_context_empty`; the three row-level siblings remain open. On a later non-empty healthy
context, the ordinary resolution path still tombstones genuinely healed codes. The exact former
failure `test_registry_empty_candidate_context_does_not_resolve_siblings`, plus
`test_registry_resolution_tombstone_and_recent_surface` and
`test_registry_carries_across_absent_build`, pass together after this repair. No portfolio selection,
sizing, execution, or v2 authority path changed.

Thus the continuation fixes both base correctness findings: the Neural Web lifecycle collision and
the missing A4 authority-map entries. The remaining falling-knife failure is a stale test of
intentional preexisting behavior: its 0.20 fixture is below the live 0.25 floor, not evidence that v2
changed the floor.

The final candidate was then run through the same complete offline suite. It reported 21 failures;
each exact failing node was rerun on `0340714af3986fd33d0c47f27f93626ab810b988` and failed there as
well. Ten of the clean-base failures no longer reproduce, and `REGRESSION_FROM_V2` remains zero. One
new research-reader allowlist test initially depended on an absent runtime `site/` artifact; its
fixture was made hermetic with a temporary published-contract root, and it passes in the final
candidate. The dedicated governance and Portfolio v2 release gates also pass.

This classification is not a waiver. Final-head failures must still reproduce on this exact base or
be treated as v2 regressions. The missing-runtime failures do not exercise the v2 submission,
archive, sizing, explicit-exit, queue, settlement, or forward-evaluation contracts; those contracts
have dedicated hermetic gates. A release environment with the declared pinned Macro inputs must run
those gates, and no full-suite failure may be hidden by changing the dependency fingerprint.

## Evidence record and metric definitions

Every metric cell has four fields:

```json
{
  "value": null,
  "sample_n": 0,
  "status": "missing",
  "missing_reason": "machine-readable reason"
}
```

Metric status meanings are exactly `available`, `partial`, `missing`, or `insufficient_sample`.
`not_started` is a book/evaluator lifecycle status, not a fabricated metric row. A value of zero is
valid only when an authoritative, complete source proves zero. Absence, corruption, an immature
horizon, or an unsupported join produces `value: null` with a reason. `sample_n` is the number of
eligible post-marker observations in that metric's own denominator; it is never a global count
copied into unrelated metrics.

### Durable sources

| Source | Authoritative use | Prohibited interpretation |
|---|---|---|
| `data/portfolios/<book>/account.json` | current cash and positions | not a historical path and not proof of a fill |
| `data/portfolios/<book>/fills.jsonl` | executed paper traded value and full-exit FIFO realization when authoritative | a queued target is not a fill |
| `data/portfolios/<book>/nav_history.jsonl` | marked NAV, cash/invested values, benchmark marks when present | no relative-return zero when benchmark is absent |
| `data/portfolios/<book>/positions_ledger.json` | durable open/close lifecycle used for holding duration and close counts | a trim is not a close; an absent boundary is not a zero-session hold |
| `data/portfolios/<book>/decisions.jsonl` | structured PM decision, target status, candidate/finalist/rejection/action evidence | rejected, frozen, or malformed submissions are not effective book changes |
| `data/portfolios/<book>/latest.json` | current published position weights for concentration when complete and as-of eligible | not a historical weight path and not fill evidence |
| hash-bound pending decision plus settlement receipt/outbox | queued-versus-executed transition and exact target lineage | a queue is not execution; scratch submissions are not durable authority |
| `data/portfolio_learning/<book>/post_sell.json` | full-exit/trim classification and 5/10/21/63-session forward grades | immature or unpriceable rows are not flat returns |
| `data/portfolio_learning/<book>/lessons.json` | measured local lesson evidence and requested scope/status | existence of a lesson is not behavior change |
| `data/portfolio_learning/<book>/presentations.jsonl` and `applications.jsonl` | exact IDs presented, cited, accepted, settled, and linked to outcomes | presentation/citation is not execution |
| `data/portfolio_learning/operator_lesson_state.json` | explicit operator approval metadata | generated evidence cannot approve itself |
| Portfolio registry and deployment/health attestation | active/archive identity, benchmark, currency, exact release | repository state alone is not live state |

The forward evaluator reads only the account, decisions, fills, NAV, positions, latest, and
post-sell entries in this table. The lesson trace owns the lesson, presentation, application, and
operator-state rows. Neither path makes a network, model, sizing, target, fill, or account-mutation
call.

### Exact compact metric keys

The durable snapshot uses these exact keys. The detailed definitions in the following sections are
normative; this table prevents dashboard/report code from inventing aliases or silently changing a
denominator.

| Metric group | Exact keys |
|---|---|
| Point exposure/concentration | `gross_exposure_pct`, `cash_pct`, `net_exposure_pct`, `top_1_weight_pct`, `top_3_weight_pct`, `position_hhi` |
| Accrued event samples | `marked_session_count`, `fill_count`, `closed_position_count`, `post_sell_sale_count` |
| Trading/holding | `traded_value_turnover_pct`, `closed_hold_days_average`, `closed_hold_days_median`, `closed_within_1_day_rate_pct`, `closed_within_3_days_rate_pct`, `closed_hold_sessions_average`, `closed_hold_sessions_median`, `closed_within_1_session_rate_pct`, `closed_within_3_sessions_rate_pct` |
| Performance | `inception_benchmark_relative_return_pct`, `benchmark_session_hit_rate_pct`, `full_exit_hit_rate_pct`, `max_drawdown_pct` |
| Decisions/actions | `decision_count`, `effective_decision_count`, `material_change_decision_count`, `action_counts` |
| Selection | `candidate_count`, `finalist_count`, `selected_count`, `rejected_count`, `reject_reason_coverage_pct`, `provenance_coverage_pct` |
| Prophet context | `prophet_selected_context_presence_pct`, `prophet_rejected_context_presence_pct` |
| Exit accountability | `requested_exit_count`, `effective_exit_count`, `blocked_exit_count`, `omission_carried_exit_count`, `full_exit_explicit_memo_coverage_pct`, `partial_trim_explicit_memo_coverage_pct` |
| Entry accountability | `entry_evidence_coverage_pct`, `entry_why_now_coverage_pct`, `entry_falsifier_coverage_pct`, `entry_horizon_coverage_pct`, `entry_exit_plan_coverage_pct` |
| Explicitly unavailable path/attribution metrics | `early_max_adverse_excursion_pct`, `early_max_favorable_excursion_pct`, `return_contribution_by_sleeve_pct`, `return_contribution_by_candidate_source_pct` |

The cumulative rows in `decisions.jsonl`, `fills.jsonl`, `nav_history.jsonl`,
`positions_ledger.json`, and `post_sell.json` are baselined per active book. `account.json` and the
published `latest.json` supply point state only. Point metrics describe the current as-of snapshot;
event, decision, and outcome counts include only rows after the stored baseline identity and inside
the inclusive start-to-as-of window.

### Portfolio and exposure

All weights use the same marked NAV for the snapshot. A positive held position's weight is marked
market value divided by NAV.

| Metric | Exact definition | `sample_n` |
|---|---|---:|
| Gross exposure | absolute invested value / NAV from the latest eligible durable NAV mark | `1` current eligible mark |
| Cash weight | cash / NAV from the same mark | `1` current eligible mark |
| Net exposure | signed invested value / NAV; currently equals gross in the long-only books | `1` current eligible mark |
| Top-1 concentration | largest non-negative current position weight | number of authoritative current position weights |
| Top-3 concentration | sum of three largest non-negative current position weights | number of authoritative current position weights |
| HHI | sum of squared non-negative current position weights; cash excluded | number of authoritative current position weights |
| Two-way traded-value turnover | cumulative sum of absolute post-marker executed fill value / mean eligible post-marker marked NAV; it is not halved | fills with authoritative notional |

If a position lacks an authoritative mark, concentration is `partial` or `missing`; the absent line
is not assigned zero weight. Low gross is a review-time diagnostic derived from daily exposure
snapshots, not a separate v1 metric key and not a quota. A valid candidate-scarcity or risk rationale
can justify it, and the review keeps that rationale beside the observation.

### Holding, churn, and realized outcomes

A holding episode is a new, non-baseline close event in the durable position ledger with both its
recorded open and close boundaries. A trim does not close the episode. Calendar-day metrics preserve
the legacy <=1-day/<=3-day diagnostic. The session companions count the book's canonical persisted
benchmark-mark sessions so weekends and venue holidays are not mistaken for trading opportunity.
Baseline NAV rows may define that session calendar but never become v2 outcomes or count samples.

| Metric | Exact definition | Denominator |
|---|---|---|
| Average/median closed hold days | mean/median calendar days across full-close episodes | post-v2 full closes with durable open and close dates |
| <=1-day / <=3-day churn | full-close episodes held at most one / three calendar days | same date-complete full-close episodes |
| Average/median closed hold sessions | mean/median benchmark sessions across full-close episodes | post-v2 full closes with both boundary sessions |
| <=1-session churn | full-close episodes held at most one benchmark session | same authoritative full-close episodes |
| <=3-session churn | full-close episodes held at most three benchmark sessions | same authoritative full-close episodes |
| Full-exit hit rate | profitable post-marker full-close FIFO episodes / all authoritative full-close FIFO episodes | full closes with matched fill cost basis and proceeds |
| Requested/effective/blocked exits | typed exit intents; exits admitted into accepted target; exits rejected by a trusted rule | eligible structured decisions |
| Omission-carried exits | held names omitted by the PM and deterministically carried rather than sold | eligible structured decisions with prior holdings |
| Full-exit/trim memo coverage | post-sell rows whose linked decision has non-empty reason, why-now, and evidence | post-marker full exits / partial trims, reported separately |

A fast exit with a documented approved hard reason remains in the raw churn metric; reviewers can
audit that reason through the linked decision and post-sell memo. It is never deleted to make churn
look better or silently placed in a non-canonical stratum.

### Performance

The marker excludes every preexisting NAV row; it does not manufacture a deployment-time NAV.
Return evaluation begins at the first eligible post-marker matched book/benchmark mark and ends at
the last. Surviving pre-v2 holdings contribute to those forward NAV changes, but their historical
gain/loss before the first post-marker mark does not.

| Metric | Exact definition | Required source quality |
|---|---|---|
| Inception benchmark-relative return | first-to-last post-marker book return minus first-to-last benchmark return | at least two exact post-marker matched book/benchmark marks |
| Benchmark-session hit rate | adjacent matched intervals in which book return exceeds benchmark return / all adjacent matched intervals | at least two matched marks; `sample_n` is interval count |
| Full-exit hit rate | profitable post-marker full-close FIFO episodes / authoritative FIFO full-close episodes | authoritative matched fill basis and proceeds |
| maximum drawdown | minimum of NAV / prior running peak - 1 inside the v2 window | at least two eligible marked NAV rows |

The first-to-last book and benchmark returns are transparent intermediate values, not additional v1
metric keys. They must not be confused with the account's all-history inception return.

CN uses the configured CSI 300 contract and CNY session/currency semantics; HK uses Hang Seng and
HKD; US uses SPY and USD. If a benchmark is stale, absent, mismatched, or has no exact paired session,
relative performance is missing for that observation. It is never forward-filled across an unrelated
session merely to complete a chart.

### Decision, selection, and evidence accountability

Counts are reported independently so a nightly model call cannot masquerade as an effective trade:

- **decision:** one valid structured post-boundary PM row;
- **effective decision:** an accepted decision durably published as `queued` or `executed`;
- **material change:** an effective decision contains at least one typed `ADD`, `TRIM`, or `EXIT`;
  accepted older rows without typed actions remain material only when they record execution;
- **action counts:** typed `ADD`, `HOLD`, `TRIM`, and `EXIT` rows in eligible decisions;
- **candidate/finalist/selected/rejected:** decision-scoped counts reported by each valid structured
  decision, with malformed rows surfaced rather than guessed;
- **reject-reason coverage:** rejected alternatives with a non-empty typed reason / all rejections;
- **provenance coverage:** rows with at least one bounded source identifier / applicable rows;
- **entry memo coverage:** effective additions with evidence, why-now, falsifier, expected horizon,
  and exit plan, each reported as its own exact coverage key.

Exact target-digest accountability is audited from the decision/application/settlement lineage at
review time. It is a release-quality floor, not an extra v1 snapshot key silently invented by a
dashboard.

Prophet presence is reported separately for selected and rejected structured names by inspecting
their durable provenance/evidence fields. It measures whether Prophet context was recorded, not its
strength and not whether Prophet caused selection or performance. The comparison remains
`insufficient_sample_non_causal` until both selected and rejected groups contain at least 30 names;
even then it is `descriptive_only`. No causal or promotion claim is allowed from this surface.

### Deliberately missing metrics

Early adverse excursion and early favorable excursion are emitted as `value: null`, `sample_n: 0`,
with reason `authoritative_point_in_time_per_ticker_price_path_unavailable`. The two return-
contribution metrics are also emitted missing: sleeve contribution uses reason
`authoritative_fill_to_sleeve_return_attribution_unavailable`, and candidate-source contribution
uses `authoritative_fill_to_candidate_source_return_attribution_unavailable`. A latest quote, a
reconstructed chart, or a decision-time context label is not enough. Adding support later is an
observability upgrade; it does not permit a retroactive backfill to be called contemporaneous
evidence.

## Review schedule and evidence power

All horizons use each book's eligible post-baseline benchmark sessions beginning with its first
durable forward mark. Closed-market days do not advance a horizon.

| Horizon | Purpose | Permitted ruling |
|---|---|---|
| Every run / first 5 sessions | cutover, idempotence, archive, authority, queue, fill, data-health, and memo audit | correctness/safety repair only |
| 5/10/21/63 sessions after each full exit | post-sell outcome and process review | populate mature rows; no architecture inference from one exit |
| 20 sessions | first behavioral checkpoint: coverage, gross, turnover, churn, missingness | diagnose and extend; no major redesign or performance promotion |
| 40 sessions | second behavioral checkpoint and pre-power audit | identify hypotheses; no major redesign unless a correctness/safety defect exists |
| 60 sessions | first architecture review, only if the power and quality floors below are met | retain, extend, or reopen the affected architecture |

If the 60-session power floor is not met, the freeze extends in 20-session increments. Time passing
without decisions, exits, marks, or complete evidence does not create power.

The first performance review requires, for the affected book:

1. at least 60 exact matched portfolio/benchmark sessions;
2. at least 40 effective PM decisions and 12 material-change decisions;
3. at least 95% accountable material-change, provenance, and required-memo coverage;
4. no unresolved cohort contamination, benchmark mismatch, execution correctness, or material
   missingness defect; and
5. for a churn ruling, at least 30 authoritative full-close episodes. A portfolio can meet the NAV
   floor while churn remains underpowered; that metric then stays undecided.

These floors authorize an initial architecture review, not a claim of enduring alpha.

## What counts as evidence

Evidence must be post-marker, durable, point-in-time, reproducible from authoritative local rows,
idempotent, and attributable to the exact decision/target/fill/outcome chain. It must preserve
missingness and use the correct market's benchmark sessions and currency.

The following do **not** justify a redesign or a success claim:

- one profitable or losing trade, three trades, one week, or one market headline;
- a higher or lower cash balance without the candidate-scarcity and risk rationale;
- raw legacy versus v2 returns with different dates, benchmarks, currencies, or exposures;
- a queued target, proposed lesson, context request, model memo, or shadow output without later
  accepted decision and settlement evidence;
- a Prophet-selected winner or Prophet-rejected loser without a declared comparison cohort;
- a stale/missing benchmark treated as zero;
- a short exit by itself; process reason and forward outcome must be graded separately;
- a dashboard count, generated prose, hidden chain-of-thought, or public chatbot response;
- an improvement draft or cross-market recurrence that has not changed a later accepted decision.

## Lesson-to-later-decision lifecycle

A lesson is successful only if it can be traced to a later, accepted decision and observed outcome.
The durable lifecycle is:

```text
measured observation
-> stable lesson ID and evidence basis
-> exact market scope and request-only status
-> presented to an eligible later PM
-> cited from the presented IDs
-> cited decision accepted as queued/executed
-> exact adds/holds/trims/exits/weight deltas or no_change recorded
-> hash-bound target actually settled (or remains explicitly unexecuted)
-> later outcome linked back to lesson application and decision
```

Rules:

1. Every lesson has a transparent stable ID of the form
   `lesson.v1.<SCOPE>.<mechanism_code>`, evidence rows, falsifiable wording, scope, and status. The
   initial `status` and `approval_status` are `requested`, with authority
   `research_request_only`; generation never equals approval.
2. Scope is exactly one of `US_ONLY`, `CN_ONLY`, `HK_ONLY`, or `CROSS_MARKET_CANDIDATE`.
3. A book sees only lesson IDs accessible to that market. It may cite them only in
   `decision_memo.lessons_applied`. A cited malformed, unknown, unpresented, or foreign-market ID
   fails closed and cannot create an application.
4. A rejected, packet-blocked, quote-frozen, or no-submission turn creates no application row.
5. Only an accepted `queued` or `executed` decision creates one idempotent application for the
   stable lesson/decision pair. A queued application has `executed=false`.
6. Exact target-digest settlement transitions that same application to executed; it does not create
   a second application. Failed/superseded queues remain auditable and unexecuted.
7. The application records the exact material difference: adds, holds, trims, exits, target-weight
   deltas, or explicit `no_change`. Citation without a change remains measurable but is not claimed
   as behavior improvement.
8. Later post-sell and forward rows link stable decision and application IDs. Process and outcome are
   judged separately.

Presentation rows live at `data/portfolio_learning/<book>/presentations.jsonl` under schema
`portfolio.lesson_presentation.v1`; application rows live at
`data/portfolio_learning/<book>/applications.jsonl` and count only in cohort
`portfolio_v2_lesson_trace`. The trace uses content-derived `presentation.v1.*`, `decision.v1.*`, and
`application.v1.*` IDs. The trusted pointer binds book, as-of date, exact persisted presentation,
cited lesson IDs, and a canonical submission SHA-256. The accepted application additionally binds
the canonical effective target SHA-256. A queued application can transition to `executed=true` only
through a settlement receipt whose target SHA-256 exactly matches the bound decision, including
crash recovery from that sealed receipt.

No lesson may edit code, doctrine, prompts, configuration, sizing, eligibility, execution, deployment,
or its own status. Explicit operator approval can change review state; it cannot bypass the ordinary
versioned experiment, repository review, CI, merge, exact-SHA deployment, and evaluation process.
An older measured lesson may be normalized and presented after cutover as a clearly historical,
request-only hypothesis. Its pre-v2 evidence does not enter a v2 metric denominator. Only its later
post-marker presentation, accepted application, settlement, and outcome can count in the v2 trace.

### Cross-market fence

US earnings/options behavior, China limit ecology, HK funding/peg dynamics, venue calendars,
benchmark quirks, and local market-hours behavior remain local. Independent recurrence in at least
two books may create a `CROSS_MARKET_CANDIDATE`; it does not make the lesson universal or approved.

A repeated mechanism may be presented outside its origin as a **requested** cross-market hypothesis;
presentation does not approve it or change authority. Approval requires explicit operator state with
an approver and timestamp, plus review of mechanism portability and the receiving book's equivalent
data contract. Any receiving-market application is evaluated as a separate market-scoped experiment.
Evidence from one market never silently increases another market's sample count.

## Conditions that may reopen architecture

### Immediate correctness or safety conditions

Any of the following interrupts the freeze immediately, but authorizes only the smallest safe repair:

- a live-broker path or any non-paper execution;
- a model, child, lesson, context plane, advisor, or public chatbot directly sizing, filling, or
  mutating a paper account;
- any model call, scheduler work, retry, settlement, mark, de-risk, overnight work, manual mutation,
  or state drift for Flagship, Heavyweight, or ETF Brain;
- an omission causing a sale, an ordinary full exit without an explicit memo, or an ineligible ETF /
  cross-venue instrument entering an active stock book;
- execution of the pre-v2 pending target, synthetic liquidation at cutover, or mutation of surviving
  holdings merely to prove deployment;
- execution of a malformed, stale, cross-book, digest-mismatched, partially priceable, or superseded
  target; duplicate fills; unrecoverable WAL/receipt state; or publication of rationale from a scratch
  decision instead of the hash-bound accepted decision;
- cohort contamination, a fabricated zero, non-idempotent counts, silent benchmark/session mismatch,
  or loss/corruption of decision/fill/NAV/outcome evidence;
- a scheduler/provider health attestation that reports healthy while the required runtime is dead or
  running a different release/policy.

### Adequately powered performance conditions

Performance may reopen only the **affected market's** architecture at a scheduled 60-session-or-later
review, after the applicable power/quality floors are met. At least one predeclared condition must hold:

1. **Persistent benchmark failure:** v2-cohort return trails the local benchmark by at least 5
   percentage points, maximum drawdown is at least 5 points worse than the benchmark, and a
   deterministic 10,000-resample moving-block bootstrap (five-session blocks, fixed seed) places the
   upper bound of the 95% confidence interval for mean daily active return below zero.
2. **Legacy churn has structurally returned:** among at least 30 authoritative full closes, the lower
   bound of a 95% Wilson interval for unexplained <=3-session closes exceeds the 10% behavioral gate.
   Approved hard-falsifier/risk exits remain reported separately and cannot be relabelled after seeing
   the outcome.
3. **Unaccountable cash collapse plus performance failure:** among at least 40 normal-regime effective
   decision sessions, the lower bound of a 95% Wilson interval shows more than half below 65% gross,
   the required candidate-scarcity/risk explanation is absent or contradicted by recorded priceable
   finalists, and v2 trails its local benchmark by at least 5 percentage points over the same window.

If a condition is underpowered, mixed, or driven by a known data/correctness defect, the ruling is
`extend`, not `redesign`. A market-local failure does not reopen the common three-brain substrate.
Reopening common architecture requires either a common correctness defect or the same portable,
adequately powered failure independently observed in at least two active books.

Prophet stratification, selected-versus-rejected comparisons, and lesson applications may justify a
bounded shadow hypothesis once their own cohorts are adequately mature. They do not independently
grant Prophet order authority, lesson self-promotion, or another portfolio architecture.

## Required review record

Each 20/40/60-session review appends, without rewriting prior rulings:

- exact release SHA and evaluation marker hash;
- book, benchmark, currency, start/end sessions, and cohort counts;
- metric values with `sample_n`, status, and missing reason;
- data-quality and authority incidents;
- any correctness repair and resulting cohort stratum;
- hypotheses considered, including a documented `retain` case;
- ruling: `retain`, `extend`, or `reopen`, the exact condition invoked, and operator identity;
- next review date/session and any shadow-only experiment.

Silence is not approval. If no adequately powered failure condition is met, the frozen architecture
remains in force.
