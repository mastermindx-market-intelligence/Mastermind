# Distinct CRITICAL review #2 — guard r6 + v1.1 allowlist, G2/M pin moves, namespace reconciliation, constraints

Reviewer: Claude Opus 5.5, READ_ONLY, capacity_fabric path, distinct from every author (C3 Opus, G2/M GLM, Fable integrator).
Reviewed at HEAD `c742e9fc0`. Technical assessment, not a GitHub approval.

| Row | Verdict |
|---|---|
| A1 guard r6 (#2329) | **NEEDS_REWORK** — 1 BLOCKER, 2 MAJOR, 3 MINOR (gaps present in r4/r5 too; r6 claimed them closed) |
| A2 v1.1 schema allowlist | ACCEPT_WITH_MINORS (sound; nm15 test was red at the reviewed head — fixed `07748bdbe`) |
| B1 G2 pin moves | ACCEPT_WITH_MINORS (every pin verified; ledger hunk counts/placeholders corrected) |
| B2 G2 route fence | **ACCEPT** |
| B3 M pin moves | **ACCEPT** (master itself red on `integrations/hermes_attended_fabric/native.py` pin at `85179e35c` — needs the same fix on protected master) |
| C namespace story | ACCEPT_WITH_MINORS (two minors fixed by the integrator) |
| D hard constraints | ACCEPT_WITH_MINORS (see routes JSON note) |

Ran: guard policy 325 passed; C3's 95 rows through the real `guard_bash` bound/unbound (95/95 match); 129 NEW shapes;
real hook command line 11 shapes × bind/nobind; 9 shapes against r4/r5/r6; v1.1 E2E probe 13 cases; namespace matrix 7;
G2 route/projection/pins 339 passed; E2E/claim/lease/contracts/adapter/durability/return 270 passed / 1 failed (nm15, since
fixed) / 107 subtests; guard consumers 186 passed; d8 321 passed; `native.py` pin against current master fails
(`7b6d14ea… != 9b26d8e1…`), passes at HEAD; 3-way `git merge-file` vs #2177 `70a6cf453`.

## A1 — guard r6
Root cause: the r6 lexer understands redirections anywhere, but the BINDING GATE still finds launches with text regexes that
expect wrapper and mode adjacent (`_WRAPPER_ARG_RE`, `FABRIC_LAUNCH_RE`); when neither matches, `guard_fabric_launch`
returns early before `validate_execution_binding` runs. "What r6 admits still goes through the binding gate" is false.
1. **BLOCKER** zero binding check: armed, NO binding — `pool </dev/null run grok a /tmp grok-4` ALLOWED via the real hook
   command line (the honest plain launch is DENIED). Same: `pool 2>&1 run …`, `pool 0<&- run …`, `pool r''un </dev/null …`,
   `sub.sh </dev/null grok …`, `remote_sub.sh </dev/null host grok …`, `python3 …/slot.py </dev/null grok …`,
   `bash -c 'pool </dev/null run grok …'`. Fix: drive the gate from the r6 parse; never early-return for a launch-form unit;
   enforce grammar order (redirections trailing only, `R6_REDIRECTION`); seam rows as DENY regressions.
2. **MAJOR** provider substitution unchecked with a faithful binding: `pool run </dev/null grok …`, `>/tmp/cat pool run grok …`
   (redirect target basename read as inspector head), `POOL_TASK_CLASS='code cat' pool run grok …`.
3. **MAJOR** identity projection via lossy readers: `POOL_ORCHESTRATOR_ID="root-orch-1"' evil' pool run glm …` admitted while
   the child receives `root-orch-1 evil` (zsh+bash); env-prefix/nested/`POOL_PARENT_RUN_ID` forms alike. Fix: compare the
   lexer's exact literal values against `_expected_projection`.
4. MINOR scope: `${x:-pool}`, `${x-pool}`, zsh `${:-pool}`, bash `p$""ool` launch with zero binding check.
5. MINOR inspector form admits arbitrary output redirections (`echo '…pool…' >> ~/.zshenv` — the Bash tool runs `zsh -c`).
6. MINOR every admitted head judged by basename (`/tmp/evil/env`, `./nohup`, `/tmp/evil/bash -c`, `python3 /tmp/evil/slot.py`).
Notes: lexer models bash, tool runs zsh (`$"…"`, `${:-…}`, `<1-9>` divergences); `grep` is a snapshot function to ugrep;
tokenizer failures refuse. Over-refusal confirmed (`git commit -m "fix pool"`, `pytest -k pool`, `rg`, `sed -n`, …); the
"wrapper only as command word" idea is UNSAFE; safe carve-out = closed read forms with option allowlists (git log/show/diff/
status/grep/add and `commit -m/-F` without exec-capable options; `rg` without `--pre*`/`-z`/`--hostname-bin`; `sed -n` with
a literal `^\d+(,\d+)?p$` script). T-1..T-10 clean. Coverage gap: binding-check test only exercises trailing redirections.
Real hook command line (verbatim): `pool run glm …` bind DENY(receipt)/nobind DENY(missing binding); `pool </dev/null run
grok …` ALLOW/ALLOW; `pool 2>&1 run …` ALLOW/ALLOW; `/opt/x/sub.sh </dev/null grok …` ALLOW/ALLOW; `python3 /opt/x/slot.py
</dev/null grok -- run` ALLOW/ALLOW; `bash -c 'pool </dev/null run grok …'` ALLOW/ALLOW; `pool run </dev/null grok …`
DENY/DENY; `${x:-pool} run grok …` ALLOW/ALLOW; `POOL_ORCHESTRATOR_ID="root-orch-1"' evil' pool run glm …` DENY/DENY;
`f() { pool run glm …; }; f; f` DENY R6_*; `cat /opt/x/sub.sh` ALLOW/ALLOW. r4/r5/r6 agree on every row above (the gaps
predate r6). **Disposition:** Director C5 (Opus) — r7, gate driven by the parse, all rows as regressions, carve-outs; fresh
distinct re-review of the A1 delta afterwards.

## A2 — v1.1 allowlist
Sound: identity projection, token equality, fence and one-launch law read only v1 fields. E2E probe: plain launch allowed;
substitution, re-root, second launch, stale fence, empty `pool_ref` denied; labels `v1.2`/`V1.1`/`v1.1 `/`v2` denied.
Minors: no end-to-end `guard_bash` test with a v1.1 binding (→ C5); presented env binding may differ from the owner's
receipt on v1.1-only fields with no effect today (nothing else reads `POOL_EXECUTION_BINDING`).

## B — pins and fence
B1: both G2 sha256s match at `d3f4de3a7` and HEAD; all 12 sites resolve to the same token with byte-identical line text;
the ingress anchor's protected 136-node branch is AST-identical across `70dabba15`/`d3f4de3a7`/HEAD; nothing deleted/skipped/
xfailed/widened. Ledger corrected (app.py +7, read service +4/+4/two signature edits, executive_service import+elif+set-line,
commit `108e84da3`). B2: one route in `_WORKSPACE_ADDITIONAL_QUERY_GET_ROUTES`, same HTTPS/Host/Origin fence, strict single
`attempt_id`, all four frame gates fail closed (installed client's fallback `contract.validate_frame` → `invalid_input`).
Note: attempt-id grammar admits `runs/../../etc/passwd`; used only as an equality filter (harmless). B3: `auth.rs`
`612e97c9…` sites 3812/3817/3821 byte-identical to master's and ours; `native.py` `7b6d14ea…` sites 57/280 match pre-#2365
lines; master red on that pin at `85179e35c`.

## C — namespace story
Consistent: claim stamps `operation_key` and forces `caller_namespace=""` in the claim transaction; adapter refuses an
unattested port and persists `fixed:principal`; return wiring reads the persisted namespace; no caller field reaches key or
namespace; E2E proves exactly one launch through the real runtime chain and admission-level replay never re-mints.
Minors (fixed by the integrator, same session): C-1 `_verify_binding_join` admitted the bare pinned namespace while the
launch carries `fixed:principal` → now admits only `{"", t3_request_namespace(principal)}`; C-2 return wiring fallback to
`binding.caller_namespace` dropped. C-3 coverage: no E2E drives an adapter-level lost-reply reattach with a runtime-issued
binding (unit-tested only).

## D — constraints
#2177: C's and C2's `executive_runtime.py` hunks have no #2177 hunk within 40 base lines except #2177's
`native_terminal_digest` insert 20 lines above the C2 `_terminal` seam (auto-merges; seam intact); 3-way merge vs
`70a6cf453`: 2 conflicts at HEAD vs 1 at master `ff6d5ab67`, the extra from `a436b7c71` ("child-request ready caps atomic",
pre-lane). **Routes JSON:** differs from master by +14 lines from branch commit `81f0ef906` (WO-18, 2026-11-08): a `hermes`
row with `enabled`, `autonomous_allowed`, `production_armed` all TRUE and a disabled `deepseek` row — predates every lane;
whether it had its own distinct review is UNKNOWN — the release lane (Hermes) must settle this before master. Secrets/identity
literals: none (d8 321 passed).
