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
| s3 | gemini-4-argon (sub-lead, effort high, READ_ONLY) | session lifecycle + UI state map + fix design | `L4_EXECUTIVE_SESSION_DESIGN.md` |
| s4 | grok-4.7 | installed-app driver capture: Projects/sign-in/Build details PNG+text | `projects-state.*`, `signin-state.*`, `build-details.*` |
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

## Systemic finding (owner-ask material, evidence: slice2-path-census.md)

The installed app issues 74 paths the fixed edge aborts by design. Even with
perfect auth, project-detail surfaces cannot load through
`mcp-os-edge.caddy`. Not an outage — policy. Any widening of the allowlist is
a VPS change (hard boundary): this lane prepares the exact change +
validation command for decision, never applies it.

## Fix / land / install (to be filled)

- Writer: glm-5.3 (worktree branch); attacker: grok-4.7 (diff review, different model).
- Tests: `App.projects-read-state.test.tsx` + Rust tests in `auth.rs`.
- Land: merge trunk into lane, affected suites, non-force push `HEAD:feat/mmos-v1-integration-t3`.
- Build/install per `INSTALL_RECEIPTS_AND_ROLLBACK.md` §5.1 (identity
  `mmos-l4-installed-<date>-<shortsha>`), driver captures from the new build.
