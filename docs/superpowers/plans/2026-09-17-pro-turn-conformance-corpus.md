# Pro-turn conformance corpus implementation plan

> **Historical status (qualified 2026-11-05).** This file is the original
> dated implementation plan of 2026-09-17/18 for operation
> `pro-turn-conformance-corpus-20260917-sol-001`. Its Goal, Authority,
> Source, Architecture, checklist and Stop-and-continuation wording is
> preserved as dated history and is NOT an active commission, routing
> instruction or gate list today. The actual current source custody is
> recorded under "Current custody and provenance" below, and the
> "Current blocked checkpoint" section below is historical too. Nothing
> in this file re-authorizes the refused append, the removed workspace, a
> model or provider run, a source publication, or a release.

**Goal:** make 20 public synthetic continuation/stop decisions consumable and falsifiable by the existing Agent Evaluation corpus verifier and TC3 scorer.
**Authority:** current Chairman instruction to continue implementing Pro-turn productivity; same program record on #706. Operation `pro-turn-conformance-corpus-20260917-sol-001`. (Original dated 2026-09-17 authority wording, preserved as history; it is not a current commission.)
**Source:** protected `320f586126b7c82c843ef17612f12d40d20a42e0`, Skillpack 1.0.1. Direct execution: LOWER_TOTAL_OVERHEAD. This branch owns the new public corpus root, its tests/plan/evidence, and the narrow existing inertness-fence ratchet required to admit those paths; it owns no evaluator, scorer, runtime, lifecycle, or model-routing code.
**Architecture:** use `corpus/agent_eval_pro_turns/` with the existing explicitly supplied `--corpus-root` interface. Preserve the original frozen C0 corpus and all scorer, store, provider, lifecycle and authority code. Reuse `mastermind.carrier_protocol_compliance.v1`; no second evaluator, metrics store or stop controller. The only shared-file edit is the existing R0 inertness fence: ratchet this exact plan/test plus the new corpus prefix through its existing filename guard under the Chairman-authorized operation; do not weaken its control-plane/config prohibition.

## Contract
The model receives only the input case and declared action choices. Expected answers and rationales are separate non-model-visible fixtures. All scenarios are synthetic/public, text-only and NO_EFFECT_ONLY. Source references bind protected law, not draft #706 procedure. Case identifiers and authority do not represent live assignments. Exact next-action choice is mechanically scored; rationale quality remains UNKNOWN under TC3. No model/provider run, productive duration, hidden-token usage or adoption is inferred from test results.

## Implementation order and proof

*Original dated 2026-09-17 plan checklist, preserved as history. Its
unchecked state records what the plan proposed then; it is not a current
gate list. The last item's independent-semantic-review condition is that
plan's own dated condition -- it is not established here as a mandatory
independent source-release review, and no reviewer is assigned by this
document.*
- [ ] Write failing tests for all 20 scenarios, corpus/CLI integrity, hidden gold, strict TC3 scoring, every wrong action rejected, no invented reviewer and observable boundaries.
- [ ] Write source-grounded public input/expected fixtures and README. Commit fixture bytes first so later scenario references point to a real immutable ancestor.
- [ ] Build scenario/manifest documents through existing constructors; require zero effects, zero tools and explicit corpus-root selection. The short selection exercise's execution ceiling is not a production Web-turn ceiling.
- [ ] Run existing corpus CLI and TC3 consumer tests. Tamper one copied fixture and require refusal; wrong answers must never pass. Confirm the original C0 corpus remains unchanged and valid.
- [ ] Publish the original operation branch as a bounded candidate. Independent semantic review must verify the gold decisions before any admitted fresh-model study consumes them.

## Stop and continuation

*Original dated 2026-09-17 stop/continuation wording, preserved as history.
It is not a current continuation instruction; see "Current custody and
provenance" below for what actually happened to this operation.*
No source-law update, #706 workspace takeover, runtime install, credentials, provider launch, actual model comparison, automatic ranking or native ChatGPT productivity claim. Outcome of this slice is a machine-readable conformance corpus, not completion of the parent productivity program. Continue parent release integration once independent review/custody gates clear. Keep all completed transport/repair work do-not-redo.

## Current blocked checkpoint (historical; superseded by the publication record below)

*Preserved verbatim as dated evidence of what was blocked on 2026-09-17/18.
Its present-tense workspace/resume instructions are NOT operative: the
source was subsequently published and the original workspace was removed
(see "Current custody and provenance" below). The refusal it records
stands as evidence of what was refused at that time; it is neither
replayed, reversed nor re-authorized here.*
Tests were written and executed before fixtures: six intended missing-corpus failures, one original-corpus regression PASS. The 20 synthetic case definitions are drafted in the original operation's temporary `build_fixtures.py` on Studio. The next append, which would serialize fixtures, was refused by the platform with `couldn't determine the safety status`. Same-file readback confirms that append is absent; it was not executed or rerouted. No fixture-generation effect, corpus verification success or model behavior result is claimed.
The registered source workspace retains this plan and `tests/test_agent_eval_pro_turn_corpus.py` as uncommitted work. No PR or remote branch was created for this slice. Keep the same operation and workspace; do not re-home or auto-retry the blocked write. Resume only after the actual platform/permission boundary is resolved. The original frozen corpus and scorer sources remain untouched. The schema requires a positive numerical max_tool_calls ceiling; a future text-only case must still admit no tool capability, not pretend the numerical ceiling itself grants a tool.

## Current custody and provenance (added 2026-11-05)

- **Publication.** The 20 frozen synthetic cases, their source-grounded
  fixtures, the corpus manifest, `README.md`,
  `tests/test_agent_eval_pro_turn_corpus.py` and this plan were published
  on the original branch at
  `89aac2f8f5700a69cd1670e3eee124c61093a61a` (original PR #798).
- **Terminal builder STOP / writer release.** PR #798 comment 5723823291
  records the source published and `REMOTE_COMPLETE_VERIFIED`, plus
  `RECONCILED_NO_OPEN_EFFECT` and the terminal builder STOP with
  `BRANCH_WRITER_RELEASED`.
- **Workspace removal.** PR #798 comment 5723827681 records the original
  workspace `APPLIED` and then `REMOVED`. That removed workspace is not a
  destination and is not restored.
- **The blocked checkpoint above stands as dated evidence.** The refusal it
  records (`couldn't determine the safety status`) is preserved, not
  erased, and is not claimed to have been reversed. No fixture-generation,
  corpus-verification, model-behavior or provider effect is claimed from
  it here, and the blocked append is not replayed.
- **A2 is settled and retained.** PR #692 actually merged on 2026-09-19 as
  `9e796168b467c17d9853f139c4e4a6ccdf3a3a87`; its earlier wait wording is
  settled, and the accepted A2 host-bridge work stays unchanged.
- **#917 stays excluded.** The later three-case expansion proposal
  (PR #798 comment 6070835729) is outside this operation and grants
  nothing here.
- **Still separate.** The original plan's independent semantic review of
  the gold decisions, and any admitted fresh-model study, remain separate
  future obligations. No model run, served-model identity, reviewer
  identity, runtime installation, source publication or release is
  asserted by this qualification.
