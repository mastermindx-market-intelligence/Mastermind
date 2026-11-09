# Distinct re-check #6 — guard r10 delta (`bfa233e9f..8cc4ce4ca`)

Reviewer: Claude Opus 5.5, READ_ONLY, distinct from the r10 author (C9). Technical assessment, not a GitHub approval.
Recorded by Director C10 from the principal's brief (which marks it authoritative); the reviewer's own artifact was not
committed in this checkout. The reviewer's fuzz harness (`/tmp/rvh/fuzz.py`, 8 832 candidates) was present on this host and
was re-run read-only by C10.

**Verdict: N1 PARTIAL** (all 15 listed r10 escapes fixed; three NEW seams), **N2 ACCEPT**. Overall NEEDS_REWORK.

`A` = `run grok a /tmp grok-4`. Each shape: armed guard ALLOWS bound AND unbound via the real hook CLI; sealed zsh/bash
RUN the fake wrapper.

| # | Sev | Finding | Shapes | Prescribed fix |
|---|---|---|---|---|
| N5 | MAJOR | `:1541` `#` read as a comment; `:1552`/`:1564` `((`, `<<`: r10 does not model arithmetic — inside `((…))`, `$((…))`, `for ((…))` it treats `#` as a comment start (neither shell does; the hidden `$(…)` still runs during expansion) and `<<` as a heredoc (shifts quote parity on following lines) | `(( 1 # $($(: "("; printf p)ool A) ))`; `(( #x + $(…N1…) ))`; `x=a; echo $((#x + $(…N1…)⏎))`; `echo $(( 1 # $(…)⏎))`; the `sub.sh`/`slot.py` twins; `(( x = 1 )) && (( 1 # $($(: \(; printf p)ool A) ))`; `for (( i=0 # $(…); …))` (zsh only). **N5b**: `(( y = 1 << 2 ))⏎echo "⏎2⏎"; $(: "("; printf p)ool A #"` + a `for ((…))` twin | track an arithmetic context (`$((`, a `((` in command position, `for ((`); inside it `#` is not a comment and `<<` is not a heredoc — or fail closed on either |
| N6 | MAJOR | `:1814–1822` quotes/constructs inside `brace()`; `:1448` resync: the fail-closed rule for bash/zsh `${…}` disagreements is skipped whenever a quote or construct inside the counted extent raises `_R10Stop`; the resync then drops the word being read. Also measured: zsh ends `${…}` at the FIRST `}` inside double quotes (`"[${x:-{}]"` prints `[{]` in both shells) — the dq model is wrong. Fuzz: 228 escapes in this family | `x=p; "${x:-{}"ool A`; `x=s; "${x:-{}"ub.sh glm-memory a`; `"${x-{}"ool`; `"${x#{}"ool`; `env`/`exec`/backtick/`eval '…'` wrappers; bash-only `x=p; ${x:-{}ool A⏎: "` (also with `#"`, `` # ` ``, `: '`) | in `brace()`, once `first_close >= 0`, any quote or construct → `_R10Fail`; treat in-dq `${…}` as ending at the first `}` (or fail closed on a bare `{`); never resync silently on a `_R10Stop` raised inside a construct — turn it into `_R10Fail` in `dollar()` |
| N7 | MAJOR | `:1419–1428` `computed()` flushes the deferred run: deferred re-reading covers only literal runs containing `$`, and runs are cut at each computed item, so a double-quoted `eval`/`sh -c` string gluing a construct to literal text is never read as a script (rows 8/9 fixed only for single quotes) | `eval "$(: "("; printf p)ool A"`; `bash -c "$(: "("; printf p)ool A"`; `sh -c "$(: \(; printf p)ool A"`; `zsh -fc "$(: "("; printf s)ub.sh glm-memory a"` | for a word mixing computed items with literal text containing separators, split the items at blanks/operators inside the literal parts and run `_r8_items_spell` on each fragment |
| — | MINOR (availability, armed) | `:1425`: an escaped `\$(` containing a local `${VAR}` is newly refused (cutting the run at `${VAR}` leaves an unterminated `$(` → fail closed) | `ssh h "x=\$(cat ${F}); echo \$x"`, `bash -c "n=\$(wc -l < ${F}); echo \$n"` (appears in a real repo script line) | the N7 fragment-wise judging should fix this too; add it to the honest set |
| — | NIT | ledger "worst 1.10 s" understated — `"${x:-$(a)}" ` at 262 144 takes 1.63–1.67 s (still < 2 s) | — | record true worst cases |

**Held (keep):** nested `$(…)` with quoted `)` at depth 2–3; `$((…))` with parens in strings; backticks containing `$(`;
heredocs `<<"E"`, `<<-E`+tabs, `<<-'E'`, unquoted; `case` outside a substitution; `${x#"("}`, `${x%")"}`, `${x#"}"}`;
`$'…'` with brackets and `\'`; comments with `it's (`; `bash -c` nested quotes; CR as part of a word. Honest forms (the
author's 20 + the reviewer's 10, incl. commit heredocs with apostrophes and `(`, `(( n = 1 << 2 ))⏎…`) must keep their
verdicts; the three pinned armed refusals (`sed -i '' 's/$(/x/' f`, `echo "${y:-it's}"`, `echo ${x:-{a}b}`) stay acceptable.

**N2 ACCEPT** (keep byte-identical): unarmed deny-when-named at the watchdog; armed budget-DENY stdout sha256
`9c651f8f3ce0b6ff…` must remain identical.

**Integrator disposition (Fable):** Director C10 (Opus, r11, branch `t3/guard-r11-arith-brace-fragments`): N5/N5b/N6/N7
fixes, MINOR into the honest set, NIT into the ledger, a committed fuzz test; fresh distinct re-check afterwards.

## Director C10's r11 disposition

See `LANE_EXECUTIVE_DIRECTOR_C10.md` (finding → fix → test, the rules, ground truth, fuzz counts, budgets, limits).
