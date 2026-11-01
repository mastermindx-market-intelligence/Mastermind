# Finite installed Macro adoption

This is an explicit offline maintenance operation. It changes only
`ceo_ingress_app_macro_root` to another independently qualified, published,
immutable `macro-sources/<40hex>` generation. It does not install a different
Mastermind release, stop/start a service, edit Runtime, replay acceptance,
regenerate Agent OS, or arm a caller. Execute only from the actual selected,
fully qualified release containing this helper. A prepared candidate, source
test or observation receipt is not production acceptance.
The script entry delegates into the canonical package before creating any owner
classes or process-local custody, sharing the publisher's exact identity.

The normal Macro nightly remains the only catalogue regenerator. This helper
does not schedule itself. An unattended administrative refresh owner/trigger is
**UNIMPLEMENTED/UNQUALIFIED**; Control Room refresh, COO ticks, backup and
portfolio attention have no inferred Root publication grant. Do not claim the
48-hour consumer budget is renewed by cache recomposition or by source readiness.

## Reach the offline boundary through existing owners

Let current affected jobs finish naturally. Scope quiescence to this Control,
Worker, Runtime and their source-bound effects, not unrelated chats or manual
Fabric operations. Preserve genuinely affected unknown operations. Queued
nonexecuting roots and terminal history are retained without terminalization.

The unchanged `acceptance_maintenance.require_disarmed` requires exactly these
three intake flags false: `ceo_submit_armed`, `coo_autonomy_armed`, and
`coo_operator_harness_armed`. The worker's `operator_harness_armed` must also be
false. `ceo_ingress_app_armed=true` is the App transport/read binding; it remains
unchanged and need not be turned off.

If CEO submission is armed, its existing owner is:

```text
<selected-release>/ops/executive_os/autonomy-control.sh ceo-submit-disarm --expected-sha R
```

The normal full-disarm owner is:

```text
<selected-release>/ops/executive_os/autonomy-control.sh disarm --expected-sha R
```

Its existing `derive_candidate_configs(armed=False)` closes both COO flags and
the worker harness and restores a native-return selector to the readonly profile.
It uses the existing lifecycle owner. Do not invoke disarm/restart to manufacture
quiescence while affected work is active: normal Control shutdown can cancel
ordinary dispatches. Existing `service-control.sh stop`, where genuinely needed,
is a separate admitted operation after work drains. The adoption primitive merely
requires exact Control/Worker absence, quiet dedicated principals, their canonical
service lock, no live Attempts/Jobs/held quota, no authoritative sidecars/barriers,
closed intake and exact config/receipt preimages. It never sends a signal.

An inert historical Wake value is preserved; no literal-null requirement is added
where closed COO/native execution flags already revoke its effective execution.
No held historical canary or exact-session operation is replayed.

## Inputs and preparation

Acquire and publish a separate immutable Macro generation through the normal
source/collector/seal/publication procedure. This helper performs no Git transport
or source publication. Old selected roots are never updated in place. Use the
actual installed attested boot interpreter and Control-UID collector, its unchanged
28-second cumulative deadline, full generation seal and exact artifact hash. A
real qualification failure is not waived or replaced by synthetic fixture output.
The Macro directory and every artifact ancestor must be directly canonical,
Root-owned, free of unprivileged write/ACL access and symlinks. A held artifact FD,
directory FD and bracketed ancestry bind exact bytes across the real generation
proof. Root-owned ordinary 0755 publication directories remain allowed; this does
not exclude a noncooperating privileged writer.

The internal read-only `qualify-target --release-sha R --macro-root M` subcommand
runs only as the real Control UID from the actual selected release. The Root
adoption owner invokes it through fixed `sudo -n -u`/clean environment and the
normal system interpreter. It returns only source SHA, Macro SHA/seal, artifact
SHA and timestamps, never the private boot packet. The artifact must satisfy the
existing mapper's future-skew policy and positive remaining 48-hour budget. That
predicate is checked again immediately before actual config rename.

The request is closed JSON with exactly:

```json
{
  "expected_release_sha": "<selected 40hex>",
  "current_control_sha256": "<actual raw current config hash>",
  "current_worker_sha256": "<actual raw worker config hash>",
  "expected_old_macro_root": "<canonical existing 40hex Macro path>",
  "target_macro_root": "<canonical new 40hex Macro path>",
  "target_macro_sha": "<new path basename>",
  "target_generation_seal_sha256": "<actual collector generation seal>",
  "target_artifact_sha256": "<exact Agent OS artifact hash>",
  "expected_receipts": {
    "ceo_submit": null,
    "autonomy": null,
    "control_observation": "<actual raw hash>",
    "adoption": null
  }
}
```

Each receipt value is its actual SHA256 or null only when genuinely absent.
The illustrative nulls are not permissions to omit existing receipts. Never
include credentials, private config contents or Runtime rows in this request.
Candidate preparation is a separate exclusive data write:

```text
<fixed-python> -I -S -B <selected-release>/ops/executive_os/macro_adoption.py prepare --request REQUEST --control-input PRIVATE_INPUT --output NEW_CANDIDATE
```

It validates the complete supplied schema and one-field delta. It does not inspect
the host or confer adoption authority. Root performs the separately admitted finite
operation from the same selected release:

```text
<fixed-python> -I -S -B <selected-release>/ops/executive_os/macro_adoption.py adopt --request REQUEST
```

