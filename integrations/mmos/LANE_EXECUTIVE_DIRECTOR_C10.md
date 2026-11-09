# Lane: Director C10 — guard r11, arithmetic / `${…}` / word fragments / uncertain parentheses (2026-11-09)

Branch `t3/guard-r11-arith-brace-fragments`, created from `t3/t3-hermes-restart-recovery` at `8cc4ce4ca` (r10 merged).
Implementation by Claude Opus 5.5 (native ORCHESTRATION route) answering distinct re-check #6
(`REVIEW6_GUARD_R10_OPUS_20261110.md`: N5 MAJOR, N5b, N6 MAJOR, N7 MAJOR, MINOR availability, NIT; N2 ACCEPT).
No push, no PR; no other worktree, `~/Mastermind`, `~/.hermes` or `~/.claude/settings.json` touched. Files: the guard
module, the policy test module (append-only), this ledger, and the REVIEW6 record (transcribed from the brief).
`provider_orchestrator_policy.py` is untouched. SELF_REVIEWED; CRITICAL row — the delta needs a fresh distinct re-review.

No real wrapper was invoked. Every shell ground-truth run is sealed:
`/usr/bin/env -i PATH=<fake-wrapper dir>:/usr/bin:/bin HOME=<tmp> /bin/zsh -f -c …` and
`… /bin/bash --norc --noprofile -c …` (macOS `/bin/bash` 3.2, `/bin/zsh` 5.9), stdin `/dev/null`; the fakes only touch a
marker. Shell behaviour quoted below was MEASURED that way on this M2.

## Finding → fix → test

