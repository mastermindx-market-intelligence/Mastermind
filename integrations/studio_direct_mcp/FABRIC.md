# Mastermind Subagent Fabric MCP

This is a typed interface for the **existing** attended M2 Fabric adapter, not a new orchestrator. The parent Web session delegates bounded, independently checkable work while retaining judgment and acceptance. Existing `fabric_task.py`, `pick.py`, `remote_sub.sh`, broker/host admission and `pool_ledger.py` keep their responsibilities.

## Components and ownership

`ChatGPT -> enrolled private tunnel -> existing Studio gateway -> fabric-backend.mjs -> maintained Desktop Commander process owner -> installed fabric_task.py -> incumbent provider/host pool`.

The backend exposes seven tools: `fabric_capabilities`, `fabric_request`, `fabric_status`, `fabric_wait`, `fabric_result`, `fabric_accept`, and `fabric_controller_output`. The outer gateway may expose its existing liveness and retained-output paging tools. The Fabric-only installer profile explicitly disables Git, Paper, repository workspaces and commission publication. It does not modify another account's installed service, access settings or sandbox.

The existing Studio private service and tunnel supervisors retain lifecycle ownership. Desktop Commander retains adapter process handles; the Fabric retains run state and results. The facade's bounded, in-memory attempted-call and controller-handle indexes only prevent frontend replay and arbitrary PID access within their generation. They are not a second durable operation ledger, queue, watcher or retry mechanism. No provider credentials are read or passed by the facade.

## Trust and input boundary

This installation is for already-authorized **trusted machine-owner channels**. A private tunnel principal identifies the enrolled channel, not an independently authenticated ChatGPT user, browser conversation or individual root. `root_id` and `parent_id` are correlation/continuity metadata, never authentication or permission grants. Do not use this design as a multi-tenant service.

Every request supplies a verified original operation root, the actual immediate parent, and one stable new child ID. A fresh attended operation may use the incumbent operation naming and source-custody convention; do not fabricate `CODEX_THREAD_ID`, borrow a host environment's sibling identity, or invent an identity registry. Nested work preserves the same original root. Existing Executive-submitted, active, accepted, or effect-unknown operations remain on their original carrier.

The tools do not accept arbitrary shell commands, adapter paths, working directories, providers, models, hosts, accounts or credentials. The operator pins the adapter, Python interpreter and worker working directory at installation. The default working directory is the literal `~`, expanded by the receiving worker's existing adapter path. A bounded packet must contain the required input or exact worker-accessible references; neither a Web `/mnt/data` file nor an M2 workspace is assumed available on another worker host.

Parameters have closed schemas. IDs use `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`. Packets are limited to 16,000 characters / 32,768 UTF-8 bytes, contain no NUL, and travel as literal stdin using a quoted heredoc. C0/C1/C2 classify the child independently; C3 requires a specific escalation reason. The existing router selects admitted qualified provider/host capacity. `subject_pool` expresses author-pool review independence only; it does not select the reviewer.

## Correct execution and recovery

1. Inspect `fabric_capabilities` once when this connection is unfamiliar; adapter presence is not current provider admission.
2. Select a stable child ID once. `fabric_request` reads that exact ID and submits only after a valid `NOT_FOUND` observation. Backend and adapter guards remain responsible for their respective concurrency boundaries.
3. Retain the returned controller PID together with run/root and connection generation. `CONTROLLER_CREATED` is delivery to the process owner, **not proof of worker START**. A started provider must be established by actual Fabric evidence.
4. Observe the same run with `fabric_status`, bounded `fabric_wait` (at most ten seconds), or the original `fabric_controller_output`. A `NOT_FOUND` observation after an interrupted request never proves no effect. A new backend generation cannot reconstruct the original PID binding.
5. Retrieve only an available result whose ledger root matches. The adapter response must fit the requested result limit (default 8 KiB; maximum 64 KiB). The facade captures the original CLI stdout bytes on M2 before process-output formatting, verifies byte count/base64/SHA-256, and returns those bytes as UTF-8 plus their digest.
6. Review the result and real evidence. Only then call `fabric_accept` with the reviewed digest, verification summary, and actual deterministic/reviewer method. It re-reads the current complete response and rejects a changed digest before calling incumbent acceptance; it verifies the ledger's accepted state afterward.

