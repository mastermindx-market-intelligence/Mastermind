# Commission 7 — hardening findings and disposition

Date: 4 October 2026. Original line numbers refer to the byte-preserved `source_report.original.md`, not the rewritten report. **Severity denotes importance to accepting this research/handoff, not a reproduced production incident.** “Corrected” means corrected in this report; it does not mean a corresponding production capability was implemented.

| ID | Severity | Original location | Finding | Hardening disposition / verification |
|---|---|---|---|---|
| A01 | P0 | B, lines 8–13 | Blanket absence claim conflicts with existing K1 evidence contracts and owner-specific lineage. | **Corrected.** New B names pinned sources, source-present versus live distinctions and unmeasured coverage. [R1–R5] |
| A02 | P0 | E/G/L, lines 43–58, 80–100, 167–171 | New lineage database/engine duplicates existing ownership without a committed consumer or measured need. | **Replaced.** Existing readers, refs, blocks and recipes first; K1 physical-store gate preserved. |
| A03 | P0 | C/F/H, lines 16, 24–26, 67, 117 | Orthogonality, zero correlation and statistical independence are conflated. | **Corrected and mathematically checked.** Nonlinear and XOR counterexamples; distinct PCA/ICA/CCA interpretation. |
| A04 | P0 | G/J/K/L, lines 86, 139–141, 158, 167 | “One per highly correlated cluster” can destroy useful information and is not globally justified. | **Rejected as a universal policy.** Near-clone counterexample and task-specific comparison replace it. |
| A05 | P0 | J/K, lines 139, 162 | Implied immediate automatic duplicate blocking violates documented K1 v1 effect limits. | **Corrected.** Even exact-duplicate labels remain manual/descriptive; future automatic effects need accepted versioned semantics. |
| A06 | P0 | E, line 50; C, line 18 | Computational ancestry is called a causal provenance graph; causal/lineage/statistical edges blur. | **Separated.** Relation types, evidence grades, and economic hypothesis authority remain distinct. |
| A07 | P0 | E, lines 46–56; D, line 41 | Generic timestamps and feature IDs cannot reproduce actual historical knowledge and fits. | **Expanded.** Native seven-clock mapping, actual replay versus PIT reconstruction versus current-rule recomputation; fit and family revision lineage. |
| A08 | P0 | L, lines 167–173 | No explicit source authenticity, identity-bridge or authority boundary on proposed consumer use. | **Expanded.** Native identity, hashes versus authenticity, no caller key authority, known AAPL refusal, all-false effects. |
| A09 | P1 | C, lines 16–26; F, line 73 | Weak/unsourced quotations and dangling [52]/[53] references support broad prescriptions. | **Replaced.** Primary references and source-limited claims. Feast integration separately verified as real; not all original claims were rejected. |
| A10 | P1 | D, lines 30–41 | Generic history/latency/PIT/correction/rights table blends products and unverified access. | **Replaced.** Product-specific qualification, EOD versus intraday options, actual entitlements and corporate-action vintage. |
| A11 | P1 | B/D, lines 11, 34–36 | Holdings are treated as flow evidence; reported facts and commercial normalized products are conflated. | **Corrected.** 13F filing delay/holdings scope, source/normalization distinction, no inferred transaction tape. |
| A12 | P1 | B, line 11 | Absolute analyst-revision gap risks rebuilding an active source/consumer programme. | **Qualified.** Existing #8309/#8312/#8337 carriers preserved; no new acceptance or normalized PIT claim. |
| A13 | P1 | F, line 67; K, line 156 | Adding canonical components as extra features can count an invertible representation twice. | **Corrected and checked.** Distinguish replacement/joint model inputs from independent observations. |
| A14 | P1 | H, lines 109–111 | Ablation or incremental regression performance is presented as an independence test. | **Corrected.** Task-relative predictive gain, model capacity, conditional test assumptions/power and interaction examples. |
| A15 | P1 | H, line 117 | “True independent dimension count” is inferred from effective rank. | **Corrected and checked.** Participation ratio versus variance-equivalent count; neither certifies independence. |
| A16 | P1 | E/K, lines 54, 154 | A fixed absolute-correlation threshold is suggested without population, uncertainty or nontransitivity controls. | **Expanded and checked.** Explicit sampling/horizon/missingness, PSD validity, uncertainty and correlation-chain counterexample. |
| A17 | P1 | H, lines 105–115 | Validation lacks source eligibility, mature labels, overlapping-event splits, selection budget and final untouched evaluation. | **Expanded.** Separate correctness/source/utility/production verdicts, preregistration, temporal purge, support/power and trial accounting. |
| A18 | P1 | H, lines 107, 117 | Sharpe improvement is an insufficient acceptance target and a naive raw-vote comparator is weak. | **Replaced.** Unchanged incumbent, traceability-only, gated exact-identity policy and dependence-aware comparator; proper losses and costs where relevant. |
| A19 | P1 | I, lines 126, 132 | Corrections and backfilled taxonomy/fit changes lack end-to-end invalidation and replay invariance. | **Expanded.** New eligible receipts, preservation of past decisions, fit-ancestor invalidation and future-extension tests. |
| A20 | P1 | D/E/I, lines 39–41, 46–58, 132 | Rights are generic; graph topology/caching and model-training leakage are missing. | **Expanded.** Purpose/tenant bounds, lawful tombstones, no public-URL upgrade, modern-model historical-knowledge caution. |
| A21 | P1 | I/J, lines 124, 139–143 | Statistical alarms risk silently changing portfolio exposure or family policy. | **Corrected.** Diagnostic alerts and policy effects require separate consumer approval and empirical gates. |
| A22 | P1 | K, lines 149–160 | Calendar-week schedule implies capacity/dependency knowledge not established by the research. | **Replaced.** Six owner/consumer/source/evaluation/rollout exit gates, not invented deadlines or parallel workstreams. |
| A23 | P1 | L, lines 165–173 | Generic engineering/CDO ownership does not reflect current programme/path custody. | **Replaced.** Existing workstream and owner-native admission; organisational role is not a live source lease. |
| A24 | P0 | L, line 173 | “Guarantees … never double-counts” overstates what incomplete lineage and finite statistical tests can establish. | **Removed.** Scoped invariants, explicit unknowns, authority ceilings and separate production proof. |

## What remains unresolved

The pass did not establish full producer instrumentation, current source-lease availability, a real Portfolio V3 consumer path, source rights for a new use, a valid cross-type bridge, a native implementation defect, a fresh pass of the repository suites, a profitable policy, or production behaviour. The deeper source-read safety block was not bypassed. These limits are explicit in the final report; they are not silently filled with memory or generic architecture.

## Supersession

`FINAL_REPORT.md` replaces the attachment's research/handoff prescriptions **for this submitted hardening package**. It does not supersede protected repository law or automatically adopt a new schema. The source report remains immutable historical input, including its unsupported statements. Repository references [R…] and external references [S…] resolve in the final report's source register.