| # | Sev | Finding | Fix (r11) | Tests |
|---|---|---|---|---|
| N5 | MAJOR | `#`/`<<` inside `$((…))`, `((…))`, `for ((…))` read as comment / here-document | **Arithmetic context** (`_R10Text.arith`, rule A below) for `$((`, a `((` command in certain command position, `for ((` | `test_r11_escapes_are_judged_and_refused` (8 N5 + 2 N5b rows + C10's `f() ((` row), sealed ground truth, real-hook rows |
| N5b | (N5) | `(( y = 1 << 2 ))⏎…` opened a here-document, shifting quote parity | `<<` is a shift in an arithmetic context | same |
| N6 | MAJOR | quote/construct inside `brace()` → `_R10Stop` → resync dropped the word; in-dq `${…}` model wrong | **Rule B**: in double quotes `${` ends at the FIRST `}`; unquoted, any character after bash's end but `}` fails closed at once; `_R10Stop` inside ANY construct → `_R10Fail` | 12 N6 rows (dq forms, `env`/`exec`/backtick/`eval '…'` wrappers, 4 bash-only forms) |
| N7 | MAJOR | dq `eval`/`-c` strings gluing a construct to literal text never read as script | **Rule C**: fragment judging (raw and quote-deleted) of every word mixing a computed item with literal text holding a blank/operator/quote | 4 N7 rows |
| MINOR | availability | `ssh h "x=\$(cat ${F}); echo \$x"`, `bash -c "n=\$(wc -l < ${F}); echo \$n"` refused armed | **Rule C**: the deferred re-read reads the WHOLE word, a placeholder per computed part (r10 cut it into runs) | `test_r11_escaped_cmdsub_with_a_local_brace_is_admitted_armed` (allow/allow, gate not reached), `test_r11_deferred_word_is_read_whole_with_placeholders` |
| NIT | — | "worst 1.10 s" understated | true worst cases recorded below (1.78 s) | `test_r11_budget_rows_finish_through_the_real_hook_command_line` (19 rows) |
| N2 | ACCEPT | keep byte-identical | unchanged | `test_r11_armed_budget_denial_stdout_is_byte_identical_to_r8` (sha256 `9c651f8f3ce0b6fff6e10c458de8bd2de55ef509558b635cb62b3fe1f307ac11`, 437 bytes); r10's N2 tests unchanged and green |
| **N8** | **MAJOR (found by C10)** | zsh reads a non-command-position `(` as a GLOB GROUP (`#` literal, blanks/newlines inside, constructs run); bash does for `[[ =~ (…) ]]` — r10 read a subshell and the `#` hid the rest of the line: `echo (1 # $($(: "("; printf p)ool run …))` runs `pool` in zsh, r10 ALLOW/ALLOW | **Rule D** (uncertain parentheses) | 16 N8 rows |
| **N1-cont.** | MAJOR (found by C10, pre-existing) | `$\⏎(…)`, `$\⏎{…}` — a line continuation between `$` and the opener (both shells join them); r10 read `$` + `\⏎` + `(` | **Rule E**: the text is also read with every `\⏎` removed (union) | 2 rows (`$\⏎(: "("; printf p)ool …` runs in zsh AND bash) |

## The r11 rules, stated precisely (`_r10_lexed_reading` and `_R10Text`; r11 block comment in the guard)

**A. Arithmetic context** (`$((`; a `((` in CERTAIN command position — rule D; `((` after a command-position `for`).
Read to the `))` that closes it: `#` and `<<` are literal (a shift), parentheses nest, `\x` escapes, constructs
(`$(…)`, `$((…))`, `${…}`, `$[…]`, backticks) are read with their bodies as script, and the words between them are
judged too (over-read). Measured: `echo $(( 1 # 2⏎)) after` → "operator expected at `# 2`" (zsh) / "error token is
"# 2⏎"" (bash); `echo $(( 1 << 2 ))⏎2` prints 4 then runs `2`; `16#ff`, zsh `[##36]` work. **Fail closed** (in scope):
`'`; `"` unless the span to the next `"` holds none of `( ) { } ' `` ` `` `\` and `double()` ends exactly there
(`(( "$n" > 3 ))` stays out; zsh ignores quotes for the extent, bash honours them: `echo $(( ")" ))` → zsh runs `)`);
`$'`/`$"`; a quote inside a `${…}` there; a `)` closing the context that is not `))` (bash reads `$((a) + (b))` as
arithmetic, zsh as a command substitution); an unterminated context; a `#` at a word start (after a blank, newline or
operator character) whose rest of line holds `( ) ' " `` ` `` $ \` (a comment-reading shell could end the context
elsewhere). Measured to be arithmetic in BOTH shells also: `f() ((…))`, a case arm `x) ((…))`, `! ((…))`; zsh only:
`repeat 1 ((…))`, `coproc ((…))`, `>/dev/null ((…))` — those positions are uncertain (rule D).

**B. `${…}` extents.** Inside double quotes (and unquoted here-document bodies) BOTH shells end `${` at the FIRST `}`
(measured: `"[${x:-{}]"` → `[{]`, `"[${x:-{a}b}]"` → `[{ab}]`, `"[${x:-"a}b"}]"` → `[a}b]` in both; heredoc
`[${x:-{a}b}]` → `[{ab}]` in both). Unquoted: bash ends at the first `}`, zsh counts; once bash's end is passed, any
character other than `}` → `_R10Fail` at once. Inside arithmetic, any quote in `${…}` → `_R10Fail`. `'` inside
`"${…}"` → `_R10Fail` (r10, kept). An `_R10Stop` (unterminated quote/backtick) raised inside `${…}`, `$[…]`, `$(…)`,
`$((…))`, `<(…)`/`>(…)` or a `((` command → `_R10Fail`; only a WORD-level unterminated quote still resyncs.

