# Fixed ORCH group-write prerequisite repair — source only

P8.T1.S31 extends the existing `ubuntu4_policy` maintenance owner. It does not
relax `_owned`, `operate`, `inspect_custody` or policy publication. It is neither
a retry of their original refusals nor a bootstrap, dispatcher or policy repair.

## Source decision and sharing boundary

The existing enrolled transport resolves semantic Ubuntu4 to account `ubuntu4`,
Linux host `ubuntu4-MS-7E61`. Default scope resolves that account through passwd,
requires exactly `/home/ubuntu4`, and uses the real non-root UID; no numeric UID is
guessed. `remote_sub.sh` writes support through that same SSH account/alias. The
legacy `mkdir -p ~/lanes/orch/fabric` has no explicit mode/umask and leaves an
existing mode unchanged. The canonical maintenance owner instead requires UID
match and no group/other write. No supported alternate OS group writer is declared
by these provisioning/maintenance paths. Logical provider accounts in the Broker
are not evidence of separate Unix writers or a private Unix group.

Root's retained metadata establishes only ORCH owner_matches=true,
group_writable=true, other_writable=false. It does not establish an exact mode,
UID/GID/inode, ACL, physical-host quiescence, policy preimage or historical creator.
Under the declared single-account owner contract, removing only group-write is an
ordinary prospective prerequisite repair, rather than an inherent human-only
security ceremony. This source commission DOES NOT authorize its live execution.
An actual OS/tool refusal ends that action. It supplies no authority for sudo,
chown, changing other bits, changing shared-group entitlements or reading policy.

For additional conservatism, the action requires the ORCH GID to equal the fixed
account's current passwd primary GID and refuses ACL-named extended attributes.
It does not claim complete account/group/ACL history or inspect group databases.
A different GID, present ACL, unsupported metadata API or actual declared sharing
conflict stays held: obtain a separate concrete sharing/custody decision; do not
force this repair or remove its guard. No such conflict is inferred from the
existing group-write boolean alone.

## Exact operation and source APIs

`repair_orch_group_write(operation_id=...)` opens only the fixed leaf `orch`
relative to held qualified `/home/ubuntu4/lanes`, using O_DIRECTORY|O_NOFOLLOW.
The remote transport exposes no path, UID, home, account, hostname, mode or payload
override. Python-only scope overrides match the incumbent hermetic-test pattern.
It requires owner UID, the primary GID, group-write present and other-write absent.
The selected FD's full metadata preimage is captured locally to the action, never
inferred from the prior public booleans.

The existing all-host `.admission.lock` is opened without creation, required to be
a current single-link owner0600 regular file, and held exclusively/nonblocking.
The active directory must contain exactly that lock. Held/named qualified home,
lanes, ext, active and state plus lock/active membership are rejoined repeatedly.
ACL names and both held/named ORCH metadata are rechecked before mutation. Only
`fchmod(held_orch_fd, old_mode & ~0o020)` may alter permissions. UID, GID, inode,
all other permission/special bits, directory size/link count and mtime must remain
unchanged; only the expected chmod ctime change is accepted. Named replacement,
late marker/lock/ancestor change or unexpected postimage withholds verification.
The final ancestor/lock rejoin is followed by a fresh no-ACL and full ORCH FD/name
identity check before fchmod. Separate syscalls cannot atomically exclude arbitrary
noncooperating same-UID mutation between that final check and fchmod; the held FD
prevents following a replacement, and post-effect checks retain UNKNOWN/no replay
when drift is detected. No stronger atomic namespace guarantee is claimed.
No recursive operation, descendant open/stat, policy body, original receipt body,
cleanup, rollback, chmod-by-name, sudo or chown exists.

`transport_plan(kind='repair-orch-group-write', operation_id=..., ...sourcepins)`
uses the same pinned owner/storage source and public enrolled binding parser. Its
closed remote request contains only the action and original operation ID. It
rejects payload, policy preimage/hash and original-worker settlement inputs. The
plan remains `dispatch_authorized:false`; planning invokes nothing.

`guarded_orch_repair(...)` is the private Root composition entry. It imports the
SAME enrolled `lease_broker.Broker` from the source-qualified selected native
runtime and enters its existing `qualification_maintenance_guard` for original
Root01a15741/MiniMax/Ubuntu4. No Broker instance, DB/lock override, caller guard,
detached JSON, new grant or registry is accepted. Guard checks bracket planning
and the ONE incumbent `driver.run(argv,20)`; the existing context exit checks
again. The original30s Broker deadline is unchanged. Root must qualify that actual
selected source/namespace/driver and prevent new root dispatch, as for previous
Root actions. This is trusted process composition, not an arbitrary-Python sandbox.
Scoped zero is not historical release ACK or host idle. Remote physical fencing is
independent and mandatory. Timeout/lost response/late Broker failure is UNKNOWN;
do not repeat or start new root work while that operation remains unresolved.

## Retention and no replay

Within the already-qualified state directory, only these new fixed maintenance
records may be created through incumbent `_write_new` (exclusive/no-follow0600,
fsynced file+directory):

- `ubuntu4-orch-group-write-repair.intent.json`, before fchmod;
- `ubuntu4-orch-group-write-repair.verified.json`, after exact postimage/currentness.

They are a single operation's intent/outcome, not another lifecycle/store. Any
existing name (including symlink/unknown contents) holds a future operation; no
body is opened. Intent-create attempt is sticky even if create/fsync fails. Every
exception after that boundary reports ORCH_REPAIR_EFFECT_UNKNOWN/no replay. The
intent and actual mode remain untouched after interruption; no ID replacement,
rollback, receipt deletion or automatic retry exists. Public success is closed to
schema/root/originalID/VERIFIED/group_write_removed/replay:false and no lifecycle
authority. Raw metadata stays in this operation's own private records.

The original policy/prior-install records are never opened, read, hashed or
modified. Existing inspectors remain strict and their refused operations closed.
Root's original carrier retains local intent/outcome and any uncertain transport;
a source candidate or verified helper cannot substitute for that effect evidence.

## Qualification and next action

Local temporary-directory tests exercise success, all other bit preservation,
owner/GID/ACL/API holds, no content descriptors/reads, no-follow namespace races,
physical lock/active fences, partial intent/lost chmod/outcome failures and actual
incumbent Broker SQLite/shared-lock continuity. On macOS only the unavailable
Linux xattr-name observation is explicitly injected as test metadata. Production
fails closed if that FD API is unavailable. No remote ACL/group/private ownership
or Linux host proof is claimed by these tests. Original owner/storage source is
compared separately; the new action does not call either original inspector.

Next: one changed-risk AcceptanceReview of the frozen delta. After accepted source,
Root may prepare a separately authorized ONE original action using exact pins,
current native Broker/public binding and fresh fixed metadata. This commission
performs no live observation, permission change, policy enrollment, credential,
service, lease or worker effect. No human/security-setting grant is presumed;
none is proved missing without a real control or sharing conflict.
