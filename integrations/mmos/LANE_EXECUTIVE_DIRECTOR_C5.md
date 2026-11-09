# Lane: Director C5 — guard r7, the parse drives the binding gate (2026-11-09)

Branch `t3/guard-r7-parse-driven-gate`, created from `t3/t3-hermes-restart-recovery`
at `29a82f779` (the r6 guard under review). Implementation by Claude Opus 5.5
(native ORCHESTRATION route) answering the distinct r6 review (REVIEW2, A1
NEEDS_REWORK, findings 1–6 + over-refusal note). No push, no PR, no other
worktree, `~/Mastermind` or `~/.hermes` touched. Files: the guard module, its
test module, this ledger. This is SELF_REVIEWED work; the delta needs a fresh
distinct re-review (CRITICAL row: security/source authority).

## Commits

| Commit | Content |
|---|---|
| `029298d6c` | r7 guard + 337 new tests (no existing test changed) |
| (this file) | Ledger |

## Finding → fix → test

| # | Sev | Finding (REVIEW2) | Fix (r7) | Tests |
|---|---|---|---|---|
| 1 | BLOCKER | Binding gate censused launches with text regexes that need wrapper and mode adjacent; when they missed, `guard_fabric_launch` returned before `validate_execution_binding` (`pool </dev/null run grok …` ALLOWED, zero binding check). Grammar order `… ARG* REDIR*` not enforced | (a) `_guard_armed_launch`: the r7 parse is the census. Every unit whose command word is a wrapper (or python + slot.py, including a NESTED body) becomes an `_R7Launch` (lexer argv + exact identity values); if any exists, `validate_execution_binding(raw, parse)` ALWAYS runs — there is no early return for it. Wrapper, mode and token are read from the argv (`_r7_census`); the r4 text view (`_wrapper_invocations`) must find exactly the same `(wrapper, token)` list or the launch is refused ("unaccounted descendant"). (b) Grammar order enforced in the parse: a word after a redirection in the same simple command → `R6_REDIRECTION` (applies to LAUNCH, NESTED and every read form) | REVIEW2 table rows 1–12 (seams, all deny/deny/n); 18 admitted launch shapes × {faithful allow, substituted → provider substitution, stale fence} with the census/text-view equality asserted (`test_r7_every_admitted_launch_shape_reaches_every_binding_check`, closes the r6 coverage gap); `test_r7_census_disagreement_is_refused_as_unaccounted` (incl. a text view forced empty → refused, never skipped); hook CLI rows 1–7 |
| 2 | MAJOR | Provider substitution unchecked: `pool run </dev/null grok`, `>/tmp/cat pool run grok` (redirect target read as head), `POOL_TASK_CLASS='code cat' pool run grok` (word inside a value read as head) | Same fix: token read from the parse; the first two are now structural (`R6_REDIRECTION`); the third reaches the gate and is refused by the census cross-check (the r4 view still misreads `cat` and finds no launch, the parse finds `pool run grok` → disagreement) | rows 4, 9, 10, 13 |
| 3 | MAJOR | Identity projection via lossy readers (`"root-orch-1"' evil'` passed; child gets `root-orch-1 evil`) | The gate compares the lexer's EXACT literal value of every identity assignment reaching each wrapper-head unit (prefix, `env` argument, nested outer + body) with `_expected_projection`; unassigned names use the inherited value. Values with an unquoted `~` (tilde expansion) or glob/brace character are refused structurally (`R6_ASSIGNMENT`). The r4 regex views stay as defence in depth (they can only add refusals) | rows 13–20, 59–61; `test_r7_parse_reads_exact_identity_values_everywhere`; hook row `id-lossy-value` |
| 4 | MINOR | Scope false negatives `${x:-pool}`, `${x-pool}`, `${x:-sub.sh}`, `${:-pool}`, `p$""ool`, `p$"o"ol` | Before the literal match, every `${NAME…op` opening (bash/zsh operators, zsh `(flags)`, empty name) becomes a space and `$"` becomes `"`. Also: a glob needs only ONE literal stem character (`p*`, `s*.py`); any glob in COMMAND-WORD position that can match a wrapper basename (`* run`, `???? run`); a wrapper name glued to a short option (`-O'pool run …'`, `-Opool` — found in self-review: `git grep -O'<launch>' x` ran its pager launch; r6 only caught it when `pool run` happened to be adjacent) | rows 21–29, 66–67; `test_r7_scope_is_widened_per_finding_4` (15); `test_r7_scope_residue_stays_documented` |
| 5 | MINOR | Inspector form admits any output redirection (`echo 'pool(){…}' >> ~/.zshenv`) | A read form writes ONLY to `/dev/null` or a duplicated/closed descriptor; `<&` must name a descriptor; `/dev/tcp|udp/…` refused everywhere. Also refused in read forms: `xxd` (dropped: `-r IN OUT` writes), `tail -f/-F/--follow/--retry` (never finishes), `file -C/--compile` (writes), grep-family ugrep options `--filter* --pager* --save-config* --config* --view* --query* --index*` and `-…Q…` (Claude's `grep` is a snapshot function to ugrep), and a leading-glob argument for option-sensitive heads (a staged file named `--filter=…` would become an option). Beyond the finding: a LAUNCH/NESTED never writes to a dot-path (`~/.zshenv`, `~/.local/bin/pool`, `.git/hooks/…`) | rows 30–37, 62–65; read-form refusal list |
| 6 | MINOR | Every admitted head judged by basename (`/tmp/evil/env`, `./nohup`, `/tmp/evil/bash -c`, `python3 /tmp/evil/slot.py`) | Chosen rule: transparent prefixes, nested shells, python and every read-form head must be their exact LOWERCASE bare name (resolved through the session PATH) or exactly `/bin/<name>` / `/usr/bin/<name>`; `exec`/`command` bare only (`R6_HEAD_SPELLING`). Wrapper words and the slot.py operand keep any path ON PURPOSE: what they run is the binding-checked launch itself (staged-file limit, below) | rows 38–45 (deny), 46–55 (on purpose, each reaches the gate) |
| carve | note | Over-refusal: `git commit -m "fix pool"`, `rg`, `sed -n … pool`, `git grep` | Closed (head, subcommand, option-allowlist) read forms — see the rule. `pytest -k pool`, `which pool`, `command -v pool`, `cd x && launch`, trailing `;`, `gh … \| grep pool` stay refused (no safe carve-out) | 26 admits (`test_r7_read_forms_admit_closed_reads`: allow bound AND nobind, gate never reached, parse finds no launch); 55 refusals incl. every listed exec-capable option; static allowlist check; rows 83–88 |
| msg | note | Reword the non-launch refusal | Two wordings, same `Mastermind shared-placement guard: unobservable launch —` prefix (existing assertions): a unit headed by a wrapper/python/shell (or an unreadable line) keeps "names a paid-launch wrapper but is not one plain top-level launch"; otherwise "mentions a paid-launch wrapper name … only as data or program text, and it is not an admitted read form" + "Not launching? …" (lists the read forms) + the launch remedy | `test_r7_refusal_wording_distinguishes_mentions_from_launches` |
| S1 | found in self-review (CRITICAL) | **Hook-timeout fail-open.** The registered hook timeout is 10 s and a killed/crashed hook does not block the tool call (Claude Code hook contract: only exit 2 / a deny decision blocks; not re-verified live here). `FABRIC_LAUNCH_RE`, `_WRAPPER_RE`, `_WRAPPER_NAME_RE`, `_BATCH_EXECUTOR_RE` were QUADRATIC (`(?:[A-Za-z0-9_./-]+/)?` before a name): on HEAD `pool run grok a /tmp grok-4 -O/a/a/…` took **11.5 s at 20 KB** through the real hook command line and was killed at 40 KB | Path groups removed (the lookbehind already admits a name after `/`; the group only widened `match.start()`); r4 head lookup precomputes separators and reads each simple command's first word once; identity/env/export views read bounded windows; `do…done` spans by a linear keyword scan; computed-substitution unwrapping capped at 32 levels (deeper → in scope); `fnmatch` replaced by a DP glob matcher (`*?*?…` was catastrophic); lexer reads literal runs (per-char appends were quadratic); recursion → typed `R6_TOKENIZE_FAILED`; armed gate runs BEFORE the heredoc stripper; armed commands > 262 144 chars refused outright; `main()` fails closed on any internal error in an armed session. Same input on r7: **0.09 s** | `test_r7_armed_gate_finishes_far_inside_the_hook_budget` (14 adversarial 250 KB rows, < 5 s each; measured ≤ 1.25 s on 3.12, ≤ 0.93 s on 3.9), cap test, `test_r7_main_fails_closed_on_an_internal_error_when_armed`, `test_r7_glob_and_parts_matchers_agree_with_the_regex_semantics` (8 000 random cases vs fnmatch/regex). Equivalence of the rewritten r4 views with HEAD: 0 differences over 18 686 commands (all table rows + 20 000 fuzzed) for invocations, both identity views, multiplexing, FABRIC regex, name regex, env-clear offsets (ad-hoc script, not committed) |
| S2 | found in self-review | Unarmed sessions have the same seam (`pool </dev/null run …` skipped the legacy identity check) | The unarmed early return also requires an empty parse census (only when the text names a wrapper) | `test_r7_unarmed_sessions_see_launches_the_text_regex_misses` |

## The r7 rule (precisely)

Armed sessions only (`MASTERMIND_SHARED_PLACEMENT` or a projected binding), on the
RAW command text (heredoc bodies included), before anything else in the Bash hook.

0. **Budget.** `len(raw) > 262144` → refuse. Every later step is linear in `len(raw)`.
1. **Scope** `r6_names_wrapper(raw)` (or the r4 regexes see a launch → parse anyway):
   literal wrapper name (`pool`, `sub.sh`, `remote_sub.sh`, `slot.py`; any path;
   case-insensitive; quotes/backslashes/continuations removed; `$'…'` decoded;
   `${NAME…op` openings read as spaces; `$"`→`"`), a name glued to a short option
   (`-Xpool`), a word mixing literal text with `$…`/`$(…)` that can spell a wrapper,
   a glob/brace word spelling ≥ 1 stem character of a wrapper, or a glob in
   command-word position that can match one. Out of scope → nothing to judge
   (arbitrary-process limit).
2. **Parse** (`r7_parse` → `_R7Parse`): bash/POSIX word rules (lexer of r6 plus:
   zsh `<N-M>` → `R6_TOKENIZE_FAILED`; nesting too deep → `R6_TOKENIZE_FAILED`).
   Admitted iff every code is advisory (`R6_DEFERRED_EXPANSION`) and the line is
   exactly one of:

```
LAUNCH     ASSIGN* PREFIX* ( WRAPPER | PYTHON SLOTPATH ) ARG* REDIR*
NESTED     ASSIGN* PREFIX* ( bash | sh ) -c BODY REDIR*      BODY ⊨ exactly one LAUNCH
READ       RHEAD RARG* RREDIR* ( '|' RHEAD RARG* RREDIR* )*

ASSIGN     unquoted NAME= with NAME ∈ {POOL_ORCHESTRATOR_ID, POOL_PARENT_RUN_ID, POOL_TASK_CLASS},
           '=' not '+=', literal value, no unquoted ~ or * ? [ { } in the value
PREFIX     env ASSIGN'* | nohup | setsid | exec | command | nice [-n N] | timeout DURATION   (≤ 4)
           — exact lowercase; bare name or /bin/… /usr/bin/… ; exec/command bare only
WRAPPER    literal word, basename ∈ wrappers (case-insensitive), ANY path   (on purpose)
PYTHON     python | python3 | python3.N — exact, bare or /bin/ /usr/bin/, no options
SLOTPATH   literal word, basename slot.py (case-insensitive), ANY path      (on purpose)
bash | sh  exact, bare or /bin/ /usr/bin/; exactly -c and one literal BODY; session BASH_ENV/ENV unset
ARG        literal word, no unquoted glob/brace
REDIR      < FILE | >,>>,>|,&>,&>>,>& FILE (FILE ≠ dot-path, ≠ /dev/tcp|udp, not starting '!')
           | n>&m | <&m | >&- | <&- ;   only AFTER the last ARG
RHEAD      exact lowercase, bare or /bin/ /usr/bin/, no ASSIGN/PREFIX, never in a BODY:
           cat head tail grep egrep fgrep wc ls stat file diff cmp shasum sha1sum sha256sum md5 md5sum nl od echo
           | git [--no-pager] SUB  with SUB's closed option grammar (below)
           | rg  with the rg option allowlist
           | sed -n N[,M]p FILE…            (FILE not starting '-')
RARG       literal; tail: no -f/-F/--follow/--retry; file: no -C/--compile;
           grep/egrep/fgrep: no --filter* --pager* --save-config* --config* --view* --query* --index*, no -…Q…;
           grep/egrep/fgrep/tail/file/git/rg/sed: no glob argument whose first character is a pattern char
RREDIR     < FILE | > /dev/null (also >>,>|,&>,&>>) | >& /dev/null | n>&m | <&m | close ;  only AFTER the args
```

   git option grammars (`_R7_GIT_SPECS`; anything else, incl. every git global option
   but `--no-pager`, is refused): **commit** `-a -q -s -n -m V -F V --all --quiet
   --signoff --amend --no-edit --allow-empty --no-verify --message[=]V --file[=]V`,
   and it must carry `-m`/`-F` (or `--amend --no-edit`); **log** diff-format flags +
   `--oneline --graph --decorate --all --reverse --no-merges --first-parent --follow
   … -n V -S V -G V -U V -L V -<N>` + `--max-count= --skip= --since= --until=
   --author= --grep= --format= --pretty= --date=`; **show** diff-format flags +
   `--oneline --abbrev-commit --no-notes --format= --pretty= --date= -U V`;
   **diff** diff-format flags + `--cached --staged --merge-base --exit-code
   --quiet --no-index --minimal --histogram --patience -U V`; **status** `-s -b
   -v -u[V] --short --branch --porcelain[=] --long --ignored[=]
   --untracked-files= --no-renames --ahead-behind --no-ahead-behind --show-stash`;
   **grep** `-n -i -I -l -L -c -w -v -E -F -G -P -h -H -o -q -a -r -W -p -z -e V
   -A V -B V -C V -m V -f V` + long equivalents; **add** `-A -u -n -v -f -N`
   + long equivalents. Diff-format flags: `--stat[=] --shortstat --numstat
   --name-only --name-status --patch --no-patch --raw --color[=] --no-color
   --no-ext-diff --no-textconv --ignore-all-space --ignore-space-change
   --word-diff[=] --summary --check --find-renames --no-renames --full-index
   --compact-summary --patch-with-stat --abbrev[=] --unified= --diff-filter=
   --relative=`. Absent on purpose: `-O/--open-files-in-pager --ext-diff
   --textconv --output --exec -e/--edit -p/-i/--interactive (add) -S/--gpg-sign
   -c (commit)`, and `bisect run`, `rebase --exec`, `submodule foreach`, `config`.
   rg (`_R7_RG_SPEC`): short `isSwxvlcoFnNHILUPuqp0ab.` / valued `efgtTABCmMdjrE`
   + 55 long options; absent: `--pre --pre-glob -z --search-zip --hostname-bin`.
3. **Refused shape** → deny with typed `R6_*` codes (new: `R6_HEAD_SPELLING`;
   `R6_REDIRECTION` now also covers order, read-form targets, dot-paths, network).
4. **No wrapper-head unit** (read forms only) → allowed, no binding check: no word
   on the line is executed except the read heads.
5. **Otherwise the binding gate ALWAYS runs** (`validate_execution_binding(raw, parse)`):
   binding/receipt/fence/expiry as before → census cross-check (parse `(wrapper,
   token)` list == r4 text-view list, else "unaccounted descendant") → r4
   loop/batch check → EXACT identity values vs projection (every assignment;
   inherited value if none) → r4 identity view (defence in depth) → every parsed
   token known and == `pool_ref` → at most one paid launch. Then the legacy root
   rebind / missing-identity checks on exact AND regex values. Census law
   (`_r7_census`): `pool run P` / `pool remote H P` are paid; other `pool`
   subcommands (status, plan, hosts, …), a wrapper with no argument and the helper
   modes `__launch_plan`/`__glm_memory` are not paid — but still reach the gate
   (a helper needs a valid binding in an armed session).

**Shell model.** The lexer models bash/POSIX word rules because the NESTED form is
`bash -c`/`sh -c` and POSIX is the common ground of what the gate must read. The
Bash tool on this host runs `zsh -c`. Known divergences and how r7 treats them:
`<N-M>` (zsh numeric glob / bash redirections) → refused; `>!`/`>>!` (zsh clobber
/ bash target `!…`) → refused; `=(…)`, glob qualifiers `*(e:…:)`, `&!`, `&|` →
refused through `(` / list operators; `$"…"` (bash locale; zsh plain) and
`${:-x}` (zsh only) → computed segments, refused, and decoded for scope; `=cmd`
EQUALS expansion → a head `=pool` is not an admitted head and is in scope
(refused); in an ARG it can only change that argument (token compared exactly).
zsh `repeat`/`foreach`/`time` reserved words are refused. Not modelled: zsh
global aliases and functions from the provider's shell snapshot (provider-side
environment, below).

