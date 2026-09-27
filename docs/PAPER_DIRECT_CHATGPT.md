# Mastermind Paper: private Business direct MCP

Implementation carrier: Mastermind issue **#1011**. Operation:
`paper-direct-chatgpt-mcp-20260926-sol-001`.

## Build decision and current boundary

Use one existing tunnel and the existing guarded stdio server. Do not create another Paper
proxy, auth service, effect ledger, account, or public listener. The direct build exposes
`paper_inspect`, `paper_catalog`, `paper_read`, plus separately opted-in `paper_prepare` and
`paper_edit`; the exact set is verified over a real SDK stdio handshake. The same guarded bridge
remains the Paper safety/effect owner and retains its fixed loopback endpoint, tool/schema
allowlists, desktop mutex, exact file ID and snapshot checks, explicit write opt-in, post-read
observation, and EFFECT_UNKNOWN/no-replay semantics.

The raw vendor `paper mcp` route is not selected: convenience is not evidence that it preserves
our guard contract. Studio Direct remains a legacy client, not a dependency of normal direct
Paper operations. It is not a fallback after a direct-app permission or safety denial.

**Direct `paper_prepare` + target-bound edit: PROVEN_LIVE on the Ryan Business direct v6 route.**
The accepted #1011 canary used the private Mastermind Paper app to bind the background scratch file
by exact `fileId` without changing the user-active MASTERMIND PAGES document, then performed one
bounded `set_text_content` edit with `APPLIED_RESPONSE_OBSERVED`, same-carrier post-read, screenshot
and JSX verification. No replay occurred and the user-active file remained unchanged. This is real
Ryan-route acceptance, not a claim that every Business seat is enrolled or that every future edit is
safe without its own fresh target/snapshot checks. Do not repeat the accepted scratch canary merely
to re-prove the route.

The action remains a bounded explicit-file binding, not a host-control escape hatch: callers provide
one exact bare Paper file ID, a fresh source snapshot, and a stable operation ID; URL/path/page
overrides, shell/process control, and unrestricted raw `open_file` are not exposed. Paper 0.5.12 can
address another file directly by `fileId`, including an already-open or background file, while another file remains user-active. Prepare therefore
performs no UI-focus/open effect; it validates the explicit target and returns that target snapshot
for the subsequent edit.

A newly staged bundle still begins as **STAGED_NOT_ENROLLED** infrastructure. That staging receipt is
not current service liveness, and `LOCAL_STDIO_PROVEN` still proves only initialization/tool
discovery. Current fleet truth is narrower: Ryan Business has the accepted live direct-app
prepare/edit journey; C1/C2/C3/C4/Chris Admin host tunnel services are live/ready but each still
requires its own attended ChatGPT app enrollment before that seat's direct app is accepted.

## Implementation

`integrations/paper_desktop/direct_service.py` owns deployment mechanics only:

- `stage`: new private bundle, byte-identical bridge copy, source hashes, exact Python/tunnel
  binary hashes, resolved SDK package versions, private operator worksheet and inert LaunchAgent.
- `verify`: reject symlinked/unsafe files, missing manifest entries, source or binary drift,
  altered launch configuration, and false production-acceptance claims.
- `probe`: actual MCP initialize/tools-list against the staged entrypoint, both accurate tool
  names and read/write/destructive/idempotent/open-world annotations; no application calls.
- `bind`: write one secret-free profile for the exact existing tunnel and Business workspace;
  refuse existing binding. A recorded workspace ID is configuration, NOT verified access.
- `doctor` / `run`: require verified binding, private runtime key, exact SDK versions and
  installed identities. Strip ambient credentials, tunnel IDs, MCP targets, proxies and Python
  injection variables before executing the official client.
- `serve`: expose the existing guarded stdio MCP server only. No workstation commands become tools.

The deployment supports `mcp==1.30.0` and the actual tested tunnel-client interface. Resolve
existing platform-managed executable symlinks once when staging; supply their real immutable
paths. Use a dedicated virtual environment created with `venv --copies`, so the chosen Python
path preserves the environment without relying on an executable symlink. The resolved package
versions are captured and compared before service start; do not silently upgrade the environment.
Version capture detects package-version drift; it is not an attestation of every dependency byte.

