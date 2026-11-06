# V28 — frozen V24 execution-stress surface and cross-cohort transport audit

**Evidence status: inspected DEVELOPMENT data, not an independent SOXX holdout.** This is a reproducible, source-hash-pinned read of the **already published 120 aggregate V24 CSV cells** (4 groups × 2 fixed checkpoints × 3 fixed five-minute-open execution delays × 5 additional adverse sell stresses). It does **not** rerun v2–v24, read historical bars/private execution rows, acquire vendor quotes, choose an optimized delay, revise stops or enable trades.

Original aggregate: \`early_failure_v21_v24/EXECUTION_STRESS_V24.csv\`, immutable SHA256 \`4622211616c99d6f3a68d14250cf85b35e981f1ab8f459962d57fff78473549e\`, 6,787 bytes, exactly 120 rows. Original fixed entry/stop/partial/horizon and execution assumptions remain inherited from the V24 result. The word **0bp** below means **zero *additional* adverse sell-slippage penalty**, not free execution. Values are mean **percentage-point original-position incremental returns per original episode** relative to the existing benchmark.

## 1. Direct fixed-arm results — all 91 original development episodes

Do not select a winner after seeing this grid. Each column represents one *already-fixed* hypothetical opening delay, not a separate independent sample.

| Original checkpoint | Added sell penalty | Delay 1 × 5m | Delay 2 × 5m | Delay 4 × 5m | Positive delays |
|---|---:|---:|---:|---:|---:|
| 30 minutes | 0 bp | +0.141368 | +0.192650 | +0.157419 | **3/3** |
| 30 minutes | 25 bp | +0.063571 | +0.128432 | +0.093248 | **3/3** |
| 30 minutes | 50 bp | **−0.014226** | +0.064213 | +0.029078 | **2/3** |
| 30 minutes | 100 bp | −0.169821 | −0.064223 | −0.099263 | **0/3** |
| 3 observed RTH hours | 0 bp | −0.015013 | +0.048620 | +0.007561 | **2/3** |
| 3 observed RTH hours | 10 bp | −0.037716 | +0.025914 | **−0.014036** | **1/3** |
| 3 observed RTH hours | 25 bp | −0.071771 | −0.008145 | −0.046431 | **0/3** |
| 3 observed RTH hours | 50 bp | −0.128529 | −0.064911 | −0.100424 | **0/3** |
| 3 observed RTH hours | 100 bp | −0.242044 | −0.178443 | −0.208409 | **0/3** |

The 10bp row is the published 3h grid to verify, not an independently fitted “just-right” cost. The critical stability result is **3h: 0/3 positive at +25bp**, versus **30m: 3/3 positive at +25bp**. At +100bp, **neither checkpoint has any positive all-assets delay**. This directly falsifies blanket statements that the same inspected early-exit effect is insensitive to adverse execution.

The 30m delay-1 frozen path remains the already-derived example: +0.141368pp at 0bp, −0.014226pp at 50bp, and a *retroactively interpolated* zero near +45.43bp. **That number is not a recommended slippage setting, validated threshold or marketable spread.** All six fixed arms must remain in the eventual independent report, whether good or bad.

## 2. Group disagreement — pooled success does not establish transport

The source partitions all 91 original episodes into \`inspected\` (34, includes **SOXX, SMH, QQQ, AMD**), \`new_semis\` (47), and \`sector\` (10). None is 91 independent time observations; *inspected is not SOXX-only*.

At the **3h checkpoint, 0bp additional**:

| Fixed delay | Inspected (34) | New semis (47) | Sector (10) | Pooled (91) |
|---|---:|---:|---:|---:|
| 1 × 5m | +0.209098 | −0.128629 | −0.242994 | −0.015013 |
| 2 × 5m | +0.273255 | −0.051066 | −0.246613 | +0.048620 |
| 4 × 5m | +0.197463 | −0.078448 | −0.233861 | +0.007561 |

The 3h “pooled positive” at delays 2/4 is largely a property of the inspected 34-name-combined cohort; **all three** 3h delays are negative on **new semis and sector** even before extra sell stress. At 30m, all three new-semis delays are positive at +50bp, but the sector delays are already negative at +0bp. Those are source-specific descriptive facts, not independent sector replication; trading exposures overlap and regime alignment is unresolved.

Consequently **no universal 3h exit edge is established** and a 30m edge is **not robust across all instrument groups and realistic unproven execution paths**. The only legitimate next performance test remains the *preregistered* 30m and 3h original-parent policies on genuinely untouched SOXX episodes with actual complete source/clock/marketability evidence. Do not select delay 2 because it looks better in the inspected year or drop unfavorable groups.

## 3. Reproducible integrity checks

Offline audit module: \`prospective_validation_v26/stress_surface_v28.py\`; 20 focused synthetic corruption, cross-publication and frozen-aggregate tests: \`tests/test_soxx_v28_stress_surface.py\`. Source readback must match the exact original V24 SHA256 before publishing output.

The checker validates the complete 120-cell key space, fixed per-group original denominators (91 = 34 + 47 + 10), stable elected sales by arm across extra-cost assumptions, each fixed group contribution to the pooled mean and winner-harm/loss-save counts, worst/best episode extrema, and linear non-improving incremental cost stress (within source's six-decimal rounding). Mutation tests reject duplicates, omissions, fake new delays, changed denominator, changed subgroup mean, spurious positive cost response, shifted selected-sales count, nonfinite values and altered archived bytes. It **never** calls the historical v24 simulator.

The returned \`evidence_claim\` is **\`INSPECTED_DEVELOPMENT_AGGREGATE_ONLY_NO_INDEPENDENT_EDGE\`** and trading/live-fill flags remain false. A successful audit verifies arithmetic **inside the frozen reported aggregates**, *not their price provenance*, data licence, strategy robustness, independence, prediction, live marketability, or profit at funded size.

### Second publication-format and specification witness

The first audited snapshot was the immutable CSV. V28 now **also** hash-pins the *separate original* V24 \`RESULTS_V24.json\` (SHA256 \`070be15b276b052029c5d6dbb86029899ddab0c4b65138c91bc6f4b759ad5030\`, 45,534 bytes) and the predeclared \`SPECIFICATION_V24.json\` (SHA256 \`b3d6032ff3f3b3a4edc354cfd5afd0de8df4d589c81aa4403be0881fe232d568\`, 1,891 bytes). The original JSON contains **exactly the same 120 V24 aggregate cells**, with all **11 field values** in each row agreeing with the CSV, and points to the exact pinned specification SHA. This uses three *public published research artifacts*, **not** private historical price or execution rows.

The original JSON inventory lists **12 source instruments / 91 parent entries**, including **SOXX 11**, and zero unresolved original source rows. Crucially, the same original result also explicitly sets \`NO_AUTHENTIC_BOATS_HISTORY=true\`, \`raw_quote_price_fills_proven=false\`, \`branch_production_change=false\`, and \`copied_5m_data_outside_archival_owner=false\`. Those negative source gates are preserved instead of converting a mathematically consistent 120-cell table into “live” BOATS fill proof.

Five additional unit tests were RED before cross-artifact implementation (missing witness API and metadata); the repaired implementation passed **20/20 focused tests**, including corrupted original-result SHA, altered 120-cell JSON economics, unauthorized claim of genuine BOATS history and an inflated SOXX episode inventory. CSV and JSON are **two serialized outputs of the SAME inspected simulation**, not independent measurements or replication. Matching them is evidence against unintentional report drift and forged bookkeeping only; it is not a second independent historical study.

## 4. Source and acceptance gates unchanged

- The V26/V27 online causal clock and prospective source specifications, stop/partial accounting, 52 observed RTH-hour horizon and two-claim familywise uncertainty rule remain controlling.
- The incumbent Macro Data OS remains the only producer/credential/archive owner. The last source-qualified BOATS historical REST bar inventory had AAPL/AMD only, SOXX zero; an existing ~9-minute SOXX native Q/T burst is not a qualified full night. Original [Macro #8698 comment 6137771857](https://github.com/mastermindx-market-intelligence/macro/pull/8698#issuecomment-6137771857) remains the single request to consume.
- Terminal [#955](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/955) source-merged its separate BOATS Quote Hub display, but source merge or synthetic screenshots are not installed live market-data or a historical bid/ask archive.
- **Open independent-market SOXX economic-validation episodes: zero** as of this audit; no trade, source read, raw licensed row, producer schedule, privileged vendor request or duplicated Fabric worker was created.

### Correct use

This V28 result is a **negative/fragility calibration for interpreting historical claims and an integrity diagnostic for the new study**. It is not a new candidate entry/exit signal, not a selected winner, and not any reason to revise the frozen prospective decision thresholds after reading the inspected grid. The decision to use or reject an early exit requires unseen full-episode, source-qualified benefit-minus-harm including true fill uncertainty.
