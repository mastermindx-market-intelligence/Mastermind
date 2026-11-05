# pbr-p2-spec-review — r1 (independent review of the L-P2 frozen view spec)

- Unit: L-P2 view spec, `docs/superpowers/specs/2026-10-22-pbr-product-views.md`, PR #1744 head `82cd6282` (base `db5a001b`, PR #1711). Refs #1693.
- Reviewer: Fabric lane `pbr-p2-spec-review-r1`, host `ubuntu2`, pool `minimax`, model `glm-5.3-flash`, class `review` / `C2_COMPLEX_BOUNDED`, orchestrator `pbr-product-ed665c78`. RUN_RESERVED 12:22Z, REMOTE_DONE rc=0 12:42Z. The builder (pbr-product) did not review.
- Verdict: **FAIL** (9 MAJOR, 9 MINOR, 3 NIT).
- Disposition: repaired by the builder in the commit that adds this file (self-repair; the repair diff is not independently reviewed by this record — see "Repair review" below).

## Reviewer RETURN (verbatim)

```text
RETURN pbr-p2-spec-review
VERDICT: FAIL

findings:

1. [MAJOR] §2 lines 96–104 (Route and panel map) and 130–143 (per-book switching table) — 19 of the ~20 code pointers in the section are stale: they were written against `230e9a301`/pre-#1707/pre-#1711 line numbers and no longer land on the code they name. §4 cites the same facts correctly (`index.html:6468` for `PF_GATED_ONLY`, `:6504` for `revealActivePortfolioTab`, `:6477` for `renderPortfolioSwitch`), so §2 and §4 contradict each other on the same anchors. The §3 preamble (173–179) acknowledges the drift for only 6 ids and asserts a uniform "+4" shift that does not hold for the other 13 (real offsets +3 to +89). Required fix: re-verify every `app/...:line` in §2 against `db5a001b2` and correct; then correct or delete the §3 reconciliation note so it matches reality. Concretely wrong: `index.html` 2719→2723, 2727→2730, 2751→2755, 2753→2757, 2790→2794, 2858→2861, 3818→3827, 3838→3847, 4899–4916→4988–5002, 4927→5015, 4940–4981→5015–5068, 6380→6468, 6390→6477, 6405→6492, 6417–6427→6504, 6444→6529, 6454–6457→6542–6544, 6462–6463→6551–6552; `portfolio/registry.py` 39–43→44–45 (`superseded_by` 44, `archived_reason` 45).

2. [MAJOR] §6 rows 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 15 (spec lines 2296–2309) — 15 of the ~20 code pointers in the "truth violations to fix first" list land on unrelated code, so the candidate first build PR would edit the wrong lines. Required fix: re-verify each row's line numbers. Concretely wrong: `index.html` 4507–4509→4516–4518; 4597→4606; 4601→4610; 5001–5010→5087–5093 (win-rate block: `sells` 5087, `wins` 5091, `winTxt` 5093); 6157–6159→6242 (`winTxt`); 3958→3967 (3958 is a comment); 7586→3960–3967 (7586 is the calendar footnote); 3869–3870→3877 (`_performanceEvidenceText`, `if (!a) return '';`); 4033–4038→4044–4046 (`pre_inception` branch); 4068→4077 (`allVals`); 5341–5342→5429–5430 (bucket bar widths); 8718→8806; 4731→4804; 4020→4029; `app/web.py` 1391→1388; `portfolio/performance_projection.py` 284–285→283/288 (`total_return_pct`/`day_change_pct`).

3. [MAJOR] §4 V6 Fields table (lines 1918–1950) — the `index.html` render citations are systematically displaced, so most point at the wrong cell of the position row: `security_name` `:4844`→4843; `sleeve` `:4846`→4844; `stage` `:4847`→4845; `weight` `:4848`→4846; `unrealized_pnl`/`.pct` `:4820`→4849; `avg_cost` `:4817`→4818; `data-queued-change` `:4841`→4839 (emitted at 4839, as V1 correctly cites at 702); `thesis_full.bull[]`/`.bear[]` `:4808–4823`→4897–4898; `.vetoes[]`/`.divergences[]` `:4825–4839`→4913–4923; `.what_would_prove_wrong` `:4841–4844`→4927–4930; `.confluence`/`.prob_correct` `:4852–4862`→4947; `history[]` (actual fills) `:5020–5045`→5115–5134 (fills blotter; 5020–5045 is the pending-orders renderer). Required fix: re-verify each render line against the PR base.

4. [MAJOR] §4 V6 Fields table — the `portfolio/position_log.py` block mis-maps four of five rows to the neighbouring field: `opened_at`/`held_days` `:323–325`→326–327; `entry_weight`/`current_weight` `:326–327`→328–329; `published_stop`/`buy_zone` `:332–334`→334–335; `thesis_id` `:330`→332. Only `time_stop_by` `:331` is correct. Required fix: correct the four ranges.

5. [MAJOR] §4 V6 — "subsequent factual changes", the one content item ORIGINAL_PACKET item 4 requires of V6, has no Fields row and no composed module. §7 mints **S7** for exactly that need (line 2356) but S7 appears nowhere in §1–§6. The same gap applies to **S2** (line 2351, "V6 Tier 3"), **S4** (line 2353, "V6 Tier 3") and **E12** (line 2332, "V1/V6 header provenance"): each is declared needed by a view but has no field binding in any view. Required fix: add the missing Fields rows (`CONTRACT REQUEST → S7` / `S2` / `S4` / `E12`) and place the amendment / scorecard / evidence / valuation-basis modules in V6's information hierarchy.

6. [MAJOR] §4 V1 lines 613–615 vs line 753 — two different EN+ZH pairs for the same empty state. The States section proposes "Empty — this book holds no positions yet; the next daily run will rebuild it." / "暂无 — 本组合尚无持仓，下次每日运行后重建。" and then asserts "The shipped copy already exists (`pos.empty`, `index.html:3250`) and is the model", but the shipped string is the one in the EN/ZH table at 753: "No positions yet — the book builds on the next daily run." / "暂无持仓 — 下次每日运行后将更新。". The attribution to today's code is false. Required fix: keep one pair; mark any copy change as an explicit copy request rather than "already exists"; attribute the shipped string accurately.

7. [MAJOR] Canonical state vocabulary deviation — the binding table (`_pbr_inputs/common.md`; printed at spec 416–417) fixes `empty` → EN `Empty` / ZH `暂无`. V1 (753), V3 (1355, 1417), V4 (1561) and V5 (1820) instead use bespoke sentences ("No positions yet — …" / "暂无持仓 — …", "No orders queued." / "暂无挂单。", "No recorded performance observations available." / "暂无可用的业绩记录", "No rejected names — …" / "暂无剔除标的 — …"). V2 (1043) and V7 (2139) comply. Required fix: use `Empty` / `暂无` + the reason sentence in V1/V3/V4/V5, or record each deviation in §9 as a seat decision.

8. [MAJOR] §4 V3 line 1343 (`.mx-vh` anatomy), line 1432 (`<details class="mx-disc">`), V5 line 1728 and line 1770 (`.mx-ladder`, `.mx-tbl`) — Macro `.mx-*` primitives are used as if they were the app's markup, with no binding to an `app/static/index.html` class or `theme.css` variable and no §8 gap. This contradicts §3's binding rule at line 183 ("The Mastermind app does not ship the Macro `.mx-*` primitives. Every visual role below is bound to a variable that exists today in `app/static/theme.css` or to a class that exists today in `app/static/index.html`") and §8's own claim at line 2365/2383 that the gap index "maps every name used in §1–§4" — `.mx-ladder`, `.mx-tbl` and `.mx-disc` are not in it (G6 covers `.mx-rail` only, and G6's text names V6/V7, not V3). Required fix: replace each with the app class/token that will carry it, or add explicit numbered gaps (G10+) and extend the assembled index.

9. [MAJOR] Front matter line 10 — `base_commit: "origin/master @ dce821e0"` is not the base this spec sits on. The PR base is `db5a001b2` = PR #1711, the RUNTIME read-only disposition projection that V7's entire disposition vocabulary depends on; `dce821e0` is its grandparent. The §3 preamble (174–179) states every citation in the part was "re-verified against `dce821e0`", which cannot be true for the #1711 vocabulary. Required fix: correct `base_commit` to `db5a001b2` (PR #1711) and correct the §3 verification claim.

10. [MINOR] §4 V7 line 2109 binds the per-cycle disposition to `CONTRACT REQUEST → R1`, while §7 line 2344 mints **R6** for the same field. R1's documented shape (`run_status`, `last_decision_at`, `last_attempt_at`, …) does not contain `cycles[].disposition`, so the request as written would reach RUNTIME as a mis-scoped R1 row. Required fix: bind V7's row to R6.

11. [MINOR] §4 V7 lines 2150–2151 state "No member is invented by this view and no member is renamed; the EN word is the identifier", but the table renames `started`→"Running" (2159), `accepted_no_change`→"Accepted · no change" (2160) and `incomplete_uncertain`→"Incomplete · uncertain" (2164). `common.md` amendment 5 requires exactly RUNTIME #1711's vocabulary. Required fix: keep the identifiers as the EN labels, or state the display-copy rule once and mark the renames as a seat decision.

12. [MINOR] §3 line 295, line 306 and V6 line 535 cite `index.html:3683` for `pct()`; `pct` (1 dp) is at 3682 and 3683 is `pctInt` (0 dp). Required fix: change to `:3682`.

13. [MINOR] §4 V6 line 1924 cites `paper_account.py:1729` for `market_value`; the key is declared at 1727 (1732 is the assignment) and 1729 is `unrealized_pct`. Required fix: `:1727,1732`.

14. [MINOR] §4 V1 line 527 cites `app/web.py:1421` for `_attach_security_names`; the function is at 1420. Required fix: `:1420`.

15. [MINOR] §4 V4 line 1644 cites `index.html:3228-3229` for "Recorded Drawdown · over recorded observations"; 3228 is correct for the drawdown label but 3229 is `perf.cash_lbl` — "over recorded observations" is at 3999 (static copy 2790). Required fix: cite `:3999` for the range phrase.

16. [MINOR] §4 V2 line 976 cites `index.html:7549-7551` for the `#auto-sum` banner; 7549–7551 is the calendar-excluded footnote and the banner element is at 2741 (cited correctly in the same row). Required fix: drop `:7549-7551` or point it at the fill site.

