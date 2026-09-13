# BSC-E1 — Authenticated Executive App (Chairman one-cockpit canary, rung 5)

## What this is

A stateless A1-authenticated HTTP edge (`integrations/mastermind_executive_app/`)
exposing the existing five-tool Executive MCP contract
(`integrations/executive_mcp/schemas.py`) to an authenticated caller (Chairman
or Sol) over plain HTTP, without the MCP SDK, without a new admission path,
and without touching the general Executive control socket.

## Temporary E1 four-read mode

The source-only `e1-read` mode is explicit-root and production-inert: it
requires Mastermind, Macro, and temporary runtime roots, accepts no ingress
socket, constructs no admission writer, and exposes only the four reader tool
paths. The outer MCP request authenticates its single current bearer before
the inner E1 app independently re-verifies it. Duplicate Authorization fields,
non-loopback configuration, production-root aliases, malformed frames, and
bounded request/response overflow refuse without fallback, retry, or partial
success. This is neither an installed-runtime nor deployment proof.

Use the profile only with all operator coordinates named explicitly:

```bash
python3 scripts/executive_mcp.py \
  --profile e1-read --mode readonly \
  --policy /approved/temporary/e1-policy.json \
  --repo-root /approved/reviewed/mastermind \
  --macro-root /approved/reviewed/macro \
  --read-runtime-root /approved/temporary/e1-runtime \
  --host 127.0.0.1 --port 9123
```

E1 serves the stateless authenticated MCP surface at `POST /mcp`, with exactly
`executive_state`, `executive_inbox`, `executive_job`, and
`ceo_intent_status`. The in-process `/v1/tools/...` reader map is not a second
listener and has no submit/reconcile route. A sole raw bearer must have the
exact read scope; missing, duplicate, malformed, wider submit-scope, or invalid
bearers stop at the outer gate. Valid MCP arguments are passed through the
existing strict validator before the one inner request. Only a complete
canonical reader envelope crosses back unchanged; invalid JSON, foreign
envelopes, non-200 responses, response loss, and response overflow return the
canonical `backend_unavailable` envelope without retry.

The request ceiling is 65,536 bytes across all ASGI frames (not the declared
`Content-Length`); incomplete, malformed, or 65,537-byte input refuses before
MCP dispatch. The inner response is held until it is fully framed and within
262,144 bytes, preventing partial healthy responses. Every temporary runtime
root is fenced lexically and after symlink resolution at construction and again
before each reader. Missing, foreign, unreadable, or moved runtime state remains
an explicit degradation/unavailable result and never falls back to repository
lifecycle data or causes the reader to create files.

`--describe` confirms the pinned four-reader profile without reading the policy,
importing the serving SDK, or binding a listener. It still requires the explicit
coordinate flags so the production-path refusal is exercised:

```bash
python3 scripts/executive_mcp.py --profile e1-read --mode readonly --describe \
  --policy /approved/temporary/e1-policy.json \
  --repo-root /approved/reviewed/mastermind \
  --macro-root /approved/reviewed/macro \
  --read-runtime-root /approved/temporary/e1-runtime --port 9123
```

This runbook documents a source-only temporary composition. It does not grant
authority to install, start, tunnel, connect a custom app, read a real runtime,
or describe the composition as production-ready.

* The four READ tools (`executive_state`, `executive_inbox`, `executive_job`,
  `ceo_intent_status`) are reused verbatim through
  `integrations.executive_mcp.adapter.ExecutiveMcpGateway` — same schemas,
  same validation, same envelope shape.