**What r7 guarantees, and only that.** In an armed session, a single Bash command
whose text is in scope reaches the shell only if it is one of the forms above;
every admitted unit whose command word is a wrapper is censused from the parse,
cross-checked against the text view, and judged by the binding gate with exact
identity values; read forms write nowhere but `/dev/null`; and the hook finishes
(linear scans, size cap, fail-closed on internal error). It is a fence over command
TEXT, not a sandbox.

## REVIEW2 table — every reviewer row + r7 extras + controls (88 rows)

`b/n/g` = verdict with the faithful binding / verdict armed without a binding /
whether `validate_execution_binding` was reached (spy on the module attribute; same
in both runs). r6 = the guard at `29a82f779` (`git show 29a82f779:ops/executive_os/provider_orchestrator_guard.py`), r7 = `029298d6c`,
both through each module's real `guard_bash` under the same fixture (owner-channel
receipt, inherited projected identity). The review recorded names/prose only; each
command is my reconstruction from the name, the finding text that cites it and the
reviewer's r6 column, which the harness reproduces for every reviewer row
(`insp-echo-bashrc`/`insp-pipe-write` were rebuilt without `pool run` text, and
`id-gt-no-space` with the first-quoted-span form, to match the reviewer's ALLOW).
`_R6_P` = faithful identity prefix, `_R6_L` = `_R6_P pool run glm a /tmp glm-5.3`,
`_R6_B` = bare launch. Bold = verdict changed.

| # | row | class | reconstructed command | r6 b/n/g | r7 b/n/g | note |
|---|---|---|---|---|---|---|
| 1 | `seam-redir-before-mode-pool` | seam | `pool </dev/null run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 2 | `seam-redir-before-mode-pool-out` | seam | `pool >/tmp/lane.out run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 3 | `seam-fd-dup-before-mode` | seam | `pool 2>&1 run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 4 | `seam-redir-after-run` | seam | `pool run </dev/null grok a /tmp grok-4` | allow/deny/Y | **deny/deny/n** |  |
| 5 | `seam-redir-subsh` | seam | `/opt/mastermind/ext/sub.sh </dev/null grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 6 | `seam-redir-remote-sub` | seam | `/opt/mastermind/ext/remote_sub.sh </dev/null mini2 grok /tmp/p.txt /repo grok-4` | allow/allow/n | **deny/deny/n** |  |
| 7 | `seam-redir-slot` | seam | `python3 /opt/mastermind/ext/slot.py </dev/null grok -- run` | allow/allow/n | **deny/deny/n** |  |
| 8 | `seam-redir-nested` | seam | `bash -c 'pool </dev/null run grok a /tmp grok-4'` | allow/allow/n | **deny/deny/n** |  |
| 9 | `seam-redir-target-named-cat` | seam | `>/tmp/cat pool run grok a /tmp grok-4` | allow/deny/Y | **deny/deny/n** |  |
| 10 | `seam-redir-target-named-grep-subsh` | seam | `>/tmp/grep /opt/mastermind/ext/sub.sh grok a /tmp grok-4` | allow/deny/Y | **deny/deny/n** |  |
| 11 | `fd-close-before-mode` | seam | `pool 0<&- run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 12 | `quoted-run-redirect` | seam | `pool r''un </dev/null grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 13 | `head-misread-via-taskclass-value` | id | `POOL_TASK_CLASS='code cat' POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 pool run grok a…` | allow/deny/Y | **deny/deny/Y** | refused by the census cross-check (r4 view misreads `cat` as head; the parse does not) |
| 14 | `id-dq-then-sq-space` | id | `POOL_ORCHESTRATOR_ID="root-orch-1"' evil' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm…` | allow/deny/Y | **deny/deny/Y** |  |
| 15 | `id-dq-dq-space` | id | `POOL_ORCHESTRATOR_ID="root-orch-1"" evil" POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm…` | allow/deny/Y | **deny/deny/Y** |  |
| 16 | `id-parent-sq-esc-space` | id | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID='hermes-run-7'\ evil POOL_TASK_CLASS=code pool run glm …` | allow/deny/Y | **deny/deny/Y** |  |
| 17 | `id-env-prefix` | id | `env POOL_ORCHESTRATOR_ID="root-orch-1"' evil' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run…` | allow/deny/Y | **deny/deny/Y** |  |
| 18 | `id-nested-body` | id | `bash -c "POOL_ORCHESTRATOR_ID='root-orch-1'' evil' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code poo…` | allow/deny/Y | **deny/deny/Y** |  |
| 19 | `id-gt-no-space` | id | `POOL_ORCHESTRATOR_ID="root-orch-1"'>x' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a …` | allow/deny/Y | **deny/deny/Y** |  |
| 20 | `id-gt-unquoted` | id | `POOL_ORCHESTRATOR_ID=root-orch-1'>x' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /t…` | deny/deny/Y | deny/deny/Y |  |
| 21 | `scope-param-default` | scope | `${x:-pool} run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 22 | `scope-param-default-nocolon` | scope | `${x-pool} run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 23 | `scope-param-default-subsh` | scope | `${x:-sub.sh} grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 24 | `scope-zsh-empty-name` | scope | `${:-pool} run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 25 | `scope-locale-empty` | scope | `p$""ool run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 26 | `scope-locale-glue` | scope | `p$"o"ol run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 27 | `scope-glob-1char` | scope | `p* run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 28 | `scope-glob-head-wildcard` | scope | `???? run grok a /tmp grok-4` | allow/allow/n | **deny/deny/n** |  |
| 29 | `scope-homoglyph` | doc-limit | `рool run grok a /tmp grok-4` | allow/allow/n | allow/allow/n | documented limit: names a different file; only a staged binary of that name could run |
| 30 | `insp-echo-zshenv` | insp | `echo 'pool() { command pool "$@"; command pool "$@"; }' >> ~/.zshenv` | allow/allow/n | **deny/deny/n** |  |
| 31 | `insp-echo-bashrc` | insp | `echo 'pool() { command pool "$@"; command pool "$@"; }' >> ~/.bashrc` | allow/allow/n | **deny/deny/n** |  |
| 32 | `insp-cat-copy-wrapper` | insp | `cat /opt/mastermind/ext/sub.sh > /tmp/evil/sub.sh` | allow/allow/n | **deny/deny/n** |  |
| 33 | `insp-pipe-write` | insp | `cat /opt/mastermind/ext/sub.sh \| head -c 100000 > /tmp/evil/sub.sh` | allow/allow/n | **deny/deny/n** |  |
| 34 | `insp-pipe-append-zshenv` | insp | `echo 'pool run grok a /tmp grok-4' \| cat >> ~/.zshenv` | deny/deny/Y | **deny/deny/n** |  |
| 35 | `insp-devtcp` | insp | `cat /opt/mastermind/ext/sub.sh > /dev/tcp/127.0.0.1/9` | allow/allow/n | **deny/deny/n** |  |
| 36 | `insp-xxd-r` | insp | `xxd -r -p /tmp/pool.hex /tmp/evil/pool` | allow/allow/n | **deny/deny/n** |  |
| 37 | `insp-tail-f` | insp | `tail -f /tmp/lane/pool` | allow/allow/n | **deny/deny/n** |  |
| 38 | `path-prefix-env` | path | `/tmp/evil/env POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool ru…` | allow/deny/Y | **deny/deny/n** |  |
| 39 | `path-prefix-nohup` | path | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code ./nohup pool run glm …` | allow/deny/Y | **deny/deny/n** |  |
| 40 | `upper-NICE` | path | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code NICE -n 5 pool run gl…` | allow/deny/Y | **deny/deny/n** |  |
| 41 | `path-bash-staged` | path | `/tmp/evil/bash -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code po…` | allow/deny/Y | **deny/deny/n** |  |
| 42 | `path-python-staged` | path | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code /tmp/evil/python3 /op…` | allow/deny/Y | **deny/deny/n** |  |
| 43 | `upper-PYTHON3` | path | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code PYTHON3 /opt/mastermi…` | allow/deny/Y | **deny/deny/n** |  |
| 44 | `path-inspector-staged` | path | `/tmp/evil/cat /opt/mastermind/ext/sub.sh` | allow/allow/n | **deny/deny/n** |  |
| 45 | `slot-python2-literal` | path | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code python2 /opt/mastermi…` | deny/deny/n | deny/deny/n |  |
| 46 | `path-wrapper` | on-purpose | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code /opt/mastermind/ext/p…` | allow/deny/Y | allow/deny/Y | on purpose: wrappers live at install-specific paths; the launch is binding-checked (staged-file limit) |
| 47 | `path-prefix-system-env` | on-purpose | `/usr/bin/env POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run…` | allow/deny/Y | allow/deny/Y | on purpose: /usr/bin is root-owned |
| 48 | `nested-comment` | on-purpose | `bash -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm…` | allow/deny/Y | allow/deny/Y | on purpose: the comment is whitespace in both shells |
| 49 | `nested-bs-newline-in-sq` | on-purpose | `bash -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool ru\\nn …` | allow/deny/Y | allow/deny/Y | on purpose: the inner shell joins the continuation; the parse of the body does too |
| 50 | `nested-trailing-redirect` | on-purpose | `bash -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm…` | allow/deny/Y | allow/deny/Y | on purpose: trailing redirection of the outer unit |
| 51 | `nested-sh` | on-purpose | `sh -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a…` | allow/deny/Y | allow/deny/Y | on purpose: NESTED admits sh |
| 52 | `nested-bash-path` | on-purpose | `/bin/bash -c 'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool ru…` | allow/deny/Y | allow/deny/Y | on purpose: /bin is root-owned |
| 53 | `slot-staged-path` | on-purpose | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code python3 /tmp/staged/s…` | allow/deny/Y | allow/deny/Y | on purpose: slot.py operand keeps any path; binding-checked (staged-file limit) |
| 54 | `slot-upper` | on-purpose | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code python3 /opt/mastermi…` | allow/deny/Y | allow/deny/Y | on purpose: SLOT.PY = slot.py on case-insensitive APFS; censused case-insensitively and binding-checked |
| 55 | `slot-python2` | on-purpose | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code python /opt/mastermin…` | allow/deny/Y | allow/deny/Y | on purpose: unversioned `python` (Python 2 on legacy hosts) is a python name; binding-checked |
| 56 | `zsh-numeric-glob` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 57 | `zsh-clobber-spaced` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 58 | `zsh-clobber-glued` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 59 | `id-tilde-value` | r7-extra | `POOL_ORCHESTRATOR_ID=~root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp …` | deny/deny/Y | **deny/deny/n** |  |
| 60 | `id-env-glob-value` | r7-extra | `env POOL_ORCHESTRATOR_ID=root-orch-? POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /t…` | deny/deny/Y | **deny/deny/n** |  |
| 61 | `id-trailing-space` | r7-extra | `POOL_ORCHESTRATOR_ID='root-orch-1 ' POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tm…` | allow/deny/Y | **deny/deny/Y** |  |
| 62 | `launch-writes-zshenv` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 63 | `launch-overwrites-wrapper` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 64 | `launch-devtcp` | r7-extra | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | **deny/deny/n** |  |
| 65 | `read-devtcp-input` | r7-extra | `cat < /dev/tcp/127.0.0.1/9 /opt/mastermind/ext/sub.sh` | allow/allow/n | **deny/deny/n** |  |
| 66 | `glued-pager-launch` | r7-extra | `git grep -O'pool run grok a /tmp grok-4' x` | allow/deny/Y | **deny/deny/n** |  |
| 67 | `glued-pager-name` | r7-extra | `git grep -Opool x` | allow/allow/n | **deny/deny/n** |  |
| 68 | `pool-helper-reaches-gate` | r7-extra | `pool status` | allow/allow/n | **allow/deny/Y** | r7 consequence: a wrapper head never skips the gate (helper mode = zero paid launches) |
| 69 | `subsh-helper-reaches-gate` | r7-extra | `/opt/mastermind/ext/sub.sh __launch_plan glm /tmp` | allow/allow/n | **allow/deny/Y** | same |
| 70 | `control-plain-launch` | control | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | allow/deny/Y |  |
| 71 | `control-trailing-redirects` | control | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | allow/deny/Y | allow/deny/Y |  |
| 72 | `control-inherited-bare-launch` | control | `pool run glm a /tmp glm-5.3` | allow/deny/Y | allow/deny/Y |  |
| 73 | `control-env-prefix` | control | `env POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code nohup nice -n 5 t…` | allow/deny/Y | allow/deny/Y |  |
| 74 | `control-slot` | control | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code python3 /opt/mastermi…` | allow/deny/Y | allow/deny/Y |  |
| 75 | `control-pool-remote` | control | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool remote mini2 glm…` | allow/deny/Y | allow/deny/Y |  |
| 76 | `control-cat` | control | `cat /opt/mastermind/ext/sub.sh` | allow/allow/n | allow/allow/n |  |
| 77 | `control-grep-pipe` | control | `grep -n 'pool run' docs/runbook.md \| head -5 2>/dev/null` | allow/deny/Y | **allow/allow/n** | r7 fixes an r6 over-refusal: a read form never reaches the gate |
| 78 | `control-ls-stderr` | control | `ls -la ~/.local/bin/pool 2>/dev/null` | allow/allow/n | allow/allow/n |  |
| 79 | `control-echo-fd` | control | `echo pool >&2` | allow/allow/n | allow/allow/n |  |
| 80 | `control-wc-input` | control | `wc -l < /opt/mastermind/ext/sub.sh` | allow/allow/n | allow/allow/n |  |
| 81 | `control-gh-pr-view` | control | `gh pr view 2329` | allow/allow/n | allow/allow/n |  |
| 82 | `control-pytest-m` | control | `python3 -m pytest tests/test_provider_orchestrator_policy.py` | allow/allow/n | allow/allow/n |  |
| 83 | `overrefusal-pytest-k` | over-refusal | `pytest -k pool` | deny/deny/n | deny/deny/n |  |
| 84 | `overrefusal-which` | over-refusal | `which pool` | deny/deny/n | deny/deny/n |  |
| 85 | `overrefusal-command-v` | over-refusal | `command -v pool` | deny/deny/n | deny/deny/n |  |
| 86 | `overrefusal-cd-and` | over-refusal | `cd /tmp && POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run g…` | deny/deny/n | deny/deny/n |  |
| 87 | `overrefusal-trailing-semicolon` | over-refusal | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp g…` | deny/deny/n | deny/deny/n |  |
| 88 | `overrefusal-gh-pipe-grep` | over-refusal | `gh pr view 1 \| grep pool` | deny/deny/n | deny/deny/n |  |

Totals: 88 rows (45 reviewer rows + 43 r7 extras / on-purpose / controls /
over-refusals). **Fail-before: 57/88 rows fail on the r6 guard**: 12 seam, 8 scope,
8 inspector, 7 identity, 7 path/spelling, 14 r7-extra, 1 control
(`control-grep-pipe`, an r6 over-refusal without a binding). **29 of them were ALLOWED
by r6 with and without a binding and never reached the gate** (zero binding check:
9 seams, 8 scope, 7 inspector, 1 path, 4 extras); the others reached the gate but
were ALLOWED with a faithful binding (lossy identity, unchecked token, staged head
path). 0/88 fail on r7. Reviewer rows whose verdict r7 keeps: the 10 "judge each"
rows admitted ON PURPOSE (each reaches the gate) and the homoglyph limit.

## The 95 r6 rows (incl. the r5 review's 86 shapes), re-run with nobind + gate flag

`test_r7_r6_table_rows_with_gate_instrumentation` (95 params) asserts for every row
of C3's `_R6_TABLE` (which contains the r5 review's 86 reconstructed shapes + 9
pins/controls): bound verdict = the C3 expectation; refused rows are refused
structurally (gate never reached, bound and nobind); the 11 admitted launch rows
(`exec command nohup setsid timeout nice`, plain launch, slot.py, faithful
`bash -c` ×2, inherited bare launch) reach the gate in both runs and are refused for
"missing binding" without one; the 5 admitted non-launch rows (2 pinned
out-of-scope computed words, `cat sub.sh`, `python3 -m pytest`, `gh pr view`) never
reach it and stay ALLOW without a binding. Result: 95/95 on r7 and 95/95 on r6 — these
are regression rows; nothing r6 got right changed. The original C3 table test
(`test_r6_reviewer_adversarial_shape_table`, typed codes) is unchanged and green.

