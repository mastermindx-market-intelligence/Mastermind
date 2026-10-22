# PRODUCT_CENSUS.md - Mastermind portfolio product (W9 census)

Lane `pbr-p1-census` - Root Mastermind#1693 - Orchestrator `pbr-product-ed665c78`.
Source: detached checkout of Mastermind `origin/master` at `230e9a301`. Read-only census; no tracked file was modified.
Convention: `path:line` cites the handler `def` line unless stated otherwise (the route decorator is the line above). "Rendered as" names the DOM id / panel label the page JS actually writes. Anything not directly read is marked UNVERIFIED.

## Summary

1. One FastAPI app (`app/main.py:103`) mounts `app/web.py` (77 routes) and `app/pfolio.py` (`/api/pfolio/*`, 5) plus 14 app-level routes in `app/main.py` = **89 routes: 7 pages, 5 static/file, 77 api (58 GET, 19 mutating)**.
2. There is **no browser login** - every GET (all pages, all read APIs, the SSE chat stream) is anonymous by design (`app/auth.py:13-16`, `app/auth.py:436-438`). The only credential in the process is the operator bearer token (`MASTERMIND_AUTH_TOKEN`) on 19 mutating/LLM paths, plus the `/api/pfolio/*` prefix gate.
3. **The Pro gate is not in this process.** `app/auth.py:132-141` documents an external edge subscription paywall (`{"locked":true,"tier":"anon","required_tier":"pro"}`) and states the edge must not be treated as the gate. No view is Pro-gated in code; an anon/non-Pro caller is served the entire read surface.
4. V1-V4, V6 and part of V7 live in one SPA (`app/static/index.html`, 9,051 lines); Market View, Agenda and the Portfolio Risk Desk are standalone pages. For the product book (`autonomous`) V1/V2/V3/V4/V6 are substantially implemented; **V5 (opportunities) and V7 (operations) are Flagship-bound and unreachable for the product book** (`index.html:6462-6463`).
5. Evidence discipline in the newest paths is genuinely strong: `app/decision_availability.py` + `app/decision_availability_selection.py`, `portfolio/performance_projection.py`, `/api/trades` pending-target projection and `_pendingTruthNoticeHtml` keep independent clocks, explicit `unavailable` states and no-substitution rules (TR1/TR2/TR3 met there).
6. Defects cluster in older display paths: `/api/self_directed` synthesises a $1,000,000 account on error (`app/web.py:2424`), `renderSelfHeader` repeats the fabrication client-side (`index.html:5980`), and `renderAllocation` coerces missing sleeve weights to 0% (`index.html:4507-4509`).
7. `/api/activity` (Brain Log) and `/api/research_papers` (Research gate join) are hardcoded to the **archived flagship** tree `data/portfolio/` (`app/web.py:2947`, `app/web.py:2980`, `app/web.py:1912`); narrative can contradict the displayed book - live TR1 risk.
8. Two GET read paths **mutate state**: `GET /api/self_directed/history` settles queued orders and writes `account.json`/`fills.jsonl` (`portfolio/self_directed.py:741`), and `GET /api/portfolio` triggers paper-transaction WAL recovery (`portfolio/paper_account.py:191`, reached from `app/web.py:1340`).
9. The response cache key is path + canonicalised query only (`app/response_cache.py:72-83`) - never user (there is no user), and book only when the handler takes `portfolio`/`book` in the query. No cross-book merge was found; the residual isolation exposure is that the personal `self_directed` book is anonymous-readable while the equivalent Supabase panel was deliberately closed.
10. Mobile: viewport meta on all 7 pages, 21 breakpoints in the SPA, wide tables are wrapped in `overflow-x:auto`, ZH red=up inversion implemented (`theme.css:71-77`). ZH copy exists **only** in `index.html`; the other four pages are English-only.

## Route table

