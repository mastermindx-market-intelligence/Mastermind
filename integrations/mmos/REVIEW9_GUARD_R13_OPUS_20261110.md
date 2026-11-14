# Distinct re-check #9 — guard r13 delta (`ce39d8daf..e6479f848`, assembled-continuation + flag-combined `-m slot`)

Reviewer: Claude Opus (native AUDIT route, `MODE: READ_ONLY`). I am distinct from Director C11 (who authored r12), from the
principal who authored r13, and from the re-check #8 reviewer. This is a technical assessment only: it is not a GitHub approval,
and I made no source edit, no commit and no GitHub or Slack post. All scratch files are under `/tmp/rv9`.

Ground truth comes only from sealed shells: `/usr/bin/env -i PATH=<fake dir>:/usr/bin:/bin HOME=<tmp>`, then
`/bin/zsh -f -c` (zsh 5.9) or `/bin/bash --norc --noprofile -c` (GNU bash 3.2.57), with stdin `/dev/null`. The fakes `pool`,
`sub.sh`, `remote_sub.sh` and `slot.py` only record argv, and a fake python `slot.py` module only writes a tag file. No real wrapper
was invoked.

Guard copies: r12 = `git show ce39d8daf:…`, r13 = `e6479f848`, which is byte-identical to the worktree. Verdicts come from two
places: the committed test module's own fixtures (`_r7_both`: armed, identity present, bound and unbound, with a gate spy), and
the real hook command line (`python3 "<guard>"`, using the owner shim when bound).

## VERDICT: **ACCEPT** — row reviewed at source level, under the documented limits

The documented limits are: arbitrary-process / pipe-to-interpreter; names that resolve to a wrapper by homoglyph, symlink, PATH
or alias; and shells as measured (zsh 5.9, bash 3.2).

r13 closes REVIEW8 #1 (BLOCKER) and #2 (MINOR) completely. No shell-quoting construction I could build makes an admitted nested
interpreter run a wrapper while r13 lets the command through without judging it. That covers any number of quote levels, the
admitted prefixes, CR/CRLF, escaped quotes and empty quote pairs. This holds by construction (argument below) and by measurement
(0 of 57 shell-grammar launches escape).

Four non-blocking items follow:
- one MINOR that sits inside documented limit #1 (`env -S`);
- one MINOR availability cost (new over-refusal shapes beyond the single pinned one);
- three NITs.

## Findings