The transport singleton uses a private advisory lock under the existing user state root:
`~/.local/state/mastermind-paper/direct-business/tunnel.lock`. Its descriptor survives exec into
the official tunnel client. It prevents two adapter-launched clients for this logical service
across versioned bundles. It is not a Paper write lease, distributed lock or replay ledger.
Existing launchd remains the supervision owner; no new supervisor, background queue or scheduler
is added. Raw clients launched outside this adapter are still an operator collision to check.

## Multi-seat Business rollout

Multiple ChatGPT accounts/workspaces use **one Paper execution plane** through the same guarded bridge, not one Paper
gateway or editor identity per account. Each accepted ChatGPT seat gets one seat-aware v3 bundle
with a safe lowercase `seat_id`, one exact existing Secure MCP Tunnel, one transport lock, one
loopback health endpoint, one log pair, and one launchd label
`com.mastermind.paper-direct.business.<seat>`. The Paper Desktop process, bridge allowlists, schema
pin, effect semantics and per-OS-user `~/.local/state/mastermind-paper/desktop.lock` remain shared.
Consequently, two ChatGPT seats may keep their tunnel clients connected concurrently. Bridge calls
from the same OS user still serialize through `desktop.lock`, and a colliding local call may fail
closed as `DESKTOP_BUSY`; this is not a hidden queue, retry plane, or document lease. Multiple
admitted sessions/hosts may modify the same exact `fileId`, including the same page. Prefer disjoint
board/artboard/node targets; known same-board overlap is coordinated with disjoint node targets plus
fresh re-read/re-plan. The advertised contract is `MULTI_WRITER_PER_FILE_TARGET_SCOPED`.

A v3 seat binding records the exact tunnel ID and may record an exact backend workspace ID when it
is independently known. It must **not invent a workspace ID** merely to start the daemon: OpenAI's
existing tunnel/workspace association remains the platform-side owner, while local `doctor` proves
only that the runtime credential can use that tunnel. Legacy v2 bundles retain their historical
workspace-ID requirement and global transport singleton so already-running seats are not silently
reinterpreted.

One runtime key may be reused across seat bundles only when the exact key/tunnel matrix is proven by
`doctor`; otherwise isolate the affected seat behind its own runtime key. Credentials remain local
and are never copied into ChatGPT, Git, plist arguments or logs. A working seat does not need to be
restarted merely to add another seat.

## Secret-free preparation

Use a reviewed immutable source commit and a new bundle directory. Example operator commands:

```sh
"$SDK_PYTHON" -I integrations/paper_desktop/direct_service.py stage \
  --root "$BUNDLE" --python "$SDK_PYTHON" --tunnel-client "$TUNNEL_BINARY" \
  --source-revision "$EXACT_COMMIT" --allow-prepare --allow-write
"$SDK_PYTHON" -I "$BUNDLE/runtime/direct_service.py" verify --root "$BUNDLE"
"$SDK_PYTHON" -I "$BUNDLE/runtime/direct_service.py" probe --root "$BUNDLE"
```

Omit `--allow-write` to expose only the three read tools. Staging does not read a key, bind a
tunnel, create an account, launch Paper, install/load launchd, approve tools, or publish a plugin.
Existing destinations fail closed rather than overwrite. A partially written bundle must be
inspected as that exact failed staging effect; do not call it complete or silently replay it.

`app-definition.json` is an enrollment worksheet, **not a Plugin Creator manifest**. Current
Plugin Creator archive actions do not establish a portable tunnel-binding field. Use the
supported developer-mode Tunnel connection in the actual Business workspace at setup time.
Do not publish a skills-only placeholder and describe it as a working Paper connection.

## Final attended setup — intentionally last

1. Verify the Chairman-created tunnel ID, exact Platform organization and Business workspace
   association, and any existing app/client with the same purpose. Reuse that tunnel. Source
   code cannot prove the subscription or workspace association.
2. The daemon needs a **runtime key** with Tunnels Read + Use. An **admin key** is reserved for
   authorized tunnel metadata administration and is never used as the daemon credential.
   Enter the runtime credential through the approved local secret-entry mechanism into
   `$BUNDLE/secrets/runtime-key`, owner-only mode `0600`. Never put it in chat, Git, logs,
   a command argument, an environment dump, or a plugin archive. The launcher rejects an
   obvious admin-key prefix as an additional guard, not as proof of runtime permissions.
