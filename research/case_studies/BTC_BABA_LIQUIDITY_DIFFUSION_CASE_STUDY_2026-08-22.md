# Case Study — BTC → China/HK Delayed Liquidity Repricing

**Date:** 2026-08-22  
**Program:** W-LIQ — Global Liquidity Transmission  
**Purpose:** canonical hypothesis / replay fixture for the Liquidity Transmission Lab; **not** a hard-coded trading rule.

---

## 1. Observation

Across several visible 2023–2026 risk-on/liquidity episodes, Bitcoin appeared to reprice materially earlier than Alibaba and broader China/HK risk assets. During portions of Bitcoin's initial positive leg, BABA often weakened or failed to participate; BABA/China then caught up roughly several weeks to a few months later.

The strongest qualitative pattern motivating this study is approximately:

```text
positive global liquidity / risk-capacity impulse
      ↓
BTC / fast global high-beta reprices first
      ↓
China/HK remains flat or weak while local gates remain hostile
      ↓
local China/HK conditions improve / global risk broadens
      ↓
BABA / China internet / HK beta catches up later
```

The chart observation suggests a lag around the **2–4 month** region in several recent episodes, with ~12–14 weeks a particularly visible interval. This is a research prior only.

---

## 2. What the hypothesis is — and is not

### Hypothesis A — common shock, different transfer functions

A common global liquidity shock can affect assets at different speeds because their transfer functions differ.

BTC is a plausible fast responder because it is:

- 24×7 and globally accessible;
- strongly dollar-linked;
- high beta to marginal risk capacity;
- highly reflexive / momentum-sensitive;
- leverage-friendly;
- weakly anchored to near-term cash-flow valuation.

China/HK equities are additionally gated by:

- CNH / USD conditions;
- China credit impulse / TSF;
- PBoC / domestic liquidity;
- Chinese growth expectations;
- policy / regulatory state;
- earnings revisions;
- local and foreign flows;
- valuation / positioning;
- HK funding conditions.

Thus global liquidity can be positive while China/HK remains weak until local transmission improves.

### Hypothesis B — temporary marginal risk-budget substitution

During the first BTC leg, investors may redirect **marginal risk budget, attention, leverage capacity and momentum capital** toward crypto and away from unloved China/HK risk assets.

This can depress the marginal bid for BABA without implying that Bitcoin literally destroys or absorbs aggregate system cash. Cash paid for Bitcoin is received by a seller; the potentially scarce objects are portfolio risk budget and marginal demand.

This substitution channel is plausible but must be tested separately from the common-shock/lag channel.

### Hypothesis C — second-round wealth / collateral / breadth effect

A first-stage rally in BTC / high-beta assets can increase wealth, collateral values, P&L and willingness to take risk. That may later broaden the search for lagging beta into EM / China/HK.

This creates a possible second-order loop:

```text
liquidity impulse
 -> BTC repricing
 -> wealth / collateral / risk tolerance rises
 -> search for lagging beta broadens
 -> EM / China/HK catches up if local gates allow
```

Again: hypothesis, not assumed truth.

---

## 3. Why “BTC sucks liquidity out of Hong Kong” is an incomplete model

A literal hydraulic story is too strong.

Better decomposition:

```text
R_BTC ≈ beta_liquidity * global liquidity
      + beta_risk * marginal risk appetite
      + reflexivity / leverage / momentum

R_BABA ≈ beta_global * global risk capacity
       + beta_china * China growth / credit / policy
       + delta China risk premium
       + FX / flow / earnings / idiosyncratic terms
```

The same global shock can therefore produce:

```text
BTC ↑ strongly
BABA ↓
```

without contradiction if the China-local terms remain sufficiently negative.

The GLT lobe should model **common upstream shock + heterogeneous transmission + local gates**, and treat flow substitution as a possible modifier rather than the sole explanation.

---

## 4. Research questions

