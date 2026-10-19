# Mastermind Steward Business App

The Steward app is a read-only, partial company-cockpit source for Sol and the
Chairman. It projects only facts present in the existing Chairman Control Room
through the protected six-tool Secretary contract. It owns no lifecycle,
queue, identity directory, session, crawler, cache, retry ledger, or
organizational state.

## Capability surface

```text
list_responsibilities
get_responsibility
get_attention
get_current_runtime
explain_blocker
resolve_surface
```

Every tool is read-only, idempotent, closed-world, structured, and requires
`mastermind.steward.read` in authenticated HTTP mode. This remains the
installed/default `secretary-v2` generation and its exact six-tool contract is
unchanged.

## Explicit research-v3 app generation

Company Knowledge / Deep Research compatibility is implemented as an opt-in
Steward application generation, not as a seventh/eighth tool silently added to
the protected Secretary contract:

```text
secretary-v2 (default)
  -> protected six Secretary tools exactly as before

research-v3 (candidate)
  -> the same protected six tools
  -> search(query)
  -> fetch(id)
```

`search` is a deterministic catalog adapter over the existing protected
`list_responsibilities` result. It does not crawl GitHub, Slack, Linear,
Studio Direct, the filesystem, hosts, browser state, or the web. A stable
research document id is a one-way SHA-256 identity derived from the protected
responsibility reference (plus a fixed global attention document). No lookup
table, cache, index authority, vector database, corpus, or persistent document
store is created.

`fetch` validates the id, rebuilds the current catalog, and then reconstructs
the selected document only by invoking the existing protected Secretary reads.
For a responsibility document those reads are `get_responsibility`,
`explain_blocker`, `get_current_runtime`, `resolve_surface`, and
`get_attention`; for the global attention document only `get_attention` is
added after catalog resolution. Existing `DEGRADED`, `UNKNOWN`, freshness,
reason-code, and source-attribution truth is rendered without inference.

The research tool contract is pinned separately from the six-tool Secretary
contract:

```text
research server version: 3.0.0
research generation: 1
research schema sha256: 89602f8d6baa76f644b5c41aa931531698a0626bb85e1eb36a593569e8982c7a
research tool schema digest: 8eec65289bf72818fe8362cb02587b6cc78c6eb526a1f602edbd22ffff030918
```

Both tools advertise `readOnlyHint=true`, `destructiveHint=false`,
`idempotentHint=true`, and `openWorldHint=false`. Successful research calls
return structured MCP output plus the same JSON-encoded payload as text.

### Citation URL proof boundary

The current Steward/Control Room deployment has no truthful citation URL
surface. The existing public edge admits only the OAuth protected-resource
metadata path and the MCP resource path. The Control Room UI is an in-chat
`ui://` resource, not an absolute browser URL. The HTTP app deliberately owns
no users, browser sessions, cookies, or authorization-code store, and a bearer-
authenticated MCP request is not proof that a citation click is user-openable.

Therefore research-v3 currently returns `url=""` and fetch metadata
`citation_status=CITATION_URL_SURFACE_MISSING`. The empty URL is deliberate:
it suppresses citation metadata rather than inventing a non-resolving or
unauthorized URL.

The smallest acceptable future surface is a same-host authenticated
`GET /evidence/steward/v1/<research-id>` view that:

1. reuses an already-authoritative browser authentication/session owner;
2. authorizes before any company-state read;
3. recomputes the research id from current protected Steward evidence rather
   than looking it up in a new store;
4. renders only the same bounded, secret-sanitized fetched document;
5. returns not-found for stale, forged, or unknown ids and fails closed on
   source/auth changes; and
6. creates no new session, token, retry, cache, index, or research database.

No such browser-auth owner is present in the current Steward architecture, so
this carrier does not create one. Until that owner exists and a real browser
canary proves click-through, the truthful result is
`CITATION_URL_SURFACE_MISSING`.

## Truthful capability ledger

The advertised server identity remains `mastermind-steward`. Its current
source capability is intentionally narrower than a complete six-tool Business
cockpit:

| Surface | Maximum truthful claim |
|---|---|
| Grouped-v2 six-tool protocol, exact A1 app/verifier policy binding, Host/raw-path/media/body guards, structured/JSON-text fallback, and inert UI source | `BUILT_NOT_PROVEN / PRODUCTION_INERT` |
| research-v3 deterministic `search`/`fetch` adapter over the six-tool contract | `BUILT_NOT_PROVEN / STEWARD_RESEARCH_ADAPTER / PRODUCTION_INERT / CITATION_URL_SURFACE_MISSING` |
| `list_responsibilities` | Complete `FACTS` when its current Agent OS source bundle is complete |
| `explain_blocker` | Complete `FACTS` when the blocker source bundle is complete |
| `get_responsibility` | `PARTIAL / DEGRADED`: the current Control Room source carries no authoritative objective |
| `get_attention` | `PARTIAL / DEGRADED`: the current Control Room source carries no authoritative `requested_action` |
| `get_current_runtime` | `PARTIAL / DEGRADED`: the current producer supplies no Attempt, Worker, RuntimeBinding, or continuation facts; effect remains unknown where applicable |
| `resolve_surface` | `PARTIAL / DEGRADED`: no authoritative `surface.ref`, review-state, or health bundle exists |
| Full six-tool Business cockpit and live one-cockpit read canary | OPEN and not production-proven |

