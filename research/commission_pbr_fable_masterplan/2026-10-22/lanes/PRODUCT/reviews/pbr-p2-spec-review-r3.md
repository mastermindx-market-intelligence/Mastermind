# pbr-p2-spec-review — r3 (scoped review of the r2 repair)

- Unit: the r2 repair diff `29fd1026..60c19825` of `docs/superpowers/specs/2026-10-22-pbr-product-views.md` (PR #1744). Refs #1693.
- Reviewer: Fabric lane `pbr-p2-spec-review-r3`, host `ubuntu2`, pool `minimax`, model `glm-5.3-flash`, class `review` / `C2_COMPLEX_BOUNDED`, orchestrator `pbr-product-ed665c78`. RUN_RESERVED 13:09Z, DONE rc=0 13:14Z. The builder did not review.
- Verdict: **PASS**. r2 closure: 11 RESOLVED / 0 NOT RESOLVED / 0 REGRESSED; 26 of 26 changed citations ok; retention of r2 identical. Findings: 2 MINOR, 2 NIT.
- Disposition: the four findings are repaired by the builder in the commit that adds this file. The repair is self-checked (strict GFM table count, copy-form scan, checklist numbering, cited lines read at the base) and has **not** been independently reviewed. Under the standing policy, MINOR and NIT fixes after a PASS do not open another review round.

## Reviewer output (verbatim)

````text
I have completed the verification. Here is the r3 review.

**Verification performed:** the repair diff `29fd1026..60c1982` was taken as the sole scope (`git diff --name-status` → exactly `M` the spec + `A` the r2 review file); all 11 r2 findings were re-checked against the spec at HEAD and the code; all 26 distinct `file:line` targets on `+` lines (16 full-path + 10 short-form) were read in this checkout; every Markdown table in the spec was re-counted the way GFM counts cells; the seven Acceptance checklists were parsed for numbering gaps/duplicates; every `§`/`G<n>` reference on a `+` line was resolved; the retained reviewer output was extracted with `awk` and `diff`ed against `_pbr_inputs/R2_OUT.txt`; `git diff dce821e0 db5a001b -- app/ portfolio/` is empty, confirming the byte-identical claim.

```
RETURN pbr-p2-spec-review-r3
VERDICT: PASS

r2 closure: 11 RESOLVED / 0 NOT RESOLVED / 0 REGRESSED
  - #1 (MAJOR, §2 stale pointers): RESOLVED. spec 104 now cites `index.html:2897` (`id="runs"`) and
    `index.html:2750` (`id="forward-evaluation"`); both verified in this checkout. The §3 preamble's
    completeness sentence (spec 174-177) is now true for §2: every remaining §2 index.html citation was
    re-read (2723/2730/2861/2755/2757/2794/3827/3847/5015/5031-5068/4988-5003/6477/6504-6513/6529/
    6468/6542-6545/6550-6551/2962/1388-1393/6554/6493/2899/4309/4606/4610) and the builder's two extra
    §2 corrections also verify — `index.html:3834-3847` is the `_PF_LABELS` + `_PF_ORDER` block and
    `registry.py:32-143` is the `PORTFOLIOS` list (decl `:33`, closing `]` `:143`). §6's 15 rows verify
    unchanged. `git diff dce821e0 db5a001b -- app/ portfolio/` is empty.
  - #2 RESOLVED (`registry.py:45-46` = `"superseded_by"`, `"archived_reason"`). #3 RESOLVED
    (`app/web.py:1447` = the field tuple). #4 RESOLVED (`app/web.py:187-191`; `:187-188` = the
    `else 0.0` default, `:189` = `day_change_pct = 0.0`). #5 RESOLVED (`\|\| 0` escaped; §6 row 3 now
    counts 3 cells against the 3-column header). #6 RESOLVED (V1 item 16, V3 item 9, V4 item 10,
    V5 item 6 — all four shipped strings `pos.empty`/`pend.none`/`ec.no_data`/`rej.empty` covered, each
    with an EN/ZH agreement test). #7 RESOLVED (`:4309` is the `.mm-empty` loader; `:4310` is `return;`).
    #8 RESOLVED (`nav-research`/`nav-desk` `:6550-6551`, `#view-research` `:2962`, CSS gate `:1388-1393`,
    fallback `:6554`; `flagship` is `_portfolio === 'flagship'` at `:6536`). #9 RESOLVED (`:4933-4937`).
    #10 RESOLVED (one parenthetical at spec 56-57). #11 RESOLVED (§3 states one form; see findings 1
    and 3 for the residual inventory/typography gaps it leaves).

