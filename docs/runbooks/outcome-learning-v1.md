# Outcome Learning V1 (OL-V1) — runbook

## 1. What OL-V1 is

OL-V1 is one sealed, prospective decision-expectation receipt bound to one reversible
GitHub PR-title canary effect, evaluated deterministically and DESCRIPTIVE_ONLY, feeding
one n=1, non-promoting self-model and one candidate-only Agent OS projection. It is a
vertical *proof of the mechanism*, not a policy and not a claim about memory efficacy in
general.

It exists to demonstrate — for exactly one episode — that:

- a decision can be sealed with its expectations BEFORE any effect is attempted;
- one narrow, reversible, supervised effect can be applied and restored under a hard
  two-call, no-retry bound, with the ambiguous case (`EFFECT_UNKNOWN`) stopping instead
  of guessing or retrying — and drift between preflight and the live effect is refused
  BEFORE any call is issued, not discovered after the fact;
- the evaluation that follows is a pure function of what was actually observed, never of
  what was hoped for — including an honest `"UNOBSERVED"` when nothing was actually
  confirmed, rather than a guessed "nothing changed"; and
- nothing here mutates any standing rule, grants any authority, or promotes any signal —
  the self-model is `sample_size=1`/`promotion=NONE`/`authority=NONE`, and the Agent OS
  projection is candidate-only.

OL-V1 sits under `DEC:OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE` (the sealed
receipt / two-call-canary / DESCRIPTIVE_ONLY architecture this vertical implements) and
the 2026-09-02 receipt-v2 amendment (the `mastermind.decision_expectation_receipt.v2`
shape, the forbidden self-referential keys, and the external, non-self-referential
preflight design this build carries out).

**Scope note — `DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE`:** that decision governs
the *randomized* two-decision canary gate for OL-5B (probabilistic assignment, held-out
comparison, promotion-bearing statistics). OL-V1 is a separate, supervised, deterministic
n=1 episode outside that gate's scope — its `assignment.probability` is always `None`
with `probability_null_reason=DETERMINISTIC_NO_COUNTERFACTUAL_SUPPORT` by design, not an
omission (`assignment.method` names *which lawful A1 path* produced the choice — see
"Compose's gate and the honest frontier" below — it is never a randomized draw). Do not
read this episode as satisfying, or as exempt from having to satisfy, the OL-5B gate —
the two programs are independent.

## 2. The episode sequence

Run every step from the Mastermind checkout, using the injectable transport/runner
seams — real `gh`/`git` calls are made by the default `GhCliTransport`/
`SubprocessRunner` classes only; nothing in `control_plane/outcome_learning_*` performs
I/O. Paths below chain in sequence — `EPISODE=/tmp/olv1-episode` is the SAME directory
across `compose`, `seal`, and `canary`; `OUT=/tmp/olv1-out` holds the externally-sealed
expectation/request/preflight (never inside this checkout); the six research artifacts
land under `research/outcome_learning/` once the episode has a confirmed outcome.

