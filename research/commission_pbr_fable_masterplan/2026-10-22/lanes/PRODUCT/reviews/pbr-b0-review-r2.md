# PBR B0 — scoped delta review r2 (independent, frontier class)

- Reviewer: fabric lane `pbr-b0-review-r2`, ubuntu2, glm-5.3 (frontier class, C2, escalation reason recorded)
- Builder: pbr-product (Opus orchestrator) — not the reviewer
- Exact head reviewed: 2f6ee76f3dd6c956c895011a41cc6a5e4bb582f5
- Scope: the post-r1 delta (sd.unavailable word, qualified badge ink, test pins) and the seven r1 dispositions

## Disposition

1. NIT (r1 record sentence understated the delta) — fixed in this commit: the r1 record now states three source lines plus one comment across two changes, plus three pins.

## Reviewer output (verbatim)

All four claims verified. Final assessment:

**Claim 1 — `sd.unavailable` EN word (index.html:3653).** Now `'Unavailable'`, matching spec §3 (`docs/superpowers/specs/2026-10-22-pbr-product-views.md:436`: "unavailable | Unavailable | 不可用 | the word in the value slot, muted, never a number") and the existing token keys `state.unavailable`/`state.weight_unavailable` (both 'Unavailable'). All consumers: 4 Self-Directed tiles via `un` (:6451–6454), NAV slot (:6448), two trades-summary stat values (:6655–6656), and two in-sentence compositions (:6754, :6785). The in-sentence uses render "Buying power Unavailable" — mid-sentence capitalisation, but that is exactly the house token pattern already shipped at index.html:4822 (`t('alloc.' + key) + ' ' + t('state.unavailable')` → "Conviction Unavailable") and spec rows 546–547 ("weights render `Unavailable`"); the word functions as a state token, not prose, so it does not read wrong. No consumer embeds it inside lowercase prose — the prose-style keys (`sd.unavailable_reason`, `sd.mkt.unknown`, `state.risk_unavailable`) are separate and untouched. ZH unaffected.

**Claim 2 — `--ok`.** Defined in dark `:root` (theme.css:19) and light (theme.css:54); the ZH blocks (:76–79, :81–85) rebind only `--up/--down/--q1/--q3` — the block comment explicitly leaves status colours (`--ok/--warn/--act`) alone. Non-flipping in both themes, as claimed.

**Claim 3 — pins discriminate.** All three updated pins are exact-match assertions that fail on the old value: `test_pbr_self_unavailable.py:232,247` asserts the literal substring `en: 'Unavailable'` in the i18n body; `test_pbr_b0_truth_rows.py:745→760` asserts exact tile-text equality via the node renderer; `:795` asserts exact sd-nav text equality. None is string-presence-only.

**Claim 4 — dispositions.** All seven check out at 2f6ee76f: D1 `or 1_000_000.0` still at web.py:1408 (accepted, no change claimed); D2 Retry button still hard-coded at index.html:2814 with `state.retry` (:3330) and `state.empty/stale/closed_market/queued/weight_unavailable` consumer-less — grep confirms no `t('…')` uses; D3 fixed exactly as dispositioned; D4 `_account_state_probe` unchanged at web.py:251; D6 `test_t10_all_cash_flat_pair_keeps_its_true_zero` exists (:487) and passed; D7 zero `<h1` in index.html. One imprecision: the closing delta paragraph says "Two lines plus pins" — the delta is 3 source lines + 1 comment (and also carries disposition 3's badge fix, which the paragraph doesn't mention). Cosmetic, retained-doc only.

```
RETURN pbr-b0-review-r2
VERDICT: PASS
findings:
1. [NIT] research/commission_pbr_fable_masterplan/2026-10-22/lanes/PRODUCT/reviews/pbr-b0-review-r1.md:85-86 — the delta paragraph says "Two lines plus pins" but the delta is 4 source lines across two changes (the sd.unavailable word plus disposition 3's badge fix, which the paragraph omits) — correct the record sentence for accuracy of the retained log
consumers checked: 9 render paths / 6 call sites (index.html:6448 sd-nav standalone, ok; :6451 sd-cash tile, ok; :6452 sd-invested tile, ok; :6453 sd-unreal tile, ok; :6454 sd-return tile, ok; :6655 trades-summary stat, ok; :6656 trades-summary stat, ok; :6754 switcher "Buying power Unavailable" label+token = house pattern of :4822, ok; :6785 estimate line same pattern, ok)
tests: 121 passed, 0 skipped, 0 failed in 2.18s (node v22.23.3 present, so all @requires_node tests executed — no skips to report)
```
