# W-LIQ — Global Liquidity Transmission & Repricing Intelligence

**Date:** 2026-08-22  
**Owner:** Sol architecture / multi-session implementation  
**Status:** ARCHITECTURE FROZEN FOR BUILD; zero new trading authority  
**Branch:** `sol/liquidity-transmission-masterplan`  
**Scope:** VegaMacro-inspired global liquidity impulse + the BTC→China/HK delayed-repricing case study + the strongest transferable Vega product primitives.

---

## 0. Executive decision

Do **not** add a standalone “GLI feature,” a BTC→BABA rule, or another isolated dashboard.

Build a first-class **Global Liquidity Transmission (GLT) lobe** whose job is to answer five different questions that Mastermind currently treats separately:

1. **STATE — How much global liquidity exists, and is its impulse accelerating or decelerating?**
2. **QUALITY — What kind of liquidity is it? Durable monetary easing, mechanical Treasury plumbing, credit expansion, dollar funding relief, or stress liquidity?**
3. **TRANSMISSION — Which asset/theme/region historically reprices first, second, and later after this type of shock?**
4. **GAP — Which expected beneficiaries have already repriced and which are still anomalously behind their learned response curve?**
5. **LEARNING — Did the predicted transmission actually occur, under what conditions, and should this relation gain or lose trust next time?**

The lobe is initially a **deterministic, read-only perception organ**. It publishes structured artifacts to Market View and Neural Web; it does not size, buy, sell, or override existing gates. It earns authority by forward grading, the same way existing Mastermind perception planes are required to earn authority.

The BTC→BABA observation becomes a **canonical research fixture**, not a hard-coded trading rule. It seeds a more general “liquidity diffusion / repricing clock” hypothesis:

> a common global liquidity shock can hit assets through different transfer functions; high-beta, always-open, low-fundamental-gating assets can reprice first, while regionally gated assets may lag until local transmission gates turn supportive. The alpha opportunity is the **remaining expected repricing**, conditional on those gates actually being open.

This architecture deliberately keeps the best parts of VegaMacro while improving the weak parts:

- keep **impulse > level** as a hypothesis to test;
- keep **macro × theme mapping** as a compression layer;
- keep **explicit thesis / catalyst / kill-condition / timestamp / scorecard** product discipline;
- keep **event-triggered research** and **portfolio-news mapping**;
- improve global liquidity beyond a single composite by separating **state, source/quality, credit, dollar funding, breadth, and transmission**;
- improve “second-order alpha” by using the existing Neural Web / graph / dislocation stack rather than only a hand-curated thematic list;
- improve learning by making every shock and every predicted response an immutable, forward-graded observation.

---

## 1. Why this belongs in the existing architecture

### 1.1 Existing Mastermind pieces this program must extend, not duplicate

Mastermind already has the structural ingredients:

- `brain/liquidity_quality.py` — US liquidity **quality** classifier separating WALCL/RRP/TGA quantity from composition, RRP buffer and HY/NFCI stress confirmation.
- `brain/treasury_context.py` — TGA, net-liquidity, Treasury-plumbing context bridge.
- `brain/market_view.py` — the single perception artifact with freshness/confidence/status and validated-vs-advisory authority rules.
- `brain/neural_web_context.py` — structured macro→bot graph/context bridge and typed decision-policy chokepoint.
- `brain/rotation_tensor.py`, cycle/rotation machinery — market migration / relative-strength context.
- `portfolio/context_gate.py`, Prophet feed / entry engine — right-name/right-time checks that must remain downstream of any liquidity idea.
- `brain/outcome_ledger.py`, `brain/board_learning.py`, `brain/journal.py`, `brain/improvement_agenda.py`, `brain/self_tune.py`, experiment registry — the existing learning and bounded-self-improvement substrate.
- Neural Web and its graph/contradiction/bottom-sensor system — the correct home for second- and third-order causal relationships.

Therefore the new program is **not another book** and **not another free-form AI analyst**. It is a new perception/forecasting lobe that connects existing machinery.

### 1.2 Correct architectural position

