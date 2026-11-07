# Native terminal metadata and EVAL producer boundary

The existing authenticated native `read_original` operation now exposes a bounded
`terminal_metadata` projection from the original retained admission result. The
same principal, role/profile, session, submission, input digest and admission
checks still run before the stored result is read. The private socket, admission
owner, result store, source-currentness checks and response limits are unchanged.

This implements original terminal metadata delivery. It is not a complete native
EVAL producer, a learning efficacy claim or installed acceptance.

## Returned information

The optional object has schema `mastermind.hermes_native_terminal_metadata/v1`:

- `reported` contains only present, well-typed retained completion/failure/partial/
  interruption and output-transformation flags; the per-turn `api_calls` count;
  and bounded configured/reported model, requested-model, provider, session and
  exit-reason labels. Missing fields remain missing. False remains false. A null
  retained label remains null. Malformed selected fields are omitted and named
  in `invalid_fields`, without forwarding their values or discarding a valid answer.
- `output`, when an answer is deliverable, identifies its exact UTF-8 bytes and
  SHA-256 under stage `retained_redacted_final_response`. Whitespace and Unicode
  are preserved. If the answer is absent, oversized or invalid, `output` is null;
  actual retained failure metadata can still be inspected.
- `model_identity_verified` is always false. The retained model labels are not
  proof of the model that answered. Upstream `served_model` is deliberately
  omitted because it can be a proxy address or configured fallback hint.

The reported session can be the physical conversation after native compaction;
it never replaces the authoritative original admission's session reference.
The existing `successful` answer projection is preserved for compatibility. It
does not assert `completed=True`; consumers must not interpret a legacy answer
with missing completion metadata as a technically valid EVAL run.

No reasoning, history, tool bodies, raw errors, pre-transform response, arbitrary
metadata, account fields or usage dictionary is forwarded. Session-wide token
and cost counters must not be relabelled as per-trial resources. The projection
has fixed fields and bounded values and fits well within the existing wire cap.
It is generated on read, with no new persistence, retry, inference, admission or
provider selection. Missing original admissions retain `EFFECT_UNKNOWN`.

## Why EVAL still requires a real producer

The existing `run_draft` requires observed model, actual process/session/workspace/
environment and policy fingerprints, effective instruction/context/tool evidence,
and timing. Terminal metadata alone does not supply those facts. The v3
contribution below adds selected transport and execution facts, with explicit
coverage gaps. Marking a
run invalid does not make invented schema-required values truthful. Neither a
configured model label nor a digest of an empty placeholder fills that gap.

The next change belongs in the held native execution path: observe the actual
qualified transport after any execution middleware, account for every provider
attempt, bind actual context and tool schemas/events, retain original outcome
and effect/cleanup facts, and project those through this same owner. Existing
pre/post API hooks are fail-open and can miss middleware-synthesized requests;
they alone cannot attest complete coverage. Provider-reported identity is not
independent attestation of model weights.

Once the real producer supplies a complete draft, reuse the existing EVAL
finalizer, ArtifactStore, run graph verification and merged memory-grounding
scorer with exact retained expected/input/output bytes. Do not add a parallel
validity system or observation store. Keep memory comparisons separate from
Harness2's skill-only configuration lock. Outcome Learning #398 remains held.

## Source qualification

The native-control tests exercise the real original-result reader with explicit
native storage doubles, then a real AF_UNIX request through NativeSecretaryClient.
They cover identity refusal before stored-result access, false versus missing,
malformed metadata, exact output bytes, nonterminal/missing results, sensitive
field omission and one original request without resubmission. These are source
and protocol tests, not a running Hermes or authenticated production-host proof.

Upstream semantics were inspected at Hermes
`1c0cd667746d3395fe9e1b6c74f8f85952486f18`, in
`gateway/session_results.py`, `hermes_state_terminal.py`,
`agent/turn_finalizer.py`, `agent/turn_api_request.py` and
`agent/turn_response_intake.py`. The current native runtime and original Ubuntu1
C26 administrator-connection gate remain with their existing owner.

## Tool-observation v2 contribution

The same original outer result now retains post-hook aggregate tool-schema
digests, actual native callback entry/return/raise, and separate original tool
commit return facts. Correlation requires a unique complete native identity,
valid observer ordering and no relevant coverage gap; it never substitutes for
selected-child effect evidence. The reader preserves historical v1 unchanged.

