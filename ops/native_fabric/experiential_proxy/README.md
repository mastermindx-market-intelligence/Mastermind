# Experiential Labs — Fabric OpenAI SDK transport

**Scope:** an opt-in **outbound inference proxy** for authorized Fabric workers that already use the OpenAI Python SDK. It is not a new Fabric queue, worker scheduler, router, identity system, model selector, or provider-account allocation policy. The existing `fabric_task.py` / `pick.py` / admission / `pool_ledger.py` remain canonical. No live credentials or account connections are committed or changed.

### Supported wire surface

`POST /v1/chat/completions`, `POST /v1/responses`, `POST /v1/embeddings`, `POST /v1/systemone`, `POST /v1/decisions`, `GET /v1/models`. Chat and Responses SSE streaming is passed through without transforming chunks. The supplied provider slug is not rewritten. Caller-supplied `Idempotency-Key` is forwarded for Chat and Responses only; this version never automatically replays a POST after an ambiguous failure.

**Optional single-organization metadata ingress (default OFF):** Set
`EXPLABS_ACCOUNT_METADATA_ENABLED=1` **only** on a credential-owning gateway
with exactly **one** configured provider key, then the same authenticated
loopback listener also accepts read-only `GET /api/whoami`,
`GET /api/v1/key` and `GET /api/v1/credits`. An invalid enablement
flag or multiple keys refuses gateway startup. These requests enter the **same**
durable sliding RPM admission queue as Chat, Responses and Jev, and the vendor
key never leaves the host. The gateway emits **only** the Brain-required
`org_id/org_slug`, `data.limit/limit_remaining` and
`data.total_credits/total_usage` fields: it strips arbitrary provider
account metadata and error bodies, caps decoded metadata at 64 KiB, and
refuses unexpected paths or malformed JSON. Both selected financial fields
must be present as finite JSON numbers, except that the key API's paired
`limit: null, limit_remaining: null` is preserved as an uncapped **daily key**
restriction. One null, missing fields, booleans, strings, arrays and objects
still fail with a generic 502. An uncapped key is neither an unlimited wallet
nor proof of a subscription allowance. Credits API numbers are **USD**, despite
the historical `total_credits` field name. Nothing turns unknown funding into zero. Integers are preserved exactly, and
floating values are checked without coercion. The proxy validates shape only:
cap, remaining-balance and funding-policy decisions still belong to Brain's
separate reviewed consumer. Invalid replies retain the one consumed RPM
reservation and release the same in-flight slot, with no replay or key rotation.
The local bearer remains sensitive;
any holder of the inference proxy token can also query these reduced account
values when this switch is on. Keep this endpoint loopback-only and distribute
tokens only to the authorized Brain/account consumer. Two different serving
organizations require **separate** gateway state directories, key owners and
scoped local tokens; they must never share a vendor quota identity.
This release adds metadata ingress **only**: Brain PR #1918 still uses direct
provider API calls until a separate reviewed client-transport binding routes
its account observations **and** inference POSTs through the corresponding
gateway. No claim of a verified `$1/day` provider cap, real serving or live
shared Brain RPM follows from merely enabling the metadata option.

Each configured credential has its own durable, **sliding 60-second** admission history, default 1,000 sends per 60 seconds (strictly more conservative than a full-burst token bucket). An optional `SAFE_RPM_SHARED` enforces an additional organization-wide rolling RPM ceiling across all configured keys, using those same durable admission records, including sends from recently rotated keys. Round-robin available slots; a FIFO in-process waiting queue holds the HTTP request until any key has room. A downstream ASGI disconnect cancels a waiting ticket without sending to Experiential Labs; an already committed RPM reservation remains conservatively counted if disconnect races with admission. A separate configurable per-key in-flight cap (default 128) also queues work before opening upstream sockets. The HTTPX connection pool is explicitly sized to the sum of configured per-key in-flight caps so a smaller transport default cannot silently admit durable RPM and then time out before provider send. The waiting queue is bounded by both request count and aggregate queued body bytes (64 MiB default); if either fills, or the caller exceeds its maximum queue wait, explicit 503/504 ends the request rather than unbounded memory growth. An **upstream** 429 is preserved because it may be a non-transient organization/credit/review restriction, not simply per-key RPM. No account switching to bypass provider refusals.

