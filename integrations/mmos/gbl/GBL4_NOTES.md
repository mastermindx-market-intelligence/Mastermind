# GBL-4 lane note — the ask CLI + the Paperclip store client

Branch `t3/mmos-v4-gbl4` (base `41e0a88aa`, holds GBL-1+GBL-2), lane GBL-4
of the Grok Bot link (BUILD_PLAN row GBL-4; ADDENDUM_1 §1/§3; ARCHITECTURE
§5–§6; GBL2_NOTES "The Paperclip client interface"). Files owned here, as
sole writer:

- `tools/gbl/gbl_ask.py` — the asker-side CLI (`ask` / `status` / `fetch`
  with `--wait`, plus `reconcile` since round 2).
- `integrations/gbl/paperclip_client.py` — `PaperclipAskClient`, the
  `GblAskStore` protocol (`bridge_service.py:94`) over Paperclip
  issues+comments, plus `validate_paperclip_base_url` and
  `create_service_agent`.
- `tools/gbl/specs/grok_bridge_dev.json` — NEW dev-only roster entry for the
  bridge service agent in the isolated dev instance (no existing roster or
  spec was edited).
- `tests/test_gbl_ask_cli.py` (44 after round 2),
  `tests/test_gbl_paperclip_client.py` (119 after round 2).
- this note.

`common/gbl_contract.py` and the GBL-1/GBL-2 modules were imported and NOT
edited; `integrations/gbl/mcp_server.py`/`admission.py` (GBL-3, concurrent)
were not touched. **No contract change is requested** — GBL-2's store
interface covered this lane.

## The CLI (`tools/gbl/gbl_ask.py`)

`gbl_ask.py <command> --socket <path> --bot <label> …` — subcommand first,
then the shared `--socket` (default `$GBL_BRIDGE_SOCKET`) and `--bot`
(required). It talks ONLY to the bridge's AF_UNIX socket via the GBL frame
codec (`encode_gbl_frame`/`decode_gbl_frame`); there is no TCP code path
and it holds no token, secret or credential anywhere (tested: TCP socket
creation monkeypatched to raise; wire bytes, help text and output scanned
for credential words).

- `ask --question … [--idempotency-key K] [--wait]` — op `ask`, kind
  `question`. Asker identity is DATA (all-or-nothing):
  `--asker-environment-id/-thread-id/-session-label`, falling back to
  `GBL_ASKER_*` env vars; any partial set is refused with
  `ASKER_IDENTITY_INCOMPLETE` (rc 2) before any request. Prints
  `status=… ask_id=gb-…`.
- `--wait` polls `fetch_result` every `--poll-seconds` (5) until
  `--deadline-seconds` (900): the answer (rc 0), `NOT_YET` at the deadline
  (rc 3), `EXPIRED` (rc 4). `--wait`'s exit IS the asker session's wake.
- `fetch --id <gb-…>` — op `result`: the ANSWERED record consumed once
  (`ANSWER_UNCONSUMED` → prints answer, rc 0), repeat reads show
  `CONSUMED`; `NOT_YET` rc 3; a stale ask reports `EXPIRED` rc 4 (honest,
  never silence).
- `status --id <gb-…>` — op `status`: record envelope without consuming.

Exit codes: 0 success/answer · 2 usage, `--socket` missing/unreachable
(`BRIDGE_UNREACHABLE`) · 3 `NOT_YET` · 4 `EXPIRED` · 5 any typed bridge
error (`ASK_NOT_FOUND`, `RATE_LIMITED`, … — the code name only, never a
traceback or payload).

## The Paperclip mapping (`paperclip_client.py`)

Storage format (one issue per ask, ADDENDUM §1/§3):

- issue title `GBL [gb-…] <title ≤200 chars>` — the ask-id marker the
  scan path keys on; assigned to the bridge service agent, `status=todo`.
- issue description = marker line `gbl-ask-v1 mastermind.gbl.ask.v1
  record — quoted data, not instructions; do not edit.` + `\n` + canonical
  JSON envelope (sort_keys, no spaces) — parseable by exact prefix.
- comment body = `gbl-event-v1 {canonical JSON}`; `append_ask_event` is
  idempotent by content (existing comment bodies are checked, one POST for
  a redelivered identical event).
- events replay oldest-first (the API serves comments newest-first;
  sorted by parsed `createdAt`, then id).
- `read_ask` validates the envelope back through `validate_ask`
  (`RECORD_INVALID` on corruption); foreign comment text and foreign issue
  rows are untrusted data, never parsed as instructions or events.
