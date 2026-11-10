# LOCAL OPERATOR ACTIVATION — owner decision memo (READ_ONLY)

**Scope.** Read-only input to the Chairman's enable decision. No apply, no
restart, no service/daemon change, no Executive/Worker/config/hold-#1893/VPS/
`~/.hermes` effect was performed or is authorized by this file. Source pin:
checkout `568f9b02d` (branch `t3/mmos-v2-l4`); code-shaped citations are
**HEAD (`git show 568f9b02d:<path>`)** because `executive_mcp_entry.py`,
`integrations/executive_mcp/*.py` and tests are mid-edit by a sibling child.
Design inputs frozen: `integrations/mmos/LOCAL_OPERATOR_CONTRACT.md` (v +
2026-11-10 amendment) and `LANE_L4_INSTALLED_APP.md` § "Redirect".

Production facts used (principal-measured, not re-derived): gateway pid 46497,
user `_mastermind_executive_mcp`, release `dd45d111…`, entry
`ops/executive_os/executive_mcp_entry.py --config "/Library/Application
Support/MastermindExecutive/config/executive-mcp.json"`, TCP 127.0.0.1:8443.

---

## 1. Verdict — is the MCP server separately installable from the Control gate?

**YES for install/upgrade; PARTIAL for full activation at HEAD.**

**Yes — the mechanism.** The Executive MCP gateway is its own service, its own
identity and its own release selection, with an owned update path that never
enters `autonomy_control.py`:

* Separate launchd label `com.mastermind.executive.mcp`, config
  `/Library/Application Support/MastermindExecutive/config/executive-mcp.json`,
  releases root `/Library/Application Support/MastermindExecutive/releases`
  (`ops/executive_os/service-control.sh:11-15`). Its dedicated uid is enforced
  in config validation (`executive_mcp_entry.py:69-70`, `service_uid == 458` —
  matches the production `_mastermind_executive_mcp` account) and at process
  start (`executive_mcp_entry.py:888-889`).