**Acceptance limit:** this digest identifies the complete adapter CLI response, not every referenced artifact. It does not make the legacy acceptance operation atomic or cryptographically attest the bytes originally reviewed. Do not claim stronger guarantees than the existing ledger supplies.

Any lost modifying response is `EFFECT_UNKNOWN` with no retry permission. Preserve the original child and process; do not create a replacement child, change carriers, kill a worker or manually release a lease. Missing result delivery is a same-run recovery problem, not a reason to rerun paid work. Read-only observations may continue without moving the operation. There is no facade cancellation or recursive spawn tool. A tool timeout, provider admission error, explicit permission denial and process exit are different evidence.

## Quota continuity

The production facade enables the existing adapter's bounded foreground quota
continuation. Before creating a controller it checks for `request --quota-fallback`
and `status --follow` support. An older installed adapter returns
`ADAPTER_CONTINUITY_UNAVAILABLE` before dispatch. Capabilities report whether the
adapter supports this contract, with a maximum of three sequential attempts.

Eligible ordinary requests can move to another admitted pool after a proven
pre-task capacity rejection. Inside the selected MiniMax/GLM Claude wrapper, a
single small provider request checks capacity before the task CLI, hooks or MCP
servers start. It uses the exact leased endpoint/model/account and a fixed prompt
with one maximum generated token; task content and tools are absent. The check
adds one request, has a 20-second whole-response deadline, and neither follows
redirects nor retries. Unknown responses and timeouts leave the original CLI path
available. Documented billing, authentication, policy and spend-limit responses
are distinct from capacity and do not authorize migration.

Automatic continuation requires the source-bound pre-task proof, actual process
cleanup, a strict terminal quota outcome, release of the original lease, and the
unchanged frozen task digest. A CLI's initial error alone is insufficient.
Successors keep the original root and immediate parent but receive distinct run
IDs and immutable predecessor links. Existing admission, model quality, account
and economic rules still select the successor. The whole attempt chain remains
within the original commission timeout; it creates no background queue or wake.

Status, wait and result return the actual `effective_run_id` and prior attempts.
Review the successful leaf's complete result and pass its explicit `accept_run_id`
to acceptance. Accepting through a failed origin is refused with
`ACCEPT_EXPLICIT_SUCCESSOR_REQUIRED`. Missing controller completion remains
unconfirmed; reading status never starts another attempt.

The native broker stores shared cooldowns across requests and permits only one
probe lease when a cooldown expires. Model aliases conservatively share their
account's short backoff; known cross-product subscriptions require explicit
existing `quota_scope` metadata. A failure after work starts preserves the
session and cools the allowance but does not automatically replay actions.
Native parent token/context exhaustion, fixed-model or artifact contracts and
cross-provider resume after tool activity require their existing lifecycle and
review owners. This feature does not restart a native parent conversation.

Roll out the complete native code generation first, then select this same facade
account's backend from the actual merged release with its existing service owner.
For the enrolled `subagent-fabric-c3` account, use the narrow
`private_service.py fabric-backend-release` preview and apply contract. It checks
the old manifest and full runtime seal, the merged backend's Git blob and SHA256,
and the exact preview plan; apply requires the original service to be unloaded.
It updates only `config.args[0]` and the corresponding three manifest fields,
preserving the gateway bundle, private SDK, account, tunnel, port and selected
protocol. The generic `upgrade` retains its same-backend-path requirement.
The operator separately reconciles existing controllers, then stops and starts
this original service through the same owner. See
`ops/native_fabric/quota_continuity/README.md` for native evidence, retention and
publication boundaries.

## Opt-in stateless protocol compatibility

The private Fabric profile may explicitly enable `modernFabricProtocol: true` through
`private_service.py stage` or `upgrade --modern-fabric-protocol`. It is off by default.
The setting requires the restricted loopback Fabric profile and the incumbent
`shared-account` BackendOwner. An unspecified upgrade preserves a manifest-verified
selection; `--no-modern-fabric-protocol` explicitly returns to the legacy profile.
Neither operation changes the account, port, backend entry, tunnel, credentials or
another installed account. Stop the existing account before upgrading, then install
its exact lockfile, seal and start through the same private service owner.

