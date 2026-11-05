# Unresolved questions

Questions that could not be answered without a targeted follow-up investigation.

1. Why is Copilot absent from the authenticated v5.9.4 navigation and live controls: plan entitlement, rollout flag, account configuration, geography, or a renamed entry point?
2. If Copilot becomes available, does it read the same NVDA annual revenue consensus, revision history, and beat/miss values shown in Estimates, and what source links does it return?
3. Can Copilot query the cross-document corpus and the company-specific `MMX CapEx to Revenue` metric, or does it fall back to web/search data?
4. Does the QUIK Revenue Estimates surface represent zero analyst observations, unsupported company coverage, a delayed request, or a rendering defect? No explanatory state was shown.
5. Can the dashboard picker be forced to the displayed primary listing, and why did selecting the visible NVDA entity persist `BUL:NVD` while notifications still projected NVIDIA content?
6. With deletion approval, remove the unintended `BUL:NVD` dashboard row and verify whether notifications return to the explicit empty state.
7. Is there a supported way to name the supplied dashboard/watchlist `MMX_FISCAL_RECON_01`? No naming control was visible on the empty or populated dashboard.
8. Can a company-specific custom metric be converted to global scope after creation without rebuilding it? The creation toggle was left off; NVDA's reuse search could not find it.
9. Does recreating the metric with `Apply Metric to all companies` make it available in Charting and Screener, or only in other companies' Custom Metrics tabs?
10. Is there a direct ownership-holder → investor-profile route for mapped entities? Holder names were inert while filing provenance was actionable.
11. Is there a dedicated quarter-over-quarter management-message comparison on another event type or route? It was not present in NVDA Q1 2027.
12. Are document-search results universe-wide without selecting a company, and can results be saved/exported/compared? The tested query used NVDA and exposed no save/export/compare controls.
13. Do Notifications apply a deliberate subset of dashboard News (for example, `Measurable Impact` plus selected research), and is the rule configurable?
14. What does Owner Mode compute or suppress beyond adding the Business Owner Mode projection? It preserved the standard company tabs and most overview content in both tested companies.

## Raised by the evidence-packaging repair

These were found by inspecting the captures before removing them, not by a new
run. They are unresolved because Run 01 cannot be replayed and this repair was
not permitted to open a new session.

15. Was the QUIK Revenue Estimates surface ever actually empty? The OBS-011 record says nothing rendered after bounded waiting; its own capture showed a populated chart and table. If the surface hydrated late, question 4 is a latency question rather than a coverage question, and the run's only `negative` estimates finding is wrong.
16. Did the as-reported switch described in OBS-012 get captured at all? The archived frame showed a single charted revenue series rather than the issuer-worded sparse rows the record describes, so the as-reported presentation claim rests on the record alone.
17. Should a future run capture evidence in a rights-safe form at capture time — cropping to interaction chrome, empty states and failures as it goes — rather than taking full-frame captures that later have to be destroyed? Run 01 produced 30 captures of which 25 could not lawfully be kept.
