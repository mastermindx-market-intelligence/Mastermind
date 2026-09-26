# Grok Secretary MCP / OpenClaw — Current-Source & Single-Path Gateway Amendment

**Date:** 2026-08-29  
**Parent operation:** `grok-secretary-mastermind-mcp-openclaw-f0-20260828-sol-001`  
**Authority:** narrow current-source amendment to the existing Grok Secretary design/program carrier. It wins for current protected-source state, H0 collision status, the installed `user-openclaw` owner/launch chain, and the one-path Gateway repair contract below.  
**Status:** records/source law only. This amendment does not modify the Grok host, Cursor backend config, OpenClaw package, Tailscale, Mac node, credentials, services, permissions, Gateway session, or MAS-198 Web-Sol canary.

## 1. Current protected source

Current protected Mastermind is:

```text
Mastermind@dfd69451dce5e186ce05f65446023fbe21f07a58
Skillpack mastermind.sol_skillpack.v1 1.0.1
bootstrap major 1
```

Protected movement after the final H0 source release is records-only watcher-resource design PR #205. Direct protected compare:

```text
229aebce5e8d0c1c7372f5fead9c24516b027cc1
  -> dfd69451dce5e186ce05f65446023fbe21f07a58
```

is exactly one commit and one changed path:

```text
docs/superpowers/specs/2026-08-28-watcher-resource-freshness-design.md
```

No authenticated H0 path and no Grok Secretary #188 record path moves in that protected delta. This #188 branch has been history-preservingly reconciled to protected `dfd69451...`; no reset, rebase, force push or replacement carrier is permitted.

Current watcher procedure also requires carrier-fresh reads and resource discipline. Reasoning-model watches default to 60 minutes; watcher silence never proves carrier freshness. This is procedure/attention law only, not a new lifecycle or scheduler.

## 2. Current dependency / capability state

### Worker Presence / Agent Dialogue

WP-1 remains merged and `BUILT_NOT_PROVEN / PRODUCTION_INERT`. Subsequent protected Agent Dialogue / continuity work does not turn Slack delivery into Executive execution, does not make the Secretary MCP runtime live, and does not grant OpenClaw lifecycle authority.

The existing no-duplicate boundaries remain:

- Executive OS owns Job/Attempt/Worker/Event lifecycle;
- Agent Dialogue / Agent Relay owns bounded communication semantics;
- Wake owns attention only;
- Grok Secretary is an Executive Operator reasoning surface;
- OpenClaw is optional subordinate hands;
- Slack is transport/hot-state only.

### CF2-H0

The old `ACTIVE_LOCAL_CARRIER_IDENTITY_UNKNOWN` / local H0 collision is superseded.

Mastermind PR #213 source-released the final authenticated H0 v3 transport as protected:

```text
229aebce5e8d0c1c7372f5fead9c24516b027cc1
```

That commit remains the immutable final-v3 H0 repair provenance. Native H0 is still `BUILT_NOT_PROVEN / PRODUCTION_INERT`: the final current-protected carrier build + bounded administrator ceremony + repeated verify-only receipts are still owed, and CF2-P0 / CF2-I remain held.

Protected master has since advanced to `dfd69451...` only through records-only #205. The H0 two-pin contract therefore now has a distinct current carrier axis and immutable repair axis; exact action-time re-pin / ancestry / five-path mode+blob equality remains required before any H0 native action.

**Important collision ruling:** the future Grok/VPS `user-openclaw` same-name catalog repair defined below is not an H0 host mutation. It touches the Grok/VPS host/backend MCP configuration and the OpenClaw child only, not the Mac H0 source/generation/root namespace. H0 no longer blocks that bounded VPS-side repair. This does not authorize Mac node actions, node-capability changes, exec-approval mutation, the Web-Sol canary, or any H0/P0 work.

## 3. Credential ownership remains owner-specific

The dedicated Linear Portfolio Projector credential boundary and existing Executive/Relay credentials do not become generic secret stores.

Secretary/OpenClaw work must not borrow or expose:

- Portfolio Projector credential files;
- Executive/Agent Relay credential coordinates;
- managed-browser/Keychain coordinates;
- provider credentials;
- human browser cookies/tokens/caches;
- raw OpenClaw Gateway token material.

The observed `user-openclaw` token remains in its existing host-owned connector-secret path. Future repair may preserve the existing token-file argument by opaque path/identity, but must never print, copy, transform or migrate the token value.

## 4. Installed `user-openclaw` owner and launch chain — GS-OP2 accepted

Read-only exact-session archaeology `grok-openclaw-catalog-single-path-gsop2-20260829-sol-001` returned `effect_state=NONE` and was Sol-accepted / terminally STOPPED.

The installed canonical server is **not** a marketplace plugin and is **not** owned by `mcpBoxServers`.

Sanitized installed identity:

```text
serverName: user-openclaw
account: default
transport: stdio
host: Grok Bot sand-host / host-main.cjs
host build: 05f7880
registrar: /exec-daemon/index.js LoadMcpServers
child: npm/npx openclaw@2026.5.7
mcpBoxServers: []
plugin id: none
```

Observed launch chain:

```text
sand-host definitionSource.getStdioServerConfigs()
  <- Cursor backend GetEffectiveMcpConfigForUser config_json
  -> host _ensureBoxServersPushed { mcpServers }
  -> boxLoadMcpServers
  -> exec-daemon ControlService.LoadMcpServers(remove_missing=true)
  -> loadSessionMcpServers / commandBasedMcpServer
  -> LazyMcpClient spawn
  -> openclaw stdio child
```

The existing token-file coordinate and remote endpoint/launch arguments are supplied by the host/backend catalog contract. `channels/openclaw/connection.json` is label-only. `mcpBoxServers` is a list of user-added names and is not the canonical `user-openclaw` definition owner.

Installed command-based stdio schema accepts:

```text
required: command
optional: type=stdio, args, env<string,string>, cwd
```

The installed host does not expose a local per-server env overlay for the built-in catalog entry. `AddMcpServer` can create/update account MCP configuration, but a new server name would create a second path and is rejected. The backend effective config / host push path is the owner that can preserve the same `serverName`.

Exec-daemon replaces the client when the same `serverName`'s serialized command/args/env changes. Therefore **same-name replacement is the canonical one-path mutation seam**. No second MCP identity is required or permitted.

## 5. Root cause: installed OpenClaw 2026.5.7 cannot inherit the proven Gateway proxy path

GS-OP1 established, without final repair effect, that this Grok/VPS runtime has existing userspace Tailscale proxy endpoints:

```text
SOCKS5: 127.0.0.1:1055
HTTP forward proxy: http://127.0.0.1:1056
```

The HTTP proxy reaches the private Gateway. The default VPS resolver does not resolve the private `ts.net` hostname. The built-in `user-openclaw` descriptor can appear ready/stdio/9-tools while live calls return `Not connected`.

The exact upstream `openclaw@2026.5.7` Git release source is inspected. For a remote Gateway URL it constructs:

```text
new WebSocket(url, wsOptions)
```

and only creates a direct agent for loopback. It does **not** activate inherited managed proxy routing before a remote Gateway connect. Generic `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` therefore cannot be treated as a proven fix for this installed version.

This supersedes the earlier process-proxy-env hypothesis as an implementation plan. GS-OP1 correctly stopped before effect when the host lacked a same-server env overlay; even if that overlay had existed, `2026.5.7` remote WebSocket routing was not proven to consume it.

## 6. Preferred repair target — OpenClaw 2026.6.34 extended-stable

The preferred future target is exact `openclaw@2026.6.34`, the current npm/container `extended-stable` channel release.

This target is preferred over current npm `latest` `2026.7.1-2` because it already contains the exact capability needed here while reducing the upgrade/change surface and avoiding the Git-tag/npm patch-label mismatch observed on the later candidate.

Primary-source checks on Git `v2026.6.34` show:

- `package.json.version = 2026.6.34`;
- bin `openclaw -> openclaw.mjs`;
- Gateway host deps inject:

```text
beforeConnect: ensureInheritedManagedProxyRoutingActive
```

- the managed proxy lifecycle recognizes inherited managed proxy routing when the child has:

```text
OPENCLAW_PROXY_ACTIVE=1
HTTP_PROXY=<http-or-https forward proxy URL>
```

and installs the Proxyline managed route before Gateway connect;
- exact release commit `5c38f996d4059ebd9080cf74dc611ec3a17f4d50` is Git-signature verified;
- the release includes proxy end-to-end fixture work, providing a materially stronger basis for this specific repair than the installed `2026.5.7`.

Published release verification for exact `2026.6.34` identifies:

```text
npm package: openclaw@2026.6.34
npm integrity: sha512-Rm4khBrWn9HYqE99NBryCFgjwlsIuwBqK5jIANn2773CGXJ1JIZkDn5twEHB+8SVFdh0FPNPHRVgZepzNJDfHg==
release commit: 5c38f996d4059ebd9080cf74dc611ec3a17f4d50
channel: extended-stable
```

and reports npm signatures/SLSA provenance plus successful release validation. These are review-time reference identities only. The future implementation must bind the **direct action-time npm registry metadata, signature/provenance and staged artifact bytes** before effect; it must not trust this document as a package registry.

For this estate the already-proven candidate forward proxy is:

```text
http://127.0.0.1:1056
```

No SOCKS-specific OpenClaw contract is required for the preferred repair because inherited managed-proxy activation is explicitly HTTP-forward-proxy based.

### Why `2026.7.1-2` is not the preferred target

Current npm `latest` `2026.7.1-2` also contains the managed-proxy behavior in corresponding stable source, but it widens the change surface without adding a capability required by this repair. Its checked Git source tag also reports `package.json.version=2026.7.1` while npm publishes `2026.7.1-2`, which would require an additional package-label/content reconciliation. It is therefore not the approved preferred candidate for this wave. A later separate source-law amendment may revisit it if `2026.6.34` proves incompatible or unsafe; the implementation worker may not auto-fallback to it.

**Still unproven:** that an exact attested `openclaw@2026.6.34` npm artifact plus inherited managed-proxy env completes the private Gateway WebSocket handshake in this exact Grok/VPS host. That must be proven by the implementation canary; source comparison and release verification are not production proof.

## 7. Frozen one-path repair contract

A future implementation child may modify exactly **one canonical MCP identity**: the existing `user-openclaw` entry.

Before any live write it must fresh-read and bind:

- exact current host build / exec-daemon identity;
- exact current effective `user-openclaw` config from the existing backend owner;
- exact current `serverName=user-openclaw` and absence of another OpenClaw MCP path;
- current `mcpBoxServers=[]` or otherwise prove it contains no second OpenClaw path;
- exact current child package/version and executable/package location;
- current remote endpoint / token-file launch arguments by sanitized structure only;
- current process identity and effect state;
- current local HTTP proxy reachability to the private Gateway.

### Stage 0 — package staging / integrity / rollback proof before the live entry moves

The approval-gated implementation operation must separate **package staging** from the later **live same-entry transition**. The live canonical `user-openclaw` config must remain byte/semantically unchanged throughout staging.

Before changing the live entry:

1. bind action-time npm registry metadata for exact candidate `openclaw@2026.6.34`, including immutable distribution integrity and published provenance/signature identity;
2. require the action-time registry identity to match the reviewed exact version/channel and expected reference integrity above, or STOP for Sol rather than silently adopting a republished/mismatched artifact;
3. acquire the candidate into an isolated operation-owned staging/cache boundary without overwriting or upgrading the live `2026.5.7` child/package in place;
4. independently digest the staged tarball/package tree and verify registry integrity/signature/provenance as available to the host;
5. verify the staged package's own `package.json` reports exactly `2026.6.34`;
6. inspect the **staged executable bytes** to prove the Gateway client calls inherited managed-proxy activation and the staged proxy lifecycle accepts the required `OPENCLAW_PROXY_ACTIVE=1` + HTTP(S) `HTTP_PROXY` contract;
7. bind the exact staged CLI entrypoint and prove it maps to the staged `openclaw.mjs` rather than an ambient/global executable;
8. preserve/stage an exact rollback-capable copy or otherwise network-independent executable closure of the currently running `openclaw@2026.5.7` package before live mutation, with its version and package/tree digest bound;
9. prove both candidate and rollback executables can be selected by the existing command/args schema **without any network fetch or package mutation after the live transition starts**.

