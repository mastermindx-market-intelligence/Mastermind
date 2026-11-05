# H1 — the deterministic one-cockpit receipt validator

**Package:** `integrations/business_sol_canary/` (`__init__.py`, `evidence.py`)
**Tests:** `tests/test_business_sol_canary_evidence.py`,
`tests/test_business_sol_canary_evidence_mutation.py`
**Program:** Rung 4 of the Chairman one-cockpit canary
(`business-sol-one-cockpit-h1-receipt-validator-20260902-fable-001`)

## What H1 is, and what it is not

H1 is a **pure, deterministic evidence validator**. Given a packet claiming
to satisfy the frozen contract below and a caller-supplied "evaluated at"
instant, it returns exactly one verdict — `PASS`, `FAIL`, `UNKNOWN`, or
`REFUSED` — plus the complete, sorted set of issues that produced that
verdict.

H1 performs **no app, account, workspace, plugin, OAuth, credential,
Executive, RuntimeBinding, Agent-OS, Slack, Linear, or deployment action of
any kind.** It does not import an MCP SDK. It never:

- reads the process clock (no `datetime.now()`, no `time.time()`);
- reads the environment or discovers the filesystem;
- makes a network call;
- uses randomness or any other hidden state.

Every notion of "now" comes from the caller's `evaluated_at` argument. This
is enforced, not just documented — `test_business_sol_canary_evidence.py`
walks the module's own AST and fails the suite if a forbidden import or
call is ever introduced.

**A `PASS` verdict from H1 grants no Executive, Business, OAuth,
deployment, merge, or RuntimeBinding authority of any kind.** The output
always carries `production_acceptance_granted: false`. `PASS` means only
that the supplied packet is internally consistent with, and satisfies,
the frozen contract below — nothing more. A retrieved receipt's own text
never grants authority; H1 evaluates the shape and content of the packet
it is handed, and nothing else.

H1 exists specifically to stop these from being mistaken for the complete,
reversible one-cockpit Business canary result: a green CI run, a plugin
import, an app connection, an OAuth login, a single (non-post-expiry)
Steward read, a queued fixture Job, or a prose claim of completion.

## Authority precedence (frozen at commission time)

1. protected Skillpack/source law at current master
2. the P5 one-cockpit packet + its completion ruler
3. protected P1 #302 / `12c2cb8993f78e81c6cb9e9a75a9829f9b194dab`
   (`evidence.EXPECTED_P1_COMMIT`)
4. protected A1 #310 / `524b6dc8071d6ea0b484819630e9de846e1df93e`
   (`evidence.EXPECTED_A1_COMMIT` — documented anchor; not itself a
   required input field of the closed contract below)
5. Executive MCP #64 canary receipt as **sample evidence only**, never
   live-production proof

## Calling H1

```python
from integrations.business_sol_canary import validate_receipt

result = validate_receipt(packet, evaluated_at="2026-09-02T00:05:00Z")
```

- `packet`: the evidence document (a `dict`/mapping). H1 never raises for
  adversarial *content* — malformed or hostile content is reported as
  issues in the output, never an exception.
- `evaluated_at`: a caller-supplied, strict UTC ISO-8601 instant string
  (e.g. produced from the caller's own trusted clock at receipt-review
  time). This is the only source of "now" H1 ever uses. A malformed
  `evaluated_at` is a caller/integration bug, not evidence, and raises
  `TypeError`/`ValueError` rather than being silently absorbed.

## Verdict domain and precedence

Exactly one of `PASS`, `FAIL`, `UNKNOWN`, `REFUSED`.

The verdict is always the **highest-severity issue present**, in the fixed
order `REFUSED > FAIL > UNKNOWN`, with `PASS` reserved for zero issues.
This means one `REFUSED`-level finding (e.g. an embedded secret) always
wins over any number of `FAIL`/`UNKNOWN` findings elsewhere in the same
packet — see `test_verdict_precedence_refused_over_fail` and
`test_kill_issue_precedence_downgrade` for the enforced/kill-tested proof.

- **`REFUSED`** — H1 will not ingest this packet as evidence at all: it
  carries a secret/private-locator/model-authored-authority-claim pattern,
  is not a mapping, or declares an `evidence_source_provenance` other than
  `live_receipt` (CI-green, a merge event, Slack delivery, a queued
  fixture Job, and a prose claim are all refused substitutes for the live
  receipt).
- **`FAIL`** — the packet was evaluable and contradicts a required
  contract rule (duplicated cockpits, wrong P1 commit, inventory drift,
  wrong Executive admission shape, timestamp violations, etc).
- **`UNKNOWN`** — a required section or field is entirely absent, so H1
  cannot judge that dimension. Absence is never inferred as success.
- **`PASS`** — zero issues found across every check.

## Input contract: `mastermind.business_sol_one_cockpit_receipt.v1`

