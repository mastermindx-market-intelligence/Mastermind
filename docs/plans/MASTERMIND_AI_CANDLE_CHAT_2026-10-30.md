# Mastermind AI chat — inline candlestick explanation diagrams

- Operation: `mastermind-ai-chat-candle-diagrams-20261030-sol-001`.
- Task-tree owner: `mastermindx-market-intelligence/Mastermind`; path: `docs/plans/MASTERMIND_AI_CANDLE_CHAT_2026-10-30.md`.
- Protected procedure: `master@bb85b429f2ffffd38408080ce4df7d6378c34100`, `docs/sol_skills/INDEX.md` schema `mastermind.sol_skillpack.v1`, version 1.0.1.
- Current source base: `master@bb85b429f2ffffd38408080ce4df7d6378c34100`.
- Product entry: `app/static/index.html` loads `/chat.js` from `app/web.py`; `app/main.py` streams `/chat`, and `brain/advisor.py` stores assistant text for history.
- Chairman outcome: Mastermind AI chat draws legible candlestick diagrams inline, showing a downtrend, pivot candle, trigger, stop, breakout, and a readable explanation like the provided 30-minute example.
- DONE_WHEN: A user can request an illustrative bullish or bearish setup in actual Mastermind AI chat, see a semantically correct inline chart responsive on mobile, reload the conversation and see the same chart, with an honest illustration label. Invalid/chart-injection payloads do not execute scripts or corrupt ordinary chat; independent review, exact-head CI, and real signed-in browser evidence qualify release.
- Source custody: this isolated PR branch; adjacent open Draft #1454 also changes `app/static/chat.js` (paper-selection concurrency), and must be reconciled before protected merge, not overwritten.
- Organizational link: an exact Agent OS workstream is not yet grounded. This GitHub source tree is not a write to Agent OS or Executive OS.

## Task hierarchy

| ID | Dependency | Scope and acceptance | Editorial status |
|---|---|---|---|
| P1 | current protected source and zero new runtime authority | Inspect chat streaming, rehydration, and chart-data authority; choose fenced schema and no unverified live OHLC. | accepted (source inspection, 2026-10-30) |
| P1.T1 | P1 | Add `app/static/candlestick-chart.js`: bounded schema validation, bullish/bearish pivot contract, safe SVG renderer, accessible summary, labels and responsive themes. Tests reject bad OHLC and hostile text. | ready |
| P1.T2 | P1.T1 | Wire only assistant textual `mmx-candles` fenced objects into stream and history; keep ordinary text, papers, tools, new-chat, errors and chartless flows intact. | proposed |
| P1.T3 | P1.T2 | Supply a constrained system prompt explaining the schema, label illustration, refuse invented historical OHLC, and keep output non-executing. | proposed |
| P2 | P1.T1-P1.T3 | Automated positive/negative tests; independent non-author review and exact-head CI; reconcile concurrent `chat.js` review before merge. | proposed |
| P3 | P2 | Real authenticated page test (desktop/mobile), verify request→chart→reload and theme/keyboard semantics. Protected merge/production deployment only with normal gates. | proposed |

### Contract and held scope

The `mmx-candles` JSON fence is a **display instruction**, never a portfolio command. Mode v1 is `illustration` only, with 4–48 artificial candles and one pivot; no dates, symbols, source citations, price quotations, model-origin market history, order tickets, order sizing, or new feed are inferred. The renderer does not fetch data, mutate the book or write to a second authority. A future observed-OHLC mode must obtain typed, source-attributed bars from an existing approved market-data owner, with timeframe/timezone/session and provider as-of/freshness before it can be labeled live.

Review/release falsifiers: visible fabricated prices presented as real; malformed OHLC accepted; annotation semantics disagree with candles; cross-site scripting through title/labels; chart missing after rehydration; pending partial fences flood the chat; narrow mobile view clips annotations; an existing paper/auth/chat path regresses. Separate the source-built/CI/merged/installed/real-page states.