# Rakazo qualification (HC-P1B.T1)

Pinned source: [elie222/rakazo](https://github.com/elie222/rakazo) `c5e66e010ee3f3166d2ad216f928a75a0b9a2218`, Apache-2.0. The tree is fetched at test time and is not vendored. Declared contract/runtime dependencies used to load those modules are `zod@4.6.7`, `@orpc/contract@1.15.7`, and `croner@10.0.1`.

```bash
npm test --prefix integrations/rakazo_qualification
```

`tests/test_rakazo_qualification.py` runs that command. Set `RAKAZO_SOURCE` to an existing checkout of the same commit to skip the fetch.

Observations come from the pinned modules. `db_client_stub.mjs` and `row_security_stub.mjs` only let `packages/db/src/computers.ts` evaluate. They are not a database, and Postgres, Graphile Worker, Docker, and the donor API are not adopted as company authority.

| Case | Test |
| --- | --- |
| Pin, license, dependency identity | `pinned Apache-2.0 source is the only admitted Rakazo identity` |
| Two bot identities | `two bot identities stay distinct on private computers and share one team computer` |
| Conversation | `conversation keeps each bot's history and does not treat a routine as the conversation` |
| Routine | `routine schedule and inbound prompt stay owner-authored` |
| Private versus shared computer visibility | `private computers hide paths that a shared computer exposes only through shared/` |
| Effect approval | `effect approval pauses a ruled side effect and keeps one effect identity across replay` |
| Disconnect recovery | `disconnect recovery rebuilds the retained thread and does not replay a cancelled run` |
| Streaming and cancellation without replay | `streaming folds one live reply and cancellation drops it without replay` |
| Restart persistence | `restart keeps a failed run and the same workspace path` |
| Unsupported: Cordis plugin load, Postgres/Graphile product journey, signed-in UI | `unsupported capabilities stay explicit` |

Missing proof, recorded by that last test: authenticated UI, database-backed product journeys, Cordis plugin load, a live model provider, and the 24-hour and seven-day observations.