3. Bind only after the exact tunnel is known. For seat-aware v3 bundles, do not invent a backend
   workspace ID: bind the exact tunnel and include `--workspace-id` only when that ID is
   independently observed. Legacy v2 bundles retain their historical workspace-ID requirement.

   ```sh
   "$SDK_PYTHON" -I "$BUNDLE/runtime/direct_service.py" bind --root "$BUNDLE" \
     --tunnel-id "$EXISTING_TUNNEL_ID"
   "$SDK_PYTHON" -I "$BUNDLE/runtime/direct_service.py" doctor --root "$BUNDLE"
   ```

4. Through the existing host service owner, install the staged LaunchAgent exactly once with no
   overwrite of an incumbent service. Seat-aware v3 uses
   `service/com.mastermind.paper-direct.business.<seat>.plist`; legacy v2 retains the historical
   unsuffixed label. Do not also launch a manual client for the same seat. Health binds only to
   `127.0.0.1:0`; its assigned address is in `state/health.url`.
5. In the actual Business workspace, the authorized admin enables developer mode and creates
   private **Mastermind Paper**, choosing Connection **Tunnel** and the existing tunnel ID.
   A plugin name or successful registration is not proof of any Paper operation. When an accepted
   source/runtime revision changes tool descriptions or collaboration metadata, review and refresh
   the **same app's** approved action snapshot. If ChatGPT still shows older file-exclusive wording
   after the runtime is current, record `DIRECT_TOOL_PUBLICATION_DRIFT / EFFECT_NONE`; do not
   create a duplicate app/tunnel or treat stale transport metadata as a document lease.
6. Discover exactly the accepted tools in a fresh ChatGPT session. Use the assigned direct app
   for the approved scratch-file inspect/catalog/read -> one bounded edit -> post-read ->
   screenshot inspection -> JSX journey. Preserve file ID, snapshot and stable operation ID.
   Never replay after an uncertain result or switch to Studio/DC to obtain a denied effect.
7. Verify actual read/write confirmations, representative differences from Studio Direct,
   restart/reconnect without duplicate clients/writers, and loopback-only Paper/health listeners.
   A process lock test does not prove live tunnel delivery or exactly-once effects.
8. Record accepted cutover in the existing carrier and make the direct app the normal Paper
   route for this Business workspace. Retire the old Studio-primary requirement for this seat;
   preserve unrelated Studio tools and non-migrated seats.

Business account subscription and selected model reasoning mode are distinct. Switching model
mode is neither workspace enrollment nor permission recovery. No mode/account switch may bypass
a denial or clear an unresolved effect.

## Annotation ruling

Read tools remain read-only, non-destructive, idempotent and closed-domain. `paper_edit` remains
write-capable, potentially destructive and non-idempotent. It accepts HTML/style operations;
the adapter does not enforce a closed-world asset URL policy. Therefore retain `openWorldHint=true`
conservatively rather than asserting that localhost implies no external entities. Any later
narrower tool must reuse the bridge and have its own truthful semantics, not disguise a write.

## Proof and release

The proof stages remain distinct: source tests -> staged integrity -> local stdio -> real tunnel
doctor/health -> Business app discovery -> exact scratch read -> bounded write and same-carrier
reconciliation -> visual screenshot/JSX -> restart/reconnect -> cutover acceptance. Ryan Business
has completed that direct-app canary and a same-runtime host restart, with loopback-only listener
proof and a read-only representative Studio comparison recorded on #1011. C1/C2/C3/C4/Chris Admin
have live/ready host transports but still require per-account app enrollment and fresh read-only
discovery before their seat can claim direct-app acceptance.

Global repository CI, independent exact-head review and protected source convergence remain separate
from runtime acceptance. No source merge is implied by a live canary, and no newly staged seat is
accepted merely by running `stage`, `probe` or `doctor`.

## Official sources rechecked 2026-09-26

- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- Developer-mode plan/account gates: https://help.openai.com/en/articles/12584461
- Private developer-mode connection: https://developers.openai.com/plugins/deploy/connect-chatgpt
- Paper MCP: https://paper.design/docs/mcp
- MCP annotation semantics: https://ts.sdk.modelcontextprotocol.io/v2/api/index/@modelcontextprotocol/client/

The installed tunnel client's own help and built-in `sample_mcp_stdio_local` are the configuration
reference for the selected binary. Do not assume a future release retains identical flags; stage
and validate a new reviewed bundle instead of upgrading an active installation in place.
