# Lane L4 — installed app "Projects are unavailable" (Hermes Rev5 / MMOS)

Lead: L4 lane lead (glm-5.3), principal: Fable meta-orchestrator.
Branch `t3/mmos-v2-l4` from trunk `origin/feat/mmos-v1-integration-t3` @
`8d4e24d120ac35ca7622f26f27c8594a298cec6f` (2026-11-10). Evidence dir:
`~/.mastermind/mmos_evidence/l4-20261110/`.

## Problem (Chairman, installed app)

Installed app `~/Applications/Mastermind OS.app`, identity
`mmos-l3-install2-20261110-5420bb17`, source `5420bb1714…` shows
"Projects are unavailable right now. The current project list could not be
confirmed." Refresh does not help.

Principal's edge facts (2026-11-10 ~04:50 UTC): `GET /os/` 200;
`GET /workspace/programs/current` 401 without token; `POST
/os/executive/context` `{}` no token → 403
`{"code":"transport_refused","message":"fixed OS transport refused"}`.
Caddy edge (`vps-mmx:/etc/caddy/mcp-os-edge.caddy`) is a fixed allowlist;
unlisted paths abort. Prior incident note at
`t3-daae3d66/…/INCIDENT_EXECUTIVE_ENDPOINT_20261109.md` (untracked there)
concluded "origin-path outage on the VPS hop" — unsupported (chisel bind 200
on VPS, local origin `127.0.0.1:8443` 200); this lane lands a corrected
record on trunk.

Hypotheses: **A** Executive access token expired, no refresh
(`persistent()` L73 excludes `Resource::Executive`), UI shows generic
unavailable instead of sign-in-again. **B** Projects read refused for
another reason (401 / 403 transport_refused / contract mismatch with
Executive generation `dd45d111`). **C** build calls a path/method the edge
aborts.

## Evidence slices (launched 2026-11-10, one batch)

| # | Model | Angle | Output |
|---|---|---|---|
| s1 | glm-5.3 | app logs/diagnostics, exact request+status (OBSERVED vs INFERRED) | `slice1-app-observation.md` |
| s2 | deepseek-v4.1-flash | full path/method census @5420bb17+trunk vs Caddy allowlist (VPS read-only) | `slice2-path-census.md` |
| s3 | gemini-4-argon (sub-lead, effort high, READ_ONLY) | session lifecycle + UI state map + fix design | `L4_EXECUTIVE_SESSION_DESIGN.md` — completed pre-redirect; designs (a)/(b) dropped, facts kept (see Redirect) |
| s4 | grok-4.7 | installed-app driver capture: Projects/sign-in/Build details PNG+text | cancelled 2026-11-10 (app not running at probe time; no captures owed; none on disk) |
| s5 | deepseek-v4.1-flash | 2nd independent investigator (V3 rule): source facts (persist/refresh/generation), live unauth edge probes, non-secret artifacts | `slice5-hypothesis-probes.md` |

## Desktop safety rules (principal, 2026-11-10 — binding on all GUI work)

1. One GUI-driving child at a time; none while a build is installing.
2. Captures scoped to the Mastermind OS window only
   (`peekaboo image --app "Mastermind OS" --path <file>` or
   `screencapture -l <window id>`). Never full-screen/desktop. No image to a
   vision model unless it is that one window.
3. Accessibility text/clicks before coordinate clicks; two failed attempts
   at one click with no tree change → stop and report.
4. GUI child time-box: 20 minutes.

## Evidence log (lead-verified artifacts only)

