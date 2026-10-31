# Outcome Learning V1 — supervised production runbook

## Purpose

OL-V1 turns one real agent decision into bounded organizational learning:

1. acquire current owner state and a trusted Chairman directive;
2. preregister one expectation before any outcome exists;
3. observe one reversible, supervised effect through the existing GitHub carrier;
4. evaluate process, calibration, and assumptions deterministically;
5. append later owner evidence without mutating the original artifacts;
6. project candidate-only organizational context; and
7. prove the result against immutable remote commits and hosted checks.

OL-V1 never grants ranking, trading, execution, routing, policy, or promotion authority.
Every self-model and Agent OS projection remains `authority=NONE`, `promotion=NONE`, and
candidate-only. One episode never becomes a universal score.

This runbook is for the real vertical after the exact repair head has received independent
review. Repair work itself must stop at zero effect and HOLD; it must not run the canary,
push evidence, claim production proof, or merge itself.

OL-V1 on PR #398 is a one-shot mechanism proof, not a recurring effect service. The
six-path boundary governs source-head review; after that exact head is approved, this same
carrier may add only the frozen `research/outcome_learning/` artifacts named below and must
receive new exact-head evidence review. Once the accepted episode is merged, the carrier is
consumed. Any second episode requires a separately preregistered successor version/carrier,
fresh authority, and a new prospective expectation; it must not replay this operation.

## Existing planes only

OL-V1 extends, but does not replace:

- Executive OS `ceo_intent` receipts for trusted directive and exact packet selection;
- Chairman Cognition A1/A2 for options, adjudication, and packet identity;
- the incumbent GitHub branch/PR carrier for the bounded reversible effect;
- the canonical Mastermind Executive host-state root for the single-shot journal;
- the existing Agent OS candidate projection plane; and
- hosted GitHub checks for delayed owner evidence.

There is no second lifecycle, evaluation database, journal selector, memory plane, or retry
plane.

## Hard safety laws

- `compose` refuses when protected Mastermind, canonical Macro/Agent OS, boot state, or the
  trusted directive cannot be acquired as current.
- A multi-option A1 frontier is not resolved locally. `seal` requires a second accepted,
  undispatched, READ-only `ceo_intent` that binds the exact packet digest and option.
- Event times come from the host clock. The public CLI has no timestamp override.
- The effect journal path is host-owned and identity-derived. The public CLI has no journal
  path or root override.
- The canary is at most two PATCH calls: apply once, restore once. There is no effect retry.
- Outcome assembly reacquires the sealed expectation/request and requires GitHub-owner rename
  events for every completed PATCH; the host journal cannot self-author effect success.
- `EFFECT_UNKNOWN` is terminal until one reconciliation on the same carrier resolves it.
- Initial artifacts are immutable. Every correction is an append-only successor with an
  exact predecessor revision id, prior payload digest, owner evidence, and chronology.
- The delayed CI metric is `ci_green_at_frozen_evidence_commit`. It never points at the
  moving final branch head.
- A production proof is an external attestation about an immutable subject commit. It is
  refused inside the repository so it cannot claim to prove its own containing commit.
  Before rendering, it re-reads every receipt-bound git blob, proves the frozen evidence
  commit is an ancestor of the final subject, revalidates the immutable owner check by
  check-run id, and confirms the live branch, PR, and complete latest check-run set still
  equal the final receipt.

## Operator variables

Use an external, private working directory for source packets, receipts, and the final
production attestation. Do not place it inside any repository.

