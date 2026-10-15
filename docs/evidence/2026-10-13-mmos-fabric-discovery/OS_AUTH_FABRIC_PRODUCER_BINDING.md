# Mastermind OS — authorized Fabric observation binding

**Purpose:** an exact implementation/acceptance contract for the original OS access and Fabric runtime owners. **Not an authorization grant, second service, source modification or release instruction.** This only identifies current accepted owner seams and the missing permission proof, now that #1359's local Fabric MCP service is functioning.

## Existing source owners (protected Mastermind observation `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`)

1. `integrations/mastermind_workspace_app/app.py::WorkspaceAppConfig`: existing pinned `JwtAuthenticator`, `authorize_principal` and async `client.request`. Constructor verifies the exact workspace resource and `mastermind.workspace.read` scope. Existing `_dispatch_v2` authenticates the bearer, rejects request bodies and ambiguous selectors, performs first authorization and permission stamp, dispatches a bounded owner frame, then rechecks token expiry, owner authorization and permission stamp before publishing a no-store JSON result.
2. `control_plane/workspace_read_service.py::WorkspaceReadService`: already constructed by the trusted host with the pseudonymous principal authorizer, current source/Runtime owner and injected readers. It owns request admission, permissions and typed source failure; arbitrary HTTP input cannot supply constructors or a new runtime reference.
3. `common/executive_workspace_contract.py::permission_stamp`: the actual current sealed authorization receipt, to be reused and revalidated, not replaced by user-selected run/root labels.
4. `ops/executive_os/os_public_edge.py::GET_ROUTES`: production public edge's fixed allowlist currently contains Mission v3, Result and Work reads but **no Fabric catalog/status route**. New public routes must enter through that existing release owner only after a corresponding reviewed authenticated app path exists; never use generic unrestricted proxying.
5. `app/mastermind_os/src/web-auth.ts`: `read('acquisition', fixed url, signal)` already handles existing OAuth bearer custody, no-store, abort, bounded JSON and generation fencing for the workspace resource. `host.ts` defines optional `readAttendedFabric` and `readAttendedFabricCatalog` ports but deliberately wires **no default producer**. Native Tauri has its own fixed HTTPS owner and requires separate wiring and proof.

## What the already-working M2 runtime can and cannot attest

Installed `subagent-fabric-c3` service on M2 is Fabric-only, loopback MCP alive, installed backend SHA256 matches #1359's protected merge. Actual `fabric_status` returns `mastermind.fabric_mcp.v1` as its **machine-owner envelope**, with a nested `mastermind.fabric_task_status.v1` metadata record, the requested `expected_root_id` and a `root_verified` equality result. Its authority is the trusted local machine owner. Neither its `root_verified` equality nor the caller-supplied `run_id` proves an **OS user's right to inspect another session**. The current MCP has no individual OS principal or owned-run selector and must not be mounted directly into the browser.

The strict OS consumer `mastermind.attended_fabric_catalog.v1` accepts at most 32 sanitized run metadata rows, null/partial coverage and only existing status-v1 fields. A real two-run local-MCP metadata fixture passed the current catalog/status decoders without marking accepted/unaccepted results equivalent. This proves parser compatibility, **not** global discovery, user authorization or a live browser read.

## The missing admission edge — must be supplied by the existing owner

A verified `VerifiedPrincipal` with `mastermind.workspace.read` is necessary but **not sufficient** for access to a machine-owner run. The source owner must supply an authorized run-set membership proof tied to that very principal, the existing organizational responsibility/Executive root (where one exists), original Fabric run and immediate parent, plus current binding/lease/effect ownership. Do not infer membership from shared host, label prefixes, literal root equality, browser selection, or the assumption that a Chairman seat always authorizes every run. No second run registry or arbitrary per-browser allowlist is authorized.

If the current owners cannot prove such membership through an existing canonical record and verified permission generation, the safe server response is a fixed denied/unavailable envelope with no Fabric data. That is an actual missing upstream authority edge, not a request to weaken auth. To unlock it, the owning Executive/Agent OS admission source must publish the narrowly scoped principal-to-original-run membership via its existing projection and revision/revocation witness; production placement remains Capacity/Fabric-owned. Scope the first canary to explicitly qualified existing original run IDs, **not a global machine fleet enumeration**.

## Minimum safe producer and consumer acceptance

Once the original owner establishes the above authorization source, extend the **existing** workspace read/HTTP/edge owner. Preserve the full v2-style pre/post authorization and sealed permission-stamp checks. Require an exact closed selector, reject query/body ambiguity, and requalify the **same principal + original run-set association** after M2 read and before publishing. Normalize the machine MCP envelope to *only* status-v1 metadata; strip prompts, hidden output, controller paths, credentials, raw errors, arbitrary provider stdout or model text. Never allow a browser to supply controller PIDs, arbitrary paths, account/host/model selectors or Fabric command names.

The catalog response must qualify its observation source/time, actual candidate/omitted counts when known, sequential/non-atomic coverage, partial/unknown missingness, and no claimed unique global worker census. A present result is not acceptance; terminal/rc0 is not acceptance; active-or-waiting is not worker START. `EFFECT_UNKNOWN` is never safe for retry. The app still explicitly triggers load/read; selection never launches or accepts.

Required discriminating tests and real path proof:
- Absent/mismatched/read-only-but-unentitled/expired principal: **no M2 acquisition**, generic 401/403, no payload.
- Principal or authorized run-set revocation during the async read: no stale response, closed refusal, no change to underlying original Fabric run.
- Guessing a sibling run/root or using an empty/duplicated/encoded selector: fixed refusal; never infer authorized association.
- Partial/corrupt/unavailable M2 status or concurrent controller movement: typed source limitation, zero credentials/logs leaked, no fabricated idle/healthy inference.
- Bound `<=32` source rows and response size, strict status-v1 identity and acceptance invariants, accepted and nonaccepted original run test.
- Existing web OAuth acquisition and separately governed native credential/host bind each produce a valid read for an **authorized** principal; anonymous access and unauthorized sibling reads do not.
- Actual signed-in app browsing → selected run → separate explicit detail read → sign-out/rebind clears content; browser proof and deployed edge provenance required.

**Gated execution order:** principal/run membership producer evidence → actual current-owner authenticated service integration and isolated tests → closed public edge + approved web/native clients → exact-source independent review and protected release → signed-in and signed-out browser/production proofs. Do not create/reuse an unauthorized tunnel key or treat #1359's M2 trusted channel as a public app grant. Earlier platform refusal on the shared backend-contract write remains a stop on that exact operation; this packet is read-only architecture evidence, not a replay or replacement writer.

## Live state / source refs

- Parent source [#1411](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1411) merged; OS catalog consumer [#1426](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1426) remains Draft/Hold, source head to reconcile.
- M2 MCP source [#1359](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1359) merged; local service running and read-only-proven; **remote C3 managed tunnel not running**.
- Actual M2 local status and consumer proof: `docs/evidence/2026-10-13-mmos-fabric-discovery/m2-local-mcp-qualification-20261014.md`.
- Existing source owners, protected pins and effects survive this handoff. Product mission **NOT COMPLETE**.
