# Incident (CORRECTED): Mastermind OS — "Projects are unavailable", 2026-11-09

Verdict superseded 2026-11-10. Original diagnosis 19:45–19:58 MST (worktree `t3-daae3d66`); corrected
by synthesis of lead-verified slices 1/2/5 in `~/.mastermind/mmos_evidence/l4-20261110/`. The original's
**probe table is kept** — those measurements were real. The **inference** drawn from them was not.
Window: broke ~19:22–19:45 MST (three projects rendered ~19:15). Build `mmos-l3-install2-20261110-5420bb17`
(pid 99257). Symptom: "Projects are unavailable right now. The current project list could not be confirmed."

## Route map (end to end) — unchanged; every hop verified healthy

1. App → `https://mcp.mastermind-x.com` (`const ORIGIN`, auth.rs:33; audiences `workspace/read`, `workspace/window/current`, `MM_EXECUTIVE_RESOURCE`).
2. DNS → CNAME `mcp.mastermind-x.com.eo.dnse3.com` → 43.159.98.106 / 43.159.99.101 (EdgeOne edge); TCP+TLS fine.
3. Edge origin = VPS **146.190.142.17:443**, Caddy front, valid public cert (`/etc/caddy/mcp-os-edge.caddy`).
4. VPS loopback upstream `127.0.0.1:49152` = chisel **server** reverse-bind, carried by the chisel client on this Mac.
5. This Mac: root LaunchDaemon `com.mastermind.executive.os-public-tunnel` (`os_tunnel_entry.py`, release `a858ac24…`) → chisel client pid 765, up since Oct 25, `--keepalive 20s`.
6. Origin: Executive MCP `127.0.0.1:8443`, pid 46497, release `dd45d111…`, up since 02:44.

## Measured evidence (19:45–19:55 MST, read-only) — real, as recorded

| Check | Result |
|---|---|
| Public `/healthz` + `/.well-known/oauth-protected-resource` via edge | curl exit 92 (h2 INTERNAL_ERROR), reproduced |
| Direct to VPS bypassing edge (`--resolve …:443:146.190.142.17`) | identical exit 92 — edge faithfully forwarding |
| TCP/TLS to VPS 146.190.142.17:443 | succeeds (nc + curl TLS) |
| Local origin `127.0.0.1:8443/.well-known/oauth-protected-resource` | **200** — origin healthy; other paths 404 (vhost routing, not a crash) |
| chisel client pid 765 | ESTABLISHED; stderr ends `04:29:45 client: Connected`, zero events since; no bind errors back to Nov 6 |
| Second chisel pid 44781 (fabric-application-tunnel) | binds `R:127.0.0.1:50142:127.0.0.1:4142` — no conflict with 49152 |
| Executive Control/MCP processes | up ~17 h, unchanged through the window; no restarts |
| Local receipts after 17:00 (`/Library/Application Support/MastermindExecutive`, `/private/var/db/mastermind-executive`) | none (excluding sqlite-wal/pyc) — no local Executive act |
| `~/.local/share/studio-direct-mcp/control` | all files Nov 8 23:27 — nothing today |

Slice5 annotation: the two exit-92 rows are **unauthenticated metadata / unknown-route** shapes — refusals
the edge is designed to produce (P5, P7), reproducible today. They say nothing about the read the app issues.

## ~~Verdict: H1 (origin-path outage) — dead hop on the VPS~~ **STRUCK**

> **Why H1 is wrong.** (a) slice5 **P4**: `POST /os/executive/context` **with any bearer is served**
> — 401 `authentication_required` from uvicorn. The route is not dead; the principal's 403 is this
> server's uniform *no-credential* answer (P3, also `/os/executive/status`), not an outage. (b) slice5
> **P5**: edge aborts occur only for wrong-method/unknown-route shapes (GET or OPTIONS on the Executive
> prefix, made-up `/os/executive/*` routes, `POST` on a GET path) — the app sends none. (c) slice2 §1:
> the failing Projects read `GET /workspace/programs/current` is **edge-ALLOWED** verbatim in the Caddy
> `@get` matcher, and the principal measured 401-without-token on it (P2) — the path is served end to
> end, so the user-visible symptom cannot be an edge/VPS outage.
> **Methodological cause.** The 19:45 session probed unauthenticated metadata paths and inferred an
> outage from transport refusals that are today's *designed* no-credential behavior. H2 was excluded on
> that same misreading; H2 was closer to the truth.

## Corrected verdict (INFERRED) — no valid Acquisition token on an edge-ALLOWED read

The string traces to the app's Projects read failing on a route the edge **allows**, because the app holds
no valid Acquisition token:

- The read is `GET /workspace/programs/current` with `Authorization: Bearer <Acquisition access token>`, `Accept: application/json`, `Cache-Control: no-store` (slice1 (c), slice5 F6; slice2 #1 ALLOWED). Live, that request without a token or with a bad one returns `401 {"error":"authentication_required"}` with a precise `WWW-Authenticate` (slice5 P2, P6).
- **Tokens are memory-only.** No `std::fs`/`tokio::fs` in `auth.rs`, no persistence plugin, only in-memory `Inner` (slice5 F1, F2). No on-disk session store: `Application Support/com.mastermind.os`, `HTTPStorages`, `Saved Application State`, `Preferences` absent; `LocalStorage`/`IndexedDB` empty (slice5 C2; slice1 (a) rows 5–7). Only durable credential = one Keychain refresh service for Acquisition/Content, build-gated by `MM_NATIVE_REFRESH_ENABLED` (slice5 F3).
- **No Executive refresh path exists:** `persistent()` is `self != Self::Executive && native_refresh::enabled()`; `refresh_one` refuses Executive twice; startup restores only Acquisition/Content (slice5 F4, F17, F18). A restart guarantees the Executive token is gone (slice5 C3: app not running at probe time).
- **The string cannot discriminate.** Every failure code — 401, 403, 404, transport, schema, body — renders the identical sentence, and the stale-owner/epoch fence renders it too on a *successful* read (slice1 (c) status map; slice5 F10, F12, B1).
- The **2026-11-09 exit-92 public-metadata failures remain real** (slice5 P7) but are metadata routes the app's reads never call — they do not explain the app symptom.
- Scope: `programs_read.phase`/`http_status` was never read, so the per-read failure code is **UNKNOWN** (slice1 (e); slice5 N2 names the one field that would settle it). The verdict above is the sole class consistent with an allowed route + memory-only tokens; the stale-owner fence (slice5 B1) remains a second, server-free rendering of the same string.

## Outcome supersede — Chairman decision 2026-11-10 05:10 UTC

OAuth repair is **not being built**. For local M2 use, OAuth sign-in is removed via **local operator mode**:
the app reads/writes the local Executive over a Unix domain socket — no Auth0, no browser, no token. See
`integrations/mmos/LANE_L4_INSTALLED_APP.md` § "Redirect" and `integrations/mmos/LOCAL_OPERATOR_CONTRACT.md`.
OAuth code stays in tree, unused in local mode.

## Day-to-day session note (kept — it fed the final diagnosis)

In `5420bb171:auth.rs`, `Resource::persistent()` is `self != Self::Executive && native_refresh::enabled()`,
and `native_refresh::enabled()` is compile-time `MM_NATIVE_REFRESH_ENABLED == "1"`. The **Executive resource
never gets `offline_access`/refresh** — only Acquisition/Content can persist, and only in a refresh-enabled
build. An Executive signed-in session cannot outlive its access-token lifetime (`parse_token` requires
`expires_in`); expiry forces explicit re-sign-in via a fresh Authorization Code + PKCE transaction (slice5 F18).
