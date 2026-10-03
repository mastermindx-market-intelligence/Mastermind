# I3-W0 execution candidate and actual owner-input evidence

Parent: Mastermind PR #1183. Commission: `11a64ce93328d5248967987be0d2a51883765797`. This directory is subordinate execution evidence, not another masterplan or canonical workstream.

Read `ADMISSION_STATUS.md` for the current gate/return state, then `W0_ADMISSION_CANDIDATE.md`, `TRIAL_OWNER_ADMISSION.md` and `W1_IMPLEMENTATION_PACKET.md`. The independent review must distinguish proposed interface admission from executed evidence.

## What actually ran

Four unchanged tests from the pinned Macro FIF module passed: governed AAPL values, unlinked-vintage refusal, source/system point-in-time cutoffs, and statement/query source reconciliation. Three earlier setup/input-snapshot failures are preserved. No source or frozen test was changed.

Two additional source-native queries produced immutable responses: the same-filing AAPL annual revenue pair and the known unlinked-assets refusal. These are owner inputs, not an accepted I3 transition, production emission, economic classification or prediction. The method/version/requests were captured before the queries; the capture boundary states what remains unbound.

`evidence/targeted-source-delta.json` compares only the ten named W0/W1 owner dependencies with the audit pin. Its scope is not a whole-repository or active-writer census. `evidence/*.response.json` contains the exact owner bytes; receipt SHA-256 must match those bytes, not reformatted JSON.

To independently replay the unchanged owner tests and exact query bytes, run `python3 research/issuer_inflection/2026-10-03/w0/replay_owner_inputs.py --macro-git-dir <existing-Macro-common-git-dir> --output-dir <new-scratch-directory-inside-admitted-workspace>`. The script exports only the fixed accepted source, restores both exact Data OS reference inputs, isolates HOME, captures the driver hash before execution, preserves failures, and compares original owner response bytes. It does not create a Git checkout or write to the owner.

Run the capsule's local integrity check with `python3 research/issuer_inflection/2026-10-03/w0/verify_evidence.py`. It is a non-mutating verification of published evidence, not I3 acceptance or a replacement for the actual owner tests.

## Open gates

Independent exact-head review, source-owner/interface acceptance, actual canonical workstream/runtime/capture binding, closed derived schema acceptance, and connected W1 implementation/preview remain open. No new canonical schema is registered here. Full W0–W11 remains governed by the original audited plan.

## Candidate contract checks

Run `PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/test_candidate_schema.py` for the 29 current synthetic shape/compatibility tests. They reject closed-shape and authority/emission violations while explicitly demonstrating the unresolved semantic gates. They do not evaluate AAPL, classify an inflection, resolve a real rights decision or grant schema admission.

## R1 precision correction

`R1_RESOLUTION.md` records C2's real caller-context defect and the bounded exact-rational repair proposal. Run `PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/test_comparator_policy.py` for the 16 numeric-policy tests. The pre-fix RED receipt and both corrected test receipts are retained in `evidence/R1-*.json`. This test-only math witness is not an I3 composer, financial owner, live signal or publication. External confirmation and W0 owner admission remain open.
