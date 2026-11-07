# Optional authenticated principal ruling producer

`build_principal_ruling_mcp_app(core, target=...)` publishes a single static
`ruling` tool at literal POST `/mcp/principal-ruling`. Its arguments and tool
annotations are the existing Company Dialogue principal ruling contract. The
six-tool COO profile and four-tool Company Dialogue facet remain unchanged.
Installed configuration and service bytes have not been changed. The source
Web-CEO v2/v3 COO builders select the new factory
only when supplied an explicit `principal_ruling_target`; absence keeps the
existing routes and metadata behavior.

The qualified host supplies an existing exact `CooApp` and an immutable
`PrincipalRulingTarget(work_ref, obligation_id, reasoning_surface)`. The target
must be selected from the original canonical pending decision request. It is
not an identity or authority grant. The model cannot supply a mission, worker,
thread, obligation, caller, binding, peer, guard or scope. A target does not
retarget itself when another worker becomes current; the host must qualify a
new composition interval. The existing receiving owner checks that the exact
original obligation and current mission still admit the ruling.

The new app owns only its MCP session manager. The composed COO host owns one
shared COO App. Its lifespan stops the ruling manager before closing that
core. The existing Web-CEO builders mount the literal route in the same App
process, preserve protected resource metadata and refuse a selected route
that would collide with the metadata endpoint. This factory creates no
listener, credentials, account enrollment or service. No HTTP or MCP URL is
claimed to be installed by this source change.

The sealed App launcher accepts an optional top-level `principal_ruling_target`
with exactly `work_ref`, `obligation_id`, and `reasoning_surface`. It requires
the supported Web-CEO v2/v3 profile and one matching installed COO mission.
Absent selection preserves the existing launcher behavior. It does not invent
an obligation or prove that one is pending; the qualified host must select the
canonical original obligation and Control must independently admit it. The
existing sealed current-projection loader freezes the entire target alongside
the release, policy and immutable mission scope. Changing or withdrawing it
invalidates the running principal binding rather than retargeting a send.
The target contract is stdlib-only so Control's sealed configuration reader
does not import Starlette, JWT, HTTP or MCP libraries. No installed configuration
is modified by accepting this source parser.

Every tool call reuses the current signed JWT verifier, exact COO binding and
scope, canonical mission/authority derivation, single-send forwarder and
Control's App-peer/COMMIT checks. Raw duplicate Authorization and JSON keys,
nonfinite/deep/oversized JSON, method/query/path aliases and other tools fail
before a send. The raw body is preserved through the SDK boundary. The shared
COO tool inventory and metadata are not expanded.

The result uses `mastermind.principal_ruling_forward.v1` with `ok`, the original
`obligation_id`, existing `transport` classification and the validated inner
`result`. Application preflight and boundary refusal use the fixed
application error shape (`ok: false`, `error.code`, `error.message`). HTTP body
overflow returns 413; malformed bodies return 400. Missing credentials pass to
the existing SDK authentication middleware, retaining its standard OAuth
`WWW-Authenticate` challenge with the configured protected-resource metadata URL.
Duplicate credentials are refused before authentication. Any lost, malformed,
withheld or oversized response after sending
retains the original obligation and an uncertain outcome; there is no retry,
new target, recovery RPC, replacement worker or lease mutation. Original
read-only recovery remains with `PrincipalDialogueRuntimeCommitOwner`.

Qualification covers signed MCP HTTP through a real local App/Control Unix
socket, existing Runtime and Relay owners, one COMMIT/post and original-worker
consumption, with both canonical observation routes and real response loss.
Account enrollment, installed service lifecycle and Slack storage remain
fixtures. Independent source review, protected composition, installed provider
and producer selection, actual enrolled account authority, and live original
parent consumption are still required before claiming delivery.
