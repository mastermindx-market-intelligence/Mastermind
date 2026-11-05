# Native probe drift qualification for the retained 2bca PASS

This is a separate, closed incident route through the existing privileged
readiness action. Source eligibility does not approve a live probe, inference
canary, credential replacement, service start or worker activation.

## Historical evidence

The native readiness controller 41117 ended at
2026-10-20T08:04:27.668781Z with exit 65 and
`credential_identity_changed_during_probe`. It stopped before reservation or
inference. Its retained result is:

- `/Volumes/Mastermind/evidence/mmos-commission-01a15741/readiness-renewal-20261020-result.json`
- SHA256 `ffa2dec44d1d81569be113ebcd4b199464ba8e50e100b894196c32e82fa50d42`
- Retained PASS receipt SHA256 `2bca56bcf84b1c5332879eaa22f23f521b37cea30c01dfe5936c3923c3f651cf`

Only credential mtime/ctime drift was retained. The writer and continuity of
credential contents remain UNKNOWN. This route does not turn that native event
into an original broker request, a failed inference canary, or evidence of
unchanged credential contents. It does not extend the expired October 20 approval.

The existing `654abd…` company-device route, ordinary exact-metadata renewal,
and current-pin/DUE10 grant routes keep their separate contracts. This native
event needs neither a fabricated grant nor a new allocation registry.

## Qualification and approval before the effect

Install the independently reviewed source through the existing release owner
and qualify its complete sealed manifest. The new broker route checks that
manifest and its agreement with the running broker release before creating an
inflight marker or starting a child. A source checkout alone cannot pass it.

Reconcile the actual existing readiness transaction and worker state through
their admitted owners. An occupied transaction, unknown provider effect or
actual permission refusal remains a hold. An unattributed historical process
start is not by itself proof of a current pending operation.

Obtain and retain fresh explicit human approval for one current-identity
qualification attempt and at most one inference canary, including an exact UTC
credential deadline more than 30 and no more than 60 minutes ahead when the
eligibility check runs. A later deadline is not an automatic retry. This source
route does not change credential contents, authenticate a new account, enable a
worker or restart Control.

The exact retained PASS must still occupy the fixed company receipt path. The
credential must have the same device, inode, UID/GID 451, mode 0600, size and
single-link status. At least one timestamp must differ. The historical receipt
must be expired, internally passing, and bound to the exact reviewed installed
Codex binary. No credential bytes are read by these classifiers.

## One broker identity

Use only the existing `mmx-admin` broker entry point with this designated
identity. It is a proposed source-bound identity until actually issued:

`mmos-native-probe-drift-2bca-20261022-v1`

After all preceding qualifications, substitute the actual approved deadline:

```bash
mmx-admin executive.worker_auth.verify_ready \
  --request-id mmos-native-probe-drift-2bca-20261022-v1 \
  --expected-credential-kind device-auth \
  --workspace-binding-class company-workspace-admin-attested \
  --credential-expires-at '<approved-UTC-deadline>' \
  --requalify-native-probe-drift-sha256 \
  2bca56bcf84b1c5332879eaa22f23f521b37cea30c01dfe5936c3923c3f651cf
```

Do not invoke the lower-level provisioner/readiness helper directly for this
incident. Its receipt preimage fences the canary, while the broker's retained
request identity also fences a probe that stops before changing that receipt.
The CLI requires an explicit ID; the action validator refuses any different ID,
credential kind, slot override, preimage or mixed recovery route. The canonical
request digest binds the selected deadline and complete arguments.

The existing readiness lock surrounds the transaction. A fresh passing identity
must match current credential and provider policy. The old receipt is archived
byte-for-byte before its exact CAS replacement with a sticky canary reservation.
Credential/binary observations are checked across that replacement. The normal
single inference and post-inference identity comparator remain unchanged.

## Retained outcome and uncertainty

If the child ends with exit 65 before reservation, the broker retains FAILED for
the same request. Repeating that exact request reads its terminal without a new
source check, probe or canary. Changing its deadline conflicts with the retained
request digest. A successful terminal is also retained by the same owner.

For a lost transport response, observe this original identity:

```bash
mmx-admin status --request-id mmos-native-probe-drift-2bca-20261022-v1
```

EFFECT_UNKNOWN keeps its original marker; it does not authorize another ID or
direct-shell attempt. If the existing reconciliation owner later proves the
exact pre-request PASS remains, no readiness transaction lock exists, and no
verify-ready process remains, it may record NOT_APPLIED using the original
request/marker/release hashes. Historical reconstruction works after the
approved deadline has expired. Reconciliation preserves the original marker and
records a non-replayable result; it never refunds execution authority.

Retain the actual broker terminal and final readiness receipt before assessing
worker readiness. A PASS is credential-readiness evidence, not completion of the
Mastermind OS programme or installed app journey. The subsequent acceptance is
one authenticated app-originated commission, its real worker START/result and
recovery of the original app pointer without another submission.
