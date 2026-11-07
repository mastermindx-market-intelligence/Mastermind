# ACP common-worker integration

`AcpReadOnlyTurn` uses the official `agent-client-protocol==0.12.1` SDK.
`AcpWorkerAdapter` connects that turn to the existing Executive worker contract.
The existing broker can consume start, status, collect and cancellation without
a second broker, queue, lifecycle, credential store or provider retry mechanism.

## Current source capability

The adapter freezes the admitted result schema before native resource acquisition,
requires the exact workspace Git base, binds the returned process reference to the
request, and uses the existing JSON-schema and Git validation implementations.
A successful collection returns the existing `WorkerResult` and `CollectionReceipt`.
Wrong identity, changed workspace, nonempty artifacts or unvalidated output cannot
be promoted to success. A protocol terminal alone cannot release the lane.

Cancellation requires the terminal response to the original prompt plus the native
owner's matching cleanup receipt. Lost RPC responses, exceptional prompt completion,
unsettled SDK tasks or unresolved native cleanup preserve effect uncertainty and
quarantine the adapter. No automatic resubmission, account switch or host failover
is implemented. A first-profile native validation request is refused: the profile
grants READ/RESEARCH, not arbitrary execution or RUN_TESTS.

## Shared framing dependency

This source composes the unchanged `StrictFrameReader` and `ProbeClient` from
PR #575 (`c9d9ee2789ee78bdf957c2a604f7f986a99dc92a`). Their original author and
qualification operation remain separate. No parallel JSON-RPC parser was added.
The first combined profile admits text result updates only; richer callbacks are
not silently enabled. Agent/model negotiation remains in the turn driver.

## Native ownership and activation boundary

The trusted host composition must supply `open_run` at adapter construction.
It returns exclusive streams, an attested `WorkerProcessRef`, the admitted schema,
and one bounded `finish` operation from the existing native process owner.
`AcpRunResources` and `AcpProcessCompletion` are private in-process construction
values, not a new wire schema, lifecycle record or caller-controlled permission.
Neither a Job nor a provider may supply these values or choose a resource factory.

**No production native factory is supplied by this increment.** Binary/realm
attestation, dedicated-principal isolation, actual process launch, captured-stream
hashes, terminal process/pipe settlement and restart reconciliation remain native
owner responsibilities. The existing broker owns its stronger UID sweep. The
`acp` descriptor and production routes stay disabled. PR #576 remains the owner
of fixed broker-adapter startup configuration; its files are not changed here.

## Proof and continuation

The two focused modules are `tests/test_acp_worker_turn.py` and
`tests/test_acp_worker_broker.py`. Install `requirements/acp-worker.txt` in an
isolated development environment plus the repository's test dependencies. The
SDK distribution must be exactly 0.12.1; absent-SDK skips are not qualification.
The current check exercised 12 cases with the real SDK and actual broker methods,
using explicit fixture native identities, cleanup observations and UID sweeps.
It does not prove native provider execution, OS isolation, Executive admission,
parent wake/consumption, production installation or browser behavior.

Release requires accepted framing dependency, independent review and current-base
CI. Then the existing native owner must bind a qualified resource factory before
registration or a real provider canary. All current HF/PF/Capacity/provider-auth
gates remain intact; source integration does not waive them.


## DSH per-Attempt MCP tool-profile binding

`createDshGrantedToolProfile` now requires `attemptOverlay` for the closed ACP
`worker.acp.providerfree.readonly.v1` profile. The value is the immutable
`cwd + six MMX_ACP_* environment keys` produced by the **existing**
`AcpInstalledHostPacket.mcp_runtime_overlay(spec, now_ms)`. Its transport
configuration is constructed before the donor MCP client can discover tools.
The transport receives only those six Attempt values plus an explicit fixed
`PATH=/usr/bin:/bin` and `HOME`/`TMPDIR` bound to the same admitted
workspace. The latter two override the pinned SDK's inherited defaults so
it cannot receive the host's credential-bearing home/temp directories.
Ambient provider credentials, `NODE_OPTIONS`, arbitrary environment entries,
config-selected cwd and automatic reconnection are all rejected. The original fixed server
command/argv, MCP schema grant, dispatch guard, AbortSignal and process
lifecycle retain their incumbent owners.