findings:
1. [MINOR] spec 439-442 (new rule) and 2175 (V7 States row) — the new §3 sentence "One rendering form
   for every empty state: the label, an em dash, then the reason" binds every empty state in V1–V7, but
   only the four strings in §3's inventory (spec 434-436) have a copy request and an Acceptance item.
   Concretely, V7's States row (spec 2175) still makes the empty state "the existing `.mm-empty` +
   `runs.empty` treatment (`index.html:4308-4310`, key at `:3383`)" — the shipped EN text is "No runs
   logged yet — runs appear here after the bot executes." (`index.html:3383`), which carries no canonical
   `Empty` label, so it cannot render as `Empty — <reason>`; and §3 line 439 states "No view treats a
   shipped bespoke string as accepted copy", which that row accepts. No V7 Acceptance item (V7 has 13,
   spec 2282-2294) is a copy request, so the string the new rule forces out of the build has no owner
   and no test. The same gap covers the other bespoke empty strings the views render (`brain.empty`
   `:5151`, `research.empty` `:5197`, `rp.empty` `:5274`, `cal.lens_empty` `:5451`, `cal.log_empty`
   `:5482`, `desk.wl_empty` `:5772`, `desk.cio_empty` `:5835`, `sd.alloc_empty` `:6119`,
   `sd.hist_empty` `:6239`). Required fix: either narrow the new rule to the states §3 already names, or
   extend §3's shipped-string inventory and the per-view Acceptance checklists to `runs.empty` and the
   other listed strings so "every empty state" has a copy request and an EN/ZH agreement test.
2. [MINOR] spec 1906-1908 (V5 Acceptance item 6) vs spec 1803 — the new item's trigger "A fixture with
   no rejected names" is broader than V5's States row trigger "`rejected[]` empty **and** no finalist
   rows" (spec 1803). As written, a fixture with finalists and zero rejected names must render the
   whole-view `Empty` state, which contradicts 1803 and would blank the ladder's `FINALIST n` cell
   (spec 1794). The other three new items (V1 949, V3 1513, V4 1736) state triggers that stay inside
   their States rows; V5 is the outlier. Required fix: use the spec 1803 condition in item 6 (or scope
   item 6 to the rejected module).
3. [NIT] spec 2003 (V6 States row) and 2175 (V7 States row) — under the new one-line form these two
   reasons do not match the canonical pair's style: they render "Empty — This holding has no recorded
   fills on this book." and "Empty — No runs recorded for this book yet." (capitalised after the em
   dash, where all four copy requests and V2 use lower case, spec 628/1061), and V7's ZH reason
   "本组合暂无运行记录。" then yields "暂无 — 本组合暂无运行记录。" (the label twice). Required fix:
   lower-case the two EN reasons and drop the leading 暂无 from V7's ZH reason, or state explicitly that
   a capitalised reason and a label-repeat are permitted.
4. [NIT] `research/commission_pbr_fable_masterplan/2026-10-22/lanes/PRODUCT/reviews/pbr-p2-spec-review-r2.md:10,15,131,132`
   — the verbatim block's bytes are intact (see retention), but the wrapper does not render as code: the
   ```text fence opened at line 10 is closed by the retained output's own ``` at line 15, so only lines
   11-14 render as code, the RETURN block (16-130) renders as prose, and line 131 opens a block that
   line 132 closes empty. Required fix: use a four-backtick fence (````text) so the inner ``` fences are
   contained and the whole retained output renders as one verbatim code block.

citations checked: 26 ok / 0 wrong-line / 0 missing (16 full-path targets + 10 short-form `:NNNN`
targets on `+` lines; every target resolves to an existing file and an in-range line)
verified list: index.html:2899/2962/3834-3847/4606/4610/4884-4893/4927-4930/4933-4937/6468/6493/
6542-6545/6550-6551/1388-1393/2897/2750/4309/6554; app/web.py:1441-1446/1447/187-191/187-188/189-191;
portfolio/registry.py:32-143/45-46; portfolio/performance_projection.py:283/288
retention: identical — review-file lines 11-131 are byte-for-byte equal to `_pbr_inputs/R2_OUT.txt`
(121 lines, `diff` empty); only the fence nesting differs (finding 4)
checklist: 1=ok 2=ok 3=ok 4=ok 5=issue
```

**Note for the seat:** the verdict is PASS because no BLOCKER or MAJOR finding survived and r2 finding 1 (the MAJOR) is fully RESOLVED. Findings 1 and 2 are copy-inventory/precision gaps that the builder should close before the spec drives a build; finding 2 is the one I would fix first, since it is executable and could send an implementer down the wrong path.
````

## Disposition per finding

| # | Sev | Disposition |
|---|---|---|
| 1 | MINOR | Fixed by narrowing and closing the rule. §3 now scopes the one-line form to every empty state that a V1–V7 build renders. It names the five shipped strings with copy requests, now including `runs.empty`, and adds a shared **empty-form closure** test to every V1–V7 build PR: with each module seeded empty, every non-Loading `.mm-empty` starts with `Empty — ` / `暂无 — `. It also gives copy for the other bespoke lines inside the views' surfaces: V5 item 7 covers `rp.empty`, `cal.no_data`, `cal.lens_empty` and `cal.log_empty`, and drops the passed hard-coded date; V7 item 14 covers `runs.empty`, `desk.wl_empty` and `desk.cio_empty`. Surfaces §2 does not place (`#brainlog`, `#research`, `#view-self`) are named as outside this freeze. The V7 States row no longer accepts the shipped string. |
| 2 | MINOR | Fixed. V5 item 6 now uses the States-row trigger: `rejected[]` empty and no finalist rows. |
| 3 | NIT | Fixed. The V6 and V7 EN reasons are lower case. The V7 ZH reason is `本组合尚无运行记录。`, so it does not repeat `暂无`. §3 states both rules. |
| 4 | NIT | Fixed. The r2 review file uses a four-backtick fence, so the retained output renders as one code block. Its bytes are unchanged. This file uses the same fence. |