* The ONE modifying tool, `submit_ceo_intent`, is admitted **only** through
  the dedicated PR-A/AD-ID1 CeoIngress AF_UNIX socket
  (`control_plane/executive_ceo_ingress.py`'s v2 submit frame). This app is a
  pure network CLIENT of that socket: it never calls
  `control_plane.ceo_intent.submit_intent` in-process, never imports
  `control_plane.executive_service`, and never widens that module's peer
  list.

This is rung 5 of the Chairman one-cockpit canary: an authenticated
Chairman/Sol can read Executive state and make ONE separately-confirmed
harmless admission that ends at **QUEUED / dispatched=false / Attempts=0 /
Worker=none** — no execution, no provider placement, no Wake, no Agent-OS
write, no Slack/Linear effect, no RuntimeBinding mutation, and no second
ingress.

## Reused vs. new

| Surface | Status |
|---|---|
| Executive MCP five-tool schemas/validation (`integrations/executive_mcp/schemas.py`) | Reused verbatim. Unchanged — schema digest `546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232`. |
| Read gateway (`integrations/executive_mcp/adapter.py::ExecutiveMcpGateway`) | Reused verbatim for the four read tools only. |
| A1 resource-server stack (`integrations/business_mcp_auth/*`) | Reused verbatim: `JwtAuthenticator`, `ResourcePolicy`, JWKS cache, claims/metadata helpers. |
| Dedicated CeoIngress wire protocol (`control_plane/executive_ceo_ingress.py`) | Reused verbatim; this app is a client of its v2 submit/status frames. |
| `control_plane/executive_service.py` | Untouched (PR #265 owns it). Never imported. |
| `control_plane/ceo_request.py` | ONE additive function, `app_request_ref(operation_key) -> "req-<32 hex>"`, mirroring `mcp_intent_id`/`slack_intent_id` with its own domain separator. Every existing function is byte-for-byte unchanged. |
| `integrations/mastermind_executive_app/` (this app) | New. |

## Why `app_request_ref` exists

The AD-ID1 v2 submit frame (`SUBMIT_SCHEMA_V2`) requires a caller-supplied
`request_ref` matching `control_plane.ceo_request.AUTOMATED_REQUEST_REF_RE`
(`^req-[a-z0-9][a-z0-9._-]{7,95}$`). Before this change, `ceo_request.py` had
no function that DERIVED a `request_ref` from an operation identity — only
`automated_intent_id(request_ref)`, which *consumes* an already-formed one.
`app_request_ref(operation_key)` fills exactly that gap: deterministic,
depends only on the caller's `operation_key` (the same field already legal on
the existing `submit_ceo_intent` five-tool shape), and separately namespaced
(`mastermind.executive_app.operation_key.v1` domain bytes) so its output can
never collide with the MCP (`mcp-`) or Slack (`slack-`) identity spaces.

## Two resource policies, not one

`integrations.business_mcp_auth.claims._scope_claim` enforces an **exact**
match between a token's granted scopes and `ResourcePolicy.required_scopes`
— never a subset check. So this app authenticates against TWO independent
policies:

* **read**: `required_scopes = ["mastermind.executive.read"]`
* **submit**: `required_scopes = ["mastermind.executive.intent.submit", "mastermind.executive.read"]`

A caller therefore needs a token minted with exactly one scope set or the
other. See `config/business_mcp/executive_policy.example.json` for the full
wire shape (EXAMPLE ONLY — every hostname is `example.com`; never read by
any production path).

## Running it

```
python3 scripts/mastermind_executive_app.py \
  --policy /path/to/real-policy.json \
  --mastermind-root /path/to/mastermind/checkout \
  --macro-root /path/to/macro/checkout \
  --ceo-ingress-socket /path/to/already-installed/ceo-ingress.sock \
  --port 8443
```

Every one of `--policy`, `--mastermind-root`, `--ceo-ingress-socket`, and
`--port` is REQUIRED — there is no default configuration, so running the
script with no arguments does nothing but print usage and exit non-zero.
`--host` defaults to `127.0.0.1` and refuses any non-loopback value. The
script never installs, arms, or mutates a production socket; it only
connects to one that already exists.

## HTTP surface

* `GET <ResourcePolicy.resource_metadata_url path>` — an unauthenticated RFC
  9728 protected-resource metadata document. The route is derived from the
  validated read policy, not a host header or hard-coded hostname, and returns
  exactly its A1-owned `resource`, `authorization_servers`, and
  `scopes_supported` projection. Read and submit policy instances must name
  the same resource, metadata URL, issuer, and authorization-server set when
  the app starts; otherwise construction refuses the incoherent generation.
  An authority-only metadata URL maps to HTTP path `/`; percent-encoded or
  duplicate-slash path spellings are refused at construction because the
  raw-path fence deliberately will not serve them.
  The exact path accepts only a query-free `GET`: trailing-slash, query,
  encoded-separator, duplicate-slash, and non-GET forms never alias it.
* `POST /v1/tools/{executive_state|executive_inbox|executive_job|ceo_intent_status}`
  — body `{"arguments": {...}}`, `Authorization: Bearer <read-scope token>`.
  Returns the exact `ExecutiveMcpGateway.call()` envelope.
* `POST /v1/tools/submit_ceo_intent` — body `{"arguments": {...}}` (the exact
  five-tool `submit_ceo_intent` shape), `Authorization: Bearer <both-scope
  token>`. Returns `{"ok", "status", "request_ref", "receipt"?, "error"?}`.
  `status` is one of `accepted`, `operation_conflict` (409), `refused` (200
  — a clean, zero-effect backend refusal), `ingress_unavailable` (503), or
  `effect_unknown` (202 — the frame may have reached the backend but the
  response was lost; see below).
* `POST /v1/tools/submit_ceo_intent/reconcile` — body `{"request_ref":
  "req-..."}`, same submit-scope auth. The ONLY legal follow-up to an
  `effect_unknown` outcome: sends a v2 STATUS frame on the SAME
  `request_ref`, never a resubmission.

A raw-path fence (`app._RawPathFence`) refuses any request whose UNDECODED
path bytes contain `%2f`, `%5c`, or `//` before routing or authentication
ever run — this is what stops
`/v1/tools/submit_ceo_intent%2Freconcile` from silently decoding into, and
matching, the literal `.../submit_ceo_intent/reconcile` route.

**Deployment contract — the fronting reverse proxy must NOT re-decode
`raw_path`.** The fence matches single-encoded separators only
(`%2f`/`%5c`/`//` in the exact bytes ASGI hands it). A double-encoded
`%252f` or a Unicode fullwidth solidus (`／`, U+FF0F) never becomes an
actual `/` inside THIS process — Starlette/uvicorn decode a path exactly
once, so those forms simply fail to match any route and 404; they can never
alias onto a different, differently-privileged handler here. That safety
property depends on nothing in front of this app performing a SECOND
decode pass before forwarding the request (a proxy that normalizes
`%252f` → `%2f` → `/`, or that decodes Unicode look-alike separators before
proxying, would reintroduce exactly the aliasing class this fence exists to
close). Any reverse proxy or gateway placed in front of
`scripts/mastermind_executive_app.py` MUST forward the original raw path
byte-for-byte and must not apply its own path normalization/decoding ahead
of this app's own fence.

The metadata document is a public resource-server configuration projection,
not an authorization-server endpoint. This app never proxies, caches,
rewrites, or fabricates `/.well-known/oauth-authorization-server`, JWKS,
token, registration, callback, consent, or other IdP discovery routes; those
remain owned by the configured authorization server.

## effect_unknown — what a caller must do

If the dedicated CeoIngress connection is lost AFTER the frame was fully
sent (timeout waiting for a response, connection reset, oversized/malformed
response), this app returns `status: "effect_unknown"` and never retries
internally. The caller must:

1. POST the SAME `request_ref` to `/v1/tools/submit_ceo_intent/reconcile`.
2. Never re-POST to `/v1/tools/submit_ceo_intent` for the same logical
   operation with a NEW `operation_key` as a workaround — `app_request_ref`
   is deterministic, so retrying the original call with the SAME
   `operation_key` is itself safe and idempotent (it reconciles to the same
   Job), but inventing a new key to "try again" creates a second, unrelated
   Job.
3. Never fail over to another transport (Slack, MCP, or the general control
   socket) for the same operation.

## Statelessness

This app holds no durable state of its own: no session table, no token
cache, no job mirror, no result store. Every request is verified from
scratch and every admission call re-reads grounding fresh. A process
restart loses nothing because there is nothing to lose — the durable truth
lives entirely in the Executive Runtime behind the dedicated CeoIngress
socket.

## Tests

* `tests/test_mastermind_executive_app_admission.py` — the `app_request_ref`
  helper (determinism, format, domain separation, regression pin) and the
  ADMISSION composition against a fake `CeoIngressClient`.
* `tests/test_mastermind_executive_app_asgi.py` — the full auth negative
  matrix (wrong issuer/resource/scope/subject/algorithm/key/time, duplicate
  Authorization, encoded-path aliasing, oversized body, wrong
  Host/Origin-is-inert), plus the REAL acceptance canary: genuine RS256 +
  a temporary, no-execution `ExecutiveControlService`/`Runtime` (mirroring
  `tests/test_executive_ceo_ingress.py`'s own hermetic harness) proving
  QUEUED / dispatched=false / zero Attempts / zero Workers, stable duplicate
  readback, and operation_conflict on a changed payload.
* `tests/test_mastermind_executive_app_static_fences.py` — the invariants a
  runtime test cannot see: no import of `control_plane.executive_service` or
  the MCP SDK anywhere in this app, no reference to `send_control_request`
  or a `.submit_intent(` call site, the frozen schema digest, and zero diff
  on `control_plane/executive_service.py`.

## Native five-tool MCP composition

`integrations.executive_mcp.server.build_executive_mcp_app(settings,
audit_sink=...)` composes the frozen five-tool contract over stateless
Streamable HTTP `POST /mcp`. It owns one existing Executive App instance;
readers use its canonical gateway and submit uses its existing dedicated
CeoIngress client. It adds no admission queue, token store or retry service.

The builder accepts the exact read policy or the exact two-scope submit
policy through two unchanged A1 adapters. A token upgraded for submission can
also read through an explicit App setting, with the full submit policy
independently verified by the App. The default direct HTTP App and temporary
`e1-read` profile retain their original policy boundaries. Tool OAuth metadata
and the insufficient-scope challenge use the existing A1 helpers; the input
schemas and annotations remain unchanged.

Both request and inner response buffering reuse the existing bounded ASGI
boundary. The final escaped MCP result has its own budget, reserving space
for the admitted JSON-RPC request ID. Literal routes refuse query strings,
encoded aliases and trailing-slash redirects. The MCP backend accepts loopback
Host values and is intended for the existing Secure MCP Tunnel.

The composition also exposes the existing authenticated
`POST /v1/tools/submit_ceo_intent/reconcile` status route. This is an operator
status endpoint, not a sixth MCP tool. A lost, oversized, malformed or
identity-mismatched reply after possible admission returns `effect_unknown`
with the original `request_ref`; reconcile that same reference before taking
another modifying action. No transport retry is performed.

Focused proof lives in `tests/test_executive_mcp_app_composition.py`: real
A1-signed test tokens, real temporary repositories, a real temporary
CeoIngress/Runtime with execution disabled, exact tool scan, authorization
upgrade, one queued Job, duplicate/conflict behavior and loss-after-admission
reconciliation. These tests do not establish production installation or a
successful ChatGPT call.

### Production binding decision required

For operation
`executive-plugin-transport-five-tool-closure-20260913-sol-001`, the source
composition is separate from the remaining installed host binding. No new
production launcher or activation path is supplied by this change.

The attended Studio configuration projection identified installed release
`a6fde00413979ede525033053bc09a495d6e5fbd`, runtime
`/var/db/mastermind-executive/control/db`, and the dedicated socket
`/var/run/mastermind-executive/ceo-ingress.sock`, with
`ceo_ingress_peer_uid=452`. Current protected `ExecutiveControlService`
authorizes one exact kernel peer UID. UID 452 is the dedicated
`_mastermind_sol_relay` principal, and C1 preparation explicitly keeps that
principal out of the broad Executive/worker groups. Running a separate MCP
service does not satisfy this installed peer contract.

The commission preserves C1 ownership and explicitly stops at a required
change to CeoIngress semantics. Proposed bounded extension for the holding
authority to approve:

1. Give the Executive MCP process its own non-login service principal after a
   fresh identity census; preserve the dedicated C1 principal and credentials.
2. Extend the existing CeoIngress kernel-peer configuration to admit that one
   reviewed principal while preserving C1's authorization. Keep the same
   socket, frame protocols, admission predicates, operation identity and
   idempotency rules. Introduce no new ingress or direct Runtime mutation.
3. Bind the four readers to the same installed canonical Runtime through
   narrowly scoped read access and an explicit installed configuration.
   Preserve all temporary-profile production-root refusals.
4. Add the MCP process to the existing exact-release installation and service
   ownership path, then qualify its Auth0 policy, existing Business tunnel,
   ChatGPT app generation and separately confirmed harmless admission canary.

This extension is not authorized by the transport-only source change. Until
that scope decision and provider qualification are settled, the production
capability remains `BUILT_NOT_PROVEN`; the existing listener, host principals,
C1 activation, tenant objects, grants and Business app are unchanged.