```bash
set -euo pipefail

export MM_ROOT=/absolute/path/to/Mastermind
export MACRO_ROOT=/absolute/path/to/macro
export OL_OUT="$(mktemp -d /private/tmp/olv1-real-XXXXXXXX)"
export EPISODE_DIR="$OL_OUT/episode"
export REPO=mastermindx-market-intelligence/Mastermind
export BRANCH=sol/outcome-learning-v1-complete-vertical-20260902
export PR_NUMBER=398
export OPERATION_KEY=outcome-learning-v1-real-episode

# These must already exist in the canonical Executive OS plane.
export DIRECTIVE_INTENT_ID=CEO-OLV1-DIRECTIVE-REPLACE_ME
# Set only after compose returns DECISION_REQUIRED and the exact packet exists.
export SELECTION_INTENT_ID=CEO-OLV1-SELECTION-REPLACE_ME

export EXPECTATION_OUT="$OL_OUT/expectation.json"
export REQUEST_OUT="$OL_OUT/request.json"
export PREFLIGHT_OUT="$OL_OUT/preflight.json"
export OUTCOME_OUT="$OL_OUT/outcome.json"
export EVALUATION_V1_OUT="$OL_OUT/evaluation_v1.json"
export REVISION_V1_OUT="$OL_OUT/evaluation_revision_1.json"
export SELF_MODEL_V1_OUT="$OL_OUT/self_model_v1.json"
export PROJECTION_V1_OUT="$OL_OUT/projection_v1.json"
export LOCAL_PROOF_V1_OUT="$OL_OUT/local_candidate_v1.md"
export EVIDENCE_RECEIPT_OUT="$OL_OUT/evidence_publication_receipt.json"
export EVALUATION_V2_OUT="$OL_OUT/evaluation_v2_matured.json"
export REVISION_V2_OUT="$OL_OUT/evaluation_revision_2.json"
export SELF_MODEL_V2_OUT="$OL_OUT/self_model_v2.json"
export PROJECTION_V2_OUT="$OL_OUT/projection_v2.json"
export LOCAL_PROOF_V2_OUT="$OL_OUT/local_candidate_v2.md"
export FINAL_RECEIPT_OUT="$OL_OUT/final_publication_receipt.json"
export PRODUCTION_PROOF_OUT="$OL_OUT/production_proof.md"

export EXPECTATION_REPO_PATH=research/outcome_learning/OLV1_EXPECTATION.json
export REQUEST_REPO_PATH=research/outcome_learning/OLV1_CANARY_REQUEST.json
export PREFLIGHT_REPO_PATH=research/outcome_learning/OLV1_PREFLIGHT.json
export OUTCOME_REPO_PATH=research/outcome_learning/OLV1_OUTCOME.json
export EVALUATION_V1_REPO_PATH=research/outcome_learning/OLV1_EVALUATION_V1.json
export REVISION_V1_REPO_PATH=research/outcome_learning/OLV1_EVALUATION_REVISION_1.json
export SELF_MODEL_V1_REPO_PATH=research/outcome_learning/OLV1_SELF_MODEL_V1.json
export PROJECTION_V1_REPO_PATH=research/outcome_learning/OLV1_AGENTOS_PROJECTION_V1.json
export LOCAL_PROOF_V1_REPO_PATH=research/outcome_learning/OLV1_LOCAL_CANDIDATE_V1.md
export EVALUATION_V2_REPO_PATH=research/outcome_learning/OLV1_EVALUATION_V2.json
export REVISION_V2_REPO_PATH=research/outcome_learning/OLV1_EVALUATION_REVISION_2.json
export SELF_MODEL_V2_REPO_PATH=research/outcome_learning/OLV1_SELF_MODEL_V2.json
export PROJECTION_V2_REPO_PATH=research/outcome_learning/OLV1_AGENTOS_PROJECTION_V2.json
export LOCAL_PROOF_V2_REPO_PATH=research/outcome_learning/OLV1_LOCAL_CANDIDATE_V2.md

assert_exact_staged_paths() {
  EXPECTED_PATHS="$(printf '%s\n' "$@" | LC_ALL=C sort)"
  ACTUAL_PATHS="$(git -C "$MM_ROOT" diff --cached --name-only | LC_ALL=C sort)"
  if [ "$ACTUAL_PATHS" != "$EXPECTED_PATHS" ]; then
    printf 'refusing unexpected staged paths\nexpected:\n%s\nobserved:\n%s\n' \
      "$EXPECTED_PATHS" "$ACTUAL_PATHS" >&2
    return 1
  fi
}

push_once_and_reconcile() {
  EXPECTED_HEAD="$1"
  case "$-" in *e*) HAD_ERREXIT=1 ;; *) HAD_ERREXIT=0 ;; esac
  set +e
  git -C "$MM_ROOT" push origin "HEAD:refs/heads/$BRANCH"
  PUSH_RC=$?
  LS_REMOTE_OUTPUT="$(git -C "$MM_ROOT" ls-remote origin \
    "refs/heads/$BRANCH")"
  BRANCH_READ_RC=$?
  if [ "$BRANCH_READ_RC" -eq 0 ]; then
    REMOTE_BRANCH_SHA="$(printf '%s\n' "$LS_REMOTE_OUTPUT" | awk 'NR == 1 {print $1}')"
  else
    REMOTE_BRANCH_SHA=""
  fi
  REMOTE_PR_SHA="$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq '.head.sha')"
  PR_READ_RC=$?
  if [ "$HAD_ERREXIT" -eq 1 ]; then set -e; else set +e; fi

  if [ "$BRANCH_READ_RC" -ne 0 ] || [ "$PR_READ_RC" -ne 0 ] || \
     [ "$REMOTE_BRANCH_SHA" != "$EXPECTED_HEAD" ] || \
     [ "$REMOTE_PR_SHA" != "$EXPECTED_HEAD" ]; then
    printf 'EFFECT_UNKNOWN: push/readback unresolved; no retry\n' >&2
    printf 'push_rc=%s branch_rc=%s pr_rc=%s expected=%s branch=%s pr=%s\n' \
      "$PUSH_RC" "$BRANCH_READ_RC" "$PR_READ_RC" "$EXPECTED_HEAD" \
      "$REMOTE_BRANCH_SHA" "$REMOTE_PR_SHA" >&2
    return 1
  fi
  printf 'push_reconciled expected=%s push_rc=%s\n' "$EXPECTED_HEAD" "$PUSH_RC"
}
```

