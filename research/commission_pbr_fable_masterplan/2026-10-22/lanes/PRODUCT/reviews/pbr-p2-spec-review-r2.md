# pbr-p2-spec-review — r2 (scoped review of the r1 repair)

- Unit: the r1 repair diff `82cd6282..29fd1026` of `docs/superpowers/specs/2026-10-22-pbr-product-views.md` (PR #1744). Refs #1693.
- Reviewer: Fabric lane `pbr-p2-spec-review-r2`, host `ubuntu2`, pool `minimax`, model `glm-5.3-flash`, class `review` / `C2_COMPLEX_BOUNDED`, orchestrator `pbr-product-ed665c78`. RUN_RESERVED 12:58Z, REMOTE_DONE rc=0 13:04Z. The builder did not review.
- Verdict: **PARTIAL** — r1 closure 20 RESOLVED / 1 NOT RESOLVED (r1 #1) / 0 REGRESSED; 1 MAJOR, 5 MINOR, 5 NIT; 123 of 131 changed citations ok; all five builder overrides of r1 values judged correct.
- Disposition: repaired by the builder in the commit that adds this file.

## Reviewer output (verbatim)

````text
I have completed the verification. Here is the r2 review.

**Verification performed:** all 131 unique `file:line` targets appearing on `+` lines of the repair diff were read against this checkout; all 21 r1 findings were re-checked against the spec at HEAD; the five disposition overrides were independently adjudicated; the §3 preamble's insertion-offset claim was reproduced from `git diff 230e9a301 db5a001b -- app/static/index.html` (+4/+9/+73/+88 — exactly as stated); `git diff dce821e0 db5a001b -- app/ portfolio/` is empty, confirming the byte-identical claim.

```
RETURN pbr-p2-spec-review-r2
VERDICT: PARTIAL

r1 closure: 20 RESOLVED / 1 NOT RESOLVED / 0 REGRESSED (non-resolved: r1 #1)
  - r1 #1 (MAJOR, §2 stale pointers): every one of r1's 19 enumerated pointers is corrected and
    all five builder overrides are correct, but §2 line 104 still carries two census-base
    pointers — `#runs` `:2893` (actual `app/static/index.html:2897`) and `#forward-evaluation`
    `:2746` (actual `index.html:2750`); both cited lines are `</div>`. r1's required fix also
    said "correct or delete the §3 reconciliation note so it matches reality"; the rewritten note
    (spec 176) now asserts "every `index.html` citation in those sections was re-cited", which
    is false for those two. The §6 half of the finding is fully closed (all 15 rows verified,
    including the unchanged rows 1/9/11).
  - r1 #2-#9, #10-#21: all verified RESOLVED at HEAD (see per-finding evidence below).

findings:
1. [MAJOR] spec 104 and spec 176 — §2's V7 row still carries two census-base line numbers:
   `#runs` (`:2893`) and `#forward-evaluation` (`:2746`). At HEAD `#runs` is
   `app/static/index.html:2897` and `#forward-evaluation` is `index.html:2750`; lines 2893 and
   2746 are both `</div>`. This is the same defect class as r1 #1, unfixed in the table r1 named,
   and it falsifies the §3 preamble's completeness claim ("every `index.html` citation in those
   sections was re-cited", spec 176) and the r1 disposition row's "Every §2 citation re-read
   against `db5a001b`" (the disposition's own line list stops at 103). Required fix: cite
   `index.html:2897` and `index.html:2750`, then re-read the whole of §2 line 104 and either
   correct the §3 sentence or name the exceptions.
2. [MINOR] spec 143 — `registry.py:44-45` does not cover what the sentence names. The row cites
   "`archived_reason` and `superseded_by` line (`index.html:6493`, `registry.py:44-45`)", but
   `portfolio/registry.py:44` = `"status": "archived"`, `:45` = `"superseded_by"`, and
   `archived_reason` is at `portfolio/registry.py:46` — outside the cited range. Required fix:
   `registry.py:45-46`.
3. [MINOR] spec 1953 — the V6 row `thesis_full.what_would_prove_wrong` cites `app/web.py:1445`,
   which is `continue` (the `if not tf:` guard). The tuple that carries the field is
   `app/web.py:1447` — `for field in ("summary", "why_now", "sizing_rationale",
   "what_would_prove_wrong")`. Required fix: `:1447`.
4. [MINOR] spec 2326 — §6 row 7 cites `app/web.py:190-196` for "`day_change_pct = 0.0`,
   `total_return_pct` default", but those are at `app/web.py:189` and `:187-188` (the `else 0.0`
   branch); `190-196` is the override plus the benchmark block. Required fix: `:187-191`.
5. [MINOR] spec 2322 — §6 row 3 contains an unescaped `|| 0` inside a table cell
   ("remove the `|| 0` so they join it"), which splits the row into 5 cells against the 3-column
   header at 2318 (row 2 correctly writes `\|\|`). The §6 table therefore renders misaligned.
   Required fix: escape as `\|\|`.
6. [MINOR] spec 434-439 — §3's new "Shipped strings that predate this table" paragraph promises
   the empty-copy replacements "land in that view's build PR with an EN/ZH agreement test", but
   no view Acceptance checklist names one (V1's EN/ZH item at 930-933 covers ink flipping and
   "no English leak", not the new `Empty`/reason pair). Required fix: add the copy-pair
   assertion to the V1/V3/V4/V5 acceptance checklists.
7. [NIT] spec 2400 — §8 G5 cites the second prose loader as `index.html:4310`; the `.mm-empty`
   prose block is at `index.html:4309` (4310 is `return;`). Required fix: `:4309`.
8. [NIT] spec 102 — §2's V5 row names "`#nav-research` / `#view-research`" but cites
   `index.html:6550-6551`, which is `nav-research` + `nav-desk`. `#view-research` is a different
   element (`index.html:2962`), CSS-gated at `:1388-1393`, with the `showView('dashboard')`
   fallback at `:6554`. The claim is materially true but the citation names the wrong pair.
9. [NIT] spec 1950 — the `thesis_full.summary`/`.why_now`/`.sizing_rationale` row cites
   `index.html:4884-4893`, which covers summary (4884-4887) and why_now (4890-4893) but not
   `sizing_rationale` (`index.html:4933-4937`). Required fix: add `:4933-4937`.
10. [NIT] spec 56 — doubled parenthesis: "...(DS anatomy, bound in §3 Tokens to the `.panel`
    surface + `.mm-perf-stat-value` figure; no `.mx-vh` class ships) (holdings count, cash,
    NAV + status, one as-of stamp)". Required fix: merge into one clause.
