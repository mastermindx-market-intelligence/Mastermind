# Distinct re-check #8 — guard r12 delta (`13177c94a..ce39d8daf`, structural armed scope)

Reviewer: Claude Opus (native AUDIT route, `MODE: READ_ONLY`), distinct from the r12 author (Director C11) and from
re-check #7. Technical assessment only — not a GitHub approval, no source edit, no commit, no GitHub/Slack post. All
ground truth is sealed: `/usr/bin/env -i PATH=<fake-wrapper dir>:/usr/bin:/bin HOME=<tmp>` + `/bin/zsh -f -c` /
`/bin/bash --norc --noprofile -c`, stdin `/dev/null`, fakes only record argv. `/bin/zsh` 5.9, `/bin/bash` 3.2 on M2.
No real wrapper invoked. Guard copies: r12 = `ce39d8daf`, r11 = `git show 13177c94a:…`.

## VERDICT: **NEEDS_REWORK** — one BLOCKER: an armed, construct-free (by r12's own test), literally-unnamed command that the guard **ALLOWS without reaching the binding gate** runs the fake wrapper `pool run grok a /tmp grok-4` in **both** sealed zsh and bash. It is neither documented limit. Minimal fix below (validated: closes all 6 escape forms, 0 new over-refusals on the 28 honest controls).

The structural rule is a large, real improvement over r11's scanner (every prior escape family now denies; see the counts),
and B/C/D/E/F/G below all pass. But r12's central claim — "construct-free, literally-unnamed text cannot make any shell
compute a word … no line continuation (a word joined across lines)" — has a counterexample, so the #2329 row cannot yet
be called REVIEWED at source level.

## Findings

| # | Sev | Finding | Measured ground truth |
|---|---|---|---|
| 1 | **BLOCKER** | **Emergent line-continuation across adjacent quoted segments, re-parsed by a nested `bash -c`/`sh -c`/`zsh -c`.** The outer shell concatenates adjacent quoted words `"po\\"`→`po\`, `'⏎'`→literal newline, `"ol…"`→`ol…` into one argument `po\⏎ol run grok a /tmp grok-4`, which the admitted nested `-c` interpreter parses as a **line continuation** (`\⏎`→join) giving `pool run grok a /tmp grok-4`. r12 scans the **raw** bytes for an adjacent `\⏎`, which is never present (the `\` is followed by `"`, the newline sits inside the next quoted segment); and the literal check deletes `"'\` but keeps the newline as a separator, so it reads `po`\|`ol`, not `pool`. Both scope conditions pass ⇒ **out of scope ⇒ ALLOW, parse never runs.** | Through the **real hook CLI**, armed, identity present, no binding: `bash -c "po\\"'⏎'"ol run grok a /tmp grok-4"` → **ALLOW (empty stdout, gate not reached)**; the honest spelling `bash -c 'pool run grok a /tmp grok-4'` → **deny (missing binding)**. Sealed run records argv `pool \| run grok a /tmp grok-4` in **zsh AND bash**. `r12_constructs=[]`, `r12_literal_names_wrapper=False`, `_r6_lex` ok, `r6_names_wrapper=False`. Six variants all launch in both shells and all ALLOW: bash/sh/zsh `-c`, single- and double-quote backslash forms, and a `sub.sh` variant (argv `sub.sh \| glm-memory a`). |
| 2 | MINOR | **`_R12_SLOT_MODULE_RE` misses flag-combined `python3 -m` forms.** The regex `(?:^\|[^A-Za-z0-9_])m?slot(?![A-Za-z0-9_])` requires a non-alnum char before `m?slot`, so `-Bmslot`, `-sBmslot`, `-umslot`, `-qmslot`, `-Imslot`, `-OOmslot` (all valid `-B -m slot` etc.) are **not** caught. Allowed unjudged. **Not a regression** (r11 left *all* `-m slot` out of scope), but an incomplete *new* r12 check, and the ledger claims the module form closed ("r11 left `python3 -m slot glm -- run` out of scope"). Precondition: `slot.py` importable as bare module `slot` (cwd/PYTHONPATH) — the same precondition `_R12_SLOT_MODULE_RE` already assumes. | `cd <dir with slot.py> && python3 -Bmslot glm -- run`: `r12_constructs=[]`, `r12_literal_names_wrapper=False`, **r12 armed = allow**; sealed zsh/bash both import+run the module. Sibling `python3 -m slot glm -- run` → **deny**. `python3 -m slot` and `-mslot` and `pkg.slot` are correctly caught. |
| 3 | NIT | The r12 block comment's absolute claim "no line continuation (a word joined across lines)" and "every word is a fixed byte string formed from contiguous characters minus quote removal, which is exactly what the joined view reads" is false for finding #1; the joined view (`_r9_joined`, literal check) deletes `\` and keeps `⏎`, i.e. the reverse of what a nested interpreter does. The same quote-removal→adjacency gap is theoretically possible for other adjacency-detected constructs, but only `\⏎` is exploitable here (`<<`/`<N-M>` require *unquoted* operator chars; quoted `<` is a literal word char, so an emergent `<<` is a filename, not a heredoc — confirmed not exploitable). | n/a — documentation/robustness note; the fix for #1 makes the comment true. |

