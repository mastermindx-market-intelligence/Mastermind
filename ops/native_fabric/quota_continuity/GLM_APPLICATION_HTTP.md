# GLM application turns through the native owner

This change adds the intentional `glm-5.3` and `glm-5.3-flash` choices to
the existing native application path. It preserves the original GLM account
owner, Broker ledger, finite enrollment transaction, and native generation
format.

## Runtime and admission

The GLM application adapter uses the Z.ai Coding Plan chat-completions endpoint
`https://api.z.ai/api/coding/paas/v4/chat/completions`. Each admitted request
has one concrete model, an authorized account, and that model's canonical
recipe digest. A multi-model grant cannot reuse one recipe digest.

The application capability has the separate v4 GLM HMAC domain
`mastermind.glm.application-lease-capability/v4\0`. Existing worker
capabilities and the original application v1/v2/v3 domains keep their original
grammars. Cross-domain verification is refused.

The common application HTTP owner records a pending request before sending.
A repeated request does not send again. Tool continuations preserve the
assistant's raw `reasoning_content`, tool call identifiers, and arguments
while retaining the original application lease. A completion or a verified
recovery uses the same Broker request and turn records. An uncertain transport
outcome retains the lease and is not treated as permission to send again.

The adapter is synchronous and non-streaming. Buffered output is not streaming
parity.

## Captured native source

Build the optional GLM pair with all three flags:

```sh
python3 ops/native_fabric/quota_continuity/rollout/build_review_stage.py \
  --output /absolute/review-stage \
  --include-go-application \
  --include-application-http \
  --include-application-glm
```

The GLM flag adds exactly these payload members, alongside the complete
existing HTTP group and original `glm_keys.py`:

- `ext/glm_application_adapter.py`
- `ext/application_http_realms.v2.json`

The sealed v2 metadata retains the unchanged v1 projection and binds the
actual Git commit and exact captured GLM source inputs. Dirty or foreign
captured inputs are rejected. Disposable tests create a real fixture commit;
they do not claim a protected production commit.

Git qualification occurs during staging. The finite installer verifies the
captured projection against the accepted generation hash, the fixed source
inputs, and exact canonical recompilation. It launches no Git process and does
not replace the recorded commit with the repository's later HEAD.

The immutable adapter alias is `glm_application_adapter`. The externally
owned `glm_shim` module retains its original identity and pin.

Current native builds also require the complete three-member Go dependency
successor: `lease_broker.py`, `go_lease_capability.py`, and
`go_lease_gateway.py`. Historical payloads are captured from pinned inert
preimages; the successor is applied after the existing provider, quota, and
remote compositions. The transformation checks complete pre- and postimages
for the base, provider, H2, and provider-plus-H2 Broker variants. It does not
change historical ancestry pins. `native_generation.py` remains validator
source and is not a runtime payload member.

## Archived release derivation

The committed 107-member manifest and source inventory remain historical
inputs. During ordinary Executive release staging, the existing installer
captures both raw records and runs its archived builder once. Unchanged
records retain the original raw-equality path. If the records change, a pure
verifier from that same builder admits only the authenticated three-member
core successor.

The verifier derives both complete expected records from the captured
originals. It checks the historical and candidate source commitments, original
byte counts and source fields, and exact composition metadata. All other 104
members, installed-preimage fields and top-level inventory values remain
unchanged. Canonical raw-byte comparison rejects partial transitions,
unrelated metadata changes and ambiguous encodings. Verification performs
no process launch, record rewrite or second builder execution.

The existing release seal then captures the actual derived records and
payload bytes. The source commit/tree provenance and exclusive publication
owner remain unchanged. This default 107-member derivation does not enable
the optional GLM pair or select a native generation.

## Original finite enrollment

The existing routed v9 service specification accepts an optional
`glm_application_http` record with only these caller-supplied fields:

- `pool`: `glm`
- `source_projection_sha256`
- `recipes`
- `accounts`

The original enrollment owner captures the provider profile path, file
identity, and content digest itself. Callers cannot assert that custody.
Private profile values and service credentials are not published in plans or
receipts. Preparation and application use the original owner, held file
identities, locks, atomic replacement, intent, and completion receipt.

Fresh credential use checks the original GLM account helper, explicit Coding
Plan endpoint, account set, private file identity, and captured contents.
Completed enrollment reconciliation and retained request recovery do not
require a current provider configuration or a newly compiled recipe. Removing
or revoking current credentials therefore blocks fresh use without preventing
truthful recovery of the original completed effect.

Attended, secretary, and meta-CEO roles retain their own finite service
bindings. Compatible completed roles share the same verified provider
projection and physical Broker owner. Enrolling one role does not rewrite a
peer's binding.

## Qualification and activation

The focused suites cover real isolated HTTP handler/Broker execution,
capability-domain rejection, original paid GLM compatibility, sealed native
packaging, finite role enrollment, provider-custody changes, lost
acknowledgement recovery, and shared-role startup. Synthetic fixture
credentials are confined to disposable tests and make no provider request.

Source qualification does not prove installation or user acceptance. Release
must use the protected source and original whole-bundle installer, regenerate
forward plans against that source, and preserve the normal stop/cutover/start
sequence. Final H4 acceptance separately requires actual served-model and
usage evidence, native tool continuation, delegated execution with terminal
result and original-parent consumption, recovery/revocation evidence, and
the actual OMH path.
