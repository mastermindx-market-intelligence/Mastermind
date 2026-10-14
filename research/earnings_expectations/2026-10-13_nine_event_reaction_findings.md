# Nine-event earnings reaction casebook — observed returns, not validated alpha

**As of:** 2026-10-13. **Scope:** Alphabet, Microsoft and Amazon earnings releases from January–July 2026. **Status:** reproducible read-only research evidence; not a forecast, production event engine, live alert or trade signal.

## Reproduction

From `research/earnings_expectations/`:

```bash
python3 -m pytest -q test_reaction_replay.py test_replay_casebook.py test_management_guidance_cases.py
python3 replay_casebook.py --format markdown
python3 replay_casebook.py --format json
```

Local: **62/62 tests passed** (Python 3.13, pytest 9). Implementation, tests and all nine public-source input packets were individually read back from GitHub with byte-matching Git blob hashes. This demonstrates reproducible arithmetic and typed input handling; not any production acceptance or predictive backtest.

For each event `R_issuer = adj_close(first affected regular session) / adj_close(last unaffected regular session) − 1`, likewise SPY and the named sector ETF. Report issuer minus SPY / sector in **percentage points**. Source inputs and public-release witness URLs reside in the nine `sourced_event_packets/*.json` files.

## Observed release-window outcomes

| Release → affected session | Issuer | Cloud growth YoY | Issuer one-session | vs SPY (pp) | vs sector (pp) |
|---|---|---:|---:|---:|---:|
| Microsoft Jan 28 → Jan 29 | MSFT | Azure 39% | −9.99% | −9.79 | −8.41 XLK |
| Alphabet Feb 4 → Feb 5 | GOOGL | Google Cloud 48% | −0.54% | +0.71 | −0.03 XLC |
| Amazon Feb 5 → Feb 6 | AMZN | AWS 24% | −5.55% | −7.47 | −5.97 XLY |
| Alphabet Apr 29 → Apr 30 | GOOGL | Google Cloud 63% | +9.96% | +8.96 | +8.90 XLC |
| Microsoft Apr 29 → Apr 30 | MSFT | Azure 40% | −3.93% | −4.93 | −4.17 XLK |
| Amazon Apr 29 → Apr 30 | AMZN | AWS 28% | +0.77% | −0.23 | −0.53 XLY |
| Alphabet Jul 22 → Jul 23 | GOOGL | Google Cloud 82% | −7.13% | −5.90 | −3.63 XLC |
| Microsoft Jul 29 → Jul 30 | MSFT | Azure 43% | +15.51% | +13.83 | +10.01 XLK |
| Amazon Jul 30 → Jul 31 | AMZN | AWS 37% | +15.32% | +14.60 | +12.03 XLY |

Cloud operating growth and stock-price sign clearly do not map one-to-one. Per-issuer sequential Apr→Jul cloud YoY growth / issuer next-day stock return changed:
- **Alphabet:** 63%→82% cloud while +9.96%→−7.13% stock, a **−17.09 percentage-point** reaction swing.
- **Microsoft:** 40%→43% Azure while −3.93%→+15.51% stock, a **+19.44-point** reaction swing.
- **Amazon:** 28%→37% AWS while +0.77%→+15.32% stock, a **+14.55-point** reaction swing.

All three published after the Apr 29 close: the following Apr 30 SPY return (+1.00%) is shared background context, not a controlled experiment. Microsoft Azure +40% in April reportedly matched a contemporaneous +40% analyst estimate while Google Cloud +63% beat a reported +50.1% expectation; Amazon AWS +28% beat a reported +25%. These estimates were reported by financial news at the time, **not** admitted historical point-in-time source-owner consensus.

## Management guidance is a separate expectation channel: a real Amazon comparison

Amazon's own prior-quarter management guidance provides a public, fixed-fiscal-target expectation baseline **distinct from sell-side consensus**:

| Actual fiscal target | Prior management sales range | Midpoint | Reported sales | Above midpoint | Above upper bound | Post-report stock move |
|---|---:|---:|---:|---:|---:|---:|
| 2026 Q1 (guided Feb 5) | $173.5–178.5B | $176.0B | $181.5B | +$5.5B (+3.125%) | +$3.0B | +0.77% |
| 2026 Q2 (guided Apr 29) | $194.0–199.0B | $196.5B | $200.6B | +$4.1B (+2.0865%) | +$1.6B | +15.32% |