- **s1 ACCEPTED** (glm-5.3; artifact opened by lead). Projects read =
  `GET https://mcp.mastermind-x.com/workspace/programs/current` (Bearer,
  `read_programs` → `Resource::Acquisition`), identical at 5420bb17+trunk.
  No on-disk logs/persisted state exist (no logging framework; log dirs and
  WebKit storage empty — OBSERVED absence). Status→code: 401→`AUTHENTICATION_REQUIRED`,
  403→`ACCESS_REFUSED`; all codes render the same UI string
  (`ArchiveProjectsView.tsx:250`). Live incident status only in memory:
  Technical details → "Refresh local native diagnostics" → "Last Projects
  HTTP status" (`executive_auth_status(diagnostics:true)`, local read).
  Decisive A-vs-B evidence = that diagnostics reading; C unlikely for this
  read (path is edge-proxied per principal's 401-without-token).

- **s2 ACCEPTED** (deepseek-v4.1-flash; artifact + verbatim Caddy block opened by
  lead; rows spot-checked against principal's measurements). Census: 83
  (method,path) pairs at trunk / 82 at installed; edge proxies only 6 GET +
  3 POST; **74 ABORTED (89%)** — every project-detail surface
  (`project-plan`, `projects/archive`, `direction/journal/session/admission/
  access/knowledge/memory/source`, all `project-planning|execution|session|
  conversation` Executive routes). One revision delta: trunk-only
  `GET /workspace/resources/t3/attempts/current` (also aborted). Single
  literal origin `https://mcp.mastermind-x.com` (auth.rs:33); no separate
  Acquisition host (audience = same host, auth.rs:68).
- **Lead verification (test home read directly):** the failing string is
  driven by `read_programs` rejecting (`App.projects-read-state.test.tsx`
  line ~30: held `read_programs` reject `SOURCE_UNAVAILABLE` → exact
  string). `read_programs` = `GET /workspace/programs/current` = edge
  **ALLOWED** → hypothesis C does NOT explain the Projects-tab string.
  Test 3: `mastermind-auth-state` `{signed_out, NATIVE_TOKEN_EXPIRED,
  acquisition:false}` → rows withheld + `.auth-entry` shown — the truthful
  sign-in-again UI already exists; it fires only if expiry is DETECTED and
  emitted. Discriminator still open: live diagnostics phase
  (`AUTH_UNAVAILABLE` vs `HTTP_FAILURE 401/403` vs `NETWORK_FAILURE`).

- **s5 ACCEPTED** (deepseek-v4.1-flash; 499-line artifact opened in full by
  lead). Corroborates s1/s2 and settles the discriminators: no Executive
  refresh path exists at 5420bb17 (`refresh_one` refuses Executive
  auth.rs:806/811; `ensure_native_token` skips refresh 929-931; `start_restore`
  restores only Acquisition+Content ~1009; expiry = clear-and-report 217-227);
  tokens memory-only, no on-disk session store (Keychain: Acquisition/Content
  refresh only); `dd45d111` appears nowhere in app source (generation =
  process-local counters, auth.rs:45/203-212). Probes P1–P7 reproduce the
  principal's numbers and add: **P4** any bearer on
  `POST /os/executive/context` → 401 `authentication_required` (route SERVED;
  the 403 is the uniform no-credential answer, not an outage); **P5** edge
  aborts only for wrong-method/unknown-route shapes the app never sends. App
  not running at probe time.

## Systemic finding (owner-ask material, evidence: slice2-path-census.md)

The installed app issues 74 paths the fixed edge aborts by design. Even with
perfect auth, project-detail surfaces cannot load through
`mcp-os-edge.caddy`. Not an outage — policy. Any widening of the allowlist is
a VPS change (hard boundary): this lane prepares the exact change +
validation command for decision, never applies it.

## Redirect (Chairman 2026-11-10 05:10 UTC) — outcome: LOCAL OPERATOR MODE

OAuth repair and session-lifecycle work STOP; the root cause of the Projects
string is settled (missing or rejected Acquisition token on an edge-ALLOWED
read) and the new outcome removes it: on the M2 the native app reads/writes the
local Executive over a Unix domain socket — no Auth0 sign-in, browser, or
token. OAuth code stays in tree, unused in local mode.

- **Contract with L8** (first landed commit, trunk):
  `LOCAL_OPERATOR_CONTRACT.md` — config block
  `local_operator:{socket_path, allowed_uids, operator_subject}` (off unless
  present), socket path convention, app switch `MM_LOCAL_OPERATOR=1` (+ optional
  `MM_LOCAL_OPERATOR_SOCKET`), dev bundle `com.mastermind.os.dev`.
- **Design** (principal's decision; one design-attack child, then build unless
  it reproduces a real break): Unix-socket listener in a NEW Executive module +
  smallest `server.py` hook; kernel peer-uid admission + socket file mode;
  socket requests attributed to the configured operator subject for OS
  executive + workspace routes, no bearer; TCP listener byte-for-byte unchanged
  (existing transport tests untouched). REJECTED IN ADVANCE: any
  trust-loopback-TCP or trust-a-header rule — the public tunnel
  (EdgeOne→Caddy→chisel) reaches `127.0.0.1:8443` with
  `X-Forwarded-For 127.0.0.1`.
- **Negative tests gate**: forged headers (XFF/Host/made-up local-operator
  header) on TCP → exactly today's refusal; peer uid ∉ allowed_uids refused on
  the socket; config block absent → no socket created; app switch off →
  sign-in gate + OAuth flow as today (existing tests untouched, green).
- **Owner gate (first hour)**: ONE read-only decision memo (gemini-4-argon) →
  `LOCAL_OPERATOR_ACTIVATION_MEMO.md` — is the Executive MCP server separately
  installable from the Control component refusing
  `control_component_worker_live`; exact owner install/enable commands;
  rollback; untouched list incl. hold #1893. No apply, no restart. Principal
  takes it to the Chairman.
- **Proof owed**: second Executive from lane code under the lead's own user at a
  fresh dev root (not L1's scratch root, not production), socket enabled; app
  built in local mode as `com.mastermind.os.dev`; text evidence under
  `~/.mastermind/mmos_evidence/l4-20261110/local-operator/` (Projects read 200
  over the socket with no token + the four negative tests).
- **Shape**: writer+attacker on each half (Executive module; app transport),
  different models, ≤2 rounds. Auth = CRITICAL row: changed files listed in the
  final return under `CRITICAL FOR RC REVIEW`.
- **Dropped**: OAuth refresh repair, session-lifecycle design (s3 designs a/b),
  rebuild/reinstall of the Chairman's installed app (waits for the activation
  decision). **Retained**: corrected incident record (flash worker); desktop
  safety rules above unchanged.

## Re-scope (principal, PROGRAM_PLAN_V3 @ trunk 46621f5ad, 2026-11-10)

Paperclip is the product shell; the native app becomes a thin window (L8) and the
old app screens are frozen. The client half of local operator mode
(`app/mastermind_os` changes to `auth.rs`/`host.ts`/`App.tsx`) is DROPPED — no
child had started it; nothing half-done is stranded on the branch. The socket
consumer is a Paperclip module worker process running as the Chairman's user;
L4 owes a small Python client example for that lane to copy. Lane closes after:
Executive socket listener + gating tests + client example, activation memo,
corrected incident record, final return.

- **Activation memo ACCEPTED** (glm-5.3 child, effort high; 367-line artifact
  opened in full by lead; load-bearing citations spot-checked against source:
  `service-control.sh:11-15/:1052-1055/:1077-1080`, `mcp_component_update.py`
  worker/control grep = 0 and allowed-change set `:587`, `autonomy_control.py:8333/:8865`,
  `install.sh:1675-1682` stage-only receipt, `executive_mcp_entry.py:69-71/:1023-1031`).
  Verdict: **YES** install/upgrade separable (own label/uid/release root + owned
  updater that never enters the Control flow), **PARTIAL** activation at HEAD
  (gateway process must restart; no owned tool can write the `local_operator`
  key until the landed release admits it — `validate_document` closed key set).
  Landed `888aa5b98`. Drafting history: gemini-4-argon attempts died on the
  provider thought_signature bug after writing the draft to disk; glm child
  revised that draft in place (same start verified); snapshot
  `/tmp/memo-gemini-draft-0711utc.md`.

## Lead adjudication — production socket mode (from memo finding, 2026-11-10)

The memo proved a real defect in contract §2 for the production case: a socket
created by gateway uid 458 with mode `0600` under a `0700` parent is
**unconnectable by the Chairman's uid 501** — file permissions gate `connect()`
before `getpeereid` is ever consulted. Dev/proof runs (same uid) never hit it,
which is why the ctypes proof passed. Resolution (launchd discipline): the
socket must be *connectable* (explicit `0660`/`0666`; parent traversable when
the module creates it), and **admission lives solely in the kernel peer-uid
check** — unforgeable, and unreachable by the TCP tunnel (different address
family). Applied to the landed module after writer verification; contract §2
carries a dated amendment. Positive side effect: with a connectable socket the
disallowed-uid negative test is meaningful (misconfigure `allowed_uids` to
exclude the test uid and exercise the real check instead of an EACCES at
connect).

## Design-attack adjudication (lead, 2026-11-10)

Grok-4.7's return said "design holds" but wrote NO artifact to disk (prose not
counted — evidence rule). Lead review of the prose: the tunnel-bypass,
OAuth-leakage and config-semantics areas are consistent with the contract —
build proceeds. One claim REFUTED by command: "peercred absent on macOS, skip
uid check" — `getpeereid(2)` works on Darwin (ctypes proof via
`/opt/homebrew/bin/python3.12` on a socketpair: `peer uid=501 == my uid`).
Skipping the uid check would admit any local user: REJECTED. Adopted as
requirements: fail closed on empty `allowed_uids`, relative `socket_path` or
malformed block (no socket created); stale socket at bind refused-if-live /
unlinked-if-stale; socket removed on stop.