```text
          GLOBAL + LOCAL LIQUIDITY INPUTS
      central banks / money / credit / TGA / RRP
      USD funding / curves / credit spreads / FX
                       │
                       ▼
         ┌────────────────────────────┐
         │ GLOBAL LIQUIDITY STATE     │
         │ stance / impulse / breadth │
         │ orthogonalised impulse     │
         └─────────────┬──────────────┘
                       │
          ┌────────────┴─────────────┐
          ▼                          ▼
 US LIQUIDITY QUALITY          GLOBAL QUALITY / SOURCE
 existing W-I classifier       monetary / fiscal-plumbing /
 WALCL-RRP-TGA + credit        bank-credit / dollar-funding
          └────────────┬─────────────┘
                       ▼
             LIQUIDITY SHOCK ENGINE
       immutable shock_id + magnitude + type
                       │
                       ▼
          LIQUIDITY TRANSMISSION LAB
    learned conditional impulse-response curves
     asset / region / sector / theme / horizon
                       │
                       ▼
             REPRICING GAP ENGINE
 expected response - realised response so far
                       │
       ┌───────────────┼──────────────────┐
       ▼               ▼                  ▼
   Market View     Neural Web         Dislocation lane
   advisory plane  causal context     candidate evidence
       │               │                  │
       └───────────────┼──────────────────┘
                       ▼
           EXISTING QUALITY × ENTRY × CONTEXT
           Prophet / research / risk / gates
                       │
                       ▼
                   decisions
                       │
                       ▼
              outcome + learning loop
```

The new system **creates evidence and candidates; it does not bypass the existing decision constitution.**

---

## 2. Naming and object model

Program name: **Global Liquidity Transmission (GLT)**.

The public/product-facing language can be simpler:

- **Liquidity State** — “what changed?”
- **Repricing Map** — “what moved first / what is lagging?”
- **Liquidity Opportunities** — “where is the remaining gap?”
- **Track Record** — “did these calls work?”

Internally, GLT is one lobe with six deterministic sub-engines:

1. `liquidity_state` — stance / impulse / orthogonalised impulse / breadth.
2. `liquidity_quality_global` — source and quality classification; consumes existing US quality instead of replacing it.
3. `liquidity_shocks` — identifies immutable shock episodes.
4. `transmission_curves` — conditional forward response estimates.
5. `repricing_gap` — remaining expected response and anomaly score.
6. `transmission_learning` — forward grades, calibration, trust/demotion, experiment registry.

The **AI layer is downstream**: it explains, investigates, proposes causal edges and launches research when deterministic state changes materially. An LLM never manufactures the core signal.

---

## 3. GLT-1 — Global Liquidity State kernel

### 3.1 Vega-inspired baseline

Reproduce the disclosed Vega idea independently, not their source code:

- global central-bank / money components;
- log-transform where economically appropriate;
- point-in-time expanding z-scores;
- stance = composite level;
- impulse = first difference of stance;
- orthogonalised impulse = expanding/rolling regression residual of impulse on stance;
- all calculations causal at each timestamp.

The point is **not** to assume Vega’s factor is true. It becomes one candidate signal inside the GLT lab.

### 3.2 Mastermind extensions

The state kernel should publish separate families rather than forcing one magic scalar:

- `monetary_stance`
- `monetary_impulse`
- `orthogonalised_impulse`
- `liquidity_breadth` — number/share of major jurisdictions improving.
- `credit_impulse_global` — bank/market credit where reliable.
- `usd_funding_impulse` — dollar / funding / basis / financial-condition proxy bundle.
- `policy_liquidity_impulse` — central-bank balance-sheet actions.
- `market_confirmation` — optional, never part of the causal raw signal itself.

The core artifact must preserve the components, contribution weights, timestamps, native frequencies, last real observation, and revision/vintage status. Missing data **reduces coverage/confidence**; it never silently becomes neutral.

### 3.3 Point-in-time requirement

Backtests must use data as known at the time wherever possible (ALFRED/vintage-aware for revised US series; release-date alignment for other sources). Final-revised history must never be allowed to masquerade as a live tradable historical signal.

---

## 4. GLT-2 — Liquidity quality and source decomposition

This is where Mastermind should be better than a simple GLI.

Existing `liquidity_quality.py` already demonstrated why “net liquidity up” is insufficient: TGA drawdown / depleted RRP / widening credit can look quantitatively positive while economically reflecting mechanical or stress conditions.

GLT therefore represents a liquidity move as a **typed shock**:

```text
monetary_easing
monetary_tightening
fiscal_plumbing_injection
fiscal_plumbing_drain
bank_credit_expansion
bank_credit_contraction
usd_funding_relief
usd_funding_stress
em_local_liquidity_expansion
mixed_or_conflicted
unknown
```

A shock includes:

- source contributions;
- direction;
- magnitude z-score / percentile;
- persistence;
- breadth;
- quality label;
- credit confirmation / contradiction;
- dollar confirmation / contradiction;
- revision risk / freshness;
- confidence.

This matters because BTC, duration, gold, US cyclicals and China equities can react differently to equal-size shocks from different sources.

---

## 5. GLT-3 — Shock episode registry

The entire learning loop requires **immutable event identity**.

Every material liquidity change creates a `shock_id`, for example:

```text
liq_2026-08-18_global_ortho_pos_8f31
```

A shock record should include:

