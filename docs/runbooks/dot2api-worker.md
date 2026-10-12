# Dot2API Executive Worker

## Purpose and maturity

This runbook installs one OpenAI Dot as a **READ/RESEARCH-only** Mastermind Executive worker through Dot2API. The implementation reuses the existing Executive Job, Attempt, Worker, Event, claim, cancellation, retry, terminal-result, remote-broker and recovery owners. Dot2API is a provider-local transport; its task database and lease are never Mastermind lifecycle authority.

Current source posture is `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` until the installed acceptance campaign below succeeds. Source publication, host installation, Dot connection, provider selection, successful execution, originating-parent consumption and production routing are separate predicates.

Upstream contract basis: `Pluviobyte/dot2api@66a761505ff73c5dca730260efcaeb5697db81ad`, MIT licensed. Mastermind does not vendor upstream source; it consumes the documented HTTPS task API and MCP Events contract.

## Identities and credentials

Keep these principals distinct:

| Principal | Credential | Scope | Storage |
|---|---|---|---|
| Mastermind worker producer | caller token | `submit` + `read` on queue `dot` | worker-owned `provider_home/dot2api.token`, mode `0600`; never argv or plist |
| OpenAI Dot | Dot token or capability URL | `work` + `read` + `subscribe` on queue `dot` | ChatGPT custom MCP connection only |
| Executive control | mTLS/Unix broker identity | existing Mastermind control/remote-worker scopes | existing Executive owners |

Never reuse the Chairman's ambient browser token, place a Dot2API token in Git, Agent OS, Runtime, launchd environment, command arguments, logs, or a Job prompt, or give the caller token `work` authority.

## Network topology

```text
Mastermind Dot worker -> http://127.0.0.1:8788        (caller task API)
OpenAI Dot            -> https://<public-host>/mcp     (MCP + Events ingress)
                                      |
                                      +-> reverse proxy -> same loopback service
```

The worker adapter refuses a non-loopback base URL. Public ingress, TLS, DNS, callback validation and proxy-log redaction belong to the Dot2API deployment owner. Do not point the worker at the public URL and do not disable callback address validation.

## Source and host files

- worker adapter: `control_plane/dot2api_worker.py`
- strict client: `integrations/dot2api/client.py`
- local carrier: `ops/executive_os/dot2api_transport_worker.py`
- host service: `ops/executive_os/dot2api_worker_service.py`
- entrypoint: `scripts/executive_os_dot2api_worker.py`
- config template: `ops/executive_os/dot2api-worker.json.template`
- launchd template: `ops/executive_os/com.mastermind.executive.worker.dot2api.plist.template`
- control-side physical binding template: `ops/executive_os/remote-worker-bindings.dot2api.json.template`

## Prepare Dot2API

1. Install upstream Dot2API at the reviewed upstream commit in its own service environment. Initialize its data directory and encryption key using its documented local setup command.
2. Create one queue named `dot`.
3. Create separate caller and Dot principals with the scopes in the table above. Configure task `max_attempts=1` for Mastermind submissions; the adapter enforces this on every response.
4. Bind Dot2API to loopback. Put a public TLS reverse proxy in front of `/mcp` for the Dot only. Preserve `Authorization`, bound request sizes and webhook signature headers; disable redirects.
5. Verify `/healthz` and `/readyz` locally. These checks prove process/storage readiness only, not Dot execution.

## Prepare the dedicated worker principal

Use a distinct non-root UID/GID with no ambient provider processes. Create three disjoint real directories:

```text
/var/db/mastermind-executive/jobs/workspaces
/var/db/mastermind-executive/jobs/dot2api-runs
/var/db/mastermind-executive/workers/dot2api-01/provider-home
```

The provider home must be owned by the worker and mode `0700` or narrower. Write the caller token atomically to:

```text
/var/db/mastermind-executive/workers/dot2api-01/provider-home/dot2api.token
```

The file must be a regular one-link file owned by the configured worker UID/GID, mode `0600`, between 20 and 4096 printable ASCII bytes, with at most one trailing newline. Rotation is atomic replacement under the same path; each request re-reads and revalidates the current inode.

## Render and validate the service

1. Copy the config template outside the release tree and replace both digest placeholders with exact lowercase SHA-256 values:

```bash
shasum -a 256 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
shasum -a 256 <release>/ops/executive_os/dot2api_transport_worker.py
```

2. Set the exact worker/control identities, paths and loopback Dot2API URL. Keep `require_secret_canary=true` and `operator_harness_armed=false`.
3. Root-own the config and remove group/other write permission.
4. Validate from the installed release root without starting the service:

```bash
<python> -I -S -B <release>/scripts/executive_os_dot2api_worker.py \
  check-config --config <root-owned-config>
```

The output contains only schema, validity, worker identity, worker UID and launchd socket name. It must contain no credential or provider response.