The pinned MCP v2 server and Node adapter validate the 2026-07-28 envelope, mirrored
headers, discovery and result encoding. The SDK era predicate preserves the existing
sessionful legacy handler while sending malformed modern claims to the modern
validator. Request-scoped views use the same backend owner and limiter, so completing
an HTTP request detaches its view without closing retained Fabric controllers or
results. Client metadata never supplies authentication; the existing private tunnel
principal is checked on each request. Only the seven Fabric tools and the existing
ping/output-page tools are available on this path. This does not supply individual
conversation authentication or the Executive v5 current-writer COMMIT fence.

`/readyz` reports the selected modern protocol only after its handler is constructed.
A modern `studio_ping` reports the protocol and backend generation; its `sessionId`
is null because this exchange does not create an MCP protocol session. These are
installation/selection observations, not worker execution or exact-parent acceptance.
Qualification still requires the actual originating parent to dispatch, consume,
adjudicate and act on its result through its native tool connection.

## Source and local tests

The Fabric facade continues to use the existing pinned SDK v1. The opt-in HTTP entry adds pinned MCP v2 server/Node packages in the same lockfile; the v2 client is a test-only dependency. It can run behind the existing private gateway's configured backend entry. Backend code and its SDK dependency resolution must come from an immutable reviewed release, not a mutable authoring worktree.

```sh
cd integrations/studio_direct_mcp
npm ci --ignore-scripts --no-audit --no-fund
node --test fabric-backend.test.mjs
python3 -m unittest private_service_fabric_test private_service_test private_service_workspaces_test private_service_commission_test -q
node fabric-preflight.mjs YOUR_UNUSED_CHECK_ID YOUR_VERIFIED_ROOT
```

The tests use an isolated local CLI fixture, never real provider credentials or the production ledger. They cover strict inputs, literal packet transport, same-ID rejection, uncertain effects, root mismatch, byte capture, changed-result rejection, acceptance separation, original PID binding, and preservation of the restricted installation across restage/upgrade.

`fabric-preflight.mjs` is a read-only real SDK/engine/adapter probe. `fabric-console.mjs` is an attended developer acceptance client: it issues one MCP call per input line, does not retry, and does not automatically accept a worker. Neither is an unattended orchestrator or proof of native ChatGPT installation.

## Restricted installation and connection

Use the existing `private_service.py stage` with `--fabric-only` for a **new distinct account/profile**, an unused observed loopback port, the protected release source, exact Node binary and released `fabric-backend.mjs` entry. A Fabric-only profile cannot acquire repository or commission publication tools. It remains restricted during restage/upgrade without another flag; an existing Studio profile cannot be repurposed by passing this flag.

After staging, install the lockfile-defined dependencies and use the incumbent `seal-runtime` and `start` operations. Preserve runtime, backend, dependency and manifest hash checks. Do not bypass a failed seal or change an existing active service. Existing runtime/tunnel managers may have newer installed manifest schemas; a rejected status read is not permission to rewrite those profiles.

Create/associate a private tunnel only through the existing official tunnel owner, with verified target organization/workspace and existing permitted key references. Keep runtime/admin keys on the host, never in the package or chat. Do not overwrite a migrated tunnel profile with `runtimes connect` or introduce another supervisor.

In ChatGPT, the supported private connection flow is **Plugins -> Add custom MCP server -> Tunnel**. Select the exact enrolled tunnel and its actual authentication mode, then complete the platform's required consent. An OpenAI-hosted tunnel is not a public `server_url`; do not invent one in `mcp.json`. Bind the packaged skill to the actual newly registered app ID only after that ID exists. Private tunnel connections are not public-directory submissions.

Publication, protected merge, host installation, tunnel readiness, plugin creation, individual account installation, tool snapshot exposure and native invocation are separate evidence. A passing local test or successful creation does not prove adoption across all six Web accounts. The final native acceptance requires this tool catalog, one admitted bounded worker, retained result consumption and explicit verified acceptance from the connected Web session. No Web turn is a daemon; unattended return requires its existing real owner and return path.

Official connection references: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels and https://developers.openai.com/plugins/deploy/connect-chatgpt .
