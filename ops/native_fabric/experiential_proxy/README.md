# Experiential Labs — Fabric OpenAI SDK transport

**Scope:** an opt-in **outbound inference proxy** for authorized Fabric workers that already use the OpenAI Python SDK. It is not a new Fabric queue, worker scheduler, router, identity system, model selector, or provider-account allocation policy. The existing `fabric_task.py` / `pick.py` / admission / `pool_ledger.py` remain canonical. No live credentials or account connections are committed or changed.

### Supported wire surface

`POST /v1/chat/completions`, `POST /v1/responses`, `POST /v1/embeddings`, `GET /v1/models`. Chat and Responses SSE streaming is passed through without transforming chunks. The supplied provider slug is not rewritten. Caller-supplied `Idempotency-Key` is forwarded for Chat and Responses only; this version never automatically replays a POST after an ambiguous failure.

Each configured credential has its own durable, **sliding 60-second** admission history, default 1,000 sends per 60 seconds (strictly more conservative than a full-burst token bucket). An optional `SAFE_RPM_SHARED` enforces an additional organization-wide rolling RPM ceiling across all configured keys, using those same durable admission records, including sends from recently rotated keys. Round-robin available slots; a FIFO in-process waiting queue holds the HTTP request until any key has room. A downstream ASGI disconnect cancels a waiting ticket without sending to Experiential Labs; an already committed RPM reservation remains conservatively counted if disconnect races with admission. A separate configurable per-key in-flight cap (default 128) also queues work before opening upstream sockets. The waiting queue is bounded by both request count and aggregate queued body bytes (64 MiB default); if either fills, or the caller exceeds its maximum queue wait, explicit 503/504 ends the request rather than unbounded memory growth. An **upstream** 429 is preserved because it may be a non-transient organization/credit/review restriction, not simply per-key RPM. No account switching to bypass provider refusals.

**Caveats:** the configured per-key ceiling is only a local sending policy. Experiential Labs meters **platform-funded traffic** against organization-wide rate and token limits, shared across API keys (BYOK has different accounting). Four credentials do **not** guarantee 4,000 usable requests/minute. Configure `SAFE_RPM_SHARED` below the actual org RPM quota once verified in Experiential Settings → Rate limits; leave it unset until the correct org scope is confirmed. Shared TPM remains provider-owned and is **not** locally enforced. The provider's actual per-key limit and permissions must be independently confirmed. This is one-process-per-state-directory, one-host quota accounting. Multiple hosts or independent state directories using the same credentials can exceed a shared cap; do not start multiple proxy replicas for the same keys. Queueing is bounded, not infinite. Existing worker execution routes do not automatically become SDK consumers. The separately owned Jev/System One native adapter in PR #1851 is **not** a route through this gateway; concurrent vendor traffic requires a separately verified aggregate provider quota/budget boundary before both are activated.

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

`FABRIC_REQUEST_ID` must be a **stable identifier for one logical call**, unique when the call body changes; it is an upstream replay-protection hint, not a Fabric root/attempt ID replacement. Do not automatically retry a failed job from this sample. For a fully remote worker, establish an *authorized encrypted tunnel* to the machine hosting `127.0.0.1:8311`; do not expose this process on `0.0.0.0` or copy the provider keys to other hosts. The remote client gets only the local `FABRIC_PROXY_TOKEN` and a tunneled `FABRIC_OPENAI_BASE_URL`.

### Operating requirements

- Where several keys are for the **same** Experiential organization, set `SAFE_RPM_SHARED` to a conservative aggregate ceiling verified for that organization and funding lane. Without this value the proxy enforces only per-key counts, and cannot promise to prevent org-level 429s.
- Run with `--workers 1`; the admission lock prevents a second process using the same `.state`. Per-key counters are durable SQLite reservations written **before** transmission. Cancellations after reservation conservatively consume one RPM slot.
- An in-flight concurrency cap (`FABRIC_MAX_INFLIGHT_PER_KEY`, default 128) is separate from RPM and may lower practical throughput for slow completions. Tune under load instead of forcing excessive sockets.
- The 600-second queue deadline should fit the client 900-second total timeout **plus expected model execution time**; raise the client timeout when needed. An external reverse proxy or SSH tunnel may have its own timeout. `FABRIC_MAX_PENDING` defaults to 2,000 and `FABRIC_MAX_PENDING_BYTES` to 67,108,864 bytes; exhausting either yields 503, not 429. The byte cap accounts for requests *waiting for admission* after their body is received, not arbitrary socket-receive concurrency.
- The HTTP proxy requires a separate local bearer token and binds to loopback; keep both the token and upstream credentials out of source, logs, and diagnostics.
- No accounting of input/output tokens, per-model eligibility, per-org budget or platform credits is asserted. These remain with Experiential Labs and incumbent Fabric capacity/budget control.
- This is source-level opt-in only. Live M2 deployment, API key enrollment, remote worker tunnel, realistic load test, and accepted independent review are separate gates before production routing.

Offline qualification from Mastermind repository root:

```bash
python -m pip install pytest pytest-asyncio
python -m pytest -q tests/test_experiential_proxy.py
```

Provider references: <https://platform.experientiallabs.ai/docs>, <https://platform.experientiallabs.ai/docs/openai-compatibility>, <https://platform.experientiallabs.ai/docs/errors>.