## Gate 0 — recover current authority and exact carrier

Before running any command:

1. freshly pin protected Mastermind and load the same-SHA Sol Skillpack;
2. reconcile `WS:AGENT-EVAL-FABRIC` directly from current Agent OS records;
3. verify the accepted repair head and independent review return;
4. verify the carrier worktree is clean and no other process owns it;
5. verify the canonical Macro checkout is current and clean; and
6. verify the directive Executive intent is accepted, undispatched, `QUEUED`,
   READ-only/A0, grounded to the exact Mastermind/Macro source, and has zero attempts.
   The selection intent does not exist before compose; when return code `7` creates the
   exact packet, acquire and verify it immediately before Step 2.

The directive objective is a canonical JSON mapping with exactly:

```json
{
  "authority_ceiling": "COMPOSE_ONLY_NO_EFFECT_NO_PROMOTION",
  "carrier_ref": "github:Mastermind:branch:sol/outcome-learning-v1-complete-vertical-20260902",
  "expires_at": "<future canonical UTC Z timestamp>",
  "operation_key": "outcome-learning-v1-real-episode",
  "schema": "mastermind.olv1_directive.v1",
  "workstream": "WS:AGENT-EVAL-FABRIC"
}
```

Do not mint this receipt locally. If the canonical `ceo_intent` status adapter cannot read
it, OL-V1 must return `DIRECTIVE_SOURCE_UNVERIFIED`.

## Step 1 — compose current owners without effect

```bash
cd "$MM_ROOT"
set +e
python3 scripts/outcome_learning_v1.py compose \
  --mastermind-root "$MM_ROOT" \
  --macro-root "$MACRO_ROOT" \
  --episode-dir "$EPISODE_DIR" \
  --directive-intent-id "$DIRECTIVE_INTENT_ID" \
  --operation-key "$OPERATION_KEY"
COMPOSE_RC=$?
set -e
```

Lawful outcomes:

- `0`: A1 produced one unique actionable canary frontier. No selection intent is accepted.
- `7`: A1 preserved multiple incomparable actionable options. This is expected for the
  canary/HOLD frontier; obtain one exact packet-bound selection intent before sealing.
- `4`: a load-bearing owner is not current. Stop.
- `5`: source identity, directive, or composition is invalid. Stop.

For return code `7`, derive the exact packet and carrier:

```bash
export PACKET_DIGEST="sha256:$(jq -r '.packet.packet_digest' \
  "$EPISODE_DIR/composition.json")"
export SELECTED_CARRIER="$(jq -r \
  '.options[] | select(.option_id == "OPT-OLV1-PR-TITLE-CANARY") | .carrier_ref' \
  "$EPISODE_DIR/bundle.json")"
```

The accepted selection intent objective must be canonical JSON with exactly:

