# pbr-p3b-review-r1 — independent leaf review of Mastermind PR #1719 at ad804111

- Lane: `pbr-p3b-review-r1`, Fabric remote on ubuntu1, glm-5.3-flash, POOL_TASK_CLASS=review, C2.
- Reviewed head: `ad804111e876f8547aedecd4b22ce0ba83c48365` (the head the seat named).
- Builder ≠ reviewer: a separate review lane on a fresh detached worktree; it did not build the change.
- Retained verbatim below, then PRODUCT dispositions.

## Reviewer output (verbatim)

All verification complete. The parent confirms discrimination: `$1,000,000` seed, `fmtNav((_self || {}).cash || 0)` fallback, no markers, no `status` key, `1000000` in the except bytes — every behavioral test fails there. Summarizing the review:

**Checklist results:**
1. **Scope** — exactly the 4 declared files.
2. **API truth** — both `except` branches (web.py:2431-2435, 2451-2455) return `status`/`reason_code`, null every previously-fabricated money/rate field (`nav/cash/invested/starting_nav/allocation`, `realized_total/n_closed/n_buys`), and replace the fabricated `market: closed` with the real clock or `null`. The `try` paths are byte-unchanged (diff touches only the except hunks).
3. **Consumers** — 15 checked; every one is either gated on the new state machine or null-safe. Buying power and the order-ticket estimate render `unavailable` instead of `$0`, and Buy/Sell are disabled when the settled book is unreadable; the order endpoint also fails safe server-side (`500 {ok:false}`, web.py:2479-2484).
4. **SPA states** — `pending`/`unavailable`/`ok` tristate implemented (index.html:5997-6011); header, alloc, positions, history, market label each handle it; markup seed is `—`; heartbeat static+muted only under `data-availability="unavailable"`; only `var(--muted)` used, and the `body.page-mm` selector variant wins specificity.
5. **EN/ZH** — all 4 new keys carry both languages with matching meaning.
6. **Tests** — `18 passed in 0.47s`; discrimination verified against `git show d31aade92b:...`.
7. **Other** — five NITs (below), including the disclosed pre-existing `_load_account` fabrication (E13) that this PR does not touch and does not worsen.

```
RETURN pbr-p3b-review-r1
VERDICT: PASS
findings:
1. [NIT] app/web.py:2434,2453 — unavailable payloads keep `positions/pending/history` as `[]`, so a raw API client that ignores `status`/`reason_code` reads "zero positions/fills"; the SPA gates every renderer, so nothing renders 0 — optional: null them (SPA is already null-safe) or document as structural empties.
2. [NIT] app/static/index.html:6061 — `_mktLabel` returns cls `closed` for an unknown session, so the pill looks "closed" while its text truthfully says "Market status unavailable" (and the pill leaves its `—` seed during pending); a distinct neutral class would separate unknown from closed.
3. [NIT] app/static/index.html:6344-6357 — during the pending window `bookUnknown` is false, so Buy is clickable while buying power already reads "unavailable", unlike the code comment "stays inert until it settles readable"; server fails safe (web.py:2479-2484 returns {ok:false} on an unread account), so no blind trade executes — stricter gate would be `!== 'ok'`.
4. [NIT] portfolio/self_directed.py:68-78 (pre-existing, untouched) — `_load_account()` still returns a fabricated fresh $1M book when the account file is present-but-malformed, so that corruption class never reaches the fixed except branch; disclosed in review_evidence/pbr/p3b-self-unavailable/README.md as open ECON E13; this PR neither regresses nor worsens it.
5. [NIT] app/static/index.html:3115 — the new `sd-nav-status` reason line has no aria-live, so an ok→unavailable transition mid-session is not announced to screen readers (codebase uses aria-live elsewhere); cosmetic.
consumers checked: 15 — app/web.py:2431 (book unavailable payload, ok), app/web.py:2451 (history unavailable payload, ok), app/web.py:2479 (order endpoint, ok — fails safe server-side), app/static/index.html:6013 renderSelfHeader (ok — gated; ok-path nav guaranteed numeric by _selfBookState), :6060 _mktLabel (nit #2), :6068 renderSelfMarket (ok — no payload numbers), :6080 renderSelfAlloc (ok — gated), :6112 renderSelfPositions (ok — gated), :6188 renderSelfPending (ok — blank host, no "0 pending" claim), :6211 renderSelfHistory (ok — gated; n_closed/n_buys null-safe), :6315 renderSelfSelected buying power (ok — isFinite guard, else `unavailable`), :6338 selfUpdateEst (nit #3), :5976 _heldShares (ok — 0 only behind ok-state), :8756 _mergeLiveMarks (ok — settles on success-only live book), :8916 _applyPortfolioSnapshot (ok — hasOwnProperty + settled, null snapshot → unavailable); no Python HTTP consumer of the two GET endpoints exists (grep: auth lists POSTs only; scheduler reads self_directed directly, not the route).
tests: 18 passed in 0.47s ; weak tests: test_api_self_directed_success_path_is_unchanged passes on both parent and head — intentional positive control for the "success path unchanged" requirement; all other tests verified to FAIL on d31aade92b (parent has the $1,000,000 seed, `fmtNav((_self || {}).cash || 0)`, `cash = (_self || {}).cash || 0`, no PBR markers, no `status` key, `1000000` in the except bytes)
checklist: 1=ok 2=ok 3=ok 4=ok 5=ok 6=ok 7=ok (NITs #1-#5 above; E13 dependency disclosed, not touched)
```

## PRODUCT dispositions (pbr-product, 2026-10-22)

VERDICT PASS consumed; #1719 queued at `ad804111` (`gh pr merge 1719 --squash --match-head-commit ad804111…`, merge-queue entry QUEUED 13:41:11Z).

1. NIT raw-client `[]` lists — accepted as documented: `status`/`reason_code` are the contract and every SPA renderer gates on them. No change.
2. NIT `_mktLabel` unknown → `closed` class — taken into B0 as the self-directed sibling of §6 row 14 (an unmapped session state is `Unavailable`, never closed).
3. NIT Buy clickable during `pending` — taken into B0: the order ticket stays inert until the book state is `ok` (server already fails safe, web.py order endpoint returns `{ok:false}`).
4. NIT `_load_account()` malformed-file fallback — ECON contract request E13, open; out of PRODUCT scope; this PR does not worsen it.
5. NIT `sd-nav-status` without `aria-live` — taken into B0 (one attribute, `aria-live="polite"`).

No repair to #1719 itself: all five are NIT class; the three PRODUCT-side ones land in B0 under B0's own frontier review.
