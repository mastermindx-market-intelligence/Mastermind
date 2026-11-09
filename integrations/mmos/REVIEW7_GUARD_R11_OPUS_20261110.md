# Distinct re-check #7 — guard r11 delta (`8cc4ce4ca..13177c94a`, merged `13177c94a`)

Reviewer: Claude Opus 5.5, READ_ONLY, distinct from the r11 author (C10). Technical assessment, not a GitHub approval.
Recorded by Director C11 from the principal's brief, which marks it authoritative; the reviewer's own artifact, its
verbatim rows and its generator were not committed in this checkout. **Verdict at r11: N5/N6/N7 and line continuations
FIXED_CONFIRMED; N8 PARTIAL; the guard row NOT reviewed at source level.**

## Findings

| # | Sev | Finding (line refs at r11) | Measured by the reviewer |
|---|---|---|---|
| F1 | MAJOR (zsh, pre-existing in r10) | r11's "command position" model is too narrow. zsh accepts reserved words and compound commands after an fd-number redirection (`2>…`, `2>&1`, `3<…` — r11 reads the digit as the command word), after `repeat N` and `coproc`, after the short forms `for x (…)` and `if [[ … ]]`, and in a case arm following `(pattern)`. `[[` is not recognised there (a newline inside it restores command position, the next `(` is read as a CERTAIN subshell and `#` hides the rest of the line); a `case` inside `$(…)` is not recognised (its pattern `)` ends the substitution early, bypassing r10's fail-closed rule); a case pattern after `in⏎` is read as a subshell. `finish()` ~:1673–1697 (both checks require `command_position`), newline reset ~:1705, `_R10_KEEP_COMMAND_POSITION` :1375 | 12 CLI rows (F1 + F2): armed ALLOW bound and unbound, the binding gate never reached, a sealed zsh runs the fake wrapper |
| F2 | MAJOR (zsh, pre-existing) | zsh `=(…)` process substitution is read as an uncertain glob group; a `case` inside it throws the paren count off; the unmatched top-level `)` branch (~:1815–1817) wrongly restores command position | (in the 12 rows) |
| — | fuzz | the reviewer's targeted generator (prefix contexts absent from `_R11_FUZZ_PRE`) | **275 escapes** |
| — | MINOR | the pinned armed over-refusal `out=$((cd a && make) 2>&1)` is worth stating plainly | — |
| — | NIT | `x=$(echo (a # it is) ok)` was already refused by r10, not newly by r11 | — |
| — | UNVERIFIED | budgets at 262 144 were not re-measured by the reviewer (only the committed 19 rows, all under 4 s) | — |

Prescribed fixes (reviewer): recognise `case … in` and `[[` anywhere (a `case` inside any substitution fails closed;
`[[` sets `in_condition`); an all-digit word or `{name}` immediately followed by `<`/`>` is a redirection, not a command
word; after `repeat`, `coproc`, `for NAME (…)`, `if [[ … ]]` the next word may be a command word; read `=(` at a word
start like `<(` through `substitution()`; fail closed on an unmatched top-level `)` unless a case pattern is open; add
the F1/F2 prefix contexts to the committed generator.

## Principal's decision (Fable COO) — r12 STRUCTURAL rule for armed sessions

After seven distinct reviews the hidden-wrapper-name scanner keeps leaking new zsh grammar families, so the security
decision in an ARMED session (`MASTERMIND_SHARED_PLACEMENT` armed, binding present or not) must not depend on finding
hidden wrapper names: (a) a command is out of scope only if it holds no expansion or substitution construct at all
and names no wrapper (literal check, quote-joined), the tokenizer having succeeded; (b) everything else is in scope and
must match the ADMIT grammar exactly (LAUNCH / NESTED / READ with their carve-outs), otherwise DENY with the structural
code; (c) the r6–r11 scanner stays a secondary, widening-only reading and remains the unarmed mechanism (N2 behaviour
byte-identical); (d) the availability trade — armed sessions refuse every command using shell expansion outside the
admitted forms — is stated in the ledger and tests, with the reason text "armed session: shell expansion is not
admitted; use a literal command or a file argument". The F1/F2 scanner fixes are applied too.

## Director C11's r12 disposition

See `LANE_EXECUTIVE_DIRECTOR_C11.md` (the rule token by token, F1/F2 fixes, the reconstructed rows with r11 fail-before
through the real hook command line and sealed ground truth, the structural escape table, the over-refusal table, fuzz
counts, true worst budgets, limits).
