# Interaction ledger

Ordered factual account of the authenticated workflows tested in Fiscal.ai. Observation IDs link to `observations.jsonl` and focused screenshots.

| Step | Surface / action | Result | Evidence |
|---:|---|---|---|
| 1 | Open supplied authenticated dashboard | Empty portfolio dashboard; global product navigation visible. | OBS-001 |
| 2 | Global-search NVDA and open company | NVDA context, next-earnings link, delayed quote marker, and sibling tabs loaded. | OBS-001 |
| 3 | Open annual Financials | Company context persisted; standardized/as-reported, period, scale, common-size, template, and statement controls appeared. | OBS-002 |
| 4 | Open Revenue Estimates | Future columns were marked `(E)`, history `(A)`; mean/median/high/low/std-dev/count and beat/miss rows appeared. | OBS-003 |
| 5 | Open EPS then Price Targets | EPS used the same estimate grammar; price targets exposed high/consensus/low/actual and rating counts. | OBS-004 |
| 6 | Leave Estimates for global Charting | NVDA estimate context did not transfer. Adding NVDA manually still yielded no `Consensus` metric and no estimate-series match. | OBS-031 |
| 7 | Open Query / Cross-Document Search, add NVDA, search `AI infrastructure` | 98 of 116 documents shown; Equity Research, Filings, and Investor Relations results were visually distinguished. | OBS-005 |
| 8 | Open Q1 2027 transcript hit | A new event tab opened with `searchTerms` and `searchResultIndex`; seven highlights were present at the exact transcript context. | OBS-006 |
| 9 | Click a highlighted transcript sentence | Audio sought from 0:00 to the matching location; speaker names/roles and the Q&A boundary were visible. | OBS-007 |
| 10 | Switch the same event to Report and Slides | Event/company selection persisted; Quartr report and 17-page slide viewer coexisted with audio and AI Summary/Custom Prompt controls. | OBS-008 |
| 11 | Search the event workspace for a visible quarter-over-quarter message comparison | No dedicated comparison workflow or matching comparison copy was found. | OBS-008 |
| 12 | Enable Owner Mode on NVDA | Standard company fields remained; an additional Business Owner Mode projection appeared after hydration. | OBS-009 |
| 13 | Move to QUIK while Owner Mode remained enabled | Mode persisted across company navigation and added the same owner projection; core company data later hydrated. | OBS-010 |
| 14 | Disable Owner Mode | The Business Owner Mode projection disappeared; the setting was left off. | OBS-010 |
| 15 | Open QUIK Revenue Estimates | Header and controls rendered, but no estimate chart or table appeared after bounded waiting. | OBS-011 |
| 16 | Open QUIK Financials and switch to As Reported | Route gained `templateType=as-reported`; row labels changed to issuer wording and many cells remained honest em-dashes. | OBS-012 |
| 17 | Open AMZN Segments & KPIs | Long annual segment, geography, EBIT, CapEx, and KPI histories were present. | OBS-013 |
| 18 | Create `MMX CapEx to Revenue` from `Capital Expenditure / Total Revenues` | Metric was saved as company-specific, Ratio format, and returned negative ratios because CapEx is stored as a cash outflow. | OBS-014 |
| 19 | Select the custom-metric row | Fiscal generated an inline chart labeled `User Generated` with annual values and summary statistics. | OBS-015 |
| 20 | Add AMZN to global Charting and search the metric | Charting retained its own prior NVDA context, accepted AMZN separately, but returned no custom-metric result. | OBS-031 |
| 21 | Search the metric in Screener criteria | The selector fell back to a broad standard catalog; no exact `MMX CapEx to Revenue` option appeared. | OBS-016 |
| 22 | Reload AMZN Custom Metrics | The table was initially empty, then the metric hydrated and reappeared without another action. | OBS-029 |
| 23 | Open NVDA Custom Metrics → Add Existing Metric; search AMZN metric | `No metrics found`; the company-specific metric was not reusable on NVDA. | OBS-030 |
| 24 | Open NVDA Ownership → Insiders | 17 insiders with role, shares, market value, and ownership percentage. | OBS-017 |
| 25 | Switch to Holders | 5,495 institutional holders with changes, values, report dates, and filing dates. | OBS-018 |
| 26 | Open BlackRock holding source | An embedded 1,661-page institutional-ownership filing viewer opened with a new-tab affordance. | OBS-019 |
| 27 | Open Fund Letters and filter Investor = BlackRock | 54 letters across nine funds and multiple letter types were returned. | OBS-020 |
| 28 | Open a BlackRock letter | Detail included performance table, themes, extracted summary, and source-PDF link. | OBS-021 |
| 29 | Follow BlackRock from letter to investor detail | Investor profile exposed book state, mentions, latest view, position, date, funds, letters, and NVDA as long/bullish. | OBS-022 |
| 30 | Open Notifications before adding dashboard companies | Explicit empty state said companies must be added to the dashboard. | OBS-023 |
| 31 | Add the visible NVDA result to supplied dashboard | Saved row became NVIDIA on `BUL:NVD`, not the displayed U.S. listing. No further companies were added. | OBS-024 |
| 32 | Reopen Notifications | The feed populated with dated NVDA News and Morningstar items plus `Measurable Impact` labels. | OBS-025 |
| 33 | Open dashboard News | News exposed a broader typed/importance-filtered event stream and factual summaries; it was not identical to Notifications. | OBS-026 |
| 34 | Open JPM annual Income Statement and Balance Sheet | Bank-specific presentation surfaced net interest income, provision for credit losses, deposits, loans, trading assets/liabilities, and allowances. | OBS-027, OBS-028 |
| 35 | Inspect authenticated navigation and live controls for Copilot | No Copilot route, label, prompt box, or actionable control appeared; no prompt was submitted. | OBS-032 |

No emails, SMS, pushes, brokerage connections, network inspection, private endpoints, or access-control workarounds were used.
