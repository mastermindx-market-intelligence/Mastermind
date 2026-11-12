# GBL bridge — install list (staged, rehearsed, principal-only)

Lane: GBL install (ruling 16 rehearsal). Date: 2026-11-12. Author: GBL lane lead (sub-agent).
Code to install: trunk `feat/mmos-v1-integration-t3` at **merged head 26c754bfd** — item5
(8dad45083) is merged (principal's update 13:27Z); its `integrations/gbl` files are byte-equal to
8dad45083, verified by digest. The digests below were re-taken at **26c754bfd** and every one
equals the value taken at 8dad45083, so the rehearsal copy (`git archive 8dad45083`) exercises
byte-identical bridge code.

**Rehearsal statement (ruling 16):** every step in this list was run end to end against a COPY
(`git archive 8dad45083` under `~/.mastermind/mmos_dev/gbl/install-rehearsal/repo/`): the bridge
was started by hand (never launchd), against the test fake-board fixture on an ephemeral port
(never 127.0.0.1:3100), the tunnel config was validated without running a tunnel and without
touching `~/.cloudflared`, and each rollback below was run exactly once (R1–R6). Final run:
**25/25 rehearsal steps passed** and the **7 GBL test suites (361 tests) pass at the merged head**
(all rc=0). Results and logs: `REHEARSAL.md` (same folder). Nothing in this list was installed
for real by the lane. The rehearsal found and fixed two real defects, which is exactly what
ruling 16 is for: (1) a runner edge-build failure left a stale door socket behind (fixed: the
runner now closes the door before dying typed `EDGE_START_FAILED`); (2) `load_resource_policy`
REFUSES an empty `allowed_subject_digests` list, so the edge policy cannot ship with `[]` — it
ships with ONE non-admitting placeholder digest until the sitting (see "The real spec" below).
Three further usage findings are folded into the steps below: the cloudflared `--config` flag
position (step 8), the exact HMAC-key mint moment (spec section + step 6/7), and the
`status=`-line consumer contract for `fetch` (ruling-19b section).

**Effect on running sessions (ruling 16):** NONE of the steps restarts, reconfigures or interrupts
any teammate session, the Chairman's app, the team server, or any running conversation. The
install only ADDS: new files under `~/.mastermind/gbl/`, one new launchd user agent (new process),
one new AF_UNIX socket, one new loopback port (3193), one new named tunnel. The bridge's launchd
PATH includes `~/.t3/bin` for the stock `t3` binary used by team.message — it runs `t3` only for
allowlisted sends, and the allowlist ships EMPTY, so no thread is ever touched before the
principal switches a row on. Until admission rows exist, every door op and every MCP tool call is
refused typed; the connector cannot cause an ask.

---

## Phase 0 — prerequisites and BLOCKERS (principal, before anything is placed)

### P0-1 item5 merged — **DONE 2026-11-12** (principal: trunk is now 26c754bfd)
`git merge-base --is-ancestor 8dad45083 26c754bfd` exits 0 (verified by the lane); all 17
digests below re-taken at 26c754bfd equal the 8dad45083 values (verified by the lane).

### P0-2 BLOCKER — the real board port is refused by the shipped code
`integrations/gbl/paperclip_client.py` line ~98: `RESERVED_PORTS = frozenset({3100, 3179})`;
`validate_paperclip_base_url` refuses them. The assignment names the real board as
`http://127.0.0.1:3100`. At both trunk head and 8dad45083 a spec naming 3100 makes the runner exit
typed (`BASE_URL_NOT_ALLOWED`) **before binding anything** — the rehearsal proved this refusal path
via the runner's `from_spec` call. Two ways forward, principal's choice:
- **(a) reviewed change to RESERVED_PORTS** (e.g. remove 3100, or add an explicit
  `allow_reserved_port: true` spec field gated behind the same review). This edits
  `integrations/gbl/paperclip_client.py` — a critical surface (base-URL law, ruling 3/17): needs
  its own review and tests; the lane was forbidden to edit `integrations/gbl/*.py`.
- **(b) dedicated board instance for the bridge on a non-reserved port**, leaving the law untouched
  (ruling 14 launcher law applies to any dev board; a *production* second instance is the
  principal's call and needs its own data-ownership statement).
- **Check:** `python3.12 - <<'EOF'` … `PaperclipAskClient.from_spec(spec_path)` constructs without a
  typed refusal, against the chosen base_url.
- **Rollback:** revert the reviewed change / stop the dedicated instance; nothing else depends on
  the choice until step 5.

### P0-3 checkout + digest verification at the merged head
- **Check:** in the checkout the spec's `repo` will name (at 26c754bfd or a descendant),
  `shasum -a 256` every file in the table below; all 17 must match.
- **Rollback:** a mismatch stops the install; re-fetch the exact head.

### Digest table (at merged head 26c754bfd — byte-equal to 8dad45083, verified)

| sha256 | path |
|---|---|
| 9ca56fb5a74603c25d2270b5054ce95bb4c7f4d34ad62582ef9f73af461e57fc | integrations/gbl/__init__.py |
| 7a27d6f21ccf1739229185272b2b81d054ee38f9a259c114f90f3850d4f74e52 | integrations/gbl/admission.py |
| e006e38affccd5bdc2fbc69ea45ff6c652b2c486b5dbd3e7b82620c47b7c19fe | integrations/gbl/bridge_service.py |
| adc1486af987014ebf4e1c25e24c54c84ab70b2de4356d7874d75ddddfb548c1 | integrations/gbl/mcp_server.py |
| c3140af9ce9e4b691cc9f1e3b0e5f62b19e81de729fb1c2e7893249fd96b7548 | integrations/gbl/message_send.py |
| ba5096b1cb7fbf2a3daf95e72bdf1078d506093c68b025a04446b710f4b9fe56 | integrations/gbl/nudge.py |
| d4ba0f61b7b641fb3bbe9be23d6b5b61f44791e1e4cf48cd26292e177dc608ec | integrations/gbl/paperclip_client.py *(still carries RESERVED_PORTS — P0-2 open)* |
| 91a5d32c0ab4da1cb0e51d1b4fd9cd59ffc527400000bd808f0cc75fc5e5bd3d | common/gbl_contract.py |
| 2bba37cb178b53dc4a9cccee7eeb40a1493dfe168a7fbb70f978cf6da6078738 | tools/gbl/gbl_ask.py |
| abcc8c4fccf8c2da8eadafd508f328515087346f0636d7cefdcd43a29b170d8a | tools/gbl/specs/grok_bridge_dev.json |
| b096f26ecc29f574ba6d5a0fe9f227637e2cee9ecb9cb06adb1be0c2da49425a | integrations/business_mcp_auth/contracts.py |
| 4ea589039579c4baa3d2cc99119f92345ba9723e8f3e4a0d19729364c503a0af | integrations/business_mcp_auth/jwt_verifier.py |
| 7aea430a49888397cde56c73dbebfb0ec61d33326a6f4dea50475ba71feef561 | integrations/business_mcp_auth/jwks.py |
| d5d8abe98f09ecfda0e183e50a8c402177ff6da3348caa30c0b1f6787e86c460 | integrations/business_mcp_auth/metadata.py |
| 6cf7d2ef654931a6b2ebe6d3da9f24cba6ee02bd1e697721660db50ea2b09040 | integrations/business_mcp_auth/audit.py |
| 2cd9c64e85d848975c99793875d87d896ccbd3d41ef8e53f65cae111ef9d66e5 | integrations/executive_wake/grok_bot_http.py |
| db7dc37c1bfc67a6be15c70e52a6b29327cf3d938cee1aa08ccf0a80897d27b6 | integrations/executive_wake/grok_bot_routine.py |

These files are NOT copied anywhere — the runner imports them from the checkout named by
`spec.repo`. What gets placed on disk is the five staged artifacts in
`~/.mastermind/mmos_evidence/gbl-20261111/install/staged/` (copies of this folder are also in the
repo at `integrations/mmos/gbl/INSTALL.md` — this document — while the artifacts themselves stay in
evidence until the principal places them):

| staged artifact | placed at | mode |
|---|---|---|
| gbl_bridge_runner.py | ~/.mastermind/gbl/gbl_bridge_runner.py | 755 |
| spec.production.template.json | ~/.mastermind/gbl/spec.json (after filling) | 600 |
| com.mastermind.gbl.bridge.plist | ~/Library/LaunchAgents/ | 644 |
| com.mastermind.gbl.tunnel.plist | ~/Library/LaunchAgents/ | 644 |
| config.yml | ~/.mastermind/gbl/tunnel/config.yml | 600 |

## The real spec (what the staged template fixes and what the principal fills)

- **Socket path:** `~/.mastermind/gbl/run/bridge.sock` (AF_UNIX; admission = kernel peer uid only;
  a live or stale socket path at start = typed `SOCKET_IN_USE`, never adopted).
- **HMAC key path:** `~/.mastermind/gbl/run/hmac_v1.key`. **The bridge creates the key on first
  use** (32 random bytes, 0600, O_NOFOLLOW, symlink refused, parent dir must not be
  group/other-writable). Rehearsal precision: "first use" means the first **TAGGED** event — the
  answer/state append (`_hmac_key()` is lazy) — NOT the first plain ask; after a READY with no
  answer activity the key legitimately does not exist yet (S05/S08). **No step ever reads an
  existing key**; no pre-create is needed (the GBL4_NOTES `umask 077 && head -c 32 /dev/urandom`
  pre-create option remains available but the rehearsal proved lazy creation works). The key
  never crosses the wire, a log, or argv.
- **Real board address:** `http://127.0.0.1:3100` — **see the P0-2 BLOCKER**: the shipped
  base-URL law refuses 3100 until the principal resolves it.
- **Grok Bridge agent fields:** `<PRINCIPAL FILLS>` — company_id, agent_id (agent created in step
  4; role must be `general`, the board rejects `service` with HTTP 400; adapter `process`; no
  heartbeat).
- **Edge:** loopback `127.0.0.1:3193` (verified free 2026-11-12; no lane port collides —
  3773/3774/3780/3190/3796/3800 untouched), `allowed_hosts` carrying both `127.0.0.1:3193` and
  `mmos-link.mastermindx.ai` so the DNS-rebinding check passes with or without the tunnel's
  `httpHostHeader` rewrite; OAuth policy fields `<PRINCIPAL FILLS>` (issuer/jwks_uri/policy_id from
  the sitting's OAuth client).
- **Admission:** BOTH tables ship **EMPTY** (`bridge admission: []`, `edge.admission: []`), and
  `team.message` ships with an EMPTY allowlist and EMPTY environments — `ALLOWLIST_EMPTY` refusal
  for every (environment, thread). Enrollment is principal-only (step 10/11).
- **Subject-digest placeholder (rehearsal finding):** `load_resource_policy` REFUSES an empty
  `allowed_subject_digests` list (contracts.py `_sorted_unique_strings`: ≥1 item, sorted, unique),
  so the edge policy cannot ship with `[]`. It ships with ONE non-admitting placeholder:
  `subject_digest(issuer="<issuer>", subject="gbl-enrollment-pending")` — deterministic, matches
  no real token (no connector authenticates before enrollment anyway; the empty `edge.admission`
  table independently refuses every tool call). The principal REPLACES it with the real digest(s)
  in the same edit that enrolls rows (step 10). Alternatively the whole `edge` block may be
  omitted at step 5 and added at step 10 — the runner supports the door-only shape (rehearsal
  S04a: READY with `edge=disabled`).
- **Nudge:** no `routine` block ships; the runner logs `nudge=NOT_CONFIGURED` and no nudge can
  fire. The principal adds the block after the sitting creates the webhook routine (step 9), and
  even then the production CALLER of the nudge intake lands with GBL-5 (open dependency below).

## Tunnel config.yml (staged text; principal places and runs it)

Tunnel `mmos-link`, id `39ab99e9-d2f4-4f39-bcd0-0262d031c666`, hostname
`mmos-link.mastermindx.ai`. **Only ingress = the bridge's own HTTP listener on loopback**
(`http://127.0.0.1:3193` with `originRequest.httpHostHeader: 127.0.0.1:3193`), **then catch-all
`http_status:404`** — exactly two rules; any other hostname on this tunnel serves nothing.
The `credentials-file:` line names the standard Cloudflare-managed path
`/Users/chriswong/.cloudflared/39ab99e9-….json` as a **placeholder the lane never opened**: no lane
step read, printed, copied or hashed anything under `~/.cloudflared`; only cloudflared itself reads
it at run time.

---

## Phase 1 — placement steps (principal-only; each with its own check and rollback)

### 1. Create the state root
`mkdir -p ~/.mastermind/gbl/run ~/.mastermind/gbl/tunnel && chmod 750 ~/.mastermind/gbl ~/.mastermind/gbl/run ~/.mastermind/gbl/tunnel`
(The client refuses a missing dir `HMAC_KEY_DIR_MISSING` and never mints directories; the dir must
not be group/other-writable or the key is refused.)
- **Check:** `stat -f '%Lp %N' ~/.mastermind/gbl ~/.mastermind/gbl/run` → `750` both; running
  sessions unaffected (new empty dirs).
- **Rollback:** `rmdir ~/.mastermind/gbl/run ~/.mastermind/gbl/tunnel ~/.mastermind/gbl` (only
  while empty).

### 2. Place the runner
Copy staged `gbl_bridge_runner.py` → `~/.mastermind/gbl/gbl_bridge_runner.py`, `chmod 755`.
- **Check:** `shasum -a 256` matches the staged digest recorded in REHEARSAL.md;
  `/opt/homebrew/bin/python3.12 -m py_compile` exits 0.
- **Rollback:** `rm ~/.mastermind/gbl/gbl_bridge_runner.py` (nothing references it yet).

### 3. Resolve P0-2 (BLOCKER) — choose (a) reviewed RESERVED_PORTS change or (b) dedicated board
instance; record the choice in this file's history before step 5.
- **Check / Rollback:** as stated in P0-2.

### 4. Create the production board agent (principal-only — a lane may never create a board agent)
On the REAL board (read-only for lanes): create agent **"Grok Bridge"**, role `general`
(`service` → HTTP 400), adapter `process`, heartbeat off, in the production company. Fill the
returned `company_id` / `agent_id` into the spec template.
- **Check:** `GET` the agent back (GET-only is all a lane may do at 3100; the principal may do
  more) — role reads `general`, id matches the spec.
- **Rollback:** deactivate/delete the agent through the board's own path; the idle agent has no
  effect on any running session either way.

### 5. Place the spec
Fill every `<PRINCIPAL FILLS>` (repo checkout path at the merged head; company_id/agent_id from
step 4; OAuth policy fields — issuer, authorization_servers=[issuer], jwks_uri same scheme/host/
port, policy_id; edge port if 3193 was taken). Save as `~/.mastermind/gbl/spec.json`, `chmod 600`.
Admission/allowlist/environments stay `[]`. No `routine` block.
- **Check:** `/opt/homebrew/bin/python3.12 - <<'EOF'` importing `PaperclipAskClient.from_spec`
  from the repo and constructing against the spec — exits clean (this is exactly the runner's own
  startup gate; it refuses 3100 until step 3 is done, refuses a missing hmac dir, requires
  base_url/company_id/agent_id/hmac_key_path).
- **Rollback:** `rm ~/.mastermind/gbl/spec.json`.

### 6. Install + bootstrap the bridge launchd job (principal-only)
Copy staged `com.mastermind.gbl.bridge.plist` → `~/Library/LaunchAgents/`, then
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mastermind.gbl.bridge.plist`.
- **Check (all four):**
  1. `launchctl print gui/$(id -u)/com.mastermind.gbl.bridge` → state `running`;
  2. `~/.mastermind/gbl/run/bridge.log` contains one `"ready": true` line with
     `"nudge": "NOT_CONFIGURED"`, `"door_admission_rows": 0`, `"edge_admission_rows": 0`,
     `"message_allowlist_rows": 0`;
  3. `~/.mastermind/gbl/run/bridge.sock` exists and `hmac_v1.key` does NOT exist yet (created on
     first use only);
  4. `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3193/.well-known/oauth-protected-resource`
     → 200, and `curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:3193/mcp` → 401.
- **Rollback (run once in rehearsal):**
  `launchctl bootout gui/$(id -u)/com.mastermind.gbl.bridge && rm ~/Library/LaunchAgents/com.mastermind.gbl.bridge.plist`
  — SIGTERM path unlinks the socket and frees 3193; no other process or session is touched.

### 7. Empty-table refusal smoke (before any enrollment)
`/opt/homebrew/bin/python3.12 <repo>/tools/gbl/gbl_ask.py --socket ~/.mastermind/gbl/run/bridge.sock --bot probe ask --question x --idempotency-key smoke-1`
- **Check:** exit 5 with a typed admission refusal (`ADMISSION_REFUSED`/`PRINCIPAL_NOT_ADMITTED`
  family — the exact code the empty table returns); NO issue appears on the board; the store wrote
  nothing beyond its own key/lock on first tagged event (key may now exist 0600/32B — that is the
  adapter, not an ask).
- **Rollback:** none needed (refusal writes no ask); delete the smoke key from nothing — no state.

### 8. Place + start the tunnel (principal-only; AFTER step 6 is healthy — the tunnel's one origin
is the bridge listener)
Copy staged `config.yml` → `~/.mastermind/gbl/tunnel/config.yml` (`chmod 600`), copy staged
`com.mastermind.gbl.tunnel.plist` → `~/Library/LaunchAgents/`,
Before bootstrapping, re-validate the PLACED config the same way the rehearsal did — note the
FLAG POSITION (rehearsal finding): `cloudflared tunnel --config ~/.mastermind/gbl/tunnel/config.yml ingress validate`
and `… ingress rule https://mmos-link.mastermindx.ai/mcp` (must print rule #0 →
`http://127.0.0.1:3193`) — `--config` must come BEFORE `ingress`; after it, cloudflared prints
"Incorrect Usage" yet exits 0 (a false PASS), and a misplaced `ingress rule` falls back to the
DEFAULT config under `~/.cloudflared` instead of the named file. The rehearsal proved these
commands read no credential file (they passed with `credentials-file` pointing at a non-existent
path). Then
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mastermind.gbl.tunnel.plist`.
- **Check:** the pre-start validate/rule above → OK / rule #0 `http://127.0.0.1:3193`;
  `~/.mastermind/gbl/run/tunnel.log` shows registered tunnel connections;
  `curl -s -o /dev/null -w '%{http_code}' https://mmos-link.mastermindx.ai/.well-known/oauth-protected-resource`
  → 200; a request to the same host on any OTHER path pattern not routed (e.g. a bogus hostname via
  `--resolve`) → 404 from the catch-all; `lsof -nP -i :3193` shows ONLY the bridge python and
  cloudflared's loopback connections.
- **Rollback (config validated without a tunnel in rehearsal):**
  `launchctl bootout gui/$(id -u)/com.mastermind.gbl.tunnel && rm ~/Library/LaunchAgents/com.mastermind.gbl.tunnel.plist`
  — the public URL goes dark; the bridge and every running session are unaffected.

### 9. Chairman sitting steps 1–4 (principal + Chairman; order fixed by the sitting draft)
OAuth client "Mastermind Bridge" (scope/audience `mastermind.gbl.bridge`) → Secretary bot →
webhook routine "Mastermind Bridge" (URL + key delivered to the secret-owner path — never this
file, never a log) → connector URL `https://mmos-link.mastermindx.ai/mcp` (OAuth, not header).
Then, and only then, the principal may add a `routine` block to the spec (credential_path =
secret-owner path, binding_id, binding_generation, handle) and `launchctl kickstart -k
gui/$(id -u)/com.mastermind.gbl.bridge` once.
- **Check:** connector lists EXACTLY FIVE tools (static census — team.delegate / team.result /
  team.question / team.answer / team.message; digest
  d29615d2bfff3f12676b144340bdf38269cfae8e4334ed636aff04b5d9c30c4e); bridge.log READY line now
  shows `"nudge": "CONFIGURED"`.
- **Rollback:** remove the connector in Grok's UI; remove the `routine` block and kickstart again
  (nudge returns to NOT_CONFIGURED). The bridge job itself stays.

### 10. Enrollment — subject digest + door rows (principal-only; sitting step 5)
REPLACE the placeholder in `policy.allowed_subject_digests` with the real OAuth subject digest(s)
(sorted), add their row(s) to `edge.admission` (with targets/kinds/max_asks_per_hour and per-row
`message_allowlist` — which stays empty until step 11) and the matching door rows to top-level
`admission`; if the edge block was deferred, add it now (policy fields from the sitting's OAuth
client). Then `launchctl kickstart -k gui/$(id -u)/com.mastermind.gbl.bridge` (ONE restart for
many changes, ruling 8).
- **Check:** READY line shows the new row counts; an admitted `gbl_ask ask` from the principal's
  own shell now succeeds and creates the issue on the real board (first true end-to-end); an
  unadmitted label still refuses typed.
- **Rollback:** remove the rows, kickstart again; in-flight asks keep their board issues (data,
  not configuration) — reconcile with `gbl_ask reconcile`.

### 11. team.message allowlist rows — ONLY after the Chairman's environment sentence
For each admitted (environment, thread): add a `message_allowlist` row plus the matching
`environments` row (environment_id + t3code_home). Until then EVERY team.message call refuses
`ALLOWLIST_EMPTY` (rehearsal-proven) — the connector can ask/answer but cannot touch any thread.
- **Check:** READY shows `message_allowlist_rows > 0`; a test message to the listed thread arrives
  with the `[gb-<id>]` marker first line and the quoted-words wrapper; a redelivery attempt
  returns ALREADY_SENT (one delivery, ruling 19 — a test expecting a second delivery is a defect).
- **Rollback:** remove the row(s), kickstart; the marker scan means a half-sent message is
  reconciled, never double-sent.

### 12. Canary window (BUILD_PLAN)
Announced window; principal watches first asks. **Canary proof 1 (delegate round trip) is BLOCKED
until GBL-5** (open dependency below); proof 2 (question via `gbl_ask … ask --wait` / `fetch`)
works with the installed pieces — run the canary on flow 2 first.

---

## Ruling-17 overlap table (every moment between steps; old session = anything already running)

| moment | old/running sessions | new GBL pieces |
|---|---|---|
| after 1–5 (files only) | works — nothing loaded | works — inert files |
| after 6 (bridge up, tables empty) | works — untouched process/port | works — refuses typed only |
| after 7 | works | works — refusal proven |
| after 8 (tunnel up, no connector) | works | works — public 401/404 only |
| during 9 (sitting) | works | works — connector may appear before enrollment; every tool call still refuses typed (empty tables) |
| after 10 (enrolled) | works | works — admitted asks live |
| after 11 | works — a listed thread may now receive a marked message | works |
No cell fails; the only "absent ability" windows are: no asks before 10, no messages before 11,
no nudge before 9+GBL-5. The human step (9) comes before the step that depends on it (10/11).

## Ruling-21b — which side may start which work while both exist

| work kind | initiator today | after this install |
|---|---|---|
| Slack pickup + heartbeat (Secretary) | Hermes timer (stays armed) | UNCHANGED — this install adds no Slack path and moves no timer |
| board issue filed to a teammate | teammate's Hermes body ("front desk") per ruling 22b | UNCHANGED until the principal switches a kind on |
| GBL ask (question/delegate) to a Grok account | — (did not exist) | Grok-side connector ONLY, via the bridge; requires step 10 enrollment |
| team.message into a t3 thread | — | bridge ONLY, and only allowlisted (env, thread) rows after step 11 + the Chairman's environment sentence |
No effect gains two initiators.

## Ruling-19b — one host writes
`~/.mastermind/gbl/run/` holds `append.lock` (flock) + the mint/delivery ledger: numbering and
appending serialize across every process on THIS host. Only this host's bridge writes the store;
never run a second bridge against the same board company/agent, never point another host's clients
at it, never delete `append.lock`. The delivery mark is permanent: a consumed answer never
redelivers. **Consumer contract (rehearsal S13, three-fetch proof):** `fetch` delivers the answer
exactly once — the ONE hand-over is the `status=ANSWER_UNCONSUMED` response; every later fetch
exits 0, prints `status=CONSUMED` and ECHOES the answer text with a stable `answer_id` (the echo
is reconciliation aid, not a second delivery; `DELIVERY_MARK_POST_FAILED` can never produce a
second ANSWER_UNCONSUMED). Consumers — the asker wake above all — MUST branch on the `status=`
line, never on the exit code or on whether text is present.

## Open dependencies (surface, not silent)
1. **P0-2 RESERVED_PORTS blocker — STILL OPEN at 26c754bfd** (its `paperclip_client.py` is
   byte-equal to 8dad45083, so the 3100 refusal stands): install cannot reach step 5's check
   until the principal picks option (a) or (b).
2. **GBL-5 not merged**: `ask_return.py` absent; the nudge intake's production caller (the carrier
   "asked-for work returned" wake) and the control-socket carrier-result seam have no production
   caller at 26c754bfd. Consequence: canary proof 1 (delegate) is blocked; flow 2 (question via
   CLI `--wait`) works with what this list installs. The staged runner already contains the
   production nudge wiring (https-only, no-redirect bounded poster; secret read at resolve time,
   never logged) so no runner change is needed when GBL-5 lands — only the spec `routine` block.
3. **OAuth policy fields** exist only after the sitting's step 1; the edge cannot authenticate a
   real connector before then (401 for all — proven in rehearsal with a TEST issuer).

## Rehearsal artifacts (evidence, not repo)
- Driver: `~/.mastermind/mmos_dev/gbl/install-rehearsal/scripts/rehearse.py` (+ `board_standin.py`)
- Copy: `…/install-rehearsal/repo/` (`git archive 8dad45083`)
- Staged copies rehearsed: `…/install-rehearsal/staged/` (digest-equal to the evidence staged/)
- Logs: `…/install-rehearsal/logs/` — `bridge.log`, `bridge-r3.log`, `board_standin.log`,
  `rehearsal-summary.json`
- Results: `REHEARSAL.md` (this folder)
