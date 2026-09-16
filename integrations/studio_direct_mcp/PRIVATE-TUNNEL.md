# Studio Direct private tunnel

Studio Direct connects ChatGPT to the maintained Desktop Commander engine on this Mac through OpenAI Secure MCP Tunnel. ChatGPT selects **Tunnel** and **No Auth**. This path does not require a public hostname, inbound firewall port, Tailscale Funnel, or a second application OAuth grant.

## Trust and sessions

The tunnel runtime authenticates to OpenAI with an existing account-specific runtime key reference. The tunnel object associates the intended Platform organization and ChatGPT workspace. Each account gets a dedicated loopback listener and session map; the server assigns a fixed `tunnel:<account>` principal for that listener.

This principal identifies the configured channel. It does not cryptographically identify an individual ChatGPT user or conversation. Anyone permitted to use that tunnel receives the same Mac-user authority, subject to ChatGPT's own plan and action controls. Other processes running locally on the Mac can also reach the loopback listener. Use this topology only for the trusted accounts intended to have that authority.

The adapter always binds `127.0.0.1`, refuses the existing OAuth port 45017, rejects non-loopback peers, and does not trust forwarded identity headers. It imports the existing gateway and uses one persistent Desktop Commander child per configured account. ChatGPT can create a fresh MCP session for every tool without losing process or search handles. Account backends remain separate, with four concurrent backend requests and four queued requests per account. Completed idle frontend sessions can be reclaimed at the configured 64-session private-seat cap without closing the child. Duplicate requests are rejected; an ambiguous timeout remains `EFFECT_UNKNOWN` and is never replayed. A timeout taints its originating session while preserving the healthy shared child. If the child actually dies, every attached session is tainted; only a new session can obtain a new backend generation. The generic public gateway retains its default per-session isolation.

There are no 15-minute application access tokens on this private path. The owned tunnel LaunchAgent passes an explicit five-hour transport lifetime, and private gateway configuration allows five hours of idle session retention. These settings avoid routine transport recycling during a two- or three-hour session; they are not a promise that ChatGPT never reconnects. After a lost session, establish a new session for future work and inspect the outcome of any interrupted operation before issuing it again.

## Runtime layout

- Source: `integrations/studio_direct_mcp/` in the canonical Mastermind repository; attended work may use a linked workspace, but merged source remains the release authority.
- Gateway installation: `~/.local/share/studio-direct-mcp/private/<account>/`.
- LaunchAgent: `com.mastermind.studio-direct-private.<account>`.
- Tunnel profiles: `~/.config/tunnel-client/studio-direct-private/`.
- Tunnel supervision: `com.mastermind.studio-direct-tunnel.<account>` runs the pinned official tunnel-client binary at login, with explicit `5h` transport lifetime, concurrency `4`, and the official `30s` MCP startup wait.
- Manage the tunnel with `private_tunnel_service.py stage|start|status|stop`. Do not run `runtimes connect` for a migrated account: it overwrites the profile and creates a second supervisor.
- No key values belong in this directory, command arguments, receipts, or chat. Profiles contain only `file:` references.

`private_service.py stage` creates an account installation; `start`, `status`, and `stop` operate on that exact account. The helper verifies installed content and service identity. It is not an updater or a second recovery manager. Dependencies are installed from the committed package lock with `npm ci --omit=dev --ignore-scripts` before the first start.

## Local control

`studio-direct status` reports the configured C1 gateway and tunnel together. `studio-direct start` starts the gateway, then the tunnel, and waits for both to become ready; `studio-direct stop` stops the tunnel before the gateway. Use `--account chatgpt2` or another installed account label to select that account explicitly. The command is installed under `~/.local/bin`, with its service helpers stored internally under `~/.local/share/studio-direct-mcp/control`, so it does not depend on the external checkout being mounted. It does not create tunnels, change credentials, replay calls, or add a watcher.

## Verification

Local proof and native ChatGPT proof are separate:

1. Core and adapter regressions: run the Node tests and the isolated Python service tests.
2. Start the installed private gateway, then run `node private-acceptance.mjs http://127.0.0.1:<port>/mcp`. It checks absent OAuth metadata, lists the real engine tools, reads eight lines of the system version file, runs a unique harmless `printf`/`true`, and deletes its MCP session.
3. Run `tunnel-client doctor` for the exact profile. No Auth metadata returning 404 is expected; initialization must succeed.
4. Start the owned tunnel LaunchAgent and verify `running`, `healthy`, `ready`, `managedAliasRunning: false`, and `transportTTL: "5h"` with `python3 private_tunnel_service.py status --account <account>`.
5. Run `node private-state-probe.mjs <absolute-private-gateway-module> --expect-shared` against an isolated real engine to prove cross-session process reads, creator DELETE, and twelve-session capacity churn.
6. Create/select the native ChatGPT app with the exact tunnel and **No Auth**. Invoke `studio_ping` and a bounded file read. Match the returned hostname, process generation, and calls in the installed gateway log. Test a harmless command only if the native account permits that correctly annotated tool.

An installed process, a green doctor check, or a tool-list scan alone does not prove native ChatGPT execution. Receipts in `work/` record the scope of each check. Existing public OAuth and Desktop Commander services are separate; only the owned public Funnel 8443 is eligible for retirement after private native verification.

## Product priority

Workbench remains the first choice for project-specific workflows and bounded project context. Studio Direct supplies general host tools when Workbench lacks a capability or is unavailable. Both can share maintained local capabilities without sharing tunnel profiles or replacing each other's active services.

Official references: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) and [ChatGPT developer-mode availability and action permissions](https://help.openai.com/en/articles/12584461). The live C1 Personal account successfully admitted the correctly annotated `start_process` tool on September 13, 2026. Native capability is verified per account; tool annotations remain truthful.

## Verified C1 checkpoint

C1 Personal (`chatgpt1@mastermind-x.com`) installed Studio Direct with No Auth, then executed native `studio_ping`, an eight-line system-version read, and a harmless marker command. The acceptance chat is https://chatgpt.com/c/6aa7482c-23e0-83ea-b745-982558f05f62 and its receipt is `work/private-c1-native-acceptance.json`. The final native test after the repair is recorded in `work/private-c1-final-native-acceptance.json`: three distinct MCP sessions successfully performed ping, one bounded process start, and continuation of that exact process. ChatGPT returned both markers, exit 0, and no tool errors in 16 seconds, including a deliberate two-second sleep. Final acceptance chat: https://chatgpt.com/c/6aa75bd5-4f54-83e9-9a7d-47d6a107c0f0 .

The owned public Funnel 8443 was removed after this native proof. Tailscale private 443 remains pointed to 127.0.0.1:18789. The old OAuth gateway was stopped after confirming zero active sessions; its configuration was retained. The original hosted Desktop Commander service remained healthy throughout.

Migration detail: official `runtimes rm` removes the generated profile and local runtime log as well as alias metadata. If removing a stopped alias, do so before staging the replacement LaunchAgent profile. During the C1 migration, the exact manifest-matched profile was restored immediately after alias removal, and stop/start then verified the saved profile loads successfully. It contains a file reference, never key bytes.
