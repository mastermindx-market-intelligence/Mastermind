# REVIEW_RESULT

## Bounded read-only source review

**Subject:** `Mastermind@7ff6ca1ecfe1aa2c9231cf18bac483660874cd55` entrypoint/projection packet
**Files reviewed (against supplied hashes, not re-fetched):** `AGENTS.md`, `CLAUDE.md`, `docs/DELIVERY_WORKFLOW.md`, `docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md`, `scripts/project_execution_brief.py`, `tests/test_execution_brief_projection.py`, `tests/test_execution_policy_contract.py`
**Inputs trusted as supplied.** Not executed, edited, or written to; no tool calls beyond this review text.

---

## Blocking findings

**NO_BLOCKING_FINDINGS.**

The packet removes the redundant ceremony the brief targets without inventing authority, claiming permanent Web-session availability, forcing unrelated deployments, or bypassing consent. The Markdown projection utility satisfies the eight safety properties listed in the brief.

Per-property assessment of `scripts/project_execution_brief.py`:

| Property | Evidence | Verdict |
|---|---|---|
| Exact preimage | `expected_sha256` required for `--apply`; compared before any write (`apply()` lines check `before != expected_sha256` → raise). | Pass |
| Selective managed-block replacement | Only the named `MARKER` / `MEMORY_MARKER` and `LEGACY_BLOCKS` are targeted in `remove_block`; for codex, only the explicit `CODEX_SECTIONS` set is retired inside the legacy heading. Modal/transport/adapter user sections retained by test `test_codex_keeps_modal_and_transport_instructions`. | Pass |
| Unrelated instructions preservation | Claude-profile test asserts the modal restriction, personal preference, and "Native model restriction stays." survive; codex test asserts modal, admitted carrier, and user data survive; memory test asserts pre-existing historical `EFFECT_UNKNOWN` line and `v1` header survive. | Pass |
| Backups | `backup` written via `'xb'` with `0o600` mode; collision handled by content-equality re-check; backup path keyed by `digest(abs_path)[:16] + before-hash`. | Pass |
| Idempotence | Early return when `current == new`; `test_projection_is_idempotent` confirms `project(project(x)) == project(x)` across all three profiles. | Pass |
| Readback | `after = digest(path.read_bytes())` followed by `if after != digest(new): raise RuntimeError`. | Pass |
| Failure handling | Multiple typed `ValueError` paths: non-`.md`/symlink/non-file target, preimage mismatch, duplicate managed block, unbalanced markers, reversed managed block, symlink re-check during prep, post-prep preimage check, content disagreement against existing backup. CLI `parser.error` for missing `--expected-sha256` / `--backup-dir`. | Pass |
| Race boundaries | `tempfile.mkstemp` in the target's directory + `os.fsync` + `os.replace` (atomic on POSIX); symlink and re-read preimage check between prepare and replace; `finally: temp.unlink(missing_ok=True)`. | Pass (with the usual TOCTOU window between the final preimage check and `os.replace`, which is inherent to the atomic-rename pattern and is the reason for the post-write readback) |

Per-line authority/consent/deployment assessment of the prose diffs:

- **Hierarchy rewrites (AGENTS.md, CLAUDE.md):** Replace `AI CEO — GPT-5.6 Sol` with role-based language; explicitly state "Role names do not grant permissions or override those actual controls" and "A model name, account or archived chat does not permanently occupy that role." No authority is claimed; the existing `authority_map.yml` / `packet_gate.py` / `governance.py` / Macro fleet guards remain the source of authority. ✓
- **`Session lifetime and acceptance scope` (AGENTS.md and CLAUDE.md):** States "ChatGPT Web sessions are ephemeral… a Meta-CEO title does not make an old chat available to receive work." Does not promise any persistent availability. "Acceptance follows the assigned effect" prevents unrelated deploys. "exact-session proof obligations… are not cleared or transferred" preserves consent/evidence fences. ✓
- **Completion block (AGENTS.md):** "A source-only change does not trigger an unrelated runtime deployment" + "Do not substitute whichever unrelated commit happens to be the newest `origin/master`." ✓
- **`## Model and delegation policy` (CLAUDE.md):** "they are not permission to spawn Claude-native children. Observe the host's actual native-model, capacity and tool grants." This explicitly fences the previous Fabric-only default and defers to the host's actual grants rather than asserting them. ✓
- **`docs/DELIVERY_WORKFLOW.md` step 7:** Changes `merge_sha="$(git rev-parse origin/master)"` to `gh pr view --json mergeCommit --jq '.mergeCommit.oid'` with `test -n "$merge_sha" && test "$merge_sha" != null`. The operation's own merge commit is bound to the deploy, not arbitrary `origin/master` HEAD. Conditional "Deploy only when the assigned change requires runtime rollout…" preserves consent for production restart. ✓
- **`docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md` rewrite:** Removes the persona-bound "Your primary job is not to code" / "No one-shot strategic builds" / 12-step "Required sequence for major programs" headings. Replaces with scope-bound assignment language. Retains "An explicit permission or safety refusal ends that effect's retry. Do not change tools, accounts, models or carriers to obtain the refused effect" — i.e., refusals are not worked around. ✓
- **`MEMORY_NOTICE` (in `project_execution_brief.py`):** States the historical records "are not live authority, current permissions, active source leases…" and "A permissive local setting never proves that a real approval prompt can be bypassed." ✓

## Nonblocking observations

1. **`docs/DELIVERY_WORKFLOW.md` step 7 `gh pr view` invocation.** The example omits a PR selector, so it relies on `gh`'s branch-based PR resolution. In a script/CI context without an unambiguous current branch → PR mapping, this can be non-deterministic or prompt. The pattern itself is correct; an operator-driven explicit PR number would be safer. Affects documentation, not the patch's safety properties.

2. **Codex projection discards preamble text under the legacy heading.** Inside `project()`, for `'codex'`, after splitting on the legacy heading, `re.split(r'(?m)^(?=##? )', rest)` puts any text between the heading and the first `# ` / `## ` into `parts[0]`, which is then dropped. The inline comment ("Preserve modal consent, actual transport instructions, native restrictions and unknown user text") refers to *sections*; the preamble paragraph(s) under the retired heading are lost. This appears intentional (the entire legacy section is retired) but the supplied tests do not exercise a meaningful non-legacy preamble under that heading, so a future accidental user paragraph would disappear silently. A defensive tightening would be to retain `parts[0]` when it does not begin with the legacy-heading siblings.

3. **`main()` reads `--brief` without existence/emptiness checks.** `args.brief.read_text()` raises `FileNotFoundError` rather than a typed, actionable error. An empty `brief` produces an empty managed block (valid syntax, semantically empty). Cosmetic UX, not a safety issue.

4. **`memory` profile leaves `LEGACY_BLOCKS` untouched** while removing only `MEMORY_MARKER`. This is consistent with the comment about Codex memory v2 having a different layout, but a caller passing a memory profile over an `AGENTS.md`/`CLAUDE.md` would silently keep the legacy blocks. The CLI currently does no profile-vs-target sanity check beyond the `.md`/symlink filter; the supplied tests assume distinct files per profile.

5. **`apply()` re-checks `path.is_symlink()` *after* temp write** but not *between* `temp.chmod(mode)` and `os.replace`. The `digest(path.read_bytes()) != before` check at the same point covers content changes; only TOCTOU race for replacing `path` itself with a symlink remains. POSIX `os.replace` is atomic against symlink swap in practice because it uses `rename(2)`, which follows symlinks but the source is a real file; this is the standard pattern.

## Limitations

- Read-only review against the supplied diff and full-file text; no execution or runtime testing was performed and none was permitted by the packet.
- The "CURRENT IMMUTABLE SUBJECT HASHES" block was not re-verified against rebuilt contents; treated as the trusted identifiers the packet declares.
- The separately reviewed auditor/CI classifier is out of scope per the packet and was not inspected.
- Supplied tests were inspected as evidence; test outcomes were not observed.
- I did not inspect other instruction files that the projection utility might be aimed at (e.g., other worker-account kernels) — only the four subject files plus the utility/tests were in scope.

Reviewed evidence is not release permission or fresh-model adoption, as the packet states.
