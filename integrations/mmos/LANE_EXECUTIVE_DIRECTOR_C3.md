# Lane: Director C3 — guard r6, claim namespace, lease join (2026-11-09)

Branch `t3/guard-r6-claim-namespace`, created from `t3/t3-hermes-restart-recovery`
at `f6ed10a32` (the distinct review head). Implementation by Claude Opus 5.5
(native ORCHESTRATION route) answering `REVIEW_C_E_OPUS_20261109.md` findings
A1 1–4, A2 6, A3 7. No push, no PR, no other worktree, `~/Mastermind` or
`~/.hermes` touched; nothing started, stopped or bound. This is SELF_REVIEWED
work; the review row asks for a fresh distinct re-review of this delta.

## Commits

| Commit | Content |
|---|---|
| `f9cc4f2f6` | Guard r6 ADMIT rule + r6 test block + 11 justified test updates |
| `c3ae1caeb` | Claim join `caller_namespace` fix (A2) + lease join refusals (A3) + tests |
| (this file) | Ledger |

Files: `ops/executive_os/provider_orchestrator_guard.py`,
`tests/test_provider_orchestrator_policy.py`, `control_plane/executive_runtime.py`
(only `_join_native_runtime_binding` + its docstring), `control_plane/workspace_lease.py`
(only `attach_workspace_lease`), `tests/test_executive_claim_job_placement_authority.py`,
`tests/test_workspace_lease.py`. NOT touched: `control_plane/t3_execution_adapter.py`
(Director A3), `complete_attempt`/terminal paths (Director C2),
`config/executive_worker_routes.json`, `worker_adapter.py`, any pin file, `src-tauri`, React.

## Finding → fix → test

| # | Sev | Finding (review) | Fix | Tests |
|---|---|---|---|---|
| 1 | BLOCKER | Interpreter check saw only the first word; `env/sudo/nice/timeout/exec/uv run` in front hid it (6 r4 regressions); `R\|Rscript` dead after lowercasing; unlisted interpreters allowed | Rule INVERTED (r6 ADMIT rule, below). No interpreter or runner list exists any more; an unlisted interpreter/runner is simply not an admitted form. The r5 scanner, `_INTERPRETER_HEAD_RE` (incl. the dead `R\|Rscript`), `_ALWAYS_INLINE_HEAD_RE`, `_SHELL_FEED_RE` and `_deny_structurally_unobservable` are deleted | Table rows 3–7, 16–18, 23–25, 64–73 (REG rows 67–72); `test_r6_admit_rule_refuses_everything_outside_the_closed_grammar` (guile, elixir, rg --pre, less, python3 -u, python3 other.py); `test_r6_dead_interpreter_lists_are_gone` |
| 2 | MAJOR | M-A not closed: `f() if/case`, `builtin trap`, `alias`, `$C;$C`, `"${a[@]}"` twice, hyperfine, git bisect run, entr, launchctl, crontab, zsh `repeat`/short `for`, fish/tcsh/busybox loops | Every shape outside the closed grammar is refused: list operators/newlines (`R6_COMPOUND_LIST`), `(`/`)` (`R6_GROUPING`), reserved words incl. zsh/csh `repeat`/`foreach` (`R6_KEYWORD`), `alias`/`trap`/`builtin`/… in command position (`R6_ENV_BUILTIN`), any `$`-expansion (`R6_EXPANSION`), any non-wrapper command word (`R6_NOT_A_PLAIN_LAUNCH`), non-inspector pipes (`R6_PIPELINE`) | Table MULT rows 43–66, 73 |
| 3 | MAJOR | M-B not closed: nested bodies scanned only for exactly `-c`; `builtin eval`, `if :; then eval`, `builtin source`, `command .`, `if source`; `ZDOTDIR=… zsh -c` | NESTED form admits only `bash`/`sh` with exactly `-c`, exactly one literal body, nothing after it, the body itself ONE plain launch (rule applied once, no deeper nesting), and refuses if the session sets `BASH_ENV`/`ENV`. Every other shell/flag is `R6_NESTED_SHELL`; eval/source/`.` are refused wherever they sit; only `POOL_ORCHESTRATOR_ID/POOL_PARENT_RUN_ID/POOL_TASK_CLASS` assignments are admitted (ZDOTDIR, BASH_ENV, PATH, LD_*/DYLD_*, BASH_FUNC_* … are `R6_ASSIGNMENT`, "unobservable launch environment") | Table ID rows 74–82, r5-deny rows 13–15, 20–21, 26–29; refusal tests (`bash -c` nested twice, `arg0`, `--`, inspector body, computed body, `PATH=`, `FOO=`, `BASH_FUNC_`, `+=`, `env -u`); `test_r6_nested_shell_refused_when_the_session_sets_bash_env` |
| 4 | Note | No-wrapper early return: `${p}ol run`, `$'\x70ool' run` launch with zero binding check (arbitrary-process limit) | Limit kept explicit (r2), scope widened cheaply: `$'…'` decoded before the name check; a word gluing a `$`-expansion/command substitution to a partial wrapper name (`${p}ol`, `"$p"ool`, `$s.sh`, `$(echo p)ool`) or a glob/brace spelling ≥2 stem characters (`po?l`, `{p,}ool`, `su*.sh`) names the wrapper. A WHOLLY computed word still names nothing | Table rows 83–87 (two pinned ALLOW rows document the residue); `test_r6_scope_stays_the_documented_wrapper_name_limit`; refusal tests for `po?l`, `{p,}ool`, `"$p"ool`, `$s.sh`, `$'\160ool'` |
| 5 | MINOR | service-account identity literal in a guard docstring (d8) | Already fixed by `70dabba15` (pre-dates this lane); r6 adds no identity literal | `tests/test_ceo_submit_armed_composition.py` green in the acceptance run |
| 6 | MAJOR | `caller_namespace=T3_REQUEST_NAMESPACE` stamped at claim; adapter wraps it again | Join leaves `caller_namespace` empty; docstring rewritten (namespace story below) | `test_t3_claim_binding_and_real_adapter_agree_on_namespace_and_key[port-attests-principal\|port-without-principal]`; `test_t3_native_claim_issues_v1_1_binding_with_t3_idempotency_join` updated (T-9) |
| 7 | MINOR | `attach_workspace_lease` checked only `lease_status`: expired-active, foreign `active_assignment_refs`, silent re-attach of a different lease | Required injected `now_ms` (module convention); typed `LEASE_EXPIRED`, `LEASE_ASSIGNMENT_MISMATCH`, `LEASE_REBIND_REFUSED`; same lease idempotent | `test_workspace_lease_join_refuses_an_active_but_expired_lease`, `…_assigned_to_another_attempt`, `…_rebinding_to_a_different_lease`, `test_attach_workspace_lease_refusals_are_typed_and_pure` |
| 8 | MINOR | `quota_preview_os_current.json` local paths/aliases | Not in this lane's brief (A4 data artifact); untouched | — |

