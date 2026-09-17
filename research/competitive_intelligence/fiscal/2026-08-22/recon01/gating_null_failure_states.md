# Gating, null, and failure states

Only states directly observed during Run 01 are recorded here. `Unavailable on trial`, `data unavailable`, `zero observations`, and `UI failure` remain distinct.

| State | Surface | Observed semantics | Classification | Evidence |
|---|---|---|---|---|
| Overview shell with em-dashes, then populated values | NVDA/QUIK Overview | Company statistic placeholders later hydrated into values without another action. | Loading state; not data absence | OBS-001, OBS-010 |
| QUIK Revenue Estimates controls with no chart/table | `/estimates/revenue/` | Metric tabs and formatting controls rendered; no explanatory text, rows, or series followed after bounded waiting. | Data unavailable or zero-covered observations; UI does not distinguish | OBS-011 |
| Em-dash financial cells | QUIK annual statements | Some metrics/periods remained `—` while adjacent values existed. | Cell-level data absence | OBS-012 |
| Standardized → As Reported | QUIK Financials | Route gained `templateType=as-reported`; issuer labels changed and more granular sparse rows appeared. | Alternate source/presentation state; no entitlement gate | OBS-012 |
| Source value audit control | NVDA holders | `View source filing for Blackrock, Inc.` opened an embedded 1,661-page filing viewer. | Available provenance | OBS-019 |
| Notification empty state | Dashboard notifications | Explicit instruction: add companies to dashboard to start receiving notifications. | Zero watched entities, not entitlement denial | OBS-023 |
| Populated Notifications after one dashboard addition | Notification dialog | Dated News and Morningstar items appeared, with impact labels. | Available after prerequisite state | OBS-025 |
| Dashboard picker listing mismatch | Supplied dashboard | Visible U.S. NVIDIA entity selection saved as `BUL:NVD`; notifications still projected NVIDIA content. | Context-selection/UI failure; cleanup pending confirmation | OBS-024, OBS-025 |
| Custom metric missing immediately after reload, then present | AMZN Custom Metrics | First read showed only Add buttons; later hydration restored the saved row. | Loading state; not persistence failure | OBS-029 |
| Exact custom metric absent from Charting | Global Charting | Search returned no match even after AMZN was added. | Cross-surface reuse unavailable in tested path | OBS-031 |
| Exact custom metric absent from Screener | Screener criteria | Unknown query fell back to a broad standard catalog; no exact custom result. | Cross-surface reuse unavailable in tested path | OBS-016 |
| `No metrics found` for AMZN metric on NVDA | Add Existing Metric | Dialog explicitly returned no metric match. | Company-specific scope, not a paywall | OBS-030 |
| Copilot not present | Global nav, company surfaces, Query, Charting, Screener, settings menu, event workspace | No labeled route, prompt box, or live control. The distinct IR `Custom Prompt` panel was not treated as Copilot. | Feature unavailable or not exposed; entitlement cause unproven | OBS-032 |
| No quarter-over-quarter comparison found | NVDA IR event | Transcript, report, slides, audio and search were available, but no dedicated message-comparison control/copy was found. | Feature absent in tested event; not entitlement denial | OBS-008 |
| No explicit paywall/upgrade dialog | All tested lanes | No blocked click produced an upgrade modal or plan label. | No directly observed entitlement denial | Entire run |

## Important non-equivalences

- An empty estimate surface is not proof that estimates do not exist elsewhere; QUIK Overview still showed an earnings estimate summary.
- A temporarily empty custom-metric table is not a persistence failure; delayed hydration restored the metric.
- Copilot absence is not proof that the plan forbids Copilot. The account exposed no entry point, and the reason was not named.
- The Bulgarian-listing save is not treated as a user choice. The selected result visibly presented NVIDIA's U.S. entity before the saved row resolved to `BUL:NVD`.
