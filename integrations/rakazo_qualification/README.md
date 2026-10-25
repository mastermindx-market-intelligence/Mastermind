# Rakazo qualification (HC-P1B.T1)

Pinned source: [elie222/rakazo](https://github.com/elie222/rakazo) `c5e66e010ee3f3166d2ad216f928a75a0b9a2218`, Apache-2.0. The tree is fetched into an attempt-owned directory at test time and is not vendored. Declared contract/runtime dependencies used to load those modules are `zod@4.6.7`, `@orpc/contract@1.15.7`, and `croner@10.0.1`.

```bash
python3 -m pytest --noconftest tests/test_rakazo_qualification.py
```

That pytest entry is the admitted launcher. Before the first `npm test` / Node process it sets `env=` to `qualification_launcher_env`: `PATH` copied from the surrounding process, plus `HOME`, `TMPDIR`, `LC_ALL=C`, `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`, `GIT_NO_REPLACE_OBJECTS=1`, an empty owned `npm_config_userconfig`, `npm_config_globalconfig=/dev/null`, an owned `npm_config_cache`, and `npm_config_ignore_scripts=true`, `npm_config_audit=false`, `npm_config_fund=false`, `npm_config_update_notifier=false`. `NODE_OPTIONS` and ambient npm config are not forwarded. `npm test` then runs `node ./run-tests.mjs`, which refuses `NODE_OPTIONS` or a canary npm registry/userconfig before checkout.

`RAKAZO_SOURCE`, when set, must already be that commit with a clean worktree. A symlink alias is bound to its canonical realpath before import. The source is read and checked before import, and it is never deleted. A fetch uses a new `rakazo-qualification-*` directory and removes only that directory when the fetch or the source check fails.

Git validation uses that same explicit environment, `GIT_NO_REPLACE_OBJECTS=1`, and per-invocation `-c` overrides (`core.fsmonitor` empty, `core.fsmonitorHookVersion=0`, `core.hooksPath=/dev/null`). Those overrides do not write the caller's git config. Worktree bytes are hashed with `git hash-object --no-filters`. Ignored and untracked `.js` siblings of tracked `.ts` files are rejected before import.

Observations come from the pinned modules. `db_client_stub.mjs` and `row_security_stub.mjs` only let `packages/db/src/computers.ts` evaluate. They are not a database. Postgres, Graphile Worker, Docker, and the donor API are not started and are not adopted as company authority.

| Case | Test |
| --- | --- |
| Pin, license, dependency identity | `pinned Apache-2.0 source is the only admitted Rakazo identity` |
| Modified source rejected before import | `tampered donor source is rejected before import` |
| Replacement refs and clean filters | `replacement refs and clean filters do not change the pinned tree` |
| fsmonitor and local git config | `fsmonitor and local git config do not run during validation` |
| Symlink root and ignored transitive shadow | `a symlink root and an ignored transitive shadow are rejected before import` |
| Unowned path survives a rejected lookup | `an unowned sentinel path survives a rejected lookup` |
| Ambient env does not leak | `unrelated environment variables do not leak into execution` |
| Outer launcher env | `qualification_launcher_env` in `tests/test_rakazo_qualification.py` |
| Two bot identities | `two bot identities stay distinct on private computers and share one team computer` |
| Conversation | `conversation keeps each bot's history and does not treat a routine as the conversation` |
| Routine | `routine schedule and inbound prompt stay owner-authored` |
| Private versus shared computer visibility | `private computers hide paths that a shared computer exposes only through shared/` |
| Approval rule and effect key | `approval rules resolve ask or allow and identical arguments keep one effect key` |
| Connection classification and fabricated event projection | `connection failures classify reachability and a fabricated event log projects the same messages` |
| Streaming preference and fabricated progress | `streaming preference and fabricated progress deltas fold into one projection` |
| Fabricated cancel projection and status transition | `a fabricated cancel event clears that progress projection and forbids cancelled to running` |
| Failed-status transition and repeated path function | `a failed status may return to queued and the workspace path function repeats` |
| Cordis ABSENT versus NOT_RUN proofs | `Cordis absence is distinct from NOT_RUN process, disconnect, and database proofs` |

`NOT_RUN` covers process restart, a real disconnect/stream/cancel, committed-effect deduplication, the database-backed product journey, signed-in UI, a live model provider, and the 24-hour and seven-day windows. Cordis is `ABSENT`: `git grep -I -l cordis` finds no host in the pin. The database journey stays skipped until `VERIFY_DATABASE=1` and `DATABASE_URL` are both set for `packages/testkit/src/journeys.test.ts`. This package does not install or start that Postgres.
