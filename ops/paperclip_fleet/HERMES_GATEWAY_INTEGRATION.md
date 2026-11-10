# Hermes gateway compatibility required by Paperclip

Status: **prepared integration design; no Hermes core patch or new credential bridge deployed**.

This is the remaining harness integration for the existing MastermindX Paperclip
company. It does not authorize a new authentication service, a profile-wide
credential relay, a provider change, or changes to active unowned source.

## Evidence and qualification boundary

Paperclip is the installed official npm release 2026.1106.0, source commit
`d69631b01b9c658f80bf8bed389863dce82643e1`. Its `hermes_local` adapter injects a
run-scoped `PAPERCLIP_API_KEY` and a separate `PAPERCLIP_RUNTIME_TOOLS_TOKEN`.
The former is the original Paperclip run JWT; the latter authorizes runtime-tool
access. A static agent key is not equivalent: Paperclip's secrets service requires
an `agent_jwt` actor for run-scoped secret access.

Hermes source was inspected on M2 under
`/Users/chriswong/.hermes/hermes-agent`, checkout
`ba4ddf9945a213ede9dda016602a86591ed634f9`. This is a local commit not found by the
public GitHub contents API for NousResearch/hermes-agent. The booted gateway
reported `09ccb0db84968b92821568bb9adb78efbf0b5ff1`; source inspection of the newer
checkout is not live-daemon proof. The existing gateway serves the root plus the
13 named profiles. Read-only Product attachment to the existing owner succeeded;
no gateway was restarted, replaced, or given a second owner.

The original consumer test is **MAS-2**, issue
`4f8769dc-1c3f-41f7-bdec-08f137f551ef`. Its latest native retry is blocked on
workspace validation before reaching a model. Repair and qualify this original
path before applying a speculative core change against a different live revision.

## Current source behavior

| Surface | Observed implementation | Consequence |
| --- | --- | --- |
| Managed instructions | HERMES_EPHEMERAL_SYSTEM_PROMPT is collected into session.create client_env and bound to the session. | Supported on a fresh compatible gateway session; not yet proven through MAS-2. |
| Nonsecret run context | PAPERCLIP names are not in the built-in client allowlist; terminal.client_env_passthrough is the supported extension. | The readiness installer adds only explicitly named nonsecret context. |
| API and runtime-tool credentials | agent/session_client_env.py rejects KEY and TOKEN names even when configured. | Both run credentials are lost by the ordinary client_env path. Preserve this generic filter. |
| Resume | session.resume sends no fresh client_env. | A new Paperclip run can inherit stale prompt/run context. persistSession is now false. |
| Profile binding | The private control handshake verifies the served home and mints a profile/instance-bound session ticket. | Reuse the existing multiplexer and individual Hermes profiles. |
| Model selection | CLI model=auto is an explicit model; the profile default applies when model is absent. | Adapter model now matches the actual profile model. Adapter provider=auto omits --provider, preserving profile Capacity Fabric selection. |

Source seams: `hermes_cli/gateway_chat.py`, `gateway_client.py`,
`gateway/session_local_route.py`, `gateway/run_config_loaders.py`,
`gateway/session_worker_construct.py`, and `agent/session_client_env.py`.

No supported plugin hook was found that transports these private values across
the closed session-create boundary. Profile secret sources, terminal backend
providers, lifecycle hooks, and inference launch keys have different contracts.
Do not disguise a Paperclip tool credential as an inference key.

## Existing custody to extend

Reuse `gateway/session_policy.py` and its `authority._local_launch_keys` owner.
The current inference key remains private; durable policy holds only a reference
and fingerprint. The managed-worker path reserves a worker, hydrates private
bootstrap data, and sends it over the existing stdin pipe. Its stderr sink already
scrubs exact secret values through `worker.secrets`.

Add one typed Paperclip run member to this owner. Keep inference accessors
`launch_key()` and `route_launch_key()` returning only inference credentials.
No additional inbox, proxy, daemon, secret database, queue or watcher is needed.

### Proposed private wire field

A closed optional `paperclip_run_v1` object on fresh `session.create`:

- version: 1
- company_id, agent_id, run_id: canonical UUIDs
- task_id: canonical UUID or null
- api_url: validated intended HTTP(S) service endpoint
- api_key: bounded secret string
- api_expires_at: timestamp
- runtime_tools: null, or a complete object containing token, expires_at, mcp_url
  and only necessary existing endpoint metadata

Do not accept arbitrary environment names or a generic secret dictionary.
Reject partial runtime-tool grants.