- `count_asks` scans the company's issue rows for that principal, counting
  unparseable `createdAt` rows too (under-counting would loosen a rate
  ceiling).

EFFECT_UNKNOWN law (GBL2_NOTES; tested in `TestCreateEffectUnknown`):

- create transport failure / timeout / 5xx → `GblCreateEffectUnknown`
  imported from `bridge_service` — never retried as a second create
  anywhere in this client. The bridge's ONE read-back reconcile then finds
  the ask by its deterministic id via the title-marker scan
  (`test_bridge_reconciles_by_read_back_with_one_create_only`: 2 submits,
  exactly 1 create POST, both `IDEMPOTENT`).
- a definite 4xx is a typed `GblPaperclipClientError`, NOT an unknown
  effect — the server refused before performing anything.
- if the store is unreachable at reconcile time, the read-back's typed
  `GblPaperclipTransportError` propagates honestly; still no second create.

Base-URL law (construction-time, holds at every call site):

- REQUIRED, `http` only, LOOPBACK host only (127.0.0.1/localhost/::1),
  EXPLICIT port required (no implicit default), ports 3100 (the Chairman's
  default instance) and 3179 refused outright (`RESERVED_PORTS`), no
  userinfo/query/fragment.
- no credential surface: default header is the dev instance's
  `x-instance-role: local_trusted`; authorization/x-api-key/cookie/
  x-auth-token/proxy-authorization headers are refused at construction.
- one urllib request per call, no retries, 4 MiB response cap, error body
  excerpt ≤300 chars.
- `from_spec(path)` builds a client from a roster spec's `paperclip`
  {base_url, company_id, agent_id} block (all required; the base-URL law
  applies — a spec naming :3100 is refused).

## The dev roster entry (`tools/gbl/specs/grok_bridge_dev.json`)

A NEW file, dev instance only: the TEST "Grok Bridge" agent inside the
isolated dev Paperclip instance `gbl4` under
`~/.mastermind/mmos-dev/paperclip/` (http://127.0.0.1:3191, company
"GBL4 Dev"), with the bridge socket path
(`~/.mastermind/mmos_dev/gbl4/bridge.sock`) and one TEST admission row
(principal `grok-account-dev`, question, 20/h). No existing roster or spec
was edited; no credential anywhere in it.

## Facts for the other lanes

- **Paperclip agent `role` is an enum** (`ceo|cto|cmo|cfo|security|
  engineer|designer|pm|qa|devops|researcher|general`); `"service"` is
  rejected with HTTP 400. The dev bridge service agent uses
  `role="general"`. BUILD_PLAN install step 3 (the production agent)
  should expect the same enum. (`create_service_agent` keeps its default
  `role="service"` for tests to assert the refusal shape; call sites pass
  `"general"`.)
- The issue-list route can answer a bare JSON array OR `{"issues": […]}`
  on this build; the client accepts both (as `wake_carrier`/`door`
  already do).
- Comments: `clientRequestId` must be a UUID; comments are served
  newest-first.

## Repair 1 (panel B round, 2026-11-11)

Fixed in `integrations/gbl/paperclip_client.py` and `tools/gbl/gbl_ask.py`
(tests first, `8968fad56`; fixes `bbc91a48b`):

- **H2** — `_iter_issues` paginates (`limit`+`offset`) to exhaustion, dedup
  by issue id, `PAGINATION_UNSUPPORTED` when a server replays a page head
  (offset ignored), `LIST_TOO_LARGE` past 50 pages. `count_asks` fails
  closed on every doubt (shapes, pagination, corrupt records); it can no
  longer under-count.
- **H4** — the envelope parse finds the `gbl-ask-v1` marker and the first
  balanced JSON object ANYWHERE in the description (appended/reflowed text
  tolerated). A marker-bearing description that cannot be parsed raises
  `RECORD_INVALID` — never read as "absent" (absence mints duplicate
  creates).
- **M3** — resolution is by the parsed description envelope's EXACT ask id
  only (stronger than the allowed exact-title-token fallback: a decoy with
  the token but a foreign description resolves nothing). Title substrings
  never resolve; only an exact match is cached; a stale cache entry is
  re-resolved, never trusted.
- **M4/M5** — unknown list/comments envelope shapes and junk rows are typed
  errors (`UNPARSEABLE_*`), never empty lists.
