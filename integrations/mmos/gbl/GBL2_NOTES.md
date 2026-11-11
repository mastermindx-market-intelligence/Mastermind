# GBL-2 lane note — the bridge core

Branch `t3/mmos-v4-gbl`, lane GBL-2 of the Grok Bot link (BUILD_PLAN row
GBL-2; ADDENDUM_1 §1/§3/§4b; ARCHITECTURE §4–§6). Files owned here, as sole
writer:

- `integrations/gbl/bridge_service.py` — `GblBridge` (ask lifecycle over the
  store interface), `BridgeServer` (AF_UNIX, peer-uid admission), the
  admission table, `RENUDGE_COOLDOWN_SECONDS`.
- `integrations/gbl/nudge.py` — `GblNudgeClient` / `GblNudgeSender`: the
  existing wake fabric wrapped, closed-key body only.
- `integrations/gbl/message_send.py` — per-environment `team.message` sender
  over the stock `t3` CLI.
- `integrations/gbl/__init__.py` — package marker only.
- `tests/test_gbl_bridge_service.py` (35), `tests/test_gbl_nudge.py` (10),
  `tests/test_gbl_message_send.py` (19).

`common/gbl_contract.py` was imported and NOT edited; **no contract change is
requested** — GBL-1's surface covered this lane.

## The Paperclip client interface (GBL-4 implements this)

Protocol: `GblAskStore` at `integrations/gbl/bridge_service.py:94`
(`@runtime_checkable`, four methods). The real Paperclip client (GBL-4)
implements exactly this against issues+comments; the reference fake is
`FakeStore` in `tests/test_gbl_bridge_service.py:41`.

```python
def create_ask(self, ask: Mapping[str, Any]) -> None: ...
def read_ask(self, ask_id: str) -> Mapping[str, Any] | None: ...
def append_ask_event(self, ask_id: str, event: Mapping[str, Any]) -> None: ...
def count_asks(self, principal: str, since_iso: str) -> int: ...
```

- **`create_ask(ask)`** — persist the validated ask envelope as ONE
  Paperclip issue (one issue per ask, ADDENDUM §1). The envelope is the
  dict from `gbl_contract.build_ask`; store its fields verbatim (they are
  re-validated as the record). When the create request began but its
  outcome is unknown (transport timeout, lost reply), raise
  `GblCreateEffectUnknown` (import from `bridge_service`) — do NOT retry,
  do NOT guess. The bridge then reconciles by ONE read-back of the
  deterministic ask id (`bridge_service.py:232-240`); it never issues a
  second create. A definite provider refusal may raise any Exception; the
  bridge surfaces it as `INTERNAL_ERROR` (typed failures preferred).
- **`read_ask(ask_id)`** — return the stored record for the ask id, or
  `None` if no such ask exists. Record shape = the ask envelope fields
  PLUS one key `"events"`: a list of event dicts in append order
  (`bridge_service.py:84-90`):
  - `{"type": "answer", "answer_id": str, "idempotency_key": str, "text": str}`
  - `{"type": "state", "state": str}`
  - `{"type": "nudge", "state": "ANSWERED", "at": str}` (`at` = UTC ISO-8601)
  Read-back must find an ask by its deterministic id even when the create
  reply was lost (that is the only create reconciliation path).
- **`append_ask_event(ask_id, event)`** — append ONE Paperclip comment
  carrying the event; idempotent by content (a redelivered append of an
  identical event must not duplicate the comment). Unknown ask id may raise;
  the bridge only appends to records it has just read.
- **`count_asks(principal, since_iso)`** — number of that principal's asks
  created at or after `since_iso` (UTC ISO-8601, `%Y-%m-%dT%H:%M:%SZ`), for
  the hourly rate ceilings. One issue per ask keeps this a simple count.

The bridge owns ALL law on top of this store: admission, mints, duplicate
classification, state chain, expiry, re-nudge budget/cooldown. GBL-4 adds no
law of its own — only this persistence mapping.

