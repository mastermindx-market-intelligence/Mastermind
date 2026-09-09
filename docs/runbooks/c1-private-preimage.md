# C1 private-host preimage

Status: source-only, operator-invoked, read-only evidence collector.

This collector describes the bounded Executive OS installation surface before
any uninstall, install, preparation, enrollment, activation, Runtime, tunnel,
provider, or worker action. A receipt is evidence for a later operator ruling;
it is never permission to mutate the host. The source-delivery wave that added
this collector did not execute it against a private host.

## Authority boundary

Run `ops/executive_os/c1_private_preimage.py` only after a separate, explicit
root-host START that names the expected release commit and tree. Normal
collection requires macOS and effective UID 0. The program does not invoke
`sudo`, write files, change metadata, signal a host-service PID, enumerate
processes, open sockets or databases, or enable, disable, load, unload, or start
a launchd service.

The only accepted collection arguments are:

```text
--expected-release-sha <40 lowercase hex>
--expected-tree-sha <40 lowercase hex>
```

`--describe` prints the static surface and may be used without root. It cannot
be combined with collection arguments. There are no alternate root, path,
label, command, user, timeout, output-file, or plugin arguments.

After separate host authorization, an operator may capture stdout through an
external, pre-authorized receipt mechanism. The collector itself only writes
canonical JSON to stdout:

```text
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  -I -S -B ops/executive_os/c1_private_preimage.py \
  --expected-release-sha <40-lowercase-hex-commit> \
  --expected-tree-sha <40-lowercase-hex-tree>
```

Do not use this example during source review or on an unapproved host.

## Frozen probe surface

The collector projects nine fixed content-bearing public/provenance documents:

- five LaunchDaemon plists: `control`, `worker.codex`, `backup`,
  `sol-state-relay`, and `agent-relay`;
- `control.json` and `worker-codex.json`;
- the pinned Python runtime provenance receipt;
- the pinned Codex attestation receipt.

It separately reads exactly one `.executive-release-manifest.json`, and only
under the release directory derived from the admitted expected SHA. Thus the
closed surface has nine fixed documents plus one exact-SHA manifest, while the
aggregate accepted content ceiling remains 9 MiB. Each individual content read
is limited to 1 MiB. JSON rejects duplicate keys. Plist decoding uses a
duplicate-rejecting mapping so XML plists—with or without a declaration—and
binary plists are rejected before a repeated key can overwrite its predecessor.
Plist parsing is in-process, and only validated projections enter the receipt.
Unknown fields are deliberately not projected.

Private config, tokens, keys, canaries, provider auth, DR, job, backup, relay,
and socket paths are metadata-only. Their bytes, hashes, values, prefixes, and
suffixes are never read or emitted. Metadata is restricted to lexical path,
existence, type, device, inode, link count, UID, GID, mode, size, `mtime_ns`,
and `ctime_ns`. Each frozen path has a closed expected object type and the
principal, group, and exact mode declared by its current owner. Private files
also require one hard link. The admitted release root follows the canonical
release-manifest rule instead of an invented duplicate verifier: root:wheel,
no group/other write, both service traversal bits, and no ACL. Socket paths
must be sockets, and fixed runtime directories must be directories.

Filesystem reads reject final symlinks and unexpected ancestor symlinks, require
read-only `O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK`, apply path-specific descriptor
type/owner/group/mode/link contracts, bind the metadata/ACL observation to the
opened descriptor and post-read named identity, recheck ancestor identities,
and reject torn observations. Metadata-only observations likewise compare the
complete admitted ancestor identity before and after the final `lstat`, even
when the final path is absent. The exact macOS
`/var -> /private/var` alias is the only accepted alias. ACL checks use the
macOS stat marker and bind pre/post device and inode.

The command adapter permits only:

```text
/bin/launchctl print-disabled system
/bin/launchctl print system/<one frozen label>
/bin/ps -o uid=,gid=,pid=,ppid= -p <exact positive launchd pid>
/usr/bin/stat -f %Sp <one frozen path>
```

Commands use no shell, a five-second total execution/settlement deadline, no
retry, acquisition-time bounded nonblocking output, `stdin=DEVNULL`, and
`close_fds=True`. One second of the deadline is reserved for terminating and
reaping only the directly created probe child. Custody begins immediately after
spawn, covers selector/stream setup and cleanup failures, and samples the
original monotonic deadline after potentially blocking operations before
accepting a result. A known exit observed after the boundary is a late, reaped
timeout; unknown termination, reap, or cleanup outcomes remain explicit
sanitized facts. Bytes returned by a bounded read are counted before the fresh
deadline decision, so late data remains rejected without losing its known byte
count. It never signals the host-service PID. Process output contains only UID,
GID, PID, and PPID for the exact positive PID reported by launchd. Raw stderr,
partial output, and arbitrary exception text are never serialized.

## Receipt and interpretation

The canonical schema is `mastermind.c1_private_preimage/v1`. Encoding is UTF-8
JSON with sorted keys, compact separators, finite values, and exactly one
trailing newline. Every receipt includes:

```text
schema, observed_at, expected_release_sha, expected_tree_sha,
state, classification, reason_codes, facts, probe_counts,
source_limits, mutation_count
```

`mutation_count` must always be integer zero.

States are:

- `FACTS`: the bounded observation settled;
- `DEGRADED`: a probe transport failed without a more specific settlement;
- `REFUSED`: arguments, platform, privilege, or an internal boundary refused;
- `UNSETTLED`: timeout, permission, ACL, command, process, or identity evidence
  could not be settled.

Non-`FACTS` receipts always classify as `UNKNOWN`. Settled classifications use
this precedence:

1. `UNSAFE`
2. `EFFECT_UNKNOWN`
3. `ACTIVE_FOREIGN`
4. `ACTIVE_OWNED`
5. `MATCHING_STOPPED`
6. `STALE_STOPPED`
7. `ABSENT_CLEAN`

`ACTIVE_OWNED` binds the frozen launchd label, loaded `program` and `arguments`
fields, exact disk ProgramArguments and working directory, the admitted expected
release, plist user/group, and the UID/GID returned for launchd's positive PID.
The process must also have launchd as its direct parent (`PPID == 1`).
Loaded arguments must exactly equal the internally retained validated disk
arguments; raw values are never projected. A different executable, entrypoint,
argument, release, principal, or settled non-launchd parent is
`ACTIVE_FOREIGN`; missing or ambiguous loaded/process identity is `UNSETTLED`.
None can fall through to owned.

`ABSENT_CLEAN` additionally requires coherent absence of the whole frozen
surface, all four principals, and every service. A residual socket, principal,
partial document set, generic launchctl error, or unrecognized launchd state
cannot become clean absence. `STALE_STOPPED` also requires all four expected
principals to be present and matching; stale documents with missing principals
remain `EFFECT_UNKNOWN`. Validated stale release identities are compared
internally but emitted only as `release_matches: false`; rejected schema,
principal, path, and provenance values never enter a receipt.

Exit codes describe receipt transport only:

- `0`: a canonical `FACTS` receipt was emitted;
- `2`: a canonical `DEGRADED` or `REFUSED` receipt was emitted;
- `3`: a canonical `UNSETTLED` receipt was emitted;
- `64`: arguments, platform, or effective UID were refused before collection,
  so no receipt was emitted.

A zero exit—including `UNSAFE`, `ACTIVE_FOREIGN`, or `EFFECT_UNKNOWN`—does not
authorize install, activation, enrollment, provider, Runtime, or production
work. Preserve the receipt and return it to the named operator/carrier for a
separate decision.