## The r6 rule (precisely)

Applies only in ARMED sessions (shared placement), before the no-launch early
return, to the raw command text (heredoc bodies included). Entry point
`r6_refusal_codes(raw)`; `[]` means admitted or out of scope.

**Scope.** `r6_names_wrapper(raw)`: true if (a) the quote/backslash-stripped,
continuation-joined text with every `$'…'` decoded matches the r4 wrapper-name
regex (`pool`, `sub.sh`, `remote_sub.sh`, `slot.py`, any path prefix, case-insensitive);
or (b) a rough word whose basename mixes literal text with a `$`-expansion /
command substitution can spell a wrapper basename; or (c) a glob/brace word that
fnmatches a wrapper basename and spells ≥2 characters of its stem. Otherwise the
command is OUT OF SCOPE: the documented arbitrary-process limit (REVIEW_2329 r2).

**Tokenizer.** `_r6_lex`: bash-style words as typed segments (`lit`, `sq`, `dq`,
`esc` = fixed text; `param`, `arith`, `cmdsub`, `ansi`, `locale` = computed),
operators by longest match (`;;& <<< <<- &>> ;; ;& && || |& << <> <& <( >> >& >| >( &> ; & | < > ( ) \n`),
`\<newline>` joined with nothing, `#` comments only at word start, fd numbers
attached to redirections, process substitutions skipped with balanced matching.
REFUSE (`R6_TOKENIZE_FAILED`) on an unterminated quote/substitution, a
redirection without a target, or any control character other than TAB/LF.
Lexing stops at a here-document operator (the operator alone refuses).

**Admitted (and nothing else on the line):**

