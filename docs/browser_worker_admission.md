# Browser worker admission candidate

This additive candidate extends PR #993 at `3690e03b781b60db45649d2066cc7ffd1fdf42d2`, which is itself stacked on the held browser-resource PR #940. It addresses the grant and Runtime admission boundary in Slice A of the Browser Fabric packet. It does not complete Slice A or enable a production capability.

## Implemented boundary

`create_browser_tunnel_server` optionally accepts an existing `McpServerGrant`. Discovery and dispatch use its exact tool set, server identity/version, stdio transport, and tool-schema digest. Generic `run_browser_action` also checks the signed action's native tool against the granted prepare tools. Grant refusals use the existing channel audit.

`worker.project_worker_browser_lease` projects the original Job, Attempt, Worker, epoch, generation, fence and capability-profile digest into the existing Workbench scope fields. It only shortens expiry. This projection is not admission.

`WorkerBrowserAdmission` reads the existing Runtime owner for each call, including the port check after work enters the bounded executor. It checks the live lease/token/fence, current epoch and writer generation, sealed requested profile, effective attestation, provider writer observation, workspace device/inode/ownership, and any stronger orchestrator admission. It creates no lease, registry, scheduler, host placement, retry or controller endpoint.

The trusted supervisor can compose `create_worker_browser_server` over its existing runtime. In the trusted process already bound to the Attempt’s private stdin/stdout, `serve_worker_browser_stdio` uses the existing fixed-channel runner for framing, revocation, and bounded shutdown, including factory failures and uncertain cleanup. It does not create or transfer pipes, spawn workers, or establish the channel binding. RuntimeStore access, lease tokens and signing keys stay in that supervisor. Tool discovery works before attestation to avoid an attestation/discovery cycle; calls are refused until admission succeeds.

## Integration required before enabling

The incumbent SCF owner must wire this factory into the real supervisor lifecycle and prove that the worker receives only the intended stdio channel. No CLI argument or environment variable accepting worker-supplied authority has been added. The existing CLI remains the fixed-channel candidate from #993; invoking it alone does not exercise this adapter.

The canonical capability owner must admit an exact reviewed browser grant and supply the existing network/resource enforcement. The profile object passed here is trusted supervisor configuration; this adapter checks its consistency with the sealed Runtime profile, but is not a replacement capability registry or egress sandbox. Tests use a synthetic grant. Production registry entries and B1 are unchanged.

Before installation, resolve #940/#993 source review and release holds. Before claiming Slice A/B, run real admitted workers on an admitted host, verify overlapping disjoint browser state, wrong-reference refusal, effect uncertainty and owned cleanup, and verify result consumption by the original parent. Unit tests and a remote source reviewer do not satisfy those cases.

Authenticated profile enrollment, attachment extension, viewer integration and fleet rollout remain later packet slices under their incumbent owners. The packet references an `ACCEPTANCE_CASES.json` that was not supplied; no substitute acceptance result has been fabricated.

## Local validation

The focused transport/contract/port suite passed 51 tests. A broader browser, B1, OHF Runtime, capability and supervisor run passed 335 tests and encountered six Unix socket path-length refusals caused by macOS pytest's long default temporary root. Rerunning the relay file with a short, unique external-volume `--basetemp` passed all nine tests, including all six previously blocked cases. Across those two runs, all 341 selected cases passed; this was not one all-green invocation.

No browser, provider worker, production Runtime or live account is started by the new tests. SQLite admission tests use synthetic durable Attempts and observations. Existing relay/stdio regression tests use synthetic child processes.

The subsequent private-stdio regression uses two simultaneous synthetic Runtime Attempts and actual MCP protocol child processes. It verifies exact tool discovery, separate signed scope identities, denied ungranted calls, cancellation of one channel while the other still prepares, no lease token in either wire, and zero-exit EOF shutdown without cleanup fallback. It starts no browser or provider. The updated transport/admission suite passed 27 tests. This is protocol evidence, not the required two-browser/fabric-worker canary.

A separate compatibility experiment loaded the protected `bf709270f29f5445288e8f453fe82f6c4dd389b4` Runtime module before importing the candidate admission fixtures: all eight passed. Other modules remained candidate-stack versions; this is neither full-tree integration nor coverage of the changed interactive-role/result-seal semantics. Integration must call the current Runtime-owned predicate rather than copy its old body. The shared supervisor/profile and browser R1–R3 repair proposals remain separately owned.