17. [MINOR] §4 V7 line 2147 cites `app/decision_availability.py:556`; the file has 543/544 lines and the `expected_opportunity` object is at 538. Required fix: `:538`.

18. [MINOR] §4 V1 line 620 names the stale trigger `archive_as_of` — no such field exists anywhere in the repo; the archived payload's field is `frozen_as_of` (`app/web.py:199`, `:222`, `:231`). An invented field name is presented as existing. Required fix: `frozen_as_of`.

19. [NIT] §8 table rows are ordered G1, G5, G3, G6, G7, G8, G2, G4, G9 (2362–2383); the assembled index underneath is in numeric order. Reorder the table for readability.

20. [NIT] §4 V1 line 581 repeats the function name: "reusing `revealActivePortfolioTab`, `revealActivePortfolioTab`".

21. [NIT] §6 row 14 (line 2308) is the one row whose pointer I verified as correct (`index.html:8730-8736` — the session map and its `|| '休市'` fallback); keep it as the model for the re-verified rows.

citations checked: 397 ok / 58 wrong-line / 1 missing (of 456 unique `file:line` targets enumerated in the spec; all 456 resolve to an existing file, and 455 resolve to an in-range line)
bad ones (wrong-line):
- §2: `app/static/index.html` 2719→2723, 2727→2730, 2751→2755, 2753→2757, 2790→2794, 2858→2861, 3818→3827, 3838→3847, 4899–4916→4988–5002, 4927→5015, 4940–4981→5015–5068, 6380→6468, 6390→6477, 6405→6492, 6417–6427→6504, 6444→6529, 6454–6457→6542–6544, 6462–6463→6551–6552; `portfolio/registry.py` 39–43→44–45
- §3: `index.html` 3683→3682 (cited at 295, 306, 535)
- §4 V1: `app/web.py` 1421→1420; `index.html` 8718→8806, 8747→8752
- §4 V2: `index.html` 7549–7551→2741
- §4 V4: `index.html` 3228–3229→3228 + 3999
- §4 V6: `portfolio/position_log.py` 323–325→326–327, 326–327→328–329, 330→332, 332–334→334–335; `portfolio/paper_account.py` 1729→1727; `index.html` 4731→4804, 4817→4818, 4820→4849, 4841→4839, 4844→4843, 4846→4844, 4847→4845, 4848→4846, 4808–4823→4897–4898, 4825–4839→4913–4923, 4841–4844→4927–4930, 4852–4862→4947, 5020–5045→5115–5134
- §6: `index.html` 3958→3967, 4020→4029, 4033–4038→4044–4046, 4068→4077, 4164–4166→4162–4164, 4507–4509→4516–4518, 4597→4606, 4601→4610, 5001–5010→5087–5093, 6157–6159→6242, 7586→3960–3967, 3869–3870→3877, 5341–5342→5429–5430, 8718→8806, 4731→4804; `app/web.py` 1391→1388; `portfolio/performance_projection.py` 284–285→283/288
missing (out of range): `app/decision_availability.py` 556 → 538