### Q1 — Does BTC actually lead China/HK after liquidity shocks?

Test BTC forward/current response against later returns for:

- KWEB
- MCHI
- FXI
- Hang Seng / HSTECH proxies
- BABA
- Tencent / other HK megacaps where clean history exists.

Do **not** simply correlate overlapping rolling returns. Eventize independent liquidity shock episodes first.

### Q2 — Is BTC the cause, or merely the fastest observable proxy?

Compare leader candidates:

- orthogonalised global liquidity impulse itself;
- BTC;
- QQQ / semis / high-beta US factors;
- USD / real-yield changes;
- crypto breadth / stablecoin liquidity where available.

If BTC adds no incremental information after the upstream liquidity shock is known, it should be treated as a **confirmation sensor**, not a causal driver.

### Q3 — Is concurrent China weakness systematic?

Within positive global-liquidity episodes, test whether BABA/China tends to underperform during the first BTC repricing stage after controlling for:

- China policy/growth state;
- CNH;
- domestic credit;
- starting momentum/valuation;
- local news shocks.

This distinguishes a repeatable risk-budget/segmentation effect from three memorable examples.

### Q4 — Does a ChinaGate improve the signal?

Test whether delayed-repricing precision improves when the later China/HK entry window requires an improving/open ChinaGate.

A useful result would look like:

```text
BTC/global-liquidity lead alone: weak/moderate future China signal
+ ChinaGate opening: materially better hit rate / rank IC / MFE-MAE
```

If the gate adds nothing, it should not survive.

### Q5 — What is the true lag distribution?

Do not fit “14 weeks” because the chart suggests it.

Estimate response at precommitted horizons:

`5 / 10 / 20 / 40 / 60 / 90 / 120 business days`.

Report the full response curve and uncertainty. The peak may move by shock type / regime.

---

## 5. Canonical causal graph to test

```text
                         GLOBAL LIQUIDITY SHOCK
                                   │
             ┌─────────────────────┼──────────────────────┐
             ▼                     ▼                      ▼
          BTC / CRYPTO         US HIGH BETA           USD / CREDIT
        fast responder        fast responder       funding transmission
             │                     │                      │
             └──────────────┬──────┴───────────────┬─────┘
                            ▼                      ▼
                    GLOBAL RISK CAPACITY      DOLLAR / VaR RELIEF
                            │                      │
                            └──────────┬───────────┘
                                       ▼
                                  CHINA / HK GATE
                          CNH / credit / PBoC / policy /
                          growth / flows / earnings
                                       │
                  ┌────────────────────┴──────────────────┐
                  ▼                                       ▼
              gate closed                           gate opening/open
         China can remain weak                    catch-up path available
                                                          │
                                                          ▼
                                                BABA / KWEB / HK beta
```

The graph encodes **testable conditional edges**, not fixed truths.

---

## 6. ChinaGate v1 candidate inputs

Initial research inventory; inclusion in the live gate requires point-in-time availability and forward evidence.

### FX / global funding

- USD/CNH trend / acceleration;
- DXY / broad USD;
- US real yields;
- HKD/HIBOR funding where relevant.

### China domestic liquidity / credit

- TSF / credit impulse;
- bank loan growth;
- PBoC liquidity / reserve / policy measures;
- money growth where reliable.

### Growth / policy

- China economic surprise / PMIs / activity proxies;
- policy stimulus state;
- regulatory-risk state.

### Market confirmation

- China/HK breadth;
- southbound / foreign flow state;
- China internet relative strength;
- earnings revisions;
- valuation / positioning;
- Prophet / technical stage **only as downstream timing confirmation**, not part of the causal liquidity score.

Gate status must degrade to `unknown` or `conflicted` when coverage is poor; it must never invent an “open” state from missing inputs.

---

## 7. Repricing-gap application

For a given positive shock:

```text
expected_BABA_return(h | shock, state)
        - realized_BABA_return_since_shock
        = remaining repricing gap
```

