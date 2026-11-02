# Hermes BYOK — operator-triggered in-service native canary

**Status:** SOURCE-ONLY / NOT INSTALLED / NOT CERTIFIED. This slice is stacked after the native output verifier (#1947) and depends on the role-private localhost HTTPS CONNECT egress contract (#1952). The existing Grok Secretary must remain live.

## Why this is needed

A valid model-output parser in a developer shell does not prove that a Hermes role can authenticate, reach its intended provider, or remain network-confined on Ubuntu1. The pinned native subprocess is normally launched by `integrations.hermes_runtime.supervisor.ServiceRuntime` inside one `systemd --user` unit with `IPAddressDeny=any` and `IPAddressAllow=localhost`. Running a canary from a user's ordinary shell bypasses that unit's real confinement and is therefore not accepted evidence.

This candidate adds one `ExecReload` command to **each existing role service**. Systemd executes it as a control process in that service cgroup, using its original `EnvironmentFile=` and existing release. It calls `integrations.hermes_runtime.cli._canary` (same code path as `python -m integrations.hermes_runtime canary`) and the exact existing `ServiceRuntime._model_child_env` owner to reconstruct one role-private, proxy-bound model environment.

There is **no new daemon, Slack listener, timer, network listening socket, credential loader, Agent OS state, Executive Job/Attempt or fallback/retry queue** in this change. No child model request runs at install, service start, health check, or status read.

## Admission before every real attempt

An authorized Ubuntu1 operator first verifies all of these through the proper private host/credential owners:

1. #1952, #1947 and this PR have passed exact-head checks, independent non-author review, normal protected release and on-host installed-source validation.
2. The role's user unit, 0600 secrets file, provider pointer and **distinct** gateway/dashboard keys are installed. The on-disk manifest points to the actual current numbered release, whose install receipt has `upstream_attested=true`, and the local pinned Git checkout is exactly `1c0cd667746d3395fe9e1b6c74f8f85952486f18`.
3. The independently owned per-role localhost CONNECT proxy is listening with an actual inspected hostname/port allowlist. Secretary may reach only `ark.ap-southeast.bytepluses.com:443`, Meta-CEO only `api.z.ai:443`; off-list destinations and cross-role access are **proven denied**, not assumed from the URL. The native HTTPS client must still validate TLS; a token-bearing provider request is not a reason to relax `IPAddressDeny=any`.
4. The operator has explicitly authorized one provider-charged canary attempt on that host. A failure/timeout is not proof of no remote effect; reconcile the original attempt rather than blindly retrying.

Only once those gates are real, each role is triggered separately via the existing unit:

```sh
# On ubuntu1, by its authorized operator. No keys or prompt on command line.
systemctl --user reload hermes-runtime-mmsecretary.service
# Later, as another explicitly authorized attempt:
systemctl --user reload hermes-runtime-mmmeta.service
```

This is `ExecReload` (not a restart or reload-all hook), and the operator uses the installed systemd service, **not** `python ... canary` from an unrestricted shell. One invocation performs one fixed, nonce-challenged native `chat -Q --query-file - --format stream-json` request with an upper-bound timeout and byte limits. The model receives no Slack token, gateway bearer, arbitrary prompt, extra provider key or inherited shell proxy.

## Fail-closed criteria and proof boundary

The command refuses before loading secrets unless its process belongs to the exact role service cgroup. It refuses unmatched install paths, wrong release/role/manifest, unattested upstream, missing model credential, unconfigured role proxy, cross-role key exposure, invalid pinned model config, and unqualified binary/environment. Native model stderr/stdout and bearer values are never returned to the operator; the printed JSON is a bounded **redacted** output-observation receipt. The unit reports failure when the observation returns `BLOCKED` or process execution errors.

`PASS_CHILD_OUTPUT_OBSERVATION_ONLY` only says the expected pinned-style JSON stream and nonce were seen. It is **not** a remotely attested provider call, network-policy/eBPF enforcement proof, TLS peer proof, credential/billing receipt, Slack roundtrip, or production approval. The installed executable's build provenance, host-side process identity, actual network deny/allow controls and provider-side authenticated usage must be verified independently.

The same evidence must subsequently be linked to an authorized **original-parent** Slack dialogue through the already-existing Agent Dialogue owner and separately enrolled Secretary/Meta-CEO bots. Do not count the current #1958 synthetic CEO CONTINUE reply consumer as live Slack chat; it has no general role-bot ingress or installed host binding.

## Synthetic check

```sh
python3 -m unittest integrations.hermes_runtime.tests.test_operator_canary_reload -v
```

The tests use fake manifests, in-memory child credential ownership, an injected canary result and no external sockets. Passing them means `BUILT_NOT_PROVEN`, not `PROVEN_LIVE`.