**Caveats:** the configured per-key ceiling is only a local sending policy. Experiential Labs meters **platform-funded traffic** against organization-wide rate and token limits, shared across API keys (BYOK has different accounting). Four credentials do **not** guarantee 4,000 usable requests/minute. Configure `SAFE_RPM_SHARED` below the actual org RPM quota once verified in Experiential Settings → Rate limits; leave it unset until the correct org scope is confirmed. Shared TPM remains provider-owned and is **not** locally enforced. The provider's actual per-key limit and permissions must be independently confirmed. This is one-process-per-state-directory, one-host quota accounting. Multiple hosts or independent state directories using the same credentials can exceed a shared cap; do not start multiple proxy replicas for the same keys. Queueing is bounded, not infinite. Existing worker execution routes do not automatically become SDK consumers. The gateway can now accept **typed Jev System One JSON requests** at `POST /v1/systemone` with its existing scoped local bearer token. This route shares the same rolling SQLite RPM admissions and host-owned provider credential as Chat/Responses and returns bounded non-stream JSON without rewriting model slugs; `Idempotency-Key` is **not forwarded** for System One. The separately owned Jev native adapter in PR #1851 **still calls its direct endpoint until a distinct reviewed client-binding change** selects the localhost proxy; adding the gateway route by itself does not switch or activate Jev. Concurrent vendor traffic may be considered safe only after that binding is installed and a separately verified aggregate organization quota/budget boundary has been admitted.

### Subscription plan request policy

The existing gateway supports three deployment modes in `EXPLABS_PLAN_POLICY`:

| Mode | Inference targets |
| --- | --- |
| `legacy` | Existing reviewed callers; default when unset, preserving their contract |
| `free_only` | The seven requested free models, using exact `:free` wire IDs |
| `free_and_uncensored` | The same free targets plus the two selected paid Uncensored models |

The example environment uses `free_only`. Plain promotional slugs are refused
in both enforced modes because they can draw from wallet funds when a free
allowance ends. The provider's `:free` contract supplies the hard no-spill
boundary; the gateway does not manufacture a second daily credit ledger.

Free chat/Responses models are `deepseek-v4.1-flash:free`,
`deepseek-v4.1-flash-1017:free`, `gpt-6-luna:free`, `clef:free`, and
`clef-flash:free`. Native decision models stay on their own protocols:
`jev-latest:free` on `systemone`, and `gpt-6-luna-decisions:free` on
`decisions`. They are not generic coding workers.

The paid preference is **DeepSeek first**:
`deepseek-v4.1-flash-uncensored`, then `glm-5.3-flash-uncensored`.
This ordering is for a new selection by the incumbent router; it is never a
fallback after a send, refusal, timeout, or unknown effect. The old full
`glm-5.3-uncensored` route and its Account A/B holds are unchanged. Other paid
models and client-supplied routing overrides are refused before admission.

An enforced POST must carry `X-Fabric-Plan-Policy` equal to
`plan_policy_digest(mode)`. The Attempt-owned consumer includes the digest in
its route generation and sends the header itself; the SDK helper derives it
from the same environment setting. A missing or changed policy returns 409
before an RPM reservation or vendor send. The header cannot enable paid access:
the credential-owning gateway's deployed mode is authoritative. No digest or
local token is forwarded to the provider.

Before enabling paid mode, the existing budget owner must bind and verify the
actual account's monthly spend boundary. The Chairman's $200/month and
7,000 free credits/day are desired plan limits, **not observations of current
remaining allowance**. This change introduces no monthly monetary ledger and
does not enroll a native pool, create a lease, or claim a live worker.
The inference key cannot administer the provider budget; use the existing
provisioning/account owner for that control. Current free allowance, account
eligibility, rate limits, quota reset and pending reservations remain
provider-owned.

### Install on the machine that should own the credentials

From the `ops/native_fabric/experiential_proxy` directory in a checked-out Mastermind repository:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
# Edit .env locally: replace both placeholder values with your own secrets.
# Create local token: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
set -a
. ./.env
set +a
mkdir -p .state && chmod 700 .state
python -m uvicorn ops.native_fabric.experiential_proxy.gateway:app --app-dir ../../.. --host 127.0.0.1 --port 8311 --workers 1 --no-access-log
```

This uses a **single instance** (not `--reload`, not `--workers 2+`). Source keys from a local `0600` env file or an existing secrets manager; do not commit secrets. Each additional credential uses `EXPLABS_KEY_2`, `_3`, and `_4` (remove the comment marker in `.env` and restart the gateway). Existing SQLite admissions per key remain in `.state` across restart, so the rolling cap is preserved if a process is restarted. Never copy this state directory to other active proxy processes.

Check without spending inference credits (the authenticated status endpoint is local-only and exposes no provider tokens):

```bash
curl -fsS http://127.0.0.1:8311/healthz
curl -fsS http://127.0.0.1:8311/statusz -H "Authorization: Bearer $FABRIC_PROXY_TOKEN"
curl -fsS http://127.0.0.1:8311/v1/models -H "Authorization: Bearer $FABRIC_PROXY_TOKEN"
```

Use a slug exactly as returned by the catalog. For an existing SDK worker, use `worker_client.py` or:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ.get("FABRIC_OPENAI_BASE_URL", "http://127.0.0.1:8311/v1"),
    api_key=os.environ["FABRIC_PROXY_TOKEN"],
    timeout=900.0,
    max_retries=0,
)
result = client.chat.completions.create(
    model=os.environ["EXPLABS_MODEL"],
    messages=[{"role": "user", "content": "Say ok"}],
    extra_headers={"Idempotency-Key": os.environ["FABRIC_REQUEST_ID"]},
)
print(result.choices[0].message.content)
```

