# Fixed Ubuntu4 routing-policy enrollment

This is a source candidate in the incumbent Fabric support/bootstrap owner. It
adds no dispatcher, scheduler, provider grant, lease operation, credential route,
mode promotion, automatic retry, generic bootstrap or fleet sweep.

The Nov7 original qualification failed before worker launch because the uploaded
support policy was present but the independent incumbent
`/home/ubuntu4/lanes/orch/fabric/pools.yaml` was absent. `support_bundle.publish`
correctly refused: its semantic compatibility check requires that incumbent.
Ordinary bootstrap mirrors `ext/`; it does not populate this sibling policy path.
This explains the missing prerequisite, not when or why the remote file became
absent. Do not weaken publication to bootstrap policy automatically.

`ubuntu4_policy.transport_plan` prepares one argv using the existing storage
owner's transport and public enrolled-binding parser. It never dispatches.
`kind="inspect"` returns only a fixed policy SHA/ABSENT and presence of prior
installation history, with no writes. The only accepted semantic host is Ubuntu4,
resolved from public config to its literal SSH alias; the remote account must be
`ubuntu4`, machine `ubuntu4-MS-7E61`, Linux and non-root. The default home
is derived from that account's passwd entry and must be exactly `/home/ubuntu4`;
inherited HOME cannot select an alternate owned lanes tree. No guessed alias is used.

Before a real operation, Root must qualify this exact module and its unchanged
protected `preview_install.py` dependency. Pass their independently reviewed SHA256
pins to `transport_plan`; fresh source bytes do not self-authorize themselves.
Revalidate current public registry/SSH config and custody. Root alone may execute
that plan via the existing driver's `run(plan["argv"], plan["timeout"])` after an
explicit scoped decision. There is no new network entrypoint in this module.
No plan, receipt or boolean is an authentication or installation grant.

An actual inspect must settle before constructing an install plan. Install is
supported only for a separately observed **ABSENT** target. Supply the exact
approved public policy bytes and independent `expected_policy_sha`, an original
operation ID, and `original_settled=True` only after reconciling the original
qualification's actual provider lease/effects through its existing owner. A
terminal prelaunch status alone is not a lease-release acknowledgement.
Existing policy, a previous installation record, unknown state, missing paths,
missing/replaced/busy admission lock, active/unknown markers, symlink/hardlink,
foreign ownership and writable namespaces all refuse. No paths are created by
inspection; the installer creates only its fixed one-shot receipt, own stage and
the one absent policy file. The existing physical admission lock is opened without
creation and held throughout. All held named directories, lock inode, active set
and observed policy identity are rejoined before accepting results.

The installer uses a no-clobber link of its fsynced private stage; it cannot replace
an existing policy. The fixed receipt is created before any target write. Every
prior receipt holds further writes, even VERIFIED, so a late fence/fsync/terminal
failure can never become permission to replay with a new ID. An interrupted install
is UNKNOWN until its original owner reconciles it. Preserve the target and record;
there is no automatic rollback, cleanup or retry. This ABSENT-only source candidate
does not upgrade/repair existing policy.

The actual original run retained packet and support-source uploads and reached
publication. No immutable support release or worker START was reached by that
publication branch. Controller EXIT attempts broker release but suppresses its
return; retained logs do not prove that release. Remote uploaded files are not
cleaned by the controller's local cleanup. No new worker may be inferred or replayed.

Targeted hermetic checks:

```sh
python3 -m unittest tests.test_ubuntu4_policy_enrollment -v
```

These exercise local temporary directories only. They establish source behavior,
not remote preimages, installed helper bytes, lease settlement, provider readiness,
registry promotion or capacity restoration. Original refused/terminal requests
remain closed, including `mmos-u4-minimax-qualification-01a15741-20261107-v1`.
