# Distinct CRITICAL review #4 — guard r8, C7 composition r2, native.py pin move

Reviewer: Claude Opus 5.5, READ_ONLY at `798152b7c`, distinct from every author (C6 Opus, C7 GLM, integrator). Technical
assessment, not a GitHub approval. **r8 is strictly better than r7:** over 5,274 commands bound and unbound, 0 verdicts went
deny→allow and 46 went allow→deny (all intended).

| Row | Verdict |
|---|---|
| A1 S1 closure / budget | **ACCEPT** — every review #3 input ≤0.21 s at the cap through the real hook CLI (fail-before r7: 5.18 s @40K, 6.93 s, 2.71 s); 45 new adversarial shapes at 262,144: worst launch-path case 1.39 s, none >2 s; post-gate CI-wait shapes hit the watchdog DENY at 7.06–7.09 s |
| A2 watchdog | **ACCEPT** — armed only; override only downward (floor 1 s, `inf`/`1e309`/`-inf` handled); 300 racing runs: exactly one JSON object each; stalled stdin → DENY; real hook process has SIGALRM at SIG_DFL |
| A3 `onFailure` row + validator | ACCEPT_WITH_MINORS — live zero-spend matrix: 2.1.319/2.1.296 block on timeout and exit 1 with the key (RAN without it); 2.1.287 ignores the key; exit 2 blocks regardless; validator reports DRIFT without the key. **F4** availability: watchdog armed-only → unarmed adversarial `gh` text stalls 10 s and is now BLOCKED (honest gh ≤0.15 s). **F5** deployment: the installed `~/.claude` row is the broad Oct-20 one (27 KB guard, no `onFailure`) — owner must re-run `apply_policy`; never hand-add the key to the broad row |
| A4 scope escapes | **NEEDS_REWORK** — **F1 MAJOR** quote-adjacent glue out of scope: `${x:-p}"ool" run grok …` ALLOWED armed/unbound (sealed zsh -f and bash --norc both run `pool run grok …`); cause `_R6_ROUGH_WORD_SPLIT_RE` treats quotes/backslash as separators (used by `_r8_computed_glue` and the partial-word reader). Pre-existing in r7 (13/13 rows identical). Depth note: honest `echo $(…)` chains enter scope at k=10, ledger said >8 |
| A5 git carve-out fix | **ACCEPT** (93 rows; every reviewer shape refused; honest forms admitted; env-prefix forms refused as `R6_ASSIGNMENT`) |
| A6 regressions | **ACCEPT** (95/95 r6 rows; 88/88 REVIEW2 rows; 100/100 r8 tests; 1083 guard+d8; review #3's 150 shapes UNKNOWN — replaced by the 5,274-command differential) |
| B1 composition r2 | ACCEPT_WITH_MINORS — **F2** non-UTF-8 token file still crashes the service (`UnicodeDecodeError` not caught); **F3** broken-enrollment reason surfaces only as an ERROR log (seam returns `{}` for NOT_ENROLLED and BROKEN alike) |
| B2 constructor-law calibration | **ACCEPT** (one new site; follows #2365's predecessors' precedent) |
| B3 transport | **ACCEPT** (32 barrier threads: initialize=1; 404 → typed, no retry/re-init; 301/302/303/307/308 → typed, 0 requests to the target; proxies ignored — control urlopen DID leak the bearer) |
| B4 bridge twin check | **ACCEPT** (16/16 forgeable fields refused before the inner adapter; on-loop refused; `to_thread` accepted) |
| B5 scope-roots conclusion | ACCEPT_WITH_MINORS — **F6** "no env-passing seam" is literally true but operationally wrong: `modelSelection.instanceId` selects a provider instance whose `environment` (`providerInstance.ts:79`) is merged into the Claude process env (`ClaudeHome.ts:82`) and inherited by hooks; cwd is selectable via `projectId`/`workspaceStrategy`. A dedicated t3-native provider instance can carry `MASTERMIND_SCOPE_ROOTS` + the binding env; no upstream patch needed (not verified live) |
| C pin move | **ACCEPT** (rows byte-identical; #2365 single hunk adds 9 lines above; origin/master `12146bdb4` red on this test, reproduced) |

Hard constraints: r8 touched only the guard, the policy module (constant, `_hook_row`, `_managed_hook_count`), guard tests, ledger; 0 test lines removed. C7: phase1c, executive_runtime, executive_supervisor, routes, t3 adapter unchanged. 84-file phase1c sweep: 80 failures identical at base and head (environmental: ownership, launchd, canary, fs device, realm digest).

**Integrator disposition (Fable):** F1 + F4 → Director C8 (Opus, r9); F2 fixed (non-UTF-8 → `T3_ENROLLMENT_BROKEN`, test); F3 recorded as a canary want (typed status field) — owner decision; F5 and F6 recorded as owner-side preconditions in the #983 handoff (re-run `apply_policy`; dedicated t3-native provider instance carrying scope roots and binding env); `onFailure: "block"` pin KEPT (fail-closed).
