# Route and context map

Only transitions directly observed during Run 01 are recorded here.

| From | Action | To | What persisted | What did not transfer / changed |
|---|---|---|---|---|
| Supplied dashboard UUID | Global-search NVDA | `/company/NasdaqGS-NVDA/` | Authentication and global shell | Dashboard portfolio state was not represented in the company URL. |
| NVDA Overview | Financials / Estimates / Ownership / IR sibling tabs | Company-scoped routes | Company, quote header, next-event context, global shell | Surface-specific selections changed. |
| NVDA Estimates | Global Charting | `/fundamental-charting/` | Authentication only; Charting later remembered its own prior NVDA selection | Estimate metric, selected estimate tab, period, and forecast series did not transfer. |
| Global Charting | Leave and return later | `/fundamental-charting/` | Charting's manually added NVDA context persisted independently | Current company context from AMZN/JPM did not overwrite it. |
| Query with NVDA + `AI infrastructure` | Click Q1 2027 transcript hit | NVDA IR event in new tab | Company, event identity, query text, result index, highlighted match | Search result list remained in the originating tab rather than becoming event state. |
| Transcript highlight | Click sentence | Same event + audio | Event, company, match, speaker context | Audio time changed to the matching location and began/continued playback. |
| Transcript | Report → Slides | Same event document workspace | Company, event, audio, left event list | Selected document mode and page/zoom changed. |
| NVDA Owner Mode | Global-search QUIK | QUIK Overview | Owner Mode setting persisted | Company-specific data changed; mode was later restored off. |
| AMZN Segments & KPIs | Custom Metrics tab | AMZN custom-metric route | Company, period, currency/scale controls | As-reported mode was disabled for custom metrics. |
| AMZN custom metric row | Select checkbox | Inline chart + table | Formula result, period, company, metric identity | No transfer to a new route was needed. |
| AMZN custom metric | Full reload | Same custom-metric route | Metric eventually reappeared and remained company-specific | First post-reload read was temporarily empty during hydration. |
| AMZN custom metric | Global Charting | `/fundamental-charting/` | Charting's own saved company set | Custom metric was undiscoverable. |
| AMZN custom metric | Screener metric search | `/screener/` | Authentication | Exact custom metric was undiscoverable; standard catalog remained. |
| AMZN custom metric | NVDA Add Existing Metric | NVDA custom-metric route | Authentication and NVDA company context | Search returned `No metrics found`; AMZN metric did not transfer. |
| NVDA Holders | Click holder name | Same holder table | Table state | No holder-detail transition occurred; holder name was not a link. |
| NVDA Holders | Click filing provenance control | Embedded institutional filing dialog | Company and holder row context | No investor profile context; the document viewer opened instead. |
| Fund Letters filtered to BlackRock | Open a letter | Letter detail route | Investor, fund, period, document identity | Global letter-list filters became route-specific detail state. |
| BlackRock letter | Click investor name | Investor detail route | BlackRock identity and letter corpus | Ownership-table filing context did not link directly into this profile. |
| Empty dashboard | Add visible NVDA picker result | Portfolio row | NVIDIA entity and notification eligibility | Saved listing changed unexpectedly from displayed U.S. entity to `BUL:NVD`. |
| Dashboard row | Notifications | Notification dialog (`All`, `Untitled`) | Dashboard entity projection | Portfolio metrics and shares did not appear. |
| Dashboard row | Dashboard News | News tab | Dashboard entity projection | News included more event types and `Notable Update` rows than Notifications. |
| Any inspected active company surface | Search navigation/live DOM for Copilot | No transition | Authentication and current surface | No Copilot entry point or prompt context was exposed. |

## Context boundaries

- Company sibling tabs are the strongest context-preserving family.
- Query, Charting, dashboard, fund letters, and investor profiles are independent workspaces with their own state.
- Exact document-search deep links carry query terms and result index into event context.
- A holder's filing receipt is directly traversable, but holder name → investor profile is not; the investor profile was reached through Fund Letters.
- Bottom `Untitled` tabs belong to the persistent Query workspace. Creating a new tab there produced a document-search tab, not a Copilot conversation.
