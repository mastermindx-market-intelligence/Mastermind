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
  `tests/test_gbl_paperclip_client.py` (136 after the final round).
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

Merged the GBL lane's `t3/mmos-v4-gbl` at `e5a69f9ff` (superseding the
round's first merge of `a20872981`; both clean, non-force; NO GBL-owned
file — `bridge_service.py`, `gbl_contract.py`, `nudge.py`,
`message_send.py`, `mcp_server.py`, `admission.py`, their tests — was
edited here). The contract note
(`integrations/mmos/gbl/GBL_REPAIR1_NOTES.md` §1–§3 at `e5a69f9ff`)
needed no change; everything it requires was implementable on the
current Paperclip surface. Tests first (`de402e7e2`, 88 failing
assertions), fixes in the same files I own
(`integrations/gbl/paperclip_client.py`, `tools/gbl/gbl_ask.py`, the
two test files, this note, the dev spec):

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
- **§1.2 seq + trusted (trusted-only derivation, exact bool)** — every
  append is stamped BY THE STORE with
  `seq = max(seq over events with trusted === true) + 1` (per record,
  starting at 1) and surfaced `trusted` as an EXACT bool. Incoming
  `seq`/`tag`/`trusted` keys on an append are never written through.
  **Implemented per GBL_REPAIR1_NOTES §1.2 at `e5a69f9ff` (first ruled
  by the deputy's round-2 steer):** seq derives ONLY from tag-verified
  (trusted) events, so a foreign or untrusted comment — including one
  carrying a huge forged `seq` or a claimed `"trusted": true` — can
  never move or block the sequence (the reference FakeStore's
  last-event derivation was deliberately NOT copied), and trust is
  gated on `trusted is True` EXACTLY (the flag is computed from HMAC
  verification, never read from the comment JSON; every surfaced
  `trusted` is a real bool). A fresh client instance continues the
  record's sequence: derivation is from the stored record, not
  instance state. `EVENT_TRUST_INVALID` stays the bridge's own check on
  non-bool stored rows; this store never writes one.
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
- **§3 expires_at + reconcile + nudge_settled** — `status` prints
  `expires_at` whenever the bridge carries it and exits 4 on a status
  of `EXPIRED`. New `reconcile --bot <label> --id <gb-…>` subcommand:
  wire op `reconcile` with arguments EXACTLY `{principal, ask_id}` (the
  round-2 law at `e5a69f9ff`; it shares the common `--socket/--bot`
  shape because the op now carries the same creator-or-addressee party
  check as every other mutating op — the door's `_OP_ARGUMENTS` pins
  the key set). Rationale for the CLI owning this surface: the MCP edge
  is a static five-tool census
  (`team.delegate/result/question/answer/message`) with no reconcile
  tool, so the local AF_UNIX door is the op's one lawful caller — an
  operator settling a `NUDGE_EFFECT_UNKNOWN` by observation, which
  never sends. The new `nudge_settled` event kind is persisted and
  signed like any other event (stamped seq, v1 tag, surfaced with
  computed `trusted`) — tested explicitly; the
  `NUDGE_ATTEMPT_UNSETTLED` re-arm block is bridge law over the store.
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

## Round 3 (panel B delta 1, micro round, 2026-11-11)

Head under review `894f8aae5`: 10/10 round-1 items CLOSED, F1 seam
CLOSED, HMAC core held, 398/398. This round fixes the two required MEDs
in new code and the two cheap med-notes; LOWs left as noted by the panel.

- **D1 + D2 (MED, fixed — unparseable forgery never raises)** — the law:
  a comment whose JSON cannot be parsed or canonicalised (NaN/Infinity,
  nesting past the recursion limit, anything oversized, any parse or
  canonical error) is UNTRUSTED and ignored, never a raw exception out
  of `read_ask`/`append_ask_event`. Implemented as the deputy's
  sanctioned shape — a LENGTH CAP plus a RecursionError catch around the
  parse and canonicalise steps, with `parse_constant` rejecting the
  NaN/Infinity family:
  - `_parse_event_body`: `MAX_EVENT_JSON_CHARS` (64 KiB — ~16× the
    store's own largest write) caps the payload BEFORE `json.loads`;
    `parse_constant=_reject_json_constant` turns NaN/Infinity/-Infinity
    into a parse failure; the except is now `(ValueError,
    RecursionError)`.  Every failure → `None` (the R3-precedent drop:
    unparseable = not an event = ignored).
  - `_verified_event`: the canonicalise step (`_event_tag` →
    `_canonical`) is wrapped in the same `(ValueError, RecursionError)`
    catch — an event that parses but cannot be canonicalised verifies as
    nothing → `trusted: False`. (Defense in depth: with the parse-time
    constant rejection, NaN can no longer reach canonicalisation at
    all; the catch also covers a parse-shallow/canonicalise-deep
    asymmetry.)
  - Sibling surface, same paths: the ISSUE DESCRIPTION is foreign-writable
    too. `_parse_ask_envelope` takes the same `parse_constant` and the
    `RecursionError` in its except — on that surface the law is the
    typed `RECORD_INVALID` (panel B H4: corruption is never read as
    absence), which is what a deep marker payload and a NaN marker
    payload now both raise instead of a raw RecursionError / surfaced
    `float('nan')` data.
  - Tests (one per shape, each showing the ask still reads AND appends
    with the forgery present, seq counter untouched): NaN / Infinity /
    -Infinity, ~20k-deep nesting, oversize (cap+1), deep marker payload,
    NaN marker payload — plus the four key-anchor tests below. All were
    failing first against `894f8aae5` (raw `ValueError`, raw
    `RecursionError`, symlink adopted, group-writable dir accepted).
- **D3 (MED-note, fixed — dangling-symlink recursion)** — the first-use
  race retry was an unbounded `return _load_or_create_hmac_key(path)`:
  a dangling symlink (stat→FileNotFoundError, O_EXCL create→EEXIST)
  looped to a raw RecursionError. Now `FileExistsError` takes ONE
  bounded `lstat` of whatever exists and falls through to the normal
  law (typed `HMAC_KEY_UNREADABLE` if nothing is there); no recursion.
- **D5 (MED-note, fixed — key-anchor hardening, the cheap parts)** —
  `lstat` + `S_ISLNK` refusal (`HMAC_KEY_IS_SYMLINK`: a symlink to a
  valid 0600 key is no longer adopted verbatim, and a dangling one is
  refused as a symlink before any create loop); `O_NOFOLLOW` on the
  first-use create open; and a state-root mode check refusing group- or
  other-WRITE bits (`HMAC_KEY_DIR_MODE_INVALID`, mask 0o022 — the
  ordinary 0755 dev/production roots stay legal, tested).  Residual,
  accepted: `lstat`-then-`read_bytes` still has an unlink+replace TOCTOU
  window requiring local write at the state root (an install-law
  violation) — an fd-based `O_NOFOLLOW` read would close it if a future
  round wants it.
- **D4 (MED-note, left as a note)** — two COLD racing `create_ask`
  callers can both pass the absence read and POST twice (2 issues, same
  ask id).  Unreachable in v1: the store's only caller (the bridge)
  serves strictly serialized.  Flagged for any future multi-writer
  round; not fixed here (not a few lines — it needs a server-side
  uniqueness constraint or a create-then-reconcile-merge the contract
  does not define).
- **LOWs R1–R6 (left, per the deputy)** — unchanged.

### Install: HMAC key — one added line for the principal

The install step in the section below gains one check: the state root
directory must not be group- or other-writable (`chmod 750`/`755` fine,
`770`/`777` refused with `HMAC_KEY_DIR_MODE_INVALID` at first use), and
the key file must be a regular file — a symlink, even to a valid key,
is refused (`HMAC_KEY_IS_SYMLINK`).

## Repair round 2 (deputy ruling 2 under RULING 19, 2026-11-12)

Independent check of the GBL-5 head (`REVIEW-deputy-deepseek.md`): 2 HIGH,
3 MED, 6 LOW. Both HIGHs verified and fixed at `dd22e755f`…`16ecba69f`.

- **H1 → RULING 19(b): one lock across every process.** The A1/A2 guard
  was a `threading.Lock` + per-object `_issued_seq` floor — per client
  OBJECT, so a second client or another process re-issued taken numbers
  (the failing-first proof: two real child processes, each with its OWN
  client, both minted seq 3 over a lagging listing). Fix: ONE exclusive
  flock on `append.lock` in the GBL state dir (the HMAC key's directory),
  held across the whole allocation+append step of `append_ask_event` —
  every writer path funnels through that method (the bridge ops, the CLI
  over the bridge socket, control intake, nudge/reconcile, `from_spec`
  clients), so every writer takes the same host lock. The lock file
  doubles as the cross-process mint ledger (append-only JSON lines; the
  floor is read under the lock before every mint; the line is written at
  mint time, BEFORE the POST, so a number once minted is never re-issued
  by any process even when its POST fails — worst case a skipped
  number). The kernel releases the flock when a holder dies; a torn
  ledger tail line is ignored on read. Typed errors:
  `APPEND_LOCK_UNWRITABLE`, `APPEND_LOCK_UNREADABLE`. **ONE HOST WRITES
  THE STORE**: the lock and ledger are host-local files, so a second host
  constructing clients against the same board holds a different lock and
  is OUT OF CONTRACT by construction — never point two hosts' state dirs
  at one Paperclip store.
- **H2 → RULING 19(a): a delivery mark is permanent.** The A3 demotion
  picked the later holder of a duplicate seq by position with no type
  check — on the MMO-1 shape it dropped the CONSUMED, replay re-derived
  ANSWERED, and the next `fetch_result` handed the SAME answer out a
  second time before a "healed" CONSUMED indistinguishable from a first
  delivery. Fix: a STATE event re-issuing a taken seq is never demoted —
  the reading refuses typed `EVENT_ORDER_AMBIGUOUS` (both the store's
  `_chain_verified_events` and the bridge's `_ordered_events`, the same
  law) and NOTHING is delivered, re-derived or healed forward; the
  append path refuses the same way, so no blind healing append exists
  (MED-3 is closed by this refusal: an ambiguous record cannot mint an
  indistinguishable CONSUMED). Non-state duplicates keep the per-event
  demotion (first holder authoritative, record readable). The test that
  expected the second delivery is rewritten to expect the refusal
  (RULING 19(c): such a test is a defect, not a specification).
- **MED-1: `seq < last_seq` refuses, never drops.** A strictly lower
  trusted seq after a higher one (a delayed or torn append) used to be
  stamped `EVENT_SEQ_DUPLICATE` and vanish; it now refuses
  `EVENT_ORDER_AMBIGUOUS` on both layers.
- **MED-2: demoted nudge markers still count.** Budget, cooldown and
  settlement in `maybe_renudge`/`reconcile_nudge` count every
  nudge-family row the trusted writer really POSTed — including rows the
  duplicate law demoted (`defect: EVENT_SEQ_DUPLICATE`; tag verified,
  only the number re-issued). Foreign rows count nothing.
- **MED-3: closed by the H2 refusal** (above) — no healing append exists
  to mask.
- **6 LOWs wait** (unbounded detail across the typed door, lazy-import
  serve-loop risk, truncated-key unlink, close-time EIO, idempotency
  over demoted rows, unbounded floor map / lock-held-across-POST) —
  later list, per the deputy.

### Install: one host writes — the state dir now holds `append.lock`

The install step gains this line: the GBL state root (the directory
holding `hmac_v1.key`) now also holds `append.lock`, created on first
append — the ONE host-wide serialisation point (flock + mint ledger).
ONLY ONE HOST writes the store: the bridge host's state dir owns that
file; do not share the state dir or point a second host's clients at the
same Paperclip store, and do not delete `append.lock` (a lost ledger
falls back to the server listing, re-opening the lag window between
processes).

## Final round (panel B delta 2, ruling 12, 2026-11-11)

Delta check 2 at `337b145d1`: 4/4 delta-1 items CLOSED, no new HIGH,
409/409. Final items:

- **F1 (MED, fixed — marker-removal replay duplicate)** — a foreign edit
  that deletes the marker line makes the ask read as ABSENT, and a
  create replay minted a duplicate issue whose empty record became the
  resolver, stranding the original answer.  `create_ask`'s absence path
  now cross-checks the exact `[ask_id]` title token across the company
  (titles only — no description parsing, so no new F2 exposure) and
  refuses with the typed `AMBIGUOUS_CREATE` before any POST.  Exactness
  is by construction: ask ids are a fixed `gb-`+32-hex shape, so the
  closing bracket cannot belong to a longer id; a different ask's
  create is never refused by this ask's issue (tested).  The repair for
  the operator is out-of-band (restore the description); with no
  duplicate minted, the stored events survive and the record reads back
  intact once restored — tested end-to-end including the trusted answer
  event.
- **F3 (MED-note, fixed — about 13 lines)** — the first-use key create
  sat inside the `except FileNotFoundError` handler, so `os.open`
  failures other than `FileExistsError` (EACCES/EROFS/ELOOP) and
  `os.write` failures (ENOSPC family) escaped RAW out of
  `read_ask`/`append_ask_event`.  Both steps now raise the typed
  `HMAC_KEY_UNWRITABLE`; a partial file left by a failed write fails
  closed on the next use as `HMAC_KEY_INVALID`.  Tests failing first:
  a 0555 state dir (real EACCES → raw `PermissionError` before) and a
  simulated ENOSPC on the write (raw `OSError` before).
- **F2 (MED-note, kept as a note by the deputy's instruction)** — one
  foreign issue ANYWHERE in the company whose description carries the
  marker plus an unbalanced `{` raises the typed `RECORD_INVALID` out
  of `count_asks` (hourly-ceiling check dead) and out of `read_ask`
  for any ask whose scan reaches the bad row — a whole-lane typed DoS
  lever from a foreign-writable surface.  Fail-closed is the DESIGN
  (an H4/M5 law: corruption is never read as absence, never a short
  count), so a fix would have to distinguish "corrupt foreign row"
  from "corrupt own row" — i.e. skip-rows-on-scan semantics the
  contract does not define.  Availability-only, no data loss, typed at
  both reviewed heads.  A future round could add a per-scan quarantine
  (skip a corrupt row in RESOLUTION scans while count_asks still fails
  closed) if the contract lane defines it; not done here.
- **F4 (LOW, note)** — editing the stored envelope's `principal` field
  makes the ask invisible to `count_asks` (its hourly-ceiling check
  misses it) while `read_ask` still resolves it by ask id — a
  ceiling-evasion lever on a foreign-writable surface.  Same
  storage-model family as F2 (the description is the record); a
  server-side ask_id uniqueness/ownership row is the real fix (the D4
  lane item).
- **F5 (LOW, note)** — `append_ask_event` canonicalises the
  CALLER-SUPPLIED core unguarded: a bridge-side event carrying a
  non-finite float raises a raw `ValueError`.  The caller is trusted
  bridge code (not a forged path — every FOREIGN value is
  parse-hardened since round 3), so this is a defensive-hardening
  nicety, not a reachable defect from Paperclip data.



`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest
-p no:cacheprovider <file>` — at the final-round head, all eight GBL
files one at a time:

- `tests/test_gbl_paperclip_client.py` — 136/136 (121 at round 2, +11 in
  round 3, +2 F1 and +2 F3 in the final round; the fake HTTP server
  binds 127.0.0.1 on an EPHEMERAL port, and the real GblBridge is driven
  over the client for the EFFECT_UNKNOWN tests)
- `tests/test_gbl_ask_cli.py` — 44/44 (real GBL-2 `GblBridge`+
  `BridgeServer` on a temp socket, `allowed_peer_uids=(uid,)`, a real
  `PaperclipAskClient` behind it for the door tests)
- `tests/common/gbl_contract_test.py` — 79/79
- `tests/test_gbl_bridge_service.py` — 64/64
- `tests/test_gbl_nudge.py` — 12/12
- `tests/test_gbl_message_send.py` — 27/27
- `tests/test_gbl_mcp_server.py` — 28/28
- `tests/test_gbl_admission.py` — 23/23

No real Paperclip instance is contacted by any test. (Round 1 for the
record: CLI 20/20, client 33/33, contract 72/72, bridge 35/35, nudge
10/10, message_send 19/19.)

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

## Micro round (GBL-5 review r2, 2026-11-12)

The independent r2 review of `eb5a5754a` → `cf93a832f` (HIGH 0, MED 3, LOW 7,
ruling 19 met) left three MEDs on the delivery layer; its 7 LOWs wait on the
later list (`~/.mastermind/mmos_evidence/gbl-20261111/LATER.md`). Each fix has
a test that fails first at `cf93a832f` (red output in
`~/.mastermind/mmos_evidence/gbl-20261111/gbl5/micro/`).

- **MED-1: a marking only the store may set.** `_verified_event` stripped
  only `tag`/`trusted`, so a foreign comment carrying
  `"defect": "EVENT_SEQ_DUPLICATE"` survived the read and counted as a real
  POST for the re-nudge budget, cooldown and settlement: three forged
  comments drove an ask the writer does not own into
  `RENUDGE_BUDGET_EXHAUSTED`. Every key only the store may set is now one
  named constant, `STORE_ONLY_EVENT_KEYS` (`tag`, `trusted`, `defect`,
  `comment_id`, `comment_author`, `comment_created_at`, `comment_order`),
  removed from the parsed body BEFORE verification; the demotion stamp is
  re-attached only by the chain law, after the tag verified. `seq` stays: it
  is signed v1 content and is consulted only on a tag-verified event.
- **MED-2: a counted marker needs a usable timestamp.** A counted marker
  with no `at` (or an unparseable one) raised a raw `KeyError`/`ValueError`
  out of `maybe_renudge` — an untyped `INTERNAL_ERROR` at the socket door,
  repeated forever. It now refuses with the typed
  `NUDGE_MARKER_TIMESTAMP_INVALID` and sends nothing; `reconcile_nudge`
  validates the attempt's timestamp the same way before any transport call,
  so it cannot send a wake whose settlement row is unwritable.
- **MED-3: the delivery decision is under the host lock.** `fetch_result`
  read, replayed and appended `CONSUMED` outside the append lock, so two
  callers could each see `ANSWERED` and each be handed the answer as
  `ANSWER_UNCONSUMED`. The client now exposes `result_delivery_lock()` — the
  same flock on `append.lock`, same order (threading lock, then flock) and
  re-entrant with `append_ask_event`, which reuses the thread's open handle
  instead of deadlocking on a second flock — and `fetch_result` re-reads its
  record inside it. The bridge uses it when the store offers it
  (`GblResultDeliveryLockStore`) and keeps the plain read for test doubles.

Install is unchanged: no new state file, no new configuration, no restart
step beyond the ordinary bridge restart for the new code. Suites at this
round: admission 23, ask_cli 44, bridge 72, mcp_server 28, message_send 27,
nudge 12, paperclip_client 146 — 352 passed (348 before the four new tests).

### Item 4 (principal's ruling, 10:55Z): the delivery record cannot lag

Item 3 serialised the decision but kept its SOURCE: `_require_ask` reads the
issue's comment listing, and this store's own proof 1 shows a listing can lag
a write that has already landed (`comment_visibility_lag`, the reason the mint
ledger exists). Caller A marks CONSUMED and is served `ANSWER_UNCONSUMED`;
caller B takes the lock, re-reads, sees a stale `ANSWERED`, finds no trusted
mark to dedupe against, mints the next number and posts a SECOND `CONSUMED` —
and is served the answer again. `test_two_callers_share_one_delivery` passed
only because the fake's lag was 0.

Class rule: a delivery decision is never taken from a read that can be behind
the host's own writes. The host already has a record that cannot lag: the
append ledger file, under the same flock.

- The delivery is recorded in the ledger — `append.lock` in the HMAC key's
  directory, one JSON line `{"ask_id": …, "answer_id": …, "delivered": true}`
  — under `result_delivery_lock`, BEFORE the `CONSUMED` post, and
  `fetch_result` consults it FIRST (`delivered_answer_id` /
  `record_delivery`, both re-entrant with `append_ask_event`). A record with
  no integer `seq` is ignored by `_ledger_floor`, so the mint floor is
  unaffected.
- Recorded ⇒ `CONSUMED`, whatever the listing shows; a lagging listing can
  no longer hand the answer over twice.
- If the record lands and the `CONSUMED` post then fails, the answer stays
  withheld and the caller gets the typed `DELIVERY_MARK_POST_FAILED`; every
  retry is `CONSUMED`, never a second `ANSWER_UNCONSUMED`. (The minted number
  of the failed post is skipped, never reused.)
- The `_delivery_lock` no-op fallback now FAILS CLOSED: a store with no host
  lock refuses `DELIVERY_LOCK_UNAVAILABLE` typed unless it is an explicitly
  marked test double (`GBL_TEST_DOUBLE = True` on the three fakes). A store
  offering the lock but only part of the record capability refuses
  `DELIVERY_CAPABILITY_INCOMPLETE` rather than deciding from the listing
  again.

Tests (red at `6e7c5e58a`, output in
`~/.mastermind/mmos_evidence/gbl-20261111/gbl5/micro/item4-red.txt`):
`TestDeliveryLedger::test_a_lagging_listing_cannot_deliver_twice` (two client
objects, the first caller's mark hidden by `comment_visibility_lag`, exactly
one `ANSWER_UNCONSUMED`, exactly one trusted `CONSUMED` after the reveal) and
`::test_a_failed_mark_post_withholds_the_answer_and_reports_typed`;
`TestFetchResult::test_a_store_without_a_delivery_lock_refuses_typed`.
Suites: admission 23, ask_cli 44, bridge 73, mcp_server 28, message_send 27,
nudge 12, paperclip_client 148 — 355 passed.
