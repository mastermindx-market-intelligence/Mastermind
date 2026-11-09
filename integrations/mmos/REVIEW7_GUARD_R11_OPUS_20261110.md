# Distinct re-check #7 — guard r11 delta (`8cc4ce4ca..9524fc2dd`, merged `13177c94a`)

Reviewer: Claude Opus 5.5, READ_ONLY, distinct from the r11 author (C10). Technical assessment, not a GitHub approval.
**Overall NEEDS_REWORK. The #2329 guard row cannot be called REVIEWED at source level, even under the documented limits.**

| Item | Verdict | Evidence |
|---|---|---|
| N5 arithmetic | FIXED_CONFIRMED | 46 targeted probes, 0 escapes |
| N6 `${…}` | FIXED_CONFIRMED | first-`}` rule inside double quotes matches both shells on 21 forms; the 15 lost-scope commands run nothing (30 sealed runs) |
| N7 fragments + MINOR | FIXED_CONFIRMED | 39 probes, 0 escapes; escaped `\$(` forms allowed |
| N8 glob groups | **PARTIAL** | 4 of 45 glob probes escape, plus two new families |
| continuations | FIXED_CONFIRMED | 26 probes, 0 escapes |

All 45 r11 rows deny bound/unbound (225 CLI runs), gate not reached, sealed ground truth matches the ledger (90 runs).
Scope differential reproduced (136,326 commands; 15 lost, none runs anything). Committed fuzz at N=20,000 (seeds 5/6,
mutations 11/12): 0 escapes. Reviewer's targeted generator: 12,000 candidates → **275 escapes**, all in the two new families
(their prefix contexts are absent from the committed generator). Honest generator: r11 leaves 5.03% in scope (r10 9.92%), 0
new over-refusals; 76 honest CLI forms: only the 3 intended deny→allow and 3 pinned refusals changed. Budgets at 262,144:
UNKNOWN (not re-measured; the committed 19 rows pass under 4 s). Hard constraints hold (guard, tests, ledger, REVIEW6 only;
0 test lines deleted; d8 green). pytest 1347 passed.

## New findings (zsh; both already present in r10)
- **F1 MAJOR** — the scanner's "command position" model is too narrow: zsh accepts reserved words / compound commands after
  an fd-number redirection (`2>…`, `2>&1`, `3<…`), after `repeat N` and `coproc`, after the short forms `for x (…)` and
  `if [[ … ]]`, and in a case arm following `(pattern)`; `[[` is not recognised; a `case` inside `$(…)` is not recognised
  (its pattern `)` ends the substitution early, bypassing the fail-closed rule); a case pattern after `in⏎` is read as a
  subshell (`finish()` ~:1673–1697; newline reset ~:1705; `_R10_KEEP_COMMAND_POSITION` :1375).
- **F2 MAJOR** — `=(…)` process substitution is read as an uncertain glob group; a `case` inside it throws off the paren
  count; the unmatched top-level `)` branch (~:1815–1817) wrongly restores command position.
- 12 CLI rows: armed ALLOW bound and unbound, gate never reached; sealed zsh runs the fake wrappers (bash 3.2 never runs
  them on its own). MINOR: pinned over-refusal `out=$((cd a && make) 2>&1)` worth stating. NIT: one "new" pinned refusal
  was already refused by r10.

**Integrator decision (Fable):** after seven rounds the hidden-wrapper-name scanner is not structurally closable against
zsh's grammar. r12 (Director C11, Opus) changes the ARMED rule: a command is out of scope only when it is purely literal
(no expansion/substitution/glob/brace/continuation constructs at all) and names no wrapper; everything else must match the
admitted grammar or is denied structurally — the scanner no longer carries the armed security decision (kept as a
secondary reading and for the unarmed legacy path). Availability cost accepted: armed sessions refuse shell expansion
outside the admitted forms. F1/F2 scanner fixes also applied for the unarmed path.
