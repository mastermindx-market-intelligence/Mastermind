# Studio Direct

Studio Direct connects an authorized ChatGPT account to the Mac Studio's existing Desktop Commander engine through our own Streamable HTTP MCP gateway. It is a private host-tool fallback. Workbench remains the priority for first-party project context and governed workflows; this gateway can be useful independently while Workbench's account integration is completed.

The gateway binds to `127.0.0.1:45017`. Its external endpoint is `https://mac-studio.taila6eca1.ts.net:8443/mcp`. Tailscale Funnel8443 is active under the user's explicit authorization; ChatGPT account linking still requires successful OAuth discovery and approval. Existing private Tailscale port 443 and the existing Desktop Commander remote service are separate.

## Local M2 versus remote routes

**M2 is the Studio Direct gateway's local backend, not a remote fleet route.**
For an authorized M2 diagnostic, use a fresh, **unselected** Studio Direct MCP
session on the M2 account gateway. The ordinary Desktop Commander tools on
that session target local `m2studio` without any `studio_select_host` call.
A bounded, read-only `get_config` plus `start_process("hostname")` on the
**same unselected session** can verify the actual local host when authorized;
the observed hostname on 2026-11-07 was `m2studio` (exit 0).

`studio_select_host({hostRef: ...})` binds an MCP session **once** to one
explicitly configured *remote* route. It is not a generic fleet-host picker:
the `physicalFleet` section of `studio_fleet_status` is advisory Fabric
visibility, not the Studio Direct remote-route allowlist. The installed
`admin-business` M2 gateway's `fleetRouting.routes` contained `mini3`
and `mini4` at the November 7 observation, **not `m2`**. Do not hard-code
those minis as permanent inventory; inspect authorized installed configuration
rather than treating a fresh online fleet node as a selectable remote route.
Once the session has dispatched local Desktop Commander tools, it cannot
subsequently select a remote host; use a different lawfully authorized new
session for a genuinely different remote operation, not to replay a refusal.

Calling `studio_select_host({hostRef: "m2"})` on this gateway is therefore
the **wrong action**. The original `FLEET_ROUTE_PREFLIGHT_REFUSED` response
was `NOT_APPLIED`, before local/remote host dispatch. It proves neither
M2 outage nor lost M2 permission. Retain the denied selection as a historical
refusal; do not repeat it via a second account, host, connector or identity.
Independent, authorized local read-only diagnostics use the existing local
backend and do not replay the denied remote-selection effect. This path does
not grant Hermes/native installation, Fabric admission, privileged access,
Ubuntu1 C26 root/admin journal access, or permission to retry a separate
denied effect.

