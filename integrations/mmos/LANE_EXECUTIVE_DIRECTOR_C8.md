# Lane: Director C8 — guard r9, quote-adjacent glue + unarmed watchdog (2026-11-09)

Branch `t3/guard-r9-quote-glue`, created from `t3/t3-hermes-restart-recovery` at
`798152b7c` (r8 merged). Implementation by Claude Opus 5.5 (native ORCHESTRATION route)
answering distinct review #4 (REVIEW4: A4 NEEDS_REWORK — F1 MAJOR, F4 MINOR, depth note).
No push, no PR; no other worktree, `~/Mastermind`, `~/.hermes` or `~/.claude/settings.json`
touched. Files: the guard module, the policy test module (append-only), this ledger.
`provider_orchestrator_policy.py` is untouched. SELF_REVIEWED; CRITICAL row — the delta
needs a fresh distinct re-review.

No real wrapper was invoked. Every shell ground-truth run is sealed:
`/usr/bin/env -i PATH=<fake-wrapper dir>:/usr/bin:/bin HOME=<tmp> zsh -f -c …` and
`… /bin/bash --norc --noprofile -c …`; the fakes only `touch <tmp>/ran/<name>-$1`.
(A first ad-hoc sealed-shell probe was stopped by the harness's removal checker before it
ran — it contained no `rm`; the ground truth was then run only through the committed
pytest test.)

## Commits

| Commit | Content |
|---|---|
| (code) | r9 guard + 76 new tests (no existing test line changed or removed) |
| (this file) | Ledger |

## Finding → fix → test

| # | Sev | Finding | Fix (r9) | Tests |
|---|---|---|---|---|
| F1 | MAJOR (REVIEW4) | `_R6_ROUGH_WORD_SPLIT_RE` treats `"`, `'`, `\` as word SEPARATORS in both partial-word readers (`_r8_computed_glue`'s `literal()` and the `marked` partial reader in `r6_names_wrapper`); the shell's quote removal JOINS adjacent quoted/unquoted segments → `${x:-p}"ool" run grok …` armed, no binding: ALLOWED (sealed zsh/bash run `pool`) | **Joined reading, added to both readers** (union with r8's readings — never narrower): `_r9_joined(text)` = `$"`→`"`, then delete every `"`, `'`, `\` (one `replace` + one `sub`, linear); words then split on blanks and operators only (`[\s;&|<>()]+`). `r6_names_wrapper` now runs the partial reader on `_r9_joined(marked)` and `_r8_computed_glue(text) or _r8_computed_glue(_r9_joined(text))` (each view recurses within itself: 2× r8's cost, no cross product) | `test_r9_quote_glue_escapes_are_judged_and_refused[16]` (deny bound AND unbound, R6_* shape refusal, gate not reached), `test_r9_sealed_shells_run_each_quote_glue_shape` (ground truth, 28 shell runs), `test_r9_reviewer_row_through_the_real_hook_command_line`, `test_r9_scope_escape_table_covers_every_reviewer_shape`, `test_r9_quoting_never_takes_a_word_out_of_scope` (6 000 random words), non-regression rows, budget rows |
| F4 | MINOR (REVIEW4, availability) | watchdog armed only in armed sessions; with `onFailure: "block"` an UNARMED session on adversarial `gh` CI-wait text stalls to the 10 s kill and is BLOCKED | **Choice (a): the watchdog runs in every session.** Armed: exactly r8 (firing → DENY "guard budget exceeded — fail closed", 7 s default). Unarmed: firing → **no decision** — `main()` returns normally, exit 0, nothing written (never an allow). Handler restored and timer disarmed in all paths | `test_r9_unarmed_adversarial_ci_text_is_no_decision_well_inside_the_timeout` (real hook CLI, default 7 s budget), `test_r9_unarmed_watchdog_firing_writes_nothing[5]`, `test_r9_armed_adversarial_ci_text_still_denies_on_budget`, `test_r9_honest_unarmed_gh_commands_are_unchanged[8]`, `test_r9_unarmed_watchdog_in_process_restores_the_handler`; the r8 test `test_r8_watchdog_is_off_for_unarmed_sessions_and_after_a_verdict` (asserts empty unarmed output) is unchanged and green |
| D | NOTE (REVIEW4 depth) | ledger C6 said "construct nesting > 8"; honest `echo $(…)` chains go in scope at k = 10 | **Doc fixed, code unchanged**: the reader recurses into a body only when it holds `$`/backtick, so k nested constructs are read to reader depth k−1; the cap fires at reader depth 9 → in scope from **k = 10** (k ≤ 9 out). Stated in the `_R8_MAX_CONSTRUCT_DEPTH` comment | `test_r9_construct_depth_boundary_is_ten_nested_constructs` (k = 1…9 out; 10, 11, 16 in) |