checklist: 1=ok 2=ok 3=issue 4=issue 5=issue 6=ok 7=issue 8=issue 9=ok
```

## Disposition per finding

| # | Sev | Disposition |
|---|---|---|
| 1 | MAJOR | Fixed. Every §2 citation re-read against `db5a001b` (lines 99–103, 113, 115, 119, 121, 132, 143, 282). Reviewer value overridden where a direct read disagrees: `6405` → `6493` (the archived-title line; `6492` is the line before it); `4899-4916` → `4988-5003` (`5003` is the closing `};` of `toggleExpand`); `4940-4981` → `5031-5068` with `4927` → `5015`; `registry.py:39-43` → `:44-45` (not flagged). |
| 2 | MAJOR | Fixed (§6 lines 2296–2309). Reviewer values overridden: `7586` → `7674` (the `vs_benchmark_pct` read; the reviewer's `3960-3967` is the label block, cited separately as `3967`); `4164-4166` → `4173-4175` (reviewer `4162-4164`); `4033-4038` → `4040-4046` (reviewer `4044-4046`). Also fixed rows the review did not list: gross label `4526` → `4532`; `app/web.py:1391` → `:1388`; `performance_projection.py:284-285` → `:283` and `:288`. |
| 3 | MAJOR | Fixed (V6 Fields render citations). Beyond the review's list, also re-verified and fixed: 1937 `4769-4774` → `4766-4767`; 1938 `4796-4806` → `4884-4893`; 1939 `4808-4823` → `4895-4910` and `4811` → `4903`; 1942 `4852-4862` → `4934-4948`; 1943 `4859-4877` → `4860-4878`; 1963 `4845-4854` → `4844-4853`; 2005 `4808-4823` → `4895-4910`; 1552 `2753-2790` → `2757-2794`, `2792-2812` → `2794-2813`. |
| 4 | MAJOR | Fixed (`position_log.py` 326–327, 328–329, 332, 334–335). Row 1931 also rewritten: `current_weight` is not rendered today — `_heldPendingChange` reads the pending-target row's own `current_weight` (`index.html:4775`) and does not draw it. |
| 5 | MAJOR | Fixed. V6 gains Fields rows for `amendments[]` (S7, subsequent factual changes; delivered-and-empty is `Empty — no amendments since entry.`; never inferred by diffing `thesis_full`), `scorecard[]` (S2), `evidence[]` (S4) and `valued_at_cost[]`/`nav_basis` (E12). Tier table, 1280 and 375 layouts, States and EN/ZH table updated. |
| 6 | MAJOR | Fixed. V1 has one empty pair (`Empty — this book holds no positions yet; …` / `暂无 — 本组合尚无持仓，…`), declared a copy request replacing shipped `pos.empty`. |
| 7 | MAJOR | Fixed. §3 adds "Shipped strings that predate this table" (`pos.empty`, `pend.none`, `ec.no_data`, `rej.empty`): views cite them only as current state and specify `Empty`/`暂无` + reason replacements as PRODUCT copy requests with an EN/ZH agreement test. V1, V3 (1355, 1417), V4 (1561), V5 (1779, 1820, 1867) rewritten. |
| 8 | MAJOR | Fixed. §3 Tokens binds the DS anatomy to shipped app classes: verdict block → `.panel` + `.mm-perf-stat-value` + `.mm-perf-stat-sub`; bounded table → `.mm-table-wrap` > `table`; disclosure → `<details class="mm-da-foot">`. `.mx-rail` is bound to gap G6 and `.mx-ladder` to a new gap G10 (count ladder; the app has only `.mm-rej-grid`). No `.mx-*` class is cited as app markup. |
| 9 | MAJOR | Fixed. `base_commit` is `db5a001b` (PR #1711); the §3 preamble records the `230e9a301` → #1707 insertion offsets and this re-verification. |
| 10 | MINOR | Fixed: V7 per-cycle disposition binds to `R6`. |
| 11 | MINOR | Fixed: identifiers are never renamed or printed raw; the four differing EN display labels are listed and made §9 seat decision 11. |
| 12–18 | MINOR | Fixed as required (`:3682`; `:1727,1732`; `web.py:1420`; `:3228` + `:3999`; `:7549-7551` dropped; `decision_availability.py:538` at both 2116 and 2147; `frozen_as_of`). |
| 19 | NIT | Fixed: §8 rows ordered G1–G9, G10 appended; index updated. |
| 20 | NIT | Fixed. |
| 21 | NIT | Kept unchanged (`index.html:8730-8736` verified). |

Also overridden from the reviewer's wrong-line list: V1 `8747` → `8835` (the spec quotes `Number(seconds) || 120`, which is at `8835`; the reviewer's `8752` is a different default, `Number(d.poll_after_seconds) || 120`). Additional defect found during repair: the V5 S9 entry-readiness Fields row was missing its nullability cell (7 of 8 columns); filled.

## Repair review

The repair is a builder self-check (every changed citation printed against `db5a001b`, residual `.mx-*`/`3683`/`archive_as_of` grep, table column-count check). A self-check is not an independent review. A scoped r2 covers only the repair diff (`82cd6282..` this commit) and is recorded in `pbr-p2-spec-review-r2.md` when it returns.
