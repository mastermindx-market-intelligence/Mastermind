# Mastermind Steward Business App

The Steward app is the read-only company cockpit for Sol and the Chairman. It
projects the existing Chairman Control Room through the protected six-tool
Secretary contract. It owns no lifecycle, queue, identity directory, session,
crawler, cache, retry ledger, or organizational state.

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
resource and metadata paths to `127.0.0.1:8766`. Add the externally visible Host
value through `--extra-allowed-hosts` or
`MASTERMIND_STEWARD_ALLOWED_HOSTS`. Do not expose the process directly and do
not add TCP/HTTP to ExecutiveControlService.

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
