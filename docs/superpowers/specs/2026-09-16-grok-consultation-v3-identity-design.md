# Grok Consultation V3 Identity Design

## Outcome

Introduce an honest, versioned consultation QUESTION identity for the trusted `grok-bot` reasoning surface without enabling a target, transport, credential, provider call, native execution, or production path.

## Current authority

- W6-C2 repair source acceptance: PR #681, exact head `de190b2c7e878fd5a4cf6ecb2fc58b34b058ee74`.
- Protected master at design freeze: `0fe8074ff953b2ced9025ed40f0f66019c759967`.
- Existing carrier to preserve: branch `sol/grok-consultation-v2-g1b-20260915`, prior head `b0b4b48d6c4e61255d8f6a93554c6b64e2fb9b57`.
- The branch name is historical carrier identity. It is not authority to reuse consultation v2.

## Pull-request carrier law

While accepted W6-C2 repair PR #681 remains unmerged, the Grok identity PR is stacked on its exact remote branch/head rather than opened directly against `master`. This keeps the Grok PR limited to the new v3 identity capability and avoids duplicating W6-C2's five-path repair carrier. After #681 lands, the same Grok PR may be retargeted to `master` only with refreshed latest-base integration proof and review-reuse classification; no replacement PR, rebase-for-freshness, or ancestry-only source commit is required.

## Version law

- `mastermind.agent_dialogue_consultation.v1` remains byte- and behavior-compatible. It retains the protected closed key set and the existing `codex`/`claude` recipient-surface law.
- `mastermind.agent_dialogue_consultation.v2` remains the request-linked `ANSWER`/`CORRECTION` schema with `question_message_key`. Its key set, purposes, surfaces, fingerprints, and refusal behavior remain unchanged.
- `mastermind.agent_dialogue_consultation.v3` is the first unused schema and is reserved in this wave for `QUESTION` frames addressed to `grok-bot`.
- V3 uses the exact v1 QUESTION key shape: no `question_message_key`, `correlation.request_message_key == message_key`, one question, no answer, one-answer budget, zero forwarding hops.
- V3 accepts exactly `recipient_binding.reasoning_surface == "grok-bot"`. It refuses `codex`, `claude`, `gemini`, and unknown surfaces.
- This wave does not define a Grok answer/correction schema. Future response semantics require a separate reviewed wave.

## Components

### Dialogue contract

`common/agent_dialogue_consultation_contract.py` adds the literal v3 schema constant, a closed schema-to-surface table, and a trusted surface-to-QUESTION-schema selector. Validation dispatch is schema-specific and must leave existing v1/v2 paths unchanged.

### Peer resolution and Company MCP

`ConsultationPeer` derives its consultation QUESTION schema from the trusted binding surface. `company.consult` carries the derived schema in its internal dispatch request. Callers cannot supply or override that field. `company.peers` remains byte-shape compatible and does not expose schema metadata.

### Runtime receipt

`ConsultationRuntime.intent` persists the exact validated `item["schema"]` rather than hard-coding v1. The pure INTENT payload producer is tested with v3, while the full v3 runtime call must still fail current-recipient admission and emit zero events because this wave creates no Grok SessionTarget. No dispatch, native-acceptance, provider, or credential behavior is added.

### Session-target vocabulary

`grok-bot` becomes a recognized reasoning-surface token only. No checked-in SessionTarget uses it; no wake transport is implemented or armed; no config or registry entry is added.

## Failure and correction behavior

- Unknown schema or surface: fixed `MESSAGE_INVALID` / typed binding refusal.
- Caller-supplied `consultation_schema`: Company MCP `INVALID_REQUEST`, zero dispatcher calls.
- Stale or malformed binding: existing `BINDING_UNAVAILABLE` behavior.
- Existing v1/v2 vectors: literal compatibility tests must pass unchanged.
- Duplicate/replay semantics: unchanged; fingerprints include the literal schema, so v1/v2/v3 frames are not aliases.

## Proof contract

The wave is accepted only when:

1. exact protected v1 fingerprints and v2 request-link tests remain green;
2. v3 accepts only Grok QUESTION frames and rejects all cross-version/surface misuse;
3. Company MCP derives v3 from the trusted peer and refuses caller override;
4. runtime INTENT records exact v3;
5. session-target tests prove vocabulary-only addition with zero target/transport implementation;
6. focused, touched-importer, and current-base integrated suites pass;
7. independent review finds no blocker or major;
8. PR remains draft and claims only `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

## Non-goals

No Grok target, provider identity, credential, endpoint, route, transport registration, implementation bit, service installation, Slack path, provider call, native execution, answer schema, deployment, work acceptance, or production proof.
