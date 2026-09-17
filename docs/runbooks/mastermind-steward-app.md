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
`mastermind.steward.read` in authenticated HTTP mode.

## Truthful capability ledger

The advertised server identity remains `mastermind-steward`. Its current
source capability is intentionally narrower than a complete six-tool Business
cockpit:

| Surface | Maximum truthful claim |
|---|---|
| Grouped-v2 six-tool protocol, exact A1 app/verifier policy binding, Host/raw-path/media/body guards, structured/JSON-text fallback, and inert UI source | `BUILT_NOT_PROVEN / PRODUCTION_INERT` |
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
