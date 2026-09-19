# Studio Direct

Studio Direct connects an authorized ChatGPT account to the Mac Studio's existing Desktop Commander engine through our own Streamable HTTP MCP gateway. It is a private host-tool fallback. Workbench remains the priority for first-party project context and governed workflows; this gateway can be useful independently while Workbench's account integration is completed.

The gateway binds to `127.0.0.1:45017`. Its external endpoint is `https://mac-studio.taila6eca1.ts.net:8443/mcp`. Tailscale Funnel8443 is active under the user's explicit authorization; ChatGPT account linking still requires successful OAuth discovery and approval. Existing private Tailscale port 443 and the existing Desktop Commander remote service are separate.

## Runtime and account access

The service label is `com.mastermind.studio-direct-mcp`. Installed files and private OAuth state live in `/Users/chriswong/.local/share/studio-direct-mcp`. The backend is pinned to `/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js`; the new gateway never modifies that engine or its existing remote parent.

Each MCP session receives its own stdio backend child. The local tool surface has the Desktop Commander catalog plus `studio_ping`; when the bounded typed-Git publisher is configured, it also adds `studio_git_publish_status`, `studio_git_commit_current_changes`, and `studio_git_push_current_branch`, plus `studio_web_commission_materialize` where the host commission compiler is installed. These tools can access files and run processes with the Mac user's permissions. OAuth approval grants `studio.control`; it is not a narrower filesystem sandbox.

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

## Typed Web publication

The typed publication plane exists so an attended Web operation can publish a commission artifact without pushing a rendered document or a heredoc through a generic process tool. The journey is:

```text
compact commission request
  -> studio_web_commission_materialize   (host compiler renders research/executive_commissions/COMMISSION.md)
  -> studio_git_commit_current_changes   (fenced by the exact expected local HEAD)
  -> studio_git_push_current_branch      (exact non-force ref push, exact remote SHA readback)
```

Every destination is host-resolved. The push destination is qualified in full before any effect: `remote.origin.pushurl` and `url.<base>.pushInsteadOf` rewrites are expanded, the result must be the single host-allowed repository the operation also reads back from, and the authorized ref effect stays one branch regardless of ambient `push.followTags`, `push.recurseSubmodules` or `remote.origin.mirror` configuration. The caller supplies an `operation_id` and, for materialization, one compact `mastermind.craft_commission_request.v1` object of at most 16384 serialized bytes. The repository, remote, workspace path and `sol/web-*` branch come from the canonical `mmx-workspace` registration; the commission path is the fixed `research/executive_commissions/COMMISSION.md` expected by the trusted resolver. There is no caller-selected repository, remote, branch, path, force option, shell command, provider, model or account anywhere on this surface.

`studio_web_commission_materialize` is an adapter, not a compiler. It invokes the incumbent Mastermind Craft commission compiler (`research/worker_craft/mastermind-craft/scripts/brief.py`) over `argv` with the compact request staged as a private bounded file outside the workspace, then refuses the result unless the compiler's declared `commission_sha256` is the SHA-256 of the exact bytes it returned and the compiler reports no execution authority and no provider, model or account selection. The bytes are staged and renamed into place, then read back and hashed again before the call reports `APPLIED`. Identical existing bytes report `ALREADY_APPLIED` without rewriting, so repeating the call after an uncertain result reconciles by exact digest readback instead of blind retry.

Configure it under `gitPublish` alongside the typed-Git keys:

```json
{
  "gitPublish": {
    "enabled": true,
    "workspaceCli": "/ABSOLUTE/PATH/mmx-workspace",
    "gitBinary": "/usr/bin/git",
    "sourceRepository": "/ABSOLUTE/PATH/Mastermind",
    "allowedRemoteUrls": ["https://github.com/OWNER/REPO.git"],
    "commissionCompiler": "/ABSOLUTE/PATH/Mastermind/research/worker_craft/mastermind-craft/scripts/brief.py",
    "commissionCompilerInterpreter": "/usr/bin/python3"
  }
}
```

The compiler is an optional host dependency. Omitting `commissionCompiler` and `commissionCompilerInterpreter` leaves the typed-Git plane fully usable and simply does not advertise the commission tool. The private installer wires these two keys automatically when the compiler is actually present in the same checkout the typed-Git plane already publishes from and an absolute `python3` exists, so an installation that predates the compiler offers no tool that cannot run, and re-staging picks it up once it lands. That compiler is still unprotected on its own PR stack, so `git-publish.test.mjs` proves this adapter against its frozen process contract through `fixtures/commission-compiler.mjs`, and its real-compiler test skips while the compiler is absent from the checked-out base rather than vendoring a copy of it.

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

`service.py stage --source ABSOLUTE_SOURCE --node ABSOLUTE_NODE --backend ABSOLUTE_BACKEND` stages this exact installation. It refuses foreign, changed, symlinked or loaded installations before writing. An intentional update from the same source requires stopping this service first; installed bytes must still match its prior manifest. Install locked dependencies into the runtime, then use `python3 service.py start` and `python3 service.py status`.

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
