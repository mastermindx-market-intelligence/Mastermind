# pbr-b0-review-r1 — independent frontier review of the B0 product foundation at 15ce4294

- Lane: `pbr-b0-review-r1`, Fabric remote on ubuntu2, glm-5.3, POOL_TASK_CLASS=review, C2_COMPLEX_BOUNDED
  (escalation recorded: the seat commission requires a frontier-class review for B0, V1 and V6).
- Reviewed range: `05a9eb52..15ce429487baa83dd603b38be4366ec6eb01444d` (master after #1756 → B0 head).
- Builder ≠ reviewer: a separate review lane on a fresh detached worktree; it did not build the change.
- Retained verbatim below, then PRODUCT dispositions.

## Reviewer output (verbatim)

# Independent review — PBR B0 product foundation (`05a9eb52..15ce4294`)

## Scope (checklist 1)
`git diff --name-status 05a9eb52 HEAD` lists exactly the nine expected files (6 modified, 1 spec doc, 2 new test files), 4 commits. **ok**

## Server truth (checklist 2)
- `_archived_performance` (`app/web.py:210-215,242,246`): `total_return_pct`/`day_change_pct` are `None` when uncomputable — no `or 0` anywhere in the changed hunks; `vs_benchmark_pct` is additionally guarded against `None` arithmetic (`web.py:222`).
- `_account_state_probe` (`web.py:251-277`) is read-only (`account_file_status` documents "NEVER writes, quarantines or alerts"), bounds problems to 20 strings ×120 chars, swallows every failure to `None`. Attach points: `api_performance` success+except (`:1101,:1107`), degraded `api_live_marks` (`:1287`), `api_portfolio` account-read except (`:1485`). VALID probe → no key → byte-identical body (pinned by `test_t12_api_performance_valid_is_byte_identical`).
- No new/removed routes; `api_self_directed*` untouched (diff has no hunks there).
- The pre-existing `or 1_000_000.0` (`web.py:1408`) and `_first_number(..., default=1_000_000.0)` (`web.py:153`) are **unchanged** — see finding 1. On the live path the coercion is dead code: `_load_account` fails closed (`paper_account.py:408-436`) on any non-positive `starting_nav` (`validate_account_state` → `starting_nav_invalid`), so line 1408 only ever sees a validated positive number or a fresh-account seed.
- Consumers of newly-nullable fields all safe (13 traced; list below). The switcher sub-line renders `—` for a null return (per-cell mark convention, spec §3 explicitly permits this outside state slots).

## Routing (checklist 3)
`MM_VIEWS`/`_parseHash` (`index.html:6875-6891`): book validated against `_portfolios`/`_PF_ORDER`; view must be in `MM_VIEWS`; ticker decode-then-shape-checked `^[A-Z0-9.\-\^]{1,15}$`. I independently probed hostile fragments (`#/x/position/<img src=x onerror=1>`, `%3Cscript%3E…`, `#/../`, 500-char books, 200-char tickers, quotes, uppercase book) — every one falls back safe; the ticker is only ever compared against held positions and drives `toggleExpand(index)`, never a string sink. Fragment never enters a `fetch` URL (all fetches use fixed paths + `encodeURIComponent(_portfolio)` from the known list) or the response-cache key. `_mmOnRoute` (`:6984`) is idempotent under dual hashchange+popstate (pinned by S7); unheld ticker is dropped from the URL (`:6971-6974`).

## XSS (checklist 4)
All 16 B0 sinks enumerated below — every data-derived string goes through `esc()`, a whitelist, a `^[0-9a-f]{16}$` regex, or `textContent`. Problem codes (which can embed raw ticker text via `position_shares_invalid:<label>`) are slice-then-escaped, capped at 6 shown + counted remainder. No unescaped sink found.

## Truth rows (checklist 5)
- **TR-C**: `index.html:4196-4206` (benchmark word in the stat), `:4276-4291` (legend names it, swatch hidden), `:4461-4464` (no path emitted without a finite `spy_nav`) — pinned by `test_t3_*`, `test_t4_no_finite_benchmark…`, `test_t4_finite_benchmark…`.
- **TR-D(a)**: server `_flat_unpriced_pair` (`web.py:187-206,212-215`) + client word (`index.html:4209-4217`) — pinned by `test_t10_flat_unpriced_pair…`, `test_t10_zero_starting_nav…`. TR-D(b)/(c) are V3/V6/V7 work per the frozen build order (§6 rows 4–5, 9–11 deferred with their views).
- **TR-A**: B0's contribution is negative (account-only rendering; an invalid account renders *no* numbers at all — `:4134,:4298-4305,:5099-5105`); the seeded memo-vs-account DOM test belongs to V1/V2 per the spec's build order. **TR-B** is master's #1707, retained verbatim (`:5155-5167`).
- **D-ACCT-1**: one canonical cell in NAV slot, curve and positions; self-directed takes the sha16 strictly from the quarantine **file name** (`:6422-6432`); evidence tier lists validator codes verbatim/escaped/capped. Pinned by the whole T12 + self-directed suite, including malformed-sha and path-only-sha16 negatives.

## Motion/skeleton (checklist 6)
Exactly one new keyframes `mm-pf-reveal` (140 ms, `prefers-reduced-motion:reduce → animation:none`); base's `mmhb`/`mmEmptyBreathe` untouched. Skeletons are static gradients with `aria-busy`, prose-free; failure is a named line + `role=status` announcement + Retry. Zero hard-coded colours in all B0 CSS blocks (verified by scan). Smooth `scrollTo`/`scrollIntoView` both reduce-motion guarded.

## EN/ZH (checklist 7)
All 24 vocabulary + 2 shell keys carry both languages with matching meaning (qualified/unverified pair 已核实/未核实 is consistent; tab labels idiomatic). No mistranslation found.

## Accessibility (checklist 8)
Tabs are real links, `:focus-visible` ring, `aria-current="page"`, `hidden` tabs removed from the tab order, hidden views removed by `display:none!important`; non-colour cues: ⊘ glyph + 3px rule (book-invalid), dashed hollow pill (unknown market), border/word badges (epi). One `h1` per view is currently **zero** h1 — pre-existing, NIT.

## Tests (checklist 9)
`135 passed in 2.34s`. Discrimination verified against `05a9eb52`: `test_s1_parse_and_format_hash` (no ROUTER marker → slice ValueError), `test_t10_flat_unpriced_pair…` (base computes `0.0`), `test_t10_zero_starting_nav…` (base `0.0`), `test_t5_absent_sleeve_weight…` (base renders "Conviction 0%"), `test_t7_absent_verdict…` (base coerces to `HOLDING`), `test_t8_unknown_session…` (base maps unknown → `closed`/`休市`), `test_t12_probe_reports_invalid_with_sha16` (no `_account_state_probe` → AttributeError), `test_self_directed_invalid_account_is_the_canonical_cell…` (base renders the plain word), `test_s5…` (base has no `mm-skel`/`aria-busy`/`mm-pf-failed`) — all FAIL on base. Weak layer named below.

## Regressions (checklist 10)
Research/Desk/Self keep their own chrome (viewbar hidden, hash writes gated to dashboard, `/research`-`/desk` URLs unchanged — pinned by S8); book switcher, buying power (tightened to inert-until-`ok`, test-pinned), `data-queued-change` all intact. All 19 dashboard sections tagged; nothing orphaned into every view.

```
RETURN pbr-b0-review-r1
VERDICT: PASS
findings:
1. [MINOR] app/web.py:1408 (and :153) — the packet's claim "the silent `or 1_000_000.0` is gone" is not implemented: both defaults are byte-identical to base and B0 renders no starting-NAV slot (spec §9 seat decision 10 lands with V1 per the frozen build order; the live-path coercion is unreachable behind #1756 fail-closed validation, and archived books' 1M default matches their true $1M paper inception, so no new user-visible fabrication) — land the row-10 display rule in V1 as commissioned (or delete the dead coercions now) and correct the PR/packet description so the claim matches the code.
2. [NIT] app/static/index.html:2813 vs :3338 — the viewbar Retry button hard-codes l-en/l-zh spans while `state.retry` ('Retry'/'重试') sits unreferenced; `state.empty`, `state.stale`, `state.closed_market`, `state.queued`, `state.weight_unavailable` are also defined but unused — render the button via t('state.retry') and drop `state.weight_unavailable` (duplicate of `state.unavailable`) or leave the rest as commissioned V1–V7 vocabulary.
3. [NIT] app/static/theme.css:962 — `.mm-epi-badge.qualified{color:var(--up)}` rides the market-direction variable that flips under ZH (red-up/green-down); epistemic ink should be non-flipping — bind qualified to `--ok`.
4. [NIT] app/web.py:1101 — `_account_state_probe` re-reads and re-hashes account.json on every /api/performance (and degraded live-marks) request even when the book is VALID — skip the probe when the preceding performance() read succeeded, or accept the small per-request read.
5. [NIT] app/web.py:265 — for product books the sha16 is the content-hash prefix rather than literally parsed from an `account.quarantine.<16hex>.json` file name (the self-directed path does parse the name, index.html:6422-6432); in the degraded live-marks path the quarantine copy may not exist yet when "Quarantine ref" is shown — equal by construction to the future quarantine file name, but the label slightly anticipates the file.
6. [NIT] app/web.py:196-203 — an all-cash flat pair (invested==0 both rows) keeps a true 0.00%, deviating from the literal TR-D(a) seed ("identical nav/cash/invested → Unavailable"); cash is not inspected — deliberate, docstringed and test-pinned (`test_t10_all_cash_flat_pair_keeps_its_true_zero`); record it as a seat-visible refinement of the spec sentence.
7. [NIT] app/static/index.html (whole page) — pre-existing: the page ships zero `h1`, so "exactly one h1 per view" is currently zero-per-view; B0 adds none — land the per-view h1 with V1.
sinks checked: 16 (index.html:3729 _unavailHtml, escaped; :3736 _overflowHtml, escaped; :3741 _epiBadgeHtml, whitelist+escaped; :3752 _bookInvalidHtml, sha16-regex+escaped; :3769 _bookInvalidEvidenceHtml, slice-then-escaped; :4141 evidence innerHTML, builder-escaped; :4151 navLabel innerHTML, esc(textContent)+whitelisted badge; :4300 curve invalid cell, builder-escaped; :5100 positions invalid cell, builder-escaped; :6438 sd-nav innerHTML, builder-escaped; :6453 sd-nav-status innerHTML, builder-escaped; :6512/:6546 self alloc/positions, esc(t()); :6934-6943 tab hrefs, setAttribute(whitelisted _formatHash)+encodeURIComponent; :7157 data-scope-message, setAttribute+CSS attr() (no HTML parsing); :7162 status, textContent; web.py:268-272 problems bounded/JSON-encoded) — all escaped|textContent, no issue
consumers checked: 13 (index.html:4169 total_return word, ok; :4209 day_change word, ok; :4196 vs_benchmark word, ok; :4226 drawdown word, ok; :4244 cash word, ok; :4315 startNav finite-guard, ok; :7059 switcher ret null→'—'+no class, ok; :8283 auto-banner !=null guarded, ok; :9454-9457 meta.status null-copy, ok; :9514 account_preview→_perf→absent() word, ok; :6469 sd-return null→'—', ok; web.py:1596-1604 portfolios status null-safe, ok; web.py:282/:2327 frozen_as_of-only readers, ok) — no NaN/$0/0%/TypeError path found
tests: 135 passed in 2.34s ; weak tests: test_t1_state_vocabulary_is_exact_in_en_and_zh (string-presence only), test_self_ticket_is_inert_until_book_ok_and_status_is_announced (string containment), the six test_s9_* static-contract tests (no execution), test_performance_clears_previous_cash_when_new_response_is_unavailable (asserts the i18n KEY 'state.unavailable' because its harness stubs t(); the word itself is pinned by T2/T3)
checklist: 1=ok 2=ok 3=ok 4=ok 5=ok 6=ok 7=ok 8=ok 9=ok 10=ok
```

## PRODUCT dispositions

1. MINOR (web.py:1408 `or 1_000_000.0`) — accepted as a description error. Seat decision 10 lands
   with V1 per the frozen build order; the B0 PR body no longer claims it. V1 removes the coercion and
   renders `starting_nav` as Unavailable / 不可用 when absent.
2. NIT (Retry markup, unused vocabulary) — kept. The unused keys are the commissioned V1–V7 §3
   vocabulary and the T1 block is pinned verbatim; the Retry button's static l-en/l-zh pair is the
   house convention for static chrome.
3. NIT (qualified badge on `--up`) — fixed in the post-review delta: `.mm-epi-badge.qualified` binds
   `--ok`, which does not flip under ZH.
4. NIT (probe on every request) — accepted cost: one bounded read-only read and hash per request;
   a cache would add a staleness path to the one cell that must never be stale.
5. NIT (sha16 for product books is the content-hash prefix) — recorded; equal by construction to the
   quarantine file name `paper_account` writes.
6. NIT (all-cash flat pair keeps a true 0.00%) — recorded as a seat-visible refinement of the TR-D(a)
   sentence; deliberate and test-pinned.
7. NIT (zero h1) — lands with V1 (one h1 per view).

Post-review delta (proof-found): the Self-Directed stat tiles rendered the lower-case `unavailable`
in EN (`sd.unavailable`); the §3 word is `Unavailable`, so the key now carries it. The delta is
three source lines plus one comment across two changes (that word, and disposition 3's
`.mm-epi-badge.qualified` rule on `--ok`), plus the three test pins. Scoped re-review: r2.
