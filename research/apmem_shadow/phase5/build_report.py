"""Render the research report from retained aggregate results, never invented cells."""
from pathlib import Path
import json
import hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parent
p=pd.read_csv(ROOT/'primary_results/portfolio_metrics.csv')
f=pd.read_csv(ROOT/'followup_results/policy_metrics.csv')
n=pd.read_csv(ROOT/'native_comparison_results/portfolio_metrics.csv')
c=pd.read_csv(ROOT/'credit_results/portfolio_metrics.csv')
q=pd.read_csv(ROOT/'prediction_results/prediction_scores.csv')
a=pd.read_csv(ROOT/'audit_results/information_decomposition.csv')


def row(df,**filters):
    x=df
    for k,v in filters.items():x=x[x[k].eq(v)]
    if len(x)!=1:raise ValueError('Ambiguous report cell '+str(filters))
    return x.iloc[0]


def book_table(items):
    lines=['| Research policy | CAGR | Sharpe | Maximum close drawdown | Mean exposure | Closed trades |',
           '|---|---:|---:|---:|---:|---:|']
    for label,r in items:
        lines.append(f"| {label} | {r.cagr:.2%} | {r.sharpe:.3f} | {r.maximum_drawdown:.2%} | {r.mean_exposure:.2%} | {int(r.closed_trades)} |")
    return '\n'.join(lines)

pre=[('Raw settled grey dot',row(p,segment='pre',phase=0,horizon=21,cost_bp=5,policy='dot')),
 ('Dot + market repair',row(p,segment='pre',phase=0,horizon=21,cost_bp=5,policy='dot_repair')),
 ('Dot + repair + receding new lows',row(f,segment='pre',phase=0,horizon=21,cost_bp=5,policy='declining_low_pressure')),
 ('Dot + repair, continuing-support exit',row(f,segment='pre',phase=0,horizon=21,cost_bp=5,policy='ongoing_repair')),
 ('Remember dot, then wait for repair',row(p,segment='pre',phase=0,horizon=21,cost_bp=5,policy='sequence_repair')),
 ('Native T1 confirmed',row(n,segment='pre',horizon=21,cost_bp=5,policy='t1')),
 ('Native T2',row(n,segment='pre',horizon=21,cost_bp=5,policy='t2'))]
recent=[('Raw settled grey dot',row(p,segment='post',phase=0,horizon=21,cost_bp=5,policy='dot')),
 ('Dot + repair + receding new lows',row(f,segment='post',phase=0,horizon=21,cost_bp=5,policy='declining_low_pressure')),
 ('Native T1 confirmed',row(n,segment='post',horizon=21,cost_bp=5,policy='t1')),
 ('Native T2',row(n,segment='post',horizon=21,cost_bp=5,policy='t2')),
 ('Native T1/T2 union',row(n,segment='post',horizon=21,cost_bp=5,policy='union')),
 ('Dot, VIX must not be rising',row(p,segment='post',phase=0,horizon=21,cost_bp=5,policy='dot_vix_not_rising'))]
early=[('Raw dot, phase0',row(c,era='2001_2006',phase=0,horizon=21,lag=0,cost_bp=5,policy='dot')),
 ('Dot + repair + receding new lows, phase0',row(c,era='2001_2006',phase=0,horizon=21,lag=0,cost_bp=5,policy='declining_low_pressure')),
 ('Raw dot, phase2',row(c,era='2001_2006',phase=2,horizon=21,lag=0,cost_bp=5,policy='dot')),
 ('Dot + repair + receding new lows, phase2',row(c,era='2001_2006',phase=2,horizon=21,lag=0,cost_bp=5,policy='declining_low_pressure'))]

