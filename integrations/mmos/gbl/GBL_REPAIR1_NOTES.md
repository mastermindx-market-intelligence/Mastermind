# GBL repair round 1 — contract note for GBL-4 (Paperclip store)

- Repair heads: failing tests `519a1e89c`, fixes `f8c98a65d` on `t3/mmos-v4-gbl`
  (reviewed base `5063b46cb`, panel A + panel B rows H1/H3/M1/M2).
- Written: 2026-11-11 (GBL lane repair round 1). Everything here is the
  GblAskStore contract GBL-4's Paperclip client must implement in its own
  round. `integrations/gbl/paperclip_client.py` was NOT touched.

## 1. The store protocol (exact)

```python
class GblAskStore(Protocol):
    def create_ask(self, ask: Mapping[str, Any]) -> Mapping[str, Any] | None: ...
    def read_ask(self, ask_id: str) -> Mapping[str, Any] | None: ...
    def append_ask_event(self, ask_id: str, event: Mapping[str, Any]) -> None: ...
    def count_asks(self, principal: str, since_iso: str) -> int: ...
```

### 1.1 `create_ask` is CREATE-IF-ABSENT (panel A M6)

- Returns `None` when it created the record.
- Returns the EXISTING record (a deep copy is safest) when the deterministic
  ask id is already present — it does NOT raise, does NOT create a second
  issue, does NOT mutate the existing one.
- The bridge calls it only after its own `read_ask` returned `None`, and
  classifies whatever comes back (`IDEMPOTENT` / `CONFLICT`). Two racing
  submits of the same key can therefore never produce two records, even when
  the bridge's read raced (verified by the LaggingStore test).
- `GblCreateEffectUnknown` keeps its meaning: the create began, the effect is
  unknown — the bridge reconciles by `read_ask` of the deterministic id and
  never issues a second create.

### 1.2 Event records: `seq` + `trusted` (panel B M1/M2)

Every event the STORE appends is stamped by the store itself:

```json
{"type": "answer", "answer_id": "gbm-…", "idempotency_key": "…",
 "text": "…", "seq": 3, "trusted": true}
```

- `seq`: a per-record STRICTLY INCREASING integer, assigned by the store at
  append time. Derive it from `comment_order` (your paginated, offset-honoured
  field) or an internal counter — either is fine; the law is monotonicity per
  ask record.
- `trusted`: `true` on the store's own appends; `false` on any event-shaped
  comment the store did not append itself.
- Bridge law (already shipped): events with `trusted: false` are ignored
  entirely — they never advance state, never answer, never burn nudge budget.
  `seq` monotonicity is validated across trusted events; an equal or
  missing/non-integer stamp raises typed `EVENT_SEQ_INVALID` (visible, never a
  silent reorder that bricks the record as ASK_STATE_REGRESSION).
- Events with NO `trusted` key are legacy pre-contract bridge-local/test
  records and stay authoritative (ordered by list position). No production
  Paperclip events predate this note, so once you ship, every foreign comment
  MUST be surfaced `trusted: false`.

## 2. M1 trust basis — RULING (deputy FACT, gbl4-devproof 21:5x)

Paperclip's plain comments route returns `authorAgentId: null` and
`authorType: "user"`. **The author field alone cannot separate the bridge's
own events from a forged comment** — `comment_author`, `comment_id`,
`comment_created_at` and `comment_order` are display/ordering metadata only,
NEVER a trust basis.

Chosen basis: **(b) a host-held HMAC tag on every appended event.** Paperclip
comments carry the record; only tag-valid events are authoritative. Everything
else is display.

GBL-4 requirements, exactly:

1. The store adapter holds one host-local key: 32 random bytes, generated on
   first use, stored `0600` under the bridge's state root on the same host as
   the bridge process. It never leaves the host, never crosses the wire, is
   never written to Paperclip, never logged.
2. Tag shape: `"v1:" + HMAC-SHA256(key, message).hexdigest()` where `message`
   is `ask_id + "\n" + str(seq) + "\n" + canonical_json(event_without_tag)`
   (canonical JSON = sorted keys, compact separators, UTF-8). The tag binds
   the event to ITS ask record: replaying a tagged comment onto another ask
   fails verification.
3. On append: the store writes the event JSON with its tag into the comment
   (the existing marker line + JSON document shape, plus `"tag"`).