The gateway derives profile, principal, gateway instance/epoch, session,
admission and worker generation from its existing authenticated context. The
client cannot choose those server-side bindings. Paperclip remains issuer,
signature verifier and authorization owner. Decoding its JWT for consistency
and expiry checks must never be treated as signature verification.

### Client and closed protocol

1. In `hermes_cli/gateway_chat.py`, collect exactly the two credentials into a
   private local object before connection/bootstrap. Do not place them in CLI
   arguments or generic client_env.
2. Strip them from daemon-start inheritance in
   `hermes_cli/gateway_runtime_start.py`.
3. Require an advertised capability before submitting the prompt. An older
   gateway must return a bounded compatibility error rather than discard fields.
4. Extend the canonical Pydantic contract, generated contracts, and
   `session_policy.CREATE_FIELDS` explicitly.
5. Initially allow only a fresh tool session and one finite admission. Reject
   resume, branch inheritance and title-based existing-session attachment.
6. Strip credentials before creation of `request_json` / `info.launch_request`
   and the durable creation receipt.
7. Ensure contract validation failures contain field/reason codes, never the
   invalid secret value. The current generic ValidationError formatter needs an
   explicit private-input projection.

### Transactional staging and lifetime

Use the incumbent staged-publication path: `StagedReceipt.on_create`,
`commit_local_session` publication after insertion, and withdrawal on failed or
losing transactions. Compose with existing prefill publication.

Exact-create retries compare immutable run identity, endpoints, expiry,
principal/profile and credential fingerprints. An overlapping request cannot
replace the winner's grant.

The current inference secret cleanup preserves resumable branches. Paperclip
credentials need stricter lifetime inside the same custody owner:

- Claim for the actual finite admission, not merely a session label.
- Check expiry on admission, worker hydration and every tool-environment lookup.
- Retire after terminal execution, cancellation, or unknown-execution fencing.
- A viewer disconnect is not itself cancellation or permission to replay.
- Expire unused grants on owner access; add no polling service.
- Refuse another profile, another admission, branch or delegated-agent inheritance.
- After owner restart, history remains readable, but missing private run
  credentials fail closed. A new attempt remains Paperclip-owned.

`gateway/session_finite.py` is a clean common execution wrapper; this design
does not require editing dirty `gateway/run.py`.

### Worker and tool scope

Extend the existing closed managed-worker bootstrap validator and private frame
in `gateway/session_managed_worker.py` and `agent/managed_worker.py`.
Validate against the reserved worker's profile/session/generation. Register both
tokens in the exact-value log scrubber before sending the frame.

Bind an execution-local context that supplies only:

- PAPERCLIP_API_KEY
- PAPERCLIP_RUNTIME_TOOLS_TOKEN

with their matching nonsecret run identity. Consume it in the existing local
terminal and code-execution environment builders after generic filtering.
Do not write daemon-global os.environ or the profile's persistent secret store.

Scrub both exact values before tool results become canonical history or events.
This protection must not depend on a user toggle such as security.redact_secrets.
A profile-wide vault registry is not the run's custody or lifetime owner.

## Source composition that must be preserved

The read-only review found user-owned changes in:

- tui_gateway/contracts/canonical_sessions.py
- apps/shared/src/gateway-contract.generated.ts
- apps/shared/src/gateway-contract.openrpc.json
- gateway/session_authority.py
- gateway/run_turn_runner.py
- gateway/run.py

The canonical contract changes observed concern correction contracts, separate
from create fields, but must still be preserved. Prepare a future patch in an
isolated owned source context and reconcile the actual current contract before
deployment. Do not overwrite, reset, stash or silently release unrelated changes.
No core patch is deployed by this readiness operation.

## Required tests and actual consumer proof

Use synthetic tokens and fake issuer/tool endpoints for source tests:

1. Same-create idempotence; altered token/scope rejection; losing-transaction cleanup.
2. Concurrent runs and profiles receive only their own credentials.
3. No token in receipts, policies, launch requests, validation errors, history,
   events, logs or diagnostics, including with optional generic redaction disabled.
4. Expiry, cancellation, completion, unknown execution, branch, delegation and
   owner restart refuse further use.
5. In-process and managed-worker behavior match; wrong generation/profile is refused.
6. Inference launch-key resume and route-change protections remain unchanged.
7. Older gateway refusal occurs before the prompt reaches a model.

Then qualify the actual running revision, two distinct Paperclip runs, exact
profile/run/task binding, a real Capacity Fabric model receipt, a permitted
runtime-tool call, ordinary task return, run-scoped secret behavior when actually
needed, OMH write/read continuity and the intended original task disposition.
Do not claim full integration from static tests, a CLI exit code or a model-only
response. Keep MAS-2's original effects and approval dependency attached.
