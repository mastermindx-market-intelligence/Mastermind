# Codex Personal Pro readiness: protected test-fixture correction

**Scope:** provider-free test-only change to the existing Executive OS
readiness owner. No worker installation, credential, receipt, canary, routing
or production admission mutation.

**Source baseline:** protected Mastermind master commit
fd1159695b0491a1b2c8d3042dce1232ad8365b4. Protected skillpack law
content was unchanged relative to previously verified pin
386ab9336b50600f81d767474bf6b26479a5cb55.

## Production proof and remaining gates

The incumbent root-only approved Executive host bootstrap is installed under
release bcf4a2f72538682f2fbe4902f6417e59cd038678. A prior exact invocation
completed successfully. Subsequent root-level provider-slot-status showed all
four reviewed worker principal homes and credentials PRESENT with correct
private metadata. The existing provision-worker-auth.sh --verify-only succeeded
independently for company codex-01 and Personal Pro codex-pro-01/02/03.
These are credential-login proofs only, not inference readiness.

Original protected readiness receipts, read only through the canonical root
status owner, remained NOT_READY: company codex-01, Personal Pro 02/03 report
readiness_expired_or_insufficient_margin; Personal Pro 01 reports
readiness_receipt_not_passing. A non-secret historical composite validator
with allow_expired_readiness=True confirmed the original Personal Pro 02/03
receipts otherwise validated under the pinned source. This did not prove
their original *credential* deadlines are still eligible for a new canary.
The company-specific --renew-device-revalidation-sha256 option explicitly
requires the company principal and MUST NOT be used on a Personal Pro slot.

The ordinary existing provider_readiness.classify_refresh_eligibility
applies to a historically PASSING device-auth receipt on a Personal Pro slot
only when current auth/binary lstat identity remains exact, the reason for
strict refusal is expired readiness alone, the original credential deadline
is still valid with margin, and any new deadline does not extend the
predecessor credential deadline. It returns reuse status 4. The old failed
Personal Pro 01 receipt is ineligible for this path. Fresh provider identity,
root transaction admission, one-shot canary, archive, final receipt validation
and Chairman-approved specific expiry remain separate gates. No new expiry
or canary was invented or spent here.

## Five failing tests diagnosed and isolated

The current-master provider-free suite initially had FIVE failures:
- Two existing real-protected receipt tests T11 and T12 assumed tmp_path files
  always had the runner's primary os.getgid(). M2 test-volume files actually
  inherit the temp directory group. The real lstat_identity and protected
  receipt group check correctly refused identity_group_mismatch.
- Three tests for the sanitized provider-slot-status response used the
  ordinary runner's UID/GID to stand in for dedicated Executive worker
  service principals. The actual production gate refuses those identities;
  unit tests failed before reaching the intended status-output checks.

Corrections are confined to tests/test_provider_readiness_refresh.py and
tests/test_provider_slot_status.py. T11/T12 now bind the synthetic storage
contract to the actual temporary parent GID, retaining the unmocked real
lstat/group/mode/symlink check. Three status tests independently stub ONLY
their already-separate private home/credential metadata validators to test
redaction and routing; a new negative test explicitly proves the real
validators reject an ordinary unprivileged fixture for a reviewed Personal
Pro worker. No implementation owner, protected constant, worker lease,
allowance expiry or production control was altered.

**Verification:** RED = five focused failures on current master.
GREEN = all tests pass across original three affected modules and four
additional provider identity, terminal, same-generation, and invalidation
modules. Python compile and git diff --check pass. Independent exact-head
hosted CI/review remain gates before considering this source-only fixture
correction accepted.

## Avoidable actions

No Personal Pro credential should be reauthorized just because a non-root
file inspection says a protected home is missing; root-level readback
disproved that earlier claim. Do not repin the distinct Homebrew Codex binary;
the approved root-owned Executive binary matches protected SHA-256 and team
signature. Do not use an already expired readiness receipt as authority to
extend any credential expiry; reserve and fresh inference canary must remain
on existing owners with the exact Chairman-approved deadline. Executive
plugin backend_unavailable and the legacy Macro Fabric one-default-seat
broker are independent unresolved lanes.