```bash
EPISODE=/tmp/olv1-episode
OUT=/tmp/olv1-out
mkdir -p "$OUT"

# 1. Compose + evaluate the Chairman-cognition source bundle (read-only). --as-of is
#    OPTIONAL — omit it and the CLI computes it AFTER acquisition as the later of "now"
#    and boot_packet.generated_at, so a slow acquisition can never produce a receipt
#    that postdates it (see "Compose's gate" below for the exit-code contract: 0, 4, 5).
python3 scripts/outcome_learning_v1.py compose \
  --mastermind-root /path/to/Mastermind \
  --macro-root "/path/to/Macro Dashboard" \
  --episode-dir "$EPISODE" \
  --operation-key mastermind-outcome-learning-v1-complete-vertical-20260902-sol-001
# stdout includes: as_of_mode=auto(max_observed_at) as_of=<computed> — or
# as_of_mode=explicit as_of=<your value> if you passed --as-of yourself.

# 2. Seal the decision-expectation receipt + canary request. seal RE-RUNS
#    evaluate_bundle over $EPISODE/bundle.json and refuses if the recomputation does
#    not byte-match $EPISODE/composition.json — composition.json is not trusted
#    verbatim (BLOCKER 3). sealed_hash is computed with the field itself absent;
#    assumption_resolutions == [] in the sealed receipt.
python3 scripts/outcome_learning_v1.py seal \
  --composition "$EPISODE/composition.json" \
  --episode-dir "$EPISODE" \
  --parent-head <40-hex current Mastermind HEAD> \
  --recorded-at 2026-09-02T00:05:00Z \
  --operation-key mastermind-outcome-learning-v1-complete-vertical-20260902-sol-001 \
  --out-expectation "$OUT/OLV1_EXPECTATION_2026-09-02.json" \
  --out-request "$OUT/OLV1_CANARY_REQUEST_2026-09-02.json"

# 3. Build the external preflight receipt (refuses to write inside this checkout).
#    --expectation-repo-path / --request-repo-path are REQUIRED — there is no
#    local-uncommitted-file fallback (Sol REQUEST_REPAIR, 2026-09-02: a
#    `git hash-object <local-file>` fingerprint proves only that bytes exist
#    somewhere on disk, never that they are part of --sealed-commit). For each
#    artifact, preflight makes TWO INDEPENDENT git calls — `git rev-parse
#    <sealed-commit>:<repo-path>` to resolve a real committed blob id, then a
#    SEPARATE `git cat-file -p <blob-id>` to read that blob's own bytes — and proves
#    the canonical digest of the committed bytes equals the canonical digest of the
#    supplied artifact file. --mastermind-root is an EXPLICIT cwd for both calls,
#    never an implicit "wherever this shell happens to be". A repo-path is refused
#    outright (before any git call) if it is absolute or contains a ".." segment.
python3 scripts/outcome_learning_v1.py preflight \
  --mastermind-root /path/to/Mastermind \
  --repo mastermindx-market-intelligence/Mastermind \
  --branch sol/outcome-learning-v1-complete-vertical-20260902 \
  --sealed-commit <40-hex sealed commit> \
  --expectation "$OUT/OLV1_EXPECTATION_2026-09-02.json" \
  --request "$OUT/OLV1_CANARY_REQUEST_2026-09-02.json" \
  --expectation-repo-path research/outcome_learning/OLV1_EXPECTATION_2026-09-02.json \
  --request-repo-path research/outcome_learning/OLV1_CANARY_REQUEST_2026-09-02.json \
  --observed-at 2026-09-02T00:10:00Z \
  --out "$OUT/preflight.json"
# The written preflight.json carries seal_provenance="COMMITTED_BLOBS_VERIFIED" — the
# only valid literal; expectation_blob_sha/request_blob_sha are the sealed-commit's
# real blob ids, and expectation_content_sha256/request_content_sha256 are the
# canonical digests of the COMMITTED blob contents (proven equal to the supplied
# files', never merely asserted). Refusals (all before any effect, all specific):
#   - missing --expectation-repo-path / --request-repo-path
#   - repo-path is absolute, or contains a ".." segment (checked before any git call)
#   - the sealed commit does not contain the exact artifact path (unresolvable blob)
#   - the committed blob's canonical content does not match the supplied file
#     (committed-vs-supplied digest mismatch — a forged pairing)

# 4. Apply the two-call canary. There is no --out-journal override (BLOCKER 2): the
#    journal filename is DERIVED as
#    canary_journal.<operation_key>.<expectation_sealed_hash[7:19]>.json inside
#    --episode-dir, and a second invocation with the SAME episode-dir refuses outright
#    — a caller cannot bypass the single-shot guard by naming a different output path
#    within the same episode-dir. (A DIFFERENT --episode-dir is not stopped by the
#    journal check — that is stopped only by the supervised single-operator law: one
#    principal owns one episode end-to-end and never re-runs canary for the same
#    sealed request from a second location.) Before any PATCH, canary re-reads the
#    live PR once and refuses — zero PATCHes issued — if it has drifted from what
#    preflight observed (MAJOR 5).
python3 scripts/outcome_learning_v1.py canary \
  --preflight "$OUT/preflight.json" \
  --request "$OUT/OLV1_CANARY_REQUEST_2026-09-02.json" \
  --recorded-at 2026-09-02T00:11:00Z \
  --episode-dir "$OUT"