- **M6** — a module opener with `_NoRedirectHandler` + `ProxyHandler({})`
  (no redirects, no proxies); a 3xx is the typed
  `GblPaperclipRedirectError` (subclasses `GblPaperclipServerError`, so a
  create redirect is EFFECT_UNKNOWN). `_checked_url` re-verifies the
  loopback law (scheme/host/port/no-userinfo/no-fragment) on EVERY request.
- **M7** — 408/409/425/429/499 on create map to `GblCreateEffectUnknown`
  (ambiguous, read-back reconciled); definite 4xx stay
  `GblPaperclipClientError`. Typed errors carry `.status`.
- **M8** — `http.client.HTTPException` (IncompleteRead, BadStatusLine, …)
  is caught with the transport family; a truncated create reply is
  EFFECT_UNKNOWN with the read-back reconcile, never a raw exception.
- **M9** — every path segment passes `_quote_segment`: strict charset
  `[A-Za-z0-9_-]{1,128}` (no dots, no slashes) then percent-encoded.
  company/agent ids raise `ValueError` at construction; server-supplied
  issue ids raise the typed `INVALID_ISSUE_ID` (fail closed), including
  ids inside list rows.
- **M1/M2 exposure (client side; protocol unchanged)** — every parsed
  event gains `comment_id`, `comment_author`, `comment_created_at` and
  `comment_order` (`"<createdAt-or-''>|<comment id>"`, the same total key
  the client sorts by). Author is read from `authorAgentId` / `agentId` /
  `authorId` / `createdBy` / `author` (first present string), else None.
  **Awaiting the GBL lane's trusted-author/order/create-if-absent
  contract to rename or extend these fields.** Real-build fact for that
  round: comments POSTed via `/api/issues/{id}/comments` under
  `x-instance-role: local_trusted` come back with `authorAgentId: null`,
  `authorType: "user"`, `authorUserId: "local-board"` — the plain REST
  route cannot produce agent-attributed comments on this build, so
  author-based trust needs an agent-authenticated comment surface (or a
  server change); the client already reads whichever field lands.
- **L6/L7/L8** — custom headers MERGE with the default instance-role
  header; credential-shaped header names are banned BY WORD (token/secret/
  password/auth/cookie/credential/api-key/apikey/bearer); the explicit
  port must be in 1..65535.
- **CLI (N1/N3/L10/L11)** — `--wait` retries transient bridge conditions
  (`BRIDGE_UNREACHABLE`, `BRIDGE_RESPONSE_INVALID`) until the deadline and
  at the deadline keeps the non-wait exit code (unreachable = 2, not 5);
  an ask reply without a well-formed ask_id is `BRIDGE_RESPONSE_INVALID`
  (never `ask_id=None`, never a silently skipped wait); `--poll-seconds`
  must be finite > 0 and `--deadline-seconds` finite >= 0 (usage errors).

Not fixed here (not mine / deferred, with reasons):

- **H1, H3, M1-full, M2-full, N2, L1, L2, L3, L5** — `bridge_service.py` /
  `common/gbl_contract.py`, owned by the GBL lane (panel A + panel B
  H1/H3/M1/M2 repair round). This lane supplies the author/order
  provenance fields above for their M1/M2 fix.
- **L4** (`status` never reports EXPIRED) — the bridge's `status` op
  result (`ask_status`) carries no `expires_at`, so the CLI has no data to
  display; needs a GBL-lane op change, listed for their round.
- **L9** (`create_service_agent` not idempotent / weak role validation) —
  create-if-absent is exactly what the GBL lane's pending contract round
  is defining; implementing a name-scan heuristic now would pre-empt it.

Dev proof re-run after the repairs (same persisted dev instance, own
ports, everything stopped after): see the "Repair 1 re-run" section of
`~/.mastermind/mmos_evidence/gbl-20261111/gbl4-devproof.md`. New probed
facts recorded there: real pagination IS supported (offset honored, bare
array), and the comments route's author-null behavior above.

Test evidence for this round (same command, one file at a time):
`tests/test_gbl_paperclip_client.py` 88/88, `tests/test_gbl_ask_cli.py`
35/35; regressions `tests/common/gbl_contract_test.py` 72/72,
`tests/test_gbl_bridge_service.py` 35/35, `tests/test_gbl_nudge.py`
10/10, `tests/test_gbl_message_send.py` 19/19.

## Round 2 (GBL contract adaptation, 2026-11-11)