Package staging is a known, separately receipted host filesystem effect inside the same approved operation (`PACKAGE_STAGE_APPLIED`), but it is not a Gateway/MCP identity change and must not restart or replace `user-openclaw`. If package staging, integrity, package-content proof, or rollback staging is ambiguous or fails, STOP before the live config transition. Do not compensate by letting `npx` fetch on demand during the live swap.

A future implementation may use the existing npm/npx machinery only if it proves an exact offline/network-independent invocation for both versions after staging. Otherwise it must use another already-supported command/args form that points at the attested staged CLI entrypoint. This source law does not invent a new package manager or runtime store.

### Stage 1 — one live same-name configuration transition

Preserve the same `serverName=user-openclaw`, same account, same endpoint semantics and same token-file coordinate. Change the same effective entry so the child executes the **attested staged** `openclaw@2026.6.34` artifact and receives only the process-local inherited managed-proxy environment required by the verified artifact contract:

```text
OPENCLAW_PROXY_ACTIVE=1
HTTP_PROXY=http://127.0.0.1:1056
HTTPS_PROXY=http://127.0.0.1:1056
```

`HTTPS_PROXY` is carried for ordinary child HTTP compatibility; the Gateway managed-proxy activation is grounded by `OPENCLAW_PROXY_ACTIVE=1` + `HTTP_PROXY`.

The exact existing remote Gateway URL / token-file args must be preserved if fresh preflight proves they are already the intended private Gateway coordinates. If they are absent, ambiguous, point elsewhere, or require secret exposure to interpret, STOP and return to Sol; do not invent or rewrite endpoint/auth coordinates inside the same operation.

The live write must use the existing backend/host same-name configuration owner (`SetMcpConfig` / equivalent exact owner seam) and then the existing `LoadMcpServers` same-name replacement behavior. **Do not call `AddMcpServer` with a new name and do not add `mcpBoxServers`.**

### Live-effect discipline

The live modifying effect is one logical same-entry configuration transition. Bind an exact pre-state digest/identity and candidate config digest before mutation. Package staging is already complete and network access for package resolution is forbidden once this transition begins.

After the live write:

1. reconcile the effective backend config and prove only `user-openclaw` changed;
2. prove exactly one `user-openclaw` logical server remains;
3. allow only the one same-name replacement/restart required by existing `LoadMcpServers` semantics;
4. prove the old child is gone before accepting the new child;
5. prove the new child executes the exact previously attested staged `2026.6.34` bytes/version;
6. run read-only Gateway acceptance probes.

If the config write/replacement outcome is ambiguous, mark `EFFECT_UNKNOWN`, inspect the same effective entry/process state and reconcile before any retry, rollback or alternate avenue. Never blind retry and never create another MCP path as fallback.

### Rollback

Rollback capability must be proven **before** the live transition. A definite canary failure with known applied config may restore the exact pre-state **same named entry** once, through the same owner, selecting only the already-attested, already-staged `2026.5.7` rollback executable. Rollback must require no package-network access and must prove the pre-state config digest plus old child version/package identity are restored. Rollback is not a new server, alternate transport or retry carrier.

If rollback outcome is ambiguous, preserve `EFFECT_UNKNOWN` and stop for same-carrier reconciliation. Do not fetch another package, switch versions again, or create a second MCP path after ambiguity.

## 8. Acceptance proof for the future implementation child

Success requires all of:

