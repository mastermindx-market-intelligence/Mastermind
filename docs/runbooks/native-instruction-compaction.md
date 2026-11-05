# Native instruction compaction through the existing writer

This is an opt-in rendering profile for `scripts/project_execution_brief.py`, not
another installer, policy owner, startup hook or execution gate. The accepted
protected policy and actual host grants remain controlling. The shorter profile
is `docs/NATIVE_EXECUTION_BRIEF.md`; the renderer is pure
`scripts/native_instruction_compaction.py`. A source merge alone installs neither.

## Scope and ownership

Parent: Mastermind #917; existing task tree
`docs/superpowers/plans/2026-11-02-delivery-turnaround-execution.md`, nodes
P2.C2.N1-N4. Operation: `native-instruction-compaction-20261105-web-001`.
The active #2064 supplier owns the policy counts, root AGENTS.md/CLAUDE.md,
full account instructions and existing installer changes. This additive profile
changes none of those paths and does not turn its proposed policy into law.
Do not install either source over a live or uncertain instruction writer.

## What changes and what does not

The core brief is 8,101 UTF-8 bytes / 134 lines after the fenced-example repair, versus
24,048 bytes in the same-pin canonical full account brief: 66.31% fewer source
bytes. This is not a measured reduction in total model context or elapsed time.
Repository, ancestor, plugin, hook and retained host-specific instructions may
still load. A Markdown import that loads the old text is not a context saving.

A plan replaces one exact reviewed `mastermind-assigned-execution-v1` block.
Historical blocks are preserved unless explicitly selected by eligible marker
AND exact reviewed whole-block SHA-256. Marker eligibility is not deletion
permission. Unknown content, storage controls, native consent, Parall isolation
and continuity/adapter instructions have no generic retirement path. Malformed,
quoted, fenced-example, nested, duplicate, changed or unreviewed selected blocks
are refused. Ordinary Markdown backtick/tilde fences are conservatively tracked;
a shorter or differently typed closer cannot expose a quoted marker for deletion.
An absent selected historical block is idempotent, not permission to delete
something else. UTF-8 byte counts, before/after identities and diagnostics are
returned without changing any file or claiming native loading.

The older unmarked temporary storage exception is only an advisory. The renderer
neither decides mount state nor deletes it. Retire it separately through the
existing writer only after permitted inspection, actual condition evidence,
semantic review and an exact current preimage. A reported inspection refusal
must not be replayed through a different tool, account, host or operator.

## Use the existing owner

1. Reconcile the current source, target and active writers. Follow actual denials,
   pending effects and installed-source requirements. Select an authorized exact
   native instruction target; this utility does not enroll missing host files.
2. Read the permitted target and approved source brief once. Review the full old
   managed block and each proposed retirement. Check that every obligation has an
   immediate or appropriately task-scoped replacement. Record the exact reviewed
   digests in the existing operation evidence, not a new fleet registry.
3. Call `plan_compaction` with the full target preimage, brief identity, reviewed
   main-block identities and optional retirement mapping. Review its returned
   text, remaining diagnostics and byte delta. Unknown host-specific text must
   remain byte-identical. A digest identifies content; it grants no authority.
4. When installation is authorized, hand the planned text and full preimage to
   the existing `project_execution_brief.apply(path, text, expected_sha256,
   backup_dir)`. Do not add another file-writing service or alter native trust.
   The existing owner creates the private backup, rechecks the target, preserves
   its mode, replaces it and verifies readback. Its checks are not a filesystem
   CAS transaction or a substitute for excluding concurrent writers.
5. Record before/after hashes, backup identity and exact readback. Repeat-preview
   should be unchanged. For rollback, reread the current target through a permitted
   path and use that same existing writer with the verified after-hash and original
   backup. Never overwrite a newer target or retry an uncertain write.

Python API composition, with all uppercase names supplied from actual reviewed
operation evidence rather than computed-and-assumed approval:

```python
from scripts.native_instruction_compaction import plan_compaction
from scripts.project_execution_brief import apply

plan = plan_compaction(
    ORIGINAL_TEXT, APPROVED_BRIEF, PROFILE,
    expected_preimage_sha256=REVIEWED_FILE_SHA256,
    expected_brief_sha256=APPROVED_BRIEF_SHA256,
    reviewed_managed_sha256=REVIEWED_MANAGED_BLOCK_SHA256S,
    retirements=REVIEWED_RETIREMENT_MARKERS_AND_SHA256S,
)
# Preview and source/host authorization precede the existing owner's write.
receipt = apply(TARGET_PATH, plan['text'], plan['before_sha256'], BACKUP_DIRECTORY)
assert receipt['after_sha256'] == plan['after_sha256']
```

The existing `--brief` CLI supports core-only source selection. Its original
legacy-block behavior remains its own contract; use this explicit renderer when
exact whole-block retirement evidence is needed. A later ordinary full-brief
installation can expand the file again, so the operation's normal consumer must
select this compact source deliberately. This PR does not silently change the
installer default while #2064 owns that path. Consolidating the accepted default
is a follow-on integration, not an installed behavior claim in this source slice.

## Fresh consumer acceptance, not hidden-instruction disclosure

Use a legitimately authorized native session on the intended host/account and
workspace. Do not launch Codex/Work or spend credits merely because this runbook
exists. Do not require verbatim disclosure of hidden instructions; observe the
correct next action and ordinary native instruction-loading diagnostics.

| Case | Required observable behavior |
|---|---|
| Small reversible source fix | Starts the assigned edit/tests without a redundant owner or top-level-reviewer ceremony |
| Required native review | Applies the accepted actual surface policy; never calls self-review independent |
| Pending CI | Preserves exact head/run and continues useful independent work; consumes the original result |
| Original author archived | Recovers the current frontier and next permitted action without demanding the old chat |
| Real active writer | Preserves actual custody; no inferred takeover |
| Explicit action denial | No same-effect alternate-tool/account/host replay; independent work may continue |
| Interrupted modifying call | Reconciles the original effect; never treats missing short-list output as absence |
| Missing optional Wake | Uses a separately admitted foreground path without claiming idle wake |
| New source revision | Requalifies affected evidence only; no history-wide rescan or empty CI restart |
| Product component done | Continues the unfinished original user journey rather than declaring whole-product success |
| Resume or compaction | Preserves latest accepted work, DO_NOT_REDO and uncertainty; observes selected instructions |
| Rollback or newer host edit | Uses exact current preimage; preserves newer text and actual human consent |

Measure comparable tasks on the same actual consumer: effective loaded bytes,
first useful action, unnecessary approvals, redundant tool calls, completion,
accepted outcome and regressions. Static tests are not model adherence; fewer
bytes are not faster streaming. Record installed, loaded and behavior-proven
separately. Stop only the failed rollout lane, not independent source work.

## Official loader references checked November 5, 2026 UTC

- OpenAI: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Anthropic: https://code.claude.com/docs/en/memory

Codex's global/project discovery and effective overrides must be inspected on the
actual consumer. Anthropic recommends concise instructions and explicitly notes
that imports organize files but do not reduce loaded context. The existing
`scripts/audit_execution_instructions.py` reports static eligibility only; do not
promote its result to runtime proof or impose it as a new startup gate.