`FABRIC_REQUEST_ID` must be a **stable identifier for one logical call**, unique when the call body changes; it is an upstream replay-protection hint, not a Fabric root/attempt ID replacement. The `worker_client.new_client(request_id=...)` helper now binds the optional idempotency key as an SDK default header, also using `FABRIC_REQUEST_ID` if no explicit argument is passed. **Use a fresh SDK client or an explicit `extra_headers` override for each distinct logical inference**; do not reuse one idempotency key across different requests. The executable `worker_client.py` example requires a non-empty request ID. Do not automatically retry a failed job from this sample. For a fully remote worker, establish an *authorized encrypted tunnel* to the machine hosting `127.0.0.1:8311`; do not expose this process on `0.0.0.0` or copy the provider keys to other hosts. The remote client gets only the local `FABRIC_PROXY_TOKEN` and a tunneled `FABRIC_OPENAI_BASE_URL`.

### Operating requirements

- Where several keys are for the **same** Experiential organization, set `SAFE_RPM_SHARED` to a conservative aggregate ceiling verified for that organization and funding lane. Without this value the proxy enforces only per-key counts, and cannot promise to prevent org-level 429s.
- Run with `--workers 1`; the admission lock prevents a second process using the same `.state`. Per-key counters are durable SQLite reservations written **before** transmission. Cancellations after reservation conservatively consume one RPM slot.
- An in-flight concurrency cap (`FABRIC_MAX_INFLIGHT_PER_KEY`, default 128) is separate from RPM and may lower practical throughput for slow completions. Tune under load instead of forcing excessive sockets.
- The 600-second queue deadline should fit the client 900-second total timeout **plus expected model execution time**; raise the client timeout when needed. An external reverse proxy or SSH tunnel may have its own timeout. `FABRIC_MAX_PENDING` defaults to 2,000 and `FABRIC_MAX_PENDING_BYTES` to 67,108,864 bytes; exhausting either yields 503, not 429. The byte cap accounts for requests *waiting for admission* after their body is received, not arbitrary socket-receive concurrency.
- The HTTP proxy requires a separate local bearer token, must bind to 127.0.0.1, and also rejects non-loopback client peer IPs at all of its defined HTTP routes (defense in depth, not permission to use 0.0.0.0); keep both the token and upstream credentials out of source, logs, and diagnostics. The unauthenticated local healthz returns only {"ok": true}; the authenticated statusz has aggregate counters but no key identities. Provider error bodies are bounded by FABRIC_MAX_BODY_BYTES before being copied downstream; overlarge error responses become 502 after cleanup.
- No accounting of input/output tokens, live account entitlement, per-org budget or platform credits is asserted. The opt-in request policy restricts exact model/endpoint targets. These remain with Experiential Labs and incumbent Fabric capacity/budget control.
- This is source-level opt-in only. Live M2 deployment, API key enrollment, remote worker tunnel, actual workload proof, and accepted release are separate gates before production routing; review follows the current session-local policy and enforced repository rules.

Offline qualification from Mastermind repository root:

```bash
python -m pip install pytest pytest-asyncio
python -m pytest -q tests/test_experiential_proxy.py tests/test_experiential_systemone_gateway.py tests/test_experiential_account_metadata_proxy.py
```

Offline qualification on the Mac can run `python -m pytest --noconftest -q tests/test_experiential_proxy.py`; the full test set now includes a real ephemeral local TCP upstream using actual HTTPX connection pooling, non-loopback refusal, SDK idempotency setup and bounded provider errors. These tests use fixture credentials and no vendor calls. A green test is **not** approval to install an unreviewed branch.

Provider references: <https://platform.experientiallabs.ai/docs>, <https://platform.experientiallabs.ai/docs/openai-compatibility>, <https://platform.experientiallabs.ai/docs/errors>, <https://platform.experientiallabs.ai/docs/account-api>, <https://platform.experientiallabs.ai/docs/cost-api>.