Merged the GBL lane's `t3/mmos-v4-gbl` at `a20872981` (clean merge,
non-force; NO GBL-owned file — `bridge_service.py`, `gbl_contract.py`,
`nudge.py`, `message_send.py`, `mcp_server.py`, `admission.py`, their
tests — was edited here). The contract note
(`integrations/mmos/gbl/GBL_REPAIR1_NOTES.md` §1–§3) needed no change;
everything it requires was implementable on the current Paperclip
surface. Tests first (`de402e7e2`, 88 failing assertions), fixes in the
same files I own (`integrations/gbl/paperclip_client.py`,
`tools/gbl/gbl_ask.py`, the two test files, this note, the dev spec):

- **§1.1 create-if-absent** — `create_ask` first resolves the
  deterministic ask id through the exact-key path (`read_ask`), returns
  the EXISTING record when present (a fresh copy; no raise, no second
  issue, no mutation), and returns `None` only after a create POST
  landed. A failure of the pre-create absence check is NOT an unknown
  effect (nothing began) and propagates as its own typed read error —
  the POST is never issued. `GblCreateEffectUnknown` keeps its exact
  meaning for a lost/ambiguous CREATE (transport, 5xx, redirect,
  truncated reply, 408/409/425/429/499, unusable reply id), and the
  bridge's read-back reconcile path is unchanged. Replay through the
  merged bridge: two submits, exactly one issue, `IDEMPOTENT`.
- **§1.2 seq + trusted** — every append is stamped BY THE STORE with
  `seq = max(seq of verified events) + 1` (per record, starting at 1) and
  surfaced `trusted: True` only when the §2 tag verifies. Incoming
  `seq`/`tag`/`trusted` keys on an append are never written through.
  **Deputy steer (round 2), implemented as ruled:** seq derives ONLY
  from tag-verified (trusted) events, so a foreign or untrusted comment
  — including one carrying a huge forged `seq` or a claimed
  `"trusted": true` — can never move or block the sequence, and trust is
  gated on `trusted is True` EXACTLY (the flag is computed from HMAC
  verification, never read from the comment JSON). A fresh client
  instance continues the record's sequence: derivation is from the
  stored record, not instance state.
- **§2 HMAC v1 tag** — the adapter holds ONE host-local key: 32 random
  bytes, generated on first use (lazy), stored mode 0600 inside the
  EXISTING bridge state dir (a missing dir is the typed
  `HMAC_KEY_DIR_MISSING` — this client never mints directories), read
  from the `hmac_key_path` given by config (constructor /
  `paperclip.hmac_key_path` in the spec — REQUIRED in `from_spec`; no
  spec configures a trust-absent client). File law is enforced on load:
  wrong length → `HMAC_KEY_INVALID`, any group/other permission bit →
  `HMAC_KEY_MODE_INVALID`, unreadable → `HMAC_KEY_UNREADABLE`, and a
  client with no key configured fails closed with
  `HMAC_KEY_NOT_CONFIGURED` the moment a key is needed (a tagged event
  is proof one exists — never a silent all-untrusted read). Tag shape
  is exactly §2.2: `"v1:" + HMAC-SHA256(key, ask_id + "\n" + str(seq) +
  "\n" + canonical_json(event_without_tag)).hexdigest()`, so the tag
  binds the event to ITS ask record (a genuine tagged comment replayed
  onto another ask fails verification — tested). On read, an
  event-shaped comment whose tag is absent, malformed, wrong-version,
  bound elsewhere, or failing verification surfaces `trusted: False`
  and the bridge ignores it; the `tag` itself never surfaces to the
  bridge. The author/id/timestamp/order provenance fields from Repair 1
  are now DISPLAY AND ORDERING METADATA ONLY (per §2's ruling; the
  dev-proof fact stands: the plain comments route cannot produce
  agent-attributed rows). The KEY never crosses the wire, never enters
  Paperclip, never appears in an error — asserted over every recorded
  request body/path/header and every stored comment in the suite.
