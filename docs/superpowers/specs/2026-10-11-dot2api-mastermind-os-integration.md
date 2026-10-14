# Dot2API ↔ Mastermind OS Integration Design

**Status:** implementation candidate / production disarmed
**Protected source basis:** `1f5befa44487ffb7ac2a0ca44ccd85c7c9da1355`
**Upstream basis:** `Pluviobyte/dot2api@66a761505ff73c5dca730260efcaeb5697db81ad` (MIT)

## Outcome

Make an OpenAI Dot addressable as a bounded Mastermind Executive worker without adding a second Mastermind lifecycle, queue, retry authority, identity registry, or result store. Executive OS remains the canonical owner of Job, Attempt, Worker, Event, claim, retry, cancellation, acceptance, and recovery state. Dot2API is a provider-local transport substrate only.

The first accepted capability is one **READ/RESEARCH-only** Executive Attempt: Mastermind submits exactly one Dot2API task, records its exact provider task identity, waits for a schema-valid structured result, maps cancellation and terminal state into the existing worker contract, and can recover the same task after a control restart. No source write, validation command, connected-app authority, provider retry, or production arm is included.

## Existing owners reused

- `control_plane.worker_execution_contract` owns launch, process, result, cancellation, validation, and recovery shapes.
- `control_plane.executive_runtime` owns lifecycle and retry decisions.
- `control_plane.executive_supervisor` owns launch persistence, heartbeats, terminalization, and result acceptance.
- `control_plane.executive_worker_broker` and `remote_attempt_transport` own remote-host placement and control-side facades.
- `control_plane.model_router` and Capacity own provider/model/host eligibility.
- Session Bridge remains the Dot-facing Mastermind continuation/summon surface; this integration does not replace it.
- Dot2API's task database, lease and webhook machinery remain internal provider transport and are never projected as Mastermind lifecycle truth.

## Architecture

```text
Executive Job / Attempt
  -> existing Model Router + Capacity (provider alias `dot`, initially disabled)
  -> existing remote WorkerBroker on the selected host
  -> Dot2ApiWorkerAdapter
  -> one local, attested transport subprocess
  -> one Dot2API POST /v1/tasks (max_attempts=1, stable idempotency key)
  -> exact provider task id persisted in WorkerProcessRef.provider_session_id
  -> Dot wakes through its existing Dot2API MCP Events subscription
  -> Dot completes the provider task with one JSON object
  -> adapter GETs the exact task, validates schema and unchanged workspace
  -> existing CollectionReceipt / WorkerResult
  -> Executive terminalization and parent consumption
```

A local transport subprocess is deliberate: it preserves the existing process identity, launch-attestation, cancellation, dedicated-worker isolation, and restart contracts. Credentials cross only the spawn boundary in an environment variable and are absent from argv, durable JSON, logs, result receipts, Runtime, Git, and model-visible state.

## Contracts and invariants

1. **One Attempt → one provider task.** The idempotency key is derived from exact Job, Attempt/run, and Worker identity. The adapter never changes it and never retries an ambiguous submit.
2. **Effect truth.** Known pre-submit validation failures are `NO_EFFECT`. Transport loss or a response failure after a mutating request may be `EFFECT_UNKNOWN`; it is fenced on the original carrier and never replayed automatically.
3. **No provider retries.** Every submitted Dot2API task uses `max_attempts=1`. Executive OS alone decides whether a later new Attempt is lawful.
4. **READ/RESEARCH ceiling.** Accepted worker authorities are exactly a non-empty subset of `READ` and `RESEARCH` containing `READ`. Write paths, validation commands, native helpers, MCP grants, skills, plugins, and artifacts are refused.
5. **Loopback worker egress.** The worker adapter connects only to a loopback Dot2API origin. A separately owned reverse proxy may expose the same service publicly to the Dot; that public ingress is not worker egress authority.
6. **Strict bounded JSON.** Requests and replies are size-bounded, UTF-8, duplicate-key rejecting, and non-finite-number rejecting. The terminal Dot reply must be one JSON object matching the exact Executive result schema.
7. **Exact task binding.** Submission response queue, attempt ceiling, task id, and state must match the request. Status, cancellation, collection, and recovery use only that exact task id under server-side principal authorization.
8. **Race-honest cancellation.** A cancel that loses to an already terminal task does not relabel a completed/failed/expired result as cancelled. Ambiguous cancel remains effect-unknown.
9. **Immutable local carrier.** Python executable and transport script identity/digest are revalidated immediately before spawn. Drift refuses before provider I/O.
10. **Restart recovery.** The existing `WorkerRecoveryBinding` reconstitutes the exact LaunchSpec and provider task id; recovery reads current task state and never submits again.

## Capability and routing posture

The adapter id is `dot2api`; provider alias is `dot`; execution surface is `dot2api`; profile is `sealed.worker.dot.readonly.no-extensions.v1`. Source may be `BUILT_NOT_PROVEN` while all production selectors remain closed:

- adapter descriptor `implemented=false` until real provider qualification;
- provider `enabled=false` and `autonomous_allowed=false`;
- `dot.research` remains non-worker-eligible and absent from active suitability tiers;
- global `production_armed=false`.

Activation is a separate source/installation effect after exact-host credentials, endpoint, capacity, live canary, cancellation, restart, and result-consumption proof. Source completion must not silently enable routing.

## Failure behavior

- Invalid config, authority, schema, workspace, credential, binary, or script: refuse before provider I/O.
- HTTP/auth/schema errors proven before mutation: typed known failure.
- Mutating timeout, connection loss, unsafe HTTP status, malformed post-submit binding, or uncertain cancellation: effect unknown; preserve task/idempotency carrier and quarantine rather than replay.
- Read outage after the exact task id is known: no new task; return a typed unavailable/unknown state to the incumbent owner.
- Completed but malformed result: `INVALID_RESULT`; no fallback prose acceptance.
- Workspace mutation: `INVALID_RESULT` even when provider output is otherwise valid.

## Verification and acceptance

### Source acceptance

- strict client contract tests, including no retry and unsafe HTTP classifications;
- local fake Dot2API round trip, schema validation, credential non-persistence, cancellation race, recovery, and drift tests;
- capability-policy, model-router, remote broker/fleet, and remote-attempt transport regressions;
- compile, diff hygiene, focused suites, then repository CI on the exact head;
- independent exact-head review.

### Installed acceptance (still required after source release)

1. Dedicated worker host and credential owner configured without exposing the token.
2. Loopback Dot2API readiness and public HTTPS MCP endpoint independently verified.
3. The intended Dot subscribes to `task.available`; a signed event wakes that exact Dot.
4. One harmless Executive research Job reaches the Dot, returns schema-valid evidence, and is consumed by its originating parent.
5. Duplicate submit protection, caller disconnect/cancel, provider outage, malformed output, and restart/reattach are proven on the installed generation.
6. Capacity, selected model/surface, provider task identity, clocks, and unknown usage remain truthful.
7. Only after those proofs may a separate reviewed change set descriptor/provider/alias eligibility and production selection.

## Held non-goals

- importing Dot2API's SQLite task store as Executive state;
- using Dot2API as an OpenAI/Anthropic coding-model backend;
- granting a Dot filesystem, shell, connected-app, Slack, publication, merge, deployment, or trading authority;
- write-capable Executive Jobs;
- automatic resubmission after uncertain effects;
- token-level streaming, tool-call emulation, usage fabrication, or multi-Dot scheduling.