A closed contract — unrecognized fields at any nesting level are rejected
(`UNRECOGNIZED_FIELD`). Top level:

| Field | Purpose |
|---|---|
| `schema_id` | must equal `mastermind.business_sol_one_cockpit_receipt.v1` |
| `receipt_id`, `generation_id` | opaque identity strings |
| `observed_at` | strict UTC instant the receipt was assembled |
| `is_correction`, `correction` | append-only correction lineage (see below) |
| `source_refs` | array of `{ref_id, owner}`; `owner` is one of `s1`, `executive_app`, `control_room`, `h1`, `steward`, `secretary`, `business_app` |
| `cockpit_selection` | `{selected_ref, control_refs: [two, distinct], selection_basis: "opaque"}` |
| `personal_cockpit` | `{separately_selectable: true, merged_into_business: false}` |
| `business_membership_transition` | initial → transitioned → reverted → readback states + their timestamps, in order, reverting to the initial state |
| `protected_baseline` | `{p1_commit, package_inventory, package_inventory_digest, expected_package_inventory, expected_package_inventory_digest}` |
| `generation_identities` | `{s1, executive_app, control_room, h1}`, each `{expected_id, observed_id, source_ref_id}` |
| `steward_census` | `{tool_names: [exactly six, distinct], initial_read, post_expiry_read}` |
| `control_room_evidence` | `{desktop, mobile}`, each with all six states: `normal`, `stale`, `degraded`, `partial`, `effect_unknown`, `no_action` |
| `executive_admission` | the harmless admission receipt (QUEUED, `dispatched=false`, `attempts=0`, `attempt_limit=1`, `authorities={READ, RESEARCH}`, no write paths/validation commands, no side effects) + status readback |
| `rollback` | `{performed: true, post_rollback_*_state, readback_confirmed: true}` |
| `evidence_source_provenance` | must be `live_receipt` |

