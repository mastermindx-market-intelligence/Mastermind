# Review record — lr-a03-r2 (PR #1709 A03 PIT marks, re-review after the r1 BLOCKER repair)

Lane: pool `ubuntu1`, model glm-5.3 (pool glm-frontier), class review C2_COMPLEX_BOUNDED, run-id `pbr-econ-lr-a03-r2`, 2026-10-22T11:18Z–11:25Z, rc=0. Read-only; remote worktree removed after the run.
Reviewed head: #1709 b4426142 (repair commit over 74bb3eb3, which lr-a03-r1 reviewed).
Verdict: PASS #1709 (no findings; r1 BLOCKER RESOLVED).

ECON disposition:
- r1 BLOCKER (test_desk_ab regression): RESOLVED. 22/22 on HEAD and on master. Two scratch mutations (hold-guard removed; build loop skipping prod) are each caught by the repaired tests. The production delta 74bb3eb3..b4426142 is AST-identical for portfolio/desk_ab.py and portfolio/shadow_books.py.
- Regression matrix: every shared test file has identical per-id outcomes on HEAD and master. The test_safety pair (test_full_report_shape_and_ranges, test_bootstrap_ci_present) fails on both trees; it is pre-existing and outside this PR.
- r1 MINORs 2 and 3 were not re-raised; their dispositions in lr-a03-r1.md stand.
- #1709 is reserved (mark selection). It is green and independently reviewed at b4426142, and is returned to the seat for the acceptance row. ECON does not merge it.
- Reviewer note: CONTRACTS.md was read from origin/pbr/econ-contracts (#1699), because the packet's paths are not on master until #1699 lands.

---

# Independent re-review — LR-A03-R2: PR #1709 (A03 point-in-time marks) at head `b4426142`

## Setup

- Working tree verified: detached at `b4426142` = `origin/pbr/econ-a03-pit-marks`, clean. Repair range `74bb3eb3..b4426142` is exactly one commit touching 3 files.
- **Contract note:** `CONTRACTS.md` is absent at the packet's two named paths (`origin/pbr/econ-hk-bridge`, `origin/master`). Searched all local refs; it exists only on `origin/pbr/econ-contracts`, from which I read §(b) A03 in full (items 1–8 + acceptance). §(b):196 confirms the #728 same-day rule this review re-checks ("live-quote fill is allowed only when `mark_asof == today`").
- Scratch: `~/lanes/tmp/pbr-econ-lr-a03-r2/{head,master,pre,mutA,mutB}` via `git archive`. All tests run with the packet's pytest invocation. Nothing in the working tree was modified; no network.

## Check 1 — r1 BLOCKER resolution: **RESOLVED**

- `tests/test_desk_ab.py`: **HEAD 22/22** (run twice, deterministic), **master 22/22**.
- `diff` of the test file HEAD vs master: the two tests' **assertions are byte-identical**; only the two `desk_ab.run(...)` call sites changed (gained the dated `prices=` seed + a comment). Test 1 still asserts SMH in `prod` holdings, `no_etf` drops SMH, clone replays `["AME"]`, all policy ids in the leaderboard, sandbox account.json exists. Test 2 still asserts held-not-liquidated shares on the carried day, `holdings == ["AME"]`, and a 06-23 NAV row.
- **No weakening — proven by scratch mutations:**
  - **Mut-A** (`portfolio/desk_ab.py:359` guard `if targets or _has_inputs:` → `if True:`, i.e. carried day rebalances to empty targets): `test_carried_day_empty_inputs_holds_not_liquidates` **FAILS** at the carried-day assertion (`tests/test_desk_ab.py:293`, positions `{}` → shares 0). Seeded prices did not mask the liquidation trap — the seeded AME price actually makes the mutated rebalance *execute* the liquidation.
  - **Mut-B** (build loop skips the `prod` book): `test_run_isolates_to_sandbox_and_builds_all_books` **FAILS** at `tests/test_desk_ab.py:221` (leaderboard missing `prod`).
  - The seeding is the contract-compliant dated path, and it preserves the original failure detection: if either the seed consumption or the same-day guard regressed, the historical asof leaves the names unpriced and test 1 fails — precisely the pre-repair HEAD failure mode. The leftover `_current_price` monkeypatch is inert on HEAD (never consulted for a historical asof) and its misuse is independently pinned by `test_shadow_books_price_clock.py::test_historical_shadow_gather_never_calls_undated_current_price` (a `pytest.fail` probe).

## Check 2 — production delta non-semantic: **PROVEN**

All three hunks of `74bb3eb3..b4426142`, quoted:

1. `portfolio/desk_ab.py` (EOF hunk, sole change is adding the trailing newline; the `\ No newline at end of file` marker is on the `-` side only):
   ```diff
   -    return S._update_theses(book_id, policy, eff_inputs, targets, asof)
   \ No newline at end of file
   +    return S._update_theses(book_id, policy, eff_inputs, targets, asof)
   ```
2. `portfolio/shadow_books.py:118` (comment text only):
   ```diff
   -    if policy["calibration"]:                              # exactly what prod did (calib on)
   +    if policy["calibration"]:                              # exactly what prod did (committee+calib on)
   ```
3. `portfolio/shadow_books.py` (EOF hunk, trailing newline only):
   ```diff
   -        return {}
   \ No newline at end of file
   +        return {}
   ```

Proof beyond quoting: `ast.dump(ast.parse(...))` is **identical** between `74bb3eb3` and `b4426142` for both files. Comments and trailing newlines cannot alter the AST, so no executable statement changed.

## Check 3 — same-day guard: **HOLDS**

- `tests/test_shadow_books_price_clock.py`: **3/3 on HEAD** (historical asof never consults `_current_price`; same-day admitted; explicit seed authoritative).
- Guard code confirmed at `portfolio/shadow_books.py:389` (`mark_asof = str(asof)[:10] if asof else str(date.today())`) and `:398` (`if mark_asof == str(date.today()):` — the undated `_current_price` fill sits strictly inside this branch).
- **One adversarial test of my own** (scratch `tests/test_adv_lr_a03_r2.py`, passes on HEAD): a **future** asof (`"2027-01-01"`) and a **full-timestamp** asof (`"2026-06-01T15:30:00"`, truncated to its date) both refuse the undated accessor (guard is `== today`, not `<= today`), while `asof=None` — the live daily flow's default — still receives the emergency fallback, proving the guard doesn't over-block the default path.

## Check 4 — no regression elsewhere: **CLEAN**

Per-test-id comparison (both trees, same host):

| file | HEAD | master |
|---|---|---|
| test_marks_observation_basis.py | 18 P | n/a (new) |
| test_portfolio_marks_point_in_time.py | 8 P | n/a (new) |
| test_desk_ab_asof_propagation.py | 1 P | n/a (new) |
| test_shadow_books_price_clock.py | 3 P | n/a (new) |
| test_marks.py | 10 P | 10 P |
| test_daily_marks.py | 27 P | 27 P |
| test_interim_marks.py | 3 P | 3 P |
| test_shadow_books.py | 23 P | 23 P |
| test_settle_open_price.py | 14 P | 14 P |
| test_cash_yield.py | 7 P | 7 P |
| test_safety.py | 16 P / 2 F | 16 P / 2 F (identical ids) |
| test_portfolio_eod_marks.py | 11 P | 11 P |
| test_desk_ab.py | 22 P | 22 P |

Every shared file has **identical test ids and identical outcomes** on both trees; zero differences to name. The two `test_safety` failures (`test_full_report_shape_and_ranges`, `test_bootstrap_ci_present`, both `assert None is not None`) are pre-existing environment/data failures, byte-identical across trees. Host note: this host has `vendor/macro` present, so `test_portfolio_eod_marks` is 11P here vs 8F/3P on r1's vendor-less host — a host-data difference, identical across trees either way.

## Check 5 — authority grep: **CLEAN**

Over all added lines of `git diff origin/master...b4426142`:
- `balanc` / `rewrite`: **zero** hits. `reset`: one hit, inside a comment ("...stale mark live forever by resetting its own asof") — prose, no code.
- `seed` executable hits: `portfolio/marks.py` — `"seed": 0` counter init and the seed-row emission `px, src, stale = float(seed[sym]), "seed", 0` + `observed, basis, time_kind, close_qualified = asof, "unknown", "seed", False`. This is the **pre-existing** seed-price mechanism (master `marks.py:142–182,214` already short-circuits `seed` as a trusted mark), extended with the new observation fields; source label, not an account seed. `portfolio/shadow_books.py` — `marks.prices_for(want, mark_asof, seed=px, persist=False)` passes the caller's dated price dict through. Remaining hits are docstring/comment prose and test fixtures.
- `avg_cost`: only "never touches avg_cost" prose. The one `avg_cost` *use* near the diff (`portfolio/desk_ab.py:393`, thesis-entry synthesis for the clone grader) is **pre-existing on master** (`master:393`), untouched by this PR, and not a mark path. `desk_ab.py`'s entire executable delta vs master is one line: `S._gather_prices(needed, prices)` → `S._gather_prices(needed, prices, asof)`.
- No account reset, no seed rewrite, no balancing fill, no avg_cost-as-mark.

## Check 6 — r1 MINORs: not re-raised

- `portfolio/shadow_books.py:389,398` machine-local `date.today()` same-day bound: still present, still fallback-only (only the emergency `_current_price` admission around UTC midnight). Unchanged from r1's grading; my evidence does not make it worse.
- `tests/test_portfolio_marks_point_in_time.py:101` unpinned `_polygon_eod("AAPL", "2026-06-01")`: still unpinned, still fails only on a host clocked before 2026-06-01. Unchanged; not worse.

## Findings

**None.** The repair is tests-only over a provably non-semantic production delta; the regression is closed without weakening either test; all contract-relevant guards hold under mutation and adversarial probing.

```
RETURN pbr-econ-lr-a03-r2
head: b4426142
findings: none
blocker_r1: RESOLVED — tests/test_desk_ab.py 22/22 on HEAD (run twice) and 22/22 on origin/master; the two tests' assertions are byte-identical to master (diff = the two desk_ab.run calls gained the dated prices= seed + comments only); mutations prove no weakening: Mut-A (desk_ab.py:359 hold-guard removed → carried-day rebalance to {} ) fails test_carried_day_empty_inputs_holds_not_liquidates at :293 (positions {}); Mut-B (build loop skips prod) fails test_run_isolates_to_sandbox_and_builds_all_books at :221 (leaderboard missing 'prod'); a guard- or seed-consumption regression reproduces the original unpriced-name failure the test already detects.
tests: file | HEAD | master — test_desk_ab 22P|22P; test_marks 10P|10P; test_daily_marks 27P|27P; test_interim_marks 3P|3P; test_shadow_books 23P|23P; test_settle_open_price 14P|14P; test_cash_yield 7P|7P; test_safety 16P/2F|16P/2F (identical ids: test_full_report_shape_and_ranges, test_bootstrap_ci_present — pre-existing); test_portfolio_eod_marks 11P|11P (11P here vs 8F/3P on r1's host: vendor/macro present on this host; identical across trees); new files on HEAD: test_marks_observation_basis 18P, test_portfolio_marks_point_in_time 8P, test_desk_ab_asof_propagation 1P, test_shadow_books_price_clock 3P (absent on master, n/a). Per-id diff: zero differences on every shared file.
mutations: (1) desk_ab.py hold-guard `if targets or _has_inputs:` → `if True:` — carried-day test CAUGHT (shares 0, positions {}); (2) build loop `if bid == "prod": continue` — builds-all-books test CAUGHT (leaderboard missing prod). Production non-semantic proof: ast.dump identical between 74bb3eb3 and b4426142 for portfolio/desk_ab.py and portfolio/shadow_books.py (3 hunks = 2 EOF-newline restorations + 1 comment-word change, all quoted above).
VERDICT: PASS #1709 — the r1 BLOCKER (test_desk_ab regression) is repaired tests-only over an AST-identical production delta, both repaired tests still catch liquidation and missing-book mutations, the #728 same-day guard refuses historical/future/timestamp asofs while admitting today (existing 3 tests + 1 adversarial), all shared suites are identical to master per test id, and the authority grep is clean (seed = pre-existing dated-seed mechanism, no reset/balanc/rewrite/avg_cost-as-mark).
commands_run: git rev-parse HEAD/origin/pbr/econ-a03-pit-marks (=b4426142, clean tree); git log/diff 74bb3eb3..b4426142 (1 commit, 3 files, hunks quoted); CONTRACTS.md located via all-ref ls-tree (absent at both packet paths; read from origin/pbr/econ-contracts) §(b) A03; git archive → {head,master,pre,mutA,mutB}; pytest test_desk_ab on HEAD×2 and master; per-id outcome matrix (13 files × head+master, --tb=no -v, python per-id comparison); mutation runs mutA/mutB; test_shadow_books_price_clock + scratch tests/test_adv_lr_a03_r2.py (passes); AST equality check pre/head; authority grep (all added lines + executable-lines-only pass); r1-MINOR site inspections (shadow_books.py:389,398; test_portfolio_marks_point_in_time.py:101); master marks.py seed-mechanism confirmation (master:142-182,214); desk_ab.py full delta vs master (one line, _gather_prices gains asof).
not_verified: live Polygon/yahoo network paths (offline mandate; all feeds injected/monkeypatched); CONTRACTS.md at the packet's two named paths (absent on both — read from origin/pbr/econ-contracts, the only ref carrying it); the PR description on the forge (local refs only); the 2 pre-existing test_safety failures' root cause (identical on both trees, outside this PR's gate); master-side behaviour of the 4 new test files (absent there by design).
```
