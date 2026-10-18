# Native Codex quota observation: real consumer, not a second allocator

Status: source candidate; PR #1585. Not installed and not a multi-seat rollout.
Protected comparison base: `e77631490e5bddca7d40c8cf039ae7763ce17b99`.
Original carrier: `codex-quota-epoch-observer-20261017-sol-001`.

## Capability delta
The first candidate supplied only a pure comparison utility. This continuation
connects it to the existing `probe_native_account` function and
`scripts/executive_codex_account.py readiness` consumer. The owner may supply
its previous sanitized observation as `previous_observation`, or explicitly
pipe that observation to `readiness --previous-observation-stdin`. The normal
CLI remains backward compatible. No second collector, database, quota ledger,
selector, credential owner, watcher or scheduler is introduced.

The result adds `quota_change` after the native process cleanup disposition is
known. The native method sequence remains initialize, account/read and
account/rateLimits/read. There is no thread/start, turn/start, reset redemption,
account switching, provider inference or additional quota request.

## Trust and accounting boundaries
- The previous observation is caller supplied. Shape checks are NOT provenance
  authentication; `provenance_verified=false` is explicit. The existing quota
  observation owner must retain and validate its own evidence. CLI stdin must
  never become a production reservation or admission authority.
- Account hashes and limit IDs must agree. Empty/malformed IDs, nonmonotonic
  samples, changed plans and overly separated samples are not reset proof.
- Native primary/secondary applicability is preserved, including a weekly-only
  plan with an explicit null sibling. Unknown is neither zero nor unlimited.
- An early timer advance plus recovered headroom is only an early-refresh
  candidate. The provider cause remains unattributed. Natural rollover and
  headroom corrections without timer movement remain distinct.
- No percentage is converted to a token balance, invoice or pooled capacity.
  No promotional reset is predicted or treated as guaranteed future supply.
- Active reservations, source custody, authentication/refusal holds and unknown
  effects are never cleared by a quota observation.

## Red-first repairs and verification
Three regressions failed on the predecessor: two missing limit IDs compared as
valid; an oversized integer raised OverflowError; and a plan change could look
like a promotional reset. All three now fail closed.

Four integration cases failed before wiring the real consumer: native probe
comparison, cleanup-uncertain rejection, invalid CLI stdin before account
access, and successful CLI prior-observation transport. They now pass with
mocked native RPC; only the existing two account reads occur.

The final combined native-account, reset-inventory, comparison, native factory
and execution-contract suites passed 147 tests with zero failures/errors/skips.
An expanded run first exposed an existing macOS test-fixture GID mismatch: the
private temp directory and dummy receipt inherited wheel, while the fixture
correctly requested the process primary group. The test now sets ONLY its owned
disposable receipt to os.getegid(); the production root/GID/0440 checks are
unchanged. No real credential, installed receipt or provider was touched.
Compile and diff checks passed.

## Remaining integration and acceptance
The Shared AI Provider Control quota producer remains the accounting owner;
`capacity_economics_projection.py` remains an advisory first-suitability-tier
consumer. Do not invent a substitute preview producer because the installed
private owner cannot currently be inspected on this operation.

Next: source review and exact-head CI; qualified native account/host observation
through the existing owner; owner-retained sample provenance; account/model
shared-window debit and review/repair reservations; claim-time revalidation;
then an admitted useful task, retained result, independent review and original
parent acceptance. Long-lived broker quota notifications should feed the
existing observer rather than creating an extra auth-refresh process per job.

The historical CODEX-01 issuer and separate Auth0 registration uncertainties
remain on their original carriers. This candidate does not retry or resolve
them. No production Worker, account, host, runtime or installed config changes
are authorized by this document or by green source tests.