```json
{
  "shock_id": "...",
  "as_of": "YYYY-MM-DD",
  "first_detected": "...",
  "state_before": {},
  "state_after": {},
  "shock_type": "monetary_easing",
  "direction": 1,
  "magnitude_z": 1.73,
  "breadth": 0.67,
  "quality": "benign|mechanical|stress|mixed",
  "confidence": 0.78,
  "conditions": {
    "dxy": "falling",
    "real_yields": "falling",
    "credit": "stable",
    "growth": "softening",
    "inflation": "cooling",
    "china_gate": "closed"
  },
  "source_snapshot_hash": "..."
}
```

**Keep-first** semantics: later revisions can append an amendment, but the original live-time shock state is never rewritten. This is the no-cherry-picking substrate for the scorecard.

---

## 6. GLT-4 — Liquidity Transmission Lab / Repricing Clock

This is the highest-value new primitive.

### 6.1 Research question

For each liquidity shock type and market regime:

> what is the expected response of asset/theme/region *i* at horizon *h*, and how stable is that response out-of-sample?

Estimate at fixed horizons such as:

`1, 5, 10, 20, 40, 60, 90, 120` business days.

Universe begins with liquid macro proxies, then expands only when the data substrate is trustworthy:

- BTC / crypto beta
- SPY / QQQ / semis / software / small caps
- duration / yields / credit
- gold / silver / commodities / oil / copper
- developed ex-US
- EM broad
- China/HK broad (MCHI/FXI/KWEB/HSTECH/HK indexes)
- BABA/Tencent/selected HK megacaps
- sector / theme baskets
- later: individual-stock clusters where enough independent episodes exist.

### 6.2 Do not use one unconditional lag

The BTC→BABA observation is explicitly **conditional**. The same leader-laggard relation may disappear or reverse under different local conditions.

Response estimation therefore conditions on compact state variables, for example:

- liquidity shock type / magnitude / breadth;
- DXY / dollar funding state;
- real-yield state;
- global credit state;
- growth / inflation regime;
- volatility regime;
- starting valuation/extension;
- starting positioning/crowding;
- local regional gate (China/HK below);
- Prophet / price stage as a separate timing confirmation, not a causal liquidity input.

Use hierarchical/shrunk estimates: broad asset-class priors first; narrower theme/ticker relationships must earn their own sample size. No 3-observation “edge.”

### 6.3 Output: response curve, not a binary signal

For every target:

```json
{
  "target": "BABA",
  "shock_family": "global_positive_impulse",
  "expected_curve": {
    "5d": 0.01,
    "20d": 0.03,
    "40d": 0.07,
    "60d": 0.11,
    "90d": 0.09
  },
  "uncertainty": {...},
  "peak_horizon_bdays": 60,
  "effective_n": 18,
  "oos_metric": {...},
  "status": "shadow|advisory|validated|demoted"
}
```

The curve allows the system to reason about *where we are on the expected repricing clock*.

---

## 7. GLT-5 — China/HK Transmission Gate

The BTC→BABA case study becomes the first explicit local-gate template.

### 7.1 First-principles model

The lobe must not encode “BTC sucks HK liquidity” as literal plumbing. The better decomposition is:

```text
common global liquidity shock
      │
      ├── fast / highly reflexive / 24×7 global assets → BTC reprices rapidly
      │
      └── China/HK risk assets
             │
             └── require local gates to open:
                 CNH / dollar
                 China credit impulse / TSF
                 PBoC/local liquidity
                 growth surprises
                 policy/regulatory state
                 earnings revisions
                 southbound / foreign flows
                 valuation / positioning
                 HK funding conditions
```

The system may additionally measure **risk-budget substitution** (BTC/crypto dominance, flows, momentum) as a possible temporary negative concurrent effect, but this is a hypothesis to grade—not a hard-coded causal truth.

### 7.2 `china_gate` output

```text
closed     global liquidity exists but local China transmission is hostile
opening    2+ causal local legs improving; still shadow
open       enough validated local legs supportive
conflicted supportive and hostile legs coexist
unknown    data insufficient/stale
```

The gate has **no direct buy authority**. It changes the interpretation of a delayed-repricing hypothesis.

### 7.3 Canonical example logic

```text
BTC + strong positive impulse confirmation
BABA / KWEB materially behind expected response curve
China gate CLOSED  -> “lagging, but no actionable catch-up thesis”
China gate OPENING -> “watch / candidate for research”
China gate OPEN    -> “liquidity repricing gap is live evidence; send to existing entry/context gates”
```

The system must be able to discover that BTC is *not* the right leader in future regimes and replace/demote that relation automatically through forward grading.

---

## 8. GLT-6 — Repricing Gap / Liquidity Dislocation engine

