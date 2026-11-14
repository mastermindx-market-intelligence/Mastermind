# Functional design: what each component must earn

This is first-principles synthesis plus explicitly bounded public-source research. It is not a claim to know every successful trader's private process. The empirical arms are governed by PROTOCOL.md and its pre-outcome addenda, not by persuasive language here.

## The economic object is a distribution of net wealth changes

A decision needs a reason for expected compensation, an executable opportunity, an estimate of the possible path, an exposure budget, and a way to recognize when the opportunity has expired. These cannot be replaced by a count of agreeing indicators. The elementary objective is expected payoff after trading costs and financing, subject to loss, concentration, liquidity and capital constraints. Different investors legitimately choose different points on that tradeoff.

Three main ways an equity opportunity can be compensated are hypotheses about (i) bearing a priced risk with sufficient capacity to survive, (ii) future cash flows or discount rates being mispriced and subsequently revised, and (iii) slow information incorporation, persistent flows or liquidity provision. A price pattern may be evidence of one of these mechanisms; it is not the mechanism itself. An attractive company is not necessarily an attractive price, a valid trigger is not necessarily positive expectancy, and low volatility is not a reason for expected outperformance.

## Component jobs and concrete falsifiers

| Component | Its actual job | What it does NOT prove | Discriminating test |
|---|---|---|---|
| Opportunity evidence | Explain why expected net return should be positive relative to available alternatives | A visually attractive chart is underpriced | Benchmark-relative and cash-relative payoffs, point-in-time fundamentals/revisions where actually available |
| Slow relative momentum | Detect persistent relative repricing/leadership | It knows the catalyst or is independent of market beta | Same-date cross-name comparison, beta/sector caveats, persistence beyond costs |
| T1/T2 or an alternative trigger | Locate a specified change of price-momentum state and define when to evaluate an entry | It is the only possible representation of momentum or a calibrated probability | Canonical prefix replay, interchangeable triggers, common outcomes and opportunity set |
| Volatility forecast | Estimate dispersion/scale over the actual holding horizon | Direction, positive expectancy, exact stop probability or a future loss cap | Common-target forecast loss, calibration, stress and conditional marginal utility |
| Path-risk model | Estimate which stop/target/timeout outcome is plausible for this setup | Avoiding all stop-outs maximizes returns | Full class distribution, payoff-aware and stop-only controls, timeouts/dead money |
| Position/portfolio construction | Translate opportunity and uncertainty into survivable exposure with scarce capital | Independent-looking indicators create diversified risks | Shared capital, covariance/concentration, matched exposure and trade count |
| Execution | Capture an opportunity at attainable prices before information decays | A next-bar label guarantees a fill at the desired stop or target | Opening gaps, costs, ambiguous OHLC order, liquidity, latency, no retroactive cash recycling |
| Exit | End or reduce an opportunity when its thesis, price structure, time window or risk budget is invalidated | It can consistently sell the absolute top | Same-entry exit ablations, right-tail preservation, recovery and repeat-stop costs |

The current experiment has price, volatility and membership evidence. It does NOT contain a qualified per-event earnings-revision/catalyst/fundamental panel or observed institutional dealer inventories. Those mechanisms remain explicit missing ingredients, not labels fabricated from prices.

## A useful mathematical sanity check

For a continuous driftless price martingale stopped at +8% or -5%, with eventual barrier absorption and no fees/dividends, let p be the probability of the upper barrier. Optional stopping gives 0 = .08*p - .05*(1-p), hence p=5/13, about 38.46%, and stop frequency about 61.54%. These assumptions are deliberately idealized. A finite timeout adds its conditional payoff; discrete jumps can overshoot barriers; equity risk premia and conditional drift change the result.

The lesson is not a market probability forecast. It is a falsifier of the inference 'more than half the trades stop out, therefore the entry has no edge'. Conversely, a stop-avoidance classifier can choose quiet timeouts with little upside and still look accurate. This is why the model reports the whole payoff distribution and tests estimated net expectancy against frequency, price-only and exposure-matched controls.

## Horizon alignment before indicator sophistication

A short-horizon reversal, a multi-week continuation and a multi-year value investment are different decisions. A 21-session barrier classifier cannot be silently reused as a 63-session trend model. A fixed profit cap may remove the positive tail that a trend strategy needs. An oscillator that identifies a bounce can be useful without identifying the start of a durable fundamental rerating. Combine components only when their information cutoffs, targets and holding clocks agree.

The registered 63-session trailing/no-profit-cap arm tests payoff asymmetry rather than assuming it helps. The slow-momentum controls test whether the expensive entry oscillator contributes anything beyond a simple, interpretable persistence signal. A null finding is useful: keep the simpler representation when the extra component fails its incremental test.

## What public institutional research actually supports

- Moskowitz, Ooi and Pedersen, Time Series Momentum (2012), AQR author research page: documents persistence using instruments' own past returns in 58 futures/forwards across asset classes. This motivates a slow-trend comparator, not evidence that a 2D/3D equity crossover has alpha. https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- Garleanu and Pedersen, Dynamic Trading With Predictable Returns and Transaction Costs (2013), AQR author research page: jointly considers expected-return dynamics, risk/correlation and trading costs. The conceptual implication is to trade toward an economically justified target rather than react equally to every signal update. This experiment does not claim to implement the paper's optimal control solution. https://www.aqr.com/Insights/Research/Journal-Article/Dynamic-Trading-With-Predictable-Returns-and-Transactions-Costs
- Kaminski and Lo, When Do Stop-Loss Rules Stop Losses? (MIT author manuscript record): stopping rules can add or subtract value depending on the return process and policy. Its index-futures findings are not a universal endorsement of a 5% stock stop. https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee
- Bessembinder, Do Stocks Outperform Treasury Bills? (2018), ASU author research record: the historical distribution of individual stock outcomes is strongly positively skewed and aggregate wealth creation concentrated. This motivates measuring missed winners and uncapped payoff tails, not an assumption that every losing stock should be held indefinitely. https://asu.elsevierpure.com/en/publications/do-stocks-outperform-treasury-bills/
- Cederburg et al., On the Performance of Volatility-Managed Portfolios (2020), University of Arizona research record: reports important limits to the robustness and real-time implementation benefits of volatility-managed equity strategies. Our risk overlays must demonstrate their own utility rather than inherit the favorable result of another sample. https://experts.arizona.edu/en/publications/on-the-performance-of-volatility-managed-portfolios/
- AQR, Trading Costs (2018), author research page: large institutional execution data show why costs/capacity are an empirical part of strategy design. The paper's trading-cost estimates are not imported as our own stock fills. https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs

These are inspected primary-source summaries/abstracts, not a claim of exhaustive access to proprietary institutional systems or a full reproduction of every paper. Prior internal G-T2X and phase2 failures remain independent counterevidence. What changes a decision is incremental, timely, executable information, not the reputation or number of indicators supporting it.

## Consumer boundary

A research context can describe the opportunity family, observed tier, horizon, volatility scale, conditional outcome estimates, missing inputs and evidence maturity. It must preserve the entry engine's existing verdict and return may_rank=false, may_size=false, may_trade=false until the existing scientific and production owners separately qualify stronger use. No component can manufacture a good opportunity out of another component's confidence.