```json
{
  "authority_ceiling": "SEAL_ONLY_NO_EFFECT_NO_PROMOTION",
  "carrier_ref": "<SELECTED_CARRIER>",
  "chosen_option_id": "OPT-OLV1-PR-TITLE-CANARY",
  "operation_key": "outcome-learning-v1-real-episode",
  "packet_digest": "<PACKET_DIGEST>",
  "schema": "mastermind.olv1_selection.v1",
  "workstream": "WS:AGENT-EVAL-FABRIC"
}
```

It must be accepted strictly after the packet source cutoff. A narrative approval, local
JSON file, fixture, or environment variable is not a substitute.

## Step 2 — seal expectation and request

For a multi-option frontier:

```bash
python3 scripts/outcome_learning_v1.py seal \
  --composition "$EPISODE_DIR/composition.json" \
  --episode-dir "$EPISODE_DIR" \
  --mastermind-root "$MM_ROOT" \
  --selection-intent-id "$SELECTION_INTENT_ID" \
  --out-expectation "$EXPECTATION_OUT" \
  --out-request "$REQUEST_OUT"
```

For a unique actionable frontier, omit `--selection-intent-id`.

The expectation is written before the request. The final decision digest binds the exact
operation, packet, chosen option, carrier, and selection receipt. The request contains no
free authority and no operator-authored timestamp.

## Step 3 — build the one lawful sealed carrier commit

The canary option's `expected_head_sha` is the action-time remote branch/PR head acquired
by `compose`; it is not protected master. Protected master remains source-law evidence only.
A normal seal commit must be the direct child of that frozen carrier tip. Do not merge,
rebase, squash, or force-push protected master into the carrier to manufacture ancestry.

```bash
cd "$MM_ROOT"
export CARRIER_HEAD="$(jq -r \
  '.options[] | select(.option_id == "OPT-OLV1-PR-TITLE-CANARY") | .expected_head_sha' \
  "$EPISODE_DIR/bundle.json")"

test "$(git rev-parse HEAD)" = "$CARRIER_HEAD"
test -z "$(git status --porcelain)"
REMOTE_BRANCH_SHA="$(git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
REMOTE_PR_SHA="$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq '.head.sha')"
test "$REMOTE_BRANCH_SHA" = "$CARRIER_HEAD"
test "$REMOTE_PR_SHA" = "$CARRIER_HEAD"

mkdir -p "$MM_ROOT/research/outcome_learning"
install -m 0644 "$EXPECTATION_OUT" "$MM_ROOT/$EXPECTATION_REPO_PATH"
install -m 0644 "$REQUEST_OUT" "$MM_ROOT/$REQUEST_REPO_PATH"
git add -- "$EXPECTATION_REPO_PATH" "$REQUEST_REPO_PATH"
assert_exact_staged_paths "$EXPECTATION_REPO_PATH" "$REQUEST_REPO_PATH"

git commit -m "Seal OL-V1 prospective episode"
export SEALED_COMMIT="$(git rev-parse HEAD)"
test "$(git rev-parse "$SEALED_COMMIT^")" = "$CARRIER_HEAD"
push_once_and_reconcile "$SEALED_COMMIT"
```

The push helper sends exactly once, then reads the remote branch and PR exactly once even
when the client reports a nonzero result. Ambiguous or mismatched readback stops
`EFFECT_UNKNOWN`; it never retries the push.

The current-base GitHub merge ref and hosted checks remain separate integration evidence;
they never change the sealed commit's parent identity.

## Step 4 — committed preflight and single-shot canary

```bash
python3 "$MM_ROOT/scripts/outcome_learning_v1.py" preflight \
  --repo "$REPO" \
  --branch "$BRANCH" \
  --sealed-commit "$SEALED_COMMIT" \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --expectation-repo-path "$EXPECTATION_REPO_PATH" \
  --request-repo-path "$REQUEST_REPO_PATH" \
  --mastermind-root "$MM_ROOT" \
  --out "$PREFLIGHT_OUT"
```

`preflight` independently proves that the sealed commit has exactly one parent and that
its complete changed-path set is exactly the expectation/request preregistration pair. It
then resolves both committed blobs, verifies canonical content, selects exactly one open PR,
and requires the PR head to equal the sealed commit.

Only after all gates remain valid may the supervised operator run:

```bash
python3 "$MM_ROOT/scripts/outcome_learning_v1.py" canary \
  --preflight "$PREFLIGHT_OUT" \
  --request "$REQUEST_OUT" \
  --mastermind-root "$MM_ROOT"
```

The journal is reserved before the first GitHub read under:

```text
/Library/Application Support/MastermindExecutive/state/outcome-learning-v1/journals/
```

Its identity includes repository, branch, operation, expectation, request, sealed commit,
and PR. There is no CLI path override. After freshness passes and before the first PATCH,
the canary also captures a complete bounded/paginated baseline of owner rename-event IDs.
Outcome evidence must use rename events absent from that baseline, so GitHub's second-precision
event clock cannot invalidate a legitimate microsecond local attempt or revive an old event.

Canary terminal states:

- `APPLIED_AND_RESTORED`: exactly one apply PATCH and one restore PATCH, with matching
  readbacks and unchanged head.
- `INVALIDATED_BEFORE_EFFECT`: selector or freshness changed; zero PATCH calls.
- `EFFECT_UNKNOWN`: a PATCH may have crossed the effect boundary. No retry. Preserve the
  journal and reconcile once on the same carrier.

## Step 5 — derive the initial learning chain

```bash
python3 "$MM_ROOT/scripts/outcome_learning_v1.py" outcome \
  --preflight "$PREFLIGHT_OUT" \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --mastermind-root "$MM_ROOT" \
  --out "$OUTCOME_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" evaluate \
  --expectation "$EXPECTATION_OUT" \
  --outcome "$OUTCOME_OUT" \
  --request "$REQUEST_OUT" \
  --out "$EVALUATION_V1_OUT" \
  --out-revision "$REVISION_V1_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" self-model \
  --evaluation "$EVALUATION_V1_OUT" \
  --expectation "$EXPECTATION_OUT" \
  --out "$SELF_MODEL_V1_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" project \
  --evaluation "$EVALUATION_V1_OUT" \
  --expectation "$EXPECTATION_OUT" \
  --outcome "$OUTCOME_OUT" \
  --out "$PROJECTION_V1_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" proof \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --outcome "$OUTCOME_OUT" \
  --evaluation "$EVALUATION_V1_OUT" \
  --self-model "$SELF_MODEL_V1_OUT" \
  --project "$PROJECTION_V1_OUT" \
  --revision "$REVISION_V1_OUT" \
  --out "$LOCAL_PROOF_V1_OUT"
```

The first revision has `revision=1`, `supersedes=null`, and
`prior_payload_digest=null`. The delayed CI metric remains unresolved. The proof title must
be `OL-V1 Local Candidate Proof`; it is not production evidence.

## Step 6 — publish and freeze the evidence commit

Copy only public-safe artifacts into the existing research path:

```bash
cd "$MM_ROOT"
test -z "$(git status --porcelain)"
install -m 0644 "$PREFLIGHT_OUT" "$MM_ROOT/$PREFLIGHT_REPO_PATH"
install -m 0644 "$OUTCOME_OUT" "$MM_ROOT/$OUTCOME_REPO_PATH"
install -m 0644 "$EVALUATION_V1_OUT" "$MM_ROOT/$EVALUATION_V1_REPO_PATH"
install -m 0644 "$REVISION_V1_OUT" "$MM_ROOT/$REVISION_V1_REPO_PATH"
install -m 0644 "$SELF_MODEL_V1_OUT" "$MM_ROOT/$SELF_MODEL_V1_REPO_PATH"
install -m 0644 "$PROJECTION_V1_OUT" "$MM_ROOT/$PROJECTION_V1_REPO_PATH"
install -m 0644 "$LOCAL_PROOF_V1_OUT" "$MM_ROOT/$LOCAL_PROOF_V1_REPO_PATH"

git add -- \
  "$PREFLIGHT_REPO_PATH" \
  "$OUTCOME_REPO_PATH" \
  "$EVALUATION_V1_REPO_PATH" \
  "$REVISION_V1_REPO_PATH" \
  "$SELF_MODEL_V1_REPO_PATH" \
  "$PROJECTION_V1_REPO_PATH" \
  "$LOCAL_PROOF_V1_REPO_PATH"
assert_exact_staged_paths \
  "$PREFLIGHT_REPO_PATH" \
  "$OUTCOME_REPO_PATH" \
  "$EVALUATION_V1_REPO_PATH" \
  "$REVISION_V1_REPO_PATH" \
  "$SELF_MODEL_V1_REPO_PATH" \
  "$PROJECTION_V1_REPO_PATH" \
  "$LOCAL_PROOF_V1_REPO_PATH"
git commit -m "Record OL-V1 initial evidence"
export EVIDENCE_COMMIT="$(git rev-parse HEAD)"
push_once_and_reconcile "$EVIDENCE_COMMIT"
```