Define the conceptual quantity:

```text
RepricingGap(i,t,h) = ExpectedResponse(i | shock,state,h)
                    - RealisedResponse(i since shock)
```

But raw difference is insufficient. A useful score also needs uncertainty, causal-gate status, extension, and independent confirmation.

Proposed shadow score:

```text
GapScore = standardized_remaining_response
         × transmission_reliability
         × gate_quality
         × shock_confidence
         × non_redundancy
```

where **non_redundancy** penalizes signals that merely restate an already-consumed regime/price factor.

Output states:

- `EARLY` — expected beneficiary, response window not yet mature.
- `LAGGING` — materially behind expected curve.
- `CATCHUP_FORMING` — lagging + local/causal gate opening + price-state confirmation emerging.
- `REPRICED` — expected move largely realized.
- `OVERSHOT` — moved materially beyond expected curve.
- `BROKEN_CHAIN` — expected transmission failed / gate closed / causal contradiction.
- `INSUFFICIENT` — sample/data too thin.

Only `LAGGING` / `CATCHUP_FORMING` are candidates for the existing dislocation/entry funnel. They do not themselves authorize a position.

---

## 9. Macro × Theme sensitivity matrix (Vega idea, Mastermind version)

Vega’s 5-pillar × theme matrix is an excellent **compression interface**, but Mastermind should not hand-author the scores if empirical data can learn them.

Create a matrix over a compact set of top-level macro drivers:

- global liquidity
- growth
- inflation
- real rates / duration
- credit / funding
- USD
- volatility / risk appetite
- optional local/regional factors

For each theme/sector/asset, estimate signed sensitivity and confidence conditionally by regime.

The user-facing matrix can look simple:

```text
THEME               LIQ  GROWTH  INFL  RATES  CREDIT  USD  TOTAL
AI infrastructure   +2    +2      -1    -1      +1    +1   +6
Gold                +2    -1      +2    +2       0    +2   +7
China internet      +1    +2      -1    +1      +1    +2   +6 [gate opening]
```

Underneath, every cell carries `effective_n`, OOS evidence, freshness and status. A cell with no evidence renders `—`, not a fabricated zero.

This matrix should become a compact bridge between **Market View → themes → second-order opportunities**.

---

## 10. Second-order alpha: use Neural Web, do not build a parallel graph

Vega productizes “we buy bottlenecks, not the obvious first-order name.” Mastermind already has the architecture to make this materially more powerful.

GLT should publish shock/context nodes into Neural Web:

```text
liquidity shock
  -> first-order asset classes / factors
  -> themes
  -> industries / supply chains
  -> companies
  -> portfolio exposure
```

Neural Web then provides causal paths; GLT provides the **timing / expected response / gap** dimension.

A ranked second-order opportunity should therefore contain:

- upstream shock;
- causal path;
- historical transmission curve;
- realized response so far;
- remaining repricing gap;
- local/context gates;
- Prophet/entry state;
- contradictory evidence;
- thesis falsifier;
- confidence and `effective_n`.

This becomes the quantitative backbone for a future **Second-Order Alpha Feed** instead of a curated list of clever stories.

---

## 11. Forecast / signal scorecard

Adopt Vega’s strongest trust-building product primitive: **timestamped, immutable scorecards**.

Every GLT shock makes forward predictions before outcomes are known:

```text
shock_id
asset/theme
horizon
expected direction
expected return/range
probability/confidence
state/gates at prediction time
model/version hash
prediction timestamp
```

When horizons mature, grade automatically:

- direction hit rate;
- return error / interval coverage;
- Brier score for probabilistic calls;
- rank IC across the target universe;
- calibration by shock type / regime / region;
- “remaining repricing gap” hit rate;
- comparison against simple baselines (same-time momentum, unconditional average, no-signal).

No retroactive editing. A model change creates a new version; old predictions stay attached to the version that made them.

This scorecard should eventually be user-facing. It is not marketing decoration—it is the promotion/demotion authority substrate.

---

## 12. Autonomous learning and improvement

### 12.1 The lobe learns from *every shock*, not only trades

This is critical. A trading-only learner is selection-biased.

For every shock and every tracked target, the system records forward outcomes whether or not Mastermind bought anything.

Ledger shape:

```text
shock_id × target × horizon × state_bucket × model_version
    -> expected
    -> realized
    -> error
    -> gate state
    -> response timing
```

This creates thousands of observations over time without requiring portfolio turnover.

### 12.2 Automatic relationship lifecycle

Every candidate transmission relation has a state:

```text
DISCOVERED -> SHADOW -> ADVISORY -> VALIDATED
                  \-> DEMOTED / DEAD
```

Rules:

- **DISCOVERED:** statistical/graph relationship proposed; zero authority.
- **SHADOW:** forward predictions written, no decision consumption.
- **ADVISORY:** minimum effective sample + basic OOS gate; can appear in UI/context.
- **VALIDATED:** pre-registered forward threshold passed; may sign a Market View tilt or originate candidacy, subject to existing P3 authority rules.
- **DEMOTED:** recent rolling calibration breaks; loses decision weight immediately.
- **DEAD:** repeated failure / unstable sign; retained historically, not used.

No LLM may promote a relationship. Promotion is deterministic from pre-registered evidence.

### 12.3 Discovering new leaders and lags

The learner periodically searches for:

- stable lead/lag response peaks after shock events;
- changing peak horizons;
- regime-specific sign flips;
- target groups that consistently lag first-order beneficiaries;
- causal graph neighbors with repeated delayed response.

To prevent data-mining:

- nested / walk-forward lag selection;
- multiple-testing / FDR control for broad searches;
- effective-n accounting for overlapping shocks;
- economic plausibility / graph path as an optional prior, never proof;
- frozen OOS period before promotion.

BTC→BABA may prove to be a real conditional path, a broader BTC→China path, a generic “fast risk asset → EM catch-up” path, or a 2023–26 accident. The architecture is designed to learn which one is true.

### 12.4 Concept-drift detection

For each validated relation maintain:

- rolling hit rate;
- rolling Brier / return error;
- lag drift;
- calibration drift;
- sign stability;
- regime composition.

If the relation falls below its demotion gate, authority shrinks automatically. Restoration requires new forward evidence; never auto-restore from an in-sample refit.

### 12.5 Integration with Mastermind AI / W-L

GLT learning should emit structured items into the existing improvement system:

- repeated miss due to local gate absent -> proposal to add/repair a gate source;
- lag drift -> experiment to re-estimate horizon family;
- new candidate leader -> new SHADOW experiment;
- data freshness problem -> nudge / agenda item;
- poor scorecard bucket -> model-family demotion;
- successful relation -> journal/scorecard evidence, **not** automatic leverage increase.

Only bounded `doctrine.yml` priors may be self-tuned through the existing immutable Lab/self_tune path. New code, new data sources, new causal edges with authority remain proposal/review items.

---

## 13. Event-triggered research and thesis invalidation

Adopt Vega’s “research triggered by alpha inputs” concept, but make it state-aware and grounded.

### 13.1 Research trigger

Material GLT events may wake research when:

- a new high-confidence shock is detected;
- a target flips into `LAGGING` / `CATCHUP_FORMING`;
- a validated transmission relation breaks;
- a portfolio holding becomes exposed to a negative shock/path;
- a second-order candidate crosses a research threshold.

The research agent receives structured evidence + source data; it must not infer numbers from model memory.

### 13.2 Dependency-keyed research

Generalize Vega’s regime-keyed cache.

A Mastermind thesis should carry dependency hashes such as:

```text
macro_state
liquidity_state
transmission_relation
local_gate
fundamental_state
valuation_state
positioning_state
entry_state
```

A materially changed dependency marks the affected section **stale** and triggers targeted re-research. Do not blindly regenerate every memo on a timer.

### 13.3 Kill conditions

Every user-facing liquidity opportunity must include a deterministic falsifier / kill condition where possible, for example:

- shock impulse reverses below threshold;
- China gate recloses;
- expected lag window expires without response;
- causal graph contradiction becomes active;
- fundamentals/earnings invalidate the beneficiary thesis;
- price already overshoots the learned curve.

This maps naturally to Mastermind’s existing falsifier culture.

---

## 14. Portfolio-news / event mapping

Vega’s real-time portfolio-news mapping is worth adopting as a product pattern, but its natural Mastermind implementation is broader:

```text
incoming event/news
 -> entities / macro variables / themes
 -> Neural Web causal paths
 -> portfolio holdings
 -> GLT exposure: does this reinforce/break a current liquidity-transmission thesis?
 -> urgency / confidence / direct-vs-second-order
```

A portfolio alert should say more than “news mentions BABA.” Example:

```text
BABA — indirect liquidity thesis changed
Global liquidity impulse remains +1.4σ.
China gate moved OPENING -> OPEN after CNH + credit confirmation.
BTC leader leg is already +31%; BABA remains 1.2σ behind its 60d response curve.
New event: policy support reinforces local transmission path.
Status: CATCHUP_FORMING. Entry gate still required.
```

This is a future user-facing wedge and a direct consumer of the new lobe.

---

## 15. Decision / allocation history

Do not import Vega’s automatic rebalancing as another independent authority layer. Mastermind already has a richer decision constitution.

Do import the **auditability**:

Every time GLT changes a state that is consumed downstream, log:

- old state;
- new state;
- exact source changes;
- model/version;
- expected implications;
- targets affected;
- what downstream system did or did not do;
- eventual outcome.

User-facing later as **Decision Timeline / Why It Changed**.

---

## 16. Site / Terminal product surfaces

The core lobe exists even if no UI ships. UI is a *view over the same artifacts*, never a separate analytics implementation.

### 16.1 Surface A — Market State / Liquidity card

Compact top-level card:

```text
GLOBAL LIQUIDITY
Stance: +0.7σ
Impulse: +1.5σ ↑
Breadth: 4/6 improving
Quality: mixed-positive
USD funding: easing
US plumbing: mechanical-positive
Confidence: 74%
```

Click opens the full Repricing Map.

### 16.2 Surface B — Repricing Map

The defining GLT product page.

Rows / lanes:

```text
TARGET      PHASE             EXPECTED PEAK    REALIZED    GAP      STATUS
BTC         first responder   20d              +28%        small    REPRICED
QQQ         early             40d              +13%        modest   IN-PROGRESS
Semis       early             40d              +18%        small    REPRICED
Gold        conditional       60d               +7%        +4%      LAGGING
China/HK    delayed           60-90d            -3%        +14%     GATE OPENING
BABA        delayed           ~60d             -11%        +?       WATCH
```

Numbers shown only when statistically supported; otherwise labels/uncertainty.

### 16.3 Surface C — Liquidity Opportunities / second-order feed

Ranked cards only for large, reliable gaps:

- upstream shock;
- target/theme;
- causal path;
- remaining gap;
- expected window;
- gate state;
- Prophet/entry status;
- kill condition;
- track-record link.

This is where the sophisticated backend gets Vega-like compression.

### 16.4 Surface D — Macro × Theme matrix

A simple matrix fed from learned sensitivities. Useful in both Macro Dashboard and Terminal “Market Dashboard” suite.

### 16.5 Surface E — Track Record / Scorecard

Public-facing eventually:

- GLT forecasts;
- regime transitions;
- repricing-gap calls;
- Prophet calls;
- dislocation calls;
- economic nowcasts.

A single **Mastermind Track Record** is preferable to one scorecard per subsystem.

### 16.6 Per-stock integration

BABA / any stock page can show a small **Macro Transmission** block:

```text
Liquidity sensitivity: positive
Current GLT state: delayed beneficiary
Repricing state: lagging
Local gate: opening
Expected window: 40–90d
Track record: advisory (n=...)
```

No giant separate page is needed per ticker.

---

## 17. Vega feature adoption map

| Vega idea | Mastermind decision | Home |
|---|---|---|
| Orthogonalised GLI | **BUILD + independently validate** | GLT state kernel |
| Impulse > level | **Treat as hypothesis, not law** | GLT experiments |
| 5 macro pillars | **ADAPT to learned macro-driver matrix** | Macro × Theme |
| Alpha Engine / thematic scoring | **ADAPT; empirical + Neural Web enriched** | theme sensitivity + second-order feed |
| Second-order alpha | **STRONGLY ADOPT, deeper implementation** | Neural Web × GLT gap |
| Conviction score 1–10 | **DISPLAY summary only; do not replace gates** | opportunity cards |
| 7/9 factors + 6 rebalance triggers | **Do not clone unknown weights/triggers**; adopt explicit-trigger audit trail | existing decision spine |
| Thesis + catalyst + kill condition | **ADOPT everywhere user-facing** | research/theses/opportunity cards |
| Forecast scorecard | **HIGH PRIORITY ADOPT** | unified Track Record |
| Allocation-change timestamping | **ADOPT** | decision timeline |
| AI research triggered by alpha inputs | **ADOPT, grounded** | research trigger service |
| Regime-keyed research cache | **GENERALIZE to dependency-keyed invalidation** | research substrate |
| Real-time portfolio-news mapping | **ADOPT + graph/second-order enrich** | portfolio intelligence |
| Daily Alpha Feed | **ADAPT to Opportunity Feed** | UI |
| Weekly Review | **Fold into existing CIO / Mastermind AI review** | learning/agenda |
| AI chatbot over live engine | **Use existing Brain/Copilot, add GLT tools/context** | Terminal/Macro chat |
| Model portfolios | **Do not add a new book solely for Vega parity** | existing seven books |
| REST API / institutional feed | **Later expose GLT artifacts through existing API strategy** | API |

---

## 18. Contracts and ownership

### 18.1 Producer: Macro / Neural Web repo

Macro side should own raw global-liquidity ingestion and the canonical GLT producer because the data and Neural Web already live there.

Proposed public contract:

`site/liquiditydata/global_liquidity_transmission.json`