4. On read: any event-shaped comment whose tag is absent, malformed, wrong
   version, bound to another ask, or failing HMAC verification is surfaced
   with `trusted: false`. The bridge ignores it.
5. Rotation: `v1` pins a single key. Rotating invalidates old tags unless
   events are re-tagged — that is a conscious future migration, not part of
   this round.
6. If any part of this cannot be built on the current Paperclip surface,
   REPORT it absent in your round notes; do not silently fall back to
   author-field trust.

Rejected: (a) an agent-attributed comment surface. The dev proof shows the
plain route is user-attributed, so (a) makes trust conditional on an
unverified Paperclip capability whose failure mode is "trust absent". (b)
keeps "the Paperclip issue IS the ask record" literally true (the full record
stays in Paperclip, readable by any fresh bridge instance holding the key),
adds no new provider capability, and forging requires the host-held key.

## 3. Other contract changes GBL-4 must know

- **Answer write law (H2/panel B H1):** `post_answer` appends exactly ONE
  event (`type: "answer"`); the ANSWERED state is inferred by replay from the
  trusted answer event. Old two-append records repair themselves on read;
  do not "fix" records on your side.
- **New wire op `reconcile`** (`{ask_id}` → `reconcile_nudge`): settles the
  last nudge attempt by observation; it never sends. Ops are now
  `{ask, answer, result, question, status, reconcile}`.
- **Wire argument validation:** the bridge door now enforces per-op key sets.
  `answer` is exactly the contract's `ANSWER_ARGUMENT_KEYS`
  `{"principal","ask_id","answer","idempotency_key"}`; `ask` requires
  `{principal,kind,target,title,body,idempotency_key}` and optionally accepts
  `{correlation,asker}`; `question`/`result`/`status` are `{principal,ask_id}`;
  `reconcile` is `{ask_id}`.
- **`ask_status`** now reports `EXPIRED` and carries `expires_at` (L4).
- **Nudge law (M7/M8):** a `nudge_attempt` event is persisted BEFORE the
  send; cooldown counts `nudge` + `nudge_attempt` markers; budget counts
  delivered `nudge` events only. Receipt outcomes: ACCEPTED/DELIVERED →
  RENUDGED; TARGET_UNAVAILABLE/FAILED → `NUDGE_NOT_DELIVERED` (no budget);
  effect-unknown → `NUDGE_EFFECT_UNKNOWN` (settle via `reconcile`).
- **One answer cap (M1):** `MAX_ANSWER_CHARS = BODY_MAX_CHARS = 4096`.
- **team.answer public argument** is `answer` (was `text`); the edge schema
  digest is re-pinned
  (`d29615d2bfff3f12676b144340bdf38269cfae8e4334ed636aff04b5d9c30c4e`).

## 4. Evidence

All suites one file per invocation,
`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider <file>`:

- `tests/common/gbl_contract_test.py` — 79 passed
- `tests/test_gbl_bridge_service.py` — 57 passed
- `tests/test_gbl_nudge.py` — 12 passed
- `tests/test_gbl_message_send.py` — 27 passed
- `tests/test_gbl_mcp_server.py` — 27 passed
- `tests/test_gbl_admission.py` — 23 passed

No server was run against any real port; no request to any real service.

## 5. Not fixed in this round (LOWs, with reasons)

- `GblNudgeSender.send/reconcile` `asyncio.run` wiring — binds the sender to
  a sync caller; real event-loop integration is a wiring decision for the
  live deployment, not reachable from any live caller today.
- Edge `asks_last_hour` default is a no-op counter — the bridge re-enforces
  the ceiling; wiring a real counter is a deployment concern.
- Serve connections remain strictly serialized (one at a time) — H3 removed
  the death-on-error, and per-(env,thread) locking covers the message path;
  concurrency inside the bridge door is a deliberate future decision.
- A delivered-nudge append lost after the POST still loses cooldown/budget
  record (same non-atomicity family as H2) — mitigated: the attempt is
  persisted BEFORE the send, and `reconcile` settles it; fully closing it
  needs the same store-side write law as events (GBL-4's round).
- Panel B L1 (socket-path symlink redirect requires parent-dir write —
  admission still uid-gated) and L2 (stale socket after SIGKILL: `close()`
  and loop exit now unlink; the residual hard-kill case wants a pid/liveness
  check design) — left to the deployment round.
