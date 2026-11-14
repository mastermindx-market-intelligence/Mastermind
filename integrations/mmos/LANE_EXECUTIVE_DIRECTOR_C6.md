# Lane: Director C6 — guard r8, every armed-path scan linear + fail-closed budget (2026-11-09)

Branch `t3/guard-r8-linear-budget`, created from `t3/t3-hermes-restart-recovery`
at `166923b1d` (r7 = `029298d6c`, merged as `251ddcd24`). Implementation by Claude
Opus 5.5 (native ORCHESTRATION route) answering distinct review #3 (REVIEW3: A3 S1
NEEDS_REWORK, A2 MINOR, A1 NOTE). No push, no PR; no other worktree, `~/Mastermind`,
`~/.hermes` or `~/.claude/settings.json` touched. Files: the guard module, the policy
module (hook row + validator only — support was proven, see the onFailure section), the
policy test module, this ledger. SELF_REVIEWED; the delta needs a fresh distinct
re-review (CRITICAL row: security/source authority, release automation of a guard).

## Commits

| Commit | Content |
|---|---|
| `1e895f290` | r8 guard + policy row/validator + 100 new tests (no existing test changed) |
| (this file) | Ledger |

## Finding → fix → test

| # | Sev | Finding | Fix (r8) | Tests |
|---|---|---|---|---|
| B1 | BLOCKER (REVIEW3 A3) | `_R7_GLUED_OPTION_RE` quadratic (a match could start at every `-X` of a `-a/-a/…` run and scan to its end); runs only for computed-glue launches → `p${x}ool run grok … -a/…` 60 KB 11.5 s → hook killed → launch unchecked | `_r8_glued_option`: the SAME language, decided in one pass per `[A-Za-z0-9_./-]+` run (option starts = `-`+letter at run start or after `/`/`-`; form (a) a name after a `/` ≥ 3 chars past the FIRST start; form (b) a name inside the letter run after an option letter) | `test_r8_glued_option_scan_accepts_exactly_the_r7_regex_language` (40 000 random strings vs the r7 regex, kept in the test module as reference: 0 differences); budget rows `rv-computed-glue-dash-path`, `rv-param-default-dash-path`, `rv-glob-head-dash-path`, `rv-computed-glue-double-dash`; cap rows |
| B2 | BLOCKER (A3) | `_R6_COMPUTED_RE` alternative `\$\[[^\]]*\]` rescans to the end from every `$[` when no `]` follows (140 KB in a single-quoted arg > 10 s) | `\$\[(?:[^\]$]\|\$(?!\[))*\]`: a `$[…]` match may not run across another `$[` (nested arithmetic unwraps innermost-first in the existing passes, like `${}`/`$()`) | budget row `rv-arith-padding-quoted`; scope fuzz (narrower than r7 only on unbalanced `$[ … $[` lines, which zsh and bash both refuse to parse — `-n` checked, listed below) |
| B3 | BLOCKER (A3) | `_effective_identity_values`: for every identity-name occurrence `_IDENTITY_VALUE_RE.match` re-read the rest of the value run (`a=NAME=NAME=…`, 250 KB 11.6–13.5 s) and the substitution check ran only after it → bound-glm session launches grok | a value is read ONCE: an assignment that starts inside the previous value's run records `''` (never the non-empty projection). Two assignments in one run can never both equal the projection (different lengths), so the verdict is unchanged; the message may name `''` instead of the suffix | `test_r8_identity_runs_are_read_once_with_an_unchanged_verdict`; budget rows `rv-bound-identity-run`, `bound-identity-run-parent`, `bound-identity-quoted` (owner channel: every binding check reached) |
| M1 | MAJOR (A3) | `_R7_PARAM_OPERATOR_RE` subscript `(?:\[[^\]]*\])?` super-linear (`${x[` runs: 8.1 s) | replaced by `_r8_dash_view`: after the first `${`, every `-` reads as a boundary for the name scan. r7 replaced each `${NAME…op` opening by a space; the only operator character that blocks the name regex's lookbehind is `-`, so every name r7 saw is still seen (proof sketch in the code comment; fuzzed). Wider on purpose: `${${x}:-pool}` and `${x[a[1]]:-pool}` (both r7 escapes, below) | `test_r8_scope_views_are_at_least_as_wide_as_r7` (60 000 random strings: every r7-view hit is an r8 hit); budget rows `rv-subscript-run`, `rv-subscript-run-no-wrapper` |
| M2 | MAJOR (A3) | `_r7_glob_match`: a `find("]")` per `[` (`[`-run 7.1 s) | `_r8_glob_atoms`: reading stops once fixed atoms exceed the name length (≤ 14 `]` searches per pattern), a set body is reduced ONCE to the wrapper alphabet, one parse per pattern for all four names (64-entry cache) | existing `test_r7_glob_and_parts_matchers_agree_with_the_regex_semantics` (8 000 cases vs fnmatch) unchanged and green; budget row `rv-bracket-run-no-wrapper` |
| m1 | MINOR (A3) | the budget test had no row without a literal wrapper name and no bound identity-run row | `test_r8_budget_rows_finish_through_the_real_hook_command_line` (23 rows at exactly 262 144 chars through `python3 "<guard>"`, bound rows through the owner-channel shim) + `test_r8_cap_boundary_through_the_real_hook_command_line` (262 143 / 262 144 / 262 145); each asserts verdict and wall < 4 s (measured ≤ 0.69 s) | as named |
| R-a | recommended (A3) | SIGALRM watchdog for armed sessions | `main()`: armed → `ITIMER_REAL` = `r8_watchdog_seconds()` (7 s default; `MASTERMIND_GUARD_BUDGET_S` honoured only downward; floor 1 s); the handler raises `_R8BudgetExceeded` (a `BaseException`), `main()` writes DENY "guard budget exceeded — fail closed" and exits 0; `_emit` disarms before printing; the previous handler is restored | `test_r8_watchdog_budget_is_overridable_only_downward` (12), `test_r8_watchdog_denies_fail_closed_when_a_step_is_slow[sleep, regex]` (in-process; a catastrophic `(a+)+$` is interrupted), `test_r8_watchdog_through_the_hook_process` (subprocess, injected slow step), `test_r8_watchdog_is_off_for_unarmed_sessions_and_after_a_verdict` |
| R-b | recommended (A3) | `onFailure: "block"` on the hook row + validator once host support is confirmed | support PROVEN (below): the Claude row now carries `"onFailure": "block"` (pin `CLAUDE_GUARD_HOOK_ON_FAILURE`; `None` renders the pre-r8 row); `_managed_hook_count` requires it on the Claude row and its absence on the Codex row | `test_r8_claude_hook_row_blocks_on_failure_and_codex_row_does_not` (rendered row, verify OK, key removed → DRIFT, `"continue"` → DRIFT) |
| A2 | MINOR (REVIEW3) | git optional-argument options read as consuming the NEXT word → `git log -U --output=<path> --grep=pool -1` admitted and git writes the file | `_r7_spec` gains optional-value sets (as `_R7Spec` attributes, so the 4-tuple still unpacks): `-U`, `--unified`, `--relative`, `--pretty`, `--format` (log/show/diff) and status `-u`, `--untracked-files` consume NOTHING; `--output*`, `--ext-diff*`, `--textconv*`, `-O*`, `--open-files-in-pager*` refused wherever they appear (option, value, after `--`) | 17 refused rows (the reviewer's exact shapes + value/`--` positions), 12 admitted honest forms, spec invariant test |
| A1 | NOTE (pre-existing, #1228) | `guard_bash` returns before any check when cwd is outside the scope roots; `~/.t3/worktrees/…` is not a root | NOT changed (Director C7 owns the t3 child-session env). Pinned honestly | `test_r8_t3_worktree_cwd_is_outside_the_scope_roots_pinned_limit` (no check under `~/.t3/worktrees` without `MASTERMIND_SCOPE_ROOTS`; refused when the root is projected) |
| P1 | found by the r8 probe | nested-shell `-c` detection `re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*")` backtracks quadratically: `bash pool -ccc…c!` 4.7 s at **32 KB** | `_r8_option_cluster` (letters-only check + membership) | `test_r8_option_cluster_equals_the_r7_fullmatch` (20 000 random); budget row `nested-shell-option-cluster` |
| P2 | probe | same fullmatch in `_env_clear_offsets` (`-[A-Za-z]*[iS][A-Za-z]*`, quoted `'env -iii…'` text reaches it on the bound path) | `_r8_option_cluster(word, "iS")` | same test; budget row `bound-env-cluster-quoted` |
| P3 | probe | `_R6Word.add` re-concatenated the growing literal segment per piece (`a$.a$.…`) | literal pieces collected and joined once on read (merging after a read preserved) | `test_r8_word_literal_pieces_join_like_r7`; budget row `literal-dollar-merge` |
| P4 | probe | `_r6_decode_ansi_c` sliced the rest of the body per octal/hex escape | precompiled patterns matched at a position | budget row `ansi-octal-escapes` |
| P5 | probe | `_r7_parse` dropped leading newlines with `pop(0)` per newline | one slice | budget row `leading-newline-run` |
| P6 | probe | `_UNOBSERVABLE_ENV_RE` and `CMD_POS` used `\s*` after a separator class containing `\n`: every newline of a run rescanned the run | `[^\S\n]*` (a newline is itself a separator, so a gap spanning newlines also matches from the last one) | `test_r8_newline_gap_regexes_find_what_r7_found` (30 000 random: same `search` results); budget row `newline-run-launch` |
| P7 | probe | `_wrapper_invocations.head_at` re-sliced a long first word for every invocation in its unit | the unit's head basename is computed once | budget row `long-head-many-invocations` |
| E1–E8 | **found in this lane (r7 scope escapes, zero binding check)** | see "Scope escapes" — zsh RUNS each shape, r7 judged it out of scope | `_r8_computed_glue`: one bracket-stack pass finds maximal `$(…)`/`$((…))`/`$[…]`/`${…}`/backtick constructs; a rough word gluing literal text to constructs names a wrapper when some construct value completes it (≥ 1 fixed literal character: a wholly computed word still names nothing); `${x[:]-\|=\|? WORD}` = value OR WORD, `${x[:]+WORD}` = WORD or nothing (an `alt` item); construct BODIES are read too (depth ≤ 8, deeper → in scope) | `test_r8_zsh_runs_each_closed_scope_escape` (sealed `env -i … zsh -f`, fake wrappers only), `test_r8_scope_escapes_are_judged_and_refused[8]` (bound and unbound deny), `test_r8_scope_stays_out_for_wholly_computed_and_unrelated_words[11]`; budget row `nested-construct-glue(-closed)` |

## Every armed-path scan and its bound (r8)

Armed path = `guard_bash` (armed) → cap → `_guard_armed_launch` → `r7_parse` → `validate_execution_binding` → root/identity checks → (only if `"gh "` is in the command) CI-wait checks. `n` = command length ≤ 262 144.

| Scan | r8 bound |
|---|---|
| length cap | O(1); above the cap refused before anything else (0.05–0.08 s through the hook CLI) |
| `FABRIC_LAUNCH_RE.search`, `_WRAPPER_RE`, `_WRAPPER_NAME_RE`, `_BATCH_EXECUTOR_RE`, `_LOOP_KEYWORD_RE` | linear (r7, unchanged: no path group, single quantifiers) |
| `_wrapper_invocations` | linear: separators once, each unit's first word and its basename once (P7), ≤ 3 args read per wrapper match |
| `r6_names_wrapper`: ANSI-C decode | linear (P4) |
| quote-free view + `_r8_dash_view` + `_WRAPPER_NAME_RE` | linear (M1) |
| `_r8_glued_option` | linear: one pass per run, bisect per option start (B1) |
| `_r7_glob_head_names_wrapper` | one lex (linear) + per-unit head; glob parse ≤ 14 fixed atoms (M2) |
| `_R6_COMPUTED_RE` passes | ≤ 32 passes × linear (B2); measured ≤ 0.37 s at 256 KB in-process worst case (depth-31 nest + padding) |
| `_r6_partial_wrapper` | parts match ≤ 14 steps; glob parse bounded (M2); stem regex runs only after a glob match (≤ 13 literal `[` × n) |
| `_r8_computed_glue` | per depth level: one bracket-token pass, one item walk, ≤ 14-state DP per word; levels are disjoint substrings; depth ≤ 8 (deeper → in scope) |
| `_r6_lex` | linear: literal runs, `_R6Word` literal builder (P3), each `$(`/`${`/quote span consumed once |
| `_r7_parse` | linear (P5); nested `-c` detection linear (P1); body parsed once at depth 1 only |
| `_UNOBSERVABLE_ENV_RE` | linear (P6) |
| `_runtime_multiplexed` | O(spans × offsets) with offsets = text-view invocations, which must equal the parse census (≤ 1 launch) before it runs |
| `_effective_identity_values` | linear (B3); `_command_assignments` (quoted spans pair up) linear; `_env_clear_offsets` ≤ 32 words per `env`, option clusters linear (P2) |
| CI-wait checks (`strip_heredocs`, `CI_WATCH_RE`, `CI_READ_RE`, `DO_DONE_RE`, poll keys) | run only when the launch gate has already ALLOWED and `"gh "` is in the command (r8 skips the heredoc stripper otherwise — stripping never creates `"gh "`). `CMD_POS` made newline-linear (P6). The heredoc fixpoint, `do … done` lazy scans and `[^;&\|\n]*--watch` tails remain super-linear on adversarial `gh` text: **hard-bounded by the watchdog** (7 s → DENY, fail closed); they can only ever add a refusal |
| whole hook process (armed) | watchdog 7 s → DENY; plus `onFailure: "block"` (timeout/crash → blocked) on Claude Code ≥ 2.1.296 |

## Benchmarks — real hook command line, before (r7) → after (r8)

`/bin/sh -c 'python3 "<guard>"'` with the PreToolUse JSON on stdin, armed, Homebrew
`python3` 3.14.7, this M2 host, one run each, sequential. "killed>30" = the harness
killed it at 30 s (the provider kills at 10 s and does not block); "—" = not run because a
smaller size was already killed. Nobind rows through the real command; BOUND rows through
the owner-channel shim (`python3 -c <shim> "<guard>"`: loads the same file, reports a
principal uid that does not own the receipt — on a single-uid host a bound command is
otherwise refused at the receipt channel before the identity scans, so the shim is the
only way to time them). Sizes are the TOTAL command length.

| input (real hook CLI) | 20,000 | 40,000 | 60,000 | 80,000 | 120,000 | 200,000 | 250,000 | 262,143 | 262,144 | 262,145 |
|---|---|---|---|---|---|---|---|---|---|---|
| `G1 p${x}ool run grok … + -a/` | 1.33 → **0.07** | 5.18 → **0.08** | 11.51 → **0.08** | 21.28 → **0.08** | killed>30 → **0.09** | — → **0.11** | — → **0.12** | — → **0.12** | — → **0.12** | — → **0.08** |
| `G2 ${x:-p}ool run grok … + -a/` | 1.34 → **0.07** | 5.11 → **0.08** | 11.80 → **0.08** | 20.37 → **0.09** | killed>30 → **0.09** | — → **0.11** | — → **0.12** | — → **0.12** | — → **0.12** | — → **0.07** |
| `G3 p* run grok … + -a/` | 1.32 → **0.07** | 5.14 → **0.08** | 11.42 → **0.08** | 20.46 → **0.08** | killed>30 → **0.09** | — → **0.10** | — → **0.11** | — → **0.11** | — → **0.12** | — → **0.07** |
| `G4 p${x}ool run grok … + --a` | 0.55 → **0.07** | 2.01 → **0.08** | 4.42 → **0.08** | 7.78 → **0.08** | 17.53 → **0.09** | killed>30 → **0.10** | — → **0.11** | — → **0.11** | — → **0.11** | — → **0.07** |
| `G5 p${x}ool run grok … '$[…'` | 0.23 → **0.08** | 0.69 → **0.08** | 1.47 → **0.09** | 2.56 → **0.10** | 5.62 → **0.11** | 15.48 → **0.13** | 24.20 → **0.14** | 26.82 → **0.15** | 27.46 → **0.14** | 0.07 → **0.07** |
| `G6 BOUND glm: pool run grok … a=POOL_ORCHESTRATOR_ID=…` | 0.14 → **0.08** | 0.39 → **0.06** | 0.74 → **0.07** | 1.23 → **0.07** | 2.75 → **0.08** | 7.58 → **0.11** | 11.93 → **0.12** | 12.83 → **0.12** | 12.84 → **0.11** | 0.06 → **0.05** |
| `G7 pool </dev/null run grok … + ${x[` | 0.12 → **0.07** | 0.26 → **0.08** | 0.46 → **0.09** | 0.72 → **0.09** | 1.52 → **0.10** | 4.07 → **0.12** | 6.25 → **0.13** | 6.80 → **0.14** | 6.80 → **0.13** | 0.07 → **0.08** |
| `G8 [-run (no wrapper)` | 0.14 → **0.08** | 0.29 → **0.08** | 0.55 → **0.09** | 0.80 → **0.10** | 1.62 → **0.11** | 4.14 → **0.14** | 6.28 → **0.16** | 6.88 → **0.17** | 6.85 → **0.17** | 0.07 → **0.07** |
| `G9 ${x[-run (no wrapper)` | 0.13 → **0.09** | 0.28 → **0.09** | 0.51 → **0.11** | 0.83 → **0.11** | 1.73 → **0.14** | 4.56 → **0.18** | 7.03 → **0.20** | 7.71 → **0.21** | 7.75 → **0.21** | 0.07 → **0.07** |
| `G10 C5 pool run grok … -O/a/a…` | 0.07 → **0.07** | 0.07 → **0.07** | 0.07 → **0.07** | 0.07 → **0.08** | 0.07 → **0.08** | 0.07 → **0.08** | 0.07 → **0.08** | 0.07 → **0.08** | 0.07 → **0.08** | 0.07 → **0.07** |
| `N1 bash pool -ccc…c!` | 1.75 → **0.08** | 6.88 → **0.07** | 16.21 → **0.07** | 28.14 → **0.07** | killed>30 → **0.08** | — → **0.08** | — → **0.09** | — → **0.09** | — → **0.09** | — → **0.07** |
| `N2 BOUND launch + newline run` | 1.82 → **0.10** | 7.05 → **0.15** | 15.70 → **0.19** | 27.91 → **0.25** | killed>30 → **0.34** | — → **0.55** | — → **0.66** | — → **0.69** | — → **0.69** | — → **0.06** |
| `N3 p${x}ool run glm … + a$.` | 0.09 → **0.09** | 0.12 → **0.10** | 0.19 → **0.12** | 0.38 → **0.14** | 0.89 → **0.17** | 1.39 → **0.24** | 2.44 → **0.28** | 2.01 → **0.29** | 1.77 → **0.28** | 0.07 → **0.07** |
| `N4 p${x}ool $'\1\1…'` | 0.08 → **0.08** | 0.10 → **0.09** | 0.10 → **0.09** | 0.13 → **0.10** | 0.18 → **0.11** | 0.32 → **0.14** | 0.44 → **0.15** | 0.12 → **0.13** | 0.46 → **0.15** | 0.07 → **0.07** |
| `N5 BOUND quoted 'env -u …'` | 0.10 → **0.10** | 0.14 → **0.15** | 0.20 → **0.19** | 0.21 → **0.23** | 0.30 → **0.32** | 0.45 → **0.50** | 0.55 → **0.61** | 0.57 → **0.64** | 0.57 → **0.62** | 0.06 → **0.06** |

r8 verdicts at 262 144 (r7 verdicts identical where r7 finished): G1–G5, N3, N4 deny
`R6_EXPANSION/R6_NOT_A_PLAIN_LAUNCH` (G3 `R6_NOT_A_PLAIN_LAUNCH`); G6, N5 deny the
`POOL_ORCHESTRATOR_ID` projection (every binding check reached); G7 deny
`R6_TOKENIZE_FAILED`; G8, G9 ALLOW (no wrapper named: out of scope); G10 deny missing
binding; N1 deny `R6_NESTED_SHELL`; N2 ALLOW (a faithful bound launch followed by
newlines). 262 145 → every row refused by the size cap ("above the 262144-character
limit … refused fail-closed") in 0.05–0.08 s. N4 at 262 143 is `R6_TOKENIZE_FAILED` (the
fill cuts an escape). r7 rows G4 onward were measured while a 5-process probe ran on this
24-core host (r8 rows: alone).

Heaviest launch-path shapes found by the probe, r8 final code, single run, 262 144 chars:
`p${x}ool run glm … )))…` **0.99 s** (worst found; linear parse-object cost of 262 K
grouping tokens), `((((` 0.93 s, `))` 0.96 s, newline run 0.87 s, `-O` + `do⏎` 0.92 s,
bound `bash -c '<launch>⏎⏎…'` 0.77 s, bound trailing/leading newline runs 0.69–0.70 s,
backtick run 0.38 s, `echo $(p${x}ool x) …` 0.24 s. Target ≤ 1.5 s: met.

Same inputs on `/usr/bin/python3` 3.9.6 (r8, 262 144): computed-glue `-a/` 0.11 s,
bound identity run 0.13 s, `[`-run 0.17 s; the injected-slow-step watchdog fired at
1.07 s with `MASTERMIND_GUARD_BUDGET_S=1` (sleep and catastrophic regex alike).

In-process complexity probe (not committed; `/tmp` harness; armed, bound, owner channel
emulated, real `guard_bash`): prefixes (literal launch, computed glue, quoted,
double-quoted, nested shell, `bash -c`, read forms, ANSI-C, `env`, leading text, glued
option, `gh` CI text) × units (every operator, quote, expansion opener, wrapper fragment,
identity name, keyword…). r7, 16 × 115 = 1 840 shapes at 8 K → 32 K: 48 flagged
super-linear (ratios 9–23 for 4× size; e.g. `bash pool -ccc…!` 4.7 s at 32 K). r8 final,
21 × 127 = 2 667 shapes at 64 K → 256 K: no super-linear shape on the launch path (max
ratio 6.4 on a 0.10 s case — noise; linear ≈ 4); the 14 remaining flags are all
post-gate CI-wait shapes (`gh ` text with heredoc markers, `do⏎` or newline runs) that
exceed the probe's 6 s limit at 256 K — in the hook they hit the watchdog (DENY).

## Watchdog semantics

* Armed sessions only (`MASTERMIND_SHARED_PLACEMENT` or a projected binding), armed at
  the start of `main()` — before stdin is read — with `setitimer(ITIMER_REAL)`.
* Budget `r8_watchdog_seconds()`: 7.0 by default; `MASTERMIND_GUARD_BUDGET_S` may only
  LOWER it (a larger, NaN or malformed value reads as 7.0); hard floor 1.0 s.
* Firing: the SIGALRM handler raises `_R8BudgetExceeded` (a `BaseException`, so no
  `except Exception` on the judging path swallows it); `main()` writes
  `permissionDecision: deny` with "guard budget exceeded — fail closed" and exits 0.
  Python code and long `re` searches are interrupted (the regex engine polls signals):
  verified on 3.12 (tests), 3.14.7 and 3.9.6 (hook process).
* Output integrity: `_emit` disarms the timer BEFORE printing, so a late alarm cannot
  interleave a second decision; an alarm between a verdict and the final disarm is a
  budget denial, never a traceback. The previous SIGALRM handler is restored.
* Unarmed sessions: unchanged — no watchdog (a crash or timeout there is governed by the
  hook row, below).
* Platforms without `setitimer` (Windows) run without a watchdog.

## onFailure determination (Claude Code hook row)

**Static (installed binary).** `~/.local/share/claude/versions/2.1.319` embeds the
settings schema for command hooks: `onFailure` — "What a failure of this hook does: it
could not start …, timed out, exited with a code other than 0 or 2, or printed JSON that
is invalid … 'continue' (default) … 'block': the failure counts as exit code 2, so the
action the event guards (a tool call, …) is blocked. Ignored for async hooks and on
Stop, SubagentStop, TaskCompleted and TeammateIdle." The implementation (`lee()` →
`HVt()`) turns a timed-out or failed non-async command hook with `onFailure === "block"`
into `outcome: "blocking"`.

**Observed (native behaviour, zero spend).** A first attempt with `claude -p` on the
default config dir failed at authentication before any model call (OAuth expired; cost
0); this session's own router credential was NOT reused for a second process. Instead: a
local fake Anthropic Messages endpoint on 127.0.0.1 (returns one `tool_use` Bash call,
`touch MARKER`, then `DONE`), each CLI binary run headless with a scratch
`CLAUDE_CONFIG_DIR`, a dummy API key, `--setting-sources local` from an empty scratch dir,
`--settings <scratch hook file>`, `--strict-mcp-config`, `--tools Bash`. No real model, no
credential, no user settings touched. Hook = `sleep 20` with `timeout: 2` (or a crash):

| CLI | hook | `onFailure` | Bash tool call | CLI log / tool result |
|---|---|---|---|---|
| 2.1.319 | `sleep 20`, timeout 2 s | absent | **RAN** (S1 fail-open confirmed live) | `timed out after 2000ms`; `(Bash completed …)` |
| 2.1.319 | `sleep 20`, timeout 2 s | `"block"` | **BLOCKED** | `PreToolUse command hook timed out; blocking (onFailure: "block")` |
| 2.1.319 | `python3 -c "raise SystemExit(1)"` | absent | RAN | `finished with status 1` |
| 2.1.319 | same | `"block"` | **BLOCKED** | `failed; blocking because onFailure is "block"` |
| 2.1.319 | `python3 "<missing file>"` (exit 2) | absent | **BLOCKED** | `finished with status 2` — exit 2 always blocks |
| 2.1.319 | same | `"block"` | BLOCKED | same |
| 2.1.296 | `sleep 20`, timeout 2 s | `"block"` | **BLOCKED** | `timed out; blocking (onFailure: "block")` |
| 2.1.287 | `sleep 20`, timeout 2 s | absent | RAN | — |
| 2.1.287 | `sleep 20`, timeout 2 s | `"block"` | RAN — key accepted and **ignored** | — |
| 2.1.287 | deny-JSON hook | `"block"` | BLOCKED by the deny | the hook still registers and its deny applies |

(2.1.287 needed `--permission-mode default`: its auto-mode classifier otherwise blocked
both arms for lack of a real model.)

**Determination.** Claude Code 2.1.319 (installed here) and 2.1.296 honour
`onFailure: "block"` on PreToolUse command hooks; 2.1.287 ignores it without dropping the
hook (degrades to today's behaviour). REVIEW3's side claim "missing guard file → python
exit 2 → treated as allow" is **refuted** on 2.1.319: exit 2 blocks with or without the
key. → The registered Claude row now sets `"onFailure": "block"` (pin
`CLAUDE_GUARD_HOOK_ON_FAILURE` in `provider_orchestrator_policy.py`; `None` restores the
pre-r8 row) and `verify_policy` reports `claude_settings.pretool` DRIFT for a Claude row
without it. The Codex row is unchanged (a Claude Code key).

**Consequences to accept or revert at review.** On a supporting CLI, ANY guard failure
now blocks Bash/Agent/Task in EVERY session (armed or not): a guard timeout (unarmed
sessions keep the r7-era CI-wait scans), an uncaught crash (exit 1) and a missing
`python3` (exit 127). This is the fail-closed direction S1 asked for; it is also an
availability dependency on `python3` and on the guard finishing. Installed homes keep the
old row until the policy is re-applied (an owner-run step; `verify_policy` shows DRIFT
until then). Fleet CLI versions are UNKNOWN here; a host on ≤ 2.1.287 still fails open on
a timeout (armed sessions are still covered by the watchdog).

## Git carve-out (A2) — fail-before through the real hook command line, no binding

| Command | r7 | r8 |
|---|---|---|
| `git log -U --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny R6_NOT_A_PLAIN_LAUNCH |
| `git log -pU --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny |
| `git log --unified --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny |
| `git log --relative --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny |
| `git log --pretty --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny |
| `git log --format --output=/tmp/r8.out --grep=pool -1` | **ALLOW** | deny |
| `git diff -U --output=/tmp/r8.out -- pool` | **ALLOW** | deny |
| `git show -U --output=/tmp/r8.out -- pool` | **ALLOW** | deny |
| `git log -U --ext-diff --grep=pool -1` | **ALLOW** | deny |
| `git log -U --textconv --grep=pool -1` | **ALLOW** | deny |
| `git status -u --output=/tmp/r8.out -- pool` | **ALLOW** | deny |
| `git status --untracked-files --output=/tmp/r8.out -- pool` | **ALLOW** | deny |
| `git log --grep=pool -- --output=/tmp/r8.out` | **ALLOW** | deny |
| `git log --author --output=/tmp/r8.out --grep=pool` | **ALLOW** | deny |
| `git commit -m --output=/tmp/r8.out -- pool` | **ALLOW** | deny |
| `git grep -O pool` | deny | deny |
| `git log --grep=pool -O/tmp/order` | deny | deny |
| controls: `git log -U --grep=pool -1`, `-U3`, `-pU5`, `--unified=5`, `--pretty=oneline`, `--format=%H`, `--relative=src`, `git diff -U5 -- pool`, `git show --stat -U1 -- pool`, `git status -uno -- pool`, `--untracked-files=no`, `git commit -m "fix pool"` | allow | allow (bound and unbound, gate never reached) |

15/17 refused rows were admitted by r7. (The guard was run, not git: nothing was written.)
Over-refusal accepted: a commit message or grep value that starts with `--output`,
`--ext-diff`, `--textconv`, `-O` or `--open-files-in-pager`.

## Scope escapes closed (E1–E8; found while linearising r7)

Ground truth in a sealed zsh: `env -i PATH=<fake wrapper dir>:/usr/bin:/bin HOME=<tmp> zsh -f -c …`
with FAKE `pool`/`sub.sh`/`slot.py` that only touch a marker. Every row ran a wrapper.
APFS here is case-insensitive, so zsh's uppercase base-36 digit `O` resolves `pOol` to `pool`.

| # | Shape (+ ` run grok a /tmp grok-4`) | zsh runs a wrapper | r7 scope | r8 scope / armed verdict |
|---|---|---|---|---|
| E1 | `p$[[##36]24]ol` (zsh arithmetic base output → `pOol`) | yes (case-insensitive FS) | **out** | in / deny R6_EXPANSION |
| E2 | `p$(([##36]24))ol` | yes (case-insensitive FS) | **out** | in / deny |
| E3 | `${x:-p}${y:-ool}` (split operator words) | yes | **out** | in / deny |
| E4 | `${${x}:-pool}` (zsh nested) | yes | **out** | in / deny |
| E5 | `${x[a[1]]:-pool}` (nested subscript) | yes | **out** | in / deny |
| E6 | `echo $(p${x}ool …)` (glue inside a command substitution) | yes | **out** | in / deny R6_COMMAND_SUBSTITUTION |
| E7 | ``echo `p${x}ool …` `` | yes | **out** | in / deny |
| E8 | `zsh -f -c 'p$[[##36]24]ol …'` (quoted body) | yes (case-insensitive FS) | **out** | in / deny |
| ctl | `${x:-s}${y:-ub}.sh`, `${x:+zz}${x:-slot}.py` | yes | in | in |

Kept out of scope (arbitrary-process limit, unchanged): `$W run grok`,
`$(printf p)$(printf ool) run`, `python3 *.py`, `bash ${dir}/run${n}.sh`,
`git log $(git merge-base a b)..HEAD`, `echo $($(echo hi))`; and not newly in scope:
`cd ${HOME:-/Users/me}`, `echo ${X:-o}`, `echo ${X:-s}`, `echo "${PORT:-8080}"`,
`echo ${name//-/_}` (a `/pat/repl` replacement is runtime-dependent — r7 parity).

**Incident (reported, no effect found).** While first reproducing E1–E4 I ran
`zsh -c '<shape> run grok a'` with my fake `pool` only PREPENDED to PATH, without `-f`:
zsh sourced `~/.zshenv`, which put the REAL `~/.local/bin/pool` first, so the real wrapper
was invoked four times. Each invocation was refused by the wrapper's own economic policy
before any launch (`ECONOMIC_POLICY_REFUSED {"allowed":false,"reason":"unknown_task_class",…}`,
exit 78). No file under the wrapper's release store, the Macro-Dashboard project dir or
`~/.local/state` was written afterwards (checked with `find -newer`; only an unrelated
storage-cleanup job's files). Every later shell experiment ran under `env -i … zsh -f`
with fake wrappers. This also proved the escapes live: the real wrapper was reached by
computed-glue words r7 judged out of scope.

## Scope-roots note (REVIEW3 A1; pre-existing, #1228)

`guard_bash` returns before ANY check when the payload cwd is outside the scope roots
(`_scope_roots`: `~/.mastermind/worktrees`, `~/lanes`, `~/terminals`,
`~/Documents/Cluade`, `~/Documents/GitHub`, `~/Projects/MastermindX/repos`,
`/Volumes/Mastermind/agent-workspaces`, plus `MASTERMIND_SCOPE_ROOTS`). `~/.t3/worktrees/…`
is not among them and `MASTERMIND_SCOPE_ROOTS` is unset in T3 sessions here, so an ARMED
session whose cwd is a T3 worktree gets no launch checks at all (and no watchdog
decision either: `guard_bash` returns before judging). Not changed in this lane (scope
semantics; Director C7 owns the t3 child-session environment). Pinned by
`test_r8_t3_worktree_cwd_is_outside_the_scope_roots_pinned_limit`, which fails — on
purpose — once T3 worktrees become a scope root.

## Behaviour changes vs r7 (intentional)

- Refused now: the 15 git shapes above; E1–E8; words gluing literal text to
  `${x:-WORD}`/`$((…))`/`$[…]`/construct bodies that can spell a wrapper; `-` after a
  `${` no longer hides a wrapper name.
- Armed sessions: any judging step past 7 s → DENY (watchdog); `"gh "`-free commands skip
  the heredoc stripper (same result).
- Hook row: Claude row `onFailure: "block"` (see consequences above); validator requires it.
- Unchanged: every r7 test (662) and table; the r7 admit grammar; unarmed CI-wait checks
  (only `CMD_POS`'s newline gap, same matches).

## Known limits (not claimed closed)

1. **Post-gate CI-wait scans** (`strip_heredocs` fixpoint, `DO_DONE_RE` lazy bodies, CI
   regex `--watch` tails) stay super-linear on adversarial text containing `gh `. They run
   only after the launch gate allowed; in armed sessions the watchdog turns them into a
   DENY at 7 s (availability cost on such text only). Unarmed sessions: a timeout there now
   blocks via `onFailure` on a supporting CLI.
2. **Scope model** (r7 limits stand): a computed value that produces a `/` (basename
   restart) is not modelled (`/Users/x/.local/b${x}ol` with x=`in/po`); `/pat/repl`
   replacements are runtime text; unbalanced `$[ … $[` lines (shell syntax errors) are
   read narrower than r7; homoglyphs; staged files; provider-side environment.
3. **Depth caps**: construct nesting > 8 (r8 reader) or > 32 substitution passes → in scope
   (fail closed: an honest command nested that deep is refused in an armed session).
4. **Watchdog**: absent on platforms without `setitimer`; it bounds the guard, not Python
   start-up or a provider that skips the hook; a host whose CPU is ~10× slower than this M2
   would see the 7 s watchdog DENY a few 256 KB adversarial inputs (fail closed).
5. **onFailure fleet**: CLI versions on other hosts are UNKNOWN; ≤ 2.1.287 ignores the key.
   Installed homes need a policy re-apply (owner-run) to get the new row.
6. **Scope roots** (A1 above): T3 worktrees are unguarded unless projected.
7. **Equivalence evidence** is randomized fuzzing (glued option exact; name/glued views
   ⊇ r7; option clusters exact; newline-gap regexes same), not a proof assistant.

## Commands and counts (lane head)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash\|provider_orchestrator_policy" tests/)
  → 1268 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed

tests/test_provider_orchestrator_policy.py → 762 passed (662 pre-existing, unchanged + 100 r8)
tests/test_ceo_submit_armed_composition.py (d8 identity scans) → 321 passed (after the commit)
```

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL): B1–B3/M1/M2 linearity,
  E1–E8 scope reader (over/under-refusal), the watchdog, the `onFailure` row decision and
  its fleet consequences, A2 grammars.
- Integrator/owner: decide the `onFailure` rollout (keep the pin or set it to `None`
  before release); re-apply the policy on each host to install the row (owner-run);
  check fleet Claude Code versions (≥ 2.1.296 honours the key).
- Director C7: T3 worktree scope roots (A1).