### Minimal prescribed fix (finding #1)

Make `r12_constructs` (and the literal-name join) see the continuation the current shell's quote-removal creates:
additionally scan a **quote-characters-deleted, backslash-preserving** view — `re.sub(r"['\"]", "", raw.replace('$"','"'))`
— for `\⏎`; treat a hit as the existing `\⏎ (line continuation)` construct (and, after joining `\⏎`→``, let the literal
name check see the resulting `pool`/`sub.sh`). This puts the nested `-c` body in scope, so `_r7_parse` runs on it and it
reaches the gate exactly like the honest spelling. The philosophy is identical to r9's `_r9_joined` for `${x:-p}"ool"`; the
only change is preserving the backslash in that one extra view so the emergent `\⏎` is visible. **Validated in-process:**
flags all 6 escape forms; **0** of the 28 honest armed controls newly flagged (including real multi-line quoted commands
`git commit -m 'line1⏎line2'`, `python3 script.py --flag "a⏎b"`). Finding #2's fix is a one-token regex broaden
(`m?slot` → allow intervening option letters, e.g. `(?:^|[^A-Za-z0-9_])-?[A-Za-z]*m?slot…` or simply also test the
option-cluster view) **or** an explicit note moving flag-combined `-m slot` into documented limit #1.

## Escape-count table (own generators, sealed zsh+bash ground truth)

