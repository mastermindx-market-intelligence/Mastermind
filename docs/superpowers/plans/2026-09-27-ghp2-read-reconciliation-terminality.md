# GHP2 read-only reconciliation terminality repair

Parent: browser-continuity-convergence-20260927-astra-001. Review/repair operation browser-ghp2-core-review-20260927-astra-001, isolated registered workspace on exact incumbent #409 head55155d33a51921a3b6d2cae2db49d31703a80b8a. Protected procedure c01d890f6536539496f2d6744f3143ff49da296d, compatible Skillpack1.0.1/bootstrap1. No source-writer transfer or independent approval is implied by this proposal. Direct retained work reason: bounded effect-semantics judgment and LOWER_TOTAL_OVERHEAD for the minimal repair.

## Finding and red evidence

The existing three-module core baseline passes257 tests. Two independent added cases fail while all257 controls pass: after the initial possibly delivered mutation returnsEFFECT_UNKNOWN, calling read-only reconciliation before original request settlement returnsNOT_APPLIED with reconciled=true. The same original request then settlesAPPLIED without any second mutation. A reconstructed gateway with the SAME owner has identical false-negative behavior.

Cause: _reconcile returns the native negative observation verbatim; the native port's absence/current-history proof is only a snapshot, not request terminality. The prior55155 repair corrected the immediate _commit return, but _reconcile has no durable native-attempt terminality evidence to justify a later negative settlement.

## Minimal selected repair

In the existing _reconcile path, require exact completeAPPLIED evidence to settle; otherwise use the existing _effect_unknown_receipt helper. Preserve token-bound historical lookup, caller authentication, no write-authority lookup, no new effect or retry, and no new ledger. Pre-dispatch/typed local refusalNOT_APPLIED in _commit remains unchanged. The canonical native observation contract and schemas remain unchanged.

Compatibility: a never-executed but expired prepared token can still reconcile/read, but a negative GitHub snapshot alone returnsUNKNOWN instead of a terminal no-effect claim. Without an upstream owner-native terminal-no-send receipt, stateless reconciliation cannot distinguish that case from an earlier possibly delivered request. Do not persist an in-memory guess or add a second attempt store to keep the old optimistic test green.

Tests: original-call delayed settlement; same and reconstructed gateways; current/unavailable/moved organizational write authority; expired execution token; all existing core/compiler/release tests. This repairs the read-only reconciliation path only. It is not full independent approval or release of the8-file app and does not close every possible source/runtime/deployment gate.

## Executed qualification

- Original unchanged baseline:257PASS. The independent two-case reproducer added two failures while all257 original controls passed; it samples reconciliation before settling the FIRST pending request and then proves that same request becomesAPPLIED with native mutation count1.
- Expanded source regressions:7FAIL before repair, covering same/reconstructed gateway, current/unavailable/moved write owner and expired execution token.
- Minimal production change: nine added lines in the existing _reconcile path. Existing expired-token test intentionally changes its negative-snapshot expectation toUNKNOWN; historical reading remains available, but no durable terminal-no-send proof is invented.
- Final owner/compiler/release matrix:264PASS/0FAIL/0ERROR/0SKIP, exit0. Existing immediate typed-pre-sendNOT_APPLIED controls remain green. Remove only the new guard: all7 discriminators fail; restore exact production bytes: all264 pass again.
- Evidence root: /Volumes/Mastermind/evidence/browser-ghp2-core-review-20260927-astra-001. Files baseline.log, review.log/.xml, terminality-red.log, terminality-green.log/.xml, terminality-mutant.log, terminality-final.log/.xml, and independent standalone reproducer.
- This is focused semantic repair proof, not exhaustive approval of every8-file behavior, current-base hosted CI/security, source-writer release, merged source, installation or real GitHub commit proof. No live credential or remote mutation occurred. The source author of this proposal does not independently approve it. All old incumbent writer/transport/effect gates and original #409 carrier remain intact.