### The F1 rule change, stated precisely

r8: a word is read by splitting the text on `[\s;&|<>()"'\\]+` (quote characters and
backslashes are separators), in two readers: (1) the `marked` reader (constructs replaced
by `\x00` via `_R6_COMPUTED_RE` passes, each word's basename tested by
`_r6_partial_wrapper`), (2) `_r8_computed_glue` (bracket-nesting spans → items, literal
pieces split, ≤ 14-state DP per word).

r9: each reader ALSO reads the joined text — `$"` replaced by `"`, then every `"`, `'` and
`\` deleted — and splits it on `[\s;&|<>()]+`. A command is in scope if r8's readings OR the
joined readings name a wrapper. Consequences:

* Quoting is shell-transparent for scope: whenever an unquoted spelling is in scope, the
  spelling with its literal pieces wrapped in `"…"`/`'…'`, backslash-escaped, separated by
  `""`/`$""`, or with a construct wrapped in `"…"`, is in scope too (property test).
* Splitting the joined text also at QUOTED blanks/operators is deliberate and safe: a
  wrapper basename contains no blank or operator character, so a quoted blank/operator
  either lies inside the final path component (then the shell's basename is not a wrapper)
  or before the last literal `/` (then the split piece still contains that `/` and the
  basename restart). Over-reading here only widens scope.
* Over-reads (all toward wider scope, i.e. armed refusal): `\\` (escaped backslash) is
  deleted entirely; a quote character that is literal inside the other quote kind
  (`"it's"`) is deleted; an escaped blank (`p\ ool`) splits.
* Kept OUT (documented arbitrary-process limit, unchanged): wholly computed words —
  `$W run`, `"$W" run`, `$(([##36]1198389))`, `"$(([##36]1198389))" run`,
  `$(printf p)$(printf ool) run`, `"$(printf p)$(printf ool)" run`.
* NOT newly refused (tests): `cd ${HOME:-/Users/me}`, `cd "${HOME:-/Users/me}"`,
  `cd "${HOME:-/Users/me}"/src`, `echo ${name//-/_}`, `echo "${name//-/_}"`, `"p"`,
  `echo "p"`, `echo "${PORT:-8080}"`, `echo $($(echo hi))`,
  `git log "$(git merge-base a b)"..HEAD`, `echo "$HOME" "notes"`,
  `python3 "$ROOT"/scripts/run.py`, `printf '%s\n' "$x" 'ok'` stay out of scope; in-scope
  data keeps its r8 armed verdict ALLOW bound and unbound, gate not reached:
  `echo "pool"`, `echo 'pool run is a wrapper'`, `grep -n "slot.py" docs/runbook.md`,
  `cd ${HOME:-/Users/me} && echo ok`, `echo "${name//-/_}"`.
* Newly in scope by design (quoted twin of an r8-in-scope unquoted form): e.g.
  `"$v".sh`, `"${v}".py`, `"${x:-p}""${x:-p}"` (joins to r8's E3 shape). In an ARMED
  session an honest `bash "$name".sh` is therefore refused exactly as r8 already refused
  `bash $name.sh`. Unarmed sessions are unaffected (their census needs a wrapper head).

## F1 rows — fail-before (r8) → after (r9), real hook command line

Armed session. BOUND = owner-channel shim (every binding check reachable); UNBOUND = real
`python3 "<guard>"`, no binding. Args `run grok a /tmp grok-4` (slot.py row: `glm a /tmp glm-5.3`).
Gate reached: **no** for every r9 row (refused by shape before the binding gate, in both
sessions). Ground truth = sealed shells actually ran a fake wrapper.

| Row | Command | r8 bound / unbound | r9 bound / unbound | Ground truth |
|---|---|---|---|---|
| dq-suffix | `${x:-p}"ool" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH / same | zsh ✓ bash ✓ |
| sq-suffix | `${x:-p}'ool' …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| dq-construct-then-literal | `"${x:-p}"ool …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| backslash-suffix | `${x:-p}\ool …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| dq-suffix-two-default-chars | `${x:-po}"ol" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| cmdsub-dq-suffix | `$(printf p)"ool" …` | **ALLOW / ALLOW** | deny R6_COMMAND_SUBSTITUTION, R6_NOT_A_PLAIN_LAUNCH / same | zsh ✓ bash ✓ |
| sub-sh-dq-suffix | `${x:-s}"ub.sh" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| slot-py-dq-suffix | `${x:-sl}"ot.py" glm …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| empty-dq-between | `${x:-p}""ool …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ bash ✓ |
| locale-empty-between | `${x:-p}$""ool …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | bash ✓ (zsh: `$""` is not locale quoting — it yields `p$ool`, no wrapper; row is bash-only) |
| dq-cmdsub-dq | `"p"$(true)"ool" …` | **ALLOW / ALLOW** | deny R6_COMMAND_SUBSTITUTION, … / same | zsh ✓ bash ✓ |
| nested-in-echo-cmdsub | `echo $(${x:-p}"ool" …)` | **ALLOW / ALLOW** | deny R6_COMMAND_SUBSTITUTION / same | zsh ✓ bash ✓ |
| nested-in-bash-c | `bash -c '${x:-p}"ool" …'` | **ALLOW / ALLOW** | deny R6_DEFERRED_EXPANSION, R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH / same | zsh ✓ bash ✓ |
| zsh-arith-base-bracket-dq | `$[[##36]25]"OOL" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ (case-insensitive APFS: `POOL`) |
| zsh-arith-base-paren-dq | `$(([##36]25))"ool" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ (case-insensitive APFS: `Pool`) |
| zsh-anchored-replace-dq | `${x/#/p}"ool" …` | **ALLOW / ALLOW** | deny R6_EXPANSION, … / same | zsh ✓ |
| control | `pool run grok a /tmp grok-4` | deny missing binding | deny missing binding | — |

All 16 reviewer shapes were ALLOWED by r8 in both sessions; r9 denies all 16 in both.

## F4 — choice and behaviour

**Choice (a)**, the watchdog in all sessions with NO DECISION when unarmed. Reasons: it
bounds EVERY unarmed scan (stripper, `do … done`, `--watch` tails, `CI_READ_RE` /
`API_RUN_READ_RE` `then|do gh api` runs — all five found super-linear here) with one
mechanism, and the r8 test that pins "unarmed slow step → empty output" already states this
contract. (b) would need exact linear rewrites of five regex scans; I designed an exact
linear heredoc stripper (closing-line index per name + a single "absorb to the last
`H…HEREDOC` closing" step proves equal to the regex fixpoint) but did NOT implement it: the
brief asks for ONE choice, and (a) already bounds it.

| Session | Watchdog fires (default 7 s; `MASTERMIND_GUARD_BUDGET_S` only lowers, floor 1 s) |
|---|---|
| armed | DENY "guard budget exceeded — fail closed" (r8, unchanged; `test_r9_armed_adversarial_ci_text_still_denies_on_budget`, all r8 watchdog tests) |
| unarmed | exit 0, NO output, `main()` returns normally; timer disarmed, previous SIGALRM handler restored |

Measured through the real hook command line (`/bin/sh -c 'python3 "<guard>"'`, Homebrew
python3 3.14.7, M2, one run each), unarmed:

| Input | r8 | r9 |
|---|---|---|
| REVIEW4 text `touch …; : gh run view 123` + `⏎`×60 000 + `: end`, default budget | stalls (reviewer: 10.5 s → BLOCKED via `onFailure`) | **7.08 s, no output, exit 0** |
| same, budget 1.5 s | 13.74 s | **1.58 s**, no output |
| `gh run view 1;` + `do⏎`×40 000, budget 1.5 s | 26.99 s | **1.59 s** |
| `x` + ` then gh api x`×18 000, budget 1.5 s | 57.00 s | **1.62 s** |
| `gh run view 1⏎` + `<<A⏎`×40 000 (stripper), budget 1.5 s | 27.81 s | **1.59 s** |
| `gh run view 1 <<` + `A`×120 000 + `⏎B⏎` (stripper), budget 1.5 s | 38.61 s | **1.58 s** |
| ARMED, REVIEW4 text, budget 1.5 s | DENY budget, 1.61 s | DENY budget, 1.59 s (unchanged) |
| honest unarmed: `gh run view N`, `gh pr checks N` | no output | no output (identical, ≤ 0.08 s) |
| honest unarmed: fg `gh run watch N --interval 150` / `gh pr checks N --watch` / bg watch / `for …; do gh pr checks N; sleep 30; done` | deny fg / deny cadence / context ASYNC / deny poll loop | identical (≤ 0.08 s) |
| honest unarmed: `gh pr view N --jq '<192 000 a>'`; `cat <<EOF` + 180 KB of `gh run watch 1` lines + `EOF⏎gh pr view N` | no output | identical (0.12 s / 0.08 s) |

(The honest rows were run against both the r8 file and r9 via
`MASTERMIND_R6_GUARD_UNDER_TEST`: same outcomes.)

## Budgets — every row at exactly 262 144 chars, real hook command line, r8 → r9

Armed; bound rows through the owner-channel shim. Threshold in the tests: 4 s. One run each.

| Row | r8 s | r9 s | r8 verdict | r9 verdict |
|---|---|---|---|---|
| `rv-computed-glue-dash-path` | 0.13 | **0.12** | deny R6_EXPANSION | same |
| `rv-param-default-dash-path` | 0.12 | **0.12** | deny R6_EXPANSION | same |
| `rv-glob-head-dash-path` | 0.12 | **0.11** | deny R6_NOT_A_PLAIN_LAUNCH | same |
| `rv-computed-glue-double-dash` | 0.11 | **0.11** | deny R6_EXPANSION | same |
| `rv-arith-padding-quoted` | 0.15 | **0.15** | deny R6_EXPANSION | same |
| `rv-subscript-run` | 0.14 | **0.14** | deny R6_TOKENIZE_FAILED | same |
| `rv-bracket-run-no-wrapper` | 0.18 | **0.22** | allow | allow |
| `rv-subscript-run-no-wrapper` | 0.22 | **0.36** | allow | allow |
| `c5-option-path` | 0.09 | **0.09** | deny missing binding | same |
| `rv-bound-identity-run` | 0.12 | **0.12** | deny POOL_ORCHESTRATOR_ID | same |
| `bound-identity-run-parent` | 0.14 | **0.14** | deny POOL_PARENT_RUN_ID | same |
| `bound-identity-quoted` | 0.11 | **0.11** | deny POOL_ORCHESTRATOR_ID | same |
| `bound-env-u-quoted` | 0.64 | **0.63** | deny POOL_ORCHESTRATOR_ID | same |
| `bound-env-cluster-quoted` | 0.15 | **0.15** | allow | allow |
| `nested-shell-option-cluster` | 0.09 | **0.09** | deny R6_NESTED_SHELL | same |
| `newline-run-launch` | 0.72 | **0.71** | allow | allow |
| `leading-newline-run` | 0.72 | **0.71** | allow | allow |
| `literal-dollar-merge` | 0.29 | **0.30** | deny R6_EXPANSION | same |
| `ansi-octal-escapes` | 0.16 | **0.16** | deny R6_EXPANSION | same |
| `long-head-many-invocations` | 0.16 | **0.15** | deny R6_NOT_A_PLAIN_LAUNCH | same |
| `grouping-run` | 0.97 | **0.97** | deny R6_GROUPING | same |
| `nested-construct-glue` | 0.20 | **0.19** | deny R6_TOKENIZE_FAILED | same |
| `nested-construct-glue-closed` | 0.26 | **0.26** | deny R6_COMMAND_SUBSTITUTION | same |
| **new** `r9-dq-glue-dq-run` (`${x:-p}"ool" …` + `"a"`) | 0.26 | **0.30** | **allow** | deny R6_EXPANSION |
| **new** `r9-dq-glue-sq-run` (+ `'a'`) | 0.22 | **0.21** | **allow** | deny R6_EXPANSION |
| **new** `r9-dq-glue-backslash-run` (+ `\a`) | 0.26 | **0.24** | **allow** | deny R6_EXPANSION |
| **new** `r9-dq-glue-locale-run` (+ `$""`) | 0.29 | **0.35** | **allow** | deny R6_EXPANSION |
| **new** `r9-dq-glue-quote-only-run` (+ `"`) | 0.19 | **0.26** | **allow** | deny R6_EXPANSION |
| **new** `r9-dq-glue-dash-path-joined` (+ `-"a"/`) | 0.28 | **0.32** | **allow** | deny R6_EXPANSION |
| **new** `r9-joined-glue-one-word-no-wrapper` (`"${x}"a` run) | 0.33 | **0.41** | allow | allow |
| **new** `r9-joined-partial-one-word-no-wrapper` (`$(x)"a"` run) | 0.32 | **0.38** | allow | allow |
| **new** `r9-joined-construct-quote-run-no-wrapper` (`"${x}"` run) | 0.30 | **0.38** | allow | allow |
| **new** `r9-joined-default-glue-run` (`"${x:-p}"` run) | 0.52 | **0.73** | **allow** | deny R6_EXPANSION |
| **new** `r9-nested-quote-glue` (`echo ` + `$(${x:-p}"ool" ` run) | 0.40 | **0.21** | **allow** | deny R6_TOKENIZE_FAILED |
| **new** `r9-bash-c-quote-glue-body` | 0.18 | **0.26** | **allow** | deny R6_DEFERRED_EXPANSION, R6_EXPANSION |
| **new** `r9-bound-launch-quoted-args` (bound) | 0.23 | **0.22** | allow | allow |
| **new** `r9-escaped-cmdsub-run-no-wrapper` (`\$(` run) | 0.52 | **0.61** | allow | allow |
| **new** `r9-dq-glue-escaped-cmdsub-run` | 0.52 | **0.95** | **allow** | deny R6_GROUPING |
| probe `p${x}ool … )))` (r8 ledger worst) | 0.98 | **0.96** | deny R6_GROUPING | same |
| probe `p${x}ool … ((((` | 0.96 | **0.94** | deny | same |
| probe `${x:-p}"ool" … ")` | 0.43 | **0.80** | **allow** | deny R6_GROUPING |
| probe `echo    ` + `$(${x:-p}"ool" x) ` run (closed) | 0.43 | **0.49** | **allow** | deny R6_COMMAND_SUBSTITUTION |
| probe `${x:-p}"o"` run | 0.52 | **0.62** | allow | allow |

Worst r9 row: **0.97 s** (r8's own `grouping-run`, unchanged); worst new-reader row 0.95 s;
review #4 measured r8's worst at 1.39 s on its run — no regression. The joined reader at
most doubles the glue reader's share (it is a second linear pass). In-process linearity
sweep of `r6_names_wrapper` (5 prefixes × 27 quote-heavy units, 64 K → 256 K): **0 shapes
super-linear** (ratio > 6 and > 50 ms), worst 0.64 s (`\$(` run, now a budget row).
`/usr/bin/python3` 3.9.6 loads and runs the r9 file (F1 row True, honest `cd "${HOME:-…}"` False).

## Every armed-path scan and its bound (r9 delta to the C6 table)

| Scan | r9 bound |
|---|---|
| `_r9_joined` | linear: one `str.replace`, one single-class `re.sub` |
| joined partial reader | one linear split of the joined `marked` text; `_r6_partial_wrapper` per word as r8 (parts ≤ 14 steps, glob parse bounded) |
| `_r8_computed_glue` on the joined text | same bound as r8 (per level: one bracket pass, one item walk, ≤ 14-state DP; depth cap) — the two views recurse independently, total 2× |
| whole hook process | armed: watchdog 7 s → DENY (r8); unarmed: watchdog 7 s → no decision (r9) |

## Tests and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash\|provider_orchestrator_policy" tests/)
  → 1344 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed
    (C6: 1268 passed → +76 new, 0 changed)

tests/test_provider_orchestrator_policy.py → 838 passed (762 pre-existing, unchanged + 76 r9)
git diff tests/ → 418 insertions, 0 deletions (no existing assertion touched)
```

New tests (76 collected): F1 deny rows 16, reviewer-coverage 1, real-hook reviewer row 1,
sealed ground truth 1 (28 shell runs: 15 zsh, 13 bash), stay-out 19, armed honest verdicts 5,
quoting property 1 (6 000 words, > 1 000 in scope), depth boundary 1, budget rows 15,
F4: default-budget real hook 1, unarmed firing 5, armed budget 1, honest unarmed 8,
in-process handler 1. Fail-before: run against the r8 file
(`MASTERMIND_R6_GUARD_UNDER_TEST=<r8 copy>`) the reviewer row, 10 quote-glue budget rows
and the 5 unarmed firing rows FAIL (allow / 13.7–57 s); honest rows and the armed budget
row pass identically.

## Known limits (not claimed closed)

1. **F4 choice (a) trades one failure mode in UNARMED sessions.** Any unarmed judging step
   past the budget now yields no decision. That includes the pre-verdict heredoc stripper
   (unarmed `guard_fabric_launch` judges the heredoc-stripped text) and enormous unarmed
   commands (no size cap unarmed). So adversarial `<<` text can make the unarmed legacy
   identity check give no decision where r8 + `onFailure: "block"` (Claude Code ≥ 2.1.296,
   once the row is installed) would have blocked at 10 s; Codex and ≤ 2.1.287 already ran
   the command on a timeout. The ARMED gate (WO-11, the security boundary) is unchanged:
   fail-closed DENY. If the owner wants unarmed fail-closed on budget, the follow-up is the
   exact linear heredoc stripper sketched above (option (b) for that scan only).
2. An unarmed firing inside `repeat_poll_reason` may leave one `<digest>.<pid>.tmp` file in
   the poll-state directory (the record itself is replaced atomically).
3. Joined-reading over-reads (wider only): escaped backslash, a literal quote inside the
   other quote kind, escaped blanks; quoted twins of r8-in-scope unquoted forms
   (`bash "$name".sh`) are refused in armed sessions.
4. Depth: honest `$(…)` chains of ≥ 10 nested constructs are in scope (armed refusal, fail
   closed); > 32 substitution passes likewise (r7/r8, unchanged).
5. r8 limits stand: wholly computed words; a computed value producing `/`; `/pat/repl`
   runtime text; homoglyphs; staged files; provider-side environment; T3 worktree scope
   roots (REVIEW3 A1, Director C7); onFailure fleet versions UNKNOWN; watchdog absent
   without `setitimer`.
6. Ground truth is this M2 (APFS case-insensitive; macOS `/bin/bash` 3.2, `/bin/zsh`);
   the two arithmetic-base rows are skipped on a case-sensitive file system.

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL): the joined reading (scope
  width both ways), F4 choice (a) and limit 1, budgets.
- Owner decision on limit 1 (accept, or add the linear heredoc stripper).
- `REVIEW4_GUARD_R8_C7_PIN_OPUS_20261110.md` was not present in this checkout; this lane
  did not create it (out of its file scope).