- action-time registry identity/integrity/provenance for exact `openclaw@2026.6.34` matches the reviewed release identity;
- independent staged-artifact digest/content proof;
- staged candidate itself contains the required managed-proxy hook/lifecycle;
- network-independent `2026.5.7` rollback was staged/attested before live mutation;
- no package fetch or package mutation occurred after the live transition began;
- `user-openclaw` remains the sole canonical OpenClaw MCP identity;
- no OpenClaw entry is added to `mcpBoxServers`;
- same serverName/account survives replacement;
- child package/tree is the exact approved and attested staged `2026.6.34` candidate;
- only approved process-local proxy env is added;
- existing remote endpoint/token-file coordinate is preserved by sanitized identity;
- live `conversations_list` succeeds from this exact Grok runtime;
- live `permissions_list_open` succeeds;
- exact intended Mac node is visible/approved through read-only Gateway state;
- current per-node exec-approval policy is readable;
- no Mac command, browser action, Ollama call, pairing, capability change or exec-approval mutation occurs;
- no token/auth/Tailscale/global proxy/`/etc/hosts` mutation occurs;
- no second MCP/Gateway path exists;
- no MAS-198 Web-Sol canary action occurs inside this repair.

The repair stops at `GROK_OPENCLAW_SINGLE_PATH_GATEWAY_PASS` (human-readable receipt; do not invent a typed runtime state if no canonical schema exists). Sol then independently adjudicates whether the already-existing MAS-198 canary may CONTINUE.

## 9. Failure states

Fail closed on:

- current host/backend owner or effective entry differs from GS-OP2 evidence;
- serverName collision or second OpenClaw MCP path;
- current endpoint/token-file structure cannot be proven without revealing secrets;
- action-time npm candidate metadata/tarball/integrity/provenance cannot be bound exactly;
- action-time registry identity differs from the reviewed exact `2026.6.34` release identity;
- staged package version/content does not match `2026.6.34` or does not prove the required managed-proxy hook;
- exact network-independent rollback executable/package closure for `2026.5.7` cannot be proven before live mutation;
- candidate package cannot be staged without changing unrelated host state;
- package integrity/version cannot be proven;
- live command would depend on post-transition network/package fetch;
- process-local proxy env is rejected or silently dropped;
- same-name replacement leaves two children or cannot prove old child reaped;
- live Gateway probes remain disconnected;
- any Mac/node/approval mutation appears;
- config/restart/rollback outcome becomes `EFFECT_UNKNOWN`;
- host update would require patching opaque minified `host-main.cjs` in place rather than the supported effective-config owner.

Do not weaken to current npm `latest`, another package version, a second MCP server, `mcpBoxServers`, global proxy, `/etc/hosts`, public ingress, Tailscale ACL/route/DNS/Serve/Funnel change, Mac re-pairing, or arbitrary `system.run` just to make the canary green. Any alternate package target requires fresh Sol source-law adjudication.

## 10. Current implementation/release boundary

This amendment is architecture/source law only. It does not authorize a worker merely because the design is written.

The intended next implementation is one fresh exact-session Grok Secretary child after this #188 carrier is exact-head validated, independently reviewed and protected/merged as source law. That child must receive a fresh operation key, exact current thread/carrier, current protected re-pin, exact pre-state/config digest, approved package-stage effect boundary, independently attested candidate + rollback packages, one logical same-entry live mutation, reciprocal watcher setup and the stop/rollback law above.

No implementation may start from the terminal GS-OP1 or GS-OP2 watcher/session authority.

## 11. All other Grok Secretary rulings remain unchanged

- one Mastermind MCP platform with separate bounded server identities;
- existing Executive MCP v1 remains unchanged;
- read-only Secretary MCP first;
- OCR-6 remains the canonical Executive Steward/Control Room owner; OpenClaw is optional subordinate hands only;
- provider-native session/Wake mechanics outrank GUI automation;
- no generic remote shell/computer-control surface;
- one logical operation / target / carrier until reconciliation;
- `EFFECT_UNKNOWN` blocks retry/failover;
- FULL FABRIC requires exact intended-seat and exact bound-conversation foreground proof;
- credential ownership remains owner-specific;
- this records carrier makes no implementation or production capability live.
