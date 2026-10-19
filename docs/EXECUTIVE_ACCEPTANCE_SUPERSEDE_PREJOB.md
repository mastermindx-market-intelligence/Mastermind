# Preserve a pre-Job interrupted acceptance

The explicit `supersede_prejob_v1` maintenance branch carries an interrupted V2
or `supersede_unstarted_v1` acceptance prefix (the interrupted release may itself
be an unstarted-supersession successor) into one fresh protected release. It never
replays the failed release, credits it with PASS, changes its files, rebaselines
Runtime, recovers historical capacity or arms a service. Unstarted supersession
remains strict, and a selected `supersede_prejob_v1` release is admitted and
re-validated with its own sealed bundle, run-started marker and pre-Job evidence
exactly like any other selected link.

This repairs the observed `0123ad5ae7408a35fd38b4a0b4e9bf5a132bbe65` service-start
exit 141. The failed descriptor is
`d21e00d5b35f5a742b6f12f2e67a9d34fc001adfb999902456dba5a06c80cf20`.
Its stopped Runtime matched the original 19 Jobs / 24 Attempts with no changed
tables. The start marker existed but only the two pre-service acceptance receipts
had been written. Source qualification is separate from host eligibility.

The sole host lifecycle owner uses the existing stopped/disarmed preparation,
with the actual accepted ancestor as `--predecessor-sha`, the new exact protected
release as `--successor-sha`, the original root, `--carry-terminal-dispatch`,
`--supersede-prejob-sha` naming the failed installed release and
`--superseded-descriptor-sha256` naming its original descriptor. Neither recovery
selector nor `--supersede-unstarted-sha` may accompany this mode. Source tools
must run through the qualified isolated, bytecode-disabled Python invocation.

Preparation requires the installed release to match that selected failed release.
The accepted ancestor retains its actual PASS chain. All V2 semantic fields,
entire live database snapshot, artifact inventory and prior canary must match
the failed descriptor's sealed baseline exactly; schema remains v5. The selected
bundle must contain only its six original files plus an exact run marker
binding its descriptor and carrying the interrupted release's own schema
(`v2`, or `supersede_unstarted_v1` for an unstarted-supersession successor) (and,
if present, the already-supported sealed empty legacy backup sidecars). When the
interrupted release is an unstarted-supersession successor, validation continues
through its own `superseded_unstarted_sha` link to the accepted V2 ancestor; that
inner release must still be sealed, unstarted (no run marker, no Runtime
acceptance directory) and match the same live baseline.

The selected control-owned 0700 acceptance directory may contain exactly
`nonexecutive-launchd-before.json` and `protected-group-membership.json`. Both
must be control-owned, single-link, 0400 JSON files without ACLs. Their exact
bytes and expected prefix shapes are checked, hashed into the new descriptor,
and rechecked before the successor's exclusive run marker is written.
`nonexecutive-launchd-before.json` holds exactly `sha256` and `labels_excluded`
(2). `protected-group-membership.json` holds exactly the eight keys the acceptance
producer writes: `passed` (true), `effective_members` (object),
`attended_worker_membership`, `control_definition_sha256` (64 lowercase hex),
`primary_gid_census` (`COMPLETE`), `name_members` and `uuid_members` (`EXACT`),
and `nested_groups` (`ABSENT`). `attended_worker_membership` is `null` when
control.json has no `fabric_attended_probe` stanza; otherwise exactly the ten
fields of `_attended_worker_membership` (`worker_user`/`worker_group`
`_mastermind_*` names of at most 31 characters, `worker_uid`/`worker_gid` integers in
400-499, `worker_id`, an absolute `worker_config_path`, a `provider_home` derived
from `worker_id`, and three 64-hex digests). Any other key set or shape is refused
as a schema drift; for the selected failed release the earlier six-key form is not
accepted. Unsafe aliases, changed namespace/receipts, summaries, canary receipts,
additional outputs or any Runtime delta refuse recovery. Only the existing trusted
Darwin `/var` alias is recognized; ordinary unstarted absence checks are unchanged.

An already-sealed `supersede_prejob_v1` link seen as a historical ancestor is
re-validated differently from the candidate. Descriptors sealed before the eight-key
receipt (the Oct 11 generation, such as the interrupted release `0123ad5a…`) bound
`prejob_evidence_sha256` over a `protected-group-membership.json` with exactly six
keys: `passed`, `effective_members`, `primary_gid_census`, `name_members`,
`uuid_members` and `nested_groups`, holding the same values as above. The
carry-chain walk (`validate_prior_carry_binding`, the only place that sets
`historical=True`) admits exactly two generations of that receipt: the current eight-key
form and this six-key form. Any other key set or value is refused with the same
schema-drift error, and the hash is still recomputed over the sealed bytes, so a
changed receipt still fails as drifted pre-Job evidence. `prepare` validates the
candidate with the flag unset and so requires the eight-key form. At acceptance start
the walk also visits the candidate's own selected link once; the strict
`validate_superseded_binding` call that follows it, which does not set the flag, still
refuses the six-key form. The launchd receipt, the file and directory modes, the
`/var` alias and the namespace checks are the same on both paths.

The old administrative canary is under the old release's checkout; it is kept.
The successor creates its own distinct sentinel normally. No sentinel is deleted
or reused to simulate a clean run.

The new release still needs its real install, provider readiness, full acceptance,
PASS summary/carry receipt and normal arming through the existing owners. A failed
attempt remains evidence on its original operation. This branch cannot carry a
later-stage acceptance, an unrelated supersede_preproof_v1 interruption, or an
unknown effect merely because an operator describes it as pre-Job.

Tests use isolated files and Runtime fixtures with explicit principal/service
test seams. They establish source behavior, not live installation or execution.
