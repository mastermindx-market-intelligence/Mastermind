# Lane: Director C11 — guard r12, the STRUCTURAL scope rule for armed sessions (2026-11-09)

Branch `t3/guard-r12-structural-armed`, created from `t3/t3-hermes-restart-recovery` at `13177c94a` (r11 merged).
Implementation by Claude Opus 5.5 (native ORCHESTRATION route) answering distinct re-check #7
(`REVIEW7_GUARD_R11_OPUS_20261110.md`: F1 MAJOR, F2 MAJOR, MINOR, NIT; budgets UNVERIFIED) and the principal's r12
decision. No push, no PR; no other worktree, `~/Mastermind`, `~/.hermes` or `~/.claude/settings.json` touched. Files:
the guard module, the policy test module, this ledger, and the REVIEW7 record (transcribed from the brief).
`provider_orchestrator_policy.py` is untouched. SELF_REVIEWED; CRITICAL row — the delta needs a fresh distinct re-review.

No real wrapper was invoked. Every shell ground-truth run is sealed:
`/usr/bin/env -i PATH=<fake-wrapper dir>:/usr/bin:/bin HOME=<tmp> /bin/zsh -f -c …` and
`… /bin/bash --norc --noprofile -c …` (macOS `/bin/bash` 3.2, `/bin/zsh` 5.9), stdin `/dev/null`; the fakes only touch a
marker file. Shell behaviour quoted below was MEASURED that way on this M2.

## The r12 rule (armed sessions only — `_guard_armed_launch`, `r12_armed_in_scope`)

An ARMED session (`MASTERMIND_SHARED_PLACEMENT` armed; binding present or not) judges a command as follows.

**OUT OF SCOPE** (allowed with no binding check) only when ALL of:

1. **No shell construct anywhere in the raw text, quoted or not** (`r12_constructs` → `[]`). A construct is any of:
   - `$` — any `$`: `$(`, `$((`, `${`, `$[`, `$'`, `$"`, `$NAME`, `$1`, `$?`, a lone `$`;
   - a backtick;
   - `\` followed by a newline (a line continuation);
   - `<<` (here-document `<<`/`<<-`, here-string `<<<`);
   - a zsh numeric glob `<N-M>` (`<->`, `<1-5>`);
   - `*`, `?`, `[` (globs);
   - `(` or `)` (subshell, group, function definition, array, zsh glob group, `((`, `$(`, `<(`, `>(`, `=(`, case pattern);
   - `{` — EXCEPT a `{` followed by a blank, newline, `;`, `&`, `|`, `<`, `>` or the end of the text, which is a word of
     its own and never a brace expansion (measured: `printf "<%s>" { a,b}` prints `<{><a,b}>` in bash, a parse error in
     zsh). `{}` is NOT exempt: bash expands `p{},ool}` to `p}` `pool` (measured);
   - `~` (tilde expansion at a word start, after `=`/`:`; zsh `EXTENDED_GLOB` exclusion);
   - `#` (a comment — whose extent the shells model differently — or a zsh `EXTENDED_GLOB` operator);
   - `^` (zsh `EXTENDED_GLOB` negation);
   - `!` followed by anything but a blank, newline, `=`, `"`, `'` or the end (history expansion; a lone `!`, `! cmd`,
     `!=`, `"fix!"` stay literal);
   - a control character other than tab and newline (`\r`, NUL, ESC, …);
   - one of the WORDS `eval`, `source`, `alias`, `trap`, `coproc`, `repeat` (case-insensitive, read on the quote-joined
     text: `e\val`, `'ev'al` count).
2. **No literal wrapper name** (`r12_literal_names_wrapper`): on the text with every `"`, `'` and `\` deleted (the
   word every shell builds from literal pieces, at any nesting depth of `bash -c '…'`/`ssh h "…"`), no `pool`,
   `sub.sh`, `remote_sub.sh`, `slot.py` as a word (`_WRAPPER_NAME_RE`, r8 dash view), none glued to a short option
   (`-O'pool run …'`), no `FABRIC_LAUNCH_RE`/`_wrapper_invocations` hit, and no `slot` module word
   (`python3 -m slot`, `-mslot`, `pkg.slot` — Python resolves it to `slot.py`; new in r12, r11 left
   `python3 -m slot glm -- run` out of scope).
3. **The tokenizer reads it** (`_r6_lex` → no error; an unterminated quote is in scope).
4. **The r6–r11 scanner (`r6_names_wrapper`) does not name a wrapper.** It is a SECONDARY reading: consulted only for
   construct-free, literally unnamed text, it can only widen scope (`test_r12_out_of_scope_needs_every_condition`,
   `test_r12_scanner_is_not_consulted_for_construct_bearing_commands`).

**IN SCOPE** otherwise: the command must be exactly one admitted ADMIT form — `_r7_parse`, unchanged since r7:
`LAUNCH ASSIGN* PREFIX* (WRAPPER | PYTHON SLOTPATH) ARG* REDIR*` / `NESTED bash|sh -c BODY` /
`READ RHEAD RARG* RREDIR*` with the git/rg/sed carve-outs, pipelines of read forms. Anything else is DENIED with
`R12_SHELL_CONSTRUCT` (naming up to three constructs) plus the grammar's `R6_*` codes. No `$`-expansion, command or
process substitution, here-document or backtick is admitted by any form (`R6_EXPANSION`, `R6_COMMAND_SUBSTITUTION`,
`R6_PROCESS_SUBSTITUTION`, `R6_HEREDOC` — kept). What the grammar does admit in scope, as before: a single-quoted `$`
(advisory `R6_DEFERRED_EXPANSION`), `~`/`^`/`#`/globs inside admitted READ arguments (`ls ~/notes`, `git log HEAD^`,
`cat docs/*.md`, `echo hi # note`; glob-sensitive heads refuse a leading glob), quoted construct characters in launch
arguments (`pool run glm a /tmp glm-5.3 '(x)'`), and the `~/…/pool` wrapper path.

**Why quoting does not exempt a construct.** Quoted text is literal to THIS shell, but `eval`, `bash -c`, `sh -c`,
`zsh -c`, `ssh HOST`, `trap`, `watch`, `find -exec sh -c`, `xargs sh -c`, `su -c`, `git -c alias.x='!…'` … hand it to
another shell that expands it (`bash -c 'p*l run …'` runs `pool` from `~/.local/bin`; `eval '$(printf p)ool …'`). That
set of programs is open, so a structural rule cannot trust quoting; quotes and backslashes still delimit literal words
(the literal check deletes them). This is stricter than the brief's wording ("quotes/backslashes are fine") on purpose:
without it the rule would again depend on recognising evaluators, and the structural table below (`bash -c '$(…)ool …'`
rows) could not deny with the scanner off.

**Why construct-free text cannot hide a name.** With none of the above, no shell (bash 3.2, zsh 5.9 with default or
`EXTENDED_GLOB`/`KSH_GLOB`/`extglob` options, at any `-c` nesting depth) performs an expansion: every word is a fixed
byte string formed from contiguous characters minus quote removal, which is exactly what the joined view reads.

**Refusal text** (exact headline, `_R12_HEADLINE`):
`Mastermind shared-placement guard: unobservable launch — armed session: shell expansion is not admitted; use a literal
command or a file argument. In a shared-placement (paid-launch) session a command holding a shell construct must be
exactly one admitted launch or read form, and this one is not; the guard does not search it for hidden wrapper names
(r12 structural rule; refusal codes: R12_SHELL_CONSTRUCT, …): …` followed by the clauses and the remedy ("Write it with
literal words only — quoting is fine, but no $, backticks, globs (* ? [), braces, parentheses, ~, #, ^, ! history,
here-documents or line continuations, even inside quotes; pass content through a file argument (git commit -F FILE);
or use the Read/Grep/Glob tools. Admitted read forms with constructs: …"). A command that ALSO names a wrapper
literally keeps the r7 wording ("names a paid-launch wrapper …"/"mentions a paid-launch wrapper name …") with
`R12_SHELL_CONSTRUCT` added to its codes.

**Unarmed sessions** are unchanged: the legacy identity check on the census, the r10 N2 deny-when-named watchdog, the
CI-wait checks — all driven by the scanner (`r6_names_wrapper`), which only gains the F1/F2 fixes below.

## The availability trade (principal's decision (d)) — refusal table

Armed only; each DENY bound and unbound, gate unreached, with the headline above
(`test_r12_over_refusal_class_is_refused_with_the_r12_reason`, 20 rows; unarmed all 20 stay allowed):

| Refused armed | Literal / tool alternative |
|---|---|
| `cd "$(git rev-parse --show-toplevel)"` | the worktree root is the session cwd; `cd` to the literal path |
| `git commit -m "$(cat <<'EOF'⏎fix: guard r12⏎…⏎EOF⏎)"` | write the message with the Write tool, `git commit -F msg.txt` |
| `echo "${HOME}/notes"` | the literal path |
| `export PATH="$HOME/.local/bin:$PATH"` | not needed: the session PATH is inherited |
| `for f in *.py; do wc -l "$f"; done` | `wc -l a.py b.py` (literal names) or Glob |
| `ls $(git rev-parse --show-toplevel)` | `ls` (cwd) or the literal path |
| `git log "$(git merge-base origin/master HEAD)"..HEAD` | `git log origin/master..HEAD` |
| `DATE=$(date +%Y%m%d); echo $DATE` | `date +%Y%m%d` |
| `cat "${TMPDIR:-/tmp}/out.log"` | `cat /tmp/out.log` or Read |
| `pytest -q $(git diff --name-only \| grep test_)` | list the test files literally |
| `wc -l $(rg -l foo src)` | `rg -c foo src` or Grep |
| `test -n "${CI:-}" && echo ci` | — (session state is not a worker concern) |
| `out=$((cd a && make) 2>&1)` | `make -C a 2>&1` (re-check #7 MINOR: already refused by r11's `$((` rule) |
| `python3 -c "import sys; print(sys.version)"` | `python3 --version`; quoted parentheses count (see "Why quoting") |
| `gh pr view 2329 --json statusCheckRollup --jq '.statusCheckRollup[].conclusion'` | `gh pr checks 2329` / drop `--jq` |
| `jq -r '.models[]' config.json` | Read the file |
| `awk '{print $1}' results.txt` | Read / Grep |
| `find . -name '*.py' -newer setup.cfg` | Glob |
| `(cd sub && make)` | `make -C sub` |
| `source .venv/bin/activate` | call `.venv/bin/python` by path |

**Existing r11 armed ALLOW expectations turned into DENY** (all hold a construct and are not an admitted form;
updated in place, no assertion removed — `_R12_ARMED_FLIPS` / `_R12_ARMED_FLIP_ROW_IDS`, checked by
`test_r12_armed_flips_are_exactly_construct_bearing_refusals`): 7 in-process commands (`TOOL=ls; $TOOL -la /tmp`,
`jq -r '.models[]' config.json`, `cd ${HOME:-/Users/me} && echo ok`, `echo "${name//-/_}"`, the r10 commit
here-document, the two REVIEW6 MINOR `\$(…${F})` forms that r11 had re-admitted) and 32 table rows: the r6 rows
`computed-word-out-of-scope` / `env-word-out-of-scope` (the wholly computed command word — the r2 arbitrary-process
limit through SHELL substitution is now closed in armed sessions), the r7 `glob-head` budget row, and 29 "no-wrapper"
budget rows of r8 (2), r9 (4), r10 (9), r11 (14). The CHANGED assertion lines (allow → the r12 expectation) are
`test_n3_computed_launch_refusal_stays_scoped_to_wrapper_tokens`, `test_r5_b1_structural_refusals_stay_scoped`
(the computed and `jq` commands now assert DENY + headline; `{ echo grouped; }` stays allowed),
`test_r9_honest_forms_keep_their_armed_verdict`, `test_r10_honest_forms_keep_their_armed_verdict`,
`test_r11_escaped_cmdsub_with_a_local_brace_is_admitted_armed` (expected verdict via `_r12_armed_expectation`), and the
row data above. No DENY expectation was weakened or deleted.

## Honest armed controls (`test_r12_honest_armed_controls_still_pass`, 28 rows; bound and unbound)

| Command | Armed verdict |
|---|---|
| faithful plain launch (identity prefix + `pool run glm a /tmp glm-5.3`) | bound ALLOW through the gate; unbound "missing binding" |
| `python3 /opt/mastermind/ext/slot.py glm -- run` (identity prefix) | same (launch) |
| `bash -c '<faithful plain launch>'` | same (launch) |
| inherited bare launch `pool run glm a /tmp glm-5.3` | same (launch) |
| `cat /opt/mastermind/ext/sub.sh`, `git commit -m "fix pool"` | ALLOW (literal name → in scope → admitted read form) |
| `python3 -m pytest tests/…`, `gh pr view 2329`, `git commit -F msg.txt`, `git log --oneline -5`, `rg -n foo src`, `sed -n 1,5p f`, `ls -la` | ALLOW (construct-free, out of scope) |
| `echo 'a b; c' > /dev/null`, `git status --short 2>/dev/null`, `printf 'x\n' > out.txt`, `wc -l < README.md`, `npm test -- --runInBand "a b"`, `{ echo grouped; }`, `git log -1 --format='%H %s'`, `make -C build test 2>&1 \| tail -n 20` | ALLOW (literal-only with quotes, redirections, pipes) |
| `git diff --stat HEAD~1`, `git log --oneline HEAD^..HEAD`, `ls ~/notes`, `cat docs/*.md`, `grep -rn 'TODO(' src`, `rg -n 'foo$' src`, `echo hi # a comment` | ALLOW (a construct, but an admitted read form) |
| `pytest -k pool` | **DENY, by the r7 NAME rule, not by r12** (construct-free; the literal wrapper name in a non-admitted command — unchanged since r7) |

## F1/F2 scanner fixes (secondary reading + unarmed mechanism; `_R10Text.script`)

| Fix | Detail |
|---|---|
| `case` anywhere | `case` is recognised at any position (r11: command position only); inside any substitution (`$(…)`, `<(…)`, `>(…)`, `=(…)`) it fails closed |
| `case WORD {` (found by C11) | zsh's alternate `case x { (x) …;; }` opens pattern position like `in`; it ends at `}` |
| `[[` anywhere | sets `in_condition` at any position; the `]]` that closes it leaves a "maybe command" position (`if [[ … ]] cmd`) |
| fd prefixes | an unquoted all-digit word or `{name}` glued to `<`/`>` is the redirection's, not the command word (`2>/dev/null case …`) |
| maybe-command positions | after `repeat N`, `coproc` (added to `_R10_KEEP_COMMAND_POSITION`), a `for/select/foreach NAME (…)` list, a `((…))` command, a `(pattern)` arm and `]]`: keywords are recognised but a `(` there is never a CERTAIN subshell (it stays an uncertain group: rule D's dual reading) |
| `=(` | at a word start, read through `substitution()` like `<(` (its body a script) |
| unmatched top-level `)` | `_R10Fail` (in scope) unless a case pattern is open; inside a rule-D dual-read comment region it ends the region's group: argument position, sticky |

Rows — fail-before (r11 = `13177c94a`) → after (r12), REAL hook command line, armed, BOUND (owner-channel shim) and
UNBOUND; gate reached: no in every r12 row. `{N}` = `$($(: "("; printf p)ool run grok a /tmp grok-4)`. The brief
carried re-check #7's families, not its verbatim rows: the 12 REVIEW7 rows are RECONSTRUCTED from the family
descriptions; C11 adds 6. Ground truth: a sealed zsh RUNS the fake wrapper for each (bash: syntax error, runs nothing).

| id | origin | command | r11 bound/unbound | r12 bound/unbound (codes) |
|---|---|---|---|---|
| r7-f1-fd-case-in-newline | REVIEW7 F1 | `2>/dev/null case x in⏎(x # {N}) :;; esac` | **ALLOW/ALLOW** | deny/deny (R12_SHELL_CONSTRUCT, R6_REDIRECTION, R6_KEYWORD, R6_GROUPING, …) |
| r7-f1-fd-dup-condition-newline | REVIEW7 F1 | `2>&1 [[ a =~ ⏎(a # {N}) ]] && echo m` | **ALLOW/ALLOW** | deny/deny (same family) |
| r7-f1-fd-read-case-in-newline | REVIEW7 F1 | `3</dev/null case x in⏎(x # {N}) :;; esac` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-repeat-case | REVIEW7 F1 | `repeat 1 case x in⏎(x # {N}) :;; esac` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-repeat-condition | REVIEW7 F1 | `repeat 1 [[ a =~ ⏎(a # {N}) ]]` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-coproc-condition | REVIEW7 F1 | `coproc [[ a =~ ⏎(a # {N}) ]]⏎wait` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-for-short-case | REVIEW7 F1 | `for x (a) case x in⏎(x # {N}) :;; esac` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-if-short-condition | REVIEW7 F1 | `if [[ a ]] [[ a =~ ⏎(a # {N}) ]]` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-arm-after-pattern-condition | REVIEW7 F1 | `case x in (x) [[ a =~ ⏎(a # {N}) ]];; esac` | **ALLOW/ALLOW** | deny/deny |
| r7-f1-cmdsub-fd-case | REVIEW7 F1 | `$(2>/dev/null case x in x) printf p;; esac)ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R12_SHELL_CONSTRUCT, R6_COMMAND_SUBSTITUTION, …) |
| r7-f1-cmdsub-repeat-case | REVIEW7 F1 | `$(repeat 1 case x in x) printf p;; esac)ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny |
| r7-f2-eqparen-case | REVIEW7 F2 | `: =(case x in x) :;; esac) (x # {N})` | **ALLOW/ALLOW** | deny/deny |
| c11-case-brace-form | C11 F1 | `case x {⏎(x # {N}) :;; }` | **ALLOW/ALLOW** | deny/deny |
| c11-coproc-case | C11 F1 | `coproc case x in⏎(x # {N}) :;; esac⏎wait` | **ALLOW/ALLOW** | deny/deny |
| c11-if-short-case | C11 F1 | `if [[ a ]] case x in⏎(x # {N}) :;; esac` | **ALLOW/ALLOW** | deny/deny |
| c11-arm-after-pattern-case | C11 F1 | `case x in (x) case y in⏎(y # {N}) :;; esac;; esac` | **ALLOW/ALLOW** | deny/deny |
| c11-fd-case-sub-sh | C11 F1 | `2>/dev/null case x in⏎(x # $($(: "("; printf s)ub.sh glm-memory a)) :;; esac` | **ALLOW/ALLOW** | deny/deny |
| c11-eqparen-case-slot-py | C11 F2 | `: =(case x in x) :;; esac) (x # $($(: "("; printf sl)ot.py glm a /tmp glm-5.3))` | **ALLOW/ALLOW** | deny/deny |

Each row is denied by STRUCTURE alone (same verdict and reason with the scanner off) AND named by the fixed scanner
(r11's scanner named none). Real hook CLI 0.07–0.08 s per row.

## (1) The structural escape table — every recorded escape, scanner off

`test_r12_structural_table_every_escape_row_denies_without_the_scanner`: **335 escape rows** this module encodes from
REVIEW2–REVIEW7 and the C5–C11 ledgers (r6 deny rows 81, REVIEW2 shape rows 53, refused read forms 55, r7 hook rows 11,
r8 scope escapes × 3 wrappers 24, r8 git 17, r9 16, r10 15, r11 45, r12 18). Armed, bound and unbound: **335/335 DENY,
gate never reached**, verdicts AND reasons byte-identical with `r6_names_wrapper`/`_r10_lexed_reading` monkeypatched to
"names no wrapper"; the 203 rows holding a construct carry `R12_SHELL_CONSTRUCT`, the other 132 are in scope by the
literal check and refused with their R6 codes.

`test_r12_every_documented_wrapper_running_span_is_refused_or_gated`: the RECORDS themselves — every inline code span of
REVIEW2–REVIEW7 and LANE C5–C11 that mentions a wrapper (2 316 spans at C11 → 320 candidates; `A`/`…N1…` expanded;
network/destructive programs never run), run in sealed zsh and bash: **188 spans run a fake wrapper**; armed with the
scanner off **150 are DENIED and 38 are plain launches the binding gate judges (bound and unbound); 0 allowed unjudged**
(r11 allowed 2: the C6/C8 wholly computed `$(printf p)$(printf ool) run` forms). This ledger and the REVIEW7 record
are harvested too: at commit **196 running spans → 157 DENIED, 39 gated, 0 unjudged** (11 of them from this ledger);
the two arbitrary-process examples in "Limits" are excluded there and pinned instead.

## Fuzz (sealed ground truth: zsh AND bash)

| Generator | Candidates | r11 | r12 |
|---|---|---|---|
| Committed structured `_r11_fuzz_candidates` + the F1/F2 prefixes (13), contexts (11) and glue (4) — SCANNER (unarmed) reading, default seed 20261113 | 3 000 | out 244, **63 sealed escapes** | out 25, 50 shell runs, **0 escapes** |
| same, seeds 1, 2, 3 | 3 × 20 000 | out 1 616 / 1 619 / 1 646, **439 / 439 / 439 escapes** (1 317; the equal counts re-counted: 435 zsh + 9 bash / 437 + 6 …) | out 155 / 128 / 148, 862 shell runs, **0 escapes** |
| same generator, judged ARMED (the structural rule) | 3 000 + 3 × 20 000 | (r11 armed out of scope = its scanner's out, above) | **out of scope 0, admitted 0, DENY 63 000** |
| Literal fuzz `_r12_literal_candidates` (construct-free pieces: quotes, `\`, operators, wrapper fragments, `bash -c`/`sh -c`/`zsh -fc`/`env`/`exec`/`xargs`), ARMED, default seed 20261116 | 1 500 | — | out of scope 1 187, all construct-free, **0 escapes** (committed test) |
| same, seeds 1, 2, 3 | 3 × 10 000 | — | out of scope 7 874 / 7 926 / 7 869 (all construct-free and literally unnamed), **47 338 sealed shell runs, 0 escapes** |
| Mutations of the r11+r12 escape rows (+ F1/F2 tokens), armed AND scanner | 800 (committed seed 20261117) | — | test asserts 0 escapes |
| Re-check #7's generator (275 escapes at r11) | not in this checkout | — | not re-run (its families are in the extended lists above) |

Totals on the final code: **136 500 candidates; armed: 0 construct-bearing candidate out of scope, 0 escapes in
48 838 sealed runs (literal side); scanner: 0 escapes in 1 218 sealed runs (r11: 1 380 escapes on the same
candidates).** A liveness check pins that quote/backslash-joined literal names DO run in sealed shells and are in scope
(`test_r12_literal_joined_names_run_and_are_in_scope`, 11 forms incl. nested `bash -c`/`sh -c`).

The committed tests run the default seeds (structured armed 3 000, literal 1 500, mutations 800, r11's scanner fuzz on
the extended lists 3 000 + 800); larger runs are opt-in through the existing environment variables.

## Scope differential of the scanner (unarmed path), r11 → r12

111 699 distinct string constants of every `tests/*.py` at C11 + 25 000 random F1/F2 token soups (seed 20261115):
**constants: gained 62, lost 0; random: gained 1 734, lost 14 — none of the 14 runs anything in sealed zsh or bash**
(all syntax-error soup in which r11's misread `case x {`/`((` failed closed and r12's correct pattern reading resyncs at
a word-level unterminated quote, the r10 leniency).

## (5) Unarmed byte-identity

`test_r12_unarmed_output_is_byte_identical_to_r11` — 16 rows through the real hook command line, stdout sha256 pinned
from r11 (`13177c94a`): the three r10 N2 shapes (deny-when-named at the watchdog), the REVIEW4 F4 CI text and the
unclosed-heredoc `gh` text (no decision), foreground `gh run watch`, interval and cadence denials, the loop/delayed poll
denials, the background-watch context, a single read, the unarmed missing-identity denial, an unarmed `$(…)` text —
**all byte-identical**. One intended difference: an F1 row under the N2 heredoc tail — r11 gave NO decision (its scanner
missed the name: fail open), r12 denies with the N2 text. Armed budget-DENY stdout sha256
`9c651f8f3ce0b6fff6e10c458de8bd2de55ef509558b635cb62b3fe1f307ac11` unchanged (r11 test kept and green).

## (7) Budgets — 262 144 chars, real hook command line (`python3` 3.14.7), armed

115 rows, one run each, M2 (re-check #7: UNVERIFIED for r11 beyond the committed rows):

| Rows | r12 seconds | verdicts |
|---|---|---|
| 23 r8 rows | 0.09–0.74 | as in the tests (2 flipped to DENY) |
| 15 r9 rows | 0.15–0.65 | (4 flipped) |
| 20 r10 rows | 0.13–0.37 | (9 flipped) |
| 19 r11 rows | 0.15–0.76 | (14 flipped; r11 measured 0.27–1.78 there — construct rows no longer run the scanner armed) |
| 38 r12 rows (F1/F2 rows padded with their own structure, construct fill, admitted forms with constructs, construct-free fill, literal names) | 0.17–1.16 | 21 DENY, 17 ALLOW |
| 25 construct-free pathological fills (C11 probe: `a⏎`, `a;`, `a\|`, `a>b `, quote runs, `p\o\o\l `, …) | 0.15–**1.50** | as expected |

**True worst r12: 1.50 s** (`a⏎` × 131 072 — construct-free, so `_r6_lex`, the literal check and the secondary scanner
all run); worst r12 table row 1.16 s (`r12-literal-newlines`). Every construct-bearing row skips the scanner: ≤ 0.76 s.
`r12_constructs` + `r12_literal_names_wrapper` are two C-level regex scans and one quote-joined view: linear
(`test_r12_construct_scan_is_linear`: < 0.5 s at 262 144, ≤ 8× from 64 K to 256 K). The fixed scanner on F1/F2 fills
at the cap stays < 3 s in process (`test_r12_scanner_stays_fast_on_the_f1_f2_shapes`, 14 shapes).

## Limits (not claimed closed)

1. **Homoglyphs / names by resolution.** A literal word that is not a wrapper name by its bytes is out of scope:
   `рool` (Cyrillic р) names a different file. Likewise a STAGED copy, symlink, hard link or `hash -p`/PATH entry that
   resolves an innocent literal word to a wrapper, an alias or function the provider's shell snapshot defines, and
   `python3 -c 'import slot'` beyond the `slot` word check. r12 decides shell structure, not the filesystem or the
   provider's environment (C9 limits: staged files, provider-side environment).
2. **Arbitrary process (REVIEW_2329 r2).** A PROGRAM may compute the name and another run it, with no shell construct:
   `printf '\160ool run grok a /tmp grok-4' | sh` and `echo cG9vbCBydW4gZ3JvayBhIC90bXAgZ3Jvay00 | base64 -d | sh` run
   the wrapper in sealed shells and are allowed unjudged armed (`test_r12_known_limits_are_pinned`; pinned, not
   desired). r12 does close the SHELL-substitution form of this class in armed sessions
   (`$(printf '\160\157\157\154') run …`, `$LAUNCHER run …` were the r6 doc-limit rows). A possible follow-up, not
   in this lane's brief: treat a shell or interpreter word after `|` (reading a program from stdin) as in scope.
3. **Shell versions and options.** Ground truth is this M2's `/bin/bash` 3.2 and `/bin/zsh` 5.9 (`zsh -f`). The rule's
   construct set covers bash ≥ 4 and the zsh/bash glob options (`EXTENDED_GLOB`, `KSH_GLOB`, `extglob`, `BRACE_CCL`)
   by construction, but other shells were not measured. The ADMIT grammar's own reading of in-scope READ forms
   (`_r6_lex`: comments recognised, a non-interactive shell) is r7's and unchanged.
4. **The scanner is no longer load-bearing for armed security**, but it remains the UNARMED mechanism; its fixed
   seams are tested, not proven (14 random-soup losses above run nothing).
5. **Over-refusal** (table above): every construct, even inside quotes, puts an armed command in scope; quoted
   brackets in `jq`/`python3 -c`/`awk` programs are refused unless the command is an admitted read form.
6. r7–r11 limits stand otherwise (T3 worktree scope roots, onFailure fleet versions, watchdog absent without
   `setitimer`).

## Tests and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash\|provider_orchestrator_policy" tests/)
  → 1773 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed  (229.5 s)
    (C10: 1532 passed → +241; the d8 identity scan in test_ceo_submit_armed_composition.py green)
```

`tests/test_provider_orchestrator_policy.py` → 1 267 collected (C10: 1 026; +241 r12). New tests: flips record 1;
sealed zsh ground truth 1 (18 rows); escapes refused by structure alone 18; F1/F2 scanner names each row 18; real hook
CLI 8; structural escape table 1 (335 rows × bound/unbound × scanner on/off); documented-span harvest 1 (188 running
spans); known limits pinned 1; honest controls 28; `pytest -k pool` name rule 1; over-refusals 20 + alternatives 1;
construct kinds 38; literal text 18; literal check 1; joined names run + in scope 11; out-of-scope conditions 1; scanner
not consulted 1; linear scan 1; unarmed byte-identity 16; armed structured fuzz 1; literal fuzz 1; mutation fuzz 1;
budgets 38; scanner F1/F2 speed 14 — 241 r12 tests. Assertion lines 585 → 673; the three changed `assert … ("allow", "allow")` lines
became `assert … (expected, expected)`; no assertion removed.

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL): the construct set (is any expansion trigger missing for
  bash 3.2/5.x or zsh with common options?), the literal check (joined view, glued options, `slot` module), the
  quoted-construct decision, the flipped expectations, and the F1/F2 scanner fixes for the unarmed path.
- Owner decisions carried: limit 2 (stdin-to-interpreter arbitrary-process forms), the quoted-construct strictness
  (availability), C9/C10 limits.