report='''# Independent sector-recovery, grey-dot and native-entry research

## Executive finding

This is an executed independent market-data study and implementation, not a delegation to the local T3 team. The strongest retained direction is **conditional use of early timing in observable market repair**, not a universal replacement of T1/T2 and not a rule requiring every fear/credit indicator to become calm. Receding new-low pressure can add useful descriptive structure; however its economic benefit varies by era and three-day bar alignment. The full study does not establish a robust all-objective trading winner or a calibrated probability of an exact bottom.

A particularly useful distinction is now measured: a context that helps an early grey-dot candidate need not help a later confirmed T1/T2 candidate. The same filter can be redundant or detrimental after confirmation. Context belongs to the particular decision and horizon, not a universal agreement-count score.

## What was held fixed and what was exploratory

The original protocol was committed before new payoff comparisons. It used nine original sector ETFs: XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV and XLY, plus SPY, VIX, VVIX and VIX3M. No sector was chosen for its return. Technical inputs use the incumbent Yahoo split-adjusted price-only close; outcome inputs use its total-return-adjusted close. Current vendor vintages, retrospective revisions, historical sector reconstitutions and ETF implementation remain limitations. The price series is not a raw-share corporate-action settlement ledger.

The local team's reserved January2020-May2023 interval was removed before indicators, labels or fits. Features restart independently on June1,2023; a504-observation warmup makes the later evaluation **June5,2025-November9,2026**, only360 sessions. The primary earlier window is **January3,2007-December31,2019**,3272 sessions. The later2001-2006 falsifier is explicitly additional retrospective evidence. None is called an untouched holdout to the wider research program.

The native grey-dot math is pinned to Terminal82cb8cbf799fc3a91c9bee0f11a4db718fde68eb. It uses the D-line oversold memory over eight3D bars, one rising2B RSI-MACD histogram observation, and known-time joins. Only settled3D observations are tested. The stored-history anchor is disclosed, and all three fixed phase offsets are retained; the experiment does not claim to recover every true listing anchor or live provisional print.

Market repair means positive equal-sector5-session return plus increasing participation above20-session means. Receding new-low pressure means the average share of these nine sector ETFs making20-session closing lows over the latest5 days is below the preceding5-day window. This is **cross-sector ETF participation, not within-sector stock-constituent breadth**. A recent broad washout means at least five of nine sectors were5% below their63-session highs at some point in the preceding21 sessions.

Entry fills are **next-session CLOSE**, not next-open or signal-close. Primary costs are5bp each way;20bp and an extra entry-session delay are separate sensitivities. Positions are unlevered; each sector has an initially equal capital sleeve with no idle-cash redistribution, pyramiding, stop-loss or profit-cap optimization. Unused cash earns0%. Maximum drawdown is close-marked, not a continuous intraday bound. The initial one-third and50/50 mixture experiments have their own disclosed portfolio construction.

The original15-policy, horizon, phase and cost experiment has242 account rows. Its48 paired mean-return tests use63-session calendar blocks and Holm correction: **none passed the complete family correction**. Follow-ups are labeled outcome-guided. The large number of dependent account variants is not an independent sample size or a license to report only the best row.

## Primary older-window results: same clocks and fees,21-session holding limit

'''+book_table(pre)+'''

The repair subset's slightly higher CAGR is not evidence of a larger mean return: its paired mean daily return difference versus the raw-dot account was slightly negative, while realized risk was lower. Compounding and loss reduction can improve the growth path without creating directional alpha.

For the63-session limit, raw-dot CAGR/Sharpe/drawdown were4.38%/.403/-40.74%; repair was5.10%/.600/-23.62%; receding-new-low pressure was5.84%/.733/-18.75%. The continuing-support policy was3.20%/.663/-8.90%, with much lower exposure. Its exit occurs at the next close after two sessions of deteriorating common support; it is not a price stop or a promise to exit before a loss.

### Is this just more cash?

A hindsight static raw-dot/cash mixture matched to the21-session repair account's mean exposure earned2.61%,Sharpe.431,drawdown-18.43%, compared with repair3.72%,.673,-13.32%. That diagnostic indicates that simple exposure reduction does not explain every older-window difference. It does not establish implementable selection skill: the match uses hindsight, some later comparisons favor the static control on drawdown, and the primary return test remains null.

The receding-new-low arm's exposure-matched repair/cash control earned2.84% versus3.76% for the candidate in the same older21-session comparison. At the63-session limit the figures were4.35% versus5.84%. Those are descriptive point estimates, not significance-certified improvements. Full phase, cost, delay, exposure and calendar-placebo rows remain in the evidence.

Leave-one-sector-out repair produced similar older-window results:21-session CAGR3.55%,Sharpe.649,drawdown-13.32%. The context is therefore not solely the focal ETF being included in its own repair measure. It is still not proof of sector-specific selection.

## Recent window and the actual native T1/T2 comparison

'''+book_table(recent)+'''

The same-panel comparison gives **no basis for universally replacing T1/T2 with the grey dot**. Native T2 was stronger in this recent sample, whereas the raw grey dot and repair-conditioned variants were stronger on several older21-session measures. T1 was much more selective and carried far less exposure. At the older63-session horizon, T1 Sharpe was.675 with-7.54% drawdown at22.92% mean exposure, demonstrating why raw return alone is not a sufficient replacement criterion.

The native comparison reused the previously qualified phase3 last-marker projection and necessary-condition sieve, unchanged, against Macro6bbc4b0fc694c847077661ff5bf4c19ea41e4e81. Ninety sampled exact native decision comparisons matched, including three native-T1-tier and five native-T2-tier cases. Eighteen instrument/segment replays completed with no unavailable native rows. Confirmed T1 is separated from forming T1; the historical peer-washout waiver remains disabled because its contemporaneous input was not qualified. These are fixed research representations, not proof of identical historical live deployments or individual-stock performance.

## Earlier-era falsifier: why the promising row is not a proven winner

'''+book_table(early)+'''

The2001-2006 episode weakens a universal recovery-filter story. The receding-pressure candidate reduced losses in some alignments but lost money in phase2. Continuing-support exits also lost money in parts of that era. We did not delete the adverse era, select the most favorable phase, retune thresholds or rename the failing rule as a new discovery.

The appropriate decision is to keep the mechanism as a research candidate and preserve more than one entry representation. Historical bar alignment materially affects results, so live promotion requires exact deployed source/anchor identity and separately frozen forward testing.

## Fear, credit and simple sector leadership did not supply an automatic rescue

A non-rising-VIX requirement cut the recent21-session raw-dot CAGR from6.00% to0.99%. Requiring non-rising VVIX or both volatility means to ease also removed substantial upside. Those results do not mean fear information is useless; they reject the tested universal veto construction.

A separate high-yield credit-spread hypothesis was tested on the incumbent FRED/ICE BofA OAS history, with a two-equity-session observation delay and fixed one/five-session sensitivities. Missing data stayed missing. A delay is not proof of historical publication availability; current-vintage and licensing boundaries remain. The credit-not-rising and credit-easing gates also removed too many profitable opportunities in several samples. They were not adopted as a universal fix.

Unconditional monthly top-three sector momentum earned7.80% before2020 but only1.97% in the later window; the trend-qualified version lost1.86% annualized recently. A distinct recovery-laggards/continuation-leaders router looked excellent recently but was dangerous historically: the21-session router returned15.71% recently with only eleven closed trades, yet its older maximum drawdown was about60.17%. There were only four recent recovery entries. That is a counterexample to promoting an attractive recent regime narrative.

A fixed half-core/half-repair mixture can change the tradeoff without discovering a magical combination. For the broad equal-trend core, the older21-session repair mixture returned4.31%,Sharpe.703,drawdown-10.32%, versus half-core/cash2.77%,.561,-9.50%. Recently the repair mixture returned3.99%,.959,-2.96%, while the raw-dot mixture returned4.99%,1.027,-2.94%. Mixture weights were not optimized; higher return than holding cash is not, by itself, alpha.

## What the probability models actually learned

Four fixed chronological models were compared on423 common issued grey-dot events across212 dates. Training labels had to end strictly before each prediction date; preprocessing was training-only and fits refreshed on a fixed63-session cadence. No predicted probability was used to rank or size a portfolio.

The tasks were separate: positive net return; outperformance of the equal-sector comparison; preservation of the prior21-session closing low. The models were matured frequency, price/risk features, additional market-repair/VIX context, and a VVIX/term-structure extension.

| Prediction task | Frequency log loss | Price log loss | Context log loss | Volatility-extension log loss |
|---|---:|---:|---:|---:|
'''
for target in ['positive_net','positive_sector_relative','closing_low_holds']:
    vals=[row(q,target=target,model=m).log_loss for m in ['frequency','price','context','vol_extension']]
    report+='| '+target+' | '+' | '.join(f'{x:.6f}' for x in vals)+' |\n'
