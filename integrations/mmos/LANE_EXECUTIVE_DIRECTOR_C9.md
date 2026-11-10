# Lane: Director C9 — guard r10, lexer scope reading + unarmed watchdog decision (2026-11-09)

Branch `t3/guard-r10-lexer-scope`, created from `t3/t3-hermes-restart-recovery` at `bfa233e9f` (r9 merged).
Implementation by Claude Opus 5.5 (native ORCHESTRATION route) answering distinct re-check #5
(`REVIEW5_GUARD_R9_OPUS_20261110.md`: N1 MAJOR, N2 MODERATE, N3 MINOR doc, N4 NIT; overall NEEDS_REWORK).
No push, no PR; no other worktree, `~/Mastermind`, `~/.hermes` or `~/.claude/settings.json` touched. Files: the guard
module, the policy test module (append-only), this ledger, and the REVIEW5 record (transcribed from the brief, as the
brief directs). `provider_orchestrator_policy.py` is untouched. SELF_REVIEWED; CRITICAL row — the delta needs a fresh
distinct re-review.

No real wrapper was invoked. Every shell ground-truth run is sealed:
`/usr/bin/env -i PATH=<fake-wrapper dir>:/usr/bin:/bin HOME=<tmp> /bin/zsh -f -c …` and
`… /bin/bash --norc --noprofile -c …` (macOS `/bin/bash` 3.2); the fakes only `touch <tmp>/ran/<name>-$1`.

## Finding → fix → test

