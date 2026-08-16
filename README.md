# Mastermind

A seven-book, paper-only portfolio operating system spanning US, ETF, mainland
China, Hong Kong, concentrated, and self-directed mandates. Reasoning agents
analyze and propose; deterministic engines own sizing, caps, settlement, marking,
and binding release gates. The system never auto-executes broker trades.

This is one of three first-class Mastermind-X repositories alongside Macro
Dashboard and Mastermind Terminal. It consumes bounded Macro context and publishes
privacy-whitelisted paper state and accountability back through Macro.

## Architecture (one sentence)

Macro evidence and context → manager reasoning → deterministic controls → seven
paper books → decision/outcome ledgers → sanitized Macro publication. Reasoning
may propose intent but cannot bypass deterministic portfolio authority.

```
Mastermind/
  app/               FastAPI product, operator routes, dashboard, scheduler
  bot/               scheduled paper-book builders and orchestration
  brain/             reasoning, Macro adapters, accountability, operator AI
  portfolio/         book registry/state, deterministic sizing, risk, marking
  loop/              offline research and forward-paper qualification
  control_plane/     contracts, authority modes, packets, locks, governance
  data_layer/        Macro refresh, data reads, storage, price snapshots
  bridge/            sanitized snapshot, feedback, and Macro publication
  config/            doctrine, mandates, providers, contracts, authority modes
```

## Status

Operating paper system with seven current books: Flagship, Heavyweight, US Brain,
ETF Brain, CN Brain, HK Brain, and Self Directed. Open pull requests are proposed
overlays, not current `master` behavior.

Start with `AGENTS.md` for authority and delivery rules,
`research/MASTERMIND_CHARTER_V2.md` for the canonical charter, and
`docs/DELIVERY_WORKFLOW.md` for operations. The first unarmed
frontier-lead/economical-worker routing layer and rollout path are documented in
`docs/EXECUTIVE_WORKER_ROUTING.md`. `README.md` is orientation only.