The current installed gateway's generic preflight error can omit the specific
`FLEET_ROUTE_HOST_NOT_CONFIGURED` reason. The existing source candidate
[PR #1773](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1773)
contains reason-code qualification but is not assumed installed; do not
duplicate its source writer. Original M2 diagnosis/readback:
[PR #2184 comment 6702814736](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2184#issuecomment-6702814736).
New sessions also load the same-pinned `docs/sol_skills/COLD_START.md`
local/remote distinction before concluding M2 host access is blocked.

## Runtime and account access

The service label is `com.mastermind.studio-direct-mcp`. Installed files and private OAuth state live in `/Users/chriswong/.local/share/studio-direct-mcp`. The backend is pinned to `/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js`; the new gateway never modifies that engine or its existing remote parent.

Each MCP session receives its own stdio backend child. The local tool surface has the Desktop Commander catalog plus `studio_ping`; when the bounded typed-Git publisher is configured, it also adds `studio_git_publish_status`, `studio_git_commit_current_changes`, and `studio_git_push_current_branch`. These tools can access files and run processes with the Mac user's permissions. OAuth approval grants `studio.control`; it is not a narrower filesystem sandbox.

OAuth uses public clients, PKCE S256, an exact `/mcp` resource audience, single-use one-minute codes, 15-minute bearer tokens, and rotating seven-day refresh tokens. Every connection requires an exact local approval. An operator label identifies the approved connection; it does not establish a verified ChatGPT email identity. No ChatGPT password, account cookie, or OpenAI API key is collected by this gateway. Tokens are hashed in mode-0600 state with serialized atomic updates. Local revocation invalidates tokens and unredeemed codes. Each request revalidates its token and binds its MCP session to the approved principal and client.

ChatGPT registers through its documented OAuth callback paths. The browser waits while the local operator reviews and approves its displayed request ID:

```sh
node /Users/chriswong/.local/share/studio-direct-mcp/auth.mjs \
  --state-dir /Users/chriswong/.local/share/studio-direct-mcp/state pending

node /Users/chriswong/.local/share/studio-direct-mcp/auth.mjs \
  --state-dir /Users/chriswong/.local/share/studio-direct-mcp/state \
  approve REQUEST_ID --label chatgpt1
```

Compare the request ID in the browser with the CLI entry before approval. The callback origin and client name alone do not authenticate who initiated the request. The approval command returns the principal ID needed for revocation:

```sh
node /Users/chriswong/.local/share/studio-direct-mcp/auth.mjs \
  --state-dir /Users/chriswong/.local/share/studio-direct-mcp/state \
  revoke PRINCIPAL_ID
```

## Failure behavior

A timed-out or disconnected tool call returns `EFFECT_UNKNOWN`, taints that session, and closes only its owned backend. The gateway never replaces the child within that failed session. Further work requires explicit initialization of a new session. Opening a new session does not resolve or authorize replay of the old call; inspect its actual effect first.

Duplicate `tools/call` JSON-RPC IDs are refused with HTTP 409 for the lifetime of their session. The gateway retains up to 4096 call IDs, then requires a new session for future work. The generic gateway defaults to eight sessions; the private Business-seat installer configures 256 frontend sessions while retaining four active backend operations and four queued operations per account. Authenticated GET returns405: this connector does not need an idle stream for unsolicited server events. Request-scoped POST streaming remains supported. The idle GET stream previously blocked later requests through the public transport. Inactive sessions expire after 30 minutes when no backend operation is active. Client DELETE releases its session immediately.

The gateway logs tool names, timings and outcome classes, without arguments, file contents or bearer tokens. Desktop Commander may itself perform its normal feature-flag, telemetry and browser-dependency activity; this project makes no claim that the engine is network-isolated.

## C1 fleet gateway Git-failure correction

The formatter compiler, the native installer's build validator, and its exact
retained launcher source remain in the original Control bundle. Its current
63-file closure contains the previous 13 helpers plus the 50 fixed Go reader
inputs declared by control_bundle.py. Those inputs include the source records,
candidate bytes, and exact patches needed to validate native42 memory/support
through the APPLICATION transition from an installed location.

The original bundle owner accepts the exact prior 3-, 4-, 10-, and 13-file
cohorts only for verification and migration under the observed original digest.
The 10-, 13-, and 63-file cohorts retain the existing required lock and strict
bytecode/layout checks. Runtime admission requires the full current 63-file
inventory. Every file is sealed and captured; the manifest's source path is
provenance and cannot supply an absent dependency. The installed-reader test
removes its temporary source checkout before validating the real retained Go
plan in a fresh isolated interpreter, and verifies that preview leaves the
original selection, bridges, and receipts unchanged.

Installed invocation loads the compiler from the authenticated captured bytes.
An existing `fleet-status-module-successor` record blocks formatter preview and
apply until that original owner is reconciled; this transition never edits it.

The installed C1 fleet gateway (`chatgpt1`) is an older module than the current
protected `gateway.mjs`. Its typed-Git handler discarded the thrown exception
and answered `REFUSED` / `NOT_APPLIED` / `TYPED_GIT_PRECHECK_REFUSED` for every
thrown status, commit and push. That is false for a mutation: a thrown commit
or push is not proof that the source ref was never updated, so the effect is
unknown rather than refused. The correction applies the current protected
gateway's own failure classification to that exact old module and to nothing
else.

`fleet_git_failure_compat.py` is the deterministic source compiler for that one
transition. It is not a runtime listener, an installer, a publisher, a registry,
a queue or a service, and it never touches a host, an installed directory, a
credential or a live effect.

| identity | value |
|---|---|
| predecessor Git blob | `f87ac012339e82fe46bce5ddc70d1d04183d1b6e` |
| predecessor SHA-256 | `17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30` (101068 bytes) |
| successor SHA-256 | `336de8ed10e7da483d46e93bd98439fd00c3e277111b39b5baa9cf0e68074674` (102141 bytes) |
| successor Git blob | `c02bcdada5217bbc987099e90ebdce236f023b86` |
| reference gateway SHA-256 | `c000159636ca5f42b9e91d1d2120f78cd22119711230e264952462e4e2a3f2da` |

The compiler accepts exactly the predecessor bytes. It checks exactly one
original typed-Git catch and one insertion boundary, preserves every other
byte, and checks the fixed complete successor hash. There is no prefix-only
hash, no marker-only qualification, no hash learning and no broad text
substitution. The two edited regions are byte-exact copies of the current
protected gateway's own classifier and typed-Git catch, so the classification
semantics are inherited rather than re-invented.

The successor answers:

| condition | result |
|---|---|
| thrown read-only status | `REFUSED` / `NOT_APPLIED` / `TYPED_GIT_READONLY_INSPECTION_REFUSED` |
| thrown commit or push | `UNKNOWN` / `EFFECT_UNKNOWN` / `TYPED_GIT_EFFECT_UNQUALIFIED`, and the session is tainted |
| real typed publisher result | unchanged, including its original stage and effect receipt |
| `selectedHostRef` set | `REFUSED` / `NOT_APPLIED` / `TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION`, before any publisher dispatch |

The classifier never inspects or serializes the exception object, the command
arguments, the credentials, the paths or the stderr. A client-added
`INVALID_ARGUMENT` is a presentation artifact, not an OS diagnosis.

This repairs effect and classification truth. It does not recover the lost
inner error and it does not prove that workspace inspection or publication now
succeeds.

### Finite procedure

The transition lives inside the incumbent `private_service.py` owner. There is
no second installer, publisher, registry or account.

```sh
python3 private_service.py upgrade --account chatgpt1 --port PORT \
  --source ABSOLUTE_SOURCE --node ABSOLUTE_NODE --backend ABSOLUTE_BACKEND \
  --c1-fleet-git-failure-compat \
  --publisher-expected-manifest-sha256 OBSERVED_MANIFEST_SHA256 \
  --publisher-preflight-only
```

The read-only preflight works while the service is still running. It reports
the exact before and target hashes, the preserved capabilities, the retained
native-pool pin state and any real blocker. The same command without
`--publisher-preflight-only` performs the closed transition once: it requires
the account lifecycle lock, the original manifest CAS, a positively stopped
matching launchd service and renewed exact preimages, then replaces only the
gateway and its manifest digest through the incumbent atomic-write,
manifest-last transaction.

The administrator supplies the exact observed manifest digest. The gateway hash
alone never qualifies an installation: the complete existing file map, the
manifest, config and plist hashes, the dependency seal, the Node and backend
identity, the account, the port and the actual permitted publisher pair are
verified first. A foreign account, an unrecognized publisher pair, a config or
fileset drift, a manifest CAS mismatch, a changed installed gateway, a loaded
service and a contended lifecycle lock all refuse.

Only `chatgpt1` is eligible. The route does not widen C2, C3 or any other seat
and creates no enrollment. The successor is compiled from the exact installed
predecessor bytes, so no caller-supplied source bundle reaches the
installation.

The transition preserves the installed configuration bytes, the fleet modules,
routes and scheduling caps, the dependency tree, the package files, the backend
and Node binaries, the plist, the authorization and the grants. It never runs a
package manager against an unchanged dependency tree.

The retained native-pool pin is checked by its existing complete transaction
proof, including the original intent, APPLIED result, selected phase and bridge.
An already accepted Paper v20 configuration is derived by the existing frozen
cohort planner and preserved. Apply holds the existing native publication lock
through its gateway/manifest transaction under the existing lifecycle lock.
Both new qualification suites run in the required Fabric compatibility gate:
`private_service_fleet_git_failure_test.py` enters its existing Python discovery,
and `gateway-fleet-git-failure.test.mjs` exercises status, commit and push through
the generated gateway. Historical fixture objects are read offline; missing
objects or an incompatible Git executable fail qualification.

A failure after the manifest commit is `EFFECT_UNKNOWN` until the same
transaction state is read back. There is no blind repeat, no automatic
restart, no replacement operation, no forced rollback and no deletion of prior
evidence. Recovery distinguishes the exact original bytes, the exact target
bytes and any foreign or mixed bytes. See `PIN_TRANSITION.md` for the retained
native-pool pin interaction.

## Build and verification

From this source directory:

```sh
npm ci --ignore-scripts --no-audit --no-fund
node --test auth.test.mjs gateway.test.mjs
python3 service.test.py -q
```

The tests cover OAuth approval, PKCE and audience binding, code reuse, expiration, revocation, refresh replay, concurrent state writers, private file permissions, session isolation, authentication and origin rejection, duplicate calls, backend timeouts and backend exits after an actual fixture effect. No missing implementation is counted as a skipped success.

`acceptance.mjs ENGINE_CONFIG` exercises production OAuth, local approval, HTTP MCP, the actual configured engine, a system-version file read and a harmless `printf`/`true` command. `--installed-local` uses the installed loopback service and a disposable grant, then closes the session and revokes that grant. `--remote` uses the configured public HTTPS endpoint and requires authorized external activation. It also rotates access/refresh tokens, proves the SAME MCP session remains usable, and invalidates both access tokens on revocation. Cleanup revokes the disposable grant on failure. Reports contain timings and the unique command marker, without file contents or credentials.

`private-acceptance.mjs http://127.0.0.1:<port>/mcp` is a separate harness for the dedicated private loopback listener, not the OAuth `acceptance.mjs` path: it asserts that no OAuth discovery metadata is present, exercises the real engine tools, creates a bounded marker file under the platform's own temporary root (`/private/tmp` on Darwin, `/tmp` on Linux) and reads that marker back through the bounded file tool, and runs a unique harmless `printf`/`true` command. A platform other than Darwin or Linux is refused with a `FAIL` receipt and a nonzero exit; there is no system-file fallback. It creates and revokes no OAuth grant. Its finalization steps are independent: a failed session termination, client close or marker-fixture removal is reported as a `FAIL` receipt with a named diagnostic alongside any original acceptance error, exits nonzero, and still emits the bounded receipt. Selecting the Linux root is a source-level portability change and does not by itself establish that the installed file policy may read the Linux marker path. It proves neither ChatGPT account linking nor native app adoption.

`smoke.mjs --stdio CONFIG --noop` measures the engine directly. `smoke.mjs --url BASE --token-file PRIVATE_FILE --noop` measures an already authenticated connection.

## Install, start and stop

`private_service.py stage --account ACCOUNT --port PORT --source ABSOLUTE_SOURCE --node ABSOLUTE_NODE --backend ABSOLUTE_BACKEND` stages one exact private-account installation. It refuses foreign, changed, symlinked or loaded installations before writing and records SHA-256 identities for the exact Node executable and Desktop Commander backend. An intentional update from the same source requires stopping this service first; installed bytes must still match its prior manifest.

The installer deliberately does **not** own the package manager. After stage/upgrade, install the lockfile-defined production dependencies in the returned runtime directory with the reviewed operator command `npm ci --omit=dev --ignore-scripts --no-audit --no-fund`, then run `python3 private_service.py seal-runtime --account ACCOUNT`. Sealing is allowed only while the service is stopped; it binds a canonical, host-path-independent digest of the installed `node_modules` tree, including relative symlink targets. Only then may `python3 private_service.py start --account ACCOUNT` load the LaunchAgent. `start` re-hashes Node, the backend, and the complete sealed dependency tree before any launchd effect. Same-path byte drift, dependency drift, absolute/out-of-tree dependency symlinks, an unsealed v2 manifest, or a legacy v1 manifest all refuse. Legacy installs must use the explicit stopped-service `upgrade` path and be resealed before restart.

`stop` intentionally remains available when Node/backend/dependency bytes have drifted: it verifies the existing manifest, staged source/config/plist and exact loaded launchd path, but does not require the new runtime seal to be healthy before bootout. Runtime drift therefore cannot trap a running service. `status` remains observation only.

The LaunchAgent uses an explicit Homebrew PATH and `ProcessType=Interactive`, matching an interactive MCP server's latency needs. `KeepAlive` restarts a failed gateway process, but does not replay calls or recover old sessions. Readiness proves the gateway is accepting HTTP, not that an account has connected or a tool has run.

After exact approval, `python3 service.py funnel-enable` checks local health, OAuth discovery and unauthenticated MCP rejection, then adds only HTTPS port 8443. It compares the complete existing port-443 subtree before and after. `python3 service.py funnel-disable` removes only that owned port and target. Never use a global Tailscale reset for this service.

For rollback, disable its funnel and run `python3 service.py stop`. Both operations are limited to this gateway. Preserve its state and source for inspection; broad process kills and directory deletion are unnecessary.

## Plugin integration

ChatGPT's private plugin form uses name **Studio Direct**, Server URL `https://mac-studio.taila6eca1.ts.net:8443/mcp`, OAuth, and scope `studio.control`. Select the exact locally approved request, finish OAuth, then verify `studio_ping`, a read, and an authorized harmless command in ChatGPT. A prepared form or successful local test is not proof that this account integration is complete.

ChatGPT stores an admin-approved frozen snapshot of an MCP app's tools and inputs; a later server-side `tools/list` change does **not** automatically update already approved chats/workspace actions. Compare the installed gateway catalog with the actual ChatGPT surface before claiming an action is available. As verified against OpenAI's current [custom MCP connection guidance](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt) and [troubleshooting guidance](https://help.openai.com/en/articles/20001497-troubleshooting-plugins-and-apps-in-chatgpt) on 2026-11-03 UTC, Business as well as Enterprise/Edu administrators can refresh an existing custom MCP app's tool list from workspace app settings without recreating it. The administrator needs permission to manage that exact app and a valid connection. Use the existing app's supported refresh/review controls where available; preserve its account, connection, identity, audience and unrelated actions. New actions may require explicit enablement. Do not treat a gateway restart, a new chat or OAuth reconnect alone as an action refresh, and do not prescribe app recreation from older launch-era documentation. Personal-account UI availability must be verified separately; this workspace guidance is not an account or permission grant.

### Publication capability check before substantial source work

Use existing read-only discovery, not a dummy commit/push or a new readiness service. For work in Macro or Terminal, first verify that the actual exposed publisher schema accepts `repository` and that the existing `studio_workspace_repositories` response includes the intended canonical alias. If a prepared integration needs two parents, also verify that the actual commit tool exposes the nested `merge` object with `expected_protected_base_sha` and `expected_tree_sha`. Only then use read-only publication status for the original operation. An old Mastermind-only tool schema must not receive undeclared arguments or be tested with a known-refused Macro operation.

Keep three capability diagnoses separate: missing installed repository enrollment; installed publisher implementation lacking merge support; and a stale client action snapshot despite an updated server. A generic `TYPED_GIT_PRECHECK_REFUSED` also does not, by itself, prove an access denial: reconcile the original effect and use one bounded read-only check of the same owner to distinguish a genuine policy refusal from a command deadline or binding failure. C4's native workspace status was observed to succeed in 24.256 seconds against a 15-second publisher deadline; its enrollment candidate uses the existing bounded 45-second command policy while preserving the 60-second push limit. Do not retry mutations blindly or patch live sealed configuration to bypass a refusal. Report the exact missing capability and preserve the original source/work/effect. A completed `native-pool-pin` transaction requires its owning successor path; never hand-edit sealed configuration, delete the retained pin, or use a different account to evade the refusal. Existing review, branch protection and release acceptance still govern after these capability checks pass.

`plugins/studio-direct/` contains validated Codex plugin packaging for the remote endpoint. It is source packaging until a marketplace installation and its native OAuth callback flow are verified. ChatGPT plugin connection and Codex plugin installation are distinct steps.

Current install, acceptance reports, routing logs and pending actions are recorded in `work/` and `work/STATUS.md`; these are local operational artifacts, excluded from Git. No public issue, provider report, release or app-directory submission is part of this private build.

## Current public-path evidence

After removing the optional idle event stream, the authenticated public HTTPS acceptance passed with27tools, reads176–185ms, a harmlesscommand205ms, and same-session refreshed read192ms. First tools/list took1.733s. The test substituted a fresh public DNS A record for this one hostname because the Mac system resolver currently fails; TLS validation remained enabled. This is gateway/tunnel/engine proof, not native ChatGPT invocation proof. See `work/public-no-idle-stream-acceptance.json`.

Access tokens remain15minutes. Refresh tokens rotate automatically when a client exchanges them, and each newly issued refresh token lasts7days. Active2–3hourworkflows do not require300minuteaccess tokens. Native ChatGPT automatic refresh remains unproven until account linking succeeds.

## Bounded text-result ingestion

Catalogued backend tools without a strict `outputSchema` preserve small results byte-for-byte at the object boundary. When a text-only result exceeds 16 KiB of serialized MCP tool-result JSON, the gateway returns `OUTPUT_PAGED`, a bounded head/tail preview, original error truth, a receipt, original byte count, and SHA-256. JSON-RPC/HTTP/SSE framing is outside this payload measurement. Native media, mixed content, schema-bound tools, and tools not yet observed in the catalog are unchanged; this is not a universal traffic cap.

Use `studio_output_page({receipt_id, offset})` with offset zero, then each returned `next_offset`, to read only needed portions. Concatenating the page text reconstructs the original UTF-8 JSON result, including its `structuredContent`, `_meta`, and `isError`. Verify its byte count and digest before treating a complete reconstruction as evidence. Page success says only that bytes were read; it is not the original tool's verdict. A preview is explicitly incomplete.

Retention belongs to the existing backend lifetime: shared-account frontends use their existing principal-bound `BackendOwner`, while per-session mode retains within that session's backend. A creator frontend's DELETE does not erase a shared owner's results. Different principals and separate backend generations cannot read one another's receipts. Each owner retains at most eight results and 8 MiB, evicting oldest results; owner closure clears retained bytes. No disk store, transcript history, scheduler, retry mechanism, or new identity plane is added.

`OUTPUT_NOT_RETAINED` means no full-result receipt exists. `OUTPUT_NOT_AVAILABLE` means the requested receipt is unknown, expired, or belongs elsewhere. `OUTPUT_PROJECTION_FAILED` means a backend response was received but could not be projected. None authorizes repeating the original action. Reconcile its original source/effect instead. Projection failures are kept out of backend timeout/taint handling, and original error flags remain truthful. Do not log result bodies, request arguments, or opaque receipts as telemetry.

The existing private installer stages `output-budget.mjs` and recognizes both exact historical file layouts for controlled stopped-service upgrades. Tests use local fixture backends and temporary installer roots, not installed accounts. Source/fixture qualification does not establish protected publication, installation, native-account adoption, or improved Pro-turn behavior; those remain separate release and acceptance gates.