# exit 0 -> effect_state APPLIED_AND_RESTORED
# exit 3 -> effect_state EFFECT_UNKNOWN; STOP — never re-run this command
# exit 6 -> effect_state INVALIDATED_BEFORE_EFFECT (pre-effect drift); zero PATCHes sent
JOURNAL="$OUT/canary_journal.mastermind-outcome-learning-v1-complete-vertical-20260902-sol-001.<sealed-hash-slice>.json"

# 5. Assemble + validate the outcome artifact. Restoration is derived from, in priority
#    order: a reconciliation GET's actually-observed title (ground truth when the
#    calls themselves could not be trusted) > the last completed call's own readback
#    (when no reconciliation was needed) > the literal "UNOBSERVED" poststate when
#    genuinely nothing was ever confirmed (BLOCKER 1).
python3 scripts/outcome_learning_v1.py outcome \
  --journal "$JOURNAL" \
  --preflight "$OUT/preflight.json" \
  --expectation "$OUT/OLV1_EXPECTATION_2026-09-02.json" \
  --request "$OUT/OLV1_CANARY_REQUEST_2026-09-02.json" \
  --recorded-at 2026-09-02T00:12:00Z \
  --out research/outcome_learning/OLV1_OUTCOME_2026-09-02.json

# 6. Deterministic evaluation, self-model, projection, and the production proof.
python3 scripts/outcome_learning_v1.py evaluate \
  --expectation research/outcome_learning/OLV1_EXPECTATION_2026-09-02.json \
  --outcome research/outcome_learning/OLV1_OUTCOME_2026-09-02.json \
  --request research/outcome_learning/OLV1_CANARY_REQUEST_2026-09-02.json \
  --recorded-at 2026-09-02T00:13:00Z \
  --out research/outcome_learning/OLV1_EVALUATION_2026-09-02.json

python3 scripts/outcome_learning_v1.py self-model \
  --evaluation research/outcome_learning/OLV1_EVALUATION_2026-09-02.json \
  --expectation research/outcome_learning/OLV1_EXPECTATION_2026-09-02.json \
  --recorded-at 2026-09-02T00:14:00Z \
  --out research/outcome_learning/OLV1_SELF_MODEL_2026-09-02.json

python3 scripts/outcome_learning_v1.py project \
  --evaluation research/outcome_learning/OLV1_EVALUATION_2026-09-02.json \
  --expectation research/outcome_learning/OLV1_EXPECTATION_2026-09-02.json \
  --outcome research/outcome_learning/OLV1_OUTCOME_2026-09-02.json \
  --recorded-at 2026-09-02T00:15:00Z \
  --out research/outcome_learning/OLV1_AGENTOS_PROJECTION_2026-09-02.json
# key_hint is derived from --recorded-at's own date (e.g. OLV1-EPISODE-CONSEQUENCE-2026-09-02)

python3 scripts/outcome_learning_v1.py proof \
  --expectation research/outcome_learning/OLV1_EXPECTATION_2026-09-02.json \
  --request research/outcome_learning/OLV1_CANARY_REQUEST_2026-09-02.json \
  --outcome research/outcome_learning/OLV1_OUTCOME_2026-09-02.json \
  --evaluation research/outcome_learning/OLV1_EVALUATION_2026-09-02.json \
  --self-model research/outcome_learning/OLV1_SELF_MODEL_2026-09-02.json \
  --project research/outcome_learning/OLV1_AGENTOS_PROJECTION_2026-09-02.json \
  --out research/outcome_learning/OLV1_PRODUCTION_PROOF_2026-09-02.md