The interface heading of this note is `GBL2_NOTES.md:21` ("## The Paperclip
client interface (GBL-4 implements this)"); the protocol itself lives at
`integrations/gbl/bridge_service.py:94`.

## Reuse map (imported as-is, nothing edited)

- `common.gbl_contract` — mints (`mint_ask_id` via `build_ask`,
  `mint_message_id`), `build_ask`/`validate_ask`/`validate_wake`,
  `classify_ask_duplicate`, `advance_ask_state`, `surface_ask_state`,
  `compute_expires_at` (via `is_expired`), `admit_ask_rate`,
  `check_thread_allowlist`, `wrap_message_body`, `DEFAULT_ALLOWLIST`,
  frame codec `encode_gbl_frame`/`decode_gbl_frame`.
- `control_plane.wake_dispatcher` — `WakeNudge`, `WakePreSubmitError`,
  `mint_nudge_id` (nudge identity).
- `control_plane.wake_events` — `canonical_json_bytes` (the exact body bytes
  posted over the webhook).
- `integrations.executive_wake.grok_bot_routine` —
  `GrokBotRoutineWakeDispatcher` (the wrapped dispatcher; its
  `reasoning_surface`/`wake_transport` are reused, not restated).
- `integrations.executive_wake.grok_bot_http` — `GrokRoutineCredential`,
  `grok_routine_target_digest`, `BoundedHttpResult`,
  `POST_TIMEOUT_SECONDS`, `MAX_RESPONSE_BYTES` (same bounded-post
  discipline; only the body differs — GBL posts its own closed-key wake,
  since the Sept `mastermind.grok_bot_wake.v1` payload is a different
  schema).
- `common.company_consultation_host_contract` — `HostFrameError` (frame
  decode errors), on top of the frame codec GBL-1 already wraps.
- Peer-uid mechanism follows the Slack-relay B14 service pattern
  (`integrations/slack_agent_dialogue/service.py`); it is re-expressed
  (the original is private) as `bridge_service._peer_uid`: macOS
  `getpeereid` (ctypes) / Linux `SO_PEERCRED`; `None` ⇒ refuse.

## Surface contract of the socket door

One request per connection, newline-framed GBL frames. Request
`mastermind.gbl.request.v1` = `{schema, op, arguments}` with
`op ∈ {ask, answer, result, question, status}` (mapped to bridge methods);
response `mastermind.gbl.response.v1` = `{schema, ok: true, result}` or
`{schema, ok: false, error: {code, detail}}`. Error codes include
`PEER_NOT_ALLOWED`, `REQUEST_INVALID`, `UNKNOWN_OP`, `INVALID_ARGUMENTS`,
`INTERNAL_ERROR` (type name only — never a traceback or payload), plus
every bridge/contract code (`RATE_LIMITED`, `TARGET_NOT_ALLOWED`,
`KIND_NOT_ALLOWED`, `CONFLICT`, `EFFECT_UNKNOWN`, `ASK_NOT_FOUND`,
`ANSWER_ALREADY_GIVEN`, `RENUDGE_COOLDOWN`, `RENUDGE_BUDGET_EXHAUSTED`,
`EXPIRED`, `INVALID_*` contract codes, …). `open()` binds AND serves on a
daemon thread; `close()` stops it, unlinks the socket, joins the thread.
Admission is the kernel peer uid read BEFORE any payload byte; there is no
TCP listener and no header/token admission, ever.

## Lane-chosen latitudes (not doc-pinned — flag to the deputy if unwanted)

- `RENUDGE_COOLDOWN_SECONDS = 900` (`bridge_service.py:62`) — one re-nudge
  per ask per 15 minutes, bounded by the contract's 3-per-ask budget.
  ARCHITECTURE names the budget; the cooldown number is this lane's pick.
- `BridgeServer.ACCEPT_TICK_SECONDS = 0.25` — accept poll tick so `close()`
  is prompt; connection recv keeps `request_timeout_seconds` (default 15).
- `message_send`: scan `t3 thread show <thread> --json --messages 60`
  (T2's proven scan shape, depth 60); send `t3 thread send <thread> -
  --wait --json`; per-environment `T3CODE_HOME`; send marker `[gb-<id>]` as
  the first stdin line; `SubprocessRunner` timeouts 120s scan / 900s send;
  exit 0/1/2 mapped SENT/SEND_FAILED/SEND_NEEDS_HUMAN; a lost send outcome
  reconciles by ONE marker re-scan (RECONCILED / EFFECT_UNKNOWN), never a
  second send.
- Gate order in `message_send` (tested): EMPTY allowlist refuses everything
  first (`ALLOWLIST_EMPTY`), then environment lookup
  (`ENVIRONMENT_NOT_CONFIGURED`), then the (environment, thread) row
  (`THREAD_NOT_ALLOWED`). Both `DEFAULT_ALLOWLIST` and
  `DEFAULT_ENVIRONMENTS` ship EMPTY.
- nudge body: exactly `canonical_json_bytes(build_wake(ask_id, state))` —
  `{schema, ask_id, state}`; the bearer token rides the Authorization
  header only and never appears in body or logs. Nudge identity:
  `mint_nudge_id(target_digest, (f"{ask_id}:{state}",))` — redelivery of
  the same (ask, state) keeps its identity.

## Test-run evidence (one file at a time)

`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q
-p no:cacheprovider <file>`:

- `tests/test_gbl_bridge_service.py` — 35/35
- `tests/test_gbl_nudge.py` — 10/10
- `tests/test_gbl_message_send.py` — 19/19

Regressions of imported modules: `tests/common/gbl_contract_test.py` 72/72,
`tests/test_grok_bot_routine_http.py` 64/64,
`tests/test_grok_bot_routine_wake_dispatcher.py` 29/29,
`tests/test_teamlink_contracts.py` 64/64,
`tests/test_company_consultation_host.py` 12/12.

Fakes everywhere: Paperclip store, routine URL/bearer/poster, and the `t3`
runner are in-process fakes; no server, no network, no real T3 home.