| Generator / family | Candidates (that launch in sealed zsh) | r11 escapes¹ | r12 escapes² |
|---|---|---|---|
| F1/F2 prefix contexts — own generator (fd-redir, `repeat N`, `coproc`, `for x (…)`, `if [[…]]`, `case x {…}`, `(pattern)` arm, `=(…)`; hidden name via `$($(: "("; printf p)ool …)` comment) | 120 | **82** | **0** |
| Randomized construct soup, 15 000 candidates (prior-family tokens + F1/F2) | 220 | 11 | **0** |
| Structured runner-prefix + split/quoted wrapper name, construct-free, 4 077 | — | 0 | **0** |
| **Emergent line-continuation through nested `-c` (finding #1)** | 6 | 6 | **6 (BLOCKER)** |
| `python3 -m slot` flag-combined (finding #2) | demo set | (r11 allowed every `-m slot`) | 1 family (MINOR, precondition-gated) |

¹ r11 armed scope = the scanner `r6_names_wrapper`; "escape" = scanner says out-of-scope but sealed zsh launches.
² r12 armed = the structural rule; "escape" = r12 returns ALLOW (gate not reached) but sealed zsh/bash launches.

The F1/F2 and prior families are fully closed — r12 denies every construct-bearing command structurally (any `$`,`` ` ``,
glob, `(`, `{…`, `~`,`#`,`^`, `!x`, control char, `<<`, `<N-M>`, or `eval/source/alias/trap/coproc/repeat` word ⇒ in scope
⇒ only an admitted form passes). The 335-row structural-escape table and the F1/F2 scanner-fix rows pass. The only armed
holes found are #1 (BLOCKER) and #2 (MINOR), neither detected by any construct- or name-bearing signal in the raw text.

## B. Regression of prior families — PASS
All REVIEW2–7 / C5–C11 families deny armed. Own F1/F2 generator: 82 of 120 launching rows escaped r11's scanner; r12
denied all 82. Randomized 15 000-candidate soup: r11 missed 11 of 220 launching rows, r12 denied all 220. `_R12_ESCAPES`
(18 rows) and the committed 335-row structural table pass under the full `pytest` run.

## C. Honest controls / over-refusal — PASS (cost as documented)
28 honest armed controls behave as the ledger states. Every ordinary command the brief flagged is correctly handled, **not**
wrongly denied: `git commit -m "fix: pool run (see #2329)"` → allow; `rg -n 'TODO(' src`, `grep -rn 'TODO(' src`,
`cat docs/*.md`, `ls ~/notes`, `git log HEAD~1..HEAD`, `sed -n 1,5p f`, `echo hi # note`, `make … | tail` → allow; plain
`python3 /opt/mastermind/ext/slot.py glm -- run` and `bash -c '<launch>'` → **gate** (correct — they are launches needing a
binding). Over-refusals are exactly the documented set — `awk '{print $1}' f`, `(cd sub && make)`, `for f in *.py; …`,
`python3 -c '…'`, `echo "$HOME"` all DENY (construct-bearing, not an admitted read form). Availability cost, stated plainly:
armed workers lose `$VAR`/command-substitution, subshells, `for`/`while`, `awk`/`python3 -c`/`jq '…[]…'` programs, and any
quoted bracket/paren outside an admitted read head; inspection is preserved through the admitted read forms and Read/Grep/Glob,
launches through plain/by-path/nested `-c`. The 2 known limits (`printf '\\160ool…' | sh`, `echo <b64> | base64 -d | sh`) are
pinned with sealed ground truth in `test_r12_known_limits_are_pinned`. **Judgement on the pipe-to-interpreter limit:** it is the
long-standing arbitrary-process boundary (r2), correctly pinned, not introduced or worsened by r12 (r12 *narrows* it by closing
the `$(printf …)`/`$LAUNCHER` shell-substitution form armed). A general in-scope rule for an interpreter word after `|` / as
command word is unclosable within a shell-structure guard (open set: `sh/bash/zsh/perl/ruby/node/php/env/xargs/busybox …`, by
path, etc.) and would re-introduce the deny-list-over-open-grammar approach r6 abandoned. I do **not** require it before the row
is reviewed; the author already lists it as an optional follow-up. (Contrast finding #1: that is **not** an arbitrary-process
case — it is pure shell quoting with an admitted `-c` form, and `\⏎` is already in r12's own construct set.)

## D. Unarmed byte-identity — PASS
19-command sample (prior-family denials, read forms, CI-wait text, foreground/loop/background watch, `$(…)` text, F1 family,
`python3 -m slot`/`-Bmslot`) through the real hook CLI: r11 vs r12 stdout **byte-identical, 0 diffs, 0 DENY→non-DENY**. The
F1/F2 scanner fixes are a protection *gain* unarmed (no demonstrated unarmed DENY turned ALLOW); the one intended F1 change
(ledger: a heredoc-tail N2 row, no-decision→deny) is a gain, consistent with 0 deny→nondeny observed.

## E. Budget — PASS
Real hook CLI, armed, 262 144-char fills: worst construct-free `a⏎`×131072 = **1.63 s** (allow, gate not reached), `a;`×
= 1.49 s; every construct-bearing / named fill 0.24–0.39 s (deny). **No budget-DENY emitted — the 7 s watchdog never fired**;
far inside the provider 10 s timeout. `r12_constructs`/`r12_literal_names_wrapper` linear: 3.7 → 6.8 → 14.4 ms at 64K→128K→256K
(≈2× per doubling); the scanner runs only for construct-free text, as designed.

## F. Test integrity — PASS
`git diff` of the test module: **0 DENY expectations removed or weakened** (grep of removed `-` lines for `deny`: 0 hits). Every
removed assertion is an ALLOW→DENY flip. The 39 flips = 7 in-process + 32 table rows (`test_r12_armed_flips_are_exactly_
construct_bearing_refusals` asserts 39); I independently confirmed all 7 in-process flips are construct-bearing and flip
allow→deny, and that each flip is either a genuine new protection (`computed-word`/`env-word-out-of-scope` — the r2 SHELL-
substitution launch now closed armed) or an accepted over-refusal (the `…-no-wrapper` rows hold a construct but launch nothing).
No flip is a lost DENY.

## G. Identity scan + guard module — PASS
`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -p no:cacheprovider` : `tests/test_hermes_fabric_native_identity_review.py`
→ **2 passed**; `tests/test_provider_orchestrator_policy.py` → **1267 passed** (1267 collected, as expected); the two together →
**1269 passed**. All green on the committed tree (the BLOCKER is a gap in the rule, not a failing test — no committed test exercises
the cross-quoted-segment continuation).

---
One-line: **NEEDS_REWORK** — r12 structurally closes every prior family and passes B–G, but a nested `-c` body assembled into a
`\⏎` line continuation across adjacent quoted segments is a construct-free, unnamed, gate-bypassing paid launch in both shells
(finding #1, BLOCKER); apply the quote-deleted-backslash-preserving continuation scan (0 honest-control cost) and broaden the
`-m slot` regex (finding #2, MINOR), then the #2329 row is reviewable under the two documented limits.
