# Subagent Fabric access: immutable release and live return qualification

**Release-preparation kit.** Depends on [Mastermind PR #1694](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1694). Source-reviewed candidate head: `37f00e59c480300c6c44de4a0e04c8d536af6890`. Full independent Fabric reviews were accepted for `e213d8bd...` (functional changes) and `37f00e59...` (integrated source). Linux CI `39852755814` completed successfully on the latter. This document and its scripts **do not select code, change auth/pools, dispatch a worker, merge or certify a live runtime**.

## Outcome and release invariants

M2 Claude and Codex sessions should each load the installed `mastermind-claude-fabric-delegation` and `mastermind-fabric-delegate` skills automatically, delegate one real low-risk Fabric leaf under the session's **actual** root and immediate parent, retrieve and review the exact response, and record principal acceptance. A separately admitted GLM/Grok operator should delegate one C0/C1 leaf, receive its result in the same operator, acknowledge the exact digest, and return its own result to its original principal for acceptance.

These are different gates: skill installed, fresh session skill loaded, native Fabric launch, worker START, terminal retained result, recipient attention/delivery, parent acceptance, immutable generation selected, and production runtime behavior. Never treat one as proof of another.

The current M2 Fabric native generation at initial qualification was:

```text
CURRENT: 09b1ff4204c49acc71bb228751c4efefc22c70c89092734d9ea2fafe3fff1a49
sequence: 16
selected operator SHA256: 8473ba07f597d84605940897cb0f4047a9ad7458380be10d4e122456e88a0645
reviewed PR operator candidate SHA256: 4bb2c134eb500afe6b5c980abecb8d02092fe1462c6b7fcd7f433ff0370746ba
isolated additive operator SHA256: fcb79e9dc4b873832e18e1fde16f0ba900374a08d62d0fc8b9b624a40ec1cd17
```

The 85-file PR source stage **must not be selected wholesale**. It diverges from the actually selected Grok 4.7 and companion native release in nine files. The only reviewed additive effect is replacement of the `OPERATOR_INSTRUCTIONS` string in the selected operator module. It must preserve every executable function and the selected Grok 4.7 binding. No new root, token authority, broker, lease, queue, retry, auth, watcher, or publication plane is permitted.

## Gate A — protected merge and custody

1. Confirm **PR #1694 is merged** using GitHub, record the actual merged commit SHA and its required CI/merge-queue receipt. Do not substitute auto-merge being enabled, a successful pull-request CI run, or source approval.
2. Fetch protected `master` into the authorized Mastermind checkout; ensure the merged source contains `ops/native_fabric/quota_continuity/candidate/fabric_operator_client.py` with the exact candidate SHA256 above. Do not assume a historical PR worktree is the protected branch.
3. Confirm the existing M2 Claude and Codex user-home skill installers are still `READY`; refresh only the missing skill guide through their versioned skill-only installer if needed. Preserve `~/.claude/settings.json`, `~/.codex/config.toml`, the global instructions, hooks, and the native subagent limits (Claude 12, Codex 32/33). A new session must separately demonstrate loading.
4. Freeze the actual live `native-code-releases/CURRENT.json` generation and sequence and compare against source review. If changed from the pinned source, **stop and requalify against the new selected generation**; never replace `CURRENT.json` to make a test pass.

## Gate B — deterministic offline qualification (executable now)

In a verified, authorized M2 checkout containing this release-prep kit:

```bash
KIT="$HOME/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08"
SCRIPT="ops/native_fabric/delegation_access/qualify_release.py"
CANDIDATE="ops/native_fabric/quota_continuity/candidate/fabric_operator_client.py"
SELECTED="09b1ff4204c49acc71bb228751c4efefc22c70c89092734d9ea2fafe3fff1a49"

python3 "$SCRIPT" \
  --installed-store "$KIT/native-code-releases" \
  --candidate-file "$CANDIDATE" \
  --expected-selected "$SELECTED"
```

The qualifier validates the versioned candidate SHA256, selected sealed 85-file code manifest, unchanged executable operator code/Grok 4.7 grant, and the single allowed `OPERATOR_INSTRUCTIONS` mutation. It creates an **isolated fake native store**, publishes and verifies both immutable generations using the incumbent owner, selects the successor with CAS, proves a stale CAS refused, and confirms that the live `CURRENT.json` bytes did not change. It neither reads provider secrets nor starts a worker.

Observed baseline M2 result on October 22: `QUALIFIED_ISOLATED_ONLY`; 85 native files; **one** changed file; successor operator SHA256 `fcb79e9d...`; scratch publish/verify/select and stale-CAS refusal passed; real live selected sequence remained 16. This was qualification against selected `09b1...`, **not** production activation.

Reject all changed/missing native closure entries, unreviewed candidate hashes, expired/wrong selected generation, missing Grok 4.7 binding, missing exact child-request instruction schema, symlinked candidate file, or any executable change other than the instruction literal.

## Gate C — protected-source staging, then the existing immutable publisher

Only **after Gate A is proven**, with the actual latest `SELECTED` verified, the release maintainer may construct a fresh, stage-only sibling workspace (new unique name, never overwrite an old stage):

```bash
git -C "$HOME/Documents/GitHub/Mastermind" fetch --no-tags origin master
PROTECTED_REF="refs/remotes/origin/master"
STAGE_PARENT="/Volumes/Mastermind/agent-workspaces/web"
STAGE="$STAGE_PARENT/pr1694-native-guide-release-UNIQUE"
python3 "$SCRIPT" \
  --installed-store "$KIT/native-code-releases" \
  --candidate-file "$CANDIDATE" \
  --expected-selected "$SELECTED" \
  --merged-repo "$HOME/Documents/GitHub/Mastermind" \
  --merged-ref "$PROTECTED_REF" \
  --stage-parent "$STAGE_PARENT" --release-stage "$STAGE"
```

`--merged-ref` is accepted only when contained in protected `origin/master` and that exact git object contains the pinned operator candidate. The tool rejects an existing stage, creates only a reviewed 85-file `source/`, `manifest.json`, and `qualification.json` in the sibling directory, and never publishes to the live kit. An independent release reviewer compares `manifest.json` to every staged file and rechecks the current-generation pointer. **Stage output is not permission to select.**

After the release owner has verified original-source custody, collision/lease status, reviewed stage identity, live selection preimage and required approval, use the existing native owner; do **not** manually copy individual code files into `ext/`:

```bash
GEN="ops/native_fabric/quota_continuity/rollout/native_generation.py"
python3 "$GEN" publish --source "$STAGE/source" \
  --stable-ext "$KIT/ext" --manifest "$STAGE/manifest.json"
# Capture the resulting NEW_GENERATION as a receipt.
python3 "$GEN" verify --store "$KIT/native-code-releases" \
  --generation "$NEW_GENERATION"
# Only the authorized owner, with a current CAS preimage and explicit release decision:
python3 "$GEN" select --store "$KIT/native-code-releases" \
  --generation "$NEW_GENERATION" --expect "$SELECTED"
```

The publisher and selector are distinct. After an actual owner selection, read `CURRENT.json`, `RELEASE.json`, and the new operator module hash back; verify the reported predecessor, monotonic sequence, all 85 files, and exact executable code closure. Existing running controllers remain bound to their original selected code. A CAS refusal or changed `CURRENT` freezes this lane; do **not** retry or change providers/carriers without reconciling the original effect.

Rollback, if the owning release decision requires it, is another explicit native generation selection **with the then-current successor as expected preimage**, not deletion of the previous generation, killing existing controllers, or writing flat `ext/` files.

## Gate D — real Claude / Codex / nested operator canaries

Preflight **after actual runtime selection**. Each canary has its **own verified original root and immediate parent identity**. A Web-authenticated account, skill name, old root string, host PID, synthetic receipt, or locally guessed `CODEX_THREAD_ID` is not identity or child-grant authority. Avoid borrowing another session's root. Use the existing Fabric client and existing session/worker admission. Do not mint credentials or force modes.

**D1: Fresh Claude principal.** Start an authorized new M2 Claude session, verify that its installed `mastermind-claude-fabric-delegation` skill was loaded by *that session*, and retain the session ID and skill source SHA256. Commission one low-risk C0 read-only Fabric worker using its actual root and immediate parent. Suggested task: compute the SHA256 of a literal innocuous text string supplied wholly within the worker packet; no filesystem secrets, live orders, external writes or deployment. Capture the same-ID task admission, **worker START**, completed terminal status, exact retained result response/digest, response readback by Claude, and principal acceptance. If admission rejects, record the refusal rather than retrying with a new run ID.

**D2: Fresh Codex principal.** Start a distinct M2 Codex session; verify native skill-catalog discovery **and actual loading** of `mastermind-fabric-delegate` (mere presence on disk is insufficient). With Codex's separately verified native root and immediate parent, commission a separate C0 read-only Fabric task and consume it back through the same route. Require the same START/status/result/digest/principal-acceptance evidence as Claude. Do not change Codex's 32/33 native agent settings; native `spawn_agent` is not a Fabric worker.

**D3: Admitted GLM/Grok domain operator.** The original principal verifies the root authorization, actual allowance, per-run capsule support, and a legitimate need for one bounded child. A positive grant of at least one child and enough lifetime for lease + task + return is required. Commission one `domain_orchestration` C3 operator with a bounded child request; the incumbent operator/lease owner binds support, root, operator ID, lease, account, model, packet and budget. When `mastermindStudio` tools are actually visible to that operator, it calls `fabric_operator_scope {}` and, if admitted, `fabric_child_request` exactly once (C0/C1), with the **original root** and **operator run as immediate parent**. Follow the **same ID** with child status/result, read its bytes, and `fabric_child_acknowledge` using the returned SHA256. The operator returns its findings and child digest to the original principal; the principal separately reviews/accepts the operator result. Ordinary Fabric-spawned leaves have no recursive delegation grant. A Grok 4.7 model binding alone is not a capsule grant.

**Minimum canary proof:**

| Case | Required evidence |
| --- | --- |
| Claude -> leaf -> Claude | Session skill-load; verified distinct root/parent; admitted START; terminal result; exact digest consumed by Claude; principal acceptance |
| Codex -> leaf -> Codex | Native skill discovery *and load*; separate verified root/parent; START; exact retained result; principal acceptance |
| Operator -> leaf -> operator -> principal | Root authorization; positive capsule/budget; child START and result; same-operator digest acknowledgment; operator START/result; original-principal acceptance |
| Production selection | Protected merged source; qualified source closure; immutable code generation publication+verify; actual CAS selection readback; no mixed-code regressions |

All three cases are **real** actions against the selected generation, not fake test packets or assertions over untrusted JSON. A failed, refused, orphaned or effect-unknown request stays on the original run ID; no second carrier, blind retry, account pivot or manual lease cancellation.

## Gate E — post-run receipt checks

Save bounded, *sanitized* returned tool receipts from the existing Fabric and operator owners, with one report per release. See `ops/native_fabric/delegation_access/canary_receipts.py`. It expects:
- the actual protected merged SHA and selected runtime generation;
- independently observed source/selection provenance;
- separately verified root and immediate parent for Claude, Codex and operator;
- for each of four run IDs (Claude leaf, Codex leaf, operator, its child): exact lineage, START receipt, terminal result, reviewed parent-return digest, principal acceptance and selected generation;
- the operator's scoped positive child budget and its exact digest acknowledgment to the same operator.

Run:

```bash
python3 ops/native_fabric/delegation_access/canary_receipts.py --receipts /path/to/sanitized-runtime-receipts.json
```

The parser rejects duplicated JSON keys, mismatched roots/parents, missing START, QUEUED-as-DONE, missing/changed response SHA256, missing return acknowledgment, absent/expired admission evidence, or missing acceptance. Even `ASSERTIONS_PASS_PROVENANCE_NOT_VERIFIED` **does not prove** that the supplied JSON was authentic: the release owner must cross-check each run and digest directly with the canonical Fabric ledger and actual native recipient and runtime selection. Never fabricate canary JSON from the test fixture or claim that passing unit tests verify live execution.

## Verification and closeout rules

- CI: `python3 -m pytest -q tests/test_fabric_delegation_release_prep.py` and required repository Linux CI. The fixture uses an isolated fake 85-file native store, never the user's live runtime.
- Good outcomes: protected merge; independently reviewed exact resulting release manifest; qualified publication and CAS readback; all real principal/worker/return/ack/acceptance canaries; durable verified evidence linked from the original PR and owning release workstream.
- Held outcomes: merely successful PR CI, installed user-home skill, locally imported operator module, fake-store CAS, reviewer APPROVE, or task status QUEUED/RUNNING.
- Failure handling: preserve original run ID, root/parent and effect evidence; reconcile original target. Missing authorization stops only that lane; do not create new credential, operator, queue, state registry or watchdog.

**Go/no-go now:** isolated release qualifier and structural canary tests can be ready before merge. The live release must wait for the actual protected merge and current selection requalification. This kit grants no new runtime permission.