Schema: `global_liquidity_transmission.v1`.

Top-level blocks:

```text
meta
state
quality
active_shocks
transmission_summary
repricing_map
theme_matrix
scorecard_summary
freshness
```

Heavy historical ledgers remain in data/R2, not one giant site JSON.

### 18.2 Consumer: Mastermind repo

New sole reader:

`brain/liquidity_transmission.py`

Public API should be minimal and fail-soft:

```text
context()
market_plane()
target(ticker_or_asset)
opportunities(limit=...)
audit_row()
decision_signals(target)  # initially fully inert / shadow only
```

No downstream module may read the raw macro artifact directly.

Add a dedicated `liquidity_transmission` plane to `brain/market_view.py`; status = `advisory` until forward validation gates pass.

Neural Web context may also carry the same state/target facts, but the dedicated reader remains the attributable signal source for grading.

### 18.3 Terminal/site

Presentation consumes the published contract/API. It never re-computes GLI, response curves or gap scores in React.

---

## 19. Authority ladder

New env/config authority must be monotone and conservative:

```text
off       reader may exist; no computation consumed
shadow    compute + log predictions, no user/decision surface required
display   may show in UI / research context
candidacy may originate a candidate for existing gates
context   may contribute a bounded context/shrink signal
vote      may sign a Market View / lens vote only after explicit validation
```

Recommended default on first merge: **shadow**.

No mode gives GLT direct sizing or execution authority. Existing Quality × Entry × Context, Gate Officer / deterministic brake stack remain superior.

---

## 20. Validation gates

### 20.1 GLI-family signal gate

Before any state signal is validated:

- point-in-time / release-date backtest;
- expanding/rolling causal transforms only;
- true walk-forward OOS;
- compare level vs impulse vs orthogonalised impulse;
- pre-register assets/horizons before final holdout;
- multiple-testing correction for broad searches;
- report failures as prominently as successes.

### 20.2 Transmission relation gate

A relation must clear all:

- enough **independent shock episodes**, not overlapping daily rows;
- stable sign / peak-horizon region in train→validation→forward;
- incremental value over simple momentum/regime baselines;
- acceptable calibration / Brier or rank-IC depending output;
- no single episode dominating effect;
- condition bucket not so narrow it is unusable.

### 20.3 Repricing-gap gate

The actual alpha question is not whether assets correlate with liquidity; it is whether the **remaining-gap score predicts future relative return after controlling for starting momentum/extension**.

Primary tests:

- cross-sectional rank IC of GapScore vs future return;
- hit rate of top-decile gaps;
- MFE/MAE and time-to-catch-up;
- baseline comparison to price momentum, simple mean reversion, and Prophet alone;
- ablation: GLT + Prophet vs Prophet; GLT + ChinaGate vs GLT alone.

If GLT adds no incremental edge, it stays explanatory/display-only.

---

## 21. The BTC→BABA case study as a permanent regression fixture

The case study is not merely documentation. It seeds three explicit tests:

1. **Lead/lag:** do BTC/global fast-risk assets consistently lead China/HK assets after positive global-liquidity shocks, and at what horizon?
2. **Concurrent divergence:** is BABA/China weakness during the initial BTC leg systematic after controlling for China-local conditions, or anecdotal?
3. **Gate value:** does a ChinaGate opening materially improve the future-return precision of the delayed-repricing signal?

A frozen historical fixture should cover at least the observed 2023–2026 episodes, then a longer sample using BTC and broad China proxies. The BABA-specific relation must never be promoted from three attractive chart examples alone.

The fixture is a **sanity/replay test**, not the optimization target. Thresholds may not be tuned to force those episodes to pass.

---

## 22. Build program

### W-LIQ.0 — architecture + case study (THIS BRANCH)

**Deliverables**
- this masterplan;
- canonical English BTC→BABA case-study spec;
- contract + authority decisions frozen.

**Owner:** Sol.  
**Behavior change:** none.

### W-LIQ.1 — data + Global Liquidity State producer

**Macro repo**
- inventory existing global CB/money/credit series before adding sources;
- implement point-in-time-aligned state kernel;
- reproduce Vega-style stance/impulse/orthogonalised impulse as named candidate factors;
- add breadth/source/coverage;
- publish `global_liquidity_transmission.v1` with state only initially;
- historical backfill + unit tests.

**Owner:** Codex macro/data worker, because it needs repo-local data inspection, actual execution and backfill tests. Sol specifies/reviews.

### W-LIQ.2 — Mastermind reader + Market View shadow plane

**Mastermind repo**
- `brain/liquidity_transmission.py` sole reader;
- `audit_row()` and freshness contract;
- `liquidity_transmission` added to Market View as advisory;
- decision ladder implemented but default `shadow`/inert;
- golden tests showing no book change when shadow/off.

