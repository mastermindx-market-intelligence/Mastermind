# Anthropic OAuth — Fabric capacity gateway

**Scope:** a loopback-only Anthropic Messages wire proxy in front of the Claude Max
OAuth accounts Hermes already owns. It is an admission and token-rotation owner,
not a scheduler, model router, or new credential store. Hermes' `auth.json`
credential pool stays the single source of truth; this gateway reads it live on
every admission.

### What it serves

`POST /v1/messages` and `POST /v1/messages/count_tokens` (Anthropic wire passed
through unchanged, SSE included), plus `GET /v1/models` for the twelve registered
catalogue ids. `GET /healthz` is unauthenticated local liveness; `GET /statusz`
requires the local bearer and returns per-account budgets, cooldowns, in-flight
counts and model weights — never token values.

Public aliases that differ from the upstream id are rewritten at the edge
(`claude-fable-5.1` -> `claude-fable-5-1`).

Optional `x-fabric-account: <label|id>` on a messages request pins one account
for a canary or a Fabric reservation. Unknown labels are a 404.

### Capacity rules

- Every account has a durable, **rolling 5-hour** and **weekly** weighted-request
  budget in `.state/budget.sqlite3`. A reservation is written **before** the
  upstream send, so a crash cannot undercount.
- Model weights are operator-configured (`ANTHROPIC_MODEL_WEIGHTS`), first match
  wins. Default: `claude-fable-5*` = 2.0 (Fable runs at ~50% of normal limits),
  `claude-opus-5*` = 1.5, everything else 1.0.
- Round-robin across accounts with remaining budget and no active cooldown;
  per-account in-flight cap defaults to 1, matching `accounts.yaml`.
- An upstream **429** benches only that account for its `retry-after` (60s when
  the provider sends none), refunds the local reservation, and rotates to the
  next eligible account. **401/403** triggers one token refresh for that account
  and one retry; a failed refresh benches it for 300s and rotates.
- The waiting queue is bounded by request count and aggregate body bytes;
  saturation returns 503, and a queue deadline returns 504. A caller that would
  exceed all account budgets waits only until the first window frees, then 504.

### Credential rotation

Tokens and refresh tokens are read from
`credential_pool.anthropic` in `~/.hermes/auth.json` at request time. A stale
`expires_at_ms` is refreshed proactively. The refresh POST uses the Claude OAuth
client id (`9d1c250a-…`) at `platform.claude.com/v1/oauth/token` with the
`axios/1.7.9` token-endpoint user agent (Claude 429s `claude-code/*` there), JSON
body for `manual:hermes_pkce` rows and form encoding as fallback. The rotated
pair is committed under `auth.json.lock` after re-reading the file and merging
only that row, so other providers are never clobbered; if another process
rotated first, its pair is adopted instead of replayed.

Inference headers are fixed to the verified Claude Code shape: `Bearer <oat>`,
`anthropic-beta: oauth-2025-04-20`, `user-agent: claude-code/2.1.300`,
`anthropic-version: 2023-06-01`. Caller-supplied beta headers are replaced so a
native-API beta cannot reach a subscription OAuth route.

### Install

```bash
D=~/.local/share/mastermind/anthropic-gateway
mkdir -p "$D/state" "$D/logs" && chmod 700 "$D" "$D/state" "$D/logs"
python3 -m venv "$D/venv"
"$D/venv/bin/python" -m pip install -r ops/native_fabric/anthropic_oauth_proxy/requirements.txt
cp ops/native_fabric/anthropic_oauth_proxy/.env.example "$D/gateway.env"
chmod 600 "$D/gateway.env"
# fill FABRIC_PROXY_TOKEN (secrets.token_urlsafe(32)) and the absolute state dir
```

A launchd unit (`ai.mastermind.anthropic-gateway`) runs `service.py` on
`127.0.0.1:8312` with `--workers 1`; the state directory flock refuses a second
process. `service.py` refuses a symlinked, group/world-readable or non-owned env
file and only exports the allow-listed names.

### Hermes wiring

```bash
hermes config set providers.anthropic-fabric.base_url http://127.0.0.1:8312
hermes config set providers.anthropic-fabric.transport anthropic_messages
hermes config set providers.anthropic-fabric.key_env ANTHROPIC_FABRIC_TOKEN
hermes config set model.aliases.fab5-oa anthropic-fabric/claude-fable-5.1
```

`ANTHROPIC_FABRIC_TOKEN` lives in `~/.hermes/.env` (600). The Anthropic SDK
appends `/v1/messages`, so the base URL carries no `/v1`. Hermes authenticates
with `x-api-key`, which this gateway accepts alongside `Authorization: Bearer`.

### Offline qualification

```bash
python3 -m unittest ops.native_fabric.anthropic_oauth_proxy.test_budget
```

The tests cover first-match model weights, Fable 2x exhaustion, round-robin
fairness, cooldown skipping, weekly-window blocking, and reservation refunds.
They use no network and no credentials.

### Caveats

Budgets are **local admission policy**, not provider entitlements: Claude Max
limits are owned by Anthropic and can 429 below or above these numbers. The
gateway one-process-per-state-directory accounting does not survive a second
host or a copied state dir. Upstream 5xx is passed through without replay
because a POST may already have run. `max_tokens` on Fable must be generous
enough for its thinking budget; a 32-token cap can 400 upstream.