| # | Sev | Finding | Measured ground truth |
|---|---|---|---|
| 1 | MINOR (within documented limit #1, pre-existing, not an r13 regression) | **`env -S` decodes its own escapes and feeds a nested `bash -c` a continuation.** macOS `env -S` turns `\\` into `\` and `\n` into a newline. So `env -S 'bash -c po\\\nol'` (no newline byte, no construct, no literal name) hands bash the body `po\⏎ol`, and bash joins it. The text is construct-free and literally unnamed, so the parse never runs. This is the same mechanism as the pinned `printf '\160ool…' \| sh`: a program computes the launch text from an escape language. The guard already knows `env -S` is not transparent: in scope it refuses with `R6_PREFIX_FORM` ("env -S is outside the transparent prefix grammar"). The broader limit #1 is just as reachable without tricks: `perl -e 'exec "po"."ol", "run", …'` is also construct-free, unnamed and allowed. | Sealed zsh **and** bash run the fake `pool` for `env -S 'bash -c po\\\nol\_run\_glm…'` and for the double-quoted variant. r12 and r13 armed: **allow, gate not reached**, both bound and unbound. `env -S 'pool run glm …'` (named) → deny `R6_PREFIX_FORM`. `perl -e` row: launches in both shells; r12 and r13 allow it unjudged. Optional cheap follow-up: count an `env` word with `-S`/`--split-string` (or an option cluster containing `S`) as a re-evaluating construct word, like `eval`; that puts it in scope, where `R6_PREFIX_FORM` already refuses. Or pin it beside `test_r12_known_limits_are_pinned`. |
| 2 | MINOR (availability; the trade is the documented one) | **r13's over-refusal is wider than the single pinned shape.** The quote-deleted view treats any backslash followed by quote characters and then a newline as an assembled continuation. Besides the pinned `echo 'a\'⏎echo b`, it now refuses honest commands where an escaped `\"` sits immediately before a newline inside a multi-line double-quoted argument of a head that is not an admitted read form (for example `gh pr create --body "Fixes \"x\"⏎⏎More"` or `python3 tools/report.py --msg "He said \"hi\"⏎next"`). It also refuses multi-line lists whose first command ends in a quoted `\` or `\"…\""` (`git commit -m "say \"hi\""⏎git log -1`, refused as a compound list). r12 allowed all of these. | 6 of my 31 own honest commands flip from allow to deny (`own02/03/05/06/22/30`). All 35 committed honest controls (28 from r12, 7 from r13) are unchanged. Options: (a) document and pin the escaped-dq shape next to the existing pin; the remedy text already points to `--body-file` / `-F FILE`. (b) Optional refinement, validated in-process but **not prescribed**: test `\⏎` on each level-0 lexed word value with the quotes deleted (the exact argument a nested interpreter receives, conservative for deeper levels), and fall back to the whole-text view when `_r6_lex` errors. On my set it loses **0** of the launching rows and restores **all 6** honest rows. Its cost is that scope then depends on the lexer's fidelity, which r12 deliberately avoided. That is the author's call. |
| 3 | NIT | A **raw** `\⏎` is reported twice. The raw scan reports `\⏎ (line continuation)`, then r13 appends `\⏎ (line continuation assembled by quote removal …)`, because the view check doesn't skip text the raw scan already flagged. The second description is misleading in the denial reason. | `bash -c "po\⏎ol …"` → `constructs = ['\⏎ (line continuation)', '\⏎ (… assembled by quote removal …)']`. Wording only: the verdict and gate are the same as r12. |
| 4 | NIT | `_R12_SLOT_MODULE_RE` branch `-[A-Za-z]*m` has no left boundary, so it also over-reads `--teamslot`, `-Wignoremslot` and `-Xdevmslot`, plus `-I`/`-P` clusters (which drop cwd from `sys.path`). | All are in scope and none imports `slot`: harmless over-detection (see B). |
| 5 | NIT | Pin coverage: `_R13_ESCAPES` pins zsh only in the double-quote form. A related limit instance worth noting in the ledger: `python3 -c 'import ｓｌｏｔ'` imports `slot.py` because CPython NFKC-normalises identifiers. It is unnamed and construct-free, so out of scope, and falls under the homoglyph limit plus the `python3 -c` (arbitrary-process) limit. `python3 -m ｓｌｏｔ` does **not** import. | zsh single-quote form: r13 D-/D- (structural). NFKC row: imports under CPython 3.14.7 and is out of scope in both r12 and r13. Documented-limit class; no change required. |

## Why the closure is complete for shell grammar

Without `$` or backticks (both raw constructs), every quote-removal step in bash, sh and zsh only **deletes** characters, and only
three kinds: quote delimiters, escaping backslashes, and `\⏎` pairs. So each nesting level's string is a subsequence of the
level before.

Suppose some level's string holds an adjacent `\⏎`. Then in the raw text, the only characters between the source `\` and the
source `⏎` are ones some level deleted:
- quote characters — the view deletes these too;
- escaping backslashes — the view keeps these, but they are backslashes themselves;
- an adjacent `\⏎` pair — already a raw construct.

Therefore the quote-deleted, backslash-kept view (`_r12_unquoted_view`) contains `\⏎` at **every** depth. CR and other control
characters are raw constructs. `$'…'` and `$"…"` start with `$`.

Other emergent multi-character constructs don't add a join. An emergent `<<`/`<<<` has a body that is either literal or joins only
through `\⏎`/`$`. An emergent `!x` is inert because non-interactive `-c` shells have no history expansion. An emergent `<N-M>`
matters only under zsh, and `zsh -c` is refused. Measured below.

## A. REVIEW8 #1 — closed

82 candidates; 60 of them launch a fake wrapper in sealed zsh and/or bash.

| Family (sealed: launches?) | r12 armed (bound/unbound) | r13 armed (bound/unbound) |
|---|---|---|
| The six REVIEW8 rows (bash/sh dq+sq, zsh dq, `sub.sh`) plus zsh sq — launch in both | ALLOW, gate unreached ×7 | bash/sh rows **deny at the gate** ("unaccounted descendant" bound, deny unbound); zsh rows **deny structurally** (`R12_SHELL_CONSTRUCT`+`R6_NESTED_SHELL`) |
| Unquoted `po\\'⏎'ol…` / `po\\"⏎"ol…`; `p'o'\\"'⏎'"ol` (nested quotes); two continuations in one word; `sl\\…ot.py`, `remote_su\\…b.sh` — launch | ALLOW, unjudged | deny at the gate |
| Nested double-quote continuation `bash -c "\"po\\"'⏎'"ol\" …"` — launches (**a second r12 escape REVIEW8 didn't list**) | ALLOW, unjudged | deny at the gate |
| Two levels (`bash -c '<REVIEW8 row>'`, double-quoted, `sh` sq-in-dq), the continuation **assembled only by the second quote removal** (`bash -c 'bash -c po\\"⏎"ol\ …'`, both quotings), three levels (dq-dq, sq-dq) — all launch | ALLOW, unjudged ×7 | **deny structurally** ×7 (nested shell in a nested body) |
| Admitted prefixes `env`, `nohup`, `command`, `exec`, `nice`, `/bin/bash -c`, `/usr/bin/env bash -c` — launch | ALLOW, unjudged | deny at the gate |
| `env --`, `bash -xc`, `bash -e -c`, `bash -c … x` ($0), `bash --norc -c`, `sh -c --`, `find -exec bash -c`, `xargs bash -c`, `echo … \| bash`/`\| sh` — launch | ALLOW, unjudged | deny structurally |
| `timeout 5 …` (no `timeout` binary on macOS → no launch) | ALLOW | deny at the gate |
| Raw `\⏎` in dq / sq / unquoted (shell deletes or joins) — launch | judged: bound ALLOW at the gate (an honest-equivalent launch the fixture binding authorises), unbound deny | same |
| `\r⏎`, CRLF, `\`+`\r` | deny (control character) — no launch | deny |
| `$'\n'` form | deny (`$'`) | deny |
| `zsh -c 'pool run …'` (honest) | deny `R6_NESTED_SHELL` | deny — **there is no admitted zsh form** |
| Assembled body inside admitted READ forms (`echo … > /dev/null`, `cat f \| grep`, `rg -n`, `sed -n 1p`, `git log --grep`, `ls`, `git commit -m`) | ALLOW | in scope, **admitted, ALLOW — none launches** in either shell |
| Honest launch plus a hidden assembled second launch (`;`, `&&`) | deny (named) | deny (compound list) |
| Assembled mode/token (`pool r…un gr…ok`), bound token split (`g…lm`) | deny at the gate | deny at the gate (cannot attribute) |
| Identity value split (`POOL_TASK_CLASS=co…de pool run glm …`) | bound ALLOW at the gate | bound ALLOW at the gate — the parse reads `code`, the shell passes `code`, and the binding authorises exactly this launch: correctly judged |
| `env -S` with `\\` + `\n` escapes feeding `bash -c` — launches | ALLOW, unjudged | **ALLOW, unjudged** (finding #1: limit #1) |
| `perl -e 'exec "po"."ol", …'` — launches | ALLOW, unjudged | ALLOW, unjudged (limit #1, reference) |

**Escape counts** ("unjudged launch" means the sealed shell launches while armed r13 ALLOWs with the gate unreached):

| Generator | Launching candidates | r12 unjudged | r13 unjudged |
|---|---|---|---|
| Shell-quoting families above (all levels, prefixes, read forms, mixed) | 57 | 38 | **0** |
| Arbitrary-process programs (`env -S` ×2, `perl -e`) | 3 | 3 | 3 (documented limit #1) |
| **Total** | 60 | 41 | 3 |

Of the 57 judged r13 shell-grammar launches: 29 reached the binding gate (7 bound ALLOW: honest-equivalent launches matching the
binding) and 28 were refused structurally.

**New blind spot from the `\⏎` join in the literal check: none.** The join only fires when `\⏎` is in the view, and then
`r12_constructs` is already non-empty. So scope doesn't change; `named` only selects the reason wording. No in-scope row was
"allowed with no launch" while a shell launched. Unarmed paths never reach the r13 code (see D).

## B. REVIEW8 #2 — closed

I fuzzed 2,131 `python3` command lines, each run sealed (`env -i`, `zsh -f`) under **CPython 3.9.6** (`/usr/bin/python3`) and
**3.14.7** (Homebrew), with cwd holding a fake `slot.py` that only writes a tag file. The set covers:
- every option cluster of 0–2 flags from `bBdEiOqsSuvxIPR`, in the `-…mslot`, `-…m slot` and `-… -mslot` forms;
- 500 random 3-flag clusters;
- 400 random clusters of 4–10 flags;
- `-W`/`-X`/`-c` consuming the cluster;
- 64 hand forms: `-m=slot`, `-W ignore -mslot`, `--check-hash-based-pycs never -m slot`, `-cimport\ slot`, `-c 'import os,slot'`, tab and newline separators, `-m runpy slot`, `-m slot.__init__`, `-m 'sl''ot'`, `-m s\lot`, `-mSLOT`, `-- -mslot`, `-m -- slot`, `.slot`, repeated `-m`, `-I`/`-P`/`-V`/`-h`, and others.

| | Count |
|---|---|
| Import `slot` under at least one CPython | 1,391 (the two versions agree on every candidate) |
| **r13 out of scope while importing** | **0** |
| r12 out of scope while importing | 666 (e.g. `-BBOmslot`, `-BEdmslot`, `-BExBExdBmslot`) |
| r13 in scope without importing (over-detection) | 740, of which 457 are new vs r12. All are `-I`/`-P` clusters (cwd dropped), `-W…m`/`-X…m`/`-c…m` (the `m` is consumed as a value) or `-V`/`-h` — harmless |

The regex is sound for CPython's cluster grammar: option letters only, and `W`/`X`/`c`/`m` consume the rest of the cluster. It is
linear: 10–18 ms at 262,144 characters on `-m…m`, `-B…B`, `(-aaaaaaa)*`, `(-m)*`, `( mslo)*` and `(-Bmslo)*`.

## C. Over-refusal (r12 vs r13, armed, bound and unbound)

- **28 r12 honest controls + 7 r13 honest controls: identical** verdicts and gate behaviour (launch rows: bound ALLOW at the gate, unbound "missing binding"; the rest ALLOW with the gate unreached).
- My 31 extra honest worker commands, including multi-line commit messages with Windows paths and regexes, `\\` in rg/grep/sed/tr, pipelines with newlines after `|`, `\t` in quotes, `ls \⏎ -la`, `git commit -m 'line… \\ …⏎…'`, `Revert "x"` messages, `don't`/`won't` lines and `npm --define "X=\"y\""`: **25 unchanged, 6 newly refused**:

| Newly refused (r12 ALLOW → r13 DENY, structural) | Shape | Judgement |
|---|---|---|
| `gh pr create --title t --body "Fixes \"x\"⏎⏎More text"` | `\"` immediately before a newline inside dq; head not an admitted read form | accepted cost; use `--body-file`; **not pinned** (finding #2) |
| `python3 tools/report.py --msg "He said \"hi\"⏎next line"` | same | accepted cost; not pinned |
| `printf '%s\n' 'C:\dir\'⏎ls` | quoted trailing `\` then a newline | the pinned shape (variant) |
| `echo "C:\\temp\\"⏎echo b` | dq trailing escaped `\` then a newline | the pinned shape (variant) |
| `echo 'a\'⏎echo b` | — | **the pinned accepted over-refusal** |
| `git commit -m "say \"hi\""⏎git log -1` | two admitted read forms, the first ending in `\"…\""` | accepted cost (an in-scope list); not pinned |

No row newly refused by r13 is a launch. `git commit -m "Fix \"quoted\"⏎⏎Body"` on its own stays ALLOW (in scope, admitted).

## D. Unarmed byte-identity — PASS

The r13 code (`_r12_unquoted_view`, the r13 branch of `r12_constructs`, the r13 plain view, `_R12_SLOT_MODULE_RE`) is reached
only from `_guard_armed_launch`. The only other caller, `r12_armed_in_scope`, has no in-guard caller and is used by tests only.
`_guard_armed_launch` is called only under `shared_placement_armed()`.

Through the real hook CLI, unarmed, I ran 25 commands with the identity present and the same 25 with it absent (50 runs) on both
r12 and r13. The commands were: the six REVIEW8 rows and a two-level row, raw `\⏎`, plain and identity launches, `-Bmslot`/`-m slot`/
`-sBmslot`, `p${x}ool`, `p*l`, CI watch at `--interval 5`/`60`, `--watch`, a poll loop, a `$(cat <<EOF` commit, both over-refusal
shapes, read forms, `env -S`, `$(printf …)`, `printf … | sh`.

Result: **0 stdout or exit-code diffs, 0 deny → non-deny.**

## E. Budget — PASS

Real hook CLI, armed, at **262,144 characters**, bound (owner shim) and unbound. Times are wall-clock seconds.

| Fill | Bound | Unbound |
|---|---|---|
| `"a\\"'⏎'`× | 0.18 deny | 0.20 deny |
| `x\⏎`× | 0.15 deny | 0.17 deny |
| `'\'⏎`× | 0.47 deny | 0.49 deny |
| `'\'"⏎"`× | 0.18 deny | 0.20 deny |
| Named join `po\\"'⏎'"ol `× | 0.16 | 0.18 |
| `bash -c "` + `x\\"'⏎'"`× (+ launch tail) | 0.16–0.17 | 0.18 |
| `python3 -B…Bmslot` | 0.09 | 0.11 |
| `-Bm`× | 0.14 allow | 0.17 allow |
| Construct-free `"\\" `× / `\"`× | 0.25–0.36 allow | 0.25–0.36 allow |
| `'a'"b"`× / `'\'`× | 0.18–0.23 deny (unterminated tail) | — |
| **Worst: construct-free `a⏎`× / `a;`×** | **1.19–1.23 allow** | — |

**No budget-exceeded deny; the 7 s watchdog never fired.** In process, `r12_constructs` + `r12_literal_names_wrapper` scale
linearly at 64K → 128K → 256K: `"a\\"'⏎'` 18 → 33 → 65 ms; `x\⏎` 13 → 26 → 52 ms; `'\'⏎` 17 → 35 → 76 ms; `'\'` 15 → 29 → 58 ms;
`a⏎` 25 → 50 → 96 ms.

## F. Test integrity — PASS

- `git diff --numstat` for the test module: **+216 / −0**. No assertion was removed or weakened, so 0 DENY expectations were lost. There are 28 new tests.
- **Fail-before**, measured with a scratch pytest plugin that swaps the r12 guard into `ops.executive_os.provider_orchestrator_guard` (no source edit): **19 of 28 r13 tests FAIL on r12**: 6 view/scope rows, 6 gate rows, 4 hook-CLI rows (r12 ALLOW), the over-refusal pin, and 2 slot tests. The 9 that pass on r12 are the ones that should: sealed ground truth (12 shell runs), the 7 honest controls, and linearity.
- The tests assert what the claims say:
  - the raw regex finds nothing and the `_r9_joined` view is unnamed (the pinned fail-before facts);
  - `\⏎` appears in `_r12_unquoted_view`, `r12_constructs == [_R13_ASSEMBLED_CONTINUATION]`, the name is read and the row is in scope;
  - bash/sh rows reach the gate ("unaccounted descendant" bound; missing binding or unaccounted unbound), identically with the scanner on and off;
  - the zsh row is refused structurally with `R6_NESTED_SHELL`;
  - the honest spelling is judged through the gate;
  - the hook CLI denies bound and unbound within 4 s, while the honest spelling gives bound ALLOW and unbound "missing binding";
  - sealed ground truth covers 6 rows × 2 shells = 12;
  - the 7 controls are construct-free and armed ALLOW with the gate unreached;
  - the over-refusal pin is deny with the gate unreached;
  - the slot regex is tested both positively and negatively.
- Gaps (NIT #5): the zsh single-quote form isn't pinned, and finding #2's escaped-dq shape isn't pinned.

## G. Suite — PASS

`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -p no:cacheprovider --basetemp=/tmp/rc9 tests/test_provider_orchestrator_policy.py tests/test_hermes_fabric_native_identity_review.py`
→ exit 0, **1297 passed** (1295 + 2 collected). `-k r13 -rs`: 28 passed, 0 skipped.

---
One line: **ACCEPT** — r13 makes every quote-assembled `\⏎` continuation (any depth, any admitted prefix) visible. Each such
launch now reaches the binding gate or is refused structurally (0 of 57 shell-grammar launches unjudged, against 38 on r12). The
`-m slot` cluster regex has 0 escapes over 1,391 importing CPython forms. Unarmed behaviour is byte-identical, the budget stays
linear, and the suite is green. Follow-ups, none blocking: pin or close `env -S` (#1, a documented-limit instance); pin or decide
on the escaped-dq over-refusal shape (#2); three NITs.