The v2 observations do not supply actual provider dispatch, response-model
facts, process/workspace/policy fingerprints, complete timing or model weights.
They therefore do not themselves create an EVAL run draft. Missing seed,
effective sampling or other required facts must remain missing until their
original native execution owner supplies them.

## Transport and execution contribution in v3

`mastermind.hermes_request_observation/v3` extends the same retained outer
document with `transport`, schema
`mastermind.hermes_native_transport_observation/v1`. The historical reader keeps
v1 and v2 as exact, separate shapes; neither inherits transport fields.

The selected path is the pinned Hermes nonstream chat-completions request through
the original request-local synchronous HTTPX client. The observer qualifies and
binds both `agent.turn_api_call.perform_api_call` and the conversation loop's
imported alias. It preserves the function signature used by `_run_phase`. It
observes logical execution around execution middleware, the original nonstream
dispatch, and `httpx.Client._send_single_request` below SDK retries and HTTPX
redirect handling. A middleware-synthesized response may have a logical call and
no dispatch. Multiple middleware callbacks remain distinct dispatches.

These records identify **HTTPX single-request invocations**, not every TCP
connection attempt, all network activity, provider delivery, or model weights.
Request-client construction, streaming, async clients, Codex, Anthropic, Bedrock,
MoA and custom transports are not complete covered paths. A changed/unqualified
source or binding closes this observation leaf without replacing the original
request, client, result, retry or cleanup owner.

Only already-materialized request bytes and already-consumed response bytes are
projected. The observer never calls `read`, `json`, stream iteration or `close`.
HTTPX redirects may reconstruct a request around its original stream, leaving
`.content` unavailable at entry; the new invocation is retained with unavailable
body evidence. Returned headers and subsequently consumed response bodies are
different states. Raw URL, headers, prompts, tools, bodies and error text are not
retained. Model strings are byte digests; only a closed reasoning-effort
vocabulary can remain raw. Missing seed is absent, never defaulted to zero.
Explicitly supplied seed zero is retained as observed zero. Provider defaults,
effective model identity and effective sampling are not inferred.

Execution wall-time witnesses and monotonic duration describe the actual original
admission wrapper. Process evidence reuses `_NativeGatewayLaunch.observe_child`
and its existing held image/identity/source checks. The projection includes
observed PID, boot/birth identity, real/effective UID/GID, image hash, held release
and manifest digest. Missing clocks/process reads remain unavailable. The
existing scope/event locks seal all contributions before slow end-process I/O;
late copied worker contexts cannot append, finish or move records into a later
admission. Bound dispatch identity comes from its captured logical call, not a
later mutable agent label.

All arrays share the incumbent 16-KiB outer metadata budget. Truncation and
observation failures remain explicit. The original admission result is the only
carrier. Cancellation or an exception with no original pending result produces
no synthetic result or zero-effect conclusion. `complete_evaluation`,
`provider_delivery_proven` and `model_identity_verified` remain false.

The source fixtures contain unmodified complete upstream files with Git blob,
SHA-256, byte length, commit and license provenance: Hermes
`1c0cd667746d3395fe9e1b6c74f8f85952486f18` and HTTPX 0.28.1
`26d48e0634e6ee9cdc0533996db289ce4b430177`. The tests execute the pinned caller,
phase dispatcher, logical call, nonstream worker body, context copier, SDK bypass
and native dispatch. Actual OpenAI 2.54.0 and HTTPX 0.28.1 use an in-process
`MockTransport`; phase dependencies, watchdog registry, process custody and
admission storage are declared test edges. This is source/SDK integration proof,
not a live provider, private Control socket, host service, cleanup attestation or
EVAL efficacy claim.

### Remaining complete-producer requirements

An eligible draft still needs independently qualified model/seed/effort facts,
complete instruction/context/source and tool coverage, actual workspace and
environment identity, enforced policy/network/sandbox evidence, and original
effect/cleanup results. Missing fields must prevent draft creation; the existing
validity helper's subset comparisons are not a completeness check. A complete
run must pass the incumbent finalizer and create-only ArtifactStore/run-graph
checks before any Trial is given to the existing Harness2 refinement port.
Memory comparisons remain a separate factor from its skill-only configuration
lock. No new EVAL validity/store/runner, production Harness2Port, learning
adoption, profile activation or release of Learning #398/PR #409 is introduced
by this contribution.