| # | Sev | Finding | Fix (r10) | Tests |
|---|---|---|---|---|
| N1 | MAJOR | Construct extents are found by quote-unaware matchers (`_r8_construct_spans`, `_R6_COMPUTED_RE`); a quoted/escaped/commented bracket inside a construct hides the glued word in the raw AND the joined view: `$(: "("; printf p)ool run grok …` ALLOWED armed, bound and unbound, no binding check (sealed zsh/bash run `pool`) | **A fourth scope reading, `_r10_lexed_reading(raw)`, OR-ed after the r8/r9 readings** in `r6_names_wrapper` (union — never narrower): a quote-aware scanner dedicated to scope (rule below) | `test_r10_bracket_matcher_escapes_are_judged_and_refused[15]`, `test_r10_sealed_shells_run_each_escape` (26 shell runs), `test_r10_reviewer_row_through_the_real_hook_command_line`, `test_r10_escape_table_covers_every_reviewer_shape`, honest-out rows [20], armed honest verdicts [3], pinned over-refusals [3], depth boundary, union property, 20 budget rows |
| N2 | MODERATE | Unarmed: the quadratic heredoc stripper runs before the legacy identity check; `pool run grok a /tmp grok-4⏎` + N×`<<A⏎`, no `POOL_*` env: r8 DENIED at 7–9.5 s, r9 NO DECISION at 7 s (fail open on every CLI) | **Choice (a) kept; before the stripper the unarmed path records whether the RAW text names a wrapper** (`_r10_note_unarmed_scope`: `FABRIC_LAUNCH_RE` / `_WRAPPER_NAME_RE` on the quote-stripped text first, then the full `r6_names_wrapper`, i.e. every reader incl. the N1 reading). Watchdog firing, unarmed: state `True` or `"pending"` → **DENY** (reason names the missing identity, like r8); `False` or `"unset"` (no unarmed Bash judgement started) → no decision (r9) | `test_r10_unarmed_heredoc_launch_denies_at_the_watchdog_default_budget` (exact shape, N = 24 000, default 7 s), `…_at_a_lowered_budget[21000/22500/24000]`, `test_r10_unarmed_watchdog_denies_every_wrapper_naming_text[3]` (incl. N1+N2 combined), `test_r10_unarmed_adversarial_ci_text_is_still_no_decision` (reviewer's `gh` text, default budget; `gh` + `<<A` run), `test_r10_unarmed_scope_state_drives_the_watchdog_decision` (pending → DENY, False → none, unset → none) |
| N3 | MINOR (doc) | quoted idiomatic operands (`"$f".sh`, …) in scope → armed refusal | **Documented, behaviour unchanged** (no carve-out proven safe) — class below | (none; r9 tests unchanged) |
| N4 | NIT | over-reads (scope widens only) | **Documented** — list below | — |

## The r10 reading, stated precisely

`_r10_lexed_reading(raw)` (in scope = True) scans the raw command text as shell script. Text holding neither `$` nor a
backtick returns False at once (no word can be computed without one; literal and glob words are read by the r6–r9
readers). Otherwise:

1. **Words.** Blanks, newlines and the operators `; & | < > ( )` (longest match from `_R6_OPERATORS`) separate words.
   A word becomes items for the existing r8 DP (`_r8_items_spell`): unquoted literal, `'…'`, `"…"` literal text,
   `\x`, decoded `$'…'` → `lit`; `$"…"` is read as `"…"` (bash locale; zsh's `$`+`"…"` reading cannot spell more);
   `${…}` → `_r8_construct_items` of the construct text; `$name`, `$1`/`$@`…, `$(…)`, `$((…))`, `$[…]`, backticks,
   `<(…)`/`>(…)` → `any`. A word with a computed item is in scope when the DP spells a wrapper basename using ≥ 1 fixed
   literal (wholly computed words name nothing — the documented arbitrary-process limit); a wholly literal word is in
   scope when its basename is a wrapper.
2. **Bodies.** `$(…)`/`$((…))`/`<(…)` bodies are read as script (a `)` at paren depth 0 closes; `(`/`)` inside nest);
   backtick bodies (unescaped as the shell does) and nested `${…}`/`$[…]` constructs are read recursively.
3. **Deferred text.** Every literal run of a word whose QUOTED or escaped part holds `$` or a backtick is re-read as a
   script (`bash -c '…'`, `eval "…"`, `\$(…)`, `$'\x24(…)'`).
4. **Comments.** `#` at a word start skips to the newline — at top level and inside `$(…)`.
5. **Here-documents** (`<<`/`<<-`, not `<<<`), at every level: the delimiter word (quoted if it holds `'`, `"` or `\`)
   is recorded; at the next unquoted newline the body runs to the first line equal to the delimiter (leading tabs
   stripped for `<<-`; found with one C-level regex), or to the end of the text (as bash/zsh do). Every body is read as
   script (a shell may read it); an unquoted-delimiter body is also read for the expansions the shell performs in it
   (quotes literal; `$`-constructs and backticks read).
6. **Fail closed (in scope):** an unterminated `$(`/`<(` (the reviewer's "lex failure → in scope" rule, kept for
   constructs); construct nesting > `_R10_MAX_DEPTH` = 9 (a `$(…)` chain of k constructs reaches depth k: k ≤ 9 out,
   k ≥ 10 in — r9's boundary); a `case` word in command position inside `$(…)`/`<(…)` (its pattern `)` would close the
   substitution; zsh runs `$(case x in x) printf p;; esac)ool`); bare braces in `${…}` whose bash end (first `}`, bash
   3.2) and zsh end (counted) differ by anything but `}` (`x=p; ${x:-{}ool` runs `pool` in bash); a `'` inside
   `"${…}"` (bash 3.2: a quote; zsh: literal); `'`/`"` inside `$[…]`; more than `_R10_MAX_RESYNCS` = 4 unterminated
   quotes in one text; any unexpected reader exception or `RecursionError`.
7. **Lenient:** an unterminated quote or backtick is a syntax error the shell refuses too (zsh refuses the whole `-c`
   text; bash has already run earlier lines, which were already read here); the reading resynchronises one character
   after the opening quote and reads the rest as script — never narrower than the shell. A `${`/`$[` with no `}`/`]`
   anywhere after it is literal text (both shells refuse it); a `${…}` with no closing `}` under either rule is
   lenient the same way.

**Why not `_r6_lex` (the reviewer's prototype).** Measured: (i) `_r6_lex` FAILS on the standard commit idiom
`git commit -m "$(cat <<'EOF' … doesn't … EOF)"` (it cannot read a here-document inside `$(…)`, so the apostrophe is an
unterminated quote) — "failure + `$` → in scope" would refuse every such armed commit
(`test_r10_r6_lex_fails_on_the_commit_idiom_the_r10_reader_does_not`); (ii) it misses four siblings that run in a
sealed shell (table below rows 12–15: `case` and a heredoc inside `$(…)` close early; lexing stops at a top-level `<<`;
the bash/zsh `${` extent split). `_r6_lex` and `_r7_parse` are unchanged, so every refusal code is unchanged.

## N1 rows — fail-before (r9) → after (r10)

Armed. BOUND = binding present (every binding check reachable), UNBOUND = no binding. Args `run grok a /tmp grok-4`
(slot.py row: `glm a /tmp glm-5.3`). r9 = bfa233e9f. Gate reached: **no** in every r10 row, both sessions (refused by
shape). Ground truth = a sealed shell ran a FAKE wrapper (marker file written).

| # | Row | Command | r9 bound / unbound | r10 bound / unbound (codes) | Ground truth |
|---|---|---|---|---|---|
| 1 | quote-glued | `$(: "("; printf p)"ool" …` | **ALLOW / ALLOW** | deny / deny (R6_COMMAND_SUBSTITUTION, R6_NOT_A_PLAIN_LAUNCH) | zsh ✓ bash ✓ |
| 2 | dq-paren | `$(: "("; printf p)ool …` | **ALLOW / ALLOW** | deny / deny (same) | zsh ✓ bash ✓ |
| 3 | sq-close-paren | `$(: ')'; printf p)ool …` | **ALLOW / ALLOW** | deny / deny (same) | zsh ✓ bash ✓ |
| 4 | escaped-paren | `$(: \(; printf p)ool …` | **ALLOW / ALLOW** | deny / deny (same) | zsh ✓ bash ✓ |
| 5 | brace-dq-close | `${x:-p${y#"}"}}ool …` | **ALLOW / ALLOW** | deny / deny (R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH) | zsh ✓ bash ✓ |
| 6 | comment-paren | `$(printf p # (⏎)ool …` | **ALLOW / ALLOW** | deny / deny (R6_TOKENIZE_FAILED) | zsh ✓ bash ✓ |
| 7 | nested-in-echo | `echo $($(: "("; printf p)ool …)` | **ALLOW / ALLOW** | deny / deny (R6_COMMAND_SUBSTITUTION) | zsh ✓ bash ✓ |
| 8 | nested-in-bash-c | `bash -c '$(: "("; printf p)ool …'` | **ALLOW / ALLOW** | deny / deny (R6_DEFERRED_EXPANSION, R6_COMMAND_SUBSTITUTION, R6_NOT_A_PLAIN_LAUNCH) | zsh ✓ bash ✓ |
| 9 | sub-sh | `$(: "("; printf s)ub.sh …` | **ALLOW / ALLOW** | deny / deny (R6_COMMAND_SUBSTITUTION …) | zsh ✓ bash ✓ |
| 10 | slot-py | `$(: "("; printf sl)ot.py glm …` | **ALLOW / ALLOW** | deny / deny (R6_COMMAND_SUBSTITUTION …) | zsh ✓ bash ✓ |
| 11 | sq-open-paren (C9: the 11th, sq twin of 3) | `$(: '('; printf p)ool …` | **ALLOW / ALLOW** | deny / deny (R6_COMMAND_SUBSTITUTION …) | zsh ✓ bash ✓ |
| 12 | case-in-cmdsub (C9 sibling) | `$(case x in x) printf p;; esac)ool …` | **ALLOW / ALLOW** | deny / deny (R6_GROUPING, R6_COMMAND_SUBSTITUTION …) | zsh ✓ (bash 3.2 ✗) |
| 13 | heredoc-in-cmdsub (C9 sibling) | `$(cat <<E >/dev/null⏎)⏎E⏎printf p)ool …` | **ALLOW / ALLOW** | deny / deny (R6_GROUPING …) | zsh ✓ (bash 3.2 ✗) |
| 14 | heredoc-then-line (C9 sibling) | `cat <<E >/dev/null⏎$(⏎E⏎$(: "("; printf p)ool …` | **ALLOW / ALLOW** | deny / deny (R6_HEREDOC) | bash ✓ (zsh ✗) |
| 15 | brace-first-close (C9 sibling) | `x=p; ${x:-{}ool …` | **ALLOW / ALLOW** | deny / deny (R6_TOKENIZE_FAILED) | bash ✓ (zsh ✗) |

The brief speaks of "all 11 N1 escapes"; the REVIEW5 text lists 10 strings — the 11th here is the single-quoted
open-paren twin. A further backtick shape (`` `: "("; printf p`ool …``) runs in both shells but was already in scope
in r9. Fail-before for all 15: `test_r10_reading_is_never_narrower_than_r9` asserts r6–r9 readings alone return False
on every row and r10 returns True.

### Honest forms (stay OUT of scope; `test_r10_honest_bracket_and_heredoc_forms_stay_out_of_scope`, 20 rows)

The reviewer's two named forms `x=$(grep "(" f)` and `echo "a (b" $(date)`; the reviewer's other honest rows were not
in this checkout, so C9 supplied the class: `git commit -m "$(cat <<'EOF' … doesn't … (r10) … EOF)"` (two variants,
with backticks), `gh pr create … --body "$(cat <<'EOF' … it's … EOF)"`, `cat > x.py <<'EOF'⏎print('hi $x (')⏎EOF`,
`echo "$(date +%s) (started)"`, `awk '{print $1 ")"}' f`, `sed -n "s/(\(.*\))/\1/p" f`,
`for f in $(ls *.py); do echo "$f (done)"; done`, `echo $(( (1 + 2) * 3 ))`, `echo "${HOME}" # (comment`,
`printf '%s (%s)\n' "$a" "$b"`, `result=$(python3 -c "print('(')")`, `` echo `date` "(x)" ``, `echo $(( 1 << 2 ))`,
`cat <<E⏎$HOME (home)⏎E⏎echo done`, `echo ${CONFIG:-{}}`, `grep -n '${{ matrix.index }}' …`,
`sed -i '' 's/${{ github.token }}/x/' ci.yml`. In scope but ADMITTED (armed allow bound and unbound, gate not reached):
`grep -n '$(' docs/runbook.md`, `rg -n "\$\(" src`, a commit message containing `$(x)`.

## Scope differential (r9 → r10)

132 287 commands (111 300 distinct string constants of every `tests/*.py` file + 25 000 random quote/bracket/construct
texts), pure functions of both files: **scope lost 0; refusal deny→allow 0**; allow→deny 307 (gained scope 308). The
59 gained real constants are: the escape rows/fragments themselves; truncated `X="$(` source fragments (an unterminated
`$(` → fail closed, by design); `` echo `p${x}ool `` (unterminated backtick: the resync reads `p${x}ool`); and the three
pinned over-refusals below. Review #4's 16 shapes: deny/deny unchanged (r9 tests green). Armed budget-DENY stdout:
**byte-identical** r8 = r9 = r10 (sha256 `9c651f8f3ce0b6ff…`, 437 bytes; REVIEW4 F4 text, budget 1.5 s).

## N2 — measured (real hook command line `/bin/sh -c 'python3 "<guard>"'`, python3 3.14.7, unarmed, no `POOL_*`)

| Input | r8 | r9 | r10 |
|---|---|---|---|
| `pool run grok a /tmp grok-4⏎` + 21 000 × `<<A⏎`, default budget | DENY "missing POOL_ORCHESTRATOR_ID, …" 7.35 s | no decision 7.08 s | **DENY 7.09 s** ("guard budget exceeded … names a Fabric launch wrapper — fail closed … missing POOL_ORCHESTRATOR_ID, POOL_PARENT_RUN_ID, POOL_TASK_CLASS") |
| same, 24 000 × | DENY 9.55 s | no decision 7.08 s | **DENY 7.08 s** |
| REVIEW4 F4 `gh` text (60 000 newlines), default budget | no decision 13.09 s (→ BLOCKED by `onFailure` at 10 s) | no decision 7.08 s | **no decision 7.09 s** (unchanged) |

The unarmed scope reading runs on the RAW text (heredoc bodies included — wider than the stripped text the legacy
check reads). Cost added to every unarmed Bash command: one `r6_names_wrapper` pass (≤ ~1.7 s in-process at 262 144
chars worst measured; µs–ms for ordinary commands). The optional linear heredoc stripper was NOT implemented (bounded
by choice (a) + the flag; C8's design note stands).

## Budgets — every row at exactly 262 144 chars, real hook command line, r9 → r10

Armed; bound rows through the owner-channel shim. Test threshold 4 s. One run each, M2, python3 3.14.7.

| Row | r9 s | r10 s | r9 verdict | r10 verdict |
|---|---|---|---|---|
| 23 r8 rows (C6) | 0.08–0.96 | **0.09–0.95** | — | identical (worst `grouping-run` 0.95) |
| 15 r9 rows (C8) | 0.20–1.49 | **0.21–0.96** | — | identical (`r9-escaped-cmdsub-run-no-wrapper` 0.62 → 0.93) |
| **new** `r10-dq-paren-glue-dash-path` | 0.13 | **0.13** | **allow** | deny R6_COMMAND_SUBSTITUTION |
| **new** `r10-sq-close-glue-dq-run` | 0.26 | **0.33** | **allow** | deny R6_COMMAND_SUBSTITUTION |
| **new** `r10-brace-dq-glue-sq-run` | 0.23 | **0.25** | **allow** | deny R6_EXPANSION |
| **new** `r10-comment-paren-glue-run` | 0.37 | **0.40** | **allow** | deny R6_TOKENIZE_FAILED |
| **new** `r10-bash-c-paren-glue-body` | 0.25 | **0.35** | **allow** | deny R6_DEFERRED_EXPANSION … |
| **new** `r10-case-cmdsub-run` | 0.31 | **0.44** | **allow** | deny R6_GROUPING … |
| **new** `r10-heredoc-unclosed-run` | 0.24 | **0.25** | **allow** | deny R6_HEREDOC |
| **new** `r10-param-nested-default-run` | 0.84 | **0.84** | deny R6_EXPANSION | same |
| **new** `r10-param-default-p-run` | 0.41 | **0.41** | deny R6_EXPANSION | same |
| **new** `r10-quoted-heredoc-unclosed-cmdsub-run` | 0.29 | **0.29** | allow | deny R6_HEREDOC (unclosed `$(` in a body: fail closed) |
| **new** `r10-param-sq-default-run-no-wrapper` | 0.73 | **1.01** | allow | allow |
| **new** `r10-assign-cmdsub-run-no-wrapper` (`x=$(a) ` run) | 0.77 | **1.10** | allow | allow |
| **new** `r10-quoted-paren-cmdsub-run-no-wrapper` | 0.33 | **0.48** | allow | allow |
| **new** `r10-deferred-sq-cmdsub-run-no-wrapper` | 0.33 | **0.54** | allow | allow |
| **new** `r10-closed-heredoc-run-no-wrapper` | 0.29 | **0.41** | allow | allow |
| **new** `r10-quoted-heredoc-prose-run-no-wrapper` | 0.28 | **0.41** | allow | allow |
| **new** `r10-backtick-run-no-wrapper` | 0.47 | **0.61** | allow | allow |
| **new** `r10-escaped-dq-cmdsub-run-no-wrapper` | 0.35 | **0.55** | allow | allow |
| **new** `r10-unclosed-sq-tail-no-wrapper` | 0.41 | **0.64** | allow | allow |
| **new** `r10-bound-launch-quoted-paren-args` (bound) | 0.35 | **0.35** | allow | allow |

Worst r10 row: **1.10 s** (a new no-wrapper adversarial row; r10 adds ≤ 0.33 s on any row). The reviewer quoted
≤ 0.95 s for their `_r6_lex` prototype on their rows; this reader does more work (heredoc bodies, deferred runs) and is
measured on more adversarial rows — still ≤ 1.10 s, well inside the 7 s watchdog. In-process sweep (52 units ×
3 prefixes at 262 144, python 3.12): r10 reading alone ≤ 0.43 s; `/usr/bin/python3` 3.9.6 loads and runs the file.

### r10 scan bounds

| Scan | Bound |
|---|---|
| top-level text | one pass (regex runs for literal text and blanks); returns at once without `$`/backtick |
| construct bodies | read once, inline, while finding their end (no rescan) |
| deferred runs, heredoc bodies, backtick bodies | each re-read once per nesting level; depth cap 9 |
| resyncs | ≤ 4 per text (an sq resync leaves no `'` after it; further stops are dq/backtick) |
| heredoc delimiter search | one compiled `^…$` (re.M) search per heredoc; an unterminated body ends the text |
| `${`/`$[`/`$(` with no closer after | O(1) via precomputed last `}`/`]`/`)` |

## N3 — the quoted-operand class (documented; behaviour unchanged)

Armed, bound and unbound (pure refusal codes; r8 = 798152b7c):

| Command | r8 | r9 | r10 |
|---|---|---|---|
| `cat "$f".sh` | out | deny R6_EXPANSION | deny R6_EXPANSION |
| `python3 "$script".py` | out | deny R6_EXPANSION | same |
| `cp "${src}".py "${dst}".py` | out | deny R6_EXPANSION | same |
| `rm -f "$tmp".sh` | out | deny R6_EXPANSION | same |
| `chmod +x "$f".sh` | out | deny R6_EXPANSION | same |
| `sed -i '' 's/a/b/' "$f".py` | out | deny R6_EXPANSION | same |
| `mv "$(mktemp)".py out.py` | out | deny R6_COMMAND_SUBSTITUTION | same |
| `touch "$(date +%s)".sh` | out | deny R6_COMMAND_SUBSTITUTION | same |
| `diff <(cat "$a".py) <(cat "$b".py)` | out | deny R6_PROCESS_SUBSTITUTION | same |
| `printf '%s\n' "$x"ool` | out | deny R6_EXPANSION | same |
| `cat $f.sh` / `python3 $script.py` (unquoted) | deny R6_EXPANSION | same | same |

The class: any word `<computed>.sh` / `<computed>.py` / `<computed>ool` / `<computed>ub.sh` … — quoted or not — can
spell a wrapper basename (`sub.sh`, `slot.py`, `pool`), so it is in scope wherever it stands, and an armed session
refuses any in-scope command that is not exactly one admitted form. r9 made quoting transparent (correct: the shell
joins), so the quoted twins joined r8's unquoted refusals; r10's own reading has the same property. A carve-out
("partial names only in command position") is NOT made: computed words outside command position still reach a wrapper
through `bash "$f".sh`, `xargs`, `env`, `exec`, `command`, `nohup`, `find -exec`, and C9 cannot prove a position rule
safe across those. **Owner decision:** accept the armed refusal of the class (status quo since r8 for unquoted), or
specify a positional rule for a future re-review.

## N4 — over-reads (scope only widens; unchanged)

- A backslash-newline inside single quotes is deleted by the r6/r9 views (`echo 'p\⏎ool'` is in scope; the shell keeps
  `p\⏎ool`, no wrapper).
- `${…}` inside single quotes is read as a construct by the r8/r9 views (`echo '${x:-p}ool'` is in scope).
- r10 adds (all widen): deferred runs re-read as script even when no shell reads them (`grep '$('` in scope, then
  admitted); `$"…"` read as bash locale quoting; every heredoc body read as script; an unterminated quote resyncs.

## Known limits (not claimed closed)

1. **Pinned over-refusals (armed only; `test_r10_known_over_refusals_are_pinned`):** an unterminated `$(` inside quoted
   data in a non-read command (`sed -i '' 's/$(/x/' f` → R6_NOT_A_PLAIN_LAUNCH); `'` inside `"${…}"`
   (`echo "${y:-it's}"` — bash 3.2 cannot run it either); bare braces in `${…}` whose bash/zsh ends differ by more than
   `}` (`echo ${x:-{a}b}`). Also any unarmed/armed text with a quoted-heredoc body holding an unclosed `$(`.
2. **bash 3.2 `$(…)` heuristics.** r10 models zsh's (full-parse) reading of `$(…)` plus explicit fail-closed rules
   (`case`), and reads every heredoc body as script; bash 3.2's own mis-parses (it fails rows 12–13) are not separately
   modelled. Divergence elsewhere is caught by the union with r8/r9 and the resync, not proven absent.
3. **zsh glob alternation in command position** (`(p|x)ool run …` with a staged file `pool` in cwd) is NOT read by any
   reader — a sibling of the r7 glob-head rule found during this lane, out of N1's scope (staged-file class). Recorded
   for the owner.
4. **Unarmed "pending" = DENY.** An unarmed command so large that `r6_names_wrapper` itself has not finished at the
   watchdog (multi-megabyte; ≤ ~1.7 s measured at 262 144) is denied at 7 s; r8 blocked such commands at 10 s via
   `onFailure`, r9 gave no decision.
5. Unarmed watchdog denial is a budget denial, not the legacy identity check: with all three `POOL_*` set it still
   denies (fail closed) when the text names a wrapper and judging exceeds the budget.
6. r9/r8 limits stand (C8 ledger limits 2–6): wholly computed words; a computed value producing `/`; homoglyphs; staged
   files; provider-side environment; T3 worktree scope roots; onFailure fleet versions; watchdog absent without
   `setitimer`; ground truth is this M2 (APFS case-insensitive; `/bin/bash` 3.2, `/bin/zsh`).

## Tests and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash\|provider_orchestrator_policy" tests/)
  → 1420 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed
    (C8: 1344 passed → +76 new, 0 changed)

tests/test_provider_orchestrator_policy.py → 914 collected, all passing (838 pre-existing, unchanged + 76 r10)
git diff tests/ → 0 deletions (no existing assertion touched; append-only)
```

New tests (76 collected): N1 deny rows 15, table coverage 1, real-hook reviewer row 1, sealed ground truth 1 (26 shell
runs: 13 zsh, 13 bash), honest-out 20, `_r6_lex` commit-idiom contrast 1, armed honest verdicts 3, pinned over-refusals
3, depth boundary 1, union/fail-before property 1, budget rows 20; N2: default-budget exact shape 1, lowered budget 3,
wrapper-naming texts 3, reviewer `gh` text 1, in-process state machine 1.

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL): the r10 reading (rule above, both scope directions,
  bounds), the N2 state machine and its "pending" choice, the pinned over-refusals.
- Owner decisions: N3 class (accept or specify a positional rule); limit 3 (zsh alternation globs); limit 4.