Reconcile the remote once; do not infer success from the local command alone. Then capture
the immutable branch/PR/blob receipt. The receipt must stay outside the repository because
it observes the commit and cannot be contained by that same commit.

```bash
python3 scripts/outcome_learning_v1.py capture-publication \
  --stage EVIDENCE_COMMIT \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --repo "$REPO" \
  --branch "$BRANCH" \
  --pr-number "$PR_NUMBER" \
  --target-commit "$EVIDENCE_COMMIT" \
  --frozen-evidence-commit "$EVIDENCE_COMMIT" \
  --artifact "$EXPECTATION_REPO_PATH" \
  --artifact "$REQUEST_REPO_PATH" \
  --artifact "$PREFLIGHT_REPO_PATH" \
  --artifact "$OUTCOME_REPO_PATH" \
  --artifact "$EVALUATION_V1_REPO_PATH" \
  --artifact "$REVISION_V1_REPO_PATH" \
  --artifact "$SELF_MODEL_V1_REPO_PATH" \
  --artifact "$PROJECTION_V1_REPO_PATH" \
  --artifact "$LOCAL_PROOF_V1_REPO_PATH" \
  --mastermind-root "$MM_ROOT" \
  --out "$EVIDENCE_RECEIPT_OUT"
```

This is the immutable target for delayed CI. Never replace it with a later moving head.

## Step 7 — mature the delayed owner observation append-only

Wait for the exact hosted check on `EVIDENCE_COMMIT`. Then run:

```bash
export EVIDENCE_CHECK_NAME='<exact GitHub check-run name>'

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" mature-evaluation \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --outcome "$OUTCOME_OUT" \
  --initial-evaluation "$EVALUATION_V1_OUT" \
  --initial-revision "$REVISION_V1_OUT" \
  --evidence-receipt "$EVIDENCE_RECEIPT_OUT" \
  --check-name "$EVIDENCE_CHECK_NAME" \
  --out-evaluation "$EVALUATION_V2_OUT" \
  --out-revision "$REVISION_V2_OUT"
```

The command queries GitHub itself. It requires exactly one matching check run, exact
`head_sha=EVIDENCE_COMMIT`, terminal status, and an owner result. It never accepts a
caller-supplied realized value. It leaves both initial files byte-identical and creates one
revision-2 successor with:

- exact revision-1 predecessor id;
- exact prior payload digest;
- the frozen evidence commit and check-run id/name/result;
- strict UTC chronology;
- correction reason `DELAYED_OWNER_EVIDENCE_MATURATION`; and
- `authority=NONE`, `promotion=NONE`.

Regenerate the bounded downstream candidates from the authoritative later evaluation:

```bash
python3 "$MM_ROOT/scripts/outcome_learning_v1.py" self-model \
  --evaluation "$EVALUATION_V2_OUT" \
  --expectation "$EXPECTATION_OUT" \
  --out "$SELF_MODEL_V2_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" project \
  --evaluation "$EVALUATION_V2_OUT" \
  --expectation "$EXPECTATION_OUT" \
  --outcome "$OUTCOME_OUT" \
  --out "$PROJECTION_V2_OUT"

python3 "$MM_ROOT/scripts/outcome_learning_v1.py" proof \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --outcome "$OUTCOME_OUT" \
  --evaluation "$EVALUATION_V2_OUT" \
  --self-model "$SELF_MODEL_V2_OUT" \
  --project "$PROJECTION_V2_OUT" \
  --revision "$REVISION_V1_OUT" \
  --revision "$REVISION_V2_OUT" \
  --out "$LOCAL_PROOF_V2_OUT"
```

This proof is still a local candidate because the maturation artifacts have not yet been
published and checked remotely.