```
LAUNCH     ASSIGN* PREFIX* ( WRAPPER | PYTHON SLOTPATH ) ARG* REDIR*
NESTED     ASSIGN* PREFIX* ( bash | sh ) -c BODY          BODY ⊨ exactly one LAUNCH
INSPECTOR  INSP ARG* REDIR* ( '|' INSP ARG* REDIR* )*

ASSIGN    unquoted NAME=, NAME ∈ {POOL_ORCHESTRATOR_ID, POOL_PARENT_RUN_ID, POOL_TASK_CLASS},
          '=' not '+=', literal value (still held to the binding projection downstream)
PREFIX    env ASSIGN'*  (env args, same names, quoting allowed, NO options)
          | nohup | setsid | exec | command          (no options)
          | nice [-n N] | timeout DURATION           (DURATION = \d+(\.\d+)?[smhd]?)
          ≤ 4 stacked
WRAPPER   literal word, basename ∈ {pool, sub.sh, remote_sub.sh, slot.py} (case-insensitive)
PYTHON    literal word, basename python | python3 | python3.N; NO options
SLOTPATH  literal word, basename slot.py, not starting with '-'
INSP      cat head tail grep egrep fgrep wc ls stat file diff cmp shasum sha1sum
          sha256sum md5 md5sum nl od xxd echo   (no assignments/prefixes; never in a BODY)
ARG       literal word; in LAUNCH/NESTED no unquoted * ? [ { }
REDIR     < > >> >| >& <& &> &>>  with a literal target (fd digits allowed)
```

Literal = only `lit`/`sq`/`dq`/`esc` segments. Leading/trailing newlines and
comments are whitespace.

**Refused (every other command that names a wrapper), typed codes:**
`R6_COMPOUND_LIST` (`; & && || ;; ;& ;;&` or a newline between commands),
`R6_PIPELINE` (any pipe with a non-inspector stage, or any pipe in a BODY),
`R6_GROUPING` (`(`/`)`: subshells, `f()`, arrays, extglob), `R6_KEYWORD`
(reserved word in command position: `if then elif else fi for while until do done
case esac select function time coproc repeat foreach end in ! { } [[ ]]`),
`R6_ENV_BUILTIN` (`eval source . alias unalias trap builtin enable declare typeset
export readonly local set shopt unset hash let read mapfile readarray emulate setopt
unsetopt autoload zmodload functions fc bind` in command position),
`R6_COMMAND_SUBSTITUTION`, `R6_PROCESS_SUBSTITUTION`, `R6_HEREDOC` (`<<`, `<<-`,
`<<<`), `R6_EXPANSION` (any `$name`, `${…}`, `$((…))`, `$[…]`, `$'…'`, `$"…"`
outside single quotes, wrapper word included), `R6_GLOB_OR_BRACE`, `R6_ASSIGNMENT`,
`R6_PREFIX_FORM` (`env -S/-i/-u/…`, any other prefix option, `timeout` without
one literal DURATION, >4 prefixes), `R6_REDIRECTION` (`<>`), `R6_NOT_A_PLAIN_LAUNCH`
(command word is not WRAPPER/PYTHON-slot.py/bash|sh/INSP, or is computed/a pattern,
or assignment-only), `R6_NESTED_SHELL` (other shells — zsh, dash, ksh, mksh, fish,
tcsh, csh, pwsh, … — any flag other than exactly `-c`, extra words, nested-in-nested,
session `BASH_ENV`/`ENV`). The BODY's own codes are merged into the refusal.
`R6_DEFERRED_EXPANSION` (a `$`/backtick inside single quotes) is advisory: it
explains a refusal and never refuses alone.

The deny reason is one message: header `unobservable launch … (r6 admit rule;
refusal codes: …)`, one clause per code, and the remedy (run the launch as a
plain command). What r6 admits still goes through the unchanged
binding gate: missing binding, receipt channel/integrity, stale fence/expiry,
projection equality of every identity assignment, token equality, one launch per
binding, and the r4 eval/loop/batch regexes as defence in depth
(`test_r6_admitted_launch_still_reaches_every_binding_check`).

**What the rule guarantees, and only that.** In an armed session, a single
Bash-tool command whose text names a wrapper (as scoped above) can reach the
shell only if it is one of the three forms. Those forms contain no shell construct
that can repeat, defer or background a command, redefine a name, or compute a
command word or argument. Where the wrapper names itself, every admitted launch
is a lexically visible invocation that the binding gate judges. This is a
fence over command TEXT. It is not "structurally closed" against a hostile
principal (see Known limits).

## Adversarial-shape table (all rows)

Concrete commands are in `_R6_TABLE` (`tests/test_provider_orchestrator_policy.py`).
The review recorded row NAMES, not command text, so each command is rebuilt from
the name and description. `L` = faithful identity prefix + `pool run glm a /tmp glm-5.3`.
r5 = the guard at `f6ed10a32`; r6 = this branch. Both judged by each module's
real `guard_bash` under the same armed fixture (faithful binding, owner-channel
receipt, inherited projected identity).

