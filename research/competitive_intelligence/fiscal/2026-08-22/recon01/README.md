# Fiscal.ai Authenticated Reconnaissance — Run 01

Research-only evidence collected through the legitimately authenticated Fiscal.ai Pro trial on 2026-08-22/23. This manifest records observed product behavior; it does not assess strategy or recommend features.

## Evidence index

- `observations.jsonl` — one structured record per observation.
- `interaction_ledger.md` — ordered account of the tested workflows.
- `route_and_context_map.md` — observed transitions and context persistence.
- `gating_null_failure_states.md` — observed absence, entitlement, and failure semantics.
- `unresolved_questions.md` — questions requiring a targeted follow-up run.
- `evidence/screens/` — focused screenshots named by observation ID.

## Scope

Companies: NVDA, AMZN, JPM, QUIK, with one logical peer only where a lane required it. Browser-network inspection, private endpoints, access-control bypasses, broad public-feature rediscovery, and strategic analysis were excluded.

## Run facts

- Authenticated surface: Fiscal.ai v5.9.4 in the user's existing Chrome session.
- Observation records: 32 (`OBS-001`–`OBS-032`).
- Focused screenshots: 30 PNGs.
- Copilot interactions: 0. No Copilot entry point, prompt box, or labeled control was visible in the authenticated navigation or inspected live controls; the IR `Custom Prompt` panel was not substituted for Copilot.
- Persistent object created: company-specific AMZN custom metric `MMX CapEx to Revenue` (`Capital Expenditure / Total Revenues`).
- Dashboard mutation: the supplied empty dashboard received one NVIDIA entity through the visible picker. The picker displayed the U.S. entity but saved `BUL:NVD`; deletion is intentionally pending operator confirmation because it is cloud-data deletion.
- Explicit paywall dialogs: none encountered. Absence, delayed hydration, `No metrics found`, and empty data surfaces are therefore recorded separately from entitlement denial.

## Directly observed coverage

- Lane A — company information architecture and context persistence: covered.
- Lane B — estimates, revisions, beat/miss semantics, and charting handoff: covered; Copilot parity unavailable.
- Lane C — cross-document search and exact-hit traversal: covered.
- Lane D — IR transcript/report/slides/audio workspace: covered.
- Lane E — dashboard News, notifications, and `What's happening`: covered for NVDA; multi-company dashboard comparison was stopped after the listing mismatch.
- Lane F — segments/KPIs and custom-metric lifecycle: covered.
- Lane G — insiders, institutional holders, filing provenance, letters, and investor detail: covered.
- Lane H — Owner Mode: covered on NVDA and QUIK; restored to off.
- Lane I — sparse/null and as-reported semantics: covered on QUIK.
- Lane J — Copilot parity: unavailable because no Copilot surface was exposed; zero prompts were spent.

## Evidence-reading note

Several surfaces hydrate in stages. A shell, blank table, or em-dash overview state was not treated as terminal until a bounded wait and re-read. The AMZN custom metric is the clearest example: it was absent at the first post-reload read and then reappeared without another user action.
