# Browser reconciliation recovery implementation plan

**Goal:** Read the existing durable result for one exact browser action after its execution capability expires or its owned process retires, without reopening execution authority.

**Architecture:** Preserve BrowserActionPort, BrowserRefCodec, and ActionArtifactStore. Separate read-only historical receipt resolution from live browser dispatch validation. Authentication and exact owner/project/action binding remain mandatory; no new ledger, browser owner, or retry route.

**Tech stack:** Existing Python 3.12 Workbench browser companion.

**Scope:** integrations/workbench_browser_mcp/browser_port.py and tests/test_workbench_browser_port.py on immutable #940 head b2fdb1d1d1584a53c5ac1f94e2da1c1fa7be9200. This workspace is an isolated repair proposal; no incumbent branch custody is assumed.

**Protected procedure:** fda6ed3911cdda24eb63b2ccbe1b174121cf404f; Skillpack 1.0.1/bootstrap 1.

## Constraints and review focus

- Execution still requires fresh browser/action references and exact live process identity.
- Reconciliation authenticates both signed references, their mutual digest binding, and the current caller/owner/project/host binding.
- Expired caller or owner scope never becomes a historical-receipt authorization.
- An unresolved prior effect remains EFFECT_UNKNOWN; read-only reconciliation never calls the relay.
- Wrong caller, owner generation, host, or tampered reference still refuses.
- Host reboot, owner-generation replacement, egress policy and login readiness are separate integration work, not silently accepted here.

## Task 1 — recover durable receipts after execution expiry/process retirement

- [ ] Add parameterized expiry/dead-process tests for APPLIED, NOT_APPLIED and EFFECT_UNKNOWN, asserting no second relay dispatch.
- [ ] Run the new tests against unchanged source and preserve the failing output.
- [ ] Add the smallest read-only historical validation path; leave live dispatch validation strict.
- [ ] Add refusal tests for tampering, changed owner/caller, expired authentication/scope, and attempts to execute old references.
- [ ] Run the focused owning module and complete browser suite in the repository-pinned test environment.
- [ ] Preserve exact diff, source hashes and test receipts; return the proposal to #940 without claiming release or runtime acceptance.

## Task 2 — investigate unresolved-effect barriers

Use the existing action artifact owner to test whether preparing a new action while an earlier browser action is uncertain can dispatch twice. Any repair must remain within that existing owner; do not add a parallel operation journal.

## Initial capability/collision ledger

#473 exact source review approved; Rust analyzer failed and release remains held. #940 has no submitted review. #663/#988 remain unreleased. The connected C3 Workbench exposes canary file/command actions only, no browser actions. GitHub owner-app search resolves to #409; no successor found in the bounded exact-name search. No production profile, credentials, service or browser process changed. A separate source-map inspection call was safety-blocked and is not retried through another carrier. No effect uncertainty exists for this session's own operations.

## Executed source checkpoint

- Original five-module core baseline: 42 PASS.
- Nine expiry/process-retirement cases on unchanged production source: 9 FAIL, expected closed browser/action/process refusal paths, zero collection errors.
- Minimal historical-receipt recovery repair: original six plus new nine tests PASS.
- Seven additional wrong-identity/tampering/current-auth temporal cases added.
- Complete nine-module Browser suite: 81 PASS; XML and stdout retained in the operation evidence root.
- Full repository pytest attempted: collection stopped with two errors, `tests/test_self_tune.py` (missing vendored `engine.signal_archive`) and `tests/test_single_name_factor.py` (missing vendored `lib`). No full-repository pass claimed.
- Independent resource-uncertainty probes: 2 FAIL. A second freshly minted action_ref dispatches again on the same browser after the first action is EFFECT_UNKNOWN, whether prepared before or after the first lost reply. Synthetic relay call count is 2, expected 1. The current read-only reconciliation repair does not change prepare/run behavior and does not fix this blocker.
- Preserve the existing action/effect owner. A durable resource-wide uncertainty barrier is required before authenticated activation; an in-memory flag, fresh operation ID, or another ledger is not acceptance.
- No production browser/profile/credential use, installation, remote source push or merge occurred. This is a source repair candidate, not an independently approved release.

Evidence root: `/Volumes/Mastermind/evidence/browser-continuity-convergence-20260927-astra-001`.