## Real hook command line (16 shapes, armed, with and without a binding)

The registered hook is `python3 "<guard>"` (`provider_orchestrator_policy.py`), run
here exactly so via `/bin/sh -c` with the PreToolUse JSON on stdin
(`test_r7_real_hook_command_line`, 16 params × 2 runs; `python3` = Homebrew 3.14.7).
On a single-uid host the receipt is necessarily principal-owned, so a bound run that
reaches the gate is refused at the receipt channel ("not owner-authenticated") and an
unbound one for "missing binding" — both prove the gate ran; the bound ALLOW of a
faithful launch is proven in-process with the owner-channel fixture.

| row | command | r6 bound | r6 nobind | r7 bound | r7 nobind |
|---|---|---|---|---|---|
| `seam-redir-before-mode` | `pool </dev/null run grok a /tmp grok-4` | **ALLOW** | **ALLOW** | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-fd-dup` | `pool 2>&1 run grok a /tmp grok-4` | **ALLOW** | **ALLOW** | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-redir-after-run` | `pool run </dev/null grok a /tmp grok-4` | deny: not owner-authenticated | deny: missing binding | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-subsh` | `/opt/x/sub.sh </dev/null grok a /tmp grok-4` | **ALLOW** | **ALLOW** | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-slot` | `python3 /opt/x/slot.py </dev/null grok -- run` | **ALLOW** | **ALLOW** | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-nested` | `bash -c 'pool </dev/null run grok a /tmp grok-4'` | **ALLOW** | **ALLOW** | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `seam-target-named-cat` | `>/tmp/cat pool run grok a /tmp grok-4` | deny: not owner-authenticated | deny: missing binding | deny R6_REDIRECTION | deny R6_REDIRECTION |
| `scope-param-default` | `${x:-pool} run grok a /tmp grok-4` | **ALLOW** | **ALLOW** | deny R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH | deny R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| `scope-locale` | `p$""ool run grok a /tmp grok-4` | **ALLOW** | **ALLOW** | deny R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH | deny R6_EXPANSION, R6_NOT_A_PLAIN_LAUNCH |
| `insp-echo-zshenv` | `echo 'pool() { command pool "$@"; command pool "$@"; }' >> ~` | **ALLOW** | **ALLOW** | deny R6_DEFERRED_EXPANSION, R6_REDIRECTION | deny R6_DEFERRED_EXPANSION, R6_REDIRECTION |
| `path-prefix-env` | `/tmp/evil/env pool run glm a /tmp glm-5.3` | deny: not owner-authenticated | deny: missing binding | deny R6_HEAD_SPELLING | deny R6_HEAD_SPELLING |
| `id-lossy-value` | `POOL_ORCHESTRATOR_ID="root-orch-1"' evil' POOL_PARENT_RUN_ID` | deny: not owner-authenticated | deny: missing binding | deny: not owner-authenticated | deny: missing binding |
| `control-plain-launch` | `POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-r` | deny: not owner-authenticated | deny: missing binding | deny: not owner-authenticated | deny: missing binding |
| `control-git-commit` | `git commit -m "fix pool"` | deny R6_NOT_A_PLAIN_LAUNCH | deny R6_NOT_A_PLAIN_LAUNCH | ALLOW | ALLOW |
| `control-cat` | `cat /opt/mastermind/ext/sub.sh` | ALLOW | ALLOW | ALLOW | ALLOW |
| `control-gh` | `gh pr view 2329` | ALLOW | ALLOW | ALLOW | ALLOW |

Fail-before: 12/16 rows fail on r6 (7 shapes ALLOWED with and without a binding,
i.e. zero binding check, plus `git commit -m "fix pool"` refused). r7: 0/16.

## Hook budget (fail-open by timeout)

Real hook command line, armed, no binding, `pool run grok a /tmp grok-4 -O/a/a/…`:

| chars | r6 (`29a82f779`) | r7 |
|---|---|---|
| 10 030 | 2.74 s | 0.08 s |
| 20 030 | **11.47 s** (> 10 s registered timeout) | 0.09 s |
| 40 030 | **killed at 30 s** | 0.09 s |

r7 in-process worst cases at ~262 KB (adversarial set of 22 + bound set of 9 shapes):
≤ 0.30 s unbound, ≤ 1.25 s bound (`'env -u env -u …'` in a quoted argument) on
python3.12; ≤ 0.93 s on `/usr/bin/python3` 3.9.6. The suite pins 14 of them under
5 s each.

## Honest controls (ALLOW)

Bound and unbound as appropriate, through the real `guard_bash`: faithful plain
launch; trailing `> /tmp/lane.log 2>&1 </dev/null`; inherited bare launch;
`env … nohup nice -n 5 timeout 90m pool run …`; `/usr/bin/env …`; `python3 …/slot.py
glm -- run` (also `python3.12`, `python`, staged path, `SLOT.PY`); `pool remote
mini2 glm …`; `sub.sh`/`remote_sub.sh`; continuation-split `pool ru\⏎n`; quoted
`'run' "glm"`; `bash -c` / `sh -c` / `/bin/bash -c` (with comment, continuation in
the body, trailing redirection); `pool status` and `sub.sh __launch_plan` (with a
binding); `cat sub.sh`, `grep -n 'pool run' … | head -5 2>/dev/null`, `ls -la
~/.local/bin/pool 2>/dev/null`, `echo pool >&2`, `wc -l < sub.sh`, `gh pr view`,
`python3 -m pytest …`; the 26 carve-out reads (bound AND unbound). Also all 16 r6
admit controls (`test_r6_admit_rule_admits_the_closed_grammar`) unchanged.

## Behaviour changes vs r6 (intentional)

- A wrapper-head unit always reaches the gate: `pool status`, `pool plan`, `sub.sh
  __launch_plan` in an armed session need a valid binding (r6 skipped them).
- Read forms never reach the gate: `grep 'pool run' …` no longer needs a binding.
- Refused now: redirection before/among arguments; read-form writes; launch writes
  into dot-paths; `/dev/tcp|udp`; `xxd`; `tail -f`; `file -C`; ugrep
  filter/pager/config options; leading-glob args to option-sensitive read heads;
  uppercase or non-system-path prefixes/shells/python/read heads; zsh `<N-M>` and
  `>!` forms; identity values with unquoted `~`/glob or not exactly the projection
  (e.g. trailing space); any disagreement between parse and text census (e.g. task
  text naming a wrapper: pass it in a packet file); armed commands > 262 144 chars.
- Admitted now: the git/rg/sed read forms.
- Unarmed: launches the text regex missed now get the legacy identity check.

## Known limits (not claimed closed)

1. **Arbitrary-process limit.** A command naming no wrapper is out of scope: wholly
   computed words (`$W run …`, `$(printf '\160…') run …`), wholly wildcard operands
   (`python3 *.py`, `bash *.sh`), homoglyph names, binaries/scripts that launch
   internally. r7 widens scope cheaply (finding 4 + glued options + glob heads); it
   cannot close this lexically.
2. **Staged-file limit.** Anything staged by an EARLIER command and run later: a
   function in `~/.zshenv` (sourced by every `zsh -c`; r7 stops read forms and
   launches from writing it, but an out-of-scope command such as `printf '\160ool()…'
   >> ~/.zshenv` still can), a binary named `pool`/`env`/`cat` earlier on PATH
   (including principal-writable PATH directories such as Homebrew's), a fake wrapper
   or `slot.py` at the explicit path a launch names, git config/hooks/attributes
   (`core.fsmonitor`, `diff.external`, filter drivers, `core.hooksPath` — run by the
   git read forms exactly as by any out-of-scope git command), an rg/ugrep config
   file.
3. **Provider-side environment.** The Bash tool sources a shell snapshot (functions
   such as `grep`→ugrep, aliases incl. zsh global aliases) and inherits session
   variables (`PATH`, `RIPGREP_CONFIG_PATH`, `GIT_*`, `PYTHONPATH`, …). The guard
   checks only `BASH_ENV`/`ENV` (NESTED). `command pool …` bypasses functions; plain
   `pool …` does not.
4. **Wrapper semantics.** What the admitted wrapper does with its literal arguments is
   its contract: `slot.py <pool> -- <command…>` runs `<command…>` under the slot
   (argv, not shell — a tail naming a wrapper is refused by the census cross-check,
   a tail that launches internally is limit 1); `pool request` goes through Executive
   admission and is not counted as a paid launch.
5. **Hook contract.** The fail-open-by-timeout/crash analysis relies on Claude Code's
   documented hook semantics (only a deny/exit 2 blocks); not re-verified against a
   live provider in this lane. r7 bounds time and fails closed on internal errors;
   it cannot stop a provider that skips the hook.
6. **Over-refusal (honest direction).** `pytest -k pool`, `which pool`, `command -v
   pool`, `cd x && launch`, trailing `;`, `gh … | grep pool`, task text naming a
   wrapper, uppercase command names, CRLF.
7. **Unarmed sessions** keep the legacy identity checks only.

## Commands and counts (lane head)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest tests/test_provider_orchestrator_policy.py \
  tests/test_mmos_admission_to_t3_native_e2e.py tests/test_mmos_negative_matrix.py \
  tests/test_ceo_submit_armed_composition.py $(grep -rl "provider_orchestrator_guard\|guard_bash" tests/)
  → 1140 passed, 3 skipped (pre-existing), 1 xfailed (pre-existing strict xfail), 29 subtests passed
    (nm15 green; d8 identity scan green)

tests/test_provider_orchestrator_policy.py → 662 passed (325 pre-existing, unchanged + 337 r7)

fail-before (r6 guard = git show 29a82f779:ops/executive_os/provider_orchestrator_guard.py > /tmp/r6_guard.py):
MASTERMIND_R6_GUARD_UNDER_TEST=/tmp/r6_guard.py env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest \
  tests/test_provider_orchestrator_policy.py -k "test_r7_review2_table_bound_nobind_and_gate or \
  test_r7_r6_table_rows_with_gate_instrumentation or test_r7_real_hook_command_line or \
  test_r6_reviewer_adversarial_shape_table"
  → 69 failed / 225 passed  (REVIEW2 table 57/88, hook CLI 12/16, r6 rows 0/95, C3 table 0/95)
```

## Open / next dependency

- Fresh distinct read-only re-review of this delta (CRITICAL row), against
  REVIEW2's tables and the S1 hook-budget finding.
- Integrator: S1 also applies to any other copy of the guard installed before r7
  (verbatim-copy deployment); installing r7 is a separate, owner-run step.
