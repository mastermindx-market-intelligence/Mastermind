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