Source evidence: [2025 Q4 guidance for 2026 Q1](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Fourth-Quarter-Results/default.aspx), [2026 Q1 actual and guidance for Q2](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000012/amzn-20260331xex991.htm), [2026 Q2 actual](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000024/amzn-20260630xex991.htm). The prior guidance and later actuals concern the same issuer, metric, unit, currency and fiscal target; the guide's approximate FX assumptions differed (+180bp vs −10bp impact on revenue growth), so this is reported-sales exceedance rather than an ex-FX organic surprise.

The smaller management-guide exceedance in Q2 accompanied a much larger share-price reaction. This is **direct counterevidence against the simplistic claim that larger headline guide beats mechanically cause larger stock jumps**. It is not causal evidence of expectations ratcheting; market consensus, forward guidance, capex, AWS mix/margins, rates and positioning remain unmeasured. The original source values and explicit basis are preserved in `amazon_management_guidance_cases.json`; `test_management_guidance_cases.py` tests the arithmetic and joins to the two corresponding stock events. No normalized issuer-guidance production owner has been replaced.

## Evidence and limitations

1. Each event has a company earnings report/IR source and a dated after-close wire or press-release reprint. An unambiguous *first* public release second was **not** established; the replay uses the explicit weaker `AFTER_CLOSE_WINDOW_CORROBORATED` class, with `first_published_utc = null`, rather than treating SEC filing acceptance as the source time. Winter trading clocks are 14:30–21:00 UTC, spring/summer 13:30–20:00 UTC.
2. Adjusted closes are fixed **retrospective** Yahoo Finance observations for issuer, SPY and XLC/XLK/XLY; providers may later restate adjusted history for corporate actions. The two-bar packets permit only first affected close-to-close return; H5/H20 drift is `INSUFFICIENT_FUTURE_SESSIONS`, never zero. They are not an execution-cost-aware tape.
3. Sector ETFs may own the issuer, and simple issuer-minus-SPY/ETF differences are neither beta-neutral, hedged, causal, nor ex-issuer. They do not isolate independent surprise, valuation, rates, flows or intraday price discovery.
4. Three megacap AI-cloud issuers and nine hand-selected events are **not a representative predictive validation sample**. No actual time-matched sell-side estimate vintages have been admitted. Price reactions reveal neither a unique buy-side expectation nor recency-bias causation. No ranking, sizing, Prophet influence or market-trading authority follows from this result.

## Primary/public evidence links

- Alphabet company [Q4 2025](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000012/googexhibit991q42025.htm), [Q1 2026](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000043/googexhibit991q12026.htm), [Q2 2026](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm).
- Microsoft investor earnings [FY26 Q2](https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q2/press-release-webcast), [Q3](https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q3/press-release-webcast), [Q4](https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q4/press-release-webcast).
- Amazon [Q4 2025](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Fourth-Quarter-Results/default.aspx), [Q1 2026](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000012/amzn-20260331xex991.htm), [Q2 2026](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Second-Quarter-Results/default.aspx).
- Time witnesses include [Alphabet Q4 Feb 4 4:05 pm EST](https://www.marketscreener.com/news/alphabet-2025-q4-earnings-press-release-ce7e5adad089f622), [Microsoft FY26 Q2 Jan 28 4:07 pm EST](https://www.marketscreener.com/news/microsoft-earnings-press-release-available-on-investor-relations-website-ce7e5bded981f427), [Amazon Feb 5 4:01 pm EST](https://www.nasdaq.com/press-release/amazoncom-announces-fourth-quarter-results-2026-02-05). Additional April/July witness URLs are recorded beside each event's two-day bars.
- Historical closing price sources: `https://finance.yahoo.com/quote/<ticker>/history/` for GOOGL, MSFT, AMZN, SPY, XLC, XLK, XLY, recorded per input packet. Contemporaneous April financial expectation reporting: [Reuters](https://www.investing.com/news/stock-market-news/microsofts-cloud-revenue-growth-disappoints-investors-shares-drop-2-4647241).

## Next scientific / product acceptance

The reproducible **descriptive nine-event casebook is delivered**. The binding scientific dependency is the existing C19 MAS-271/Alpha SRC-A1/EXP-1 owner certifying one rights-bearing, issuer+fiscal-period+metric-matched, timestamp-valid **two-vintage EPS/revenue consensus** pair, or a typed `UNESTIMABLE` refusal. Once supplied, join prior guidance, actuals, forecast revisions, estimated forward economics and a representative pre-registered B2 vs C1 prediction test with a chronological holdout. Reuse the existing Earnings Event / market incorporation / Terminal consumer owners; no second event database or independent belief score plane.