| # | shape | class | r5 | r6 | expected | r6 codes |
|---|---|---|---|---|---|---|
| 1 | `xargs-sh-c` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 2 | `find-exec-sh-c` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 3 | `awk-BEGIN-system` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 4 | `perl-e` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 5 | `ruby-e` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 6 | `node-e` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 7 | `python3-m` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 8 | `indirection` | r5-deny | DENY | DENY | DENY | R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 9 | `eval-cmdsubst` | r5-deny | DENY | DENY | DENY | R6_COMMAND_SUBSTITUTION, R6_ENV_BUILTIN |
| 10 | `here-string-python` | r5-deny | DENY | DENY | DENY | R6_HEREDOC, R6_NOT_A_PLAIN_LAUNCH |
| 11 | `here-string-bash` | r5-deny | DENY | DENY | DENY | R6_HEREDOC, R6_NESTED_SHELL |
| 12 | `procsubst-bash` | r5-deny | DENY | DENY | DENY | R6_PROCESS_SUBSTITUTION, R6_NESTED_SHELL |
| 13 | `bash-lc-eval-split` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_ASSIGNMENT, R6_NESTED_SHELL, R6_EXPANSION, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 14 | `env-bash-c-eval-split` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_ASSIGNMENT, R6_EXPANSION, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 15 | `sudo-bash-c-eval` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| 16 | `osascript-js` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 17 | `php-r` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| 18 | `lua-e` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 19 | `expect-c` | r5-deny | ALLOW (r5 allowed this reconstruction) | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 20 | `dash-c-eval` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_NESTED_SHELL, R6_EXPANSION, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 21 | `mksh-c-eval` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_NESTED_SHELL, R6_EXPANSION, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 22 | `pwsh-c` | r5-deny | ALLOW (r5 allowed this reconstruction) | DENY | DENY | R6_NESTED_SHELL, R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 23 | `julia-e` | r5-deny | DENY | DENY | DENY | R6_DEFERRED_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| 24 | `python3.12-c` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 25 | `path-python-c` | r5-deny | DENY | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 26 | `bash-norc-c-source` | r5-deny | DENY | DENY | DENY | R6_NESTED_SHELL, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 27 | `bash-c-function-twice` | r5-deny | DENY | DENY | DENY | R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 28 | `set-a-dot-top` | r5-deny | DENY | DENY | DENY | R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 29 | `BASH_ENV-export` | r5-deny | DENY | DENY | DENY | R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 30 | `env-S` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_PREFIX_FORM, R6_NOT_A_PLAIN_LAUNCH |
| 31 | `exec` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 32 | `command` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 33 | `zsh-c` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_NESTED_SHELL |
| 34 | `fish-c-single` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_NESTED_SHELL |
| 35 | `nohup` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 36 | `setsid` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 37 | `timeout` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 38 | `nice` | obs-1 | ALLOW | ALLOW | ALLOW | - |
| 39 | `chroot` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 40 | `tmux` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 41 | `screen` | obs-1 | ALLOW (obs-1; outside r6 grammar) | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 42 | `at-now` | deferred | ALLOW (deferred-1) | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 43 | `array-expansion-twice` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_GROUPING, R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 44 | `var-wordsplit-twice` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 45 | `script-file-multiplied` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_NESTED_SHELL, R6_COMPOUND_LIST, R6_PIPELINE |
| 46 | `make-stdin` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 47 | `printf-format-reuse-sh-file` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_NESTED_SHELL, R6_COMPOUND_LIST |
| 48 | `bash-lc-function-twice` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 49 | `env-bash-c-function-twice` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 50 | `busybox-sh-c-fn` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 51 | `zsh-repeat` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_KEYWORD |
| 52 | `zsh-for-short` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_GROUPING, R6_KEYWORD, R6_NOT_A_PLAIN_LAUNCH |
| 53 | `fish-c-loop` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_KEYWORD, R6_COMPOUND_LIST |
| 54 | `tcsh-c-repeat` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_KEYWORD |
| 55 | `func-if-body` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 56 | `func-case-body` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 57 | `alias-reuse` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_ENV_BUILTIN, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 58 | `builtin-trap` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_ENV_BUILTIN, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 59 | `hyperfine` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 60 | `git-bisect-run` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 61 | `entr` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 62 | `launchctl-submit` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 63 | `crontab` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 64 | `swift-stdin` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH, R6_PIPELINE |
| 65 | `Rscript-loop` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 66 | `R-e-loop` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 67 | `env-python3-c-loop` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 68 | `sudo-perl-e-loop` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 69 | `nice-node-e` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 70 | `timeout-ruby-e` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 71 | `exec-python3-c` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 72 | `uv-run-python-c` | REG | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 73 | `command-awk` | MULT | ALLOW **(r5 bypass)** | DENY | DENY | R6_NOT_A_PLAIN_LAUNCH |
| 74 | `builtin-eval-split-identity` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 75 | `then-eval-split-identity` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST |
| 76 | `bash-lc-dot-source` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 77 | `env-bash-c-dot-source` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 78 | `bash-xc-source` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_NESTED_SHELL, R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 79 | `builtin-source-top` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 80 | `command-dot-top` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_ENV_BUILTIN, R6_COMPOUND_LIST |
| 81 | `if-source-top` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_KEYWORD, R6_COMPOUND_LIST |
| 82 | `zsh-ZDOTDIR` | ID | ALLOW **(r5 bypass)** | DENY | DENY | R6_ASSIGNMENT, R6_NESTED_SHELL |
| 83 | `ansi-c-quoting` | doc-limit | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| 84 | `ansi-c-quoting-token-elsewhere` | doc-limit | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 85 | `param-glue` | doc-limit | ALLOW **(r5 bypass)** | DENY | DENY | R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_COMPOUND_LIST |
| 86 | `computed-word-out-of-scope` | doc-limit | ALLOW | ALLOW | ALLOW | - |
| 87 | `env-word-out-of-scope` | doc-limit | ALLOW | ALLOW | ALLOW | - |
| 88 | `control-plain-launch` | control | ALLOW | ALLOW | ALLOW | - |
| 89 | `control-slot-py` | control | ALLOW | ALLOW | ALLOW | - |
| 90 | `control-faithful-bash-c` | control | ALLOW | ALLOW | ALLOW | - |
| 91 | `control-faithful-bash-c-outer-identity` | control | ALLOW | ALLOW | ALLOW | - |
| 92 | `control-inherited-bare-launch` | control | ALLOW | ALLOW | ALLOW | - |
| 93 | `control-cat-sub-sh` | control | ALLOW | ALLOW | ALLOW | - |
| 94 | `control-python3-m-pytest` | control | ALLOW | ALLOW | ALLOW | - |
| 95 | `control-gh-pr-view` | control | ALLOW | ALLOW | ALLOW | - |