5. Render the launchd template with the exact release root, Python, entrypoint, config, provider home, worker user/group, broker socket and log paths. Do not add the token to `EnvironmentVariables`.
6. Install/load the plist through the existing host installation owner. The `WorkerBroker` launchd socket remains the local broker carrier.
7. For remote placement, render `remote-worker-bindings.dot2api.json.template` under the Control-host root with the exact Capacity `host_ref`, worker identity, private gateway endpoint, mTLS paths, server-certificate fingerprint and accepted secret-canary receipt. Root-own it, group it to the Control service, and set mode `0440`. Add its absolute path as `remote_worker_bindings_path` in the Executive control config. Startup then uses the existing Attempt-bound resolver; a missing/moved/foreign row refuses and never falls back to Codex. This control composition is deliberately remote-only: every claimed worker must have an exact root-managed row, so enroll any retained Codex/Claude capacities through the same incumbent gateway rather than mixing an implicit local fallback.
8. Enroll the existing Remote Worker Gateway and Capacity join with provider `dot`, worker type/adapter `dot2api`, and the same exact worker identity. The endpoint cannot create or change host placement; Capacity must already select the exact `host_ref`.

## Connect the Dot

1. In ChatGPT, create a custom MCP server for the public Dot2API `/mcp` endpoint using only the restricted Dot credential. A capability URL is a secret and must be redacted in proxy logs.
2. Subscribe the Dot to `task.available` for queue `dot`, using the host-provided callback and signing secret. Renew before `refreshBefore`.
3. Give the Dot standing instructions to list queued tasks, claim one, read `payload.messages`, return only one JSON object matching the supplied schema, complete the task, and release terminally when it cannot comply. Explicitly forbid connected apps, messages, publication, trading and other external effects.
4. After every reconnect, list queued tasks once because the upstream Events extension has no replay cursor.

## Qualification campaign

The checked-in adapter descriptor remains `implemented=false` until a real provider-turn receipt is reviewed. This is intentional: the installed broker may be configured and observed, but ordinary `start` refuses before provider I/O while that gate is closed. Do not flip the descriptor merely to make a fixture green.

Qualification therefore has two serialized stages:

1. **Transport qualification:** use one separately reviewed, attended, one-shot qualification carrier over the exact installed `Dot2ApiWorkerAdapter` bytes to prove the real Dot task, wake, result, cancellation and restart contracts. It must use the same config, credential loader, loopback endpoint, Python and transport digests and preserve one idempotency carrier. This diagnostic is not an Executive Job, does not route work and creates no persistent lifecycle state. Attach the complete receipt to the source carrier.
2. **Executive qualification:** only after independent review accepts that real-turn receipt may the same source carrier set `ADAPTER_DESCRIPTORS["dot2api"].implemented=true`. Keep provider/alias/global routing disabled. Then execute one exact admitted Executive research Job through the normal broker and originating parent.

The complete campaign is:

1. **Readiness:** local service ready, broker status healthy, exact config/release digests match, dedicated UID sweep passes.
2. **Happy path:** after the descriptor gate is lawfully opened, one `READ+RESEARCH` Job submits exactly one task, records its exact task ID, wakes the intended Dot, returns schema-valid JSON, and reaches an Executive terminal result consumed by the exact originating parent.
3. **Duplicate request:** same Attempt/idempotency key returns the same provider task; changed payload conflicts. Submission count remains one.
4. **Malformed output:** duplicate JSON keys, NaN/Infinity, non-object output, wrong schema and oversized output become `INVALID_RESULT`; prose is never accepted as structured success.
5. **Cancellation race:** queued/running cancellation reaches `CANCELLED`; a Dot completion that wins the race remains completed and is not relabeled cancelled.
6. **Response loss:** interrupt after provider submission but before response. Reconcile the original task/idempotency carrier; do not resubmit. Unknown effect remains quarantined.
7. **Restart:** stop the local carrier after the task ID is persisted, restart the broker, reattach through `WorkerRecoveryBinding`, and collect the same task without another submission.
8. **Provider outage:** status reads stop at the bounded monotonic deadline. The exact task ID remains recoverable; no second provider task appears.
9. **Drift:** change Python, transport script, config, token ownership/mode, endpoint, provider/adapter pair or Runtime binding. Admission must refuse before provider I/O or preserve effect-unknown on the original carrier as appropriate.
10. **Isolation:** verify no credential bytes in Runtime, Job/Attempt rows, process argv, plist, environment-key receipt, logs, Git diff, test artifacts or model-visible output.

Record exact release SHA, Python and transport digests, Dot2API upstream revision, host/worker identity, task ID, Job/Attempt IDs, clocks, test/CI/review identities and originating-parent consumption evidence. Unknown model serving, provider usage and cost stay unknown.

## Activation boundary

Passing the campaign does not edit routing automatically. A separate reviewed activation must:

- set the exact provider/Capacity record live;
- change `providers.dot.enabled` and `autonomous_allowed` only when current routing law permits it;
- make `dot.research` worker-eligible and place it in an explicit suitability tier;
- bind exact host capacity and required capability/profile digests;
- preserve Codex/Claude fallbacks and review separation;
- prove rollback.

Until then the adapter implementation exists, but its descriptor and normal Model Router selection remain closed.

## Rollback

1. Disable/remove the Dot Capacity join and keep provider/alias routing disabled.
2. Stop and boot out the Dot2API worker plist. Reconcile any active Attempt and exact provider task before removing the socket.
3. Revoke the caller token and Dot token independently. Disable Dot subscriptions; an in-flight callback cannot be recalled.
4. Preserve Runtime/Attempt evidence and provider task IDs. Do not delete or recreate them to make the system appear clean.
5. Remove host config/provider home only after the original carrier has no unresolved effect and retained evidence has been archived under its canonical owner.