But an actionable candidate requires:

```text
large remaining gap
AND relation reliability sufficient
AND ChinaGate opening/open
AND shock still live / not invalidated
AND no strong causal contradiction
AND existing Mastermind entry/context gates do not block
```

Possible output:

```text
BABA
GLT status: CATCHUP_FORMING
Leader stage: BTC REPRICED
ChinaGate: OPENING
Remaining gap: high (advisory)
Peak historical window: 40–90d
Relation status: SHADOW / effective_n=...
Prophet: WAIT
Action: WATCH, not buy
Kill: liquidity impulse reversal OR ChinaGate recloses OR lag window expires
```

This is the desired separation between **macro intelligence** and **execution timing**.

---

## 8. Historical fixture design

### 8.1 Recent visual episodes

Freeze the visually identified 2023–2026 episodes as a human-observation fixture. The fixture answers:

- does the pipeline reproduce the intuitive sequencing without being tuned to it?
- does it correctly flag counterexamples such as China-specific stimulus shocks that cause China/HK to jump independently of the normal cascade?

### 8.2 Long sample

Use the longest clean overlapping history for BTC and broad China proxies. BABA-specific testing begins at its available listing history but must be interpreted separately from broad China.

### 8.3 Keep the recent case out of final tuning

The system may be designed using the observation, but final thresholds/horizons must not be optimized to force the recent arrows to pass. Use train/validation/holdout or rolling walk-forward with the case episodes explicitly labeled in reports.

---

## 9. Required baselines

The BTC→China relation only matters if it beats simpler explanations.

Compare against:

1. China own momentum / mean reversion.
2. DXY alone.
3. global liquidity impulse alone.
4. QQQ / global risk-on proxy alone.
5. ChinaGate alone.
6. Prophet / technical entry state alone.
7. BTC lead alone.
8. GLT shock + BTC confirmation + ChinaGate.
9. full RepricingGap + downstream entry gate.

The desired evidence is **incremental value**, not a high raw correlation.

---

## 10. Falsifiers

Kill or demote the BTC→China path if any of the following persists after adequate effective sample:

- BTC lead disappears after conditioning on upstream liquidity;
- peak lag is unstable / sign flips across adjacent windows;
- ChinaGate provides no incremental predictive value;
- relation is driven by one or two episodes;
- top-gap candidates do not outperform momentum/mean-reversion baselines;
- forward performance degrades materially after discovery;
- broad China works but BABA does not — in which case BABA-specific edge is removed while broader relation may survive;
- the relation is only descriptive and has no incremental future-return value — then keep it display/explanation-only.

---

## 11. What this fixture should teach the autonomous learner

The system's long-term goal is not to memorize BTC→BABA. It should learn a general class of relationships:

```text
upstream shock
 -> fastest responder(s)
 -> intermediate responders
 -> delayed gated beneficiaries
 -> observed vs expected progress
 -> remaining gap
```

For every new cycle it should be able to discover that:

- BTC remains the best leader;
- or semis replace BTC;
- or credit leads;
- or China becomes a first-stage responder because domestic stimulus overwhelms the normal gating;
- or the whole learned cascade has broken.

A mature GLT system should therefore update the **topology and clocks** from evidence while preserving historical model versions and never rewriting past predictions.

---

## 12. Product rendering of this exact case

A future user should not need this entire document.

A card could read:

```text
CHINA/HK CATCH-UP WATCH

Global liquidity impulse       +1.5σ ↑
Fast-risk leader               BTC — 82% repriced
China/HK transmission gate     OPENING
BABA response                  1.1σ behind expected curve
Expected window                40–90 business days
Relation status                ADVISORY · n=18
Entry timing                   WAIT

Why: global risk has repriced faster than China/HK while local
transmission is beginning to improve.

Kill: impulse reverses / ChinaGate recloses / lag window expires.
Track record →
```

That is the compression target for W-LIQ.
