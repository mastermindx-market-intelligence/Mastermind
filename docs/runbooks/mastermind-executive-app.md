# BSC-E1 — Authenticated Executive App (Chairman one-cockpit canary, rung 5)

## What this is

A stateless A1-authenticated HTTP edge (`integrations/mastermind_executive_app/`)
exposing the existing five-tool Executive MCP contract
(`integrations/executive_mcp/schemas.py`) to an authenticated caller (Chairman
or Sol) over plain HTTP, without the MCP SDK, without a new admission path,
and without touching the general Executive control socket.

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