## Step 8 — publish the maturation candidate and require terminal hosted checks

```bash
cd "$MM_ROOT"
test -z "$(git status --porcelain)"
install -m 0644 "$EVALUATION_V2_OUT" "$MM_ROOT/$EVALUATION_V2_REPO_PATH"
install -m 0644 "$REVISION_V2_OUT" "$MM_ROOT/$REVISION_V2_REPO_PATH"
install -m 0644 "$SELF_MODEL_V2_OUT" "$MM_ROOT/$SELF_MODEL_V2_REPO_PATH"
install -m 0644 "$PROJECTION_V2_OUT" "$MM_ROOT/$PROJECTION_V2_REPO_PATH"
install -m 0644 "$LOCAL_PROOF_V2_OUT" "$MM_ROOT/$LOCAL_PROOF_V2_REPO_PATH"

git add -- \
  "$EVALUATION_V2_REPO_PATH" \
  "$REVISION_V2_REPO_PATH" \
  "$SELF_MODEL_V2_REPO_PATH" \
  "$PROJECTION_V2_REPO_PATH" \
  "$LOCAL_PROOF_V2_REPO_PATH"
assert_exact_staged_paths \
  "$EVALUATION_V2_REPO_PATH" \
  "$REVISION_V2_REPO_PATH" \
  "$SELF_MODEL_V2_REPO_PATH" \
  "$PROJECTION_V2_REPO_PATH" \
  "$LOCAL_PROOF_V2_REPO_PATH"
git commit -m "Mature OL-V1 delayed owner evidence"
export MATURATION_COMMIT="$(git rev-parse HEAD)"
test "$MATURATION_COMMIT" != "$EVIDENCE_COMMIT"
push_once_and_reconcile "$MATURATION_COMMIT"
```

After the remote branch and PR both identify `MATURATION_COMMIT`, wait for every latest
hosted check on that exact commit to reach terminal success. Then capture the final receipt:

```bash
python3 scripts/outcome_learning_v1.py capture-publication \
  --stage MATURATION_COMMIT \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --repo "$REPO" \
  --branch "$BRANCH" \
  --pr-number "$PR_NUMBER" \
  --target-commit "$MATURATION_COMMIT" \
  --frozen-evidence-commit "$EVIDENCE_COMMIT" \
  --artifact "$EVALUATION_V2_REPO_PATH" \
  --artifact "$REVISION_V2_REPO_PATH" \
  --artifact "$SELF_MODEL_V2_REPO_PATH" \
  --artifact "$PROJECTION_V2_REPO_PATH" \
  --artifact "$LOCAL_PROOF_V2_REPO_PATH" \
  --mastermind-root "$MM_ROOT" \
  --out "$FINAL_RECEIPT_OUT"
```

`MATURATION_COMMIT` must differ from and descend from `EVIDENCE_COMMIT`. The command
refuses if either the remote branch or PR points elsewhere, any artifact is absent from the
target commit, the latest check-run page is incomplete (`total_count` differs from the
returned set), any latest check is non-terminal, or any terminal conclusion is not
`success`. More than 100 latest checks therefore fail closed rather than producing partial
evidence.

## Step 9 — render the external production attestation

Only after both remote receipts exist:

```bash
python3 "$MM_ROOT/scripts/outcome_learning_v1.py" proof \
  --expectation "$EXPECTATION_OUT" \
  --request "$REQUEST_OUT" \
  --outcome "$OUTCOME_OUT" \
  --evaluation "$EVALUATION_V2_OUT" \
  --self-model "$SELF_MODEL_V2_OUT" \
  --project "$PROJECTION_V2_OUT" \
  --revision "$REVISION_V1_OUT" \
  --revision "$REVISION_V2_OUT" \
  --evidence-receipt "$EVIDENCE_RECEIPT_OUT" \
  --final-publication-receipt "$FINAL_RECEIPT_OUT" \
  --mastermind-root "$MM_ROOT" \
  --out "$PRODUCTION_PROOF_OUT"
```