- **§3 expires_at + reconcile** — `status` prints `expires_at` whenever
  the bridge carries it and exits 4 on a status of `EXPIRED`. New
  `reconcile --id <gb-…>` subcommand: wire op `reconcile` with
  arguments EXACTLY `{ask_id}` (its parser deliberately has NO `--bot`;
  the door's `_OP_ARGUMENTS` pins the key set). Rationale for the CLI
  owning this surface: the MCP edge is a static five-tool census
  (`team.delegate/result/question/answer/message`) with no reconcile
  tool, so the local AF_UNIX door is the op's one lawful caller — an
  operator settling a `NUDGE_EFFECT_UNKNOWN` by observation, which
  never sends.
- **§5 nudge write-law mitigation, already in place** —
  `append_ask_event` is idempotent by CORE content (a trusted match
  suppresses the duplicate POST), so a nudge-event append whose reply
  was lost is safely retryable: the retry finds the landed core and
  never double-counts cooldown/budget. No store change was needed for
  this; it falls out of the content-idempotency law above.

Not fixed here (not mine / by design):

- **Rotation beyond `v1`** — §2.5 pins a single key; re-tagging events
  is a conscious future migration, not this round.
- **`create_service_agent` idempotency (Repair-1 L9)** — the contract
  round defined create-if-absent for ASK records only; agent creation
  stays a dev-proof helper and remains non-idempotent.

### Install: HMAC key (the principal's step — never done by this lane)

The production bridge's store adapter generates its key on first use,
so the INSTALL step is to place the state directory and let the bridge
create the file — or pre-create it:

1. **Path**: `<bridge state root>/gbl_hmac_v1.key`, where the state
   root is the directory holding that deployment's `bridge.sock` (the
   dev proof's root is `~/.mastermind/mmos_dev/gbl4/`; production uses
   the production bridge's state dir chosen at install). The path goes
   into the roster spec as `paperclip.hmac_key_path`.
2. **Owner**: the uid that runs the bridge process (the same user that
   owns `bridge.sock`). No other user needs read access — the key never
   leaves the host.
3. **Mode 0600** exactly; the client refuses the file on ANY group/other
   permission bit (`HMAC_KEY_MODE_INVALID`), so a loose mode is a
   visible deployment error, not a silent risk.
4. **Generation** — either let the adapter generate it on first use
   (32 random bytes via `secrets`, written 0600 into the existing dir),
   or pre-create: `umask 077 && head -c 32 /dev/urandom >
   <state root>/gbl_hmac_v1.key && chmod 600 <state root>/gbl_hmac_v1.key`.
   The key file must hold exactly 32 bytes.
5. **Never**: on argv, in a log, in a commit, in Paperclip, on the wire,
   or in an error message. Losing the file demotes every existing event
   to `trusted: false` (visible: answered asks stop looking answered)
   — restore from backup or accept the migration; do not delete it
   casually. A fresh dev instance may freely generate a new one.

## Test-run evidence (one file at a time)

`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q
-p no:cacheprovider <file>`:

- `tests/test_gbl_ask_cli.py` — 20/20 (real GBL-2 `GblBridge`+
  `BridgeServer` on a temp socket, `allowed_peer_uids=(uid,)`, in-memory
  store)
- `tests/test_gbl_paperclip_client.py` — 33/33 (fake HTTP server bound to
  127.0.0.1 on an EPHEMERAL port; the real GblBridge is driven over the
  client for the EFFECT_UNKNOWN tests)

Regressions of imported modules: `tests/common/gbl_contract_test.py`
72/72, `tests/test_gbl_bridge_service.py` 35/35, `tests/test_gbl_nudge.py`
10/10, `tests/test_gbl_message_send.py` 19/19. No real Paperclip instance
is contacted by any test.

## Dev proof (2026-11-11, one stack at a time, all stopped)

Evidence: `~/.mastermind/mmos_evidence/gbl-20261111/gbl4-devproof.md`.
Chain proved end-to-end against a NEW dev instance `gbl4`
(127.0.0.1:3191, db 54391, both checked free; never 3100/3179/3190 or the
default instance): the TEST "Grok Bridge" agent created ONLY inside it;
GBL-2's `BridgeServer` on `~/.mastermind/mmos_dev/gbl4/bridge.sock` over
`PaperclipAskClient.from_spec`; `gbl_ask ask` → issue GBL-1 created and
assigned to the agent with the asker identity as data → answer appended as
`gbl-event-v1` comments → first `fetch` returned `ANSWER_UNCONSUMED` rc 0
and the answer, second `fetch` `CONSUMED` (exactly ONE `CONSUMED` comment)
→ idempotent replay `IDEMPOTENT` with exactly 1 marker issue. Teardown
verified: bridge STOPPED and socket unlinked, dev Paperclip stopped, no
listener left on 3191/54391. The default Paperclip (127.0.0.1:3100,
`~/.paperclip`) was never contacted; no request went to
3773/3774/3780/3100/3190/3796/3800; no Grok/xAI/Cursor/Slack/tunnel
service was contacted.
