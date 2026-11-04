# Review record — lr-a12b2-r1 (PR #1752, scoped re-review of the LR-A12B repair)

**Lane:** pool `ubuntu1`, model glm-5.3-flash, class review C1_ROUTINE_BOUNDED, run-id `pbr-econ-lr-a12b2-r1`, 2026-10-22T14:18Z–14:23Z, rc=0. Lane worktree and tmp removed afterwards; removal verified.

**Reviewed head:** #1752 3ccee19804002500e44bb953584a1638d48fed46. The repair is diffed against the r1-reviewed head e25a7c6f.

**Verdict: PASS #1752.**
- Scope: TEST_ONLY. The only change is `tests/test_benchmark_window_consumers.py`, +17/−0.
- Mutation (iv) is now caught by `test_attribution_book_term_is_window_return_not_stored_return_pct`.
- Mutation (i), which r1 left unverified because fastapi was absent, is caught by `test_web_self_directed_vs_spy_on_shared_window`.
- Pristine run: 7 files, 160 passed.
- Findings: none. not_verified: none.

## ECON disposition
- r1's BLOCKER 1 is closed by this re-review.
- r1's MINORs 2–4 stand as dispositioned in `lr-a12b-r1.md`: follow-up candidates outside ECON, or unreachable. None is repaired here.
- Scope rule: this was a scoped re-review of the changed risk, not a restart of the full review. The production code is unchanged since r1 reviewed it at e25a7c6f.
- Merge: #1752 is RESERVED, so it returns to the seat. The commit that adds this file is docs-only and sits after the reviewed head 3ccee198.

---

All checks complete. Both scratch mutations were caught, scope is clean, and the pristine suite is green.

**Check 1 — Scope:** `git diff --stat` (verified with exact full refs) between `e25a7c6f…` and `3ccee198…` shows exactly one file, `tests/test_benchmark_window_consumers.py`, +17/−0 — a single new test `test_attribution_book_term_is_window_return_not_stored_return_pct`. No production file touched. TEST_ONLY.

**Check 2 — Mutation (iv):** With `book_ret = (row.get("return_pct") or 0) / 100.0` in `brain/attribution.py:478`, the new test fails: `assert -0.4 == 0.15` — exactly the stored-term arithmetic (−50% book − (−10%... SPY −10%) = −40%). Fixture divergence is confirmed inside the test itself: `stored == pytest.approx(-50.0)` passes while the window curve 1.00→1.05 is +5%. Caught by `tests/test_benchmark_window_consumers.py::test_attribution_book_term_is_window_return_not_stored_return_pct` (44 others still pass).

**Check 3 — Mutation (i):** fastapi imports (0.143.3), so this is now verified. With `vs_spy_pct = book since-inception − ledger["bogeys"]["spy"]["return_pct"]` in `app/web.py`, `tests/test_benchmark_window_consumers.py::test_web_self_directed_vs_spy_on_shared_window` fails (`assert -80.0 == 10.0`); the 53 other tests in the two files pass.

**Check 4 — Pristine:** all seven files pass, 160 passed total, per-file counts sum exactly to that.

```
RETURN pbr-econ-lr-a12b2
head: 3ccee19804002500e44bb953584a1638d48fed46
scope: TEST_ONLY
mutation_iv: tests/test_benchmark_window_consumers.py::test_attribution_book_term_is_window_return_not_stored_return_pct
mutation_i: tests/test_benchmark_window_consumers.py::test_web_self_directed_vs_spy_on_shared_window
tests: tests/test_benchmark_window_consumers.py | 23/0
tests: tests/test_attribution.py | 22/0
tests: tests/test_benchmark_ledger.py | 21/0
tests: tests/test_benchmark_ledger_latest.py | 23/0
tests: tests/test_firm_allocator.py | 27/0
tests: tests/test_improvement_agenda.py | 13/0
tests: tests/test_self_directed.py | 31/0
findings: none
VERDICT: PASS #1752 — repair is test-only; the new window-return test catches the reverted book term (stored −50% vs window +5%) and the previously-unverified web Self-Directed mutation is also caught now that fastapi is present (all 160 pristine tests pass).
commands_run: git log --oneline -3; git status; git diff --stat e25a7c6f… 3ccee198… (full-ref re-run + full diff read); git archive 3ccee198 → scratch pristine/mut_iv/mut_i; Edit mut_iv brain/attribution.py:478 book_ret=(row.get("return_pct") or 0)/100.0; pytest mut_iv test_benchmark_window_consumers.py test_attribution.py (1 failed / 44 passed); python -c "import fastapi" (0.143.3 OK); Edit mut_i app/web.py vs_spy_pct=total_return_pct−ledger bogey spy return_pct; pytest mut_i test_self_directed.py test_benchmark_window_consumers.py (1 failed / 53 passed); pytest pristine 7 files (160 passed; per-file 23/22/21/23/27/13/31)
not_verified: none
```
