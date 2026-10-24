# Independent review: PR #1710 (L-P1 product census)

- reviewer lane: `pbr-p1-census-review-r1`, host ubuntu2, model glm-5.3-flash, class review C2 (ECONOMIC_POLICY allowed, tier leaf-labor), LEASE_OK pool=glm, REMOTE_DONE rc=0 at 2026-10-22T08:41Z
- builder lane: `pbr-p1-census-r4` (qwen3.8-flash, ubuntu1), plus the orchestrator's verification section
- reviewed identity: PR #1710 head `9fdca122` on base `d31aade9`
- disposition: MINOR 1, MINOR 2, NIT 3 and NIT 5 were applied in the follow-up PRODUCT docs PR. NIT 4 (the host label and off-repo path) was not applied, because host labels are established practice in this repository's commission ledgers (`git grep ubuntu1 -- research/`) and the off-repo evidence path with its sha256 is the program's proof convention for a public repository.

## Reviewer narrative (verbatim)

Review complete. All checks done against `230e9a301` via `git show`, read-only, no files touched.

**Summary of what I verified:**
- **Scope & counts**: HEAD is exactly `d31aade9` + the one docs commit adding the two lane files. I counted decorators myself: web.py 70 (63 GET), pfolio.py 5 (2 GET), main.py 14 (5 GET) → 89 total, 19 mutating, 58 api-GET after excluding 7 pages + 5 static. The census table itself has exactly 89/7/5/77/58/19 rows. Full agreement.
- **Hygiene**: no credentials, tokens, IPs, emails, or live-book quantities in either file. All dollar figures are the code-fabricated `$1,000,000`, coerced `$0`, or the `$1M` baseline; all other numbers are line refs, file sizes, and diff stats. Only borderline: internal infra naming (`ubuntu1`, off-repo `/Volumes/...` evidence path) in the orchestrator section.
- **Truth violations**: verified 13 (incl. all 8 required: 1, 2, 3, 5, 9, 10, 20, 22). Every quoted line exists at the cited line ±0 and the consequences follow. One clause of #9 is overstated ("full line weight" — actually 1.8px @ 0.5 opacity vs realized 2.2px @ 1.0; the same-color and y-extent claims do hold, and I confirmed the server emits `nav = starting_nav` for pre-inception rows so the extent compression is real).
- **TR2 correction (item 11)**: confirmed all three ways — `renderPositions` builds the verdict chip from `p.verdict` only (index.html:4731; the SPA's only `pending_target` references are the Trades truth notice at 4928 and the decision panel at 7252); web.py:2174-2180 maps a held, priced ticker with `target_weight <= 0` to `exit/sell` (held-context via `is_held` at 2144); actionable rows are promoted into `pending` (web.py:2372). "API compliant, Positions row violated" is accurate.
- **Gap map**: V5 confirmed verbatim (`PF_GATED_ONLY` includes `rejected` at 6380; nav-research/nav-desk flagship-only at 6462-6463). V6's rendered-UI gap is real (zero `time_stop`/`next_review` hits in index.html) — but the payload-absence wording is wrong: `position_log.open_positions()` publishes `time_stop_by` per position into `/api/trades open[]` (position_log.py:331), and `/api/desk/macro-risk` publishes `check_by` (web.py:3436, flagship-only lane).
- **Contract requests**: every row carries field/type/nullability/units/provenance/consumer/status except R5 (a dependency record, not a field request). No domain-ownership violations; E11 → gap map V4 and S5 → gap map V2/V6 both trace. S5 should acknowledge the already-flowing `time_stop_by` field.

```
RETURN pbr-p1-census-review
VERDICT: PASS
route count: web.py 70 (63 GET) + pfolio.py 5 (2 GET) + main.py 14 (5 GET) = 89 total, 19 mutating; − 7 pages − 5 static = 77 api, 58 api-GET vs census 89/7/5/77/58/19 — agree
truth violations verified: 1, 2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 20, 22 — confirmed 13 / refuted 0
findings:
1. [MINOR] PRODUCT_CENSUS.md:296 (gap map V6), :265, :681-685 (open question 8) — "no check-by date rendered from any endpoint" / "whether the data exists in a writer artifact that no route exposes … not traced to a route" overstates payload absence: position_log.open_positions() publishes a per-position `time_stop_by` into `/api/trades` `open[]` (position_log.py:331, returned at app/web.py:2353-2354 at 230e9a301) and `/api/desk/macro-risk` publishes `check_by` (app/web.py:3436); the SPA renders neither, so the user-facing V6 gap is real but the data is route-exposed, and CONTRACT_REQUESTS.md S5 asks RESEARCH for `next_review_at` without acknowledging the existing field — amend the three sentences and S5 to "time_stop_by already flows in /api/trades open[] but is unrendered; S5 extends it with horizon_end/review_condition"
2. [MINOR] PRODUCT_CENSUS.md:358 (truth violation 9) — "at full line weight" is false: the pre-inception path draws stroke-width 1.8 at opacity 0.5 (index.html:4165) vs the realized segment's 2.2 at full opacity plus area fill (index.html:4171); the same-`--up`-color claim and the allVals y-extent compression both verified (performance_projection.py:258-259 emits nav=starting_nav for pre_inception rows) — reword to "near-full weight at half opacity"; violation stands
3. [NIT] PRODUCT_CENSUS.md:720 (orchestrator correction) — "maps a held ticker whose target weight is 0 or below to action:'exit' … and lists it as a pending order" is unconditional; the unpriced case maps to action:"unpriceable"/suppressed_by:"missing_exit_price" (app/web.py:2175-2177) and is not listed as pending — qualify with "when priced"
4. [NIT] PRODUCT_CENSUS.md:701,738 — internal infra naming in a public repo: lane host label `ubuntu1` and the off-repo local path `/Volumes/Mastermind/evidence/pbr/product-capture-20261022T073304Z/`; no credential, IP or routable hostname, but genericize (e.g. "lane host", "off-repo evidence volume, manifest sha256 retained") 
5. [NIT] CONTRACT_REQUESTS.md:37 (R5) — the one row not meeting the required column semantics: "field" is a wiring task, "product consumer" ("prerequisite for E1 = QUALIFIED") names no product view; deliberate per its status text, but mark it explicitly as a dependency record rather than a field request row
checklist: 1=ok 2=ok (NIT 4) 3=ok 4=ok 5=ok 6=issue (MINOR 1) 7=issue (NIT 5) 8=ok (MINOR 2, NIT 3)
```
