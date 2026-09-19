# Studio Direct

Studio Direct connects an authorized ChatGPT account to the Mac Studio's existing Desktop Commander engine through our own Streamable HTTP MCP gateway. It is a private host-tool fallback. Workbench remains the priority for first-party project context and governed workflows; this gateway can be useful independently while Workbench's account integration is completed.

The gateway binds to `127.0.0.1:45017`. Its external endpoint is `https://mac-studio.taila6eca1.ts.net:8443/mcp`. Tailscale Funnel8443 is active under the user's explicit authorization; ChatGPT account linking still requires successful OAuth discovery and approval. Existing private Tailscale port 443 and the existing Desktop Commander remote service are separate.

## Mosyle read-only MDM visibility

A private Studio Direct seat can expose cloud MDM status through the existing gateway and Secure MCP Tunnel without creating another MCP server or control plane. When the host has a secure credential file at `~/.local/share/studio-direct-mcp/secrets/mosyle.json` (owned by the gateway user with mode `0600`), the gateway adds exactly two tools:

- `mosyle_fleet_status` — bounded paged inventory/status reads for macOS, iOS/iPadOS, or tvOS.
- `mosyle_device_status` — status lookup for one exact serial number.

The host credential JSON contains Mosyle API integration fields `accessToken`, `email`, and `password`. Those credentials and the short-lived bearer token stay on the Studio host and are never returned through MCP. The adapter calls only Mosyle `/v2/login` and `/v2/listdevices`, requests a fixed bounded field set, and strips unknown response fields before returning data. No lock, wipe, erase, lost-mode, profile, application-install, or other MDM mutation capability is exposed.

If the credential file is absent, symlinked, owned by another user, or group/world-readable, Mosyle integration stays disabled or fails closed. Web sessions cannot choose another API endpoint, credential path, token, or host.

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

Duplicate `tools/call` JSON-RPC IDs are refused with HTTP 409 for the lifetime of their session. The gateway retains up to 4096 call IDs, then requires a new session for future work. The generic gateway defaults to eight sessions; the private Business-seat installer configures 64 frontend sessions while retaining four active backend operations and four queued operations per account. Authenticated GET returns405: this connector does not need an idle stream for unsolicited server events. Request-scoped POST streaming remains supported. The idle GET stream previously blocked later requests through the public transport. Inactive sessions expire after 30 minutes when no backend operation is active. Client DELETE releases its session immediately.

The gateway logs tool names, timings and outcome classes, without arguments, file contents or bearer tokens. Desktop Commander may itself perform its normal feature-flag, telemetry and browser-dependency activity; this project makes no claim that the engine is network-isolated.

## Build and verification

From this source directory:

```sh
npm ci --ignore-scripts --no-audit --no-fund
node --test auth.test.mjs gateway.test.mjs
python3 service.test.py -q
```

The tests cover OAuth approval, PKCE and audience binding, code reuse, expiration, revocation, refresh replay, concurrent state writers, private file permissions, session isolation, authentication and origin rejection, duplicate calls, backend timeouts and backend exits after an actual fixture effect. No missing implementation is counted as a skipped success.

`acceptance.mjs ENGINE_CONFIG` exercises production OAuth, local approval, HTTP MCP, the actual configured engine, a system-version file read and a harmless `printf`/`true` command. `--installed-local` uses the installed loopback service and a disposable grant, then closes the session and revokes that grant. `--remote` uses the configured public HTTPS endpoint and requires authorized external activation. It also rotates access/refresh tokens, proves the SAME MCP session remains usable, and invalidates both access tokens on revocation. Cleanup revokes the disposable grant on failure. Reports contain timings and the unique command marker, without file contents or credentials.

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