**C. Words.** Every word is judged whole (r10). A word holding a computed item and literal text with a blank,
newline, `; & | < > ( )`, quote or backslash is ALSO split at blanks/newlines/operators inside its literal parts —
once as written, once with `' " \` deleted — and each fragment judged by r10's word rule (`_r8_items_spell`, ≥ 1
fixed literal). A word whose quoted/escaped literal holds `$` or a backtick is re-read as script ONCE, whole, with
`\x00` standing for each computed part; the placeholder is a computed item wherever it lands (bare, `'…'`, `"…"`,
`${…}` operator words read as `$_`).

**D. Uncertain parentheses (N8).** A `(` is a CERTAIN subshell only in command position, not glued (no word in
progress and the previous character is a blank/newline/operator), not a redirection target, not inside `[[ … ]]`,
not inside an uncertain group and not after the sticky switch. Every other `(` opens an UNCERTAIN group (measured
glob groups in zsh: argument position, glued `a(…)`, here-document delimiter `<<:a(…`, case patterns after `in`/`;;`,
`for x in (…)`, `: > (…)`, `noglob (…)`; bash too: `[[ a =~ (…) ]]`). Inside an uncertain group a word-start `#` is
read BOTH ways: the rest of its line is read as an isolated script with every `#` literal, then skipped as a comment.
If that skipped region holds `( ) ' "` or a backtick — or a zsh word terminator `; & < >` occurs inside an uncertain
group (zsh ends the word and drops the open group: `$(: a( "(" & printf p)` ends at the `)`) — the structure past it may
differ from zsh's: inside `$(…)`/`<(…)` → `_R10Fail`; at the top level → sticky (every later `(` uncertain, every
later word-start `#` read both ways). A non-glued `((` in an uncertain position may be arithmetic: `<<` inside it →
`_R10Fail`; a glued `((` (`print((…))`) is never arithmetic. Case patterns: after `case WORD in` and after `;;`, `;&`,
`;;&`, zsh `;|` a pattern follows — kept across newlines and `;` (zsh accepts `;; ;` and `;;⏎(…)`) — until a bare
`pattern)` (a case arm: command position) or the `)` of `(pattern)` (an arm left uncertain). After a group's `)` an
operator follows (not command position). Inside `[[ … ]]` no position is a command position.

**E. Line continuations.** When the raw text holds `\⏎`, it is read a second time with every `\⏎` removed (union;
an over-read inside single quotes, like the r6–r9 views).

Unchanged from r10: depth cap 9, resync cap 4, here-document handling, `case` in a substitution, the r6–r9 readers.

## Rows — fail-before (r10 = 8cc4ce4ca) → after (r11), real hook command line

Armed; BOUND = binding present through the owner-channel shim (every binding check reachable), UNBOUND = no binding.
Gate reached: **no** in every r11 row (refused by shape). Ground truth = a sealed shell RAN a fake wrapper.
45 rows: REVIEW6's 26 (N5 8, N5b 2, N6 12, N7 4) + 19 found by C10. `sub.sh` args `glm-memory a`, `slot.py` args
`glm a /tmp glm-5.3`, else `run grok a /tmp grok-4`.

| id | origin | command | r10 bound/unbound | r11 bound/unbound (codes, bound) | gate | ground truth |
|---|---|---|---|---|---|---|
| n5-dparen-comment | REVIEW6 N5 | `(( 1 # $($(: "("; printf p)ool run grok a /tmp grok-4) ))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-dparen-hash-x | REVIEW6 N5 | `(( #x + $($(: "("; printf p)ool run grok a /tmp grok-4) ))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-arith-hash-x-nl | REVIEW6 N5 | `x=a; echo $((#x + $($(: "("; printf p)ool run grok a /tmp grok-4)⏎))` | **ALLOW/ALLOW** | deny/deny (R6_ASSIGNMENT,R6_COMPOUND_LIST,R6_EXPANSION,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-arith-comment-nl | REVIEW6 N5 | `echo $(( 1 # $($(: "("; printf p)ool run grok a /tmp grok-4)⏎))` | **ALLOW/ALLOW** | deny/deny (R6_EXPANSION) | no | zsh ✓ bash ✓ |
| n5-dparen-sub-sh | REVIEW6 N5 | `(( 1 # $($(: "("; printf s)ub.sh glm-memory a) ))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-dparen-slot-py | REVIEW6 N5 | `(( 1 # $($(: "("; printf sl)ot.py glm a /tmp glm-5.3) ))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-dparen-and-escaped | REVIEW6 N5 | `(( x = 1 )) && (( 1 # $($(: \(; printf p)ool run grok a /tmp grok-4) ))` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5-for-dparen | REVIEW6 N5 | `for (( i=0 # $($(: "("; printf p)ool run grok a /tmp grok-4); i<1; i++ )); do :; done` | **ALLOW/ALLOW** | deny/deny (R6_ASSIGNMENT,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n5b-dparen-shift | REVIEW6 N5b | `(( y = 1 << 2 ))⏎echo "⏎2⏎"; $(: "("; printf p)ool run grok a /tmp grok-4 #"` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_HEREDOC,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n5b-for-shift | REVIEW6 N5b | `for (( i = 1 << 2; i < 0; i++ )); do :; done⏎echo "⏎2⏎"; $(: "("; printf p)ool run grok a /tmp grok-4 #"` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_HEREDOC,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n6-dq-brace-default | REVIEW6 N6 | `x=p; "${x:-{}"ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-dq-brace-sub-sh | REVIEW6 N6 | `x=s; "${x:-{}"ub.sh glm-memory a` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-dq-brace-dash | REVIEW6 N6 | `x=p; "${x-{}"ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-dq-brace-hash | REVIEW6 N6 | `x=p; "${x#{}"ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-env | REVIEW6 N6 | `x=p; env "${x:-{}"ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-exec | REVIEW6 N6 | `x=p; exec "${x:-{}"ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✓ |
| n6-backtick | REVIEW6 N6 | `x=p; `"${x:-{}"ool run grok a /tmp grok-4`` | **ALLOW/ALLOW** | deny/deny (R6_ASSIGNMENT,R6_COMMAND_SUBSTITUTION,R6_COMPOUND_LIST,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n6-eval-sq | REVIEW6 N6 | `x=p; eval '"${x:-{}"ool run grok a /tmp grok-4 # '` | **ALLOW/ALLOW** | deny/deny (R6_ASSIGNMENT,R6_COMPOUND_LIST,R6_DEFERRED_EXPANSION,R6_ENV_BUILTIN,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n6-bare-nl-dq | REVIEW6 N6 | `x=p; ${x:-{}ool run grok a /tmp grok-4⏎: "` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✗ bash ✓ |
| n6-bare-hash-dq | REVIEW6 N6 | `x=p; ${x:-{}ool run grok a /tmp grok-4 #"` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✗ bash ✓ |
| n6-bare-hash-backtick | REVIEW6 N6 | `x=p; ${x:-{}ool run grok a /tmp grok-4 # `` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✗ bash ✓ |
| n6-bare-nl-sq | REVIEW6 N6 | `x=p; ${x:-{}ool run grok a /tmp grok-4⏎: '` | **ALLOW/ALLOW** | deny/deny (R6_TOKENIZE_FAILED) | no | zsh ✗ bash ✓ |
| n7-eval-dq | REVIEW6 N7 | `eval "$(: "("; printf p)ool run grok a /tmp grok-4"` | **ALLOW/ALLOW** | deny/deny (R6_COMMAND_SUBSTITUTION,R6_ENV_BUILTIN) | no | zsh ✓ bash ✓ |
| n7-bash-c-dq | REVIEW6 N7 | `bash -c "$(: "("; printf p)ool run grok a /tmp grok-4"` | **ALLOW/ALLOW** | deny/deny (R6_COMMAND_SUBSTITUTION) | no | zsh ✓ bash ✓ |
| n7-sh-c-escaped | REVIEW6 N7 | `sh -c "$(: \(; printf p)ool run grok a /tmp grok-4"` | **ALLOW/ALLOW** | deny/deny (R6_COMMAND_SUBSTITUTION) | no | zsh ✓ bash ✓ |
| n7-zsh-fc-sub-sh | REVIEW6 N7 | `zsh -fc "$(: "("; printf s)ub.sh glm-memory a"` | **ALLOW/ALLOW** | deny/deny (R6_COMMAND_SUBSTITUTION,R6_NESTED_SHELL) | no | zsh ✓ bash ✓ |
| n8-argument-group | C10 N8 | `echo (1 # $($(: "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-glued-group | C10 N8 | `echo a(1 # $($(: "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-case-pattern-group | C10 N8 | `case x in a) :;; (x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-for-in-group | C10 N8 | `for x in (a # $($(: "("; printf p)ool run grok a /tmp grok-4)); do :; done` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-redirect-target-group | C10 N8 | `: > (x # $($(: "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH,R6_TOKENIZE_FAILED) | no | zsh ✓ bash ✗ |
| n8-regex-group | C10 N8 | `[[ a =~ (a # $($(: "("; printf p)ool run grok a /tmp grok-4)) ]] && echo m` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n8-noglob-group | C10 N8 | `noglob (x # $($(: "("; printf p)ool run grok a /tmp grok-4)⏎)` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n5-function-body-dparen | C10 N5 | `f() (( 1 # $($(: "("; printf p)ool run grok a /tmp grok-4) )); f` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n8-region-paren-group | C10 N8 | `echo (a # (⏎)⏎(b # $($(: "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-region-paren-line-comment | C10 N8 | `echo (a # (⏎) ⏎ x # $($(: "("; printf p)ool run grok a /tmp grok-4)` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-region-paren-cmdsub-end | C10 N8 | `$(printf p; : "("; : (a # )⏎)ool run grok a /tmp grok-4; : (b # (⏎))` | **ALLOW/ALLOW** | deny/deny (R6_COMMAND_SUBSTITUTION,R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-region-double-hash | C10 N8 | `echo (1 # #$($(: "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-case-terminator-semicolon | C10 N8 | `case x in a) :;; ; (x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-case-terminator-newline | C10 N8 | `case x in a) :;;⏎(x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-case-in-newline | C10 N8 | `case x in⏎(x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-heredoc-delimiter-group | C10 N8 | `echo (1 # $($(<<:a( "("; printf p)ool run grok a /tmp grok-4))` | **ALLOW/ALLOW** | deny/deny (R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n8-condition-newline | C10 N8 | `[[ a =~ ⏎(a # $($(: "("; printf p)ool run grok a /tmp grok-4)) ]] && echo m` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_KEYWORD,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✗ |
| n1-continuation-cmdsub | C10 N1 | `$\⏎(: "("; printf p)ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_COMPOUND_LIST,R6_GROUPING,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |
| n1-continuation-brace | C10 N1 | `$\⏎{x:-p${y#"}"}}ool run grok a /tmp grok-4` | **ALLOW/ALLOW** | deny/deny (R6_EXPANSION,R6_NOT_A_PLAIN_LAUNCH) | no | zsh ✓ bash ✓ |

## Honest forms

Real hook CLI, r10 vs r11, bound and unbound (45 rows): C9's 20 `_R10_HONEST_OUT`, the reviewer's 10, the three
`\$(` forms, the three pinned refusals, 9 C10 forms → **SAME** verdicts except the two MINOR forms, which go
deny → **allow/allow** (intended): `ssh h "x=\$(cat ${F}); echo \$x"`, `bash -c "n=\$(wc -l < ${F}); echo \$n"`
(the third, `ssh h "cd ${DIR} && ls \$(pwd)"`, was already allowed). The three r10 pinned armed refusals keep their
codes (`sed -i '' 's/$(/x/' f` R6_NOT_A_PLAIN_LAUNCH…, `echo "${y:-it's}"` R6_TOKENIZE_FAILED, `echo ${x:-{a}b}`
R6_EXPANSION). `_R11_HONEST_OUT` (23 rows: the reviewer's not already pinned + C10's — `$((16#ff))`, `$(([##16]255))`,
`(( "$n" > 3 ))`, `echo $(( "1" + 1 ))`, `case "$x" in a) (( n = 1 << 2 ));; esac`, `echo "${x:-{a}b}" "$y"`,
`case "$x" in (a|b) …`, `arr=(a b # comment⏎c)`, `f() { … }`, Python in a quoted here-document with `print((…))` and
`(1 << 2)`, …) stays out of scope.

**New pinned armed over-refusals** (`test_r11_known_over_refusals_are_pinned`; armed only):
`(( "${n}" > 3 ))` (braces in an arithmetic dq span, R6_EXPANSION); `out=$((cd a && make) 2>&1)` (`$((` not ending `))`,
R6_EXPANSION); `case "$x" in (a) (( n = 1 << 2 ));; esac` (a `((` after `(pattern)` holding `<<`, R6_HEREDOC);
`x=$(echo (a # it is) ok)` (an uncertain-group comment region holding a paren inside `$(…)`).

## Scope differential (r10 → r11)

136 326 commands: 111 326 distinct string constants of every `tests/*.py` at 8cc4ce4ca + 25 000 random
quote/bracket/construct/arithmetic texts (seed 20261112), pure functions of both files:
**gained 1 780 (0 real constants; all random)**; **lost 15, all random token soup; none runs anything in sealed zsh or
bash** (all are syntax errors). Each loss is a model correction required by the brief: 12 hold `"…${x:-{}…` that r10
failed closed on under its wrong counted-brace model in double quotes (rule B — the reviewer's honest
`echo "${CONFIG:-{}}"` needs the measured first-`}` model), 3 hold `<<` inside `$((…))` that r10 read as an
unterminated here-document (rule A). Refusal codes: deny → allow on exactly those 15 (out of scope ⇒ admitted).
On the post-r11 test file the extra differences are r11's own new test strings (escape rows, fuzz templates) and the
four intended honest losses (the three `\$(…${F}…)` forms, `echo "${x:-{a}b}" "$y"`).

## Fuzz (sealed ground truth: every out-of-scope candidate run in zsh AND bash)

| Generator (committed in `tests/`, or `/tmp` harness) | Candidates | r10 out / escapes | r11 out / shell runs / escapes |
|---|---|---|---|
| **Committed structured** `_r11_fuzz_candidates` (35 glue × 99 contexts × 11 prefixes × 18 suffixes), default seed 20261113 | 3 000 | 774 / **354** | 26 / 52 / **0** |
| Committed structured, seeds 1, 2, 3 (`MASTERMIND_GUARD_FUZZ_N=20000 …_SEED=n`) | 3 × 20 000 | — | 191, 190, 179 / 1 120 / **0** |
| **Committed mutations** `_r11_mutations` (1–3 inserts/deletes of 44 structure tokens on all 45 r11 + 15 r10 rows), default seed 20261114 | 800 | — | (test asserts 0) |
| Mutations, seeds 8, 9 (≤ 3 edits), 10 (≤ 6 edits) on the final code | 3 × 20 000 | seed 3: 13 075 / **2 837** | 2 956, 3 062, 3 824 / 19 684 / **0** |
| Token soup (46 pieces, 3–12 per text), seed 44 | 6 000 | — | 3 988 / 7 976 / **0** |
| Reviewer's `/tmp/rvh/fuzz.py` (12 glue × 32 prefixes × 23 suffixes) | 8 832 | (REVIEW6: 228+) | 27 / 54 / **0** |
| Liveness: in-scope candidates of the committed generator that RUN a wrapper | 200 sampled | — | 95 / 200 (≈ 47 %) |

Totals on the final code: **137 832 candidates, 28 886 sealed shell runs, 0 escapes.** The committed tests run the
default seeds in ≈ 2.5 s (structured) and ≈ 3.7 s (mutations); larger runs are opt-in via the environment variables.

During the lane the mutation fuzz found 21 r11-intermediate escapes (19 + 2) in five families — a second `#` in the
dual-read region, `$\⏎(`, case pattern position across `;`/newline, a glob group glued to a here-document delimiter,
`[[ =~ ⏎(…) ]]`; each family is fixed (rules D, E) and represented by a row above. The reviewer's 228-escape family
(`/tmp/rvh/fuzz.py`, 8 832 candidates) → **27 out of scope, 54 shell runs, 0 escapes**.

## Budgets — every row at exactly 262 144 chars, real hook command line (`python3` 3.14.7), r10 → r11

Armed; bound rows through the owner-channel shim. Test threshold 4 s. One run each, M2.

| Rows | r10 s | r11 s | verdicts |
|---|---|---|---|
| 23 r8 rows (C6) | — | 0.09–0.96 | unchanged |
| 15 r9 rows (C8) | — | 0.21–0.96 | unchanged |
| 20 r10 rows (C9) | worst 1.10 | 0.13–1.12 (`r10-assign-cmdsub-run-no-wrapper` 1.09 → 1.12) | unchanged |
| `r11-dparen-comment-glue-shift-lines` | 0.27 allow | 0.27 | deny (R6_GROUPING, R6_HEREDOC …) |
| `r11-dq-brace-glue-run` | 0.94 allow | 0.88 | deny R6_TOKENIZE_FAILED |
| `r11-eval-dq-glue-fragments` | 0.50 allow | 0.56 | deny R6_COMMAND_SUBSTITUTION … |
| `r11-argument-group-glue-lines` | 0.51 allow | 0.65 | deny R6_GROUPING … |
| `r11-arith-long-no-wrapper` (one 262 K `$((…))`) | 0.47 | 0.41 | allow |
| `r11-dparen-shift-lines-no-wrapper` | 0.27 | 0.27 | allow |
| `r11-dollar-arith-cmdsub-no-wrapper` | 0.66 | 0.64 | allow |
| `r11-for-arith-no-wrapper` | 0.47 | 0.47 | allow |
| `r11-dq-brace-no-wrapper` | 1.16 | 1.22 | allow |
| `r11-dq-word-fragments-no-wrapper` (one 262 K dq word) | 0.52 | 0.63 | allow |
| `r11-deferred-joined-no-wrapper` (one 262 K `bash -c "…\$(…${F})…"`) | 0.57 deny | 0.83 | **allow** (MINOR) |
| `r11-argument-group-comment-lines-no-wrapper` | 0.51 | 0.58 | allow |
| `r11-case-pattern-groups-no-wrapper` | 0.79 | 0.79 | allow |
| `r11-case-terminators-no-wrapper` | 0.73 | 0.74 | allow |
| `r11-arith-base-no-wrapper` | 0.73 | 0.74 | allow |
| `r11-uncertain-dparen-no-wrapper` | 0.73 | 0.72 | allow |
| `r11-dq-param-cmdsub-no-wrapper` (the reviewer's NIT row) | 1.63 | 1.65–1.67 | allow |
| `r11-continuation-dq-param-cmdsub-no-wrapper` (rule E: two lexer passes) | 1.43 | **1.78** | allow |
| `r11-bound-launch-quoted-arith-args` (bound) | 0.26 | 0.25 | allow |

**True worst r11: 1.78 s** (`"${x:-$(a)}" \⏎` × N — the continuation second pass); without continuations 1.67 s
(`"${x:-$(a)}" ` × N, r10 1.63 s — the C9 ledger's "worst 1.10 s" was understated, as the reviewer said). In-process
(python 3.12) the r11 reading alone is ≤ 0.39 s and the full scope reading ≤ 1.45 s on 22 adversarial units. Scan
bounds added: an arithmetic context is one pass; fragment judging is linear in the word's items (two passes); the
whole-word deferred re-read replaces r10's per-run re-reads (≤ one re-read per nesting level, depth cap 9); a dual-read
comment region is read once (its own `#` literal, so it does not nest); rule E doubles the lexer reading only when the
text holds `\⏎`.

## Known limits (not claimed closed)

1. **Model scope.** Ground truth is this M2's `/bin/bash` 3.2 and `/bin/zsh` 5.9. bash ≥ 4 parses `$(…)` with a full
   parser (comments, here-documents, `case`) — closer to zsh's than 3.2's, and r11 reads `$(…)` the zsh way, but no
   other version was measured. zsh options were defaults (`zsh -f`); `EXTENDED_GLOB`, `SH_GLOB`, `KSH_ARRAYS`, bash
   `extglob` change what a `(`/`#` means and were not modelled.
2. **Computed values inside deferred text** are read as a structure-free computed item: a value that itself carries a
   quote or operator into an `eval`/`-c` script (`eval "$(printf "'")p'ool …"`) is the arbitrary-value class (like
   wholly computed words); r10's per-run re-reading caught some such cases by accident, the whole-word re-read reads
   the faithful text. The quote-deleted fragment pass and the r9 joined view still read `p'ool` → `pool`.
3. **zsh glob groups are not modelled as words**: a group glued to computed text in COMMAND position
   (`$(…)(x)ool` with a staged file) is the staged-file glob class (C9 limit 3), not this parse seam.
4. **Pinned over-refusals** (r10's three + r11's four above), and quotes in arithmetic generally (`$(( '1' ))` is an
   error in both shells anyway). An uncertain-group `#` region with a paren/quote inside a `$(…)` fails closed.
5. **Unarmed**: r11 only widens `r6_names_wrapper`; the unarmed watchdog's deny-when-named (r10 N2) therefore denies a
   few more texts IF judging exceeds the budget; no unarmed verdict otherwise changes.
6. r10/r9/r8 limits stand (C9 limits 2–6): wholly computed words; computed `/`; homoglyphs; staged files; provider-side
   environment; T3 worktree scope roots; onFailure fleet versions; watchdog absent without `setitimer`.
7. The fuzz shows absence of escapes for its generators (structured, token soup, mutations of every known escape) — not
   a proof of closure. Each fix round so far has been followed by new seams from a different angle; a fresh distinct
   re-review should attack rule D (uncertain parentheses) and rule A's fail-closed boundary first.

## Tests and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash\|provider_orchestrator_policy" tests/)
  → 1532 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed  (152.9 s)
    (C9: 1420 passed → +112 new, 0 changed; the d8 identity scan in test_ceo_submit_armed_composition.py green)

tests/test_provider_orchestrator_policy.py → 1026 collected, all passing (914 pre-existing, unchanged + 112 r11)
git diff tests/ → 574 insertions, 0 deletions (no existing assertion touched; append-only)
```

New tests (112 collected): escape table coverage 1 (asserts all 26 REVIEW6 shapes verbatim, N5 8 / N5b 2 / N6 12 /
N7 4); escapes judged and refused 45 (in process, bound + unbound, R6_ codes, gate unreached, no budget denial);
lexer-reading-alone fail-before 1; real hook command line 12 (6 rows × bound/unbound); sealed ground truth 1 (70 shell
runs over 45 rows: each row's listed shells RUN a fake wrapper); honest-out 23; escaped `\$(` admitted armed 2;
whole-word deferred re-read 1; pinned over-refusals 4; structured fuzz 1 (3 000 candidates, sealed, 0 escapes,
liveness ≥ 20 % asserted); mutation fuzz 1 (800 mutations, sealed, 0 escapes); budget rows 19; armed budget-DENY
stdout sha256 1. r10's tests (N1 rows, honest forms, pinned refusals, depth boundary, union property, budget rows,
N2 watchdog) are unchanged and green.

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL): rules A–E (both scope directions, the four new pinned
  over-refusals, the 16 random scope losses), the committed fuzz harness and its seeds.
- Owner decisions carried: N3 class (C9), limit 3 (zsh alternation globs, C9), and limit 1 above (other shell versions /
  options).
