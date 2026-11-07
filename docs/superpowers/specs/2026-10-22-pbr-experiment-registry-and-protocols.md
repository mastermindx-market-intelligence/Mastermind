# PBR — Experiment Registry and Evaluation Protocols (W7/W8 freeze)

**Date:** 2026-10-22 · **Program:** Portfolio Bot Rebuild (issue #1693) · **Class:** records-only design spec
**Serves:** W7 (construction) and W8 (outcomes and experiments) protocol needs — MASTERPLAN §11.2, lines 577–578
**Status:** proposed protocols. No experiment has been registered or run under this document. Nothing here is implemented, promoted, or live.

**Citation keys** (used throughout):
- **[MP §x.y]** — the PBR masterplan, `research/commission_pbr_fable_masterplan/2026-10-22/MASTERPLAN.md` (program carrier PR #1695), sha256 `4c7a0d449f02de080e4d8d310af5db09515af86683ac6a3bca1298f2e034d970` (verified against packet).
- **[V2R:l]** — `docs/PORTFOLIO_V2_FORWARD_EVALUATION_2026-08-11.md` (the August-11 forward-evaluation ruling).
- **[FE:l]** — `portfolio/forward_evaluation.py` (the existing V2 forward evaluator).
- **[V3 §x / V3:l]** — `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md`.

## 1. Authority and non-goals

**What this document is.** The protocol record for how PBR experiments are registered, compared, and judged:
trial registry (§2), E0–E6 protocols (§3), benchmark ladder and metrics (§4), statistical discipline (§5),
preserved review gates (§6), the HK prospective-opening-checkpoint evaluation rule (§7), and the required
attribution chain (§8). It is the protocol layer the masterplan requires before experimentation [MP §9.1,
line 457] and the preregistration the V3 program already mandates [V3 §24.5, V3:1789–1802].

**What this document is not.**
1. **No code, no promotion, no live effect.** It changes no source, grants no authority, and promotes nothing.
   Source merge establishes at most `BUILT_NOT_PROVEN / PRODUCTION_INERT` [V3 §25.1, V3:1808–1822]; a protocol
   document establishes less.
2. **No reset or redefinition of the V2 marker or the August-11 cohort.** The V2 cohort marker
   (`data/portfolio_forward_evaluation/start.json`, sha256 `75d5182d55ffc7e569f50008d9293682cadf56130d42b00eaba23412e2e8585c`,
   evaluation start 2026-08-11) [V2R:143–144; MP Appendix, line 718] is immutable by construction: the evaluator
   creates it once and "later deploys can never reset it" [FE:527–528]; an unreadable boundary is a freeze, never
   permission to reset [FE:544–546; marker identity block at FE:282]. Its statistics are cited, never redefined:
   exclusion policy `exclude_all_rows_present_at_stopped_service_v2_baseline` [FE:552; V2R:57–90]; legacy/pre-v2
   rows "may not be appended to the forward cohort, used to satisfy a minimum sample, or presented as v2
   performance" [V2R:178–180]; V3 shadow "never resets, edits, or appends to the V2 live cohort"
   [V3 §23.5, V3:1721–1723].
3. **Three separate verdicts, never merged.** *Operationally correct*, *economically qualified*, and *investment
   value demonstrated* are independent verdicts with distinct evidence [MP §1, lines 29–37]. This document can
   support the first two as engineering deliverables; **it cannot claim investment value**, and no statement in it
   may be read as one. Each report states separately what changed, its accepted evidence, remaining uncertainty,
   owner, and next bounded action [MP §13, line 682].
4. **No simulator blending.** Different simulator ⇒ different simulator generation; never silently blended into
   V2 [MP §8, line 449; MP §12.1, line 629].
5. **Shadow stays shadow.** Shadow/new modules terminate in isolated storage with no registry membership, no
   pending-target route, and no settlement call [MP §12.1, line 631]; shadow activation requires negative controls
   proving no settlement effect [V3 §25.2, V3:1824–1834].

## 2. Trial registry (`pbr.trial_protocol.v1`) — MASTERPLAN §9.1

Every experiment receives an immutable protocol **before it runs** [MP §9.1, line 457]. One registered record =
one trial protocol version.

### 2.1 Record schema

```yaml
schema: pbr.trial_protocol.v1
trial_id: pbr.trial.<EXP>.<seq>.v<N>        # EXP in {E0..E6}; N increments on amendment
experiment: E0|E1|E2|E3|E4|E5|E6
hypothesis: <one falsifiable statement, with the specific condition that proves it wrong>
owner: <accountable domain owner + role, per MP §11.1 line 560>
registered_at: <immutable timestamp; registration = design lock>
policy_version: <exact policy generation id: prompt, model, allocator, risk-policy identities —
                 every material change creates a new generation, outcomes stratified by
                 generation [V3 §23.4, V3:1713–1719; MP §12.1, line 629]>
simulator_version: <economic simulator generation id [MP §9.2, line 479]>
data_versions:
  instruments: <id>          # point-in-time instrument records [MP §7.2, lines 326-338]
  prices: <id>               # qualified marks, adjustment basis
  corporate_actions: <id>
  benchmarks: <id>           # basis: original V2 history vs prospective TR comparator vs
                             # labeled reconstruction [MP §6.1, line 272]
  snapshots: <id>            # immutable point-in-time decision snapshots [MP §7.4]
  macro_artifacts: <id>      # vendored Macro inputs, pinned revision
universe:
  books: [autonomous|china|hk]              # per-book mandate identities [MP §3.1, lines 150-152]
  eligibility_rule: <point-in-time instrument/venue/liquidity/data rule id [MP §7.4, line 366]>
dates:                                        # chronological walk-forward only [MP §9.1, line 461]
  design_lock: <date>                         # = registered_at date
  train: [<start>, <end>]
  validation: [<start>, <end>]
  test: [<start>, <end>]                      # unseen; unblinded once, per stopping rule
  embargo_sessions: <n>                       # separates overlapping labels / info lag
  purge_rule: <overlap purge rule id>         # purge overlapping holding-period labels
cost_model:
  version: <id>                               # venue- and date-specific fees/taxes/lots [MP §8, lines 434-447]
  cash_yield: <declared native-currency investable convention, never an unexplained
               universal 4% [MP §7.7, line 416]>
  fx: <conversion-leg convention [MP §7.2, lines 339-340]>
  execution: <slippage/participation model id>
primary_metric: <exactly one; exact key + horizon + book scope>
economic_minimum:                             # declared BEFORE unblinding [MP §9.4, line 493]
  value: <number or structural predicate>
  unit: <e.g., pp net active return per horizon; or "zero unexplained residuals">
  declared_at: <timestamp>
  declared_by: <owner + seat ratification>
risk_limits: {drawdown, tail, concentration, turnover, operational_integrity}
comparison_family:
  family_id: <stable id; all arms incl. controls and abandoned variants>
  arms: [<challenger arm ids>]
  controls: [<control arm ids; e.g., current categorical allocator, equal weight>]
sample_floors: {nominal_n, effective_clusters, per_arm_minimums}
stopping_rule: <predeclared extend/stop/abort conditions; incl. what happens when a floor
                is unmet — extend, not redesign [V2R:443-444]>
status: registered|running|unblinded|reported|superseded|abandoned|failed
amends: <prior trial_id or null>              # amendments create a NEW version; old record retained
outcomes_ref: <append-only outcome row reference; written only at/after unblinding>
```

### 2.2 Registration rules

1. **Register before running.** No arm executes on evaluation data before its protocol record exists. This is
   the masterplan's "immutable protocol" requirement [MP §9.1, line 457] and V3's preregistration step
   [V3 §23.1, V3:1679–1686].
2. **Amendments create a new version.** A changed hypothesis, arm, metric, date window, or cost model opens
   `…v<N+1>` linked by `amends`; the prior record and its status are retained. Observations from materially
   different generations are never pooled as one strategy [MP §12.1, line 629; V3 §23.4, V3:1713–1719].
3. **Abandoned and failed trials stay in the family.** The registry records failed trials and abandoned variants
   as well as winners [MP §9.1, line 457]; they remain in `comparison_family` so multiple-comparison control
   sees the true number of trials (§5).
4. **One primary metric per trial**, fixed at registration. The winning metric is not changed after inspecting
   results [MP §6.3, line 297; V3 §24.5, V3:1802].
5. **The registry is a knowledge record, not a control plane.** It never gates execution, sizes a position, or
   promotes anything; deterministic code and existing owners keep those authorities [V2R:9; V3 law 23, V3:506].

### 2.3 Where records live — proposal (seat decision)

**Proposal:** an append-only JSONL file under a research path in this repository —
`research/pbr/trial_registry.jsonl`, one `pbr.trial_protocol.v1` object per line, with git history providing
append-only auditability and ordinary PR review for each append. Amendments append; nothing is rewritten.

**Flag — seat decision.** Exact path, append authority (W8 owner per [MP §11.2, line 578]), review route, and
whether outcome rows live beside protocols or in a sibling file are for the seat to ratify. Constraints any
decision must respect: no duplicate control plane (Charter P7 [V3 §2.2, V3:137; V3 law 28, V3:511]); no path that
could acquire runtime authority; V2's own evidence ledger remains untouched [V2R:99–113].

## 3. E0–E6 experiment protocols — MASTERPLAN §9.2

Common rules binding every experiment below:

- **Common economic model (mandatory).** Incumbent reference policy and challengers run through **identical**
  qualified price, corporate-action, cash-yield, fee, currency, trading-unit, and execution conventions with the
  same contemporaneous information availability; the actual V2 account and frozen cohort remain a separate
  observed series; both policy and simulator are versioned; reference-policy reproduction limits are disclosed;
  changes from corrected economics are attributed separately — **a new simulator never receives credit as
  investment-policy improvement** [MP §9.2, line 479; MP §13, line 678]. The first constructor comparison also
  reuses the V2 decision cutoff, calendar, priceability, cost, and marking conventions [V3 §22.1, V3:1609–1622].
- **Economic minimums are placeholders** (`MIN_Ex`). Each is set by the accountable owner at registration and
  ratified by the seat **before unblinding** [MP §9.4, line 493], in units of the primary metric, net of the
  common cost model, and above the cost/delay stress noise band (§5). A trial with no declared minimum may not
  unblind.
- **Sample floors** state both nominal n and effective independent clusters [MP §9.4, line 491]; where a
  comparison group is used, the existing precedent floor applies: selected-vs-rejected comparisons stay
  `insufficient_sample_non_causal` until both groups have ≥30 names, and are `descriptive_only` even then
  [V2R:416–417].
- **Ordering.** E1, E2, E5 preserve the approved V3 sequence [MP §9.2, line 477; V3 law 24, V3:507; V3 §24].
  Cash/exit work (E3, E4) may begin as retrospective diagnostics but **cannot promote parameters ahead of the
  relevant upstream evidence gates** [MP §9.2, line 477].

### 3.1 E0 — economic truth

- **Hold fixed:** captured decisions and existing fills [MP §9.2, line 469].
- **Compared arms:** original stored records vs. qualified accounting and labeled correction analyses.
- **Primary metric:** bridge closure — quantity, cash, and wealth identities (`ending wealth = opening + flows +
  market P&L + income − costs`; `ending shares = opening + buys − sells + corporate-action adjustments`
  [MP §7.3, lines 346–352]) with zero unexplained residuals beyond explicitly bounded intervals.
- **Secondary metrics:** per-symbol replay deltas (HK's six discrepancies [MP §2.5, lines 115–124]); non-trade
  cash residual explanations [MP §2.4, line 93]; corrections classified separately [MP §4 A02–A03, lines 199–200].
- **Economic minimum (`MIN_E0`):** structural — zero unexplained residuals, or a ratified explicit uncertainty
  boundary for named legacy intervals. Not a return number.
- **Main falsifier:** any unexplained reconciliation, source-time, or currency difference [MP §9.2, line 469].
- **Sample floor:** all captured history per book; no sampling.
- **Data:** entirely **retrospective**. E0 produces accounting truth, never policy evidence.
- **Dependency gates:** gates every economic claim — until a book's bridges reconcile or are explicitly bounded,
  **no certified return/attribution claim for the affected interval** and no manufactured balancing events
  [MP §11.3 G1, line 590; MP §2.5, line 124]; HK realized-P&L attribution stays withheld [MP §2.4, line 91].

### 3.2 E1 — constructor

- **Hold fixed:** selected names, inputs, and execution assumptions [MP §9.2, line 470].
- **Compared arms:** (a) the **current categorical allocator** (control, kept per [MP §7.6, line 399]); (b)
  **equal weight** (control); (c) risk anchor; (d) risk anchor plus bounded PM tilt [MP §9.2, line 470].
  Volatility-scaled and correlation/factor-aware anchors are candidates, not automatic winners [MP §7.6, line 389].
  (V3's fifth arm, a direct expected-return optimizer challenger [V3 §24.1, V3:1739], is a family-definition
  question for the seat — Open question 3.)
- **Primary metric:** predeclared net active return over the decision horizon, challenger vs. each control on the
  same selected set [MP §6.3, line 291; V3 §24.1, V3:1741–1747].
- **Secondary metrics:** weight stability under declared perturbations (return windows, candidate inclusion,
  claim strength, quote perturbation, covariance estimates [MP §7.6, line 401; V3 §18]); hidden concentration;
  turnover and net cost; the weight waterfall `risk anchor → tilt → constraints → feasibility → target`
  [MP §7.6, line 395].
- **Economic minimum (`MIN_E1`):** placeholder — net pp per horizon vs. the better control, above the stress
  noise band.
- **Main falsifier:** complexity adds instability, concentration, turnover, or cost without useful incremental
  value [MP §9.2, line 470]. Constructor instability is a hard acceptance signal [V3 law 17, V3:500].
- **Sample floor:** declared per trial; at minimum, effective date clusters reported [V3 §23.3, V3:1700–1711].
- **Data:** **retrospective** matched replay is valid for deterministic policy comparison, accounting, and
  feasibility [MP §9.1, line 463]; **prospective** shadow evidence decides adaptive claims; retrospective LLM
  exercises are exploratory unless knowledge contamination is convincingly excluded [MP §9.1, line 461].
- **Dependency gates:** after E0; precedes E2 and E5 [MP §9.2, line 477]. Staged entry/exit variants are excluded
  here to avoid confounding selection, sizing, timing, and execution [V3 §22.2, V3:1624–1633].

### 3.3 E2 — research

- **Hold fixed:** the qualified constructor and execution [MP §9.2, line 471].
- **Compared arms:** snapshot-only PM; bounded specialist claims; source-family ablations (e.g., no-Prophet /
  no-Neural-Web contexts per [V3 §24.2, V3:1753–1759]); deterministic candidate-ordering control
  [MP §9.2, line 471].
- **Primary metric:** exactly one of paired stock-selection contribution or forecast-calibration improvement
  (Brier / rank information coefficient per [V3 §23.1, V3:1653–1661]), declared at registration.
- **Secondary metrics:** source-family incremental value; claim reliability and independence ledger coverage
  [V3 §14]; rejected-name opportunity cost; trigger precision [MP §6.3, line 295].
- **Economic minimum (`MIN_E2`):** placeholder — selection/calibration gain sufficient to justify research cost
  [MP §6.3, line 295; MP §8, line 451].
- **Main falsifier:** extra research changes prose and cost but does not improve selection or calibration
  [MP §9.2, line 471].
- **Sample floor:** paired same-date comparisons; comparison-group floors per §3 common rules [V2R:416–417].
- **Data:** decisive evidence is **prospective** — genuinely unseen snapshots and outcomes [MP §9.1, line 463];
  retrospective ablations are diagnostic/exploratory.
- **Dependency gates:** requires the winning E1 constructor held fixed [MP §9.2, line 477; V3 §24.2, V3:1751].

### 3.4 E3 — cash and timing

- **Hold fixed:** comparable opportunity and risk sets [MP §9.2, line 472].
- **Compared arms:** incumbent cash policy; a declared simpler allocation; trigger/confirmation variants
  [MP §9.2, line 472].
- **Primary metric:** net active return vs. the incumbent cash policy on matched opportunity/risk sets
  [MP §6.3, line 291].
- **Secondary metrics:** the four-component cash waterfall — intentional risk cash, opportunity cash, constraint
  cash, operationally stranded cash — each with its declared evaluation [MP §7.7, lines 405–413]; re-entry
  condition and review-date discipline [MP §7.7, line 414]; protection delivered (drawdown/tail avoided).
- **Economic minimum (`MIN_E3`):** placeholder — pp net per horizon.
- **Main falsifier:** cash or entry rules systematically reject useful feasible exposure without compensating
  protection [MP §9.2, line 472].
- **Sample floor:** declared per trial; cash-ruling power requires decision-session clusters, not raw days
  (precedent: ≥40 normal-regime effective decision sessions for a cash-collapse condition [V2R:580–583]).
- **Data:** **retrospective diagnostics first**; prospective confirmation required for any promotion.
- **Dependency gates:** cannot promote parameters ahead of the E1/E2/E5 upstream gates [MP §9.2, line 477].
  A trigger demanding perfectly simultaneous inputs must be tested as the underinvestment hypothesis, not
  weakened by assertion [MP §7.7, line 414].

### 3.5 E4 — exits

- **Hold fixed:** same entry cohorts and contemporaneous evidence [MP §9.2, line 473].
- **Compared arms:** hold/review control; explicit thesis-falsifier exits; trail/trim variants
  [MP §9.2, line 473; MP §7.8, line 428].
- **Primary metric:** net outcome of each exit variant on matched cohorts, net of the common cost model.
- **Secondary metrics:** post-sell 5/10/21/63-session forward grades on matured rows [V2R:437–438]; churn and
  process-reason separation (a fast exit with an approved hard reason stays in raw churn, never deleted to
  improve appearances [V2R:367–369]); four-clock discipline (research horizon, thesis review, execution,
  portfolio risk) [MP §7.8, line 420; V3 §21].
- **Economic minimum (`MIN_E4`):** placeholder — pp net per horizon vs. hold/review control.
- **Main falsifier:** frequent intervention degrades net outcomes or relies on hindsight [MP §9.2, line 473].
  No exit is selected after observing the future path [MP §7.8, line 428].
- **Sample floor:** matched entry cohorts; churn rulings require ≥30 authoritative full-close episodes
  [MP §9.5, line 501; V2R:453].
- **Data:** **retrospective** on matched cohorts (diagnostic); promotion requires prospective evidence per the
  ladder (§6). The prior finding that a sector-peak veto harmed its tested strategy stands unless new
  preregistered evidence overturns it [MP §7.8, line 428; MP §5.1, line 243].
- **Dependency gates:** diagnostic-first; no early parameter promotion [MP §9.2, line 477].

### 3.6 E5 — execution

- **Hold fixed:** names and target weights [MP §9.2, line 474].
- **Compared arms:** next eligible execution; no-trade bands; staged variants [MP §9.2, line 474;
  V3 §24.3, V3:1770–1777].
- **Primary metric:** net-of-cost implementation result (realized slippage/fee/delay outcome) vs. the
  next-eligible-execution baseline.
- **Secondary metrics:** fill/defer/reject rates under session, price-eligibility, lot/tick, suspension, and
  participation rules [MP §8, lines 434–447]; duplicate-effect and recovery integrity [MP §8, line 444].
- **Economic minimum (`MIN_E5`):** placeholder — net bp saved per unit of added delay/risk.
- **Main falsifier:** apparent benefit disappears after costs, delays, or eligibility rules [MP §9.2, line 474].
- **Sample floor:** declared per trial across eligible sessions and names.
- **Data:** **retrospective replay** for feasibility and cost behavior; **prospective** confirmation for any
  adopted execution change.
- **Dependency gates:** after E1 and E2 [MP §9.2, line 477]; staged entry/exit tested only after selection and
  target weights are held fixed [V3 §22.2, V3:1624–1633].

### 3.7 E6 — full system

- **Hold fixed:** simultaneous markets and declared evaluation conventions [MP §9.2, line 475].
- **Compared arms:** frozen V2 incumbent vs. complete V3 shadow, run simultaneously as separate policy
  generations through the common qualified economic simulator [MP §6.2, line 285; MP §9.2, line 479].
- **Primary metric:** predeclared net active return vs. the declared control ladder (§4) over the decision
  horizon, subject to drawdown/tail/concentration/turnover/integrity constraints [MP §6.3, line 291].
- **Secondary metrics:** the full attribution decomposition (§8); factor/cash-explained share; operational
  completion; calibration; the three verdicts reported separately [MP §1, lines 29–37].
- **Economic minimum (`MIN_E6`):** placeholder — the predeclared materiality increment the seat must ratify;
  this document does not set it and cannot anticipate its satisfaction.
- **Main falsifier:** benefit is explained by cash/style, vanishes out of sample, or cannot survive reliable
  operation [MP §9.2, line 475].
- **Sample floor:** the preserved gates in §6 govern all review claims; power/economic-materiality analysis is
  required on top of them [MP §9.5, line 513].
- **Data:** **prospective only** for the decisive comparison — the challenger and frozen incumbent reference run
  on upcoming snapshots through the same qualified simulator with zero live effects [MP §11.2 W10, line 580].
- **Dependency gates:** requires W3–W9 contracts and the shadow-activation gate (installed source identity,
  separate shadow storage, no registry membership, no pending-target route, one real snapshot-to-shadow-target
  journey, negative controls, rollback) [MP §11.2 W10, line 580; V3 §25.2, V3:1824–1834; MP §11.3 G4, line 593].

## 4. Benchmark ladder and metrics — MASTERPLAN §6.2, §6.3

### 4.1 Books and comparators (per book/currency)

| Book | Currency | Primary benchmark | Mandate basis |
|---|---|---|---|
| US `autonomous` | USD | SPY [MP §2.1, line 47; §3.1, line 150] | long-only, unlevered, common-stock paper mandate [MP §6.1, line 268] |
| China `china` | CNY | CSI 300 [MP §2.1, line 48; §3.1, line 151] | same, venue-specific economics [MP §3.1, line 151] |
| HK `hk` | HKD | Hang Seng [MP §2.1, line 49; §3.1, line 152] | same, inventory bridge precedes economic acceptance [MP §3.1, line 152] |

Original V2 benchmark histories are retained; improved total-return comparators are introduced **prospectively**
or as explicitly labeled reconstructed analyses [MP §6.1, line 272]. Benchmarks compare on the same currency,
dates, and income basis; an absent or stale benchmark is never treated as zero or forward-filled
[MP §6.2, line 278; V2R:389–391]. Same-window discipline per the open benchmark comparability owners
(#1432/#1433/#1434) [MP §4 A12, line 209].

### 4.2 The ladder

| Comparator | Question it answers | Misuse control |
|---|---|---|
| Predeclared broad regional total-return benchmark | Did the product beat broad passive exposure? | Same currency, dates, income basis, disclosed tracking convention [MP §6.2, line 278] |
| Investable cash return | Did equity risk beat feasible cash? | Currency/account-appropriate yield, fees, accrual dates [MP §6.2, line 279]; declared native-currency convention, never an unexplained universal 4% [MP §7.7, line 416] |
| Fixed strategic equity/cash mix | Did active allocation beat a simple risk budget? | Weights and rebalance rule frozen before outcomes [MP §6.2, line 280] |
| Lagged exposure-matched benchmark | Was relative performance mostly exposure/cash? | Diagnostic only; not causal alpha [MP §6.2, line 281] |
| Equal-weight selected stocks | Did the constructor add value beyond the selected set? | Same names, prices, constraints, costs [MP §6.2, line 282] |
| Simple deterministic selection control | Did discretionary research improve selection? | Point-in-time universe, fixed ranking/eligibility rule [MP §6.2, line 283] |
| Sector/style/risk-matched analysis | Are gains explained by common exposures? | Honest factor coverage, uncertainty, residual reporting [MP §6.2, line 284] |
| Incumbent frozen V2 policy | Is the full proposed system better than what it replaces? | Simultaneous shadow comparison, separate policy generations [MP §6.2, line 285] |

### 4.3 Metrics

- **Primary (declared per trial):** predeclared net active return over the relevant decision horizon, subject to
  drawdown, tail-risk, concentration, turnover, and operational-integrity constraints; report confidence
  intervals and economic materiality, not just a point estimate [MP §6.3, line 291].
- **Secondary:** total return; drawdown/recovery; volatility; downside/tail; beta; sector/style exposures;
  information ratio where the sample supports it; cash contribution; security selection; sizing/timing effects;
  realized implementation costs; unexplained residual fraction [MP §6.3, line 293].
- **Research process:** forecast calibration, rank usefulness, adverse/favorable excursion on qualified paths,
  trigger precision, rejected-name opportunity cost, thesis-falsifier response, model/source incremental value;
  **product:** accountable completed cycles, useful information per unit of research cost [MP §6.3, line 295].
- **Prohibited:** annualizing a short sample into a persuasive marketing claim; inferring independent evidence
  from dozens of correlated names on one day; changing the winning metric after inspecting results
  [MP §6.3, line 297].

V2 evaluator statistics are cited, never redefined: exact metric keys [V2R:308–319], four-field metric cells
(value/sample_n/status/missing_reason) [V2R:262–278], and durable-source interpretations [V2R:282–299] remain
frozen for the V2 cohort.

## 5. Statistical discipline — MASTERPLAN §9.4

1. **Uncertainty units.** Cluster by decision date, overlapping holding horizon, issuer exposure, and regime;
  cross-market observations can be correlated and are not automatically pooled [MP §9.4, line 491]. Evidence
  from one market never silently increases another market's sample count [V2R:542].
2. **Effective sample.** Report the effective independent sample beside every nominal count
  [MP §9.4, line 491]; record decision-date clusters, overlapping windows, regimes, issuer and factor
  concentration, and effective sample size [V3 §23.3, V3:1700–1711].
3. **Paired differences.** When arms share the same dates and conditions, compare paired differences, not
  independent samples [MP §9.4, line 493].
4. **Declared block bootstrap.** The bootstrap design is declared at registration, before outcomes. Block-length
  rule: moving-block bootstrap with block length ≥ the longer of (a) the arm's overlapping-label horizon in
  sessions and (b) the lag at which the paired-difference autocorrelation decays to noise; fixed seed; ≥10,000
  resamples. This generalizes the existing V2 precedent — "a deterministic 10,000-resample moving-block
  bootstrap (five-session blocks, fixed seed)" [V2R:574–575]. Purge overlapping labels and apply declared
  embargoes before inference [MP §9.1, line 461].
5. **Multiple-comparison control over the registered family.** The family is the registry's full
  `comparison_family` — all arms, controls, versions, and abandoned/failed trials (§2.2 rule 3). A winner is
  not selected by whichever metric looks best after the fact [V3 §24.5, V3:1802].
6. **Deflated Sharpe Ratio — applicability conditions.** DSR-style adjustment [Bailey & López de Prado, cited at
  MP §9.1, line 459] applies only when its inputs are available: (a) the complete inventory of effective
  independent trials (from the registry, including failures); (b) the trial-selection mechanism; (c)
  non-normality inputs (skew/kurtosis); (d) track-record length/variance used to standardize. Where any input is
  unavailable, report without DSR and fall back to declared familywise control — "use multiple-testing-aware
  inference where its assumptions and inputs are available" [MP §9.1, line 459]. A favorable statistic never
  replaces clean data or prospective evidence [MP §9.1, line 459].
7. **Cost/delay stress and robustness.** Every positive result must survive stress on plausible costs and
  execution delays [MP §9.4, line 493; MP §8, line 449] and must not depend on one name, one episode, or one
  favorable market condition [MP §9.4, line 495].
8. **Minimum before unblinding.** The minimum economically useful improvement is decided before unblinding
  results [MP §9.4, line 493] (see `economic_minimum`, §2.1).
9. **No rescue search.** A negative or inconclusive result is a valid program outcome; no additional cycle is
  spent searching for a statistic that rescues a favored feature [MP §9.4, line 495]. Failing features are
  removed or narrowed [MP §12.2, line 647].

## 6. Preserved gates — MASTERPLAN §9.5

These floors are quoted, not restated or redefined. "Extend under the existing rule; do not reset the marker or
quietly redefine its statistics" [MP §9.5, line 501].

### 6.1 V2 first-review floors (currently unmet [MP §9.5, lines 499–501])

> "V2's existing first-review floor requires at least 60 exact matched portfolio/benchmark sessions, 40
> effective PM decisions, 12 material-change decisions, at least 95% applicable accountability/provenance/memo
> coverage, and no unresolved integrity defects. A churn ruling additionally requires 30 authoritative
> full-close episodes." [MP §9.5, line 501]

Same floors in the V2 ruling [V2R:446–456]: ≥60 exact matched portfolio/benchmark sessions; ≥40 effective PM
decisions and 12 material-change decisions; ≥95% accountable material-change, provenance, and required-memo
coverage; no unresolved cohort contamination, benchmark mismatch, execution-correctness, or material-missingness
defect; churn rulings additionally require ≥30 authoritative full-close episodes — a book can meet the NAV floor
while churn stays underpowered. The floors authorize an initial architecture review, not a claim of enduring
alpha [V2R:456]. Current state: 52 raw observations, 27/25/21 effective decisions, 4/5/2 closed positions for
US/China/HK [MP §9.5, line 499].

Behavioral checkpoints en route: 20 sessions diagnose/extend (no redesign or performance promotion); 40 sessions
identify hypotheses; 60 sessions is the first architecture review, only if the power floors are met — otherwise
the freeze extends in 20-session increments, because "time passing without decisions, exits, marks, or complete
evidence does not create power" [V2R:435–444].

### 6.2 V3 ladder (earliest review opportunities, not automatic promotion dates [MP §9.5, line 513])

| Checkpoint | Permitted conclusion |
|---|---|
| First real vertical | Snapshot, claim, target, receipt/isolated shadow, and display operate as specified [MP §9.5, line 507; V3 §25.2] |
| 20 eligible sessions | Operational quality, reproducibility, authority isolation, attribution completeness; **no alpha claim** [MP §9.5, line 508; V3 §25.3, V3:1836–1848] |
| 60 eligible sessions | Behavior, stability, turnover, cash, initial falsification; **no annual-horizon claim** [MP §9.5, line 509; V3 §25.4, V3:1850–1861] |
| 126 eligible sessions | Earliest serious paper-policy review, conditional on ≥20 material decisions, matured 21/63-session episodes, ≥8 independent date clusters, more than one meaningful condition, and complete attribution [MP §9.5, line 510; V3 §25.5, V3:1863–1872] |
| 252 eligible sessions | Earliest review for annual-horizon claims; still conditional on evidence quality and statistical power [MP §9.5, line 511; V3 §25.6, V3:1874–1876] |

Any later cutover additionally requires the twelve V3 promotion criteria, ending with explicit Chairman approval
[V3 §25.7, V3:1878–1893].

### 6.3 Added power/economic-materiality requirement

> "The new plan adds an explicit power/economic-materiality analysis on top of the approved minimums. A
> generation with too few independent decisions remains inconclusive even after a year." [MP §9.5, line 513]

Protocol consequence: every review under §6.1/§6.2 reports, alongside the floor counts, the effective
independent decision count, the analysis's minimum detectable effect at the declared economic minimum, and
whether the observed sample can distinguish the declared minimum from zero. Underpowered ⇒ ruling is
`extend`, not redesign [V2R:585–586 analog; V2R:443–444].

## 7. HK prospective opening checkpoint — evaluation treatment rule

Source rule [MP §11.3, lines 598–600; reiterated in the charter, MP §13, line 678]. This section defines only
**how evaluations must treat** such a checkpoint; **any accounting proposal is owned by the accounting/economic
truth domain owner (ECON, W1)** [MP §11.1, line 560; MP §11.3, line 598] — this document proposes none.

1. **Trigger.** Only if legacy HK history cannot be reconstructed, the accounting owner *may propose* a
   prospective shadow opening checkpoint with an explicit uncertainty boundary, while preserving the original
   account/history and the V2 cohort [MP §11.3, line 598].
2. **Enumerated components.** Cash; quantities; qualified opening marks; pending orders/targets; unresolved
   corporate actions; any unsupported historical cost basis [MP §11.3, line 598].
3. **Corroborated vs. assumed.** Each component is labelled independently corroborated or adopted assumption;
   comparing the account file to itself is not independent verification; cash or quantities that cannot be
   corroborated are labelled **assumed opening inventory** [MP §11.3, line 598].
4. **Pending effects.** The disposition of all pending effects is recorded so nothing can be counted twice
   [MP §11.3, line 598].
5. **P&L basis.** Prospective shadow P&L begins at the declared opening valuation, with all subsequent economic
   events reconciled. **Unsupported legacy cost basis cannot become certified realized P&L.** The checkpoint
   permits bounded future learning; it does not repair the past, reset the actual account's losses, or support
   a lifetime-performance claim [MP §11.3, line 600].
6. **Visibility.** An assumed opening checkpoint **stays visible in every affected evaluation** [MP §11.3,
   line 600]: every E-family outcome row touching HK carries the checkpoint label and its component labels;
   checkpoint-based and reconciled-history series are never pooled silently (generation stratification,
   [V3 §23.4, V3:1713–1719]).
7. **Gate interaction.** Until the checkpoint exists (or the bridge reconciles), HK falls under G1: no certified
   return/attribution claim for the affected interval, and no manufactured balancing events [MP §11.3 G1,
   line 590].

## 8. Attribution chain — MASTERPLAN §9.3

**Required lineage for every experiment observation:**

```text
snapshot → claim → PM view → target → feasible order → receipt → fill → position episode → outcome
```

[MP §9.3, line 483]. Rules:

1. **Attribution follows real execution effects.** Proposed or queued actions remain **unexecuted** until their
   receipts say otherwise — "a queued target is not a fill" [MP §9.3, line 483; V2R:285; V2R:290].
2. **Decomposition.** Performance decomposes into market exposure, cash/risk allocation, sector and style
   exposure, security selection, sizing, entry/exit timing, implementation costs, and unresolved residual, with
   an explicit bridge for measurement corrections [MP §9.3, line 485].
3. **Order-dependence.** Where a decomposition is order-dependent, use more than one attribution lens and
   disclose interaction effects [MP §9.3, line 485].
4. **Missed opportunities.** Operational missed opportunities compare against the original accepted intent at
   prices and feasibility available in its intended window — never against the best trade visible in hindsight
   [MP §9.3, line 487].
5. **Source identity.** Candidate-source attribution preserves source and selection identity at decision time;
   a later narrative label cannot establish provenance [MP §9.3, line 487]. The V2 evaluator currently emits
   source/sleeve return attribution as deliberately missing (`authoritative_fill_to_candidate_source_return_attribution_unavailable`)
   [V2R:419–428]; filling it is an observability upgrade through authoritative lineage only — no retroactive
   backfill may be called contemporaneous evidence [V2R:427–428].
6. **Durable sources.** Lineage binds to the durable rows and their prohibited interpretations (account.json is
   not a fill; latest.json is not a historical weight path; a queue is not execution) [V2R:282–299].

## 9. Open questions for the seat

1. **Registry custody (§2.3).** Ratify path, append authority (W8 owner), review route, and outcome-row
   location; confirm the git-tracked research-path proposal or select another, within Charter P7's
   no-duplicate-control-plane constraint.
2. **Economic minimums.** Set and ratify `MIN_E1`–`MIN_E6` values (and confirm `MIN_E0`'s structural form).
   Until declared, no trial may unblind.
3. **E1 family definition.** Does the E1 comparison family include V3's fifth arm (direct expected-return
   optimizer challenger [V3 §24.1, V3:1739]), which the masterplan's E1 row omits [MP §9.2, line 470]? The
   answer changes the multiple-comparison family and DSR's effective-trial count.
4. **Trial-count custody for DSR.** Confirm the registry is the sole source of the effective number of trials,
   and decide how pre-registry historical experiments (e.g., the July sector-peak-veto test [MP §5.1, line 243])
   enter that count.
5. **Benchmark basis per rung.** For each ladder rung and book, decide which basis applies — original V2
   benchmark history, prospective total-return comparator, or labeled reconstruction [MP §6.1, line 272] —
   coordinated with the open benchmark owners #1432/#1433/#1434 [MP §4 A12, line 209].
6. **E6 prospective clock.** Confirm the binding start event for "unseen" prospective evidence — proposed: the
   V3 shadow-activation gate's first real snapshot-to-shadow-target journey [V3 §25.2, V3:1832; MP §11.2 W10,
   line 580].
7. **E3/E4 promotion boundary.** Define the exact condition under which retrospective cash/exit diagnostics may
   inform a registered prospective arm, given they "cannot promote parameters ahead of the relevant upstream
   evidence gates" [MP §9.2, line 477] — proposed: only after the E1/E2 conclusions they depend on are
   themselves unblinded and reported.
8. **Per-experiment sample floors.** Ratify default floors for E1/E3/E5 (E4 churn and E6 reviews inherit
   preserved floors); decide whether the 30-name selected/rejected precedent [V2R:416–417] generalizes to all
   comparison-group metrics.

*Records-only protocol specification. No experiment registered, no code changed, no promotion claimed, no live
effect. The V2 marker (sha256 `75d5182d…`) and the August-11 cohort are preserved untouched.*