**Owner:** Codex implementation worker; Sol can draft code/review, but a worker should run the full test suite.

### W-LIQ.3 — shock registry + transmission lab

- immutable shock episodes;
- target universe registry;
- horizon response ledger;
- point-in-time walk-forward harness;
- BTC→China/BABA fixture;
- hierarchical/shrunk response curves;
- relation lifecycle / FDR / effective-n.

**Owner:** dedicated quant Codex session. This is the statistically sensitive core and should not be implemented as a quick patch.

### W-LIQ.4 — local gates + repricing-gap engine

- ChinaGate v1;
- broader local-gate contract so EM/region gates are extensible;
- `EARLY/LAGGING/CATCHUP_FORMING/REPRICED/OVERSHOT/BROKEN_CHAIN` state machine;
- GapScore shadow output;
- Prophet/context integration only as downstream confirmation;
- dislocation candidate bridge.

**Owner:** split quant + Mastermind integration workers; Sol final synthesis/review.

### W-LIQ.5 — autonomous grading / learning

- forward prediction ledger for every shock/target;
- scorecard calculations;
- promotion/demotion rules;
- concept-drift monitor;
- experiment-registry entries;
- improvement-agenda hooks;
- no-LMM self-learning math; new relations shadow-only by default.

**Owner:** Codex + Sol review against W-L / P3/P8 laws.

### W-LIQ.6 — Macro × Theme + second-order graph

- learned driver sensitivity matrix;
- map GLT shock nodes into Neural Web;
- combine graph path × response curve × pricing gap;
- ranked second-order opportunities;
- portfolio exposure mapping.

**Owner:** macro/Neural-Web worker + Mastermind consumer worker.

### W-LIQ.7 — product compression

- Liquidity State card;
- Repricing Map;
- Liquidity Opportunity Feed;
- Macro × Theme matrix;
- per-stock Macro Transmission block;
- unified Track Record / Scorecard integration;
- Decision Timeline.

**Owner:** Terminal/frontend Codex worker after schemas stabilize. Do not build UI against guessed payloads.

### W-LIQ.8 — triggered research + dependency invalidation

- event/material-state trigger service;
- grounded research packet;
- dependency hashes / targeted invalidation;
- portfolio-news mapping consumes same graph/state;
- Copilot/Brain tools for “why is this lagging?” / “what would invalidate this?”

**Owner:** Mastermind AI/research worker + Sol architecture review.

---

## 23. What Sol can do vs what should be delegated

### Sol should own

- architecture and authority boundaries;
- Vega idea selection / rejection;
- exact schemas and semantics;
- causal model / case-study framing;
- statistical acceptance criteria;
- cross-repo integration map;
- reviews of worker PRs;
- final product compression / naming;
- kill/promote decisions after evidence.

### Codex workers should own

- repo-local data census and source wiring;
- large historical backfills;
- implementation that requires running tests/benchmarks;
- walk-forward / FDR / OOS quant harness;
- frontend implementation against frozen contracts;
- multi-repo wiring and CI proof.

### Why not let Codex design the whole thing

The risk is local optimization: one worker adds a GLI module, another adds a dashboard, another adds a China factor, and Mastermind accumulates three disconnected systems. Sol must remain the architectural integrator and use Codex as execution capacity.

---

## 24. Immediate implementation order

1. Merge/freeze W-LIQ.0 docs only.
2. Commission **one macro/data census worker** before writing a producer. It must answer what global-liquidity data already exists and where; do not duplicate feeds.
3. Commission **one quant design worker** to create the point-in-time validation harness + BTC→China case fixture in parallel.
4. Once the producer schema is stable, build the Mastermind shadow reader/plane.
5. Accumulate/backfill shadow predictions **before** any candidacy/context authority.
6. Build Repricing Map UI only after state/gap schemas and uncertainty semantics are stable.
7. Build second-order feed after the gap engine and Neural Web bridge are attributable and gradeable.

---

## 25. Definition of success

This program succeeds if Mastermind can eventually answer, with an auditable track record:

> “A global liquidity impulse occurred. BTC and US high-beta assets have already completed most of their historically expected first-stage repricing. China/HK remains behind, but its local transmission gate has shifted from closed to opening. BABA is currently 1.1σ behind the conditional response curve; the relationship is advisory with effective_n=17 and has added incremental forward rank-IC over momentum in the holdout. Prophet still says wait, so the name remains on watch. These three conditions would invalidate the catch-up thesis.”

That is the desired product: **state → transmission → gap → causal gating → timing → falsifier → track record**, compressed into something a user can understand in seconds.

The sophistication lives underneath. The surface stays simple.