Totals (95 rows): r6 matches the expected verdict on 95/95. **Fail-before: 52/95
rows fail on the r5 guard** = 43 bypasses (31 MULT incl. 6 REG, 9 ID, 3 doc-limit:
the review's 40 + 2 doc-limit + the finding-4 `${p}ol` row) + 7 rows outside the r6 grammar
by design (6 obs-1 + `at-now`) + 2 r5-deny rows whose rebuilt command r5 actually allows
(`expect-c` is a single spawn; `pwsh-c` loops, an extra r5 MULT bypass the
review's own command for that row did not hit). **54/95 fail on the r4 guard
(`636424a1e`)**; all six REG rows pass there, matching the review's statement
that r4 refused them.

### obs-1 verdict changes (intentional over-refusal)

The review marked these obs-1 (one honest launch observed). r6 refuses the ones
outside its closed grammar, as the brief's own prefix rule requires:
`env -S` (re-splits a string into new argv/assignments), `zsh -c` (sources
`$ZDOTDIR/.zshenv` before the body), `fish -c` (sources `config.fish`), `chroot`
(re-roots: a different `pool` binary), `tmux new-session` / `screen -dm` (the
command runs detached in a server whose environment the command line does not
set), `at now` (deferred: outlives the lease). Admitted obs-1 shapes: `exec`,
`command`, `nohup`, `setsid`, `timeout DUR`, `nice -n N`.

## Honest controls

All pass through the real `guard_bash` (table rows 88–95, plus the admit test):
plain launch with literal identity; `python3 /opt/mastermind/ext/slot.py glm -- run`
(slot.py is not itself a shell wrapper here. It is a wrapper basename, run either directly
or as `python[3[.N]]` + a literal `…/slot.py` first operand with no interpreter
options; r5 admitted it as the "bare script-file form" of an interpreter, and r6
keeps it ONLY as a plain top-level LAUNCH or NESTED body); faithful
`bash -c '<L>'` with the identity inside or on the outer command; inherited bare
launch; `cat /opt/mastermind/ext/sub.sh`; `python3 -m pytest …` (names no wrapper:
out of scope); `gh pr view 2329`. Also admitted (`test_r6_admit_rule_admits_the_closed_grammar`,
16): redirections `> log 2>&1` / `< packet`, trailing/leading newline, trailing
comment, continuation-split launch, single-quoted args containing `;()$`, quoted
wrapper path, stacked `env … nohup nice -n 5 timeout 90m`, `exec env …`,
`grep -n 'pool run' docs | head -5`, `ls …/*.sh`, `echo pool`, `pool status`,
`sub.sh __launch_plan …`.

## Real hook command line (5 representative shapes)

The registered hook command is `python3 "<guard>"` with the PreToolUse JSON on
stdin (`provider_orchestrator_policy.py:459`). Driven exactly so (system
`python3` 3.14.7, armed env, receipt at a principal-owned temp path, cwd in
`MASTERMIND_SCOPE_ROOTS`):

| shape | r6 (this branch) | r5 (`f6ed10a32`) |
|---|---|---|
| REG `env python3 -c '…for _ in range(3): os.system("<L>")'` | deny: `R6_NOT_A_PLAIN_LAUNCH` | deny: receipt not owner-authenticated |
| ID `X=… Y=…; builtin eval "$X$Y"; pool run …` | deny: `R6_EXPANSION, R6_ASSIGNMENT, R6_NOT_A_PLAIN_LAUNCH, R6_ENV_BUILTIN, R6_COMPOUND_LIST` | deny: receipt not owner-authenticated |
| MULT `f() if true; then <L>; fi; f; f` | deny: `R6_GROUPING, R6_NOT_A_PLAIN_LAUNCH, R6_KEYWORD, R6_COMPOUND_LIST` | deny: receipt not owner-authenticated |
| ID `bash -lc '. ./forged.env; pool run …'` | deny: `R6_NESTED_SHELL, R6_ENV_BUILTIN, R6_COMPOUND_LIST` | deny: receipt not owner-authenticated |
| doc-limit `$'\x70ool' run glm …` | deny: `R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH` | **ALLOW** (zero binding check) |
| control `cat /opt/mastermind/ext/sub.sh` | ALLOW | ALLOW |
| control `gh pr view 2329` | ALLOW | ALLOW |
| control plain launch | deny: receipt not owner-authenticated (expected: passes r6, reaches the binding gate) | same |

On the CLI the receipt is necessarily principal-owned (no owner service account
here), so r5's four structural bypasses show up only as "reached the binding
gate". With an owner-channel receipt they are ALLOWED (table above). r6 refuses
them structurally before the receipt is read. The driver script was a throwaway in
the session temp dir; the table above is its output.

## Earlier tests changed by r6 (justification)

Verdicts of all DENY tests are unchanged; only the asserted reason moved to the
structural code because r6 refuses before the later check runs. ALLOW controls
that r6 now refuses are changed and renamed.

| Id | Test | Change | Why |
|---|---|---|---|
| T-1 | `test_m1_every_identity_assignment_is_held_to_the_projection` [nested-export, dup-dynamic] | reason → `R6_ENV_BUILTIN` / `R6_EXPANSION` | `export` inside the `-c` body and a `$OTHER` value are not admitted forms; still deny |
| T-2 | `test_m3_every_launch_in_a_compound_command_is_checked` [second-/first-substituted, echo-decoy] | reason → `R6_COMPOUND_LIST` | compound lines are refused before per-launch token comparison; the `two-matching` row and the `launch_provider_tokens` positional unit check are unchanged |
| T-3 | `test_m1_canonical_identity_still_admits_faithful_launches` | 2 of 3 former ALLOW rows now DENY (`env -i …` → `R6_PREFIX_FORM`; `echo …; export …; launch` → `R6_COMPOUND_LIST`); added the faithful `env NAME=… pool run` spelling as ALLOW | `env -i` also strips the owner-projected `POOL_EXECUTION_BINDING`/receipt env from the launched child; a compound line is not one plain launch (the reads/exports stay available as their own commands) |
| T-4 | `test_m3_every_wrapper_shape_is_enumerated_and_checked` (last leg) | reason `'grok'` → `R6_COMPOUND_LIST` | same as T-2; all five single-shape ALLOWs and `&&`-repeat DENYs unchanged |
| T-5 | `test_minor_heredoc_staged_wrapper_launch_is_judged_under_shared_placement` | reason `'grok'` → `R6_HEREDOC` | the here-document itself refuses |
| T-6 | `test_n2_launch_feeding_a_batch_tool_stays_allowed` → `…_is_refused_under_r6` | ALLOW → DENY `R6_PIPELINE`; plain launch alone still ALLOW | `xargs` executes a program per input line; r6 admits pipes only between inspectors |
| T-7 | `test_r5_b1_structural_refusals_stay_scoped` | heredoc JSON write moved from ALLOW to a DENY `R6_HEREDOC` assertion; 7 other controls unchanged | a here-document in a command naming a wrapper is program text for whatever reads it (and its end is grammar-dependent); write such files with a non-shell tool |
| T-8 | `test_r5_mb_separate_process_dot_stays_allowed` → `…_is_refused_under_r6` | ALLOW → DENY `R6_COMPOUND_LIST`; the two halves as separate commands both ALLOW | one line is a compound list; N5-ctl2's intent (a separate sourcing process cannot touch the launch) survives as two commands |
| T-9 | `test_t3_native_claim_issues_v1_1_binding_with_t3_idempotency_join` | `caller_namespace == T3_REQUEST_NAMESPACE` → `== ""` | finding 6 |
| T-10 | `test_workspace_lease_join_stamps_containment_by_contract` | three calls pass `now_ms=NOW` | finding 7 (required injected clock) |

## Namespace story (A2)

What the claim transaction actually knows: the admitted `ChildExecutionRequest`
(root/parent/child refs, digests, budget grant), the placement spec, the
Executive worker row (`worker_id`, provider, capacity metadata incl. `adapter_id`)
and the `lease_owner` process label. It holds **no OAuth client / authenticated
principal**: that is the credential the T3 port authenticates with, and only the
port knows it. So the join stamps **no** `caller_namespace` (empty; the v1.1 dict
carries `""`). The adapter (`_current_request_namespace`, unchanged, Director A3's
file) then uses, in order, the port's attested principal, the binding's
`caller_namespace` (now empty), and the legacy fixed namespace. The namespace on the
wire is therefore exactly what the port attests, and the adapter persists it with
the launch intent and receipt before the native call / ACK. DONE_WHEN 4's
original-OAuth-namespace binding is recorded **by the adapter at launch**.
Joining that durable `request_namespace` back onto the Executive ledger
(e.g. the attempt's launch metadata) is the open seam for Director A3 / the integrator.
No principal is invented at claim.

Equality test `test_t3_claim_binding_and_real_adapter_agree_on_namespace_and_key`
(2 params): `claim_job` with a t3-native route → binding from the
`JOB_CLAIMED` payload → the REAL `T3ExecutionAdapter` with a fake port
(`oauth-client-X` attested / no `authenticated_namespace`) and a durable
`SQLiteT3AdapterStateStore`. It asserts byte-for-byte: `binding.caller_namespace == ""`;
envelope namespace `== "<fixed>:oauth-client-X"` / `== "<fixed>"` (the fixed
namespace occurs exactly once); envelope `clientRequestId == binding.operation_key
== claim payload operation_key`; and a second store instance on the same file reads
back intent/receipt `request_namespace`, intent key and a binding identical to the
claim payload.

Fail-before (pre-fix `executive_runtime.py` at HEAD, same tests): 3/3 namespace
tests fail. Wire probe on the real adapter, pre-fix → post-fix:

```
pre-fix  principal='oauth-client-X' caller_namespace='mastermind.control_plane.t3_execution_adapter/v1' wire='…/v1:oauth-client-X'
pre-fix  principal=None             caller_namespace='mastermind.control_plane.t3_execution_adapter/v1' wire='…/v1:mastermind.control_plane.t3_execution_adapter/v1'
fixed    principal='oauth-client-X' caller_namespace=''                                                  wire='…/v1:oauth-client-X'
fixed    principal=None             caller_namespace=''                                                  wire='mastermind.control_plane.t3_execution_adapter/v1'
```

Transaction: the join still runs inside `claim_job`'s `store.transaction()`
before `append_event`; the unknown-adapter rollback test is unchanged and green.
`operation_key` derivation unchanged (review observation kept: it excludes
attempt/generation, so a retry of the same logical child reuses the key, which is Director A's
design, not changed here). Proposal C-P1's "verify caller_namespace equals the
adapter namespace" must not be implemented as written. The correct check is "binding
`caller_namespace` empty or equal to the port's bare principal".

**PR #2177 hunk protection.** `git fetch origin refs/pull/2177/head` →
`70a6cf453`. 3-way `git merge-file` of `executive_runtime.py` (base = merge-base
`7a3c0b787`, theirs = #2177): **2 conflicts before this change, the same 2 after**
(lines 1058 and 17873 of the merged file, the pre-existing failures the review
recorded). This delta lands at merged lines 19226–19277, ≥1,330 lines from either.
The edit is confined to `_join_native_runtime_binding` (2 hunks: docstring, return).

## Lease join (A3)

`attach_workspace_lease(binding, record, *, now_ms)`. `now_ms` is required (the
module convention: injected epoch-ms, typed `INVALID_VALUE` otherwise). Refusal order:
type checks → `LEASE_NOT_ACTIVE` → `LEASE_EXPIRED` (`expires_ms <= now_ms`;
`None` never expires) → `LEASE_ASSIGNMENT_MISMATCH` (`binding.attempt_ref ∉
active_assignment_refs`; an empty list contains nobody) → `LEASE_REBIND_REFUSED`
(the binding already carries any containment field (`lease_ref`/`workspace_ref`/
`base_ref`/`writer_epoch`) that differs from this lease's: a different lease or a
drifted same-id record). Re-attaching the same lease returns an equal binding.
Pure: inputs never mutated. Still no production caller (as the review noted).
Fail-before: 5/5 lease tests fail on HEAD's module. The first fails at the
API level (`now_ms` keyword), the rest on the new refusals.

## Commands and counts (final lane SHA)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_provider_orchestrator_policy.py tests/test_executive_claim_job_placement_authority.py \
  tests/test_workspace_lease.py tests/test_rev5_contracts_v1_1.py tests/test_worker_adapter.py \
  tests/test_child_execution_contracts.py tests/test_t3_execution_adapter.py \
  tests/test_t3_adapter_durability.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py
  → 857 passed, 1 xfailed (pre-existing strict xfail in test_mmos_negative_matrix.py), 21 subtests passed
    (d8 identity scan green)

grep -rl "provider_orchestrator_guard\|guard_bash" tests/   → 7 test files + 1 fixture module
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q tests/test_operator_first_real_codex_skill_catalog.py \
  tests/test_fabric_full_harness_skill_catalog.py tests/test_provider_orchestrator_policy.py \
  tests/test_operator_first_policy.py tests/test_claude_parall_isolation_installer.py \
  tests/test_ci_wait_guidance.py tests/test_fabric_local_integration.py
  → 460 passed, 3 skipped (pre-existing non-root/root-file skips), 29 subtests passed

per file: test_provider_orchestrator_policy.py 324 passed (173 pre-existing incl. 11 updated
  + 151 r6: 95 table rows, 35 refusals, 16 admissions, 5 others);
  test_executive_claim_job_placement_authority.py 28; test_workspace_lease.py 13

fail-before (r6 table only):
git show f6ed10a32:ops/executive_os/provider_orchestrator_guard.py > /tmp/r5_guard.py
MASTERMIND_R6_GUARD_UNDER_TEST=/tmp/r5_guard.py env -u PYTHONPATH /opt/homebrew/bin/python3.12 \
  -m pytest tests/test_provider_orchestrator_policy.py -k test_r6_reviewer_adversarial_shape_table
  → 52 failed / 43 passed   (r4 guard 636424a1e → 54 failed / 41 passed)
```

The guard parses and runs on `/usr/bin/python3` 3.9.6 as well (stdlib-only test green).

## Known limits (not claimed closed)

1. **Arbitrary-process limit (REVIEW_2329 r2).** A command that names no wrapper is
   out of scope: a wholly computed command word (`$W run …`, `$(printf '\160\157\157\154') run …`,
   pinned as ALLOW rows 86–87), a binary or script that launches internally, or an
   interpreter whose program never spells a wrapper name. r6 narrows the scope gap
   (ANSI-C, expansion- and glob-glued partials) but cannot close it lexically.
2. **Staged-file limit.** A file staged in an EARLIER command (including an admitted
   inspector write such as `echo … > f`, or a file named `pool`/`slot.py` at ANY path
   or earlier on PATH, since the wrapper word is judged by basename) and run later
   is not observed. The same holds for a staged `.zshenv`/`.bashrc`. Within ONE command,
   staging-and-running is refused (compound).
3. **Provider-side environment.** Variables, aliases or functions already in the session
   shell (shell snapshots, `PYTHONPATH`, `SHELLOPTS`+`PS4`, `.pth` files) are outside the
   command text. The guard checks only `BASH_ENV`/`ENV` for the NESTED form.
4. **Wrapper semantics.** What the admitted wrapper does with its literal arguments is
   the wrapper's contract; only `pool run|remote`, `sub.sh`, `remote_sub.sh`, `slot.py`
   modes are recognised as launches (unchanged since r2).
5. **Over-refusal (honest direction).** In armed sessions any command naming a wrapper
   outside the three forms is refused even when benign: `git commit -m "fix pool"`,
   `pytest -k pool`, `command -v pool`, `which pool`, `cd x && pool run …`, a trailing
   `;`, CRLF line endings, heredoc file writes naming a wrapper. Remedy: run the read or
   write without the bare wrapper word, or as its own plain command.
6. **Unarmed sessions** keep the legacy identity checks only; r6 is the armed gate.

## Open / next dependency

- Fresh distinct re-review of this delta (A1 1–4, A2 6, A3 7) per the review's next-dependency line.
- Director A3 / integrator: join the adapter's persisted launch `request_namespace` back
  onto the Executive ledger (DONE_WHEN 4), and drop/replace C-P1 as noted above.