These limits are source limits, not transport defects. The adapter must not
alias `program` to objective, relabel a runtime next-action list as
`requested_action`, manufacture Job/Attempt/Worker/RuntimeBinding or
continuation references, invent `surface.ref`, or turn unknown review or
health state into approval. Missing owner-native facts remain honestly
`DEGRADED`, `UNKNOWN`, or `REFUSED` until a separately authorized producer-to-
consumer vertical supplies them.

HTTP success, MCP `ok=true`, a rendered UI, or a `DEGRADED` result proves only
that the request crossed the applicable transport and schema boundary. It does
not prove that every originally desired fact exists. A tool may report
`FACTS` only when its protected required predicate family is actually present;
otherwise the explicit partial state and reason codes are part of the result.

## Public result generation

The public result schema is
`mastermind.secretary_grounding_mcp_result.v2`. Successful data contains
`state`, `data.subjects[]`, and `reason_codes`. Each subject owns its
`subject_ref`; nested facts contain only predicate, value, freshness, and
source attribution. The Control Room resource is
`ui://mastermind/steward/control-room-v2.html` and applies one global 64-fact
display bound across the protected subject order.

The injected `StewardReadPort` remains the flat internal, typed facts boundary.
The protected Secretary contract alone validates and groups those facts for the
public generation. Structured results and their matching JSON text fallback
remain usable when the optional UI cannot render.

Passing source, transport, and UI checks is not production proof. This carrier
remains `BUILT_NOT_PROVEN / PRODUCTION_INERT`; the full cockpit and the
separately authorized Business installation/read canary both remain open.

## Install the isolated app runtime

```bash
python3 -m venv ~/.venvs/mastermind-steward
~/.venvs/mastermind-steward/bin/python -m pip install -e '.[business-mcp]'
```

The base/sealed Executive runtime remains independent of the MCP/JWT packages.

## Fast private-tunnel canary

This mode is deliberately read-only and carries no OAuth identity. Use it only
behind a private Secure MCP Tunnel during app discovery and early read testing.

```bash
~/.venvs/mastermind-steward/bin/python scripts/mastermind_steward_app.py \
  --transport stdio \
  --repo-root "$PWD"
```

Machine-readable surface:

```bash
~/.venvs/mastermind-steward/bin/python scripts/mastermind_steward_app.py \
  --describe
```

Inspect the source-only research generation without changing the default:

```bash
~/.venvs/mastermind-steward/bin/python scripts/mastermind_steward_app.py \
  --app-generation research-v3 \
  --describe
```

A private-tunnel research canary can likewise use
`--app-generation research-v3 --transport stdio`. This does not publish,
install, or replace the existing Business app generation.

## Authenticated HTTP mode

Copy `config/business_mcp/steward_policy.example.json` outside Git, replace all
example values with the exact IdP/resource values, and replace the placeholder
subject digest with a value produced by
`integrations.business_mcp_auth.subject_digest`.

Start only on loopback:

```bash
MASTERMIND_STEWARD_POLICY=/absolute/path/steward-policy.json \
~/.venvs/mastermind-steward/bin/python scripts/mastermind_steward_app.py \
  --transport http \
  --host 127.0.0.1 \
  --port 8766
```

Routes derive from the immutable policy:

```text
GET /healthz
GET /readyz
GET <resource_metadata_url path>
POST <resource path>
```

The server refuses a non-loopback bind. It performs strict RS256/JWKS/issuer/
resource/scope/subject/time verification through the existing Business MCP auth
library. Tokens, refresh tokens, authorization codes, users, sessions, and
company responses are never persisted.

## Reverse proxy / public endpoint

Terminate TLS in the existing deployment owner and forward only the policy's
resource and metadata paths to `127.0.0.1:8766`. The reverse proxy must
preserve the exact Host authority from `policy.resource` when forwarding to
the loopback process; do not rewrite or widen it. Do not expose the process
directly and do not add TCP/HTTP to ExecutiveControlService.

## ChatGPT app values

```text
Name: Mastermind Steward
Description: Read-only Mastermind responsibilities, attention, runtime,
             blockers, surfaces, and company continuity.
Authentication: OAuth
Scope: mastermind.steward.read
MCP URL: exact policy.resource
```

The authorization server must issue an RS256 token with exact string audience,
issuer, allowed subject, bounded lifetime, and the resource scope. `offline_access`
may be requested for session continuity but is stripped from MCP tool authority.

## Operational truth

A successful connection proves only the app transport. A useful cockpit read
must also carry current source timestamps and explicit degradation. Knowledge
from Project memory, GitHub, Slack, Linear, or returned text never grants write
authority.
