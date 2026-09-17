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
```

## Gate 0 — recover current authority and exact carrier

Before running any command:

1. freshly pin protected Mastermind and load the same-SHA Sol Skillpack;
2. reconcile `WS:AGENT-EVAL-FABRIC` directly from current Agent OS records;
3. verify the accepted repair head and independent review return;
4. verify the carrier worktree is clean and no other process owns it;
5. verify the canonical Macro checkout is current and clean; and
6. verify both Executive intents are accepted, undispatched, `QUEUED`, READ-only/A0,
   grounded to the exact Mastermind/Macro source, and have zero attempts.

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

`preflight` requires the sealed commit's **first parent** to equal the protected Mastermind
SHA used by compose. The incumbent repair branch may already contain several commits. Do
not force-push or discard them. Instead, after independent review, construct a merge commit
whose first parent is protected master and whose second parent is the accepted repair head.
Because the repair head is a parent of the merge commit, advancing the existing branch to
that merge commit is still a non-force fast-forward.

```bash
cd "$MM_ROOT"
export REPAIR_HEAD="$(git rev-parse HEAD)"
export PROTECTED_MASTER="$(git ls-remote origin refs/heads/master | awk '{print $1}')"
export SEAL_WT="$(mktemp -d /private/tmp/olv1-seal-wt-XXXXXXXX)"

git worktree add --detach "$SEAL_WT" "$PROTECTED_MASTER"
git -C "$SEAL_WT" merge --no-commit --no-ff "$REPAIR_HEAD"

install -m 0644 "$EXPECTATION_OUT" "$SEAL_WT/$EXPECTATION_REPO_PATH"
install -m 0644 "$REQUEST_OUT" "$SEAL_WT/$REQUEST_REPO_PATH"
git -C "$SEAL_WT" add -- \
  "$EXPECTATION_REPO_PATH" \
  "$REQUEST_REPO_PATH"

git -C "$SEAL_WT" diff --cached --name-only
# The staged paths must be only the reviewed repair merge plus the two preregistration files.

git -C "$SEAL_WT" commit -m "Seal OL-V1 prospective episode"
export SEALED_COMMIT="$(git -C "$SEAL_WT" rev-parse HEAD)"
test "$(git -C "$SEAL_WT" rev-parse "$SEALED_COMMIT^1")" = "$PROTECTED_MASTER"
git -C "$SEAL_WT" merge-base --is-ancestor "$REPAIR_HEAD" "$SEALED_COMMIT"
```

Advance the incumbent branch once, without force:

```bash
git -C "$MM_ROOT" merge --ff-only "$SEALED_COMMIT"
git -C "$MM_ROOT" push origin "HEAD:refs/heads/$BRANCH"
```

A timeout or transport cancellation does not prove the push failed. Reconcile exactly once:

```bash
REMOTE_BRANCH_SHA="$(git -C "$MM_ROOT" ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
test "$REMOTE_BRANCH_SHA" = "$SEALED_COMMIT"
```

If the remote state is ambiguous, stop `EFFECT_UNKNOWN`; do not retry the push blindly.
Remove the temporary seal worktree only after the local and remote branch both identify the
same sealed commit.

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

`preflight` independently resolves both committed blobs, verifies canonical content,
verifies the sealed commit's first parent, selects exactly one open PR, and requires the PR
head to equal the sealed commit.

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
and PR. There is no CLI path override.

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
install -m 0644 "$PREFLIGHT_OUT" "$MM_ROOT/$PREFLIGHT_REPO_PATH"
install -m 0644 "$OUTCOME_OUT" "$MM_ROOT/$OUTCOME_REPO_PATH"
install -m 0644 "$EVALUATION_V1_OUT" "$MM_ROOT/$EVALUATION_V1_REPO_PATH"
install -m 0644 "$REVISION_V1_OUT" "$MM_ROOT/$REVISION_V1_REPO_PATH"
install -m 0644 "$SELF_MODEL_V1_OUT" "$MM_ROOT/$SELF_MODEL_V1_REPO_PATH"
install -m 0644 "$PROJECTION_V1_OUT" "$MM_ROOT/$PROJECTION_V1_REPO_PATH"
install -m 0644 "$LOCAL_PROOF_V1_OUT" "$MM_ROOT/$LOCAL_PROOF_V1_REPO_PATH"

cd "$MM_ROOT"
git add -- \
  "$PREFLIGHT_REPO_PATH" \
  "$OUTCOME_REPO_PATH" \
  "$EVALUATION_V1_REPO_PATH" \
  "$REVISION_V1_REPO_PATH" \
  "$SELF_MODEL_V1_REPO_PATH" \
  "$PROJECTION_V1_REPO_PATH" \
  "$LOCAL_PROOF_V1_REPO_PATH"
git diff --cached --name-only
git commit -m "Record OL-V1 initial evidence"
export EVIDENCE_COMMIT="$(git rev-parse HEAD)"
git push origin "HEAD:refs/heads/$BRANCH"
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
install -m 0644 "$EVALUATION_V2_OUT" "$MM_ROOT/$EVALUATION_V2_REPO_PATH"
install -m 0644 "$REVISION_V2_OUT" "$MM_ROOT/$REVISION_V2_REPO_PATH"
install -m 0644 "$SELF_MODEL_V2_OUT" "$MM_ROOT/$SELF_MODEL_V2_REPO_PATH"
install -m 0644 "$PROJECTION_V2_OUT" "$MM_ROOT/$PROJECTION_V2_REPO_PATH"
install -m 0644 "$LOCAL_PROOF_V2_OUT" "$MM_ROOT/$LOCAL_PROOF_V2_REPO_PATH"

cd "$MM_ROOT"
git add -- \
  "$EVALUATION_V2_REPO_PATH" \
  "$REVISION_V2_REPO_PATH" \
  "$SELF_MODEL_V2_REPO_PATH" \
  "$PROJECTION_V2_REPO_PATH" \
  "$LOCAL_PROOF_V2_REPO_PATH"
git diff --cached --name-only
git commit -m "Mature OL-V1 delayed owner evidence"
export MATURATION_COMMIT="$(git rev-parse HEAD)"
test "$MATURATION_COMMIT" != "$EVIDENCE_COMMIT"
git push origin "HEAD:refs/heads/$BRANCH"
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
to contain the exact revision-1 evaluation and envelope, requires the final receipt to
contain the exact matured evaluation/revision/self-model/projection bytes, proves git
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