```

Every JSON write goes through the same law, for EVERY artifact this CLI produces —
including `bundle.json`/`composition.json` (which have no OL-V1 contracts schema of
their own) and the proof markdown: **validate via `control_plane.outcome_learning_contracts`
where a schema applies, then `scan_public_safe_text`, then
`scripts.agent_eval.privacy.assert_public_safe_evidence`, then write** (pretty sorted
JSON with a trailing newline, or the raw markdown text for the proof). `preflight`'s
`--out` and `canary`'s `--episode-dir` additionally refuse any path inside this
checkout — those artifacts are external, non-self-referential receipts by design (§3).

### The `agentos_revision_attestation.source_records_digest` producer (discovery)

`scripts/agentos.py` (in the Macro checkout) already emits
`agentos.source_records_digest.v1`'s value as the top-level `source_records_digest`
field of its `status` subcommand's output — a pure function of the direct-record
markdown paths + bytes (`_source_records_digest` in `scripts/agentos.py`, around the
`SOURCE_RECORDS_DIGEST_SCHEMA` constant). `status --dry-run` prints that JSON and writes
nothing, so `compose`'s default acquisition path calls it read-only:

```bash
python3 scripts/agentos.py status --root "<macro-root>/agentos" --dry-run --now <as-of>
```

`compose --agentos-records-digest <sha256:...>` overrides this acquisition entirely —
use it only when the producer is genuinely unavailable (e.g. a Macro checkout without a
Python environment reachable from the Mastermind session), and record why in the episode
notes when you do.

### Local-path redaction (MAJOR 13, principal review)

Before the boot packet is embedded in `bundle.json` or digested for either
attestation, `compose` redacts `mastermind.root`, `macro.root`, and
`macro.candidates_tried` to the literal `"REDACTED_LOCAL_PATH"`. This changes no
digest: both attestations' `payload_digest` fields are computed over
`strategic_state`/`brief` alone, never over `mastermind`/`macro`, so the redaction is a
privacy cut with zero effect on content identity. `scan_public_safe_text` additionally
rejects `sk-ant-`, `gh[sou]_` token prefixes, any `/Users/<name>/` path fragment, and
UUID4 shapes anywhere in an artifact, on top of the original Slack-ts / `ghp_` /
`github_pat_` / PEM-header / AWS-key patterns.

### Compose's gate and the honest frontier (principal correction, 2026-09-02)

`compose` does **not** require `packet.selection_state == "UNIQUE_ACTIONABLE_FRONTIER"`
or `packet.recommended_option_id == "OPT-OLV1-PR-TITLE-CANARY"`. An earlier draft of
this build forced that shape by equalizing `OPT-OLV1-PORTFOLIO-HOLD`'s costs to the
canary's — reviewed and rejected as dishonest input-shaping. Under
`control_plane.chairman_cognition._dominates` (strict Pareto dominance), an option can
never dominate a *strictly cheaper* option regardless of benefits. `OPT-OLV1-PORTFOLIO-
HOLD` is genuinely near-zero-cost (it does nothing — its only real cost is deferring all
evidence indefinitely, `time_to_evidence=90`, everything else `0`), so an honest HOLD is
**never** dominated by the higher-benefit, higher-cost canary. Both options lawfully
join the actionable frontier, and `selection_state` is lawfully
`MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS` with `recommended_option_id=None` — that is
`control_plane/chairman_cognition.py`'s A1 law working exactly as designed (its own
2026-09-02 amendment anticipates this: A1 "may recommend the canary only if it is
uniquely actionable" — it anticipates a no-recommendation packet, it does not require
one), not a defect to engineer around.

What actually gates the episode is whether the **canary option's own adjudication** is
serviceable. `compose` looks up `OPT-OLV1-PR-TITLE-CANARY`'s entry in
`packet.adjudications` and keys its exit code on that entry's `disposition`/`reason`
alone — never on the aggregate `selection_state`. A raised
`ChairmanCognitionSourceError`/`ChairmanCognitionError` — a COMPOSITION defect (a
malformed bundle, an unbindable envelope, a stale `--as-of` that slipped past the
up-front check) — is a SEPARATE case from a successfully-composed packet whose canary
option is refused; the two are never rendered through the same message template
(addendum B, 2026-09-02):

| Case | Exit | Output |
|---|---|---|
| `evaluate_bundle` raised before producing a packet | `5` | `BLOCKER COMPOSITION_INVALID <exception message>` |
| canary `disposition == "ELIGIBLE_WITHIN_DELEGATION"` | `0` | `COMPOSE_OK canary_disposition=ELIGIBLE_WITHIN_DELEGATION selection_state=<verbatim> recommended_option_id=<verbatim-or-None>` |
| canary `disposition == "REFUSED"` and `reason == "SOURCE_NOT_CURRENT"` | `4` | `BLOCKER OWNER_SOURCE_NOT_CURRENT <first non-CURRENT load-bearing source_ref>=<state>`, taken from the packet's own `source_summary` |
| canary disposition/reason is anything else | `5` | `BLOCKER CANARY_NOT_ELIGIBLE <disposition>/<reason>` |

Exit 4 is reserved STRICTLY for the third row — a real, successfully-composed packet
with a real `ref=state` pair. `bundle.json` and `composition.json` are written to
`--episode-dir` verbatim in every row except the first (there is no packet to write
when composition itself failed) — the full A1 packet is always on disk for audit
whenever one exists. A human (the principal, in practice) makes the final selection
among an incomparable frontier by choosing to `seal` the canary option; `compose` never
manufactures a false uniqueness to avoid that choice.

`seal` records which of the two lawful paths produced the sealed episode's assignment,
truthfully, from the packet:

- `assignment.method == "deterministic_a1_unique_actionable_frontier"` when
  `packet.recommended_option_id` already equals the chosen option — A1 alone
  determined the choice.
- `assignment.method == "principal_selection_from_a1_incomparable_frontier"` when
  `packet.selection_state == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"` and the chosen
  option's own adjudication is `ELIGIBLE_WITHIN_DELEGATION` — a human selected among an
  A1-validated but incomparable set.

