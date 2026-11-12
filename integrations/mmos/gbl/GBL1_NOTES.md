# GBL-1 lane note — the contract module

Branch `t3/mmos-v4-gbl`, from trunk `c266559a5`. Files owned and written:
`common/gbl_contract.py`, `tests/common/gbl_contract_test.py`, this note.
Nothing else touched; nothing in `common/agent_dialogue_*`, `control_plane/*`,
or any other lane's files edited.

## What shipped

`common/gbl_contract.py` — pure schema + rules, no transport/store/socket:

- **Wake** `mastermind.gbl.wake.v1`: exactly `{schema, ask_id, state}`,
  closed-key (any other key → `INVALID_WAKE_FIELDS`). States admitted:
  `QUESTION_AVAILABLE`, `ANSWERED` only — a nudge never claims
  OPEN/CONSUMED/EXPIRED (no run should start for those).
- **Ask** `mastermind.gbl.ask.v1`: closed keys, optional `asker`
  (`{side:"t3_thread", environment_id, thread_id, session_label}` — data on
  the issue, never an agent, ADDENDUM §3). `correlation` embeds the
  TeamLinkMessage.v1 WO-17 keys, validated over the imported
  `CORRELATION_KEYS`/`REQUEST_DIGEST_RE`/`REF_MAX_CHARS` grammar.
- **team.message** `mastermind.gbl.message.v1`: exactly
  `{schema, message_id, principal, environment_id, thread_ref,
  idempotency_key, body}` — the allowlist fields ride the envelope.
  `DEFAULT_ALLOWLIST = ()`: empty allowlist ⇒ `ALLOWLIST_EMPTY` universal
  typed refusal; listed env + unlisted thread ⇒ `THREAD_NOT_ALLOWED`.
- **Quoted-data wrapper**: verbatim ADDENDUM §4b header, `"> "`-prefixed
  body lines; a forged first-line marker or wrapper header can never become
  the first line of the delivered message.
- **States**: `OPEN → QUESTION_AVAILABLE → ANSWERED → CONSUMED` monotonic
  (`ASK_STATE_REGRESSION` on drift, terminals absorb), `EXPIRED` reachable
  from any live state; work on an expired record → `ASK_EXPIRED`; surfaced
  label `ANSWER_UNCONSUMED` for answered-but-unfetched.
- **Budgets**: 20 asks/h/principal (`admit_ask_rate` → `RATE_LIMITED`),
  3 re-nudges/ask, 1 routine/account, 16k ask-body/answer, 32 KiB frames.
  `RESPONSE_BUDGET` IS the imported consultation `RESPONSE_BUDGET_MAXIMA`
  (B1 law adopted, not re-declared).
- **Mints**: `gb-<32hex>` over (principal, target, idempotency_key);
  `gbm-<32hex>` over (principal, environment, thread, key, body). Same
  inputs ⇒ same id; same key + changed content ⇒ `CONFLICT`
  (`classify_ask_duplicate`; `DIFFERENT_OPERATION_KEY` typed refusal when
  the key itself differs). Semantic fingerprint ignores `state`/`expires_at`
  so a stored record that advanced, or a TTL-recomputed expiry, is still
  `IDEMPOTENT`.

## Reuse (imports=<modules reused>)

`control_plane.teamlink_contracts` — `mint_message_id` (the hash law under
both GBL mints; re-prefixed, never rewritten), `is_expired` and
`followup_requires_new_key` (re-exported unchanged — the tests pin function
identity), plus `CORRELATION_KEYS`, `OPERATION_KEY_RE`, `REQUEST_DIGEST_RE`,
`ISO_PATTERN`, `BODY_MAX_CHARS` (4096 = the team.message body cap),
`PRINCIPAL_ID_MAX`, `THREAD_REF_MAX`, `REF_MAX_CHARS`.
`common.agent_dialogue_consultation_contract` —
`consultation_semantic_fingerprint` (canonical-JSON + SHA-256 duplicate law),
`DuplicateClassification`, `RESPONSE_BUDGET_MAXIMA`.
`common.company_consultation_host_contract` — `encode_json_frame`/
`decode_json_frame` (the frame codec, GBL cap 32 KiB).

Precedent note: `common/` already imports `control_plane` (e.g.
`common/executive_workspace_contract.py`), so the teamlink import does not
break the layering convention.

## Latitude the docs left open (lane decisions, flagged)

- `DEFAULT_ASK_TTL_SECONDS = 86400` — no TTL is doc-pinned; a day to answer,
  then honest `EXPIRED`. GBL-2 may pass `ttl_seconds`.
- `TITLE_MAX_CHARS = 512` — not doc-pinned.
- `WAKE_STATES = {QUESTION_AVAILABLE, ANSWERED}` — derived from Flow 1 step 8
  and Flow 2 step 2; open to widening with evidence if a live flow needs it.
- The send marker `[gb-<messageId>]` is left to GBL-2's `message_send.py`;
  GBL-1 mints the id it wraps.

## Tests

`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p
no:cacheprovider tests/common/gbl_contract_test.py` → **72 passed** (first
commit `8305cd8f5` = the failing tests; module commit follows).

Imported modules' suites, one file at a time, all pass at this head:
`tests/test_teamlink_contracts.py` (64), `tests/test_agent_dialogue_consultation_contract.py`
(46), `tests/test_company_consultation_host.py` (12).

## For GBL-2 (the only consumer so far)

Consume `build_ask`/`validate_ask`, `build_wake` (nudge payload),
`admit_ask_rate` + `MAX_RENUDGES_PER_ASK`, `check_thread_allowlist`,
`wrap_message_body`, `advance_ask_state`/`surface_ask_state`,
`classify_ask_duplicate`, `ask_followup_requires_new_key`,
`encode_gbl_frame`/`decode_gbl_frame`. Do not restate the maxima or the
wrapper header locally.