## Fix / land / install (local operator mode — re-scoped)

- Executive half ONLY: writer glm-5.3, attacker grok-4.7 (≤2 rounds). Files:
  NEW `integrations/executive_mcp/local_operator.py` (+ tiny Python client
  example), smallest hooks in `integrations/executive_mcp/server.py` and
  `ops/executive_os/executive_mcp_entry.py`.
- Tests: new `tests/test_executive_local_operator.py` — (1) block absent ⇒ no
  socket; (2) peer uid not in list ⇒ refused on the socket; (3) allowed uid
  reads an OS route over the socket, no bearer; (4) TCP request with forged
  loopback/forwarded/made-up local-operator headers ⇒ exactly today's refusal;
  plus malformed-config fail-closed rows. Existing transport tests untouched
  and green.
- Command: `TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m
  pytest -q tests/test_executive_local_operator.py
  tests/test_mastermind_os_session_transport.py`.
- Land: merge trunk into lane, affected suites, non-force push
  `HEAD:feat/mmos-v1-integration-t3`. No app build, no install.

## Lane closed — listener landed (writer glm-5.3, 2026-11-10)

- Landed on `feat/mmos-v1-integration-t3` from `t3/mmos-v2-l4r`
  (head `ca2cca616` at close): NEW `local_operator.py`,
  `tests/test_executive_local_operator.py` (28 tests),
  `tools/mmos_dev/local_operator_client.py`, findings record
  `L4_LISTENER_ATTACK.md`; hooks only in `server.py`
  (`build_local_operator_mcp_app`) and `executive_mcp_entry.py`
  (optional `local_operator` block, listener beside uvicorn).
- Attack: both grok-4.7 rounds fabricated (invented shas, no file, no
  remote ref) — discarded; see `L4_LISTENER_ATTACK.md`. The real fixes
  came from the principal's three h11 questions: 100-continue stall
  and crashed-app silent close both reproduced then fixed
  (`1e77c1bee`); chunked bodies work. Keep-alive was silently dead
  (h11 0.16 API removal) and is fixed in the same commit.
- CRITICAL for RC review (auth-adjacent new surface):
  `integrations/executive_mcp/local_operator.py`,
  `integrations/executive_mcp/server.py` (hook only),
  `ops/executive_os/executive_mcp_entry.py` (hook only),
  `tests/test_executive_local_operator.py`,
  `tools/mmos_dev/local_operator_client.py`.
- Lane closed as commissioned. No app build, no install, no config
  change on any live machine.