`seal` refuses outright (naming the disposition and reason) if the chosen option's
adjudication is `REFUSED` or `CHAIRMAN_REQUIRED` — there is no lawful assignment method
for sealing a decision A1 has not actually cleared. Before any of that, `seal` also
RE-RUNS `evaluate_bundle` over `bundle.json` and refuses unless the recomputation is
byte-identical to `composition.json` (BLOCKER 3, §3) — `composition.json` sitting on
disk between `compose` and `seal` is never trusted verbatim.

## 3. The laws

- **Seal before effect.** `mastermind.decision_expectation_receipt.v2` is sealed
  (`sealed_hash` computed over every other field, that field itself absent) before any
  canary call is made. `assumption_resolutions` is `[]` in the sealed receipt — resolving
  assumptions is an evaluation-time act, never a retroactive edit to the sealed record.
- **Committed-seal-before-effect (Sol REQUEST_REPAIR, 2026-09-02).** `head_equals_sealed_commit
  = True` alone never proved the sealed artifacts were the exact bytes committed at
  `sealed_commit_sha` — a `git hash-object` fingerprint of a local, uncommitted file
  emitted the same closed preflight shape. `preflight` now requires
  `--expectation-repo-path`/`--request-repo-path` (no local fallback exists) and,
  for each artifact, makes two INDEPENDENT git calls — `git rev-parse
  <sealed_commit>:<repo-path>` for the blob id, then a separate `git cat-file -p` for
  the blob's own bytes — and proves the committed content's canonical digest equals
  the supplied file's. The preflight doc carries the closed field `seal_provenance`,
  whose only valid literal is `"COMMITTED_BLOBS_VERIFIED"`; `validate_preflight`
  enforces it exactly, and `canary` validates the preflight — seal_provenance
  included — BEFORE its first transport call, so a tampered or absent
  `seal_provenance` yields ZERO PATCHes (and zero GETs). A repo-path is refused
  before any git call if it is absolute or contains a `".."` segment.
- **`seal` does not trust `composition.json` verbatim (BLOCKER 3).** `evaluate_bundle`
  is pure and deterministic, so `seal` re-runs it over the on-disk `bundle.json` and
  requires `canonical_digest` equality against the on-disk `composition.json`; any
  mismatch (a hand edit, e.g. `REFUSED` silently rewritten to
  `ELIGIBLE_WITHIN_DELEGATION`, or ordinary drift) refuses the seal outright. `seal`
  also hard-refuses unless `composition.execution_authority_granted is False`, and
  derives each alternative's `eligible`/`exclusion_reason` from the packet's own
  adjudications — never from a hardcoded `True`.
- **Pre-effect freshness gate (MAJOR 5).** Before issuing any PATCH, `canary` reads the
  live PR once and refuses — with ZERO PATCHes sent — unless the live head sha equals
  `preflight.sealed_commit_sha` AND the live title's hash equals
  `preflight.original_title_sha256`. A refusal here journals `effect_state =
  INVALIDATED_BEFORE_EFFECT` with empty `effect_calls` and exits `6`.
