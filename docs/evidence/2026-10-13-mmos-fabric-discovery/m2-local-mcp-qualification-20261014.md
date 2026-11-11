# M2 local Fabric MCP → OS catalog contract qualification

**Scope:** read-only qualification of the already-running, source-matched M2 Fabric service and the existing app consumer. This is not OS user authorization, a new worker request, authenticated remote tunnel proof, global fleet discovery, backend implementation, or permission to release #1426.

## Original sources and identities

- M2 hostname: `m2studio`.
- Installed gateway service: `subagent-fabric-c3`, loopback port `45119`; actual running process observed. Its installed `fabricOnly=true`, Git publication and Paper routes disabled.
- Installed `fabric-backend.mjs` SHA256: `a34bd21065b64aef68af26fa3c37b310f861d7a5c4545adca52f5c07de5c56c6`, exactly matching the Fabric backend at the protected merge of #1359 (`76576d8680bb70cdb9e1cfe7016aefec0fb3286f`). Installed manifest's backend hash verified.
- Actual MCP Streamable HTTP SDK initialization succeeded on `127.0.0.1:45119/mcp`. Seven explicit `fabric_*` tools listed; `fabric_capabilities` returned `adapter_available=true`, `worker_admission=UNPROBED`, `worker_start=UNPROBED`.
- Through the same running MCP service, `fabric_status` for two **existing** owner-confirmed runs returned `root_verified=true` and `TERMINAL/rc0/ok`. Review run `mmos-fabric-interiors-review-20261013-c4-02` remained `ACCEPTED`, with result available and 11,052 bytes; existing earlier canary `fabric-mcp-web-20261011-c3-check-01` remained `NOT_ACCEPTED` with result available and 3,672 bytes. Neither content was read, no worker started, and no acceptance action was invoked.

## Consumer contract evidence

A **metadata-only**, intentionally PARTIAL exact-run-set catalog fixture was built from those two installed-server observations, with `source.scope=EXACT_RUN_SET`, `atomic=false`, `revision=null`, `scan_complete=false`, `candidate_count=null`, and `omitted_count=null`. It does **not** pretend to enumerate the machine fleet or invent a complete source revision.

The source fixture is `app/mastermind_os/src/fixtures/fabric-catalog-m2-status-observation-20261014.json` and the discriminating tests are `app/mastermind_os/src/fabric/catalog-m2-status-observation.test.ts`. These prove that the current strict `decodeFabricCatalog` and `decodeAttendedStatus` accept actual, distinct `ACCEPTED`/ `NOT_ACCEPTED` status semantics, reject false promotion of the incomplete sample to `AVAILABLE`, and reject contradictory identity and acceptance metadata. Focused run: **23 passed across two files**, TypeScript `tsc --noEmit` passed.

This establishes **local source → source-shaped metadata fixture → frontend decoder** compatibility. It does not establish an OS server-side producer, a signed-in principal entitlement or an authenticated user-facing live read. The installed MCP wrapper is `mastermind.fabric_mcp.v1` with a nested `status` object; the eventual OS server source owner must extract/protect only the status-v1 allowlist *behind the OS acquisition grant*, not surface the machine-owner trusted channel to the browser.

## Remaining transport/authorization gates

- Remote C3 tunnel `tunnel_6aced2fc0d1481919ef1cf868cdc2720` was found in the C3 admin-profile remote inventory for workspace `570f6f34-c906-4c90-a1c1-7c8c33ef124e`. The local `subagent-fabric-c3` **managed tunnel** profile still reports `running=false`, `ready=false`, and `tunnelId=null`; only the loopback gateway is running. Do not claim remote ChatGPT connection or individual account selection.
- The separate pre-staged `fabric-chatgpt3-w570f6f34` Fabric-only gateway is **not running**. Do not start or replace this as a workaround. No credential reference was changed, guessed or reused.
- A pre-existing unrelated C3 tunnel manifest returned `corrupt tunnel manifest` when queried using an old helper; this is an observation only, not permission to clear or restage it.
- #1359 owns existing Fabric MCP bridge/tunnel source. #1426 owns OS presentation. The missing shared OS-principal read admission and exact authorized run-set membership require the actual OS access/source owner. Run/root selectors and an already-working trusted-channel MCP status are **not** user authorization.
- Earlier platform refusals for shared backend contract creation, independent review dispatch, Playwright browser proof and focus mutation remain held; none was retried or rerouted during this qualification.

## Next safe milestone

Owner of the existing C3 tunnel must reconcile its original remote alias, exact profile/account and approved per-tunnel runtime-key reference before binding to the already-running reviewed gateway. The existing OS-auth owner must qualify machine/individual principal grants for a bounded run list, then produce the catalog and status over an authorized existing read path. Source/CI review, fresh browser proof, actual installation and selection remain separate. Preserve original source owners and do not create a second broker, queue, credential or lifecycle plane.
