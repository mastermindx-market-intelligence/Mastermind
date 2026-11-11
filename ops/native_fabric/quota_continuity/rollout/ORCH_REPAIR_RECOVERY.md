# Original ORCH repair receipt recovery — read only

P8.T1.S33.S4 extends the incumbent Ubuntu4 maintenance owner after the original
20-second driver timeout. The original operation remains UNKNOWN until its owner
consumes a qualified recovery result. This source does not retry that operation,
read its lost stdout, inspect policy, change the driver timeout, or acquire a
Broker guard/lease. Original repair, enrollment and storage behavior is unchanged.

The sole new literal transport kind is `read-orch-repair`, with operation exactly
`mmos-u4-orch-maintenance-01a15741-20261108-v1` and the existing fixed root. There
are no path/account/UID/root/mode/receipt selectors. `transport_plan` additionally
requires the exact SHA of `orch_repair_read.py`; its existing storage reader must
qualify all three source files. Each is below the unchanged 32768-byte bound.
The embedded remote program compiles those exact bytes, supplies the incumbent
scope/active-membership implementation internally and invokes only the reader.
The existing enrolled target parser and driver argv/20-second cap remain intact.
Planning grants no dispatch permission. Root alone owns any actual recovery read.

The reader uses the incumbent fixed passwd/account/hostname checks and opens
qualified held HOME/lanes/ext/active/state directories with no-follow traversal.
It opens the EXISTING owner0600 single-link admission lock read-only, takes a
nonblocking shared flock and refuses busy/unknown active membership. It neither
creates nor modifies that lock. It opens only the fixed ORCH directory metadata
and these two original operation files under held STATE:

- `ubuntu4-orch-group-write-repair.intent.json`
- `ubuntu4-orch-group-write-repair.verified.json`

Both must be owner0600 single-link regular files, bounded by the existing storage
reader, with stable held/named identity. Closed duplicate-rejecting JSON validates
the original schema/root/operation, exact fields/types, preimage, expected single
mode-bit removal and paired postimage. The old policy/enrollment receipt and all
ORCH descendants are never opened. After body reads, ancestor/lock/membership,
receipt identity, current ACL names and held/named leaf identity are rejoined.
A detected concurrent change withholds the result. As with the original owner,
separate syscalls cannot defeat arbitrary noncooperating same-UID mutation
atomically; this is the same trusted fixed-account custody contract, not a new
cryptographic attestation or proof of historical process identity.

Results keep historical settlement separate from current prerequisites:

- Neither file: UNKNOWN / ORIGINAL_RECORDS_ABSENT, never proof of no effect.
- Valid intent only: UNKNOWN / ORIGINAL_INTENT_ONLY, even if mode is now 0755.
- Valid exact paired receipts: VERIFIED / ORIGINAL_RECEIPTS_VERIFIED describes
  recorded historical completion. `current_postimage_qualified` separately
  reports exact current postimage and observable no-ACL metadata. Later drift
  retains the recorded terminal fact but forbids treating it as new admission
  qualification; unavailable ACL metadata similarly leaves current qualification
  false. Neither result grants maintenance, policy, worker or lifecycle rights.
- Wrong identity/schema/pair, malformed/changed/foreign receipt or unqualified
  current owner: closed HELD_OR_UNKNOWN; no historical reconstruction.

Every outcome has replay:false, retry_authorized:false and lifecycle_authority:false.
Successful observations expose only fixed identity, states, closed reasons and
SHA-256 of the two operation records, never their raw metadata or policy bodies.
The existing transport public-refusal encoder remains the sole error projection.

Original source provenance is retained in Root's local intent. The original
remote receipt format has no source hash: this read does not retrofit one or
claim the receipt independently proves which executable ran. It verifies the
existing owner-produced receipt contract under current fixed-account custody.

Focused tests use the actual original mutator in disposable directories, actual
receipt bytes and the actual source-pinned embedded reader. Linux scope/ACL facts
are explicit inert substitutions; no real host, Control, Broker, SSH or grant is
used. No original runtime result is claimed from those fixtures.