- **Exactly two effect calls, in order, forever.** `TITLE_APPLY` (seq 1) then
  `TITLE_RESTORE` (seq 2). `max_effect_calls` is frozen at `2`; a third call, an
  out-of-order kind, or a `seq` that does not match its 1-based position is a contract
  violation, not a warning.
- **No retry, ever.** `retry_policy` is frozen to `"NONE"`. The canary command's own
  exception handling never issues a second `PATCH` of either kind — on ambiguity it
  performs exactly one *read-only* reconciliation `GET` and then stops.
- **`EFFECT_UNKNOWN` stops the episode, and the journal never discards real evidence
  (BLOCKER 1).** If the apply PATCH completed but the restore PATCH then raised, the
  completed apply call IS journaled (never `effect_calls: []`), and
  `restoration.poststate_title_sha256` comes from the one reconciliation GET's
  actually-observed title — or, when even that fails, the literal string
  `"UNOBSERVED"` (never a guessed "nothing changed"). `restoration.byte_identical` is
  then a DERIVED fact — `True`/`False` exactly when `prestate == poststate` and the
  poststate is observed, `None` if and only if poststate is `"UNOBSERVED"` — never a
  free choice.
- **`response_status` is honestly typed (MAJOR 7).** `gh api` without `-i` never
  exposes an HTTP status; the default `GhCliTransport` records the literal
  `"UNOBSERVED"` rather than fabricate a `200`. The field's real type is `int (100-599)
  | "UNOBSERVED"`.
- **Process-quality is re-derived, never trusted (MAJOR 8).** Every
  `evaluation.process_quality` field is recomputed by the evaluator from independently
  checkable evidence — `sealed_before_effect` recomputes the expectation's own
  canonical-content sha and compares it to what preflight recorded, rather than merely
  checking the field's shape. A zero-call episode (`NOT_ATTEMPTED` /
  `INVALIDATED_BEFORE_EFFECT`, or an `EFFECT_UNKNOWN` whose apply never completed)
  honestly reads `False` on `single_apply_single_restore` and
  `readback_after_each_call` — there is no call sequence or readback to credit.
- **Forecast scoring is kind-specific (MAJOR 4/10).** A probability-kind metric is
  scored with `brier_score = (estimate - realized) ** 2` and never carries
  `within_interval` (always `None`); a count/duration_seconds metric keeps the
  interval framing and never carries a `brier_score`. Every forecast entry is bound
  VERBATIM to its matching sealed-expectation metric (`kind`/`estimate`/`lower`/
  `upper` compared field-by-field), never merely referenced by `metric_id`.
- **PUBLIC_SAFE, two layers, on every artifact this CLI writes.** Every artifact is
  scanned recursively by `control_plane.outcome_learning_contracts.scan_public_safe_text`
  (Slack-ts shapes, `xox*-`, `ghp_`, `github_pat_`, `sk-ant-`, `gh[sou]_`, PEM headers,
  AWS access-key shapes, `/Users/<name>/` path fragments, UUID4 shapes) AND by
  `scripts.agent_eval.privacy.assert_public_safe_evidence` immediately before every
  write — including `bundle.json`, `composition.json`, and the proof markdown, which
  have no dedicated OL-V1 contracts schema of their own but never bypass this scan on
  that account. `privacy_class` is `"PUBLIC_SAFE"` on every schema-bearing artifact,
  checked, not assumed. Local filesystem locators are redacted from the boot packet
  before it is bundled (see above).
- **Non-self-referential seal + external preflight (2026-09-02 binding correction).**
  `containing_commit_sha` and `current_pr_head` are rejected recursively, anywhere,
  inside the expectation and the canary request — a sealed receipt must never encode a
  fact about its own future commit or PR head, because that fact does not exist yet at
  seal time. The pre-effect binding field instead is `expected_parent_head` (the sealed
  commit's *parent*, known before the seal commit exists). The preflight receipt that
  later confirms `head_equals_sealed_commit` is generated by an EXTERNAL, non-repo path
  (`preflight --out` and `canary --episode-dir` both refuse a path inside this
  checkout) precisely so it cannot be a self-referential fact baked into the sealed
  record itself.
- **Single-shot journal, and what it does and does not stop (BLOCKER 2).** `canary`'s
  journal filename is DERIVED from `operation_key` + `expectation_sealed_hash[7:19]` —
  never a caller-chosen path — and a second `canary` invocation against the SAME
  `--episode-dir` refuses outright. A caller pointing at a DIFFERENT `--episode-dir` is
  not stopped by this file check; that case is stopped only by the supervised
  single-operator law (§1): one principal owns one episode end-to-end, and the
  operational discipline is to never re-invoke `canary` for an already-sealed
  `expectation_sealed_hash` from a second location. This is a real limit, named here
  rather than silently assumed away.

## 4. How an auditor verifies this episode (13 checks, plus the 2026-09-02 additions)

Given the six research artifacts plus the proof markdown, an independent auditor can
mechanically confirm all of the following without trusting any narrative:

1. **Expectation seals cleanly.** `control_plane.outcome_learning_contracts.verify_sealed`
   recomputes `sealed_hash` over every other field and it matches exactly.
2. **`assumption_resolutions == []`** in the sealed expectation — resolutions live only
   in the evaluation artifact.
3. **No forbidden self-referential key** (`containing_commit_sha`, `current_pr_head`)
   appears anywhere in the expectation or the canary request.
4. **The canary request is bound to the sealed expectation**:
   `request.expectation_sealed_hash == expectation.sealed_hash`.
5. **The canary request's frozen fields are exactly the pinned values** —
   `effect_class`, `pr_selector`, `canary_token` (`"[OL-V1-CANARY]"`), `apply_rule`,
   `restore_rule`, `max_effect_calls == 2`, `retry_policy == "NONE"`,
   `ambiguity_policy == "EFFECT_UNKNOWN_STOP"`, `execution_authority_granted is False`.
6. **The preflight receipt is external and committed-seal-verified** — its path is not
   inside this checkout (an auditor checks the path the operator hands over, not a
   repo-relative artifact); `head_equals_sealed_commit` is `True` for any episode that
   reports an effect; and `seal_provenance == "COMMITTED_BLOBS_VERIFIED"` — an auditor
   can independently re-run `git rev-parse <sealed_commit_sha>:<repo-path>` followed by
   `git cat-file -p <blob-id>` for each artifact and confirm the canonical digest of
   that committed content equals `expectation_content_sha256`/`request_content_sha256`.
7. **The outcome is bound to both prior artifacts**:
   `outcome.expectation_sealed_hash == expectation.sealed_hash` and
   `outcome.request_digest` equals the canonical digest of the canary request.
8. **Exactly two effect calls for `APPLIED_AND_RESTORED`**, `TITLE_APPLY` then
   `TITLE_RESTORE`, each `seq` matching its 1-based position, method `PATCH`.
9. **Every head_sha agrees.** `preflight.head_sha`, both readbacks' `head_sha`, and
   `preflight.sealed_commit_sha` are all the identical 40-hex value.
10. **Restoration is byte-identical AND internally consistent.** For
    `APPLIED_AND_RESTORED`: `restoration.byte_identical is True`,
    `restoration.poststate_title_sha256 == preflight.original_title_sha256`, and the
    restore call's own readback title hash matches the same value. For ANY effect
    state: `restoration.byte_identical` must equal `prestate == poststate` whenever
    `poststate_title_sha256` is not the literal `"UNOBSERVED"`, and must be `None`
    exactly when it is.
11. **The evaluation is bound to both the expectation and the outcome**
    (`expectation_sealed_hash`, `outcome_digest`), `causal_grade == "DESCRIPTIVE_ONLY"`,
    and `promotion == "NONE"` — hard-enforced values, not merely typical ones. Every
    forecast entry's `kind`/`estimate`/`lower`/`upper` matches its named expectation
    metric verbatim, and probability-kind entries carry `within_interval == None` with
    a correctly-computed `brier_score`.
12. **The self-model is n=1 and non-promoting.** `sample_size == 1`,
    `sample_state == "INSUFFICIENT_SAMPLE"`, `promotion == "NONE"`,
    `authority == "NONE"`, and the `universal_score` KEY is present and its value is
    `None` (not omitted, not zero, not a placeholder number).
13. **The Agent OS projection grants nothing.** `automatic_writes is False`,
    `grants_authority is False`, and every candidate's `status == "CANDIDATE_ONLY"` —
    an auditor can re-derive each candidate's `payload_digest` from its own
    `{kind, target_repository, key_hint, summary, falsifier, so_what}` fields and confirm
    it matches.

Every one of these is enforced by `control_plane/outcome_learning_contracts.py`'s
`validate_*` functions at write time — an auditor re-running
`validate_expectation`/`validate_canary_request`/`validate_outcome`/`validate_evaluation`/
`validate_self_model`/`validate_agentos_projection` over the six committed JSON files is
the fastest way to reproduce checks 1–13 mechanically instead of by hand.

**Two additional structural checks introduced by the 2026-09-02 correction pass**
(folded into the mechanism above rather than renumbered): (a) re-running
`evaluate_bundle` over the committed `bundle.json` reproduces `composition.json`
byte-for-byte (BLOCKER 3 — proves the sealed episode's A1 packet was never
hand-edited); (b) for any `EFFECT_UNKNOWN` outcome, `journal["reconciliation"]`
(embedded nowhere in the committed schema, but recoverable from the operator's raw
canary journal if retained) explains exactly why `restoration.poststate_title_sha256`
carries the value it does.

## 5. What this episode proves — and does not

**Proves — conditional on the actual `effect_state`, not asserted uniformly (MAJOR
12):**

- `APPLIED_AND_RESTORED`: one narrow, reversible, supervised GitHub PR-title canary
  effect was attempted, applied, and restored byte-identically inside a two-call,
  no-retry contract.
- `EFFECT_UNKNOWN`: the episode attempted the effect and stopped on ambiguity rather
  than guessing or retrying — no second PATCH of either kind was ever issued. If the
  restoration was never confirmed (`poststate_title_sha256 == "UNOBSERVED"` or
  `byte_identical is not True`), the proof markdown says so explicitly under **MANUAL
  RESTORATION MAY BE OWED** — a human must check the carrying PR directly before
  treating it as clean.
- `INVALIDATED_BEFORE_EFFECT`: the pre-effect freshness gate refused before any PATCH
  was issued; zero PATCHes were sent.
- `NOT_ATTEMPTED`: no effect was attempted this episode.

In every case: the evaluation is DESCRIPTIVE_ONLY with promotion=NONE; the self-model
is n=1, sample_state=INSUFFICIENT_SAMPLE, promotion=NONE, authority=NONE,
universal_score=None; the Agent OS projection carries candidate-only entries
(automatic_writes=False, grants_authority=False, every candidate
status=CANDIDATE_ONLY) with the DSC candidate's `so_what` itself conditional on the
same `effect_state`.

**Does not prove:**

- **Not broad memory efficacy.** This is one episode; the self-model says so explicitly
  (`sample_size=1`, `sample_state=INSUFFICIENT_SAMPLE`).
- **Not executive competence.** The exercised effect class is one narrow, reversible,
  metadata-only action on a repository the operator owns — nothing here generalizes to
  higher-stakes or less-reversible action classes.
- **Not route superiority.** No alternative route was executed for comparison; there is
  no counterfactual in this design (`assignment.probability=None`,
  `probability_null_reason=DETERMINISTIC_NO_COUNTERFACTUAL_SUPPORT` — whichever lawful
  A1 path `assignment.method` names, neither is a randomized draw).
- **Not policy.** Nothing here changes any standing rule. The self-model and the Agent OS
  projection are non-promoting by construction (`promotion=NONE`, `authority=NONE`,
  `automatic_writes=False`, `grants_authority=False`, every candidate
  `CANDIDATE_ONLY`) — a human, or a separately gauntleted process, decides whether and
  how to act on the projection's candidates.

## 6. Known limitation — OLV1-A5 (read-after-write adequacy)

`mastermind.olv1_outcome.v1`'s `effect_calls[*].readback` does not record whether a
readback came from the mutating `PATCH` response itself or from the single read-only
reconciliation `GET` the CLI performs on ambiguity — both populate the identical closed
shape. `control_plane/outcome_learning_evaluator.py` therefore resolves assumption
`OLV1-A5` to `NOT_TESTED` for every v1 episode; this is an honest ceiling of this
version's schema, not a defect being silently papered over, and it is not required for
any of the 13 auditor checks above.
