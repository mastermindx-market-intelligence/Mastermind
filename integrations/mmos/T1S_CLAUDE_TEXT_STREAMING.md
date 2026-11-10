# T1s — Claude driver live answer-text streaming (2026-11-10)

Patch: `integrations/t3/upstream_patches/claude_text_delta_0770446.patch`
(sha256 `8ca39b00add5b6813db79bf4e0c3e3a32bd670dfa883b0279496db9fc8043d56`; applies
cleanly on the bare pin `0770446` and on pin+`mastermind_admission_0770446.patch`;
details and test commands in `upstream_patches/MANIFEST.md`, T1s section).

## What the patch does, plainly

The Claude driver (`claudeAgent`) used to emit answer text once per completed content
block. Now it mirrors what the Codex adapter already did: `text_delta` stream frames
update ONE live assistant item per API message id (`assistant-text:<message.id>`),
coalesced at 50 ms. When the SDK's `assistant` snapshot for that message id arrives,
it completes the same item with the snapshot's authoritative text — no second item, no
re-emit. If the turn ends without a snapshot (interrupt), the accumulated partial text
settles as one completed item at turn finalize. Streamed text reserves its ordinal at
the first delta, so text keeps its place before same-snapshot tool items (the incumbent
emitted tool items first). Sub-agent (parented) frames and synthetic notices are
excluded, and replayed history never streams.

## What the Chairman sees differently

- Thinking and tool liveness: unchanged.
- Answer text: now grows live in the transcript — **but only when the incumbent
  paragraph streaming filter finds a release boundary**. This filter
  (`assistantStreaming.ts`, `splitBufferedAssistantText`, the default "paragraph"
  mode) releases running text ONLY at blank lines, list-item starts
  (`/^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]/`), closing code fences, or top-level ATX
  headings, with a 400 ms rate limit. Completed text always passes.
- Honest live result: with the pinned proof prompt ("Count from 1 to 40 … one number
  per line, with a short word after each") glm-5.3 answers `"1 one\n2 two\n…"` —
  tight lines, no boundary — so every running update is held by the filter and the
  text still appears at completion (2 text changes per turn, same as stock). With
  blank lines between numbers, the same patched server shows live growth
  (85→267→478→485 chars across one turn; `stream_diag` evidence). Demonstrated at
  source level: counting style → `ready:""`; blank-line style → text released;
  list style → text released.
- So: the patch makes the adapter stream; the filter decides what the Chairman
  watches. Most prose answers (paragraphs, lists, code) cross boundaries and will
  now stream; tight single-token lines will not.

## Cost

- Events per turn: adapter emits a coalesced (50 ms) running update per streamed
  item, plus one completed burst per message. Delivered client events are bounded
  downstream by the filter's 400 ms rate limit; running `node.updated` frames are
  dropped by the filter (as for Codex).
- Store growth: none in item count — one item per API message id, same as the
  incumbent's per-message item; only live `turn_item.updated` projection events
  increase.

## Not covered

- The paragraph filter itself is untouched (no new streaming mode, per lane brief).
  Boundary-free answers still appear only at completion; a filter change is a
  separate decision for the principal.
- Thinking deltas, tool streaming, other adapters: unchanged. Only `claudeAgent`.
- Desktop/e2e suites not run; unit suites for the adapter + affected orchestration
  files are green (351/351 + 107/107 + 99/99, logs in evidence).
- Live proof used a dev server on port ≥3790 with the built web client; the pinned
  ≥8-changes PASS rule fails for the counting prompt for the filter reason above
  (honest FAIL, mechanism demonstrated).

## Carrying into a T3 bundle

Same mechanism as the admission patch: this file is a pinned upstream patch under
`integrations/t3/upstream_patches/` recorded in `MANIFEST.md`; the bundle builder
applies it (with `mastermind_admission_0770446.patch`, disjoint files) to the donor
pin at build time. The lane ships the patch + tests + this note; performing the
bundle carry is the principal's step, not this lane's.

## Evidence

`~/.mastermind/mmos_evidence/t1s-20261110/` — red/green + suite logs, before/after
stream JSON, diag, tool-between-text and interrupted-turn proofs with reload
comparisons.