The output title is `OL-V1 Production Proof`. It names both immutable commits and states
that it is an external attestation about `MATURATION_COMMIT`. Before writing, the command
recomputes every receipt artifact from the exact git commit, requires the evidence receipt
to contain the exact expectation, request, preflight, outcome, revision-1 evaluation, and
revision-1 envelope at their canonical paths, requires the final receipt to contain the exact
matured evaluation/revision/self-model/projection bytes, proves git
ancestry, re-reads the frozen owner check by immutable check-run id, and re-reads the live
final branch, PR, and complete latest check set. Generate it before any later branch move.
The command refuses a production-proof output path inside Mastermind; committing it would
create a new head and invalidate its own subject receipt.

The independent reviewer may attach the external proof and receipt digests to the existing
PR/review record. Do not mutate the subject branch to add the production attestation.

## Append-only correction law

`mastermind.olv1_artifact_revision.v1` is the generic correction envelope for expectation,
outcome, evaluation, self-model, and Agent OS projection artifacts.

- Revision 1 has explicit null predecessor fields.
- A successor binds one exact prior `revision_id` and `payload_digest`.
- Artifact kind and episode identity cannot change.
- Payload bytes/digest must change; a no-op successor is refused.
- Owner evidence is mandatory for every successor.
- Backdating, off-chain predecessors, duplicate successors, self-supersession, cycles,
  in-place mutation, and multiple revision-1 roots are refused.
- Original artifacts remain byte-identical.
- Revisions carry no authority and cannot promote policy.

The `mature-evaluation` command is the first owner-specific adapter. Other corrections must
use the same generic contract plus a real owner evidence adapter; never add a local freeform
"correction" flag.

## Failure and null behavior

| Condition | Required result |
|---|---|
| trusted directive unavailable or stale | `DIRECTIVE_SOURCE_UNVERIFIED`; no seal/effect |
| A1 frontier incomparable | `DECISION_REQUIRED`; exact selection intent required |
| protected/Macro/Agent OS owner not current | refuse; do not substitute fixture state |
| committed blob, parent, carrier, PR, or head mismatch | preflight refuses before PATCH |
| selector changed before effect | `INVALIDATED_BEFORE_EFFECT`, zero PATCH |
| freshness changed before effect | `INVALIDATED_BEFORE_EFFECT`, zero PATCH |
| apply/restore ambiguity | `EFFECT_UNKNOWN`, no retry, one same-carrier reconciliation |
| completed PATCH lacks exact GitHub rename event | outcome refuses; journal alone is not proof |
| journal already exists | refuse every repeat, regardless of journal state |
| remote branch/PR drift | no publication receipt; do not infer or retry a push |
| check name missing/duplicated or SHA mismatched | no maturation files |
| delayed result not observed | remains explicit `null`, never guessed |
| correction predecessor/identity/chronology invalid | successor refused |
| only local artifacts exist | `Local Candidate Proof`, never production |
| final checks absent/non-success | no final publication receipt or production proof |

## Verification before return

Run at least:

```bash
cd "$MM_ROOT"
python3 -m py_compile \
  control_plane/outcome_learning_contracts.py \
  control_plane/outcome_learning_evaluator.py \
  scripts/outcome_learning_v1.py

python3 -m pytest \
  tests/test_outcome_learning_v1.py \
  tests/test_outcome_learning_v1_cli.py \
  -q
```

Review the exact diff against protected master. The implementation repair remains confined
to the six frozen files named by the accepted audit. Generated episode evidence belongs
under `research/outcome_learning/` only after the supervised real run.

## Acceptance and durable continuation

Green local tests, a push, a PR, a receipt, and hosted CI are distinct from acceptance.
Acceptance requires all of the following:

1. one lawful preregistered expectation preceded every effect;
2. one real outcome was observed through the canonical journal;
3. deterministic evaluation resolved or preserved every unknown honestly;
4. the initial and matured evaluations form one valid append-only chain;
5. the frozen evidence SHA and exact owner check are durable;
6. the final subject SHA has branch/PR readback and terminal hosted checks;
7. the self-model remains n=1/non-promoting and projection remains candidate-only;
8. an independent reviewer adjudicates the complete evidence against the original mission;
9. the Agent OS continuation for `WS:AGENT-EVAL-FABRIC` records what was learned, what was
   not learned, the authoritative revision, and the exact next action; and
10. only then may Sol decide release/merge acceptance.

Never call a context rotation, local proof, green CI, remote receipt, or candidate projection
completion by itself.