The trusted host's **existing** `isCurrentBinding` callback receives the
frozen `request.attempt` claim at startup, after async preflight, at discovery
and on every tool dispatch. That host must compare it against the live
Executive Attempt/worker/source and revoke on drift; a caller-selected claim
never authenticates itself. The ACP grant cannot start without an overlay.
Other execution surfaces cannot borrow it.

The portable `tests/test_dsh_attempt_overlay.py` invokes the provider-free
Node acceptance tests with no bundled donor packages. Real DSH ToolRuntime
and MCP SDK integration, installed Seatbelt UID/GID/artifact attestation,
native WorkerResult and parent-consumption must be qualified separately:
passing the overlay consumer does **not** set ACP `implemented:true` or
authorize an Executive or production release.


## Native Attempt handoff via existing readiness socket

The original `InstalledAcpWorkerAdapter` and `AcpNativeProcessOwner`
now carry the packet's exact per-Attempt `mcp_runtime_overlay` over the
**existing single inherited `MMX_ACP_ATTEST_FD`** socket, never ambient
environment, stdout, user argv, Job payload or a new transport owner.
Before the native subprocess is created, the incumbent owner verifies
workspace/base SHA, Job/run/worker IDs, bounded deadline and read-only
authority against its actual `WorkerLaunchSpec`. An expired or foreign
snapshot refuses launch; source/tool/artifact/UID ownership is unchanged.

Runs with this additional payload use
`mastermind.acp_tools_ready/v2` (old no-overlay source remains v1). The
parent's one-shot seed includes `attempt_overlay: {cwd, env}` alongside
its original process nonce, PID, base SHA and tool/artifact digests. A
v2-aware installed child must validate the seed and send the **existing**
ready echo plus `attempt_overlay_sha256`, computed from its parsed
overlay using sorted, compact canonical JSON. A v1-only child cannot
qualify an ACP Attempt. Parent ACK and `prepare_prompt` stay behind the
existing exact nonce/identity/attested-artifact fence, and no new grants
are minted from the echo.

The real pinned DSH MCP profile consumer accepts the exact
`attemptOverlay` object before discovery (as separately qualified in
`dsh_attempt_overlay.mjs`). The private socket and donor SDK tests
prove the two interfaces individually. **Installed bootstrap wiring from
that v2 socket reader to the live native DSH AgentLoop and WorkerResult
is not yet proven**; no profile flip, live chat target, sealed OS release
or product claim follows from these fixtures.


### Child-side v2 receiver

The provider-free source helper
`integrations/acp_worker/dsh_native_attempt.mjs` is an opt-in
consumer of that **same inherited FD**. It validates the v2 frame
against the current process PID, exact independently pinned parent
projection/artifact digests, process nonce shape, Job/run/worker/base
SHA, closed workspace/identity/deadline and one named tool catalog.
Only an *attested installed host* may supply its `activate` callback.
That callback must await the existing
`createDshGrantedToolProfile` and its real MCP tool discovery before
the helper echoes `ready:true` plus canonical overlay SHA256.
The original parent must then return its exact `accepted:true` ACK.
An aborted, expired, wrong-artifact or refused callback cannot produce
a successful handoff; no credentials, source retargeting or Retry path
is added.

`tests/test_acp_native_dsh_child.py` exercises a REAL Node child and
the existing Python `AcpNativeProcessOwner` through the inherited
socket; it proves receive/ACK, withheld ambient keys, digest refusal
and process cleanup. Its child activation is deliberately a fixed
test-only no-provider stub. The installed trusted payload wiring of
this helper into the compiled DSH profile, agent turn/WorkerResult,
original parent consumption, UID/Seatbelt proof, authenticated chat
and sealed production release remain **UNPROVEN**.