report+='''
Lower is better. Only the price-model improvement in low preservation passed the separately declared18-contrast family correction, for both log loss and Brier loss. Additional context did not establish incremental predictive superiority, and none of the richer models beat the frequency model on the aggregate positive-return or sector-outperformance loss shown here. The same-date tests equal-weight dates, so their contrasts need not equal differences between event-weighted aggregate cells.

This is not a reliable-live-bottom probability. Low preservation can partly reflect distance from the reference low and the scale of ordinary movement; it is not equivalent to attractive future return. The consumer therefore carries no calibrated entry-probability claim.

## Timing versus sector selection

Older21-session raw-dot event mean net return was0.73%; the repair-plus-receding-pressure subset was1.73%. But its average excess over the equal-sector same-date payoff was only about0.024 percentage points. The improvement is principally consistent with common-market timing, not a demonstrated ability to identify the best sector. In the recent63-session subset the selected-sector increment was negative. These estimates have overlapping windows and small independent date counts.

The actual remaining bottleneck is therefore clearer: an early-turn detector and improving common conditions are not enough to establish durable relative leadership. Individual-stock alpha should not be forced into this stage, but neither should a market-timing effect be advertised as solved sector rotation.

## Decisions from this experiment

- Retain grey dots, confirmed T1/T2 and continuation as distinct candidates; do not replace them universally or assume every dot is an early T2.
- Retain market repair and receding new-low pressure as descriptive, signalfamily-specific research context. Do not multiply their votes into a confidence score.
- Reject the tested universal rising-VIX/VVIX and easing-credit vetoes as default entry rules. Different data or a properly registered conditional model could change that conclusion; these tests do not prove the factors contain no information.
- Do not promote the laggard-recovery router, the most favorable phase, or a recent high-Sharpe row. Historical failures and small recent counts are material.
- Keep volatility prediction separate from expected payoff and structural-low persistence. Earlier APMEM/MEM numerical work is not refitted or relabeled from close-only inputs here; the new research does not pretend that EWMA sizing is the prior OHLC-target model.
- Before capital authority, qualify exact live grey-dot identity, actual constituent breadth, observed source clocks, a finite uninspected forward roster and the particular consumer decision. Adding historical gates until the chart looks good is not that qualification.

## Actual implementation and verification

The source includes native-math replay, time-safe contexts, fixed event/account evaluators, corporate-source manifests, training-only probabilities, calendar controls, cost-funded sector portfolios, early-era/credit falsifiers and a read-only consumer adapter. Sixty-six tests passed in the numerical runtime. Original primary default-account curves remained equal after the optional exit extension to floating-point precision (maximum observed difference4.44e-16). Exact versions and all result/source hashes are retained.

The consumer witness invoked the actual pinned Mastermind entry assessor for all nine ETFs with explicit price/native inputs and current-data defaults disabled. The new context left every incumbent verdict, score and buyability unchanged. The source ended November9 while the expected completed session was November13; all nine observations correctly remained stale research context. Missing VVIX stayed unknown. This is source-level research integration, **not a deployed service, a fresh live signal, a trading instruction or production acceptance**.

No LLM subagent team, independent reviewer, background process, automated collector, account change, live ranking, sizing or order execution is claimed. The principal owns the work. All launched numerical jobs were reconciled as completed; no post-response work is promised.

## Reproduction and scientific boundary

Start with README.md, the frozen protocols and INPUT_MANIFEST.json. Licensed raw histories are not redistributed. A full replay requires the retained private snapshots with exact hashes and native source pins. The portable test suite does not invent them: it explicitly skips the native-private-data class when those fixtures are absent, while running the hermetic mechanics. No skip is counted as an executed native parity test.

The primary48-return-comparison family yielded no corrected rejection. The separately labeled24-test audit yielded three adverse-tail contrasts below its correction threshold, mainly ongoing-support versus longer exposure; those are exploratory and not exposure-neutral causal effects. The18-prediction-test family supported only the price-model low-preservation result. These families do not correct all prior research selection across the entire program.

The source and measured comparison framework are delivered as research. A universally superior strategy remains unproven. The next discriminating evidence is exact deployed-observation accrual and genuinely richer, time-qualified cohort information, not a claimed immediate replacement of the native entry system.

## Primary external context, not evidence of this strategy's profitability

[P1] Cboe VIX FAQ and VVIX methodology/dashboard: VIX is option-implied expected SPX variability; VVIX measures expected variability of forward VIX. These are not individual-security directional probabilities. https://www.cboe.com/tradable_products/vix/faqs and https://www.cboe.com/us/indices/dashboard/VVIX

[P2] Daniel and Moskowitz, Momentum Crashes, NBER Working Paper20439: momentum's poor behavior in some high-volatility rebound states motivates testing, rather than assuming, a single leadership rule. https://www.nber.org/papers/w20439

[P3] Moskowitz and Grinblatt, Do Industries Explain Momentum?: industry-level effects motivate the market/sector/name decomposition, not this short-horizon bottom detector. https://www.aqr.com/Insights/Research/Journal-Article/Do-Industries-Explain-Momentum

[P4] FRED, ICE BofA US High Yield Index Option-Adjusted Spread, BAMLH0A0HYM2: definition and observation convention. Our analysis uses the pre-existing private snapshot, not a new redistributed data download. https://fred.stlouisfed.org/series/BAMLH0A0HYM2

[P5] Federal Reserve, Recession Risk and the Excess Bond Premium (April8,2016): distinguishes corporate risk pricing from expected defaults. This OAS test is not an excess-bond-premium model and does not reproduce its recession results. https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html
'''
(ROOT/'RESULTS.md').write_text(report)
print('REPORT_WRITTEN',len(report.encode()),'bytes')
