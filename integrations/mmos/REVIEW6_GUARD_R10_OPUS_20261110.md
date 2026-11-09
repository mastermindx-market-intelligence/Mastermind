# Distinct re-check #6 — guard r10 delta (`bfa233e9f..9dab2fdcb`, merged `8cc4ce4ca`)

Reviewer: Claude Opus 5.5, READ_ONLY, distinct from the r10 author (C9). Technical assessment, not a GitHub approval.
**Overall NEEDS_REWORK; N1 PARTIAL; N2 ACCEPT. The guard row is NOT yet reviewed at source level.**

Ran: pytest 1,235 passed (incl. the d8 identity scan); about 560 real-hook-CLI runs (N1 rows, seam probes, honest forms,
N2 and byte-identity checks, budgets); about 1,960 sealed shell runs (`env -i`, `zsh -f` / `bash --norc --noprofile`, fake
argv-logging wrappers only); a 55,008-command scope differential (repo `.sh`/`.md` shell blocks, random, structured):
deny→allow **0**, allow→deny 3,117 (real-corpus cases are almost all lines cut mid-construct, fail closed by design); 8,832
structured fuzz candidates, of which 875 were out of scope for r10 and 234 of those ran a fake wrapper in a sealed shell.

Confirmed fixed: all 15 N1 escapes listed in re-check #5 and the C9 ledger (r9 allowed; r10 denies bound and unbound,
binding gate not reached, each under 0.08 s; every row runs the fake wrapper in the shells the ledger names). N2 accepted:
the unarmed heredoc shape is denied at the watchdog with the r8-style missing-identity reason; CI-wait text still gets no
decision; the armed budget-DENY output is byte-identical across r8/r9/r10.

## New findings — three parser seams in the r10 scanner, each reopening the armed-unbound class
- **N5 MAJOR** (scanner comment/heredoc handling at ~:1541, ~:1552, ~:1564): r10 does not model an arithmetic context.
  Inside `((…))`, `$((…))` and `for ((…))` it treats `#` as a comment start and `<<` as a heredoc; the shells do neither, so
  a substitution placed after a `#` inside arithmetic still runs and quote parity on later lines shifts. Ten shapes (incl.
  `sub.sh`/`slot.py` twins; one zsh-only). Fix: track the arithmetic context; inside it `#` is not a comment and `<<` is not a
  heredoc, or fail closed on either.
- **N6 MAJOR** (`brace()` ~:1814–1822; resync ~:1448): the fail-closed rule for bash/zsh `${…}` end disagreements is skipped
  when a quote or construct inside the counted extent raises `_R10Stop`, and the resync then drops the word being read; also
  zsh ends `${…}` at the first `}` inside double quotes, so the double-quote model is wrong. Fuzz found 228 escapes in this
  family (incl. `env`/`exec`/backtick/`eval` wrappers and bash-only multi-line forms). Fix: once `first_close >= 0`, any
  quote or construct → `_R10Fail`; treat in-dq `${…}` as ending at the first `}` (or fail closed on a bare `{`); never
  resync silently on a `_R10Stop` raised inside a construct.
- **N7 MAJOR** (`computed()` ~:1419–1428): deferred re-reading covers only literal runs containing `$`, and runs are cut at
  each computed item, so a double-quoted `eval`/`sh -c`/`bash -c`/`zsh -fc` string that glues a construct to literal text is
  never read as a script (the single-quoted forms were fixed in r10). Fix: for a word mixing computed items with literal text
  containing separators, split at blanks/operators inside the literal parts and judge each fragment with `_r8_items_spell`.
- **MINOR (availability, armed)** (~:1425): an escaped `\$(` containing a local `${VAR}` is newly refused (the run is cut at
  `${VAR}`, leaving an unterminated `$(`); appears in a real repo script line. The N7 fragment-wise judging should fix it.
- **NIT**: ledger "worst 1.10 s" understated — one unit at 262,144 chars takes 1.63–1.67 s through the real CLI (still <2 s).

Seams that held: nested substitutions with quoted parens at depth 2–3; arithmetic with parens in strings; backticks
containing `$(`; all heredoc delimiter forms; `case` outside a substitution; quoted-bracket parameter ops; ANSI-C quoting with
brackets; comments with apostrophes; nested quotes in `bash -c`; carriage returns. Honest forms (author's 20 + 10 more incl.
commit heredocs with apostrophes and parens) keep r9 verdicts; the three pinned armed refusals are acceptable fail-closed.
Budgets: 58 rows at 262,144 through the real CLI, worst 1.09 s on the r10 rows; 64K→256K sweep linear. Hard constraints
hold (guard, tests, C9 ledger, REVIEW5 record only; policy untouched; 0 test lines deleted).

Unknown: bash 5.x / other zsh versions; the Bash tool's real zsh options from user rc files (`extendedglob` would widen the
staged-file glob class).

**Integrator disposition (Fable):** Director C10 (Opus, r11): N5 arithmetic context, N6 brace fail-closed + dq end, N7
fragment-wise judging (also closing the MINOR), committed fuzz harness, true worst budgets; fresh distinct re-check (#7) over
the 24 listed shapes + the fuzz afterwards. Until then the #2329 guard row stays NOT REVIEWED at source level — reported as
such to Hermes; r4 remains what #2329's own branch carries.