Root config/worker/receipt CAS, installed source, accepted historical proof,
target generation, real custody and Runtime quiescence are independently re-proven.
The same config-directory inode mutex and existing `autonomy-transaction.lock`
namespace serialize the operation with incumbent writers. A complete private
generation and its held directory flock precede canonical marker publication.
Prospective preparation first creates an exclusive, unselected private stage,
writes every archived preimage, PREPARED manifest and candidate, and fsyncs it
before exclusively publishing the deterministic private generation and canonical
marker. An incomplete unselected stage is preserved, never selected or deleted;
old incomplete generations are not adopted by this prospective behavior.
Every effect has a durable preceding phase; no missing receipt is fabricated.

## Result, authority and ordinary return to service

Success leaves the services absent and all intake/harness/native execution
authority closed. It publishes the normal nonsecret Control observation and one
Root-owned `config/macro-adoption-receipt-v1.json`, which is evidence only. Prior
CEO/autonomy receipts remain historical/disarmed. Changing the Macro root breaks
the old CEO binding; changing config bytes breaks the old full-autonomy digest.
The helper cannot mint either authority or extend readiness/credentials.

For readside-only use, normal admitted `service-control.sh start-readside` is a
separate lifecycle action; no arm is needed for a catalogue observation. For full
worker operation, use the existing ordinary arm owner with the actual current
Gate B, readiness, credential and workspace inputs:

```text
autonomy-control.sh arm --expected-sha R --gate-b-receipt G --expected-credential-kind K --workspace-binding-class W --credential-expires-at T [--native-return | --foreground-only]
autonomy-control.sh ceo-submit-arm --expected-sha R
```

Choose only the genuinely admitted profile. Normal arm independently validates
the historical acceptance/carry, current install, Gate B, provider readiness and
quiescence and generates fresh config-bound receipts. The CEO-submit owner derives
its fresh actual Macro/peer/socket binding and supports only proven safe
coexistence. The helper does not supply those prerequisites. Inspect normal actual
readbacks, fresh Mission CURRENT state and real result navigation separately; no
new Mastermind release or manual config editing is required per Macro refresh.

## Unknown effect and explicit same-operation closeout

Never repeat `adopt`, use another request/carrier, or remove a marker because a
response was lost. Read-only `status --request REQUEST` reports the exact original
configuration and retained operation. It never clears, retries or rolls back.
Private prepublication failures remain held under a path derived from the same
Control preimage, preventing a different target request from bypassing them.

An interrupted operation with independently proven complete postimage, normal
observation and complete matching adoption receipt can use the explicit normal
owner `close-complete --request REQUEST`. It acquires the SAME original marker
inode/flock without waiting (a live writer refuses), same selected source and
canonical service lock, and proves all archived bytes, closed flags, quiescence,
actual config/worker/observation/receipt joins and immutable target again. Only
`RECEIPT_PUBLICATION_STARTED` or `COMPLETE` with every completed byte proven can
close. It removes only the completed owned marker; it never replays or repairs a
config, observation, receipt, phase, migration or Job. Partial/missing/mismatched
evidence remains held, not a human-only gate or permission to retry.
Closeout atomically moves the complete, still-locked original generation into its
existing private transaction-generation path with exclusive Darwin rename. Every
archived byte and the complete manifest remain, including after a lost
acknowledgement. An occupied archive refuses without replacement. Closeout never
tears apart proof by unlinking entries before releasing the canonical namespace.

The read-only completed-target observer may verify the original immutable bytes
after their historical timestamp ages: this is cleanup of an already-proven
effect, not a freshness waiver for adoption or a new authority grant. Adoption
always requires current positive budget. An uncertain cleanup response remains
same-operation unknown. If the marker's removal crossed before acknowledgement,
the retained complete archive, latest receipt and exact postimage identify it; status reports facts
for Root adjudication rather than authorizing another write.
Status reports receipt facts independently even when a canonical/private marker
is partial or unreadable. A fully PREPARED generation whose exact current config, worker and all receipt
preimages remain unchanged has a separate finite no-effect close owner:

```text
<fixed-python> -I -S -B <selected-release>/ops/executive_os/macro_adoption.py close-prepared --request REQUEST --owner-device DEVICE --owner-inode INODE
```

Use only the `prepared_owner_token` observed by normal `status` for the exact
held generation. That device/inode pair correlates an owner; it is not authority.
The owner independently requires the same selected source, actual Root custody,
exclusive config and generation locks, stopped services, closed intake, historical
acceptance and selected Runtime quiescence. It rechecks exact manifest namespace,
complete archives, candidate and every live preimage at the rename edge. Literal
PREPARED is required: later, unknown, missing or mismatched evidence refuses.
No config, phase, receipt, Runtime, service or arming write is performed.

The owner exclusively archives that same complete inode under
`.macro-adoption-prepared-closed-<operation>-<device>-<inode>` and preserves all
bytes. After a lost close acknowledgement, the same request and owner token may
only observe success after proving that archive's actual inode and complete byte
joins with the unchanged preimage, locks and offline conditions. Its name alone
never proves completion. Read-only status cannot close or clear an operation;
unknown mutation outcomes remain held until this exact positive proof exists.
Incomplete old private generations and incomplete unselected stages remain held
and preserved. Neither close verb repairs or removes them.

All filesystem exclusion assumes exclusive administrative custody against a
noncooperating privileged writer; locks do not globally constrain arbitrary Root.
Source fixtures prove contract behavior only. Actual Darwin identities, full
sealed source/target, permissions, lock/process predicates, host effects and
recurring owner/trigger remain distinct qualification obligations.
