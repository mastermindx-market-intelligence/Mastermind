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

## October 17 evening: native observation trust/shape regression closure

Original managed Codex quota workspace/branch retained. Starting immutable source
head `36a1fb380a689945b717beb80628b41e27b69aa3`; tracked tree was clean,
ignored Python test caches preserved, no live writer process observed. Source
preimage `control_plane/codex_quota_observation.py` Git blob
`a1370f2190bdb80a9c06288c3ddc4b89d982ab91` was verified before editing.

Nine focused regression cases FAILED on that predecessor, establishing that
missing/malformed native transport provenance, contradictory native quota window
shapes, or a 15-second reset-time adjustment could be silently accepted or
misclassified. This successor now rejects non-native/missing `api_fallback`,
requires known explicit native window states and valid matching observed
windows, distinguishes changed constraint shapes with a fail-closed rebaseline
request, and treats any reset-time movement as a changed schedule without
inventing a promotional reset. Previously implemented same-subject, limit,
plan and `provenance_verified=false` safeguards remain. The new
`constraint_shape_changed` result property is informational only; no
Capacity admission, switch, redemption or entitlement is granted.

A fresh combined M2 suite passed **144/144** tests across account environment,
comparison, 18 new hardening tests, reset inventory and native worker factory.
Python compileall, `git diff --check`, and managed workspace source readback
passed. No actual native provider RPC, credential, model turn, live reservation,
worker lease, tool permission or production configuration was changed.

This proof qualifies source behavior only. Independent current-head source and
security review, hosted exact-head CI, current protected-master compatibility,
existing quota-owner provenance and claim-time reservation integration, and a
real originally-parented admitted Codex work return remain outstanding. Keep
Draft/uninstalled. Existing CODEX-01 and Auth0 unknown effects remain frozen
on their original carriers; unrelated Fable programme and messaging PR #1587
remain separate.

## October 17 late follow-up - refuse unknown quota qualifiers

After hosted CI passed predecessor 8fb4ad0fbf4a9c3aba57c6056422be748d3fb960,
a second read-only adversarial review identified that the pure native comparison
discarded unknown extra windows/window_states keys and accepted identical
null, blank or structured plan_type values as equal entitlements. Five
RED-first cases reproduced CHANGE_OBSERVED when UNKNOWN was required.

This same original source branch now rejects an additional unmodeled quota
window/state rather than inferring refresh from only the modeled subset,
and requires an explicit bounded nonempty plan identifier. The existing
provider-free fixture lacked the plan_type emitted by the real managed
native account/read; it was corrected to "pro" rather than weakening the
runtime check. No account/home, credentials, entitlement, source owner,
reservation, model turn, worker, or provider state changed.

M2 regression: 149/149 passed, comprising account environment (75),
quota comparison (27), quota adversarial (23), reset inventory (14), and
native worker factory (10). Python compileall and git diff --check
passed. Previous exact-head CI must not be reused as approval for this
successor head. Still DRAFT / NOT_INSTALLED / SOURCE_ONLY, pending
independent new-head security review, hosted CI, existing canonical quota
producer and claim-time revalidation, enrolled native accounts, and
one real original-parent worker return and acceptance.


## October 17 late native C1 enrollment and App Server environment verification

The Chairman completed the native OAuth device-login ceremony for the isolated M2
C1 CODEX_HOME; its private auth.json (mode 0600) exists and native Codex CLI
0.159.3 reports an active ChatGPT login. C2/C3/C4 remained unenrolled and no
Business native homes were registered at the bounded observation.

First exact existing scripts/executive_codex_account.py readiness on the C1
home failed during initialize with NATIVE_READ_UNAVAILABLE and clean private
process-group cleanup. A bounded differential showed that merely supplying
TMPDIR still fails, but a controlled PATH including /opt/homebrew/bin allows
native initialize -> account/read -> account/rateLimits/read to succeed. The
exact same isolated home, explicit managed-ChatGPT file store, and openai provider
were retained. The account/read email did not match the intended C1 account
from the Chairman's account roster. The actual email, credential and token values
were never copied or published. Therefore C1 is NOT identity-qualified, and
nothing was admitted, dispatched, rotated, or reset.

Fix on the original #1585 branch: probe_native_account uses the fixed
/opt/homebrew/bin search prefix only for the exact attended
/opt/homebrew/bin/codex binary. It never inherits ambient PATH or credentials
and leaves the separately installed pinned Executive Codex binary at the old
strict system-only PATH. Two RED-first fake-App-Server tests confirm the positive
Homebrew path and negative installed-binary path. The combined native account,
quota, credit inventory, and worker factory suite passed 151/151, with Python
compileall and diff checks passing.

The exact post-fix real C1 CLI probe completed with exit=0,
NATIVE_READS_COMPLETED, MANAGED_CHATGPT_OBSERVED, plan=pro,
AVAILABLE_OBSERVED, primary window=100% remaining / 10080 minutes,
secondary=NOT_APPLICABLE, and private_group_empty=true. This is native
observation evidence, not successful Astra/Sol model execution, verified
seat-to-email binding, canonical sample custody, runtime claim-time reservation,
or six-seat admission. Preserve the C1 credentials as observed; only the
account owner can correct the browser login for the intended C1 identity.
Remain DRAFT / NOT_INSTALLED pending reviewed exact head CI and integration.