11. [NIT] spec 765 / 1367 / 1429 / 1573 / 1791 / 1832 vs 1988 / 2160 — the repair's new empty copy
    joins label and reason with an em dash ("Empty — <reason>"), while V6 (1988) and V7 (2160)
    render the label and the reason as separate pieces. Both satisfy §3's "full-weight sentence
    with the reason"; one form should be chosen for the copy requests.

citations checked: 123 ok / 8 wrong-line / 0 missing (of 131 unique `file:line` targets added on
`+` lines; every target resolves to an existing file and an in-range line)
bad ones (wrong-line):
- `app/static/index.html:2893` (spec 104, `#runs`) → should be `index.html:2897`
- `app/static/index.html:2746` (spec 104, `#forward-evaluation`) → should be `index.html:2750`
- `portfolio/registry.py:44-45` (spec 143) → `archived_reason` is at `:46`
- `app/web.py:1445` (spec 1953) → the field tuple is at `:1447`
- `app/web.py:190-196` (spec 2326) → the named `= 0.0` defaults are at `:187-189`
- `app/static/index.html:4310` (spec 2400) → the `.mm-empty` prose loader is at `:4309`
- `app/static/index.html:6550-6551` (spec 102) → `nav-research` + `nav-desk`; `#view-research` is
  CSS-gated at `index.html:1388-1393`
- `app/static/index.html:4884-4893` (spec 1950) → does not cover `sizing_rationale` (`:4933-4937`)
verified-correct highlights (non-exhaustive): `index.html:2723/2730/2861` (`#decision-availability`,
`#auto-banner-sec`, `#decisions-sec`), `5031-5068` + `:5015` (`_pendingOrdersHtml`,
`_pendingTruthNoticeHtml`), `2755/2757/2794`, `6468` + `6542-6545` + `6550-6551`
(`PF_GATED_ONLY`, gating loop, nav pair), `4988-5003` (`toggleExpand`), `6493` (archived title),
`3847` (`_PF_ORDER`), `6477`, `6504-6513`, `6529`, `3827`, `3682` (`pct`), `3228` + `:3999`
(drawdown label + range phrase), `4843/4844/4845/4846/4849/4809-4811/4839/4836-4838/
4766-4767/4775/4884-4893/4895-4910/4903/4913-4923/4927-4930/4934-4948/4860-4878/5115-5134`
(V6 render block), `position_log.py:326-327/328-329/332/334-335` + `:157-161`,
`paper_account.py:1725/1727/1728-1729`, `performance_projection.py:283/599-600`,
`decision_availability.py:538` (both sites) and `:145-157`, `web.py:1388/1420/2370/1433-1438/
1441-1446/1448-1455/1157-1158/1186-1193/1361/1380/205-225/249`, `registry.py:33-45`,
`theme.css:129`, `index.html:72/565/2492-2493/922-932/4963/5059/7006/7087/7258/7412`,
`index.html:4516-4518/4532/4606/4610/5087-5093/6242/3967/7674/3877/4040-4046/4173-4175/4077/
5429-5430/8806/4804/4029/8730-8736`, `index.html:2899`, `index.html:1239`,
`app/pfolio.py:357-359/382-383`, `portfolio.html:676-686/681/686`, `market_view.html:414/427`.
Also verified unchanged-but-relied-on: `index.html:2750` (`#forward-evaluation`),
`index.html:2897` (`#runs`), `index.html:2962` (`#view-research`).