| Method | Path | Handler (path:line) | Kind | Auth | Cached? | key incl. user? | key incl. book? |
|---|---|---|---|---|---|---|---|
| GET | `/` | `app/web.py:859` `dashboard()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/agenda` | `app/web.py:891` `agenda_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/desk` | `app/web.py:876` `desk_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/market_view` | `app/web.py:882` `market_view_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/portfolio_desk` | `app/web.py:3596` `portfolio_desk_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/research` | `app/web.py:864` `research_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/self` | `app/web.py:870` `self_directed_page()` | page | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/account.js` | `app/web.py:923` `account_js()` | static/file | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/chat.js` | `app/web.py:915` `chat_js()` | static/file | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/research_paper.pdf` | `app/web.py:989` `research_paper_pdf()` | static/file | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/theme.css` | `app/web.py:902` `theme_css()` | static/file | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/theme.js` | `app/web.py:908` `theme_js()` | static/file | open - no login anywhere (auth.py:436-438) | no - not /api/*; HTTP headers only (`_PAGE_CACHE` web.py:845, `_ASSET_CACHE` web.py:851) | no (response_cache.py:72-83) | n/a |
| GET | `/api/activity` | `app/web.py:2931` `api_activity()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/agenda` | `app/web.py:1807` `api_agenda()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/autonomous/run` | `app/main.py:390` `autonomous_run()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/china/run` | `app/main.py:479` `china_run()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/decisions` | `app/web.py:1682` `api_decisions()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/desk/decisions` | `app/web.py:3212` `api_desk_decisions()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/experiments` | `app/web.py:3505` `api_desk_experiments()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/firm-exposure` | `app/web.py:3460` `api_desk_firm_exposure()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/macro-risk` | `app/web.py:3415` `api_desk_macro_risk()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/scorecard` | `app/web.py:3326` `api_desk_scorecard()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/strategist` | `app/web.py:3169` `api_desk_strategist()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/desk/watchlist` | `app/web.py:3282` `api_desk_watchlist()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/distill` | `app/web.py:2611` `api_distill()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/engine_backtest` | `app/web.py:2638` `api_engine_backtest()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/etf/outcomes` | `app/web.py:1833` `api_etf_outcomes()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/etf/run` | `app/main.py:568` `etf_run()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/factor_zoo` | `app/web.py:2652` `api_factor_zoo()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/firm_allocator` | `app/web.py:3475` `api_firm_allocator()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/forward-evaluation` | `app/web.py:1652` `api_forward_evaluation()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/fundamentals` | `app/web.py:2666` `api_fundamentals()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/heavyweight/run` | `app/main.py:435` `heavyweight_run()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/hk/run` | `app/main.py:524` `hk_run()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/interim_marks` | `app/web.py:2625` `api_interim_marks()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/live_marks` | `app/web.py:1054` `api_live_marks()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/macro` | `app/web.py:2834` `api_macro()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/market_view` | `app/web.py:1777` `api_market_view()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/mastermind_ai` | `app/web.py:2687` `api_mastermind_ai()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/mastermind_ai/act_on_nudges` | `app/web.py:2780` `api_mastermind_ai_act_on_nudges()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/mastermind_ai/directive` | `app/web.py:2767` `api_mastermind_ai_directive()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/mastermind_ai/improvements` | `app/web.py:2717` `api_mastermind_ai_improvements()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/mastermind_ai/loop_log` | `app/web.py:2704` `api_mastermind_ai_loop_log()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/mastermind_ai/reflection` | `app/web.py:2730` `api_mastermind_ai_reflection()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/mastermind_ai/run` | `app/web.py:2794` `api_mastermind_ai_run()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/mastermind_ai/settings` | `app/web.py:2755` `api_mastermind_ai_settings()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/outcome_ledger` | `app/web.py:1964` `api_outcome_ledger()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/outcomes` | `app/web.py:2502` `api_outcomes()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/overnight-tape` | `app/web.py:1845` `api_overnight_tape()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/performance` | `app/web.py:1037` `api_performance()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/pfolio/alerts` | `app/pfolio.py:621` `get_alerts()` | api | bearer on authoritative VPS; 403 on serve-only; open on local/dev (auth.py:400-433) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/pfolio/positions` | `app/pfolio.py:416` `get_positions()` | api | bearer on authoritative VPS; 403 on serve-only; open on local/dev (auth.py:400-433) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/pfolio/positions` | `app/pfolio.py:468` `create_position()` | api | bearer on authoritative VPS; 403 on serve-only; open on local/dev (auth.py:400-433) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| DELETE | `/api/pfolio/positions/{position_id}` | `app/pfolio.py:589` `delete_position()` | api | bearer on authoritative VPS; 403 on serve-only; open on local/dev (auth.py:400-433) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| PATCH | `/api/pfolio/positions/{position_id}` | `app/pfolio.py:526` `update_position()` | api | bearer on authoritative VPS; 403 on serve-only; open on local/dev (auth.py:400-433) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/portfolio` | `app/web.py:1269` `api_portfolio()` | api | open - no login anywhere (auth.py:436-438) | yes; `?view=decision_availability` bypasses (response_cache.py:125-131) | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/portfolio_learning` | `app/web.py:2819` `api_portfolio_learning()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/portfolios` | `app/web.py:1625` `api_portfolios()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/posture` | `app/web.py:1755` `api_posture()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/predictions` | `app/web.py:2553` `api_predictions()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/provenance` | `app/web.py:3556` `api_provenance()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/readiness` | `app/web.py:2806` `api_readiness()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/rejections` | `app/web.py:2569` `api_rejections()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/research` | `app/web.py:1859` `api_research()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/research_papers` | `app/web.py:1895` `api_research_papers()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/risk` | `app/web.py:1228` `api_risk()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| GET | `/api/runlog` | `app/web.py:3096` `api_runlog()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/runs` | `app/web.py:3071` `api_runs()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/scheduler` | `app/web.py:3540` `api_scheduler()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/self_directed` | `app/web.py:2409` `api_self_directed()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/self_directed/cancel` | `app/web.py:2492` `api_self_directed_cancel()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/self_directed/history` | `app/web.py:2434` `api_self_directed_history()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/self_directed/order` | `app/web.py:2470` `api_self_directed_order()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/self_directed/quote` | `app/web.py:2460` `api_self_directed_quote()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/self_directed/search` | `app/web.py:2450` `api_self_directed_search()` | api | open - no login anywhere (auth.py:436-438) | no - `_DENY_PREFIXES` (response_cache.py:44-51) | no (response_cache.py:72-83) | no - path+query only |
| POST | `/api/self_directed/thesis` | `app/web.py:2481` `api_self_directed_thesis()` | api | operator bearer + 30/hr (auth.py:179-189, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/shadow_bandit` | `app/web.py:2583` `api_shadow_bandit()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/shadow_books` | `app/web.py:2528` `api_shadow_books()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/student` | `app/web.py:2596` `api_student()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | no - path+query only |
| GET | `/api/trades` | `app/web.py:2229` `api_trades()` | api | open - no login anywhere (auth.py:436-438) | yes when MASTERMIND_RESP_CACHE_TTL>0 | no (response_cache.py:72-83) | YES - `portfolio`/`book` query is in the key |
| POST | `/chat` | `app/main.py:632` `chat()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/chat/history` | `app/main.py:675` `chat_history()` | api | open - no login anywhere (auth.py:436-438) | no - not /api/* | no (response_cache.py:72-83) | no - path+query only |
| GET | `/chat/paper` | `app/main.py:682` `chat_paper()` | api | open - no login anywhere (auth.py:436-438) | no - not /api/* | no (response_cache.py:72-83) | no - path+query only |
| POST | `/daily` | `app/main.py:369` `daily()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/health` | `app/main.py:196` `health()` | api | open (`_OPEN_PATHS` auth.py:158) | no - not /api/* | no (response_cache.py:72-83) | no - path+query only |
| GET | `/ready` | `app/main.py:209` `ready()` | api | open (`_OPEN_PATHS` auth.py:158) | no - not /api/* | no (response_cache.py:72-83) | no - path+query only |
| POST | `/reason` | `app/main.py:243` `reason()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |
| GET | `/regime` | `app/main.py:219` `regime()` | api | open - no login anywhere (auth.py:436-438) | no - not /api/* | no (response_cache.py:72-83) | no - path+query only |
| POST | `/research` | `app/main.py:613` `research()` | api | operator bearer + 8/hr AND 2/min (auth.py:166-176, 440-470) | no - GET-only (response_cache.py:112) | no (response_cache.py:72-83) | no - path+query only |

## Route → API → field → owner

Scope of this table: every field the pages actually read off a JSON response. `Source` is the code that
**produces** the value (server) or the line that **writes** the DOM (client). Panel id / label names the
element rendered into. Null-handling is what the user sees when the field is absent.

### V1 Portfolio overview — `index.html` dashboard

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V1 | `/api/portfolio?portfolio=` | `positions[].ticker` | Positions table col 1 `.pos-ticker` | ECON | `app/web.py:1355-1400`, render `index.html:4756` | row absent → no row |
| V1 | `/api/portfolio` | `positions[].name` / `name_zh` | sub-line under ticker | PRODUCT | `app/web.py:1421` `_attach_security_names`; `index.html:3586` `securityName()` | name omitted (sub-line not drawn) |
| V1 | `/api/live_marks` | `positions[].current_price` | col "Current price" (`curStr`) | ECON | `app/web.py:1148-1160`; merged `index.html:8684-8716` | `'—'` (dash) — correct |
| V1 | `/api/portfolio`+`/api/live_marks` | `positions[].cost_basis` / `avg_cost` | col "Entry" (`entryStr`) | ECON | `app/web.py:1364`, `app/web.py:1155`; `index.html:4745` | `'—'`; pending rows show `est_price` instead |
| V1 | `/api/live_marks` | `positions[].market_value` | weight denominator + P&L | ECON | `app/web.py:1366` / `1152` | `'—'` |
| V1 | `/api/live_marks` | `positions[].weight` | col "Weight" via `pct()` | ECON | `app/web.py:1380` (computed only when valuation basis is `provided_prices`/`cash_only`, `app/web.py:1186-1193`) | `pct(null)` → `'—'` (`index.html:3673`) |
| V1 | `/api/live_marks` | `positions[].unrealized_pnl` / `unrealized_pct` | col "Unrealized" (`pnlCell`) | ECON | `app/web.py:1152-1153`; `index.html:3603` `pnlCell()` | `'—'`, no colour class |
| V1 | `/api/live_marks` | `positions[].quote_source` / `quote_as_of` / `quote_is_live` / `quote_stale_days` | status strip text + freshness wording | RUNTIME | `app/web.py:1103-1116`; `index.html:8630-8679` | strip falls back to `generated_at`; "live feed asleep" branch |
| V1 | `/api/live_marks` | `pricing.priced_positions` / `total_positions` / `complete` | status strip ("partial pricing / snapshot fallback") | ECON | `app/web.py:1204-1208`, `1133-1137` | `Number(pricing.total_positions || 0)` at `index.html:8718` — missing counts become 0 |
| V1 | `/api/live_marks` | `session.state` / `market` / `timezone` / `next_open` / `is_open` | status strip ("US open · next open Oct 22 9:30 AM") | RUNTIME | `portfolio/market_sessions.py`; `index.html:8637-8679` | `stateEn[state] || 'closed'` — unknown venue state silently displays "closed" |
| V1 | `/api/live_marks` | `poll_after_seconds` | "refreshes about every N min" + timer | RUNTIME | `app/web.py:1131`, `1199` | `Number(seconds) || 120` (`index.html:8747`) |
| V1 | `/api/live_marks` | `archived` / `frozen_as_of` | status strip "Archived history · frozen …" | ECON | `app/web.py:247-253`; `index.html:8620-8628` | `fmtDate()` → `'—'` |
| V1 | `/api/portfolio` | `positions[].sleeve` (`brain`/`conviction`/`leadership`/`account`) | sleeve chip | RESEARCH | `app/web.py:1385`, `1390` (`"sleeve":"account"`) | defaults to leadership styling |
| V1 | `/api/portfolio` | `positions[].stage` | col "Stage" | RESEARCH | book file `latest.json` | `'—'` |
| V1 | `/api/portfolio` | `positions[].verdict` | verdict chip (`exit_pending` → "EXIT PENDING") | RESEARCH | `index.html:4752-4753` (`vKey` map incl. `pos.v_exit_pending`) | `(p.verdict || 'hold')` — missing verdict displays HOLD |
| V1 | `/api/portfolio` | `positions[].rs_pctile` / `confluence` | cols "RS %" / "Confluence" | RESEARCH | book file | `'—'`, guarded `!= null` |
| V1 | `/api/portfolio` | `positions[].opened_at` / `held_days` | col "Held since" | ECON | book file / `position_log` | `'—'`; pending rows show "fills at …" |
| V1 | `/api/portfolio` | `positions[].pending` + `fill_after` + `est_price` | "PENDING" chip + entry estimate | ECON | book file; `index.html:4730-4745` | `fmtDateShort()` → `'—'` |
| V1 | `/api/portfolio` | `positions[].live_only` | account-only rows injected when the strategy snapshot is empty | ECON | `app/web.py:1388-1420`; merge logic `index.html:8703-8716` | n/a (flag only) |
| V1 | `/api/portfolio` | `sleeves.leadership` / `.conviction` / `.cash` | Allocation bar segments + legend | ECON | `index.html:4507-4509` **`(sl.x || 0) * 100`** | **renders `0%`** — see Truth violation #3 |
| V1 | `/api/portfolio` | `gross` | legend "Gross" | ECON | `index.html:4526` | label hidden (`''`) when null — correct |
| V1 | `/api/portfolio` | `market_status === 'closed'` | "Markets closed" banner over Positions | RUNTIME | `index.html:4869-4876` | no banner |
| V1 | `/api/portfolio` | `disclaimer` / `disclaimer_zh` | footer disclaimer | RESEARCH | `app/web.py:1428-1433`; `index.html:8390-8399` | falls back to `t('footer.disc')` dictionary string |
| V1 | `/api/risk` | `safety_score` / `grade` / `verdict` | "Portfolio Safety" score tile | ECON | `app/web.py:1228-1267`; `index.html:4551-4560` | `'—'` + "Not enough data…" empty state (`index.html:4537-4541`) |
| V1 | `/api/risk` | `metrics.max_drawdown_pct`/`ann_volatility_pct`/`beta_spy`/`effective_n`/`mean_pairwise_corr`/`cvar95_1d_pct`/`var95_1d_pct`/`sharpe` | metric tiles | ECON | `portfolio/safety.py`; `index.html:4594-4602` | `num()/pc()` → `'—'` |
| V1 | `/api/risk` | `metrics.n_names` | tile sub-line "N actual" | ECON | `index.html:4597` **`(m.n_names || 0)`** | **renders `0 actual`** — violation #4 |
| V1 | `/api/risk` | `cash_weight` | tile "Cash buffer" | ECON | `index.html:4601` **`(d.cash_weight || 0) * 100`** | **renders `0.0%`** — violation #4 |
| V1 | `/api/risk` | `coverage.weight_covered` / `score_confidence` / `as_of` / `source` / `n_positions` | meta line under the score | ECON | `index.html:4554-4560` | each `!= null` guarded, omitted |
| V1 | `/api/risk` | `subscores.*` / `breaches[]` / `caveats[]` / `overlay` | sub-score bars, doctrine breaches, caveats | ECON | `index.html:4604-4707`; `app/web.py:1252-1254` | bar width 0 when null (`index.html:4606`) |

### V2 Manager decision — `index.html`

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V2 | `/api/portfolio?view=decision_availability` | `schema`/`portfolio_id` identity re-check | whole panel gated | RUNTIME | `index.html:8791-8793`, `7197-7202` | mismatch → "Decision status unavailable" alert, no numbers |
| V2 | same | `last_valid_decision.ts` / `asof` | card "Last valid decision" value | RESEARCH | `app/decision_availability.py:555-557`; `index.html:7208`, `7295` | `say('Unavailable','不可用')` |
| V2 | same | `last_valid_decision.summary` / `summary_zh` | banner `#auto-sum` (original accepted memo) | RESEARCH | `index.html:7549-7551`, `7600-7604` | "Valid decision memo unavailable. See decision and account status above." |
| V2 | same | `last_valid_decision.submitted_holding_count` | detail "Submitted holdings" | ECON | `index.html:7296` | `text()` → `'—'` |
| V2 | same | `last_valid_decision.summary_truncated` | "Memo preview truncated…" note | RESEARCH | `index.html:7298-7300` | note omitted |
| V2 | same | `latest_attempt.ts` / `run_id` / `target_status` | card "Latest recorded attempt" | RUNTIME | `app/decision_availability.py:558-560`; `index.html:7301-7306` | "Unavailable" |
| V2 | same | `latest_attempt_kind` (`accepted`/`failed`/`accepted_with_error`/`protective_carry`) | "Outcome" label + top alert | RUNTIME | `index.html:7210-7240` | falls back to `kindLabels.unknown` "Outcome unverified" |
| V2 | same | `accepted_target.execution_evidence` (`receipt_identity_verified`/`not_settled`/`unverified`) | card "Accepted target and execution" value | ECON | `app/decision_availability.py:289-318`; `index.html:7263-7268` | "Execution evidence unavailable" |
| V2 | same | `accepted_target.fill_count` / `settled_asof` / `settlement_transaction_id` | "Recorded no trade" vs "Recorded settlement" + settled date | ECON | `app/decision_availability.py:313-317`; `index.html:7309-7311` | branch shows queued/unverified wording |
| V2 | same | `accepted_target.gross_exposure` | detail "Target gross exposure" | ECON | `app/decision_availability.py:296`; `index.html:7307` | `percent()` → `'—'` |
| V2 | same | `accepted_target.weights_status` | (audit only) | ECON | `app/decision_availability.py:295` | `unavailable` |
| V2 | same | `accepted_target.pending.status` / `.target` / `.queued_at` / `.asof` / `.lineage_status` / `.clock_status` | "Pending state" row + lineage/timing warnings | ECON | `app/decision_availability.py:335-357`; `index.html:7269-7271`, `7252-7261`, `7307-7308` | "No pending target file observed" / "Pending target <status>" |
| V2 | same | `account.status` (+ labels map) | card "Persisted account" value | ECON | `app/decision_availability.py:160-232`; `index.html:7272-7280` | 7 explicit labels; unknown → "Account status unverified" |
| V2 | same | `account.cash` / `account.position_count` | details "Cash" / "Positions" | ECON | `index.html:7281-7282` | `money()` → `'—'` (no substitution) |
| V2 | same | `account.valuation.nav` / `.gross_exposure` / `.cash_weight` / `.price_date_from` / `.price_date_through` / `.status` | "Value at recorded prices", "Gross / cash at those prices", "Price dates", "Valuation unavailable…" | ECON | `app/decision_availability.py:160-232`; `index.html:7283-7290` | explicit "Valuation unavailable: quantities or qualified prices are incomplete." |
| V2 | same | `account.last_recorded_nav.nav` / `.date` | "Last NAV ledger entry" + "Historical mark; binding … unavailable" | ECON | `app/decision_availability.py:233-270`; `index.html:7291-7293` | row omitted if no entry |
| V2 | same | `consistency.status` / `.transaction` / `.changed_sources` | alert text (provisional reconciliation) | RUNTIME | `app/decision_availability.py:478-497`; `index.html:7241-7250` | no alert when `observed_stable` |
| V2 | same | `history_status`, `attempt_coverage`, `origin_lineage_status` | alerts + "Origin identity fields" | RUNTIME | `index.html:7243-7247`, `7297` | wording "Decision history is incomplete or unavailable" |
| V2 | same | `issues[]` | "Qualifications" list in `<details>`; `queued_decision_without_pending_target` alert | RUNTIME | `index.html:7251-7254`, `7340` | joined or `'—'` |
| V2 | same | `sources{file,status,sha256}` | "Source coverage and identities" block | RUNTIME | `index.html:7316-7322` | status text always printed |
| V2 | same | `settlement_price_inspection.*` (`status`,`receipt_linkage`,`fill_count`,`selected_price_count`,`price_context`,`durable_ledger_status`,`execution_qualification`,`book_consistency`) | settlement-price evidence table (`_settlementPriceEvidenceHtml`) | ECON | `app/decision_availability.py:398-425`; `app/settlement_price_read.py`; `index.html:6567-6600` | server default object is `status:"unavailable"` with `reason:"receipt_inspection_unavailable"` |
| V2 | same | `provider_diagnostic_inspection.*` (`candidates[]`,`candidates_observed`,`attempt_coverage`,`provider_start`,`effect_reconciliation`,`legacy_failure_observation`,`latest_observation_at`,`observation_age_seconds`) | provider-diagnostics panel | RUNTIME | `app/decision_availability.py:427-463`; `app/provider_diagnostic_read.py`; `index.html:7022-7100` | server default `status:"unavailable"`, `provider_start:"not_proven"`, `effect_reconciliation:"not_performed"` |
| V2 | `/api/portfolio` (non-availability books) | `summary` / `summary_zh` / `sold_note` | banner `#auto-sum` | RESEARCH | `app/web.py:1481-1499` (walks back to the last decision carrying a summary) | "No decision yet — appears after the Brain's first run." |
| V2 | `/api/portfolio` | `as_of` | meta chip "as of" | RUNTIME | `index.html:7591-7593` | chip omitted |
| V2 | `/api/posture?book=` | `posture_label` / `posture_label_zh` / `posture_tone` / `sub_strategy` / `favored[]` / `avoided[]` / `driver` / `detail` / `as_of` / `available` | "Strategy posture" chip + hover playbook | RESEARCH | `app/web.py:1755-1775`; `index.html:7664-7694` | `available:false` → "No posture yet / Appears after the Brain's first run." |
| V2 | `/api/decisions` | `decisions[].asof` + `today` | Daily Decision Log rows + "NEW" badge | RUNTIME | `app/web.py:1708`; `index.html:5088-5100` (activity) / `renderDecisions` | badge omitted |
| V2 | `/api/decisions` | `decisions[].summary(_zh)` / `sold_note(_zh)` / `brain_text(_zh)` | row memo | RESEARCH | `app/web.py:1736-1741` | zh falls back to EN |
| V2 | `/api/decisions` | `decisions[].executed[].ticker/side/value/pct_of_position/realized_pnl/realized_pct` | executed-action lines | ECON | `app/web.py:1723-1733` (FIFO backfill from `trade_history.sell_realized`) | fields simply absent → line not drawn |
| V2 | `/api/decisions` | `decisions[].holdings[]` / `effective_holdings[].rationale(_zh)` | per-name rationale | RESEARCH | `app/web.py:1742-1747` | line omitted |
| V2 | `/api/decisions` | `decisions[].execution_evidence_status` (`receipt_verified`/`legacy_unverified`/`none`) | evidence qualifier per decision row | ECON | `app/web.py:1712-1721` | derived on every read, never trusted from the file |
| V2 | `/api/decisions` | `archived` / `lifecycle` / `scope` / `note` | header + "decision log is Brain-book-only" notice | RUNTIME | `app/web.py:1687`, `1750-1753` | note shown |

### V3 Pending activity — `index.html`

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V3 | `/api/trades` | `pending[]` legacy rows (`.ticker`, `.side`/`.action`, `.shares`, `.est_price`, `.est_value`, `.fill_after`) | "Pending Orders" table inside `#trades` | ECON | `app/web.py:2369-2372` (legacy queue + projected target actions); render `index.html:4943-4981` | shares/est px/est value → `'—'`; settlement text → "awaiting" |
| V3 | `/api/trades` | `pending[].side` normalisation (`sell`/`trim`/`exit`/`reduce` → sell; `hold`/`quarantine_hold` → hold) | side chip BUY/SELL/HOLD | ECON | `index.html:4918-4926` | unknown side → BUY (legacy fallback, documented in-code) |
| V3 | `/api/trades` | `pending_target.status` (`queued`/`none`/`invalid`/`unavailable`) | truth notice banner above the table | ECON | `app/web.py:2043-2071`; `index.html:4927-4942` | explicit `pend.invalid` / `pend.unavailable` copy |
| V3 | `/api/trades` | `pending_target.comparison_status` (`current_weights_available`/`prices_unavailable`/`account_unavailable`/`constraint_snapshot_mismatch`/`transaction_pending`) | truth notice banner (error tone for invalid/mismatch) | ECON | `app/web.py:2118-2137`; `index.html:4933-4941` | specific sentence per state; nothing inferred |
| V3 | `/api/trades` | `pending_target.rows[].action` (`exit`/`trim`/`add`/`buy`/`hold`/`filtered`/`unpriceable`/`blocked`/`comparison_unavailable`) + `suppressed_by` | audit rows; only `side in {buy,sell}` becomes an order row | ECON | `app/web.py:2143-2222` | held name with `target_weight<=0` → `exit/sell` → shows while still held (TR2 satisfied) |
| V3 | `/api/trades` | `pending_target.rows[].current_weight` / `target_weight` | audit table | ECON | `app/web.py:2207-2210` | `current_weight` omitted when prices unavailable |
| V3 | `/api/trades` | `pending_target.fill_after` / `asof` / `queued_at` / `schema_version` / `engine_version` | "fills at …" + provenance | RUNTIME | `app/web.py:2057-2065`, `2211-2218` | `fmtDate()` → `'—'` / "awaiting" |
| V3 | `/api/trades` | `market.is_open` / `.session` / `.next_open` | closed-market banner + settlement date | RUNTIME | `app/web.py:2353-2359` (`market_calendar`/`china_calendar`); `index.html:4869-4876` | banner hidden; `'—'` |
| V3 | `/api/trades` | `snapshot_status` (`coherent`/`account_unavailable`/`transaction_pending`) | gate on whether rows are shown at all | RUNTIME | `app/web.py:2293`, `2383` | WAL present → empty arrays + `transaction_pending` notice (no partial mix) |
| V3 | `/api/self_directed` | `pending[]` (`.ticker`,`side`,`shares`,`notional`,`est_value`,`est_shares`,`order_id`) | "Pending orders" chip strip + ✕ cancel | ECON | `portfolio/self_directed.py:616-700`; `index.html:6125-6147` | empty → block not rendered |
| V3 | `/api/portfolio?view=decision_availability` | `accepted_target.pending.*` | "Pending state / Queued at / Queue decision binding" | ECON | see V2 rows | see V2 |


### V4 Performance — `index.html`

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V4 | `/api/performance` | `current_nav` | `#perf-nav` (label switches to "Last recorded NAV"/"Provisional NAV") | ECON | `portfolio/performance_projection.py:600-615`; `index.html:3929-3934`, `3943` | `fmtNav(null)` → `'—'` |
| V4 | same | `availability.valuation_basis` / `.status` | NAV label wording switch | ECON | `index.html:3935-3940` | defaults to plain "NAV" only when basis is neither provisional nor recorded |
| V4 | same | `total_return_pct` | `#perf-ret` "+x.xx%" | ECON | `index.html:3944-3949` | `fmtPctSign` → `'—'` + `neu` class |
| V4 | same | `inception_date` | `#perf-since` "since <date>" | ECON | `index.html:3952-3956` | "since inception" |
| V4 | same | `vs_benchmark_pct` | `#perf-spy` labelled "vs <benchmark_name>" | ECON | `index.html:3957-3962` | `'—'` when null — **but see Truth violation #6 (silent SPY substitution)** |
| V4 | same | `vs_spy_pct` | fallback for the same element | ECON | `index.html:3958` | — |
| V4 | same | `benchmark` / `benchmark_name` / `benchmark_name_zh` | "vs …" label + curve legend | ECON | `app/web.py:1311-1313` (`registry.benchmark*` overrides the file), `index.html:3922`, `4013` | `'Benchmark'` literal fallback (`index.html:3922`) |
| V4 | same | `day_change_pct` + `day_change_window.from/to` | `#perf-day` + sub-line | ECON | `index.html:3965-3975` | `'—'`; sub-line → "between recorded observations" |
| V4 | same | `max_drawdown_pct` + `drawdown_window` | `#perf-dd` + range | ECON | `index.html:3977-3988` | `'—'`; range → "over recorded observations" |
| V4 | same | `cash` | `#perf-cash-lbl` "cash: …" | ECON | `index.html:3990-3993` | `fmtNav(null)` → `'—'` |
| V4 | same | `starting_nav` | y-axis anchor + pre-inception flat segment | ECON | `index.html:4034` (validated `number && finite && >0`, else null) | pre-inception points render as gaps, not zeros |
| V4 | same | `realized_since` | legend "Portfolio (recorded since …)" + START marker | ECON | `index.html:4015-4018`, `4186-4191` | `'—'` in legend; marker omitted when `realIdx<0` |
| V4 | same | `series[].date` / `.nav` / `.spy_nav` / `.kind` | SVG equity curve + hover tooltip | ECON | `portfolio/performance_projection.py:233-275`; `index.html:4031-4041`, `4133-4176` | `pathStr()` lifts the pen on null (no plunge to zero, `index.html:4082-4092`); tooltip `'—'` (`index.html:4229-4243`) |
| V4 | same | `availability.status` / `.history_status` / `.account_history_binding` / `.as_of` / `.issues[]` | `#perf-evidence` qualification sentence | ECON | `index.html:3866-3893` | empty string when `availability` absent — see violation #7 |
| V4 | same | `external_flow_adjustment === 'not_applied'` | "NAV change is not adjusted for external cash flows" | ECON | `index.html:3890-3892` | sentence omitted |
| V4 | same | `return_measure` / `benchmark_return_basis` / `benchmark_total_return_status` / `benchmark_comparison_scope` / `observed_at` / `sources` | carried into the panel state (rendered only through the qualification text today) | ECON | `app/web.py:1174-1182` (live-marks passthrough list) | — |
| V4 | `/api/performance` (archived book) | `frozen_as_of` + `series` from persisted history, note | whole panel, "Archived history" strip | ECON | `app/web.py:139-226`; `app/web.py:1040-1042` | `'—'` |
| V4 | failure path | `unavailable_performance()` shape | panel with all-dashes + "Performance evidence unavailable; no balance or zero return has been substituted." | ECON | `app/web.py:1051-1052` → `portfolio/paper_account.py:3448-3477`; text `index.html:3870-3871` | every numeric key explicitly `None`; no synthetic capital — TR3/TR4-compliant by construction |

### V5 Opportunities — `index.html`

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V5 | `/api/portfolio` | `rejected[].ticker` | "Rejected" card title | RESEARCH | book file; `index.html:4477` | `'—'` |
| V5 | `/api/portfolio` | `rejected[].reason` / `reason_zh` | card body | RESEARCH | `app/web.py:1463-1471`; `index.html:4471`, `4478` | zh falls back to EN, then `'—'` |
| V5 | `/api/portfolio` | `rejected[].vetoes[]` / `bear[]` / `bear_zh` | veto chips + top-3 bear bullets | RESEARCH | `app/web.py:1467-1470`; `index.html:4480-4497` | section omitted when empty |
| V5 | `/api/portfolio` | `rejected[].confluence` | card footer value | RESEARCH | `index.html:4465-4466`, `4500` | `'—'` |
| V5 | `/api/research_papers` | `papers[].ticker` / `asof` / `reviewed_at` | Research table cols | RESEARCH | `app/web.py:1932-1960`; `index.html:5174-5228` | `fmtDate` → `'—'` |
| V5 | `/api/research_papers` | `papers[].engine_score` / `research_score` / `combined` / `viability` | score columns + CI colour band | RESEARCH | `app/web.py:1943-1948`; `index.html:5211-5217`, `5161-5172` | `'—'` (`_scoreCell`) |
| V5 | `/api/research_papers` | `papers[].action` (`buy_confirmed`/`research_held`/`evaluated`) + `trade_time` + `weight` | action column | ECON | `app/web.py:1912-1930` (**flagship-only join**); `index.html:1940-1942` | defaults to `evaluated`, `weight` absent |
| V5 | `/api/research_papers` | `papers[].confirmed` / `recommend` / `confidence` / `fair_value` / `price_at_review` / `price_assessment` | thesis modal score strip | RESEARCH | `app/web.py:1949-1954`; `index.html:5861-5935` | modal row omitted |
| V5 | `/api/research_papers` | `papers[].summary(_zh)` / `report_md(_zh)` / `key_risks[]` | modal body (markdown) | RESEARCH | `app/web.py:1955-1959`; `index.html:3611` `renderMd()` | empty body |
| V5 | `/research_paper.pdf?id=&ticker=` | binary PDF | "Download PDF" button | RESEARCH | `app/web.py:989-1035` | 404/503 JSON error surfaces in the fetch chain |
| V5 | `/api/outcome_ledger` | `summary.n`/`status`/`brier`/`hit_rate`/`calibration_error` | Calibration page header | RESEARCH | `app/web.py:1964-2000`; `index.html:5296-5429` | `n:0,status:'building'` shape on error |
| V5 | `/api/outcome_ledger` | `reliability_curve[].bucket` / `mean_predicted` / `hit_rate` / `n` | calibration bars | RESEARCH | `index.html:5341-5342` | **`|| 0` → a missing bucket plots as 0%**, violation #8 |
| V5 | `/api/outcome_ledger` | `lens_edge[]` / `lens_weights{}` / `records[]` (`prob_correct`,`realized_rel`,`outcome`,`asof_decided`,`asof_resolved`,`quad_at_entry`,`confluence_at_entry`,`lens_dirs`) | per-lens edge table + resolved-thesis log | RESEARCH | `app/web.py:1971-1999` | `lens_dirs` defaults `{}` |
| V5 | *(no endpoint)* | — | "entry readiness" (is a finalist actionable now?) | RESEARCH | **absent** | see Gap map V5 |

### V6 Position review — `index.html`

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V6 | `/api/portfolio` | `positions[].thesis_full.summary` / `why_now` / `sizing_rationale` (+ `_zh`) | expand-row thesis panel | RESEARCH | `app/web.py:1441-1456`; `index.html:4796-4799`, `4801-4806`, `4846-4851` | block omitted when absent |
| V6 | `/api/portfolio` | `positions[].thesis_full.bull[]` / `bear[]` (+ `_zh`) | "Case for / Case against" two-column list | RESEARCH | `app/web.py:1448-1455`; `index.html:4808-4823` | explicit "no bull points" empty li |
| V6 | `/api/portfolio` | `positions[].thesis_full.vetoes[]` / `divergences[]` | veto / divergence chips | RESEARCH | `index.html:4825-4839` | section omitted |
| V6 | `/api/portfolio` | `positions[].thesis_full.what_would_prove_wrong` (+ `_zh`) | "Falsifier" box | RESEARCH | `app/web.py:1445`; `index.html:4841-4844` | box omitted — **no automatic review date/check condition** |
| V6 | `/api/portfolio` | `positions[].thesis_full.confluence` / `prob_correct` | sizing numbers | RESEARCH | `index.html:4852-4862` | guarded `!= null`; whole block skipped |
| V6 | `/api/portfolio` | `positions[].research.{engine_score,research_score,combined,viability,summary,summary_zh,mode,paper_id}` | "Research Desk" gate block + "view full paper" | RESEARCH | `app/web.py:1435-1440`; `index.html:4779-4795` | `'—'` per score; block omitted if `research` absent |
| V6 | `/api/live_marks` | actual fills/marks: `cost_basis`, `current_price`, `unrealized_pnl`, `unrealized_pct`, `quote_source` | the "actual fills" half of the review | ECON | `app/web.py:1148-1163` | `'—'` |
| V6 | `/api/trades` | `history[].date`/`ticker`/`action`/`shares`/`price`/`exit_price`/`realized_pnl`/`realized_pct` | Trade History blotter rows | ECON | `portfolio/trade_history.py:31-180`; `index.html:5020-5045` | `'—'` per cell |
| V6 | `/api/trades` | summary tiles: realized total, `sells.length`, `buys.length`, win rate | `#trades` scorecard | ECON | `index.html:4999-5012` | tiles show `'—'` when `sells.length==0`; **win-rate shown with no sample gate** — violation #5 |
| V6 | `/api/trades` | `open[]` / `closed[]` (`position_log`) | not rendered by the SPA (payload only) | ECON | `app/web.py:2352-2353`; `portfolio/position_log.py:316-352` | UNVERIFIED whether any consumer reads them |
| V6 | `/api/portfolio` | `accountability.{n_resolved,n_open,horizon_d,weight_ic,book_edge_mean,book_edge_significant,hit_rate,by_conviction.*}` | "Sizing Scorecard" cards + by-conviction table | RESEARCH | `index.html:8408-8476` | hides the whole section when `n_resolved == null` (`8412-8415`); `n_open/horizon_d` default `0`/`21` (`8426-8427`) |
| V6 | `/api/self_directed/history` | `history[].queued` | "⧖ queued fill" flag | ECON | `portfolio/self_directed.py:737-800`; `index.html:6166` | flag omitted |
| V6 | *(no endpoint)* | — | "next review condition" (time stop / stage review date) | RESEARCH | **absent from every rendered payload** | see Gap map V6 |

### V7 Operations — `index.html` + standalone pages

| View/page | API endpoint | Field (JSON path) | Rendered as (element/label) | Owner | Source | Null handling |
|---|---|---|---|---|---|---|
| V7 | `/api/runs` | `[].run_id`/`ts`/`kind`/`title`/`n_steps`/`cost_usd`/`summary` (+ `_zh`) | "Brain Activity — Full Trace" list | RUNTIME | `app/web.py:3071-3093`; `index.html:4295-4341` | title → `run_id` → `'—'`; steps `'—'`; cost omitted |
| V7 | `/api/runlog?run_id=` | `steps[].ts`/`type`/`title`/`detail` + status/severity | lazy step trace per run | RUNTIME | `app/web.py:3096-3102`; `index.html:4383-4443` | "click to load", empty list |
| V7 | `/api/scheduler` | `jobs[].id`/`last_status`/`last_severity`/`last_started`/`last_finished`/`last_skipped`/`last_reason`/`last_target_status`/`next_run_time` | Desk → scheduler table | RUNTIME | `app/web.py:3540-3553`; `app/scheduler.py` `scheduler_health()`; `index.html:5474-5513` | `'—'` for both clocks; empty → "Scheduler not available…" |
| V7 | `/api/desk/strategist?asof=` | `status` (`building`) / verdict fields / `asof` | Desk "Strategist" panel | RESEARCH | `app/web.py:3169-3210`; `index.html:5515-5563` | explicit "building" state, never a default verdict |
| V7 | `/api/desk/decisions?asof=` | `decisions[]` action/reason/asof | Desk decisions table | RESEARCH | `app/web.py:3212-3280` (reads `gate_officer`/`risk_officer` `decisions.json`); `index.html:5632-5679` | `_deskEmpty` |
| V7 | `/api/desk/watchlist?book=flagship` | `watchlist[].ticker`/`reason`/`asof`/state rows | Desk watchlist | RESEARCH | `app/web.py:3282-3324`; `index.html:5680-5700` | `[]` → empty state |
| V7 | `/api/desk/scorecard` | `seats[].calibration/attribution/reputation`, `cio` | Desk per-seat scorecard | RESEARCH | `app/web.py:3326-3413`; `index.html:5701-5753` | `status:'building'` initial payload |
| V7 | `/api/desk/macro-risk?asof=` | fragility/macro-risk rows | Desk macro-risk lane | RESEARCH | `app/web.py:3415-3458`; `index.html:5564-5625` | empty state |
| V7 | `/api/desk/firm-exposure`, `/api/firm_allocator?rebuild=` | book/sector exposure rows | Desk firm exposure | ECON | `app/web.py:3460-3503`; `index.html:5766-5860` | `_firmBooksStr` fallback |
| V7 | `/api/portfolio?view=decision_availability` | `expected_opportunity.status` (always `unknown` + `reason:"scheduler_evidence_not_bound"`) | footer sentence "Scheduled opportunity status is unverified" | RUNTIME | `app/decision_availability.py:556`; text `index.html:7325-7329` | permanently unknown — the scheduler evidence is not bound |
| V7 | `/api/forward-evaluation?portfolio=&asof=` | `status`, `latest_asof`, `snapshot.{asof,book,schema,cohort.evaluation_start,nav_date_basis}`, `observation_qualification.{schema,calendar_status,calendar_count_unit,calendar_session_count,calendar_basis,reported_mark_count_status,price_qualified_session_count,calendar_missing_reason,source_scope}` | "Evaluation record" facts + qualification note + "Inspect evidence record" link | ECON | `app/web.py:1652-1679`; `portfolio/forward_evaluation.py:1840-2020`; `index.html:7404-7535`, fetch `7530` | every unverified dimension prints "Unverified"/`'—'`; unknown `status` → saved record + stale banner |
| V7 | `/api/market_view` (page `/market_view`) | `planes{}`, `serving_freshness.current_confirmation_available`, `label_vs_planes.{label_direction,plane_consensus_direction,relationship,lead,lag,magnitude,conflict,dissenting_planes}`, `net_posture_tilt.{direction,tilt}`, `assembly.{eligible_validated,validated,fresh,stale,missing}`, `coherence`, `brief`, `coverage`, `built_at`, `asof`, `region`, `seq` | planes table, label-vs-planes banner, deterministic brief, top rotation pairs | RESEARCH | `app/web.py:1777-1804`; `brain/market_view.py` `serving_view`; `market_view.html:340-540` | 404 `{available:false,note}` → "unavailable" message; `fmt(null)` → `'—'` |
| V7 | `/api/agenda` (page `/agenda`) | `items[].rank`/`title`/`evidence`/`suggested_fix`/`fix_type`/`expected_impact`/`owner`/`age_weeks`/`readiness`, `n_items`, `owners`, `class_counts`, `as_of`, `schema_version`, `readiness_input` | ranked agenda cards | RESEARCH | `app/web.py:1807-1831`; `brain/improvement_agenda.py:52`; `agenda.html:300-400` | 404 `{available:false,note}` → message + "unavailable" subtitle |
| V7 | `/health`, `/ready` | `status`, `paper_only`, `scheduled_runtime_ok`, `reasoning_policy_ok`, `commit`/`version`, `serve_only` | uptime probe / deploy probe body (no page renders them) | RUNTIME | `app/main.py:196-218` + `_runtime_health()` `app/main.py:140-195` | honest `"degraded"` when the scheduler is dead |


## Gap map

| View | Status | Where (page + API) | Present content | Missing content (vs the required list) | Questions answered |
|---|---|---|---|---|---|
| **V1 Portfolio overview** | **exists** | `index.html` `#positions`/`#alloc`/`#safety`/`#live-marks-status` ← `/api/portfolio`, `/api/live_marks`, `/api/risk` (+ `/api/self_directed` for that book) | Actual holdings from the paper account including account-only lots the strategy snapshot omits (`app/web.py:1388-1420`, `index.html:8703-8716`); cash (`/api/live_marks.performance.cash`, `#perf-cash-lbl`); current/estimated valuation with per-name entry vs mark, weight, unrealized; valuation timestamp + provenance per name (`quote_source`/`quote_as_of`/`quote_stale_days`) and an exchange-clock strip with next open; limitations via risk caveats and the snapshot/prior-EOD wording | Sleeve allocation can display a fabricated `0%` split (violation #3); `self_directed` NAV can display a fabricated `$1,000,000` (violations #1/#2); no single "as-of" for the whole book — the clock is per name and per panel | **Q1 yes** (with the caveats above) |
| **V2 Manager decision** | **exists** | `index.html` `#auto-banner-sec`, `#decision-availability`, `#decisions-sec`, posture chip ← `/api/portfolio?view=decision_availability`, `/api/decisions`, `/api/posture` | Latest accepted decision with identity checks (`last_valid_decision`, `decision_id`, `origin_lineage_status`); explicit actions (`executed[]` with side/value/pct_of_position/realized, `accepted_target.weights`/`gross_exposure`); compact rationale (original accepted memo, never a refreshed snapshot — `index.html:7548`); horizon is **absent**; invalidation only as free text `what_would_prove_wrong`; unchanged-book explanation (posture "No posture yet", `consistency` alerts, `latest_attempt_kind` incl. `protective_carry`, the `queued_decision_without_pending_target` warning) | No structured **horizon** field anywhere in the payload; no explicit "book unchanged today because …" structured reason (it is inferred from the memo + attempt kind); the non-availability books (flagship/heavyweight/etf) get no decision-availability panel at all (`ACTIVE_BOOKS` = autonomous/china/hk, `app/decision_availability.py:20`) | **Q2 yes**, **Q5 partially** (evidence status is present and rigorously qualified; horizon/invalidate date is not) |
| **V3 Pending activity** | **exists** | `index.html` `#trades` pending block + `_pendingTruthNoticeHtml` ← `/api/trades` (+ `accepted_target.pending` and `#sd-pending-host`) | Queued target as a full audit object (`pending_target.rows[]` with `action`/`target_weight`/`current_weight`/`suppressed_by`), only actionable rows promoted to the order table; next eligible session (`fill_after` from `market_status.next_open`, `app/web.py:2064`); expiration/supersession handled as states — `invalid`/`unavailable`/`constraint_snapshot_mismatch`/`transaction_pending`/`lineage_status:conflict`; final disposition (settled via `execution_evidence`, cancelled/no-cash rows in `self_directed`) | No explicit **expiration timestamp** for a queued target (supersession is shown as a mismatch warning, not a scheduled expiry); no "final disposition" history list for Brain targets (only the WAL/`transaction_pending` transient); the legacy `pending` list mixes account orders and projected target actions after `_pendingOrderSide` defaults an unknown side to **BUY** (`index.html:4918-4926`) | **Q3 yes** |
| **V4 Performance** | **exists** | `index.html` `#performance` + `#equity-curve` ← `/api/performance` (+ `/api/live_marks.performance`) | Same-window portfolio/benchmark curves (`series[].nav` + `series[].spy_nav`, benchmark as a dashed reference line); total-return/cost basis qualified through `availability.valuation_basis` (`last_recorded_nav`/`provided_prices`/`cash_only`/`unavailable`) plus the `_performanceEvidenceText` qualification sentence; drawdown with its own observed window (`max_drawdown_pct` + `drawdown_window`); cash; qualified/provisional status is explicit and `unavailable_performance()` substitutes nothing (`portfolio/paper_account.py:3448-3477`) | **Attribution is missing from V4** — the Brinson/per-seat credit rollup exists only on the Flagship Desk (`/api/desk/scorecard` ← `brain/attribution.rollup()`, `app/web.py:3326-3413`), not on the product performance panel; external-flow adjustment is disclosed but never quantified; no benchmark "unavailable" label on the curve legend itself (violation #9) | **Q4 yes** for the curve/return/drawdown/cash basis; **Q5 partially** (qualification text is strong, attribution absent) |
| **V5 Opportunities** | **partial** | Rejected finalists: `#rejected` ← `/api/portfolio.rejected`; papers: `#view-research` ← `/api/research_papers`; Calibration ← `/api/outcome_ledger` | Rejection reasons + vetoes + top-3 bear bullets + confluence per rejected name; researched finalist table with engine/research/combined scores, viability, action, review date, PDF export; forward-grading calibration (Brier, hit-rate, reliability curve, lens edge/weights) | **The product book cannot reach it.** `#rejected` is in `PF_GATED_ONLY` so it is hidden for Brain books (`index.html:6454-6457`), and the Research/Desk tabs render only when `_portfolio === 'flagship'` (`index.html:6462-6463`) — flagship is archived (`portfolio/registry.py:33-45`). **Entry readiness** (can this finalist be entered now: session open, liquidity, price band) is not modelled anywhere. **Source coverage** exists only as `/api/research_papers.mode` and the decision-availability `sources{}` map, never joined to the finalist list. The gate join in `/api/research_papers` reads the flagship book file regardless of the requested book (`app/web.py:1912`) — violation #10 | none of Q1–Q5 for the product book; V5 answers **Q5** only for the archived flagship |
| **V6 Position review** | **partial** | `index.html` expand-row per position (`toggleExpand`, `index.html:4900-4916`) + `#trades` blotter + `#sizing-sec` | Original thesis (summary/why_now/bull/bear/vetoes/divergences/falsifier/sizing rationale + Research Desk gate block with paper link); actual fills (`cost_basis`, per-fill blotter with FIFO realized P&L); loss/gain contribution (unrealized per name, realized per sell incl. `pct_of_position`); subsequent factual changes **only** as the divergence chips and the (stale) memo — there is no dated change log per position | **Next review condition is missing**: no stage-review date, no time-stop countdown, no check-by date rendered from any endpoint (DOCTRINE's stage lifecycle and time stop are not surfaced as a per-position review trigger); `thesis_full.what_would_prove_wrong` is free text with no bound metric/date; `open[]`/`closed[]` from `position_log` (thesis history per position) are returned but never rendered (`app/web.py:2352-2353`) | **Q1 partial, Q2 partial, Q5 partial**; win-rate tile without a sample gate (violation #5) |
| **V7 Operations** | **partial** | `index.html` `#runs`/`#run-steps` + `#view-desk` (7 lanes) ← `/api/runs`, `/api/runlog`, `/api/scheduler`, `/api/desk/*`; standalone `/market_view` ← `/api/market_view`; standalone `/agenda` ← `/api/agenda`; `#forward-evaluation` ← `/api/forward-evaluation` | Delayed/failed/partial is explicit in several places: `latest_attempt_kind:failed` alert, `snapshot_status:transaction_pending`, `consistency:changed_during_read`, `status:stale_after_error` on the evaluation record, scheduler `last_status/last_severity/last_reason`, market-view `serving_freshness` + stale pills, agenda `readiness`; technical detail is available separately (the `settlement_price_inspection`/`provider_diagnostic_inspection` tables and the "Inspect evidence record" raw-JSON link, `index.html:7530`) | The scheduler/Desk lanes are **Flagship-only in the UI** (`index.html:6462-6463`), so an operator on the product book has no one-glance "is the daily job delayed" panel — the honest signals they do see are on the decision panel; `expected_opportunity.status` is permanently `unknown` (`app/decision_availability.py:556`) so "was today's run scheduled at all" is not answerable; `/api/readiness`, `/api/outcomes`, `/api/rejections`, `/api/portfolio_learning`, `/api/provenance`, `/api/macro`, `/api/etf/outcomes`, `/api/overnight-tape`, `/api/shadow_bandit`, `/api/desk/experiments` have **no consumer in this repo** | **Q5 partial** (ops evidence for the book exists; job-level delay/health is not reachable per product book) |

**Reachability summary for the default product book (`autonomous`)**: V1 ✓, V2 ✓, V3 ✓, V4 ✓, V5 ✗ (hidden), V6 partial, V7 partial. `Q1 ✓ Q2 ✓ Q3 ✓ Q4 ✓ Q5 partial`.


## Truth violations

Ordered by severity within each rule. `path:line` is exact; quotes are ≤3 lines.

1. **TR1 / unknown→capital — HIGH.** `app/web.py:2424` — `/api/self_directed` failure path invents a full account.
   ```python
   return JSONResponse({"nav": 1_000_000.0, "cash": 1_000_000.0, "invested": 0.0,
                        "positions": [], "pending": [],
   ```
   The user sees the Self-Directed book as a real $1,000,000 all-cash account with 0.00% return and 100% cash (`index.html:6046-6049` renders `allocation` normally), plus the string only inside `error` which the page never shows (`refreshSelf` at `index.html:5951-5960` ignores it). Nothing on screen says the read failed.
2. **TR1 / unknown→capital — HIGH.** `app/static/index.html:5980` — client-side repeat of the same invention.
   ```javascript
   if (E('sd-nav'))   E('sd-nav').textContent = fmtNav(b.nav != null ? b.nav : 1000000);
   ```
   If `nav` is absent for any other reason (partial payload, older server), `#sd-nav` displays `$1,000,000` as the account's NAV. Cash/invested/gross all correctly fall back to `'—'` (`index.html:5981-5985`) — only NAV fabricates.
3. **unknown→0 — HIGH.** `app/static/index.html:4507-4509` — missing sleeve weights render as a definite 0% split.
   ```javascript
   var lead = (sl.leadership || 0) * 100;
   var conv = (sl.conviction || 0) * 100;
   var cash = (sl.cash || 0) * 100;
   ```
   With `_book.sleeves` absent/malformed the Allocation panel shows a full-width **Cash 0%** bar and the legend "Leadership 0% · Conviction 0% · Cash 0%" — an impossible allocation presented as fact. Note the sibling field `gross` is handled correctly (`index.html:4526` hides the label when null), so this is an inconsistency, not a house style. The static HTML seed (`index.html:2818-2820` "50% / 8% / 42%") is masked only while `_book == null` via `.mm-pf-awaiting` (`index.html:2467-2469`).
4. **unknown→0 — MEDIUM.** `app/static/index.html:4597` and `4601` — safety tiles.
   ```javascript
   tile(H('Effective names','有效持仓数'), num(m.effective_n,1), (m.n_names || 0) + (isZh?' 实际':' actual'))
   tile(H('Cash buffer','现金缓冲'), pc((d.cash_weight || 0) * 100))
   ```
   An unavailable risk snapshot's cash buffer reads "0.0%" and its name count reads "0 actual", both implying a measured zero rather than a missing value. Every sibling metric uses `num()/pc()` which do return `'—'`.
5. **TR5 — MEDIUM.** `app/static/index.html:5001-5010` (paper books) and `6157-6159` (Self-Directed) — win rate without a minimum-sample rule.
   ```javascript
   var wins = sells.filter(function(r){ return (r.realized_pnl || 0) > 0; }).length;
   var winTxt = sells.length ? Math.round(wins / sells.length * 100) + '%' : '—';
   ```
   A single closed position renders "Win Rate 100%". Mitigations that do exist: the adjacent "Closed" tile shows the denominator (`index.html:5008`) and the footnote explains realized-only accounting (`index.html:3467`, `5048`); what is missing is any "n too small to conclude anything" gate, while the Sizing Scorecard does gate its edge claim on significance (`index.html:8467-8471`).
6. **mislabelled comparison (TR3-adjacent) — MEDIUM.** `app/static/index.html:3958` and `7586`.
   ```javascript
   var relativeReturn = p.vs_benchmark_pct != null ? p.vs_benchmark_pct : p.vs_spy_pct;
   ```
   The element is labelled `vs <benchmark_name>` (`index.html:3952-3956`), so the fallback reads "vs 沪深300" while displaying an SPY-derived figure. **Today the number cannot actually be wrong** because the server publishes both keys from one value (`portfolio/performance_projection.py:599-600`, `app/web.py:210-211` `"vs_spy_pct": vs_benchmark_pct`) — the defect is the alias itself: a CSI-300/Hang-Seng comparison is shipped under the field name `vs_spy_pct`, which the shadow-book column then renders under an SPY header (`app/static/index.html:8048`, `app/web.py:1576-1577` sets `vs_spy_pct` for `self_directed` from the SPY bogey).
7. **TR3 — MEDIUM.** `app/static/index.html:3869-3870`.
   ```javascript
   var a = p && p.availability;
   if (!a) return '';
   ```
   When `/api/performance` carries no `availability` object the qualification line is simply empty and the NAV label defaults to plain "NAV" (`index.html:3936-3940`). This is reachable: `_archived_performance()` returns **no `availability` key at all** (`app/web.py:205-225`), so for every archived book (flagship / heavyweight / etf) a frozen historical mark is presented as an unqualified current NAV, with no evidence sentence.
8. **unknown→0 — MEDIUM.** `app/web.py:190-196` (`_archived_performance`).
   ```python
   total_return_pct = ((current_nav / starting_nav - 1.0) * 100.0 if starting_nav > 0 else 0.0)
   day_change_pct = 0.0
   ```
   A zero/missing starting NAV displays **+0.00%** return, and a book with one NAV row displays **+0.00%** day change — flat by omission, not by measurement. The active-book equivalent (`portfolio/performance_projection.py:284-285`) correctly returns `None` for the same unknowns.
9. **TR4 — MEDIUM.** `app/static/index.html:4033-4038`, `4164-4166`.
   ```javascript
   if (s.kind === 'pre_inception' || s.kind === 'hypothetical') return startNav;
   svg += '<path d="' + pathStr(navVals, 0, realIdx) + '" fill="none" stroke="var(--up)" stroke-width="1.8" opacity="0.5"/>';
   ```
   Pre-inception synthetic points are drawn as a **solid line in the same `--up` (green) family as real performance**, at full line weight, and `allVals` (`index.html:4068`) folds them into the y-axis extent — a long flat $1M tail compresses the visible range and makes the realised segment look calmer than it is. Partial mitigations: a dashed inception baseline (`index.html:4154-4156`), a labelled "START" marker (`4186-4191`), the legend "recorded since …" (`4015-4018`), and area fill restricted to the realised segment (`4125-4126`, `4171-4172`). The tooltip does state "pre-inception" (`index.html:4233-4234`).
10. **TR1 — HIGH.** `app/web.py:2947`, `app/web.py:2980` and `app/web.py:1912` — narrative bound to a different book than the holdings.
    ```python
    ledger_path = _data() / "portfolio" / "positions_ledger.json"      # /api/activity
    portfolio_path = _data() / "portfolio" / "latest.json"             # /api/activity
    book = json.loads((_data() / "portfolio" / "latest.json").read_text())  # /api/research_papers
    ```
    `data/portfolio/` is the **archived flagship** tree (`portfolio/registry.py:257-258`; `DEFAULT_ID = "flagship"` `registry.py:29`), while the dashboard defaults to `autonomous` (`registry.py:30`, `app/web.py:22`). The Brain Log therefore narrates flagship trades/decisions underneath autonomous positions, and the Research page stamps `buy_confirmed`/`research_held` from the flagship gate for any requested book (`app/web.py:1913-1930`). The UI partially hides this: `#brainlog` is in `PF_GATED_ONLY` and the Research tab renders only for flagship (`index.html:6454-6463`) — but the endpoints themselves are open and the JSON is book-agnostic.
11. **TR2 — compliant (verified, recorded here so the census is not read as silence).** A queued exit on a still-held name is shown as a pending change: `app/web.py:2174-2180` maps a held ticker with `target_weight <= 0` to `action="exit", side="sell"`, `app/web.py:2221-2222` promotes it into the legacy `pending` list, `index.html:4918-4926` labels it SELL, and the held row additionally renders the `exit_pending` verdict chip (`index.html:4752-4753`) plus a PENDING chip/fills-at line when `positions[].pending` is set (`index.html:4730-4733`, `4757`). The "not yet in Positions" caption is accurate for names not yet owned (`index.html:3285`).
12. **unknown→0 — MEDIUM.** `app/pfolio.py:357-359` + `app/static/portfolio.html:676-686`.
    ```python
    total_value = 0.0
    day_pnl = 0.0
    total_pnl_usd = 0.0
    ```
    `_portfolio_totals()` nulls these only when **no** position has a market value (`app/pfolio.py:382-383`). If holdings exist but quotes/P&L do not, `/api/pfolio/positions` publishes `day_pnl: 0.0` and `total_pnl_usd: 0.0`, and the Portfolio Risk Desk renders "+$0.00" for both (`portfolio.html:680-686` via `fmt$`) — a measured zero flat day.
13. **unknown→colour — LOW.** `app/static/portfolio.html:681` and `686`.
    ```javascript
    dpEl.className = "val " + (parseFloat(dp) >= 0 ? "pos" : "neg");
    ```
    For `day_pnl: null` (the legitimate unavailable case) `parseFloat(null)` is `NaN`, the test is false, and the dash is styled **negatively (red/down)** — an unknown reading as a loss. The value text itself is an honest `—` (`portfolio.html:541-546`).
14. **unknown→0 — LOW.** `app/static/index.html:5341-5342` (Calibration reliability bars).
    ```javascript
    var predW = Math.max(0, Math.min(100, (b.mean_predicted || 0) * 100));
    var realW = Math.max(0, Math.min(100, (b.hit_rate || 0) * 100));
    ```
    A bucket with no observed predictions draws a 0-width bar at the "0%" position instead of an absent/`—` bucket.
15. **unknown→0 — LOW.** `app/static/market_view.html:414`, `427`.
    ```javascript
    (a.eligible_validated == null ? (a.validated || 0) : a.eligible_validated)
    (a.fresh || 0) + " fresh, " + (a.stale || 0) + " stale, " + (a.missing || 0) + " missing"
    ```
    Missing assembly counts display as `0 fresh, 0 stale, 0 missing`, which reads as "all planes measured" rather than "coverage unknown".
16. **unknown→0 — LOW.** `app/static/index.html:8718`.
    ```javascript
    Number(pricing.total_positions || 0) === (data.positions || []).length;
    ```
    If `pricing` is missing entirely, `0 === 0` is true and the SPA treats holdings as **complete** (`holdingsComplete`) and overwrites `_book.positions` — a missing block asserting completeness. Guarded only by `!data.error` on the same expression.
17. **narrative vs account (TR1) — MEDIUM, latent.** `app/web.py:1341-1352` — `/api/portfolio` `account_preview` fabricates its own basis.
    ```python
    cash = float(account.get("cash") or 0.0)
    starting_nav = float(account.get("starting_nav") or 1_000_000.0)
    ```
    A missing `cash` renders as $0 cash with `invested` = full NAV, and a missing `starting_nav` computes `total_return_pct` against an invented $1,000,000 baseline. **Currently not user-visible through the SPA**: `index.html:8794-8800` adopts `account_preview` as a provisional performance object and then deletes it precisely because it lacks `availability` ("Legacy account previews cannot qualify unavailable performance values"). Any non-SPA consumer of `/api/portfolio` (the sister Macro site, a script) still receives the unqualified numbers.
18. **verdict default — LOW.** `app/static/index.html:4731`.
    ```javascript
    var verdict = (p.verdict || 'hold').toLowerCase();
    ```
    A position row with no verdict is labelled **HOLDING**, i.e. an active manager stance is asserted for missing data. The account-only rows injected by the server carry `"verdict": "hold"` explicitly (`app/web.py:1391`), so the display and the default coincide — which makes the fabrication invisible.
19. **session-state default — LOW.** `app/static/index.html:8637-8643`.
    ```javascript
    holiday: 'holiday', weekend: 'weekend'
  }[s.state] || 'closed';
    ```
    An unknown or missing `session.state` displays "closed" (zh "休市") rather than "unknown", which can hide a clock failure behind an ordinary closed market.
20. **benchmark availability not shown where it matters (TR3) — LOW/MEDIUM.** `app/static/index.html:4020`.
    ```javascript
    if (legBenchEl) legBenchEl.textContent = benchDisplay + (isZhEc ? '（参考序列）' : ' (reference series)');
    ```
    The curve legend always names the benchmark as a reference series even when `series[].spy_nav` is null for every point (the dashed path is then empty, `index.html:4161-4162`), so a chart with **no** benchmark line still claims one in its legend. The headline stat does degrade honestly: `#perf-spy` shows `'—'` (`index.html:3957-3962`) and the evidence line adds "A comparison over common benchmark dates is unavailable" (`index.html:3883`).
21. **stale docstring that misdescribes a mutating GET — LOW (documentation).** `app/web.py:2411` states `/api/self_directed` "Settles any due pending orders on read", while the call passes `read_only=True` (`app/web.py:2418-2420`, semantics at `portfolio/self_directed.py:616-631`). The behaviour is correct; the contract text is not. The genuinely mutating case is #22.
22. **read path that changes the account — HIGH (integrity, TR1-adjacent).** `portfolio/self_directed.py:741` reached from `GET /api/self_directed/history` (`app/web.py:2434-2441`).
    ```python
    settle_pending(now=now, market_open=market_open, prices=prices)
    ```
    An unauthenticated GET (browser prefetch, a proxy retry, the response cache re-serve path, or `curl`) fills or cancels queued paper orders and writes `account.json` / `fills.jsonl` / `pending.json` (`portfolio/self_directed.py:313-325`). `GET /api/portfolio` also recovers a WAL through `paper_account._load_account()` (`app/web.py:1340` → `portfolio/paper_account.py:191`); `/api/trades` deliberately avoids that by using `_load_account_file` (`app/web.py:2298-2303`), so the inconsistency is within the same product surface.

## Auth + cache isolation

**The model, as coded.** There is no per-user identity in this process. `app/auth.py:13-16` states the
browser password-cookie login flow has been REMOVED — no `/login`, no `/logout`, no session cookie — and
`MASTERMIND_PASSWORD`, `MASTERMIND_SESSION_DAYS`, `MASTERMIND_COOKIE_SECURE`, `MASTERMIND_REQUIRE_AUTH`
are documented no-ops. Every GET falls through open (`app/auth.py:436-438`); `_OPEN_PATHS = {"/health",
"/ready"}` (`app/auth.py:158`) is only the never-gated set, not an allowlist, because nothing else is gated
either. Four things are enforced: serve-only POST guard, the `/api/pfolio/` prefix, the bearer operator
tier, and operator rate limits (`app/auth.py:5-11`, `app/auth.py:358-368`).

1. **There is no Pro gate in this repository.** `app/auth.py:132-141` documents the entitlement layer that
   answers an anonymous `GET /api/pfolio/positions` with `{"locked":true,"tier":"anon","required_tier":"pro"}`
   and then states plainly: *"That is a SUBSCRIPTION paywall, not an operator-identity check… it is also
   external to this process, so any path that reaches the origin directly… never sees it. The gate below is
   the one that has to hold."* Consequence for the census: **no view (V1–V7) is Pro-gated in code**; a non-Pro
   user is treated exactly like a Pro user for every read surface, and V1/V2/V3/V4/V6 of the *product* books
   are anonymous-readable by design. Only `/api/pfolio/*` (the operator's real Supabase holdings) and the 16
   operator POSTs are restricted.
2. **Fail-closed behaviour on the authoritative box is correct.** `assert_authoritative_auth_configured()`
   (`app/auth.py:318-337`) refuses startup when `MASTERMIND_VPS_AUTHORITATIVE=1` with no
   `MASTERMIND_AUTH_TOKEN`; per-request the same condition returns 503 `operator_auth_misconfigured`
   (`app/auth.py:441-457`) instead of the old dev pass-through. Bearer comparison is `hmac.compare_digest`
   (`app/auth.py:353`). The dual LLM rate limit is expressed as two independent sliding windows
   (`app/auth.py:233-300`), and the serve-only guard blocks all methods on `/api/pfolio/` (`app/auth.py:400-407`).
3. **ISOLATION RISK (privacy, not cross-tenant merge) — personal books are anonymous.** `GET /api/self_directed`
   (`app/web.py:2409-2423`) and `GET /api/live_marks?portfolio=self_directed` (`app/web.py:1054`, whose
   `self_directed` branch reads `portfolio/self_directed/_load_account()` at `app/web.py:1077`) publish the
   human's own holdings, order queue and per-name thesis notes (`portfolio/self_directed.py:616-700` includes
   `theses.json` content) to any caller, and are **cacheable** (`/api/self_directed` is not in
   `_DENY_PREFIXES`, `app/response_cache.py:44-51` — only `/search` and `/quote` are). Meanwhile the
   structurally identical surface `/api/pfolio/*` was deliberately closed (`app/auth.py:396-433`) and is
   denylisted (`app/response_cache.py:44`). The two decisions are inconsistent for the same class of data.
4. **Cache key composition.** `app/response_cache.py:72-83`: `path + "?" + urlencode(sorted(parse_qsl(query)))`
   — order-insensitive, **no user, no cookie, no Authorization header, no book unless the book is a query
   parameter**. There is no user to include (finding 1), so identity cannot leak; per-book responses are safe
   *because* all 12 book-scoped handlers take `portfolio`/`book` in the query (see the Route table's last
   column) and so get distinct keys. `_cacheable()` limits scope to `/api/*` minus the denylist
   (`app/response_cache.py:68-69`); only 200 + `application/json` bodies are admitted
   (`app/response_cache.py:143-152`); the gate is off unless `MASTERMIND_RESP_CACHE_TTL>0`
   (`app/response_cache.py:61-65`, `app/response_cache.py:122-131`).
5. **Cache correctness checks that DO hold** (verified, listed so the absence of a flag is not mistaken for
   an oversight): `/api/portfolio?view=decision_availability` bypasses the cache so its `no-store` and
   per-observation clocks survive (`app/response_cache.py:125-131` — a targeted special case; `app/web.py:1299`
   sets `no-store`); `/api/performance`, `/api/live_marks`, `/api/market_view`, `/api/mastermind_ai*` and
   `/api/pfolio/*` are denylisted (`app/response_cache.py:44-51`); LRU + expired-purge bounds were fixed so a
   full cache cannot wedge itself (`app/response_cache.py:88-106`).
6. **Middleware order verified against the installed library.** `app/main.py:118` installs the cache, then
   `app/main.py:126` installs auth. Starlette `add_middleware` does `user_middleware.insert(0, …)`
   (starlette 1.8.0, `applications.py:107`) and `build_middleware_stack` places `user_middleware` outermost
   (`applications.py:77`), so **auth is outside the cache** — the claim in `app/response_cache.py:13-16` is
   true, and an unauthenticated request cannot populate or read the cache. Not proven by running the server
   (starting the app is out of scope for this lane).
7. **Residual key-collision surface — LOW.** `POST`/`PATCH`/`DELETE` never invalidate the cache: there is no
   `clear()` call from any route (`app/response_cache.py:110-112` is exported but unreferenced in `app/`), so
   within the TTL a mutation (e.g. a settled paper order written by `/api/self_directed/order`) is served
   stale from `/api/self_directed`. `app/response_cache.py:8-10` documents TTL-level staleness as acceptable;
   the self-directed order path is the one place where a user expects immediate read-back, and the code
   comment at `app/response_cache.py:41-43` explicitly granted that guarantee only to `/api/pfolio/`.
8. **Broken flows created by the auth model (product-visible, not security).**
   - `/portfolio_desk` is served to any browser (`app/web.py:3596-3602`, page GET is open) but its only data
     call `GET /api/pfolio/positions` (`app/static/portfolio.html:643`) requires a bearer token on the
     authoritative VPS (`app/auth.py:408-433`) and `portfolio.html` never sends one → the page always renders
     `Failed to load: HTTP 401` (`app/static/portfolio.html:648-652`). `app/auth.py:126-131` documents this
     as the intended cost ("the personal panel is not reachable from a plain browser session"), but the page
     itself still advertises an "Add position" form (`app/static/portfolio.html:829-906`, all 401).
   - The advisor widget is loaded on every page (`app/static/index.html:3207`) and POSTs `/chat` with no
     Authorization header (`app/static/chat.js:448-449`); `/chat` is an LLM operator path
     (`app/auth.py:166-176`) → 401 → `onEvent({type:'error'})` (`app/static/chat.js:469`). Same for the
     Self-Directed order ticket: `POST /api/self_directed/order|thesis|cancel` carry no bearer
     (`app/static/index.html:6303-6304`, `6324-6325`, `6340-6341`) and are operator paths
     (`app/auth.py:179-183`), so V1/V3/V6 for that book are read-only in a browser.
   - `app/account.py` defines 6 routes under `/api/account*` (`app/account.py:193-326`) but `app/main.py:103-112`
     includes only `web.router` and `pfolio.router`, so the account broker is **unmounted in this app** — and it is additionally **orphaned**: it reuses
     `auth._supabase_url()` / `auth._supabase_anon()` / `auth._supabase_decode()` (`app/account.py:59-138`), none of which
     exist in `app/auth.py` (no `SUPABASE` symbol appears anywhere in that module), so mounting it as-is would raise
     `AttributeError` on the first request.
     `account.js` is nevertheless loaded on every page (`app/static/index.html:3208`) and calls
     `/api/account` on same origin (`app/static/account.js:29`, `app/static/account.js:173`) → 404, absorbed
     by the `.catch` at `app/static/account.js:169` and rendered as a signed-out panel; therefore server-side
     theme/lang preference hydration (`app/static/account.js:189-200`) never happens here, and
     `location.href = '/logout'` (`app/static/account.js:459`) targets a route that `app/auth.py:13-14` says
     no longer exists.
   - `app/web.py:3600` still documents `/portfolio_desk` as "session-auth-gated by the same middleware";
     there is no session auth. Documentation drift on a security claim.

## Mobile + i18n

### Mobile

| Page | viewport meta | Breakpoints | Fixed widths >390px | Horizontal-scroll risk |
|---|---|---|---|---|
| `/` `/research` `/self` `/desk` (`index.html`, 9,051 lines) | ✓ `index.html:5` `width=device-width, initial-scale=1, viewport-fit=cover` | 21 `@media` (`index.html:37,65,161,381,582,871,874,904,1719,1740,2264,2269,2340…,2409,2418,2434,2464,2481,2501,2510,2511`); includes `max-width:440px` and `pointer: coarse` blocks (`index.html:2409`, `2418`) and `prefers-reduced-motion` (`1719`, `2434`) | `min-width:1100px`/`1560px` are **padding-only** centre-sets at large widths (`index.html:37-38`, `1740-1742`) — no mobile effect. Real widths are inside scrollers: `.mm-table-wide table{min-width:660px}` (`index.html:2340`) and `.mm-da-evidence table{min-width:760px}` (`index.html:2495`), each with `min-width:0` on the flex/grid parents (`index.html:2492`, `2475`) | **Contained.** `.mm-table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}` (`index.html:561`), re-asserted with `overscroll-behavior-inline:contain` under the mobile block (`index.html:2335-2338`); `@media(max-width:620px)` collapses the evidence table to stacked labelled rows and hides the `<thead>` accessibly (`index.html:2501-2508`), and the decision-availability grid goes 4→2→1 columns (`index.html:2510-2511`). `.mm-hide-sm` columns drop below 640px (`index.html:582`) so Positions shows 5 of 11 columns. The portfolio tab strip scrolls internally and recentres the active tab (`index.html:6416-6425`). Equity chart is `clientWidth`-driven with a `ResizeObserver` (`index.html:4058`, `4258-4266`). A swipe hint is emitted for the scheduler table (`index.html:5502`) |
| `/portfolio_desk` (`portfolio.html`, 1,004 lines) | ✓ `portfolio.html:5` | 4 (`portfolio.html:31,160,310,317`) | `@media(min-width:1100px)`/`(min-width:1360px)` widen the grid only | 4 breakpoints incl. `max-width:620px` (`portfolio.html:317`); tables use the shared `theme.css` wrapping. **Moot on the VPS browser path** — the page renders 401 (Auth finding 8) |
| `/market_view` (`market_view.html`, 562 lines) | ✓ `:5` | 4 (`:28,101,131,272`); pairs grid 1→2 at `min-width:640px` (`:101`) | `@media(max-width:820px)` block at `:272` | Planes table + brief are fluid; no `min-width` table traps found in this file |
| `/agenda` (`agenda.html`, 419 lines) | ✓ `:5` | 3 (`:28,102,246`); `max-width:620px` at `:246` | `min-width:1160px` is a 2-column upgrade only (`:102`) | Cards are single-column fluid |
| `/…` chairman_control `index.html` (313) + `remote.html` (99) | ✓ but **no** `viewport-fit=cover` (`chairman_control/index.html:5`, `remote.html:5`) | 0 in the HTML; 6 in `control_room.css` | `control_room.css` carries the layout | **Not routed by this app.** Served by a separate stdlib process (`scripts/chairman_control_room.py`, `scripts/chairman_control_room_remote.py:32` `DEFAULT_STATIC_DIR`), whose own `/api/state|discover|bind|unbind|refresh-builds` (`control_room.js:230,784,1211,2503,2751,2764,2808`) are outside this route table. `chairman_control/index.html` has **0** `@media` rules and no `l-zh` strings |
| `app/mastermind_os/` | n/a | n/a | n/a | A Vite/Tauri source tree (`package.json`, `src/`, `src-tauri/`) with its own `index.html`; no route in `app/web.py` or `app/main.py` serves it. Whether it is deployed elsewhere is UNVERIFIED |

Touch-target note: `@media (pointer: coarse)` raises control heights (`index.html:2418-2434`), the self-directed ticket forces `font-size:16px` inputs to suppress iOS zoom (`index.html:2341-2343`), and the auto-banner thesis preview clamps to 4 lines under 760px (`index.html:7619-7622`).

### i18n

**Mechanism (three layers, all present):**
1. **Static UI strings** — `var I18N = {...}` (`app/static/index.html:3213` … `~3575`) with `t(key)` reading `data-lang` and falling back `entry[lg] || entry.en || key` (`app/static/index.html:3577-3581`). 336 keys covering perf/positions/trades/pend/sd/desk/research/rd/rp/help/footer.
2. **Inline dual spans** — `<span class="l-en">…</span><span class="l-zh">…</span>` (131 pairs in `index.html`, e.g. `index.html:4714`, `4873`) toggled purely in CSS: `html:not([data-lang="zh"]) .l-zh{display:none}` / `html[data-lang="zh"] .l-en{display:none}` (`theme.css:82-83`).
3. **Server-side content translation** — a file cache, not an LLM call on the read path: `_cached_zh()` wraps `brain.translate.cached_zh` and returns `None` on any failure (`app/web.py:26-32`), backed by `data/brain/translations.json` (`brain/translate.py:38`). It is applied to `disclaimer_zh`, `positions[].research.summary_zh`, `thesis_full._zh{summary,why_now,sizing_rationale,what_would_prove_wrong,bull[],bear[]}`, `rejected[]._zh{reason,bear[]}` (`app/web.py:1428-1471`), decision `summary/sold_note/brain_text/rationale_zh` (`app/web.py:1736-1747`), activity `title_zh/detail_zh` from deterministic maps (`app/web.py:2910-2927`) + cached free text (`app/web.py:2959-2990`), runs `title_zh/summary_zh` (`app/web.py:3083-3090`), posture `posture_label_zh` (`app/web.py:1755-1775`) and papers `summary_zh/report_md_zh` (`app/web.py:1956-1959`). Every consumer falls back to English when the cache is cold (`index.html:4780`, `5078-5082`, `4807-4812`) — nothing renders blank.
4. **Switch + persistence** — `setLang()` sets `data-lang`, persists to `localStorage`, and dispatches a `langchange` CustomEvent (`theme.js:93-106`); `index.html:9011-9016` re-renders every section from already-cached data on that event. Each standalone page seeds `data-lang` before paint from `localStorage` to avoid a flash (`index.html:15`, `portfolio.html:12`, `agenda.html:12`, `market_view.html:12`).

**ZH colour semantics — implemented.** `html[data-lang="zh"]` swaps the palette so red = up and green = down: `--up:#e06464; --down:#45b873` with the comment `/* swapped: red now = up */` (`theme.css:71-73`), plus the light-theme pair `--up:#cf4040; --down:#1f9a55` (`theme.css:76-77`), against the default `--up:#45b873 / --down:#e06464` (`theme.css:20`) / light `#1f9a55 / #cf4040` (`theme.css:50`). Because the whole stack uses `var(--up)/var(--down)` (P&L cells, equity-curve stroke and gradient, verdict/side chips, tab dots), the inversion propagates automatically — including on `portfolio.html`, `agenda.html` and `market_view.html`, which link `theme.css` (`portfolio.html:16`) and therefore inherit **Chinese colour conventions on English-only copy** when the user's stored language is `zh`.

**Pages with no ZH coverage:** `portfolio.html` (0 `l-zh`, 0 `I18N`, 0 `_zh`), `agenda.html` (0), `market_view.html` (0), `chairman_control/index.html` and `remote.html` (0, and no `data-lang` seeding at all). `control_room.js` (131 KB) contains no ZH strings. So V7's market-view and agenda mirrors and V1-alternate desk page are English-only.

**Untranslated content class:** narrative from the Brain is ZH-covered; **numbers/labels coming from the raw artifacts are not** — e.g. the decision-availability detail labels are inline `say(en, zh)` pairs (`index.html:7180`, hard-coded per string, not in `I18N`), and the forward-evaluation strings are likewise inline `say()` (`index.html:7404-7528`), so ZH coverage of those panels depends on hand-maintained bilingual literals rather than a dictionary.

## Render-time read set

Paths are relative to the **Mastermind data root** `_PROJECT_ROOT/data` (`app/web.py:39`, `app/web.py:44-46`).
`<book>` = `autonomous` | `china` | `hk` → `data/portfolios/<book>/` (`portfolio/registry.py:255-285`);
`flagship` → the legacy `data/portfolio/` (`portfolio/registry.py:257-258`); the Self-Directed engine keeps
its own state under `data/portfolio/self_directed/` (`portfolio/self_directed.py:37`) — note this is
`singular portfolio`, a **second location** next to `registry.data_dir('self_directed')` =
`data/portfolios/self_directed` (`portfolio/registry.py:277-278`), and the read path touches both
(`app/web.py:651-656`). **All of these are gitignored** (`.gitignore:10-15`, `25-44`: `data/portfolio/*.json`,
`data/brain/…`, `data/research/`, `data/agenda/`, `data/market_view/`, `data/marks/`, `data/benchmark/`) and
absent from this checkout (`ls data/` → only `brain/ census/ experiments/ portfolio/ signal_archive/`, all
empty of state). **A local render proof therefore needs a seeded fixture data root; none of this state ships
with the source.** The VPS is the canonical writer (AGENTS.md "Repository and delivery workflow").

| View | Files that must exist to render it | Non-file inputs (cache/network) |
|---|---|---|
| **V1** Portfolio overview | `portfolios/<book>/latest.json` (`app/web.py:1298`, `app/web.py:650`), `portfolios/<book>/account.json` (`app/web.py:1340`, `app/web.py:656`), `portfolios/<book>/nav_history.jsonl` (via `/api/performance` fallbacks), `portfolios/<book>/safety.json` (`portfolio/safety.py:885-891`), `portfolios/<book>/positions_ledger.json` (`portfolio/position_log.py:61-67`, via `/api/trades`), `portfolios/<book>/paper_transaction.json` (WAL probe, `app/web.py:2271`), `portfolio/self_directed/account.json` + `theses.json` + `pending.json` (self book only, `app/web.py:1077`, `portfolio/self_directed.py:37-42`) | live marks: `yahoo_feed` in-process cache (TTL `YAHOO_FEED_TTL_SEC`, default 120s, `data_layer/yahoo_feed.py:13`) and the sister Terminal snapshot files `vendor/macro/site/{stockdata,hkstockdata,chinastockdata}/<TICKER>.json` (`data_layer/terminal_prices.py:52`, `:73`); historical closes for `/api/risk` from `config.data_dir()/breadth/_closes_cache.parquet` (`portfolio/safety.py:297`) |
| **V2** Manager decision | `portfolios/<book>/decisions.jsonl`, `account.json`, `pending_target.json`, `nav_history.jsonl` (`app/decision_availability.py:378-386`), `paper_transaction.json` (`app/decision_availability.py:388-395`); for the banner fallback `bot/<book>_decisions` journal via `src.load_decisions(60)` (`app/web.py:1481-1495`, `app/web.py:354-369`); `brain/translations.json` (`brain/translate.py:38`) | run artifacts for provider diagnostics: `data/brain/runs/` via `runlog._RUNS_DIR` (`app/decision_availability.py:396-424`, `app/web.py:1296`); no LLM on the read path |
| **V3** Pending activity | `portfolios/<book>/pending_target.json` (`portfolio/paper_account.py:2625`), `pending_orders.json` (`portfolio/paper_account.py:171`), `fills.jsonl` (`portfolio/trade_history.py:31`), `account.json`, `latest.json`, `paper_transaction.json` (locks the whole snapshot, `app/web.py:2271-2293`); execution-constraints block is read out of `pending_target.json` itself (`app/web.py:2126-2137`) | exchange calendar: `portfolio/market_calendar` (US) / `portfolio/china_calendar` (CN/HK) holiday tables — in-code, no file (`app/web.py:2277-2283`) |
| **V4** Performance | `portfolios/<book>/account.json`, `nav_history.jsonl` (`portfolio/performance_read.py:84-88`), `paper_transaction.json` (same), plus the benchmark series from the macro store for `_load_spy_history` (`portfolio/paper_account.py:1400` → `portfolio/paper_account.py:_fetch_price_series`, `cache_only=True`) → `vendor/macro/data/…` price store + `data/benchmark/` (gitignored) | archived books: only `latest.json` + `account.json` + `nav_history.jsonl` (`app/web.py:139-226`) |
| **V5** Opportunities | `research/papers/index.jsonl` + per-paper files under `data/research/papers/` (`brain/research_paper.py:46-48`), `data/research/notes/` (`app/web.py:1860`), flagship gate join `portfolio/latest.json` (`app/web.py:1912`), shadow/calibration artifacts `data/shadow/rejections/`, `data/shadow/leaderboard.json`, `data/brain/calibration.json` (`portfolio/readiness.py:23-68`), outcome-ledger records (`brain/outcome_ledger`) | Polygon search/quote/company metadata for `/api/self_directed/search|quote` and `_company_meta` → `vendor/macro/site/stockdata/<T>.json` + Polygon (`app/web.py:929-960`) — **network, out of scope for this lane** |
| **V6** Position review | `portfolios/<book>/fills.jsonl` (`portfolio/trade_history.py:31`), `account.json`, `positions_ledger.json` (`portfolio/position_log.py:61-67`), `research/papers/index.jsonl` for the "view full paper" link, `brain/translations.json` for `thesis_full._zh` | none beyond V1's mark sources |
| **V7** Operations | `brain/runs/index.jsonl` + `brain/runs/<run_id>…` (`brain/runlog.py:21-22`), `data/committee/<asof>/<TICKER>/{strategist,forge,sentinel,nexus}.json` and `data/gate_officer/<asof>/decisions.json`, `data/risk_officer/<asof>/decisions.json` (`app/web.py:3122-3136`, `app/web.py:3179`, `app/web.py:3226`), `data/brain/{calibration,reputation}.json`, `data/brain/attribution/_rollup.json`, `data/brain/cio/<week>.{json,md}` (`app/web.py:3355`, `app/web.py:3105-3118`), `portfolios/flagship/watchlist.jsonl` (via `portfolio.watchlist`), `data/market_view/latest.json` + `data/market_view/rotation_tensor.json` (`app/web.py:1787`, `brain/market_view.py`), `data/agenda/<date>.json` (`brain/improvement_agenda.py:52`), `data/deploy_lag.json` (`brain/improvement_agenda.py:830`), forward-evaluation artifacts under `data/portfolios/<book>/` (`latest.json`, `nav_history.jsonl`, `fills.jsonl`, `account.json`, `decisions.jsonl`, `positions_ledger.json`, `post_sell.json`, `run_status.json`, `start.json` — `portfolio/forward_evaluation.py`), `vendor/macro/data/regime/latest.json` (`app/web.py:3580`, `app/web.py:2843`), `vendor/macro/site/{marketdata/subsector_rotation.json, basketdata/flow.json, liquiditydata/global_liquidity_transmission.json, neuralwebdata/mastermind_context.json}` (market-view inputs, `brain/market_view.py`) | `run_events` JSONL tail for scheduler health (`app/web.py:3540-3553`), the live APScheduler instance (`app/main.py:158`), and a `git rev-parse --short HEAD` subprocess per `/api/provenance` call (`app/web.py:3567-3577`) |

**Count for the RETURN block: 48 distinct artifact paths are named above.** Counting rule: a per-book
artifact is one name (`portfolios/<book>/account.json`), the two non-`paper_account` locations the Self-Directed
book adds are counted separately (`portfolio/self_directed/{account,fills,nav_history,pending,theses}`), the
four `committee/<asof>/<TICKER>/{strategist,forge,sentinel,nexus}.json` lanes count as 4, and the vendored
macro inputs (`vendor/macro/...`) count because they are read by render-path code even though they sit outside
the Mastermind data root. Directory-only entries (`research/notes/`, `shadow/rejections/`) count once each.

**Config / env consulted (names only — no values read).** Env vars on the render path:
`MASTERMIND_RESP_CACHE_TTL` (`app/response_cache.py:62`), `MASTERMIND_SERVE_ONLY` (`app/auth.py:208-211`),
`MASTERMIND_VPS_AUTHORITATIVE` (`app/auth.py:213-216`), `MASTERMIND_AUTH_TOKEN` (`app/auth.py:310-311`),
`MASTERMIND_NO_TRADE_BAND_FRAC` (`portfolio/paper_account.py:68`),
`YAHOO_FEED_TTL_SEC` (`data_layer/yahoo_feed.py`), `SUPABASE_URL` (`app/pfolio.py:32`) and `SUPABASE_SERVICE_ROLE_KEY` (`app/pfolio.py:36`); the account broker also expects `SUPABASE_SERVICE_KEY` as an alias (`app/account.py:57-60`), `MASTERMIND_JOBSTORE`
(`app/main.py` startup), `MASTERMIND_OPERATOR_EMAIL`. Scheduler-only names (they change *what is written*,
not what a page reads): `AUTONOMOUS_DAILY_UTC_HOUR`, `AUTONOMOUS_FIRST_RUN`, `CHINA_DAILY_UTC_HOUR`,
`CHINA_FIRST_RUN`, `HK_DAILY_UTC_HOUR`, `HK_FIRST_RUN`, `ETF_FIRST_RUN`, `HEAVYWEIGHT_FIRST_RUN`,
`BOT_DAILY_UTC_HOUR`, `ASIA_SETTLE_UTC_HOUR`, `ASIA_WATCH_UTC_HOURS`, `US_WATCH_UTC_HOURS`,
`CIO_WEEKLY_DAY`, `CIO_WEEKLY_UTC_HOUR`, `AGENDA_WEEKLY_DAY`, `AGENDA_WEEKLY_UTC_HOUR`,
`PREWARM_MARKS_UTC_HOURS`, `PREWARM_MARKS_MINUTE`, `MACRO_SNAPSHOT_UTC_HOURS`, `SETTLE_PENDING_UTC_HOUR`,
`LOOP_MAINT_UTC_HOUR`, `DERISK_US_UTC_HOURS`, `VPS_STATE_SYNC_MINUTE` (enumerated by
`control_plane.flags.enumerate_flags()`, surfaced in the `/health` `app_started` event, `app/main.py:132-137`).
No `.env` file was opened by this lane. Config files consulted on the render path: `config/doctrine.yml`
(`safety:` overlay, `portfolio/safety.py:134`), `portfolio/registry.py` `PORTFOLIOS` (in-source, not YAML —
book list, benchmark, currency, lifecycle all come from it), `config/strategic_state.yml` and
`config/authority_map.yml` are governance inputs and are **not** read by any route handler in this census.

## Recent PR inventory

`git show --stat` for the four merge commits in scope (all dated 2026-10-21 on `origin/master`), summarised
for *what the views actually use*.

**`a0faf7e4` — #1572 "Decision, account and SDK evidence" (26 files, +9,564/-29).** This is the commit that
created V2's evidence layer. It added `app/decision_availability.py` (543 lines) and
`app/decision_availability_selection.py` (518), `app/provider_diagnostic_read.py` (419),
`app/settlement_price_read.py` (247), and rewired `app/web.py` (+34) to mount them as
`GET /api/portfolio?portfolio=<book>&view=decision_availability` (`app/web.py:1271-1300`), with
`response_cache.py` patched (+9/-1) so that view bypasses the cache and keeps its `no-store` clocks. On the
client it is `index.html` +1,172 lines: the four-card "Decision and account status" panel
(`_decisionAvailabilityHtml`, `index.html:7179`), the settlement-price and provider-diagnostic evidence
tables (`index.html:6567`, `index.html:7022`), the identity guard that discards a payload whose
`schema`/`portfolio_id` do not match the requested book (`index.html:8791-8793`), and the banner rewiring
that makes the active-book narrative read the **original accepted memo** rather than a refreshed account
snapshot (`index.html:7548-7551`). It also added the recorded-fixture UI tests
(`tests/test_decision_availability_ui.py`, `test_provider_diagnostic_ui.py`, `test_fx_receipt_ui.py`,
`test_forward_evaluation_ui.py`) plus `tests/fixtures/bot_fx_receipt/{china,hk}.json`. Views that use it:
V2 (fully), V3 (`accepted_target.pending`), V1 (the persisted-account card), V7 (consistency/source coverage).

**`677f4ff2` — #1580 "Evidence-qualified portfolio performance" (11 files, +2,549/-313).** Split performance
into a strict reader and a pure projector: new `portfolio/performance_read.py` (149 lines — bounded,
signature-checked reads of `account.json` / `nav_history.jsonl` / `paper_transaction.json`,
`MAX_BENCHMARK_ROWS = 504`) and `portfolio/performance_projection.py` (619 lines) which computes NAV,
`total_return_pct`, `day_change_pct` + `day_change_window`, `max_drawdown_pct` + `drawdown_window`,
`vs_benchmark_pct`, `realized_since`, gap-preserving `series[]` and the `availability{status, valuation_basis,
history_status, account_history_binding, as_of, issues[]}` block. `portfolio/paper_account.py` was cut by
roughly 300 lines into this shape and gained `unavailable_performance()` (`portfolio/paper_account.py:3448`).
`app/web.py` (+51) now passes 10 extra qualification keys through `/api/live_marks`
(`app/web.py:1174-1182`) and serves the unavailable shape on failure; `data_layer/yahoo_feed.py` (+11) supports
the read; `index.html` (+185) gained `_performanceEvidenceText` (`index.html:3866`), the NAV-label switch to
"Last recorded NAV / Provisional NAV" (`index.html:3936-3940`), the gap-safe area path `_equityAreaPath`
(`index.html:3895`), the window sub-labels, and the deletion of any legacy `account_preview` lacking
`availability` (`index.html:8794-8800`). Views that use it: V4 (the whole qualification story), V1 (NAV/cash
chips). Tests: `test_performance_availability.py`, `test_performance_projection.py` (969 lines),
`test_performance_availability_ui.py`.

**`1b9dc45a` — #1586 "Qualify reported forward mark counts" (2 files, +914/-3).** No web-layer or template
change: all of it is `portfolio/forward_evaluation.py` (+329) plus `tests/test_forward_evaluation.py` (+588).
It introduces the `observation_qualification` object (schema `…observation_qualification.v2`, with the `.v1`
legacy shape still recognised and explicitly labelled), `nav_date_basis.v1` and `calendar_basis.v1`
fingerprints, `price_or_cutoff_qualified`, `calendar_count_unit:
selected_nav_dates_on_scheduled_cash_sessions`, `calendar_missing_reason` and
`reported_mark_count_status` (`portfolio/forward_evaluation.py:1840-2020`), and wraps every status return in
`_qualify_mark_observations` (`portfolio/forward_evaluation.py:2013`). The product surface is the V7
"Evaluation record" panel, which refuses to render the calendar claim unless ~30 cross-checks between the
saved basis, the snapshot and the published calendar agree (`_feCalendarView`, `index.html:7360-7410`) and
otherwise prints "Unverified" / "Count unavailable". Consequence for the census: the mark count the user sees
is now explicitly a *recorded NAV date count*, not a price-validated session count — `price_qualified_session_count`
stays `None` (`portfolio/forward_evaluation.py:1979`) and the panel says "Price-checked sessions: Unverified"
(`index.html:7507`).

**`4e300004` — #1599 "Share cash-session calendars across execution and display" (6 files, +582/-153).** No
UI and no `app/` change: it makes one calendar serve both settlement and display. `portfolio/china_calendar.py`
(+134) and `portfolio/market_calendar.py` (+82) became the single published cash-session authority (US and
CN/HK), while `portfolio/market_clock.py` (−~70) and `portfolio/market_sessions.py` (+42/−…) stopped
re-deriving their own session rules. Views that use it: V1 (the exchange-clock strip and `session.next_open`
via `market_sessions.status_for_portfolio`, `app/web.py:1069`), V3 (`fill_after` = `market_status.next_open`,
`app/web.py:2064`, and the venue-aware status chosen by `registry.venues()` at `app/web.py:2270-2283`),
and V7's evaluation record, which validates saved NAV dates against `…cash_session_date_evidence.v1` from
exactly these owners (`index.html:7387-7395`). `tests/test_session_calendar_consistency.py` (366 lines) is the
new guard that execution and display cannot drift apart.

## Open questions

1. **UNVERIFIED — runtime wiring.** No server was started (lane rule). Route paths, methods, handler
   annotations and response shapes are read statically; the *composed* middleware order was confirmed against
   the installed starlette 1.8.0 source, not against a live request.
2. **UNVERIFIED — whether `/api/*` endpoints listed with no in-repo consumer** (`/api/macro`, `/api/outcomes`,
   `/api/etf/outcomes`, `/api/overnight-tape`, `/api/rejections`, `/api/shadow_bandit`, `/api/readiness`,
   `/api/portfolio_learning`, `/api/provenance`, `/api/firm_allocator`, `/api/desk/experiments`,
   `/api/mastermind_ai*`) are called by the sister Macro Dashboard / Terminal over HTTP. `AGENTS.md` declares
   them one deliberately shared system and `/api/mastermind_ai` is already in the cache denylist as an "admin
   surface", which suggests an external consumer; I did not use the network to prove it.
3. **UNVERIFIED — `app/account.py` provenance.** It is unmounted *and* references `auth._supabase_*` helpers
   that no longer exist (`app/auth.py` contains no Supabase symbols). Whether it is dead-on-purpose (Supabase
   moved to the Macro side) or a broken merge is not decidable from this tree; `tests/test_secret_redaction.py`
   is the only file that imports it.
4. **UNVERIFIED — the `data/portfolio/self_directed/` vs `data/portfolios/self_directed/` split.** Both
   locations are read (`portfolio/self_directed.py:37` vs `portfolio/registry.py:277-278`). Whether the plural
   directory holds a real file for that book in production, or is vestigial, needs a VPS state read, which this
   lane may not perform.
5. **UNVERIFIED — `app/mastermind_os/`** (Vite/Tauri + `public/`, `browser-proof.html`, `src-tauri/`): no route
   in `app/web.py`/`app/main.py` serves it. Deployment status unknown.
6. **UNVERIFIED — same question for `app/static/chairman_control/`**: the census confirmed it is served by the
   separate stdlib control-room process (`scripts/chairman_control_room_remote.py:32`), but not whether that
   process is running or reachable, nor whether its `/api/*` contract overlaps this app's.
7. **Open product decision — V5 for the product book.** `#rejected` is hidden and the Research tab is gated to
   `flagship` (`index.html:6454-6463`) while `/api/portfolio` still publishes `rejected[]` for the Brain books.
   Is that intentional (Brain books have no engine-gated finalists) or is it a V5 gap that W9 must close? The
   packet's V5 requirement ("researched finalists, rejection reasons, entry readiness, source coverage") cannot
   be met for `autonomous` from the current UI without a decision either way.
8. **Open product decision — horizon and next-review condition.** Neither `/api/decisions`, nor
   `decision_availability`, nor `thesis_full` carries a structured horizon or a check-by/review date, although
   `DOCTRINE.md` (Stage 0-4 lifecycle + time stop) and V2/V6 both require them. Whether the data exists in a
   writer artifact that no route exposes (e.g. `position_log` stage fields, `portfolio/stages.py`) was not
   traced to a route in this pass — `app/web.py` renders no `stage_review` field.
9. **Scope question — archived books.** `_archived_performance()` emits no `availability` object and coerces
   two unknowns to `0.0` (violations #7, #8). Flagship/heavyweight/etf still appear as tabs
   (`portfolio/registry.py:33-45`, `_PF_ORDER` at `index.html:3838`). If the product contract applies to
   archived history too, these need the same qualification treatment; if not, the census should say so
   explicitly rather than leave the asymmetry implicit.
10. **Deliberately not run.** No pytest suite, no `bot`, no app server, no `.env` read, no network call, no git
    write. Every statement above is from reading files in this worktree at `230e9a301`.
11. **Lane-hygiene note.** One scratch file, `/tmp/rt.md`, was written by an enumeration command early in this
    pass before I switched to generating the route table directly into the deliverable. It is outside the
    worktree, contains only the generated markdown table (no credentials or private data), and no tracked file
    in this repository was created, edited, moved or deleted.


## Orchestrator verification (pbr-product)

Added by the orchestrator `pbr-product` after the lane returned. Everything above this heading is the lane's text, unchanged (lane `pbr-p1-census-r4`, ubuntu1, qwen3.8-flash, class census C1, base `230e9a301`, artifact sha256 `37f100c9e6a2a5db677eec2ada565fe4a9743b0c69e353d0530b933599a12198`). Where a finding below conflicts with the lane text, this section wins.

### Spot-checks against `230e9a301` (read with `git show`)

| # | Census claim | Result |
|---|---|---|
| 1 | Truth violation 1: `app/web.py:2424` returns a $1,000,000 all-cash account on exception | confirmed |
| 2 | Truth violation 2: `app/static/index.html:5980` falls back to `1000000` for a missing `nav` | confirmed |
| 3 | Truth violation 3: `index.html:4507-4509` coerces missing sleeve weights with `|| 0` | confirmed |
| 4 | Truth violation 10 / Summary 7: `app/web.py:1912`, `2947`, `2980` read the archived flagship tree `data/portfolio/` | confirmed |
| 5 | Truth violation 22 / Summary 8: `GET /api/self_directed/history` settles and writes (`portfolio/self_directed.py` `history()` calls `settle_pending()` first) | confirmed |
| 6 | Summary 9: the response cache key is path plus canonicalised query only (`app/response_cache.py:72-83`) | confirmed |
| 7 | Summary 4 / gap map V5: Research and Desk navigation are hidden unless the book is flagship (`index.html:6454-6463`) | confirmed |
| 8 | Truth violation 11: "TR2 compliant" | **wrong; see the correction below** |

Result: 7 of 8 confirmed, 1 factual error.

### Correction to truth violation 11 (TR2)

The lane checked the API and stopped there. The API half is correct: `/api/trades` maps a held ticker whose target weight is 0 or below to `action:"exit"` (`app/web.py:2174-2180`) and lists it as a pending order. The rendered held row does not use that information. `renderPositions` takes its verdict chip from the strategy snapshot:

```javascript
var verdict = (p.verdict || 'hold').toLowerCase();   // index.html:4731 at 230e9a301
```

So a held name with a queued exit still shows **HOLDING** in the Positions table unless the snapshot's verdict happens to say otherwise. The 2026-10-22 read-only capture (off-repo, see below) shows exactly this: MU rendered as HOLDING while the US book's queued target excluded it.

The correct reading is that TR2 is **violated on master** for the Positions view, and V3 Pending activity is compliant only in the Trades block. The fix is PR #1707 (L-P3a, `_heldPendingChange`), which shows "EXIT QUEUED" plus "fills at open <date>" on the held row and never guesses a direction for an unpriceable or comparison-unavailable row. Summary item 5's "TR1/TR2/TR3 met there" holds only for the API and the Trades block.

### Finding the lane missed (TR4, flat line)

The read-only capture shows the US book's latest two NAV-history rows with identical values on consecutive dates. The overview renders that as "Last observed change +0.00%", presented like a measured day with no movement. This is the §10.2 case "Do not visually reward a missing-price flat line as low volatility": when a row is carried, unattested or unpriced, the day is unqualified. It is not a 0.00% day. It belongs with truth violation 8 (`_archived_performance` +0.00%) and is consumed through ECON A02 (`nav_status`, `carried[]`, `nav_withheld.jsonl`). See `CONTRACT_REQUESTS.md` E1-E5.

### Lane hygiene

- The lane's last message was a prose "STATUS: COMPLETE" summary, not the required RETURN block. The artifact itself was complete, so it was accepted after verification, and the missing RETURN is recorded against the lane.
- The census contains no account quantities. `$1,000,000` is the literal value fabricated by the code under review, and the other numbers are source line references.
- Evidence for the capture-based findings is kept off-repo because this repository is public: `/Volumes/Mastermind/evidence/pbr/product-capture-20261022T073304Z/` (MANIFEST sha256 `898d41f4219cdc18e657a81b7df95b4d905d80c33c88be77bae9ef4f19ada513`).

### Census findings that need a decision above PRODUCT

These go to the seat. PRODUCT does not act on them alone.

1. V5 Opportunities cannot be reached for the product book (`autonomous`). Exposing it is a navigation and IA change to a shipped view, which is reserved for the seat.
2. No holding has a `horizon` or a next-review condition (V2/V6). This is a RESEARCH field, requested as S5 in `CONTRACT_REQUESTS.md`.
3. `/api/activity` and the research-paper join read the archived flagship tree (truth violation 10). This is a PRODUCT-owned `app/web.py` read and a candidate truth fix. It changes which book's narrative is shown, so it ships as its own bounded PR with an agreement test.
4. `GET /api/self_directed/history` writes account state (truth violation 22). A GET with a settlement side effect is a lifecycle question for RUNTIME and ECON, not a display fix.
5. The anonymous, cacheable `self_directed` personal book (Summary 9) is an auth/cache change, which is reserved for the seat.