**Sets vs. sequences:** `control_refs`, `source_refs`, `tool_names`,
`authorities`, `write_paths`, `validation_commands`, `worker_effects`, and
both package-inventory arrays are treated as **sets** — their element
order carries no meaning. Validation, the verdict, and the canonical
digest are all identical under any permutation of these arrays (or of any
object's key order); a genuine duplicate inside a set-like array is still
caught (`test_a_real_duplicate_survives_set_normalization`).

**Refused (never ingested) regardless of anything else:** raw bearer/
refresh/client secrets, tokens, tunnel secrets, email addresses, provider/
native session IDs, account-number-shaped strings, local filesystem paths,
browser profile references, Slack channel/user/team coordinates,
model-authored authority claims, and raw error/traceback text. The
offending value is never echoed back — only its path and a generic
category code are reported.

### Corrections

A correction packet (`is_correction: true`) must carry
`correction.supersedes_digest`, a sha256 hex digest naming the **exact**
prior packet it supersedes. H1 never mutates historical evidence and a
correction is validated **from scratch** against the full contract — it
cannot borrow fields from, or inherit a verdict from, the packet it
supersedes (`test_correction_never_borrows_fields_from_a_superseded_packet`).

## Output contract: `mastermind.business_sol_h1_validation.v1`

```json
{
  "schema_id": "mastermind.business_sol_h1_validation.v1",
  "verdict": "PASS | FAIL | UNKNOWN | REFUSED",
  "issues": [{"severity": "...", "code": "...", "path": "...", "detail": "..."}],
  "canonical_input_digest": "<sha256 hex>",
  "validated_identities": {"receipt_id": "...", "generation_id": "...", "generation_identities": {...}, "source_ref_ids": [...]},
  "capability_state_projection": {"executive_dispatch": "not_dispatched", "worker_effects": "absent", "...": "..."},
  "production_acceptance_granted": false
}
```

`issues` is always completely sorted (by severity, then code, then path),
so two runs over the same packet produce byte-identical output.

`canonical_input_digest` is a sha256 over the packet's canonical JSON form
(`sort_keys=True`, compact separators, `ensure_ascii=False`, no NaN — the
same idiom as `integrations/mastermind_secretary_mcp/schemas.py:canonical_json`;
this package does not import that module and stays dependency-free beyond
the stdlib) after normalizing the set-like arrays listed above, so it is
stable across key/array-order permutation.

## Timestamp law

- Every timestamp must be a strict UTC ISO-8601 instant (a trailing `Z` or
  an explicit `+00:00` offset; any other offset, or an unparsable/
  impossible calendar date, is `TIMESTAMP_MALFORMED`).
- `evidence.MAX_FUTURE_SKEW` (5 minutes): a timestamp claiming to be more
  than this far after `evaluated_at` is `TIMESTAMP_FUTURE`.
- `evidence.MAX_RECEIPT_STALENESS` (24 hours): a receipt whose own
  `observed_at` is older than this relative to `evaluated_at` is
  `TIMESTAMP_STALE`.
- Sub-evidence (Steward reads, Control Room states) may not be timestamped
  after the receipt's own assembly time (`TIMESTAMP_CONTRADICTORY_CLOCK`).
- Ordered event sequences (the membership transition's four steps; the two
  Steward reads) must not go backwards (`TIMESTAMP_ORDER_INVERSION`).

These are constants, not discovered values — H1 never reads a live clock
to decide what "now" or "stale" means; both bounds are compile-time
constants applied to the caller-supplied `evaluated_at`.

**Every timestamp above is a required field — presence is enforced, not
just format.** `_check_timestamp` is fail-closed by construction (no
`allow_missing` escape hatch): a missing top-level `observed_at`, any of
the four `business_membership_transition.*_observed_at` fields, either
Steward read's `observed_at`, or a Control Room state's `observed_at`
always produces `TIMESTAMP_MISSING` (severity `UNKNOWN`), never a silent
`PASS`. This was a confirmed defect fixed 2026-09-02 (independent review
of PR #361): the original version defaulted to permissive and depended on
every call site opting into strictness, so a single missed call site
silently accepted an absent required timestamp as complete evidence. See
`test_every_required_top_level_field_absence_is_not_pass` and
`test_every_required_nested_field_absence_is_not_pass` for the exhaustive
presence sweep across every required field in the contract, not only
timestamps.

## Output never echoes a screened secret

A value that fails the secret/private-locator screen (see above) is
withheld not only from the issue set but from the **entire serialized
output document** — `validated_identities.receipt_id`,
`.generation_id`, `.generation_identities.<component>`, and
`.source_ref_ids` each pass through `_safe_identity`, which re-checks the
same pattern table `_scan_for_secrets` uses and redacts to `None` (or
drops the entry, for `source_ref_ids`) on a match. This is deliberate
defense in depth on top of the `REFUSED` verdict: a caller that only
checks `production_acceptance_granted` or serializes the whole result
(logs, a receipt store, a UI) can never leak the offending substring
through this path. This was a confirmed defect fixed 2026-09-02
(independent review of PR #361) — see
`test_secret_in_receipt_id_is_refused_and_absent_from_serialized_output`
and its two siblings for the enforced invariant.

## Mandatory hostile cases (test coverage index)

Every case below is a distinct, named test in
`test_business_sol_canary_evidence.py` producing a stable issue code:
cockpit duplication (selected-in-controls, controls-duplicated),
account/title/recency-based selection, Personal merge / non-reversibility,
wrong P1 commit, package/plugin inventory drift, an extra
app/tool/plugin, schema mismatch, a single Steward read, a missing
post-expiry refresh read, refresh-secret leakage, missing adverse Control
Room states, UI-only Control Room evidence with no fallback, every
Executive-admission violation (not QUEUED, dispatched, any
attempt/worker effect, wrong authorities, any write path or validation
command, duplicate submission, an omitted changed-payload conflict,
status-readback mismatch), CI/merge/Slack substitution for the live
receipt, missing rollback/readback, stale/future/impossible/contradictory
timestamps and event-order inversions, source-owner mismatch, duplicate
field identity, permutation instability, secret/private-locator/error
leakage, and a correction packet without exact lineage.

## Mutation-kill matrix

`test_business_sol_canary_evidence_mutation.py` disables each enforcement
unit in-memory (via `monkeypatch`) and proves the corresponding hostile
packet would otherwise be mistaken for a clean `PASS` (or lose its
`REFUSED` classification). The required kill set — omitted refresh proof,
dispatched/attempt false-green, cockpit duplication, Personal merge,
inventory drift, stale evidence, issue-precedence downgrade, and secret
screening — is covered, plus three additional kills (rollback readback,
evidence-source provenance, correction lineage). `test_kill_matrix_is_complete`
pins that every required rule has a named test.

**Granularity is stated precisely in the file's own module docstring, not
overstated.** Most kills patch a whole *section validator*
(e.g. `_validate_cockpit_selection`) to a no-op, which proves the section
matters and, via each test's specific assertion, that the named rule
inside it is what disappears — it does not by itself distinguish that
rule from any sibling rule folded into the same section. Four of the
highest-risk Executive sub-rules are split into their own standalone
functions specifically so they can be proven independently load-bearing:
`_check_executive_authorities` (the `{READ, RESEARCH}` cardinality rule),
`_check_executive_dispatched`, `_check_executive_attempts`, and
`_check_executive_latest_attempt` (absent-iff-`attempts==0`), each with
its own rule-granular kill test.

## The Executive MCP #64 sample

`test_sanitized_exec_mcp_64_sample_does_not_pass_on_its_own` builds a
synthetic, sanitized packet in the *shape* of the #64 canary receipt —
one Steward read only, one Control Room surface/state, no rollback — and
asserts it does **not** yield `PASS`. This is deliberate: #64 is
authority-precedence tier 5, sample evidence only, and this test is the
standing proof that H1 cannot be satisfied by that sample alone.