overrides:
- `6405` → `6493` (not `6492`): **builder correct**. `index.html:6493` is
  `var title = archived ? ((p.archived_reason || 'Frozen historical portfolio') + (p.superseded_by ? ' · successor: ' + p.superseded_by : '')) ...`
  — the archived title line that names both fields the spec sentence names; `index.html:6492` is
  the `ARCHIVED` chip (`var archiveChip = archived ? '<span class="mm-archive-chip">...'`).
- `7586` → `7674` (not `3960-3967`): **builder correct**. `index.html:7674` is
  `var relative = p.vs_benchmark_pct != null ? p.vs_benchmark_pct : p.vs_spy_pct;` — the SPY-named
  alias read §6 row 5 names; `3960-3967` is the label block, which the row cites separately as
  `:3967` (also the alias read).
- `4164-4166` → `4173-4175` (not `4162-4164`): **builder correct**. `index.html:4173-4175` is
  the pre-inception block (`// Pre-inception: flat line at $1M (solid, no fill, muted)` and
  `svg += '<path ... stroke="var(--up)" ...>'`) — the solid `--up` line row 8 names.
- `8747` → `8835` (not `8752`): **builder correct**. `index.html:8835` is
  `var delay = Math.max(30, Number(seconds) || 120) * 1000;` — the exact expression the sentence
  quotes; `:8752` is a different default (`Number(d.poll_after_seconds) || 120`).
- `4899-4916` → `4988-5003` (not `5002`): **builder correct**. `index.html:4988` is
  `window.toggleExpand = function(idx) {` and `index.html:5003` is the closing `};` of that
  function — the full `toggleExpand` body, which is what §2's V6 row names.
  (The builder's two further §2 overrides, `4940-4981`→`5031-5068` with `4927`→`5015`, and the
  §6 `4033-4038`→`4040-4046`, `4526`→`4532`, `performance_projection.py:284-285`→`:283`/`:288`
  are also verified correct.)

checklist: 1=ok 2=issue 3=issue 4=ok 5=ok 6=issue
```
````

## Disposition per finding

| # | Sev | Disposition |
|---|---|---|
| 1 | MAJOR | Fixed. §2 V7 row: `#runs` `:2897`, `#forward-evaluation` `:2750`. Every remaining §2 citation was then swept by direct read, which found two more census-base values on spec line 140: tab order `index.html:3828-3848` → `:3834-3847` (the `_PF_LABELS` + `_PF_ORDER` block) and `registry.py:32-146` → `:32-143` (the `PORTFOLIOS` list ends at 143). The §3 preamble's completeness sentence is now true for §2 and §6. |
| 2 | MINOR | Fixed: `registry.py:45-46`. |
| 3 | MINOR | Fixed: `app/web.py:1447`. |
| 4 | MINOR | Fixed: `app/web.py:187-191` with the two defaults named (`:187-188`, `:189-191`). |
| 5 | MINOR | Fixed: `\|\| 0` escaped. The builder's own table check had masked pipes inside code spans; it now counts them as GFM does and reports no mismatched row. |
| 6 | MINOR | Fixed: V1 item 16, V3 item 9, V4 item 10 and V5 item 6 each assert the `Empty` pair and that the shipped string no longer renders, with an EN/ZH agreement test. |
| 7 | NIT | Fixed: `:4309`. |
| 8 | NIT | Fixed: the §2 V5 row names `#nav-research` + `#nav-desk` at `:6550-6551`, `#view-research` at `:2962`, its CSS gate `:1388-1393` and the `showView('dashboard')` fallback `:6554`. |
| 9 | NIT | Fixed: adds `:4933-4937` for `sizing_rationale`. |
| 10 | NIT | Fixed: one parenthetical. |
| 11 | NIT | Fixed: §3 states one rendering form for every empty state (`Empty — <reason>` / `暂无 — <reason>`, one full-weight line); V6 and V7 States rows render in that form. |