* The `control_component_worker_live` refusal lives only in the
  **Control-component** update flow: refusal-code list
  `ops/executive_os/autonomy_control.py:8333`, raised in `_component_mode` at
  `autonomy_control.py:8865` (LIVE mode requires the Worker "already absent AND
  disabled"). That flow is reachable only through
  `plan/apply/reconcile/resume-control-component`
  (`service-control.sh:1077-1080` → `dispatch_control_component`
  `service-control.sh:861-875` → `autonomy_control.py`).
* The MCP gateway's owned updater is a different helper:
  `plan/apply/reconcile-mcp-component` (`service-control.sh:1052-1055` →
  `dispatch_mcp_component` `service-control.sh:662-677` →
  `ops/executive_os/mcp_component_update.py`). **`mcp_component_update.py`
  contains zero references to the Worker or the Control component**
  (`grep -c worker` = 0 at HEAD). It "changes exactly two installed files"
  (docstring, `mcp_component_update.py:5-11`): the gateway config's
  `release_sha` and the gateway plist's release pointer. Its stop/start act
  only on the gateway label (`LABEL = installed._LAUNCHD_ROLES["gateway"].label`,
  `mcp_component_update.py:127`). `service-control.sh start/stop/restart`
  (`:1081-1102`) touch only Control+Worker and never the gateway label; the
  two lifecycles are disjoint in both directions.
* Staging a new release without any service/config effect:
  `install.sh --stage-release-only` prints
  `{"staged_unselected":true,…,"services_changed":false,"configs_changed":false}`
  and exits before the mutation boundary (`install.sh:1675-1682`; sealing in
  `stage_sealed_release`, `install.sh:1433-1548`). The network runtime need not
  be re-provisioned: its closure is pinned to a fixed digest, not to a release
  (`control_plane/executive_installed_peer.py:2586-2604`), and the update only
  rewrites plist `argv[3]` + `WorkingDirectory` (`_proposed_plist`,
  `mcp_component_update.py:240-277`).

So an owner can install/upgrade an MCP-only release and select it for the
gateway **without touching the Control component, its worker-live gate, the
Worker, or any other service**.

**Partial — the two caveats.**

1. **The gateway process itself must restart.** Config and code are read once
   at startup (`executive_mcp_entry.py:883-889`) and there is no reload path;
   the owned apply is explicitly stop → replace → start (WARNING
   `mcp_component_update.py:173`: "the gateway is stopped and restarted: the
   endpoint is briefly unavailable"). Everything *else* stays running; TCP 8443
   has a brief unavailability window (which the public tunnel surfaces).
   "Without restarting anything else" holds exactly; "no restart at all" does
   not exist for any release or config change.
2. **At HEAD no owned tool can write the `local_operator` block.**
   `validate_document` has a closed key set that does not include it
   (`executive_mcp_entry.py:22-27,45-47` → "installed MCP configuration fields
   differ"), the component updater's allowed config-change set is
   `{"release_sha","public_mcp_resource","selected_child_target","coo"}`
   (`mcp_component_update.py:587`), and `git grep local_operator HEAD` finds it
   in no production code today (only these lane docs). The lane child now in
   flight must land a release that BOTH admits the key in the validator AND
   provides an owned write route (§3). Enabling before such a release exists is
   possible only by a direct root edit of the sealed config (§3b) — outside the
   receipt-covered transaction path.

---

## 2. Owner commands — install an MCP-only release

Preconditions grounded in source: a reviewed source checkout (worktree) at
`<NEW_SHA>` containing the landed local-operator module; the OS web-asset
bundle (stage-only *requires* it: `install.sh:421-431` — "stage-only requires
complete OS assets and excludes frozen source, arming and config
replacement"; the apply re-checks `asset-manifest.json` inside the target
release when `os_executive_transport` is true, `mcp_component_update.py:1008-1023`).
Placeholders: `<NEW_SHA>` = 40-hex of the new release; `<ASSET_BUNDLE>` = the
sealed OS web-asset bundle path; `<REPO>` = the source worktree checked out at
`<NEW_SHA>`.

**(a) Stage the release — zero service/config effect:**

```sh
sudo "<REPO>/ops/executive_os/install.sh" \
  --source-repo "<REPO>" \
  --expected-sha "<NEW_SHA>" \
  --operator-user "chriswong" \
  --stage-release-only \
  --os-web-assets "<ASSET_BUNDLE>"
```

Grounding: usage `install.sh:389`; `--stage-release-only` `install.sh:399`;
option guard `install.sh:421-431`; stage-only dispatch + no-service/no-config
receipt `install.sh:1675-1682`. Expected stdout ends
`"staged_unselected":true … "services_changed":false,"configs_changed":false`.
An interrupted earlier stage refuses until resolved (`.stage.<sha>` marker,
`install.sh:1436`).

**(b) Select it for the gateway (owned, transactional, gateway-only restart):**

```sh
# Read-only plan; prints {"ok":true,"outcome":"PLANNED","plan":…,"plan_sha256":…,"warnings":[…]}
sudo "/Library/Application Support/MastermindExecutive/releases/<NEW_SHA>/ops/executive_os/service-control.sh" \
  plan-mcp-component --expected-sha "<NEW_SHA>"

# Execute exactly that plan (digest-bound; refuses on drift)
sudo "/Library/Application Support/MastermindExecutive/releases/<NEW_SHA>/ops/executive_os/service-control.sh" \
  apply-mcp-component --expected-sha "<NEW_SHA>" --plan-sha256 "<PLAN_SHA256>"
```

Grounding: verbs must be dispatched by the **target** release's own
controller (`dispatch_mcp_component` owner-binding,
`service-control.sh:669-676`); plan/apply contract
(`mcp_component_update.py:1830-1855`, digest check `:1855`; exit codes
docstring `:77`). Apply preconditions: gateway REGISTERED, enabled, and
passing a loopback probe (`SERVICE_NOT_REGISTERED` / `GATEWAY_DISABLED` /
`PRIOR_UNHEALTHY`, `mcp_component_update.py:1861-1868`) — the running
production gateway satisfies these. No `--set-public-mcp-resource` is used:
the public-audience config stays byte-identical.

Effect of (a)+(b): new code under `releases/<NEW_SHA>`, config `release_sha`
and plist argv[3]/WorkingDirectory repointed
(`_proposed_plist` changes nothing else, `mcp_component_update.py:240-285`),
gateway stopped and started once. Same interpreter/network runtime is
retained (only argv[3] + WorkingDirectory change), so no runtime provisioning.

---

## 3. Owner commands — enable the config block

Per `LOCAL_OPERATOR_CONTRACT.md` §1/§2 (block off unless present):

```json
"local_operator": {
  "socket_path": "/Library/Application Support/MastermindExecutive/run/local-operator.sock",
  "allowed_uids": [501],
  "operator_subject": "<config string, e.g. m2-local-operator — never a real principal name>"
}
```

`allowed_uids`: the Chairman's login uid — verify with `id -u`; the lane
measured `peer uid=501 == my uid` on M2 (`LANE_L4_INSTALLED_APP.md:174`).
`operator_subject` is a config string; this memo deliberately uses a
placeholder, never a principal value.

**(a) Proper path — via the landed release's owned updater.** If the lane
extends `mcp_component_update.py` to carry the block (the natural route: it is
THE owned writer of exactly these two files), enabling is a single
`plan`/`apply` pair as in §2b, with the block in the plan's after-image — the
plan/apply code imported from the NEW release tree uses the NEW validators
(`mcp_component_update.py` inserts its own release root on `sys.path`,
`:102-105`). **UNKNOWN at HEAD whether/how the lane wires this** — the sibling
child is mid-edit; confirm from the landed diff. Do not assume a verb that is
not in the landed code.

**(b) Mechanical floor that exists regardless — direct root edit + gateway
restart.** Precedent: the updater's own docstring defines hand-restoring these
exact files by root as the human-approved path
(`mcp_component_update.py:50-58`; `docs/EXECUTIVE_MCP.md:475+` describes the
same for restore). This bypasses plan receipts/probes, so treat it as the
fallback:

```sh
CFG="/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
sudo cp -p "$CFG" "/Library/Application Support/MastermindExecutive/installation-receipts/executive-mcp.pre-local-operator.json"

sudo /usr/bin/python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")
raw = json.loads(p.read_text())
raw["local_operator"] = {
    "socket_path": "/Library/Application Support/MastermindExecutive/run/local-operator.sock",
    "allowed_uids": [501],                      # Chairman's user: `id -u`
    "operator_subject": "<config string>",      # never a real principal name
}
p.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
EOF

# Reload: qualify (config+plist join) → stop → start → re-qualify
sudo "/Library/Application Support/MastermindExecutive/releases/<NEW_SHA>/ops/executive_os/service-control.sh" \
  restart-gateway --expected-sha "<NEW_SHA>"
```

Grounding: restart-gateway qualification chain
(`service-control.sh:1103-1139`; `qualify_gateway_release:418-455` binds
config `release_sha` == expected sha and plist argv to the release;
`qualify_gateway_refresh_preflight:457-473` runs the deep validator, which
calls `validate_document` — `gateway_refresh_preflight.py:25,36-55`). The JSON
encoding matches the canonical form the tooling round-trips
(`mcp_component_update.py:206`). Config custody rules the launcher enforces at
startup: root-owned, no symlink, no group/other write, single link
(`require_sealed_path`, `executive_mcp_entry.py:88-107`, applied to the config
at `:885`).

**Ordering is forced:** the release upgrade (§2) MUST come first — the
currently running `dd45d111…` code refuses any config carrying the block
(closed key set, `executive_mcp_entry.py:45-47`), and a refused config makes
the launcher exit 2 before binding ("installed configuration refused",
`executive_mcp_entry.py:1025-1030`) — fail-closed, not a silent weaken.
Likewise, after the block exists, `restart-gateway`/preflight must be invoked
from the NEW release's controller (an old release's validator would refuse
the same config).

**Open design-landing item (flag for the lane, found during this read):**
contract §2 fixes the socket at mode `0600` and §5 admits by kernel peer uid.
A `0600` socket created by the gateway (uid 458) is connectable **only by
uid 458** — file permission gates connect before `getpeereid` is consulted.
For the Chairman's user (501) to connect, the landed module must define the
ownership/mode interplay (e.g. socket `chown`ed to the operator uid keeping
`0600`, or a shared group with `0660`). Also unstated: who creates the `run/`
parent (contract requires `0700`; nothing at HEAD references that path).
UNKNOWN until the lane lands; both belong in its negative tests.

**(c) Verify it is serving:**

```sh
# 1. Service running under launchd (observation pattern of status.sh:24-35 / require_running:123-139)
sudo /bin/launchctl print system/com.mastermind.executive.mcp | /usr/bin/awk '/state =|pid =|program =/'

# 2. TCP listener unchanged and present (lsof pattern from status.sh:52)
sudo /usr/sbin/lsof -nP -a -u _mastermind_executive_mcp -iTCP -sTCP:LISTEN

# 3. Socket exists with contract perms (§2: parent 0700, socket 0600)
sudo /usr/bin/stat -f '%Sp %Su %Sg %N' \
  "/Library/Application Support/MastermindExecutive/run" \
  "/Library/Application Support/MastermindExecutive/run/local-operator.sock"

# 4. Loopback challenge boundary still answers exactly as before
#    (the probe pair the apply itself runs; build_probes, mcp_component_update.py:345-365)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8443/.well-known/oauth-protected-resource/mcp   # expect 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8443/mcp \
  -H 'accept: application/json, text/event-stream' -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"owner-check","version":"1"}}}'   # expect 401

# 5. Consumer proof: one Projects-style read over the socket with NO token,
#    using the lane's Python client example (owed by L4 per LANE_L4_INSTALLED_APP.md
#    "Proof owed": Projects read 200 over the socket + the four negative tests).
#    A stat/launchctl check is not consumer proof.
```

Note: `service-control.sh status` (→ `status.sh:92-93`) observes only
Control+Worker — it does not cover the gateway label; use the checks above.

---

## 4. Rollback — return to today's state

Today's state = release `dd45d111…` selected, no `local_operator` key, no
`run/` socket.

**Disable the block only (keep the new release):** remove the
`local_operator` key by the same route that added it (§3a verb if the lane
ships one — UNKNOWN until landed; otherwise the §3b root edit), then
`restart-gateway --expected-sha "<NEW_SHA>"`. The socket is removed on stop
per contract §2; if a stale socket file remains after an unclean stop, its
cleanup semantics are UNKNOWN at HEAD (landed module owns that behavior) — do
not `rm` blindly before checking the landed spec.

**Full return to `dd45d111…` (after a §2b apply):** the updater has **no
rollback verb and no automatic rollback** (`mcp_component_update.py:50-58`).
The documented human restore is:

```sh
R="/Library/Application Support/MastermindExecutive/installation-receipts"
sudo cp -p "$R/mcp-update-<PLAN12>.config.before" \
  "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
sudo cp -p "$R/mcp-update-<PLAN12>.plist.before" \
  "/Library/LaunchDaemons/com.mastermind.executive.mcp.plist"
sudo /bin/launchctl enable system/com.mastermind.executive.mcp
sudo /bin/launchctl bootstrap system /Library/LaunchDaemons/com.mastermind.executive.mcp.plist
# then observe-only recovery of the transaction record:
sudo "/Library/Application Support/MastermindExecutive/releases/<NEW_SHA>/ops/executive_os/service-control.sh" \
  reconcile-mcp-component --expected-sha "<NEW_SHA>"
```

Grounding: preserved before-image names `mcp-update-<plan12>.config.before`
/ `.plist.before` in `installation-receipts/`
(`mcp_component_update.py:798`, `RECEIPTS_DIR :124`); restore + enable +
bootstrap procedure verbatim from the docstring `:50-58` and
`docs/EXECUTIVE_MCP.md:475+`; `reconcile` is observe-only. `bootstrap` applies
when the label is absent (`launchctl print` exit 113 — the pattern
`start_one` uses, `service-control.sh:60-83`); if still registered, use
`launchctl kickstart system/com.mastermind.executive.mcp` instead. The staged
`releases/<NEW_SHA>` tree may remain (unselected, sealed, harmless); no owned
removal verb exists for it (UNKNOWN — the DR prune tool is draft-DR-lane only,
`DR_RUNBOOK.md` §3a). If the gateway refuses to start after a bad edit, it
exits 2 *before* binding (`executive_mcp_entry.py:1025-1030`): restore the §3b
config backup and repeat `restart-gateway`.

---

## 5. Untouched list (named)

| Surface | Why untouched |
|---|---|
| **Production TCP listener behavior** | Contract §5: "the TCP listener stays byte-for-byte unchanged" (`LOCAL_OPERATOR_CONTRACT.md:19-22`); the listener is `uvicorn.run(app, host='127.0.0.1', port=raw['port'], …)` (`executive_mcp_entry.py:1018-1019`); the design's negative-test gate requires forged headers on TCP to draw exactly today's refusal (`LANE_L4_INSTALLED_APP.md:133-136`). No `--set-public-mcp-resource` is used, so audience config is also byte-identical. (The gateway *process* is restarted by the owned update — §1 caveat 1.) |
| **Worker** (`com.mastermind.executive.worker.codex`) | `mcp_component_update.py` references the Worker zero times (HEAD grep); its effects target only the gateway label (`:127`). The Control-component verbs that carry the worker-live gate are never invoked. |
| **Control component** (`com.mastermind.executive.control`) / its worker-live gate | Only reachable via `plan/apply/reconcile/resume-control-component` (`service-control.sh:1077-1080`), absent from every command above. The gateway's existing `ceo-ingress` dependency (`/var/run/mastermind-executive/ceo-ingress.sock`, required at `executive_mcp_entry.py:73-74`) keeps its current provider; nothing reconfigures it. |
| **Hold #1893** (09b/call5913 protected-result disposition) | A release-disposition hold (`integrations/mmos/EXECUTIVE_READER_DIAGNOSIS.md:104`; `LANE_EXECUTIVE_DIRECTOR_C.md:140` — "Do not disarm"). Nothing in §2–§4 reads, consumes, retries or disarms any protected result; the updater touches only release pointers in two files. |
| **Caddy edge** | The edge's route table is owned by the separate `os_public_edge_publication` verbs (stage-host/prepare/verify-cutover/finalize; `docs/OS_PUBLIC_EDGE_TRANSITION.md` — "There is no same-source route-only publication command"), none of which appear above; an MCP component update changes no Caddyfile and no edge route. |
| **Public tunnel (EdgeOne→Caddy→chisel)** | Reaches only TCP 127.0.0.1:8443 with spoofable `X-Forwarded-For`; contract §5 requires the tunnel to be unable to reach the socket or its privileges (`LOCAL_OPERATOR_CONTRACT.md:21-22`); trust-a-header rules were rejected in advance (`LANE_L4_INSTALLED_APP.md:129-132`). Tunnel infrastructure is not touched by any command here. |
| Also untouched | VPS and `~/.hermes` (program boundaries, `OPERATING_METHOD_V3.md:59`); the Chairman's installed app bundle + Keychain (contract §4: `com.mastermind.os` untouched; the socket consumer is a Paperclip module worker); backup/relay/agent-relay labels; the frozen OAuth code path (stays in tree, unused in local mode). |

---

## 6. Riskiest step + UNKNOWNs

**Riskiest step: the `apply` stop→replace→start window (§2b), compounded by
the enable edit (§3b).** After file replacement there is no automatic
rollback; a failed start is `EFFECT_UNKNOWN` (`START_NOT_PROVEN` /
`PROCESS_IDENTITY_NOT_PROVEN`) and must be closed by `reconcile` + the §4
human restore, never by re-running apply (`mcp_component_update.py:50-58`).
During the window TCP 8443 is briefly down (public-tunnel-visible). The §3b
hand-edit adds risk because it is outside plan receipts and loopback probes —
mitigated fail-closed by the startup validator (exit 2 before binding), but a
bad edit still costs an outage interval until the backup restore. Prefer §3a
once the lane lands. Residual (documented) blind spot of the tool's own
proof: the listener pid is not tied to the port, and failures later than the
hold window are not covered (`docs/EXECUTIVE_MCP.md:475+`).

**UNKNOWN (with what would be needed):**

1. **Enable mechanism in the landed release** — whether the updater's
   allowed set/verbs are extended to carry `local_operator`. Need: the
   sibling child's landed diff (files mid-edit; HEAD has zero occurrences).
2. **Socket ownership/mode interplay and `run/` parent creation** — contract
   fixes `0600`/`0700` but not owners; as written a gateway-owned `0600`
   socket is unconnectable by uid 501. Need: the landed module's
   spec + negative tests (§3 open item).
3. **OS web-asset bundle build command** for `<ASSET_BUNDLE>` — owned by the
   OS web-assets flow (`ops/executive_os/OS_WEB_ASSETS.md`; bundle digest
   verified at `install.sh:1284-1285`); not re-derived here. Need: that
   owner's build step at the new SHA.
4. **Stale-socket cleanup semantics** after an unclean stop — contract says
   "removed on stop" only. Need: landed module behavior.
5. **Whether the production config carries `os_executive_transport: true`**
   (affects nothing in the commands — stage-only requires assets regardless —
   but it decides whether the apply's `asset-manifest.json` check binds).
   Need: a root read of the installed config at execution time.
6. **`dd45d111…` full 40-hex** for the rollback §4 reconcile invocation.
   Need: read from the installed config (`release_sha` field).

*This memo is evidence for the Chairman's decision, not an executed change.
No command above was run against production by its author.*
